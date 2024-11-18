"""Shared pytest fixtures."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture()
def sample_db(tmp_path: Path) -> Path:
    """Create a small SQLite DB with two tables and a foreign key."""
    db_path = tmp_path / "sample.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE author (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            birth_year INTEGER
        );
        CREATE TABLE book (
            id INTEGER PRIMARY KEY,
            author_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            FOREIGN KEY (author_id) REFERENCES author(id)
        );
        CREATE INDEX idx_book_title ON book(title);
        INSERT INTO author (id, name, birth_year) VALUES (1, 'Alice', 1980);
        INSERT INTO author (id, name, birth_year) VALUES (2, 'Bob', NULL);
        INSERT INTO book (id, author_id, title) VALUES (1, 1, 'First');
        INSERT INTO book (id, author_id, title) VALUES (2, 1, 'Second''s ride');
        INSERT INTO book (id, author_id, title) VALUES (3, 2, 'Bob book');
        """
    )
    conn.commit()
    conn.close()
    return db_path
