from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, SecretStr

from parrilladas.modules.accounts.dependencies import Admin, Authenticated, Context, Csrf, Service
from parrilladas.modules.accounts.jwt_tokens import issue_credentials
from parrilladas.modules.accounts.schemas import (
    AccountCreate,
    AccountUpdate,
    AccountView,
    SessionContext,
    SessionCreated,
)

router = APIRouter(tags=["accounts"])


class LoginInput(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)


class RefreshInput(BaseModel):
    refresh_token: SecretStr = Field(min_length=43, max_length=43)


@router.post("/auth/sessions", response_model=SessionCreated, status_code=201)
def anonymous_session(request: Request, service: Service) -> SessionCreated:
    return issue_credentials(service.anonymous_session(), request.app.state.settings)


@router.post("/auth/login", response_model=SessionCreated)
def login(
    request: Request,
    data: LoginInput,
    service: Service,
    context: Context,
    csrf: Csrf,
) -> SessionCreated:
    created = service.login(data.email, data.password.get_secret_value(), context.id)
    return issue_credentials(created, request.app.state.settings)


@router.post("/auth/refresh", response_model=SessionCreated)
def refresh(request: Request, data: RefreshInput, service: Service) -> SessionCreated:
    created = service.rotate_refresh(data.refresh_token.get_secret_value())
    return issue_credentials(created, request.app.state.settings)


@router.get("/auth/me", response_model=SessionContext)
def me(context: Context) -> SessionContext:
    return context


@router.post("/auth/logout", status_code=204)
def logout(service: Service, context: Authenticated, csrf: Csrf) -> Response:
    service.logout(context.id)
    return Response(status_code=204)


@router.get("/accounts", response_model=list[AccountView])
def accounts(service: Service, context: Admin) -> list[AccountView]:
    return service.list_accounts(context.account.id)


@router.post("/accounts", response_model=AccountView, status_code=201)
def create_account(
    data: AccountCreate, service: Service, context: Admin, csrf: Csrf
) -> AccountView:
    return service.create_account(context.account.id, data)


@router.get("/accounts/{account_id}", response_model=AccountView)
def account(account_id: UUID, service: Service, context: Admin) -> AccountView:
    return service.get_account(context.account.id, account_id)


@router.patch("/accounts/{account_id}", response_model=AccountView)
def update_account(
    account_id: UUID,
    data: AccountUpdate,
    service: Service,
    context: Admin,
    csrf: Csrf,
) -> AccountView:
    return service.update_account(context.account.id, account_id, data)
