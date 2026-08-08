"""Subprocess manager for local llama-server background process."""

import logging
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from app.config.settings import settings

logger = logging.getLogger("talenthunt.ai.local_server")


class LocalServerManager:
    """Manages the background llama-server process lifecycle."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        model_path: Path | str | None = None,
        n_ctx: int = 4096,
        n_gpu_layers: int = 0,
    ) -> None:
        self.host = host or settings.llama_server_host
        self.port = port or settings.llama_server_port
        self.model_path = Path(model_path or settings.local_model_path)
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self.process: subprocess.Popen[bytes] | None = None
        self.start_time: float | None = None

    def find_executable(self) -> str | None:
        """Locate the llama-server executable in PATH or standard system paths."""
        binary = shutil.which("llama-server") or shutil.which("llama-server.exe")
        if binary:
            return binary
        
        # Fallback search paths
        candidate_paths = [
            Path("C:/llama.cpp/llama-server.exe"),
            Path("C:/tools/llama-server.exe"),
            Path("/usr/local/bin/llama-server"),
        ]
        for candidate in candidate_paths:
            if candidate.exists():
                return str(candidate)
        return None

    def is_running(self) -> bool:
        """Check if LM Studio / local server is active and responding on HTTP."""
        if self.process is not None and self.process.poll() is not None:
            return False

        # HTTP check against LM Studio / OpenAI endpoints
        endpoints = [
            f"http://{self.host}:{self.port}/v1/models",
            f"http://{self.host}:{self.port}/health",
        ]
        for url in endpoints:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "TalentHuntOS/0.1"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status in (200, 503):
                        return True
            except Exception:
                continue
        return False

    def start(self) -> bool:
        """Connect to LM Studio local server."""
        if self.is_running():
            logger.info("Connected to LM Studio / local AI server on http://%s:%s", self.host, self.port)
            return True

        binary = self.find_executable()
        if not binary or not self.model_path.exists():
            logger.info("LM Studio is not currently running on http://%s:%s. Please open LM Studio and start the Local Server.", self.host, self.port)
            return False

        cmd = [
            binary,
            "-m", str(self.model_path),
            "--host", self.host,
            "--port", str(self.port),
            "-c", str(self.n_ctx),
            "-ngl", str(self.n_gpu_layers),
        ]

        logger.info("Starting local AI server: %s", " ".join(cmd))
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.start_time = time.time()
            
            # Poll for readiness
            for _ in range(10):
                time.sleep(0.5)
                if self.is_running():
                    logger.info("Local AI server started successfully.")
                    return True

            logger.error("Local AI server process (pid %s) failed to initialize.", self.process.pid)
            return False
        except Exception as exc:
            logger.exception("Failed to start local AI server process: %s", exc)
            return False

    def stop(self) -> bool:
        """Stop the llama-server subprocess."""
        if self.process is None:
            logger.info("llama-server is not managed by this process handle.")
            return True

        try:
            logger.info("Stopping llama-server (pid %s)...", self.process.pid)
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                try:
                    self.process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    pass
            logger.info("llama-server process stopped.")
            self.process = None
            self.start_time = None
            return True
        except Exception as exc:
            logger.exception("Failed to stop llama-server process: %s", exc)
            return False

    def get_status(self) -> dict[str, Any]:
        """Return diagnostic status dict of the local AI server."""
        active = self.is_running()
        uptime = round(time.time() - self.start_time, 2) if (active and self.start_time) else 0.0
        return {
            "status": "running" if active else "stopped",
            "pid": self.process.pid if (self.process and self.process.poll() is None) else None,
            "host": self.host,
            "port": self.port,
            "model_path": str(self.model_path),
            "model_exists": self.model_path.exists(),
            "uptime_seconds": uptime,
        }


# Global Local Server Manager Instance
local_server_manager = LocalServerManager()
