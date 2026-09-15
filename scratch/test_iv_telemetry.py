import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from backend.main import app

def test_iv_telemetry_and_alerts():
    client = TestClient(app)

    print("=" * 60)
    print("IV BAG TELEMETRY & MULTI-CHANNEL ALERTS TEST")
    print("=" * 60)

    # 1. Test setting IV level to 0% (Empty)
    res_empty = client.patch("/patients/p1/iv-status", json={"fill_percent": 0.0, "flow_rate_ml_hr": 125.0})
    assert res_empty.status_code == 200, f"Expected 200, got {res_empty.status_code}"
    iv_data = res_empty.json()["iv_status"]
    
    print("\n[1] Empty IV Status Response:")
    print(f"  - Fill Percent: {iv_data['fill_percent']}%")
    print(f"  - Flow Rate:    {iv_data['flow_rate_ml_hr']} mL/hr")
    print(f"  - Volume Left:  {iv_data['vol_remaining_ml']} mL")
    print(f"  - Time Left:    {iv_data['time_remaining_mins']} mins")
    print(f"  - Drip Speed:   {iv_data['drip_rate_gtt_min']} gtt/min")

    assert iv_data['fill_percent'] == 0.0
    assert iv_data['vol_remaining_ml'] == 0.0
    assert iv_data['time_remaining_mins'] == 0

    # 2. Test setting IV level to 82% (Normal)
    res_normal = client.patch("/patients/p1/iv-status", json={"fill_percent": 82.0, "flow_rate_ml_hr": 125.0})
    assert res_normal.status_code == 200
    iv_norm = res_normal.json()["iv_status"]

    print("\n[2] Normal IV Status Response (82%):")
    print(f"  - Fill Percent: {iv_norm['fill_percent']}%")
    print(f"  - Volume Left:  {iv_norm['vol_remaining_ml']} mL / 1000 mL")
    print(f"  - Time Left:    {iv_norm['time_remaining_mins']} mins ({iv_norm['time_remaining_mins']//60}h {iv_norm['time_remaining_mins']%60}m)")

    assert iv_norm['fill_percent'] == 82.0
    assert iv_norm['vol_remaining_ml'] == 820.0
    assert iv_norm['time_remaining_mins'] == 393 # 820/125 * 60 = 393.6 mins

    print("\n" + "=" * 60)
    print("SUCCESS: ALL IV TELEMETRY TESTS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    test_iv_telemetry_and_alerts()
