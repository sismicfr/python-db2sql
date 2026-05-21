#!/usr/bin/env python3
"""Build a standalone db2sql executable with PyInstaller.

The resulting binary embeds the Python interpreter and all dependencies, so
it can be shipped on a machine where Python is not installed.

PyInstaller does not cross-build: this script must be executed on the same
operating system / CPU architecture the binary is going to run on. The
supported targets are:

* Windows x86_64       -> ``db2sql-<version>-windows-x86_64.zip``
* Linux x86_64         -> ``db2sql-<version>-linux-x86_64.tar.gz``
* Linux aarch64        -> ``db2sql-<version>-linux-aarch64.tar.gz``
* macOS arm64 (Apple)  -> ``db2sql-<version>-macos-arm64.tar.gz``
* macOS x86_64 (Intel) -> ``db2sql-<version>-macos-x86_64.tar.gz``

Before running this script, install the project in the active environment::

    pip install -e ".[all]" pyinstaller
    python installer/build.py

The companion shell scripts (``build-linux.sh``, ``build-macos.sh``,
``build-windows.ps1``) take care of creating an isolated virtual environment
and invoking this module — prefer them for clean builds.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Optional
from zipfile import ZIP_DEFLATED, ZipFile

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parent
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from db2sql import __version__  # noqa: E402  pylint: disable=wrong-import-position

EXE_NAME = "db2sql"
DIST_NAME = "python_db2sql"

# Optional driver import names declared in pyproject.toml extras. They are
# picked up automatically when installed in the build environment so the
# resulting binary can talk to the corresponding databases. The distribution
# name (used by ``--copy-metadata``) is resolved at build time via
# :func:`_resolve_dist_name` — required because ``psycopg2-binary`` ships the
# ``psycopg2`` module under a different distribution name.
OPTIONAL_DRIVERS = ("pymssql", "pymysql", "psycopg2", "oracledb")


def _is_module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _resolve_dist_name(module_name: str) -> Optional[str]:
    """Return the installed distribution providing ``module_name``, or ``None``.

    Tries the module name itself first (covers the common case where module
    and distribution names match), then falls back to
    :func:`importlib.metadata.packages_distributions` to handle wheels whose
    distribution name differs from the importable module (e.g. ``psycopg2``
    is provided by the ``psycopg2-binary`` distribution).
    """
    try:
        return importlib.metadata.distribution(module_name).metadata["Name"]
    except importlib.metadata.PackageNotFoundError:
        pass
    try:
        mapping = importlib.metadata.packages_distributions()
    except Exception:  # noqa: BLE001 — best effort
        return None
    dists = mapping.get(module_name)
    return dists[0] if dists else None


def _platform_tag() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        return f"macos-{'arm64' if machine in ('arm64', 'aarch64') else 'x86_64'}"
    if system == "windows":
        return f"windows-{'arm64' if machine in ('arm64', 'aarch64') else 'x86_64'}"
    if system == "linux":
        if machine in ("aarch64", "arm64"):
            return "linux-aarch64"
        if machine in ("x86_64", "amd64"):
            return "linux-x86_64"
        return f"linux-{machine}"
    return f"{system}-{machine}"


def _executable_name() -> str:
    return f"{EXE_NAME}.exe" if platform.system() == "Windows" else EXE_NAME


def _is_github_action() -> bool:
    return os.environ.get("GITHUB_ACTIONS") is not None


def _windows_version_file(version: str) -> str:
    template = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'000004b0',
        [StringStruct(u'Comments', u'Created with PyInstaller'),
         StringStruct(u'CompanyName', u'SISMIC'),
         StringStruct(u'FileDescription', u'Dump any supported source database to PostgreSQL through a SQL file'),
         StringStruct(u'FileVersion', u'{version}'),
         StringStruct(u'LegalCopyright', u'Copyright 2024 SISMIC'),
         StringStruct(u'ProductName', u'db2sql'),
         StringStruct(u'ProductVersion', u'{version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [0, 1200])])
  ]
)
"""
    base_version = version.split("-", 1)[0].split("+", 1)[0]
    parts = [int(p) for p in base_version.split(".")[:4]]
    while len(parts) < 4:
        parts.append(0)
    return template.format(version=base_version, version_tuple=tuple(parts))


def _run_pyinstaller(args: list[str], env: dict[str, str]) -> None:
    cmd = [sys.executable, "-m", "PyInstaller", *args]
    print("->", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)


