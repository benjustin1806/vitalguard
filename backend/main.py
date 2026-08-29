import os
import json
import uuid
import hashlib
from datetime import datetime, timezone
from typing import List, Optional, Set, Dict
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel


app = FastAPI(title="VitalGuard Backend")

# CORS middleware to allow calls from any local file or origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# File paths
HOSPITALS_FILE = os.path.join(os.path.dirname(__file__), "hospitals.json")
PATIENTS_FILE  = os.path.join(os.path.dirname(__file__), "patients.json")
STAFF_FILE     = os.path.join(os.path.dirname(__file__), "staff.json")

# In-memory session token store (token_str -> staff_dict)
TOKEN_STORE: Dict[str, dict] = {}

def load_staff() -> List[dict]:
    """Read staff records from JSON file."""
    if not os.path.exists(STAFF_FILE):
        return []
    try:
        with open(STAFF_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def hash_password(password: str, salt: str) -> str:
    """Computes SHA-256 hash with salt for secure password verification."""
    return hashlib.sha256((salt + password).encode()).hexdigest()

def get_current_staff(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency to enforce Bearer token authentication on protected routes."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.replace("Bearer ", "").strip()
    if token not in TOKEN_STORE:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    return TOKEN_STORE[token]


# ---------------------------------------------------------------------------
# ML Model Loading & Prediction Helper (Phase 6)
# ---------------------------------------------------------------------------
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "ml", "model.joblib")
FEATURES_PATH = os.path.join(os.path.dirname(__file__), "..", "ml", "feature_columns.json")

ml_model = None
ml_feature_columns = []

def load_ml_model():
    global ml_model, ml_feature_columns
    if os.path.exists(MODEL_PATH) and os.path.exists(FEATURES_PATH):
        try:
            import joblib
            ml_model = joblib.load(MODEL_PATH)
            with open(FEATURES_PATH, "r") as f:
                ml_feature_columns = json.load(f)
            print(f"[ML] Model loaded successfully with {len(ml_feature_columns)} features.")
        except Exception as e:
            print(f"[ML] Warning: Could not load ML model: {e}")

load_ml_model()

def compute_risk_score(vitals: dict) -> dict:
    """
    Computes ML Risk Score for a given vitals dictionary.
    Maps patient vitals into the exact feature vector expected by the trained RandomForest model.
    """
    if not vitals:
        return {"risk_level": "Low Risk", "confidence": 0.5, "is_high_risk": False, "method": "default"}

    hr = float(vitals.get("heart_rate") or 75)
    rr = float(vitals.get("respiratory_rate") or 16)
    spo2 = float(vitals.get("spo2") or 98)
    
    # Temperature: Convert Fahrenheit (patient data) to Celsius (dataset format)
    temp_f = float(vitals.get("temperature") or 98.6)
    temp_c = (temp_f - 32.0) * 5.0 / 9.0

    # Blood Pressure parsing
    bp_str = str(vitals.get("blood_pressure") or "120/80")
    try:
        parts = bp_str.split("/")
        systolic = float(parts[0])
        diastolic = float(parts[1])
    except Exception:
        systolic, diastolic = 120.0, 80.0

    pulse_pressure = systolic - diastolic
    map_val = diastolic + (systolic - diastolic) / 3.0

    feature_dict = {
        "Heart Rate": hr,
        "Respiratory Rate": rr,
        "Body Temperature": temp_c,
        "Oxygen Saturation": spo2,
        "Systolic Blood Pressure": systolic,
        "Diastolic Blood Pressure": diastolic,
        "Derived_Pulse_Pressure": pulse_pressure,
        "Derived_MAP": map_val
    }

    if ml_model is not None and ml_feature_columns:
        try:
            import pandas as pd
            input_df = pd.DataFrame([feature_dict])[ml_feature_columns]
            pred = ml_model.predict(input_df)[0]
            probas = ml_model.predict_proba(input_df)[0]
            classes = list(ml_model.classes_)
            
            high_risk_idx = classes.index("High Risk") if "High Risk" in classes else 1
            confidence = float(probas[high_risk_idx]) if len(probas) > high_risk_idx else 0.5
            if str(pred) == "Low Risk":
                confidence = 1.0 - confidence
            
            return {
                "risk_level": str(pred),
                "confidence": round(confidence, 4),
                "is_high_risk": str(pred) == "High Risk",
                "method": "ml_random_forest",
                "vitals_evaluated": {
                    "heart_rate": hr,
                    "spo2": spo2,
                    "temp_c": round(temp_c, 2),
                    "bp": f"{int(systolic)}/{int(diastolic)}"
                }
            }
        except Exception as e:
            print(f"[ML] Prediction error: {e}")

    # Fallback heuristic if model not available
    is_high = spo2 < 95 or hr > 110 or hr < 50 or temp_f > 102.0
    return {
        "risk_level": "High Risk" if is_high else "Low Risk",
        "confidence": 0.85 if is_high else 0.90,
        "is_high_risk": is_high,
        "method": "heuristic_fallback"
    }

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class LoginPayload(BaseModel):
    username: str
    password: str

class AlertPayload(BaseModel):
    room: str
    message: str
    severity: str
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None


class VitalsPayload(BaseModel):
    heart_rate: Optional[int] = None
    blood_pressure: Optional[str] = None
    spo2: Optional[int] = None
    temperature: Optional[float] = None
    respiratory_rate: Optional[int] = None

class MedicationPayload(BaseModel):
    name: str
    scheduled_time: str   # ISO-8601 string, e.g. "2026-08-27T18:00:00Z"

class TakenPayload(BaseModel):
    taken_by: str

class IVStatusPayload(BaseModel):
    fill_percent: float   # 0–100
    flow_rate_ml_hr: Optional[float] = 125.0

# ---------------------------------------------------------------------------
# In-memory WebSocket connection registry
# ---------------------------------------------------------------------------
active_connections: Set[WebSocket] = set()

# ---------------------------------------------------------------------------
# File I/O helpers — Hospitals
# ---------------------------------------------------------------------------

def load_hospitals() -> List[dict]:
    """Read hospitals from JSON file."""
    if not os.path.exists(HOSPITALS_FILE):
        raise HTTPException(status_code=500, detail="hospitals.json file not found")
    try:
        with open(HOSPITALS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read data: {str(e)}")

def save_hospitals(data: List[dict]):
    """Write hospitals to JSON file."""
    try:
        with open(HOSPITALS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save data: {str(e)}")

# ---------------------------------------------------------------------------
# File I/O helpers — Patients
# ---------------------------------------------------------------------------

def load_patients() -> List[dict]:
    """Read patients from JSON file."""
    if not os.path.exists(PATIENTS_FILE):
        raise HTTPException(status_code=500, detail="patients.json file not found")
    try:
        with open(PATIENTS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read patients: {str(e)}")

def save_patients(data: List[dict]):
    """Write patients to JSON file."""
    try:
        with open(PATIENTS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save patients: {str(e)}")

def find_patient(patients: List[dict], patient_id: str) -> dict:
    """Find a patient by id or raise 404."""
    for p in patients:
        if p["id"] == patient_id:
            return p
    raise HTTPException(status_code=404, detail=f"Patient '{patient_id}' not found")

def check_missed_medications(patient: dict) -> bool:
    """
    Inspect all 'pending' medications. If scheduled_time is in the past,
    mark them 'missed'. Returns True if any medications were updated.
    """
    now = datetime.now(timezone.utc)
    changed = False
    for med in patient.get("medications", []):
        if med.get("status") == "pending":
            try:
                scheduled = datetime.fromisoformat(
                    med["scheduled_time"].replace("Z", "+00:00")
                )
                if scheduled < now:
                    med["status"] = "missed"
                    changed = True
            except (ValueError, KeyError):
                pass
    return changed

# ---------------------------------------------------------------------------
# Staff Authentication Routes (Phase 7 Part A)
# ---------------------------------------------------------------------------

@app.post("/login")
def login(payload: LoginPayload):
    """
    Staff login endpoint. Validates username and hashed password.
    Returns session token and staff metadata.
    """
    staff_list = load_staff()
    for s in staff_list:
        if s["username"] == payload.username:
            computed = hash_password(payload.password, s.get("salt", ""))
            if computed == s["password_hash"]:
                token = f"token_{uuid.uuid4().hex}"
                staff_dict = {
                    "id": s["id"],
                    "name": s["name"],
                    "role": s["role"],
                    "username": s["username"],
                    "assigned_patient_ids": s.get("assigned_patient_ids", [])
                }
                TOKEN_STORE[token] = staff_dict
                return {"token": token, "staff": staff_dict}
    raise HTTPException(status_code=401, detail="Invalid username or password")

@app.get("/me")
def get_me(current_staff: dict = Depends(get_current_staff)):
    """Return currently authenticated staff profile."""
    return current_staff

# ---------------------------------------------------------------------------
# Hospital routes & Ambulance Routing (Phase 7 Part B)
# ---------------------------------------------------------------------------

@app.get("/hospitals")
def get_hospitals():
    """Retrieve the list of all hospitals and their current bed capacity."""
    return load_hospitals()

@app.post("/hold-bed/{hospital_id}")
async def hold_bed(hospital_id: str):
    """
    Decrement the beds_available count for a specific hospital by 1.
    Broadcasts an ambulance dispatch event with Google Maps navigation link over WebSocket.
    """
    hospitals = load_hospitals()
    for h in hospitals:
        if h["id"] == hospital_id:
            if h["beds_available"] <= 0:
                raise HTTPException(status_code=400, detail="No beds available to hold")
            h["beds_available"] -= 1
            save_hospitals(hospitals)

            # Generate Google Maps driving directions URL
            lat = h.get("latitude", 12.9716)
            lng = h.get("longitude", 77.5946)
            maps_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}&travelmode=driving"

            dispatch_event = {
                "event": "alert",
                "type": "ambulance_dispatch",
                "hospital_id": h["id"],
                "hospital_name": h["name"],
                "hospital_address": h.get("address", "Emergency Hospital Location"),
                "latitude": lat,
                "longitude": lng,
                "maps_url": maps_url,
                "message": f"EMERGENCY DISPATCH: Bed held at {h['name']}. Direct navigation route generated.",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await broadcast_alert(dispatch_event)
            return h
    raise HTTPException(status_code=404, detail="Hospital not found")


# ---------------------------------------------------------------------------
# Alert broadcast route (extended with optional patient fields)
# ---------------------------------------------------------------------------

@app.post("/trigger-alert")
async def trigger_alert(alert: AlertPayload):
    """
    Accepts an alert and broadcasts it to all active WebSocket connections.
    Optionally carries patient_id and patient_name for patient-specific alerts.
    """
    alert_dict = alert.model_dump()
    await broadcast_alert(alert_dict)
    return {"status": "success", "broadcasted_to": len(active_connections)}

# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    WebSocket endpoint. Maintains active client connections and registers
    them for alert broadcasting.
    """
    await websocket.accept()
    active_connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        active_connections.discard(websocket)

async def broadcast_alert(data: dict):
    """Broadcasts a JSON payload to all active WebSocket clients."""
    if not active_connections:
        return
    for connection in list(active_connections):
        try:
            await connection.send_json(data)
        except Exception:
            active_connections.discard(connection)

# ---------------------------------------------------------------------------
# Patient routes — Phase 5 & 6 (ML Risk Scoring)
# ---------------------------------------------------------------------------

@app.get("/patients")
def get_patients(authorization: Optional[str] = Header(None)):
    """
    Return a lightweight summary list of all patients.
    If a valid Bearer token is provided, filters results to only assigned patients.
    """
    patients = load_patients()
    allowed_ids = None
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        if token in TOKEN_STORE:
            allowed_ids = set(TOKEN_STORE[token].get("assigned_patient_ids", []))

    summary = []
    for p in patients:
        if allowed_ids is not None and p["id"] not in allowed_ids:
            continue
        med_statuses = [m["status"] for m in p.get("medications", [])]
        risk_score = compute_risk_score(p.get("vitals", {}))
        summary.append({
            "id": p["id"],
            "name": p["name"],
            "room": p["room"],
            "assigned_doctor": p["assigned_doctor"],
            "assigned_nurse": p["assigned_nurse"],
            "iv_fill_percent": p.get("iv_status", {}).get("fill_percent", 100),
            "medication_statuses": med_statuses,
            "risk_score": risk_score,
        })
    return summary

@app.get("/patients/{patient_id}")
def get_patient(patient_id: str):
    """
    Return the full patient record including ML risk_score.
    Also checks for overdue pending medications and marks them 'missed' before returning.
    """
    patients = load_patients()
    patient = find_patient(patients, patient_id)

    # Lazily compute missed medications on every read
    if check_missed_medications(patient):
        save_patients(patients)

    # Calculate dynamic risk score
    patient_copy = dict(patient)
    patient_copy["risk_score"] = compute_risk_score(patient.get("vitals", {}))
    return patient_copy

@app.post("/patients/{patient_id}/risk-score")
def get_patient_risk_score(patient_id: str):
    """
    Dedicated endpoint to retrieve or evaluate the ML Risk Score for a patient.
    """
    patients = load_patients()
    patient = find_patient(patients, patient_id)
    vitals = patient.get("vitals", {})
    risk = compute_risk_score(vitals)
    return {
        "patient_id": patient_id,
        "patient_name": patient["name"],
        "vitals": vitals,
        "risk_score": risk
    }

@app.patch("/patients/{patient_id}/vitals")
def update_vitals(patient_id: str, payload: VitalsPayload, current_staff: dict = Depends(get_current_staff)):
    """
    Update one or more vitals fields for a patient.
    Only provided (non-None) fields are updated. Stamps last_updated.
    Returns updated patient object with new risk_score.
    """
    patients = load_patients()
    patient = find_patient(patients, patient_id)

    vitals = patient.setdefault("vitals", {})
    update_data = payload.model_dump(exclude_none=True)
    vitals.update(update_data)
    vitals["last_updated"] = datetime.now(timezone.utc).isoformat()

    save_patients(patients)

    patient_copy = dict(patient)
    patient_copy["risk_score"] = compute_risk_score(vitals)
    return patient_copy

@app.post("/patients/{patient_id}/medications")
def add_medication(patient_id: str, payload: MedicationPayload, current_staff: dict = Depends(get_current_staff)):
    """
    Add a new medication to a patient's medication list.
    Status defaults to 'pending'.
    """
    patients = load_patients()
    patient = find_patient(patients, patient_id)

    new_med = {
        "id": f"m{uuid.uuid4().hex[:8]}",
        "name": payload.name,
        "scheduled_time": payload.scheduled_time,
        "status": "pending",
        "taken_at": None,
        "taken_by": None,
    }
    patient.setdefault("medications", []).append(new_med)
    save_patients(patients)
    return new_med

@app.patch("/patients/{patient_id}/medications/{med_id}/taken")
def mark_medication_taken(patient_id: str, med_id: str, payload: TakenPayload, current_staff: dict = Depends(get_current_staff)):
    """
    Mark a specific medication as taken for a patient.
    Stamps taken_at with current UTC time and records taken_by from payload.
    Broadcasts a WebSocket event so both doctor and nurse views update live.
    """
    patients = load_patients()
    patient = find_patient(patients, patient_id)

    for med in patient.get("medications", []):
        if med["id"] == med_id:
            if med["status"] == "taken":
                raise HTTPException(status_code=400, detail="Medication already marked as taken")
            if med["status"] == "missed":
                raise HTTPException(status_code=400, detail="Medication was missed and cannot be marked taken")
            med["status"] = "taken"
            med["taken_at"] = datetime.now(timezone.utc).isoformat()
            med["taken_by"] = payload.taken_by
            save_patients(patients)
            return {
                "patient_id": patient_id,
                "medication": med,
                "event": "medication_taken",
            }


    raise HTTPException(status_code=404, detail=f"Medication '{med_id}' not found for patient '{patient_id}'")

@app.patch("/patients/{patient_id}/iv-status")
async def update_iv_status(patient_id: str, payload: IVStatusPayload):
    """
    Update a patient's IV fill percentage and flow rate.
    Calculates volume remaining, time remaining, and drip rate.
    Broadcasts iv_updated event plus Nurse Phone Alert & Doctor SMS Payload to WebSocket clients.
    """
    LOW_IV_THRESHOLD = 20.0
    TOTAL_BAG_VOLUME_ML = 1000.0  # 1000 mL standard IV bag

    patients = load_patients()
    patient = find_patient(patients, patient_id)

    iv = patient.setdefault("iv_status", {})
    iv["fill_percent"] = payload.fill_percent
    flow_rate = payload.flow_rate_ml_hr if payload.flow_rate_ml_hr is not None else iv.get("flow_rate_ml_hr", 125.0)
    iv["flow_rate_ml_hr"] = flow_rate

    # Calculate volume remaining (mL) and time remaining (mins)
    vol_remaining_ml = (payload.fill_percent / 100.0) * TOTAL_BAG_VOLUME_ML
    time_remaining_mins = int((vol_remaining_ml / flow_rate) * 60.0) if flow_rate > 0 else 0
    drip_rate_gtt_min = int((flow_rate * 20.0) / 60.0)  # Standard 20 gtt/mL drop factor

    iv["vol_remaining_ml"] = round(vol_remaining_ml, 1)
    iv["time_remaining_mins"] = time_remaining_mins
    iv["drip_rate_gtt_min"] = drip_rate_gtt_min
    iv["last_updated"] = datetime.now(timezone.utc).isoformat()

    save_patients(patients)

    now_iso = datetime.now(timezone.utc).isoformat()
    doctor_name = patient.get("assigned_doctor", "Dr. Priya Nair")
    nurse_name = patient.get("assigned_nurse", "Nurse Anita")

    # 1. Broadcast IV status update so UI gauges and flow indicators refresh live
    update_event = {
        "event": "iv_updated",
        "patient_id": patient_id,
        "patient_name": patient["name"],
        "room": patient["room"],
        "fill_percent": payload.fill_percent,
        "flow_rate_ml_hr": flow_rate,
        "time_remaining_mins": time_remaining_mins,
        "drip_rate_gtt_min": drip_rate_gtt_min,
        "iv_status": iv
    }
    await broadcast_alert(update_event)

    # 2. Critical notification dispatch if low or empty
    if payload.fill_percent < LOW_IV_THRESHOLD:
        is_empty = payload.fill_percent <= 0.0
        severity_label = "EMPTY" if is_empty else "CRITICALLY LOW"

        nurse_push = {
            "title": f"🚨 IV DRIP {severity_label}",
            "body": f"Ward {patient['room']}: IV bag for {patient['name']} is {severity_label.lower()} ({payload.fill_percent:.0f}%). Replace immediately!",
            "timestamp": now_iso,
            "patient_id": patient_id,
            "patient_name": patient["name"],
            "room": patient["room"],
            "severity": "high"
        }

        doctor_sms = {
            "doctor_name": doctor_name,
            "doctor_phone": "+1 (555) 019-2834",
            "message": f"URGENT ALERT: Patient {patient['name']} ({patient['room']}) IV bag is {severity_label} ({payload.fill_percent:.0f}%). {nurse_name} notified.",
            "timestamp": now_iso,
            "status": "DELIVERED VIA VITALGUARD SMS",
            "patient_id": patient_id,
            "patient_name": patient["name"]
        }

        alert = {
            "event": "alert",
            "room": patient["room"],
            "message": f"IV drip {severity_label.lower()} ({payload.fill_percent:.0f}%) for {patient['name']} — nurse & doctor notified.",
            "severity": "high",
            "patient_id": patient_id,
            "patient_name": patient["name"],
            "nurse_phone_notification": nurse_push,
            "doctor_sms_payload": doctor_sms
        }
        await broadcast_alert(alert)

    return {"patient_id": patient_id, "iv_status": iv}

# ---------------------------------------------------------------------------
# Static frontend mount — MUST come after all API routes
# ---------------------------------------------------------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

@app.get("/", include_in_schema=False)
def root():
    """Redirect root URL to the frontend dashboard."""
    return RedirectResponse(url="/app/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
