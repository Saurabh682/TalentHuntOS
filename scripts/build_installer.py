#!/usr/bin/env python3
"""
TalentHunt OS - Desktop Distribution Build Script (Phase 9)

Automates the PyInstaller bundling process for TalentHunt OS.
Bundles the NiceGUI desktop application and the complete pinned llama.cpp runtime
into a standalone distribution directory. Model weights remain a verified first-run
download so the installer stays manageable.

Usage:
    python scripts/build_installer.py [options]

Options:
    --clean             Clean previous build and dist directories before building.
    --llama-runtime-dir PATH
                        Explicit verified llama.cpp runtime directory.
    --no-runtime-download
                        Fail instead of downloading the pinned build runtime.
    --dist-dir PATH     Output directory for the distribution (default: dist).
    --console           Keep terminal console window visible for debugging (default: windowed).
    --no-auto-install   Do not auto-install PyInstaller if missing.
"""

import argparse
import importlib.util
import logging
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import List, Optional

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("talenthunt.build_installer")

# Determine base directory (TalentHuntOS root)
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
APP_ENTRY = BASE_DIR / "app" / "main.py"
APP_NAME = "TalentHuntOS"


def check_and_install_pyinstaller(auto_install: bool = True) -> bool:
    """Ensure PyInstaller is installed in the current environment."""
    if importlib.util.find_spec("PyInstaller") is not None:
        logger.info("PyInstaller is installed.")
        return True

    if not auto_install:
        logger.error("PyInstaller is not installed. Please run 'pip install pyinstaller'.")
        return False

    logger.info("PyInstaller not found. Installing via pip...")
    try:
        import subprocess

        subprocess_cmd = [sys.executable, "-m", "pip", "install", "pyinstaller"]
        subprocess.run(subprocess_cmd, check=True, capture_output=True, text=True)
        logger.info("Successfully installed PyInstaller.")
        return True
    except Exception as err:
        logger.error("Failed to auto-install PyInstaller: %s", err)
        return False


def get_nicegui_dir() -> Path:
    """Locate the installed NiceGUI package directory to collect static assets."""
    try:
        import nicegui

        nicegui_path = Path(nicegui.__file__).resolve().parent
        logger.info("Found NiceGUI package at: %s", nicegui_path)
        return nicegui_path
    except ImportError:
        logger.error("NiceGUI is not installed in the active environment.")
        sys.exit(1)


def prepare_build_runtime(
    explicit_path: Optional[str] = None, *, allow_download: bool = True
) -> Optional[Path]:
    """Resolve or install only the complete runtime pinned by the app manifest."""
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    from app.ai.embedded_runtime import (
        prepare_runtime_directory,
        runtime_directory_state,
        source_runtime_dir,
    )

    if explicit_path:
        candidate = Path(explicit_path).resolve()
        if candidate.is_file():
            candidate = candidate.parent
        state = runtime_directory_state(candidate, full_verify=True)
        if not state["verified"]:
            raise RuntimeError(
                "The supplied llama.cpp directory is incomplete or does not match "
                "TalentHunt's pinned runtime manifest."
            )
        logger.info("Using verified runtime directory: %s", candidate)
        return candidate

    target = source_runtime_dir()
    if runtime_directory_state(target, full_verify=True)["verified"]:
        logger.info("Using verified project runtime: %s", target)
        return target
    if not allow_download:
        logger.error(
            "The pinned llama.cpp runtime is absent. Re-run without "
            "--no-runtime-download to fetch and verify it."
        )
        return None

    logger.info("Downloading and verifying the pinned llama.cpp build runtime...")
    state = prepare_runtime_directory(target)
    if not state["verified"]:
        raise RuntimeError("The pinned llama.cpp build runtime failed verification.")
    return target


def clean_build_dirs(dist_dir: Path, build_dir: Path, spec_file: Path) -> None:
    """Clean existing build artifacts and dist directory."""
    logger.info("Cleaning previous build artifacts...")
    if dist_dir.exists():
        logger.info("Removing dist directory: %s", dist_dir)
        shutil.rmtree(dist_dir, ignore_errors=True)

    if build_dir.exists():
        logger.info("Removing build directory: %s", build_dir)
        shutil.rmtree(build_dir, ignore_errors=True)

    if spec_file.exists():
        logger.info("Removing old spec file: %s", spec_file)
        try:
            spec_file.unlink()
        except OSError:
            pass


