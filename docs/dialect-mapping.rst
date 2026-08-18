Dialect mapping
===============

When ``db2sql`` reads a source database and emits SQL for a different target
dialect, two things need to be translated:

1. **Column types** — the source column type is rewritten to the closest
   equivalent in the target dialect.
2. **DEFAULT expressions** — built-in functions (``GETDATE()``, ``NEWID()``,
   ``now()``, ``SYSDATE``, …) are rewritten to the target-dialect equivalent
   so the generated ``CREATE TABLE`` is replayable as-is.

Both are driven by static tables in the emitters; the tables below are the
authoritative reference (extracted from
``db2sql/infrastructure/emit/{postgres,mssql}/emitter.py``).


Target: PostgreSQL
------------------

Used when ``--target postgres`` (the default) is selected.

Type mapping
~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Source type (lowercase)
     - Postgres type
     - Notes
   * - ``bit``, ``boolean``
     - ``boolean``
     - MSSQL ``bit`` becomes PG ``boolean``; literal ``0``/``1`` defaults are
       rewritten to ``FALSE``/``TRUE``.
   * - ``tinyint``, ``smallint``
     - ``smallint``
     -
   * - ``int``, ``integer``, ``mediumint``
     - ``integer``
     - Becomes ``serial`` when the column is an identity column.
   * - ``bigint``
     - ``bigint``
     - Becomes ``bigserial`` when the column is an identity column.
   * - ``real``, ``binary_float``
     - ``real``
     -
   * - ``float``, ``double``, ``binary_double``
     - ``double precision``
     -
   * - ``numeric``, ``decimal``, ``number``
     - ``numeric``
     - Precision/scale preserved when reported by the source.  A column
       declared with an explicit scale of ``0`` (the ``NUMBER(n)`` pattern)
       is promoted to the narrowest integer type that holds it —
       ``smallint`` up to 4 digits, ``integer`` up to 9, ``bigint`` up to 18
       — so identity columns can become ``serial``/``bigserial``.  Above 18
       digits no integer type is wide enough, and the column stays
       ``numeric(p,0)``.
   * - ``money``
     - ``numeric(19,4)``
     -
   * - ``smallmoney``
     - ``numeric(10,4)``
     -
   * - ``char``, ``nchar``
     - ``char``
     - Char length preserved.
   * - ``varchar``, ``varchar2``, ``nvarchar``, ``nvarchar2``
     - ``varchar``
     - Char length preserved.
   * - ``text``, ``ntext``, ``clob``, ``nclob``, ``long``, ``longtext``, ``mediumtext``
     - ``text``
     -
   * - ``binary``, ``varbinary``, ``blob``, ``bfile``, ``raw``, ``long raw``, ``image``
     - ``bytea``
     -
   * - ``date``
     - ``date``
     -
   * - ``time``
     - ``time``
     -
   * - ``datetime``, ``datetime2``, ``smalldatetime``, ``timestamp``
     - ``timestamp``
     -
   * - ``timestamp with time zone``, ``timestamp with local time zone``, ``datetimeoffset``
     - ``timestamptz``
     -
   * - ``uniqueidentifier``
     - ``uuid``
     -
   * - ``rowid``, ``urowid``
     - ``text``
     - Oracle pseudocolumns; rendered as opaque text.
   * - ``json``, ``jsonb``
     - ``jsonb``
     -
   * - ``xml``, ``xmltype``
     - ``xml``
     -

DEFAULT expression mapping
~~~~~~~~~~~~~~~~~~~~~~~~~~

MSSQL wraps every default in extra parentheses (``((0))``, ``(getdate())``);
those are stripped before matching. ``N'…'`` unicode-prefixed strings become
plain ``'…'`` (Postgres strings are already Unicode).

.. list-table::
   :header-rows: 1
   :widths: 40 40 20

   * - Source expression
     - Postgres equivalent
     - Origin
   * - ``GETDATE()``
     - ``now()``
     - MSSQL
   * - ``SYSDATETIME()``
     - ``LOCALTIMESTAMP``
     - MSSQL
   * - ``GETUTCDATE()``, ``SYSUTCDATETIME()``
     - ``(now() AT TIME ZONE 'utc')``
     - MSSQL
   * - ``SYSDATETIMEOFFSET()``
     - ``now()``
     - MSSQL
   * - ``SYSDATE``, ``SYSTIMESTAMP``
     - ``now()``
     - Oracle (bare keywords)
   * - ``NEWID()``, ``NEWSEQUENTIALID()``
     - ``gen_random_uuid()``
     - MSSQL
   * - ``SYS_GUID()``
     - ``gen_random_uuid()``
     - Oracle
   * - ``UUID()``
     - ``gen_random_uuid()``
     - MySQL
   * - ``SUSER_SNAME()``, ``SYSTEM_USER``, ``USER_NAME()``, ``USER``
     - ``CURRENT_USER``
     - MSSQL / Oracle
   * - ``DB_NAME()``
     - ``current_database()``
     - MSSQL
   * - ``0`` / ``1`` (on a ``boolean`` column)
     - ``FALSE`` / ``TRUE``
     - any
   * - ``b'0'`` / ``b'1'`` (on a ``boolean`` column)
     - ``FALSE`` / ``TRUE``
     - MySQL

