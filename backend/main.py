import os
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Set
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

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
# Hospital routes (unchanged)
# ---------------------------------------------------------------------------

@app.get("/hospitals")
def get_hospitals():
    """Retrieve the list of all hospitals and their current bed capacity."""
    return load_hospitals()

@app.post("/hold-bed/{hospital_id}")
def hold_bed(hospital_id: str):
    """
    Decrement the beds_available count for a specific hospital by 1.
    Returns the updated hospital info.
    """
    hospitals = load_hospitals()
    for h in hospitals:
        if h["id"] == hospital_id:
            if h["beds_available"] <= 0:
                raise HTTPException(status_code=400, detail="No beds available to hold")
            h["beds_available"] -= 1
            save_hospitals(hospitals)
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
# Patient routes — Phase 5
# ---------------------------------------------------------------------------

@app.get("/patients")
def get_patients():
    """
    Return a lightweight summary list of all patients:
    id, name, room, assigned staff, iv fill_percent, and medication statuses.
    Avoids returning the full vitals object to keep the list response lean.
    """
    patients = load_patients()
    summary = []
    for p in patients:
        med_statuses = [m["status"] for m in p.get("medications", [])]
        summary.append({
            "id": p["id"],
            "name": p["name"],
            "room": p["room"],
            "assigned_doctor": p["assigned_doctor"],
            "assigned_nurse": p["assigned_nurse"],
            "iv_fill_percent": p.get("iv_status", {}).get("fill_percent", 100),
            "medication_statuses": med_statuses,
        })
    return summary

@app.get("/patients/{patient_id}")
def get_patient(patient_id: str):
    """
    Return the full patient record.
    Also checks for overdue pending medications and marks them 'missed' before
    returning, persisting the change to file if any were updated.
    """
    patients = load_patients()
    patient = find_patient(patients, patient_id)

    # Lazily compute missed medications on every read
    if check_missed_medications(patient):
        save_patients(patients)

    return patient

@app.patch("/patients/{patient_id}/vitals")
def update_vitals(patient_id: str, payload: VitalsPayload):
    """
    Update one or more vitals fields for a patient.
    Only provided (non-None) fields are updated. Stamps last_updated.
    """
    patients = load_patients()
    patient = find_patient(patients, patient_id)

    vitals = patient.setdefault("vitals", {})
    update_data = payload.model_dump(exclude_none=True)
    vitals.update(update_data)
    vitals["last_updated"] = datetime.now(timezone.utc).isoformat()

    save_patients(patients)
    return patient

@app.post("/patients/{patient_id}/medications")
def add_medication(patient_id: str, payload: MedicationPayload):
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
def mark_medication_taken(patient_id: str, med_id: str, payload: TakenPayload):
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
    Update a patient's IV fill percentage.
    Broadcasts iv_updated event to all WebSocket clients.
    If fill_percent drops below 20%, also broadcasts a critical alert.
    """
    LOW_IV_THRESHOLD = 20.0

    patients = load_patients()
    patient = find_patient(patients, patient_id)

    iv = patient.setdefault("iv_status", {})
    iv["fill_percent"] = payload.fill_percent
    iv["last_updated"] = datetime.now(timezone.utc).isoformat()
    save_patients(patients)

    # 1. Always broadcast IV status update so UI gauges refresh live
    update_event = {
        "event": "iv_updated",
        "patient_id": patient_id,
        "patient_name": patient["name"],
        "room": patient["room"],
        "fill_percent": payload.fill_percent,
    }
    await broadcast_alert(update_event)

    # 2. Broadcast high-severity alert if critically low
    if payload.fill_percent < LOW_IV_THRESHOLD:
        alert = {
            "event": "alert",
            "room": patient["room"],
            "message": (
                f"IV drip critically low ({payload.fill_percent:.0f}%) "
                f"for {patient['name']} — refill required immediately."
            ),
            "severity": "high",
            "patient_id": patient_id,
            "patient_name": patient["name"],
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
