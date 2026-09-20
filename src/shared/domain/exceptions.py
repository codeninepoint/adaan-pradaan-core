class DomainError(Exception):
    """Base for domain-layer failures."""


class ConflictError(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass


class UnauthorizedError(DomainError):
    pass
