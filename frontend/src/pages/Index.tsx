import { useCallback, useEffect, useRef, useState } from 'react';
import { StatsBar } from '@/components/surveillance/StatsBar';
import { VideoFeed, type DashboardVideoState } from '@/components/surveillance/VideoFeed';
import { DetectedObjects } from '@/components/surveillance/DetectedObjects';
import { AlertsPanel } from '@/components/surveillance/AlertsPanel';
import { ErrorModal } from '@/components/surveillance/ErrorModal';
import { ThemeToggle } from '@/components/ThemeToggle';
import { usePolling } from '@/hooks/usePolling';
import { useTheme } from '@/hooks/useTheme';
import { fetchStatus, fetchFrame, fetchAlerts, stopProcessing, startProcessing } from '@/lib/api';
import { Shield, Square, Play } from 'lucide-react';

const Index = () => {
  const { theme, toggleTheme } = useTheme();
  const [videoUiState, setVideoUiState] = useState<DashboardVideoState>('IDLE');
  const wasRunningRef = useRef(false);

  const { data: status, loading: statusLoading } = usePolling(useCallback(() => fetchStatus(), []));
  const isRunning = status?.is_running ?? false;
  const hasVideoSource = !!status?.video_source;
  const { data: frame, loading: frameLoading } = usePolling(useCallback(() => fetchFrame(), []), true);
  const { data: alertsData, refetch: refetchAlerts, loading: alertsLoading } = usePolling(useCallback(() => fetchAlerts(), []), true);

  useEffect(() => {
    const running = status?.is_running ?? false;
    const sourceAvailable = !!status?.video_source;

    if (running) {
      setVideoUiState('RUNNING');
      wasRunningRef.current = true;
      return;
    }

    if (videoUiState === 'UPLOADING') {
      return;
    }

    if (videoUiState === 'PROCESSING' && !running) {
      return;
    }

    if (!sourceAvailable) {
      setVideoUiState('IDLE');
      wasRunningRef.current = false;
      return;
    }

    if (wasRunningRef.current || (status?.frame_count ?? 0) > 0) {
      setVideoUiState('FINISHED');
      return;
    }

    if (videoUiState !== 'PROCESSING') {
      setVideoUiState('IDLE');
    }
  }, [status?.is_running, status?.video_source, status?.frame_count, videoUiState]);

  const handleStop = async () => {
    try {
      await stopProcessing();
      setVideoUiState('FINISHED');
    } catch {
      /* polled status will update */
    }
  };

  const handleResume = async () => {
    try {
      setVideoUiState('PROCESSING');
      await startProcessing();
    } catch {
      /* polled status will update */
    }
  };

  const handleUploadStart = () => {
    wasRunningRef.current = false;
    setVideoUiState('UPLOADING');
  };

  const handleUploadSuccess = () => {
    setVideoUiState('PROCESSING');
  };

  const handleUploadError = () => {
    setVideoUiState('IDLE');
  };

  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      {/* Background gradient effects */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-primary/3 rounded-full blur-3xl" />
      </div>

      {/* Init Error Modal */}
      {status?.init_error && <ErrorModal error={status.init_error} />}

      <div className="relative z-10 flex flex-col h-screen p-4 gap-4">
        {/* Header */}
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <Shield size={20} className="text-primary" />
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-wider uppercase text-foreground">Security Command Center</h1>
              <p className="text-[10px] text-muted-foreground tracking-widest uppercase">AI Surveillance System v2.0</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {isRunning && (
              <button
                onClick={handleStop}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-destructive/20 text-destructive text-xs font-semibold hover:bg-destructive/30 transition-colors"
              >
                <Square size={12} /> Stop
              </button>
            )}
            {!isRunning && hasVideoSource && videoUiState !== 'UPLOADING' && (
              <button
                onClick={handleResume}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-success/20 text-success text-xs font-semibold hover:bg-success/30 transition-colors"
              >
                <Play size={12} /> Resume
              </button>
            )}
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
            <div className="font-mono text-xs text-muted-foreground">
              {new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
              {' '}
              <span className="text-primary">{new Date().toLocaleTimeString('en-US', { hour12: false })}</span>
            </div>
          </div>
        </header>

        {/* Stats Bar */}
        <StatsBar status={status} loading={statusLoading} />

        {/* Main Grid */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4 min-h-0">
          {/* Center: Video */}
          <div className="flex flex-col min-h-0">
            <div className="flex-1 min-h-0">
              <VideoFeed
                uiState={videoUiState}
                status={status}
                onUploadStart={handleUploadStart}
                onUploadSuccess={handleUploadSuccess}
                onUploadError={handleUploadError}
              />
            </div>
          </div>

          {/* Right Sidebar: Detected Objects & Alerts */}
          <div className="hidden lg:flex flex-col gap-4 min-h-0">
            <div className="flex-1 min-h-0 overflow-hidden glass-panel p-4">
              <DetectedObjects
                frame={frame}
                loading={frameLoading && (videoUiState === 'PROCESSING' || videoUiState === 'RUNNING')}
              />
            </div>
            <div className="flex-1 min-h-0 overflow-hidden glass-panel p-4">
              <AlertsPanel
                alertsData={alertsData}
                onRefresh={refetchAlerts}
                loading={alertsLoading && videoUiState !== 'IDLE'}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Index;
