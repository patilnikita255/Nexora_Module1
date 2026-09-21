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
import time
from typing import Optional

import cv2
from fastapi import APIRouter, File, UploadFile, HTTPException, Query, Form
from fastapi.responses import StreamingResponse, FileResponse

from app.config import get_settings
from app.models.schemas import (
    AlertType,
    ConfigResponse,
    FrameMetadata,
    SystemStatus,
    ZoneConfig,
    ZoneListResponse,
)
from app.services.video_processor import VideoProcessor

router = APIRouter(prefix="/api")

# Global video processor instance
processor = VideoProcessor()


@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    mode: str = Form(default="main"),
):
    """
    Upload a video file and automatically start processing it.
    File is saved first, then processing starts in a background thread.
    Mode: 'main' (weapons & unattended objects only) or 'restricted' (perimeter intrusion only).
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

    # Save uploaded file with timestamp to prevent overwriting active playing files
    os.makedirs(settings.uploads_dir, exist_ok=True)
    safe_filename = os.path.basename(file.filename or "uploaded_video.mp4")
    name_part, ext_part = os.path.splitext(safe_filename)
    timestamp_tag = int(time.time() * 1000)
    storage_filename = f"{name_part}_{timestamp_tag}{ext_part}"
    file_path = os.path.join(settings.uploads_dir, storage_filename)

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty.",
        )

    with open(file_path, "wb") as f:
        f.write(content)
        f.flush()

    file_size_mb = len(content) / (1024 * 1024)
    print(f"[Upload] Saved: {storage_filename} ({file_size_mb:.1f} MB) [Original: {safe_filename}] [Mode: {mode}]")

    # Validate that OpenCV can actually open and read this video before disrupting current feed
    test_cap = cv2.VideoCapture(file_path)
    can_open = test_cap.isOpened()
    can_read = False
    if can_open:
        can_read, _ = test_cap.read()
    test_cap.release()

    if not can_open or not can_read:
        try:
            os.remove(file_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=400,
            detail="Uploaded file could not be decoded as a valid video. Please ensure it is a valid video file (e.g. MP4/H.264).",
        )

    # Start processing in background thread
    success = processor.start(file_path, mode=mode)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to launch video processing pipeline.",
        )

    return {
        "message": "Video uploaded and processing started",
        "filename": safe_filename,
        "mode": mode,
        "size_mb": round(file_size_mb, 2),
    }


@router.post("/start")
async def start_processing(source: Optional[str] = None, mode: str = "main"):
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

    success = processor.start(video_path, mode=mode)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to open video: {video_path}",
        )

    return {
        "message": "Processing started",
        "mode": mode,
        "source": os.path.basename(video_path),
    }


@router.post("/webcam")
async def start_webcam(camera_id: int = 0, mode: str = "main"):
    """
    Start processing from a live camera / webcam.
    Defaults to camera index 0.
    """
    success = processor.start(camera_id, mode=mode)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to open camera (index {camera_id}). Please ensure a webcam is connected and accessible.",
        )
    return {
        "message": "Live camera processing started",
        "mode": mode,
        "source": f"Webcam {camera_id}",
    }


@router.post("/stop")
async def stop_processing():
    """Stop video processing."""
    processor.stop()
    return {"message": "Processing stopped"}


@router.get("/status")
async def get_status(camera: Optional[str] = Query(default=None)):
    """Get current system status including FPS, object count, alerts."""
    status = processor.get_status(mode=camera)
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
async def video_feed(mode: str = "main"):
    """
    MJPEG video stream endpoint.
    Serves live surveillance stream or standby feed seamlessly without HTTP 503 failures.
    """
    return StreamingResponse(
        processor.generate_mjpeg(mode=mode),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/alerts")
async def get_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    camera: Optional[str] = Query(default=None),
    dashboard: Optional[str] = Query(default=None),
    type: Optional[str] = Query(default=None),
    types: Optional[str] = Query(default=None),
):
    """
    Get latest alerts filtered by dashboard, camera, or explicit types.

    Filters:
      - dashboard='general' or camera='main':
          Dashboard 1: Weapon & Unauthorized-Object Monitor (excludes Intrusion).
      - dashboard='restricted' or camera='restricted':
          Dashboard 2: Restricted Area Security Dashboard (Shows EVERYTHING: Intrusion + Weapon + Unattended Object).
      - type/types='weapon,unattended' vs 'intrusion,weapon,unattended':
          Direct query over shared alert stream.
    """
    filter_mode = (dashboard or camera or "").strip().lower()
    type_query = type or types

    target_types = None
    if type_query:
        req_types = set()
        for t in type_query.split(","):
            t_norm = t.strip().lower()
            if t_norm in ("weapon", "weapon_detected", "weapons"):
                req_types.add(AlertType.WEAPON_DETECTED)
            elif t_norm in ("unattended", "unattended_object", "bag", "bags"):
                req_types.add(AlertType.UNATTENDED_OBJECT)
            elif t_norm in ("intrusion", "zone", "perimeter"):
                req_types.add(AlertType.INTRUSION)
            elif t_norm in ("loitering", "loiter", "pacing"):
                req_types.add(AlertType.LOITERING)
        if req_types:
            target_types = req_types

    if target_types is None:
        if filter_mode in ("main", "general", "open_area"):
            # Dashboard 1: weapons, unattended objects, and loitering
            target_types = {
                AlertType.WEAPON_DETECTED,
                AlertType.UNATTENDED_OBJECT,
                AlertType.LOITERING,
            }
        elif filter_mode in ("restricted", "security"):
            # Dashboard 2: complete picture (intrusion + weapon + unattended + loitering)
            target_types = {
                AlertType.INTRUSION,
                AlertType.WEAPON_DETECTED,
                AlertType.UNATTENDED_OBJECT,
                AlertType.LOITERING,
            }

    alerts = processor.alert_manager.get_alerts(limit=limit, alert_types=target_types)
    return {"alerts": alerts, "total": len(alerts)}



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
        zones=processor.get_zones(),
    )


@router.get("/zones", response_model=ZoneListResponse)
async def get_zones():
    """Get all configured surveillance zones (restricted, excluded, monitored)."""
    zones = processor.get_zones()
    return ZoneListResponse(zones=zones, total=len(zones))


@router.post("/zones")
async def add_or_update_zone(zone: ZoneConfig):
    """
    Create or update a surveillance zone.
    Zone types:
      - 'restricted': raises intrusion alarms
      - 'excluded': waiting area / public zone (suppresses intrusion alarms)
      - 'monitored': informational tracking zone
    """
    processor.add_zone(zone)
    return {"message": f"Zone '{zone.name}' successfully configured", "zone": zone}


@router.delete("/zones/{zone_id}")
async def delete_zone(zone_id: str):
    """Delete a surveillance zone by ID."""
    removed = processor.remove_zone(zone_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")
    return {"message": f"Zone '{zone_id}' successfully removed"}
