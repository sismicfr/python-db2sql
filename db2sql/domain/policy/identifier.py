"""Identifier-naming policy: snake_case conversion."""

from __future__ import annotations

import re

# Split before a capitalized word so acronyms stay glued: "HTTPServer" → "HTTP_Server".
_CAMEL_BOUNDARY_RE = re.compile(r"(.)([A-Z][a-z]+)")
# Split between lowercase/digit and uppercase to catch trailing acronyms: "userID" → "user_ID".
_LOWER_UPPER_RE = re.compile(r"([a-z0-9])([A-Z])")


def to_snake_case(name: str) -> str:
    """Convert CamelCase / PascalCase to snake_case.

    Keeps acronym runs intact (``HTTPServer`` → ``http_server``,
    ``UserID`` → ``user_id``) and leaves all-caps identifiers as a single
    word (``MYTABLE`` → ``mytable``). Idempotent on snake_case input.
    """
    name = _CAMEL_BOUNDARY_RE.sub(r"\1_\2", name)
    name = _LOWER_UPPER_RE.sub(r"\1_\2", name)
    return name.lower()


def normalize_identifier(name: str, preserve_case: bool) -> str:
    """Normalize an identifier according to the case policy."""
    if preserve_case:
        return name
    return to_snake_case(name)
