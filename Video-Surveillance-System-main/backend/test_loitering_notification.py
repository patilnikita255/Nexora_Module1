"""
End-to-end test for Loitering Detection → Notification.

Usage:
  1. Ensure .env has EMAIL_NOTIFICATIONS_ENABLED=true and valid SMTP credentials.
  2. Run from the backend/ directory:
         python test_loitering_notification.py

This sends TWO fake loitering alerts through the full notification pipeline:
  - Alert 1: MEDIUM severity (person loitering for 25s — just past the 20s threshold)
  - Alert 2: HIGH severity (person loitering for 45s — past 2× the threshold)

Verifies that the notifier handles loitering alerts correctly with proper
severity labels, duration info, and no crashes.
"""

import logging
import sys
import time
from datetime import datetime, timezone

# Setup logging so we can see notifier output
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)

# --- Ensure imports work from backend/ directory ---
sys.path.insert(0, ".")

from app.config import get_settings
from app.models.schemas import Alert, AlertSeverity, AlertType
from app.services.notifier import send_alert_notification


def main() -> None:
    settings = get_settings()

    print("=" * 64)
    print("  Feature 2 — Loitering Detection Notification Test")
    print("=" * 64)
    print(f"  Email enabled : {settings.email_notifications_enabled}")
    print(f"  SMTP host     : {settings.smtp_host or '(not set)'}")
    print(f"  Email to      : {settings.alert_email_to or '(not set)'}")
    print(f"  SMS enabled   : {settings.sms_notifications_enabled}")
    print(f"  Loitering threshold : {settings.loitering_threshold_seconds}s")
    print(f"  Alert cooldown      : {settings.alert_cooldown_seconds}s")
    print("=" * 64)

    if not settings.email_notifications_enabled and not settings.sms_notifications_enabled:
        print(
            "\n[!] Both channels are DISABLED.  Set EMAIL_NOTIFICATIONS_ENABLED=true "
            "and/or SMS_NOTIFICATIONS_ENABLED=true in your .env to test.\n"
        )
        return

    # ---- Alert 1: MEDIUM severity loitering (25 seconds) ----
    alert_medium = Alert(
        id="LOIT-MED1",
        timestamp=datetime.now(timezone.utc),
        alert_type=AlertType.LOITERING,
        severity=AlertSeverity.MEDIUM,
        message="Person (ID:7) loitering for 25s (TEST — MEDIUM severity)",
        snapshot_url=None,
        objects_involved=["7"],
        object_id="7",
        duration_seconds=25.0,
        confidence=0.82,
    )

    print("\n[1/2] Sending MEDIUM severity loitering alert...")
    send_alert_notification(alert_medium, snapshot_path=None)

    # Small delay between alerts to avoid them merging in the queue
    time.sleep(2)

    # ---- Alert 2: HIGH severity loitering (45 seconds — past 2× threshold) ----
    alert_high = Alert(
        id="LOIT-HI01",
        timestamp=datetime.now(timezone.utc),
        alert_type=AlertType.LOITERING,
        severity=AlertSeverity.HIGH,
        message="Person (ID:7) loitering for 45s (TEST — HIGH severity, escalated)",
        snapshot_url=None,
        objects_involved=["7"],
        object_id="7",
        duration_seconds=45.0,
        confidence=0.85,
    )

    print("[2/2] Sending HIGH severity loitering alert...")
    send_alert_notification(alert_high, snapshot_path=None)

    # Give the background worker time to deliver
    print("\n[...] Waiting 15 seconds for background delivery...\n")
    time.sleep(15)

    print("-" * 64)
    print("[OK] Done. You should have received TWO emails:")
    print("     1. [MEDIUM] LOITERING — 25s duration")
    print("     2. [HIGH] LOITERING   — 45s duration (escalated)")
    print("")
    print("  If nothing arrived, check the log output above for errors.")
    print("-" * 64)


if __name__ == "__main__":
    main()
