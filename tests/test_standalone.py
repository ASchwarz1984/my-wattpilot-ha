"""Ensure the integration cannot silently use the external Wattpilot package."""

import importlib.util
import json
from pathlib import Path
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "wattpilot"


def _load_utils(package_path):
    package = types.ModuleType("standalone_test")
    package.__path__ = [str(package_path)]
    external_client = types.ModuleType("wattpilot")
    before = list(sys.path)
    with patch.dict(sys.modules, {
        "standalone_test": package,
        "wattpilot": external_client,
        "websocket": MagicMock(),
        "bcrypt": MagicMock(),
    }):
        spec = importlib.util.spec_from_file_location(
            "standalone_test.utils", COMPONENT / "utils.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert sys.path == before
        assert sys.modules["wattpilot"] is external_client
        return module


def test_bundled_client_is_loaded_even_when_external_client_is_present():
    module = _load_utils(COMPONENT)
    assert Path(module.wattpilot.__file__).resolve() == (
        COMPONENT / "wattpilot" / "src" / "wattpilot" / "__init__.py"
    ).resolve()


def test_missing_bundled_client_does_not_fall_back(tmp_path):
    (tmp_path / "const.py").write_text((COMPONENT / "const.py").read_text())
    with pytest.raises(ModuleNotFoundError, match="standalone_test.wattpilot"):
        _load_utils(tmp_path)


def test_manifest_uses_only_our_repository_and_no_external_client():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["domain"] == "wattpilot"
    assert manifest["documentation"] == "https://github.com/ASchwarz1984/my-wattpilot-ha"
    assert manifest["issue_tracker"] == manifest["documentation"] + "/issues"
    assert not any(req.startswith("wattpilot") for req in manifest["requirements"])
    assert any(req.startswith("bcrypt==") for req in manifest["requirements"])
    assert any(req.startswith("websocket-client==") for req in manifest["requirements"])
