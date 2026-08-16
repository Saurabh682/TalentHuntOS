"""Loopback-only lifecycle manager for embedded or external local AI servers."""

from __future__ import annotations

import json
import logging
import subprocess
import time
import urllib.request
from collections.abc import Callable
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from app.config.settings import settings

logger = logging.getLogger("talenthunt.ai.local_server")


def _is_loopback_host(host: str) -> bool:
    candidate = (host or "").strip().strip("[]").lower()
    if candidate == "localhost":
        return True
    try:
        return ip_address(candidate).is_loopback
    except ValueError:
        return False


class LocalServerManager:
    """Own the llama-server process while never taking ownership of external services."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        model_path: Path | str | None = None,
        n_ctx: int | None = None,
        n_gpu_layers: int = 0,
        threads: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        self._host_from_settings = host is None
        self._port_from_settings = port is None
        self._model_from_settings = model_path is None
        self.host = host or settings.llama_server_host
        self.port = int(port or settings.llama_server_port)
        self.model_path = Path(model_path or settings.local_model_path)
        self.n_ctx = n_ctx or 4096
        self.n_gpu_layers = n_gpu_layers
        self.threads = threads
        self.batch_size = batch_size
        self.process: subprocess.Popen[bytes] | None = None
        self.start_time: float | None = None
        self.runtime_source: str | None = None
        self.last_error: str | None = None

    def configure_for_current_mode(self) -> None:
        from app.ai.embedded_runtime import (
            configured_local_endpoint,
            default_model_path,
            mode_config,
        )

        config = mode_config()
        configured_host, configured_port = configured_local_endpoint(config["mode"])
        if self._host_from_settings:
            self.host = configured_host
        if self._port_from_settings:
            self.port = configured_port
        if self._model_from_settings:
            self.model_path = default_model_path()
        if config["mode"] != "external":
            self.n_ctx = int(config["context_length"])
            self.threads = int(config["threads"])
            self.batch_size = int(config["batch_size"])

    def find_executable(self) -> str | None:
        """Resolve only a verified TalentHunt-managed runtime."""
        from app.ai.embedded_runtime import resolve_verified_runtime

        runtime = resolve_verified_runtime(full_verify=True)
        if not runtime["verified"] or not runtime["executable"]:
            return None
        self.runtime_source = str(runtime["source"])
        return str(runtime["executable"])

    def _process_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _http_healthy(self) -> bool:
        if not _is_loopback_host(self.host):
            logger.warning("Refusing non-loopback local AI host: %s", self.host)
            return False
        endpoints = (
            (f"http://{self.host}:{self.port}/health", "health"),
            (f"http://{self.host}:{self.port}/v1/models", "models"),
        )
        for url, kind in endpoints:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "TalentHuntOS/0.1"})
                with urllib.request.urlopen(request, timeout=0.35) as response:  # nosec B310
                    if kind == "health" and self._process_alive() and response.status == 200:
                        return True
                    if kind == "models" and response.status == 200:
                        payload = json.loads(response.read(262_144).decode("utf-8"))
                        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                            return True
            except Exception:
                continue
        return False

    def is_running(self) -> bool:
        """Return whether any loopback OpenAI-compatible service responds."""
        if self.process is not None and self.process.poll() is not None:
            self.process = None
            self.start_time = None
        return self._http_healthy()

    def start(
        self,
        *,
        model_verified: bool = False,
        cancel_check: Callable[[], bool] | None = None,
        readiness_timeout: float = 120.0,
    ) -> bool:
        """Start the verified embedded server or connect to an explicit external one."""
        self.configure_for_current_mode()
        self.last_error = None
        if not _is_loopback_host(self.host):
            self.last_error = "Local AI host must be a literal loopback address."
            logger.error(self.last_error)
            return False

        external_mode = settings.local_ai_mode == "external"
        healthy = self._http_healthy()
        if self._process_alive() and healthy:
            return True
        if external_mode:
            if healthy:
                self.runtime_source = "external"
                return True
            self.last_error = "No external local AI server is responding on the configured port."
            return False
        if healthy and not self._process_alive():
            self.last_error = (
                "The embedded AI port is occupied by an unmanaged service. "
                "Stop it or select External mode."
            )
            return False

        from app.ai.embedded_runtime import model_state

        model = model_state(full_verify=not model_verified)
        binary = self.find_executable()
        if not binary or not model["verified"]:
            self.last_error = (
                "The verified embedded runtime and default model must be installed first."
            )
            return False

        command = [
            binary,
            "-m",
            str(self.model_path),
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--ctx-size",
            str(self.n_ctx),
            "--n-gpu-layers",
            str(self.n_gpu_layers),
            "--threads",
            str(self.threads or 1),
            "--batch-size",
            str(self.batch_size or 256),
            "--alias",
            "local-model",
            "--jinja",
        ]
        try:
            self.process = subprocess.Popen(  # noqa: S603
                command,
                cwd=str(Path(binary).resolve().parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.start_time = time.time()
            deadline = time.monotonic() + max(5.0, float(readiness_timeout))
            while time.monotonic() < deadline:
                if cancel_check and cancel_check():
                    self.stop()
                    self.last_error = "Embedded AI startup was cancelled."
                    return False
                if self.process.poll() is not None:
                    self.last_error = "llama-server exited before it became ready."
                    self.process = None
                    self.start_time = None
                    return False
                if self._http_healthy():
                    logger.info("Embedded local AI server is ready on 127.0.0.1:%s", self.port)
                    return True
                time.sleep(0.5)
            self.last_error = "llama-server did not become ready before the startup timeout."
            self.stop()
            return False
        except Exception as exc:
            self.last_error = f"Failed to start the embedded local AI server: {exc}"
            logger.exception(self.last_error)
            self.process = None
            self.start_time = None
            return False

    def stop(self) -> bool:
        """Stop only the subprocess launched by this TalentHunt process."""
        if self.process is None:
            return True
        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None
            self.start_time = None
            self.runtime_source = None
            return True
        except Exception as exc:
            self.last_error = f"Failed to stop the embedded local AI server: {exc}"
            logger.exception(self.last_error)
            return False

    def get_status(self) -> dict[str, Any]:
        """Return sanitized server status without filesystem paths or credentials."""
        self.configure_for_current_mode()
        active = self._http_healthy()
        managed = self._process_alive()
        uptime = round(time.time() - self.start_time, 1) if managed and self.start_time else 0.0
        if active and managed:
            status = "running"
        elif active:
            status = "external" if settings.local_ai_mode == "external" else "port_conflict"
        else:
            status = "stopped"
        return {
            "status": status,
            "managed": managed,
            "host": self.host,
            "port": self.port,
            "mode": settings.local_ai_mode,
            "runtime_source": self.runtime_source,
            "uptime_seconds": uptime,
            "last_error": self.last_error,
        }


local_server_manager = LocalServerManager()
