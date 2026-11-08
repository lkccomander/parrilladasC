from pathlib import Path
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from parrilladas import __release_name__, __version__
from parrilladas.modules.accounts.errors import (
    AccessDenied,
    AccountConflict,
    AccountNotFound,
    InvalidCredentials,
    LoginThrottled,
)
from parrilladas.modules.accounts.schemas import AccountCreate, AccountUpdate
from parrilladas.modules.dashboard.cookies import clear_cookies, set_session_cookie
from parrilladas.modules.dashboard.dependencies import (
    Admin,
    Authenticated,
    CheckedForm,
    Context,
    Service,
)
from parrilladas.modules.integrations.schemas import WhatsAppIntegrationStatus

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))


def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    context.setdefault("software_release", __release_name__)
    context.setdefault("software_version", __version__)
    return templates.TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
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


@router.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request, lang: Literal["es", "en"] = "es") -> HTMLResponse:
    response = page(
        request,
        "privacy_en.html" if lang == "en" else "privacy.html",
        page_language=lang,
        legal_path="/privacy",
    )
    response.headers["Content-Language"] = lang
    return response


@router.get("/terms-of-service", response_class=HTMLResponse)
def terms_of_service(request: Request, lang: Literal["es", "en"] = "es") -> HTMLResponse:
    response = page(
        request,
        "terms_en.html" if lang == "en" else "terms.html",
        page_language=lang,
        legal_path="/terms-of-service",
    )
    response.headers["Content-Language"] = lang
    return response


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
        created = service.login(email, password)
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
    service.logout()
    response = RedirectResponse("/login", status_code=303)
    clear_cookies(request, response)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, context: Authenticated) -> HTMLResponse:
    return page(request, "dashboard.html", context=context)


def integration_page(request: Request, context, report: WhatsAppIntegrationStatus) -> HTMLResponse:
    checked_at = (
        report.check.checked_at.astimezone(ZoneInfo("America/Costa_Rica")) if report.check else None
    )
    return page(request, "integrations.html", context=context, report=report, checked_at=checked_at)


@router.get("/dashboard/integrations", response_class=HTMLResponse)
def integrations(request: Request, service: Service, context: Admin) -> HTMLResponse:
    try:
        report = service.whatsapp_status()
    except AccessDenied as error:
        raise HTTPException(403, str(error)) from None
    return integration_page(request, context, report)


@router.post("/dashboard/integrations/whatsapp/check", response_class=HTMLResponse)
def check_whatsapp(
    request: Request, service: Service, context: Admin, form: CheckedForm
) -> HTMLResponse:
    try:
        report = service.check_whatsapp()
    except AccessDenied as error:
        raise HTTPException(403, str(error)) from None
    return integration_page(request, context, report)


@router.get("/dashboard/accounts", response_class=HTMLResponse)
def accounts(request: Request, service: Service, context: Admin) -> HTMLResponse:
    try:
        accounts = service.list_accounts()
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
        service.create_account(data)
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
        account = service.get_account(account_id)
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
        account = service.get_account(account_id)
        data = account_form_data(form, creating=False)
        service.update_account(account_id, data)
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
