from __future__ import annotations

import html
import logging
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Final
from uuid import uuid4

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from config import Settings, load_settings
from confirmation_store import (
    CONFIRM_ACTION,
    REJECT_ACTION,
    EDIT_ACTION,
    DURATION_ACTION,
    SLOT_ACTION,
    SAVE_UNTIMED_ACTION,
    ConfirmationStore,
    PendingTask,
)
from task_api_client import TaskApiClient, TaskApiError, TaskApiSubscriptionError
from finance_intent import FinanceIntent, detect_finance_query, extract_finance_intent
from task_extractor import TaskExtraction, TaskExtractor
from report_renderer import ReportPeriod, build_report, format_report_html, render_report_png
from secretary import (
    best_free_slots,
    conflict_warning_for_candidate,
    format_agenda_html,
    format_free_slots_html,
    free_slots,
    period_bounds,
    recommendations,
    tasks_in_period,
)
from transcriber import TranscriptionError, VoiceTranscriber


LOGGER = logging.getLogger(__name__)

SETTINGS_KEY: Final[str] = "settings"
TRANSCRIBER_KEY: Final[str] = "voice_transcriber"
TASK_EXTRACTOR_KEY: Final[str] = "task_extractor"
CONFIRMATION_STORE_KEY: Final[str] = "confirmation_store"
TASK_API_CLIENT_KEY: Final[str] = "task_api_client"
EDIT_STATE_KEY: Final[str] = "task_edit_token"
FINANCE_PENDING_KEY: Final[str] = "finance_pending"

ENTITLEMENT_MULTI_TASK: Final[str] = "multi_task_recognition"
ENTITLEMENT_SMART_SCHEDULING: Final[str] = "smart_scheduling"
ENTITLEMENT_ADVANCED_REPORTS: Final[str] = "advanced_reports"
ENTITLEMENT_FINANCE: Final[str] = "finance"
ENTITLEMENT_FINANCE_TELEGRAM: Final[str] = "finance_telegram"
LIMIT_AI_ACTIONS: Final[str] = "ai_actions_monthly"
LIMIT_VOICE_MESSAGES: Final[str] = "voice_messages_monthly"

# Telegram Bot API networking. python-telegram-bot defaults to short 5s
# connect/read/write timeouts. A slightly more tolerant configuration is
# preferable for desktop/VPN/mobile networks and large report uploads.
TELEGRAM_CONNECT_TIMEOUT_SECONDS: Final[float] = 20.0
TELEGRAM_READ_TIMEOUT_SECONDS: Final[float] = 30.0
TELEGRAM_WRITE_TIMEOUT_SECONDS: Final[float] = 30.0
TELEGRAM_MEDIA_WRITE_TIMEOUT_SECONDS: Final[float] = 60.0
TELEGRAM_POOL_TIMEOUT_SECONDS: Final[float] = 10.0


def _update_user_id(update: Update) -> int:
    user = update.effective_user
    if user is None:
        raise RuntimeError("Telegram user is unavailable")
    return user.id


def _plan_label(snapshot: dict[str, Any]) -> str:
    plan = str(snapshot.get("plan", "free"))
    return {"free": "Free", "plus": "Plus", "full": "Full"}.get(plan, plan.title())


def _has_entitlement(snapshot: dict[str, Any], key: str) -> bool:
    entitlements = snapshot.get("entitlements")
    return bool(entitlements.get(key)) if isinstance(entitlements, dict) else False


async def _subscription_snapshot(context: ContextTypes.DEFAULT_TYPE, user_id: int | str) -> dict[str, Any]:
    return await _get_task_api_client(context).get_subscription(user_id)


async def _consume_subscription_usage(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int | str,
    key: str,
    *,
    amount: int = 1,
) -> tuple[bool, str | None]:
    try:
        await _get_task_api_client(context).consume_subscription_usage(user_id, key, amount=amount)
        return True, None
    except TaskApiSubscriptionError as error:
        if error.status_code in {403, 429}:
            return False, error.detail or str(error)
        raise


async def _deliver_subscription_notifications(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
) -> None:
    client = _get_task_api_client(context)
    try:
        # Refresh entitlement state first so expired trial/overrides create their
        # audit event and notification before we fetch the notification queue.
        await client.get_subscription(user_id)
        notifications = await client.pending_notifications(user_id)
    except TaskApiError:
        LOGGER.warning("Could not load subscription notifications for user %s", user_id)
        return
    for notification in notifications[:10]:
        notification_id = notification.get("id")
        title = html.escape(str(notification.get("title") or "Smart Planner"))
        message = html.escape(str(notification.get("message") or ""))
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎁 <b>{title}</b>\n\n{message}",
                parse_mode=ParseMode.HTML,
            )
            if isinstance(notification_id, int):
                await client.mark_notification_delivered(user_id, notification_id)
        except Exception:
            LOGGER.exception("Could not deliver subscription notification %s", notification_id)
            break


def _upgrade_text(feature: str, *, plan: str = "Plus") -> str:
    return f"🔒 {feature} доступно на тарифе {plan}. Текущие данные сохраняются; можно продолжать использовать базовые функции."


async def access_guard_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Регистрирует заявку и пропускает только активных пользователей."""

    user = update.effective_user
    if user is None:
        raise ApplicationHandlerStop
    settings = _get_settings(context)
    client = _get_task_api_client(context)
    try:
        if user.id == settings.telegram_admin_user_id:
            await client.bootstrap_admin(
                user_id=user.id,
                username=user.username,
                display_name=user.full_name,
            )
            return
        record = await client.get_current_user(user.id)
        if record is None:
            response = await client.register_user(
                user_id=user.id,
                username=user.username,
                display_name=user.full_name,
            )
            record = response.get("user", {})
            if bool(response.get("created")):
                username = f"@{user.username}" if user.username else "не указан"
                await context.bot.send_message(
                    chat_id=settings.telegram_admin_user_id,
                    text=(
                        "🆕 <b>Новая заявка</b>\n\n"
                        f"Имя: {html.escape(user.full_name)}\n"
                        f"Username: {html.escape(username)}\n"
                        f"Telegram ID: <code>{user.id}</code>"
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "✅ Одобрить",
                            callback_data=f"admin:do:active:{user.id}",
                        ),
                        InlineKeyboardButton(
                            "❌ Отклонить",
                            callback_data=f"admin:do:rejected:{user.id}",
                        ),
                    ]]),
                )
        status_value = str(record.get("status", "pending"))
        if status_value == "active":
            chat = update.effective_chat
            if chat is not None:
                await _deliver_subscription_notifications(context, user.id, chat.id)
            return
        messages = {
            "pending": "Заявка отправлена администратору и ожидает решения.",
            "blocked": "Доступ к Smart Planner временно заблокирован.",
            "deactivated": "Аккаунт деактивирован. Обратитесь к администратору.",
            "rejected": "Заявка отклонена администратором.",
        }
        await _reply_access_message(update, messages.get(status_value, "Доступ пока не разрешён."))
    except TaskApiError:
        LOGGER.exception("Could not verify Telegram user access")
        await _reply_access_message(update, "Не удалось проверить доступ. Убедитесь, что Task API запущен.")
    raise ApplicationHandlerStop


async def _reply_access_message(update: Update, text: str) -> None:
    if update.callback_query is not None:
        await update.callback_query.answer(text, show_alert=True)
    elif update.effective_message is not None:
        await update.effective_message.reply_text(text)

async def start_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Обрабатывает команду /start."""

    del context

    message = update.effective_message

    if message is None:
        return

    await message.reply_text(
        "Привет! Я помогу разобрать задачи и аккуратно разместить их "
        "во внутреннем календаре Smart Planner.\n\n"
        "Можно отправить одну или сразу несколько задач текстом или голосом. "
        "Например:\n"
        "«Завтра в 10 стоматолог, после него заехать в магазин, "
        "вечером час английского и срочно отправить отчёт до 18:00»\n\n"
        "Я разделю сообщение на задачи, распознаю дату, время, длительность, "
        "приоритет и дедлайн. Для гибких задач предложу до трёх свободных "
        "окон, а конфликтующее время не сохраню без решения пользователя.\n\n"
        "Каждую найденную задачу можно подтвердить, изменить или пропустить. "
        "Задачу без конкретного времени можно оставить просто на выбранную дату.\n\n"
        "Команды секретаря: /menu, /today, /week, /tasks, /free, /finance, /report. "
        "Подробные примеры — /help.",
        reply_markup=_secretary_menu(),
    )


async def help_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Показывает примеры поддерживаемых формулировок."""

    del context

    message = update.effective_message

    if message is None:
        return

    await message.reply_text(
        "Как ставить задачи:\n\n"
        "• Точное время: «Завтра в 15:00 встреча с Иваном»\n"
        "• Гибкое время: «Завтра вечером час английского»\n"
        "• Без времени: «Завтра купить продукты»\n"
        "• С длительностью: «Завтра 2 часа поработать над проектом»\n"
        "• С приоритетом: «Срочно подготовить презентацию завтра»\n"
        "• С дедлайном: «Отправить отчёт до пятницы до 18:00»\n"
        "• Несколько задач: «Завтра в 10 стоматолог, после него магазин, "
        "вечером час английского и отправить отчёт до 18»\n\n"
        "Если для размещения не хватает длительности, я предложу 30 минут, "
        "1 час, 2 часа или ввод своего значения. Для гибкой задачи покажу "
        "до трёх свободных окон. Если точное время занято — предупрежу и "
        "предложу альтернативы, не создавая наложение.\n\n"
        "При нескольких задачах они подтверждаются по очереди: "
        "✅ подтвердить, ✏️ изменить или ❌ пропустить.\n\n"
        "Финансы: «Потратил 1450 рублей на продукты», «Получил 120000 зарплату», "
        "«Перевёл 20 тысяч на накопительный», «Сколько осталось денег?» или "
        "«На что больше всего трачу?». Любая запись денег сначала требует подтверждения. "
        "Команда /finance показывает сводку и отчёты за сегодня, неделю, месяц и год.\n\n"
        "Команды: /menu, /today, /week, /tasks, /free, /finance, /settings, /report."
    )


async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Открывает Telegram-only панель управления пользователями."""

    if _update_user_id(update) != _get_settings(context).telegram_admin_user_id:
        if update.effective_message is not None:
            await update.effective_message.reply_text("Команда доступна только администратору.")
        return
    search = " ".join(context.args).strip() if context.args else None
    await _show_admin_users(update, context, search=search)


