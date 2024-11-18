Application
===========

Use cases and port interfaces.  This layer depends only on the
:doc:`domain` and defines abstract ports that infrastructure adapters must
implement.

DTOs
----

.. automodule:: db2sql.application.dto.data_format
   :members:

.. automodule:: db2sql.application.dto.dump_request
   :members:

.. automodule:: db2sql.application.dto.migrate_request
   :members:

Ports
-----

.. automodule:: db2sql.application.ports.source_reader
   :members:

.. automodule:: db2sql.application.ports.sql_emitter
   :members:

.. automodule:: db2sql.application.ports.target_writer
   :members:

.. automodule:: db2sql.application.ports.output_sink
   :members:

.. automodule:: db2sql.application.ports.logger
   :members:

Use Cases
---------

.. automodule:: db2sql.application.use_cases.dump_database
   :members:

.. automodule:: db2sql.application.use_cases.migrate_database
   :members:

.. automodule:: db2sql.application.use_cases.materialize_views
   :members:
