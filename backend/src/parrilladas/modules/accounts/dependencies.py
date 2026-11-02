import secrets
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from parrilladas.db.session import get_session
from parrilladas.modules.accounts.contracts import Role
from parrilladas.modules.accounts.jwt_tokens import matches_context, verify_access
from parrilladas.modules.accounts.schemas import SessionContext
from parrilladas.modules.accounts.service import AccountService

bearer = HTTPBearer(auto_error=False)


def account_service(session: Annotated[Session, Depends(get_session)]) -> AccountService:
    return AccountService(session)


Service = Annotated[AccountService, Depends(account_service)]


def session_context(
    request: Request,
    service: Service,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SessionContext:
    if credentials is None:
        raise HTTPException(401, "Bearer JWT requerido.", headers={"WWW-Authenticate": "Bearer"})
    claims = verify_access(credentials.credentials, request.app.state.settings)
    context = service.context_by_id(UUID(claims["sid"]))
    if context is None or not matches_context(claims, context):
        raise HTTPException(
            401, "Sesión inválida o vencida.", headers={"WWW-Authenticate": "Bearer"}
        )
    return context


Context = Annotated[SessionContext, Depends(session_context)]


def require_account(context: Context) -> SessionContext:
    if context.account is None:
        raise HTTPException(401, "Ingrese nuevamente.", headers={"WWW-Authenticate": "Bearer"})
    return context


Authenticated = Annotated[SessionContext, Depends(require_account)]


def require_admin(context: Authenticated) -> SessionContext:
    if context.account.role != Role.ADMIN:
        raise HTTPException(403, "Se requiere una cuenta Admin.")
    return context


Admin = Annotated[SessionContext, Depends(require_admin)]


def check_csrf(request: Request, context: Context) -> None:
    supplied = request.headers.get("X-CSRF-Token", "")
    if not secrets.compare_digest(supplied.encode(), context.csrf_token.encode()):
        raise HTTPException(403, "Token CSRF inválido.")


Csrf = Annotated[None, Depends(check_csrf)]
