Configuration
=============

``db2sql`` reads its settings from a YAML or JSON configuration file.  CLI
flags always win over the config file, which itself wins over environment
variables.

.. tip::

   To bootstrap a config file interactively, run ``db2sql init``.  The
   wizard asks the relevant questions for the driver and target you pick
   and writes a minimal YAML (or JSON) file — see :ref:`cli-init`.

Config file lookup order
------------------------

When :option:`--config-file <-C>` is not set and ``DB2SQL_CONFIG`` is not
defined, ``db2sql`` searches for a config file in this order:

1. ``./db2sql.yml`` — current working directory
2. ``/etc/db2sql.yml`` — system-wide
3. ``~/db2sql.yml`` — user home directory

If none is found, all settings fall back to their defaults.

File format
-----------

Both YAML and JSON are supported.  The file extension must be ``.yml``,
``.yaml``, or ``.json``.

Complete example
----------------

.. code-block:: yaml

   # db2sql.yml
   driver: mssql
   target: postgres

   server:
     hostname: sqlserver.example.com
     port: 1433
     username: sa
     password: secret
     dbname: mydb
     options:
       charset: UTF-8

   dump:
     preserve_case: false
     limit_records: -1
     default_data_format: copy
     on_existing: fail

     include_schemas: []
     exclude_schemas: []
     include_tables: []
     exclude_tables:
       - audit_log
       - temp_data

     mapping_schemas:
       dbo: public
       legacy: archive

     tables:
       orders:
         data_format: insert
         limit_records: 1000
       audit.events:
         data_format: insert
         where: "created_at > '2023-01-01'"

   output_file: dump.sql
   split_size: 100M

Reference
---------

Top-level keys
~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Key
     - Default
     - Description
   * - ``driver``
     - ``mssql``
     - Source database driver.  See :option:`--driver`.
   * - ``target``
     - ``postgres``
     - Target SQL dialect to emit.  See :option:`--target`.
   * - ``server``
     - ``{}``
     - Source connection parameters (see `server`_).
   * - ``target_server``
     - ``{}``
     - Target connection parameters used by the ``migrate`` subcommand
       (see `target_server`_). Ignored in dump mode.
   * - ``dump``
     - ``{}``
     - Dump options (see `dump`_).
   * - ``migrate``
     - ``{}``
     - Live-migration options used by the ``migrate`` subcommand
       (see `migrate`_). Ignored in dump mode.
   * - ``output_file``
     - ``null``
     - Path to the output SQL file.  When ``null``, output goes to
       ``stdout``. Only relevant in dump mode.
   * - ``split_size``
     - ``null``
     - When set, split the dump into multiple files of at most this many
       bytes. Suffixes ``K``/``M``/``G`` (base 1024) are accepted on the
       CLI; in the config file the value must be a raw byte count. Requires
       ``output_file``. See :option:`--split-size`.

server
~~~~~~

Connection parameters for the source database.

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Key
     - Default
     - Description
   * - ``hostname``
     - ``null``
     - Server hostname or IP address.
   * - ``port``
     - ``null``
     - TCP port.
   * - ``username``
     - ``null``
     - Database user name.
   * - ``password``
     - ``null``
     - Database password.
   * - ``dbname``
     - ``null``
     - Database name (or SQLite file path).
   * - ``dsn``
     - ``null``
     - Full SQLAlchemy URL for the source, e.g.
       ``postgresql+psycopg2://user:pwd@host:5432/db?sslmode=require``. It
       **replaces** ``hostname``, ``port``, ``username``, ``password`` and
       ``dbname`` rather than merging with them, and its dialect must match
       ``driver``. Declaring it alongside any of those keys **in the same
       file** is rejected as a contradiction; overriding a file's connection
       with ``--source-dsn`` on the command line remains valid. See
       :option:`--source-dsn`.
   * - ``options``
     - ``{}``
     - Driver-specific extra options passed as key/value pairs
       (e.g. ``charset``, ``service_name`` for Oracle).

target_server
~~~~~~~~~~~~~

