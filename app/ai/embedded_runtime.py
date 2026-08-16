"""Verified artifacts and hardware policy for the embedded local Copilot."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import urllib.request
import uuid
import zipfile
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import psutil
from sqlalchemy import select

from app.config.settings import BASE_DIR, DATA_DIR, settings

CHUNK_SIZE = 1024 * 1024
MAX_RUNTIME_EXTRACT_BYTES = 128 * 1024 * 1024
RUNTIME_MARKER = ".talenthunt-runtime.json"
MODEL_MARKER_SUFFIX = ".verified.json"
EMBEDDED_MODES = {"lite", "standard"}
ALL_MODES = EMBEDDED_MODES | {"external"}

APPROVED_HF_DOWNLOAD_HOSTS = {
    "huggingface.co",
    "cas-bridge.xethub.hf.co",
    "cas-server.xethub.hf.co",
    "cas-server.xethub-eu.hf.co",
    "transfer.xethub.hf.co",
    "transfer.xethub-eu.hf.co",
    "us.aws.cdn.hf.co",
    "us.gcp.cdn.hf.co",
    "cdn-lfs.hf.co",
    "cdn-lfs-us-1.hf.co",
    "cdn-lfs-eu-1.hf.co",
}

ProgressCallback = Callable[[dict[str, Any]], None]
CancelCheck = Callable[[], bool]


class DownloadCancelled(RuntimeError):
    """Raised when a durable install job is cancelled cooperatively."""


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    """Load and validate the immutable embedded artifact manifest."""
    path = Path(__file__).with_name("embedded_manifest.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise RuntimeError("Unsupported embedded AI manifest schema.")
    for section in ("runtime", "model"):
        artifact = data.get(section)
        if not isinstance(artifact, dict):
            raise RuntimeError(f"Embedded AI manifest is missing {section} metadata.")
        for field in ("id", "file_name", "url", "size_bytes", "sha256", "license"):
            if not artifact.get(field):
                raise RuntimeError(f"Embedded AI {section} metadata is missing {field}.")
        if len(str(artifact["sha256"])) != 64:
            raise RuntimeError(f"Embedded AI {section} checksum is invalid.")
        _validate_source_url(str(artifact["url"]))
    runtime = data["runtime"]
    if len(str(runtime.get("installed_manifest_sha256") or "")) != 64:
        raise RuntimeError("Embedded AI runtime file manifest checksum is invalid.")
    return data


def runtime_artifact() -> dict[str, Any]:
    return dict(load_manifest()["runtime"])


def model_artifact() -> dict[str, Any]:
    return dict(load_manifest()["model"])


def private_runtime_dir() -> Path:
    artifact = runtime_artifact()
    return DATA_DIR / "runtime" / "llama.cpp" / str(artifact["version"])


def source_runtime_dir() -> Path:
    artifact = runtime_artifact()
    return BASE_DIR / "bin" / "llama.cpp" / str(artifact["version"])


def packaged_runtime_dir() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent / "llama-runtime"


def default_model_path() -> Path:
    return DATA_DIR / "models" / str(model_artifact()["file_name"])


def _validate_source_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "huggingface.co"}:
        raise RuntimeError("Embedded AI artifacts must use pinned HTTPS upstream URLs.")


def _validate_final_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed = (
        host in APPROVED_HF_DOWNLOAD_HOSTS
        or host == "github.com"
        or host.endswith(".githubusercontent.com")
    )
    if parsed.scheme != "https" or not allowed:
        raise RuntimeError("Artifact download redirected to an unapproved host.")


def _safe_child(root: Path, child: Path) -> Path:
    root = root.resolve()
    resolved = child.resolve()
    if not resolved.is_relative_to(root):
        raise RuntimeError("Embedded AI artifact path escaped its private directory.")
    return resolved


def _emit(progress: ProgressCallback | None, **values: Any) -> None:
    if progress:
        progress(values)


def _cancelled(cancel_check: CancelCheck | None) -> bool:
    return bool(cancel_check and cancel_check())


def _sha256_file(
    path: Path,
    *,
    progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    phase: str = "verifying",
) -> str:
    total = path.stat().st_size
    completed = 0
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            if _cancelled(cancel_check):
                raise DownloadCancelled("Embedded AI installation cancelled.")
            digest.update(chunk)
            completed += len(chunk)
            _emit(
                progress,
                phase=phase,
                bytes_completed=completed,
                total_bytes=total,
                percent=round((completed / total) * 100, 1) if total else 100.0,
            )
    return digest.hexdigest()


def _download_verified(
    artifact: dict[str, Any],
    destination: Path,
    *,
    progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    phase: str,
) -> Path:
    """Download one fixed artifact with resume, exact size, and SHA-256 verification."""
    _validate_source_url(str(artifact["url"]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_suffix(destination.suffix + ".part")
    expected_size = int(artifact["size_bytes"])
    existing = pending.stat().st_size if pending.exists() else 0
    if existing > expected_size:
        pending.unlink()
        existing = 0

    headers = {"User-Agent": "TalentHuntOS/0.1"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(str(artifact["url"]), headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310
        _validate_final_url(response.geturl())
        response_status = getattr(response, "status", 200)
        append = existing > 0 and response_status == 206
        if existing and not append:
            existing = 0
        mode = "ab" if append else "wb"
        completed = existing
        with pending.open(mode) as handle:
            while chunk := response.read(CHUNK_SIZE):
                if _cancelled(cancel_check):
                    raise DownloadCancelled("Embedded AI installation cancelled.")
                completed += len(chunk)
                if completed > expected_size:
                    pending.unlink(missing_ok=True)
                    raise RuntimeError("Artifact exceeded its pinned size.")
                handle.write(chunk)
                _emit(
                    progress,
                    phase=phase,
                    bytes_completed=completed,
                    total_bytes=expected_size,
                    percent=round((completed / expected_size) * 100, 1),
                )

    if pending.stat().st_size != expected_size:
        raise RuntimeError(
            f"Artifact download is incomplete ({pending.stat().st_size}/{expected_size} bytes)."
        )
    digest = _sha256_file(
        pending,
        progress=progress,
        cancel_check=cancel_check,
        phase=f"verifying_{phase}",
    )
    if digest.lower() != str(artifact["sha256"]).lower():
        pending.unlink(missing_ok=True)
        raise RuntimeError("Artifact checksum verification failed.")
    pending.replace(destination)
    return destination


def _runtime_marker_state(directory: Path, *, full_verify: bool) -> dict[str, Any]:
    artifact = runtime_artifact()
    marker_path = directory / RUNTIME_MARKER
    executable = directory / str(artifact["executable"])
    result = {
        "installed": False,
        "verified": False,
        "version": artifact["version"],
        "executable": executable,
    }
    if not marker_path.is_file() or not executable.is_file():
        return result
    try:
        marker_bytes = marker_path.read_bytes()
        expected_marker_size = artifact.get("installed_manifest_size_bytes")
        expected_marker_hash = artifact.get("installed_manifest_sha256")
        if expected_marker_size and len(marker_bytes) != int(expected_marker_size):
            return result
        if expected_marker_hash and hashlib.sha256(marker_bytes).hexdigest() != str(
            expected_marker_hash
        ):
            return result
        marker = json.loads(marker_bytes.decode("utf-8"))
    except (OSError, ValueError, TypeError):
        return result
    if (
        marker.get("version") != artifact["version"]
        or marker.get("archive_sha256") != artifact["sha256"]
        or not isinstance(marker.get("files"), dict)
    ):
        return result
    for name, expected in marker["files"].items():
        path = directory / name
        if PurePosixPath(name).name != name or not path.is_file():
            return result
        if path.stat().st_size != int(expected.get("size_bytes") or -1):
            return result
        if full_verify and _sha256_file(path) != expected.get("sha256"):
            return result
    result.update(installed=True, verified=True)
    return result


def runtime_directory_state(directory: Path, *, full_verify: bool = False) -> dict[str, Any]:
    """Verify a proposed runtime directory against TalentHunt's pinned manifest."""
    return _runtime_marker_state(directory.resolve(), full_verify=full_verify)


