from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageFont

ReportPeriod = Literal["week", "month"]


@dataclass(frozen=True)
class GroupReport:
    name: str
    color_hex: str
    total: int
    completed: int

    @property
    def completion_rate(self) -> float:
        return self.completed / self.total if self.total else 0.0


@dataclass(frozen=True)
class DailyReport:
    day: date
    total: int
    completed: int
    focus_minutes: int

    @property
    def completion_rate(self) -> float:
        return self.completed / self.total if self.total else 0.0


@dataclass(frozen=True)
class HabitReport:
    name: str
    states: tuple[str, ...]
    completed: int
    total: int


@dataclass(frozen=True)
class PlannerReport:
    period: ReportPeriod
    start_date: date
    end_date: date
    total: int
    completed: int
    on_time: int
    late: int
    missed: int
    pending: int
    groups: tuple[GroupReport, ...]
    daily: tuple[DailyReport, ...] = ()
    habits: tuple[HabitReport, ...] = ()
    habit_dates: tuple[date, ...] = ()
    focus_matrix: tuple[tuple[float, ...], ...] = ()

    @property
    def completion_rate(self) -> float:
        return self.completed / self.total if self.total else 0.0

    @property
    def period_label(self) -> str:
        return "Неделя" if self.period == "week" else "Месяц"


def build_report(
    *,
    tasks: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    period: ReportPeriod,
    now: datetime,
    goals: list[dict[str, Any]] | None = None,
) -> PlannerReport:
    today = now.date()
    if period == "week":
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif period == "month":
        start_date = today.replace(day=1)
        next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = next_month - timedelta(days=1)
    else:
        raise ValueError(f"Unknown report period: {period}")

    normalized = [task for task in tasks if _safe_task_date(task) is not None]
    selected = [
        task for task in normalized
        if start_date <= _safe_task_date(task) <= end_date  # type: ignore[operator]
    ]
    completed = [task for task in selected if bool(task.get("isCompleted"))]
    on_time = 0
    late = 0
    for task in completed:
        task_date = _safe_task_date(task)
        completed_at = _safe_datetime(task.get("completedAt"))
        if task_date is None or completed_at is None:
            late += 1
            continue
        if completed_at.date() <= task_date:
            on_time += 1
        else:
            late += 1

    missed = sum(
        1 for task in selected
        if not bool(task.get("isCompleted"))
        and (_safe_task_date(task) or today) < today
    )
    pending = len(selected) - len(completed) - missed

    groups_by_id = {str(group["id"]): group for group in groups if group.get("id") is not None}
    grouped: dict[str | None, list[dict[str, Any]]] = {}
    for task in selected:
        group_id = task.get("groupId")
        key = str(group_id) if group_id is not None and str(group_id) in groups_by_id else None
        grouped.setdefault(key, []).append(task)
    group_reports: list[GroupReport] = []
    for group_id, group_tasks in grouped.items():
        group = groups_by_id.get(group_id) if group_id is not None else None
        group_reports.append(
            GroupReport(
                name=str(group["name"]) if group else "Без группы",
                color_hex=_safe_color(str(group.get("colorHex", "#94A3B8"))) if group else "#94A3B8",
                total=len(group_tasks),
                completed=sum(1 for task in group_tasks if bool(task.get("isCompleted"))),
            )
        )
    group_reports.sort(key=lambda item: (-item.total, item.name.lower()))

    daily_dates = [start_date + timedelta(days=index) for index in range((end_date - start_date).days + 1)]
    daily_reports = tuple(_daily_report(day, selected) for day in daily_dates)
    chart_daily = _chart_daily(period=period, daily=daily_reports)

    habit_dates = _habit_dates(period=period, start_date=start_date, end_date=end_date, today=today)
    habits = _build_habits(
        goals=goals or [],
        tasks=normalized,
        dates=habit_dates,
        today=today,
    )
    focus_matrix = _build_focus_matrix(selected, start_date, end_date)

    return PlannerReport(
        period=period,
        start_date=start_date,
        end_date=end_date,
        total=len(selected),
        completed=len(completed),
        on_time=on_time,
        late=late,
        missed=missed,
        pending=pending,
        groups=tuple(group_reports),
        daily=chart_daily,
        habits=habits,
        habit_dates=habit_dates,
        focus_matrix=focus_matrix,
    )


