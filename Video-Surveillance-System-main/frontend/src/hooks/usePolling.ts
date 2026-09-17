import { useState, useEffect, useCallback, useRef } from 'react';

const POLL_INTERVAL = 4000;

function stableSignature(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function usePolling<T>(fetcher: () => Promise<T>, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(enabled);
  const mountedRef = useRef(true);
  const signatureRef = useRef<string | null>(null);

  const poll = useCallback(async () => {
    try {
      const result = await fetcher();
      if (mountedRef.current) {
        const nextSignature = stableSignature(result);
        if (signatureRef.current !== nextSignature) {
          signatureRef.current = nextSignature;
          setData(result);
        }
        setError(null);
        setLoading(false);
      }
    } catch (e) {
      if (mountedRef.current) {
        // Keep previous data and retry on next poll interval.
        setError(e instanceof Error ? e.message : 'Unknown error');
        setLoading(false);
      }
    }
  }, [fetcher]);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    poll();
    const id = setInterval(poll, POLL_INTERVAL);
    return () => { mountedRef.current = false; clearInterval(id); };
  }, [poll, enabled]);

  return { data, error, loading, refetch: poll };
}
