"""
Notification Service — sends email and SMS alerts via a background worker.

Architecture:
  - Single entry point: send_alert_notification(alert, snapshot_path)
  - Background daemon thread pulls from a queue — never blocks the video loop
  - Email via smtplib (stdlib), SMS via Twilio
  - Each channel: try/except with retries, then log-and-drop
  - Channels are independent — one failing doesn't block the other
"""

from __future__ import annotations

import logging
import os
import queue
import smtplib
import threading
import time
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from typing import Optional

from app.config import get_settings
from app.models.schemas import Alert

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level queue and worker
# ---------------------------------------------------------------------------

_notification_queue: queue.Queue = queue.Queue(maxsize=200)
_worker_started = False
_worker_lock = threading.Lock()

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


def _start_worker_if_needed() -> None:
    """Lazily start the background daemon worker thread (once)."""
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        t = threading.Thread(target=_worker, daemon=True, name="notifier-worker")
        t.start()
        _worker_started = True
        logger.info("[Notifier] Background worker thread started.")


def _worker() -> None:
    """Pull (alert, snapshot_path) tuples off the queue and dispatch."""
    while True:
        try:
            alert, snapshot_path = _notification_queue.get()
        except Exception:
            continue

        settings = get_settings()

        # --- Email (independent) ---
        if settings.email_notifications_enabled:
            _send_with_retry(
                _send_email, alert, snapshot_path, channel_name="Email"
            )

        # --- SMS (independent) ---
        if settings.sms_notifications_enabled:
            _send_with_retry(
                _send_sms, alert, snapshot_path=None, channel_name="SMS"
            )

        _notification_queue.task_done()


