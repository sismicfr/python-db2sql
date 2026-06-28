"""Identifier-naming policy: snake_case conversion."""

from __future__ import annotations

import re

_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case (idempotent on already-snake_case input).

    Pure-uppercase names (e.g. ``CLIENTS``) are lowered without inserting
    underscores, so ``CLIENTS`` becomes ``clients`` rather than ``c_l_i_e_n_t_s``.
    Mixed-case names like ``ClientName`` become ``client_name``.
    """
    if name.isupper() or name.islower():
        return name.lower()
    return _CAMEL_RE.sub("_", name).lower()


def normalize_identifier(name: str, preserve_case: bool) -> str:
    """Normalize an identifier according to the case policy."""
    if preserve_case:
        return name
    return to_snake_case(name)
