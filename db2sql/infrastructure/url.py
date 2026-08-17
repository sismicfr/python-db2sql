"""Build and redact the SQLAlchemy connection URLs used by readers and writers.

Every reader and writer talks to its database through a SQLAlchemy URL
assembled from a :class:`~db2sql.infrastructure.config.ServerConfig`. Keeping
that assembly in one place guarantees three things that used to be per-driver
details: credentials are percent-encoded, the shape of the URL is consistent,
and nothing ever logs a password.
"""

from __future__ import annotations

import re
from typing import Mapping, Optional
from urllib.parse import quote, unquote, urlencode

from db2sql.infrastructure.config import ConfigInvalidError, ServerConfig

# Matches the ``user:password@`` prefix of a URL authority. The password group
# requires at least one character so that a credential-less URL — or one with
# an empty password — is left untouched instead of gaining a fake secret.
_USERINFO_RE = re.compile(r"(?<=://)(?P<user>[^/?#@]*):(?P<password>[^/?#@]+)@")


def _dialect_of(scheme: str) -> str:
    """``postgresql+psycopg2`` -> ``postgresql``; the DBAPI part is free choice."""
    return scheme.split("+", 1)[0].lower()


def _check_dialect(dsn: str, expected_scheme: str) -> None:
    """Reject a DSN whose dialect contradicts the reader or writer using it.

    SQLAlchemy picks its dialect from the URL, not from ``--driver``, so a
    Postgres DSN handed to the MSSQL reader would connect successfully and
    then fail deep inside introspection with unrelated SQL errors.
    """
    dsn_scheme = dsn.split("://", 1)[0]
    if not dsn_scheme or "://" not in dsn:
        raise ConfigInvalidError(f"invalid DSN, expected a '<dialect>://' URL: {redact_url(dsn)}")

    expected = _dialect_of(expected_scheme)
    if _dialect_of(dsn_scheme) != expected:
        raise ConfigInvalidError(
            f"DSN dialect '{_dialect_of(dsn_scheme)}' does not match the selected "
            f"driver, which expects '{expected}'. Adjust the DSN or select the "
            f"matching driver."
        )


def _encode(value: Optional[str]) -> str:
    """Percent-encode a URL credential.

    ``quote`` rather than ``quote_plus``: SQLAlchemy unquotes the userinfo with
    :func:`urllib.parse.unquote`, which does not turn ``+`` back into a space.
    """
    return quote(value or "", safe="")


def build_url(
    server: ServerConfig,
    scheme: str,
    *,
    database: Optional[str] = None,
    query: Optional[Mapping[str, str]] = None,
    credentials: bool = True,
) -> str:
    """Assemble ``scheme://user:password@host:port/database?query``.

    :param server: connection parameters. When ``server.dsn`` is set it
        replaces the whole URL — every other field and argument is ignored —
        after its dialect has been checked against ``scheme``.
    :param scheme: SQLAlchemy dialect+driver, e.g. ``postgresql+psycopg2``.
    :param database: URL path; defaults to ``server.dbname``. Pass ``""`` for
        dialects that carry the database in the query string instead.
    :param query: extra query-string parameters.
    :param credentials: set to ``False`` for file-based dialects (SQLite),
        which take neither user info nor host.
    :raises ConfigInvalidError: if the DSN targets a different dialect than
        the caller.
    """
    if server.dsn:
        _check_dialect(server.dsn, scheme)
        return server.dsn

    authority = ""
    if credentials:
        authority = f"{_encode(server.username)}:{_encode(server.password)}@"
    authority += server.hostname or ""
    if server.port:
        authority += f":{server.port}"

    path = database if database is not None else (server.dbname or "")
    url = f"{scheme}://{authority}/{path}"
    if query:
        url += f"?{urlencode(query)}"
    return url


def database_from_url(url: str) -> Optional[str]:
    """Extract the database name from a URL, for dialects that need it as a label."""
    without_scheme = url.split("://", 1)[-1]
    _, separator, path = without_scheme.partition("/")
    if not separator:
        return None
    database = path.split("?", 1)[0].split("#", 1)[0]
    return unquote(database) or None


def redact_url(url: str) -> str:
    """Replace the password of ``url`` with ``***`` so it is safe to log."""
    return _USERINFO_RE.sub(lambda match: f"{match.group('user')}:***@", url, count=1)