Connection parameters for the **target** database, used exclusively by the
``migrate`` subcommand. The shape is identical to the source ``server``
section. When ``db2sql migrate`` runs, CLI flags ``--target-host``,
``--target-port``, ``--target-dbname``, ``--target-user``, ``--target-password``
override the corresponding fields here, which in turn override the
``DB2SQL_TARGET_*`` environment variables.

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Key
     - Default
     - Description
   * - ``hostname``
     - ``null``
     - Target server hostname or IP address.
   * - ``port``
     - ``null``
     - Target TCP port.
   * - ``username``
     - ``null``
     - Target database user.
   * - ``password``
     - ``null``
     - Target database password. Prefer the ``DB2SQL_TARGET_PASSWORD``
       environment variable over storing it in the file.
   * - ``dbname``
     - ``null``
     - Target database name.
   * - ``dsn``
     - ``null``
     - Full SQLAlchemy URL for the target. Same semantics as ``server.dsn``:
       it replaces the discrete fields above, its dialect must match
       ``target``, and combining it with those fields in the same file is
       rejected. See :option:`--target-dsn`.
   * - ``options``
     - ``{}``
     - Driver-specific extra options for the target connection.

migrate
~~~~~~~

Options that govern the ``migrate`` subcommand only. The DDL produced is
unaffected by these — they control transactional behaviour and the bulk-load
strategy.

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Key
     - Default
     - Description
   * - ``on_existing``
     - ``fail``
     - Strategy when an object already exists on the target.
       ``fail`` (default) attempts the ``CREATE TABLE`` and aborts on
       conflict. ``drop`` issues a ``DROP TABLE IF EXISTS`` in
       reverse-dependency order before each ``CREATE TABLE``.
       ``truncate`` skips DDL entirely (CREATE / FK / INDEX) and just
       issues ``TRUNCATE`` followed by a bulk-load — used to refresh
       data into a pre-existing schema.
   * - ``transaction_mode``
     - ``single``
     - ``single`` wraps the entire migration in one transaction (atomic).
       ``per_table`` commits after each table (lower lock pressure, partial
       failure leaves some tables loaded).
   * - ``batch_size``
     - ``1000``
     - Rows per ``executemany`` batch for writers that use it (e.g. MSSQL).
       The Postgres writer streams via ``COPY FROM STDIN`` and ignores this
       value.
   * - ``use_transaction``
     - ``true``
     - Emit the target dialect's transaction prologue/epilogue
       (``BEGIN`` / ``COMMIT``) around the migration. Set to ``false`` to
       let the target driver auto-commit each statement — useful for
       targets that disallow transactional DDL or when the writer manages
       its own transactions. Independent from ``transaction_mode``, which
       only chooses the granularity when transactions are enabled. CLI:
       ``--transaction`` / ``--no-transaction`` on ``db2sql migrate``.

Example — config file for a SQLite → live Postgres migration:

.. code-block:: yaml

   driver: sqlite
   target: postgres

   server:
     dbname: ./sample.db

   target_server:
     hostname: localhost
     port: 5432
     dbname: my_target_db
     username: postgres
     password: postgres

   dump:
     preserve_case: true

   migrate:
     on_existing: fail
     transaction_mode: single
     batch_size: 1000

