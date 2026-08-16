"""Security boundaries for the optional local model server adapter."""

from types import SimpleNamespace

import pytest

from app.ai.local_server import LocalServerManager, _is_loopback_host


@pytest.mark.parametrize("host", ["127.0.0.1", "127.42.0.8", "::1", "localhost"])
def test_local_model_adapter_accepts_literal_loopback_hosts(host):
    assert _is_loopback_host(host) is True


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "192.168.1.10", "example.com", "localhost.example.com", ""],
)
def test_local_model_adapter_rejects_non_loopback_hosts(host):
    assert _is_loopback_host(host) is False


def test_non_loopback_host_is_rejected_before_network_or_process_access(monkeypatch):
    manager = LocalServerManager(host="example.com", port=1234)
    called = SimpleNamespace(urlopen=False, executable=False)

    def fail_urlopen(*args, **kwargs):
        called.urlopen = True
        raise AssertionError("network access must not occur")

    def fail_executable():
        called.executable = True
        raise AssertionError("executable lookup must not occur")

    monkeypatch.setattr("app.ai.local_server.urllib.request.urlopen", fail_urlopen)
    monkeypatch.setattr(manager, "find_executable", fail_executable)

    assert manager.is_running() is False
    assert manager.start() is False
    assert called == SimpleNamespace(urlopen=False, executable=False)


def test_embedded_start_uses_loopback_verified_runtime_and_jinja(monkeypatch, tmp_path):
    binary = tmp_path / "runtime" / "llama-server.exe"
    binary.parent.mkdir()
    binary.write_bytes(b"loader")
    model = tmp_path / "model.gguf"
    model.write_bytes(b"model")
    manager = LocalServerManager(host="127.0.0.1", port=18991, model_path=model)
    manager.n_ctx = 2048
    manager.threads = 2
    manager.batch_size = 256
    monkeypatch.setattr(manager, "configure_for_current_mode", lambda: None)
    health = iter([False, True])
    monkeypatch.setattr(manager, "_http_healthy", lambda: next(health))
    monkeypatch.setattr(manager, "find_executable", lambda: str(binary))
    monkeypatch.setattr(
        "app.ai.embedded_runtime.model_state",
        lambda **kwargs: {"verified": True},
    )
    monkeypatch.setattr("app.ai.local_server.settings.local_ai_mode", "standard")
    captured = {}

    class FakeProcess:
        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        return FakeProcess()

    monkeypatch.setattr("app.ai.local_server.subprocess.Popen", fake_popen)

    assert manager.start(model_verified=True, readiness_timeout=5) is True
    command = captured["command"]
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "18991"
    assert command[command.index("-m") + 1] == str(model)
    assert "--jinja" in command
    assert captured["cwd"] == str(binary.parent)


def test_stop_never_takes_ownership_of_external_server(monkeypatch):
    manager = LocalServerManager(host="127.0.0.1", port=1234)
    monkeypatch.setattr("app.ai.local_server.settings.local_ai_mode", "external")
    monkeypatch.setattr(manager, "_http_healthy", lambda: True)
    assert manager.get_status()["status"] == "external"
    assert manager.stop() is True
    assert manager.process is None


def test_settings_managed_endpoint_separates_embedded_from_external(monkeypatch):
    manager = LocalServerManager()
    monkeypatch.setattr("app.ai.local_server.settings.embedded_ai_port", 18081)
    monkeypatch.setattr("app.ai.local_server.settings.llama_server_port", 1234)

    monkeypatch.setattr("app.ai.local_server.settings.local_ai_mode", "standard")
    manager.configure_for_current_mode()
    assert (manager.host, manager.port) == ("127.0.0.1", 18081)

    monkeypatch.setattr("app.ai.local_server.settings.local_ai_mode", "external")
    manager.configure_for_current_mode()
    assert (manager.host, manager.port) == ("127.0.0.1", 1234)


def test_explicit_manager_endpoint_is_not_reconfigured(monkeypatch, tmp_path):
    manager = LocalServerManager(
        host="127.0.0.1",
        port=18991,
        model_path=tmp_path / "explicit.gguf",
    )
    monkeypatch.setattr("app.ai.local_server.settings.local_ai_mode", "standard")
    manager.configure_for_current_mode()
    assert (manager.host, manager.port) == ("127.0.0.1", 18991)
    assert manager.model_path == tmp_path / "explicit.gguf"
