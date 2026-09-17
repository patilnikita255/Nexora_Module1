"""
API Routes — all REST endpoints for the surveillance system.

Endpoints:
  POST /api/upload     — Upload a video file and start processing
  POST /api/start      — Start processing an already-uploaded video
  POST /api/stop       — Stop processing
  GET  /api/status     — System status (FPS, counts, uptime)
  GET  /api/frame      — Latest frame metadata (detections)
  GET  /api/video_feed — MJPEG streaming response
  GET  /api/alerts     — Get alert list
  DELETE /api/alerts   — Clear all alerts
  GET  /api/snapshots/{filename} — Serve snapshot image
  GET  /api/config     — Current configuration
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse

from app.config import get_settings
from app.models.schemas import (
    ConfigResponse,
    FrameMetadata,
    SystemStatus,
)
from app.services.video_processor import VideoProcessor

router = APIRouter(prefix="/api")

# Global video processor instance
processor = VideoProcessor()


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """
    Upload a video file and automatically start processing it.
    File is saved first, then processing starts in a background thread.
    This endpoint returns immediately after saving the file.
    """
    settings = get_settings()

    # Validate file extension
    allowed_extensions = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Allowed: {', '.join(allowed_extensions)}",
        )

    # Save uploaded file
    os.makedirs(settings.uploads_dir, exist_ok=True)
    file_path = os.path.join(settings.uploads_dir, file.filename)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    file_size_mb = len(content) / (1024 * 1024)
    print(f"[Upload] Saved: {file.filename} ({file_size_mb:.1f} MB)")

    # Start processing in background thread — does NOT block this response
    success = processor.start(file_path)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to open the uploaded video file. Is it a valid video?",
        )

    return {
        "message": "Video uploaded and processing started",
        "filename": file.filename,
        "size_mb": round(file_size_mb, 2),
    }


@router.post("/start")
async def start_processing(source: Optional[str] = None):
    """
    Start processing a video file (must already exist in uploads/).
    If no source specified, uses the most recently uploaded file.
    """
    settings = get_settings()

    if source:
        video_path = source
    else:
        # Find most recent file in uploads/
        uploads = settings.uploads_dir
        if not os.path.isdir(uploads):
            raise HTTPException(status_code=400, detail="No videos uploaded yet.")

        files = [
            os.path.join(uploads, f)
            for f in os.listdir(uploads)
            if os.path.isfile(os.path.join(uploads, f))
            and not f.startswith(".")
        ]
        if not files:
            raise HTTPException(status_code=400, detail="No videos uploaded yet.")

        video_path = max(files, key=os.path.getmtime)

    success = processor.start(video_path)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to open video: {video_path}",
        )

    return {
        "message": "Processing started",
        "source": os.path.basename(video_path),
    }


@router.post("/stop")
async def stop_processing():
    """Stop video processing."""
    processor.stop()
    return {"message": "Processing stopped"}


@router.get("/status")
async def get_status():
    """Get current system status including FPS, object count, alerts."""
    status = processor.get_status()
    # Add init_error to response if pipeline failed to start
    result = status.model_dump()
    if processor.init_error:
        result["init_error"] = processor.init_error
    return result


@router.get("/frame", response_model=FrameMetadata)
async def get_frame_metadata():
    """Get detection metadata for the latest processed frame."""
    return processor.get_frame_metadata()


@router.get("/video_feed")
async def video_feed():
    """
    MJPEG video stream endpoint.
    Use as <img src="/api/video_feed" /> in the frontend.
    """
    if not processor.is_running:
        raise HTTPException(status_code=503, detail="No video is being processed.")

    return StreamingResponse(
        processor.generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/alerts")
async def get_alerts(limit: int = Query(default=50, ge=1, le=500)):
    """Get latest alerts, most recent first."""
    alerts = processor.alert_manager.get_alerts(limit=limit)
    return {"alerts": alerts, "total": processor.alert_manager.alert_count}


@router.delete("/alerts")
async def clear_alerts():
    """Clear all alerts."""
    count = processor.alert_manager.clear_alerts()
    return {"message": f"Cleared {count} alerts"}


@router.get("/snapshots/{filename}")
async def get_snapshot(filename: str):
    """Serve a snapshot image."""
    settings = get_settings()
    filepath = os.path.join(settings.snapshots_dir, filename)

    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return FileResponse(filepath, media_type="image/jpeg")


@router.get("/config", response_model=ConfigResponse)
async def get_config():
    """Get current system configuration."""
    settings = get_settings()
    return ConfigResponse(
        yolo_model=settings.yolo_model,
        yolo_confidence=settings.yolo_confidence,
        loitering_threshold_seconds=settings.loitering_threshold_seconds,
        intrusion_zone=settings.intrusion_zone_coords,
        unattended_object_seconds=settings.unattended_object_seconds,
        alert_cooldown_seconds=settings.alert_cooldown_seconds,
    )
