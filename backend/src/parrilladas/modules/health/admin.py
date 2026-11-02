import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health")


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=None)
def ready(request: Request) -> dict[str, str] | JSONResponse:
    try:
        response = request.app.state.api_http.get("/health/ready")
        if response.status_code == 200:
            return {"status": "ok"}
    except httpx.HTTPError:
        pass
    return JSONResponse(status_code=503, content={"status": "unavailable"})