def resolve_verified_runtime(*, full_verify: bool = False) -> dict[str, Any]:
    """Return the first verified bundled or private runtime without exposing it publicly."""
    candidates: list[tuple[str, Path]] = []
    packaged = packaged_runtime_dir()
    if packaged:
        candidates.append(("bundled", packaged))
    candidates.extend(
        (("source-bundled", source_runtime_dir()), ("private", private_runtime_dir()))
    )
    for source, directory in candidates:
        state = _runtime_marker_state(directory, full_verify=full_verify)
        if state["verified"]:
            state["source"] = source
            state["directory"] = directory
            return state
    artifact = runtime_artifact()
    return {
        "installed": False,
        "verified": False,
        "version": artifact["version"],
        "source": None,
        "directory": None,
        "executable": None,
    }


def _safe_runtime_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    artifact = runtime_artifact()
    allowed: list[zipfile.ZipInfo] = []
    total = 0
    for item in archive.infolist():
        if item.is_dir():
            continue
        path = PurePosixPath(item.filename)
        unix_mode = (item.external_attr >> 16) & 0xFFFF
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise RuntimeError("Runtime archive contains an unsafe path.")
        if unix_mode and stat.S_ISLNK(unix_mode):
            raise RuntimeError("Runtime archive contains a symbolic link.")
        name = path.name
        if name != artifact["executable"] and not name.lower().endswith(".dll"):
            continue
        total += int(item.file_size)
        if total > MAX_RUNTIME_EXTRACT_BYTES:
            raise RuntimeError("Runtime archive expands beyond the allowed size.")
        allowed.append(item)
    names = {PurePosixPath(item.filename).name for item in allowed}
    required = {
        str(artifact["executable"]),
        "llama-server-impl.dll",
        "llama-common.dll",
        "llama.dll",
        "ggml.dll",
        "ggml-base.dll",
    }
    if not required.issubset(names):
        raise RuntimeError("Runtime archive is missing required server components.")
    return allowed