def _smoke_test(binary: Path) -> None:
    print(f"-> smoke test: {binary} --version", flush=True)
    completed = subprocess.run(
        [str(binary), "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(f"binary smoke test failed (exit code {completed.returncode})")
    print(completed.stdout.strip() or completed.stderr.strip(), flush=True)


def _archive(binary: Path, archive_stem: str) -> Path:
    parent = binary.parent
    if platform.system() == "Windows":
        archive_path = parent / f"{archive_stem}.zip"
        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as zf:
            zf.write(binary, arcname=binary.name)
    else:
        archive_path = parent / f"{archive_stem}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(binary, arcname=binary.name)
    return archive_path


def build(
    *,
    source_root: Path = SOURCE_ROOT,
    work_dir: Path = HERE,
    one_file: bool = True,
    upx: bool = False,
    archive: bool | None = None,
    clean: bool = True,
) -> Path:
    """Run PyInstaller and produce a standalone db2sql binary.

    Returns the path to the produced binary.
    """
    build_dir = work_dir / "_build"
    dist_dir = work_dir / "dist"

    if clean:
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(dist_dir, ignore_errors=True)
    build_dir.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)

    entry_point = source_root / "db2sql" / "__main__.py"
    if not entry_point.exists():
        raise SystemExit(f"entry point not found: {entry_point}")

    args: list[str] = [
        "-y",
        "--noconfirm",
        "--name",
        EXE_NAME,
        "--console",
        "--paths",
        str(source_root),
        "--workpath",
        str(build_dir),
        "--distpath",
        str(dist_dir),
        "--specpath",
        str(build_dir),
    ]
    if one_file:
        args.append("--onefile")
    else:
        args.append("--onedir")
    if not upx:
        args.append("--noupx")

    # Plugin discovery: db2sql relies on importlib.metadata entry-points
    # declared in pyproject.toml. PyInstaller can't see those by static
    # analysis, so we copy the package metadata and collect every submodule.
    args.extend(["--copy-metadata", DIST_NAME])
    args.extend(["--collect-submodules", "db2sql"])

    # Optional database drivers — bundle whichever ones are installed in the
    # current environment. Skip the rest so the binary stays small on hosts
    # that don't have them (e.g. a Linux build without oracledb).
    for module_name in OPTIONAL_DRIVERS:
        if not _is_module_available(module_name):
            continue
        args.extend(["--collect-submodules", module_name])
        dist_name = _resolve_dist_name(module_name)
        if dist_name is not None:
            args.extend(["--copy-metadata", dist_name])

    if platform.system() == "Windows":
        version_file = build_dir / "windows-version-file.txt"
        version_file.write_text(_windows_version_file(__version__), encoding="utf-8")
        icon_file = HERE / "sql.ico"
        args.extend(["--version-file", str(version_file)])
        if icon_file.exists():
            args.extend(["--icon", str(icon_file)])

    args.append(str(entry_point))

    env = os.environ.copy()
    # Make sure the source tree is importable during PyInstaller analysis.
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{source_root}{os.pathsep}{existing_pp}" if existing_pp else str(source_root)
    )

    _run_pyinstaller(args, env)

    binary = dist_dir / _executable_name()
    if not binary.exists():
        candidate = dist_dir / EXE_NAME / _executable_name()
        if candidate.exists():
            binary = candidate
    if not binary.exists():
        raise SystemExit(f"PyInstaller did not produce the expected binary at {binary}")

    _smoke_test(binary)

    should_archive = archive if archive is not None else _is_github_action()
    if should_archive:
        archive_stem = f"{EXE_NAME}-{__version__}-{_platform_tag()}"
        archive_path = _archive(binary, archive_stem)
        print(f"-> archived: {archive_path}", flush=True)

    return binary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a standalone db2sql binary.")
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="produce a directory bundle instead of a single executable",
    )
    parser.add_argument(
        "--upx",
        action="store_true",
        help="enable UPX compression (UPX must be installed and on PATH)",
    )
    archive_group = parser.add_mutually_exclusive_group()
    archive_group.add_argument(
        "--archive",
        dest="archive",
        action="store_true",
        help="always produce a release archive (zip/tar.gz)",
    )
    archive_group.add_argument(
        "--no-archive",
        dest="archive",
        action="store_false",
        help="never produce a release archive",
    )
    parser.set_defaults(archive=None)
    parser.add_argument(
        "--no-clean",
        dest="clean",
        action="store_false",
        help="reuse the existing build/dist directories",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    binary = build(
        one_file=not args.onedir,
        upx=args.upx,
        archive=args.archive,
        clean=args.clean,
    )
    print(
        "\n**************  db2sql executable created!  ******************\n"
        f"\nBinary:   {binary}\n"
        f"Platform: {_platform_tag()}\n"
        f"Version:  {__version__}\n"
        "\nFeel free to copy the binary anywhere on your PATH.\n",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
