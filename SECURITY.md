# Security Policy

## Supported Versions

`python-db2sql` follows semantic versioning. Security fixes are applied to the
latest minor release of the current major version. Older majors are not
maintained — please upgrade to receive security patches.

| Version | Supported |
| ------- | --------- |
| 1.x     | ✅        |
| < 1.0   | ❌        |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

To report a vulnerability, use one of the following private channels:

- **Preferred — GitHub private vulnerability reporting**: open a draft advisory
  via the repository's [Security tab](https://github.com/sismicfr/python-db2sql/security/advisories/new).
  This keeps the discussion private until a fix is published.
- **Email**: `jraphanel@sismic.fr` — encrypt with PGP if you have sensitive
  payloads to share.

When reporting, please include:

1. A description of the vulnerability and its potential impact.
2. Steps to reproduce, including a minimal proof-of-concept if possible.
3. The version(s) of `python-db2sql` affected.
4. Any suggested mitigation, if you have one.

## What to Expect

- **Acknowledgement** within 5 business days.
- **Triage and impact assessment** within 10 business days.
- **Fix and coordinated disclosure**: we will work with you on a disclosure
  timeline. Typical target is 30–90 days from the initial report depending on
  severity and the complexity of the fix.
- **Credit**: with your consent, we will credit you in the release notes and
  the GitHub security advisory.

## Scope

In scope:

- The `db2sql` Python package and its CLI.
- The built-in reader, emitter and writer adapters shipped in this repository.
- The configuration loader and schema validation.

Out of scope:

- Vulnerabilities in third-party plugins distributed outside this repository.
- Vulnerabilities in the source or target database engines themselves.
- Issues that require an attacker to already control the host system, the
  Python interpreter, or the database credentials passed to the tool.

Thank you for helping keep `python-db2sql` and its users safe.
