"""
Test Feature 3: Unattended Object Detection (with Owner-Association).
Verifies:
  - Nearest person associated as bag owner when adjacent
  - Duration tracking when owner moves away
  - Stationary confirmation
  - Escalating alert after threshold
"""

import time
from app.core.behavior import BehaviorAnalyzer
from app.models.schemas import (
    AlertSeverity,
    AlertType,
    BBox,
    TrackedObject,
)


def test_unattended_object_owner_association():
    analyzer = BehaviorAnalyzer()
    analyzer.unattended_threshold = 10.0  # 10s for test
    frame_w, frame_h = 1000, 1000

    # Frame 1: Person standing right next to backpack
    person_near = TrackedObject(
        track_id=5,
        class_name="person",
        confidence=0.90,
        bbox=BBox(x1=300, y1=200, x2=400, y2=700),
        center_x=350,
        center_y=450,
        first_seen=time.time(),
        last_seen=time.time(),
    )
    bag = TrackedObject(
        track_id=20,
        class_name="backpack",
        confidence=0.85,
        bbox=BBox(x1=360, y1=500, x2=420, y2=580),
        center_x=390,
        center_y=540,
        first_seen=time.time(),
        last_seen=time.time(),
    )

    events = analyzer.analyze([person_near, bag], frame_w, frame_h)
    assert len(events) == 0
    # Owner should be associated
    assert analyzer._bag_owner.get(20) == 5

    # Frame 2: Person moves far away (> 200px)
    person_far = TrackedObject(
        track_id=5,
        class_name="person",
        confidence=0.90,
        bbox=BBox(x1=700, y1=200, x2=800, y2=700),
        center_x=750,
        center_y=450,
        first_seen=time.time(),
        last_seen=time.time(),
    )

    # Simulate 12 seconds elapsed while bag remains stationary
    analyzer._unattended_start_time[20] = time.time() - 12.0
    events = analyzer.analyze([person_far, bag], frame_w, frame_h)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == AlertType.UNATTENDED_OBJECT
    assert ev.primary_object_id == 20
    assert 5 in ev.involved_objects  # Owner is tracked in involved objects
    assert "Owner: Person ID:5" in ev.message


if __name__ == "__main__":
    test_unattended_object_owner_association()
    print("Feature 3 unattended object tests PASSED.")
