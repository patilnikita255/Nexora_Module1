import { useEffect, useState } from 'react';
import { Shield, ShieldAlert, ShieldCheck, Trash2, Eye, Clock, ShieldX, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { Alert, AlertsResponse, TripleLock } from '@/types/surveillance';
import { clearAlerts, getSnapshotUrl } from '@/lib/api';

interface AlertsPanelProps {
  alertsData: AlertsResponse | null;
  onRefresh: () => void;
  loading?: boolean;
}

const severityConfig: Record<string, {
  border: string;
  bg: string;
  text: string;
  icon: React.ReactNode;
  glow: string;
}> = {
  low: {
    border: 'border-l-success',
    bg: 'bg-success/[0.06]',
    text: 'text-success',
    icon: <ShieldCheck size={14} />,
    glow: '',
  },
  medium: {
    border: 'border-l-warning',
    bg: 'bg-warning/[0.06]',
    text: 'text-warning',
    icon: <Shield size={14} />,
    glow: '',
  },
  high: {
    border: 'border-l-orange-400',
    bg: 'bg-orange-500/[0.08]',
    text: 'text-orange-400',
    icon: <ShieldAlert size={14} />,
    glow: '',
  },
  critical: {
    border: 'border-l-critical',
    bg: 'bg-destructive/[0.08]',
    text: 'text-destructive',
    icon: <ShieldX size={14} />,
    glow: 'shadow-[0_0_12px_hsl(var(--critical)/0.15)]',
  },
};

const alertTypeLabels: Record<string, string> = {
  loitering: 'Loitering',
  intrusion: 'Intrusion',
  unattended_object: 'Unattended Object',
  suspicious_activity: 'Suspicious Activity',
};

function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 10) return 'Just now';
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function TripleLockDisplay({ status }: { status: TripleLock }) {
  const locks = [
    { key: 'Detection', label: 'Detection', verified: status.lock1_detection === true },
    { key: 'Behavior', label: 'Behavior', verified: status.lock2_behavior === true },
    {
      key: 'Face',
      label: 'Face',
      verified: typeof status.lock3_face_recognition === 'boolean' ? status.lock3_face_recognition : false,
    },
  ];

  return (
    <div className="flex flex-wrap gap-1.5">
      {locks.map((l) => (
        <div
          key={l.key}
          className={`flex items-center gap-1 px-2 py-0.5 rounded text-[9px] font-mono transition-colors ${
            l.verified
              ? 'bg-success/15 text-success border border-success/20'
              : 'bg-muted/30 text-muted-foreground border border-border'
          }`}
          title={`${l.key}: ${l.verified ? 'Verified' : 'Pending'}`}
        >
          <span>{l.verified ? '✔' : '○'}</span>
          <span>{l.label}</span>
        </div>
      ))}
    </div>
  );
}

