import { useState, useCallback, useEffect, useRef } from 'react';
import { Loader2, CloudUpload, FileVideo, RotateCcw } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { getVideoFeedUrl, uploadVideo } from '@/lib/api';
import type { SystemStatus } from '@/types/surveillance';

export type DashboardVideoState = 'IDLE' | 'UPLOADING' | 'PROCESSING' | 'RUNNING' | 'FINISHED';

interface VideoFeedProps {
  uiState: DashboardVideoState;
  status: SystemStatus | null;
  onUploadStart: () => void;
  onUploadSuccess: () => void;
  onUploadError: (message: string) => void;
}

export function VideoFeed({
  uiState,
  status,
  onUploadStart,
  onUploadSuccess,
  onUploadError,
}: VideoFeedProps) {
  const [dragOver, setDragOver] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [streamReady, setStreamReady] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const streamUrl = getVideoFeedUrl();

  useEffect(() => {
    if (uiState !== 'RUNNING') {
      setStreamReady(false);
    }
  }, [uiState]);

  useEffect(() => {
    if (uiState !== 'IDLE') return;
    setUploadError(null);
  }, [uiState]);

  const handleFile = useCallback(async (file: File) => {
    setUploadError(null);
    onUploadStart();
    try {
      await uploadVideo(file);
      onUploadSuccess();
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Upload failed';
      setUploadError(message);
      onUploadError(message);
    }
  }, [onUploadError, onUploadStart, onUploadSuccess]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const onFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const renderUploadIdle = () => (
    <motion.div
      animate={dragOver ? { scale: 1.01 } : { scale: 1 }}
      transition={{ type: 'spring', stiffness: 300 }}
      className={`glass-panel-elevated aspect-video lg:aspect-auto lg:h-full flex flex-col items-center justify-center gap-5 transition-all cursor-pointer relative overflow-hidden
        ${dragOver ? 'border-primary/50 glow-blue' : 'border-dashed border-2 border-border'}
        hover:border-primary/30`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      onClick={() => fileInputRef.current?.click()}
    >
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: 'radial-gradient(circle, hsl(var(--foreground)) 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }}
      />

      <div className="flex flex-col items-center gap-4 relative z-10">
        <div className={`w-20 h-20 rounded-2xl flex items-center justify-center transition-all duration-300 ${
          dragOver
            ? 'bg-primary/20 shadow-lg shadow-primary/10'
            : 'bg-muted/50'
        }`}>
          {dragOver ? (
            <FileVideo size={36} className="text-primary" />
          ) : (
            <CloudUpload size={36} className="text-muted-foreground" />
          )}
        </div>
        <div className="text-center">
          <p className="text-foreground font-semibold text-sm md:text-base">
            {dragOver ? 'Drop video file here' : 'Upload Video for Analysis'}
          </p>
          <p className="text-muted-foreground text-xs mt-1.5 max-w-xs">
            Drag & drop or click to browse • MP4, AVI, MKV, MOV, WebM
          </p>
        </div>
        {uploadError && (
          <motion.p
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-destructive text-xs font-mono bg-destructive/10 px-3 py-1.5 rounded-lg border border-destructive/20"
          >
            {uploadError}
          </motion.p>
        )}
      </div>
    </motion.div>
  );

  const renderLoadingState = (title: string, subtitle: string) => (
    <motion.div
      key={title}
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      className="glass-panel-elevated aspect-video lg:aspect-auto lg:h-full flex flex-col items-center justify-center gap-4"
    >
      <div className="w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center relative">
        <Loader2 size={36} className="text-primary animate-spin" />
        <div className="absolute inset-0 rounded-2xl border-2 border-primary/20 animate-pulse" />
      </div>
      <div className="text-center">
        <p className="text-foreground font-semibold text-sm">{title}</p>
        <p className="text-muted-foreground text-xs mt-1">{subtitle}</p>
      </div>
      <div className="w-56 h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-primary to-primary/60 rounded-full animate-shimmer"
          style={{ backgroundSize: '200% 100%', width: '65%' }}
        />
      </div>
    </motion.div>
  );

  const renderRunningState = () => {
    return (
      <div className="glass-panel-elevated glow-blue overflow-hidden relative group h-full flex flex-col">
        {/* Live badge */}
        <div className="absolute top-3 left-3 z-10 flex items-center gap-2 bg-destructive/90 backdrop-blur-sm px-3 py-1 rounded-full shadow-lg shadow-destructive/20">
          <div className="relative">
            <div className="w-2 h-2 rounded-full bg-primary-foreground" />
            <div className="absolute inset-0 w-2 h-2 rounded-full bg-primary-foreground animate-ping" />
          </div>
          <span className="text-[10px] font-bold text-primary-foreground uppercase tracking-wider">Live</span>
        </div>

        {/* Video stats overlay */}
        <div className="absolute top-3 right-3 z-10 bg-background/65 backdrop-blur-sm border border-border/60 rounded-md px-2.5 py-1.5 font-mono text-[10px] text-foreground space-y-0.5">
          <div>FPS: {(status?.fps ?? 0).toFixed(1)}</div>
          <div>OBJ: {status?.object_count ?? 0}</div>
          <div>ALT: {status?.alert_count ?? 0}</div>
        </div>

        {/* Corner decorations */}
        <div className="absolute top-0 left-0 w-8 h-8 border-t-2 border-l-2 border-primary/40 rounded-tl-lg z-10" />
        <div className="absolute top-0 right-0 w-8 h-8 border-t-2 border-r-2 border-primary/40 rounded-tr-lg z-10" />
        <div className="absolute bottom-0 left-0 w-8 h-8 border-b-2 border-l-2 border-primary/40 rounded-bl-lg z-10" />
        <div className="absolute bottom-0 right-0 w-8 h-8 border-b-2 border-r-2 border-primary/40 rounded-br-lg z-10" />

        <div className="flex-1 min-h-0 bg-background/30 flex items-center justify-center overflow-hidden">
          {!streamReady && (
            <div className="absolute inset-0 z-[2] flex items-center justify-center bg-background/60 backdrop-blur-sm">
              <div className="w-[65%] space-y-2 animate-pulse">
                <div className="h-3 bg-muted/60 rounded" />
                <div className="h-3 bg-muted/50 rounded w-5/6" />
                <p className="text-center text-[11px] text-muted-foreground font-mono mt-3">Connecting video stream...</p>
              </div>
            </div>
          )}
          <img
            src={streamUrl}
            alt="Live Camera Feed"
            onLoad={() => setStreamReady(true)}
            onError={() => setStreamReady(false)}
            className={`w-full h-full object-contain transition-opacity duration-500 ${streamReady ? 'opacity-100' : 'opacity-0'}`}
          />
        </div>

        {/* Scan line effect */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden opacity-30">
          <div className="w-full h-0.5 bg-gradient-to-r from-transparent via-primary to-transparent animate-scan-line" />
        </div>

        {/* Bottom gradient overlay */}
        <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-background/60 to-transparent pointer-events-none" />
      </div>
    );
  };

  const renderFinishedState = () => (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel-elevated aspect-video lg:aspect-auto lg:h-full flex flex-col items-center justify-center gap-4 text-center"
    >
      <div className="w-14 h-14 rounded-xl bg-success/10 border border-success/20 flex items-center justify-center">
        <RotateCcw size={24} className="text-success" />
      </div>
      <div>
        <p className="text-foreground font-semibold text-sm">Processing completed</p>
        <p className="text-muted-foreground text-xs mt-1">
          Upload a new video to run another analysis session.
        </p>
      </div>
      <button
        onClick={() => fileInputRef.current?.click()}
        className="px-4 py-2 rounded-lg bg-primary/15 text-primary text-xs font-semibold border border-primary/20 hover:bg-primary/20 transition-colors"
      >
        Upload New Video
      </button>
    </motion.div>
  );

  return (
    <div className="h-full min-h-0">
      <input
        ref={fileInputRef}
        type="file"
        accept=".mp4,.avi,.mkv,.mov,.webm"
        className="hidden"
        onChange={onFileSelect}
      />

      <AnimatePresence mode="wait">
        {uiState === 'RUNNING' ? (
          <motion.div key="running" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full">
            {renderRunningState()}
          </motion.div>
        ) : uiState === 'UPLOADING' ? (
          <motion.div key="uploading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full">
            {renderLoadingState('Uploading video...', 'Transferring file to backend')}
          </motion.div>
        ) : uiState === 'PROCESSING' ? (
          <motion.div key="processing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full">
            {renderLoadingState('Initializing AI pipeline...', 'Preparing detector, tracker, and behavior engine')}
          </motion.div>
        ) : uiState === 'FINISHED' ? (
          <motion.div key="finished" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full">
            {renderFinishedState()}
          </motion.div>
        ) : (
          <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full">
            {renderUploadIdle()}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
