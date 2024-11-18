CLI Reference
=============

Synopsis
--------

.. code-block:: text

   db2sql [OPTIONS] [--on-existing {fail,drop,truncate}]
                    [--transaction | --no-transaction]
   db2sql validate [CONFIG_FILE] [--dry-run] [--with-counts]
   db2sql init [-o PATH] [--force]
   db2sql migrate [--target-host HOST] [--target-port PORT] [--target-dbname DB]
                  [--target-user USER] [--target-password PWD]
                  [--target-driver NAME]
                  [--on-existing {fail,drop,truncate}]
                  [--transaction-mode {single,per_table}]
                  [--transaction | --no-transaction]
                  [--batch-size N]

Description
-----------

``db2sql`` reads the structure and data of a source database and either:

* writes a SQL dump in the chosen target dialect (PostgreSQL or Microsoft
  SQL Server) to a file or ``stdout`` — the default behaviour, and
* applies the same DDL and rows directly to a live target database when
  invoked via the ``migrate`` subcommand — see :ref:`cli-migrate`.

The DDL produced is identical in both modes: a single ``SqlEmitter`` per
target dialect is the source of truth, regardless of whether the SQL ends up
in a file or is executed live.

Connection options, filtering rules, and output settings can be supplied via
the :doc:`configuration` file, environment variables, or CLI flags.
**CLI flags always take precedence over the config file**, which itself takes
precedence over environment variables.

The ``init`` subcommand opens an interactive wizard that walks you through a
series of questions and produces a ready-to-use configuration file — see
:ref:`cli-init`.

Options
-------

Connection
~~~~~~~~~~

.. option:: --driver NAME

   Source database driver.  Built-in values: ``mssql``, ``mysql``,
   ``sqlite``, ``postgres``, ``oracle``.

   Additional drivers can be registered via the ``db2sql.readers``
   entry-point group.

   *Environment variable:* ``DB2SQL_DRIVER``

.. option:: --target NAME

   Target SQL dialect to emit.  Built-in values: ``postgres`` (default),
   ``mssql``.

   Additional targets can be registered via the ``db2sql.emitters``
   entry-point group.

   .. note::

      The ``mssql`` target degrades the ``copy`` data-format to ``insert``
      (T-SQL has no streaming ``COPY`` equivalent in plain DML) and emits a
      one-time runtime warning when this happens.

   *Environment variable:* ``DB2SQL_TARGET``

.. option:: -H HOSTNAME, --host HOSTNAME

   Database server hostname or IP address.

   *Environment variable:* ``DB2SQL_HOST``

.. option:: -P PORT, --port PORT

   Database server TCP port.

   *Environment variable:* ``DB2SQL_PORT``

.. option:: -d DBNAME, --dbname DBNAME

   Database name (or, for SQLite, the path to the ``.sqlite`` file).

   *Environment variable:* ``DB2SQL_DBNAME``

.. option:: -u USERNAME, --username USERNAME

   Database user name.

   *Environment variable:* ``DB2SQL_USER``

.. option:: -p PASSWORD, --password PASSWORD

   Database password.

   *Environment variable:* ``DB2SQL_PASSWORD``

   .. warning::

      Passing the password as a CLI argument exposes it to other processes via
      ``ps``.  Prefer the environment variable or :option:`-W`.

.. option:: -W, --ask-password

   Prompt for the database password interactively instead of reading it from
   :option:`-p` or the environment variable.

Output
~~~~~~

.. option:: -f PATH, --file PATH

   Write the SQL dump to ``PATH``.  When omitted, the dump is written to
   ``stdout``.

