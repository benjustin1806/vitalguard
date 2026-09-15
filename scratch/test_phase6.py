import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from backend.main import app

def test_phase6_ml_risk_scoring():
    client = TestClient(app)

    print("=" * 60)
    print("PHASE 6 VERIFICATION TEST SUITE")
    print("=" * 60)

    # 1. Test GET /patients
    res1 = client.get("/patients")
    assert res1.status_code == 200, f"Expected 200, got {res1.status_code}"
    patients = res1.json()
    print(f"\n[1] GET /patients returned {len(patients)} patients:")
    for p in patients:
        rs = p.get("risk_score", {})
        print(f"  - {p['id']} ({p['name']}): {rs.get('risk_level')} (Confidence: {rs.get('confidence', 0)*100:.1f}%)")

    # 2. Test GET /patients/p1
    res2 = client.get("/patients/p1")
    assert res2.status_code == 200
    p1 = res2.json()
    print(f"\n[2] GET /patients/p1 risk score:")
    print(f"  - Risk Level: {p1['risk_score']['risk_level']}")
    print(f"  - Method:     {p1['risk_score']['method']}")

    # 3. Test POST /patients/p1/risk-score
    res3 = client.post("/patients/p1/risk-score")
    assert res3.status_code == 200
    r3_data = res3.json()
    print(f"\n[3] POST /patients/p1/risk-score response:")
    print(f"  - Patient:    {r3_data['patient_name']}")
    print(f"  - Score:      {r3_data['risk_score']['risk_level']} ({r3_data['risk_score']['confidence']*100:.1f}% confidence)")

    # 4. Test PATCH /patients/p1/vitals to trigger High Risk
    print("\n[4] Updating p1 vitals to abnormal (spo2=84, heart_rate=145)...")
    res4 = client.patch("/patients/p1/vitals", json={"spo2": 84, "heart_rate": 145})
    assert res4.status_code == 200
    p1_abnormal = res4.json()
    risk_abnormal = p1_abnormal["risk_score"]
    print(f"  - Updated Risk Level: {risk_abnormal['risk_level']} ({risk_abnormal['confidence']*100:.1f}% confidence)")
    assert risk_abnormal["is_high_risk"] == True, f"Expected High Risk, got {risk_abnormal['risk_level']}"

    # 5. Restore p1 normal vitals
    print("\n[5] Restoring p1 vitals to normal (spo2=97, heart_rate=78)...")
    res5 = client.patch("/patients/p1/vitals", json={"spo2": 97, "heart_rate": 78})
    assert res5.status_code == 200
    p1_restored = res5.json()
    risk_restored = p1_restored["risk_score"]
    print(f"  - Restored Risk Level: {risk_restored['risk_level']} ({risk_restored['confidence']*100:.1f}% confidence)")
    assert risk_restored["is_high_risk"] == False, f"Expected Low Risk, got {risk_restored['risk_level']}"

    print("\n" + "=" * 60)
    print("SUCCESS: ALL PHASE 6 VERIFICATION TESTS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    test_phase6_ml_risk_scoring()
