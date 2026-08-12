"""Domain exceptions for filesystem access boundaries."""

from __future__ import annotations


class SecurityError(Exception):
    """Base class for filesystem boundary violations."""


class PathTraversalError(SecurityError):
    """Raised when a requested path escapes its allowed root."""


class PathNotFoundError(SecurityError):
    """Raised when a validated path does not exist on disk."""