.. option:: --split-size SIZE

   Split the dump into multiple files when the current file exceeds
   ``SIZE``.  Accepts a raw byte count (``1048576``) or a suffixed value
   (``K``, ``M``, ``G`` — base 1024; ``KB``/``MB``/``GB`` are aliases).

   Requires :option:`-f`. Files are named by inserting a 4-digit, 1-based
   part index before the suffix of ``PATH`` — e.g. ``dump.sql`` becomes
   ``dump-0001.sql``, ``dump-0002.sql``, ….

   Rotation only happens at safe boundaries (after a complete statement,
   after the ``\.`` that closes a Postgres ``COPY`` block), so a file never
   ends in the middle of an ``INSERT`` or a ``COPY`` data block. The
   transactional wrappers (``BEGIN;`` / ``COMMIT;``) span the whole dump
   — replay all parts in order in a single session, e.g.::

      $ cat dump-*.sql | psql -d target

.. option:: --on-existing {fail,drop,truncate}

   Strategy when a target object already exists. The default is ``fail``:
   the dump emits ``CREATE TABLE`` statements only, and replaying the file
   against a database that already contains those tables raises a SQL error.

   With ``drop``, the dump prepends a ``DROP TABLE IF EXISTS`` for every
   table before the matching ``CREATE TABLE``. The DROPs are emitted in
   reverse-dependency order (children before parents) so that referential
   integrity is respected without ``CASCADE`` — only the tables managed by
   the dump are touched.

   With ``truncate``, the dump is **data-only**: no ``CREATE SCHEMA``,
   ``CREATE TABLE``, foreign keys, or indexes are emitted. The script
   issues a ``TRUNCATE`` for every managed table and then reloads the data.
   The target schema must already exist; use this to refresh data into a
   pre-existing structure.

   * On the PostgreSQL target a single
     ``TRUNCATE TABLE a, b, c RESTART IDENTITY;`` is emitted — atomic, and
     foreign keys between the listed tables are resolved without
     ``CASCADE``. Sequences feeding ``IDENTITY`` / ``SERIAL`` columns are
     restarted.
   * On the Microsoft SQL Server target one ``TRUNCATE TABLE`` is emitted
     per table in reverse-dependency order, each followed by
     ``DBCC CHECKIDENT ('schema.table', RESEED, 0);`` when the table has
     an ``IDENTITY`` column.

   .. note::

      In this codebase, "views" declared in the configuration are
      materialized as synthesized tables in the dump, so they are dropped
      via ``DROP TABLE IF EXISTS`` (or truncated like any other table) —
      no ``DROP VIEW`` or ``TRUNCATE VIEW`` is emitted.

.. option:: --data-format {copy,insert}

   Default format used to emit table data.

   ``copy``
     Uses PostgreSQL ``COPY … FROM stdin`` syntax — fast bulk load.

   ``insert``
     Uses individual ``INSERT INTO`` statements.

   The default is ``copy``.  Individual tables can override this via the
   :ref:`config-table-overrides` section in the configuration file.

.. option:: --preserve-case / --no-preserve-case

   When ``--preserve-case`` is set, identifiers (schema names, table names,
   column names) are kept exactly as they appear in the source database.

   When disabled (the default), identifiers are converted to ``snake_case``
   so they work without quoting in PostgreSQL.

.. option:: --transaction / --no-transaction

   Control whether the dump is wrapped in the target dialect's transaction
   prologue/epilogue (``BEGIN; … COMMIT;`` for PostgreSQL,
   ``BEGIN TRANSACTION; … COMMIT TRANSACTION;`` for MSSQL).

   Enabled by default. Disable with ``--no-transaction`` when the SQL is
   consumed by a tool that manages its own transaction, when chunked or
   resumable replay is preferred, or when streaming into a target that
   does not support transactional DDL.

   Equivalent config key: ``dump.use_transaction`` (default ``true``).

.. option:: -n N, --max-records N

   Limit the number of rows exported from each table.  Pass ``-1`` (default)
   for no limit.

   Useful for producing a reduced dataset for development or testing.

Filtering
~~~~~~~~~

.. option:: -i NAME [NAME …], --include-schemas NAME [NAME …]

   Only export the listed schemas.  Repeatable; comma-separated values are
   also accepted.

   Example: ``-i public -i sales`` or ``-i public,sales``

