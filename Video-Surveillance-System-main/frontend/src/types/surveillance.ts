export interface BBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface Detection {
  class_name: string;
  confidence: number;
  bbox: BBox;
  center_x: number;
  center_y: number;
}

export interface TrackedObject {
  track_id: number;
  class_name: string;
  confidence: number;
  bbox: BBox;
  center_x: number;
  center_y: number;
  duration_seconds: number;
  first_seen?: string;
}

export interface FrameMetadata {
  detections: Detection[];
  tracked_objects: TrackedObject[];
  object_count: number;
  fps: number;
  frame_number: number;
}

export type AlertType = 'loitering' | 'intrusion' | 'unattended_object' | 'suspicious_activity';
export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface TripleLock {
  lock1_detection: boolean;
  lock2_behavior: boolean;
  lock3_face_recognition: boolean | string;
}

export interface Alert {
  id: string;
  timestamp: string;
  alert_type: AlertType;
  severity: AlertSeverity;
  message: string;
  snapshot_url: string | null;
  objects_involved: string[];
  object_id?: string | null;
  duration_seconds?: number;
  confidence?: number;
  triple_lock: TripleLock;
}

export interface AlertsResponse {
  alerts: Alert[];
  total: number;
}

export interface SystemStatus {
  is_running: boolean;
  fps: number;
  frame_count: number;
  object_count: number;
  alert_count: number;
  uptime_seconds: number;
  video_source: string | null;
  init_error?: string;
}

export interface UploadResponse {
  message: string;
  filename: string;
  size_mb: number;
}

export interface ConfigResponse {
  yolo_model: string;
  yolo_confidence: number;
  loitering_threshold_seconds: number;
  intrusion_zone: [number, number, number, number];
  unattended_object_seconds: number;
  alert_cooldown_seconds: number;
}
