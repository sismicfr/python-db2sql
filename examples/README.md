# db2sql — plugin examples

This folder contains three self-contained example projects that show how to
extend db2sql with custom plugins. Each one is a regular Python distribution
with its own `pyproject.toml`; install with `pip install -e .` from inside
the project directory and the plugin becomes available the next time you
run `db2sql`.

db2sql discovers plugins through two
[entry-point groups](https://packaging.python.org/en/latest/specifications/entry-points/):

| Entry-point group | Purpose | Port (Protocol)                              |
|---|---|---|
| `db2sql.readers`  | Source-database adapters | `db2sql.application.ports.SourceReader` |
| `db2sql.emitters` | Target-dialect writers   | `db2sql.application.ports.SqlEmitter`   |

The name you register becomes a usable value of `driver:` (readers) or
`target:` (emitters) in `db2sql.yml`.

## The three examples

| Folder | Adds | Shows |
|---|---|---|
| [`csv-producer/`](./csv-producer)         | reader `csv`                     | Custom producer only — a folder of CSV files becomes a source database. |
| [`sqlite-emitter/`](./sqlite-emitter)     | emitter `sqlite`                 | Custom emitter only — produces SQLite-flavoured SQL from any source. |
| [`yaml-to-markdown/`](./yaml-to-markdown) | reader `yaml` + emitter `markdown` | One package, both extension points — YAML schema in, Markdown doc out. |

## Typical workflow

```bash
cd examples/csv-producer
pip install -e .          # registers driver=csv
db2sql dump -C db2sql.yml   # uses the new reader, pipes to the built-in postgres emitter
```

To verify a plugin was picked up:

```python
from db2sql.infrastructure.plugins import available_readers, available_emitters
print(available_readers())
print(available_emitters())
```

## Programmatic registration (no entry-point)

For tests or notebooks, plugins can also be registered in-process without
publishing a distribution:

```python
from db2sql.infrastructure.plugins import register_reader, register_emitter
from csv_producer import build_reader
from sqlite_emitter import SqliteSqlEmitter

register_reader("csv", build_reader)
register_emitter("sqlite", SqliteSqlEmitter)
```

This is the same registry that the entry-point loader populates, so the rest
of db2sql (CLI, use case, config) sees them identically.
