from typing import Literal

from fastapi import APIRouter, Query, Request

from parrilladas.modules.accounts.dependencies import Admin

from .telemetry_contracts import Operation, TelemetryReport

router = APIRouter(prefix="/assistant/telemetry", tags=["assistant"])


@router.get("", response_model=TelemetryReport)
def telemetry(
    context: Admin,
    request: Request,
    days: Literal["1", "7", "30"] = "7",
    operation: Operation | None = None,
    page: int = Query(default=1, ge=1, le=10000),
):
    state = request.app.state
    return state.telemetry.report(
        settings=state.assistant_settings,
        days=int(days),
        operation=operation,
        page=page,
        runtime={
            "natural_language_available": state.assistant.enabled,
            "rag_available": state.knowledge.provider is not None,
        },
    )