dump
~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Key
     - Default
     - Description
   * - ``preserve_case``
     - ``false``
     - Preserve identifier case as-is.  When ``false``, identifiers are
       converted to ``snake_case`` — acronym runs stay glued
       (``HTTPServer`` → ``http_server``, ``UserID`` → ``user_id``) and
       all-caps names collapse to a single word
       (``MYTABLE`` → ``mytable``).  See :option:`--preserve-case` for
       the full table of examples.
   * - ``limit_records``
     - ``-1``
     - Maximum rows per table.  ``-1`` means no limit.
   * - ``default_data_format``
     - ``copy``
     - Default format for table data: ``copy`` or ``insert``.
   * - ``include_schemas``
     - ``[]``
     - Schemas to include.  An empty list means *all* schemas.
   * - ``exclude_schemas``
     - ``[]``
     - Schemas to exclude.
   * - ``include_tables``
     - ``[]``
     - Tables to include (bare name or ``schema.table``).
   * - ``exclude_tables``
     - ``[]``
     - Tables to exclude (bare name or ``schema.table``).
   * - ``mapping_schemas``
     - ``{}``
     - Map source schema names to target names, e.g.
       ``{dbo: public, legacy: archive}``.
   * - ``tables``
     - ``{}``
     - Per-table overrides (see :ref:`config-table-overrides`).
   * - ``views``
     - ``{}``
     - Custom-query exports materialized as synthesized tables
       (see :ref:`config-view-exports`).
   * - ``on_existing``
     - ``fail``
     - Strategy when a target object already exists. ``fail`` (default)
       emits ``CREATE TABLE`` only. ``drop`` prepends a
       ``DROP TABLE IF EXISTS`` for every table in reverse-dependency
       order. ``truncate`` produces a *data-only* script — no DDL is
       emitted, the dump just ``TRUNCATE``\s every managed table and
       reloads its rows (Postgres uses a single multi-table
       ``TRUNCATE ... RESTART IDENTITY``; MSSQL emits per-table
       ``TRUNCATE`` plus ``DBCC CHECKIDENT`` for identity columns).
   * - ``use_transaction``
     - ``true``
     - Wrap the dump in the target dialect's transaction prologue/epilogue
       (``BEGIN; … COMMIT;`` for PostgreSQL,
       ``BEGIN TRANSACTION; … COMMIT TRANSACTION;`` for MSSQL). Set to
       ``false`` to emit DDL/data without the surrounding transaction —
       useful for chunked or resumable replay, or for targets that
       disallow transactional DDL. CLI: :option:`--transaction` /
       ``--no-transaction``.

.. _config-table-overrides:

