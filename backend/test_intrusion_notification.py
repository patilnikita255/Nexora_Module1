"""
End-to-end test for Restricted Zone Intrusion → Notification.

Usage:
  1. Ensure .env has EMAIL_NOTIFICATIONS_ENABLED=true and valid SMTP credentials.
  2. Run from the backend/ directory:
         python test_intrusion_notification.py

Sends THREE fake intrusion alerts at escalating severity levels:
  - Alert 1: MEDIUM  — person in zone for 4s  (just past 2.5s delay)
  - Alert 2: HIGH    — person in zone for 10s (past 6s threshold)
  - Alert 3: CRITICAL — person in zone for 15s (past 12s threshold)
"""

import logging
import sys
import time
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)

sys.path.insert(0, ".")

from app.config import get_settings
from app.models.schemas import Alert, AlertSeverity, AlertType
from app.services.notifier import send_alert_notification


def main() -> None:
    settings = get_settings()

    print("=" * 64)
    print("  Feature 1 — Intrusion Detection Notification Test")
    print("=" * 64)
    print(f"  Email enabled : {settings.email_notifications_enabled}")
    print(f"  SMTP host     : {settings.smtp_host or '(not set)'}")
    print(f"  Email to      : {settings.alert_email_to or '(not set)'}")
    print(f"  Intrusion zone: {settings.intrusion_zone}")
    print("=" * 64)

    if not settings.email_notifications_enabled and not settings.sms_notifications_enabled:
        print(
            "\n[!] Both channels are DISABLED. Set EMAIL_NOTIFICATIONS_ENABLED=true "
            "in your .env to test.\n"
        )
        return

    alerts = [
        Alert(
            id="INTR-MED1",
            timestamp=datetime.now(timezone.utc),
            alert_type=AlertType.INTRUSION,
            severity=AlertSeverity.MEDIUM,
            message="Person (ID:5) in restricted zone for 4s (TEST — MEDIUM)",
            snapshot_url=None,
            objects_involved=["5"],
            object_id="5",
            duration_seconds=4.0,
            confidence=0.88,
        ),
        Alert(
            id="INTR-HI01",
            timestamp=datetime.now(timezone.utc),
            alert_type=AlertType.INTRUSION,
            severity=AlertSeverity.HIGH,
            message="Person (ID:5) in restricted zone for 10s (TEST — HIGH)",
            snapshot_url=None,
            objects_involved=["5"],
            object_id="5",
            duration_seconds=10.0,
            confidence=0.90,
        ),
        Alert(
            id="INTR-CR01",
            timestamp=datetime.now(timezone.utc),
            alert_type=AlertType.INTRUSION,
            severity=AlertSeverity.CRITICAL,
            message="Person (ID:5) in restricted zone for 15s (TEST — CRITICAL)",
            snapshot_url=None,
            objects_involved=["5"],
            object_id="5",
            duration_seconds=15.0,
            confidence=0.91,
        ),
    ]

    for i, alert in enumerate(alerts, 1):
        print(f"\n[{i}/3] Sending {alert.severity.value.upper()} intrusion alert...")
        send_alert_notification(alert, snapshot_path=None)
        time.sleep(2)

    print("\n[...] Waiting 15 seconds for background delivery...\n")
    time.sleep(15)

    print("-" * 64)
    print("[OK] Done. You should have received THREE emails:")
    print("     1. Unauthorized Entry Into Restricted Zone [Medium Priority]")
    print("     2. Unauthorized Entry Into Restricted Zone [High Priority]")
    print("     3. Unauthorized Entry Into Restricted Zone [Critical Priority]")
    print("")
    print("  If nothing arrived, check the log output above for errors.")
    print("-" * 64)


if __name__ == "__main__":
    main()