def format_report_html(report: PlannerReport) -> str:
    rate = round(report.completion_rate * 100)
    best = max(report.daily, key=lambda item: item.completion_rate, default=None)
    lines = [
        f"📊 <b>Smart Planner · {report.period_label}</b>",
        f"{report.start_date:%d.%m.%Y} — {report.end_date:%d.%m.%Y}",
        "",
        f"<b>{rate}%</b> · выполнено {report.completed} из {report.total}",
        f"✅ Вовремя: {report.on_time}   🕒 Позже: {report.late}",
        f"❌ Пропущено: {report.missed}   ⏳ Ожидают: {report.pending}",
    ]
    if best is not None and best.total:
        lines.append(
            f"🏆 Лучший день: {_weekday_short(best.day)} · {round(best.completion_rate * 100)}%"
        )
    if report.groups:
        lines.extend(["", "<b>По группам:</b>"])
        lines.extend(
            f"• {group.name}: {group.completed}/{group.total}"
            for group in report.groups[:5]
        )
    return "\n".join(lines)


def render_report_png(report: PlannerReport) -> bytes:
    width, height = 1440, 1080
    image = Image.new("RGB", (width, height), "#F6F5FF")
    draw = ImageDraw.Draw(image)
    _draw_background(draw, width, height)

    card = (42, 34, width - 42, height - 34)
    draw.rounded_rectangle(card, radius=34, fill="#FFFFFF", outline="#E9E6F6", width=2)

    # Header
    _rounded_icon(draw, (74, 67, 126, 119), "#F1EEFF", "#5A47FF", "▦", 29)
    draw.text((146, 67), f"Smart Planner · {report.period_label}", fill="#121129", font=_font(31, bold=True))
    draw.text((147, 104), f"{report.start_date:%d.%m.%Y} — {report.end_date:%d.%m.%Y}", fill="#7C8296", font=_font(17))
    overview = "Еженедельный обзор" if report.period == "week" else "Ежемесячный обзор"
    _pill(draw, (1162, 75, 1350, 111), overview, fill="#F6F3FF", text_color="#6253E8", font_size=15)

    # Hero completion card
    hero = (74, 143, 1366, 316)
    draw.rounded_rectangle(hero, radius=24, fill="#FCFBFF", outline="#ECE9F6", width=1)
    rate = round(report.completion_rate * 100)
    draw.text((102, 170), f"{rate}%", fill="#5A47F7", font=_font(70, bold=True))
    draw.text((104, 246), "выполнено", fill="#202136", font=_font(14, bold=True))
    draw.text((205, 246), f"{report.completed} из {report.total}", fill="#555B70", font=_font(14))
    _progress_bar(draw, (285, 220, 1056, 242), report.completion_rate, "#664CFA")
    draw.text((1018, 192), f"{rate}%", fill="#FFFFFF" if report.completion_rate > .82 else "#5A47F7", font=_font(12, bold=True))
    _draw_target(draw, center=(1246, 224), scale=1.0)

    # Metrics
    metric_y1, metric_y2 = 340, 456
    metric_gap = 14
    metric_w = (1292 - metric_gap * 3) // 4
    metrics = [
        ("Вовремя", report.on_time, "#25BF70", "✓"),
        ("Позже", report.late, "#F6A623", "◷"),
        ("Пропущено", report.missed, "#F04A4A", "×"),
        ("Ожидают", report.pending, "#3979F6", "○"),
    ]
    for index, (label, value, color, symbol) in enumerate(metrics):
        x1 = 74 + index * (metric_w + metric_gap)
        _metric_card(draw, (x1, metric_y1, x1 + metric_w, metric_y2), label, value, color, symbol)

    # Content cards: habits / focus / completion / groups / productivity
    habits_box = (74, 480, 568, 854)
    focus_box = (588, 480, 954, 675)
    donut_box = (974, 480, 1366, 675)
    productivity_box = (588, 695, 954, 944)
    groups_box = (974, 695, 1366, 944)
    for box in (habits_box, focus_box, donut_box, productivity_box, groups_box):
        draw.rounded_rectangle(box, radius=21, fill="#FFFFFF", outline="#ECEBF3", width=1)

    _draw_habits(draw, habits_box, report)
    _draw_focus(draw, focus_box, report)
    _draw_completion_donut(draw, donut_box, report)
    _draw_productivity(draw, productivity_box, report)
    _draw_groups(draw, groups_box, report)

    # Footer
    footer = (74, 965, 1366, 1027)
    draw.rounded_rectangle(footer, radius=18, fill="#FBFAFF", outline="#EFECF8", width=1)
    draw.text((102, 986), "★", font=_font(18, bold=True), fill="#6A54F5")
    draw.text((132, 985), _motivation_text(report), font=_font(15), fill="#7B8195")
    draw.text((1108, 985), "Продолжай в том же духе!", font=_font(15), fill="#8A8FA2")
    draw.text((1329, 985), "•", font=_font(18, bold=True), fill="#7562F5")

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _draw_habits(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], report: PlannerReport) -> None:
    x1, y1, x2, _ = box
    draw.text((x1 + 22, y1 + 18), "✦  Привычки", fill="#312E55", font=_font(17, bold=True))
    dates = report.habit_dates
    if dates:
        for index, day in enumerate(dates):
            x = x1 + 210 + index * 37
            draw.text((x, y1 + 23), _weekday_tiny(day), fill="#8F94A7", font=_font(11))
    if not report.habits:
        draw.text((x1 + 24, y1 + 82), "Создай цель с повторяющейся задачей —", fill="#858A9C", font=_font(15))
        draw.text((x1 + 24, y1 + 107), "здесь появится серия выполнения.", fill="#858A9C", font=_font(15))
        return
    row_y = y1 + 64
    palette = ["#624CF7", "#2589E9", "#2ABF73", "#EE9B2A"]
    for row, habit in enumerate(report.habits[:4]):
        y = row_y + row * 58
        label = _ellipsis(habit.name, 15)
        draw.text((x1 + 23, y + 7), label, fill="#2D3043", font=_font(14, bold=True))
        color = palette[row % len(palette)]
        for index, state in enumerate(habit.states[:7]):
            cx = x1 + 218 + index * 37
            cy = y + 17
            if state == "completed":
                draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=color)
                _center_text(draw, (cx, cy), "✓", _font(10, bold=True), "#FFFFFF")
            elif state == "missed":
                draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill="#F3A12B")
                _center_text(draw, (cx, cy), "•", _font(13, bold=True), "#FFFFFF")
            elif state == "pending":
                draw.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), outline="#D8D9E4", width=2)
            else:
                draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill="#ECECF3")
        draw.text((x2 - 53, y + 8), f"{habit.completed}/{habit.total}", fill="#9296A7", font=_font(11))