async def _show_admin_users(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    search: str | None = None,
) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    client = _get_task_api_client(context)
    admin_id = _get_settings(context).telegram_admin_user_id
    try:
        users = await client.list_users(admin_id)
    except TaskApiError:
        await context.bot.send_message(chat_id=chat.id, text="Не удалось загрузить пользователей.")
        return
    status_icons = {
        "pending": "⏳",
        "active": "✅",
        "blocked": "⛔",
        "deactivated": "⏸",
        "rejected": "❌",
    }
    keyboard = []
    normalized_search = search.casefold() if search else None
    for item in users:
        user_id = str(item.get("telegramUserId"))
        if str(item.get("role")) == "admin":
            continue
        haystack = " ".join((
            user_id,
            str(item.get("displayName") or ""),
            str(item.get("username") or ""),
        )).casefold()
        if normalized_search is not None and normalized_search not in haystack:
            continue
        title = str(item.get("displayName") or item.get("username") or user_id)
        icon = status_icons.get(str(item.get("status")), "•")
        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {title[:32]}",
                callback_data=f"admin:view:user:{user_id}",
            )
        ])
    keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="admin:menu:users:0")])
    pending = sum(str(item.get("status")) == "pending" for item in users)
    await context.bot.send_message(
        chat_id=chat.id,
        text=(
            "🛡 <b>Админ-панель</b>\n\n"
            f"Пользователей: {max(0, len(users) - 1)}\n"
            f"Ожидают решения: {pending}\n\n"
            "Выберите пользователя:\n\nПоиск: /admin имя, username или Telegram ID"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    settings = _get_settings(context)
    if query.from_user.id != settings.telegram_admin_user_id:
        await query.answer("Доступно только администратору", show_alert=True)
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) < 4:
        return
    category, action, user_id = parts[1], parts[2], parts[3]
    if category == "menu":
        await _show_admin_users(update, context)
        return
    client = _get_task_api_client(context)
    admin_id = settings.telegram_admin_user_id
    if category == "view":
        try:
            users = await client.list_users(admin_id)
        except TaskApiError:
            await query.edit_message_text("Не удалось загрузить пользователя.")
            return
        user = next((item for item in users if str(item.get("telegramUserId")) == user_id), None)
        if user is None:
            await query.edit_message_text("Пользователь уже удалён.")
            return
        await _show_admin_user_card(query, user)
        return
    if category == "ask" and action == "delete":
        await query.edit_message_text(
            "⚠️ Удалить аккаунт и весь его календарь? Это действие требует ещё одного подтверждения.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Продолжить", callback_data=f"admin:ask2:delete:{user_id}"),
                InlineKeyboardButton("Отмена", callback_data=f"admin:view:user:{user_id}"),
            ]]),
        )
        return
    if category == "ask2" and action == "delete":
        await query.edit_message_text(
            "🚨 Последнее подтверждение: данные пользователя будут удалены навсегда.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Удалить навсегда", callback_data=f"admin:do:delete:{user_id}"),
                InlineKeyboardButton("Отмена", callback_data=f"admin:view:user:{user_id}"),
            ]]),
        )
        return
    if category != "do":
        return
    try:
        if action == "delete":
            await client.delete_user(admin_user_id=admin_id, user_id=user_id)
            await query.edit_message_text("Пользователь и его календарь удалены.")
            return
        user = await client.set_user_status(
            admin_user_id=admin_id,
            user_id=user_id,
            status=action,
        )
        notifications = {
            "active": "✅ Администратор открыл вам доступ к Smart Planner.",
            "rejected": "❌ Администратор отклонил заявку.",
            "blocked": "⛔ Доступ к Smart Planner временно заблокирован.",
            "deactivated": "⏸ Аккаунт Smart Planner деактивирован.",
        }
        if action in notifications:
            try:
                await context.bot.send_message(chat_id=int(user_id), text=notifications[action])
            except Exception:
                LOGGER.warning("Could not notify user %s", user_id, exc_info=True)
        await _show_admin_user_card(query, user)
    except TaskApiError:
        await query.edit_message_text("Не удалось выполнить административное действие.")


