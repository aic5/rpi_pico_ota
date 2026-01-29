#!/usr/bin/env python3
"""
build_ota_manifest.py

Creates a MicroPython app-level OTA manifest for your Pico device.

It:
  1) Walks a local app directory (default: ./app)
  2) Computes SHA-256 for each file
  3) (Optionally) copies those files into a repo "release folder" for raw hosting:
        ./releases/<version>/...
  4) Writes/updates ./ota/manifest.json with:
        - version
        - per-file raw URLs + sha256

This matches the on-device OTA framework we set up:
  - device pulls https://raw.githubusercontent.com/<USER>/<REPO>/main/ota/manifest.json
  - manifest points to raw file URLs + sha256 for each file

Typical repo layout:
  ./app/                   (your "source" app folder)
  ./releases/<ver>/...      (generated, served by raw.githubusercontent.com)
  ./ota/manifest.json       (generated)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple


DEFAULT_EXCLUDES = {
    ".DS_Store",
    "Thumbs.db",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def collect_files(app_dir: Path, excludes: set[str]) -> List[Path]:
    if not app_dir.exists() or not app_dir.is_dir():
        raise FileNotFoundError(f"App dir not found: {app_dir}")

    files: List[Path] = []
    for p in app_dir.rglob("*"):
        if p.is_dir():
            continue
        if p.name in excludes:
            continue
        # Skip hidden files by default (common in repos)
        if p.name.startswith("."):
            continue
        files.append(p)

    # Stable ordering for clean diffs
    files.sort(key=lambda x: str(x).lower())
    return files


def bump_patch(version: str) -> str:
    # Minimal semver bump: X.Y.Z -> X.Y.(Z+1)
    parts = version.strip().split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2])
    except ValueError:
        raise ValueError(f"Version must look like semver (e.g., 0.0.1). Got: {version}")
    return f"{major}.{minor}.{patch + 1}"


def load_existing_version(manifest_path: Path) -> str | None:
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        v = data.get("version")
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass
    return None


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_manifest(manifest_path: Path, manifest: Dict) -> None:
    ensure_parent(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def copy_release_files(app_dir: Path, files: List[Path], release_dir: Path) -> None:
    # release_dir is the root (e.g. ./releases/0.0.2)
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        rel = f.relative_to(app_dir)
        dest = release_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)


def build_manifest_entries(
    app_dir: Path,
    files: List[Path],
    url_base: str,
) -> List[Dict]:
    """
    url_base should point to where the files will be hosted, for example:
      https://raw.githubusercontent.com/<USER>/<REPO>/main/releases/0.0.2

    We will append "/<relative path>" to that base.
    """
    entries: List[Dict] = []
    for f in files:
        rel = f.relative_to(app_dir).as_posix()
        entries.append(
            {
                "path": rel,  # relative to /app on-device
                "url": f"{url_base.rstrip('/')}/{rel}",
                "sha256": sha256_file(f),
            }
        )
    return entries


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Build OTA manifest for MicroPython app-level OTA.")
    parser.add_argument("--user", required=True, help="GitHub username/org (for raw.githubusercontent.com URL)")
    parser.add_argument("--repo", required=True, help="GitHub repo name (for raw.githubusercontent.com URL)")
    parser.add_argument(
        "--branch",
        default="main",
        help="Branch name used for raw URLs (default: main)",
    )
    parser.add_argument(
        "--app-dir",
        default="app",
        help="Local app source directory to package (default: ./app)",
    )
    parser.add_argument(
        "--manifest-path",
        default="ota/manifest.json",
        help="Path to write the 'latest' manifest in the repo (default: ./ota/manifest.json)",
    )
    parser.add_argument(
        "--releases-root",
        default="releases",
        help="Folder in repo where versioned files are written (default: ./releases)",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Version string like 0.0.2. If omitted, will bump patch from existing manifest, or use 0.0.1.",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="Do not copy files into releases/<version>/ (manifest still points there; you must host them yourself).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional filename to exclude (can repeat).",
    )
    args = parser.parse_args(argv)

    app_dir = Path(args.app_dir)
    manifest_path = Path(args.manifest_path)
    releases_root = Path(args.releases_root)

    excludes = set(DEFAULT_EXCLUDES) | set(args.exclude)

    # Determine version
    version = args.version
    if not version:
        existing = load_existing_version(manifest_path)
        if existing:
            version = bump_patch(existing)
        else:
            version = "0.0.1"

    # Collect files
    files = collect_files(app_dir, excludes=excludes)
    if not files:
        print(f"No files found under {app_dir}. Nothing to do.", file=sys.stderr)
        return 2

    # Copy files into releases/<version>/...
    release_dir = releases_root / version
    if not args.no_copy:
        copy_release_files(app_dir, files, release_dir)

    # Construct URL base (points to releases/<version>)
    url_base = f"https://raw.githubusercontent.com/{args.user}/{args.repo}/{args.branch}/{releases_root.as_posix()}/{version}"

    entries = build_manifest_entries(app_dir, files, url_base=url_base)

    manifest = {
        "version": version,
        "files": entries,
    }

    write_manifest(manifest_path, manifest)

    # Summary
    print(f"Version: {version}")
    print(f"App dir: {app_dir}")
    print(f"Manifest: {manifest_path}")
    if not args.no_copy:
        print(f"Release files written to: {release_dir}")
    print(f"Manifest URL (device should fetch): https://raw.githubusercontent.com/{args.user}/{args.repo}/{args.branch}/{manifest_path.as_posix()}")
    print(f"File base URL: {url_base}/<relative-path>")
    print(f"Files: {len(entries)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