def _draw_focus(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], report: PlannerReport) -> None:
    x1, y1, _, _ = box
    draw.text((x1 + 20, y1 + 18), "✦ Фокус · Deep Work", fill="#312E55", font=_font(16, bold=True))
    matrix = report.focus_matrix
    cell = 25
    gap = 5
    origin_x, origin_y = x1 + 26, y1 + 61
    for row in range(5):
        for col in range(7):
            intensity = 0.0
            if row < len(matrix) and col < len(matrix[row]):
                intensity = matrix[row][col]
            color = _blend("#F0EDFF", "#5D47F4", intensity)
            px = origin_x + col * (cell + gap)
            py = origin_y + row * (cell + gap)
            draw.rounded_rectangle((px, py, px + cell, py + cell), radius=4, fill=color)
    draw.text((origin_x + 226, origin_y + 30), "Меньше", fill="#979BAA", font=_font(10))
    for i, value in enumerate((0.15, .35, .55, .75, 1.0)):
        px = origin_x + 226 + i * 18
        py = origin_y + 53
        draw.rounded_rectangle((px, py, px + 13, py + 13), radius=3, fill=_blend("#F0EDFF", "#5D47F4", value))
    draw.text((origin_x + 226, origin_y + 75), "Больше", fill="#979BAA", font=_font(10))


