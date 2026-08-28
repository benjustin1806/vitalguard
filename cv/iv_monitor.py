import os
import sys
import time
import cv2
import numpy as np
import requests

# Configuration defaults
BACKEND_URL = "http://localhost:8000"
ROOM_ID = "ICU Bed 4"
LOW_FILL_THRESHOLD = 0.15       # Alert if fill level drops below 15%
CONSECUTIVE_LOW_FRAMES = 8      # Number of consecutive frames required to trigger
COOLDOWN_SECONDS = 15           # Cooldown between consecutive alerts

# Patient this CV monitor is tracking — must match an id in patients.json
PATIENT_ID = "p2"
PATIENT_NAME = "Sunita Mehta"

# State variables
roi_start = (0, 0)
roi_end = (0, 0)
selecting_roi = False
roi_defined = False

# Default HSV bounds (broad/inclusive initially, refined via calibration 'c')
hsv_lower = np.array([0, 0, 40])
hsv_upper = np.array([179, 255, 255])

# Counter for consecutive low readings
low_reading_counter = 0
last_alert_time = 0.0

def mouse_callback(event, x, y, flags, param):
    """Callback for mouse dragging to define the ROI (Region of Interest)."""
    global roi_start, roi_end, selecting_roi, roi_defined
    
    if event == cv2.EVENT_LBUTTONDOWN:
        roi_start = (x, y)
        roi_end = (x, y)
        selecting_roi = True
        roi_defined = False
        
    elif event == cv2.EVENT_MOUSEMOVE:
        if selecting_roi:
            roi_end = (x, y)
            
    elif event == cv2.EVENT_LBUTTONUP:
        if selecting_roi:
            roi_end = (x, y)
            selecting_roi = False
            # Ensure ROI is larger than a tiny threshold to prevent accidental clicks
            x1, y1 = min(roi_start[0], roi_end[0]), min(roi_start[1], roi_end[1])
            x2, y2 = max(roi_start[0], roi_end[0]), max(roi_start[1], roi_end[1])
            if (x2 - x1) > 15 and (y2 - y1) > 15:
                roi_defined = True
                print(f"[ROI] Defined: P1=({x1}, {y1}), P2=({x2}, {y2})")
            else:
                roi_defined = False
                print("[ROI] Selection too small, reset.")

def calibrate_color(roi_frame):
    """Calibrates the HSV range around the median color of the ROI."""
    global hsv_lower, hsv_upper
    if roi_frame is None or roi_frame.size == 0:
        print("[CALIBRATION] Error: No ROI image available for calibration.")
        return

    # Convert the ROI to HSV space
    roi_hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
    
    # Calculate median for H, S, and V channels
    h_median = np.median(roi_hsv[:, :, 0])
    s_median = np.median(roi_hsv[:, :, 1])
    v_median = np.median(roi_hsv[:, :, 2])
    
    # Tolerances for range
    h_tolerance = 15
    s_tolerance = 50
    v_tolerance = 60
    
    # Compute bounds and clip to valid HSV ranges
    h_low = max(0, int(h_median - h_tolerance))
    h_high = min(179, int(h_median + h_tolerance))
    
    s_low = max(30, int(s_median - s_tolerance))
    s_high = min(255, int(s_median + s_tolerance))
    
    v_low = max(30, int(v_median - v_tolerance))
    v_high = min(255, int(v_median + v_tolerance))
    
    hsv_lower = np.array([h_low, s_low, v_low])
    hsv_upper = np.array([h_high, s_high, v_high])
    
    print(f"\n[CALIBRATION] Calibrated around median HSV: ({int(h_median)}, {int(s_median)}, {int(v_median)})")
    print(f"[CALIBRATION] New bounds -> Lower: {hsv_lower}, Upper: {hsv_upper}")

def compute_fill_ratio(roi_frame):
    """
    Computes the fluid fill ratio in the ROI.
    Scans the ROI's thresholded mask from top to bottom.
    The first row where the 'liquid' percentage exceeds 40% is considered the fill level.
    """
    if roi_frame is None or roi_frame.size == 0:
        return 0.0, None, 0
        
    # Convert ROI to HSV and mask
    roi_hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(roi_hsv, hsv_lower, hsv_upper)
    
    # Morphological operations to reduce noise
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    
    h, w = mask.shape
    topmost_liquid_row = h
    
    # Scan rows top-down to find the topmost row that is mostly liquid (>= 40% matching pixels)
    for y in range(h):
        matching_pixels = np.sum(mask[y, :] > 0)
        ratio = matching_pixels / w
        if ratio >= 0.4:
            topmost_liquid_row = y
            break
            
    # Calculate fill ratio: height remaining vs total ROI height
    fill_ratio = (h - topmost_liquid_row) / h
    return fill_ratio, mask, topmost_liquid_row

