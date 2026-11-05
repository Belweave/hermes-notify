#!/usr/bin/env python3
"""Validate the complete staged package using pinned Hermes and an empty home."""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.local/hermes-source')]


def main():
    from scripts.stage_plugin import stage
    package = stage()
    with tempfile.TemporaryDirectory(prefix='pocket-validation-') as scratch:
        env = {'PATH': os.defpath, 'HOME': scratch, 'HERMES_HOME': str(Path(scratch) / 'profile'),
               'PYTHONNOUSERSITE': '1', 'HERMES_ENABLE_PROJECT_PLUGINS': '0'}
        # The validator and its registration probe must not see the operator's home.
        os.environ.clear()
        os.environ.update(env)
        from hermes_cli.plugin_validate import validate_plugin_dir
        result = validate_plugin_dir(package, probe=([sys.executable], env)).to_dict()
        result = json.loads(json.dumps(result).replace(str(package), '<staged-package>'))
        report = ROOT / '.local/package-validation.json'
        report.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