def prepare_runtime_directory(
    target_dir: Path,
    *,
    cache_dir: Path | None = None,
    progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    """Install the pinned llama.cpp server into a controlled directory."""
    target_dir = target_dir.resolve()
    existing = _runtime_marker_state(target_dir, full_verify=True)
    if existing["verified"]:
        return existing

    artifact = runtime_artifact()
    cache_root = (cache_dir or DATA_DIR / "runtime" / "downloads").resolve()
    archive_path = _safe_child(cache_root, cache_root / str(artifact["file_name"]))
    _download_verified(
        artifact,
        archive_path,
        progress=progress,
        cancel_check=cancel_check,
        phase="downloading_runtime",
    )

    staging = target_dir.with_name(f"{target_dir.name}.staging-{uuid.uuid4().hex[:8]}")
    staging.mkdir(parents=True, exist_ok=False)
    files: dict[str, dict[str, Any]] = {}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _safe_runtime_members(archive)
            for item in members:
                if _cancelled(cancel_check):
                    raise DownloadCancelled("Embedded AI installation cancelled.")
                name = PurePosixPath(item.filename).name
                destination = _safe_child(staging, staging / name)
                with archive.open(item) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output, length=CHUNK_SIZE)
                files[name] = {
                    "size_bytes": destination.stat().st_size,
                    "sha256": _sha256_file(destination),
                }
        marker = {
            "schema_version": 1,
            "version": artifact["version"],
            "archive_sha256": artifact["sha256"],
            "files": files,
        }
        (staging / RUNTIME_MARKER).write_text(
            json.dumps(marker, indent=2, sort_keys=True), encoding="utf-8"
        )
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        staging.replace(target_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return _runtime_marker_state(target_dir, full_verify=True)


def _model_marker_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + MODEL_MARKER_SUFFIX)


