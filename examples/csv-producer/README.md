# csv-producer — custom `SourceReader` plugin

A minimal db2sql plugin that registers a new `driver: csv`. Each `*.csv` file
in a configured folder becomes a table; the first row is the header and the
first column is treated as the primary key.

## Install

```bash
pip install -e .
```

This registers the `csv` reader through the `db2sql.readers` entry-point group
defined in `pyproject.toml`:

```toml
[project.entry-points."db2sql.readers"]
csv = "csv_producer:build_reader"
```

## Run

```bash
db2sql dump -C db2sql.yml
```

`db2sql.yml` points the reader at `./sample_data`, which contains two CSV
files. The dump is emitted as PostgreSQL DDL+INSERTs on stdout.

## What to look at

- `csv_producer/reader.py` — implements the two methods of the
  `db2sql.application.ports.SourceReader` Protocol:
  - `collect_metadata()` returns a `Database` aggregate (schemas → tables → columns)
  - `iter_rows(schema, table, limit)` streams row tuples
- `csv_producer/__init__.py` — exposes the `build_reader` factory that
  db2sql calls with `(AppConfig, Logger)`.
- `pyproject.toml` — wires the plugin name to that factory.
