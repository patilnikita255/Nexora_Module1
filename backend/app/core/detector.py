"""
YOLOv8 Object Detection wrapper for Surveillance System.

Uses:
  1. Base COCO YOLOv8n: detects person, backpack, handbag, suitcase, knife.
  2. Fine-tuned lightweight Gun model (firearm_yolov8n.pt): detects guns.
     Optimized for CPU: gun detection runs every Nth frame (e.g. 4th frame)
     to cut CPU inference load in half while maintaining smooth multi-frame confirmation.
"""

from __future__ import annotations

import os
from typing import List, Optional

import cv2
import numpy as np
import torch
from ultralytics import YOLO

# PyTorch 2.6+ compatibility for older Ultralytics weights
_original_load = torch.load
def _patched_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _original_load(*args, **kwargs)
torch.load = _patched_load

from app.config import get_settings
from app.models.schemas import BBox, Detection

# Surveillance-relevant COCO classes
SURVEILLANCE_CLASSES = {
    0: "person",
    24: "backpack",
    26: "handbag",
    28: "suitcase",
    43: "knife",
}

# Minimum allowed dimension for a gun detection box (filters tiny artifacts)
GUN_MIN_DIMENSION = 14

# Absurd boxes (whole frame / person-sized) are gun-model artifacts.
GUN_ABSURD_HEIGHT_RATIO = 0.40
GUN_ABSURD_WIDTH_RATIO = 0.40
GUN_ABSURD_AREA_RATIO = 0.15

# Minimum overlap between weapon boxes to trigger reconciliation
WEAPON_OVERLAP_IOU = 0.20


