"""Topological ordering of tables based on foreign-key dependencies.

Used to emit ``DROP TABLE`` statements in an order that respects referential
integrity without falling back to ``CASCADE``. The order is computed from the
foreign keys carried on each :class:`~db2sql.domain.model.Table`.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from db2sql.domain.model import Database

TableKey = Tuple[str, str]


def topological_order(database: Database) -> List[TableKey]:
    """Return ``(schema, table)`` pairs ordered so that referenced tables come first.

    Self-referencing foreign keys are ignored (a table never blocks itself).
    Genuine cycles between distinct tables cannot be ordered cleanly; the
    remaining nodes are appended in source order so callers always receive
    every table exactly once.
    """
    nodes: List[TableKey] = []
    incoming: Dict[TableKey, Set[TableKey]] = {}
    outgoing: Dict[TableKey, Set[TableKey]] = {}

    for schema_name, schema in database.schemas.items():
        for table_name in schema.tables:
            key = (schema_name, table_name)
            nodes.append(key)
            incoming.setdefault(key, set())
            outgoing.setdefault(key, set())

    known = set(nodes)
    for schema_name, schema in database.schemas.items():
        for table_name, table in schema.tables.items():
            child = (schema_name, table_name)
            for fk in table.foreign_keys:
                parent = (fk.schema, fk.table)
                if parent == child or parent not in known:
                    continue
                if parent in incoming[child]:
                    continue
                incoming[child].add(parent)
                outgoing[parent].add(child)

    ordered: List[TableKey] = []
    ready = [node for node in nodes if not incoming[node]]
    placed: Set[TableKey] = set()
    while ready:
        node = ready.pop(0)
        ordered.append(node)
        placed.add(node)
        for child in list(outgoing[node]):
            outgoing[node].discard(child)
            incoming[child].discard(node)
            if not incoming[child] and child not in placed:
                ready.append(child)

    for node in nodes:
        if node not in placed:
            ordered.append(node)
    return ordered


def drop_order(database: Database) -> List[TableKey]:
    """Return tables in reverse-dependency order (children before parents).

    This is the order in which ``DROP TABLE IF EXISTS`` must be emitted so a
    dependent table is removed before the table it references.
    """
    return list(reversed(topological_order(database)))