def get_hidden_imports() -> List[str]:
    """List all explicit hidden imports required for NiceGUI, Uvicorn, FastAPI, SQLAlchemy, etc."""
    return [
        # NiceGUI & Uvicorn core
        "nicegui",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # FastAPI / Starlette / Web framework
        "fastapi",
        "starlette",
        "starlette.responses",
        "starlette.routing",
        "starlette.staticfiles",
        "engineio",
        "socketio",
        "websockets",
        "jinja2",
        # Database & ORM
        "sqlalchemy",
        "sqlalchemy.ext.asyncio",
        "sqlite3",
        "alembic",
        # Application Modules
        "app",
        "app.main",
        "app.config",
        "app.config.settings",
        "app.config.constants",
        "app.ui",
        "app.ui.pages",
        "app.ui.panels",
        "app.ai",
        "app.ai.embedded_jobs",
        "app.ai.embedded_runtime",
        "app.ai.engine",
        "app.ai.local_server",
        "app.ai.providers",
        "app.candidates",
        "app.candidates.models",
        "app.candidates.search",
        "app.candidates.rag",
        "app.candidates.service",
        "app.hunts",
        "app.analytics",
        "app.analytics.service",
        "app.analytics.reports",
        "app.communications",
        "app.communications.service",
        "app.communications.email_service",
        "app.communications.outreach_service",
        "app.copilot",
        "app.voice",
        "app.voice.audio_bridge",
        "app.agents",
        "app.actions",
        "app.actions.ai_runtime",
        "app.infrastructure",
        "app.intelligence",
        # Config & Utils
        "pydantic",
        "pydantic_settings",
        "keyring",
        "cryptography",
        "psutil",
    ]


def build_pyinstaller_args(
    dist_dir: Path,
    build_dir: Path,
    nicegui_dir: Path,
    runtime_dir: Optional[Path],
    console: bool = False,
) -> List[str]:
    """Construct argument list for PyInstaller invocation."""
    sep = os.pathsep

    args = [
        str(APP_ENTRY),
        f"--name={APP_NAME}",
        "--onedir",  # Desktop distribution directory mode
        "--noconfirm",
        "--clean",
        f"--distpath={dist_dir.parent}",
        f"--workpath={build_dir}",
        f"--specpath={BASE_DIR}",
    ]

    # Console / Windowed mode
    if console:
        args.append("--console")
    else:
        args.append("--windowed")

    # Add NiceGUI static files data directory
    args.append(f"--add-data={nicegui_dir}{sep}nicegui")

    # Add app directory as package data
    args.append(f"--add-data={BASE_DIR / 'app'}{sep}app")

    # Add alembic configuration if present
    alembic_ini = BASE_DIR / "alembic.ini"
    if alembic_ini.exists():
        args.append(f"--add-data={alembic_ini}{sep}.")

    # The complete verified runtime is copied beside the built executable later.
    # Adding only llama-server.exe would omit its required llama/ggml DLLs.
    _ = runtime_dir

    # Add all hidden imports
    for item in get_hidden_imports():
        args.append(f"--hidden-import={item}")

    return args


def create_windows_launcher(dist_app_dir: Path) -> None:
    """Create a convenient batch launcher in the distribution directory for Windows."""
    if platform.system() == "Windows":
        bat_file = dist_app_dir / "run_talenthunt.bat"
        content = (
            "@echo off\n"
            "title TalentHunt OS Desktop\n"
            "echo Starting TalentHunt OS...\n"
            'start "" "%~dp0TalentHuntOS.exe"\n'
        )
        try:
            bat_file.write_text(content, encoding="utf-8")
            logger.info("Created launcher batch file: %s", bat_file)
        except Exception as exc:
            logger.warning("Failed to create launcher batch file: %s", exc)


def create_readme(dist_app_dir: Path, has_runtime: bool) -> None:
    """Create README_DIST.txt inside distribution directory."""
    content = f"""========================================================================
TalentHunt OS - Desktop Distribution
========================================================================

Version: 0.1.0
Build Date: {importlib.import_module('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

How to Run:
------------------------------------------------------------------------
1. Double-click `TalentHuntOS.exe` (or run `run_talenthunt.bat`).
2. TalentHunt OS will launch and open the web dashboard in your browser.

Embedded Local Copilot:
------------------------------------------------------------------------
{"[INSTALLED] The complete pinned llama.cpp runtime is bundled and verified." if has_runtime else "[MISSING] The verified llama.cpp runtime was not bundled; rebuild the distribution."}
The IBM Granite 4.1 3B Q4_K_M model is not embedded in the installer.
Open Settings and select Install once to download and verify about 2.1 GB.
After that first download, the embedded Copilot can run fully offline.

Directory Contents:
------------------------------------------------------------------------
- `TalentHuntOS.exe` : Main Application Executable
- `llama-runtime/`    : Verified local LLM inference engine and required DLLs
- `_internal/`        : Python runtime and compiled library dependencies
- `run_talenthunt.bat`: Windows quick launcher script

========================================================================
"""
    readme_file = dist_app_dir / "README_DIST.txt"
    try:
        readme_file.write_text(content, encoding="utf-8")
        logger.info("Created distribution README: %s", readme_file)
    except Exception as exc:
        logger.warning("Failed to create distribution README: %s", exc)