async def _show_admin_user_card(query: Any, user: dict[str, Any]) -> None:
    user_id = str(user.get("telegramUserId"))
    username = f"@{user['username']}" if user.get("username") else "не указан"
    status_value = str(user.get("status"))
    text = (
        f"👤 <b>{html.escape(str(user.get('displayName', user_id)))}</b>\n\n"
        f"Telegram ID: <code>{html.escape(user_id)}</code>\n"
        f"Username: {html.escape(username)}\n"
        f"Статус: <b>{html.escape(status_value)}</b>\n"
        f"Подписка: <b>{html.escape(str(user.get('subscriptionPlan', 'free')).upper())}</b> · {html.escape(str(user.get('subscriptionStatus', 'active')))}\n"
        f"Задач: {int(user.get('taskCount', 0))}\n"
        f"Целей: {int(user.get('goalCount', 0))}\n"
        f"Групп: {int(user.get('groupCount', 0))}\n"
        f"Регистрация: {html.escape(str(user.get('registeredAt', '—'))[:10])}\n"
        f"Последняя активность: {html.escape(str(user.get('lastActivityAt', '—'))[:16])}"
    )
    buttons: list[list[InlineKeyboardButton]] = []
    if status_value in {"pending", "rejected", "deactivated", "blocked"}:
        buttons.append([InlineKeyboardButton("✅ Активировать", callback_data=f"admin:do:active:{user_id}")])
    if status_value == "pending":
        buttons.append([InlineKeyboardButton("❌ Отклонить", callback_data=f"admin:do:rejected:{user_id}")])
    if status_value == "active":
        buttons.append([
            InlineKeyboardButton("⛔ Заблокировать", callback_data=f"admin:do:blocked:{user_id}"),
            InlineKeyboardButton("⏸ Деактивировать", callback_data=f"admin:do:deactivated:{user_id}"),
        ])
    buttons.append([InlineKeyboardButton("🗑 Удалить", callback_data=f"admin:ask:delete:{user_id}")])
    buttons.append([InlineKeyboardButton("◀️ К списку", callback_data="admin:menu:users:0")])
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает выбор периода или сразу формирует запрошенный отчёт."""
    message = update.effective_message
    if message is None:
        return
    period = context.args[0].lower() if context.args else None
    if period in {"week", "month"}:
        await _send_report(update, context, period)
        return
    await message.reply_text(
        "За какой период сформировать отчёт?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📅 Неделя", callback_data="report:week"),
            InlineKeyboardButton("🗓 Месяц", callback_data="report:month"),
        ]]),
    )


async def report_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    _, period = query.data.split(":", maxsplit=1)
    if period not in {"week", "month"}:
        await query.answer("Некорректный период", show_alert=True)
        return
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    await _send_report(update, context, period)


async def _send_report(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    period: ReportPeriod,
) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    settings = _get_settings(context)
    client = _get_task_api_client(context)
    try:
        user_id = _update_user_id(update)
        subscription = await client.get_subscription(user_id)
        tasks = await client.list_tasks(user_id)
        if not _has_entitlement(subscription, ENTITLEMENT_ADVANCED_REPORTS):
            report = build_report(
                tasks=tasks,
                groups=[],
                goals=[],
                period=period,
                now=datetime.now(settings.timezone),
            )
            rate = round(report.completion_rate * 100)
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"📊 <b>{report.period_label} · базовый отчёт</b>\n\n"
                    f"Выполнено: <b>{report.completed}/{report.total}</b>\n"
                    f"Прогресс: <b>{rate}%</b>\n"
                    f"Пропущено: {report.missed}\n"
                    f"Ожидает: {report.pending}\n\n"
                    "Расширенные графики, Deep Work и аналитика доступны на Plus/Full."
                ),
                parse_mode=ParseMode.HTML,
            )
            return
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.UPLOAD_PHOTO)
        groups = await client.list_groups(user_id)
        try:
            goals = await client.list_goals(user_id)
        except (TaskApiError, AttributeError):
            LOGGER.warning("Task API goals are unavailable; rendering report without habits")
            goals = []
        report = build_report(
            tasks=tasks,
            groups=groups,
            goals=goals,
            period=period,
            now=datetime.now(settings.timezone),
        )
        image = BytesIO(render_report_png(report))
        image.name = f"smart-planner-{period}.png"
        await context.bot.send_photo(
            chat_id=chat.id,
            photo=InputFile(image, filename=image.name),
            caption=format_report_html(report),
            parse_mode=ParseMode.HTML,
        )
    except TaskApiError:
        LOGGER.exception("Could not load report data from Task API")
        await context.bot.send_message(
            chat_id=chat.id,
            text="Не удалось сформировать отчёт. Проверь, что общий Task API запущен.",
        )
    except Exception:
        LOGGER.exception("Could not render Telegram report")
        await context.bot.send_message(
            chat_id=chat.id,
            text="Не удалось подготовить изображение отчёта. Попробуй ещё раз.",
        )


def _rubles(cents: int) -> str:
    negative = cents < 0
    absolute = abs(cents)
    rubles, kopeks = divmod(absolute, 100)
    grouped = f"{rubles:,}".replace(",", " ")
    fraction = "" if kopeks == 0 else f",{kopeks:02d}"
    return f"{'−' if negative else ''}{grouped}{fraction} ₽"


def _match_named(items: list[dict[str, Any]], hint: str | None, *, field: str = "name") -> dict[str, Any] | None:
    if not items:
        return None
    if hint:
        normalized = hint.casefold().replace("ё", "е")
        for item in items:
            name = str(item.get(field, "")).casefold().replace("ё", "е")
            if normalized in name or name in normalized:
                return item
    return next((item for item in items if bool(item.get("isDefault"))), items[0])


async def finance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    try:
        user_id = _update_user_id(update)
        client = _get_task_api_client(context)
        subscription = await client.get_subscription(user_id)
        summary = await client.finance_summary(user_id)
    except TaskApiError:
        await context.bot.send_message(chat_id=chat.id, text="Не удалось загрузить финансовые данные. Проверьте Task API.")
        return
    accounts = summary.get("accounts") or []
    if not accounts:
        can_write_finance = _has_entitlement(subscription, ENTITLEMENT_FINANCE)
        message = (
            "💳 <b>Финансы</b>\n\nСчета пока не созданы. Добавьте первый счёт в веб-разделе «Финансы», "
            "после этого расходы можно будет записывать прямо сообщениями в Telegram."
            if can_write_finance
            else "💳 <b>Финансы · Full</b>\n\nФинансовый центр доступен на тарифе Full. "
                 "Если у вас раньше был Full, существующие финансовые данные остаются доступны только для чтения."
        )
        await context.bot.send_message(
            chat_id=chat.id,
            text=message,
            parse_mode=ParseMode.HTML,
            reply_markup=_secretary_menu(),
        )
        return
    category_lines = []
    for item in (summary.get("categorySpend") or [])[:3]:
        category_lines.append(f"• {html.escape(str(item.get('name', 'Категория')))} — {_rubles(int(item.get('amountCents', 0)))}")
    categories = "\n".join(category_lines) if category_lines else "• Пока нет расходов"
    await context.bot.send_message(
        chat_id=chat.id,
        text=(
            "💳 <b>Финансы</b>\n\n"
            f"Общий баланс: <b>{_rubles(int(summary.get('totalBalanceCents', 0)))}</b>\n"
            f"Расходы месяца: <b>{_rubles(int(summary.get('monthExpenseCents', 0)))}</b>\n"
            f"Сегодня: {_rubles(int(summary.get('todayExpenseCents', 0)))}\n\n"
            f"<b>Основные категории</b>\n{categories}\n\n"
            "Можно написать: «Потратил 1450 рублей на продукты», «Получил 120000 зарплату», "
            "«Перевёл 20 тысяч на накопительный» или «На что больше всего трачу?»"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Сегодня", callback_data="finrep:day"), InlineKeyboardButton("Неделя", callback_data="finrep:week")],
            [InlineKeyboardButton("Месяц", callback_data="finrep:month"), InlineKeyboardButton("Год", callback_data="finrep:year")],
            [InlineKeyboardButton("◀️ Меню", callback_data="sec:menu:home")],
        ]),
    )


async def finance_report_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or query.data is None or user is None:
        return
    await query.answer()
    period = query.data.split(":", 1)[1] if ":" in query.data else "month"
    labels = {"day": "Сегодня", "week": "Неделя", "month": "Месяц", "year": "Год"}
    try:
        report = await _get_task_api_client(context).finance_report(user.id, period)
    except TaskApiError:
        await query.edit_message_text("Не удалось сформировать финансовый отчёт. Проверьте Task API.", reply_markup=_secretary_menu())
        return
    categories = report.get("categorySpend") or []
    lines = [
        f"• {html.escape(str(item.get('name', 'Категория')))} — {_rubles(int(item.get('amountCents', 0)))}"
        for item in categories[:5]
    ]
    categories_text = "\n".join(lines) if lines else "• Расходов за период нет"
    await query.edit_message_text(
        f"📊 <b>Финансовый отчёт · {labels.get(period, 'Период')}</b>\n\n"
        f"Расходы: <b>{_rubles(int(report.get('expenseCents', 0)))}</b>\n"
        f"Среднее в день: {_rubles(int(report.get('averageDailyExpenseCents', 0)))}\n"
        f"Текущий общий баланс: <b>{_rubles(int(report.get('totalBalanceCents', 0)))}</b>\n\n"
        f"<b>Категории</b>\n{categories_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Сегодня", callback_data="finrep:day"), InlineKeyboardButton("Неделя", callback_data="finrep:week")],
            [InlineKeyboardButton("Месяц", callback_data="finrep:month"), InlineKeyboardButton("Год", callback_data="finrep:year")],
            [InlineKeyboardButton("◀️ Меню", callback_data="sec:menu:home")],
        ]),
    )


async def _try_handle_finance_text(*, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return False
    query = detect_finance_query(text)
    client = _get_task_api_client(context)
    if query is not None:
        try:
            summary = await client.finance_summary(user.id)
        except TaskApiError:
            await message.reply_text("Не удалось получить финансовую сводку. Проверьте Task API.")
            return True
        if query == "balance":
            await message.reply_text(f"💰 На счетах сейчас: <b>{_rubles(int(summary.get('totalBalanceCents', 0)))}</b>", parse_mode=ParseMode.HTML)
        elif query == "month_expense":
            await message.reply_text(f"📉 Расходы в этом месяце: <b>{_rubles(int(summary.get('monthExpenseCents', 0)))}</b>\nВ среднем в день: {_rubles(int(summary.get('averageDailyExpenseCents', 0)))}", parse_mode=ParseMode.HTML)
        else:
            items = summary.get("categorySpend") or []
            if not items:
                await message.reply_text("Пока недостаточно расходов, чтобы определить основные категории.")
            else:
                lines = [f"{index}. {html.escape(str(item.get('name', 'Категория')))} — {_rubles(int(item.get('amountCents', 0)))}" for index, item in enumerate(items[:5], 1)]
                await message.reply_text("📊 <b>Куда уходят деньги</b>\n\n" + "\n".join(lines), parse_mode=ParseMode.HTML)
        return True

    intent = extract_finance_intent(text)
    if intent is None:
        return False
    try:
        snapshot = await client.get_subscription(user.id)
    except TaskApiError:
        await message.reply_text("Не удалось проверить подписку. Попробуйте ещё раз позже.")
        return True
    if not _has_entitlement(snapshot, ENTITLEMENT_FINANCE_TELEGRAM):
        await message.reply_text(
            "🔒 Финансовые данные доступны для просмотра, но новые операции через Telegram можно записывать только на Full. "
            "Если Full закончился, существующие счета и история сохранены в режиме только чтения."
        )
        return True
    try:
        accounts = await client.list_finance_accounts(user.id)
        categories = await client.list_finance_categories(user.id)
    except TaskApiError:
        await message.reply_text("Не удалось проверить финансовые счета. Проверьте Task API.")
        return True
    if not accounts:
        await message.reply_text("Сначала создайте хотя бы один счёт в веб-разделе «Финансы».")
        return True
    source = _match_named(accounts, intent.account_hint)
    if source is None:
        await message.reply_text("Не удалось определить счёт для операции.")
        return True
    destination = None
    if intent.kind == "transfer":
        candidates = [item for item in accounts if str(item.get("id")) != str(source.get("id"))]
        destination = _match_named(candidates, intent.to_account_hint)
        if destination is None:
            names = ", ".join(str(item.get("name")) for item in candidates)
            await message.reply_text(f"Не удалось определить счёт назначения. Доступные счета: {names}.")
            return True
    category = None
    if intent.kind == "expense":
        category = next((item for item in categories if str(item.get("id")) == intent.category_hint), None)
        category = category or next((item for item in categories if str(item.get("id")) == "other"), None)
    now = datetime.now(timezone.utc)
    token = uuid4().hex[:12]
    payload = {
        "id": uuid4().hex,
        "type": intent.kind,
        "amountCents": intent.amount_cents,
        "accountId": str(source.get("id")),
        "toAccountId": str(destination.get("id")) if destination else None,
        "categoryId": str(category.get("id")) if category else None,
        "note": intent.note[:500],
        "occurredAt": now.isoformat(),
        "createdAt": now.isoformat(),
    }
    pending = context.user_data.setdefault(FINANCE_PENDING_KEY, {})
    if not isinstance(pending, dict):
        pending = {}
        context.user_data[FINANCE_PENDING_KEY] = pending
    pending[token] = payload
    kind_text = {"expense": "Расход", "income": "Доход", "transfer": "Перевод"}[intent.kind]
    detail = f"Категория: {html.escape(str(category.get('name')))}\n" if category else ""
    if destination:
        detail += f"На счёт: {html.escape(str(destination.get('name')))}\n"
    await message.reply_text(
        f"💳 <b>{kind_text}</b>\n\n"
        f"Сумма: <b>{_rubles(intent.amount_cents)}</b>\n"
        f"Счёт: {html.escape(str(source.get('name')))}\n"
        f"{detail}"
        "\nЗаписать операцию?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Добавить", callback_data=f"fin:ok:{token}"), InlineKeyboardButton("❌ Отмена", callback_data=f"fin:cancel:{token}")]]),
    )
    return True


async def finance_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or query.data is None or user is None:
        return
    await query.answer()
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    action, token = parts[1], parts[2]
    pending = context.user_data.get(FINANCE_PENDING_KEY)
    payload = pending.get(token) if isinstance(pending, dict) else None
    if not isinstance(payload, dict):
        await query.edit_message_text("Подтверждение финансовой операции устарело.")
        return
    if action == "cancel":
        pending.pop(token, None)
        await query.edit_message_text("Операция отменена. Финансовые данные не изменены.", reply_markup=_secretary_menu())
        return
    if action != "ok":
        return
    try:
        snapshot = await _subscription_snapshot(context, user.id)
        if not _has_entitlement(snapshot, ENTITLEMENT_FINANCE_TELEGRAM):
            await query.edit_message_text(
                "🔒 Запись финансовых операций доступна только на Full. Черновик не был сохранён.",
                reply_markup=_secretary_menu(),
            )
            return
        saved = await _get_task_api_client(context).create_finance_transaction(payload=payload, user_id=user.id)
    except TaskApiError:
        await query.edit_message_text("Не удалось записать операцию. Данные не изменены; попробуйте ещё раз.")
        return
    pending.pop(token, None)
    kind_text = {"expense": "Расход", "income": "Доход", "transfer": "Перевод"}.get(str(saved.get("type")), "Операция")
    await query.edit_message_text(f"✅ {kind_text} {_rubles(int(saved.get('amountCents', 0)))} записан.", reply_markup=_secretary_menu())


def _secretary_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Сегодня", callback_data="sec:menu:today"), InlineKeyboardButton("🗓 Неделя", callback_data="sec:menu:week")],
        [InlineKeyboardButton("📋 Задачи", callback_data="sec:menu:tasks"), InlineKeyboardButton("🟢 Свободное время", callback_data="sec:menu:free")],
        [InlineKeyboardButton("💳 Финансы", callback_data="sec:menu:finance"), InlineKeyboardButton("📊 Отчёт", callback_data="sec:menu:report")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="sec:menu:settings")],
    ])


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is not None:
        await message.reply_text("🤝 <b>Секретарь Smart Planner</b>\n\nВыберите действие:", parse_mode=ParseMode.HTML, reply_markup=_secretary_menu())


async def today_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_agenda(update, context, "today")


async def week_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_agenda(update, context, "week")


async def tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    client = _get_task_api_client(context)
    settings = _get_settings(context)
    try:
        tasks = await client.list_tasks(_update_user_id(update))
        today = datetime.now(settings.timezone).date()
        upcoming = [task for task in tasks_in_period(tasks, today, today + timedelta(days=30)) if not bool(task.get("isCompleted"))]
        if not upcoming:
            await context.bot.send_message(chat_id=chat.id, text="📋 Активных задач на ближайшие 30 дней нет.", reply_markup=_secretary_menu())
            return
        keyboard = [[InlineKeyboardButton(
            f"{str(task['date'])[5:]} · {task.get('title', 'Задача')[:32]}",
            callback_data=f"sec:view:{task['id']}",
        )] for task in upcoming[:15]]
        keyboard.append([InlineKeyboardButton("◀️ Меню", callback_data="sec:menu:home")])
        await context.bot.send_message(chat_id=chat.id, text="📋 <b>Активные задачи</b>\nВыберите задачу:", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    except TaskApiError:
        await context.bot.send_message(chat_id=chat.id, text="Не удалось загрузить задачи. Проверьте Task API.")


async def free_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    client = _get_task_api_client(context)
    settings = _get_settings(context)
    try:
        user_id = _update_user_id(update)
        snapshot = await client.get_subscription(user_id)
        if not _has_entitlement(snapshot, ENTITLEMENT_SMART_SCHEDULING):
            await context.bot.send_message(
                chat_id=chat.id,
                text=_upgrade_text("Поиск свободных окон"),
                reply_markup=_secretary_menu(),
            )
            return
        tasks = await client.list_tasks(user_id)
        today = datetime.now(settings.timezone).date()
        await context.bot.send_message(chat_id=chat.id, text=format_free_slots_html(free_slots(tasks, today), today), parse_mode=ParseMode.HTML, reply_markup=_secretary_menu())
    except TaskApiError:
        await context.bot.send_message(chat_id=chat.id, text="Не удалось найти свободные окна. Проверьте Task API.")


async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    settings = _get_settings(context)
    await context.bot.send_message(
        chat_id=chat.id,
        text=("⚙️ <b>Настройки секретаря</b>\n\n"
              "Режим: отдельный календарь пользователя\n"
              f"Часовой пояс: {html.escape(settings.app_timezone)}\n"
              "Рабочее время: 09:00–18:00\n"
              "Перерыв между задачами: 15 минут\n"
              "Изменения календаря: только после подтверждения"),
        parse_mode=ParseMode.HTML,
        reply_markup=_secretary_menu(),
    )


async def _send_agenda(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    client = _get_task_api_client(context)
    settings = _get_settings(context)
    try:
        tasks, groups = await client.list_tasks(_update_user_id(update)), await client.list_groups(_update_user_id(update))
        today = datetime.now(settings.timezone).date()
        start, end = period_bounds(period, today)
        selected = tasks_in_period(tasks, start, end)
        title = f"Сегодня · {today:%d.%m.%Y}" if period == "today" else f"Неделя · {start:%d.%m}–{end:%d.%m}"
        await context.bot.send_message(chat_id=chat.id, text=format_agenda_html(selected, title=title, groups=groups), parse_mode=ParseMode.HTML, reply_markup=_secretary_menu())
    except TaskApiError:
        await context.bot.send_message(chat_id=chat.id, text="Не удалось сверить расписание с календарём. Проверьте Task API.")


async def secretary_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat = update.effective_chat
    if query is None or query.data is None or chat is None:
        return
    await query.answer()
    parts = query.data.split(":", maxsplit=3)
    if len(parts) < 3:
        return
    category = parts[1]
    if category == "menu":
        action = parts[2]
        if action == "home":
            await query.edit_message_text("🤝 <b>Секретарь Smart Planner</b>\n\nВыберите действие:", parse_mode=ParseMode.HTML, reply_markup=_secretary_menu())
        elif action == "today":
            await _send_agenda(update, context, "today")
        elif action == "week":
            await _send_agenda(update, context, "week")
        elif action == "tasks":
            await tasks_handler(update, context)
        elif action == "free":
            await free_handler(update, context)
        elif action == "finance":
            await finance_handler(update, context)
        elif action == "report":
            await context.bot.send_message(chat_id=chat.id, text="Выберите период отчёта:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📅 Неделя", callback_data="report:week"), InlineKeyboardButton("🗓 Месяц", callback_data="report:month")]]))
        elif action == "settings":
            await settings_handler(update, context)
        return
    if category == "cancel":
        await query.edit_message_text("Действие отменено. Календарь не изменён.", reply_markup=_secretary_menu())
        return
    if category == "view":
        action = "view"
        task_id = parts[2]
    else:
        if len(parts) < 4:
            return
        action = parts[2]
        task_id = parts[3]
    client = _get_task_api_client(context)
    try:
        tasks = await client.list_tasks(_update_user_id(update))
        task = next((item for item in tasks if str(item.get("id")) == task_id), None)
        if task is None:
            await query.edit_message_text("Задача уже не существует.", reply_markup=_secretary_menu())
            return
        if category == "view":
            await _show_task(query, task)
        elif category == "ask":
            await _ask_task_action(query, task, action, tasks)
        elif category == "do":
            await _perform_task_action(query, context, task, action)
    except TaskApiError:
        await query.edit_message_text("Не удалось выполнить действие. Календарь не изменён.", reply_markup=_secretary_menu())


async def _show_task(query: Any, task: dict[str, Any]) -> None:
    start = task.get("startMinute")
    duration = task.get("durationMinutes") or (60 if start is not None else None)
    time_text = "весь день" if start is None else f"{int(start)//60:02d}:{int(start)%60:02d}–{(int(start)+int(duration))//60:02d}:{(int(start)+int(duration))%60:02d}"
    text = (f"📌 <b>{html.escape(str(task.get('title', 'Задача')))}</b>\n\n"
            f"Дата: {date.fromisoformat(str(task['date'])):%d.%m.%Y}\n"
            f"Время: {time_text}\n"
            f"Приоритет: {html.escape(str(task.get('priority', 'normal')))}")
    buttons = []
    if not bool(task.get("isCompleted")):
        buttons.append([InlineKeyboardButton("✅ Выполнить", callback_data=f"sec:ask:complete:{task['id']}"), InlineKeyboardButton("➡️ На следующий день", callback_data=f"sec:ask:tomorrow:{task['id']}")])
        buttons.append([InlineKeyboardButton("🔺 Сменить приоритет", callback_data=f"sec:ask:priority:{task['id']}")])
    buttons.append([InlineKeyboardButton("🗑 Удалить", callback_data=f"sec:ask:delete:{task['id']}"), InlineKeyboardButton("◀️ Меню", callback_data="sec:menu:home")])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))


async def _ask_task_action(query: Any, task: dict[str, Any], action: str, tasks: list[dict[str, Any]]) -> None:
    labels = {"complete": "отметить выполненной", "tomorrow": "перенести на следующий день", "priority": "сменить приоритет", "delete": "удалить"}
    warning = ""
    if action == "tomorrow":
        candidate = {**task, "date": (date.fromisoformat(str(task["date"])) + timedelta(days=1)).isoformat()}
        conflict = conflict_warning_for_candidate([item for item in tasks if str(item.get("id")) != str(task["id"])], candidate)
        if conflict:
            warning = f"\n\n{html.escape(conflict)}"
    await query.edit_message_text(
        f"Подтвердите действие: <b>{labels.get(action, action)}</b>\nЗадача: {html.escape(str(task.get('title')))}{warning}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"sec:do:{action}:{task['id']}"),
            InlineKeyboardButton("❌ Отменить", callback_data="sec:cancel:action"),
        ]]),
    )


async def _perform_task_action(query: Any, context: ContextTypes.DEFAULT_TYPE, task: dict[str, Any], action: str) -> None:
    client = _get_task_api_client(context)
    if action == "delete":
        await client.delete_task(str(task["id"]), query.from_user.id)
        await query.edit_message_text("🗑 Задача удалена после подтверждения.", reply_markup=_secretary_menu())
        return
    updated = dict(task)
    now = datetime.now(timezone.utc).isoformat()
    if action == "complete":
        updated["isCompleted"] = True
        updated["completedAt"] = now
    elif action == "tomorrow":
        updated["date"] = (date.fromisoformat(str(task["date"])) + timedelta(days=1)).isoformat()
    elif action == "priority":
        updated["priority"] = {"low": "normal", "normal": "high", "high": "low"}.get(str(task.get("priority")), "normal")
    else:
        return
    updated["updatedAt"] = now
    await client.update_task(updated, query.from_user.id)
    await query.edit_message_text("✅ Изменение подтверждено и записано в календарь.", reply_markup=_secretary_menu())

async def voice_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Распознаёт голос и передаёт текст в общий сценарий секретаря."""
    message = update.effective_message
    if message is None or message.voice is None:
        return

    settings = _get_settings(context)
    transcriber = _get_transcriber(context)
    voice = message.voice
    if voice.duration > settings.max_voice_duration_seconds:
        await message.reply_text(
            "Голосовое сообщение слишком длинное.\n"
            f"Максимальная длительность: {settings.max_voice_duration_seconds} секунд."
        )
        return

    allowed, _ = await _consume_subscription_usage(
        context,
        _update_user_id(update),
        LIMIT_VOICE_MESSAGES,
    )
    if not allowed:
        await message.reply_text(
            "🎙 Лимит голосовых сообщений на текущий месяц исчерпан. "
            "Можно продолжить текстом или перейти на Plus/Full."
        )
        return

    status_message = await message.reply_text("Распознаю речь и разбираю задачи…")
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
    try:
        telegram_file = await voice.get_file()
        with tempfile.TemporaryDirectory(prefix="smart_planner_voice_") as temporary_directory:
            audio_path = Path(temporary_directory) / f"{voice.file_unique_id}.ogg"
            await telegram_file.download_to_drive(custom_path=audio_path)
            transcription = await transcriber.transcribe(audio_path)
        await status_message.delete()
        await _handle_task_text(update=update, context=context, text=transcription)
    except TranscriptionError as error:
        LOGGER.warning("Voice transcription failed: %s", error)
        await status_message.edit_text(
            "Не удалось распознать речь. Попробуй записать голосовое сообщение ещё раз в более тихом месте."
        )
    except Exception:
        LOGGER.exception("Unexpected error while processing voice message")
        await status_message.edit_text("Произошла внутренняя ошибка при обработке голосового сообщения.")


