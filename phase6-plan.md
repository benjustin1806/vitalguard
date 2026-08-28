# VITALGUARD — Phase 6: Vitals Risk Scoring (ML)

Prerequisite: `ml/data/<dataset>.csv` already exists in the project — it was
downloaded manually from Kaggle ("Human Vital Sign Dataset") and dragged in.
Do not attempt to download it yourself; work with the file that's already there.

Goal: train a classifier that flags a patient's risk level (Low/Medium/High,
or whatever labels the dataset actually uses) from their vitals, save it, and
surface it on the existing patient detail page from Phase 5.

---

## Step 1 — Inspect the dataset first (do not skip)

- [ ] Load `ml/data/<file>.csv` with pandas and print: column names, `.head()`,
      `.info()` (for null counts), and the unique values in whatever the label
      column is
- [ ] Report back the exact column names and label format before writing any
      training code — column names in this dataset will NOT match the field
      names already used in `backend/patients.json` (e.g. it might use
      `HeartRate` instead of `heart_rate`), so a mapping step is required later

---

## Step 2 — Train a baseline classifier

- [ ] Create `ml/train.py`
- [ ] Install: `pip install scikit-learn pandas joblib --break-system-packages`
- [ ] Load the CSV, select the vitals columns as features (heart rate, blood
      pressure, SpO2, temperature, respiratory rate — whichever of these
      actually exist in the real dataset) and the risk label as the target
- [ ] Handle missing values if `.info()` showed any (drop or impute — pick
      whichever is simpler for the amount of missing data actually found)
- [ ] Split into train/test with `train_test_split` (e.g. 80/20)
- [ ] Train a `RandomForestClassifier` (good default for tabular data, easy
      to explain to judges)
- [ ] Print accuracy, precision, recall on the **test** split (not train) —
      these numbers go in the pitch, so they need to be real
- [ ] If accuracy is suspiciously near 100%, check whether the label column
      accidentally got included as a feature (a common and easy-to-miss bug)

## Step 2 review checklist
- [ ] Training script runs to completion with no errors
- [ ] Printed test-set accuracy/precision/recall are visible in terminal output
- [ ] Confirmed the label column is NOT among the feature columns used for training

---

## Step 3 — Save the model

- [ ] `joblib.dump(model, "ml/model.joblib")`
- [ ] Also save the exact list/order of feature column names used, e.g. to
      `ml/feature_columns.json` — the backend will need this to build feature
      vectors in the same order the model expects, or predictions will be silently wrong

## Step 3 review checklist
- [ ] `ml/model.joblib` exists after running the script
- [ ] `ml/feature_columns.json` (or equivalent) lists the exact features in the exact trained order

---

## Step 4 — Load the model into the backend

- [ ] In `backend/main.py`, load the model once at startup:
      `model = joblib.load("../ml/model.joblib")`
- [ ] Add `POST /patients/{id}/risk-score` (or compute inline inside the
      existing `GET /patients/{id}` handler):
      - pull that patient's current vitals from `patients.json`
      - map them into the feature vector using the saved feature column order
        (this is the step most likely to break — field names differ between
        your app's `vitals` object and the dataset's original column names)
      - call `model.predict()` (or `predict_proba()` if you want a confidence
        score, not just a label)
      - return the predicted risk level

## Step 4 review checklist
- [ ] `curl -X POST http://localhost:8000/patients/p1/risk-score` returns a
      real prediction, not an error
- [ ] Manually change a patient's vitals to something clearly abnormal (e.g.
      SpO2 to 85) via the existing vitals update endpoint, re-call risk-score,
      confirm the prediction actually changes — if it doesn't change at all
      regardless of input, the feature mapping is broken even though the
      endpoint "works"

---

## Step 5 — Surface it on the patient page

- [ ] On the Phase 5 patient detail page, add a risk badge near the vitals
      panel (color-coded: green/amber/red matching Low/Medium/High)
- [ ] Populate it by calling the new risk-score endpoint when the page loads
      (and again whenever vitals are updated, if you want it to feel live)

## Step 5 review checklist
- [ ] Risk badge renders on the patient page with a real value, not a placeholder
- [ ] Changing a patient's vitals and reloading the page shows an updated badge

---

## What to be upfront about in your pitch

- The model is trained on a public dataset, not this hospital's real patient
  history — say this plainly, same honesty framing as the simulated hospital
  bed data and webcam IV monitor.
- State the actual test-set accuracy/precision numbers from Step 2 — a
  real, modest number is more credible to judges than an unverified claim.
