"""
One-Click Launcher for AI Video Surveillance System.

Usage:
    python run.py

This script:
  1. Sets up the environment paths
  2. Launches the FastAPI surveillance backend
  3. Opens the Web UI in your default browser at http://localhost:8000
"""

import os
import sys
import time
import webbrowser
import threading
import subprocess
from pathlib import Path

# Ensure execution inside the project's virtual environment
ROOT_DIR = Path(__file__).resolve().parent
candidate_venvs = [
    ROOT_DIR / "backend" / "venv" / "Scripts" / "python.exe",
    ROOT_DIR / "backend" / ".venv" / "Scripts" / "python.exe",
    ROOT_DIR / "venv" / "Scripts" / "python.exe",
    ROOT_DIR / ".venv" / "Scripts" / "python.exe",
]
venv_python = next((p for p in candidate_venvs if p.is_file()), None)

if venv_python and Path(sys.executable).resolve() != venv_python.resolve():
    print(f"[Launcher] Launching via virtual environment: {venv_python}")
    sys.exit(subprocess.call([str(venv_python), str(Path(__file__).resolve())] + sys.argv[1:]))

# Set working directory to backend/
BACKEND_DIR = ROOT_DIR / "backend"
if BACKEND_DIR.is_dir():
    os.chdir(str(BACKEND_DIR))
    sys.path.insert(0, str(BACKEND_DIR))
else:
    sys.path.insert(0, str(ROOT_DIR))

def open_browser():
    """Wait briefly for server to bind then open browser."""
    time.sleep(1.8)
    url = "http://localhost:8000"
    print(f"\n[Launcher] Opening browser at: {url}\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

if __name__ == "__main__":
    print("=" * 60)
    print("  AI-BASED SURVEILLANCE SYSTEM")
    print("  Automated Intrusion & Behavior Analysis using YOLO")
    print("=" * 60)
    print("[Launcher] Starting server on http://localhost:8000...")
    print("[Launcher] Press Ctrl+C in this terminal to stop.")
    print("=" * 60)

    # Launch browser in a background thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Run uvicorn server
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
