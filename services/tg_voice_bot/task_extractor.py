from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from dateparser.search import search_dates
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_SPOKEN_HOUR_VALUES = {
    "ноль": 0,
    "нуля": 0,
    "один": 1,
    "одного": 1,
    "два": 2,
    "двух": 2,
    "три": 3,
    "трех": 3,
    "трёх": 3,
    "четыре": 4,
    "четырех": 4,
    "четырёх": 4,
    "пять": 5,
    "пяти": 5,
    "шесть": 6,
    "шести": 6,
    "семь": 7,
    "семи": 7,
    "восемь": 8,
    "восьми": 8,
    "девять": 9,
    "девяти": 9,
    "десять": 10,
    "десяти": 10,
    "одиннадцать": 11,
    "одиннадцати": 11,
    "двенадцать": 12,
    "двенадцати": 12,
    "тринадцать": 13,
    "тринадцати": 13,
    "четырнадцать": 14,
    "четырнадцати": 14,
    "пятнадцать": 15,
    "пятнадцати": 15,
    "шестнадцать": 16,
    "шестнадцати": 16,
    "семнадцать": 17,
    "семнадцати": 17,
    "восемнадцать": 18,
    "восемнадцати": 18,
    "девятнадцать": 19,
    "девятнадцати": 19,
    "двадцать": 20,
    "двадцати": 20,
    "двадцать один": 21,
    "двадцати одного": 21,
    "двадцать два": 22,
    "двадцати двух": 22,
    "двадцать три": 23,
    "двадцати трех": 23,
    "двадцати трёх": 23,
}
_SPOKEN_MINUTE_VALUES = {
    "ноль": 0,
    "ноль ноль": 0,
    "ровно": 0,
    "пятнадцать": 15,
    "тридцать": 30,
    "сорок пять": 45,
}
_SPOKEN_HOUR_PATTERN = "|".join(
    sorted(
        (re.escape(value) for value in _SPOKEN_HOUR_VALUES),
        key=len,
        reverse=True,
    )
)
_SPOKEN_MINUTE_PATTERN = "|".join(
    sorted(
        (re.escape(value) for value in _SPOKEN_MINUTE_VALUES),
        key=len,
        reverse=True,
    )
)

