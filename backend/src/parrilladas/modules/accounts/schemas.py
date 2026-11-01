from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from parrilladas.modules.accounts.models import Role


class AccountDetails(BaseModel):
    email: EmailStr = Field(max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    role: Role

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError("Invalid name")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower() if isinstance(value, str) else value


class AccountCreate(AccountDetails):
    password: SecretStr = Field(min_length=15, max_length=128)


class AccountUpdate(AccountDetails):
    is_active: bool
    password: SecretStr | None = Field(default=None, min_length=15, max_length=128)


class PasswordReset(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=15, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower() if isinstance(value, str) else value


class AccountView(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    email: str
    display_name: str
    role: Role
    is_active: bool


class SessionContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    csrf_token: str
    expires_at: datetime
    account: AccountView | None


class SessionCreated(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: str
    context: SessionContext
