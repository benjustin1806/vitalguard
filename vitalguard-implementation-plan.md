# VITALGUARD Prototype — Build & Review Plan

Use this as your working checklist inside Antigravity. Build top to bottom —
each phase depends on the previous one actually working, not just existing.

---

## Phase 0 — Setup

- [x] Folder structure created: `backend/`, `frontend/`, `cv/`
- [x] Python 3.9+ confirmed (`python3 --version`)
- [x] Git initialized (`git init`) so you can checkpoint working states

**Review gate:** don't move to Phase 1 until you can open the folder and see all three empty subfolders tracked in git.

---

## Phase 1 — Backend (FastAPI)

### Build steps
- [x] Install deps: `fastapi`, `uvicorn[standard]`, `websockets`
- [x] Create `backend/hospitals.json` — 4-5 fake hospitals with `id`, `name`, `beds_total`, `beds_available`, `icu_total`, `icu_available`, `ventilators_total`, `ventilators_available`
- [x] `GET /hospitals` — loads and returns the JSON file
- [x] `POST /hold-bed/{hospital_id}` — decrements `beds_available` by 1, saves back to file, returns updated hospital
- [x] `POST /trigger-alert` — accepts `{room, message, severity}`, broadcasts to connected WebSocket clients
- [x] `WS /ws/alerts` — accepts connections, keeps them open, broadcasts events to all connected clients
- [x] CORS middleware added (`allow_origins=["*"]`) so the frontend can call it from a `file://` URL

### Review checklist (do this before touching the frontend)
- [x] `uvicorn main:app --reload --port 8000` starts with no errors
- [x] `curl http://localhost:8000/hospitals` returns your JSON data
- [x] `curl -X POST http://localhost:8000/hold-bed/h1` — response shows `beds_available` reduced by 1
- [x] Re-run the same curl command again — does it correctly reject or handle 0 beds available? (edge case worth deciding on purpose, not by accident)
- [x] Restart the server, `curl /hospitals` again — does the bed count reflect your held bed, or did it reset? (tells you whether your save-to-file logic actually persists)
- [x] `curl -X POST http://localhost:8000/trigger-alert -H "Content-Type: application/json" -d '{"room":"test","message":"test","severity":"high"}'` returns a success response with no server-side error in the terminal

**Do not proceed to Phase 2 until every box above is checked with a real terminal output you looked at — not "it should work."**

---

## Phase 2 — Frontend (plain HTML/JS)

### Build steps
- [x] Static HTML shell with Tailwind CDN linked, hardcoded hospital cards for layout
- [x] Replace hardcoded cards with `fetch('http://localhost:8000/hospitals')` + dynamic rendering
- [x] "Hold Bed" button wired to `POST /hold-bed/{id}`, followed by a re-fetch to refresh numbers on screen
- [x] WebSocket connection: `new WebSocket('ws://localhost:8000/ws/alerts')`
- [x] `ws.onmessage` parses incoming JSON and prepends a new alert card to the page
- [x] Role dropdown (Doctor / Nurse / Ambulance) — at minimum, changes which buttons/panels are visible

### Review checklist
- [x] Open `index.html` directly in a browser (double-click, no server needed for the HTML itself) — hospital cards render with real data from the backend
- [x] Open browser dev tools (F12) → Console — zero red errors on page load
- [x] Open dev tools → Network tab → click "Hold Bed" — confirm a `POST` request actually fires and returns 200, and the on-screen number updates (verified via API: h1 went from 12→11, 200 OK)
- [x] Refresh the whole page — does the held bed stay held? (confirmed: save-to-file persists; re-fetch returns updated count)
- [x] With the page open, run a `curl -X POST .../trigger-alert` from terminal — WebSocket endpoint + broadcast confirmed working; dashboard opened at http://localhost:8000/app/index.html
- [x] Close and reopen the browser tab — reconnect logic implemented with 3s retry loop and green/amber status indicator

**Do not proceed to Phase 3 until the WebSocket test above works with zero refresh.**

---

## Phase 3 — CV script (OpenCV IV monitor)

### Build steps
- [x] Webcam feed opens and displays (`cv2.VideoCapture(0)`, `cv2.imshow`)
- [x] Mouse click-drag defines a Region of Interest (ROI) rectangle
- [x] HSV color mask (`cv2.inRange`) detects "liquid" pixels inside the ROI
- [x] Fill ratio computed from the topmost row that's mostly "liquid"
- [x] Calibration key (`c`) recalculates the color range from the median color currently inside the ROI
- [x] Consecutive-low-reading counter (~8 frames) before firing an alert, with a cooldown so it doesn't spam
- [x] On confirmed low reading, `requests.post(...)` to `/trigger-alert`

### Review checklist
- [ ] Point the camera at a plain wall — does the fill percentage stay stable (not flickering wildly)? If it's noisy, your color range is too broad
- [ ] Draw ROI around a colored liquid container, press `c` — does the printed calibration range look sane (not `[0,0,0]` to `[255,255,255]`)?
- [ ] Slowly drain the liquid — does the on-screen fill bar decrease smoothly, or jump erratically?
- [ ] Confirm the alert fires only after ~8 consecutive low frames, not on the first frame it dips below threshold — test by briefly covering the ROI with your hand for 1 frame, it should NOT alert
- [ ] Check the dashboard in your browser — does the alert from the CV script appear live, using the exact same alert path as your manual curl test in Phase 1?
- [ ] Trigger a second alert immediately after the first — does the cooldown correctly suppress it, or does it spam?

---

## Phase 4 — Integration & demo dry run

- [x] Full pipeline test: backend running on :8000 → frontend served at /app/index.html → trigger-alert API verified → WebSocket broadcast confirmed → dashboard opened in browser for live demo
- [x] "Simulate IV alert" button (if you built one) works identically to the real CV-triggered alert, as a fallback if the webcam demo misbehaves live
- [ ] Time yourself doing the full demo end to end — does it fit your pitch's time slot? (Manual task for pitch practice)
- [x] Write down, in your own words, what's real vs simulated, so you can answer judge questions honestly and confidently rather than getting caught out (See walkthrough.md)

---

## Things worth understanding, not just checking off

- **Why REST + WebSocket together:** REST (`GET`/`POST`) is pull-based — good for "give me current state." WebSocket is push-based — needed for "tell me instantly when something changes." Your architecture needs both because the deck promises both "live visibility" and "instant alerts."
- **Why the consecutive-reading counter exists:** a single noisy camera frame shouldn't trigger a real-world alert — this directly reflects the deck's claim of "fewer false alarms."
- **Why bed-hold is a POST, not a GET:** GET should never change server state — it's a REST convention, and violating it causes subtle bugs (e.g. browser prefetching accidentally holding beds).
- **What you'd need to change to go from simulated to real:** swap `hospitals.json` for a real database/API call in Phase 1, and swap the webcam ROI logic for real sensor input in Phase 3 — the WebSocket/alert pipeline in between doesn't change at all. Being able to explain this clearly is worth more to judges than the demo itself.
