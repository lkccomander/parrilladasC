from datetime import UTC, datetime

from fastapi import Request, Response

from parrilladas.modules.accounts.schemas import SessionCreated


def cookie_name(request: Request) -> str:
    return "__Host-parrilladas" if request.app.state.secure_cookies else "parrilladas_session"


def refresh_cookie_name(request: Request) -> str:
    return (
        "__Host-parrilladas-refresh" if request.app.state.secure_cookies else "parrilladas_refresh"
    )


def set_session_cookie(request: Request, response: Response, created: SessionCreated) -> None:
    now = datetime.now(UTC)
    expires = created.access_expires_at or created.context.expires_at
    options = {
        "httponly": True,
        "secure": request.app.state.secure_cookies,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        cookie_name(request),
        created.token,
        max_age=max(0, int((expires - now).total_seconds())),
        **options,
    )
    if created.refresh_token:
        response.set_cookie(
            refresh_cookie_name(request),
            created.refresh_token,
            max_age=max(0, int((created.context.expires_at - now).total_seconds())),
            **options,
        )
    else:
        response.delete_cookie(refresh_cookie_name(request), **options)


def clear_cookies(request: Request, response: Response) -> None:
    request.state.pending_credentials = None
    for name in [cookie_name(request), refresh_cookie_name(request)]:
        response.delete_cookie(
            name, path="/", secure=request.app.state.secure_cookies, httponly=True, samesite="lax"
        )
