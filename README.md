# AIML Enabled Intelligent Video Surveillance System

A real-time AI-powered video surveillance system that detects suspicious activities using **YOLOv8** object detection, **rule-based behavior analysis** and displays live alerts on a modern **React** dashboard.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?logo=typescript&logoColor=white)
![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-00FFFF)

---

## Table of Contents

- [System Architecture](#-system-architecture)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Installation & Setup](#-installation--setup)
- [Running the System](#-running-the-system)
- [API Endpoints](#-api-endpoints)
- [Alert Behavior & Update Rules](#-alert-behavior--update-rules)
- [Triple-Lock Logic](#-triple-lock-logic)
- [Future Scope](#-future-scope)

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│              FRONTEND (React + TypeScript)                   │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────────┐     │
│  │ VideoFeed  │  │ AlertsPanel  │  │ DetectedObjects   │     │
│  │ (MJPEG)    │  │ (Polling)    │  │ (Polling)         │     │
│  └─────┬──────┘  └─────┬────────┘  └────────┬──────────┘     │
│        │               │                    │                │
└────────┼───────────────┼────────────────────┼────────────────┘
         │               │                    │
    MJPEG Stream    REST /api/alerts    REST /api/frame
         │               │                    │
┌────────┼───────────────┼────────────────────┼────────────────┐
│        │         BACKEND (FastAPI)          │                │
│  ┌─────▼────────────────────────────────────▼──────┐         │
│  │              API Layer (routes.py)              │         │
│  │  /upload  /start  /stop  /status  /video_feed   │         │
│  └─────────────────────┬───────────────────────────┘         │
│                        │                                     │
│  ┌─────────────────────▼───────────────────────────┐         │
│  │           Video Processor (Pipeline)            │         │
│  │                                                 │         │
│  │  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │         │
│  │  │  YOLOv8  │→ │  Tracker  │→ │  Behavior    │  │         │
│  │  │ Detector │  │ (Centroid)│  │  Analyzer    │  │         │
│  │  └──────────┘  └───────────┘  └──────┬───────┘  │         │
│  │                                      │          │         │
│  │                              ┌───────▼───────┐  │         │
│  │                              │ Alert Manager │  │         │
│  │                              │ + Snapshots   │  │         │
│  │                              └───────────────┘  │         │
│  └─────────────────────────────────────────────────┘         │
│                                                              │
│  Video Input: Uploaded .mp4/.avi/.mkv files                  │
└──────────────────────────────────────────────────────────────┘
```

---

## Features

### AI & Detection
- **YOLOv8 Object Detection** — Focused class filtering for surveillance-critical classes: person, backpack, handbag, suitcase, knife
- **Centroid-Based Tracking** — Persistent track IDs with class-aware matching to reduce ID switching
- **Loitering Detection** — Duration-aware per-person analysis with temporal persistence checks
- **Intrusion Detection** — Restricted-zone dwell-time verification with severity escalation
- **Unattended Object Detection** — Nearest-person distance validation + minimum unattended time
- **Triple-Lock Logic** — Multi-layer verification (Detection → Behavior → Face ID placeholder)

### Dashboard
- **MJPEG Live Video Feed** — Real-time processed video with smooth fade-in and loading skeleton
- **Drag & Drop Video Upload** — Immediate upload/processing status transitions
- **Alert Panel** — Severity-coded alerts with timestamps, object ID, duration, confidence, and snapshot links
- **Detected Objects Panel** — Live tracked objects with confidence bars
- **Stats Bar** — FPS, object count, alert count, uptime
- **State-Driven UX** — Explicit dashboard states: IDLE → UPLOADING → PROCESSING → RUNNING → FINISHED
- **Dark Theme** — Modern glassmorphism UI with animations

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **AI/ML** | YOLOv8 (Ultralytics), OpenCV |
| **Backend** | Python 3.10+, FastAPI, Uvicorn |
| **Frontend** | React 18, TypeScript, Vite |
| **Communication** | REST API + MJPEG Streaming |

---

## Project Structure

```
Video-Surveillance-System/
├── backend/
│   ├── requirements.txt            # Python dependencies
│   ├── .env                        # Configuration
│   ├── .venv/                      # Virtual environment (local)
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory
│   │   ├── config.py               # Settings from .env
│   │   ├── api/
│   │   │   └── routes.py           # All REST endpoints
│   │   ├── core/
│   │   │   ├── detector.py         # YOLOv8 detection wrapper
│   │   │   ├── tracker.py          # Centroid-based tracker
│   │   │   └── behavior.py         # Rule-based behavior analysis
│   │   ├── services/
│   │   │   ├── video_processor.py  # Video pipeline orchestrator
│   │   │   └── alert_manager.py    # Alert generation & storage
│   │   ├── models/
│   │   │   └── schemas.py          # Pydantic data models
│   │   └── utils/
│   │       └── drawing.py          # OpenCV drawing helpers
│   ├── snapshots/                  # Alert screenshots (auto-created)
│   ├── uploads/                    # Uploaded videos (auto-created)
│   └── weights/                    # YOLO model weights (.pt)
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                 # Root component
│   │   ├── index.css               # Design system
│   │   ├── types/surveillance.ts   # TypeScript interfaces
│   │   ├── hooks/usePolling.ts     # Polling hook
│   │   ├── pages/Index.tsx         # Main dashboard page
│   │   └── components/
│   │       ├── ThemeToggle.tsx
│   │       └── surveillance/
│   │           ├── VideoFeed.tsx       # Video display + upload
│   │           ├── AlertsPanel.tsx     # Alert list
│   │           ├── DetectedObjects.tsx # Object cards
│   │           ├── ErrorModal.tsx      # Blocking init error modal
│   │           └── StatsBar.tsx        # Live statistics
│   ├── vite.config.ts
│   └── package.json
│
└── README.md
```

---

## Prerequisites

| Tool | Version | Installation |
|------|---------|-------------|
| **Python** | 3.10+ | [python.org](https://www.python.org/downloads/) |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) |
| **Git** | Any | [git-scm.com](https://git-scm.com/) |

> **No GPU required.** YOLOv8 runs on CPU. GPU (CUDA/MPS) is auto-detected if available.

---

## Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/Video-Surveillance-System.git
cd Video-Surveillance-System
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (macOS/Linux)
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

> Recommended: place your model file inside `backend/weights` and point `YOLO_MODEL` to that path to avoid re-downloading.

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install
```

### 4. Configuration (Optional)

Add `backend/.env`:

```env
YOLO_MODEL=weights/yolov8m.pt   # Use local model file inside backend/weights
YOLO_CONFIDENCE=0.5             # Detection threshold
LOITERING_THRESHOLD_SECONDS=20  # Loitering time
INTRUSION_ZONE=0.6,0.0,1.0,1.0  # Restricted zone area
UNATTENDED_OBJECT_SECONDS=15     # Unattended object duration
ALERT_COOLDOWN_SECONDS=20        # Duplicate alert suppression window
DEVICE=auto                      # auto | cuda | cpu | mps
```

---

## Running the System

### Terminal 1 — Backend

```bash
cd backend
.venv\Scripts\activate    # Windows
uvicorn app.main:app --reload
```

Server starts at: **http://localhost:8000**
Swagger Docs at: **http://localhost:8000/docs**

### Terminal 2 — Frontend

```bash
cd frontend
npm run dev
```

Dashboard opens at: **http://localhost:8080**

### Using the System

1. Open **http://localhost:8080** in your browser
2. **Upload a video** — drag & drop or click the upload area
3. Dashboard transitions through: **UPLOADING → PROCESSING → RUNNING**
4. **Alerts** appear in the right panel when suspicious behavior is confirmed
5. On completion, status transitions to **FINISHED** and processing stops (no looping)
6. Click **View** on any alert to open the captured snapshot

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload` | Upload video file and start processing |
| `POST` | `/api/start` | Start processing last uploaded video |
| `POST` | `/api/stop` | Stop video processing |
| `GET` | `/api/status` | System status, FPS, counts |
| `GET` | `/api/frame` | Latest detections metadata |
| `GET` | `/api/video_feed` | MJPEG video stream |
| `GET` | `/api/alerts?limit=50` | Get alert list |
| `DELETE` | `/api/alerts` | Clear all alerts |
| `GET` | `/api/snapshots/{name}` | Get snapshot image |
| `GET` | `/api/config` | Current configuration |

---

## Alert Behavior & Decision Criteria

Alerts are designed to be stable, intelligent, and practical. The system does not raise an alert from a single noisy frame. It verifies persistence and context across frames before alerting.

### 1. Suspicious Loitering vs. Safe Waiting Discrimination
The loitering engine distinguishes between genuine suspicious activity and benign waiting:

- **Safe Waiting (Loitering Alert Suppressed):**
  1. **Designated Waiting Zones:** Person is standing inside an authorized area or waiting lounge (`EXCLUDED` zone type).
  2. **Social Companion Presence:** Person is accompanied by another individual (center distance $< 130$ pixels) — e.g. waiting together, talking, or meeting someone.
  3. **Calm Stationary Waiting:** Person is standing peacefully in place ($D_{total} < 60$ px, $D_{net} < 40$ px) without anxious pacing.
  4. **Directional Transit:** Person is walking with a clear trajectory across the area in a consistent direction ($D_{total} \approx D_{net}$).

- **Suspicious Loitering (Alert Triggered):**
  1. **Dwell Time Threshold:** Person lingers alone in the area for $\ge 15$ seconds.
  2. **Restless Pacing Ratio:** Total path traveled is significantly higher than net displacement ($D_{total} / \max(30, D_{net}) \ge 2.0$), indicating back-and-forth movement.
  3. **Direction Reversals:** At least 3 turnaround vector changes along the path.
  4. **Perimeter Casing:** Lingering within 120 pixels of a restricted zone perimeter without entering.
  5. **Composite Suspicion Score:** Overall calculated score $\ge 0.65$.

### 2. Weapon Detection & Class Reconciliation (Guns vs. Knives)
- **Specialized Firearm Model:** Evaluates frames synchronously with base detection.
- **Accurate Disambiguation:** Resolves the issue where standard COCO models misclassified guns as knives due to missing gun classes in standard 80-class COCO. Compares model confidences and prioritizes specialized firearm classifications.
- **Support Checking:** Verifies held weapon proximity to tracked individuals without requiring unrealistic tight IoU constraints.

### 3. Restricted Zone (Intrusion) Alert
- Raised when an unauthorized person breaches a restricted perimeter.
- Dwell time verification prevents false positives from momentary edge passes.
- Escalates dynamically from Medium $\to$ High $\to$ Critical severity with continued persistence.

### 4. Unattended Object Alert
- Continuously monitors carry items (backpack, handbag, suitcase).
- Tracks whether the item's previous carrier or any nearby person moves outside the proximity threshold.
- Triggers alert once left isolated longer than configured unattended seconds.

### 5. Notifications with Bold Critical Level & Explicit Reasons
- Every alert generated across **all features** includes:
  - **CRITICAL LEVEL:** Prominently formatted in **BOLD** (e.g. `CRITICAL`, `HIGH`, `MEDIUM`).
  - **REASON FOR ALERT:** Clear, plain-English explanation explaining exactly why the event triggered.
- Delivered via:
  - **Email:** Rich HTML with alert cards and plain-text fallback with attached snapshot evidence.
  - **SMS:** Immediate alert text with critical level, reason, and timestamp.
  - **Web Dashboards:** Highlighted badges and incident cards.
- **Deduplication:** 60-second cooldown window prevents duplicate alerts or notification spam for the same incident.

---

## Triple-Lock Logic

The system uses a simplified multi-layer verification:

```
Lock 1: Object Detection (YOLOv8)     ✅ Automated
        ↓ Object confirmed in frame
Lock 2: Behavior Analysis (Rules)     ✅ Automated
        ↓ Suspicious behavior matched
Lock 3: Face Recognition              🔓 Placeholder
        ↓ (Displayed as pending in UI)
  
        ══════════════════
        ║  ALERT RAISED  ║
        ══════════════════
```

In the alerts panel, this appears as:

- **[✔ Detection] [✔ Behavior] [○ Face]**

---

## Future Scope

- **Face Recognition (Lock 3)** — Integrate face detection and identification
- **Edge AI Deployment** — Run on Raspberry Pi or NVIDIA Jetson
- **Multi-Camera Support** — Process multiple video streams simultaneously
- **WebSocket Alerts** — Replace polling with real-time push notifications
- **Cloud Storage** — Store alerts and snapshots in cloud (AWS S3, GCS)
- **Deep Learning Behavior** — Replace rules with trained behavior models
- **Mobile App** — Push notifications to mobile devices

---

## Contact

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/ch-ayushman-patro) [![GitHub](https://img.shields.io/badge/GitHub-Follow-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/Ch-Ayushman-Patro)

*For questions, suggestions, or collaboration opportunities, feel free to reach out!*
