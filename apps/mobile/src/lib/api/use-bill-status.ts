import { useEffect, useRef, useState } from 'react';
import type { BillStatus } from '@clarobill/shared';
import { getBillStatus } from './bills';

const TERMINAL_STATUSES: BillStatus[] = ['complete', 'failed'];
const DEFAULT_INTERVAL_MS = 3000;

type UseBillStatusResult = {
  status: BillStatus | null;
  error: string | null;
  isPolling: boolean;
  isTerminal: boolean;
};

/**
 * Polls `GET /api/bills/[billId]` every `intervalMs` ms until the bill
 * reaches a terminal status (`complete` or `failed`).
 *
 * Pass `billId = null` to disable polling — useful when nothing is in flight.
 *
 * Cleans up the interval on unmount and on billId change so we never leave
 * a zombie poller running. Failed fetches keep the loop alive (engine may be
 * temporarily unavailable); the most recent error is surfaced via `error`.
 */
export function useBillStatus(
  billId: string | null,
  intervalMs: number = DEFAULT_INTERVAL_MS,
): UseBillStatusResult {
  const [status, setStatus] = useState<BillStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  // Track the current billId in a ref so the interval can detect changes
  // without restarting after every state update.
  const billIdRef = useRef(billId);
  billIdRef.current = billId;

  useEffect(() => {
    if (!billId) {
      setStatus(null);
      setError(null);
      setIsPolling(false);
      return;
    }

    setStatus(null);
    setError(null);
    setIsPolling(true);

    let cancelled = false;

    const tick = async () => {
      if (cancelled || billIdRef.current !== billId) return;
      try {
        const result = await getBillStatus(billId);
        if (cancelled || billIdRef.current !== billId) return;
        setStatus(result.status);
        setError(null);
        if (TERMINAL_STATUSES.includes(result.status)) {
          setIsPolling(false);
          clearInterval(intervalHandle);
        }
      } catch (e) {
        if (cancelled || billIdRef.current !== billId) return;
        setError(e instanceof Error ? e.message : String(e));
        // Keep polling — transient failures shouldn't end the watch.
      }
    };

    void tick(); // fire immediately on mount
    const intervalHandle = setInterval(tick, intervalMs);

    return () => {
      cancelled = true;
      clearInterval(intervalHandle);
    };
  }, [billId, intervalMs]);

  return {
    status,
    error,
    isPolling,
    isTerminal: status !== null && TERMINAL_STATUSES.includes(status),
  };
}
