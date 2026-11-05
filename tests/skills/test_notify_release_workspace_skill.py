"""The native skill must remain loadable after installation relocates the package."""

import importlib.util
import shutil
from pathlib import Path
from types import SimpleNamespace


def test_installed_skill_uses_its_packaged_document(tmp_path):
    source = Path(__file__).resolve().parents[2] / "skills"
    installed = tmp_path / "profile" / "plugins" / "hermes-notify" / "skills"
    shutil.copytree(source, installed, ignore=shutil.ignore_patterns("__pycache__"))
    spec = importlib.util.spec_from_file_location("installed_pocket_skills", installed / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    receipt = object()
    registrations = []

    def register_skill(name, path, *, description):
        assert path.is_relative_to(installed)
        assert path.is_file()
        document = path.read_text(encoding="utf-8")
        assert document.startswith("---\n")
        assert f"name: {name}\n" in document
        assert f"description: {description}\n" in document
        registrations.append(name)
        return receipt

    assert module.register(SimpleNamespace(register_skill=register_skill)) is receipt
    assert registrations == ["notify-release-workspace"]
