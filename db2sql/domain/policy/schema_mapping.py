"""Schema-renaming policy: source schema name to target schema name."""

from __future__ import annotations

from typing import Mapping

WILDCARD = "*"


def resolve_schema_name(mapping: Mapping[str, str], schema_name: str) -> str:
    """Return the target name for ``schema_name`` under ``mapping``.

    An exact entry always wins. The ``*`` entry, if present, catches every
    schema that has no exact entry, which is how ``--target-schema`` collapses
    a multi-schema source into a single target schema. Without either, the
    source name is kept.
    """
    exact = mapping.get(schema_name)
    if exact is not None:
        return exact
    return mapping.get(WILDCARD, schema_name)
