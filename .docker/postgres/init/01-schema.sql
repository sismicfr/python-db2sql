-- Functional-test fixture for PostgreSQL.
--
-- The "db2sqltarget" database (created from POSTGRES_DB by the entrypoint) is
-- used both as:
--   * a TARGET database for dumps produced by db2sql (apply step) — left
--     untouched outside the apptest schema below;
--   * a SOURCE database whose ``apptest`` schema mirrors the mssql/oracle
--     fixtures (type_matrix + author/book) so the PostgreSQL reader can be
--     exercised by the functional suite.
--
-- The reader filters out pg_catalog/information_schema/pg_toast, so the
-- ``apptest`` schema is the only one surfaced by collect_metadata().
-- Note: types covered are the PG-native ones referenced by
-- ``PostgresSqlEmitter.DEFAULT_TYPE_MAP`` (no MSSQL/Oracle-only types).

CREATE SCHEMA IF NOT EXISTS apptest;

DROP TABLE IF EXISTS apptest.book;
DROP TABLE IF EXISTS apptest.author;
DROP TABLE IF EXISTS apptest.type_matrix;

-- Type-coverage table -------------------------------------------------------
CREATE TABLE apptest.type_matrix (
    id                 INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    c_boolean          BOOLEAN,
    c_smallint         SMALLINT,
    c_integer          INTEGER,
    c_bigint           BIGINT,
    c_real             REAL,
    c_double           DOUBLE PRECISION,
    c_numeric          NUMERIC(18, 6),
    c_decimal          DECIMAL(12, 4),
    c_char             CHAR(8),
    c_varchar          VARCHAR(64),
    c_text             TEXT,
    c_bytea            BYTEA,
    c_date             DATE,
    c_time             TIME,
    c_timestamp        TIMESTAMP,
    c_timestamptz      TIMESTAMP WITH TIME ZONE,
    c_uuid             UUID,
    c_json             JSON,
    c_jsonb            JSONB,
    c_xml              XML
);

-- Relational mini-fixture (parallels mssql/oracle/sqlite fixtures)
CREATE TABLE apptest.author (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR(120) NOT NULL,
    birth_year  INTEGER
);

CREATE TABLE apptest.book (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    author_id   INTEGER NOT NULL,
    title       VARCHAR(200) NOT NULL,
    CONSTRAINT fk_book_author FOREIGN KEY (author_id) REFERENCES apptest.author (id)
);

CREATE INDEX idx_book_title ON apptest.book (title);

-- Representative payload (one populated row + one all-NULL row)
INSERT INTO apptest.type_matrix
    (c_boolean, c_smallint, c_integer, c_bigint,
     c_real, c_double, c_numeric, c_decimal,
     c_char, c_varchar, c_text, c_bytea,
     c_date, c_time, c_timestamp, c_timestamptz,
     c_uuid, c_json, c_jsonb, c_xml)
VALUES
    (TRUE, 32100, 2147483640, 9000000000000000000,
     1.5, 3.141592653589793, 1234567.890123, 1234.5678,
     'fixed', 'with accent é', 'long text payload', '\xDEADBEEFCAFEBABE',
     DATE '2024-01-31', TIME '14:30:00',
     TIMESTAMP '2024-01-31 14:30:00',
     TIMESTAMP WITH TIME ZONE '2024-01-31 14:30:00+01',
     '11111111-2222-3333-4444-555555555555',
     '{"k": "v"}', '{"k": "v"}',
     XMLPARSE(DOCUMENT '<root><k>v</k></root>')),
    (NULL, NULL, NULL, NULL,
     NULL, NULL, NULL, NULL,
     NULL, NULL, NULL, NULL,
     NULL, NULL, NULL, NULL,
     NULL, NULL, NULL, NULL);

INSERT INTO apptest.author (name, birth_year) VALUES ('Alice', 1980);
INSERT INTO apptest.author (name, birth_year) VALUES ('Bob', NULL);

INSERT INTO apptest.book (author_id, title) VALUES (1, 'First');
INSERT INTO apptest.book (author_id, title) VALUES (1, 'Second''s ride');
INSERT INTO apptest.book (author_id, title) VALUES (2, 'Bob book');

SELECT 'postgres apptest fixture loaded' AS status;
