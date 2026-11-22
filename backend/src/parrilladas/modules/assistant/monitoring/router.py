from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from parrilladas.modules.accounts.dependencies import Csrf, Dev

from .schemas import EvalRunView, MonitoringReport, TraceDetail

router = APIRouter(prefix="/rag/monitoring", tags=["rag-monitoring"])


class EvalStart(BaseModel):
    set_id: UUID


@router.get("/summary", response_model=MonitoringReport)
def summary(context: Dev, request: Request, days: int = Query(default=7, ge=1, le=30)):
    if days not in (1, 7, 30):
        raise HTTPException(422, "El rango debe ser 1, 7 o 30 días.")
    return request.app.state.monitoring.report(days=days)


@router.get("/traces/{trace_id}", response_model=TraceDetail)
def trace(trace_id: UUID, context: Dev, request: Request):
    result = request.app.state.monitoring.trace(trace_id)
    if result is None:
        raise HTTPException(404, "Traza no disponible.")
    return result


@router.post("/eval-runs", response_model=EvalRunView)
def start_eval(context: Dev, request: Request, csrf: Csrf, payload: EvalStart):
    if not request.app.state.assistant_settings.rag_eval_enabled:
        raise HTTPException(409, "Las evaluaciones están deshabilitadas en el API.")
    try:
        result = request.app.state.evaluations.enqueue(payload.set_id)
    except LookupError:
        raise HTTPException(404, "Conjunto de evaluación no encontrado.") from None
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return request.app.state.monitoring.eval_run_view(result)


@router.get("/eval-runs/{run_id}", response_model=EvalRunView)
def eval_run(run_id: UUID, context: Dev, request: Request):
    result = request.app.state.monitoring.eval_report(run_id)
    if result is None:
        raise HTTPException(404, "Evaluación no disponible.")
    return result
