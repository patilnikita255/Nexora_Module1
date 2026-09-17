"""
Alert Manager — generates, stores, and manages alerts.

Features:
  - Creates alert records with snapshots
  - Cooldown-based deduplication
  - In-memory storage with FIFO eviction
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.config import get_settings
from app.models.schemas import Alert, AlertSeverity, AlertType, BehaviorEvent
from app.services.notifier import send_alert_notification


class AlertManager:
    """Manages alert generation, storage, and deduplication."""

    def __init__(self, max_alerts: int = 500) -> None:
        self.alerts: List[Alert] = []
        self.max_alerts = max_alerts
        self._last_trigger_by_key: Dict[Tuple[str, int], float] = {}
        self._settings = get_settings()
        self._cooldown_seconds = self._settings.alert_cooldown_seconds
        self._min_confirmed_frames = 4
        self._duration_thresholds = {
            AlertType.LOITERING: float(self._settings.loitering_threshold_seconds),
            AlertType.INTRUSION: 2.5,
            AlertType.UNATTENDED_OBJECT: float(self._settings.unattended_object_seconds),
            AlertType.SUSPICIOUS_ACTIVITY: 1.0,
        }

        # Ensure snapshots directory exists
        os.makedirs(self._settings.snapshots_dir, exist_ok=True)

    def process_events(
        self,
        events: List[BehaviorEvent],
        frame: Optional[np.ndarray] = None,
        event_frame_counts: Optional[Dict[str, int]] = None,
    ) -> List[Alert]:
        """
        Process behavior events and create alerts (with cooldown).

        Args:
            events: List of behavior events from the analyzer.
            frame: Current video frame for snapshot.

        Returns:
            List of newly created alerts.
        """
        new_alerts: List[Alert] = []
        now = time.time()

        for event in events:
            primary_object_id = self._resolve_primary_object_id(event)
            cooldown_key = (event.event_type.value, primary_object_id)

            confirmed_frames = event.frame_count
            if event_frame_counts is not None:
                confirmed_frames = max(
                    confirmed_frames,
                    event_frame_counts.get(self._event_key(event), 0),
                )

            min_duration = self._duration_thresholds.get(event.event_type, 0.0)
            if confirmed_frames < self._min_confirmed_frames:
                continue
            if event.duration_seconds < min_duration:
                continue

            # Check cooldown
            last_time = self._last_trigger_by_key.get(cooldown_key, 0)
            if now - last_time < self._cooldown_seconds:
                continue

            # Save snapshot
            snapshot_url = None
            if frame is not None:
                snapshot_url = self._save_snapshot(frame)

            # Create alert
            alert = Alert(
                id=str(uuid.uuid4())[:8],
                timestamp=datetime.now(timezone.utc),
                alert_type=event.event_type,
                severity=event.severity,
                message=event.message,
                snapshot_url=snapshot_url,
                objects_involved=[str(oid) for oid in event.involved_objects],
                object_id=str(primary_object_id) if primary_object_id >= 0 else None,
                duration_seconds=round(event.duration_seconds, 1),
                confidence=round(event.confidence, 3),
                triple_lock={
                    "lock1_detection": True,
                    "lock2_behavior": True,
                    "lock3_face_recognition": "pending (placeholder)",
                },
            )

            self.alerts.append(alert)
            new_alerts.append(alert)
            self._last_trigger_by_key[cooldown_key] = now

            # FIFO eviction
            if len(self.alerts) > self.max_alerts:
                self.alerts = self.alerts[-self.max_alerts :]

            print(
                f"[Alert] {event.severity.value.upper()}: {event.message} "
                f"(id={primary_object_id}, frames={confirmed_frames}, duration={event.duration_seconds:.1f}s)"
            )

            # --- Send real notification (email / SMS) via background worker ---
            snapshot_filepath = None
            if snapshot_url:
                snapshot_filepath = os.path.join(
                    self._settings.snapshots_dir,
                    os.path.basename(snapshot_url),
                )
            send_alert_notification(alert, snapshot_path=snapshot_filepath)

        return new_alerts

    def get_alerts(self, limit: int = 50) -> List[Alert]:
        """Get latest alerts, most recent first."""
        return list(reversed(self.alerts[-limit:]))

    def clear_alerts(self) -> int:
        """Clear all alerts. Returns count cleared."""
        count = len(self.alerts)
        self.alerts.clear()
        self._last_trigger_by_key.clear()
        return count

    @staticmethod
    def _resolve_primary_object_id(event: BehaviorEvent) -> int:
        if event.primary_object_id is not None:
            return event.primary_object_id
        if event.involved_objects:
            return event.involved_objects[0]
        return -1

    @staticmethod
    def _event_key(event: BehaviorEvent) -> str:
        primary = AlertManager._resolve_primary_object_id(event)
        return f"{event.event_type.value}:{primary}"

    def _save_snapshot(self, frame: np.ndarray) -> str:
        """Save frame as JPEG snapshot and return the URL path."""
        filename = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
        filepath = os.path.join(self._settings.snapshots_dir, filename)
        cv2.imwrite(filepath, frame)
        return f"/api/snapshots/{filename}"

    @property
    def alert_count(self) -> int:
        return len(self.alerts)
