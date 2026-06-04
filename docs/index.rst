db2sql
======

**db2sql** is a command-line utility that moves any supported source database
(SQLite, MySQL, MSSQL, PostgreSQL, Oracle) into a target dialect — PostgreSQL
(default) or Microsoft SQL Server — preserving schemas, tables, data, indexes,
and foreign keys. It produces either a SQL file (dump mode) or applies the
changes directly to a live target database (migrate mode).

.. code-block:: console

   # SQLite → Postgres SQL file (default target)
   $ db2sql --driver sqlite --dbname mydb.sqlite -f dump.sql

   # MySQL → MSSQL SQL file
   $ db2sql --driver mysql -H mysql.example.com -d mydb -u app -p s3cr3t \
       --target mssql -f dump.sql

   # SQLite → live Postgres database (no intermediate file)
   $ db2sql --driver sqlite --dbname mydb.sqlite migrate \
       --target-host localhost --target-dbname mytarget \
       --target-user postgres --target-password s3cr3t

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: :octicon:`download` Installation
      :link: installation
      :link-type: doc

      Get ``db2sql`` running in minutes with ``pip install python-db2sql``.

   .. grid-item-card:: :octicon:`terminal` CLI Reference
      :link: cli
      :link-type: doc

      Full description of every command-line flag and environment variable.

   .. grid-item-card:: :octicon:`gear` Configuration
      :link: configuration
      :link-type: doc

      YAML/JSON configuration file: all keys, defaults, and examples.

   .. grid-item-card:: :octicon:`arrow-switch` Dialect mapping
      :link: dialect-mapping
      :link-type: doc

      How column types and ``DEFAULT`` expressions (``GETDATE()``,
      ``NEWID()``, ``now()``, …) are translated between source and target.

   .. grid-item-card:: :octicon:`code` API Reference
      :link: api/index
      :link-type: doc

      Auto-generated documentation for the Python package internals.

   .. grid-item-card:: :octicon:`plug` Plugins
      :link: plugins
      :link-type: doc

      Add your own source drivers, target emitters, and target writers
      through the ``db2sql.readers`` / ``db2sql.emitters`` /
      ``db2sql.writers`` entry-point groups.


Key features
------------

- **Multiple sources** — SQLite, MySQL, MSSQL, PostgreSQL, Oracle (via
  optional extras).
- **Multiple targets** — PostgreSQL (default) and Microsoft SQL Server,
  selectable via ``--target``.  Additional emitters and writers can be
  plugged in through the ``db2sql.emitters`` / ``db2sql.writers``
  entry-point groups.
- **Two execution modes** — produce a SQL dump file (replayable with
  ``psql -f`` / ``sqlcmd -i``) or apply the migration directly to a live
  target database via the ``migrate`` subcommand.  The DDL produced is
  identical in both modes — a single ``SqlEmitter`` per dialect is the
  source of truth.
- **Fast bulk load on migrate** — PostgreSQL writer uses ``COPY FROM STDIN``
  (psycopg2), MSSQL writer uses batched ``executemany``.
- **Extensible** — write a new source driver, target emitter, or target
  writer as a small Python package; see :doc:`plugins` for a step-by-step
  guide and three runnable example projects.
- **Validate & dry-run** — ``db2sql validate`` checks a configuration file
  without producing SQL; with ``--dry-run`` it connects to the source and
  prints the export plan, with ``--with-counts`` it adds per-table row
  counts. Handy in CI before scheduling a long dump.
- **Flexible output** — write to a file or pipe to ``stdout``; choose between
  ``COPY`` (Postgres, fast bulk load) and ``INSERT`` formats per table.
  MSSQL output always uses ``INSERT`` (T-SQL has no streaming ``COPY``).
- **Filtering** — include/exclude schemas and tables by name.
- **Schema mapping** — rename source schemas on the fly.
- **Per-table overrides** — different ``data_format``, row limit, or
  ``WHERE`` clause per table via the config file.
- **Config file** — YAML or JSON, with environment variable and CLI override
  support.


Contents
--------

.. toctree::
   :maxdepth: 2

   installation
   cli
   configuration
   dialect-mapping
   plugins
   api/index
   changelog
   contributing
