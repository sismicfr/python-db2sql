-- Functional-test fixture for MSSQL.
-- Covers every source type referenced by
-- db2sql/infrastructure/emit/postgres/emitter.py:DEFAULT_TYPE_MAP that exists
-- in MSSQL, plus a few structural features (identity, computed column,
-- foreign key, secondary index).

IF DB_ID('db2sqltest') IS NULL
BEGIN
    CREATE DATABASE db2sqltest;
END;
GO

USE db2sqltest;
GO

IF SCHEMA_ID('apptest') IS NULL EXEC('CREATE SCHEMA apptest');
GO

IF OBJECT_ID('apptest.book', 'U') IS NOT NULL DROP TABLE apptest.book;
IF OBJECT_ID('apptest.author', 'U') IS NOT NULL DROP TABLE apptest.author;
IF OBJECT_ID('apptest.type_matrix', 'U') IS NOT NULL DROP TABLE apptest.type_matrix;
IF OBJECT_ID('apptest.default_matrix', 'U') IS NOT NULL DROP TABLE apptest.default_matrix;
GO

-- Type-coverage table -------------------------------------------------------
CREATE TABLE apptest.type_matrix (
    id                   INT IDENTITY(1,1) PRIMARY KEY,
    c_bit                BIT             NULL,
    c_tinyint            TINYINT         NULL,
    c_smallint           SMALLINT        NULL,
    c_int                INT             NULL,
    c_bigint             BIGINT          NULL,
    c_real               REAL            NULL,
    c_float              FLOAT           NULL,
    c_decimal            DECIMAL(12, 4)  NULL,
    c_numeric            NUMERIC(18, 6)  NULL,
    c_money              MONEY           NULL,
    c_smallmoney         SMALLMONEY      NULL,
    c_char               CHAR(8)         NULL,
    c_nchar              NCHAR(8)        NULL,
    c_varchar            VARCHAR(64)     NULL,
    c_nvarchar           NVARCHAR(64)    NULL,
    c_text               TEXT            NULL,
    c_ntext              NTEXT           NULL,
    c_binary             BINARY(8)       NULL,
    c_varbinary          VARBINARY(MAX)  NULL,
    c_image              IMAGE           NULL,
    c_date               DATE            NULL,
    c_time               TIME            NULL,
    c_datetime           DATETIME        NULL,
    c_datetime2          DATETIME2       NULL,
    c_smalldatetime      SMALLDATETIME   NULL,
    c_datetimeoffset     DATETIMEOFFSET  NULL,
    c_uniqueidentifier   UNIQUEIDENTIFIER NULL,
    c_xml                XML             NULL,
    computed_full        AS (c_varchar + N' / ' + c_nvarchar)
);
GO

-- Default-value coverage table -------------------------------------------
-- Every column exercises a DEFAULT expression that the postgres emitter is
-- expected to translate (functions, bare keywords, literals, booleans).
CREATE TABLE apptest.default_matrix (
    id                   INT IDENTITY(1,1) PRIMARY KEY,
    d_getdate            DATETIME         NOT NULL DEFAULT GETDATE(),
    d_sysdatetime        DATETIME2        NOT NULL DEFAULT SYSDATETIME(),
    d_getutcdate         DATETIME         NOT NULL DEFAULT GETUTCDATE(),
    d_sysutcdatetime     DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    d_sysdatetimeoffset  DATETIMEOFFSET   NOT NULL DEFAULT SYSDATETIMEOFFSET(),
    d_current_timestamp  DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    d_newid              UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    d_newsequentialid    UNIQUEIDENTIFIER NOT NULL DEFAULT NEWSEQUENTIALID(),
    d_suser_sname        NVARCHAR(128)    NOT NULL DEFAULT SUSER_SNAME(),
    d_system_user        NVARCHAR(128)    NOT NULL DEFAULT SYSTEM_USER,
    d_user_name          NVARCHAR(128)    NOT NULL DEFAULT USER_NAME(),
    d_db_name            NVARCHAR(128)    NOT NULL DEFAULT DB_NAME(),
    d_bit_true           BIT              NOT NULL DEFAULT 1,
    d_bit_false          BIT              NOT NULL DEFAULT 0,
    d_int_literal        INT              NOT NULL DEFAULT 42,
    d_string_literal     NVARCHAR(32)     NOT NULL DEFAULT N'hello'
);
GO

-- Relational mini-fixture (parallels the sqlite fixture in tests/conftest.py)
CREATE TABLE apptest.author (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    name        NVARCHAR(120) NOT NULL,
    birth_year  INT NULL
);
GO

CREATE TABLE apptest.book (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    author_id   INT NOT NULL,
    title       NVARCHAR(200) NOT NULL,
    CONSTRAINT fk_book_author FOREIGN KEY (author_id) REFERENCES apptest.author (id)
);
GO

CREATE INDEX idx_book_title ON apptest.book (title);
GO

-- Representative payload
INSERT INTO apptest.type_matrix
    (c_bit, c_tinyint, c_smallint, c_int, c_bigint,
     c_real, c_float, c_decimal, c_numeric, c_money, c_smallmoney,
     c_char, c_nchar, c_varchar, c_nvarchar, c_text, c_ntext,
     c_binary, c_varbinary, c_image,
     c_date, c_time, c_datetime, c_datetime2, c_smalldatetime, c_datetimeoffset,
     c_uniqueidentifier, c_xml)
VALUES
    (1, 7, 32100, 2147483640, 9000000000000000000,
     1.5, 3.141592653589793, 1234.5678, 1234567.890123, 19.95, 1.50,
     'fixed', N'fixé', 'with accent é', N'Unicode ✓', 'long text payload', N'long ntext payload',
     CONVERT(BINARY(8), 0xDEADBEEFCAFEBABE), CONVERT(VARBINARY(MAX), 0x01020304), CONVERT(IMAGE, 0x05060708),
     '2024-01-31', '14:30:00', '2024-01-31T14:30:00', '2024-01-31T14:30:00.1234567', '2024-01-31T14:30:00',
     '2024-01-31T14:30:00+01:00',
     '11111111-2222-3333-4444-555555555555',
     CONVERT(XML, '<root><k>v</k></root>')),
    (NULL, NULL, NULL, NULL, NULL,
     NULL, NULL, NULL, NULL, NULL, NULL,
     NULL, NULL, NULL, NULL, NULL, NULL,
     NULL, NULL, NULL,
     NULL, NULL, NULL, NULL, NULL, NULL,
     NULL, NULL);
GO

INSERT INTO apptest.author (name, birth_year) VALUES (N'Alice', 1980);
INSERT INTO apptest.author (name, birth_year) VALUES (N'Bob', NULL);
GO

INSERT INTO apptest.book (author_id, title) VALUES (1, N'First');
INSERT INTO apptest.book (author_id, title) VALUES (1, N'Second''s ride');
INSERT INTO apptest.book (author_id, title) VALUES (2, N'Bob book');
GO
