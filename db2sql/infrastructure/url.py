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
from urllib.parse import quote, urlencode

from db2sql.infrastructure.config import ServerConfig

# Matches the ``user:password@`` prefix of a URL authority. The password group
# requires at least one character so that a credential-less URL — or one with
# an empty password — is left untouched instead of gaining a fake secret.
_USERINFO_RE = re.compile(r"(?<=://)(?P<user>[^/?#@]*):(?P<password>[^/?#@]+)@")


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

    :param server: connection parameters.
    :param scheme: SQLAlchemy dialect+driver, e.g. ``postgresql+psycopg2``.
    :param database: URL path; defaults to ``server.dbname``. Pass ``""`` for
        dialects that carry the database in the query string instead.
    :param query: extra query-string parameters.
    :param credentials: set to ``False`` for file-based dialects (SQLite),
        which take neither user info nor host.
    """
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


def redact_url(url: str) -> str:
    """Replace the password of ``url`` with ``***`` so it is safe to log."""
    return _USERINFO_RE.sub(lambda match: f"{match.group('user')}:***@", url, count=1)
