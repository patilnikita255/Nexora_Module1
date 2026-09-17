"""
Video Processor — orchestrates the full detection pipeline.

Pipeline per frame:
  capture → detect (YOLO) → track → analyze behavior → generate alerts → draw overlays

Runs in a background thread with thread-safe access to latest frame and metadata.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Dict, List, Optional

import cv2
import numpy as np

from app.config import get_settings
from app.core.behavior import BehaviorAnalyzer
from app.core.detector import ObjectDetector
from app.core.tracker import SimpleTracker
from app.models.schemas import (
    Detection,
    FrameMetadata,
    SystemStatus,
    TrackedObject,
)
from app.services.alert_manager import AlertManager
from app.utils.drawing import draw_frame_overlay


class VideoProcessor:
    """Manages video capture and the full AI processing pipeline."""

    def __init__(self) -> None:
        self._settings = get_settings()

        # Pipeline components (lazy-loaded in background thread)
        self._detector: Optional[ObjectDetector] = None
        self._tracker: Optional[SimpleTracker] = None
        self._analyzer: Optional[BehaviorAnalyzer] = None
        self.alert_manager: AlertManager = AlertManager()

        # State
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._initializing = False
        self._init_error: Optional[str] = None
        self._lock = threading.Lock()

        # Latest frame data (thread-safe via _lock)
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_jpeg: Optional[bytes] = None
        self._latest_detections: List[Detection] = []
        self._latest_tracked: List[TrackedObject] = []
        self._fps: float = 0.0
        self._frame_count: int = 0
        self._start_time: float = 0.0
        self._video_source: Optional[str] = None

        # Temporal buffer to confirm events across multiple frames.
        self._event_frame_buffer: Dict[str, int] = {}
        self._event_confirm_frames = 4
        self._event_decay = 1

        # Frame normalization target for more stable inference quality.
        self._target_frame_width = 768

    def _init_pipeline(self) -> bool:
        """
        Initialize AI pipeline components (heavy — runs once).
        Called inside the background thread to avoid blocking the API.
        Returns True if successful.
        """
        try:
            self._initializing = True
            if self._detector is None:
                print("[Pipeline] Initializing YOLOv8 detector...")
                self._detector = ObjectDetector()
            if self._tracker is None:
                self._tracker = SimpleTracker()
            if self._analyzer is None:
                self._analyzer = BehaviorAnalyzer()
            self._init_error = None
            print("[Pipeline] All components ready.")
            return True
        except Exception as e:
            self._init_error = str(e)
            print(f"[Pipeline] ERROR initializing: {e}")
            return False
        finally:
            self._initializing = False

    def start(self, video_path: str) -> bool:
        """
        Start processing a video file.
        This method returns immediately — processing happens in background.

        Args:
            video_path: Path to the uploaded video file.

        Returns:
            True if background thread was launched successfully.
        """
        if self._running:
            self.stop()

        # Validate file exists
        if not os.path.isfile(video_path):
            print(f"[Processor] Video file not found: {video_path}")
            return False

        # Open video to validate it before starting background work
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"[Processor] Failed to open: {video_path}")
            return False

        self._cap = cap
        self._frame_count = 0
        self._fps = 0.0
        self._start_time = time.time()
        self._video_source = os.path.basename(video_path)
        self._running = True
        self._init_error = None

        # Start processing thread (pipeline init happens inside the thread)
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        print(f"[Processor] Background thread started for: {video_path}")
        return True

    def stop(self) -> None:
        """Stop video processing."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        print("[Processor] Stopped.")

    def _process_loop(self) -> None:
        """Main processing loop — runs in background thread."""

        # Initialize pipeline INSIDE the thread (non-blocking for API)
        if not self._init_pipeline():
            print("[Processor] Pipeline init failed. Stopping.")
            self._running = False
            return

        self._tracker.reset()
        self._analyzer.reset()
        self._event_frame_buffer.clear()
        frame_times: list[float] = []

        # Skip frames for performance — process every Nth frame
        process_every_n = 2  # Process every 2nd frame for speed
        raw_count = 0

        try:
            while self._running and self._cap and self._cap.isOpened():
                t_start = time.time()

                ret, frame = self._cap.read()
                if not ret:
                    print("[Processor] End of video reached. Stopping processing.")
                    self._running = False
                    break

                raw_count += 1
                self._frame_count += 1
                frame = self._preprocess_frame(frame)

                # Process every Nth frame for performance
                if raw_count % process_every_n != 0:
                    _, jpeg = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
                    )
                    with self._lock:
                        self._latest_frame = frame
                        self._latest_jpeg = jpeg.tobytes()
                    continue

                # --- Detection ---
                detections = self._detector.detect(frame)

                # --- Tracking ---
                tracked = self._tracker.update(detections)

                # --- Behavior Analysis ---
                h, w = frame.shape[:2]
                events = self._analyzer.analyze(tracked, w, h)
                confirmed_events = self._confirm_persistent_events(events)

                # --- Alert Generation ---
                if confirmed_events:
                    self.alert_manager.process_events(
                        confirmed_events,
                        frame,
                        event_frame_counts=self._event_frame_buffer,
                    )

                # --- Draw Overlays ---
                annotated = draw_frame_overlay(
                    frame.copy(),
                    detections,
                    tracked,
                    self._settings.intrusion_zone_coords,
                    self._fps,
                )

                # --- Encode to JPEG ---
                _, jpeg = cv2.imencode(
                    ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70]
                )

                # --- Update shared state ---
                with self._lock:
                    self._latest_frame = annotated
                    self._latest_jpeg = jpeg.tobytes()
                    self._latest_detections = detections
                    self._latest_tracked = tracked

                # --- FPS calculation ---
                elapsed = time.time() - t_start
                frame_times.append(elapsed)
                if len(frame_times) > 30:
                    frame_times.pop(0)
                avg_time = sum(frame_times) / len(frame_times)
                self._fps = round(1.0 / avg_time, 1) if avg_time > 0 else 0.0

                # Small yield to prevent CPU hogging, but no artificial throttle
                time.sleep(0.001)
        finally:
            if self._cap:
                self._cap.release()
                self._cap = None
            self._running = False

    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """Apply consistent resize + CLAHE normalization for better frame quality."""
        h, w = frame.shape[:2]
        if w > 0 and w != self._target_frame_width:
            scale = self._target_frame_width / float(w)
            target_h = max(1, int(h * scale))
            frame = cv2.resize(frame, (self._target_frame_width, target_h), interpolation=cv2.INTER_LINEAR)

        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)
        enhanced = cv2.merge((l_channel, a_channel, b_channel))
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    @staticmethod
    def _event_key(event) -> str:
        primary = event.primary_object_id
        if primary is None:
            primary = event.involved_objects[0] if event.involved_objects else -1
        return f"{event.event_type.value}:{primary}"

    def _confirm_persistent_events(self, events: List) -> List:
        """Keep a decaying frame buffer and confirm events only after persistence."""
        active_keys: set[str] = set()
        event_by_key: Dict[str, object] = {}

        for event in events:
            key = self._event_key(event)
            active_keys.add(key)
            event_by_key[key] = event
            self._event_frame_buffer[key] = self._event_frame_buffer.get(key, 0) + 1
            event.frame_count = max(event.frame_count, self._event_frame_buffer[key])

        for key in list(self._event_frame_buffer.keys()):
            if key in active_keys:
                continue
            updated = max(0, self._event_frame_buffer[key] - self._event_decay)
            if updated == 0:
                self._event_frame_buffer.pop(key, None)
            else:
                self._event_frame_buffer[key] = updated

        confirmed = []
        for key, event in event_by_key.items():
            if self._event_frame_buffer.get(key, 0) >= self._event_confirm_frames:
                confirmed.append(event)

        return confirmed

    def get_latest_jpeg(self) -> Optional[bytes]:
        """Get the latest processed frame as JPEG bytes (thread-safe)."""
        with self._lock:
            return self._latest_jpeg

    def get_frame_metadata(self) -> FrameMetadata:
        """Get metadata for the latest processed frame."""
        with self._lock:
            return FrameMetadata(
                detections=list(self._latest_detections),
                tracked_objects=list(self._latest_tracked),
                object_count=len(self._latest_tracked),
                fps=self._fps,
                frame_number=self._frame_count,
            )

    def get_status(self) -> SystemStatus:
        """Get current system status."""
        uptime = time.time() - self._start_time if self._running else 0.0
        return SystemStatus(
            is_running=self._running,
            fps=self._fps,
            frame_count=self._frame_count,
            object_count=len(self._latest_tracked),
            alert_count=self.alert_manager.alert_count,
            uptime_seconds=round(uptime, 1),
            video_source=self._video_source,
        )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def init_error(self) -> Optional[str]:
        return self._init_error

    def generate_mjpeg(self):
        """Generator that yields MJPEG frames for streaming."""
        while self._running:
            jpeg = self.get_latest_jpeg()
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
            time.sleep(0.033)  # ~30fps
