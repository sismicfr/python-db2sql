Plugins — extending db2sql
==========================

``db2sql`` is built around three narrow Protocols. Anything that satisfies
them can be plugged in as a new **source driver**, a new **target emitter**
(for the file dump), or a new **target writer** (for the live ``migrate``
subcommand) — without modifying ``db2sql`` itself.

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Extension point
     - Entry-point group
     - Protocol (in ``db2sql.application.ports``)
   * - Source driver (producer)
     - ``db2sql.readers``
     - :class:`~db2sql.application.ports.source_reader.SourceReader`
   * - Target emitter (dump mode)
     - ``db2sql.emitters``
     - :class:`~db2sql.application.ports.sql_emitter.SqlEmitter`
   * - Target writer (migrate mode)
     - ``db2sql.writers``
     - :class:`~db2sql.application.ports.target_writer.TargetWriter`

The name you register becomes a usable value of ``driver:`` (readers) or
``target:`` (emitters and writers) in :doc:`configuration` — and of
:option:`--driver` / :option:`--target` on the CLI.

A target dialect can ship either an emitter, a writer, or both. The built-in
``postgres`` and ``mssql`` targets ship both, so ``db2sql --target postgres``
(dump) and ``db2sql --target postgres migrate`` use the matched pair.

.. tip::

   Three runnable example projects ship in the
   `examples/ <https://github.com/sismicfr/python-db2sql/tree/main/examples>`__
   folder of the repository. Each one is a standalone Python distribution
   that you can ``pip install -e .`` and immediately use through ``db2sql``.

   * ``examples/csv-producer`` — custom reader only (CSV folder → tables)
   * ``examples/sqlite-emitter`` — custom emitter only (SQLite-flavoured SQL)
   * ``examples/yaml-to-markdown`` — both: YAML schema reader + Markdown emitter
     in a single package

Writing a reader (producer)
---------------------------

A reader implements four methods:

.. code-block:: python

   from typing import Any, Iterator, List, Tuple

   from db2sql.application.ports import Logger
   from db2sql.domain.model import Column, Database, Table
   from db2sql.infrastructure.config import AppConfig


   class MyReader:
       def __init__(self, config: AppConfig, logger: Logger) -> None:
           self._config = config
           self._logger = logger

       def collect_metadata(self) -> Database:
           """Return a populated Database aggregate (schemas → tables → columns)."""
           ...

       def iter_rows(
           self, schema: str, table: Table, limit: int = -1
       ) -> Iterator[Tuple[Any, ...]]:
           """Stream row tuples for ``schema.table``. ``limit < 0`` means no cap."""
           ...

       def describe_query(self, query: str) -> List[Column]:
           """Infer the columns produced by ``query`` (needed for ``dump.views``).

           If your reader uses SQLAlchemy, the built-in helper
           ``db2sql.infrastructure.persistence.query_introspection.describe_query``
           runs the query, probes one row, and returns inferred Postgres-style
           types — wrap it as a one-liner.
           """
           ...

       def iter_query_rows(
           self, query: str, limit: int = -1
       ) -> Iterator[Tuple[Any, ...]]:
           """Stream row tuples for an arbitrary ``query`` (needed for ``dump.views``)."""
           ...


   def build_reader(config: AppConfig, logger: Logger) -> MyReader:
       """Factory invoked by db2sql with the resolved config + logger."""
       return MyReader(config, logger)

Then declare the entry-point in your project's ``pyproject.toml``:

.. code-block:: toml

   [project.entry-points."db2sql.readers"]
   mydriver = "my_package:build_reader"

After ``pip install -e .``, the new driver is available immediately:

.. code-block:: console

   $ db2sql --driver mydriver --dbname … -f dump.sql

Reader inputs come from :class:`~db2sql.infrastructure.config.schema.AppConfig`:

* ``config.server.hostname`` / ``port`` / ``username`` / ``password`` / ``dbname``
* ``config.server.options`` — free-form ``dict[str, str]`` for any
  driver-specific setting (e.g. ``path``, ``schema``, ``service_name``, …)

Writing an emitter
------------------

An emitter renders a :class:`~db2sql.domain.model.database.Database` aggregate
into a sink. The Protocol is dialect-agnostic — the built-in implementations
write PostgreSQL or T-SQL, and nothing prevents an emitter from writing
Markdown, GraphViz, or any other text format.

