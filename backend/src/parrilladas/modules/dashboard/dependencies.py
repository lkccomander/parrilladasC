import secrets
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import Depends, HTTPException, Request

from parrilladas.modules.accounts.contracts import Role
from parrilladas.modules.accounts.schemas import SessionContext
from parrilladas.modules.dashboard.client import AdminApiClient


def api_client(request: Request) -> AdminApiClient:
    return AdminApiClient(request)


Service = Annotated[AdminApiClient, Depends(api_client)]


def session_context(request: Request, service: Service) -> SessionContext | None:
    context = service.session_context()
    request.state.auth_context = context
    return context


Context = Annotated[SessionContext | None, Depends(session_context)]


def require_account(context: Context) -> SessionContext:
    if context is None or context.account is None:
        raise HTTPException(303, headers={"Location": "/login"})
    return context


Authenticated = Annotated[SessionContext, Depends(require_account)]


def require_admin(context: Authenticated) -> SessionContext:
    if context.account.role != Role.ADMIN:
        raise HTTPException(403, "Se requiere una cuenta Admin.")
    return context


Admin = Annotated[SessionContext, Depends(require_admin)]


async def read_form(request: Request) -> dict[str, str]:
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Formato de formulario no permitido.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 16384:
            raise HTTPException(413, "Formulario demasiado grande.")
        body.extend(chunk)
    try:
        values = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=12)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Formulario inválido.") from None
    if any(len(value) != 1 for value in values.values()):
        raise HTTPException(400, "Campos duplicados.")
    return {key: value[0] for key, value in values.items()}


def checked_form(
    request: Request, context: Context, form: Annotated[dict[str, str], Depends(read_form)]
) -> dict[str, str]:
    token = request.headers.get("X-CSRF-Token") or form.get("csrf_token", "")
    if (
        context is None
        or request.headers.get("sec-fetch-site") == "cross-site"
        or not secrets.compare_digest(token.encode(), context.csrf_token.encode())
    ):
        raise HTTPException(403, "Sesión inválida. Recargue la página e intente otra vez.")
    return form


CheckedForm = Annotated[dict[str, str], Depends(checked_form)]