def _send_with_retry(send_fn, alert: Alert, snapshot_path: Optional[str],
                     channel_name: str) -> None:
    """Try send_fn up to MAX_RETRIES times with backoff, then log-and-drop."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            send_fn(alert, snapshot_path)
            logger.info(
                "[Notifier] %s sent successfully for alert %s (attempt %d).",
                channel_name, alert.id, attempt,
            )
            return
        except Exception as exc:
            logger.warning(
                "[Notifier] %s attempt %d/%d failed for alert %s: %s",
                channel_name, attempt, MAX_RETRIES, alert.id, exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)

    logger.error(
        "[Notifier] %s permanently failed for alert %s after %d attempts. "
        "Dropping notification.",
        channel_name, alert.id, MAX_RETRIES,
    )


# Notification deduplication cache: (event_type, object_id, severity) -> last_sent_timestamp
_recent_notifications: dict[tuple[str, str, str], float] = {}
_NOTIFY_COOLDOWN_SECONDS = 60.0
_dedup_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_alert_notification(
    alert: Alert,
    snapshot_path: Optional[str] = None,
) -> None:
    """
    Enqueue an alert for background notification delivery with strict deduplication.
    Prevents repeated notifications for the same event within the cooldown window.
    """
    settings = get_settings()

    if not settings.email_notifications_enabled and not settings.sms_notifications_enabled:
        logger.debug(
            "[Notifier] Both email and SMS disabled — skipping alert %s.",
            alert.id,
        )
        return

    # Anti-duplication check
    dedup_key = (
        alert.alert_type.value,
        str(alert.object_id or ""),
        alert.severity.value.lower(),
    )
    now = time.time()
    with _dedup_lock:
        last_sent = _recent_notifications.get(dedup_key, 0.0)
        if now - last_sent < _NOTIFY_COOLDOWN_SECONDS:
            logger.info(
                "[Notifier] Suppressing duplicate notification for %s (sent %.1fs ago).",
                dedup_key, now - last_sent,
            )
            return
        _recent_notifications[dedup_key] = now

    _start_worker_if_needed()

    try:
        _notification_queue.put_nowait((alert, snapshot_path))
    except queue.Full:
        logger.warning(
            "[Notifier] Queue full — dropping notification for alert %s.",
            alert.id,
        )


# ---------------------------------------------------------------------------
# Email & SMS Formatting (Bold Critical Level & Exact Reasons)
# ---------------------------------------------------------------------------

def _friendly_alert_title(alert: Alert) -> str:
    """Map alert type to a plain-English title."""
    atype = alert.alert_type.value
    if atype == "weapon_detected":
        msg_lower = alert.message.lower()
        if "knife" in msg_lower:
            return "Dangerous Weapon Detected: KNIFE"
        elif any(w in msg_lower for w in ("gun", "firearm", "pistol", "rifle")):
            return "Lethal Threat Detected: FIREARM / GUN"
        return "Dangerous Weapon Detected"
    elif atype == "intrusion":
        zone_str = f": {alert.zone_name}" if alert.zone_name else ""
        return f"Unauthorized Perimeter Intrusion{zone_str}"
    elif atype == "unattended_object":
        return "Unattended Object Detected (Owner Left Area)"
    elif atype == "loitering":
        return "Suspicious Loitering Detected"

    return "Security Alert"


def _extract_reason(alert: Alert) -> str:
    """Extract a concise, authoritative reason for the alert."""
    atype = alert.alert_type.value
    dur = int(alert.duration_seconds)

    if atype == "weapon_detected":
        msg_lower = alert.message.lower()
        if "knife" in msg_lower:
            return "Edged weapon (knife) identified in video feed; immediate safety hazard."
        elif any(w in msg_lower for w in ("gun", "firearm", "pistol", "rifle")):
            return "Lethal firearm identified in video feed; active armed threat protocol triggered."
        return "Unlicensed dangerous weapon identified in monitored area."
    elif atype == "intrusion":
        zone_str = f"'{alert.zone_name}'" if alert.zone_name else "restricted security perimeter"
        return f"Unauthorized person entered protected zone {zone_str} and persisted for {dur}s without clearance."
    elif atype == "unattended_object":
        owner_part = ""
        if "Owner:" in alert.message:
            owner_part = f" (previously carried by {alert.message.split('Owner:')[1].split(')')[0].strip()})"
        return f"Bag/item left isolated with no person nearby for {dur}s{owner_part}."
    elif atype == "loitering":
        if "[" in alert.message and "]" in alert.message:
            details = alert.message.split("[")[1].split("]")[0]
            return f"Restless wandering without legitimate purpose for {dur}s ({details})."
        return f"Person lingering alone in open/monitored area for {dur}s exhibiting casing/pacing patterns."

    return alert.message


def _friendly_description(alert: Alert) -> str:
    """Generate detailed plain-English context for the incident."""
    atype = alert.alert_type.value
    dur = int(alert.duration_seconds)

    if atype == "intrusion":
        zone_str = f"the restricted area '{alert.zone_name}'" if alert.zone_name else "a restricted zone"
        return (
            f"Person (ID:{alert.object_id or 'Unknown'}) breached {zone_str} and has "
            f"remained inside for {dur} seconds. Immediate physical verification required."
        )
    elif atype == "unattended_object":
        owner_info = ""
        if "Owner:" in alert.message:
            owner_part = alert.message.split("Owner:")[1].split(")")[0].strip()
            owner_info = f" The item was previously associated with {owner_part}, who walked away."
        return (
            f"A bag or container has been left unattended for {dur} seconds with no owner nearby.{owner_info} "
            f"Please inspect for security compliance."
        )
    elif atype == "weapon_detected":
        return f"CRITICAL THREAT: {alert.message}. Security personnel must be alerted immediately."
    elif atype == "loitering":
        return f"Person (ID:{alert.object_id or 'Unknown'}) has been observed pacing/lingering for {dur}s. Behavior matches suspicious loitering criteria."
    return alert.message


def _format_email_plain(alert: Alert) -> str:
    """Build a plain-text email body with prominent BOLD headers."""
    title = _friendly_alert_title(alert)
    severity_upper = alert.severity.value.upper()
    reason = _extract_reason(alert)
    description = _friendly_description(alert)
    time_str = alert.timestamp.strftime("%B %d, %Y at %I:%M:%S %p (UTC)")

    return f"""============================================================
