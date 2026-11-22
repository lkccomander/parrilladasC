"""Deterministic Spanish relative-date parsing for event requests."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class ParsedEventDate:
    value: date
    evidence: str


@dataclass(frozen=True)
class ParsedEventWeek:
    week_start: date
    evidence: str


_WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}
_DAY_PATTERN = r"lunes|martes|mi[eé]rcoles|jueves|viernes|s[áa]bado|domingo"


def _fold(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(char) != "Mn"
    )


def _weekday(value: str) -> int:
    return _WEEKDAYS[_fold(value)]


def parse_relative_event_date(message: str, reference_date: date) -> ParsedEventDate | None:
    """Resolve only explicit, unambiguous relative Spanish date expressions."""
    patterns = (
        rf"(?P<weekday>{_DAY_PATTERN})\s+(?:dentro de|en)\s+(?P<weeks>\d+)\s+semanas?",
        rf"(?:dentro de|en)\s+(?P<weeks>\d+)\s+semanas?\s+(?:el\s+)?(?P<weekday>{_DAY_PATTERN})",
    )
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            base = reference_date + timedelta(weeks=int(match.group("weeks")))
            delta = (_weekday(match.group("weekday")) - base.weekday()) % 7
            return ParsedEventDate(base + timedelta(days=delta), match.group(0))

    match = re.search(r"(?:dentro de|en)\s+(?P<count>\d+)\s+d[ií]as?", message, re.IGNORECASE)
    if match:
        return ParsedEventDate(
            reference_date + timedelta(days=int(match.group("count"))), match.group(0)
        )

    match = re.search(r"\bpasado\s+ma[ñn]ana\b", message, re.IGNORECASE)
    if match:
        return ParsedEventDate(reference_date + timedelta(days=2), match.group(0))
    match = re.search(r"\bma[ñn]ana\b", message, re.IGNORECASE)
    if match:
        return ParsedEventDate(reference_date + timedelta(days=1), match.group(0))
    match = re.search(r"\bhoy\b", message, re.IGNORECASE)
    if match:
        return ParsedEventDate(reference_date, match.group(0))

    match = re.search(
        rf"(?:el\s+)?pr[oó]ximo\s+(?P<weekday>{_DAY_PATTERN})", message, re.IGNORECASE
    )
    if match:
        weekday = _weekday(match.group("weekday"))
        delta = (weekday - reference_date.weekday()) % 7 or 7
        return ParsedEventDate(reference_date + timedelta(days=delta), match.group(0))
    return None


def parse_relative_event_week(message: str, reference_date: date) -> ParsedEventWeek | None:
    """Resolve a relative week while retaining the day as an explicit follow-up."""
    match = re.search(
        r"\b(?:en|dentro de)\s+(?P<weeks>\d+)\s+semanas?\b",
        message,
        re.IGNORECASE,
    )
    if not match and re.search(
        r"\b(?:la\s+)?(?:otra|pr[oó]xima)\s+semana\b", message, re.IGNORECASE
    ):
        weeks = 1
        evidence = re.search(r"\b(?:la\s+)?(?:otra|pr[oó]xima)\s+semana\b", message, re.IGNORECASE)
    elif match:
        weeks = int(match.group("weeks"))
        evidence = match
    else:
        return None
    target = reference_date + timedelta(weeks=weeks)
    return ParsedEventWeek(
        target - timedelta(days=target.weekday()),
        evidence.group(0),
    )


def resolve_weekday_in_week(message: str, week_start: date) -> ParsedEventDate | None:
    pattern = r"\s*(?:el\s+)?(?P<weekday>" + _DAY_PATTERN + r")\s*[.!?]*\s*"
    match = re.fullmatch(pattern, message, re.IGNORECASE)
    if not match:
        return None
    value = week_start + timedelta(days=_weekday(match.group("weekday")))
    return ParsedEventDate(value, match.group(0).strip())