.. option:: -x NAME [NAME …], --exclude-schemas NAME [NAME …]

   Exclude the listed schemas from the export.  Repeatable; comma-separated
   values are also accepted.

   ``--include-schemas`` and ``--exclude-schemas`` are mutually applied:
   exclude is checked first, then include.

.. option:: -I NAME [NAME …], --include-tables NAME [NAME …]

   Only export the listed tables.  Supports bare names (``orders``) and
   fully-qualified ``schema.table`` notation.  Repeatable; comma-separated
   values are also accepted.

.. option:: -X NAME [NAME …], --exclude-tables NAME [NAME …]

   Exclude the listed tables from the export.  Supports bare names and
   ``schema.table`` notation.  Repeatable; comma-separated values are also
   accepted.

General
~~~~~~~

.. option:: -C PATH, --config-file PATH

   Path to a YAML or JSON :doc:`configuration` file.

   *Environment variable:* ``DB2SQL_CONFIG``

   When this option is omitted, ``db2sql`` searches the following locations in
   order:

   1. ``./db2sql.yml``
   2. ``/etc/db2sql.yml``
   3. ``~/db2sql.yml``

.. option:: -L PATH, --log-file PATH

   Redirect log output to ``PATH`` instead of ``stdout``.

.. option:: -V [LEVEL], --verbosity [LEVEL]

   Control log verbosity.  Valid levels, from least to most verbose:

   .. list-table::
      :header-rows: 1
      :widths: 30 70

      * - Flag
        - Description
      * - ``-Vquiet``
        - Suppress all output
      * - ``-Verror``
        - Errors only
      * - ``-Vwarning``
        - Warnings and errors
      * - ``-Vnotice``
        - Notices, warnings, errors
      * - ``-Vstatus`` *(default)*
        - Status messages and above
      * - ``-V`` / ``-Vverbose``
        - Verbose output
      * - ``-VV`` / ``-Vdebug``
        - Debug output
      * - ``-VVV`` / ``-Vtrace``
        - Full trace output

.. option:: --version

   Print version information and exit.

.. _cli-init:

The ``init`` subcommand
-----------------------

``db2sql init`` is an interactive wizard that asks a few questions about the
source database, the target dialect, and the dump options, then prints (or
writes) a configuration file ready to be passed to ``db2sql -C``.

.. code-block:: text

   db2sql init [-o PATH] [--force]

The questions are tailored to the chosen driver:

* ``sqlite`` only asks for the path to the ``.sqlite`` file and a logical
  schema name.
* ``oracle`` asks for ``service_name`` or ``sid`` and an optional
  ``owner``.
* All other network drivers (``mssql``, ``mysql``, ``postgres``) ask for
  hostname, port, database name, and user.

Passwords are opt-in: the wizard explicitly asks whether you want to store
one in the file.  When you do, the value is requested twice (masked) and
must match before it is written.

The generated file only contains the values you set — defaults are left out
to keep the file short and focused.

.. option:: -o PATH, --output PATH

   Write the generated file to ``PATH``.  Without this flag, the file is
   printed to ``stdout``.

.. option:: --force

   Skip the overwrite confirmation when ``-o PATH`` points to an existing
   file.

Example
~~~~~~~

.. code-block:: console

   $ db2sql init -o db2sql.yml
   ? Output format yaml
   ? Source database driver sqlite
   ? Target SQL dialect postgres
   ? Path to the SQLite file ./myapp.sqlite
   ? Logical schema name public
   ? Preserve identifier case? No
   ? Global row limit per table (-1 for no limit) -1
   ? Default data format copy
   ? Schemas to include (comma-separated, empty = all)
   ? Add more entries? No
   …
   Wrote configuration to db2sql.yml

   $ db2sql -C db2sql.yml -f dump.sql

Environment variables
---------------------

