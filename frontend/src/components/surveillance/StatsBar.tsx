import { Activity, Clock, AlertTriangle, Eye, Cpu, Zap } from 'lucide-react';
import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import type { SystemStatus } from '@/types/surveillance';

interface StatsBarProps {
  status: SystemStatus | null;
  loading: boolean;
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

interface StatProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  accent?: string;
  index: number;
}

function Stat({ icon, label, value, accent, index }: StatProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.06 }}
      className="glass-panel stat-card-glow gradient-border px-4 py-3 flex items-center gap-3 flex-1 min-w-[140px]"
    >
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
        accent === 'success' ? 'bg-success/15 text-success' :
        accent === 'warning' ? 'bg-warning/15 text-warning' :
        accent === 'critical' ? 'bg-destructive/15 text-destructive' :
        'bg-primary/15 text-primary'
      }`}>
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-medium">{label}</p>
        <p className={`font-mono text-base md:text-lg font-bold truncate ${
          accent === 'success' ? 'text-success' :
          accent === 'warning' ? 'text-warning' :
          accent === 'critical' ? 'text-destructive' :
          'text-foreground'
        }`}>
          {value}
        </p>
      </div>
    </motion.div>
  );
}

export function StatsBar({ status, loading }: StatsBarProps) {
  const [localUptime, setLocalUptime] = useState(0);

  useEffect(() => {
    if (status?.uptime_seconds !== undefined) {
      setLocalUptime(Math.floor(status.uptime_seconds));
    }
  }, [status?.uptime_seconds]);

  useEffect(() => {
    if (!status?.is_running) return;
    const interval = setInterval(() => {
      setLocalUptime((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [status?.is_running]);

  if (loading || !status) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-3 lg:gap-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="glass-panel px-4 py-3 min-w-[140px] h-[68px] relative overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-muted/30 to-transparent animate-shimmer"
                   style={{ backgroundSize: '200% 100%' }} />
            </div>
          ))}
        </div>
        <div className="glass-panel px-4 py-3 min-w-[140px] h-[68px] relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-muted/30 to-transparent animate-shimmer"
               style={{ backgroundSize: '200% 100%' }} />
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-3 lg:gap-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          index={0}
          icon={
            <div className="relative">
              <div className={`w-3 h-3 rounded-full ${status.is_running ? 'bg-success' : 'bg-muted-foreground'}`} />
              {status.is_running && (
                <div className="absolute inset-0 w-3 h-3 rounded-full bg-success animate-ping opacity-75" />
              )}
            </div>
          }
          label="System"
          value={status.is_running ? 'ACTIVE' : 'IDLE'}
          accent={status.is_running ? 'success' : undefined}
        />
        <Stat
          index={1}
          icon={<Zap size={18} />}
          label="FPS"
          value={status.fps.toFixed(1)}
          accent="success"
        />
        <Stat
          index={2}
          icon={<Eye size={18} />}
          label="Objects"
          value={String(status.object_count)}
        />
        <Stat
          index={3}
          icon={<AlertTriangle size={18} />}
          label="Alerts"
          value={String(status.alert_count)}
          accent={status.alert_count > 0 ? 'warning' : undefined}
        />
      </div>
      <Stat
        index={4}
        icon={<Clock size={18} />}
        label="Uptime"
        value={formatUptime(localUptime)}
      />
    </div>
  );
}
