db2sql
======

|CI| |PyPI| |Read the Docs| |Coverage| |Python| |Code Style| |Pre-Commit| |License|

``db2sql`` is a Python package providing a command-line utility to move any supported source database (SQLite, MySQL, MSSQL, PostgreSQL, Oracle) into a target dialect — PostgreSQL (default) or Microsoft SQL Server — selectable via ``--target``.

Two output modes are supported:

* ``db2sql dump`` (the default command) — write a SQL file (or stream to ``stdout``) that can later be replayed with ``psql -f`` or ``sqlcmd -i``.
* ``db2sql migrate`` — open a live connection to the target database and apply the same DDL and data directly, without an intermediate file. The DDL produced is byte-identical to dump mode: a single ``SqlEmitter`` is the source of truth in both paths.

Two helper commands round out the CLI: ``db2sql init`` generates a configuration file through an interactive wizard, and ``db2sql validate`` checks one (optionally previewing the export plan) before a long run.

Running ``db2sql`` with dump options but no command is a shorthand for ``db2sql dump`` — both forms are supported and produce identical output.


Installation
------------

``db2sql`` is compatible with Python 3.9+.

Use ``pip`` to install the latest stable version. Note the distribution name on PyPI is ``python-db2sql`` while the importable Python package is ``db2sql`` (same convention as ``python-dateutil``):

.. code-block:: console

   $ pip install --upgrade python-db2sql

After installation, the CLI is available as ``db2sql`` and the importable module as ``db2sql``:

.. code-block:: python

   from db2sql.interface.cli import main

The current development version is available on `GitHub.com
<https://github.com/sismicfr/python-db2sql>`__ and can be installed directly from
the git repository:

.. code-block:: console

   $ pip install git+https://github.com/sismicfr/python-db2sql.git


Live migration mode
-------------------

Stream a source database directly into a live target — same DDL as the file
dump, but without the round-trip through a ``.sql`` file:

.. code-block:: console

   # SQLite source → live Postgres target
   $ db2sql migrate --driver sqlite --dbname mydb.sqlite \
       --target-host localhost --target-port 5432 \
       --target-dbname mytarget --target-user postgres --target-password s3cr3t

The ``migrate`` subcommand uses the ``SqlEmitter`` of the chosen ``--target``
to produce DDL and a dialect-specific ``TargetWriter`` (e.g. ``psycopg2.copy``
for Postgres, batched ``executemany`` for MSSQL) to bulk-load rows. See the
`CLI reference <https://python-db2sql.readthedocs.org/en/stable/cli.html#db2sql-migrate>`__
for all ``--target-*`` flags and migration options (``--on-existing``,
``--transaction-mode``, ``--batch-size``).


Replayable dumps
----------------

By default, the dump emits ``CREATE TABLE`` statements only — replaying the
file against a database that already contains the target tables fails. Pass
``--on-existing drop`` (or set ``dump.on_existing: drop`` in the config) to
prepend a ``DROP TABLE IF EXISTS`` for every table in reverse-dependency
order:

.. code-block:: console

   $ db2sql dump --driver sqlite --dbname mydb.sqlite --on-existing drop -f dump.sql

Pass ``--on-existing truncate`` to produce a *data-only* script: no DDL is
emitted, the dump just ``TRUNCATE``\s every managed table and reloads its
rows. Use it to refresh data into a pre-existing schema:

.. code-block:: console

   $ db2sql dump --driver sqlite --dbname mydb.sqlite --on-existing truncate -f refresh.sql


Validating a configuration
--------------------------

Before launching a long dump, check the configuration file and (optionally)
preview the export plan without producing any SQL:

.. code-block:: console

   # syntax check + plugin name resolution (no DB connection)
   $ db2sql validate db2sql.yml

   # connect to the source and print the plan, no SQL emitted
   $ db2sql validate db2sql.yml --dry-run

   # same plan plus one SELECT COUNT(*) per kept table
   $ db2sql validate db2sql.yml --dry-run --with-counts

