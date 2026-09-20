"""
Test Feature 2: Weapon Detection (Knife + Gun).
Verifies:
  - Knife and Gun detections trigger WEAPON_DETECTED alert
  - Correlation to nearest person (wielder)
  - Critical severity assignment
"""

import time
from app.core.behavior import BehaviorAnalyzer
from app.models.schemas import (
    AlertSeverity,
    AlertType,
    BBox,
    TrackedObject,
)


def test_weapon_detection_with_person():
    analyzer = BehaviorAnalyzer()
    frame_w, frame_h = 1000, 1000

    person = TrackedObject(
        track_id=1,
        class_name="person",
        confidence=0.95,
        bbox=BBox(x1=300, y1=200, x2=450, y2=700),
        center_x=375,
        center_y=450,
        first_seen=time.time(),
        last_seen=time.time(),
    )

    gun = TrackedObject(
        track_id=10,
        class_name="gun",
        confidence=0.88,
        bbox=BBox(x1=420, y1=400, x2=480, y2=460),
        center_x=450,
        center_y=430,
        first_seen=time.time(),
        last_seen=time.time(),
    )

    events = analyzer.analyze([person, gun], frame_w, frame_h)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == AlertType.WEAPON_DETECTED
    assert ev.severity == AlertSeverity.CRITICAL
    assert 1 in ev.involved_objects  # Person associated as wielder
    assert "gun" in ev.message.lower()


def test_knife_detection():
    analyzer = BehaviorAnalyzer()
    frame_w, frame_h = 1000, 1000

    knife = TrackedObject(
        track_id=12,
        class_name="knife",
        confidence=0.75,
        bbox=BBox(x1=500, y1=500, x2=550, y2=560),
        center_x=525,
        center_y=530,
        first_seen=time.time(),
        last_seen=time.time(),
    )

    events = analyzer.analyze([knife], frame_w, frame_h)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == AlertType.WEAPON_DETECTED
    assert ev.severity == AlertSeverity.CRITICAL
    assert "knife" in ev.message.lower()


if __name__ == "__main__":
    test_weapon_detection_with_person()
    test_knife_detection()
    print("Feature 2 weapon tests PASSED.")