def trigger_backend_alert(fill_ratio):
    """
    Dispatches two requests to VitalGuard backend:
    1. PATCH /patients/{id}/iv-status  — updates the patient record and
       triggers a patient-tagged WebSocket broadcast if level is below threshold.
    2. POST /trigger-alert             — fallback generic broadcast (keeps the
       existing dashboard alert stream working even if patient update fails).
    """
    fill_percent = fill_ratio * 100
    success = False

    # 1. Update patient IV record (also triggers WS broadcast server-side)
    iv_url = f"{BACKEND_URL}/patients/{PATIENT_ID}/iv-status"
    try:
        iv_resp = requests.patch(iv_url, json={"fill_percent": fill_percent}, timeout=2.0)
        if iv_resp.status_code == 200:
            print(f"[IV STATUS] Patient record updated: {iv_resp.json()}")
            success = True
        else:
            print(f"[IV STATUS ERROR] {iv_resp.status_code}: {iv_resp.text}")
    except Exception as e:
        print(f"[IV STATUS EXCEPTION] {e}")

    # 2. Generic alert broadcast (carries patient_id so patient.html can filter)
    alert_payload = {
        "room": ROOM_ID,
        "message": f"CRITICAL: IV liquid level is dangerously low ({fill_ratio:.1%}). Refill container immediately.",
        "severity": "high",
        "patient_id": PATIENT_ID,
        "patient_name": PATIENT_NAME,
    }
    alert_url = f"{BACKEND_URL}/trigger-alert"
    try:
        alert_resp = requests.post(alert_url, json=alert_payload, timeout=2.0)
        if alert_resp.status_code == 200:
            print(f"[ALERT DISPATCHED] Broadcast to backend: {alert_resp.json()}")
            success = True
        else:
            print(f"[ALERT ERROR] {alert_resp.status_code}: {alert_resp.text}")
    except Exception as e:
        print(f"[ALERT EXCEPTION] {e}")

    return success

def open_camera():
    """Tries multiple backends (DirectShow, MSMF, Default) across indices 0 and 1 to find a working webcam."""
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if os.name == 'nt' else [cv2.CAP_ANY]
    for idx in [0, 1, 2]:
        for backend in backends:
            try:
                cap = cv2.VideoCapture(idx + backend)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        print(f"[CAMERA] Successfully opened webcam (index {idx}) with backend {backend}.")
                        return cap
                    cap.release()
            except Exception:
                pass
    return None

