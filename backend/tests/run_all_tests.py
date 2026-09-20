import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.test_feature1_intrusion import test_restricted_intrusion_escalation, test_excluded_zone_suppression
from tests.test_feature2_weapons import test_weapon_detection_with_person, test_knife_detection
from tests.test_feature3_unattended import test_unattended_object_owner_association
from tests.test_feature4_notifications import test_async_notifier_queue_non_blocking, test_alert_manager_cooldown_deduplication
from tests.test_dual_dashboards import test_dual_dashboard_filtering

def main():
    print("=" * 60)
    print("  RUNNING AI SURVEILLANCE SYSTEM VERIFICATION SUITE")
    print("=" * 60)

    print("[1/5] Testing Feature 1: Intrusion & Multi-Zone Rules...")
    test_restricted_intrusion_escalation()
    test_excluded_zone_suppression()
    print("      -> Feature 1 PASSED.")

    print("[2/5] Testing Feature 2: Weapon Detection (Knife + Gun)...")
    test_weapon_detection_with_person()
    test_knife_detection()
    print("      -> Feature 2 PASSED.")

    print("[3/5] Testing Feature 3: Unattended Object Detection...")
    test_unattended_object_owner_association()
    print("      -> Feature 3 PASSED.")

    print("[4/5] Testing Feature 4: Async Notifications & Cooldown...")
    test_async_notifier_queue_non_blocking()
    test_alert_manager_cooldown_deduplication()
    print("      -> Feature 4 PASSED.")

    print("[5/5] Testing Dual Dashboards Alert Filtering...")
    test_dual_dashboard_filtering()
    print("      -> Dual Dashboards PASSED.")

    print("=" * 60)
    print("  ALL 4 CORE FEATURES & DUAL DASHBOARDS VERIFIED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    main()
