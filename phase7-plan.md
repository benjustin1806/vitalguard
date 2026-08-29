# VITALGUARD — Phase 7: Staff Login + Ambulance Dispatch Routing

Two independent features. Build and test Part A fully before starting Part B.

---

# Part A — Doctor/Nurse Login

Goal: doctors and nurses log in and only see the patients assigned to them,
instead of everyone seeing every patient like now.

## Data model

Add `backend/staff.json`:

```json
[
  {
    "id": "s1",
    "name": "Dr. Priya Nair",
    "role": "doctor",
    "username": "priya.nair",
    "password_hash": "<hashed, not plaintext>",
    "assigned_patient_ids": ["p1", "p2"]
  },
  {
    "id": "s2",
    "name": "Nurse Anita",
    "role": "nurse",
    "username": "anita",
    "password_hash": "<hashed, not plaintext>",
    "assigned_patient_ids": ["p1"]
  }
]
```

- Never store plaintext passwords, even in a demo file. Use `bcrypt` or
  `passlib` to hash them once when you create the seed data, and hash again
  the same way when checking a login attempt.
- `assigned_patient_ids` is how you link staff to the patient records that
  already exist from Phase 5.

## Backend — new endpoints

- [ ] `POST /login` — accepts `{username, password}`, checks against
      `staff.json`, and if valid, returns a simple token. For a hackathon,
      this can be as simple as a random string stored in an in-memory dict
      mapping `token -> staff_id` — you do NOT need real JWT/OAuth for this demo.
- [ ] `GET /me` — accepts the token (e.g. `Authorization: Bearer <token>`
      header), returns that staff member's own record (name, role, assigned patients)
- [ ] Update `GET /patients` — if a valid token is provided, filter results to
      only that staff member's `assigned_patient_ids`. If no token, keep the
      old unfiltered behavior for now (or decide to require login everywhere
      — your call, note it either way).
- [ ] Reject actions with a 401 if no valid token is provided on protected
      routes (marking medication taken, adding medication, updating vitals)
      — right now those endpoints don't check who's calling them at all.

### Review checklist — backend
- [ ] `curl -X POST http://localhost:8000/login -d '{"username":"anita","password":"..."}'`
      returns a token on correct credentials, and a clear error on wrong ones
- [ ] Calling `GET /patients` with Anita's token only returns patient `p1`,
      not `p2` — confirms the assignment filter actually works, not just that
      login succeeds
- [ ] Calling a protected endpoint (e.g. mark-medication-taken) with NO token
      returns 401, not a silent success

## Frontend

- [ ] `frontend/login.html` — simple username/password form, POSTs to
      `/login`, stores the returned token (e.g. in `localStorage`)
- [ ] On the patient list / dashboard pages, read the stored token and attach
      it to every fetch call (`Authorization: Bearer <token>` header)
- [ ] If there's no valid token when a protected page loads, redirect back to
      `login.html` instead of silently showing an empty/broken page
- [ ] Add a simple "Logged in as X (role)" indicator and a Logout button
      (logout = just clear the stored token)

### Review checklist — frontend
- [ ] Logging in as Anita and viewing the patient list shows only her
      assigned patients, not all of them
- [ ] Logging in as Priya (doctor) shows her own different assigned patients
- [ ] Opening the dashboard directly without logging in redirects to the
      login page, rather than showing patient data
- [ ] Logout actually prevents further data access until logging in again
      (test: logout, then manually reload the dashboard URL)

---

# Part B — Ambulance Dispatch: Hospital Allotment + Map Route

Goal: when a bed is held for an ambulance dispatch, the ambulance-view screen
gets a live notification of exactly which hospital they've been allotted,
plus a one-tap route.

## Backend

- [ ] Add `latitude` and `longitude` fields to each hospital in
      `hospitals.json` (real or approximate coordinates for your demo hospitals)
- [ ] When `POST /hold-bed/{hospital_id}` succeeds (this endpoint already
      exists from Phase 1), also broadcast a new event type over the existing
      `/ws/alerts` WebSocket:
      ```json
      {
        "type": "ambulance_dispatch",
        "hospital_id": "...",
        "hospital_name": "...",
        "hospital_address": "...",
        "latitude": ...,
        "longitude": ...,
        "maps_url": "https://www.google.com/maps/dir/?api=1&destination=<lat>,<lng>&travelmode=driving",
        "timestamp": "..."
      }
      ```
- [ ] The `maps_url` needs no API key — it's a plain Google Maps directions
      link. When opened, Google Maps uses the device's current location as
      the starting point automatically, which is exactly what an ambulance
      crew needs, with zero setup.

### Review checklist — backend
- [ ] Holding a bed via curl still works as before (Phase 1 behavior unchanged)
- [ ] The broadcast event now includes a `maps_url` field with a real,
      correctly-formatted Google Maps link — paste it into a browser yourself
      once and confirm it actually opens directions to the right place

## Frontend

- [ ] On the existing "Ambulance view" (you already have this role in the
      dropdown from Phase 2) — when a `type: "ambulance_dispatch"` message
      arrives over the WebSocket, show a prominent card: hospital name,
      address, and a big "Get Directions" button
- [ ] The button is just `<a href="{maps_url}" target="_blank">Get Directions</a>`
      — clicking it opens Google Maps in a new tab/app with the route already loaded

### Review checklist — frontend
- [ ] With the Ambulance view open in one tab, hold a bed from another
      tab/role — the dispatch card appears live with no refresh, same pattern
      as your existing bed-hold and IV alert broadcasts
- [ ] Clicking "Get Directions" actually opens Google Maps with a real route,
      not a broken or blank link

---

## What to say plainly in your pitch

- Login uses hashed passwords and a simple bearer token, not full session
  management, refresh tokens, or OAuth — appropriate for a prototype, not a
  production claim.
- The "message to the ambulance" is a live in-app push notification with a
  map link, not an actual SMS/radio dispatch — say this clearly if asked,
  same honesty pattern as the rest of the simulated pieces in this build.