function AlertCard({ alert, index, isNewest }: { alert: Alert; index: number; isNewest: boolean }) {
  const [showSnapshot, setShowSnapshot] = useState(false);
  const cfg = severityConfig[alert.severity] ?? severityConfig.low;
  const confidencePct = Math.round((alert.confidence ?? 0) * 100);

  return (
    <motion.div
      initial={{ opacity: 0, x: -15, y: 5 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      exit={{ opacity: 0, x: 15 }}
      transition={{ duration: 0.3, delay: index * 0.04 }}
      className={`${cfg.bg} ${cfg.border} ${cfg.glow} border-l-[3px] rounded-lg p-3 space-y-2.5 hover:bg-muted/20 transition-colors ${isNewest ? 'ring-1 ring-primary/40' : ''}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`${cfg.text} shrink-0`}>{cfg.icon}</span>
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${cfg.bg} ${cfg.text} border border-current/10`}>
            {alert.severity}
          </span>
          <span className="text-xs font-semibold text-foreground">
            {alertTypeLabels[alert.alert_type] ?? alert.alert_type}
          </span>
        </div>
        <span className="font-mono text-[10px] text-muted-foreground flex items-center gap-1 shrink-0">
          <Clock size={9} />
          {relativeTime(alert.timestamp)}
        </span>
      </div>

      <p className="text-[11px] text-muted-foreground leading-relaxed">{alert.message}</p>

      <div className="grid grid-cols-3 gap-2 text-[10px] font-mono">
        <div className="bg-muted/30 rounded px-2 py-1">
          <span className="text-muted-foreground">OBJ</span>
          <span className="ml-1 text-foreground">{alert.object_id ?? '--'}</span>
        </div>
        <div className="bg-muted/30 rounded px-2 py-1">
          <span className="text-muted-foreground">DUR</span>
          <span className="ml-1 text-foreground">{(alert.duration_seconds ?? 0).toFixed(1)}s</span>
        </div>
        <div className="bg-muted/30 rounded px-2 py-1">
          <span className="text-muted-foreground">CONF</span>
          <span className="ml-1 text-foreground">{confidencePct}%</span>
        </div>
      </div>

      {alert.objects_involved.length > 0 && (
        <div className="flex gap-1 flex-wrap">
          {alert.objects_involved.map((oid) => (
            <span key={oid} className="text-[9px] font-mono bg-primary/10 text-primary px-1.5 py-0.5 rounded border border-primary/15">
              ID:{oid}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between">
        <TripleLockDisplay status={alert.triple_lock} />
        {alert.snapshot_url && (
          <button
            onClick={() => setShowSnapshot(!showSnapshot)}
            className="text-[10px] text-primary flex items-center gap-1 hover:text-primary/80 transition-colors bg-primary/10 px-2 py-0.5 rounded"
          >
            <Eye size={10} /> {showSnapshot ? 'Hide' : 'View'}
          </button>
        )}
      </div>

      <AnimatePresence>
        {showSnapshot && alert.snapshot_url && (
          <motion.img
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            src={getSnapshotUrl(alert.snapshot_url)}
            alt="Incident snapshot"
            className="w-full rounded-md border border-border mt-1"
          />
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function AlertsPanel({ alertsData, onRefresh, loading = false }: AlertsPanelProps) {
  const [clearing, setClearing] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    if (!alertsData) return;

    setAlerts((prev) => {
      const prevIds = new Set(prev.map((alert) => alert.id));
      const incoming = alertsData.alerts ?? [];
      const freshAlerts = incoming.filter((alert) => !prevIds.has(alert.id));

      if (freshAlerts.length === 0) {
        return prev;
      }

      return [...freshAlerts, ...prev].slice(0, 500);
    });
  }, [alertsData]);

  const handleClear = async () => {
    setClearing(true);
    try {
      await clearAlerts();
      setAlerts([]);
      onRefresh();
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-destructive/15 flex items-center justify-center">
            <AlertCircle size={14} className="text-destructive" />
          </div>
          <h2 className="text-xs uppercase tracking-[0.15em] text-muted-foreground font-semibold">Security Alerts</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs bg-primary/10 text-primary px-2.5 py-1 rounded-full font-bold">
            {alerts.length}
          </span>
          {alerts.length > 0 && (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={handleClear}
              disabled={clearing}
              className="text-[10px] text-destructive hover:text-destructive/80 flex items-center gap-1 disabled:opacity-50 bg-destructive/10 px-2 py-1 rounded-lg border border-destructive/15 transition-colors"
            >
              <Trash2 size={10} /> Clear
            </motion.button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin space-y-2 pr-1">
        <AnimatePresence>
          {loading && alerts.length === 0 ? (
            <div className="space-y-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="rounded-lg border border-border/60 p-3 animate-pulse bg-muted/20">
                  <div className="h-3 w-24 bg-muted/40 rounded mb-2" />
                  <div className="h-2 w-full bg-muted/30 rounded mb-1" />
                  <div className="h-2 w-3/4 bg-muted/30 rounded" />
                </div>
              ))}
            </div>
          ) : alerts.length === 0 ? (
            <div className="flex-1 flex items-center justify-center h-32">
              <div className="text-center text-muted-foreground">
                <div className="w-12 h-12 rounded-xl bg-muted/30 flex items-center justify-center mx-auto mb-2">
                  <Shield size={20} className="opacity-30" />
                </div>
                <p className="text-xs font-medium">No incidents recorded</p>
                <p className="text-[10px] mt-0.5 opacity-60">Alerts will appear here</p>
              </div>
            </div>
          ) : (
            alerts.map((alert, i) => (
              <AlertCard
                key={alert.id}
                alert={alert}
                index={i}
                isNewest={i === 0}
              />
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
