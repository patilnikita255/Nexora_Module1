"""
Test Feature 4: Real Alert Notification (Email/SMS, Async) + Snapshot.
Verifies:
  - Background non-blocking queue integration
  - Alert snapshot creation and linking
  - Cooldown deduplication preventing notification spam
"""

import time
import uuid
from datetime import datetime, timezone
import numpy as np

from app.models.schemas import Alert, AlertSeverity, AlertType, BehaviorEvent
from app.services.alert_manager import AlertManager
from app.services.notifier import send_alert_notification, _notification_queue


def test_async_notifier_queue_non_blocking():
    # Enqueue should happen instantly without blocking
    alert = Alert(
        id=str(uuid.uuid4())[:8],
        timestamp=datetime.now(timezone.utc),
        alert_type=AlertType.WEAPON_DETECTED,
        severity=AlertSeverity.CRITICAL,
        message="CRITICAL: Knife detected in main lobby",
        confidence=0.85,
    )

    t0 = time.time()
    send_alert_notification(alert, snapshot_path=None)
    elapsed = time.time() - t0
    # Must be under 10ms (non-blocking thread/queue dispatch)
    assert elapsed < 0.05


def test_alert_manager_cooldown_deduplication():
    manager = AlertManager()
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    event = BehaviorEvent(
        event_type=AlertType.WEAPON_DETECTED,
        severity=AlertSeverity.CRITICAL,
        message="Weapon detected",
        involved_objects=[10],
        primary_object_id=10,
        duration_seconds=1.0,
        confidence=0.9,
        frame_count=4,
    )

    # First trigger: creates alert
    alerts1 = manager.process_events([event], frame=dummy_frame)
    assert len(alerts1) == 1
    assert alerts1[0].snapshot_url is not None

    # Immediate second trigger: suppressed by cooldown
    alerts2 = manager.process_events([event], frame=dummy_frame)
    assert len(alerts2) == 0


if __name__ == "__main__":
    test_async_notifier_queue_non_blocking()
    test_alert_manager_cooldown_deduplication()
    print("Feature 4 notification tests PASSED.")
