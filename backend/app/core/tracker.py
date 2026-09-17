"""
Simple centroid-based object tracker.

Assigns persistent IDs to detected objects across frames
using Euclidean distance matching between centroids.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Dict, List, Tuple

import numpy as np

from app.models.schemas import Detection, TrackedObject, BBox


class SimpleTracker:
    """Centroid-based multi-object tracker."""

    def __init__(self, max_disappeared: int = 45, max_distance: float = 110.0) -> None:
        """
        Args:
            max_disappeared: Frames before a track is removed.
            max_distance: Max Euclidean distance for centroid matching.
        """
        self.next_id = 0
        self.objects: OrderedDict[int, Tuple[int, int]] = OrderedDict()
        self.disappeared: Dict[int, int] = {}
        self.class_names: Dict[int, str] = {}
        self.confidences: Dict[int, float] = {}
        self.bboxes: Dict[int, BBox] = {}
        self.first_seen: Dict[int, float] = {}
        self.last_seen: Dict[int, float] = {}
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance

    def _register(self, centroid: Tuple[int, int], detection: Detection) -> int:
        """Register a new object with a unique ID."""
        obj_id = self.next_id
        self.objects[obj_id] = centroid
        self.disappeared[obj_id] = 0
        self.class_names[obj_id] = detection.class_name
        self.confidences[obj_id] = detection.confidence
        self.bboxes[obj_id] = detection.bbox
        now = time.time()
        self.first_seen[obj_id] = now
        self.last_seen[obj_id] = now
        self.next_id += 1
        return obj_id

    def _deregister(self, obj_id: int) -> None:
        """Remove a tracked object."""
        for store in (
            self.objects, self.disappeared, self.class_names,
            self.confidences, self.bboxes, self.first_seen, self.last_seen,
        ):
            store.pop(obj_id, None)

    def update(self, detections: List[Detection]) -> List[TrackedObject]:
        """
        Update tracker with new detections and return tracked objects.

        Args:
            detections: List of detections from current frame.

        Returns:
            List of TrackedObject with persistent IDs and duration info.
        """
        now = time.time()

        # If no detections, mark all existing as disappeared
        if len(detections) == 0:
            for obj_id in list(self.disappeared.keys()):
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > self.max_disappeared:
                    self._deregister(obj_id)
            return self._build_tracked_list(now)

        # Extract centroids from new detections
        input_centroids = []
        for det in detections:
            input_centroids.append((det.center_x, det.center_y))

        # If no existing objects, register all
        if len(self.objects) == 0:
            for i, centroid in enumerate(input_centroids):
                self._register(centroid, detections[i])
            return self._build_tracked_list(now)

        # Match existing objects to new detections via class-aware distance matrix
        obj_ids = list(self.objects.keys())
        obj_centroids = list(self.objects.values())

        # Compute distance matrix
        dist_matrix = np.zeros((len(obj_centroids), len(input_centroids)))
        for i, oc in enumerate(obj_centroids):
            for j, ic in enumerate(input_centroids):
                dist_matrix[i, j] = np.sqrt(
                    (oc[0] - ic[0]) ** 2 + (oc[1] - ic[1]) ** 2
                )

        # Greedy matching across all valid class-consistent pairs.
        candidate_pairs: List[Tuple[float, int, int]] = []
        for row, obj_id in enumerate(obj_ids):
            obj_class = self.class_names.get(obj_id)
            for col, det in enumerate(detections):
                if obj_class != det.class_name:
                    continue
                distance = dist_matrix[row, col]
                if distance <= self.max_distance:
                    candidate_pairs.append((distance, row, col))

        candidate_pairs.sort(key=lambda x: x[0])
        used_rows = set()
        used_cols = set()

        for _, row, col in candidate_pairs:
            if row in used_rows or col in used_cols:
                continue

            obj_id = obj_ids[row]
            self.objects[obj_id] = input_centroids[col]
            self.disappeared[obj_id] = 0
            self.class_names[obj_id] = detections[col].class_name
            self.confidences[obj_id] = detections[col].confidence
            self.bboxes[obj_id] = detections[col].bbox
            self.last_seen[obj_id] = now

            used_rows.add(row)
            used_cols.add(col)

        # Handle unmatched existing objects
        unused_rows = set(range(len(obj_centroids))) - used_rows
        for row in unused_rows:
            obj_id = obj_ids[row]
            self.disappeared[obj_id] += 1
            if self.disappeared[obj_id] > self.max_disappeared:
                self._deregister(obj_id)

        # Register unmatched new detections
        unused_cols = set(range(len(input_centroids))) - used_cols
        for col in unused_cols:
            self._register(input_centroids[col], detections[col])

        return self._build_tracked_list(now)

    def _build_tracked_list(self, now: float) -> List[TrackedObject]:
        """Build list of currently tracked objects."""
        tracked = []
        for obj_id in self.objects:
            duration = now - self.first_seen.get(obj_id, now)
            tracked.append(
                TrackedObject(
                    track_id=obj_id,
                    class_name=self.class_names.get(obj_id, "unknown"),
                    confidence=self.confidences.get(obj_id, 0.0),
                    bbox=self.bboxes.get(obj_id, BBox(x1=0, y1=0, x2=0, y2=0)),
                    center_x=self.objects[obj_id][0],
                    center_y=self.objects[obj_id][1],
                    duration_seconds=round(duration, 1),
                )
            )
        return tracked

    def reset(self) -> None:
        """Clear all tracked objects."""
        self.objects.clear()
        self.disappeared.clear()
        self.class_names.clear()
        self.confidences.clear()
        self.bboxes.clear()
        self.first_seen.clear()
        self.last_seen.clear()
        self.next_id = 0
