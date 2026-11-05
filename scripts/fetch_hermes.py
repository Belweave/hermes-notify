#!/usr/bin/env python3
"""Fetch the tested public Hermes source archive, verify it, and extract locally."""

import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    meta = json.loads((ROOT / "docs/SOURCES.json").read_text())["hermes"]
    destination = ROOT / ".local/hermes-source"
    if destination.exists():
        print(f"Hermes source already exists at {destination}; left unchanged")
        return
    destination.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix="fetch-") as temp:
        archive = Path(temp) / "hermes.tar.gz"
        with urlopen(meta["archive_url"], timeout=30) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        with archive.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != meta["archive_sha256"]:
            raise SystemExit("Hermes archive hash differs from the research snapshot")
        with tarfile.open(archive) as source:
            source.extractall(Path(temp) / "extracted", filter="data")
        unpacked = Path(temp) / "extracted" / ("hermes-agent-" + meta["commit_sha"])
        unpacked.rename(destination)
    print(f"Verified Hermes {meta['commit_sha']} at {destination}")


if __name__ == "__main__":
    main()