All connection parameters can be set via environment variables.  CLI flags
take precedence when both are present.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``DB2SQL_DRIVER``
     - Source database driver (e.g. ``sqlite``, ``mssql``)
   * - ``DB2SQL_TARGET``
     - Target SQL dialect (``postgres`` or ``mssql``; default ``postgres``)
   * - ``DB2SQL_HOST``
     - Database server hostname
   * - ``DB2SQL_PORT``
     - Database server port
   * - ``DB2SQL_DBNAME``
     - Database name / path
   * - ``DB2SQL_USER``
     - Database user name
   * - ``DB2SQL_PASSWORD``
     - Database password
   * - ``DB2SQL_TARGET_HOST``
     - Target database hostname (used by ``db2sql migrate``)
   * - ``DB2SQL_TARGET_PORT``
     - Target database port (used by ``db2sql migrate``)
   * - ``DB2SQL_TARGET_DBNAME``
     - Target database name (used by ``db2sql migrate``)
   * - ``DB2SQL_TARGET_USER``
     - Target database user (used by ``db2sql migrate``)
   * - ``DB2SQL_TARGET_PASSWORD``
     - Target database password (used by ``db2sql migrate``)
   * - ``DB2SQL_CONFIG``
     - Path to a config file
   * - ``NO_COLOR``
     - Disable ANSI colors when set (any value)
   * - ``CLICOLOR_FORCE``
     - Force ANSI colors when set to a non-zero value
   * - ``DB2SQL_COLOR_DARK``
     - Use the dark ANSI color scheme when set to a non-zero value

Subcommands
-----------

``db2sql validate``
~~~~~~~~~~~~~~~~~~~

Validate a configuration file without producing any SQL. Useful in CI
pipelines and before scheduling a long-running dump.

.. code-block:: text

   db2sql validate [CONFIG_FILE] [--dry-run] [--with-counts]

Three modes layered on top of each other:

1. **Default — syntax + plugin resolution.**
   Parses the YAML/JSON, validates it against the Pydantic schema, and
   checks that ``driver`` and ``target`` map to a registered plugin.
   No network I/O, no source connection.

2. **--dry-run** — additionally opens the source connection, collects
   metadata, applies the include/exclude rules and per-table overrides,
   then prints a textual plan: which schemas/tables would be exported,
   in which data format, with which row limit.

3. **--with-counts** — additionally reports the number of rows that would
   be exported per kept table. Implies ``--dry-run``. The command first
   tries an optional ``count_rows(schema, table)`` method on the reader
   (cheap: ``SELECT COUNT(*)``) and otherwise falls back to consuming
   ``iter_rows`` — slow on large tables.

Arguments and flags:

.. option:: CONFIG_FILE

   Positional. Path to the configuration file to validate. When omitted,
   the usual config-file lookup applies: :option:`-C`, then
   ``$DB2SQL_CONFIG``, then ``./db2sql.yml``, ``/etc/db2sql.yml``,
   ``~/db2sql.yml``.

.. option:: --dry-run

   Run the full pipeline without emitting SQL.

.. option:: --with-counts

   Count rows per kept table during ``--dry-run``. Implies ``--dry-run``.

Exit codes:

.. list-table::
   :header-rows: 1
   :widths: 15 85

   * - Code
     - Meaning
   * - ``0``
     - Configuration is valid (and, with ``--dry-run``, the source was
       reachable and the plan was produced).
   * - ``5``
     - The configuration file is unreadable, fails Pydantic validation, or
       references an unknown ``driver`` / ``target``.
   * - ``1``
     - Only in ``--dry-run``: the source connection or metadata collection
       failed (bad credentials, missing tables, permission errors…).

Examples:

.. code-block:: console

   # Just verify the file parses and the plugin names resolve.
   $ db2sql validate db2sql.yml

   # Connect to the source and print the export plan, without emitting SQL.
   $ db2sql validate db2sql.yml --dry-run

   # Same plan plus row counts per kept table.
   $ db2sql validate db2sql.yml --dry-run --with-counts

   # Use the default config-file lookup (no positional argument).
   $ DB2SQL_CONFIG=/etc/db2sql/prod.yml db2sql validate --dry-run

