import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from parrilladas.modules.accounts.dependencies import Csrf, Dev

from .schemas import EvalRunView, MonitoringHealth, MonitoringReport, TraceDetail

router = APIRouter(prefix="/rag/monitoring", tags=["rag-monitoring"])


class EvalStart(BaseModel):
    set_id: UUID


@router.get("/summary", response_model=MonitoringReport)
def summary(context: Dev, request: Request, days: int = Query(default=7, ge=1, le=30)):
    if days not in (1, 7, 30):
        raise HTTPException(422, "El rango debe ser 1, 7 o 30 días.")
    return request.app.state.monitoring.report(days=days)


@router.get("/health", response_model=MonitoringHealth)
def health(
    context: Dev,
    request: Request,
    response: Response,
    days: int = Query(default=1, ge=1, le=30),
):
    """Return a current, non-cacheable RAG/vector health snapshot.

    The Admin normally uses this endpoint with a short polling interval.  SSE is
    available separately for clients that need a continuous stream, while this
    bounded response remains usable behind proxies that do not support streaming.
    """
    if days not in (1, 7, 30):
        raise HTTPException(422, "El rango debe ser 1, 7 o 30 días.")
    snapshot = request.app.state.monitoring.health(days=days)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["X-RAG-Health-Generated-At"] = snapshot.generated_at.isoformat()
    response.headers["X-RAG-Health-Status"] = snapshot.status
    return snapshot


@router.get("/stream")
async def stream(
    context: Dev,
    request: Request,
    days: int = Query(default=7, ge=1, le=30),
    interval: int = Query(default=5, ge=2, le=60),
):
    """Stream fresh snapshots for the Dev dashboard without retaining customer data."""
    if days not in (1, 7, 30):
        raise HTTPException(422, "El rango debe ser 1, 7 o 30 días.")

    async def events():
        while not await request.is_disconnected():
            try:
                snapshot = await run_in_threadpool(request.app.state.monitoring.health, days=days)
                yield f"event: monitoring\ndata: {snapshot.model_dump_json()}\n\n"
            except Exception:
                # Do not expose database/provider details through a long-lived stream.
                yield 'event: monitoring-error\ndata: {"status":"unknown"}\n\n'
            await asyncio.sleep(interval)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
