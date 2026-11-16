"""Read explicit Spanish calendar components without inferring a year."""

import re

MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
_MONTH = "(?:" + "|".join((*MONTHS, "setiembre")) + ")"
_YEAR = r"(?:\s+(?:de\s+|del\s+)?(?P<year>[0-9]{4}))?"
_PATTERNS = (
    re.compile(rf"(?:el\s+)?(?P<day>[0-9]{{1,2}})\s+(?:de\s+)?(?P<month>{_MONTH}){_YEAR}"),
    re.compile(rf"(?P<month>{_MONTH})\s+(?P<day>[0-9]{{1,2}}){_YEAR}"),
)


def parse_date_answer(message: str, pending: dict | None) -> tuple[int, int, int | None] | None:
    """Only whole date answers qualify; mixed messages remain with the extractor."""
    text = " ".join(message.casefold().strip().rstrip(".!?").split())
    for pattern in _PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            month = match["month"].replace("setiembre", "septiembre")
            return (
                int(match["day"]),
                MONTHS.index(month) + 1,
                (int(match["year"]) if match["year"] else None),
            )
    year = re.fullmatch(r"(?:(?:en|año|el año)\s+)?([0-9]{4})", text)
    if (
        year
        and isinstance(pending, dict)
        and type(pending.get("day")) is int
        and type(pending.get("month")) is int
    ):
        return pending["day"], pending["month"], int(year[1])
    return None