.. _cli-migrate:

``db2sql migrate``
~~~~~~~~~~~~~~~~~~

Apply the source database directly to a live target database, without going
through an intermediate ``.sql`` file. The DDL emitted to the target is
byte-identical to what ``db2sql > dump.sql && psql -f dump.sql`` would have
produced — only the row-data transport differs (the migrate path uses the
target's native bulk-load primitive: ``COPY FROM STDIN`` for PostgreSQL,
batched ``executemany`` for MSSQL).

.. code-block:: text

   db2sql migrate [--target-host HOSTNAME] [--target-port PORT]
                  [--target-dbname DBNAME] [--target-user USERNAME]
                  [--target-password PASSWORD] [--target-driver NAME]
                  [--on-existing {fail,drop,truncate}]
                  [--transaction-mode {single,per_table}]
                  [--transaction | --no-transaction]
                  [--batch-size N]

The source is configured exactly like for a file dump (top-level
``--driver`` / ``-H`` / ``-P`` / ``-d`` / ``-u`` / ``-p`` flags, the
``server:`` section of the config file, or the ``DB2SQL_*`` environment
variables). The target connection is configured via the ``--target-*``
flags below, the ``target_server:`` section of the config file, or the
``DB2SQL_TARGET_*`` environment variables.

Target connection
^^^^^^^^^^^^^^^^^

.. option:: --target-driver NAME

   Name of the registered ``TargetWriter`` to use. Defaults to the value of
   ``--target`` (so a Postgres-target dump and a Postgres-target migration
   share the same dialect name). Built-in: ``postgres``, ``mssql``.
   Additional writers can be registered via the ``db2sql.writers``
   entry-point group — see :doc:`plugins`.

.. option:: --target-host HOSTNAME

   Target database host name.

   *Environment variable:* ``DB2SQL_TARGET_HOST``

.. option:: --target-port PORT

   Target database port.

   *Environment variable:* ``DB2SQL_TARGET_PORT``

.. option:: --target-dbname DBNAME

   Target database name.

   *Environment variable:* ``DB2SQL_TARGET_DBNAME``

.. option:: --target-user USERNAME

   Target database user name.

   *Environment variable:* ``DB2SQL_TARGET_USER``

.. option:: --target-password PASSWORD

   Target database password. Prefer the environment variable or the config
   file over the command line to avoid leaking secrets in shell history.

   *Environment variable:* ``DB2SQL_TARGET_PASSWORD``

Migration behaviour
^^^^^^^^^^^^^^^^^^^

.. option:: --on-existing {fail,drop,truncate}

   Strategy when an object (schema, table) already exists on the target.
   Currently exposed for forward compatibility — the default ``fail`` means
   the migration aborts if the target is not empty. Default: ``fail``.

.. option:: --transaction-mode {single,per_table}

   Transaction granularity for the migration. ``single`` wraps the entire
   migration in one ``BEGIN`` / ``COMMIT`` (atomic, all-or-nothing).
   ``per_table`` commits after each table. Default: ``single``.

.. option:: --transaction / --no-transaction

   Control whether the emitter's transaction prologue/epilogue
   (``BEGIN`` / ``COMMIT``) is emitted at all. Enabled by default —
   disable with ``--no-transaction`` to let the target driver auto-commit
   each statement (useful for targets that disallow transactional DDL or
   when the writer manages its own transactions).

   Independent from :option:`--transaction-mode`, which only chooses the
   granularity when transactions are enabled.

   Equivalent config key: ``migrate.use_transaction`` (default ``true``).

.. option:: --batch-size N

   Number of rows per bulk-load batch. Used by writers whose bulk-load path
   is implemented via ``executemany`` (e.g. the MSSQL writer). The Postgres
   writer streams via ``COPY FROM STDIN`` and ignores this value. Default:
   ``1000``.

Exit codes:

