class SQLValidationError(ValueError):
    """Raised when SQL is malformed or not read-only."""

class SQLExecutionError(RuntimeError):
    pass