'use client';

import { useState } from 'react';

interface DownloadButtonProps {
  billId: string;
  type: 'report' | 'dispute-letter';
  label: string;
  className?: string;
}

export function DownloadButton({ billId, type, label, className }: DownloadButtonProps): JSX.Element {
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  async function handleDownload(): Promise<void> {
    setLoading(true);
    setFailed(false);
    try {
      const res = await fetch(`/api/bills/${billId}/download?type=${type}`);
      if (!res.ok) {
        setFailed(true);
        return;
      }
      const { url } = await res.json() as { url: string };
      // window.open() is blocked by popup blockers when called from an async callback
      // (user gesture context is lost after the fetch). A programmatic <a> click
      // navigates as a link and is not subject to the same restriction.
      const a = document.createElement('a');
      a.href = url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button onClick={handleDownload} disabled={loading} className={className}>
      {loading ? 'Generating link…' : failed ? 'Try again' : label}
    </button>
  );
}