def _draw_completion_donut(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], report: PlannerReport) -> None:
    x1, y1, _, _ = box
    draw.text((x1 + 22, y1 + 18), "Выполнение", fill="#312E55", font=_font(16, bold=True))
    cx, cy, radius = x1 + 122, y1 + 116, 55
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline="#E9E6F5", width=16)
    if report.total:
        end = -90 + 360 * report.completion_rate
        draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), -90, end, fill="#654BF7", width=16)
    _center_text(draw, (cx, cy - 7), f"{round(report.completion_rate * 100)}%", _font(28, bold=True), "#5B49E8")
    _center_text(draw, (cx, cy + 21), f"{report.completed} из {report.total}", _font(11), "#7D8295")
    legend_x = x1 + 220
    draw.ellipse((legend_x, y1 + 90, legend_x + 10, y1 + 100), fill="#654BF7")
    draw.text((legend_x + 18, y1 + 86), "Выполнено", fill="#555B6F", font=_font(12))
    draw.ellipse((legend_x, y1 + 121, legend_x + 10, y1 + 131), fill="#E7E4F2")
    draw.text((legend_x + 18, y1 + 117), "Осталось", fill="#555B6F", font=_font(12))


def _draw_productivity(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], report: PlannerReport) -> None:
    x1, y1, x2, y2 = box
    draw.text((x1 + 20, y1 + 18), "Продуктивность по дням", fill="#312E55", font=_font(15, bold=True))
    chart_left, chart_top = x1 + 35, y1 + 65
    chart_bottom = y2 - 40
    chart_right = x2 - 22
    for pct in (0, 25, 50, 75, 100):
        y = chart_bottom - int((chart_bottom - chart_top) * pct / 100)
        draw.line((chart_left, y, chart_right, y), fill="#F0EFF6", width=1)
        draw.text((x1 + 4, y - 7), f"{pct}%", fill="#A0A3B0", font=_font(9))
    data = report.daily[:7]
    if not data:
        return
    gap = 12
    bar_w = max(16, int((chart_right - chart_left - gap * (len(data) - 1)) / len(data)))
    for index, item in enumerate(data):
        x = chart_left + index * (bar_w + gap)
        value = item.completion_rate
        h = max(3, int((chart_bottom - chart_top) * value)) if item.total else 3
        draw.rounded_rectangle((x, chart_bottom - h, x + bar_w, chart_bottom), radius=5, fill="#765AF7" if item.total else "#E7E5EF")
        _center_text(draw, (x + bar_w // 2, chart_bottom + 18), _weekday_tiny(item.day), _font(10), "#777C90")


def _draw_groups(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], report: PlannerReport) -> None:
    x1, y1, x2, _ = box
    draw.text((x1 + 22, y1 + 18), "▣  Группы задач", fill="#312E55", font=_font(15, bold=True))
    shown = report.groups[:4]
    if not shown:
        draw.text((x1 + 22, y1 + 75), "Нет задач по группам", fill="#9397A7", font=_font(14))
        return
    for index, group in enumerate(shown):
        y = y1 + 62 + index * 44
        draw.ellipse((x1 + 22, y + 2, x1 + 32, y + 12), fill=group.color_hex)
        draw.text((x1 + 42, y - 2), _ellipsis(group.name, 19), fill="#45495B", font=_font(12, bold=True))
        draw.text((x2 - 50, y - 2), f"{group.completed}/{group.total}", fill="#8B90A1", font=_font(10))
        _progress_bar(draw, (x1 + 42, y + 20, x2 - 22, y + 28), group.completion_rate, group.color_hex, background="#ECECF2")


def _daily_report(day: date, tasks: list[dict[str, Any]]) -> DailyReport:
    day_tasks = [task for task in tasks if _safe_task_date(task) == day]
    focus_minutes = 0
    for task in day_tasks:
        if not bool(task.get("isCompleted")):
            continue
        start = _safe_int(task.get("startMinute"))
        duration = _safe_int(task.get("durationMinutes"))
        if start is not None and duration is not None:
            focus_minutes += max(0, duration)
    return DailyReport(
        day=day,
        total=len(day_tasks),
        completed=sum(1 for task in day_tasks if bool(task.get("isCompleted"))),
        focus_minutes=focus_minutes,
    )


def _chart_daily(*, period: ReportPeriod, daily: tuple[DailyReport, ...]) -> tuple[DailyReport, ...]:
    if period == "week":
        return daily[:7]
    # For a month, show productivity averaged by weekday so the chart keeps seven readable columns.
    result: list[DailyReport] = []
    for weekday in range(7):
        items = [item for item in daily if item.day.weekday() == weekday]
        if not items:
            continue
        result.append(
            DailyReport(
                day=items[0].day,
                total=sum(item.total for item in items),
                completed=sum(item.completed for item in items),
                focus_minutes=sum(item.focus_minutes for item in items),
            )
        )
    return tuple(result)


def _habit_dates(*, period: ReportPeriod, start_date: date, end_date: date, today: date) -> tuple[date, ...]:
    if period == "week":
        return tuple(start_date + timedelta(days=index) for index in range(7))
    last = min(today, end_date)
    first = max(start_date, last - timedelta(days=6))
    dates = [first + timedelta(days=index) for index in range((last - first).days + 1)]
    while len(dates) < 7:
        dates.insert(0, dates[0] - timedelta(days=1))
    return tuple(dates[-7:])


def _build_habits(
    *,
    goals: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    dates: tuple[date, ...],
    today: date,
) -> tuple[HabitReport, ...]:
    task_by_goal_date: dict[tuple[str, date], dict[str, Any]] = {}
    for task in tasks:
        goal_id = task.get("goalId")
        occurrence_raw = task.get("goalOccurrenceDate")
        if goal_id is None or occurrence_raw is None:
            continue
        occurrence = _safe_date(occurrence_raw)
        if occurrence is not None:
            task_by_goal_date[(str(goal_id), occurrence)] = task

    reports: list[HabitReport] = []
    for goal in goals:
        goal_id = str(goal.get("id", ""))
        if not goal_id:
            continue
        start = _safe_date(goal.get("startDate"))
        end = _safe_date(goal.get("endDate"))
        interval = _safe_int(goal.get("intervalDays")) or 1
        if start is None or end is None:
            continue
        states: list[str] = []
        completed = 0
        total = 0
        for day in dates:
            if day < start or day > end or (day - start).days % interval != 0:
                states.append("none")
                continue
            total += 1
            task = task_by_goal_date.get((goal_id, day))
            if task is not None and bool(task.get("isCompleted")):
                completed += 1
                states.append("completed")
            elif day < today:
                states.append("missed")
            else:
                states.append("pending")
        if total:
            reports.append(
                HabitReport(
                    name=str(goal.get("title") or goal.get("taskTitle") or "Цель"),
                    states=tuple(states),
                    completed=completed,
                    total=total,
                )
            )
    reports.sort(key=lambda item: (-item.total, item.name.lower()))
    return tuple(reports)


def _build_focus_matrix(
    tasks: list[dict[str, Any]],
    start_date: date,
    end_date: date,
) -> tuple[tuple[float, ...], ...]:
    # Five time bands × seven columns. For monthly reports columns are weekdays.
    raw = [[0 for _ in range(7)] for _ in range(5)]
    for task in tasks:
        if not bool(task.get("isCompleted")):
            continue
        task_date = _safe_task_date(task)
        start = _safe_int(task.get("startMinute"))
        duration = _safe_int(task.get("durationMinutes"))
        if task_date is None or start is None or duration is None or not (start_date <= task_date <= end_date):
            continue
        band = min(4, max(0, start // (24 * 60 // 5)))
        column = task_date.weekday()
        raw[band][column] += max(0, duration)
    maximum = max((value for row in raw for value in row), default=0)
    if maximum <= 0:
        return tuple(tuple(0.0 for _ in range(7)) for _ in range(5))
    return tuple(tuple(min(1.0, value / maximum) for value in row) for row in raw)


def _safe_task_date(task: dict[str, Any]) -> date | None:
    return _safe_date(task.get("date"))


def _safe_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _safe_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_color(value: str) -> str:
    value = value.strip()
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value.upper()
        except ValueError:
            pass
    return "#94A3B8"


def _draw_background(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = (
            int(249 - 6 * ratio),
            int(248 - 6 * ratio),
            int(255 - 1 * ratio),
        )
        draw.line((0, y, width, y), fill=color)


def _metric_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    value: int,
    color: str,
    symbol: str,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=18, fill="#FFFFFF", outline="#ECEBF3", width=1)
    draw.ellipse((x1 + 22, y1 + 25, x1 + 64, y1 + 67), fill=_blend("#FFFFFF", color, .12))
    _center_text(draw, (x1 + 43, y1 + 46), symbol, _font(19, bold=True), color)
    draw.text((x1 + 82, y1 + 20), str(value), fill=color, font=_font(29, bold=True))
    draw.text((x1 + 82, y1 + 58), label, fill="#52586B", font=_font(13, bold=True))
    dots = min(8, max(1, value))
    for index in range(8):
        dot_color = color if index < dots else "#E8E8F1"
        draw.ellipse((x1 + 82 + index * 13, y1 + 86, x1 + 89 + index * 13, y1 + 93), fill=dot_color)


def _draw_target(draw: ImageDraw.ImageDraw, *, center: tuple[int, int], scale: float) -> None:
    cx, cy = center
    for radius, color, width in ((57, "#ECE8FF", 12), (39, "#CFC5FF", 11), (21, "#7B62F7", 10)):
        r = int(radius * scale)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=max(2, int(width * scale)))
    draw.line((cx + 4, cy - 5, cx + 62, cy - 63), fill="#654BF7", width=8)
    draw.polygon([(cx + 63, cy - 64), (cx + 48, cy - 58), (cx + 58, cy - 48)], fill="#654BF7")


def _rounded_icon(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, color: str, symbol: str, size: int) -> None:
    draw.rounded_rectangle(box, radius=13, fill=fill)
    _center_text(draw, ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2), symbol, _font(size, bold=True), color)


def _pill(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    *,
    fill: str,
    text_color: str,
    font_size: int,
) -> None:
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=fill)
    _center_text(
        draw,
        ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2),
        label,
        _font(font_size, bold=True),
        text_color,
    )


