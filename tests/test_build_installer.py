"""Desktop packaging contracts for the embedded local Copilot runtime."""

import importlib.util
from pathlib import Path

import pytest

from app.ai import embedded_runtime

_SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_installer.py"
_SPEC = importlib.util.spec_from_file_location("talenthunt_build_installer", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
build_installer = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(build_installer)


def test_build_accepts_only_a_complete_verified_runtime(monkeypatch, tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    monkeypatch.setattr(
        embedded_runtime,
        "runtime_directory_state",
        lambda directory, full_verify=False: {"verified": directory == runtime_dir},
    )
    assert build_installer.prepare_build_runtime(str(runtime_dir)) == runtime_dir

    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(RuntimeError, match="incomplete"):
        build_installer.prepare_build_runtime(str(other))


def test_pyinstaller_configuration_includes_runtime_modules_not_a_lone_loader(tmp_path):
    args = build_installer.build_pyinstaller_args(
        dist_dir=tmp_path / "dist" / "TalentHuntOS",
        build_dir=tmp_path / "build",
        nicegui_dir=tmp_path / "nicegui",
        runtime_dir=tmp_path / "runtime",
    )
    assert "--hidden-import=app.ai.embedded_runtime" in args
    assert "--hidden-import=app.ai.embedded_jobs" in args
    assert "--hidden-import=app.actions.ai_runtime" in args
    assert "--hidden-import=psutil" in args
    assert not any("llama-server.exe" in item for item in args)


def test_distribution_readme_explains_first_run_model_download(tmp_path):
    build_installer.create_readme(tmp_path, has_runtime=True)
    content = (tmp_path / "README_DIST.txt").read_text(encoding="utf-8")
    assert "complete pinned llama.cpp runtime is bundled" in content
    assert "about 2.1 GB" in content
    assert "fully offline" in content
