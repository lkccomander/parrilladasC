from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    SALES = "sales"
    DEV = "dev"


class AccountPermissions:
    """Shared permission semantics for ORM accounts and public account contracts."""

    @property
    def is_admin(self) -> bool:
        return bool({Role.ADMIN, Role.DEV}.intersection(self.roles or [self.role]))

    @property
    def is_dev(self) -> bool:
        return Role.DEV in (self.roles or [self.role])
