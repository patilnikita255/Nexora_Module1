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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_alert_notification(
    alert: Alert,
    snapshot_path: Optional[str] = None,
) -> None:
    """
    Enqueue an alert for background notification delivery.

    This is the single entry point that AlertManager (and any future caller)
    should use. Returns immediately — actual sending happens on the worker
    thread.

    Args:
        alert: The Alert object to notify about.
        snapshot_path: Optional absolute path to the snapshot JPEG to attach
                       to the email.
    """
    settings = get_settings()

    if not settings.email_notifications_enabled and not settings.sms_notifications_enabled:
        logger.debug(
            "[Notifier] Both email and SMS disabled — skipping alert %s.",
            alert.id,
        )
        return

    _start_worker_if_needed()

    try:
        _notification_queue.put_nowait((alert, snapshot_path))
    except queue.Full:
        logger.warning(
            "[Notifier] Queue full — dropping notification for alert %s.",
            alert.id,
        )


# ---------------------------------------------------------------------------
# Email channel (smtplib — stdlib, no extra dependency)
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

    titles = {
        "loitering": "Suspicious Loitering Detected",
        "suspicious_activity": "Suspicious Activity Detected",
    }
    return titles.get(atype, "Security Alert")


def _friendly_severity(alert: Alert) -> str:
    """Map severity to a human-readable urgency level."""
    levels = {
        "low": "Low Priority - For your awareness",
        "medium": "Medium Priority - Please review when possible",
        "high": "High Priority - Requires prompt attention",
        "critical": "CRITICAL - Immediate action required",
    }
    return levels.get(alert.severity.value, alert.severity.value.upper())


def _friendly_description(alert: Alert) -> str:
    """Generate a plain-English description based on alert type."""
    atype = alert.alert_type.value
    dur = int(alert.duration_seconds)

    if atype == "intrusion":
        zone_str = f"the restricted area '{alert.zone_name}'" if alert.zone_name else "a restricted or off-limits zone"
        return (
            f"A person (ID:{alert.object_id or 'Unknown'}) has breached {zone_str} and has "
            f"remained inside for {dur} seconds. Please verify authorization immediately."
        )
    elif atype == "unattended_object":
        owner_info = ""
        if "Owner:" in alert.message:
            owner_part = alert.message.split("Owner:")[1].split(")")[0].strip()
            owner_info = f" The item was previously associated with {owner_part}, who has now walked away."
        return (
            f"A bag or personal item has been left unattended for {dur} seconds with no owner nearby.{owner_info} "
            f"Please inspect the item for security compliance."
        )
    elif atype == "weapon_detected":
        msg_lower = alert.message.lower()
        if "knife" in msg_lower:
            weapon_str = "a KNIFE (edged weapon)"
        elif any(w in msg_lower for w in ("gun", "firearm", "pistol", "rifle")):
            weapon_str = "a FIREARM / GUN (lethal weapon)"
        else:
            weapon_str = "a dangerous weapon"

        return (
            f"CRITICAL THREAT: {weapon_str.upper()} has been detected on surveillance.\n"
            f"  Threat Details:   {alert.message}\n"
            f"  Action Required:  Assess situation immediately and dispatch security personnel."
        )
    elif atype == "loitering":
        return (
            f"A person has been standing in the area for {dur} seconds."
        )
    else:
        return alert.message


def _format_email_body(alert: Alert) -> str:
    """Build a clear, human-readable email body that anyone can understand."""
    title = _friendly_alert_title(alert)
    urgency = _friendly_severity(alert)
    description = _friendly_description(alert)
    time_str = alert.timestamp.strftime("%B %d, %Y at %I:%M:%S %p (UTC)")

    lines = [
        f"[SECURITY ALERT] {title}",
        f"{'=' * 50}",
        "",
        f"Urgency:      {urgency}",
        f"Detected at:  {time_str}",
    ]

    if alert.alert_type.value == "weapon_detected":
        msg_lower = alert.message.lower()
        w_name = "KNIFE (Edged Weapon)" if "knife" in msg_lower else ("FIREARM / HANDGUN" if any(w in msg_lower for w in ("gun", "firearm", "pistol", "rifle")) else "DANGEROUS WEAPON")
        lines.append(f"Threat Type:  {w_name}")
    elif alert.alert_type.value == "intrusion" and alert.zone_name:
        lines.append(f"Zone Name:    {alert.zone_name}")
    elif alert.alert_type.value == "unattended_object" and "Owner:" in alert.message:
        owner_part = alert.message.split("Owner:")[1].split(")")[0].strip()
        lines.append(f"Owner Info:   {owner_part}")

    lines.extend([
        f"Confidence:   {alert.confidence:.0%}",
        "",
        f"What happened:",
        f"  {description}",
        "",
    ])

    if alert.snapshot_url:
        lines.append("[SNAPSHOT] A photo snapshot of the incident is attached to this email.")

    lines.extend([
        "",
        "-" * 50,
        "What should you do?",
        "  - Review the camera feed for the area in question.",
        "  - If the situation looks concerning, notify on-site security.",
        "  - For weapon alerts, contact emergency services immediately.",
        "",
        "This is an automated alert from the AI Video Surveillance System.",
        "If you believe this is a false alarm, no action is needed.",
    ])

    return "\n".join(lines)


def _send_email(alert: Alert, snapshot_path: Optional[str] = None) -> None:
    """Send an alert email via SMTP with optional snapshot attachment."""
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
        f"Security Alert: {_friendly_alert_title(alert)} "
        f"[{alert.severity.value.capitalize()} Priority]"
    )

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    # Body
    body = _format_email_body(alert)
    msg.attach(MIMEText(body, "plain", "utf-8"))

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
    """Build a compact but human-readable SMS body."""
    title = _friendly_alert_title(alert)
    dur = int(alert.duration_seconds)
    severity = alert.severity.value.upper()
    time_str = alert.timestamp.strftime("%I:%M:%S %p")

    atype = alert.alert_type.value
    if atype == "intrusion":
        zone = alert.zone_name or "Restricted Zone"
        detail = f"Intruder in '{zone}' ({dur}s)."
    elif atype == "unattended_object":
        owner = ""
        if "Owner:" in alert.message:
            owner = f" [{alert.message.split('Owner:')[1].split(')')[0].strip()}]"
        detail = f"Unattended item{owner} ({dur}s)."
    elif atype == "weapon_detected":
        msg_lower = alert.message.lower()
        w_tag = "KNIFE" if "knife" in msg_lower else ("GUN/FIREARM" if any(w in msg_lower for w in ("gun", "firearm", "pistol", "rifle")) else "WEAPON")
        detail = f"[CRITICAL THREAT] {w_tag} DETECTED! Urgent response required."
    else:
        detail = alert.message[:60]

    return (
        f"[ALERT] {title}\n"
        f"{detail}\n"
        f"Priority: {severity} | {time_str}"
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
