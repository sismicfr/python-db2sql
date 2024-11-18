"""RotatingFileSink: rotates files only at emitter-declared boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from db2sql.infrastructure.output import RotatingFileSink


def test_single_file_when_below_limit(tmp_path: Path) -> None:
    target = tmp_path / "dump.sql"
    with RotatingFileSink(str(target), max_bytes=1024) as sink:
        sink.write("CREATE TABLE t (id int);\n")
        sink.boundary()
        sink.write("INSERT INTO t VALUES (1);\n")
        sink.boundary()
    parts = sink.paths
    assert len(parts) == 1
    assert parts[0].name == "dump-0001.sql"
    assert parts[0].read_text() == "CREATE TABLE t (id int);\nINSERT INTO t VALUES (1);\n"


def test_rotates_when_buffered_data_would_cross_limit(tmp_path: Path) -> None:
    target = tmp_path / "dump.sql"
    statement = "INSERT INTO t VALUES (X);\n"  # 25 bytes
    with RotatingFileSink(str(target), max_bytes=30) as sink:
        for _ in range(3):
            sink.write(statement)
            sink.boundary()
    parts = sink.paths
    # 25 bytes fit; next 25 would push to 50 (> 30) so rotate to file 2;
    # third again rotates. Three statements => three files.
    assert [p.name for p in parts] == [
        "dump-0001.sql",
        "dump-0002.sql",
        "dump-0003.sql",
    ]
    for p in parts:
        assert p.read_text() == statement


def test_never_rotates_mid_statement(tmp_path: Path) -> None:
    target = tmp_path / "dump.sql"
    # Two writes form one logical statement; boundary is only at the end.
    with RotatingFileSink(str(target), max_bytes=10) as sink:
        sink.write("INSERT INTO t ")
        sink.write("VALUES (1);\n")
        sink.boundary()
        sink.write("INSERT INTO t VALUES (2);\n")
        sink.boundary()
    parts = sink.paths
    # First statement (~26 bytes) all in file 1 because we never split mid-stmt.
    assert parts[0].read_text() == "INSERT INTO t VALUES (1);\n"
    assert parts[1].read_text() == "INSERT INTO t VALUES (2);\n"


def test_concatenation_equals_total_payload(tmp_path: Path) -> None:
    target = tmp_path / "dump.sql"
    statements = [f"INSERT INTO t VALUES ({i});\n" for i in range(20)]
    with RotatingFileSink(str(target), max_bytes=60) as sink:
        for stmt in statements:
            sink.write(stmt)
            sink.boundary()
    combined = "".join(p.read_text() for p in sink.paths)
    assert combined == "".join(statements)


def test_path_template_without_suffix(tmp_path: Path) -> None:
    target = tmp_path / "dump"
    with RotatingFileSink(str(target), max_bytes=5) as sink:
        sink.write("abcdef")
        sink.boundary()
        sink.write("ghijkl")
        sink.boundary()
    assert [p.name for p in sink.paths] == ["dump-0001", "dump-0002"]


def test_rejects_non_positive_max_bytes(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        RotatingFileSink(str(tmp_path / "dump.sql"), max_bytes=0)


def test_oversized_statement_goes_to_its_own_file(tmp_path: Path) -> None:
    target = tmp_path / "dump.sql"
    big = "X" * 1000  # bigger than max_bytes by itself
    with RotatingFileSink(str(target), max_bytes=50) as sink:
        sink.write("small;\n")
        sink.boundary()
        sink.write(big)
        sink.boundary()
        sink.write("small;\n")
        sink.boundary()
    parts = sink.paths
    # small / big-alone / small
    assert len(parts) == 3
    assert parts[0].read_text() == "small;\n"
    assert parts[1].read_text() == big
    assert parts[2].read_text() == "small;\n"
