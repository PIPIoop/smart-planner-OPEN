from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from typing import Literal


FinanceKind = Literal["expense", "income", "transfer"]
FinanceQuery = Literal["balance", "month_expense", "top_categories"]


@dataclass(frozen=True)
class FinanceIntent:
    kind: FinanceKind
    amount_cents: int
    note: str
    category_hint: str | None = None
    account_hint: str | None = None
    to_account_hint: str | None = None


_CATEGORY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("food", ("продукт", "еда", "магазин", "супермаркет")),
    ("transport", ("такси", "транспорт", "бензин", "топливо", "метро", "автобус")),
    ("housing", ("аренд", "квартир", "жкх", "коммун")),
    ("entertainment", ("кино", "развлеч", "игр", "бар", "кафе", "ресторан")),
    ("subscriptions", ("подпис", "spotify", "youtube", "яндекс плюс")),
    ("health", ("лекар", "аптек", "врач", "здоров")),
    ("education", ("курс", "обуч", "книг", "англий")),
    ("shopping", ("одеж", "покупк", "техник", "маркетплейс")),
)

_MONTH_NAMES = (
    "январ", "феврал", "март", "апрел", "мая", "май", "июн", "июл",
    "август", "сентябр", "октябр", "ноябр", "декабр",
)

_MONEY_RE = re.compile(
    r"(?P<number>\d+(?:[\s\u00a0]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*"
    r"(?P<scale>млн|миллион(?:а|ов)?|тыс(?:\.|яч(?:а|и|у|ей)?)?)?\s*"
    r"(?:₽|руб(?:\.|ля|лей|ль)?|р\b)?",
    re.IGNORECASE,
)


def _money_to_cents(text: str) -> int | None:
    candidates: list[tuple[int, int, int]] = []
    for match in _MONEY_RE.finditer(text):
        suffix = text[match.end():].lstrip()
        prefix = text[:match.start()].rstrip()
        has_explicit_money_unit = bool(match.group("scale")) or bool(
            re.search(r"(?:₽|руб|\bр\b)", match.group(0), re.IGNORECASE)
        )
        if not has_explicit_money_unit:
            if suffix.startswith((':', '.', '-')) or prefix.endswith(('.', '-')):
                continue
            next_word_match = re.match(r"([а-яa-z]+)", suffix, re.IGNORECASE)
            next_word = next_word_match.group(1).casefold() if next_word_match else ""
            if any(next_word.startswith(month) for month in _MONTH_NAMES):
                continue
        raw = match.group("number").replace(" ", "").replace("\u00a0", "").replace(",", ".")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        scale = (match.group("scale") or "").casefold()
        multiplier = 1
        if scale.startswith("тыс"):
            multiplier = 1_000
        elif scale.startswith("млн") or scale.startswith("миллион"):
            multiplier = 1_000_000
        cents_decimal = value * multiplier * 100
        if cents_decimal != cents_decimal.to_integral_value():
            # Денежные значения храним строго в копейках и никогда не округляем молча.
            continue
        cents = int(cents_decimal)
        if cents <= 0:
            continue
        has_currency = bool(re.search(r"(?:₽|руб|\bр\b)", match.group(0), re.IGNORECASE))
        score = 2 if has_currency or scale else 1
        candidates.append((score, match.start(), cents))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def detect_finance_query(text: str) -> FinanceQuery | None:
    normalized = " ".join(text.casefold().replace("ё", "е").split())
    if any(phrase in normalized for phrase in ("сколько осталось денег", "сколько денег осталось", "мой баланс", "какой баланс", "сколько на счетах")):
        return "balance"
    if ("сколько" in normalized and "потрат" in normalized) or "расходы за месяц" in normalized or "расходы в этом месяце" in normalized:
        return "month_expense"
    if any(phrase in normalized for phrase in ("на что больше всего трачу", "куда уходят деньги", "главные расходы", "топ расходов")):
        return "top_categories"
    return None


def extract_finance_intent(text: str) -> FinanceIntent | None:
    normalized = " ".join(text.casefold().replace("ё", "е").split())
    amount = _money_to_cents(normalized)
    if amount is None:
        return None

    kind: FinanceKind | None = None
    if re.search(r"\b(перевел|перевела|перевести|перевод|перекинул|перекинула)\b", normalized):
        kind = "transfer"
    elif re.search(r"\b(получил|получила|заработал|заработала|доход|зарплат|пришло|поступило)\b", normalized):
        kind = "income"
    elif re.search(r"\b(потратил|потратила|потратить|расход|купил|купила|оплатил|оплатила|списал|списала)\b", normalized):
        kind = "expense"
    if kind is None:
        return None

    category_hint = None
    if kind == "expense":
        for category_id, hints in _CATEGORY_HINTS:
            if any(hint in normalized for hint in hints):
                category_hint = category_id
                break

    to_account_hint = None
    if kind == "transfer":
        match = re.search(r"\bна\s+([а-яa-z0-9 _-]{2,40})", normalized)
        if match:
            to_account_hint = match.group(1).strip(" .,!")

    account_hint = None
    match = re.search(r"\b(?:с|со)\s+([а-яa-z0-9 _-]{2,40}?)(?=\s+на\b|\s+за\b|$)", normalized)
    if match:
        account_hint = match.group(1).strip(" .,!")

    return FinanceIntent(
        kind=kind,
        amount_cents=amount,
        note=text.strip(),
        category_hint=category_hint,
        account_hint=account_hint,
        to_account_hint=to_account_hint,
    )
