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
    AlertType,
    Detection,
    FrameMetadata,
    SystemStatus,
    TrackedObject,
    ZoneConfig,
    ZoneType,
)
from app.services.alert_manager import AlertManager
from app.utils.drawing import draw_frame_overlay


class VideoProcessor:
    """Manages video capture and the full AI processing pipeline."""

    def __init__(self) -> None:
        self._settings = get_settings()

        # Pipeline components (detector/tracker lazy-loaded in background thread)
        self._detector: Optional[ObjectDetector] = None
        self._tracker: Optional[SimpleTracker] = None
        self._analyzer: BehaviorAnalyzer = BehaviorAnalyzer()
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
        self._latest_jpeg_restricted: Optional[bytes] = None
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

        self._is_webcam: bool = False
        self._camera_mode: str = "main"

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

    def start(self, video_path: str | int = 0, mode: str = "main") -> bool:
        """
        Start processing a video file or live camera.
        This method returns immediately — processing happens in background.

        Args:
            video_path: Path to video file OR 0 / 'webcam' for live camera.
            mode: 'main' (weapons & unattended objects only) or 'restricted' (perimeter intrusion only)

        Returns:
            True if background thread was launched successfully.
        """
        if self._running:
            self.stop()

        self._camera_mode = mode
        is_webcam = False
        str_source = str(video_path).strip().lower()
        if isinstance(video_path, int) or str_source.isdigit() or str_source in ("webcam", "live", "camera"):
            is_webcam = True
            cam_id = 0 if str_source in ("webcam", "live", "camera") else int(video_path)
            print(f"[Processor] Opening live camera index {cam_id}...")
            cap = cv2.VideoCapture(cam_id)
        else:
            if not os.path.isfile(video_path):
                print(f"[Processor] Video file not found: {video_path}")
                return False
            cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            print(f"[Processor] Failed to open: {video_path}")
            return False

        self._is_webcam = is_webcam
        self._cap = cap
        self._frame_count = 0
        self._fps = 0.0
        self._start_time = time.time()
        self._video_source = "Live Camera" if is_webcam else os.path.basename(str(video_path))
        self._running = True
        self._init_error = None

        # Start processing thread (pipeline init happens inside the thread)
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        print(f"[Processor] Background thread started for: {self._video_source}")
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
                    if self._is_webcam:
                        time.sleep(0.05)
                        continue
                    # Video file reached the end — loop back so the surveillance feed keeps playing seamlessly
                    print("[Processor] End of video reached. Looping back to beginning.")
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    time.sleep(0.04)
                    continue

                raw_count += 1
                self._frame_count += 1
                frame = self._preprocess_frame(frame)

                # Process every Nth frame for performance
                if raw_count % process_every_n != 0:
                    _, jpeg = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
                    )
                    jpeg_bytes = jpeg.tobytes()
                    with self._lock:
                        self._latest_frame = frame
                        self._latest_jpeg = jpeg_bytes
                        if self._latest_jpeg_restricted is None:
                            self._latest_jpeg_restricted = jpeg_bytes
                    if not self._is_webcam:
                        time.sleep(0.02)
                    continue

                # --- Detection ---
                detections = self._detector.detect(frame)

                # --- Tracking ---
                tracked = self._tracker.update(detections)

                # --- Behavior Analysis ---
                h, w = frame.shape[:2]
                events = self._analyzer.analyze(tracked, w, h, camera_mode=self._camera_mode)
                confirmed_events = self._confirm_persistent_events(events)

                # --- Draw Overlays for both Dashboard views ---
                # Dashboard 1 (General Area): detections only, no zone overlays
                annotated_main = draw_frame_overlay(
                    frame.copy(),
                    detections,
                    tracked,
                    self._settings.intrusion_zone_coords,
                    self._fps,
                    zones=None,
                    show_zones=False,
                )

                # Dashboard 2 (Restricted Area): detections + perimeter zone overlays
                annotated_restricted = draw_frame_overlay(
                    frame.copy(),
                    detections,
                    tracked,
                    self._settings.intrusion_zone_coords,
                    self._fps,
                    zones=self._analyzer.get_zones(),
                    show_zones=True,
                )

                # --- Alert Generation ---
                if confirmed_events:
                    has_intrusion = any(e.event_type == AlertType.INTRUSION for e in confirmed_events)
                    snapshot_frame = annotated_restricted if has_intrusion else annotated_main
                    self.alert_manager.process_events(
                        confirmed_events,
                        snapshot_frame,
                        event_frame_counts=self._event_frame_buffer,
                    )

                # --- Encode to JPEG ---
                _, jpeg_main = cv2.imencode(
                    ".jpg", annotated_main, [cv2.IMWRITE_JPEG_QUALITY, 70]
                )
                jpeg_main_bytes = jpeg_main.tobytes()

                _, jpeg_restricted = cv2.imencode(
                    ".jpg", annotated_restricted, [cv2.IMWRITE_JPEG_QUALITY, 70]
                )
                jpeg_restricted_bytes = jpeg_restricted.tobytes()

                # --- Update shared state ---
                with self._lock:
                    self._latest_frame = annotated_restricted
                    self._latest_jpeg = jpeg_main_bytes
                    self._latest_jpeg_restricted = jpeg_restricted_bytes
                    self._latest_detections = detections
                    self._latest_tracked = tracked


                # --- FPS calculation ---
                elapsed = time.time() - t_start
                frame_times.append(elapsed)
                if len(frame_times) > 30:
                    frame_times.pop(0)
                avg_time = sum(frame_times) / len(frame_times)
                self._fps = round(1.0 / avg_time, 1) if avg_time > 0 else 0.0

                # Pacing: target smooth ~25 FPS playback for video files
                if not self._is_webcam:
                    time.sleep(0.03)
                else:
                    time.sleep(0.001)
        finally:
            if self._cap:
                self._cap.release()
                self._cap = None
            self._running = False

    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """Resize to the target width for consistent inference.

        NOTE: No CLAHE here — contrast enhancement suppresses the fine-tuned gun
        model (verified: clahe frames drop conf ~0.64 -> ~0.40 and kill most
        inference windows), so detection must see the plain resized frame.
        """
        h, w = frame.shape[:2]
        if w > 0 and w != self._target_frame_width:
            scale = self._target_frame_width / float(w)
            target_h = max(1, int(h * scale))
            frame = cv2.resize(frame, (self._target_frame_width, target_h), interpolation=cv2.INTER_LINEAR)
        return frame

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
        weapon_confirm_frames = get_settings().weapon_confirm_frames
        for key, event in event_by_key.items():
            req_frames = weapon_confirm_frames if event.event_type == AlertType.WEAPON_DETECTED else self._event_confirm_frames
            if self._event_frame_buffer.get(key, 0) >= req_frames:
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

    def get_status(self, mode: Optional[str] = None) -> SystemStatus:
        """Get current system status."""
        active_mode = mode or self._camera_mode
        uptime = time.time() - self._start_time if self._running else 0.0

        # Dashboard 1 (General Area): strictly weapons and unattended objects
        if active_mode in ("main", "general", "open_area"):
            gen_count = self.alert_manager.get_alert_count(
                {AlertType.WEAPON_DETECTED, AlertType.UNATTENDED_OBJECT}
            )
            return SystemStatus(
                is_running=self._running,
                fps=self._fps,
                frame_count=self._frame_count,
                object_count=len(self._latest_tracked),
                alert_count=gen_count,
                uptime_seconds=round(uptime, 1),
                video_source=self._video_source,
                zone_breached=False,
                active_intruders=0,
                zone_coords="",
                zones=[],
            )


        zones = self.get_zones()
        active_restricted = [z for z in zones if z.zone_type == ZoneType.RESTRICTED and z.is_active]
        active_excluded = [z for z in zones if z.zone_type == ZoneType.EXCLUDED and z.is_active]

        intruders = 0
        with self._lock:
            if self._latest_frame is not None and self._latest_tracked:
                h, w = self._latest_frame.shape[:2]
                for obj in self._latest_tracked:
                    if obj.class_name != "person":
                        continue

                    # Suppress if in an excluded/waiting zone
                    is_excluded = False
                    for ez in active_excluded:
                        ex1, ex2 = int(ez.coords[0] * w), int(ez.coords[2] * w)
                        ey1, ey2 = int(ez.coords[1] * h), int(ez.coords[3] * h)
                        if ex1 <= obj.center_x <= ex2 and ey1 <= obj.bbox.y2 <= ey2:
                            is_excluded = True
                            break
                    if is_excluded:
                        continue

                    # Check if inside any restricted perimeter
                    for rz in active_restricted:
                        rx1, rx2 = int(rz.coords[0] * w), int(rz.coords[2] * w)
                        ry1, ry2 = int(rz.coords[1] * h), int(rz.coords[3] * h)
                        if rx1 <= obj.center_x <= rx2 and ry1 <= obj.bbox.y2 <= ry2:
                            intruders += 1
                            break

        return SystemStatus(
            is_running=self._running,
            fps=self._fps,
            frame_count=self._frame_count,
            object_count=len(self._latest_tracked),
            alert_count=self.alert_manager.alert_count,
            uptime_seconds=round(uptime, 1),
            video_source=self._video_source,
            zone_breached=(intruders > 0),
            active_intruders=intruders,
            zone_coords=self._settings.intrusion_zone,
            zones=zones,
        )

    def get_zones(self) -> List[ZoneConfig]:
        """Get currently configured surveillance zones."""
        if self._analyzer is not None:
            return self._analyzer.get_zones()
        return self._settings.get_default_zones()

    def set_zones(self, zones: List[ZoneConfig]) -> None:
        """Set surveillance zones."""
        if self._analyzer is None:
            self._analyzer = BehaviorAnalyzer()
        self._analyzer.set_zones(zones)

    def add_zone(self, zone: ZoneConfig) -> None:
        """Add or update a surveillance zone."""
        if self._analyzer is None:
            self._analyzer = BehaviorAnalyzer()
        self._analyzer.add_zone(zone)

    def remove_zone(self, zone_id: str) -> bool:
        """Remove a surveillance zone by ID."""
        if self._analyzer is None:
            self._analyzer = BehaviorAnalyzer()
        return self._analyzer.remove_zone(zone_id)

    @property
    def camera_mode(self) -> str:
        """Return the active camera mode ('main' or 'restricted')."""
        return self._camera_mode

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def init_error(self) -> Optional[str]:
        return self._init_error

    def generate_mjpeg(self, mode: str = "main"):
        """Generator that yields MJPEG frames for streaming."""
        # Wait up to 10 seconds for the first frame to be ready
        for _ in range(100):
            if not self._running:
                break
            with self._lock:
                target = self._latest_jpeg_restricted if mode == "restricted" else self._latest_jpeg
                if target is not None:
                    break
            time.sleep(0.08)

        while self._running:
            with self._lock:
                jpeg = self._latest_jpeg_restricted if mode == "restricted" else self._latest_jpeg
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
                time.sleep(0.033)  # ~30fps
            else:
                time.sleep(0.05)
