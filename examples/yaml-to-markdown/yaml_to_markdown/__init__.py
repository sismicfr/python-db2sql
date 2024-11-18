"""db2sql plugin pair: read a YAML schema, emit a Markdown documentation file.

Showcases that one distribution can register **both** a reader and an emitter
through distinct entry-point groups (``db2sql.readers`` / ``db2sql.emitters``).
"""

from .emitter import MarkdownEmitter
from .reader import YamlSchemaReader, build_reader

__all__ = ["YamlSchemaReader", "build_reader", "MarkdownEmitter"]
