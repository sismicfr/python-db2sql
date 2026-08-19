# sqlite-emitter — custom `SqlEmitter` plugin

A db2sql plugin that registers a new `target: sqlite`. It produces SQL that
can be loaded straight into `sqlite3`:

```bash
db2sql dump -C db2sql.yml > dump.sql
sqlite3 destination.db < dump.sql
```

## Install

```bash
pip install -e .
```

This registers the emitter through the `db2sql.emitters` entry-point group
declared in `pyproject.toml`:

```toml
[project.entry-points."db2sql.emitters"]
sqlite = "sqlite_emitter:SqliteSqlEmitter"
```

The factory db2sql looks up is the class itself — it is instantiated with
keyword arguments (`preserve_case=…`, `schema_mapping=…`) collected from the
configuration.

## Try it

Point any existing reader at the example. The provided `db2sql.yml` reuses
the built-in SQLite reader for source, and uses the new emitter for output:

```bash
db2sql dump -C db2sql.yml > dump.sql
```

## What to look at

- `sqlite_emitter/emitter.py` — implements every method of the
  `db2sql.application.ports.SqlEmitter` Protocol:
  - `emit_prologue` / `emit_epilogue` (wraps the dump in a transaction)
  - `emit_schemas` (no-op: SQLite has no schemas)
  - `emit_tables` (renders `CREATE TABLE` with inline `PRIMARY KEY`)
  - `emit_foreign_keys`, `emit_indexes`
  - `emit_data_copy` / `emit_data_insert` (`COPY` is rewritten to `INSERT`)
- `pyproject.toml` — wires the plugin name to the emitter class.

## What it intentionally skips

- Foreign keys (SQLite cannot add them via `ALTER TABLE`). A production
  emitter would inline them in `CREATE TABLE`; here the method is left as a
  no-op so the example stays focused.
