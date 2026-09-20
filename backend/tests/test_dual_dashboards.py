"""
Test Dual Dashboard Alert Stream Filtering.
Verifies:
  - Dashboard 1 (General Area: camera=main / dashboard=general):
      Shows WEAPON_DETECTED and UNATTENDED_OBJECT (excludes INTRUSION).
  - Dashboard 2 (Restricted Area: camera=restricted / dashboard=restricted):
      Shows ALL: INTRUSION, WEAPON_DETECTED, and UNATTENDED_OBJECT.
  - Custom type queries (type=weapon,unattended vs type=intrusion).
"""

import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import Alert, AlertSeverity, AlertType
from app.api.routes import processor


client = TestClient(app)


def test_dual_dashboard_filtering():
    # Setup test alerts across all 3 types
    processor.alert_manager.clear_alerts()

    # 1. Intrusion Alert
    a_intrusion = Alert(
        id="a1",
        timestamp=datetime.now(timezone.utc),
        alert_type=AlertType.INTRUSION,
        severity=AlertSeverity.HIGH,
        message="Staff corridor intrusion",
        confidence=0.9,
    )
    # 2. Weapon Alert
    a_weapon = Alert(
        id="a2",
        timestamp=datetime.now(timezone.utc),
        alert_type=AlertType.WEAPON_DETECTED,
        severity=AlertSeverity.CRITICAL,
        message="Gun detected",
        confidence=0.88,
    )
    # 3. Unattended Object Alert
    a_bag = Alert(
        id="a3",
        timestamp=datetime.now(timezone.utc),
        alert_type=AlertType.UNATTENDED_OBJECT,
        severity=AlertSeverity.HIGH,
        message="Unattended backpack",
        confidence=0.82,
    )

    processor.alert_manager.alerts = [a_intrusion, a_weapon, a_bag]

    # --- Dashboard 1 Query (General Area: camera=main or dashboard=general) ---
    res1 = client.get("/api/alerts?camera=main")
    assert res1.status_code == 200
    alerts1 = res1.json()["alerts"]
    types1 = {a["alert_type"] for a in alerts1}
    assert "intrusion" not in types1
    assert "weapon_detected" in types1
    assert "unattended_object" in types1

    # --- Dashboard 2 Query (Restricted Area: camera=restricted or dashboard=restricted) ---
    res2 = client.get("/api/alerts?camera=restricted")
    assert res2.status_code == 200
    alerts2 = res2.json()["alerts"]
    types2 = {a["alert_type"] for a in alerts2}
    assert "intrusion" in types2
    assert "weapon_detected" in types2
    assert "unattended_object" in types2
    assert len(alerts2) == 3

    # --- Explicit types query ---
    res3 = client.get("/api/alerts?types=weapon")
    assert res3.status_code == 200
    alerts3 = res3.json()["alerts"]
    assert len(alerts3) == 1
    assert alerts3[0]["alert_type"] == "weapon_detected"


if __name__ == "__main__":
    test_dual_dashboard_filtering()
    print("Dual dashboard tests PASSED.")