**CRITICAL LEVEL: {severity_upper}**
============================================================
**REASON FOR ALERT: {reason}**
------------------------------------------------------------
INCIDENT TITLE:   {title}
TARGET OBJECT ID: {alert.object_id or 'N/A'}
CONFIDENCE:       {alert.confidence:.0%}
DURATION:         {alert.duration_seconds:.1f} seconds
TIMESTAMP:        {time_str}

INCIDENT DETAILS:
  {description}

RECOMMENDED ACTION:
  - Verify live camera feed terminal immediately.
  - Dispatch on-site security response.
============================================================
Automated alert from AI Video Surveillance System.
"""


def _format_email_html(alert: Alert) -> str:
    """Build a styled HTML email with bold colored severity headers."""
    title = _friendly_alert_title(alert)
    severity_upper = alert.severity.value.upper()
    reason = _extract_reason(alert)
    description = _friendly_description(alert)
    time_str = alert.timestamp.strftime("%B %d, %Y at %I:%M:%S %p (UTC)")

    sev_color = "#ef4444" if severity_upper == "CRITICAL" else ("#f59e0b" if severity_upper == "HIGH" else "#3b82f6")

    return f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0b0f19; color: #f8fafc; padding: 24px; margin: 0;">
  <div style="max-width: 600px; margin: 0 auto; background-color: #111827; border: 1px solid #1f2937; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
    <div style="background-color: {sev_color}; padding: 14px 20px;">
      <h1 style="color: #ffffff; margin: 0; font-size: 20px; font-weight: 800; letter-spacing: 0.05em;">
        <b>CRITICAL LEVEL: {severity_upper}</b>
      </h1>
    </div>

    <div style="padding: 20px;">
      <div style="background: rgba(255,255,255,0.04); border-left: 4px solid {sev_color}; padding: 12px 16px; border-radius: 6px; margin-bottom: 18px;">
        <div style="font-size: 11px; text-transform: uppercase; color: #94a3b8; font-weight: 700; margin-bottom: 4px;">REASON FOR ALERT</div>
        <div style="font-size: 15px; color: #ffffff; font-weight: 700; line-height: 1.4;">
          <b>{reason}</b>
        </div>
      </div>

      <table style="width: 100%; border-collapse: collapse; margin-bottom: 18px; font-size: 13px;">
        <tr style="border-bottom: 1px solid #1f2937;">
          <td style="padding: 8px 0; color: #94a3b8;"><b>Incident Type:</b></td>
          <td style="padding: 8px 0; color: #ffffff; font-weight: 600;">{title}</td>
        </tr>
        <tr style="border-bottom: 1px solid #1f2937;">
          <td style="padding: 8px 0; color: #94a3b8;"><b>Target ID:</b></td>
          <td style="padding: 8px 0; color: #ffffff; font-weight: 600;">{alert.object_id or 'N/A'}</td>
        </tr>
        <tr style="border-bottom: 1px solid #1f2937;">
          <td style="padding: 8px 0; color: #94a3b8;"><b>Confidence:</b></td>
          <td style="padding: 8px 0; color: #ffffff; font-weight: 600;">{alert.confidence:.0%}</td>
        </tr>
        <tr style="border-bottom: 1px solid #1f2937;">
          <td style="padding: 8px 0; color: #94a3b8;"><b>Timestamp:</b></td>
          <td style="padding: 8px 0; color: #ffffff;">{time_str}</td>
        </tr>
      </table>

      <div style="margin-bottom: 20px;">
        <div style="font-size: 11px; text-transform: uppercase; color: #94a3b8; font-weight: 700; margin-bottom: 6px;">DETAILS</div>
        <div style="font-size: 13px; color: #cbd5e1; line-height: 1.5; background: #080c14; padding: 12px; border-radius: 6px;">
          {description}
        </div>
      </div>

      <div style="font-size: 11px; color: #64748b; border-top: 1px solid #1f2937; padding-top: 12px;">
        This automated security dispatch was generated by the AI Video Surveillance System.
      </div>
    </div>
  </div>
</body>
</html>"""


