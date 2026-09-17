import { ServerCrash } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface ErrorModalProps {
  error: string;
}

export function ErrorModal({ error }: ErrorModalProps) {
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-destructive/15 backdrop-blur-lg"
      >
        <motion.div
          initial={{ scale: 0.9, opacity: 0, y: 20 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.9, opacity: 0, y: 20 }}
          transition={{ type: 'spring', stiffness: 300, damping: 25 }}
          className="glass-panel-elevated glow-red max-w-lg w-full mx-4 p-8 text-center space-y-5 border-destructive/30"
        >
          <div className="w-20 h-20 rounded-2xl bg-destructive/15 flex items-center justify-center mx-auto border border-destructive/20">
            <ServerCrash size={36} className="text-destructive" />
          </div>

          <div>
            <h1 className="text-lg font-bold text-destructive uppercase tracking-wider">
              AI Engine Failed to Initialize
            </h1>
            <p className="text-sm text-muted-foreground mt-2">
              The AI model failed to load. The dashboard is blocked until this issue is resolved.
            </p>
          </div>

          <pre className="text-left text-[11px] font-mono text-destructive/80 bg-destructive/[0.05] rounded-lg p-4 max-h-48 overflow-auto scrollbar-thin whitespace-pre-wrap break-all border border-destructive/10">
            {error}
          </pre>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