Per-table overrides (``dump.tables``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``tables`` map lets you customise the export of individual tables.
Each key is either a bare table name (``orders``) or a fully-qualified
``schema.table`` name (``audit.events``).

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Key
     - Default
     - Description
   * - ``data_format``
     - ``null``
     - Override the data format for this table (``copy`` or ``insert``).
       Inherits ``dump.default_data_format`` when ``null``.
   * - ``limit_records``
     - ``null``
     - Override the row limit for this table.
       Inherits ``dump.limit_records`` when ``null``.
   * - ``where``
     - ``null``
     - SQL ``WHERE`` clause appended to the data query for this table
       (e.g. ``"status = 'active'"``, without the ``WHERE`` keyword).

Example:

.. code-block:: yaml

   dump:
     tables:
       orders:
         data_format: insert
         limit_records: 5000
       audit.events:
         where: "created_at > '2024-01-01'"

.. _config-view-exports:

View exports (``dump.views``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``views`` map declares custom SQL queries whose results are emitted as
synthesized tables in the dump. Each entry produces a ``CREATE TABLE`` plus a
``COPY`` (or ``INSERT``) block, exactly as if it were a real table — except
that the row source is the query you wrote rather than a ``SELECT *`` over a
physical table.

This is useful for anonymisation, denormalisation, pre-aggregation, or for
materialising an existing database view into the dump.

Column types are inferred from the result set by probing one row (Python
``int`` → ``integer``, ``Decimal`` → ``numeric``, ``str`` → ``text``,
``datetime`` → ``timestamp``, etc.; ``text`` if the value is ``NULL`` or the
query returns no rows). Use ``columns`` to override the parts that need a
specific SQL type.

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Key
     - Default
     - Description
   * - ``query``
     - *(required)*
     - SQL ``SELECT`` to execute. Any valid query for the source driver is
       accepted (joins, CTEs, ``GROUP BY``, etc.).
   * - ``target_schema``
     - ``public``
     - Schema under which the synthesized table is created in the dump. The
       schema is created on the fly if it doesn't already exist.
   * - ``target_table``
     - *(map key)*
     - Name of the synthesized table. Defaults to the ``views`` map key.
   * - ``data_format``
     - ``null``
     - Override the data format for this view (``copy`` or ``insert``).
       Inherits ``dump.default_data_format`` when ``null``.
   * - ``limit_records``
     - ``null``
     - Cap the number of rows emitted from this view.
       Inherits ``dump.limit_records`` when ``null``.
   * - ``columns``
     - ``{}``
     - Per-column overrides applied **after** type inference. Each key is a
       column name from the result set; the value accepts ``type``,
       ``nullable``, ``char_length``, ``precision``, and ``scale``.
   * - ``primary_key``
     - ``[]``
     - Ordered list of column names to mark as the primary key on the
       synthesized table. Listed columns are also forced to ``NOT NULL``.
   * - ``indexes``
     - ``{}``
     - Named indexes to emit on the synthesized table.
       Each key is the index name, each value the ordered list of columns.

Example — denormalised reporting table:

.. code-block:: yaml

   dump:
     views:
       customer_summary:
         query: |
           SELECT c.id,
                  c.name,
                  COUNT(o.id) AS order_count,
                  COALESCE(SUM(o.total), 0) AS lifetime_value
           FROM customers c
           LEFT JOIN orders o ON o.customer_id = c.id
           GROUP BY c.id, c.name
         target_schema: reporting       # created if missing
         target_table: customer_totals  # defaults to ``customer_summary``
         primary_key: [id]
         columns:
           lifetime_value: { type: numeric, precision: 12, scale: 2 }
         indexes:
           idx_customer_totals_value: [lifetime_value]

.. note::

   View exports never carry foreign keys (the synthesized columns have no
   referential link to other tables). They are emitted **after** the regular
   tables of the same schema, so they can safely reference real-table data
   even when emitted into an existing schema.

Schema mapping
~~~~~~~~~~~~~~

``dump.mapping_schemas`` renames schemas as they are written to the output
file.  This is useful when migrating from a SQL Server ``dbo`` schema to
PostgreSQL's ``public``:

.. code-block:: yaml

   dump:
     mapping_schemas:
       dbo: public

The key is the source schema name; the value is the target schema name used
in the generated SQL.

Recipes
-------

Each recipe below is a complete, copy-pasteable config file.  Drop it as
``db2sql.yml`` in the current directory (or pass it with ``-C path.yml``)
and run ``db2sql -f dump.sql``.

SQLite → Postgres
~~~~~~~~~~~~~~~~~

The simplest case: a local SQLite file and the default Postgres target.

.. code-block:: yaml

   driver: sqlite
   target: postgres
   server:
     dbname: ./myapp.sqlite
     options:
       schema: public   # logical schema name used in the dump
   dump:
     preserve_case: true
     default_data_format: copy

SQLite → MSSQL
~~~~~~~~~~~~~~

Same source, but emit Microsoft SQL Server output.  ``copy`` is silently
downgraded to ``insert`` (T-SQL has no equivalent of ``COPY … FROM
stdin``).

.. code-block:: yaml

   driver: sqlite
   target: mssql
   server:
     dbname: ./myapp.sqlite
     options:
       schema: dbo
   dump:
     preserve_case: false
     default_data_format: insert

MySQL → Postgres
~~~~~~~~~~~~~~~~

Production MySQL pulled into a Postgres-flavored dump, excluding two
volatile tables.

.. code-block:: yaml

   driver: mysql
   target: postgres
   server:
     hostname: mysql.example.com
     port: 3306
     username: app
     password: s3cr3t
     dbname: mydb
   dump:
     preserve_case: false
     default_data_format: copy
     exclude_tables:
       - audit_log
       - sessions

MSSQL → Postgres
~~~~~~~~~~~~~~~~

A classic migration: rename ``dbo`` to ``public`` and emit Postgres
``COPY`` blocks.

.. code-block:: yaml

   driver: mssql
   target: postgres
   server:
     hostname: sqlserver.example.com
     port: 1433
     username: sa
     password: secret
     dbname: mydb
   dump:
     preserve_case: false
     default_data_format: copy
     mapping_schemas:
       dbo: public

MSSQL → MSSQL (cross-instance copy)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pull from one SQL Server, emit T-SQL ready to be replayed on another.

.. code-block:: yaml

   driver: mssql
   target: mssql
   server:
     hostname: sqlserver-prod.example.com
     port: 1433
     username: reader
     password: s3cr3t
     dbname: mydb
   dump:
     preserve_case: true
     default_data_format: insert   # the only supported format for MSSQL
     exclude_schemas:
       - tmp

Postgres → Postgres
~~~~~~~~~~~~~~~~~~~

Round-trip a Postgres instance — useful as a logical alternative to
``pg_dump`` when you only want a subset of schemas or a row cap per table.

.. code-block:: yaml

   driver: postgres
   target: postgres
   server:
     hostname: pg.example.com
     port: 5432
     username: app
     password: s3cr3t
     dbname: mydb
   dump:
     preserve_case: true
     limit_records: 10000          # cap every table at 10k rows
     include_schemas: [public, audit]

Postgres → MSSQL
~~~~~~~~~~~~~~~~

Move data the other way: from Postgres to SQL Server.  Note the per-table
``WHERE`` clause to skip stale rows.

.. code-block:: yaml

   driver: postgres
   target: mssql
   server:
     hostname: pg.example.com
     port: 5432
     username: app
     password: s3cr3t
     dbname: mydb
   dump:
     preserve_case: false
     default_data_format: insert
     tables:
       audit.events:
         where: "created_at > '2024-01-01'"

Oracle → Postgres
~~~~~~~~~~~~~~~~~

Oracle connections are configured almost entirely through
``server.options``: pick **one** of ``service_name`` or ``sid``, and set
``owner`` to scope the dump to a single schema.

.. code-block:: yaml

   driver: oracle
   target: postgres
   server:
     hostname: oracle.example.com
     port: 1521
     username: admin
     password: s3cr3t
     options:
       service_name: ORCLPDB1
       owner: HR         # dump only the HR schema (case-insensitive)
   dump:
     preserve_case: false
     default_data_format: copy
     mapping_schemas:
       HR: human_resources  # optional rename; snake_case normalization
                            # alone would already produce "hr"

Oracle → MSSQL
~~~~~~~~~~~~~~

The same source, but emit T-SQL.  Oracle types (``CLOB``, ``BLOB``,
``RAW``, ``TIMESTAMP WITH TIME ZONE``) are mapped to MSSQL's
``nvarchar(max)`` / ``varbinary(max)`` / ``datetimeoffset`` automatically.

.. code-block:: yaml

   driver: oracle
   target: mssql
   server:
     hostname: oracle.example.com
     port: 1521
     username: admin
     password: s3cr3t
     options:
       sid: ORCL
   dump:
     preserve_case: false
     default_data_format: insert
     exclude_schemas:
       - SYS
       - SYSTEM

Pre-aggregated view export
~~~~~~~~~~~~~~~~~~~~~~~~~~

Ship a denormalised reporting table alongside the regular tables. The
``customer_summary`` view is computed at dump time and materialised into a
fresh ``reporting`` schema; column types are inferred from the result set,
with one override for the monetary column.

.. code-block:: yaml

   driver: mysql
   target: postgres
   server:
     hostname: mysql.example.com
     port: 3306
     username: app
     password: s3cr3t
     dbname: shop
   dump:
     preserve_case: false
     default_data_format: copy
     exclude_tables:
       - sessions
     views:
       customer_summary:
         query: |
           SELECT c.id,
                  c.name,
                  COUNT(o.id) AS order_count,
                  COALESCE(SUM(o.total), 0) AS lifetime_value
           FROM customers c
           LEFT JOIN orders o ON o.customer_id = c.id
           GROUP BY c.id, c.name
         target_schema: reporting
         target_table: customer_totals
         primary_key: [id]
         columns:
           lifetime_value: { type: numeric, precision: 12, scale: 2 }