async def text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Обрабатывает текст через тот же сценарий, что и голос."""
    message = update.effective_message
    if message is None or not message.text:
        return
    try:
        await _handle_task_text(update=update, context=context, text=message.text)
    except ValueError as error:
        LOGGER.warning("Invalid text message: %s", error)
        await message.reply_text("Не удалось найти описание задачи в сообщении.")
    except Exception:
        LOGGER.exception("Unexpected error while processing text message")
        await message.reply_text("Произошла внутренняя ошибка при обработке текста.")


async def _handle_task_text(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    settings = _get_settings(context)
    extractor = _get_task_extractor(context)
    store = _get_confirmation_store(context)
    now = datetime.now(settings.timezone)

    edit_token = context.user_data.get(EDIT_STATE_KEY)
    if isinstance(edit_token, str):
        pending = store.get(
            token=edit_token,
            user_id=user.id,
            chat_id=message.chat_id,
            now=now,
        )
        if pending is None:
            context.user_data.pop(EDIT_STATE_KEY, None)
            await message.reply_text("Редактирование устарело. Отправь задачу заново.")
            return
        extractions = extractor.extract_many(text, reference_datetime=now)
        if len(extractions) != 1:
            await message.reply_text(
                "Для редактирования пришли одну исправленную задачу целиком — с нужной датой, временем и длительностью."
            )
            return
        updated = store.replace_extraction(
            token=edit_token,
            user_id=user.id,
            chat_id=message.chat_id,
            extraction=extractions[0],
            now=now,
        )
        context.user_data.pop(EDIT_STATE_KEY, None)
        if updated is None:
            await message.reply_text("Не удалось обновить черновик: подтверждение уже устарело.")
            return
        await message.reply_text("✏️ Изменения применены. Проверь задачу ещё раз.")
        await _send_pending_preview(context=context, chat_id=message.chat_id, pending=updated)
        return

    if await _try_handle_finance_text(update=update, context=context, text=text):
        return

    allowed, _ = await _consume_subscription_usage(context, user.id, LIMIT_AI_ACTIONS)
    if not allowed:
        await message.reply_text(
            "🤖 Лимит AI-действий Free на этот месяц исчерпан. "
            "Обычные задачи можно продолжать создавать вручную в веб-календаре; расширенный секретарь доступен на Plus/Full."
        )
        return

    snapshot = await _subscription_snapshot(context, user.id)
    extractions = extractor.extract_many(text, reference_datetime=now)
    if len(extractions) > 1 and not _has_entitlement(snapshot, ENTITLEMENT_MULTI_TASK):
        await message.reply_text(
            _upgrade_text("Распознавание нескольких задач из одного сообщения"),
        )
        return
    if len(extractions) > 1:
        await message.reply_text(
            f"🔎 <b>Найдено задач: {len(extractions)}</b>\n"
            "Проверим их по очереди: подтвердить, изменить или пропустить.",
            parse_mode=ParseMode.HTML,
        )
        pending = store.create_batch(
            user_id=user.id,
            chat_id=message.chat_id,
            extractions=extractions,
            now=now,
        )
    else:
        pending = store.create(
            user_id=user.id,
            chat_id=message.chat_id,
            extraction=extractions[0],
            now=now,
        )
    await _send_pending_preview(context=context, chat_id=message.chat_id, pending=pending)


async def unsupported_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    del context
    message = update.effective_message
    if message is not None:
        await message.reply_text("Сейчас я принимаю только текстовые и голосовые сообщения.")


async def task_confirmation_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    chat = update.effective_chat
    if query is None or query.data is None or user is None or chat is None:
        return

    parsed = _parse_callback_data(query.data)
    if parsed is None:
        await query.answer(text="Некорректная команда.", show_alert=True)
        return
    action, token, args = parsed
    settings = _get_settings(context)
    store = _get_confirmation_store(context)
    now = datetime.now(settings.timezone)
    pending = store.get(token=token, user_id=user.id, chat_id=chat.id, now=now)
    if pending is None:
        await query.answer(text="Подтверждение устарело или уже обработано.", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            LOGGER.debug("Could not remove expired callback keyboard", exc_info=True)
        return

    if action == EDIT_ACTION:
        context.user_data[EDIT_STATE_KEY] = token
        await query.answer()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            LOGGER.debug("Could not remove edit keyboard", exc_info=True)
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                "✏️ Пришли исправленную задачу <b>целиком</b> одним текстовым или голосовым сообщением.\n"
                "Например: <i>завтра в 15:30 встреча с Иваном на 45 минут, срочно</i>."
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    if action == REJECT_ACTION:
        consumed = store.consume(token=token, user_id=user.id, chat_id=chat.id, now=now)
        if consumed is None:
            await query.answer(text="Задача уже обработана.", show_alert=True)
            return
        await query.answer()
        await query.edit_message_text(
            "❌ <b>Задача пропущена</b>\nОна не была записана в календарь.",
            parse_mode=ParseMode.HTML,
        )
        await _advance_batch(context=context, chat_id=chat.id, pending=consumed, saved=False, now=now)
        return

    if action == CONFIRM_ACTION:
        await query.answer()
        await _confirm_pending(query=query, context=context, pending=pending, now=now)
        return

    if action == DURATION_ACTION:
        await query.answer()
        await _handle_duration_choice(query=query, context=context, pending=pending, args=args, now=now)
        return

    if action == SLOT_ACTION:
        await query.answer()
        await _handle_slot_choice(query=query, context=context, pending=pending, args=args, now=now)
        return

    if action == SAVE_UNTIMED_ACTION:
        await query.answer()
        extraction = pending.extraction.model_copy(
            update={
                "scheduled_time": None,
                "scheduled_end_time": None,
                "duration_minutes": None,
                "time_is_flexible": False,
            }
        )
        updated = store.replace_extraction(
            token=token,
            user_id=user.id,
            chat_id=chat.id,
            extraction=extraction,
            now=now,
        )
        if updated is not None:
            await _save_pending(query=query, context=context, pending=updated, now=now)
        return

    LOGGER.warning("Unknown confirmation action: %s", action)


async def _confirm_pending(
    *,
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    pending: PendingTask,
    now: datetime,
) -> None:
    extraction = pending.extraction
    if extraction.intent != "create_task" or extraction.title is None or extraction.scheduled_date is None:
        await query.edit_message_text(
            _format_incomplete_extraction(transcription=extraction.source_text, extraction=extraction),
            parse_mode=ParseMode.HTML,
            reply_markup=_build_incomplete_keyboard(pending.token),
        )
        return

    if extraction.duration_minutes is None:
        await query.edit_message_text(
            _format_extraction_preview(transcription=extraction.source_text, extraction=extraction)
            + "\n\n⏱ <b>Сколько времени выделить?</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=_build_duration_keyboard(
                pending.token,
                allow_untimed=extraction.scheduled_time is None,
            ),
        )
        return

    if extraction.scheduled_time is None or extraction.time_is_flexible:
        snapshot = await _subscription_snapshot(context, pending.user_id)
        if not _has_entitlement(snapshot, ENTITLEMENT_SMART_SCHEDULING):
            await query.edit_message_text(
                _format_extraction_preview(transcription=extraction.source_text, extraction=extraction)
                + "\n\n🔒 <b>Умный подбор свободного окна доступен на Plus/Full.</b> "
                  "На Free можно сохранить задачу без времени или изменить её и указать точное время вручную.",
                parse_mode=ParseMode.HTML,
                reply_markup=_build_no_slot_keyboard(pending.token),
            )
            return
        await _offer_best_slots(query=query, context=context, pending=pending, now=now)
        return

    start_minute = extraction.scheduled_time.hour * 60 + extraction.scheduled_time.minute
    duration = extraction.duration_minutes
    if start_minute + duration > 1440:
        await query.edit_message_text(
            _format_extraction_preview(transcription=extraction.source_text, extraction=extraction)
            + "\n\n⚠️ Задача выходит за границы суток. Измени время или длительность.",
            parse_mode=ParseMode.HTML,
            reply_markup=_build_incomplete_keyboard(pending.token),
        )
        return

    tasks = await _safe_list_user_tasks(context, pending.user_id)
    candidate = _candidate_from_extraction(extraction)
    deadline_conflict = _exceeds_deadline(extraction)
    conflict = conflict_warning_for_candidate(tasks, candidate) if candidate is not None else None
    if conflict or deadline_conflict:
        reason = conflict or "⚠️ Выбранный блок заканчивается позже дедлайна."
        snapshot = await _subscription_snapshot(context, pending.user_id)
        if not _has_entitlement(snapshot, ENTITLEMENT_SMART_SCHEDULING):
            await query.edit_message_text(
                _format_extraction_preview(transcription=extraction.source_text, extraction=extraction)
                + f"\n\n{reason}\n\n"
                  "Я не буду создавать наложение. На Free измени точное время вручную или сохрани задачу без времени; "
                  "автоматические альтернативы доступны на Plus/Full.",
                parse_mode=ParseMode.HTML,
                reply_markup=_build_no_slot_keyboard(pending.token),
            )
            return
        await _offer_best_slots(
            query=query,
            context=context,
            pending=pending,
            now=now,
            heading=(
                f"{reason}\n\n"
                "Я не буду наслаивать задачу на существующую. Выбери одно из свободных окон:"
            ),
            force_single_date=True,
        )
        return

    await _save_pending(query=query, context=context, pending=pending, now=now)


async def _handle_duration_choice(
    *,
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    pending: PendingTask,
    args: tuple[str, ...],
    now: datetime,
) -> None:
    if not args:
        await query.answer(text="Не выбрана длительность.", show_alert=True)
        return
    choice = args[0]
    if choice == "custom":
        context.user_data[EDIT_STATE_KEY] = pending.token
        await query.edit_message_text(
            "✏️ Пришли задачу целиком ещё раз и укажи нужную длительность, например: <i>завтра поработать над проектом 90 минут</i>.",
            parse_mode=ParseMode.HTML,
        )
        return
    if choice == "none":
        extraction = pending.extraction.model_copy(
            update={
                "scheduled_time": None,
                "scheduled_end_time": None,
                "duration_minutes": None,
                "time_is_flexible": False,
            }
        )
    else:
        try:
            duration = int(choice)
        except ValueError:
            await query.answer(text="Некорректная длительность.", show_alert=True)
            return
        if duration not in {30, 60, 120}:
            await query.answer(text="Некорректная длительность.", show_alert=True)
            return
        extraction = pending.extraction.model_copy(
            update={"duration_minutes": duration, "scheduled_end_time": None}
        )

    store = _get_confirmation_store(context)
    updated = store.replace_extraction(
        token=pending.token,
        user_id=pending.user_id,
        chat_id=pending.chat_id,
        extraction=extraction,
        now=now,
    )
    if updated is None:
        await query.edit_message_text("Подтверждение устарело. Отправь задачу заново.")
        return
    if choice == "none":
        await _save_pending(query=query, context=context, pending=updated, now=now)
    else:
        await _confirm_pending(query=query, context=context, pending=updated, now=now)


async def _offer_best_slots(
    *,
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    pending: PendingTask,
    now: datetime,
    heading: str | None = None,
    force_single_date: bool = False,
) -> None:
    extraction = pending.extraction
    if extraction.scheduled_date is None or extraction.duration_minutes is None:
        return
    try:
        snapshot = await _subscription_snapshot(context, pending.user_id)
        if not _has_entitlement(snapshot, ENTITLEMENT_SMART_SCHEDULING):
            await query.edit_message_text(
                _format_extraction_preview(transcription=extraction.source_text, extraction=extraction)
                + "\n\n" + _upgrade_text("Автоматический подбор свободных окон"),
                parse_mode=ParseMode.HTML,
                reply_markup=_build_no_slot_keyboard(pending.token),
            )
            return
    except TaskApiError:
        LOGGER.exception("Could not verify smart-scheduling entitlement")
        await query.edit_message_text("Не удалось проверить подписку. Попробуй ещё раз позже.")
        return
    try:
        tasks = await _get_task_api_client(context).list_tasks(pending.user_id)
    except TaskApiError:
        LOGGER.exception("Could not load calendar for slot suggestions")
        await query.edit_message_text(
            _format_extraction_preview(
                transcription=extraction.source_text,
                extraction=extraction,
            )
            + "\n\n⚠️ <b>Не удалось загрузить внутренний календарь.</b> "
            "Не могу безопасно подобрать свободное окно. Попробуй ещё раз позже или сохрани задачу без времени.",
            parse_mode=ParseMode.HTML,
            reply_markup=_build_no_slot_keyboard(pending.token),
        )
        return

    start_date = extraction.scheduled_date
    end_date = extraction.scheduled_date
    if (
        not force_single_date
        and "date_inferred_from_deadline" in extraction.warnings
        and extraction.deadline_date is not None
    ):
        # Если дата появилась только из дедлайна («сделать до пятницы»),
        # задача может быть выполнена в любой день от сегодня до дедлайна.
        start_date = now.date()
        end_date = extraction.deadline_date

    preferred_minute = None
    if extraction.time_is_flexible and extraction.scheduled_time is not None:
        preferred_minute = extraction.scheduled_time.hour * 60 + extraction.scheduled_time.minute

    deadline_minute = None
    if extraction.deadline_time is not None:
        deadline_minute = extraction.deadline_time.hour * 60 + extraction.deadline_time.minute

    planning_end = 24 * 60 if preferred_minute is not None and preferred_minute >= 22 * 60 else 22 * 60
    slots = best_free_slots(
        tasks,
        start_date=start_date,
        end_date=end_date,
        duration_minutes=extraction.duration_minutes,
        now=now,
        preferred_minute=preferred_minute,
        deadline_date=extraction.deadline_date,
        deadline_minute=deadline_minute,
        max_results=3,
        planning_end_minute=planning_end,
    )

    preview = _format_extraction_preview(
        transcription=extraction.source_text,
        extraction=extraction,
    )
    if not slots:
        text = preview + "\n\n⚠️ <b>Подходящего свободного окна не найдено.</b>\nИзмени задачу или сохрани её без времени."
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=_build_no_slot_keyboard(pending.token),
        )
        return

    lead = heading or "🧭 <b>Лучшие свободные окна</b>\nВыбери подходящий вариант:"
    await query.edit_message_text(
        preview + "\n\n" + lead,
        parse_mode=ParseMode.HTML,
        reply_markup=_build_slot_keyboard(pending.token, slots),
    )


async def _handle_slot_choice(
    *,
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    pending: PendingTask,
    args: tuple[str, ...],
    now: datetime,
) -> None:
    if len(args) != 3:
        await query.answer(text="Некорректное окно.", show_alert=True)
        return
    try:
        selected_date = datetime.strptime(args[0], "%Y%m%d").date()
        start_minute = int(args[1])
        duration = int(args[2])
    except ValueError:
        await query.answer(text="Некорректное окно.", show_alert=True)
        return
    if start_minute < 0 or start_minute + duration > 1440 or duration < 15:
        await query.answer(text="Некорректное окно.", show_alert=True)
        return

    extraction = pending.extraction
    if extraction.deadline_date is not None:
        if selected_date > extraction.deadline_date:
            await query.answer(text="Это окно позже дедлайна.", show_alert=True)
            return
        if selected_date == extraction.deadline_date and extraction.deadline_time is not None:
            deadline_minute = extraction.deadline_time.hour * 60 + extraction.deadline_time.minute
            if start_minute + duration > deadline_minute:
                await query.answer(text="Это окно выходит за дедлайн.", show_alert=True)
                return

    end_minute = start_minute + duration
    updated_extraction = extraction.model_copy(
        update={
            "scheduled_date": selected_date,
            "scheduled_time": time(start_minute // 60, start_minute % 60),
            "scheduled_end_time": time(end_minute // 60, end_minute % 60) if end_minute < 1440 else None,
            "duration_minutes": duration,
            "time_is_flexible": False,
        }
    )
    candidate = _candidate_from_extraction(updated_extraction)
    tasks = await _safe_list_user_tasks(context, pending.user_id)
    conflict = conflict_warning_for_candidate(tasks, candidate) if candidate is not None else None
    if conflict:
        refreshed = _get_confirmation_store(context).replace_extraction(
            token=pending.token,
            user_id=pending.user_id,
            chat_id=pending.chat_id,
            extraction=extraction,
            now=now,
        )
        if refreshed is not None:
            await _offer_best_slots(
                query=query,
                context=context,
                pending=refreshed,
                now=now,
                heading="⚠️ Пока ты выбирал, это окно заняли. Вот актуальные варианты:",
                force_single_date=True,
            )
        return

    updated = _get_confirmation_store(context).replace_extraction(
        token=pending.token,
        user_id=pending.user_id,
        chat_id=pending.chat_id,
        extraction=updated_extraction,
        now=now,
    )
    if updated is not None:
        await _save_pending(query=query, context=context, pending=updated, now=now)


async def _save_pending(
    *,
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    pending: PendingTask,
    now: datetime,
) -> None:
    client = _get_task_api_client(context)
    extraction = pending.extraction

    # Финальная проверка непосредственно перед записью защищает от гонки:
    # календарь мог измениться после показа вариантов пользователю.
    if extraction.scheduled_time is not None and extraction.duration_minutes is not None:
        try:
            current_tasks = await client.list_tasks(pending.user_id)
        except TaskApiError:
            LOGGER.exception("Could not verify calendar immediately before task creation")
            await query.edit_message_text(
                _format_extraction_preview(
                    transcription=extraction.source_text,
                    extraction=extraction,
                )
                + "\n\n⚠️ <b>Не удалось проверить актуальный календарь.</b> "
                "Я не буду сохранять временную задачу вслепую. Попробуй подтвердить ещё раз.",
                parse_mode=ParseMode.HTML,
                reply_markup=_build_confirmation_keyboard(pending.token),
            )
            return
        candidate = _candidate_from_extraction(extraction)
        conflict = conflict_warning_for_candidate(current_tasks, candidate) if candidate is not None else None
        if conflict or _exceeds_deadline(extraction):
            await _offer_best_slots(
                query=query,
                context=context,
                pending=pending,
                now=now,
                heading=(
                    (conflict or "⚠️ Выбранное окно больше не укладывается в дедлайн.")
                    + "\n\nКалендарь изменился. Выбери актуальный свободный вариант:"
                ),
                force_single_date=True,
            )
            return

    try:
        created_task = await client.create_task(
            extraction=pending.extraction,
            user_id=pending.user_id,
            chat_id=pending.chat_id,
            confirmation_token=pending.token,
        )
    except TaskApiError:
        LOGGER.exception(
            "Task API failed: user_id=%s chat_id=%s token=%s",
            pending.user_id,
            pending.chat_id,
            pending.token,
        )
        await query.edit_message_text(
            "⚠️ Не удалось сохранить задачу во внутренний календарь. Проверь Task API и попробуй подтвердить ещё раз.",
            reply_markup=_build_confirmation_keyboard(pending.token),
        )
        return

    store = _get_confirmation_store(context)
    consumed = store.consume(
        token=pending.token,
        user_id=pending.user_id,
        chat_id=pending.chat_id,
        now=now,
    )
    if consumed is None:
        return
    await query.edit_message_text(
        text=_format_confirmed_task(pending.extraction, task_id=str(created_task["id"])),
        parse_mode=ParseMode.HTML,
        reply_markup=None,
    )
    await _advance_batch(context=context, chat_id=pending.chat_id, pending=consumed, saved=True, now=now)


async def _advance_batch(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    pending: PendingTask,
    saved: bool,
    now: datetime,
) -> None:
    next_pending, summary = _get_confirmation_store(context).advance_batch(
        pending=pending,
        saved=saved,
        now=now,
    )
    if next_pending is not None:
        await _send_pending_preview(context=context, chat_id=chat_id, pending=next_pending)
    elif summary is not None:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "📋 <b>Обработка списка завершена</b>\n\n"
                f"✅ Сохранено: {summary.saved}\n"
                f"❌ Пропущено: {summary.skipped}\n"
                f"Всего: {summary.total}"
            ),
            parse_mode=ParseMode.HTML,
        )


async def _send_pending_preview(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    pending: PendingTask,
) -> None:
    extraction = pending.extraction
    if extraction.intent == "create_task" and extraction.title is not None and extraction.scheduled_date is not None:
        text = _format_extraction_preview(transcription=extraction.source_text, extraction=extraction)
        keyboard = _build_confirmation_keyboard(pending.token)
    else:
        text = _format_incomplete_extraction(transcription=extraction.source_text, extraction=extraction)
        keyboard = _build_incomplete_keyboard(pending.token)

    if pending.batch_total > 1:
        text = f"📌 <b>Задача {pending.batch_index + 1} из {pending.batch_total}</b>\n\n" + text

    advice: list[str] = []
    if extraction.intent == "create_task" and extraction.title is not None and extraction.scheduled_date is not None:
        if extraction.duration_minutes is None:
            advice.append("После подтверждения уточню длительность, если задачу нужно поставить во временной блок.")
        elif extraction.scheduled_time is None or extraction.time_is_flexible:
            try:
                snapshot = await _subscription_snapshot(context, pending.user_id)
                if _has_entitlement(snapshot, ENTITLEMENT_SMART_SCHEDULING):
                    advice.append("После подтверждения предложу до трёх свободных окон без пересечений.")
                else:
                    advice.append("На Free можно сохранить задачу без времени; автоматический подбор окна доступен на Plus/Full.")
            except TaskApiError:
                pass
        else:
            tasks = await _safe_list_user_tasks(context, pending.user_id)
            candidate = _candidate_from_extraction(extraction)
            conflict = conflict_warning_for_candidate(tasks, candidate) if candidate is not None else None
            if conflict:
                try:
                    snapshot = await _subscription_snapshot(context, pending.user_id)
                    if _has_entitlement(snapshot, ENTITLEMENT_SMART_SCHEDULING):
                        advice.append(conflict + " При подтверждении предложу свободные альтернативы.")
                    else:
                        advice.append(conflict + " На Free укажи другое время вручную.")
                except TaskApiError:
                    advice.append(conflict)
    if advice:
        text += "\n\n💡 <b>Секретарь</b>\n" + "\n".join(f"• {html.escape(item)}" for item in advice)

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def _safe_list_user_tasks(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> list[dict[str, Any]]:
    try:
        return await _get_task_api_client(context).list_tasks(user_id)
    except TaskApiError:
        LOGGER.warning("Could not load calendar for conflict check", exc_info=True)
        return []


def _candidate_from_extraction(extraction: TaskExtraction) -> dict[str, Any] | None:
    if extraction.title is None or extraction.scheduled_date is None or extraction.scheduled_time is None:
        return None
    return {
        "id": "candidate",
        "title": extraction.title,
        "date": extraction.scheduled_date.isoformat(),
        "startMinute": extraction.scheduled_time.hour * 60 + extraction.scheduled_time.minute,
        "durationMinutes": extraction.duration_minutes or 60,
        "isCompleted": False,
    }


def _exceeds_deadline(extraction: TaskExtraction) -> bool:
    if (
        extraction.scheduled_date is None
        or extraction.scheduled_time is None
        or extraction.duration_minutes is None
        or extraction.deadline_date is None
    ):
        return False
    if extraction.scheduled_date > extraction.deadline_date:
        return True
    if extraction.scheduled_date < extraction.deadline_date or extraction.deadline_time is None:
        return False
    start = extraction.scheduled_time.hour * 60 + extraction.scheduled_time.minute
    deadline = extraction.deadline_time.hour * 60 + extraction.deadline_time.minute
    return start + extraction.duration_minutes > deadline


def _format_extraction_time(extraction: TaskExtraction, *, all_day_text: str) -> str:
    if extraction.scheduled_time is None:
        return all_day_text
    start = extraction.scheduled_time.strftime("%H:%M")
    if extraction.scheduled_end_time is None:
        return start
    return f"{start}–{extraction.scheduled_end_time:%H:%M}"


def _format_duration_minutes(value: int) -> str:
    if value < 60:
        return f"{value} мин"
    hours, minutes = divmod(value, 60)
    if minutes == 0:
        return f"{hours} ч"
    return f"{hours} ч {minutes} мин"


def _format_deadline(extraction: TaskExtraction) -> str | None:
    if extraction.deadline_date is None:
        return None
    value = f"{extraction.deadline_date:%d.%m.%Y}"
    if extraction.deadline_time is not None:
        value += f" до {extraction.deadline_time:%H:%M}"
    return value


def _priority_text(priority: str) -> str:
    return {"low": "низкий", "normal": "обычный", "high": "высокий"}.get(priority, priority)


def _format_incomplete_extraction(
    *,
    transcription: str,
    extraction: TaskExtraction,
) -> str:
    lines = [
        "⚠️ <b>Задачу нужно уточнить</b>",
        "",
        "<b>Исходный текст:</b>",
        html.escape(transcription),
    ]
    if extraction.title is not None:
        lines.extend(["", f"<b>Название:</b> {html.escape(extraction.title)}"])
    if extraction.scheduled_date is not None:
        lines.append(f"<b>Дата:</b> {extraction.scheduled_date:%d.%m.%Y}")
    if extraction.scheduled_time is not None:
        lines.append(f"<b>Время:</b> {_format_extraction_time(extraction, all_day_text='не указано')}")
    if extraction.duration_minutes is not None:
        lines.append(f"<b>Длительность:</b> {_format_duration_minutes(extraction.duration_minutes)}")
    deadline = _format_deadline(extraction)
    if deadline:
        lines.append(f"<b>Дедлайн:</b> {deadline}")
    lines.append(f"<b>Приоритет:</b> {_priority_text(extraction.priority)}")
    if extraction.clarification_question is not None:
        lines.extend(["", f"<b>Нужно уточнить:</b> {html.escape(extraction.clarification_question)}"])
    return "\n".join(lines)


def _format_extraction_preview(
    *,
    transcription: str,
    extraction: TaskExtraction,
) -> str:
    if extraction.title is None or extraction.scheduled_date is None:
        raise ValueError("Для предпросмотра требуется название и дата.")

    time_text = _format_extraction_time(extraction, all_day_text="не указано")
    if extraction.time_is_flexible and extraction.scheduled_time is not None:
        time_text += " (ориентир)"
    lines = [
        "📝 <b>Я правильно распознал задачу?</b>",
        "",
        f"<b>Название:</b> {html.escape(extraction.title)}",
        f"<b>Дата:</b> {extraction.scheduled_date:%d.%m.%Y}",
        f"<b>Время:</b> {time_text}",
    ]
    if extraction.duration_minutes is not None:
        lines.append(f"<b>Длительность:</b> {_format_duration_minutes(extraction.duration_minutes)}")
    deadline = _format_deadline(extraction)
    if deadline:
        lines.append(f"<b>Дедлайн:</b> {deadline}")
    lines.append(f"<b>Приоритет:</b> {_priority_text(extraction.priority)}")
    lines.extend([
        f"<b>Уверенность:</b> {extraction.confidence:.0%}",
        "",
        "<b>Исходный текст:</b>",
        html.escape(transcription),
    ])
    if extraction.scheduled_time is None:
        lines.extend(["", "ℹ️ <i>Сейчас задача не занимает время в календаре.</i>"])
    return "\n".join(lines)


def _format_confirmed_task(extraction: TaskExtraction, *, task_id: str) -> str:
    if extraction.title is None or extraction.scheduled_date is None:
        raise ValueError("Нельзя подтвердить неполную задачу.")
    lines = [
        "✅ <b>Задача сохранена</b>",
        "",
        f"<b>Название:</b> {html.escape(extraction.title)}",
        f"<b>Дата:</b> {extraction.scheduled_date:%d.%m.%Y}",
        f"<b>Время:</b> {_format_extraction_time(extraction, all_day_text='без времени')}",
    ]
    if extraction.duration_minutes is not None and extraction.scheduled_time is not None:
        lines.append(f"<b>Длительность:</b> {_format_duration_minutes(extraction.duration_minutes)}")
    deadline = _format_deadline(extraction)
    if deadline:
        lines.append(f"<b>Дедлайн:</b> {deadline}")
    lines.append(f"<b>Приоритет:</b> {_priority_text(extraction.priority)}")
    lines.extend(["", f"<i>ID: {html.escape(task_id)}</i>"])
    return "\n".join(lines)


def _build_confirmation_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Подтвердить", callback_data=f"{CONFIRM_ACTION}:{token}")],
            [
                InlineKeyboardButton("✏️ Изменить", callback_data=f"{EDIT_ACTION}:{token}"),
                InlineKeyboardButton("❌ Пропустить", callback_data=f"{REJECT_ACTION}:{token}"),
            ],
        ]
    )


def _build_incomplete_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✏️ Изменить", callback_data=f"{EDIT_ACTION}:{token}"),
            InlineKeyboardButton("❌ Пропустить", callback_data=f"{REJECT_ACTION}:{token}"),
        ]]
    )


def _build_duration_keyboard(token: str, *, allow_untimed: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("30 мин", callback_data=f"{DURATION_ACTION}:{token}:30"),
            InlineKeyboardButton("1 час", callback_data=f"{DURATION_ACTION}:{token}:60"),
            InlineKeyboardButton("2 часа", callback_data=f"{DURATION_ACTION}:{token}:120"),
        ],
        [InlineKeyboardButton("✏️ Своя длительность", callback_data=f"{DURATION_ACTION}:{token}:custom")],
    ]
    if allow_untimed:
        rows.insert(1, [InlineKeyboardButton("✅ Оставить без времени", callback_data=f"{DURATION_ACTION}:{token}:none")])
    rows.append([InlineKeyboardButton("❌ Пропустить", callback_data=f"{REJECT_ACTION}:{token}")])
    return InlineKeyboardMarkup(rows)


def _build_slot_keyboard(token: str, slots: list[Any]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for slot in slots:
        label = f"{slot.task_date:%d.%m} · {slot.start_minute // 60:02d}:{slot.start_minute % 60:02d}–{slot.end_minute // 60:02d}:{slot.end_minute % 60:02d}"
        rows.append([
            InlineKeyboardButton(
                label,
                callback_data=f"{SLOT_ACTION}:{token}:{slot.task_date:%Y%m%d}:{slot.start_minute}:{slot.duration_minutes}",
            )
        ])
    rows.append([
        InlineKeyboardButton("🗒 Без времени", callback_data=f"{SAVE_UNTIMED_ACTION}:{token}"),
        InlineKeyboardButton("✏️ Изменить", callback_data=f"{EDIT_ACTION}:{token}"),
    ])
    rows.append([InlineKeyboardButton("❌ Пропустить", callback_data=f"{REJECT_ACTION}:{token}")])
    return InlineKeyboardMarkup(rows)


def _build_no_slot_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🗒 Сохранить без времени", callback_data=f"{SAVE_UNTIMED_ACTION}:{token}")],
            [
                InlineKeyboardButton("✏️ Изменить", callback_data=f"{EDIT_ACTION}:{token}"),
                InlineKeyboardButton("❌ Пропустить", callback_data=f"{REJECT_ACTION}:{token}"),
            ],
        ]
    )


def _parse_callback_data(value: str) -> tuple[str, str, tuple[str, ...]] | None:
    parts = value.split(":")
    if len(parts) < 2:
        return None
    action, token, *args = parts
    if action not in {
        CONFIRM_ACTION,
        REJECT_ACTION,
        EDIT_ACTION,
        DURATION_ACTION,
        SLOT_ACTION,
        SAVE_UNTIMED_ACTION,
    } or not token:
        return None
    return action, token, tuple(args)


def _get_settings(
    context: ContextTypes.DEFAULT_TYPE,
) -> Settings:
    value = context.application.bot_data.get(
        SETTINGS_KEY,
    )

    if not isinstance(value, Settings):
        raise RuntimeError(
            "Settings are not initialized."
        )

    return value


def _get_transcriber(
    context: ContextTypes.DEFAULT_TYPE,
) -> VoiceTranscriber:
    value = context.application.bot_data.get(
        TRANSCRIBER_KEY,
    )

    if not isinstance(value, VoiceTranscriber):
        raise RuntimeError(
            "VoiceTranscriber is not initialized."
        )

    return value


def _get_task_extractor(
    context: ContextTypes.DEFAULT_TYPE,
) -> TaskExtractor:
    value = context.application.bot_data.get(
        TASK_EXTRACTOR_KEY,
    )

    if not isinstance(value, TaskExtractor):
        raise RuntimeError(
            "TaskExtractor is not initialized."
        )

    return value


def _get_confirmation_store(
    context: ContextTypes.DEFAULT_TYPE,
) -> ConfirmationStore:
    value = context.application.bot_data.get(
        CONFIRMATION_STORE_KEY,
    )

    if not isinstance(value, ConfirmationStore):
        raise RuntimeError(
            "ConfirmationStore is not initialized."
        )

    return value


def _get_task_api_client(
    context: ContextTypes.DEFAULT_TYPE,
) -> TaskApiClient:
    value = context.application.bot_data.get(TASK_API_CLIENT_KEY)
    if not isinstance(value, TaskApiClient):
        raise RuntimeError("TaskApiClient is not initialized.")
    return value


async def global_error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Logs uncaught handler errors without making another Telegram request.

    An error handler must remain usable even when Telegram itself is
    temporarily unreachable. Sending a message from here can recursively fail
    with another ``TimedOut``/``NetworkError`` and hide the original error.
    """

    error = context.error
    if isinstance(error, TimedOut) or type(error) is NetworkError:
        cause = error.__cause__
        if cause is None:
            LOGGER.warning("Telegram network error while processing update: %s", error)
        else:
            LOGGER.warning(
                "Telegram network error while processing update: %s; cause=%r",
                error,
                cause,
            )
        return

    if isinstance(error, BaseException):
        LOGGER.error(
            "Unhandled exception while processing Telegram update",
            exc_info=(type(error), error, error.__traceback__),
        )
        return

    LOGGER.error("Unhandled non-exception error while processing Telegram update: %r", error)


