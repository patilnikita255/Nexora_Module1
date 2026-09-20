"""
Test Feature 1: Person Detection & Multi-Zone Restricted-Area Intrusion.
Verifies:
  - Detection of person inside restricted perimeter
  - Escalating severity with dwell time (Medium -> High -> Critical)
  - Exclusion zone suppression for authorized waiting areas
"""

import time
from app.core.behavior import BehaviorAnalyzer
from app.models.schemas import (
    AlertSeverity,
    AlertType,
    BBox,
    TrackedObject,
    ZoneConfig,
    ZoneType,
)


def test_restricted_intrusion_escalation():
    analyzer = BehaviorAnalyzer()
    analyzer.set_zones([
        ZoneConfig(
            id="restricted_zone_1",
            name="Secure Server Room",
            zone_type=ZoneType.RESTRICTED,
            coords=(0.5, 0.0, 1.0, 1.0),
            is_active=True,
        )
    ])

    frame_w, frame_h = 1000, 1000
    # Person at x=750, y=500 (inside restricted zone)
    person = TrackedObject(
        track_id=1,
        class_name="person",
        confidence=0.92,
        bbox=BBox(x1=700, y1=400, x2=800, y2=600),
        center_x=750,
        center_y=500,
        first_seen=time.time(),
        last_seen=time.time(),
    )

    # First instant: dwell time < 2.5s -> no alert yet
    events = analyzer.analyze([person], frame_w, frame_h)
    assert len(events) == 0

    # Simulate dwell time of 3 seconds -> Medium severity
    analyzer._zone_entry_time[(1, "restricted_zone_1")] = time.time() - 3.0
    analyzer._intrusion_entry_time[1] = time.time() - 3.0
    events = analyzer.analyze([person], frame_w, frame_h)
    assert len(events) == 1
    assert events[0].event_type == AlertType.INTRUSION
    assert events[0].severity == AlertSeverity.MEDIUM

    # Simulate dwell time of 8 seconds -> High severity
    analyzer._zone_entry_time[(1, "restricted_zone_1")] = time.time() - 8.0
    events = analyzer.analyze([person], frame_w, frame_h)
    assert len(events) == 1
    assert events[0].severity == AlertSeverity.HIGH

    # Simulate dwell time of 15 seconds -> Critical severity
    analyzer._zone_entry_time[(1, "restricted_zone_1")] = time.time() - 15.0
    events = analyzer.analyze([person], frame_w, frame_h)
    assert len(events) == 1
    assert events[0].severity == AlertSeverity.CRITICAL


def test_excluded_zone_suppression():
    analyzer = BehaviorAnalyzer()
    # Zone 1: Restricted corridor (0.5 to 1.0)
    # Zone 2: Excluded seating area (0.0 to 0.4)
    analyzer.set_zones([
        ZoneConfig(
            id="restricted_corridor",
            name="Corridor",
            zone_type=ZoneType.RESTRICTED,
            coords=(0.5, 0.0, 1.0, 1.0),
            is_active=True,
        ),
        ZoneConfig(
            id="waiting_area",
            name="Waiting Area",
            zone_type=ZoneType.EXCLUDED,
            coords=(0.0, 0.0, 0.4, 1.0),
            is_active=True,
        ),
    ])

    frame_w, frame_h = 1000, 1000
    # Person inside excluded waiting area (x=200, y=500)
    person = TrackedObject(
        track_id=2,
        class_name="person",
        confidence=0.88,
        bbox=BBox(x1=150, y1=400, x2=250, y2=600),
        center_x=200,
        center_y=500,
        first_seen=time.time() - 20.0,
        last_seen=time.time(),
    )

    events = analyzer.analyze([person], frame_w, frame_h)
    assert len(events) == 0


if __name__ == "__main__":
    test_restricted_intrusion_escalation()
    test_excluded_zone_suppression()
    print("Feature 1 intrusion tests PASSED.")