Anything not in the table is passed through unchanged.

.. note::

   MSSQL's ``INFORMATION_SCHEMA.COLUMNS`` reports ``CURRENT_TIMESTAMP`` and
   ``GETDATE()`` defaults identically as ``(getdate())`` — they are
   indistinguishable at the metadata level. Both translate to ``now()`` in
   Postgres, which is semantically equivalent.


Target: Microsoft SQL Server
----------------------------

Used when ``--target mssql`` is selected.

Type mapping
~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Source type (lowercase)
     - MSSQL type
     - Notes
   * - ``bit``, ``boolean``
     - ``bit``
     - PG ``boolean`` literals (``TRUE``/``FALSE``) become ``1``/``0``.
   * - ``tinyint``
     - ``tinyint``
     -
   * - ``smallint``
     - ``smallint``
     -
   * - ``int``, ``integer``, ``mediumint``
     - ``int``
     -
   * - ``bigint``
     - ``bigint``
     -
   * - ``real``, ``binary_float``
     - ``real``
     -
   * - ``float``, ``double``, ``double precision``, ``binary_double``
     - ``float``
     -
   * - ``numeric``, ``decimal``, ``number``
     - ``numeric``
     -
   * - ``money``
     - ``money``
     -
   * - ``smallmoney``
     - ``smallmoney``
     -
   * - ``char``, ``nchar``
     - ``nchar``
     - Unified to the Unicode variant; preserves length.
   * - ``varchar``, ``varchar2``, ``nvarchar``, ``nvarchar2``
     - ``nvarchar``
     - Same; length preserved.
   * - ``text``, ``ntext``, ``clob``, ``nclob``, ``long``, ``longtext``, ``mediumtext``
     - ``nvarchar(max)``
     -
   * - ``binary``, ``varbinary``
     - ``varbinary``
     -
   * - ``blob``, ``bfile``, ``raw``, ``long raw``, ``image``, ``bytea``
     - ``varbinary(max)``
     -
   * - ``date``
     - ``date``
     -
   * - ``time``
     - ``time``
     -
   * - ``datetime``, ``datetime2``, ``smalldatetime``, ``timestamp``
     - ``datetime2``
     - MSSQL's ``timestamp`` is a row-version; we never emit it for data.
   * - ``timestamp with time zone``, ``timestamp with local time zone``,
       ``datetimeoffset``, ``timestamptz``
     - ``datetimeoffset``
     -
   * - ``uniqueidentifier``, ``uuid``
     - ``uniqueidentifier``
     -
   * - ``rowid``, ``urowid``, ``json``, ``jsonb``
     - ``nvarchar(max)``
     - MSSQL has no native JSON type.
   * - ``xml``, ``xmltype``
     - ``xml``
     -

DEFAULT expression mapping
~~~~~~~~~~~~~~~~~~~~~~~~~~

PG ``literal::type`` casts (``'foo'::text``, ``0::integer``) are unwrapped to
the literal. ANSI-compatible keywords (``CURRENT_USER``, ``SESSION_USER``,
``SYSTEM_USER``, ``CURRENT_TIMESTAMP``) are left untouched.

.. list-table::
   :header-rows: 1
   :widths: 40 40 20

   * - Source expression
     - MSSQL equivalent
     - Origin
   * - ``now()``, ``NOW()``
     - ``SYSDATETIME()``
     - PG / MySQL
   * - ``LOCALTIMESTAMP``
     - ``SYSDATETIME()``
     - PG (bare keyword)
   * - ``transaction_timestamp()``, ``statement_timestamp()``, ``clock_timestamp()``
     - ``SYSDATETIME()``
     - PG
   * - ``CURRENT_DATE``
     - ``CAST(SYSDATETIME() AS DATE)``
     - PG (bare keyword)
   * - ``CURRENT_TIME``
     - ``CAST(SYSDATETIME() AS TIME)``
     - PG (bare keyword)
   * - ``UTC_TIMESTAMP()``
     - ``SYSUTCDATETIME()``
     - MySQL
   * - ``SYSDATE``, ``SYSTIMESTAMP``
     - ``GETDATE()`` / ``SYSDATETIME()``
     - Oracle (bare keywords)
   * - ``gen_random_uuid()``, ``uuid_generate_v4()``
     - ``NEWID()``
     - PG
   * - ``SYS_GUID()``
     - ``NEWID()``
     - Oracle
   * - ``UUID()``
     - ``NEWID()``
     - MySQL
   * - ``current_database()``, ``current_catalog``
     - ``DB_NAME()``
     - PG
   * - ``current_schema``
     - ``SCHEMA_NAME()``
     - PG
   * - ``TRUE`` / ``FALSE`` (on a ``bit`` column)
     - ``1`` / ``0``
     - PG / any
   * - ``b'0'`` / ``b'1'`` (on a ``bit`` column)
     - ``0`` / ``1``
     - MySQL
   * - ``'foo'::text``, ``0::integer``
     - ``'foo'``, ``0``
     - PG cast stripped

Anything not in the table is passed through unchanged.


Overriding the mapping
----------------------

The type and default-value maps are static class attributes. To override a
mapping for a specific column, the recommended approach is to write a small
emitter subclass and register it as a plugin — see :doc:`plugins`.
