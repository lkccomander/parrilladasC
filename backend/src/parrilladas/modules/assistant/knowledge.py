"""Retrieve approved single-business facts; never generate commercial claims."""

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .schemas import KnowledgeTopic


class MenuItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    category_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=120)
    active: bool = Field(strict=True)


class Coverage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    country_code: Literal["CR"]
    country_name: Literal["Costa Rica"]
    nationwide: bool = Field(strict=True)
    provinces: list[str] = Field(min_length=1, max_length=7)


class ApprovedMenu(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: Literal[1]
    content_version: int = Field(ge=1, strict=True)
    tenant_id: Literal["parrilladas"]
    prepared_on_site: bool = Field(strict=True)
    coverage: Coverage
    items: list[MenuItem]

    @model_validator(mode="after")
    def unique_items(self):
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("Menu IDs must be unique")
        return self


@dataclass(frozen=True)
class KnowledgeAnswer:
    text: str
    source: str | None = None


def load_menu() -> ApprovedMenu | None:
    """Wheel resource in production; canonical editable file in a source checkout."""
    resource = files(__package__).joinpath("data/menu.json")
    try:
        if resource.is_file():
            raw = resource.read_text(encoding="utf-8")
        else:
            raw = (
                Path(__file__).resolve().parents[5] / "knowledge/parrilladas/menu.json"
            ).read_text(encoding="utf-8")
        return ApprovedMenu.model_validate_json(raw)
    except (OSError, ValidationError):
        return None


def answer_question(topic: KnowledgeTopic, *, tenant_id: str) -> KnowledgeAnswer:
    """Topics select bounded templates, never model-written answers or prices."""
    unknown = KnowledgeAnswer(
        "Ese detalle necesito confirmarlo con un asesor. ¿Quieres que te ponga en contacto?"
    )
    if tenant_id != "parrilladas":
        return unknown
    if topic == "pricing":
        return KnowledgeAnswer(
            "La cotización se prepara de forma personalizada y un asesor confirma los precios. "
            "Puedo ayudarte a reunir los datos de tu evento."
        )
    if topic == "availability":
        return KnowledgeAnswer(
            "La fecha y la disponibilidad deben ser confirmadas por un asesor. "
            "Puedo ayudarte a preparar la solicitud; esto no reserva el evento."
        )
    if topic == "general":
        return KnowledgeAnswer(
            "¡Con gusto! ¿Quieres conocer el menú, nuestra cobertura o preparar una cotización?"
        )
    if topic in {"allergens", "policies"}:
        return unknown
    menu = load_menu()
    if menu is None:
        return unknown
    source = f"menu:v{menu.content_version}:{topic}"
    if topic == "menu":
        names = [item.name for item in menu.items if item.active]
        if not names:
            return unknown
        return KnowledgeAnswer(
            "Nuestro menú incluye estas opciones: " + ", ".join(names) + ". "
            "Un asesor confirma la combinación y los detalles de tu evento.",
            source,
        )
    if topic == "coverage":
        coverage = menu.coverage
        return KnowledgeAnswer(
            "Atendemos en " + ", ".join(coverage.provinces) + ", Costa Rica. "
            "La cobertura no confirma disponibilidad para una fecha ni costos de traslado.",
            source,
        )
    if topic == "preparation" and menu.prepared_on_site:
        return KnowledgeAnswer("Cocinamos en el lugar del evento.", source)
    return unknown
