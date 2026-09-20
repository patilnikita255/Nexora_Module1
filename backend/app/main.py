"""
FastAPI Application Factory.

Creates and configures the FastAPI app with:
  - CORS middleware
  - API routes
  - Lifespan handler for startup/shutdown
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router, processor
from app.config import ensure_directories, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # --- Startup ---
    settings = get_settings()
    ensure_directories()
    print("=" * 60)
    print("  AI Video Surveillance System — Backend")
    print(f"  YOLO Model     : {settings.yolo_model}")
    print(f"  Confidence     : {settings.yolo_confidence}")
    print(f"  Loitering      : {settings.loitering_threshold_seconds}s threshold")
    print(f"  Intrusion Zone : {settings.intrusion_zone}")
    print(f"  Server         : http://{settings.host}:{settings.port}")
    print(f"  Docs           : http://localhost:{settings.port}/docs")
    print("=" * 60)

    yield

    # --- Shutdown ---
    print("[App] Shutting down...")
    processor.stop()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AI Video Surveillance System",
        description=(
            "Real-time AI-powered surveillance with YOLOv8 object detection, "
            "behavior analysis, and alert management."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — allow frontend to access the API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            settings.frontend_url,
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    app.include_router(router)

    # Static files and Web UI
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Root endpoint serves Web UI if available, else API info
    @app.get("/")
    async def root():
        index_file = static_dir / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return {
            "name": "AI Video Surveillance System",
            "version": "1.0.0",
            "docs": "/docs",
            "status": "/api/status",
        }

    # Dedicated Restricted Area Camera Terminal UI
    @app.get("/restricted")
    @app.get("/restricted-cam")
    async def restricted_cam_page():
        page = static_dir / "restricted_cam.html"
        if page.is_file():
            return FileResponse(page)
        index_file = static_dir / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return {"message": "Restricted Cam UI"}

    return app


# Create the app instance
app = create_app()
