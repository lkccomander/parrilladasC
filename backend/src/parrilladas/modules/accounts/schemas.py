from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from parrilladas.modules.accounts.contracts import AccountPermissions, Role


class AccountRoles(BaseModel):
    role: Role | None = None
    roles: list[Role] | None = Field(default=None, min_length=1, max_length=3)

    @model_validator(mode="after")
    def normalize_roles(self):
        if self.roles is None:
            if self.role is None:
                raise ValueError("Seleccione al menos un rol")
            object.__setattr__(self, "roles", [self.role])
        elif self.role is not None and self.role not in self.roles:
            raise ValueError("El rol principal debe pertenecer a los roles asignados")
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("Roles duplicados")
        object.__setattr__(self, "roles", sorted(self.roles))
        object.__setattr__(
            self, "role", next(r for r in (Role.ADMIN, Role.DEV, Role.SALES) if r in self.roles)
        )
        return self


class AccountDetails(AccountRoles):
    email: EmailStr = Field(max_length=254)
    display_name: str = Field(min_length=1, max_length=120)

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


class AccountView(AccountPermissions, AccountRoles):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    email: str
    display_name: str
    is_active: bool


class SessionContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    csrf_token: str
    expires_at: datetime
    account: AccountView | None


class SessionCreated(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: str = Field(repr=False)
    context: SessionContext
    refresh_token: str | None = Field(default=None, repr=False)
    access_expires_at: datetime | None = None
