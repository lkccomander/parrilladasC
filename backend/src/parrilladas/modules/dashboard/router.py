from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from parrilladas.modules.accounts.dependencies import (
    Admin,
    Authenticated,
    CheckedForm,
    Context,
    Service,
    cookie_name,
)
from parrilladas.modules.accounts.errors import (
    AccessDenied,
    AccountConflict,
    AccountNotFound,
    InvalidCredentials,
    LoginThrottled,
)
from parrilladas.modules.accounts.schemas import AccountCreate, AccountUpdate, SessionCreated

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))


def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
    )


def set_session_cookie(request: Request, response: Response, created: SessionCreated) -> None:
    response.set_cookie(
        cookie_name(request),
        created.token,
        max_age=max(0, int((created.context.expires_at - datetime.now(UTC)).total_seconds())),
        httponly=True,
        secure=request.app.state.secure_cookies,
        samesite="lax",
        path="/",
    )


def account_form_data(form: dict[str, str], *, creating: bool):
    values = {
        "email": form.get("email", ""),
        "display_name": form.get("display_name", ""),
        "role": form.get("role", ""),
        "password": form.get("password") or None,
    }
    if creating:
        return AccountCreate.model_validate(values)
    return AccountUpdate.model_validate({**values, "is_active": form.get("is_active") == "on"})


def safe_values(form: dict[str, str]) -> dict[str, str | bool]:
    return {
        "email": form.get("email", ""),
        "display_name": form.get("display_name", ""),
        "role": form.get("role", "sales"),
        "is_active": form.get("is_active") == "on",
    }


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return page(request, "index.html")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, service: Service, context: Context) -> Response:
    if context and context.account:
        return RedirectResponse("/dashboard", status_code=303)
    created = service.anonymous_session() if context is None else None
    response = page(request, "login.html", context=created.context if created else context)
    if created:
        set_session_cookie(request, response, created)
    return response


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, service: Service, context: Context, form: CheckedForm) -> Response:
    email, password = form.get("email", ""), form.get("password", "")
    if len(email) > 254 or len(password) > 128 or not email or not password:
        return page(
            request, "login.html", 422, context=context, error="Revise correo y contraseña."
        )
    try:
        created = service.login(email, password, request.cookies.get(cookie_name(request), ""))
    except InvalidCredentials as error:
        return page(request, "login.html", 401, context=context, error=str(error))
    except LoginThrottled as error:
        response = page(request, "login.html", 429, context=context, error=str(error))
        response.headers["Retry-After"] = "900"
        return response
    response = RedirectResponse("/dashboard", status_code=303)
    set_session_cookie(request, response, created)
    return response


@router.post("/logout")
def logout(
    request: Request, service: Service, context: Authenticated, form: CheckedForm
) -> Response:
    service.logout(context.id)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(
        cookie_name(request),
        path="/",
        secure=request.app.state.secure_cookies,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, context: Authenticated) -> HTMLResponse:
    return page(request, "dashboard.html", context=context)


@router.get("/dashboard/accounts", response_class=HTMLResponse)
def accounts(request: Request, service: Service, context: Admin) -> HTMLResponse:
    try:
        accounts = service.list_accounts(context.account.id)
    except AccessDenied as error:
        raise HTTPException(403, str(error)) from None
    return page(
        request,
        "accounts.html",
        context=context,
        accounts=accounts,
    )


@router.get("/dashboard/accounts/new", response_class=HTMLResponse)
def new_account(request: Request, context: Admin) -> HTMLResponse:
    return page(
        request, "account_form.html", context=context, account=None, values={"role": "sales"}
    )


@router.post("/dashboard/accounts/new", response_class=HTMLResponse)
def create_account(
    request: Request,
    service: Service,
    context: Admin,
    form: CheckedForm,
) -> Response:
    try:
        data = account_form_data(form, creating=True)
        service.create_account(context.account.id, data)
    except (ValidationError, AccountConflict) as error:
        message = (
            "Revise el correo, nombre, rol y contraseña (15–128 caracteres)."
            if isinstance(error, ValidationError)
            else str(error)
        )
        return page(
            request,
            "account_form.html",
            422 if isinstance(error, ValidationError) else 409,
            context=context,
            account=None,
            values=safe_values(form),
            error=message,
        )
    except AccessDenied as error:
        raise HTTPException(403, str(error)) from None
    return RedirectResponse("/dashboard/accounts", status_code=303)


@router.get("/dashboard/accounts/{account_id}", response_class=HTMLResponse)
def edit_account(
    request: Request, account_id: UUID, service: Service, context: Admin
) -> HTMLResponse:
    try:
        account = service.get_account(context.account.id, account_id)
    except AccountNotFound as error:
        raise HTTPException(404, str(error)) from None
    except AccessDenied as error:
        raise HTTPException(403, str(error)) from None
    return page(
        request,
        "account_form.html",
        context=context,
        account=account,
        values=account.model_dump(),
    )


@router.post("/dashboard/accounts/{account_id}", response_class=HTMLResponse)
def update_account(
    request: Request,
    account_id: UUID,
    service: Service,
    context: Admin,
    form: CheckedForm,
) -> Response:
    try:
        account = service.get_account(context.account.id, account_id)
        data = account_form_data(form, creating=False)
        service.update_account(context.account.id, account_id, data)
    except (ValidationError, AccountConflict) as error:
        message = (
            "Revise el correo, nombre, rol y contraseña (15–128 caracteres)."
            if isinstance(error, ValidationError)
            else str(error)
        )
        return page(
            request,
            "account_form.html",
            422 if isinstance(error, ValidationError) else 409,
            context=context,
            account=account,
            values=safe_values(form),
            error=message,
        )
    except AccountNotFound as error:
        raise HTTPException(404, str(error)) from None
    except AccessDenied as error:
        raise HTTPException(403, str(error)) from None
    return RedirectResponse(
        "/login" if account_id == context.account.id else "/dashboard/accounts",
        status_code=303,
    )