class ObjectDetector:
    """Wraps YOLOv8n base model and fine-tuned gun model for CPU-optimized detection."""

    def __init__(self) -> None:
        settings = get_settings()
        model_path = settings.yolo_model
        self.device = self._resolve_device(settings.device)

        # 1. Base COCO model (Person, Bags, Knife)
        try:
            self.model = YOLO(model_path)
            self.model.to(self.device)
            print(f"[Detector] Loaded base model: {model_path} on {self.device}")
        except Exception as e:
            print(f"[Detector] ERROR loading base model: {e}")
            raise

        self.confidence_threshold = settings.yolo_confidence
        self.gun_confidence = settings.gun_confidence

        # 2. Fine-tuned lightweight gun model (runs on each processed frame)
        self.gun_model = None
        self.gun_interval = 1
        self._frame_index = 0
        self._cached_gun_detections: List[Detection] = []

        if settings.enable_firearm_model:
            gun_candidates = [
                os.path.join(settings.weights_dir, "firearm_yolov8n.pt"),
                os.path.join(os.path.dirname(model_path), "firearm_yolov8n.pt"),
                os.path.join("backend", "weights", "firearm_yolov8n.pt"),
                os.path.join("weights", "firearm_yolov8n.pt"),
            ]
            for gp in gun_candidates:
                if os.path.isfile(gp):
                    try:
                        self.gun_model = YOLO(gp)
                        self.gun_model.to(self.device)
                        print(f"[Detector] Loaded fine-tuned gun model from: {gp}")
                        break
                    except Exception as e:
                        print(f"[Detector] Could not load gun model from {gp}: {e}")

    @staticmethod
    def _resolve_device(device_setting: str) -> str:
        """Resolve compute device (CPU default for smooth CPU inference)."""
        s = device_setting.strip().lower()
        if s == "auto":
            if torch.cuda.is_available():
                return "cuda"
            return "cpu"
        if s == "cuda" and not torch.cuda.is_available():
            return "cpu"
        return s

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run detection on a single frame.

        Args:
            frame: BGR image numpy array.

        Returns:
            List of Detection objects.
        """
        self._frame_index += 1
        detections: List[Detection] = []

        # 1. Base model detection (Person, Bags, Knife)
        # Using imgsz=640 for lightweight, quadratic CPU speedup
        results = self.model(
            frame,
            conf=self.confidence_threshold,
            imgsz=640,
            device=self.device,
            verbose=False,
        )

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                cls_id = int(box.cls[0])
                if cls_id not in SURVEILLANCE_CLASSES:
                    continue

                conf = float(box.conf[0])
                # Knife confidence threshold >= 0.35
                if cls_id == 43 and conf < 0.35:
                    continue

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

        # 2. Fine-tuned Gun Model Detection (Run on each processed frame)
        if self.gun_model is not None:
            persons = [d for d in detections if d.class_name == "person"]
            gun_results = self.gun_model(
                frame,
                conf=self.gun_confidence,
                imgsz=640,
                device=self.device,
                verbose=False,
            )
            current_guns: List[Detection] = []
            for g_res in gun_results:
                if g_res.boxes is None:
                    continue
                for box in g_res.boxes:
                    conf = float(box.conf[0])
                    if conf < self.gun_confidence:
                        continue
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    bw = x2 - x1
                    bh = y2 - y1
                    # Ignore tiny artifacts
                    if bw < GUN_MIN_DIMENSION or bh < GUN_MIN_DIMENSION:
                        continue
                    frame_h, frame_w = frame.shape[:2]
                    if not self._gun_box_is_plausible(
                        x1, y1, x2, y2, frame_w, frame_h, persons
                    ):
                        continue
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2

                    current_guns.append(
                        Detection(
                            class_name="gun",
                            confidence=round(conf, 3),
                            bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2),
                            center_x=cx,
                            center_y=cy,
                        )
                    )
            self._cached_gun_detections = current_guns
            detections.extend(self._cached_gun_detections)

        # 3. Reconcile weapon classes (Gun vs Knife) to prevent mislabeling
        detections = self._reconcile_weapon_classes(detections)

        return detections

    def _gun_box_is_plausible(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        frame_w: int,
        frame_h: int,
        persons: List[Detection],
    ) -> bool:
        """
        Discard absurd gun-model artifacts while keeping genuine handguns and long guns.
        Crucially:
          1. Rejects whole-body false positives (when gun model mistakes a person for a gun).
          2. When persons are present, the weapon must have physical proximity (< 220px or overlapping).
          3. Rejects frame-sized or wall-sized boxes.
        """
        if frame_w <= 0 or frame_h <= 0:
            return True

        bw = x2 - x1
        bh = y2 - y1
        gun_area = max(1, bw * bh)

        if bh / frame_h > GUN_ABSURD_HEIGHT_RATIO:
            return False
        if bw / frame_w > GUN_ABSURD_WIDTH_RATIO:
            return False
        if (gun_area / (frame_w * frame_h)) > GUN_ABSURD_AREA_RATIO:
            return False

        if persons:
            has_person_proximity = False
            for p in persons:
                px1, py1, px2, py2 = p.bbox.x1, p.bbox.y1, p.bbox.x2, p.bbox.y2
                pw = max(1, px2 - px1)
                ph = max(1, py2 - py1)
                p_area = max(1, pw * ph)

                ix1 = max(x1, px1)
                iy1 = max(y1, py1)
                ix2 = min(x2, px2)
                iy2 = min(y2, py2)
                iw = max(0, ix2 - ix1)
                ih = max(0, iy2 - iy1)
                inter = iw * ih
                union = gun_area + p_area - inter
                iou = inter / union if union > 0 else 0.0

                # Reject if the gun box is actually the whole person's body
                if iou > 0.35:
                    return False
                if inter > 0 and (gun_area / p_area > 0.40):
                    return False
                if inter > 0 and (bh / ph > 0.55):
                    return False

                # Proximity check
                dist = (
                    ((x1 + x2) / 2 - p.center_x) ** 2
                    + ((y1 + y2) / 2 - p.center_y) ** 2
                ) ** 0.5
                if inter > 0 or dist < 220:
                    has_person_proximity = True

            if not has_person_proximity:
                return False

        return True

    @staticmethod
    def _iou(box_a: BBox, box_b: BBox) -> float:
        """Intersection-over-Union between two bounding boxes."""
        ix1 = max(box_a.x1, box_b.x1)
        iy1 = max(box_a.y1, box_b.y1)
        ix2 = min(box_a.x2, box_b.x2)
        iy2 = min(box_a.y2, box_b.y2)

        inter_w = max(0, ix2 - ix1)
        inter_h = max(0, iy2 - iy1)
        inter = inter_w * inter_h
        if inter == 0:
            return 0.0

        area_a = max(0, box_a.x2 - box_a.x1) * max(0, box_a.y2 - box_a.y1)
        area_b = max(0, box_b.x2 - box_b.x1) * max(0, box_b.y2 - box_b.y1)
        union = area_a + area_b - inter
        if union <= 0:
            return 0.0
        return inter / union

    @staticmethod
    def _reconcile_weapon_classes(detections: List[Detection]) -> List[Detection]:
        """
        Accurately distinguish between Gun and Knife when both models trigger.
        
        COCO YOLO has a 'knife' class but lacks a 'gun' class, causing it to often
        mislable firearms as knives. When a specialized firearm model and base knife
        detector overlap:
          1. If gun model confidence >= knife confidence - 0.10:
             The object is correctly classified as a 'gun' (lethal firearm threat).
          2. If knife confidence is substantially higher:
             The object is classified as a 'knife' (edged weapon).
          3. Confidences are boosted with supporting detection evidence.
        """
        guns = [d for d in detections if d.class_name == "gun"]
        knives = [d for d in detections if d.class_name == "knife"]
        others = [d for d in detections if d.class_name not in ("gun", "knife")]

        if not guns or not knives:
            return detections

        suppressed_knives: set[int] = set()
        suppressed_guns: set[int] = set()

        for g in guns:
            for k in knives:
                if id(k) in suppressed_knives:
                    continue
                match_score = ObjectDetector._weapon_match_score(g.bbox, k.bbox)
                if match_score >= WEAPON_OVERLAP_IOU:
                    if g.confidence >= (k.confidence - 0.10):
                        # Specialized firearm model is confident or matches -> Gun
                        suppressed_knives.add(id(k))
                        g.confidence = round(max(g.confidence, k.confidence), 3)
                    else:
                        # Base model is significantly more confident in knife -> Knife
                        suppressed_guns.add(id(g))
                        k.confidence = round(max(k.confidence, g.confidence), 3)

        kept_guns = [g for g in guns if id(g) not in suppressed_guns]
        kept_knives = [k for k in knives if id(k) not in suppressed_knives]

        return others + kept_guns + kept_knives

    @staticmethod
    def _weapon_match_score(gun_box: BBox, knife_box: BBox) -> float:
        """Calculate overlap match between gun and knife bounding boxes."""
        iou = ObjectDetector._iou(gun_box, knife_box)
        gun_cx = (gun_box.x1 + gun_box.x2) / 2
        gun_cy = (gun_box.y1 + gun_box.y2) / 2
        knife_cx = (knife_box.x1 + knife_box.x2) / 2
        knife_cy = (knife_box.y1 + knife_box.y2) / 2

        gun_center_in_knife = (
            knife_box.x1 <= gun_cx <= knife_box.x2
            and knife_box.y1 <= gun_cy <= knife_box.y2
        )
        knife_center_in_gun = (
            gun_box.x1 <= knife_cx <= gun_box.x2
            and gun_box.y1 <= knife_cy <= gun_box.y2
        )

        if gun_center_in_knife or knife_center_in_gun:
            return max(iou, 0.40)
        return iou


reconcile_weapon_classes = ObjectDetector._reconcile_weapon_classes
