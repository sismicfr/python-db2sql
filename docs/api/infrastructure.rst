Infrastructure
==============

Concrete adapters that implement the application ports.

Configuration
-------------

.. automodule:: db2sql.infrastructure.config.schema
   :members:

.. automodule:: db2sql.infrastructure.config.loader
   :members:

.. automodule:: db2sql.infrastructure.config.mapper
   :members:

.. automodule:: db2sql.infrastructure.config.errors
   :members:

Persistence (source readers)
-----------------------------

.. automodule:: db2sql.infrastructure.persistence.sqlite.reader
   :members:

.. automodule:: db2sql.infrastructure.persistence.mysql.reader
   :members:

.. automodule:: db2sql.infrastructure.persistence.mssql.reader
   :members:

.. automodule:: db2sql.infrastructure.persistence.postgres.reader
   :members:

.. automodule:: db2sql.infrastructure.persistence.oracle.reader
   :members:

.. automodule:: db2sql.infrastructure.persistence.errors
   :members:

SQL Emitter
-----------

.. automodule:: db2sql.infrastructure.emit.postgres.emitter
   :members:

.. automodule:: db2sql.infrastructure.emit.mssql.emitter
   :members:

Target writers (live migration)
-------------------------------

.. automodule:: db2sql.infrastructure.writer.postgres.writer
   :members:

.. automodule:: db2sql.infrastructure.writer.mssql.writer
   :members:

.. automodule:: db2sql.infrastructure.writer.errors
   :members:

Output
------

.. automodule:: db2sql.infrastructure.output.stream_sink
   :members:

.. automodule:: db2sql.infrastructure.output.executing_sink
   :members:

Logging
-------

.. automodule:: db2sql.infrastructure.logging.console_logger
   :members:

.. automodule:: db2sql.infrastructure.logging.colors
   :members:

Plugins
-------

.. automodule:: db2sql.infrastructure.plugins.registry
   :members:
