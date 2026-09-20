"""
Rule-Based Behavior Analysis Engine.

Handles the core surveillance behavioral rules:
  1. Feature 1: Multi-Zone Restricted-Area Intrusion (with escalating severity)
  2. Feature 2: Weapon Detection (Knife + Gun anywhere in camera FOV)
  3. Feature 3: Unattended Object Detection (Stationary bags with owner association)
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set, Tuple

from app.config import get_settings
from app.models.schemas import (
    AlertSeverity,
    AlertType,
    BehaviorEvent,
    TrackedObject,
    ZoneConfig,
    ZoneType,
)


class BehaviorAnalyzer:
    """Analyzes tracked objects for Intrusion, Weapons, and Unattended Objects."""

    def __init__(self) -> None:
        settings = get_settings()
        self.zones: List[ZoneConfig] = settings.get_default_zones()
        self.intrusion_delay_seconds = 2.5
        self.unattended_threshold = settings.unattended_object_seconds
        self.unattended_person_distance_px = 150.0

        # Feature 1: Intrusion tracking
        # (person_id, zone_id) -> entry_timestamp
        self._zone_entry_time: Dict[Tuple[int, str], float] = {}
        self._zone_persistence: Dict[Tuple[int, str], int] = {}
        self._intrusion_entry_time: Dict[int, float] = {}
        self._intrusion_persistence: Dict[int, int] = {}

        # Feature 2: Weapon tracking
        self._weapon_persistence: Dict[int, int] = {}

        # Feature 3: Unattended Object tracking (with owner association)
        self._unattended_start_time: Dict[int, float] = {}
        self._unattended_persistence: Dict[int, int] = {}
        self._bag_owner: Dict[int, int] = {}
        self._bag_last_pos: Dict[int, Tuple[int, int, float]] = {}  # (cx, cy, timestamp)

    @property
    def intrusion_zone(self) -> Tuple[float, float, float, float]:
        """Backward compatibility: coordinates of the first active restricted zone."""
        for z in self.zones:
            if z.zone_type == ZoneType.RESTRICTED and z.is_active:
                return z.coords
        return (0.8, 0.0, 1.0, 1.0)

    def set_zones(self, zones: List[ZoneConfig]) -> None:
        """Update active surveillance zones."""
        self.zones = list(zones)

    def get_zones(self) -> List[ZoneConfig]:
        """Return the current surveillance zones."""
        return self.zones

    def add_zone(self, zone: ZoneConfig) -> None:
        """Add or replace a zone."""
        self.zones = [z for z in self.zones if z.id != zone.id]
        self.zones.append(zone)

    def remove_zone(self, zone_id: str) -> bool:
        """Remove a zone by ID."""
        initial_len = len(self.zones)
        self.zones = [z for z in self.zones if z.id != zone_id]
        return len(self.zones) < initial_len

    def reset(self) -> None:
        """Reset temporal state on video restart/source change."""
        self._zone_entry_time.clear()
        self._zone_persistence.clear()
        self._intrusion_entry_time.clear()
        self._intrusion_persistence.clear()
        self._weapon_persistence.clear()
        self._unattended_start_time.clear()
        self._unattended_persistence.clear()
        self._bag_owner.clear()
        self._bag_last_pos.clear()

    def analyze(
        self,
        tracked_objects: List[TrackedObject],
        frame_width: int,
        frame_height: int,
        camera_mode: str = "all",
    ) -> List[BehaviorEvent]:
        """
        Run behavioral analysis across all 3 detection features.
        Runs ONE shared detection pipeline per camera.
        """
        now = time.time()
        events: List[BehaviorEvent] = []

        persons = [o for o in tracked_objects if o.class_name == "person"]
        bags = [
            o for o in tracked_objects
            if o.class_name in ("backpack", "handbag", "suitcase")
        ]
        weapons = [
            o for o in tracked_objects
            if o.class_name in ("knife", "gun", "weapon", "pistol", "rifle")
        ]

        person_ids = {p.track_id for p in persons}
        bag_ids = {b.track_id for b in bags}
        weapon_ids = {w.track_id for w in weapons}
        self._cleanup_missing_tracks(person_ids, bag_ids, weapon_ids)

        # =====================================================================
        # Feature 1 — Multi-Zone Restricted-Area Intrusion
        # =====================================================================
        active_restricted = [z for z in self.zones if z.zone_type == ZoneType.RESTRICTED and z.is_active]
        active_excluded = [z for z in self.zones if z.zone_type == ZoneType.EXCLUDED and z.is_active]

        # 1. Identify persons located in EXCLUDED zones (e.g. public seating/waiting areas)
        excluded_person_ids: Set[int] = set()
        for person in persons:
            for ex_zone in active_excluded:
                pz = self._get_zone_pixel_box(ex_zone.coords, frame_width, frame_height)
                if self._point_in_zone(person.center_x, person.bbox.y2, pz) or self._point_in_zone(person.center_x, person.center_y, pz):
                    excluded_person_ids.add(person.track_id)
                    break

        # 2. Check RESTRICTED zones for persons not in excluded zones
        for person in persons:
            pid = person.track_id
            if pid in excluded_person_ids:
                # In authorized excluded area -> clear intrusion timers
                for rz in active_restricted:
                    self._zone_entry_time.pop((pid, rz.id), None)
                    self._zone_persistence.pop((pid, rz.id), None)
                self._intrusion_entry_time.pop(pid, None)
                self._intrusion_persistence.pop(pid, None)
                continue

            for zone in active_restricted:
                pz = self._get_zone_pixel_box(zone.coords, frame_width, frame_height)
                in_zone = self._point_in_zone(person.center_x, person.bbox.y2, pz) or self._point_in_zone(person.center_x, person.center_y, pz)

                key = (pid, zone.id)
                if in_zone:
                    if pid in self._intrusion_entry_time and key not in self._zone_entry_time:
                        self._zone_entry_time[key] = self._intrusion_entry_time[pid]

                    entry_time = self._zone_entry_time.setdefault(key, now)
                    self._intrusion_entry_time[pid] = entry_time
                    dwell = now - entry_time

                    if dwell < self.intrusion_delay_seconds:
                        continue

                    count = self._zone_persistence.get(key, 0) + 1
                    self._zone_persistence[key] = count
                    self._intrusion_persistence[pid] = count

                    # Escalating severity with dwell time
                    if dwell < 6.0:
                        severity = AlertSeverity.MEDIUM
                    elif dwell < 12.0:
                        severity = AlertSeverity.HIGH
                    else:
                        severity = AlertSeverity.CRITICAL

                    events.append(
                        BehaviorEvent(
                            event_type=AlertType.INTRUSION,
                            severity=severity,
                            message=(
                                f"Person (ID:{pid}) breached restricted zone "
                                f"'{zone.name}' for {dwell:.0f}s"
                            ),
                            involved_objects=[pid],
                            primary_object_id=pid,
                            duration_seconds=round(dwell, 1),
                            confidence=person.confidence,
                            frame_count=count,
                            zone=zone.id,
                            zone_id=zone.id,
                            zone_name=zone.name,
                        )
                    )
                else:
                    self._zone_entry_time.pop(key, None)
                    self._zone_persistence.pop(key, None)

        # =====================================================================
        # Feature 2 — Weapon Detection (Knife + Gun, FOV-wide)
        # =====================================================================
        for weapon in weapons:
            wid = weapon.track_id

            # Find closest person (potential wielder)
            nearest_person_id = None
            min_dist = float("inf")
            for person in persons:
                dist = (
                    (weapon.center_x - person.center_x) ** 2
                    + (weapon.center_y - person.center_y) ** 2
                ) ** 0.5
                if dist < min_dist:
                    min_dist = dist
                    nearest_person_id = person.track_id

            if nearest_person_id is not None and min_dist < 220.0:
                primary_id = nearest_person_id
                involved = [wid, nearest_person_id]
                msg = (
                    f"Weapon ({weapon.class_name}) detected held by "
                    f"Person (ID:{nearest_person_id}) with {weapon.confidence:.0%} confidence!"
                )
            else:
                primary_id = wid
                involved = [wid]
                msg = (
                    f"Weapon ({weapon.class_name}) detected in camera view "
                    f"with {weapon.confidence:.0%} confidence!"
                )

            count = self._weapon_persistence.get(primary_id, 0) + 1
            self._weapon_persistence[primary_id] = count

            events.append(
                BehaviorEvent(
                    event_type=AlertType.WEAPON_DETECTED,
                    severity=AlertSeverity.CRITICAL,
                    message=msg,
                    involved_objects=involved,
                    primary_object_id=primary_id,
                    duration_seconds=0.5,
                    confidence=weapon.confidence,
                    frame_count=count,
                )
            )

        # =====================================================================
        # Feature 3 — Unattended Object Detection (with owner association)
        # =====================================================================
        for bag in bags:
            bid = bag.track_id

            # Distance to nearest person
            nearest_person_id = None
            nearest_dist = float("inf")
            for person in persons:
                dist = (
                    (bag.center_x - person.center_x) ** 2
                    + (bag.center_y - person.center_y) ** 2
                ) ** 0.5
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_person_id = person.track_id

            is_isolated = nearest_dist > self.unattended_person_distance_px

            # Associate owner while person is near the bag
            if not is_isolated and nearest_person_id is not None:
                self._bag_owner[bid] = nearest_person_id

            # Check if bag is stationary (displacement < 25px)
            last_pos = self._bag_last_pos.get(bid)
            is_stationary = True
            if last_pos is not None:
                dx = bag.center_x - last_pos[0]
                dy = bag.center_y - last_pos[1]
                disp = (dx * dx + dy * dy) ** 0.5
                # If moving fast (> 40px), not abandoned yet
                if disp > 40.0 and (now - last_pos[2]) < 1.0:
                    is_stationary = False
            self._bag_last_pos[bid] = (bag.center_x, bag.center_y, now)

            if is_isolated and is_stationary:
                start_time = self._unattended_start_time.setdefault(bid, now)
                duration = now - start_time

                if duration >= self.unattended_threshold:
                    count = self._unattended_persistence.get(bid, 0) + 1
                    self._unattended_persistence[bid] = count

                    severity = AlertSeverity.HIGH if duration < self.unattended_threshold * 2 else AlertSeverity.CRITICAL
                    last_owner = self._bag_owner.get(bid)
                    involved = [bid]
                    owner_str = ""
                    if last_owner is not None:
                        involved.append(last_owner)
                        owner_str = f" (Owner: Person ID:{last_owner})"

                    events.append(
                        BehaviorEvent(
                            event_type=AlertType.UNATTENDED_OBJECT,
                            severity=severity,
                            message=(
                                f"Unattended {bag.class_name} (ID:{bid}) "
                                f"detected for {duration:.0f}s{owner_str}"
                            ),
                            involved_objects=involved,
                            primary_object_id=bid,
                            duration_seconds=round(duration, 1),
                            confidence=bag.confidence,
                            frame_count=count,
                        )
                    )
            else:
                self._unattended_start_time.pop(bid, None)
                self._unattended_persistence.pop(bid, None)

        return events

    def _cleanup_missing_tracks(
        self,
        person_ids: Set[int],
        bag_ids: Set[int],
        weapon_ids: Set[int],
    ) -> None:
        """Clear temporal state for disappeared tracks."""
        for (pid, zid) in list(self._zone_entry_time.keys()):
            if pid not in person_ids:
                self._zone_entry_time.pop((pid, zid), None)
                self._zone_persistence.pop((pid, zid), None)

        for pid in list(self._intrusion_entry_time.keys()):
            if pid not in person_ids:
                self._intrusion_entry_time.pop(pid, None)
                self._intrusion_persistence.pop(pid, None)

        for wid in list(self._weapon_persistence.keys()):
            if wid not in weapon_ids and wid not in person_ids:
                self._weapon_persistence.pop(wid, None)

        for bid in list(self._unattended_start_time.keys()):
            if bid not in bag_ids:
                self._unattended_start_time.pop(bid, None)
                self._unattended_persistence.pop(bid, None)
                self._bag_last_pos.pop(bid, None)

    @staticmethod
    def _get_zone_pixel_box(
        coords: Tuple[float, float, float, float],
        frame_width: int,
        frame_height: int,
    ) -> Tuple[int, int, int, int]:
        return (
            int(coords[0] * frame_width),
            int(coords[1] * frame_height),
            int(coords[2] * frame_width),
            int(coords[3] * frame_height),
        )

    @staticmethod
    def _point_in_zone(px: int, py: int, zone: Tuple[int, int, int, int]) -> bool:
        zx1, zy1, zx2, zy2 = zone
        return zx1 <= px <= zx2 and zy1 <= py <= zy2
