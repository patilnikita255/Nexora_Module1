"""
YOLOv8 Object Detection wrapper.

Uses Ultralytics YOLOv8 for real-time object detection.
The model is auto-downloaded on first run.
"""

from __future__ import annotations

from typing import List

import cv2
import numpy as np
import torch
from ultralytics import YOLO

# PyTorch 2.6+ compatibility for older Ultralytics versions
_original_load = torch.load
def _patched_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _original_load(*args, **kwargs)
torch.load = _patched_load

from app.config import get_settings
from app.models.schemas import BBox, Detection

# Classes we care about for surveillance
SURVEILLANCE_CLASSES = {
    0: "person",
    24: "backpack",
    26: "handbag",
    28: "suitcase",
    43: "knife",
}


class ObjectDetector:
    """Wraps YOLOv8 for surveillance-relevant object detection."""

    def __init__(self) -> None:
        settings = get_settings()
        model_path = settings.yolo_model

        # Resolve compute device
        self.device = self._resolve_device(settings.device)

        try:
            self.model = YOLO(model_path)
            self.model.to(self.device)
        except Exception as e:
            error_msg = (
                f"\n{'='*60}\n"
                f"  YOLO MODEL LOAD FAILED: {model_path}\n"
                f"  \n"
                f"  The model file could not be downloaded automatically.\n"
                f"  Please download it manually:\n"
                f"  \n"
                f"  1. Go to: https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8n.pt\n"
                f"  2. Save the file as: backend/{model_path}\n"
                f"  3. Restart the server\n"
                f"  \n"
                f"  Original error: {e}\n"
                f"{'='*60}\n"
            )
            print(error_msg)
            raise RuntimeError(error_msg) from e
        self.confidence_threshold = settings.yolo_confidence
        print(f"[Detector] Loaded model: {model_path} on device: {self.device}")

    @staticmethod
    def _resolve_device(device_setting: str) -> str:
        """Resolve the compute device from the DEVICE env var."""
        device_setting = device_setting.strip().lower()
        if device_setting == "auto":
            if torch.cuda.is_available():
                resolved = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                resolved = "mps"
            else:
                resolved = "cpu"
            print(f"[Detector] DEVICE=auto → resolved to: {resolved}")
            return resolved
        if device_setting == "cuda" and not torch.cuda.is_available():
            print("[Detector] WARNING: DEVICE=cuda but CUDA not available. Falling back to CPU.")
            return "cpu"
        if device_setting == "mps" and not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
            print("[Detector] WARNING: DEVICE=mps but MPS not available. Falling back to CPU.")
            return "cpu"
        return device_setting

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run detection on a single frame.

        Args:
            frame: BGR image as numpy array.

        Returns:
            List of Detection objects for surveillance-relevant classes.
        """
        results = self.model(
            frame,
            conf=self.confidence_threshold,
            device=self.device,
            verbose=False,
        )

        detections: List[Detection] = []

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                cls_id = int(box.cls[0])

                # Filter to only surveillance-relevant classes
                if cls_id not in SURVEILLANCE_CLASSES:
                    continue

                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2

                detections.append(
                    Detection(
                        class_name=SURVEILLANCE_CLASSES[cls_id],
                        confidence=round(conf, 3),
                        bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2),
                        center_x=cx,
                        center_y=cy,
                    )
                )

        return detections
