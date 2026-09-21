"""
Configuration module — loads settings from .env using pydantic-settings.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Tuple

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # YOLO
    yolo_model: str = "weights/yolov8n.pt"
    yolo_confidence: float = 0.35
    knife_confidence: float = 0.20
    device: str = "auto"  # auto | cuda | cpu | mps

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Behavior thresholds
    loitering_threshold_seconds: int = 15
    loitering_suspicion_threshold: float = 0.65
    intrusion_zone: str = "0.8,0.0,1.0,1.0"
    unattended_object_seconds: int = 15
    alert_cooldown_seconds: int = 60
    enable_firearm_model: bool = True
    gun_confidence: float = 0.20
    weapon_confirm_frames: int = 1

    # CORS
    frontend_url: str = "http://localhost:8080"

    # Notification: Email (smtplib — stdlib)
    email_notifications_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_to: str = ""  # comma-separated recipients

    # Notification: SMS (Twilio)
    sms_notifications_enabled: bool = False
    twilio_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    alert_sms_to: str = ""  # comma-separated phone numbers

    # Directories
    snapshots_dir: str = "snapshots"
    uploads_dir: str = "uploads"
    weights_dir: str = "weights"

    @model_validator(mode="after")
    def _normalize_paths(self) -> "Settings":
        """
        Resolve all project-relative paths from backend root so the app works
        whether launched from project root or backend directory.
        """
        if not os.path.isabs(self.uploads_dir):
            self.uploads_dir = str((BACKEND_DIR / self.uploads_dir).resolve())
        if not os.path.isabs(self.snapshots_dir):
            self.snapshots_dir = str((BACKEND_DIR / self.snapshots_dir).resolve())
        if not os.path.isabs(self.weights_dir):
            self.weights_dir = str((BACKEND_DIR / self.weights_dir).resolve())
        if not os.path.isabs(self.yolo_model):
            self.yolo_model = str((BACKEND_DIR / self.yolo_model).resolve())
        return self

    @property
    def intrusion_zone_coords(self) -> Tuple[float, float, float, float]:
        """Parse intrusion zone string into (x1, y1, x2, y2) normalized coords."""
        try:
            parts = [float(x.strip()) for x in self.intrusion_zone.split(",")]
        except (TypeError, ValueError):
            return (0.8, 0.0, 1.0, 1.0)

        if len(parts) != 4:
            return (0.8, 0.0, 1.0, 1.0)

        x1, y1, x2, y2 = parts
        if not (0.0 <= x1 <= 1.0 and 0.0 <= y1 <= 1.0 and 0.0 <= x2 <= 1.0 and 0.0 <= y2 <= 1.0):
            return (0.8, 0.0, 1.0, 1.0)
        if x1 >= x2 or y1 >= y2:
            return (0.8, 0.0, 1.0, 1.0)

        return (x1, y1, x2, y2)

    def get_default_zones(self) -> list:
        """Return default multi-zone configuration with restricted and excluded zones."""
        from app.models.schemas import ZoneConfig, ZoneType
        return [
            ZoneConfig(
                id="staff_restricted_corridor",
                name="Staff Only Corridor",
                zone_type=ZoneType.RESTRICTED,
                coords=self.intrusion_zone_coords,
                is_active=True,
            ),
            ZoneConfig(
                id="public_waiting_area",
                name="Public Waiting Area",
                zone_type=ZoneType.EXCLUDED,
                coords=(0.0, 0.0, 0.35, 1.0),
                is_active=True,
            ),
        ]


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


def ensure_directories() -> None:
    """Create required directories if they don't exist."""
    settings = get_settings()
    os.makedirs(settings.snapshots_dir, exist_ok=True)
    os.makedirs(settings.uploads_dir, exist_ok=True)
    os.makedirs(settings.weights_dir, exist_ok=True)