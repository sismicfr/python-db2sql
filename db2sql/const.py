"""db2sql constants."""

__all__ = [
    "ENV_DB2SQL_DRIVER",
    "ENV_DB2SQL_TARGET",
    "ENV_DB2SQL_USER",
    "ENV_DB2SQL_PASSWORD",
    "ENV_DB2SQL_HOST",
    "ENV_DB2SQL_PORT",
    "ENV_DB2SQL_DBNAME",
    "ENV_DB2SQL_TARGET_HOST",
    "ENV_DB2SQL_TARGET_PORT",
    "ENV_DB2SQL_TARGET_USER",
    "ENV_DB2SQL_TARGET_PASSWORD",
    "ENV_DB2SQL_TARGET_DBNAME",
    "ENV_NO_COLOR",
    "ENV_CLICOLOR_FORCE",
    "ENV_DB2SQL_COLOR_DARK",
    "ENV_DB2SQL_CONFIG",
]

ENV_DB2SQL_DRIVER = "DB2SQL_DRIVER"
"""Source database driver name (e.g. mssql, sqlite, mysql, postgres)."""

ENV_DB2SQL_TARGET = "DB2SQL_TARGET"
"""Target SQL dialect to emit (e.g. postgres, mssql)."""

ENV_DB2SQL_USER = "DB2SQL_USER"
"""Source database user name."""

ENV_DB2SQL_PASSWORD = "DB2SQL_PASSWORD"
"""Source database password."""

ENV_DB2SQL_HOST = "DB2SQL_HOST"
"""Source database host."""

ENV_DB2SQL_PORT = "DB2SQL_PORT"
"""Source database port."""

ENV_DB2SQL_DBNAME = "DB2SQL_DBNAME"
"""Source database name."""

ENV_DB2SQL_TARGET_HOST = "DB2SQL_TARGET_HOST"
"""Target database host (live migration)."""

ENV_DB2SQL_TARGET_PORT = "DB2SQL_TARGET_PORT"
"""Target database port (live migration)."""

ENV_DB2SQL_TARGET_USER = "DB2SQL_TARGET_USER"
"""Target database user (live migration)."""

ENV_DB2SQL_TARGET_PASSWORD = "DB2SQL_TARGET_PASSWORD"
"""Target database password (live migration)."""

ENV_DB2SQL_TARGET_DBNAME = "DB2SQL_TARGET_DBNAME"
"""Target database name (live migration)."""

ENV_NO_COLOR = "NO_COLOR"
"""Disable ANSI colors."""

ENV_CLICOLOR_FORCE = "CLICOLOR_FORCE"
"""Force ANSI colors when defined and value is not 0."""

ENV_DB2SQL_COLOR_DARK = "DB2SQL_COLOR_DARK"
"""Use the dark ANSI color scheme when set to a non-zero value."""

ENV_DB2SQL_CONFIG = "DB2SQL_CONFIG"
"""Path to a YAML/JSON configuration file."""