.. list-table::
   :header-rows: 1
   :widths: 15 85

   * - Code
     - Meaning
   * - ``0``
     - Migration completed successfully (DDL + data committed on the target).
   * - ``5``
     - Configuration error, unknown ``--target-driver``, or unreachable
       source/target.
   * - ``1``
     - Source read or target write failed mid-migration. The wrapping
       transaction is rolled back so the target is left untouched.

Examples:

.. code-block:: console

   # SQLite → live Postgres
   $ db2sql --driver sqlite --dbname mydb.sqlite migrate \
       --target-host localhost --target-port 5432 \
       --target-dbname mytarget --target-user postgres --target-password s3cr3t

   # MSSQL source → live MSSQL target (different instance), via a config file
   $ db2sql -C migrate.yml migrate

   # Use environment variables for the target credentials (recommended)
   $ export DB2SQL_TARGET_HOST=db.internal \
            DB2SQL_TARGET_DBNAME=stage \
            DB2SQL_TARGET_USER=svc_migrate \
            DB2SQL_TARGET_PASSWORD=$(vault read -field=password kv/db)
   $ db2sql --driver mssql -H prod-mssql -d sales -u readonly -p $SOURCE_PWD migrate

Examples
--------

The matrix is **5 sources × 2 targets** — any source driver can be combined
with any target emitter via ``--driver`` and ``--target``.  The recipes below
group examples by source first (the most common entry point), then list
target-specific snippets.

By source driver
~~~~~~~~~~~~~~~~

SQLite
^^^^^^

SQLite needs only the path to the ``.sqlite`` file — either as
``--dbname`` or as ``server.options.path`` in the config file.  All tables
are placed under a single logical schema (``public`` by default; override
with ``server.options.schema``).

.. code-block:: console

   $ db2sql --driver sqlite --dbname ./myapp.sqlite -f dump.sql

For a custom logical schema name, drop a config file alongside the dump
and reference it with :option:`-C`:

.. code-block:: yaml

   # db2sql.yml
   driver: sqlite
   server:
     dbname: ./myapp.sqlite
     options:
       schema: app

.. code-block:: console

   $ db2sql -C db2sql.yml -f dump.sql

MySQL
^^^^^

Requires ``pymysql`` (``pip install "python-db2sql[mysql]"``).  Default port
is ``3306``.

.. code-block:: console

   $ db2sql --driver mysql \
       -H mysql.example.com -P 3306 \
       -u app -W \
       -d mydb \
       -f dump.sql

   # piping straight into a target Postgres instance via psql
   $ db2sql --driver mysql -H mysql.example.com -d mydb -u app -p s3cr3t \
       | psql "host=pg.example.com dbname=mydb user=app"

Microsoft SQL Server (as a source)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Requires ``pymssql`` (``pip install "python-db2sql[mssql]"``).  Default port
is ``1433``.  Use ``mapping_schemas`` to rewrite ``dbo`` to the Postgres
convention ``public``.

.. code-block:: console

   $ db2sql --driver mssql \
       -H sqlserver.example.com -P 1433 \
       -u sa -W \
       -d mydb \
       -f dump.sql

   # credentials via environment instead of CLI flags
   $ export DB2SQL_DRIVER=mssql
   $ export DB2SQL_HOST=sqlserver.example.com
   $ export DB2SQL_DBNAME=mydb
   $ export DB2SQL_USER=sa
   $ export DB2SQL_PASSWORD=secret
   $ db2sql -f dump.sql

PostgreSQL (as a source)
^^^^^^^^^^^^^^^^^^^^^^^^^

Requires ``psycopg2-binary`` (``pip install "python-db2sql[postgres]"``).
Default port is ``5432``.

.. code-block:: console

   $ db2sql --driver postgres \
       -H pg.example.com -P 5432 \
       -u app -p s3cr3t \
       -d mydb \
       -i public -i audit \
       --data-format insert \
       -f dump.sql

Oracle
^^^^^^