class TaskExtraction(BaseModel):
    """Результат интерпретации одной команды создания задачи."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schema_version: Literal["1.2"] = "1.2"
    intent: Literal["create_task", "unknown"]

    source_text: str

    title: str | None = None
    scheduled_date: date | None = None
    scheduled_time: time | None = None
    scheduled_end_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=1440)

    priority: Literal["low", "normal", "high"] = "normal"
    deadline_date: date | None = None
    deadline_time: time | None = None
    time_is_flexible: bool = False

    matched_date_text: str | None = None
    matched_time_text: str | None = None
    matched_duration_text: str | None = None
    matched_deadline_text: str | None = None
    matched_priority_text: str | None = None

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    requires_confirmation: bool = True
    clarification_question: str | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_time_range(self) -> "TaskExtraction":
        if self.scheduled_time is None and self.scheduled_end_time is not None:
            raise ValueError("Время окончания требует времени начала.")
        if self.scheduled_time is not None and self.scheduled_end_time is not None:
            start = self.scheduled_time.hour * 60 + self.scheduled_time.minute
            end = self.scheduled_end_time.hour * 60 + self.scheduled_end_time.minute
            if end <= start:
                raise ValueError("Время окончания должно быть позже времени начала.")
            if self.duration_minutes != end - start:
                raise ValueError("Длительность не соответствует диапазону времени.")
        if self.deadline_time is not None and self.deadline_date is None:
            raise ValueError("Время дедлайна требует дату дедлайна.")
        return self
    @field_validator("source_text")
    @classmethod
    def validate_source_text(cls, value: str) -> str:
        normalized = " ".join(value.split())

        if not normalized:
            raise ValueError(
                "Исходный текст не может быть пустым."
            )

        return normalized

    @field_validator("title")
    @classmethod
    def normalize_title(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = " ".join(value.split())
        normalized = normalized.strip(" ,.:;—–-")

        if not normalized:
            return None

        return normalized[0].upper() + normalized[1:]


class TaskExtractor:
    """
    Локальный детерминированный извлекатель задачи.

    Он:
    1. нормализует текст;
    2. отдельно находит явное время;
    3. ищет выражение даты;
    4. удаляет служебные части;
    5. формирует название;
    6. возвращает валидированную структуру.
    """

    _SPACES_PATTERN = re.compile(r"\s+")

    _COMMAND_PREFIX_PATTERN = re.compile(
        r"""
        ^\s*
        (?:
            пожалуйста[\s,]+
        )?
        (?:
            создай
            | добавь
            | запиши
            | поставь
            | запланируй
            | напомни
            | внеси
        )
        (?:\s+мне)?
        (?:\s+новую)?
        (?:
            \s+
            (?:
                задачу
                | напоминание
                | событие
            )
        )?
        [\s,:—–-]*
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    _POLITE_SUFFIX_PATTERN = re.compile(
        r"""
        [\s,]+
        (?:
            пожалуйста
            | будь\s+добр
        )
        [.!?]*\s*$
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    _TASK_WORD_PATTERN = re.compile(
        r"""
        \b
        (?:
            задача
            | задачу
            | напоминание
            | событие
        )
        \b
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    # 15:30, 9.00, в 18 30
    _NUMERIC_TIME_PATTERN = re.compile(
        r"""
        (?<!\d)
        (?P<hour>[01]?\d|2[0-3])
        (?:
            \s*[:.]\s*
            |
            \s+
        )
        (?P<minute>[0-5]\d)
        (?!\d)
        """,
        flags=re.VERBOSE,
    )

    _NUMERIC_TIME_RANGE_PATTERN = re.compile(
        r"""
        \b(?:с|от)?\s*
        (?P<start_hour>[01]?\d|2[0-3])
        (?:\s*[:.]\s*|\s+)?(?P<start_minute>[0-5]\d)?
        \s*(?:до|по|[-–—])\s*
        (?P<end_hour>[01]?\d|2[0-3])
        (?:\s*[:.]\s*|\s+)?(?P<end_minute>[0-5]\d)?
        (?!\d)
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    _SPOKEN_TIME_RANGE_PATTERN = re.compile(
        rf"""
        \b(?:с|от)\s+
        (?P<start_hour>{_SPOKEN_HOUR_PATTERN})
        (?:\s+(?P<start_minute>{_SPOKEN_MINUTE_PATTERN}))?
        \s+(?:до|по)\s+
        (?P<end_hour>{_SPOKEN_HOUR_PATTERN})
        (?:\s+(?P<end_minute>{_SPOKEN_MINUTE_PATTERN}))?
        \b
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )
    # в 15 часов, к 9 часам
    _HOUR_WORD_PATTERN = re.compile(
        r"""
        \b
        (?P<prefix>в|к|на)?\s*
        (?P<hour>[01]?\d|2[0-3])
        \s*
        (?:
            час
            | часа
            | часов
            | часу
        )
        \b
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    _BARE_HOUR_PATTERN = re.compile(
        r"""
        \b(?:в|на)\s+(?P<hour>[01]?\d|2[0-3])\b
        (?!\s*(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр))
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    _DAY_PART_PATTERNS: tuple[
        tuple[re.Pattern[str], time],
        ...
    ] = (
        (
            re.compile(
                r"\bутром\b",
                flags=re.IGNORECASE,
            ),
            time(9, 0),
        ),
        (
            re.compile(
                r"\bдн[её]м\b",
                flags=re.IGNORECASE,
            ),
            time(14, 0),
        ),
        (
            re.compile(
                r"\bвечером\b",
                flags=re.IGNORECASE,
            ),
            time(19, 0),
        ),
        (
            re.compile(
                r"\bночью\b",
                flags=re.IGNORECASE,
            ),
            time(23, 0),
        ),
        (
            re.compile(
                r"\bв\s+полдень\b|\bполдень\b",
                flags=re.IGNORECASE,
            ),
            time(12, 0),
        ),
        (
            re.compile(
                r"\bв\s+полночь\b|\bполночь\b",
                flags=re.IGNORECASE,
            ),
            time(0, 0),
        ),
    )

    _TRAILING_PREPOSITION_PATTERN = re.compile(
        r"""
        (?:
            ^|\s
        )
        (?:
            на
            | в
            | к
            | во
            | до
        )
        \s*$
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    _LEADING_CONNECTOR_PATTERN = re.compile(
        r"""
        ^\s*
        (?:
            и
            | чтобы
            | надо
            | нужно
            | не\s+(?:забуд(?:ь|ьте)?|забыть)
            | после\s+него
            | после\s+не[её]
        )
        \s+
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    _PRIORITY_HIGH_PATTERN = re.compile(
        r"\b(?P<value>срочно|обязательно|очень\s+важно|важно|приоритетно)\b",
        flags=re.IGNORECASE,
    )
    _PRIORITY_LOW_PATTERN = re.compile(
        r"\b(?P<value>если\s+успею|не\s+срочно|необязательно|по\s+возможности)\b",
        flags=re.IGNORECASE,
    )

    _DEADLINE_DATE_PATTERN = re.compile(
        r"""
        \b(?P<prefix>до|к)\s+
        (?P<value>
            сегодня|завтра|послезавтра|
            понедельник(?:а|у)?|вторник(?:а|у)?|сред(?:а|ы|у)|четверг(?:а|у)?|
            пятниц(?:а|ы|у)|суббот(?:а|ы|у)|воскресень(?:е|я|ю)|воскресени(?:е|я|ю)|
            [0-3]?\d[./-][01]?\d(?:[./-]\d{2,4})?|
            [0-3]?\d\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)
        )
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )
    _DEADLINE_TIME_PATTERN = re.compile(
        r"""
        \b(?P<prefix>до|к)\s+
        (?:(?:в|на)\s+)?
        (?P<hour>[01]?\d|2[0-3])
        (?:(?:\s*[:.]\s*|\s+)(?P<minute>[0-5]\d))?
        (?:\s*(?:час(?:а|ов|у)?))?
        \b
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )
    _COMPOUND_DURATION_PATTERN = re.compile(
        r"""
        \b(?:на\s+)?
        (?P<hours>\d+)\s*час(?:а|ов)?
        (?:\s+и)?\s+
        (?P<minutes>\d+)\s*минут(?:а|ы|у)?
        \b
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )
    _NUMERIC_DURATION_PATTERN = re.compile(
        r"""
        \b(?:на\s+)?
        (?P<value>\d+(?:[.,]\d+)?)\s*
        (?P<unit>минут(?:а|ы|у)?|мин\.?|час(?:а|ов)?)
        \b
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )
    _SIMPLE_DURATION_PATTERN = re.compile(
        r"\b(?P<value>полчаса|полтора\s+часа|час|два\s+часа|три\s+часа|четыре\s+часа)\b",
        flags=re.IGNORECASE,
    )
    _MULTI_TASK_SEPARATOR_PATTERN = re.compile(
        r"\s*(?:[;\n]+|,(?=\s*\S)|\s+(?:а\s+)?(?:потом|затем|далее|после\s+этого)\s+)\s*",
        flags=re.IGNORECASE,
    )
    _MULTI_TASK_AND_PATTERN = re.compile(
        r"""
        \s+и\s+(?=
            (?:
                не\s+(?:забуд(?:ь|ьте)?|забыть)|нужно|надо|ещ[её]|также|
                утром|дн[её]м|вечером|ночью|
                купить|позвонить|отправить|сделать|сходить|заехать|забрать|
                поработать|почитать|позаниматься|встретиться|записаться|оплатить|
                проверить|подготовить|закончить|начать|написать|ответить
            )\b
        )
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    def __init__(
        self,
        *,
        timezone: ZoneInfo,
        language: str = "ru",
    ) -> None:
        self._timezone = timezone
        self._language = language

    def extract(
        self,
        text: str,
        *,
        reference_datetime: datetime | None = None,
    ) -> TaskExtraction:
        normalized_text = self._normalize_text(text)
        reference_datetime = self._normalize_reference_datetime(reference_datetime)

        (
            extracted_time,
            extracted_end_time,
            range_duration_minutes,
            matched_time_text,
            invalid_time_range,
        ) = self._extract_explicit_time(normalized_text)

        time_is_flexible = any(
            pattern.search(matched_time_text or "") is not None
            for pattern, _ in self._DAY_PART_PATTERNS
        )

        priority, matched_priority_text = self._extract_priority(normalized_text)
        deadline_date, deadline_time, matched_deadline_text, deadline_date_inferred = self._extract_deadline(
            normalized_text,
            reference_datetime=reference_datetime,
            excluded_time_text=matched_time_text,
        )
        extracted_duration, matched_duration_text, duration_rounded = self._extract_duration(
            normalized_text,
            excluded_time_text=matched_time_text,
        )
        duration_minutes = range_duration_minutes or extracted_duration
        if range_duration_minutes is not None:
            matched_duration_text = None

        date_search_text = normalized_text
        if matched_time_text:
            date_search_text = self._remove_once(source=date_search_text, fragment=matched_time_text)
        if matched_duration_text:
            date_search_text = self._remove_once(source=date_search_text, fragment=matched_duration_text)
        if matched_priority_text:
            date_search_text = self._remove_once(source=date_search_text, fragment=matched_priority_text)
        date_search_text = self._DEADLINE_DATE_PATTERN.sub(" ", date_search_text)
        date_search_text = self._DEADLINE_TIME_PATTERN.sub(" ", date_search_text)

        date_matches = search_dates(
            date_search_text,
            languages=[self._language],
            settings={
                "RELATIVE_BASE": reference_datetime.replace(tzinfo=None),
                "PREFER_DATES_FROM": "future",
                "DATE_ORDER": "DMY",
                "PREFER_DAY_OF_MONTH": "current",
                "RETURN_AS_TIMEZONE_AWARE": False,
            },
        )

        matched_date_text: str | None = None
        scheduled_date: date | None = None
        parsed_datetime: datetime | None = None

        if date_matches:
            matched_date_text, parsed_datetime = self._select_best_date_match(
                matches=date_matches,
                source_text=date_search_text,
            )
            scheduled_date = parsed_datetime.date()

            if extracted_time is None and self._contains_relative_clock(matched_date_text):
                extracted_time = parsed_datetime.time().replace(second=0, microsecond=0)
                matched_time_text = matched_date_text
                time_is_flexible = False

        warnings: list[str] = []
        if scheduled_date is None and deadline_date is not None:
            scheduled_date = deadline_date
            warnings.append("date_inferred_from_deadline")

        if deadline_time is not None and deadline_date is None:
            deadline_date = scheduled_date or reference_datetime.date()
            deadline_date_inferred = True

        if deadline_date_inferred:
            warnings.append("deadline_date_inferred")

        title = self._extract_title(
            source_text=normalized_text,
            matched_date_text=matched_date_text,
            matched_time_text=matched_time_text,
            extra_fragments=(
                matched_duration_text,
                matched_deadline_text,
                matched_priority_text,
            ),
        )

        if scheduled_date is None:
            warnings.append("date_not_found")
        if extracted_time is None:
            warnings.append("time_not_found")
        if invalid_time_range:
            warnings.append("invalid_time_range")
        if duration_rounded:
            warnings.append("duration_rounded_to_15")
        if title is None:
            warnings.append("title_not_found")

        deadline_invalid = False
        if scheduled_date is not None and deadline_date is not None:
            if deadline_date < scheduled_date:
                deadline_invalid = True
            elif (
                deadline_date == scheduled_date
                and deadline_time is not None
                and extracted_time is not None
                and not time_is_flexible
            ):
                start_minute = extracted_time.hour * 60 + extracted_time.minute
                deadline_minute = deadline_time.hour * 60 + deadline_time.minute
                if start_minute >= deadline_minute:
                    deadline_invalid = True
        if deadline_invalid:
            warnings.append("deadline_before_schedule")

        if invalid_time_range:
            clarification = (
                "Время окончания должно быть позже времени начала. Уточните диапазон."
            )
        elif title is None:
            clarification = "Как назвать задачу?"
        elif scheduled_date is None:
            clarification = "На какую дату создать задачу?"
        elif deadline_invalid:
            clarification = "Дедлайн получается раньше запланированного времени. Уточните дату или время."
        else:
            clarification = None

        is_complete_enough = (
            title is not None
            and scheduled_date is not None
            and not invalid_time_range
            and not deadline_invalid
        )
        confidence = self._calculate_confidence(
            title=title,
            scheduled_date=scheduled_date,
            scheduled_time=extracted_time,
        )

        return TaskExtraction(
            intent="create_task" if is_complete_enough else "unknown",
            source_text=normalized_text,
            title=title,
            scheduled_date=scheduled_date,
            scheduled_time=extracted_time,
            scheduled_end_time=extracted_end_time,
            duration_minutes=duration_minutes,
            priority=priority,
            deadline_date=deadline_date,
            deadline_time=deadline_time,
            time_is_flexible=time_is_flexible,
            matched_date_text=matched_date_text,
            matched_time_text=matched_time_text,
            matched_duration_text=matched_duration_text,
            matched_deadline_text=matched_deadline_text,
            matched_priority_text=matched_priority_text,
            confidence=confidence,
            requires_confirmation=True,
            clarification_question=clarification,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def extract_many(
        self,
        text: str,
        *,
        reference_datetime: datetime | None = None,
    ) -> list[TaskExtraction]:
        """Извлекает одну или несколько задач и переносит общий контекст даты."""
        normalized_text = self._normalize_text(text)
        reference_datetime = self._normalize_reference_datetime(reference_datetime)
        chunks = [
            item.strip(" ,.;")
            for item in self._MULTI_TASK_SEPARATOR_PATTERN.split(normalized_text)
            if item.strip(" ,.;")
        ]
        expanded: list[str] = []
        for chunk in chunks:
            expanded.extend(
                item.strip(" ,.;")
                for item in self._MULTI_TASK_AND_PATTERN.split(chunk)
                if item.strip(" ,.;")
            )
        if not expanded:
            expanded = [normalized_text]

        results: list[TaskExtraction] = []
        inherited_date: date | None = None
        for chunk in expanded:
            extraction = self.extract(chunk, reference_datetime=reference_datetime)
            has_explicit_date = self._has_explicit_calendar_date(extraction.matched_date_text)
            if inherited_date is not None and not has_explicit_date:
                updates: dict[str, object] = {"scheduled_date": inherited_date}
                warnings = [w for w in extraction.warnings if w != "date_not_found"]
                if "deadline_date_inferred" in warnings and extraction.deadline_time is not None:
                    updates["deadline_date"] = inherited_date
                updates["warnings"] = tuple(dict.fromkeys(warnings + ["date_inherited_from_previous_task"]))
                if extraction.title is not None and "invalid_time_range" not in warnings and "deadline_before_schedule" not in warnings:
                    updates["intent"] = "create_task"
                    updates["clarification_question"] = None
                extraction = extraction.model_copy(update=updates)
            if extraction.scheduled_date is not None and (has_explicit_date or inherited_date is None):
                inherited_date = extraction.scheduled_date
            results.append(extraction)

        return results

    @staticmethod
    def _has_explicit_calendar_date(value: str | None) -> bool:
        if not value:
            return False
        normalized = value.casefold()
        markers = (
            "сегодня", "завтра", "послезавтра", "понедель", "вторник",
            "сред", "четвер", "пятниц", "суббот", "воскрес",
            "январ", "феврал", "март", "апрел", "мая", "июн",
            "июл", "август", "сентябр", "октябр", "ноябр", "декабр",
            "через",
        )
        return any(marker in normalized for marker in markers) or bool(
            re.search(r"\b[0-3]?\d[./-][01]?\d(?:[./-]\d{2,4})?\b", normalized)
        )

    def _extract_priority(self, source_text: str) -> tuple[Literal["low", "normal", "high"], str | None]:
        low = self._PRIORITY_LOW_PATTERN.search(source_text)
        if low is not None:
            return "low", low.group(0)
        high = self._PRIORITY_HIGH_PATTERN.search(source_text)
        if high is not None:
            return "high", high.group(0)
        return "normal", None

    def _extract_deadline(
        self,
        source_text: str,
        *,
        reference_datetime: datetime,
        excluded_time_text: str | None,
    ) -> tuple[date | None, time | None, str | None, bool]:
        searchable = source_text
        if excluded_time_text:
            searchable = self._remove_once(source=searchable, fragment=excluded_time_text)

        date_match = self._DEADLINE_DATE_PATTERN.search(searchable)
        deadline_date: date | None = None
        date_text: str | None = None
        if date_match is not None:
            date_text = date_match.group(0)
            deadline_value = self._normalize_deadline_date_value(date_match.group("value"))
            parsed = search_dates(
                deadline_value,
                languages=[self._language],
                settings={
                    "RELATIVE_BASE": reference_datetime.replace(tzinfo=None),
                    "PREFER_DATES_FROM": "future",
                    "DATE_ORDER": "DMY",
                    "RETURN_AS_TIMEZONE_AWARE": False,
                },
            )
            if parsed:
                deadline_date = parsed[0][1].date()

        time_searchable = searchable
        if date_text:
            time_searchable = self._remove_once(source=time_searchable, fragment=date_text)
        time_match = self._DEADLINE_TIME_PATTERN.search(time_searchable)
        deadline_time: time | None = None
        time_text: str | None = None
        if time_match is not None:
            hour = int(time_match.group("hour"))
            minute = int(time_match.group("minute") or 0)
            deadline_time = time(hour, minute)
            time_text = time_match.group(0)

        fragments = [item for item in (date_text, time_text) if item]
        matched_text = None if not fragments else " ".join(fragments)
        return deadline_date, deadline_time, matched_text, False

    @staticmethod
    def _normalize_deadline_date_value(value: str) -> str:
        normalized = value.casefold().strip()
        weekday_forms = {
            "понедельника": "понедельник",
            "понедельнику": "понедельник",
            "вторника": "вторник",
            "вторнику": "вторник",
            "среды": "среда",
            "среду": "среда",
            "четверга": "четверг",
            "четвергу": "четверг",
            "пятницы": "пятница",
            "пятницу": "пятница",
            "субботы": "суббота",
            "субботу": "суббота",
            "воскресенья": "воскресенье",
            "воскресенью": "воскресенье",
            "воскресения": "воскресенье",
            "воскресению": "воскресенье",
        }
        return weekday_forms.get(normalized, value)

    def _extract_duration(
        self,
        source_text: str,
        *,
        excluded_time_text: str | None,
    ) -> tuple[int | None, str | None, bool]:
        searchable = source_text
        if excluded_time_text:
            searchable = self._remove_once(source=searchable, fragment=excluded_time_text)

        compound = self._COMPOUND_DURATION_PATTERN.search(searchable)
        if compound is not None:
            prefix = searchable[max(0, compound.start() - 8):compound.start()].casefold()
            if "через" not in prefix:
                minutes = int(compound.group("hours")) * 60 + int(compound.group("minutes"))
                if minutes >= 15:
                    rounded = ((minutes + 14) // 15) * 15
                    return min(rounded, 1440), compound.group(0), rounded != minutes

        match = self._NUMERIC_DURATION_PATTERN.search(searchable)
        if match is not None:
            prefix = searchable[max(0, match.start() - 8):match.start()].casefold()
            if "через" not in prefix:
                value = float(match.group("value").replace(",", "."))
                unit = match.group("unit").casefold()
                minutes = int(round(value * 60)) if "час" in unit else int(round(value))
                if minutes >= 15:
                    rounded = ((minutes + 14) // 15) * 15
                    return min(rounded, 1440), match.group(0), rounded != minutes

        simple = self._SIMPLE_DURATION_PATTERN.search(searchable)
        if simple is not None:
            prefix = searchable[max(0, simple.start() - 8):simple.start()].casefold()
            if "через" not in prefix:
                normalized = " ".join(simple.group("value").casefold().split())
                minutes = {
                    "полчаса": 30,
                    "полтора часа": 90,
                    "час": 60,
                    "два часа": 120,
                    "три часа": 180,
                    "четыре часа": 240,
                }[normalized]
                return minutes, simple.group(0), False

        return None, None, False

    @staticmethod
    def _contains_relative_clock(value: str) -> bool:
        normalized = value.casefold()
        return (
            "через" in normalized
            and any(
                unit in normalized
                for unit in (
                    "час",
                    "минут",
                )
            )
        )

    def _extract_explicit_time(
        self,
        source_text: str,
    ) -> tuple[
        time | None,
        time | None,
        int | None,
        str | None,
        bool,
    ]:
        numeric_range = self._NUMERIC_TIME_RANGE_PATTERN.search(source_text)
        if numeric_range:
            start_hour = int(numeric_range.group("start_hour"))
            start_minute = int(numeric_range.group("start_minute") or 0)
            end_hour = int(numeric_range.group("end_hour"))
            end_minute = int(numeric_range.group("end_minute") or 0)
            return self._build_time_range(
                start_hour=start_hour,
                start_minute=start_minute,
                end_hour=end_hour,
                end_minute=end_minute,
                matched_text=numeric_range.group(0),
            )

        spoken_range = self._SPOKEN_TIME_RANGE_PATTERN.search(source_text)
        if spoken_range:
            start_hour = _SPOKEN_HOUR_VALUES[
                spoken_range.group("start_hour").casefold()
            ]
            end_hour = _SPOKEN_HOUR_VALUES[
                spoken_range.group("end_hour").casefold()
            ]
            start_minute_text = spoken_range.group("start_minute")
            end_minute_text = spoken_range.group("end_minute")
            start_minute = (
                _SPOKEN_MINUTE_VALUES[start_minute_text.casefold()]
                if start_minute_text
                else 0
            )
            end_minute = (
                _SPOKEN_MINUTE_VALUES[end_minute_text.casefold()]
                if end_minute_text
                else 0
            )
            return self._build_time_range(
                start_hour=start_hour,
                start_minute=start_minute,
                end_hour=end_hour,
                end_minute=end_minute,
                matched_text=spoken_range.group(0),
            )

        # После проверки явных диапазонов исключаем дедлайны из поиска
        # времени начала. Иначе фраза «до пятницы до 18:00» ошибочно
        # превращает 18:00 во время старта задачи.
        searchable = self._DEADLINE_DATE_PATTERN.sub(" ", source_text)
        searchable = self._DEADLINE_TIME_PATTERN.sub(" ", searchable)

        numeric_match = self._NUMERIC_TIME_PATTERN.search(searchable)
        if numeric_match:
            hour = int(numeric_match.group("hour"))
            minute = int(numeric_match.group("minute"))
            return time(hour, minute), None, None, numeric_match.group(0), False

        hour_match = self._HOUR_WORD_PATTERN.search(searchable)
        if hour_match:
            hour = int(hour_match.group("hour"))
            prefix = hour_match.group("prefix")
            if prefix is not None or hour >= 5:
                return time(hour, 0), None, None, hour_match.group(0), False

        bare_hour = self._BARE_HOUR_PATTERN.search(searchable)
        if bare_hour:
            hour = int(bare_hour.group("hour"))
            return time(hour, 0), None, None, bare_hour.group(0), False

        for pattern, inferred_time in self._DAY_PART_PATTERNS:
            match = pattern.search(searchable)
            if match:
                return inferred_time, None, None, match.group(0), False

        return None, None, None, None, False

    @staticmethod
    def _build_time_range(
        *,
        start_hour: int,
        start_minute: int,
        end_hour: int,
        end_minute: int,
        matched_text: str,
    ) -> tuple[time | None, time | None, int | None, str, bool]:
        start_total = start_hour * 60 + start_minute
        end_total = end_hour * 60 + end_minute
        if end_total <= start_total:
            return None, None, None, matched_text, True
        return (
            time(start_hour, start_minute),
            time(end_hour, end_minute),
            end_total - start_total,
            matched_text,
            False,
        )

    def _select_best_date_match(
        self,
        *,
        matches: list[tuple[str, datetime]],
        source_text: str,
    ) -> tuple[str, datetime]:
        """
        Выбираем наиболее информативное совпадение.

        Приоритет:
        1. выражения с календарными словами;
        2. более длинные совпадения;
        3. совпадения, не состоящие только из времени.
        """

        calendar_words = (
            "сегодня",
            "завтра",
            "послезавтра",
            "понедельник",
            "вторник",
            "сред",
            "четверг",
            "пятниц",
            "суббот",
            "воскрес",
            "январ",
            "феврал",
            "март",
            "апрел",
            "ма",
            "июн",
            "июл",
            "август",
            "сентябр",
            "октябр",
            "ноябр",
            "декабр",
            "через",
        )

        def score(
            item: tuple[str, datetime],
        ) -> tuple[int, int]:
            matched_text = item[0].casefold()

            calendar_score = sum(
                word in matched_text
                for word in calendar_words
            )

            return calendar_score, len(matched_text)

        return max(matches, key=score)

    def _extract_title(
        self,
        *,
        source_text: str,
        matched_date_text: str | None,
        matched_time_text: str | None,
        extra_fragments: tuple[str | None, ...] = (),
    ) -> str | None:
        title = source_text

        # Сначала удаляем полное выражение даты.
        # Оно может уже содержать время.
        if matched_date_text:
            date_fragment = re.sub(
                r"\s+(?:с|от)\s*$",
                "",
                matched_date_text,
                flags=re.IGNORECASE,
            )
            title = self._remove_once(
                source=title,
                fragment=date_fragment,
            )

        # Если время не вошло в dateparser-совпадение,
        # удаляем его отдельно.
        if (
            matched_time_text
            and matched_time_text.casefold()
            not in (matched_date_text or "").casefold()
        ):
            title = self._remove_once(
                source=title,
                fragment=matched_time_text,
            )

        for fragment in extra_fragments:
            if fragment and fragment.casefold() in title.casefold():
                title = self._remove_once(source=title, fragment=fragment)

        # Удаляем служебные признаки даже если несколько дедлайновых фрагментов
        # были распознаны отдельно (например: «до пятницы до 18:00»).
        title = self._DEADLINE_DATE_PATTERN.sub(" ", title)
        title = self._DEADLINE_TIME_PATTERN.sub(" ", title)
        title = self._PRIORITY_LOW_PATTERN.sub(" ", title)
        title = self._PRIORITY_HIGH_PATTERN.sub(" ", title)

        title = self._COMMAND_PREFIX_PATTERN.sub(
            "",
            title,
            count=1,
        )

        title = self._TASK_WORD_PATTERN.sub(
            " ",
            title,
        )

        title = self._POLITE_SUFFIX_PATTERN.sub(
            "",
            title,
        )

        title = self._LEADING_CONNECTOR_PATTERN.sub(
            "",
            title,
            count=1,
        )

        title = self._TRAILING_PREPOSITION_PATTERN.sub(
            "",
            title,
        )

        title = self._SPACES_PATTERN.sub(
            " ",
            title,
        )

        title = title.strip(" ,.:;!?—–-")

        if not title:
            return None

        return title[0].upper() + title[1:]

    def _remove_once(
        self,
        *,
        source: str,
        fragment: str,
    ) -> str:
        return re.sub(
            re.escape(fragment),
            " ",
            source,
            count=1,
            flags=re.IGNORECASE,
        )

    def _calculate_confidence(
        self,
        *,
        title: str | None,
        scheduled_date: date | None,
        scheduled_time: time | None,
    ) -> float:
        confidence = 0.2

        if title:
            confidence += 0.4

        if scheduled_date:
            confidence += 0.3

        if scheduled_time:
            confidence += 0.1

        return min(confidence, 1.0)

    def _normalize_reference_datetime(
        self,
        value: datetime | None,
    ) -> datetime:
        if value is None:
            return datetime.now(self._timezone)

        if value.tzinfo is None:
            return value.replace(
                tzinfo=self._timezone
            )

        return value.astimezone(self._timezone)

    def _normalize_text(self, value: str) -> str:
        normalized = self._SPACES_PATTERN.sub(
            " ",
            value,
        ).strip()

        if not normalized:
            raise ValueError(
                "Текст сообщения не может быть пустым."
            )

        return normalized