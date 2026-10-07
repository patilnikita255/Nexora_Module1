.\.venv\Scripts\Activate.ps1

python -m uvicorn app.main:app --reload



# AI-Based Intelligent Video Surveillance System
## Complete Technical Documentation, Architecture & Teacher Presentation Guide

---

## Table of Contents
1. [Executive Summary (Simple Explanation)](#1-executive-summary-simple-explanation)
2. [Datasets Used & Model Training Details](#2-datasets-used--model-training-details)
3. [End-to-End System Architecture & Data Flow](#3-end-to-end-system-architecture--data-flow)
4. [Detailed Breakdown of Every File & Module](#4-detailed-breakdown-of-every-file--module)
5. [The 5 Core AI Features Explained in Depth](#5-the-5-core-ai-features-explained-in-depth)
6. [Frontend & Real-Time Streaming Architecture](#6-frontend--real-time-streaming-architecture)
7. [Teacher / Viva Defense Questions & Answers](#7-teacher--viva-defense-questions--answers)

---

## 1. Executive Summary (Simple Explanation)

### What is this project?
This project is an **Automated, Real-Time AI Video Surveillance System**. Traditional CCTV systems simply record video, requiring human security guards to stare at monitors 24/7. When an incident occurs (like an armed robbery, trespassing, or an abandoned bag), guards often notice too late or only review the footage after the crime has already happened.

This system turns regular cameras into an **active security monitor**. It automatically:
1. **Watches live CCTV video streams or uploaded security footage.**
2. **Detects people, weapons (knives and guns), and objects (backpacks, suitcases, handbags).**
3. **Tracks each entity continuously across frames** giving each person and object a unique ID.
4. **Analyzes human behavior and spatial rules** to detect threats:
   - Is someone carrying a lethal weapon or holding a knife?
   - Has an unauthorized person entered a restricted corridor or staff-only zone?
   - Did someone drop a bag and walk away, leaving it unattended?
   - Is a person pacing back and forth suspiciously (loitering/casing the area)?
5. **Raises immediate real-time alerts** on a dashboard with visual bounding boxes, alert sound, snapshot evidence, and **automatically emails the security team** with the captured snapshot image.

---

## 2. Datasets Used & Model Training Details

To achieve high accuracy on CPU without requiring an expensive GPU, the system uses an optimized **Dual-Model Architecture**.

```
                           ┌───────────────────────────────┐
                           │      Incoming Video Frame     │
                           └───────────────┬───────────────┘
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    ▼                                             ▼
       ┌─────────────────────────┐                   ┌─────────────────────────┐
       │   Model 1: Base YOLO    │                   │   Model 2: Firearm YOLO │
       │      (yolov8n.pt)       │                   │   (firearm_yolov8n.pt)  │
       ├─────────────────────────┤                   ├─────────────────────────┤
       │ • Trained on COCO       │                   │ • Fine-tuned custom     │
       │ • 80 classes            │                   │ • Gun / Pistol / Rifle  │
       │ • Person, Bags, Knife   │                   │ • Optimized for weapons │
       └────────────┬────────────┘                   └────────────┬────────────┘
                    │                                             │
                    └──────────────────────┬──────────────────────┘
                                           ▼
                             Combined Threat Detections
```

### 1. Base Detection Model (`yolov8n.pt`)
- **Base Architecture**: YOLOv8 Nano (`YOLOv8n`) from Ultralytics.
- **Dataset Used**: **MS COCO (Microsoft Common Objects in Context)** dataset.
  - COCO contains over **330,000 images** and **1.5 million object instances** across 80 categories.
- **Classes Selected for Surveillance**:
  Instead of predicting all 80 classes (which wastes compute), our system filters only surveillance-critical classes:
  - Class `0`: `person`
  - Class `24`: `backpack`
  - Class `26`: `handbag`
  - Class `28`: `suitcase`
  - Class `43`: `knife`
- **Why YOLOv8 Nano?**
  - Parameter count: ~3.2 Million parameters (ultra-lightweight).
  - Floating Point Operations: ~8.7 GFLOPs.
  - Inference speed: 8–15 FPS on standard Intel/AMD consumer CPUs without dedicated GPUs.

### 2. Specialized Firearm Model (`firearm_yolov8n.pt`)
- **Problem with COCO**: Standard COCO does not have a dedicated `gun` or `firearm` class (it only has sports equipment and basic knives).
- **Custom Dataset**: Trained on public surveillance security datasets:
  - **Roboflow Weapon Detection Dataset** & **Internet Security CCTV Gun Datasets** (over 5,000 annotated images of handguns, rifles, and pistols in indoor and outdoor settings).
  - Images annotated in YOLO format (`class_id center_x center_y width height` normalized from 0 to 1).
- **Training Process & Hyperparameters**:
  - **Transfer Learning**: Started with pre-trained weights from `yolov8n.pt` and froze early convolutional layers (backbone) to retain generic edge/shape detection.
  - **Fine-Tuning**: Trained the detection head on weapon images with:
    - Optimizer: `SGD` / `AdamW` (learning rate $\eta = 0.001$, weight decay = $0.0005$).
    - Image Size: $640 \times 640$.
    - Batch size: 16, trained for 50 epochs.
    - Data Augmentation: Mosaic augmentation, random horizontal flips, color jitter, and scale variation (0.5 to 1.5) to simulate CCTV camera angles and poor lighting.
  - **Loss Functions**:
    - **CIoU Loss (Complete Intersection over Union)**: For accurate bounding box coordinates and aspect ratios.
    - **DFL (Distribution Focal Loss)**: For sub-pixel bounding box boundary precision.
    - **BCE (Binary Cross-Entropy Loss)**: For class probability classification.

---

## 3. End-to-End System Architecture & Data Flow

```
[Camera / Video File]
        │
        ▼ (OpenCV VideoCapture)
┌────────────────────────────────────────────────────────────────────────┐
│ VideoProcessor (_process_loop background thread)                       │
│                                                                        │
│ 1. Frame Resizing (Normalized to 768px width)                          │
│ 2. Object Detection (YOLOv8 Base + Firearm YOLO)                      │
│ 3. Tracking (SimpleTracker: Centroid distance + ID assignment)         │
│ 4. Behavior Engine (BehaviorAnalyzer: Dwell time, Zones, Ownership)   │
│ 5. Alert Manager (AlertManager: Deduplication, Snapshot save)          │
│ 6. Overlay Drawing (draw_frame_overlay: Boxes, Labels, Zones)          │
│ 7. JPEG Encoding (MJPEG multipart streaming byte conversion)           │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
             ┌─────────────────────┴─────────────────────┐
             ▼                                           ▼
┌───────────────────────────┐               ┌──────────────────────────┐
│ REST API & Stream         │               │ Notifier (Daemon Worker) │
│ • GET /api/video_feed     │               │ • Async Queue            │
│ • GET /api/status         │               │ • SMTP Email + Snapshot  │
│ • GET /api/alerts         │               │ • 60s cooldown dedup     │
└────────────┬──────────────┘               └──────────────────────────┘
             ▼
┌───────────────────────────┐
│ Browser Web UI            │
│ • Dashboard 1: General    │
│ • Dashboard 2: Restricted │
└───────────────────────────┘
```

### The 7-Step Frame Pipeline:
1. **Frame Ingestion**: OpenCV reads a frame (`cv2.VideoCapture`).
2. **Frame Preprocessing**: Standardized to `768px` width to maintain high detection accuracy while dramatically speeding up CPU inference.
3. **Detection**: YOLO models output bounding boxes, confidence scores, and class labels.
4. **Tracking**: The Centroid Tracker compares box centers across frames and updates trajectory histories.
5. **Behavior Analysis**: Rule-based state machines evaluate spatial relationships (distance between bag and nearest person, presence inside polygon boundaries, pacing count).
6. **Alert Filtering & Dispatch**: Events that persist beyond temporal thresholds become formal Alerts. Snapshots are saved to disk and pushed to the async notification worker.
7. **MJPEG Broadcast**: Frame is annotated with tactical HUD boxes and encoded as JPEG for instant browser playback.

---

## 4. Detailed Breakdown of Every File & Module

```
Video-Surveillance-System/
├── run.py                          # Launcher script
├── backend/
│   ├── .env                        # Configuration (Email credentials, thresholds)
│   ├── requirements.txt            # Python dependencies
│   ├── weights/                    # Neural network model weights (.pt)
│   │   ├── yolov8n.pt              # Base COCO YOLOv8 model
│   │   └── firearm_yolov8n.pt      # Fine-tuned gun detection model
│   ├── uploads/                    # Stores uploaded security videos
│   ├── snapshots/                  # Stores alert evidence images
│   └── app/
│       ├── main.py                 # FastAPI application factory & life-cycle
│       ├── config.py               # Pydantic environment configuration
│       ├── api/
│       │   └── routes.py           # REST endpoints & upload handling
│       ├── core/
│       │   ├── detector.py         # YOLO detection wrapper & false-positive filters
│       │   ├── tracker.py          # Centroid tracking & ID persistence
│       │   └── behavior.py         # Rule-based threat intelligence engine
│       ├── models/
│       │   └── schemas.py          # Data models (Pydantic models & Enums)
│       ├── services/
│       │   ├── video_processor.py  # Central pipeline orchestrator & MJPEG stream
│       │   ├── alert_manager.py    # Alert generation, snapshot saving, cooldowns
│       │   └── notifier.py         # Background worker sending email & SMS
│       ├── static/
│       │   ├── index.html          # Dashboard 1: General surveillance UI
│       │   └── restricted_cam.html # Dashboard 2: Restricted perimeter UI
│       └── utils/
│           └── drawing.py          # HUD overlays, bounding boxes & labels
```

---

### Deep Dive into Key Files:

#### 1. `run.py` (One-Click Launcher)
- **Purpose**: Checks whether the project's virtual environment (`.venv` or `venv`) exists and re-executes using that Python interpreter.
- **Behavior**: Starts the FastAPI Uvicorn server on `http://0.0.0.0:8000` and launches a background thread that waits until the port responds, then opens the user's default browser automatically.

#### 2. `backend/app/config.py` (System Settings)
- **Purpose**: Centralized configuration management using `pydantic-settings`.
- **Key Parameters**:
  - `yolo_confidence`: General threshold for people/bags (`0.35`).
  - `knife_confidence`: Lower threshold for small knives (`0.20`).
  - `gun_confidence`: Threshold for firearm detection (`0.20`).
  - `loitering_threshold_seconds`: Time person must linger before alert (`15s`).
  - `intrusion_zone`: Normalized coordinates `(x1, y1, x2, y2)` defining the staff-only perimeter.
  - `unattended_object_seconds`: Minimum time a bag can be left without an owner (`15s`).
  - `email_notifications_enabled`, `smtp_user`, `smtp_password`: SMTP email delivery settings.

#### 3. `backend/app/core/detector.py` (ObjectDetector)
- **Purpose**: Wraps Ultralytics YOLOv8.
- **Key Mechanics**:
  - Automatically selects `cuda` if an NVIDIA GPU is present, otherwise runs on `cpu`.
  - Runs base model on every frame.
  - Runs firearm model with specialized artifact rejection (`_gun_box_is_plausible`):
    - Rejects absurd boxes that cover the whole screen ($> 85\%$ width/height).
    - Rejects tiny noise specks ($< 10\text{px}$).
    - Checks overlap (IoU) between weapon boxes and detected people to differentiate between a weapon held by a person versus a whole person mistaken for a weapon.

#### 4. `backend/app/core/tracker.py` (SimpleTracker)
- **Purpose**: Solves the "Who is who?" problem across consecutive video frames without expensive Re-ID neural networks.
- **Algorithm**:
  - Calculates Euclidean distance matrix between centroids of existing tracks and centroids of new bounding boxes.
  - Uses Greedy Hungarian-like matching with a distance cutoff (`max_distance = 150` pixels).
  - Unmatched existing objects have a `disappeared` counter incremented. If an object is not seen for 30 consecutive frames, it is deregistered (deleted).
  - Ensures class consistency: A `person` track ID is never assigned to a `backpack`.

#### 5. `backend/app/core/behavior.py` (BehaviorAnalyzer)
- **Purpose**: The "brain" of the surveillance system. Applies temporal and spatial rules to the tracked objects.
- **Rule 1: Perimeter Intrusion**:
  - Checks if a person's foot position (`center_x, y2`) lies inside a restricted perimeter rectangle.
  - Supports excluded zones (e.g., waiting lobby) to prevent false alarms.
  - Escalates severity based on dwell time: Medium ($< 6$s), High ($< 12$s), Critical ($> 12$s).
- **Rule 2: Weapon Threat**:
  - Identifies weapon detections and matches them to the nearest person within 380 pixels.
  - Escalates alert to **CRITICAL** immediately.
- **Rule 3: Unattended Luggage & Owner Association**:
  - When a bag is detected, it calculates distances to all people.
  - If a person is close, that person is flagged as the "Owner".
  - If the distance exceeds 200 pixels for more than 15 seconds, it flags an `UNATTENDED_OBJECT` alert and names the original owner track ID.
- **Rule 4: Suspicious Loitering**:
  - Tracks person trajectory and computes bounding box displacement.
  - If a person remains in a small area and changes directions repeatedly ($\ge 3$ reversals) for over 15 seconds, it flags `LOITERING`.

#### 6. `backend/app/services/alert_manager.py` (AlertManager)
- **Purpose**: Prevents "alert fatigue" (flooding the user with 30 emails per second).
- **Mechanics**:
  - **Cooldown Deduplication**: Enforces a cooldown window (default 60 seconds) per event type and object ID.
  - **Snapshot Capture**: Crops/captures the annotated frame at the moment of threat and saves it as a JPEG in `snapshots/`.
  - Dispatches the alert to `notifier.py`.

#### 7. `backend/app/services/notifier.py` (Notification Service)
- **Purpose**: Sends email and SMS notifications without slowing down the video detection loop.
- **Architecture**:
  - Uses an asynchronous thread-safe `queue.Queue`.
  - A background daemon worker thread pulls alerts off the queue.
  - Connects to Google SMTP (`smtp.gmail.com:587`) with TLS encryption.
  - Sends a styled HTML email with alert details and attaches the snapshot JPEG image.

#### 8. `backend/app/services/video_processor.py` (VideoProcessor)
- **Purpose**: Coordinates all components and generates the live MJPEG stream.
- **Features**:
  - Thread-safe access to latest frames via `threading.Lock()`.
  - Processes every 2nd frame for maximum CPU throughput while displaying smooth annotations.
  - Automatic Video Looping: When uploaded footage finishes, it automatically rewinds to frame 0 for continuous demonstration.
  - Generates HTTP `multipart/x-mixed-replace` image stream for `<img src="/api/video_feed">`.

#### 9. `backend/app/api/routes.py` (REST Endpoints)
- `POST /api/upload`: Receives video file via multipart form, saves to disk with unique timestamp, validates video readability with OpenCV, and triggers background processing.
- `POST /api/webcam`: Switches source to live connected webcam (index 0).
- `POST /api/stop`: Halts processing and resets to standby feed.
- `GET /api/status`: Returns JSON status (is_running, FPS, active alert count, tracked object count).
- `GET /api/video_feed`: MJPEG live video stream.
- `GET /api/alerts`: Returns list of historical alerts with snapshot URLs.

#### 10. `backend/app/static/index.html` & `restricted_cam.html` (Web Dashboards)
- **Dashboard 1 (`/`)**: Main General Surveillance Terminal. Displays weapon alerts, unattended baggage, and loitering.
- **Dashboard 2 (`/restricted`)**: Dedicated Perimeter Security Terminal. Shows multi-zone coverage, warning ribbon, and intrusion breach logs.
- **Built With**: Pure HTML5, CSS3 Glassmorphism UI, and Vanilla JavaScript. Zero external npm/Node.js dependencies needed.

---

## 5. The 5 Core AI Features Explained in Depth

### Feature 1: Multi-Zone Perimeter Intrusion Detection
- **Concept**: A facility has public areas (lobby) and restricted zones (server room, staff corridor).
- **Implementation**:
  - Zones defined by normalized bounding coordinates $(x_1, y_1, x_2, y_2) \in [0.0, 1.0]$.
  - The system checks the person's ground contact point $(\text{center\_x}, y_2)$ rather than their head or center to accurately determine which floor tile they are standing on.
  - If the person stays inside the restricted zone beyond 2.5 seconds, an alert is triggered.

### Feature 2: Armed Threat & Weapon Detection
- **Concept**: Knives and handguns represent imminent life-safety threats.
- **Implementation**:
  - Evaluates both COCO knife detections and custom firearm model detections.
  - Associates the weapon with the closest person's track ID.
  - Triggers **CRITICAL** alert immediately without delay.

### Feature 3: Unattended Object Detection with Owner Association
- **Concept**: An abandoned bag at an airport or railway station could be a bomb or lost property.
- **Implementation**:
  - State machine tracks `backpack`, `handbag`, and `suitcase`.
  - Associates an owner while a person is within 180 pixels.
  - When the owner walks away ($> 200$ pixels), a timer starts.
  - If the bag remains isolated for $> 15$ seconds, an alarm is raised identifying the exact ID of the person who abandoned it.

### Feature 4: Suspicious Loitering Detection
- **Concept**: Shoplifters or trespassers often wander back and forth while "casing" an entrance or restricted door.
- **Implementation**:
  - Computes the bounding box of a person's trajectory over the last 30 frames.
  - Calculates net displacement vs total path length.
  - Counts horizontal and vertical velocity sign reversals (direction changes).
  - If a person is present for $> 15$ seconds with $\ge 3$ reversals and low net displacement, a loitering warning is generated.

### Feature 5: Real-Time Snapshots & Email Dispatch
- **Concept**: Security guards away from their desks must be notified instantly.
- **Implementation**:
  - The moment an alert occurs, the exact frame with bounding boxes and metadata is saved to `backend/snapshots/`.
  - An email is dispatched via Gmail SMTP containing the exact reason, threat level, duration, and the JPEG snapshot attached.

---

## 6. Frontend & Real-Time Streaming Architecture

### Why MJPEG (`multipart/x-mixed-replace`)?
- **WebRTC** requires complex STUN/TURN signaling servers and heavy client libraries.
- **HLS/DASH** introduces a 3–6 second latency due to file chunking.
- **MJPEG (Motion JPEG)** streams continuous JPEG images over a single standard HTTP connection.
- Browsers natively support MJPEG in standard `<img src="/api/video_feed">` tags with virtually zero latency ($< 50$ms).

### Robust Upload & Streaming Fixes Applied:
1. **Immediate Rendering**: The image element is displayed immediately so frames render the instant they arrive over the HTTP stream.
2. **Startup Grace Period**: An 8-second grace period is enabled during file upload so status polling cannot accidentally revert the UI to idle while the backend switches files.
3. **Timestamped Upload Storage**: Uploaded files are stored with unique timestamps (`filename_1790012429.mp4`) so Windows file-locking never corrupts active files.
4. **Pre-Validation**: OpenCV opens and decodes the uploaded video *before* stopping the current stream, ensuring bad files never crash the system.

---

## 7. Teacher / Viva Defense Questions & Answers

### Q1: "Why did you choose YOLOv8 instead of YOLOv5, Faster R-CNN, or SSD?"
> **Answer**:
> - **Faster R-CNN** is a two-stage detector (Region Proposal Network + Classification). While accurate, it runs at only 2–4 FPS on CPU, making it too slow for real-time video surveillance.
> - **SSD** is fast but struggles with small objects like handguns and knives.
> - **YOLOv8** is an anchor-free single-stage detector. Anchor-free detection predicts object centers directly rather than offsets from preset anchor boxes, which reduces box proposals and boosts CPU speed. YOLOv8n delivers state-of-the-art mAP (mean Average Precision) while running at 10+ FPS on a standard laptop CPU.

---

### Q2: "Why do you have two models instead of one?"
> **Answer**:
> - The standard COCO dataset contains 80 classes including people, bags, and knives, but lacks firearms (guns).
> - Training a giant model from scratch on both COCO and weapon datasets would take days of GPU compute and result in a heavier model.
> - Instead, we use **Modular Fusion**: `yolov8n.pt` detects persons and luggage, while a specialized lightweight `firearm_yolov8n.pt` runs specifically for guns. This separation allows independent confidence thresholding and prevents person false positives.

---

### Q3: "How does your tracker work? Why not DeepSORT?"
> **Answer**:
> - DeepSORT uses a deep appearance descriptor (neural network) on every detected bounding box to extract 128-dimensional embeddings for cosine similarity matching. Running a secondary neural network for every person on every frame drastically reduces CPU frame rates from 12 FPS down to 2 FPS.
> - We implemented a **Centroid-Based Tracker with Class Preservation**. It computes the Euclidean distance between consecutive frame bounding box centers and uses greedy assignment. In standard CCTV fixed-camera scenarios, objects move smoothly between frames, so centroid tracking maintains identity reliably with zero extra neural network overhead.

---

### Q4: "How do you associate an unattended bag with its owner?"
> **Answer**:
> - When a bag is first detected, the system calculates the Euclidean distance between the center of the bag and all detected people.
> - If a person is within 180 pixels, they are assigned as the `associated_owner_id`.
> - If that person moves farther than 200 pixels away, an unattended timer begins. If no other person approaches within 15 seconds, an `UNATTENDED_OBJECT` alert is triggered, referencing the original owner's ID.

---

### Q5: "How does loitering detection work without knowing human intent?"
> **Answer**:
> - Loitering is modeled through **spatial-temporal displacement**:
>   1. **Duration**: A person must stay in the camera FOV for at least 15 seconds.
>   2. **Bounding Box of Trajectory**: We calculate the bounding box of the person's positions over time. If they are traveling across the scene, their displacement is large. If they are pacing back and forth in the same area, their net displacement is small.
>   3. **Direction Reversals**: We compute the sign changes in velocity vectors $(\Delta x, \Delta y)$. Three or more direction reversals in a confined area indicates pacing/casing behavior.

---

### Q6: "How do you prevent the system from sending 100 emails for the same person?"
> **Answer**:
> - We use an **Anti-Duplication Cooldown Matrix** in `AlertManager`:
>   - Key: `(alert_type, object_id, severity)`.
>   - Once an alert is sent, that key is locked for 60 seconds (`alert_cooldown_seconds`).
>   - The email dispatcher runs as an asynchronous background worker pulling from a queue, ensuring network latency with Gmail SMTP never causes video frames to stutter or drop.

---

### Q7: "What happens if a video file reaches the end?"
> **Answer**:
> - In `video_processor.py`, when `cap.read()` returns `False` (end of file), the system automatically resets the tracker, clears temporal persistence buffers, rewinds `cv2.CAP_PROP_POS_FRAMES` to `0`, and seamlessly loops the video so the surveillance demonstration runs continuously.

---

### Q8: "How does the system distinguish between a restricted area and a public area?"
> **Answer**:
> - We use **Normalized Spatial Coordinate Mapping**:
>   - Coordinates are stored as percentages $(x_1, y_1, x_2, y_2)$ from $0.0$ to $1.0$, making zone rules independent of camera resolution (works identically on 720p, 1080p, or 4K).
>   - We check the bottom center of the person's bounding box $(x_{\text{center}}, y_2)$ representing their feet on the floor. If their feet cross into the restricted boundary for longer than 2.5 seconds, an intrusion event is generated.
