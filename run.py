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
from pathlib import Path

# Set working directory to backend/
ROOT_DIR = Path(__file__).resolve().parent
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