.. code-block:: python

   from typing import Any, Iterable, Mapping, Optional

   from db2sql.application.ports import OutputSink
   from db2sql.domain.model import Database, Schema, Table


   class MyEmitter:
       def __init__(
           self,
           preserve_case: bool = False,
           schema_mapping: Optional[Mapping[str, str]] = None,
       ) -> None:
           self._preserve_case = preserve_case
           self._schema_mapping = schema_mapping or {}

       def emit_prologue(self, sink: OutputSink) -> None: ...
       def emit_epilogue(self, sink: OutputSink) -> None: ...
       def emit_schemas(self, database: Database, sink: OutputSink) -> None: ...
       def emit_tables(self, database: Database, sink: OutputSink) -> None: ...
       def emit_foreign_keys(self, database: Database, sink: OutputSink) -> None: ...
       def emit_indexes(self, database: Database, sink: OutputSink) -> None: ...

       def emit_data_copy(
           self,
           schema: Schema,
           table: Table,
           rows: Iterable[Iterable[Any]],
           sink: OutputSink,
       ) -> None: ...

       def emit_data_insert(
           self,
           schema: Schema,
           table: Table,
           rows: Iterable[Iterable[Any]],
           sink: OutputSink,
       ) -> None: ...

The factory db2sql looks up is **the class itself**, instantiated with the
keyword arguments ``preserve_case`` and ``schema_mapping`` (derived from
``dump.preserve_case`` and ``dump.mapping_schemas`` in the config). Unknown
keyword arguments are forwarded as-is, so an emitter is free to accept
extra options.

Declare it in ``pyproject.toml``:

.. code-block:: toml

   [project.entry-points."db2sql.emitters"]
   mytarget = "my_package:MyEmitter"

And use it:

.. code-block:: console

   $ db2sql --target mytarget -f dump.sql

Call sequence
~~~~~~~~~~~~~

The use case calls the emitter in this exact order (see
:class:`~db2sql.application.use_cases.dump_database.DumpDatabaseUseCase`)::

   emit_prologue
   emit_schemas
   emit_tables
   for each (schema, table):
       emit_data_copy   (when default_data_format == "copy")
       emit_data_insert (when default_data_format == "insert")
   emit_foreign_keys
   emit_indexes
   emit_epilogue

If your target dialect cannot honour a step (SQLite has no schemas, T-SQL has
no streaming ``COPY``), the convention is to make the method a no-op or to
silently degrade — the built-in MSSQL emitter does the latter for ``COPY``.

Writing a target writer (migrate mode)
--------------------------------------

A writer applies DDL strings and bulk-loads rows directly into a live target
database. It is invoked by the ``migrate`` subcommand. The DDL strings come
from the matched ``SqlEmitter`` for the same target name — that's how
``db2sql`` guarantees the migrated schema is identical to what the file
dump would have produced.

.. code-block:: python

   from types import TracebackType
   from typing import Any, Iterator, Optional, Tuple

   from db2sql.application.ports import Logger
   from db2sql.domain.model import Table
   from db2sql.infrastructure.config import AppConfig


   class MyTargetWriter:
       def __init__(self, config: AppConfig, logger: Logger) -> None:
           self._config = config
           self._logger = logger
           self._connection = None  # opened in __enter__

       def __enter__(self) -> "MyTargetWriter":
           # Open the target connection using config.target_server.*
           # Run any session-setup statements (encoding, isolation, …)
           ...
           return self

       def __exit__(
           self,
           exc_type: Optional[type[BaseException]],
           exc: Optional[BaseException],
           tb: Optional[TracebackType],
       ) -> None:
           # Commit on success, rollback on exception, then close.
           ...

       def execute_ddl(self, statement: str) -> None:
           """Execute one DDL/DML statement produced by the SqlEmitter."""
           ...

       def bulk_load(
           self,
           schema: str,
           table: Table,
           rows: Iterator[Tuple[Any, ...]],
       ) -> None:
           """Bulk-insert ``rows`` into ``schema.table`` via the target's
           fastest native primitive (COPY, BULK INSERT, executemany, …)."""
           ...


   def build_writer(config: AppConfig, logger: Logger) -> MyTargetWriter:
       """Factory invoked by db2sql with the resolved config + logger."""
       return MyTargetWriter(config, logger)

Declare it in ``pyproject.toml``:

