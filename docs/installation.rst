Installation
============

Requirements
------------

- Python **3.9** or newer
- ``pip`` 21.3+ (for PEP 660 editable installs, if installing from source)

Installing from PyPI
--------------------

The distribution name on PyPI is ``python-db2sql``; the importable package and
the CLI binary are both called ``db2sql``.

.. code-block:: console

   $ pip install --upgrade python-db2sql

This installs the core package with built-in support for **SQLite** as a
source (via the Python standard library).  To connect to any other database
engine — including PostgreSQL — install the relevant optional extra:

.. list-table::
   :header-rows: 1
   :widths: 20 25 55

   * - Extra
     - Driver
     - Install command
   * - ``mssql``
     - ``pymssql``
     - ``pip install "python-db2sql[mssql]"``
   * - ``mysql``
     - ``pymysql``
     - ``pip install "python-db2sql[mysql]"``
   * - ``oracle``
     - ``oracledb``
     - ``pip install "python-db2sql[oracle]"``
   * - ``postgres``
     - ``psycopg2-binary``
     - ``pip install "python-db2sql[postgres]"``
   * - ``all``
     - all of the above
     - ``pip install "python-db2sql[all]"``

Installing from source
----------------------

.. code-block:: console

   $ git clone https://github.com/sismicfr/python-db2sql.git
   $ cd python-db2sql
   $ pip install -e ".[all]"

Standalone binary
-----------------

For machines without a Python runtime, ``db2sql`` ships build scripts that
produce a self-contained executable via `PyInstaller
<https://pyinstaller.org/>`_.  The resulting binary bundles the interpreter
and every dependency into a single archive per platform:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Host
     - Output archive
   * - Windows x86_64
     - ``db2sql-<version>-windows-x86_64.zip``
   * - Linux x86_64 / aarch64
     - ``db2sql-<version>-linux-<arch>.tar.gz``
   * - macOS arm64 / x86_64
     - ``db2sql-<version>-macos-<arch>.tar.gz``

PyInstaller does **not** cross-build: run the build on the same OS and CPU
architecture as the target.  On Linux a docker-based wrapper is provided to
guarantee Debian 12 (glibc) compatibility.  See
`installer/README.md <https://github.com/sismicfr/python-db2sql/blob/main/installer/README.md>`__
for the per-platform build commands and packaging layout.

Verifying the installation
---------------------------

.. code-block:: console

   $ db2sql --version

You should see the current version printed to ``stdout``.