def _progress_bar(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    value: float,
    color: str,
    *,
    background: str = "#ECE9FA",
) -> None:
    x1, y1, x2, y2 = box
    value = max(0.0, min(1.0, value))
    radius = max(2, (y2 - y1) // 2)
    draw.rounded_rectangle(box, radius=radius, fill=background)
    if value > 0:
        fill_x = x1 + max(y2 - y1, int((x2 - x1) * value))
        draw.rounded_rectangle((x1, y1, min(x2, fill_x), y2), radius=radius, fill=color)


def _center_text(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: str,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    draw.text(
        (center[0] - width / 2, center[1] - height / 2 - bbox[1]),
        text,
        font=font,
        fill=fill,
    )


def _blend(start: str, end: str, amount: float) -> tuple[int, int, int]:
    amount = max(0.0, min(1.0, amount))
    a = tuple(int(start[index:index + 2], 16) for index in (1, 3, 5))
    b = tuple(int(end[index:index + 2], 16) for index in (1, 3, 5))
    return tuple(round(a[i] + (b[i] - a[i]) * amount) for i in range(3))


def _ellipsis(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: max(1, limit - 1)] + "…"


def _weekday_short(value: date) -> str:
    return ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")[value.weekday()]


def _weekday_tiny(value: date) -> str:
    return ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")[value.weekday()]


def _motivation_text(report: PlannerReport) -> str:
    rate = report.completion_rate
    if report.total == 0:
        return "Добавь задачи — и следующий обзор покажет динамику недели."
    if rate >= .85:
        return "Отличный ритм: большая часть запланированного уже выполнена."
    if rate >= .6:
        return "Хороший прогресс: ещё немного — и неделя будет закрыта уверенно."
    if report.missed:
        return "Сфокусируйся на главном: перенеси просроченное и освободи время для приоритетов."
    return "Небольшие регулярные шаги дают лучший результат на дистанции."


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]
    candidates: list[Path] = []
    windows_fonts = Path("C:/Windows/Fonts")
    linux_fonts = Path("/usr/share/fonts/truetype/dejavu")
    for name in names:
        candidates.extend((windows_fonts / name, linux_fonts / name, Path(name)))
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default()
