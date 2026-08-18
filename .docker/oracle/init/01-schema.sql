-- Functional-test fixture for Oracle (gvenzl/oracle-free).
-- Covers every Oracle source type referenced by
-- db2sql/infrastructure/emit/postgres/emitter.py:DEFAULT_TYPE_MAP, plus an
-- IDENTITY column (12c+), a foreign key and a non-unique index.
--
-- Notes:
--   * gvenzl/oracle-free runs the scripts in /container-entrypoint-initdb.d
--     as SYS **in CDB$ROOT**, not in the pluggable database as APP_USER. Left
--     alone, every table below lands in CDB$ROOT owned by SYS, and the reader
--     — which filters on owner = 'APPTEST' in FREEPDB1 — sees an empty
--     database. The two ALTER SESSION statements below are what put the
--     objects where the tests look for them; do not drop them.
--   * LONG can only be used once per table, so it lives in its own table.

ALTER SESSION SET CONTAINER = FREEPDB1;
ALTER SESSION SET CURRENT_SCHEMA = APPTEST;

ALTER SESSION SET NLS_DATE_FORMAT='YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_TIMESTAMP_FORMAT='YYYY-MM-DD HH24:MI:SS.FF';
ALTER SESSION SET NLS_TIMESTAMP_TZ_FORMAT='YYYY-MM-DD HH24:MI:SS.FF TZH:TZM';

-- ---------------------------------------------------------------------------
-- Type-coverage table
-- ---------------------------------------------------------------------------
CREATE TABLE type_matrix (
    id                       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    c_number                 NUMBER,
    c_number_ps              NUMBER(12, 4),
    c_binary_float           BINARY_FLOAT,
    c_binary_double          BINARY_DOUBLE,
    c_char                   CHAR(8),
    c_nchar                  NCHAR(8),
    c_varchar2               VARCHAR2(64),
    c_nvarchar2              NVARCHAR2(64),
    c_clob                   CLOB,
    c_nclob                  NCLOB,
    c_blob                   BLOB,
    c_raw                    RAW(16),
    c_date                   DATE,
    c_timestamp              TIMESTAMP,
    c_timestamp_tz           TIMESTAMP WITH TIME ZONE,
    c_timestamp_ltz          TIMESTAMP WITH LOCAL TIME ZONE,
    c_xml                    XMLTYPE
);

-- ---------------------------------------------------------------------------
-- LONG must live alone (Oracle restriction: max 1 LONG per table)
-- ---------------------------------------------------------------------------
CREATE TABLE type_long (
    id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload    LONG
);

-- ---------------------------------------------------------------------------
-- Relational mini-fixture (parallels the sqlite/mssql one)
-- ---------------------------------------------------------------------------
CREATE TABLE author (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR2(120) NOT NULL,
    birth_year  NUMBER(4) NULL
);

CREATE TABLE book (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    author_id   NUMBER NOT NULL,
    title       VARCHAR2(200) NOT NULL,
    CONSTRAINT fk_book_author FOREIGN KEY (author_id) REFERENCES author (id)
);

CREATE INDEX idx_book_title ON book (title);

-- ---------------------------------------------------------------------------
-- Representative payload (one populated row + one all-NULL row)
-- ---------------------------------------------------------------------------
INSERT INTO type_matrix (
    c_number, c_number_ps, c_binary_float, c_binary_double,
    c_char, c_nchar, c_varchar2, c_nvarchar2,
    c_clob, c_nclob, c_blob, c_raw,
    c_date, c_timestamp, c_timestamp_tz, c_timestamp_ltz,
    c_xml
) VALUES (
    42, 1234.5678, 1.5, 3.141592653589793,
    'fixed', 'fixé', 'with accent é', 'Unicode ✓',
    'long clob payload', 'long nclob payload',
    HEXTORAW('DEADBEEFCAFEBABE'), HEXTORAW('01020304'),
    DATE '2024-01-31',
    TIMESTAMP '2024-01-31 14:30:00.123456',
    TIMESTAMP '2024-01-31 14:30:00.123 +01:00',
    TIMESTAMP '2024-01-31 14:30:00.123',
    XMLTYPE('<root><k>v</k></root>')
);

INSERT INTO type_matrix (
    c_number, c_number_ps, c_binary_float, c_binary_double,
    c_char, c_nchar, c_varchar2, c_nvarchar2,
    c_clob, c_nclob, c_blob, c_raw,
    c_date, c_timestamp, c_timestamp_tz, c_timestamp_ltz,
    c_xml
) VALUES (
    NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL,
    NULL
);

INSERT INTO type_long (payload) VALUES ('a LONG value');

INSERT INTO author (name, birth_year) VALUES ('Alice', 1980);
INSERT INTO author (name, birth_year) VALUES ('Bob', NULL);

INSERT INTO book (author_id, title) VALUES (1, 'First');
INSERT INTO book (author_id, title) VALUES (1, 'Second''s ride');
INSERT INTO book (author_id, title) VALUES (2, 'Bob book');

COMMIT;
