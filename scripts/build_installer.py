#!/usr/bin/env python3
"""
TalentHunt OS - Desktop Distribution Build Script (Phase 9)

Automates the PyInstaller bundling process for TalentHunt OS.
Bundles the NiceGUI web/desktop application and the local `llama-server.exe` AI binary
into a single standalone desktop distribution directory.

Usage:
    python scripts/build_installer.py [options]

Options:
    --clean             Clean previous build and dist directories before building.
    --llama-path PATH   Explicit path to llama-server.exe binary.
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
        result = subprocess.run(subprocess_cmd, check=True, capture_output=True, text=True)
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


def find_llama_server(explicit_path: Optional[str] = None) -> Optional[Path]:
    """
    Search for llama-server.exe across explicit path, project folders, system paths, and PATH.
    """
    binary_name = "llama-server.exe" if platform.system() == "Windows" else "llama-server"

    # 1. User specified path
    if explicit_path:
        path = Path(explicit_path).resolve()
        if path.exists() and path.is_file():
            logger.info("Using user-specified llama-server binary: %s", path)
            return path
        logger.warning("Specified llama-server path does not exist: %s", explicit_path)

    # 2. Project local directories
    candidate_paths = [
        BASE_DIR / "bin" / binary_name,
        BASE_DIR / "models" / binary_name,
        BASE_DIR / binary_name,
        Path("C:/llama.cpp") / binary_name,
        Path("C:/tools") / binary_name,
        Path("/usr/local/bin") / binary_name,
    ]

    for candidate in candidate_paths:
        if candidate.exists() and candidate.is_file():
            logger.info("Found llama-server binary at: %s", candidate)
            return candidate

    # 3. Search in system PATH
    found_in_path = shutil.which("llama-server") or shutil.which("llama-server.exe")
    if found_in_path:
        path = Path(found_in_path).resolve()
        logger.info("Found llama-server binary in PATH: %s", path)
        return path

    logger.warning("llama-server binary was not found in standard locations.")
    return None


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
        "app.infrastructure",
        "app.intelligence",
        # Config & Utils
        "pydantic",
        "pydantic_settings",
        "keyring",
        "cryptography",
    ]


def build_pyinstaller_args(
    dist_dir: Path,
    build_dir: Path,
    nicegui_dir: Path,
    llama_path: Optional[Path],
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

    # Add llama-server.exe binary if located
    if llama_path:
        args.append(f"--add-binary={llama_path}{sep}.")

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


def create_readme(dist_app_dir: Path, has_llama: bool) -> None:
    """Create README_DIST.txt inside distribution directory."""
    binary_name = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
    content = f"""========================================================================
TalentHunt OS - Desktop Distribution
========================================================================

Version: 0.1.0
Build Date: {importlib.import_module('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

How to Run:
------------------------------------------------------------------------
1. Double-click `TalentHuntOS.exe` (or run `run_talenthunt.bat`).
2. TalentHunt OS will launch and open the web dashboard in your browser.

Local AI Engine (llama-server):
------------------------------------------------------------------------
{"[INSTALLED] `llama-server.exe` is bundled with this distribution." if has_llama else f"[MISSING] `{binary_name}` was not bundled automatically. Place `{binary_name}` in this directory for offline AI functionality."}

Directory Contents:
------------------------------------------------------------------------
- `TalentHuntOS.exe` : Main Application Executable
- `llama-server.exe`  : Local LLM Inference Engine (if bundled)
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
        "--llama-path",
        type=str,
        default=None,
        help="Explicit path to llama-server.exe binary",
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
    llama_path = find_llama_server(args.llama_path)

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
        llama_path=llama_path,
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

    # 6. Post-build handling: Ensure llama-server is in dist_app_dir
    binary_name = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
    dist_llama_target = dist_app_dir / binary_name

    if llama_path and llama_path.exists():
        if not dist_llama_target.exists():
            logger.info("Copying %s to distribution directory: %s", binary_name, dist_llama_target)
            try:
                shutil.copy2(llama_path, dist_llama_target)
            except Exception as exc:
                logger.warning("Failed to copy llama-server to dist directory: %s", exc)
        else:
            logger.info("Verified %s in distribution directory.", binary_name)
    else:
        logger.warning(
            "Note: %s was not bundled. Add it to %s manually.",
            binary_name,
            dist_app_dir,
        )

    # 7. Post-build assets
    create_windows_launcher(dist_app_dir)
    create_readme(dist_app_dir, has_llama=(llama_path is not None and llama_path.exists()))

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
