"""Conservative authorization for customer-requested human attention."""

import re
import unicodedata


def requests_human(message: str) -> bool:
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", message.casefold())
        if not unicodedata.combining(char)
    )
    if re.search(r"\b(no|sin|nunca)\b", text):
        return False
    person = r"(?:asesor|persona|humano|humana|daniel|agente)"
    if re.fullmatch(rf"\s*(?:un |una )?{person}[.!?\s]*", text):
        return True
    return bool(
        re.search(
            rf"\b(?:hablar|hablo|contactar|comunicarme|pasame|atenderme)\b.{{0,45}}\b{person}\b",
            text,
        )
        or re.search(rf"\b(?:quiero|necesito|busco|prefiero)\s+(?:un |una |a )?{person}\b", text)
    )
