"""Install profiles must retain developer tools across cache and fallback paths."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts" / "dev.py"
    spec = importlib.util.spec_from_file_location("group16_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'example'\n")
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "STAMP", tmp_path / "stamp")
    return module


@pytest.mark.parametrize(
    ("minimal", "dev", "target"),
    [(False, False, ".[embeddings]"), (True, False, "."),
     (False, True, ".[embeddings,dev]"), (True, True, ".[dev]")],
)
def test_install_profiles(launcher, monkeypatch, minimal, dev, target):
    calls = []
    monkeypatch.setattr(launcher, "run", lambda cmd: calls.append(cmd) or True)
    launcher.install(minimal, dev)
    assert calls[0][-1] == target
    launcher.install(minimal, dev)
    assert len(calls) == 1  # Repeating a successful profile needs no installation.


def test_enabling_dev_invalidates_runtime_stamp(launcher, monkeypatch):
    calls = []
    monkeypatch.setattr(launcher, "run", lambda cmd: calls.append(cmd) or True)
    launcher.install(False)
    launcher.install(False, True)
    assert [cmd[-1] for cmd in calls] == [".[embeddings]", ".[embeddings,dev]"]


def test_embedding_fallback_preserves_dev_and_stamp(launcher, monkeypatch):
    calls = []

    def run(cmd):
        calls.append(cmd)
        return len(calls) > 1

    monkeypatch.setattr(launcher, "run", run)
    launcher.install(False, True)
    assert [cmd[-1] for cmd in calls] == [".[embeddings,dev]", ".[dev]"]
    launcher.install(True, True)
    assert len(calls) == 2  # Fallback stamp describes the packages actually installed.


def test_failed_minimal_dev_install_is_not_stamped(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "run", lambda cmd: False)
    with pytest.raises(SystemExit):
        launcher.install(True, True)
    assert not launcher.STAMP.exists()
