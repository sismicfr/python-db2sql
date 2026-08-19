# Standalone builds

This folder contains everything needed to produce a self-contained
`db2sql` executable with [PyInstaller]. The resulting binary embeds
the Python interpreter and every dependency, so it can be shipped on a
machine where Python is not installed.

PyInstaller does **not** cross-build: you must run the build on the same
operating system and CPU architecture as the target. On Linux the binary
is additionally tied to the build host’s glibc version — use the
docker-based build (see below) to guarantee Debian 12 compatibility.

| Host                          | Output archive                                |
|-------------------------------|-----------------------------------------------|
| Windows x86_64                | `db2sql-<version>-windows-x86_64.zip`         |
| Linux x86_64                  | `db2sql-<version>-linux-x86_64.tar.gz`        |
| Linux aarch64                 | `db2sql-<version>-linux-aarch64.tar.gz`       |
| macOS arm64 (Apple Silicon)   | `db2sql-<version>-macos-arm64.tar.gz`         |
| macOS x86_64 (Intel)          | `db2sql-<version>-macos-x86_64.tar.gz`        |

Archives land in `installer/dist/` alongside the raw binary.

## Layout

```
installer/
├── build.py                # main entry point (cross-platform)
├── db2sql.spec             # advanced PyInstaller spec (optional)
├── build-linux.sh          # host-Python wrapper for Linux
├── build-linux-docker.sh   # Debian-12-compatible Linux build via docker
├── build-macos.sh          # wrapper for macOS arm64 / x86_64
├── build-windows.ps1       # wrapper for Windows (PowerShell)
├── build-windows.bat       # cmd.exe entry that forwards to the .ps1 script
└── sql.ico                 # icon embedded into the Windows binary
```

## Quick start

The wrapper scripts create an isolated virtual environment under
`installer/.venv-build`, install the project with every optional driver
(`pip install -e ".[all]"`) plus PyInstaller, then call `build.py
--archive`.

### Linux

Two variants are available:

* **`build-linux.sh`** uses the Python interpreter on the host. The binary
  is tied to the host’s glibc version — fine for builds you intend to run
  on the same machine, **not portable** between distros.
* **`build-linux-docker.sh`** runs the same pipeline inside the
  `python:3.12-bookworm` image (Debian 12). The resulting binary links
  against glibc 2.36, so it runs on **Debian 12+, Ubuntu 22.10+,
  RHEL/Rocky 9, Fedora 37+** and any newer GNU/Linux distribution. This
  matches what the CI release workflow produces.

```bash
# Host-Python build (not portable across distros)
./installer/build-linux.sh
PYTHON=python3.12 ./installer/build-linux.sh   # pick a specific interpreter

# Debian-12-compatible build via docker (recommended for releases)
./installer/build-linux-docker.sh
IMAGE=python:3.11-bookworm ./installer/build-linux-docker.sh    # other Python
PLATFORM=linux/arm64 ./installer/build-linux-docker.sh          # cross-arch via binfmt
```

### macOS (arm64 or x86_64)

```bash
./installer/build-macos.sh
```

To explicitly target Apple Silicon from a universal shell, prefix with
`arch -arm64`:

```bash
arch -arm64 ./installer/build-macos.sh
```

### Windows

PowerShell (recommended):

```powershell
powershell -ExecutionPolicy Bypass -File installer/build-windows.ps1
```

cmd.exe:

```cmd
installer\build-windows.bat
```

## Calling `build.py` directly

If you already have an environment with the project installed
(`pip install -e ".[all]" pyinstaller`), you can skip the wrappers:

```bash
python installer/build.py            # single-file binary, no archive
python installer/build.py --archive  # also produce the release archive
python installer/build.py --onedir   # produce a folder bundle instead
python installer/build.py --upx      # enable UPX compression (UPX on PATH)
python installer/build.py --no-clean # reuse the existing build/dist trees
```

When run inside a GitHub Actions job (`GITHUB_ACTIONS=true`), `build.py`
archives the binary automatically — you do not need `--archive` there.

## Optional database drivers

`build.py` bundles whichever optional driver wheels are present in the
build environment. The wrapper scripts install `db2sql[all]`, so by
default the binary supports MSSQL, MySQL, PostgreSQL and Oracle. To
build a slimmer binary, install only the extras you want:

```bash
pip install -e ".[mssql,postgres]" pyinstaller
python installer/build.py
```

Drivers that reach their dependencies from compiled extension modules need
those dependencies collected explicitly — PyInstaller only analyses Python
bytecode, so imports made from a `.so`/`.pyd` are invisible to it. These are
listed in `DRIVER_HIDDEN_PACKAGES` in `build.py`: Oracle's thin mode
(`oracledb.thin_impl`, a compiled Cython module) imports `cryptography`, and
without it the binary fails at connection time with *“python-oracledb thin
mode cannot be used because the cryptography package cannot be imported”*.
The build aborts if such a companion package is missing from the environment.

## Spec file (advanced)

For tweaks that don’t fit `build.py`’s flags (custom hooks, code signing,
extra hidden imports), use the spec file:

```bash
pyinstaller installer/db2sql.spec
```

[PyInstaller]: https://pyinstaller.org/