Requires ``oracledb`` (``pip install "python-db2sql[oracle]"``).  Identify
the database with **either** ``service_name`` **or** ``sid`` under
``server.options`` — neither is exposed as a top-level CLI flag, so Oracle
connections need a small config file.  ``server.dbname`` is used as a
fallback SID.  Use ``server.options.owner`` to dump a single schema
(Oracle owners are upper-cased automatically).

Via ``service_name`` (typical for pluggable databases), filtered to one
owner:

.. code-block:: yaml

   # oracle-hr.yml
   driver: oracle
   server:
     hostname: oracle.example.com
     port: 1521
     username: admin
     password: s3cr3t
     options:
       service_name: ORCLPDB1
       owner: HR

.. code-block:: console

   $ db2sql -C oracle-hr.yml -f hr_dump.sql

Via ``sid``, dumping every non-system schema:

.. code-block:: yaml

   # oracle-all.yml
   driver: oracle
   server:
     hostname: oracle.example.com
     port: 1521
     username: admin
     password: s3cr3t
     options:
       sid: ORCL

.. code-block:: console

   $ db2sql -C oracle-all.yml -f full_dump.sql

By target emitter
~~~~~~~~~~~~~~~~~

PostgreSQL output (default)
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The default target — wraps the dump in ``BEGIN; … COMMIT;``, quotes
identifiers with ``"double quotes"``, uses ``serial`` / ``bigserial`` for
identity columns, and emits ``COPY … FROM stdin`` blocks for bulk data
unless ``--data-format insert`` is requested.

.. code-block:: console

   # explicit (postgres is the default — both forms are equivalent)
   $ db2sql --driver sqlite --target postgres -d myapp.sqlite -f dump.sql

   # load straight into a running Postgres instance
   $ db2sql --driver mssql -H sqlserver.example.com -d mydb -u sa -p s3cr3t \
       | psql -h pg.example.com -U app -d mydb_imported

Microsoft SQL Server output
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Wraps the dump in ``BEGIN TRANSACTION; … COMMIT TRANSACTION;``, quotes
identifiers with ``[brackets]``, uses ``IDENTITY(1,1)`` for identity
columns, and emits schemas via
``IF NOT EXISTS (sys.schemas) EXEC('CREATE SCHEMA …')``.

.. note::

   T-SQL has no streaming ``COPY`` equivalent, so when ``--target mssql``
   is used the ``copy`` data-format degrades to ``insert``.  A one-time
   ``UserWarning`` is emitted on the first such fallback.

.. code-block:: console

   # SQLite source → MSSQL output
   $ db2sql --driver sqlite --target mssql -d myapp.sqlite -f dump.sql

   # MySQL source → MSSQL output, piped into sqlcmd
   $ db2sql --driver mysql -H mysql.example.com -d mydb -u app -p s3cr3t \
       --target mssql \
       | sqlcmd -S sqlserver.example.com -d mydb_imported -U sa -P s3cr3t

   # Postgres source → MSSQL output, restricted to two schemas
   $ db2sql --driver postgres -H pg.example.com -d mydb -u app -W \
       --target mssql \
       -i public -i audit \
       -f mssql_dump.sql

Other recipes
~~~~~~~~~~~~~

Dump only two schemas, using INSERT statements:

.. code-block:: console

   $ db2sql --driver postgres -H localhost -d mydb \
       -i public -i audit \
       --data-format insert \
       -f dump.sql

Produce a 100-row sample for every table (useful for development):

.. code-block:: console

   $ db2sql --driver mysql -H localhost -d mydb -n 100 -f sample.sql

Use a config file explicitly:

.. code-block:: console

   $ db2sql -C /etc/db2sql/production.yml -f dump.sql

Exclude a few tables from an otherwise complete MSSQL dump:

.. code-block:: console

   $ db2sql --driver mssql -H sqlserver.example.com -d mydb -u sa -W \
       -X audit_log -X temp_data \
       -f dump.sql
