"""
Standalone test for the Notification Service.

Usage:
  1. Copy .env.example → .env and fill in real SMTP / Twilio credentials.
  2. Set EMAIL_NOTIFICATIONS_ENABLED=true and/or SMS_NOTIFICATIONS_ENABLED=true.
  3. Run:  python test_notifier.py

This sends a FAKE alert through both channels WITHOUT touching the detection
pipeline — exactly the isolation test the implementation plan calls for.
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

    print("=" * 60)
    print("  Notification Service — Standalone Smoke Test")
    print("=" * 60)
    print(f"  Email enabled:  {settings.email_notifications_enabled}")
    print(f"  SMTP host:      {settings.smtp_host or '(not set)'}")
    print(f"  Email to:       {settings.alert_email_to or '(not set)'}")
    print(f"  SMS enabled:    {settings.sms_notifications_enabled}")
    print(f"  Twilio SID:     {settings.twilio_sid[:8] + '...' if settings.twilio_sid else '(not set)'}")
    print(f"  SMS to:         {settings.alert_sms_to or '(not set)'}")
    print("=" * 60)

    if not settings.email_notifications_enabled and not settings.sms_notifications_enabled:
        print(
            "\n[!] Both channels are DISABLED.  Set EMAIL_NOTIFICATIONS_ENABLED=true "
            "and/or SMS_NOTIFICATIONS_ENABLED=true in your .env to test.\n"
        )
        return

    # Build a fake alert
    fake_alert = Alert(
        id="TEST0001",
        timestamp=datetime.now(timezone.utc),
        alert_type=AlertType.INTRUSION,
        severity=AlertSeverity.HIGH,
        message="TEST — Person detected in restricted zone for 8s (this is a fake alert)",
        snapshot_url=None,
        objects_involved=["42"],
        object_id="42",
        duration_seconds=8.0,
        confidence=0.87,
    )

    print("\n[*] Sending fake alert through notification service...")
    send_alert_notification(fake_alert, snapshot_path=None)

    # Give the background worker time to process
    print("[.] Waiting 10 seconds for background delivery...\n")
    time.sleep(10)

    print("[OK] Done. Check your inbox / phone for the test notification.")
    print("   If nothing arrived, review the log output above for errors.\n")


if __name__ == "__main__":
    main()
