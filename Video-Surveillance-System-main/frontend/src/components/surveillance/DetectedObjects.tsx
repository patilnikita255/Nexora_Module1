import { Crosshair, Radar } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { FrameMetadata, TrackedObject } from '@/types/surveillance';

interface DetectedObjectsProps {
  frame: FrameMetadata | null;
  loading?: boolean;
}

const classEmojis: Record<string, string> = {
  person: '🧑',
  backpack: '🎒',
  umbrella: '☂️',
  handbag: '👜',
  suitcase: '🧳',
  bottle: '🍶',
  cup: '☕',
  knife: '🔪',
  laptop: '💻',
  'cell phone': '📱',
};

const classAccentColors: Record<string, { text: string; bg: string; bar: string }> = {
  person:       { text: 'text-success',           bg: 'bg-success/10',      bar: 'bg-success' },
  backpack:     { text: 'text-warning',            bg: 'bg-warning/10',      bar: 'bg-warning' },
  handbag:      { text: 'text-warning',            bg: 'bg-warning/10',      bar: 'bg-warning' },
  suitcase:     { text: 'text-warning',            bg: 'bg-warning/10',      bar: 'bg-warning' },
  knife:        { text: 'text-destructive',        bg: 'bg-destructive/10',  bar: 'bg-destructive' },
  laptop:       { text: 'text-primary',            bg: 'bg-primary/10',      bar: 'bg-primary' },
  'cell phone': { text: 'text-primary',            bg: 'bg-primary/10',      bar: 'bg-primary' },
  umbrella:     { text: 'text-muted-foreground',   bg: 'bg-muted/50',        bar: 'bg-muted-foreground' },
  bottle:       { text: 'text-muted-foreground',   bg: 'bg-muted/50',        bar: 'bg-muted-foreground' },
  cup:          { text: 'text-muted-foreground',   bg: 'bg-muted/50',        bar: 'bg-muted-foreground' },
};

const defaultAccent = { text: 'text-foreground', bg: 'bg-muted/50', bar: 'bg-foreground' };

function groupByClass(objects: TrackedObject[]): Record<string, TrackedObject[]> {
  return objects.reduce((acc, obj) => {
    const key = obj.class_name;
    if (!acc[key]) acc[key] = [];
    acc[key].push(obj);
    return acc;
  }, {} as Record<string, TrackedObject[]>);
}

function ConfidenceBar({ confidence, barColor }: { confidence: number; barColor: string }) {
  const pct = Math.round(confidence * 100);
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-1.5 bg-muted/50 rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className={`h-full rounded-full ${barColor}`}
        />
      </div>
      <span className="font-mono text-[10px] text-muted-foreground w-8 text-right">{pct}%</span>
    </div>
  );
}

export function DetectedObjects({ frame, loading = false }: DetectedObjectsProps) {
  const objects = frame?.tracked_objects ?? [];
  const grouped = groupByClass(objects);
  const classNames = Object.keys(grouped);

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-primary/15 flex items-center justify-center">
            <Radar size={14} className="text-primary" />
          </div>
          <h2 className="text-xs uppercase tracking-[0.15em] text-muted-foreground font-semibold">Tracked Objects</h2>
        </div>
        <span className="font-mono text-xs bg-primary/10 text-primary px-2.5 py-1 rounded-full font-bold">{objects.length}</span>
      </div>

      {loading ? (
        <div className="flex-1 space-y-2.5 pr-1">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="rounded-lg border border-border/60 p-2.5 animate-pulse bg-muted/20">
              <div className="h-3 w-24 bg-muted/40 rounded mb-2" />
              <div className="h-2 w-full bg-muted/30 rounded" />
            </div>
          ))}
        </div>
      ) : objects.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-muted-foreground">
            <div className="w-16 h-16 rounded-2xl bg-muted/30 flex items-center justify-center mx-auto mb-3">
              <Crosshair size={28} className="opacity-30" />
            </div>
            <p className="text-xs font-medium">No objects detected</p>
            <p className="text-[10px] mt-1 opacity-60">Waiting for video feed</p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto scrollbar-thin space-y-4 pr-1">
          <AnimatePresence>
            {classNames.map((cls) => {
              const accent = classAccentColors[cls] ?? defaultAccent;
              return (
                <motion.div
                  key={cls}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-base leading-none">{classEmojis[cls] ?? '📦'}</span>
                    <span className={`text-[11px] uppercase tracking-wider font-semibold ${accent.text}`}>
                      {cls}
                    </span>
                    <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded-full ${accent.bg} ${accent.text}`}>
                      {grouped[cls].length}
                    </span>
                  </div>
                  <div className="space-y-1.5 ml-6">
                    {grouped[cls].map((obj) => (
                      <motion.div
                        key={obj.track_id}
                        layout
                        className={`${accent.bg} rounded-lg p-2.5 border border-transparent hover:border-border transition-colors`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="font-mono text-[11px] text-foreground font-semibold">ID:{obj.track_id}</span>
                          <span className="font-mono text-[10px] text-muted-foreground bg-muted/40 px-1.5 py-0.5 rounded">
                            {obj.duration_seconds.toFixed(1)}s
                          </span>
                        </div>
                        <ConfidenceBar confidence={obj.confidence} barColor={accent.bar} />
                      </motion.div>
                    ))}
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}

    </div>
  );
}
