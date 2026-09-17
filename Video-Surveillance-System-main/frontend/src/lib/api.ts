import type { SystemStatus, FrameMetadata, AlertsResponse, ConfigResponse } from '@/types/surveillance';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const getVideoFeedUrl = () => `${API_URL}/api/video_feed`;

/** snapshot_url already includes /api/snapshots/ prefix, just prepend base */
export const getSnapshotUrl = (snapshotUrl: string) => `${API_URL}${snapshotUrl}`;

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const fetchStatus = () => fetchJson<SystemStatus>('/api/status');
export const fetchFrame = () => fetchJson<FrameMetadata>('/api/frame');
export const fetchAlerts = (limit = 50) => fetchJson<AlertsResponse>(`/api/alerts?limit=${limit}`);
export const fetchConfig = () => fetchJson<ConfigResponse>('/api/config');

export async function uploadVideo(file: File) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_URL}/api/upload`, { method: 'POST', body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || 'Upload failed');
  }
  return res.json();
}

export async function stopProcessing() {
  const res = await fetch(`${API_URL}/api/stop`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to stop');
  return res.json();
}

export async function startProcessing(source?: string) {
  const url = source
    ? `${API_URL}/api/start?source=${encodeURIComponent(source)}`
    : `${API_URL}/api/start`;
  const res = await fetch(url, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to start');
  return res.json();
}

export async function clearAlerts() {
  const res = await fetch(`${API_URL}/api/alerts`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to clear alerts');
  return res.json();
}
