# 🛡️ VitalGuard — Real-Time Medical Resource & Patient Safety Monitor

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![WebSockets](https://img.shields.io/badge/WebSockets-Real--Time-brightgreen?style=for-the-badge)](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer--Vision-red?style=for-the-badge&logo=opencv)](https://opencv.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css)](https://tailwindcss.com/)

**VitalGuard** is a dual-layer emergency healthcare command center designed to bridge regional logistics with bedside computer-vision telemetry. It provides instant visibility into hospital bed and equipment capacities while continuously monitoring patient IV infusions to eliminate silent ward risks.

---

## 🌟 Key Features

### 1. 🏥 Regional Hospital Bed & Resource Matrix
* **Real-time Inventory Tracking**: Displays general bed, ICU bed, and ventilator availability across regional hospitals.
* **Transit Bed-Hold Dispatcher**: Enables ambulance crews and emergency staff to reserve open beds in transit (`POST /hold-bed/{id}`).
* **Role-Based Views**: Tailors UI controls dynamically for **Doctors**, **Nurses**, and **Ambulance Drivers**.

### 2. 👁️ Computer-Vision IV Fluid Level Monitor
* **Optical Height Tracking**: Computes liquid column height inside a user-defined Region of Interest (ROI).
* **Color Range Calibration**: Adaptive HSV color masking using median color sampling (`c` key).
* **False-Alarm Noise Filtering**: Requires **8 consecutive low readings** before triggering escalation to eliminate false alarms from camera movement.
* **Alert Cooldown**: Enforces a 15-second cooldown timer between repeat alerts.

### 3. 📋 Patient Registry & Vitals Tracking
* **Per-Patient Telemetry**: Live tracking of heart rate, blood pressure, $\text{SpO}_2$, temperature, and respiratory rate.
* **Medication Administration Schedule**: Auto-evaluates scheduled vs. `pending`, `taken`, or `missed` medications.
* **Live IV Gauge Sync**: Dynamically animates fluid level bars across dashboards when edge CV telemetry updates.

### 4. ⚡ Real-Time WebSocket Broadcast Engine
* **Push-Based Telemetry**: Low-latency WebSocket channel (`ws://localhost:8000/ws/alerts`) for instant cross-device alerts.
* **Zero-Refresh UI**: Emergency alarms render live in the alert panel and patient cards without manual page reloads.

---

## 📁 Repository Structure

```
vitalguard/
├── backend/
│   ├── main.py              # FastAPI application, REST endpoints & WebSocket hub
│   ├── hospitals.json       # Persistent hospital resource dataset
│   ├── patients.json        # Persistent patient registry, vitals & medication schedules
│   └── test_ws.py           # Automated WebSocket broadcast verification script
├── frontend/
│   ├── index.html           # Main Command Center & Hospital Bed Grid dashboard
│   ├── patients.html        # Admitted Patient Registry summary list
│   └── patient.html         # Single patient detailed vitals, IV & medication view
├── cv/
│   └── iv_monitor.py        # OpenCV computer vision IV fluid volume monitor
├── requirements.txt         # Python dependency manifest
└── README.md                # Project documentation
```

---

## 🚀 Quick Start Guide

### Prerequisites
* **Python 3.9+**
* Webcam / Video capture device (for CV IV tracking)

### 1. Setup Virtual Environment & Dependencies
```bash
# Clone the repository
git clone https://github.com/benjustin1806/vitalguard.git
cd vitalguard

# Create and activate virtual environment
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch FastAPI Backend Server
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
> The API will start on **`http://127.0.0.1:8000`**

### 3. Access Command Center Dashboards
Open your browser and navigate to:
* **Command Center**: [http://127.0.0.1:8000/app/index.html](http://127.0.0.1:8000/app/index.html)
* **Patient Registry**: [http://127.0.0.1:8000/app/patients.html](http://127.0.0.1:8000/app/patients.html)

### 4. Run Computer Vision IV Monitor
In a separate terminal window:
```bash
python cv/iv_monitor.py
```
**Controls inside camera window:**
1. **Click & Drag**: Draw a rectangle (ROI) around the IV bottle/fluid column.
2. **Press `c`**: Calibrate color segmentation around the selected liquid.
3. **Press `r`**: Reset selection box.
4. **Press `q`**: Quit the monitor.

---

## 📡 API Endpoint Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/hospitals` | Retrieve all hospital bed & equipment capacity states |
| `POST` | `/hold-bed/{hospital_id}` | Reserve 1 general bed at the specified hospital |
| `GET` | `/patients` | Get summary list of all admitted patients |
| `GET` | `/patients/{id}` | Get full patient record including vitals & medications |
| `PATCH` | `/patients/{id}/vitals` | Update vitals (heart rate, blood pressure, $\text{SpO}_2$, etc.) |
| `POST` | `/patients/{id}/medications` | Prescribe a new scheduled medication |
| `PATCH` | `/patients/{id}/medications/{med_id}/taken` | Mark a medication as administered |
| `PATCH` | `/patients/{id}/iv-status` | Update IV fluid fill percentage (triggers live broadcast) |
| `POST` | `/trigger-alert` | Broadcast generic or patient-tagged emergency alert |
| `WS` | `/ws/alerts` | WebSocket connection for real-time alert stream |

---

## 🛡️ License & Versioning

Maintained under semantic versioning for healthcare technology prototypes.
Every version check-in ensures persistent data integrity, non-blocking WebSocket streams, and validated CV noise suppression.
