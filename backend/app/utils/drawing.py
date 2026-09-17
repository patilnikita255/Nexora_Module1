"""
OpenCV drawing helpers for annotating video frames.

Draws bounding boxes, labels, intrusion zones, tracking IDs, and a HUD overlay.
"""

from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np

from app.models.schemas import Detection, TrackedObject


# Color palette (BGR) for different object classes
CLASS_COLORS = {
    "person": (0, 255, 128),       # Green
    "backpack": (255, 165, 0),     # Orange
    "handbag": (255, 165, 0),      # Orange
    "suitcase": (255, 165, 0),     # Orange
    "knife": (0, 0, 255),          # Red
    "cell phone": (255, 255, 0),   # Cyan
    "laptop": (255, 200, 0),       # Light blue
    "bottle": (200, 200, 0),       # Teal
    "cup": (200, 200, 0),          # Teal
    "umbrella": (200, 100, 255),   # Pink
}

DEFAULT_COLOR = (200, 200, 200)  # Gray


def draw_frame_overlay(
    frame: np.ndarray,
    detections: List[Detection],
    tracked_objects: List[TrackedObject],
    intrusion_zone: Tuple[float, float, float, float],
    fps: float,
) -> np.ndarray:
    """
    Draw all overlays on a frame.

    Args:
        frame: BGR image to annotate.
        detections: Raw detections (not used directly — tracked_objects preferred).
        tracked_objects: Tracked objects with IDs and duration.
        intrusion_zone: Normalized zone coordinates (x1, y1, x2, y2).
        fps: Current processing FPS.

    Returns:
        Annotated frame.
    """
    h, w = frame.shape[:2]

    # Draw intrusion zone
    _draw_intrusion_zone(frame, intrusion_zone, w, h)

    # Draw tracked objects with bounding boxes and labels
    for obj in tracked_objects:
        color = CLASS_COLORS.get(obj.class_name, DEFAULT_COLOR)
        bbox = obj.bbox

        # Bounding box
        cv2.rectangle(frame, (bbox.x1, bbox.y1), (bbox.x2, bbox.y2), color, 2)

        # Label background
        label = f"ID:{obj.track_id} {obj.class_name} {obj.confidence:.0%}"
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(
            frame,
            (bbox.x1, bbox.y1 - label_size[1] - 10),
            (bbox.x1 + label_size[0] + 4, bbox.y1),
            color,
            -1,
        )
        cv2.putText(
            frame, label,
            (bbox.x1 + 2, bbox.y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1,
        )

        # Duration tag (if > 3 seconds)
        if obj.duration_seconds > 3:
            dur_label = f"{obj.duration_seconds:.0f}s"
            cv2.putText(
                frame, dur_label,
                (bbox.x1, bbox.y2 + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1,
            )

    # HUD overlay
    _draw_hud(frame, fps, len(tracked_objects))

    return frame


def _draw_intrusion_zone(
    frame: np.ndarray,
    zone: Tuple[float, float, float, float],
    w: int,
    h: int,
) -> None:
    """Draw semi-transparent red intrusion zone overlay."""
    x1 = int(zone[0] * w)
    y1 = int(zone[1] * h)
    x2 = int(zone[2] * w)
    y2 = int(zone[3] * h)

    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 200), -1)
    cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)

    # Zone border
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)

    # Label
    cv2.putText(
        frame, "RESTRICTED ZONE",
        (x1 + 8, y1 + 24),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2,
    )


def _draw_hud(frame: np.ndarray, fps: float, obj_count: int) -> None:
    """Draw heads-up display with FPS and object count."""
    h, w = frame.shape[:2]

    # Semi-transparent bar at the top
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 36), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    # Title
    cv2.putText(
        frame, "AI SURVEILLANCE",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 200), 2,
    )

    # FPS
    cv2.putText(
        frame, f"FPS: {fps:.1f}",
        (w - 180, 25),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
    )

    # Object count
    cv2.putText(
        frame, f"Objects: {obj_count}",
        (w - 90, 25),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1,
    )
