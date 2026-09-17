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

## Alert Behavior & Update Rules

Alerts are designed to be stable and practical. The system does not raise an alert from one random frame. It waits, verifies, and then shows alerts only when behavior is consistent.

### 1. Loitering Alert
- Raised when a person stays in the same monitored area longer than the configured limit.
- The system checks this for a short period before confirming, to reduce false alarms.
- If the person keeps staying longer, alert seriousness may increase.
- Alert card includes person ID and how long they have remained.

### 2. Restricted Zone (Intrusion) Alert
- Raised when a person enters the restricted area.
- The person must remain there briefly before the alert is confirmed.
- This avoids instant alerts from quick edge crossings.
- If the person keeps staying in the restricted area, the severity can move from medium to high/critical.
- Alert card includes person ID and time spent in the zone.

### 3. Unattended Object Alert
- Applies to bags and similar carry items (backpack, handbag, suitcase).
- Raised when an item is left without a nearby person for the configured duration.
- The system waits and confirms over multiple checks before creating the alert.
- If the item remains unattended longer, severity can increase.
- Alert card includes object ID and unattended duration.

### 4. Alert Deduplication and Cooldown
- The same alert for the same object is not repeated continuously.
- After an alert is raised, a cooldown period is applied before another similar one can appear.
- This keeps the panel readable and prevents alert spam.

### 5. When Alerts Appear in UI
- Alerts refresh automatically every few seconds.
- New alerts are added to the list without removing older ones.
- Each alert shows useful context: time, severity, related object ID, duration, confidence, and snapshot (if available).

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
