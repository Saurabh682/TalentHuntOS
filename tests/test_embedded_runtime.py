"""Artifact integrity and privacy tests for the embedded local Copilot runtime."""

import json
import zipfile
from pathlib import Path

import pytest

from app.ai import embedded_runtime as runtime

REQUIRED_RUNTIME_FILES = {
    "llama-server.exe": b"server",
    "llama-server-impl.dll": b"implementation",
    "llama-common.dll": b"common",
    "llama.dll": b"llama",
    "ggml.dll": b"ggml",
    "ggml-base.dll": b"ggml-base",
}


def _runtime_artifact() -> dict[str, object]:
    return {
        "version": "test-build",
        "sha256": "a" * 64,
        "file_name": "runtime.zip",
        "executable": "llama-server.exe",
    }


def _write_archive(path: Path, *, unsafe: bool = False) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in REQUIRED_RUNTIME_FILES.items():
            archive.writestr(name, content)
        archive.writestr("ignored-tool.exe", b"not bundled")
        archive.writestr("notes.txt", b"not bundled")
        if unsafe:
            archive.writestr("../outside.dll", b"unsafe")


def _install_test_runtime(monkeypatch, tmp_path: Path, *, unsafe: bool = False) -> Path:
    archive_path = tmp_path / "fixture.zip"
    _write_archive(archive_path, unsafe=unsafe)
    monkeypatch.setattr(runtime, "runtime_artifact", _runtime_artifact)

    def fake_download(artifact, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive_path.read_bytes())
        return destination

    monkeypatch.setattr(runtime, "_download_verified", fake_download)
    target = tmp_path / "runtime"
    runtime.prepare_runtime_directory(target, cache_dir=tmp_path / "cache")
    return target


def test_manifest_pins_immutable_runtime_and_model_artifacts():
    manifest = runtime.load_manifest()
    assert manifest["runtime"]["version"] == "b10430"
    assert manifest["runtime"]["size_bytes"] == 18_459_208
    assert manifest["runtime"]["sha256"] == (
        "63988c0e4a2527cf9a90c229de0199201f7ba5957c06c92dacc1c96e4c0851d7"
    )
    assert manifest["runtime"]["installed_manifest_sha256"] == (
        "e568b918af4bbab97ee43fd185f732f3380d7c9adb7ef6d0bd86019a19a07d9b"
    )
    assert manifest["model"]["revision"] == ("ab4701481089b58a082ef63cc1cee738887293ff")
    assert manifest["model"]["size_bytes"] == 2_099_501_664
    assert manifest["model"]["sha256"] == (
        "662b0626cd58f443baea23559b469df6576a81d349649c59413b36a9fb32eb29"
    )


@pytest.mark.parametrize(
    "host",
    [
        "huggingface.co",
        "us.aws.cdn.hf.co",
        "us.gcp.cdn.hf.co",
        "cdn-lfs-us-1.hf.co",
        "cdn-lfs-eu-1.hf.co",
        "cas-server.xethub.hf.co",
        "transfer.xethub.hf.co",
    ],
)
def test_final_url_accepts_documented_hugging_face_download_hosts(host):
    runtime._validate_final_url(f"https://{host}/pinned-model")


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.hf.co/model",
        "https://us.aws.cdn.hf.co.attacker.example/model",
        "http://us.aws.cdn.hf.co/model",
        "https://huggingface.co.attacker.example/model",
    ],
)
def test_final_url_rejects_unapproved_or_insecure_lookalikes(url):
    with pytest.raises(RuntimeError, match="unapproved host"):
        runtime._validate_final_url(url)


def test_runtime_extraction_keeps_only_server_dependencies(monkeypatch, tmp_path):
    target = _install_test_runtime(monkeypatch, tmp_path)
    names = {path.name for path in target.iterdir()}
    assert set(REQUIRED_RUNTIME_FILES) | {runtime.RUNTIME_MARKER} == names
    assert runtime.runtime_directory_state(target, full_verify=True)["verified"] is True