def main():
    global hsv_lower, hsv_upper, roi_start, roi_end, selecting_roi, roi_defined
    global low_reading_counter, last_alert_time
    
    print("=================================================================")
    print("                 VitalGuard IV Level Monitor")
    print("=================================================================")
    print(f"Backend Target: {BACKEND_URL}")
    print(f"Room:           {ROOM_ID}")
    print(f"Alert Threshold:{LOW_FILL_THRESHOLD:.0%}")
    print("-----------------------------------------------------------------")
    print("INSTRUCTIONS:")
    print(" 1. Click and drag on the camera feed to draw a box around the IV tube/fluid.")
    print(" 2. Press 'c' to Calibrate color using the selected ROI box.")
    print(" 3. Press 'r' to Reset/Clear the selected ROI box.")
    print(" 4. Press 'q' to Quit the program.")
    print("=================================================================\n")

    # Initialize video capture with DirectShow fallback
    cap = open_camera()
    if cap is None or not cap.isOpened():
        print("[CAMERA ERROR] Could not open webcam. Verify it is connected and not in use by another app.")
        sys.exit(1)
        
    window_name = "VitalGuard IV Monitor"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, mouse_callback)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[CAMERA ERROR] Failed to grab frame.")
            break
            
        # Flip frame horizontally for natural movement feel
        frame = cv2.flip(frame, 1)
        h_frame, w_frame, _ = frame.shape
        
        # Calculate bounding box coordinates safely
        x1, y1 = min(roi_start[0], roi_end[0]), min(roi_start[1], roi_end[1])
        x2, y2 = max(roi_start[0], roi_end[0]), max(roi_start[1], roi_end[1])
        
        # Ensure ROI coordinates are constrained within frame dimensions
        x1, x2 = max(0, x1), min(w_frame, x2)
        y1, y2 = max(0, y1), min(h_frame, y2)
        
        roi_frame = None
        mask_display = None
        fill_ratio = 0.0
        topmost_liquid_row = 0
        
        # Draw and compute ROI parameters if defined
        if roi_defined and (x2 - x1) > 0 and (y2 - y1) > 0:
            roi_frame = frame[y1:y2, x1:x2]
            fill_ratio, mask_display, topmost_liquid_row = compute_fill_ratio(roi_frame)
            
            # Determine visual status color
            if fill_ratio < LOW_FILL_THRESHOLD:
                box_color = (0, 0, 255) # Red
                status_text = "LOW LEVEL"
            else:
                box_color = (0, 255, 0) # Green
                status_text = "NORMAL"
                
            # Draw ROI box
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            
            # Draw liquid level line inside ROI
            y_level_in_frame = y1 + topmost_liquid_row
            cv2.line(frame, (x1, y_level_in_frame), (x2, y_level_in_frame), (255, 255, 0), 2)
            
            # Draw level text details next to ROI
            label = f"{status_text} ({fill_ratio:.0%})"
            cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 1, cv2.LINE_AA)
            
            # Display current ROI mask for visibility/calibration convenience
            if mask_display is not None:
                cv2.imshow("ROI Mask", mask_display)
                
            # --- Alert Trigger Logic ---
            if fill_ratio < LOW_FILL_THRESHOLD:
                low_reading_counter += 1
                if low_reading_counter >= CONSECUTIVE_LOW_FRAMES:
                    # Check cooldown
                    current_time = time.time()
                    if current_time - last_alert_time >= COOLDOWN_SECONDS:
                        print(f"\n[ALERT] Low fluid detected! Level: {fill_ratio:.1%} (Frames: {low_reading_counter})")
                        if trigger_backend_alert(fill_ratio):
                            last_alert_time = current_time
            else:
                # Reset counter when level goes back to normal
                low_reading_counter = max(0, low_reading_counter - 1)
                
        elif selecting_roi:
            # Draw selection box in yellow while dragging
            cv2.rectangle(frame, (roi_start[0], roi_start[1]), (roi_end[0], roi_end[1]), (0, 255, 255), 1)
            
        else:
            # ROI is not defined, show instructions inside the viewport
            cv2.putText(frame, "Drag a box around the IV fluid column to start", 
                        (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
            
        # Draw permanent HUD telemetry & status overlays
        hud_bg_color = (25, 20, 15) # Dark slate
        cv2.rectangle(frame, (0, h_frame - 60), (w_frame, h_frame), hud_bg_color, -1)
        
        # Display alert status in HUD
        hud_alert_status = "ALERT TIMEOUT"
        hud_status_color = (128, 128, 128)
        
        current_time = time.time()
        if not roi_defined:
            hud_alert_status = "ROI PENDING"
            hud_status_color = (0, 255, 255) # Yellow
        elif fill_ratio < LOW_FILL_THRESHOLD:
            if current_time - last_alert_time < COOLDOWN_SECONDS:
                hud_alert_status = "ALERT ACTIVE (COOLDOWN)"
                hud_status_color = (0, 165, 255) # Orange
            else:
                hud_alert_status = f"CONFIRMING LOW ({low_reading_counter}/{CONSECUTIVE_LOW_FRAMES})"
                hud_status_color = (0, 0, 255) # Red
        else:
            hud_alert_status = "MONITORING ACTIVE"
            hud_status_color = (0, 255, 0) # Green
            
        cv2.putText(frame, f"System Status: {hud_alert_status}", 
                    (15, h_frame - 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, hud_status_color, 1, cv2.LINE_AA)
        
        instructions = "[c] Calibrate  |  [r] Reset ROI  |  [q] Quit"
        cv2.putText(frame, instructions, 
                    (w_frame - 360, h_frame - 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
        
        # Display the live window
        cv2.imshow(window_name, frame)
        
        # Handle keypress events
        key = cv2.waitKey(30) & 0xFF
        if key == ord('q'):
            print("\nExiting monitor...")
            break
            
        elif key == ord('c'):
            if roi_defined and roi_frame is not None:
                calibrate_color(roi_frame)
            else:
                print("[WARN] Select an ROI first before calibrating color.")
                
        elif key == ord('r'):
            roi_defined = False
            selecting_roi = False
            roi_start = (0, 0)
            roi_end = (0, 0)
            low_reading_counter = 0
            # Close the ROI Mask helper window if open
            try:
                cv2.destroyWindow("ROI Mask")
            except Exception:
                pass
            print("[ROI] Reset.")
            
    # Cleanup resource handles
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