def create_application(
    *,
    settings: Settings,
    transcriber: VoiceTranscriber,
    task_extractor: TaskExtractor,
    confirmation_store: ConfirmationStore,
    task_api_client: TaskApiClient,
) -> Application:
    """Создаёт и настраивает Telegram Application."""

    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT_SECONDS)
        .read_timeout(TELEGRAM_READ_TIMEOUT_SECONDS)
        .write_timeout(TELEGRAM_WRITE_TIMEOUT_SECONDS)
        .media_write_timeout(TELEGRAM_MEDIA_WRITE_TIMEOUT_SECONDS)
        .pool_timeout(TELEGRAM_POOL_TIMEOUT_SECONDS)
        .get_updates_connect_timeout(TELEGRAM_CONNECT_TIMEOUT_SECONDS)
        .get_updates_read_timeout(TELEGRAM_READ_TIMEOUT_SECONDS)
        .get_updates_write_timeout(TELEGRAM_WRITE_TIMEOUT_SECONDS)
        .get_updates_pool_timeout(TELEGRAM_POOL_TIMEOUT_SECONDS)
        .build()
    )

    application.bot_data[SETTINGS_KEY] = settings
    application.bot_data[TRANSCRIBER_KEY] = transcriber
    application.bot_data[TASK_EXTRACTOR_KEY] = (
        task_extractor
    )
    application.bot_data[CONFIRMATION_STORE_KEY] = (
        confirmation_store
    )
    application.bot_data[TASK_API_CLIENT_KEY] = task_api_client

    application.add_handler(
        TypeHandler(Update, access_guard_handler),
        group=-1,
    )

    application.add_handler(
        CommandHandler(
            "start",
            start_handler,
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_handler,
        )
    )

    application.add_handler(CommandHandler("admin", admin_handler))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern=r"^admin:"))
    application.add_handler(CommandHandler("menu", menu_handler))
    application.add_handler(CommandHandler("today", today_handler))
    application.add_handler(CommandHandler("week", week_handler))
    application.add_handler(CommandHandler("tasks", tasks_handler))
    application.add_handler(CommandHandler("free", free_handler))
    application.add_handler(CommandHandler("settings", settings_handler))
    application.add_handler(CommandHandler("finance", finance_handler))
    application.add_handler(CallbackQueryHandler(secretary_callback_handler, pattern=r"^sec:"))
    application.add_handler(CallbackQueryHandler(finance_callback_handler, pattern=r"^fin:"))
    application.add_handler(CallbackQueryHandler(finance_report_callback_handler, pattern=r"^finrep:"))
    application.add_handler(CommandHandler("report", report_handler))

    application.add_handler(
        CallbackQueryHandler(report_callback_handler, pattern=r"^report:(?:week|month)$")
    )
    application.add_handler(
        CallbackQueryHandler(
            task_confirmation_handler,
            pattern=(
                rf"^(?:{CONFIRM_ACTION}|{REJECT_ACTION}|{EDIT_ACTION}|"
                rf"{DURATION_ACTION}|{SLOT_ACTION}|{SAVE_UNTIMED_ACTION}):"
            ),
        )
    )

    application.add_handler(
        MessageHandler(
            filters.VOICE,
            voice_handler,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler,
        )
    )

    application.add_handler(
        MessageHandler(
            ~filters.COMMAND,
            unsupported_message_handler,
        )
    )

    application.add_error_handler(
        global_error_handler,
    )

    return application


