import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("HERMES_SOURCE", ROOT / ".local/hermes-source"))
if not (SOURCE / "hermes_cli/plugins.py").is_file():
    raise RuntimeError("Run scripts/fetch_hermes.py before testing against real Hermes")
sys.path[:0] = [str(ROOT), str(SOURCE)]