def test_runtime_extraction_rejects_archive_traversal(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match="unsafe path"):
        _install_test_runtime(monkeypatch, tmp_path, unsafe=True)
    assert not (tmp_path / "outside.dll").exists()


def test_full_verification_detects_runtime_tampering(monkeypatch, tmp_path):
    target = _install_test_runtime(monkeypatch, tmp_path)
    (target / "llama.dll").write_bytes(b"tampered")
    assert runtime.runtime_directory_state(target, full_verify=True)["verified"] is False


def test_hardware_policy_selects_lite_standard_and_external(monkeypatch):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    lite = runtime.hardware_profile(
        total_ram_bytes=8 * 1024**3,
        available_ram_bytes=5 * 1024**3,
        cpu_threads=4,
        machine="AMD64",
    )
    standard = runtime.hardware_profile(
        total_ram_bytes=16 * 1024**3,
        available_ram_bytes=12 * 1024**3,
        cpu_threads=8,
        machine="AMD64",
    )
    unsupported = runtime.hardware_profile(
        total_ram_bytes=4 * 1024**3,
        available_ram_bytes=2 * 1024**3,
        cpu_threads=4,
        machine="AMD64",
    )
    assert lite["recommended_mode"] == "lite"
    assert standard["recommended_mode"] == "standard"
    assert unsupported["recommended_mode"] == "external"
    assert unsupported["supported"] is False


def test_public_status_never_exposes_paths_or_artifact_urls(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "resolve_verified_runtime",
        lambda **kwargs: {
            "installed": True,
            "verified": True,
            "version": "test",
            "source": "bundled",
            "directory": Path("C:/private/runtime"),
            "executable": Path("C:/private/runtime/llama-server.exe"),
        },
    )
    monkeypatch.setattr(
        runtime,
        "model_state",
        lambda **kwargs: {
            "installed": True,
            "verified": True,
            "name": "Test Model",
            "revision": "immutable",
            "quantization": "Q4",
            "size_bytes": 10,
            "path": Path("C:/private/model.gguf"),
        },
    )
    monkeypatch.setattr(
        runtime,
        "model_artifact",
        lambda: {"license": "Apache-2.0", "url": "https://secret.invalid/model"},
    )
    monkeypatch.setattr(
        runtime,
        "hardware_profile",
        lambda: {
            "ram_gb": 16.0,
            "available_ram_gb": 10.0,
            "cpu_threads": 8,
            "architecture": "amd64",
            "supported": True,
            "recommended_mode": "standard",
            "reason": "Supported.",
        },
    )
    monkeypatch.setattr(
        "app.ai.local_server.local_server_manager.get_status",
        lambda: {
            "status": "stopped",
            "managed": False,
            "host": "127.0.0.1",
            "port": 1234,
            "mode": "standard",
            "runtime_source": None,
            "uptime_seconds": 0,
            "last_error": None,
        },
    )
    monkeypatch.setattr("app.jobs.service.list_job_rows", lambda **kwargs: [])

    serialized = json.dumps(runtime.public_status())
    assert "C:/private" not in serialized
    assert "secret.invalid" not in serialized
    assert '"path"' not in serialized
    assert '"url"' not in serialized
    assert runtime.public_status()["external_endpoint"] == {
        "host": runtime.settings.llama_server_host,
        "port": runtime.settings.llama_server_port,
    }


def test_configured_endpoint_uses_dedicated_embedded_port(monkeypatch):
    monkeypatch.setattr(runtime.settings, "embedded_ai_port", 18081)
    monkeypatch.setattr(runtime.settings, "llama_server_host", "127.0.0.1")
    monkeypatch.setattr(runtime.settings, "llama_server_port", 1234)

    assert runtime.configured_local_endpoint("standard") == ("127.0.0.1", 18081)
    assert runtime.configured_local_endpoint("lite") == ("127.0.0.1", 18081)
    assert runtime.configured_local_endpoint("external") == ("127.0.0.1", 1234)
