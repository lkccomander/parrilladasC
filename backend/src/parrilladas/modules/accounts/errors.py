class AccountError(Exception):
    """Expected use-case failure; messages never include submitted credentials."""


class AccessDenied(AccountError):
    pass


class AccountNotFound(AccountError):
    pass


class AccountConflict(AccountError):
    pass


class InvalidCredentials(AccountError):
    pass


class LoginThrottled(AccountError):
    pass
