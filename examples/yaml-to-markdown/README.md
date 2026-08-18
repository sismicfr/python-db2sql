# yaml-to-markdown — custom reader **and** emitter in one plugin

A single distribution that registers **both** a `SourceReader` (driver
`yaml`) and a `SqlEmitter` (target `markdown`). Together they turn a
hand-written YAML schema description into a Markdown documentation page —
no database required.

## Install

```bash
pip install -e .
```

The `pyproject.toml` declares both entry-points:

```toml
[project.entry-points."db2sql.readers"]
yaml = "yaml_to_markdown:build_reader"

[project.entry-points."db2sql.emitters"]
markdown = "yaml_to_markdown:MarkdownEmitter"
```

You can also mix and match: use the new YAML reader with the built-in
`postgres` emitter, or feed a real MySQL database into the new `markdown`
emitter.

## Run

```bash
mkdir -p docs
db2sql dump -C db2sql.yml
cat docs/schema.md
```

## What to look at

- `yaml_to_markdown/reader.py` — implements `SourceReader`, populating
  `Database` / `Schema` / `Table` / `Column` / `ForeignKey` from YAML.
- `yaml_to_markdown/emitter.py` — implements `SqlEmitter` but writes
  Markdown instead of SQL, demonstrating that the port really is just
  "consume a Database and write to a sink".
- `pyproject.toml` — registers both entry-points from the same package.
- `schema.yml` — hand-written sample input.

## Why it matters

It proves the two extension points are **orthogonal**: you can ship a
reader-only plugin, an emitter-only plugin, or — as here — both in the
same package. db2sql wires them together based on `driver` + `target` in
the configuration.
