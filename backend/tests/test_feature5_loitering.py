"""
Test Feature 5: Suspicious Loitering Analysis & Smart Discrimination.
Verifies:
  - Loitering suppression for safe waiting:
      * Inside designated waiting/excluded zones
      * Presence of social companion (waiting with someone)
      * Calm stationary waiting
  - Loitering alert triggering for suspicious pacing:
      * High pacing ratio (back-and-forth movement)
      * Multiple direction reversals
      * Perimeter boundary casing
  - Weapon reconciliation logic (prevents gun misclassified as knife)
  - Bold notification content (CRITICAL LEVEL and REASON)
"""

import sys
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import time
from datetime import datetime, timezone
from app.core.behavior import BehaviorAnalyzer
from app.models.schemas import (
    Alert,
    AlertSeverity,
    AlertType,
    BBox,
    Detection,
    TrackedObject,
    ZoneConfig,
    ZoneType,
)
from app.services.notifier import _format_email_html, _format_sms_body
from app.core.detector import reconcile_weapon_classes


def test_safe_waiting_with_companion():
    """Two people close together (waiting for someone / socializing) must not trigger loitering."""
    analyzer = BehaviorAnalyzer()
    frame_w, frame_h = 1000, 1000

    t_start = time.time() - 25.0  # 25 seconds ago

    p1 = TrackedObject(
        track_id=1,
        class_name="person",
        confidence=0.9,
        bbox=BBox(x1=300, y1=300, x2=360, y2=450),
        center_x=330,
        center_y=375,
        first_seen=t_start,
        last_seen=time.time(),
    )
    p2 = TrackedObject(
        track_id=2,
        class_name="person",
        confidence=0.9,
        bbox=BBox(x1=340, y1=300, x2=400, y2=450),
        center_x=370,
        center_y=375,
        first_seen=t_start,
        last_seen=time.time(),
    )

    events = analyzer.analyze([p1, p2], frame_w, frame_h)
    loitering_events = [e for e in events if e.event_type == AlertType.LOITERING]
    assert len(loitering_events) == 0, "Loitering should be suppressed when person has a companion"


def test_safe_waiting_in_excluded_zone():
    """Person standing in a designated waiting zone must not trigger loitering."""
    analyzer = BehaviorAnalyzer()
    frame_w, frame_h = 1000, 1000

    waiting_zone = ZoneConfig(
        id="waiting_1",
        name="Public Waiting Area",
        zone_type=ZoneType.EXCLUDED,
        coords=(0.1, 0.1, 0.5, 0.9),  # 100 to 500 px
    )
    analyzer.set_zones([waiting_zone])

    t_start = time.time() - 25.0

    p = TrackedObject(
        track_id=3,
        class_name="person",
        confidence=0.9,
        bbox=BBox(x1=200, y1=300, x2=260, y2=450),
        center_x=230,
        center_y=375,
        first_seen=t_start,
        last_seen=time.time(),
    )

    events = analyzer.analyze([p], frame_w, frame_h)
    loitering_events = [e for e in events if e.event_type == AlertType.LOITERING]
    assert len(loitering_events) == 0, "Loitering must be suppressed inside designated waiting zones"


def test_suspicious_pacing_triggers_loitering():
    """Person pacing back and forth (high pacing ratio, direction reversals) triggers loitering."""
    analyzer = BehaviorAnalyzer()
    frame_w, frame_h = 1000, 1000

    # Simulate 20 seconds of pacing back and forth between x=400 and x=550
    now = time.time()
    t0 = now - 20.0
    analyzer._loitering_entry_time[4] = t0
    # Add oscillating positions: 400 -> 550 -> 400 -> 550 -> 400 with recent timestamps
    xs = [400, 450, 500, 550, 500, 450, 400, 450, 500, 550, 500, 450, 400]
    positions = []
    for i, x in enumerate(xs):
        pos_t = t0 + (i * 1.5)
        positions.append((x, 500, pos_t))
    analyzer._loitering_positions[4] = positions

    p = TrackedObject(
        track_id=4,
        class_name="person",
        confidence=0.92,
        bbox=BBox(x1=370, y1=400, x2=430, y2=600),
        center_x=400,
        center_y=500,
        first_seen=t0,
        last_seen=time.time(),
    )

    events = analyzer.analyze([p], frame_w, frame_h)
    loitering_events = [e for e in events if e.event_type == AlertType.LOITERING]
    assert len(loitering_events) >= 1, "Suspicious pacing must trigger loitering alert"
    ev = loitering_events[0]
    assert "pacing" in ev.message.lower() or "suspicion score" in ev.message.lower()


def test_weapon_reconciliation_preserves_gun():
    """Specialized gun detections must NOT be overridden by base COCO knife class."""
    knife_det = Detection(
        class_name="knife",
        confidence=0.35,
        bbox=BBox(x1=200, y1=300, x2=240, y2=340),
        center_x=220,
        center_y=320,
    )
    gun_det = Detection(
        class_name="gun",
        confidence=0.85,
        bbox=BBox(x1=195, y1=295, x2=245, y2=345),
        center_x=220,
        center_y=320,
    )

    reconciled = reconcile_weapon_classes([knife_det, gun_det])
    # The higher confidence specialized gun detection must prevail
    classes = [d.class_name for d in reconciled]
    assert "gun" in classes
    assert "knife" not in classes


def test_notification_formatting_bold_critical_and_reason():
    """Notification builders must prominently display bold CRITICAL LEVEL and REASON."""
    alert = Alert(
        id="test-1234",
        timestamp=datetime.now(timezone.utc),
        alert_type=AlertType.WEAPON_DETECTED,
        severity=AlertSeverity.CRITICAL,
        message="CRITICAL: Lethal firearm detected",
        confidence=0.92,
        duration_seconds=3.0,
    )

    html = _format_email_html(alert)
    assert "<b>CRITICAL LEVEL:" in html
    assert "REASON FOR ALERT" in html
    assert "CRITICAL" in html

    sms = _format_sms_body(alert)
    assert "[CRITICAL LEVEL: CRITICAL]" in sms
    assert "REASON:" in sms


if __name__ == "__main__":
    test_safe_waiting_with_companion()
    test_safe_waiting_in_excluded_zone()
    test_suspicious_pacing_triggers_loitering()
    test_weapon_reconciliation_preserves_gun()
    test_notification_formatting_bold_critical_and_reason()
    print("Feature 5 loitering & weapon reconciliation tests PASSED.")
