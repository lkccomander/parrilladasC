from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from parrilladas.core.config import ApiSettings
from parrilladas.modules.accounts.errors import InvalidCredentials
from parrilladas.modules.accounts.schemas import SessionContext, SessionCreated

ACCESS_LIFETIME = timedelta(minutes=15)


def issue_credentials(created: SessionCreated, settings: ApiSettings) -> SessionCreated:
    now = datetime.now(UTC)
    context = created.context
    expires = min(context.expires_at, now + ACCESS_LIFETIME)
    token = jwt.encode(
        {
            "sub": str(context.account.id) if context.account else str(context.id),
            "sid": str(context.id),
            "jti": str(uuid4()),
            "kind": "access" if context.account else "anonymous",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "nbf": now,
            "exp": expires,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    return SessionCreated(
        token=token,
        context=context,
        access_expires_at=expires,
        refresh_token=created.token if context.account else None,
    )


def verify_access(token: str, settings: ApiSettings) -> dict:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "nbf", "sub", "sid", "jti", "kind"]},
        )
        UUID(claims["sid"])
        UUID(claims["sub"])
        UUID(claims["jti"])
        if claims["kind"] not in {"access", "anonymous"}:
            raise ValueError("Invalid token kind")
        return claims
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise InvalidCredentials("Sesión inválida o vencida.") from None


def matches_context(claims: dict, context: SessionContext) -> bool:
    if context.account:
        return claims["kind"] == "access" and claims["sub"] == str(context.account.id)
    return claims["kind"] == "anonymous" and claims["sub"] == str(context.id)
