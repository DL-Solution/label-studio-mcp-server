#!/usr/bin/env python3
"""Bump the project version in manifest.json and pyproject.toml together.

The version lives in two files that must stay in sync:
  - manifest.json  ("version", semver — drives the .mcpb bundle / Claude Desktop)
  - pyproject.toml (version = "...", the Python package version)

Usage:
    python scripts/bump_version.py patch        # 0.1.0 -> 0.1.1
    python scripts/bump_version.py minor        # 0.1.3 -> 0.2.0
    python scripts/bump_version.py major        # 0.2.5 -> 1.0.0
    python scripts/bump_version.py 1.4.2        # set an explicit X.Y.Z
    python scripts/bump_version.py --show       # print current version, no change

Keeping the manifest 'name'/'author' stable while bumping 'version' is what lets
Claude Desktop recognise a new .mcpb as an in-place update and preserve settings.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest.json"
PYPROJECT = ROOT / "pyproject.toml"

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def read_manifest_version() -> str:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return data["version"]


def read_pyproject_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', text)
    if not m:
        raise SystemExit("ERROR: could not find version in pyproject.toml")
    return m.group(1)


def compute(current: str, bump: str) -> str:
    if SEMVER_RE.match(bump):
        return bump  # explicit version
    m = SEMVER_RE.match(current)
    if not m:
        raise SystemExit(f"ERROR: current version {current!r} is not X.Y.Z")
    major, minor, patch = (int(x) for x in m.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise SystemExit(f"ERROR: unknown bump {bump!r} (use major|minor|patch|X.Y.Z)")


def write_manifest(version: str) -> None:
    # Preserve formatting: replace only the version value.
    text = MANIFEST.read_text(encoding="utf-8")
    new, n = re.subn(r'("version"\s*:\s*)"[^"]+"', rf'\g<1>"{version}"', text, count=1)
    if n != 1:
        raise SystemExit("ERROR: could not update version in manifest.json")
    MANIFEST.write_text(new, encoding="utf-8")


def write_pyproject(version: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    new, n = re.subn(r'(?m)^(\s*version\s*=\s*)"[^"]+"', rf'\g<1>"{version}"', text, count=1)
    if n != 1:
        raise SystemExit("ERROR: could not update version in pyproject.toml")
    PYPROJECT.write_text(new, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump manifest.json + pyproject.toml version.")
    parser.add_argument(
        "bump",
        nargs="?",
        default="patch",
        help="major | minor | patch | explicit X.Y.Z (default: patch)",
    )
    parser.add_argument("--show", action="store_true", help="print current version and exit")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify manifest.json and pyproject.toml agree; exit 1 on drift",
    )
    args = parser.parse_args()

    manifest_v = read_manifest_version()
    pyproject_v = read_pyproject_version()

    if args.check:
        if manifest_v != pyproject_v:
            print(
                f"Version drift: manifest.json={manifest_v} pyproject.toml={pyproject_v}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        print(f"OK: {manifest_v}")
        return

    if manifest_v != pyproject_v:
        print(
            f"WARNING: versions differ — manifest.json={manifest_v} pyproject.toml={pyproject_v}",
            file=sys.stderr,
        )

    if args.show:
        print(manifest_v)
        return

    new_version = compute(manifest_v, args.bump)
    write_manifest(new_version)
    write_pyproject(new_version)
    print(f"{manifest_v} -> {new_version}")
    print("Updated manifest.json and pyproject.toml. Run `uv lock` if dependencies changed.")


if __name__ == "__main__":
    main()
