from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Literal

PeriodName = Literal["today", "week"]


@dataclass(frozen=True)
class SecretarySettings:
    work_start_minute: int = 9 * 60
    work_end_minute: int = 18 * 60
    break_minutes: int = 15
    overload_minutes: int = 8 * 60
    long_task_minutes: int = 3 * 60


@dataclass(frozen=True)
class Conflict:
    first: dict[str, Any]
    second: dict[str, Any]


@dataclass(frozen=True)
class FreeSlot:
    start_minute: int
    end_minute: int

    @property
    def duration_minutes(self) -> int:
        return self.end_minute - self.start_minute



@dataclass(frozen=True)
class SlotSuggestion:
    task_date: date
    start_minute: int
    duration_minutes: int

    @property
    def end_minute(self) -> int:
        return self.start_minute + self.duration_minutes


def best_free_slots(
    tasks: Iterable[dict[str, Any]],
    *,
    start_date: date,
    end_date: date,
    duration_minutes: int,
    now: datetime | None = None,
    preferred_minute: int | None = None,
    deadline_date: date | None = None,
    deadline_minute: int | None = None,
    max_results: int = 3,
    planning_start_minute: int = 8 * 60,
    planning_end_minute: int = 22 * 60,
) -> list[SlotSuggestion]:
    """Возвращает ближайшие свободные окна без пересечений.

    Это технический планировщик, а не персональное правило пользователя:
    он рассматривает дневное окно 08:00–22:00, соблюдает дедлайн и
    предпочитает края свободных блоков, чтобы меньше дробить календарь.
    """
    if duration_minutes < 15 or duration_minutes > 1440:
        raise ValueError("duration_minutes must be between 15 and 1440")
    if end_date < start_date:
        return []

    all_tasks = list(tasks)
    candidates: list[tuple[tuple[int, int, int, int], SlotSuggestion]] = []
    current = start_date
    while current <= end_date:
        if deadline_date is not None and current > deadline_date:
            break
        day_start = planning_start_minute
        day_end = planning_end_minute
        if now is not None and current == now.date():
            current_minute = now.hour * 60 + now.minute
            day_start = max(day_start, ((current_minute + 14) // 15) * 15)
        if deadline_date is not None and current == deadline_date and deadline_minute is not None:
            day_end = min(day_end, deadline_minute)
        if day_end - day_start < duration_minutes:
            current += timedelta(days=1)
            continue

        busy: list[tuple[int, int]] = []
        for task in all_tasks:
            if str(task.get("date")) != current.isoformat() or bool(task.get("isCompleted")):
                continue
            start = task.get("startMinute")
            if start is None:
                continue
            start = int(start)
            end = min(1440, start + int(task.get("durationMinutes") or 60))
            if end > day_start and start < day_end:
                busy.append((max(day_start, start), min(day_end, end)))
        busy.sort()
        merged: list[tuple[int, int]] = []
        for start, end in busy:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        gaps: list[tuple[int, int]] = []
        cursor = day_start
        for start, end in merged:
            if start - cursor >= duration_minutes:
                gaps.append((cursor, start))
            cursor = max(cursor, end)
        if day_end - cursor >= duration_minutes:
            gaps.append((cursor, day_end))

        for gap_start, gap_end in gaps:
            latest_start = gap_end - duration_minutes
            starts = {gap_start, latest_start}
            if preferred_minute is not None:
                preferred = max(gap_start, min(latest_start, (preferred_minute // 15) * 15))
                starts.add(preferred)
            for start in starts:
                if start < day_start or start + duration_minutes > day_end:
                    continue
                day_distance = (current - start_date).days
                preferred_distance = abs(start - preferred_minute) if preferred_minute is not None else 0
                fragments_block = int(start != gap_start and start != latest_start)
                score = (day_distance, preferred_distance, fragments_block, start)
                candidates.append((score, SlotSuggestion(current, start, duration_minutes)))
        current += timedelta(days=1)

    ordered: list[SlotSuggestion] = []
    seen: set[tuple[date, int]] = set()
    for _, candidate in sorted(candidates, key=lambda item: item[0]):
        key = (candidate.task_date, candidate.start_minute)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)
        if len(ordered) >= max_results:
            break
    return ordered

def period_bounds(period: PeriodName, today: date) -> tuple[date, date]:
    if period == "today":
        return today, today
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    raise ValueError(f"Unknown period: {period}")


def tasks_in_period(tasks: Iterable[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    return sorted(
        (task for task in tasks if start <= date.fromisoformat(str(task["date"])) <= end),
        key=lambda task: (str(task["date"]), task.get("startMinute") is None, task.get("startMinute") or 0, str(task.get("title", ""))),
    )


def detect_conflicts(tasks: Iterable[dict[str, Any]], *, extra_break_minutes: int = 0) -> list[Conflict]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        if task.get("startMinute") is None or bool(task.get("isCompleted")):
            continue
        by_date.setdefault(str(task["date"]), []).append(task)
    conflicts: list[Conflict] = []
    for day_tasks in by_date.values():
        ordered = sorted(day_tasks, key=lambda task: int(task["startMinute"]))
        for index, first in enumerate(ordered):
            first_end = int(first["startMinute"]) + int(first.get("durationMinutes") or 60) + extra_break_minutes
            for second in ordered[index + 1:]:
                if int(second["startMinute"]) >= first_end:
                    break
                conflicts.append(Conflict(first=first, second=second))
    return conflicts


def free_slots(
    tasks: Iterable[dict[str, Any]],
    target_date: date,
    *,
    settings: SecretarySettings = SecretarySettings(),
    minimum_minutes: int = 30,
) -> list[FreeSlot]:
    busy = []
    for task in tasks:
        if str(task.get("date")) != target_date.isoformat() or task.get("startMinute") is None or bool(task.get("isCompleted")):
            continue
        start = max(settings.work_start_minute, int(task["startMinute"]) - settings.break_minutes)
        end = min(settings.work_end_minute, int(task["startMinute"]) + int(task.get("durationMinutes") or 60) + settings.break_minutes)
        if end > start:
            busy.append((start, end))
    busy.sort()
    merged: list[tuple[int, int]] = []
    for start, end in busy:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    result = []
    cursor = settings.work_start_minute
    for start, end in merged:
        if start - cursor >= minimum_minutes:
            result.append(FreeSlot(cursor, start))
        cursor = max(cursor, end)
    if settings.work_end_minute - cursor >= minimum_minutes:
        result.append(FreeSlot(cursor, settings.work_end_minute))
    return result


def recommendations(
    tasks: list[dict[str, Any]],
    *,
    settings: SecretarySettings = SecretarySettings(),
) -> list[str]:
    advice: list[str] = []
    conflicts = detect_conflicts(tasks)
    if conflicts:
        advice.append(
            f"Обнаружено пересечений: {len(conflicts)}. "
            "Сначала разнесите конфликтующие задачи."
        )

    timed = [
        task
        for task in tasks
        if task.get("startMinute") is not None
        and not bool(task.get("isCompleted"))
    ]
    timed_by_date: dict[str, list[dict[str, Any]]] = {}
    active_by_date: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        if bool(task.get("isCompleted")):
            continue
        active_by_date.setdefault(str(task["date"]), []).append(task)
    for task in timed:
        timed_by_date.setdefault(str(task["date"]), []).append(task)

    overloaded_days = [
        task_date
        for task_date, day_tasks in timed_by_date.items()
        if sum(int(task.get("durationMinutes") or 60) for task in day_tasks)
        > settings.overload_minutes
    ]
    if overloaded_days:
        advice.append(
            f"Перегруженных дней: {len(overloaded_days)} — "
            "в них больше рекомендуемых 8 часов задач."
        )

    outside = [
        task
        for task in timed
        if int(task["startMinute"]) < settings.work_start_minute
        or int(task["startMinute"])
        + int(task.get("durationMinutes") or 60)
        > settings.work_end_minute
    ]
    if outside:
        advice.append(
            "Задач вне рабочего времени 09:00–18:00: "
            f"{len(outside)}."
        )

    long_tasks = [
        task
        for task in timed
        if int(task.get("durationMinutes") or 60)
        > settings.long_task_minutes
    ]
    if long_tasks:
        advice.append(
            "Длинные задачи лучше разбить на блоки до 3 часов с перерывом."
        )

    crowded_days = [
        task_date
        for task_date, day_tasks in active_by_date.items()
        if len(day_tasks) > 8
    ]
    if crowded_days:
        advice.append(
            f"Дней с количеством задач больше 8: {len(crowded_days)}. "
            "Выделите три главных результата."
        )

    if not advice and tasks:
        advice.append(
            "Расписание выглядит реалистично: накладок и перегрузки не найдено."
        )
    if not tasks:
        advice.append(
            "Расписание свободно — можно запланировать одну важную задачу "
            "и оставить резерв."
        )
    return advice

def format_agenda_html(
    tasks: list[dict[str, Any]],
    *,
    title: str,
    groups: list[dict[str, Any]],
    include_advice: bool = True,
) -> str:
    groups_by_id = {str(group["id"]): group for group in groups}
    lines = [f"🗓 <b>{html.escape(title)}</b>", ""]
    if not tasks:
        lines.append("Задач нет.")
    else:
        current_date = None
        for task in tasks[:30]:
            task_date = str(task["date"])
            if task_date != current_date:
                current_date = task_date
                lines.extend(["", f"<b>{date.fromisoformat(task_date):%d.%m.%Y}</b>"])
            start = task.get("startMinute")
            duration = task.get("durationMinutes") or (60 if start is not None else None)
            time_text = "весь день" if start is None else f"{_minutes(start)}–{_minutes(int(start) + int(duration))}"
            status = "✅" if bool(task.get("isCompleted")) else "▫️"
            group = groups_by_id.get(str(task.get("groupId"))) if task.get("groupId") is not None else None
            group_text = f" · {html.escape(str(group['name']))}" if group else ""
            lines.append(f"{status} <b>{time_text}</b> {html.escape(str(task.get('title', 'Без названия')))}{group_text}")
        if len(tasks) > 30:
            lines.append(f"…и ещё {len(tasks) - 30}")
    if include_advice:
        lines.extend(["", "💡 <b>Рекомендации</b>"])
        lines.extend(f"• {html.escape(item)}" for item in recommendations(tasks))
    return "\n".join(lines)


def format_free_slots_html(slots: list[FreeSlot], target_date: date) -> str:
    lines = [f"🟢 <b>Свободные окна · {target_date:%d.%m.%Y}</b>", ""]
    if not slots:
        lines.append("В рабочее время свободных окон от 30 минут нет.")
    else:
        lines.extend(f"• {_minutes(slot.start_minute)}–{_minutes(slot.end_minute)} · {slot.duration_minutes} мин" for slot in slots)
    lines.extend(["", "Учтён рекомендуемый перерыв 15 минут между задачами."])
    return "\n".join(lines)


def conflict_warning_for_candidate(tasks: list[dict[str, Any]], candidate: dict[str, Any]) -> str | None:
    conflicts = detect_conflicts([*tasks, candidate])
    candidate_id = str(candidate.get("id", "candidate"))
    related = [item for item in conflicts if str(item.first.get("id")) == candidate_id or str(item.second.get("id")) == candidate_id]
    if not related:
        return None
    names = []
    for conflict in related:
        other = conflict.second if str(conflict.first.get("id")) == candidate_id else conflict.first
        names.append(str(other.get("title", "задача")))
    return "⚠️ Накладка с: " + ", ".join(dict.fromkeys(names))


def _minutes(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"