def configure_logging() -> None:
    """Настраивает вывод логов."""

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
    )

    # Убираем избыточные сообщения о каждом HTTP-запросе.
    logging.getLogger("httpx").setLevel(
        logging.WARNING
    )


def main() -> None:
    """Точка входа приложения."""

    configure_logging()

    settings = load_settings()

    LOGGER.info(
        "Loading Whisper model: "
        "model=%s device=%s compute_type=%s",
        settings.whisper_model,
        settings.whisper_device,
        settings.whisper_compute_type,
    )

    transcriber = VoiceTranscriber(
        model_name=settings.whisper_model,
        language=settings.whisper_language,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )

    task_extractor = TaskExtractor(
        timezone=settings.timezone,
        language=settings.whisper_language or "ru",
    )

    confirmation_store = ConfirmationStore()
    task_api_client = TaskApiClient(
        base_url=settings.task_api_url,
        timeout_seconds=settings.task_api_timeout_seconds,
        service_token=settings.task_api_service_token,
    )

    application = create_application(
        settings=settings,
        transcriber=transcriber,
        task_extractor=task_extractor,
        confirmation_store=confirmation_store,
        task_api_client=task_api_client,
    )

    LOGGER.info(
        "Telegram bot started. Timezone: %s",
        settings.app_timezone,
    )

    application.run_polling(
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()