See the `CLI reference <https://python-db2sql.readthedocs.org/en/stable/cli.html#db2sql-validate>`__
for full details, exit codes, and the lookup order when the positional
``CONFIG_FILE`` is omitted.


Extensibility
-------------

Beyond the built-in drivers (SQLite, MySQL, MSSQL, PostgreSQL, Oracle) and
targets (PostgreSQL, MSSQL), ``db2sql`` discovers third-party plugins through
three `entry-point <https://packaging.python.org/en/latest/specifications/entry-points/>`__
groups:

* ``db2sql.readers`` — register a new source driver (``--driver``)
* ``db2sql.emitters`` — register a new target dialect for the file dump (``--target``)
* ``db2sql.writers`` — register a new target writer for live migration (used by ``db2sql migrate``)

A step-by-step authoring guide lives in the
`Plugins <https://python-db2sql.readthedocs.org/en/stable/plugins.html>`__
section of the documentation, and three runnable example projects ship under
`examples/ <https://github.com/sismicfr/python-db2sql/tree/main/examples>`__:

* ``examples/csv-producer`` — a custom reader (a directory of CSVs)
* ``examples/sqlite-emitter`` — a custom emitter (SQLite-flavoured SQL)
* ``examples/yaml-to-markdown`` — a single package that ships both a reader
  and an emitter

Each example is a standalone Python distribution: ``cd examples/<name> && pip install -e .``
makes its driver / target immediately usable from the ``db2sql`` CLI.


Bug reports
-----------

Please report bugs and feature requests at
https://github.com/sismicfr/python-db2sql/issues.


Documentation
-------------

The full documentation for CLI and API is available on `readthedocs
<http://python-db2sql.readthedocs.org/en/stable/>`_.

Build the docs
~~~~~~~~~~~~~~

We use ``tox`` to manage our environment and build the documentation::

    pip install tox
    tox -e docs

Contributing
------------

For guidelines for contributing to ``db2sql``, refer to `CONTRIBUTING.rst <https://github.com/sismicfr/python-db2sql/blob/main/CONTRIBUTING.rst>`_.


.. |CI| image:: https://img.shields.io/github/actions/workflow/status/sismicfr/python-db2sql/ci.yml?branch=main&label=CI&logo=github
   :target: https://github.com/sismicfr/python-db2sql/actions/workflows/ci.yml?query=branch%3Amain
   :alt: CI status on main (Python 3.9–3.14 + functional)

.. |PyPI| image:: https://img.shields.io/pypi/v/python-db2sql?label=PyPI&logo=pypi
   :target: https://badge.fury.io/py/python-db2sql
   :alt: PyPI

.. |Read the Docs| image:: https://img.shields.io/readthedocs/python-db2sql?label=Read%20the%20Docs&logo=Read%20the%20Docs
   :target: https://python-db2sql.readthedocs.org/en/latest
   :alt: Docs

.. |Coverage| image:: https://img.shields.io/codecov/c/github/sismicfr/python-db2sql?logo=Codecov&label=Coverage
   :target: https://codecov.io/github/sismicfr/python-db2sql?branch=main
   :alt: Cover

.. |Python| image:: https://img.shields.io/pypi/pyversions/python-db2sql.svg?label=Python&logo=Python
   :target: https://pypi.python.org/pypi/python-db2sql
   :alt: Python

.. |Code Style| image:: https://img.shields.io/badge/code%20style-black-000000.svg?label=Code%20Style
   :target: https://github.com/python/black
   :alt: Code Style

.. |Pre-Commit| image:: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&label=Pre-Commit
   :target: https://github.com/pre-commit/pre-commit
   :alt: Pre-Commit

.. |License| image:: https://img.shields.io/github/license/sismicfr/python-db2sql?label=License
   :target: https://github.com/sismicfr/python-db2sql/blob/main/COPYING
   :alt: License