def _send_email(alert: Alert, snapshot_path: Optional[str] = None) -> None:
    """Send an alert email via SMTP with HTML/plain bodies and optional snapshot."""
    settings = get_settings()

    recipients = [
        addr.strip()
        for addr in settings.alert_email_to.split(",")
        if addr.strip()
    ]
    if not recipients:
        logger.warning("[Notifier] No email recipients configured (ALERT_EMAIL_TO).")
        return

    subject = (
        f"[{alert.severity.value.upper()}] Security Alert: {_friendly_alert_title(alert)}"
    )

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.smtp_user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    # Attach Plain and HTML parts
    part_plain = MIMEText(_format_email_plain(alert), "plain", "utf-8")
    part_html = MIMEText(_format_email_html(alert), "html", "utf-8")
    msg.attach(part_plain)
    msg.attach(part_html)

    # Snapshot attachment (if exists)
    if snapshot_path:
        base_filename = os.path.basename(snapshot_path)
        app_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidate_paths = [
            snapshot_path,
            os.path.join(settings.snapshots_dir, base_filename),
            os.path.join(app_backend_dir, settings.snapshots_dir, base_filename),
            os.path.join(app_backend_dir, "snapshots", base_filename),
        ]
        resolved_path = next((p for p in candidate_paths if os.path.isfile(p)), None)
        if resolved_path:
            try:
                with open(resolved_path, "rb") as f:
                    part = MIMEBase("image", "jpeg")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f'attachment; filename="{base_filename}"',
                    )
                    msg.attach(part)
                    logger.info("[Notifier] Attached snapshot image: %s", base_filename)
            except Exception as exc:
                logger.warning("[Notifier] Failed to attach snapshot: %s", exc)
        else:
            logger.warning("[Notifier] Snapshot file not found at any candidate path: %s", snapshot_path)

    # Send
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_user, recipients, msg.as_string())


# ---------------------------------------------------------------------------
# SMS channel (Twilio)
# ---------------------------------------------------------------------------

def _format_sms_body(alert: Alert) -> str:
    """Build a compact SMS body with CRITICAL LEVEL and REASON clearly stated."""
    severity = alert.severity.value.upper()
    reason = _extract_reason(alert)
    time_str = alert.timestamp.strftime("%I:%M:%S %p")

    return (
        f"[CRITICAL LEVEL: {severity}]\n"
        f"REASON: {reason}\n"
        f"TARGET ID: {alert.object_id or 'N/A'} | TIME: {time_str}\n"
        f"Surveillance AI Alert"
    )


def _send_sms(alert: Alert, snapshot_path: Optional[str] = None) -> None:
    """Send an alert SMS via Twilio."""
    settings = get_settings()

    recipients = [
        num.strip()
        for num in settings.alert_sms_to.split(",")
        if num.strip()
    ]
    if not recipients:
        logger.warning("[Notifier] No SMS recipients configured (ALERT_SMS_TO).")
        return

    try:
        from twilio.rest import Client  # noqa: delay import so missing package doesn't crash email-only setups
    except ImportError:
        logger.error(
            "[Notifier] twilio package not installed. "
            "Run: pip install twilio"
        )
        return

    client = Client(settings.twilio_sid, settings.twilio_auth_token)
    body = _format_sms_body(alert)

    for number in recipients:
        client.messages.create(
            body=body,
            from_=settings.twilio_from_number,
            to=number,
        )