.. code-block:: toml

   [project.entry-points."db2sql.writers"]
   mytarget = "my_package:build_writer"

And use it:

.. code-block:: console

   $ db2sql --target mytarget migrate --target-host … --target-dbname …

Writer inputs come from :class:`~db2sql.infrastructure.config.schema.AppConfig`:

* ``config.target_server.hostname`` / ``port`` / ``username`` / ``password`` /
  ``dbname`` — the live target connection.
* ``config.migrate.batch_size`` / ``transaction_mode`` / ``on_existing`` —
  general migration options. A writer is free to honour them or ignore them
  if irrelevant (e.g. the Postgres writer streams via ``COPY`` and ignores
  ``batch_size``).

Call sequence
~~~~~~~~~~~~~

The ``migrate`` use case calls the writer through an
:class:`~db2sql.infrastructure.output.executing_sink.ExecutingSink` that pipes
emitter output into ``execute_ddl``::

   __enter__
   execute_ddl("BEGIN;")                      # via the emitter prologue
   execute_ddl("CREATE SCHEMA …;") × N
   execute_ddl("CREATE TABLE …;") × N
   for each (schema, table):
       bulk_load(schema, table, rows)         # native fast-path
   execute_ddl("ALTER TABLE … ADD FOREIGN KEY …;") × N
   execute_ddl("CREATE INDEX …;") × N
   execute_ddl("COMMIT;")                     # via the emitter epilogue
   __exit__

The fact that the same emitter ``emit_*`` methods are called in the same
order as in dump mode is what guarantees DDL identity between the two
modes.

Programmatic registration (no entry-point)
------------------------------------------

For tests, notebooks, or short scripts, plugins can be registered in-process
without building a distribution:

.. code-block:: python

   from db2sql.infrastructure.plugins import (
       register_reader,
       register_emitter,
       register_writer,
   )

   register_reader("mydriver", build_reader)
   register_emitter("mytarget", MyEmitter)
   register_writer("mytarget", build_writer)

The CLI, the use case, and ``available_readers()`` / ``available_emitters()``
/ ``available_writers()`` all see manually registered plugins the same way
they see entry-point ones.

Discovering what is installed
-----------------------------

.. code-block:: python

   from db2sql.infrastructure.plugins import (
       available_readers,
       available_emitters,
       available_writers,
   )

   print(available_readers())   # ['csv', 'mssql', 'mysql', 'oracle', 'postgres', 'sqlite']
   print(available_emitters())  # ['markdown', 'mssql', 'postgres', 'sqlite']
   print(available_writers())   # ['mssql', 'postgres']

When the configuration references an unknown name, the CLI exits with
:class:`~db2sql.infrastructure.plugins.registry.UnknownReaderError`,
:class:`~db2sql.infrastructure.plugins.registry.UnknownEmitterError`, or
:class:`~db2sql.infrastructure.plugins.registry.UnknownWriterError`, whose
message lists every known plugin.

Packaging tips
--------------

* Depend on ``python-db2sql`` in your plugin's ``[project] dependencies``.
* Pick a unique name for your entry-point — it must not collide with built-in
  drivers (``mssql``, ``mysql``, ``oracle``, ``postgres``, ``sqlite``),
  emitters (``postgres``, ``mssql``), or writers (``postgres``, ``mssql``).
* If your plugin needs an extra runtime dependency (e.g. ``pyyaml``,
  ``duckdb``, …), declare it in ``[project] dependencies`` of the plugin —
  ``db2sql`` itself stays slim.
* The plugin distribution does **not** need to live in the ``db2sql``
  namespace package. Pick any package name you like.

End-to-end examples
-------------------

The three example projects under ``examples/`` are the recommended starting
points. Each ships with a ``README.md``, a working ``db2sql.yml``, and a
sample dataset so you can run them in seconds.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Folder
     - What it demonstrates
   * - ``examples/csv-producer``
     - Custom **reader** only — a directory of CSV files becomes a source
       database (``driver: csv``); piped into the built-in ``postgres``
       emitter.
   * - ``examples/sqlite-emitter``
     - Custom **emitter** only — SQLite-flavoured SQL (``target: sqlite``);
       fed by the built-in ``sqlite`` reader.
   * - ``examples/yaml-to-markdown``
     - **Both** in one package — ``driver: yaml`` + ``target: markdown``
       turn a hand-written YAML schema into a Markdown documentation file.
