#!/usr/bin/env python3
"""Create a small installable directory without research downloads or test environments."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def stage():
    destination = ROOT / ".local/package/hermes-notify"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "plugin.yaml", "LICENSE", "README.md", "pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, destination / name)
    for name in ("hermes_notify", "scripts", "tests", "docs"):
        package = destination / name
        if package.exists():
            shutil.rmtree(package)
        shutil.copytree(ROOT / name, package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return destination


if __name__ == "__main__":
    print(stage())
