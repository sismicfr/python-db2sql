API Reference
=============

``db2sql`` follows a clean-architecture layout.  The top-level package is
``db2sql`` and contains four sub-packages:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Sub-package
     - Role
   * - :doc:`domain`
     - Core business entities and pure policies (no I/O, no framework deps).
   * - :doc:`application`
     - Use cases and port interfaces (depends only on ``domain``).
   * - :doc:`infrastructure`
     - Adapters: database readers, config loading, SQL emitter, logging.
   * - :doc:`interface`
     - Entry points: CLI parser and runner.

.. toctree::
   :maxdepth: 2

   domain
   application
   infrastructure
   interface
