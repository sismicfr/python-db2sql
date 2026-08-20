-- Functional-test fixture for MySQL.
--
-- The MySQLSourceReader uses the connection's database as the "schema"
-- (MySQL has no notion of schema separate from database), so all fixtures
-- live in the ``db2sqltest`` database created from MYSQL_DATABASE.
--
-- Coverage: every MySQL source type referenced by
-- ``PostgresSqlEmitter.DEFAULT_TYPE_MAP`` that is native to MySQL, plus the
-- standard relational fixture (author/book + foreign key + secondary index).

CREATE DATABASE IF NOT EXISTS db2sqltest;
USE db2sqltest;

DROP TABLE IF EXISTS book;
DROP TABLE IF EXISTS author;
DROP TABLE IF EXISTS type_matrix;

-- Type-coverage table -------------------------------------------------------
CREATE TABLE type_matrix (
    id              INT NOT NULL AUTO_INCREMENT,
    c_bit           BIT(1)        NULL,
    c_tinyint       TINYINT       NULL,
    c_smallint      SMALLINT      NULL,
    c_mediumint     MEDIUMINT     NULL,
    c_int           INT           NULL,
    c_bigint        BIGINT        NULL,
    c_decimal       DECIMAL(12,4) NULL,
    c_numeric       NUMERIC(18,6) NULL,
    c_float         FLOAT         NULL,
    c_double        DOUBLE        NULL,
    c_char          CHAR(8)       NULL,
    c_varchar       VARCHAR(64)   NULL,
    c_text          TEXT          NULL,
    c_mediumtext    MEDIUMTEXT    NULL,
    c_longtext      LONGTEXT      NULL,
    c_binary        BINARY(8)     NULL,
    c_varbinary     VARBINARY(64) NULL,
    c_blob          BLOB          NULL,
    c_date          DATE          NULL,
    c_time          TIME          NULL,
    c_datetime      DATETIME      NULL,
    c_timestamp     TIMESTAMP     NULL DEFAULT NULL,
    c_json          JSON          NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Relational mini-fixture (parallels mssql/oracle/postgres fixtures)
CREATE TABLE author (
    id          INT NOT NULL AUTO_INCREMENT,
    name        VARCHAR(120) NOT NULL,
    birth_year  INT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE book (
    id          INT NOT NULL AUTO_INCREMENT,
    author_id   INT NOT NULL,
    title       VARCHAR(200) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_book_author FOREIGN KEY (author_id) REFERENCES author (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_book_title ON book (title);

-- Composite primary key + composite foreign key: the reader must keep the two
-- columns in one constraint, otherwise each half points at a non-unique key.
CREATE TABLE assembly (
    id      INT NOT NULL,
    cetat   CHAR(1) NOT NULL,
    label   VARCHAR(50),
    PRIMARY KEY (id, cetat)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE assembly_vote (
    id           INT NOT NULL AUTO_INCREMENT,
    assembly_id  INT NOT NULL,
    cetat        CHAR(1) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_vote_assembly FOREIGN KEY (assembly_id, cetat)
        REFERENCES assembly (id, cetat)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Representative payload (one populated row + one all-NULL row)
INSERT INTO type_matrix
    (c_bit, c_tinyint, c_smallint, c_mediumint, c_int, c_bigint,
     c_decimal, c_numeric, c_float, c_double,
     c_char, c_varchar, c_text, c_mediumtext, c_longtext,
     c_binary, c_varbinary, c_blob,
     c_date, c_time, c_datetime, c_timestamp, c_json)
VALUES
    (b'1', 7, 32100, 8388600, 2147483640, 9000000000000000000,
     1234.5678, 1234567.890123, 1.5, 3.141592653589793,
     'fixed', 'with accent é', 'long text payload', 'medium text', 'long text',
     UNHEX('DEADBEEFCAFEBABE'), UNHEX('01020304'), UNHEX('05060708'),
     '2024-01-31', '14:30:00', '2024-01-31 14:30:00',
     '2024-01-31 14:30:00', JSON_OBJECT('k', 'v')),
    (NULL, NULL, NULL, NULL, NULL, NULL,
     NULL, NULL, NULL, NULL,
     NULL, NULL, NULL, NULL, NULL,
     NULL, NULL, NULL,
     NULL, NULL, NULL, NULL, NULL);

INSERT INTO author (name, birth_year) VALUES ('Alice', 1980);
INSERT INTO author (name, birth_year) VALUES ('Bob', NULL);

INSERT INTO book (author_id, title) VALUES (1, 'First');
INSERT INTO book (author_id, title) VALUES (1, 'Second\'s ride');
INSERT INTO book (author_id, title) VALUES (2, 'Bob book');

INSERT INTO assembly (id, cetat, label) VALUES (1, 'O', 'AG 2024');
INSERT INTO assembly_vote (assembly_id, cetat) VALUES (1, 'O');
