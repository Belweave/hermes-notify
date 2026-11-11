#!/usr/bin/env python3
"""Stage authored plugin and Worker files without local environments or credentials."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("__init__.py", "plugin.yaml", "after-install.md", "LICENSE", "README.md", "pyproject.toml", "uv.lock")
SOURCE_DIRS = ("hermes_notify", "scripts", "tests", "docs", "desktop", "dashboard", "skills", "app", "worker", "plugin-catalog")
EXCLUDED = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "node_modules", "dist", "test-results", "playwright-report",
    ".local", ".venv", ".wrangler", ".pytest_cache", ".git", ".env", ".env.*",
    ".dev.vars*", "*.sqlite*", "*.db*", "*.log",
)


def safe_ignore(directory, names):
    ignored = set(EXCLUDED(directory, names))
    # A source link must not pull arbitrary files into an installable package.
    for name in set(names) - ignored:
        if (Path(directory) / name).is_symlink():
            raise ValueError(f"Source symlinks are not staged: {Path(directory) / name}")
    return ignored


def stage():
    destination = ROOT / ".local/package/hermes-notify"
    for name in ROOT_FILES + SOURCE_DIRS:
        if (ROOT / name).is_symlink():
            raise ValueError(f"Source symlinks are not staged: {ROOT / name}")
    if destination.is_symlink():
        raise ValueError("Package destination must not be a symlink")
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in ROOT_FILES:
        shutil.copy2(ROOT / name, destination / name)
    for name in SOURCE_DIRS:
        if (ROOT / name).is_dir():
            shutil.copytree(ROOT / name, destination / name, ignore=safe_ignore)
    return destination


if __name__ == "__main__":
    print(stage())
