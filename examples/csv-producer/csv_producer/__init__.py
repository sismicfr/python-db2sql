"""db2sql CSV reader plugin: a directory of CSV files becomes a source database."""

from .reader import CsvFolderReader, build_reader

__all__ = ["CsvFolderReader", "build_reader"]
