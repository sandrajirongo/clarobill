'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

// Refreshes the reports list every 6s while at least one row is in the
// "generating" state. Mounted only when the server-rendered page detects a
// pending row, so the polling cost is bounded by how long generation takes
// (usually 1-3 minutes). Caps total polling at 5 minutes to avoid runaway
// refreshes if the engine never finishes.
export function ReportsAutoRefresh(): null {
  const router = useRouter();

  useEffect(() => {
    let ticks = 0;
    const maxTicks = 50; // 50 × 6s = 5 minutes
    const interval = setInterval(() => {
      ticks += 1;
      if (ticks > maxTicks) {
        clearInterval(interval);
        return;
      }
      router.refresh();
    }, 6000);
    return () => clearInterval(interval);
  }, [router]);

  return null;
}