def model_state(
    *,
    full_verify: bool = False,
    progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    artifact = model_artifact()
    path = default_model_path()
    marker_path = _model_marker_path(path)
    result = {
        "installed": path.is_file(),
        "verified": False,
        "name": artifact["name"],
        "id": artifact["id"],
        "revision": artifact["revision"],
        "quantization": artifact["quantization"],
        "size_bytes": artifact["size_bytes"],
        "path": path,
    }
    if not path.is_file() or path.stat().st_size != int(artifact["size_bytes"]):
        return result
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return result
    stat_result = path.stat()
    metadata_matches = (
        marker.get("id") == artifact["id"]
        and marker.get("revision") == artifact["revision"]
        and marker.get("sha256") == artifact["sha256"]
        and marker.get("size_bytes") == artifact["size_bytes"]
        and marker.get("mtime_ns") == stat_result.st_mtime_ns
    )
    if not metadata_matches:
        return result
    if full_verify:
        digest = _sha256_file(
            path,
            progress=progress,
            cancel_check=cancel_check,
            phase="verifying_model",
        )
        if digest != artifact["sha256"]:
            return result
    result["verified"] = True
    return result


def install_default_model(
    *,
    progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    """Download and register the immutable default model in private storage."""
    artifact = model_artifact()
    path = default_model_path()
    current = model_state(full_verify=False)
    if not current["verified"]:
        _download_verified(
            artifact,
            path,
            progress=progress,
            cancel_check=cancel_check,
            phase="downloading_model",
        )
        stat_result = path.stat()
        marker = {
            "schema_version": 1,
            "id": artifact["id"],
            "revision": artifact["revision"],
            "license": artifact["license"],
            "size_bytes": artifact["size_bytes"],
            "sha256": artifact["sha256"],
            "mtime_ns": stat_result.st_mtime_ns,
        }
        marker_path = _model_marker_path(path)
        pending_marker = marker_path.with_suffix(marker_path.suffix + ".tmp")
        pending_marker.write_text(json.dumps(marker, indent=2), encoding="utf-8")
        pending_marker.replace(marker_path)

    from app.infrastructure.db import LocalModelRegistry, SessionFactory, init_db

    init_db()
    with SessionFactory() as db:
        rows = list(db.scalars(select(LocalModelRegistry)).all())
        row = next((item for item in rows if item.model_name == artifact["id"]), None)
        for item in rows:
            item.is_active = False
        if row is None:
            row = LocalModelRegistry(model_name=artifact["id"], file_path=str(path))
            db.add(row)
        row.file_path = str(path)
        row.file_size_bytes = int(artifact["size_bytes"])
        row.context_length = 4096
        row.quant_type = str(artifact["quantization"])
        row.is_downloaded = True
        row.is_active = True
        db.commit()
    return model_state(full_verify=False)


def install_embedded_components(
    *,
    progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    """Install the verified runtime when needed, then the default model."""
    runtime = resolve_verified_runtime(full_verify=False)
    if not runtime["verified"]:
        runtime = prepare_runtime_directory(
            private_runtime_dir(), progress=progress, cancel_check=cancel_check
        )
    model = install_default_model(progress=progress, cancel_check=cancel_check)
    return {"runtime_verified": runtime["verified"], "model_verified": model["verified"]}


def hardware_profile(
    *,
    total_ram_bytes: int | None = None,
    available_ram_bytes: int | None = None,
    cpu_threads: int | None = None,
    machine: str | None = None,
) -> dict[str, Any]:
    """Return aggregate hardware capability without exposing process-level details."""
    memory = psutil.virtual_memory()
    total = int(total_ram_bytes if total_ram_bytes is not None else memory.total)
    available = int(available_ram_bytes if available_ram_bytes is not None else memory.available)
    threads = max(1, int(cpu_threads if cpu_threads is not None else (os.cpu_count() or 1)))
    architecture = (machine or platform.machine() or "unknown").lower()
    supported_platform = platform.system() == "Windows" and architecture in {
        "amd64",
        "x86_64",
    }
    ram_gb = round(total / (1024**3), 1)
    available_gb = round(available / (1024**3), 1)
    supported = supported_platform and ram_gb >= 6.0
    recommended = "standard" if supported and ram_gb >= 12.0 and threads >= 6 else "lite"
    reason = (
        "Standard mode fits the detected memory and CPU."
        if recommended == "standard"
        else "Lite mode reduces context and worker pressure for this computer."
    )
    if not supported_platform:
        reason = "The embedded runtime is pinned for Windows x64; use External mode here."
    elif ram_gb < 6.0:
        reason = "Less than 6 GB RAM is not supported for the default embedded model."
    return {
        "ram_gb": ram_gb,
        "available_ram_gb": available_gb,
        "cpu_threads": threads,
        "architecture": architecture,
        "supported": supported,
        "recommended_mode": recommended if supported else "external",
        "reason": reason,
    }


def mode_config(mode: str | None = None) -> dict[str, Any]:
    selected = (mode or settings.local_ai_mode or "standard").strip().lower()
    if selected not in ALL_MODES:
        raise ValueError("Local AI mode must be lite, standard, or external.")
    threads = max(1, os.cpu_count() or 1)
    if selected == "lite":
        return {
            "mode": selected,
            "context_length": 2048,
            "threads": max(1, min(4, threads // 2 or 1)),
            "batch_size": 256,
        }
    if selected == "standard":
        return {
            "mode": selected,
            "context_length": 4096,
            "threads": max(2, min(12, threads - 1 if threads > 2 else threads)),
            "batch_size": 512,
        }
    return {"mode": selected, "context_length": None, "threads": None, "batch_size": None}


def configured_local_endpoint(mode: str | None = None) -> tuple[str, int]:
    """Keep the app-owned embedded endpoint separate from external local servers."""
    selected = mode_config(mode)["mode"]
    if selected == "external":
        return settings.llama_server_host, int(settings.llama_server_port)
    return "127.0.0.1", int(settings.embedded_ai_port)


def public_status() -> dict[str, Any]:
    """Return non-secret embedded runtime health for UI and Copilot."""
    runtime = resolve_verified_runtime(full_verify=False)
    model = model_state(full_verify=False)
    hardware = hardware_profile()
    from app.ai.local_server import local_server_manager
    from app.jobs import service as jobs

    active_rows = [
        row
        for row in jobs.list_job_rows(statuses={"running"}, limit=20)
        if row.kind in {"embedded_ai_install", "embedded_ai_start"}
    ]
    active_job = None
    if active_rows:
        serialized = jobs.serialize_job(active_rows[0])
        active_job = {
            key: serialized.get(key)
            for key in (
                "id",
                "kind",
                "status",
                "message",
                "phase",
                "percent",
                "bytes_completed",
                "total_bytes",
                "elapsed_sec",
            )
            if serialized.get(key) is not None
        }
    server = local_server_manager.get_status()
    configured = mode_config()
    return {
        "status": "success",
        "mode": configured["mode"],
        "autostart": bool(settings.local_ai_autostart),
        "hardware": hardware,
        "runtime": {
            "installed": runtime["installed"],
            "verified": runtime["verified"],
            "version": runtime["version"],
            "source": runtime["source"],
        },
        "model": {
            "installed": model["installed"],
            "verified": model["verified"],
            "name": model["name"],
            "revision": model["revision"],
            "quantization": model["quantization"],
            "size_bytes": model["size_bytes"],
            "license": model_artifact()["license"],
        },
        "server": server,
        "external_endpoint": {
            "host": settings.llama_server_host,
            "port": int(settings.llama_server_port),
        },
        "active_job": active_job,
        "controls": {
            "can_install": (
                configured["mode"] in EMBEDDED_MODES
                and hardware["supported"]
                and active_job is None
            ),
            "can_start": (
                configured["mode"] in EMBEDDED_MODES
                and runtime["verified"]
                and model["verified"]
                and server["status"] == "stopped"
                and active_job is None
            ),
            "can_stop": server["managed"] and server["status"] == "running",
            "can_cancel": bool(active_job),
        },
    }
