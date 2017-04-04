"""Module exceptions."""


class Error(Exception):
    """Basic error for the module."""
    pass


class InvalidPortNumberError(Error):
    """Raised when failing port number validation."""
    pass