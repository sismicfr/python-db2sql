-- Target PostgreSQL database used by functional tests to validate a generated
-- dump. The dump is supposed to be self-sufficient (CREATE SCHEMA + DDL +
-- COPY/INSERT), so this init script only ensures the database exists and is
-- otherwise empty.

-- The database "db2sqltarget" is created from POSTGRES_DB by the entrypoint,
-- so nothing else is strictly required here. We keep the file so the volume
-- mount /docker-entrypoint-initdb.d is non-empty and to host any future
-- preconditioning (extensions, roles, etc.).

SELECT 'postgres target ready' AS status;
