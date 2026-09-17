"""
Rule-based behavior analysis engine.

Detects suspicious behaviors:
  - Loitering: person present for too long
  - Intrusion: person enters a restricted zone
  - Unattended Object: bag/suitcase without nearby person

Implements simplified "Triple-Lock Logic":
  Lock 1: Object detected (YOLO)
  Lock 2: Suspicious behavior confirmed (rules)
  Lock 3: Face recognition (placeholder — always passes)
"""

from __future__ import annotations

import time
from typing import Dict, List, Set, Tuple

from app.config import get_settings
from app.models.schemas import (
    AlertSeverity,
    AlertType,
    BehaviorEvent,
    TrackedObject,
)


class BehaviorAnalyzer:
    """Analyzes tracked objects for suspicious behaviors."""

    def __init__(self) -> None:
        settings = get_settings()
        self.loitering_threshold = settings.loitering_threshold_seconds
        self.intrusion_zone = settings.intrusion_zone_coords
        self.unattended_threshold = settings.unattended_object_seconds
        self.intrusion_delay_seconds = 2.5
        self.unattended_person_distance_px = 150.0

        # Temporal state stores for stable behavior confirmation.
        self._loitering_entry_time: Dict[int, float] = {}
        self._loitering_persistence: Dict[int, int] = {}

        self._intrusion_entry_time: Dict[int, float] = {}
        self._intrusion_persistence: Dict[int, int] = {}

        self._unattended_start_time: Dict[int, float] = {}
        self._unattended_persistence: Dict[int, int] = {}

    def reset(self) -> None:
        """Reset all temporal state (called when a new video starts)."""
        self._loitering_entry_time.clear()
        self._loitering_persistence.clear()
        self._intrusion_entry_time.clear()
        self._intrusion_persistence.clear()
        self._unattended_start_time.clear()
        self._unattended_persistence.clear()

    def analyze(
        self,
        tracked_objects: List[TrackedObject],
        frame_width: int,
        frame_height: int,
    ) -> List[BehaviorEvent]:
        """
        Analyze tracked objects for suspicious behaviors.

        Args:
            tracked_objects: Objects with tracking IDs and duration info.
            frame_width: Width of the video frame (for zone normalization).
            frame_height: Height of the video frame.

        Returns:
            List of detected behavior events.
        """
        now = time.time()
        events: List[BehaviorEvent] = []

        persons = [o for o in tracked_objects if o.class_name == "person"]
        bags = [
            o for o in tracked_objects
            if o.class_name in ("backpack", "handbag", "suitcase")
        ]

        person_ids = {p.track_id for p in persons}
        bag_ids = {b.track_id for b in bags}
        self._cleanup_missing_tracks(person_ids, bag_ids)

        # --- Check Loitering ---
        for person in persons:
            person_id = person.track_id
            entry_time = self._loitering_entry_time.setdefault(person_id, now)
            loiter_duration = now - entry_time

            if loiter_duration >= self.loitering_threshold:
                frame_count = self._loitering_persistence.get(person_id, 0) + 1
                self._loitering_persistence[person_id] = frame_count

                severity = AlertSeverity.MEDIUM
                if loiter_duration >= self.loitering_threshold * 2:
                    severity = AlertSeverity.HIGH

                events.append(
                    BehaviorEvent(
                        event_type=AlertType.LOITERING,
                        severity=severity,
                        message=(
                            f"Person (ID:{person_id}) loitering for "
                            f"{loiter_duration:.0f}s"
                        ),
                        involved_objects=[person_id],
                        primary_object_id=person_id,
                        duration_seconds=round(loiter_duration, 1),
                        confidence=person.confidence,
                        frame_count=frame_count,
                    )
                )
            else:
                # Gradually decay if threshold no longer satisfied.
                self._loitering_persistence[person_id] = max(
                    0,
                    self._loitering_persistence.get(person_id, 0) - 1,
                )

        # --- Check Intrusion ---
        zone = self._get_pixel_zone(frame_width, frame_height)
        for person in persons:
            person_id = person.track_id
            in_zone = self._point_in_zone(person.center_x, person.bbox.y2, zone)

            if in_zone:
                zone_entry = self._intrusion_entry_time.setdefault(person_id, now)
                dwell_time = now - zone_entry

                if dwell_time < self.intrusion_delay_seconds:
                    continue

                frame_count = self._intrusion_persistence.get(person_id, 0) + 1
                self._intrusion_persistence[person_id] = frame_count

                if dwell_time < 6:
                    severity = AlertSeverity.MEDIUM
                elif dwell_time < 12:
                    severity = AlertSeverity.HIGH
                else:
                    severity = AlertSeverity.CRITICAL

                events.append(
                    BehaviorEvent(
                        event_type=AlertType.INTRUSION,
                        severity=severity,
                        message=(
                            f"Person (ID:{person_id}) in restricted zone "
                            f"for {dwell_time:.0f}s"
                        ),
                        involved_objects=[person_id],
                        primary_object_id=person_id,
                        duration_seconds=round(dwell_time, 1),
                        confidence=person.confidence,
                        frame_count=frame_count,
                        zone="restricted_area",
                    )
                )
            else:
                self._intrusion_entry_time.pop(person_id, None)
                self._intrusion_persistence.pop(person_id, None)

        # --- Check Unattended Objects ---
        for bag in bags:
            bag_id = bag.track_id
            nearest_person_dist = float("inf")

            for person in persons:
                dist = (
                    (bag.center_x - person.center_x) ** 2
                    + (bag.center_y - person.center_y) ** 2
                ) ** 0.5
                nearest_person_dist = min(nearest_person_dist, dist)

            is_unattended = nearest_person_dist > self.unattended_person_distance_px

            if is_unattended:
                unattended_start = self._unattended_start_time.setdefault(bag_id, now)
                unattended_duration = now - unattended_start

                if unattended_duration < self.unattended_threshold:
                    continue

                frame_count = self._unattended_persistence.get(bag_id, 0) + 1
                self._unattended_persistence[bag_id] = frame_count

                severity = AlertSeverity.HIGH
                if unattended_duration >= self.unattended_threshold * 2:
                    severity = AlertSeverity.CRITICAL

                events.append(
                    BehaviorEvent(
                        event_type=AlertType.UNATTENDED_OBJECT,
                        severity=severity,
                        message=(
                            f"Unattended {bag.class_name} (ID:{bag_id}) "
                            f"detected for {unattended_duration:.0f}s"
                        ),
                        involved_objects=[bag_id],
                        primary_object_id=bag_id,
                        duration_seconds=round(unattended_duration, 1),
                        confidence=bag.confidence,
                        frame_count=frame_count,
                    )
                )
            else:
                self._unattended_start_time.pop(bag_id, None)
                self._unattended_persistence.pop(bag_id, None)

        # --- Triple-Lock Logic ---
        # Lock 3: Face recognition placeholder
        for event in events:
            # In a real system, this would run face recognition.
            # For now, it always passes.
            pass  # Lock 3: face recognition skipped (placeholder)

        return events

    def _cleanup_missing_tracks(self, person_ids: Set[int], bag_ids: Set[int]) -> None:
        """Reset temporal state for tracks that disappeared from the scene."""
        for person_id in list(self._loitering_entry_time.keys()):
            if person_id not in person_ids:
                self._loitering_entry_time.pop(person_id, None)
                self._loitering_persistence.pop(person_id, None)

        for person_id in list(self._intrusion_entry_time.keys()):
            if person_id not in person_ids:
                self._intrusion_entry_time.pop(person_id, None)
                self._intrusion_persistence.pop(person_id, None)

        for bag_id in list(self._unattended_start_time.keys()):
            if bag_id not in bag_ids:
                self._unattended_start_time.pop(bag_id, None)
                self._unattended_persistence.pop(bag_id, None)

    def _get_pixel_zone(
        self, width: int, height: int
    ) -> Tuple[int, int, int, int]:
        """Convert normalized zone coords to pixel coords."""
        z = self.intrusion_zone
        return (
            int(z[0] * width),
            int(z[1] * height),
            int(z[2] * width),
            int(z[3] * height),
        )

    @staticmethod
    def _point_in_zone(
        x: int, y: int, zone: Tuple[int, int, int, int]
    ) -> bool:
        """Check if point (x, y) is inside the rectangular zone."""
        return zone[0] <= x <= zone[2] and zone[1] <= y <= zone[3]
