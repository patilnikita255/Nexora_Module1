"""
Pydantic schemas for API request/response models.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(str, Enum):
    LOITERING = "loitering"
    INTRUSION = "intrusion"
    UNATTENDED_OBJECT = "unattended_object"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"


# ---------------------------------------------------------------------------
# Detection Models
# ---------------------------------------------------------------------------

class BBox(BaseModel):
    """Bounding box in pixel coordinates."""
    x1: int
    y1: int
    x2: int
    y2: int


class Detection(BaseModel):
    """Single object detection from YOLO."""
    class_name: str
    confidence: float
    bbox: BBox
    center_x: int
    center_y: int


class TrackedObject(BaseModel):
    """Detection with persistent tracking info."""
    track_id: int
    class_name: str
    confidence: float
    bbox: BBox
    center_x: int
    center_y: int
    duration_seconds: float = 0.0
    first_seen: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Behavior / Alert Models
# ---------------------------------------------------------------------------

class BehaviorEvent(BaseModel):
    """A detected suspicious behavior."""
    event_type: AlertType
    severity: AlertSeverity
    message: str
    involved_objects: List[int] = Field(default_factory=list)
    zone: Optional[str] = None
    primary_object_id: Optional[int] = None
    duration_seconds: float = 0.0
    confidence: float = 0.0
    frame_count: int = 0


class Alert(BaseModel):
    """An alert record."""
    id: str
    timestamp: datetime
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    snapshot_url: Optional[str] = None
    objects_involved: List[str] = Field(default_factory=list)
    object_id: Optional[str] = None
    duration_seconds: float = 0.0
    confidence: float = 0.0
    triple_lock: dict = Field(default_factory=lambda: {
        "lock1_detection": True,
        "lock2_behavior": True,
        "lock3_face_recognition": "skipped (placeholder)"
    })


# ---------------------------------------------------------------------------
# API Models
# ---------------------------------------------------------------------------

class SystemStatus(BaseModel):
    """Current system status."""
    is_running: bool = False
    fps: float = 0.0
    frame_count: int = 0
    object_count: int = 0
    alert_count: int = 0
    uptime_seconds: float = 0.0
    video_source: Optional[str] = None


class StartRequest(BaseModel):
    """Request body for starting processing."""
    source: Optional[str] = None


class FrameMetadata(BaseModel):
    """Metadata for the current frame."""
    detections: List[Detection] = Field(default_factory=list)
    tracked_objects: List[TrackedObject] = Field(default_factory=list)
    object_count: int = 0
    fps: float = 0.0
    frame_number: int = 0


class ConfigResponse(BaseModel):
    """Current configuration response."""
    yolo_model: str
    yolo_confidence: float
    loitering_threshold_seconds: int
    intrusion_zone: Tuple[float, float, float, float]
    unattended_object_seconds: int
    alert_cooldown_seconds: int
