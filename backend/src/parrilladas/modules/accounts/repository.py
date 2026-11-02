from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from parrilladas.modules.accounts.models import Account, AuthSession, LoginAttempt


class AccountRepository:
    def __init__(self, session: Session):
        self.session = session

    def lock_accounts(self) -> None:
        # Serialize administrative changes, bootstrap and login credential checks.
        self.session.execute(text("SELECT pg_advisory_xact_lock(734221, 1)"))

    def lock_login(self, key: str) -> None:
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int(key[:15], 16)},
        )

    def by_email(self, email: str) -> Account | None:
        return self.session.scalar(select(Account).where(Account.email == email))

    def by_id(self, account_id: UUID) -> Account | None:
        return self.session.get(Account, account_id)

    def accounts_exist(self) -> bool:
        return bool(self.session.scalar(select(func.count()).select_from(Account)))

    def list_accounts(self) -> list[Account]:
        return list(
            self.session.scalars(select(Account).order_by(Account.display_name, Account.id))
        )

    def session_by_token(self, digest: str, now: datetime) -> AuthSession | None:
        return self.session.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == digest, AuthSession.expires_at > now
            )
        )

    def session_by_id(self, session_id: UUID, now: datetime) -> AuthSession | None:
        return self.session.scalar(
            select(AuthSession).where(AuthSession.id == session_id, AuthSession.expires_at > now)
        )

    def revoke_session(self, session_id: UUID) -> None:
        self.session.execute(delete(AuthSession).where(AuthSession.id == session_id))

    def revoke_account_sessions(self, account_id: UUID) -> None:
        self.session.execute(delete(AuthSession).where(AuthSession.account_id == account_id))

    def login_attempt(self, key: str) -> LoginAttempt | None:
        return self.session.get(LoginAttempt, key)

    def prune(self, now: datetime, window_cutoff: datetime) -> None:
        self.session.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
        self.session.execute(
            delete(LoginAttempt).where(LoginAttempt.window_started < window_cutoff)
        )

    def add(self, record: Account | AuthSession | LoginAttempt) -> None:
        self.session.add(record)
        self.session.flush()