def calculate_dir_size_mb(directory: Path) -> float:
    """Calculate total size of directory in Megabytes."""
    total_bytes = 0
    if directory.exists():
        for path in directory.rglob("*"):
            if path.is_file():
                total_bytes += path.stat().st_size
    return round(total_bytes / (1024 * 1024), 2)


def main() -> None:
    """Main build execution flow."""
    parser = argparse.ArgumentParser(
        description="TalentHunt OS - PyInstaller Bundler Script (Phase 9)"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build and dist directories before starting build",
    )
    parser.add_argument(
        "--llama-runtime-dir",
        "--llama-path",
        dest="llama_runtime_dir",
        type=str,
        default=None,
        help="Explicit verified runtime directory (--llama-path remains an alias)",
    )
    parser.add_argument(
        "--no-runtime-download",
        action="store_true",
        help="Fail instead of downloading the pinned llama.cpp build runtime",
    )
    parser.add_argument(
        "--dist-dir",
        type=str,
        default="dist",
        help="Target distribution output directory (relative or absolute)",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Build with terminal console window enabled (for debugging)",
    )
    parser.add_argument(
        "--no-auto-install",
        action="store_true",
        help="Do not auto-install PyInstaller if not found",
    )

    args = parser.parse_args()

    logger.info("==================================================")
    logger.info(" Starting TalentHunt OS Desktop Bundler (Phase 9) ")
    logger.info("==================================================")

    # 1. Ensure PyInstaller is installed
    if not check_and_install_pyinstaller(auto_install=not args.no_auto_install):
        sys.exit(1)

    # 2. Locate components
    nicegui_dir = get_nicegui_dir()
    try:
        runtime_dir = prepare_build_runtime(
            args.llama_runtime_dir,
            allow_download=not args.no_runtime_download,
        )
    except Exception as exc:
        logger.error("Unable to prepare the embedded AI runtime: %s", exc)
        sys.exit(1)
    if runtime_dir is None:
        sys.exit(1)

    # 3. Setup paths
    dist_root = Path(args.dist_dir).resolve() if Path(args.dist_dir).is_absolute() else (BASE_DIR / args.dist_dir).resolve()
    dist_app_dir = dist_root / APP_NAME
    build_dir = BASE_DIR / "build"
    spec_file = BASE_DIR / f"{APP_NAME}.spec"

    if args.clean:
        clean_build_dirs(dist_root, build_dir, spec_file)

    # 4. Construct PyInstaller Command
    pyinstaller_args = build_pyinstaller_args(
        dist_dir=dist_app_dir,
        build_dir=build_dir,
        nicegui_dir=nicegui_dir,
        runtime_dir=runtime_dir,
        console=args.console,
    )

    logger.info("Invoking PyInstaller with arguments:")
    for arg in pyinstaller_args:
        logger.info("  %s", arg)

    # 5. Run PyInstaller
    import PyInstaller.__main__

    try:
        PyInstaller.__main__.run(pyinstaller_args)
        logger.info("PyInstaller bundling process completed.")
    except Exception as exc:
        logger.error("PyInstaller build failed: %s", exc)
        sys.exit(1)

    # 6. Copy and re-verify the complete runtime beside the executable.
    dist_runtime_dir = dist_app_dir / "llama-runtime"
    try:
        if dist_runtime_dir.exists():
            shutil.rmtree(dist_runtime_dir)
        shutil.copytree(runtime_dir, dist_runtime_dir)
        from app.ai.embedded_runtime import runtime_directory_state

        if not runtime_directory_state(dist_runtime_dir, full_verify=True)["verified"]:
            raise RuntimeError("Copied runtime failed final distribution verification.")
        logger.info("Bundled verified llama.cpp runtime: %s", dist_runtime_dir)
    except Exception as exc:
        logger.error("Failed to bundle the complete llama.cpp runtime: %s", exc)
        sys.exit(1)

    # 7. Post-build assets
    create_windows_launcher(dist_app_dir)
    create_readme(dist_app_dir, has_runtime=True)

    # 8. Report results
    size_mb = calculate_dir_size_mb(dist_app_dir)
    logger.info("==================================================")
    logger.info(" BUILD SUCCESSFUL! ")
    logger.info("==================================================")
    logger.info(" Output Directory: %s", dist_app_dir)
    logger.info(" App Executable:   %s", dist_app_dir / f"{APP_NAME}.exe" if platform.system() == "Windows" else dist_app_dir / APP_NAME)
    logger.info(" Total Size:       %s MB", size_mb)
    logger.info("==================================================")


if __name__ == "__main__":
    main()
