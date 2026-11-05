"""Run the pinned admission checker on a frozen copy with no user profile.

The full-package result also covers files owned by the runtime task. Its result
is a development receipt, not catalog acceptance or a live approval rehearsal.
"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
source = root / ".local/hermes-source"
sys.path.insert(0, str(source))

with tempfile.TemporaryDirectory(prefix="notify-companion-catalog-") as scratch:
    sandbox = Path(scratch)
    os.environ["HERMES_HOME"] = str(sandbox / "profile")
    package = sandbox / "package"
    package.mkdir()
    for name in ("plugin.yaml", "pyproject.toml", "__init__.py"):
        shutil.copy2(root / name, package / name)
    for name in ("hermes_notify", "desktop", "dashboard", "skills"):
        shutil.copytree(root / name, package / name, ignore=shutil.ignore_patterns("tests", ".venv", "__pycache__", ".pytest_cache"))
    # No inherited tokens or model credentials in the recording subprocess.
    probe_env = {"PATH": os.defpath, "HERMES_HOME": str(sandbox / "probe"), "PYTHONNOUSERSITE": "1"}
    from hermes_cli.plugin_validate import validate_plugin_dir
    result = validate_plugin_dir(package, probe=([sys.executable], probe_env)).to_dict()
    # The temporary path is not useful in the durable receipt.
    receipt = json.loads(json.dumps(result).replace(str(package), "<staged-package>"))
    (root / "desktop/tests/catalog-result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
