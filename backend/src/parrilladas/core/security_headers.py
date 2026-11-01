from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "same-origin"
                headers["Cache-Control"] = "no-store"
                # FastAPI's development-only Swagger page loads its own scripts.
                if scope["path"] != "/docs":
                    headers["Content-Security-Policy"] = (
                        "default-src 'none'; style-src 'self'; img-src 'self'; "
                        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
                    )
            await send(message)

        await self.app(scope, receive, secure_send)
