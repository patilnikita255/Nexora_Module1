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
GUN_MIN_DIMENSION = 28

# Absurd boxes (whole frame / wall-sized) are always gun-model artifacts.
GUN_ABSURD_HEIGHT_RATIO = 0.75
GUN_ABSURD_WIDTH_RATIO = 0.75
GUN_ABSURD_AREA_RATIO = 0.70

# A person-sized gun box is only believable when it overlaps a person.
# The fine-tuned gun model frequently fires on knife-wielding frames with a
# large region that contains no person (and no base-model knife); genuinely
# held weapons produce a box wrapped around the detected person instead
# (observed person-IoU ~0.9 on the real handgun clip).
GUN_LARGE_HEIGHT_RATIO = 0.28
GUN_LARGE_WIDTH_RATIO = 0.28
GUN_SUPPORT_PERSON_IOU = 0.30

# Minimum overlap between a gun-model box and a base-model knife box to
# reclassify the detection as "knife". Kept low because the gun boxes tend to
# be larger than the tight knife boxes (raw IoU underestimates the match).
WEAKNESS_KNIFE_IOU = 0.15


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

        # 2. Fine-tuned lightweight gun model
        self.gun_model = None
        self.gun_interval = 4  # Run gun inference every 4th frame on CPU
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

        # 2. Fine-tuned Gun Model Detection (Run every Nth frame on CPU)
        if self.gun_model is not None:
            if self._frame_index % self.gun_interval == 0:
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

            # Add cached gun detections to current frame detections
            detections.extend(self._cached_gun_detections)

        # 3. Reconcile gun-model output against base-model knives.
        # If the fine-tuned model flags something as "gun" that the base COCO
        # model reliably identifies as "knife", trust the base model.
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
        Heuristics that discard gun-model false positives:

        1. Absurd (whole-frame / wall-sized) boxes are always artifacts.
        2. A person-sized box must overlap a base-model person. The real
           handgun clip yields a gun box that essentially wraps the detected
           person (person-IoU ~0.9), whereas knife scenes frequently produce a
           large gun box over a region with no person at all.
        """
        if frame_w <= 0 or frame_h <= 0:
            return True

        bw = x2 - x1
        bh = y2 - y1
        if bh / frame_h > GUN_ABSURD_HEIGHT_RATIO:
            return False
        if bw / frame_w > GUN_ABSURD_WIDTH_RATIO:
            return False
        if (bw * bh) / (frame_w * frame_h) > GUN_ABSURD_AREA_RATIO:
            return False

        if (bh / frame_h > GUN_LARGE_HEIGHT_RATIO) or (
            bw / frame_w > GUN_LARGE_WIDTH_RATIO
        ):
            gun_bbox = BBox(x1=x1, y1=y1, x2=x2, y2=y2)
            best_support = 0.0
            for p in persons:
                best_support = max(best_support, self._iou(gun_bbox, p.bbox))
            return best_support >= GUN_SUPPORT_PERSON_IOU

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

    def _reconcile_weapon_classes(self, detections: List[Detection]) -> List[Detection]:
        """
        Reclassify gun-model boxes that overlap a base-model knife as 'knife'.

        When the base COCO model already detected a knife in the same spot, the
        gun-model box is almost certainly the same blade mislabeled as a gun.
        In that case the gun detection is dropped (the base knife already
        represents the object) and its (usually higher) confidence is merged
        into the keeper so downstream alert confidence stays meaningful.
        """
        guns = [d for d in detections if d.class_name == "gun"]
        if not guns:
            return detections

        kept = [d for d in detections if d.class_name != "gun"]
        for g in guns:
            best_iou = 0.0
            best_knife: Optional[Detection] = None
            for other in kept:
                if other.class_name != "knife":
                    continue
                score = self._weapon_match_score(g.bbox, other.bbox)
                if score > best_iou:
                    best_iou = score
                    best_knife = other
            if best_knife is not None and best_iou >= WEAKNESS_KNIFE_IOU:
                best_knife.confidence = round(
                    max(best_knife.confidence, g.confidence), 3
                )
            else:
                kept.append(g)
        return kept

    @staticmethod
    def _weapon_match_score(gun_box: BBox, knife_box: BBox) -> float:
        """
        Match a gun-model box against a base-model knife box.

        Returns a value >= WEAKNESS_KNIFE_IOU thresholds style matches. Raw IoU
        underestimates the overlap when the gun box encloses the (smaller)
        knife box, so a center-containment test is blended in: if either box's
        center falls inside the other box, the match is treated as strong.
        """
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
            return max(iou, 0.5)
        return iou
