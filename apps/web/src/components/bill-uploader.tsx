'use client';

import { useRef, useState } from 'react';
import { useBillUpload } from '@/lib/hooks/use-bill-upload';
import { useRouter } from 'next/navigation';
import s from '@/app/dashboard/dashboard.module.css';
import { COUNTIES_BY_STATE } from '@/lib/utils/county-data';

// CMS locality states — matches the state names used in cms_county_locality.
// The engine normalises to uppercase; we pass title-case for readability.
const US_STATES = [
  'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
  'Connecticut', 'Delaware', 'District Of Columbia', 'Florida', 'Georgia',
  'Hawaii/Guam', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas',
  'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan',
  'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
  'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina',
  'North Dakota', 'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania', 'Puerto Rico',
  'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas',
  'Utah', 'Vermont', 'Virgin Islands', 'Virginia', 'Washington',
  'West Virginia', 'Wisconsin', 'Wyoming',
];

export function BillUploader(): JSX.Element {
  const { uploadState, upload, reset } = useBillUpload();
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const [selectedState, setSelectedState] = useState<string>('');
  const [selectedCounty, setSelectedCounty] = useState<string>('');

  const counties = selectedState ? (COUNTIES_BY_STATE[selectedState] ?? []) : [];

  function handleStateChange(state: string): void {
    setSelectedState(state);
    setSelectedCounty(''); // reset county when state changes
  }

  if (uploadState.status === 'complete') {
    router.push(`/dashboard/bills/${uploadState.billId}`);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>): void {
    const file = e.target.files?.[0];
    if (file) upload(file, selectedState || null, selectedCounty || null);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>): void {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) upload(file, selectedState || null, selectedCounty || null);
  }

  const isActive = uploadState.status !== 'idle' && uploadState.status !== 'error';

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      className={s.uploadZone}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,image/jpeg,image/png"
        style={{ display: 'none' }}
        onChange={handleFileChange}
        disabled={isActive}
      />

      {uploadState.status === 'idle' && (
        <>
          <div className={s.geoRow}>
            <div className={s.geoField}>
              <label className={s.geoLabel}>State</label>
              <select
                className={s.geoSelect}
                value={selectedState}
                onChange={(e) => handleStateChange(e.target.value)}
              >
                <option value="">Select state…</option>
                {US_STATES.map((st) => (
                  <option key={st} value={st}>{st}</option>
                ))}
              </select>
            </div>
            {counties.length > 0 && (
              <div className={s.geoField}>
                <label className={s.geoLabel}>County <span style={{ fontWeight: 400, textTransform: 'none', fontSize: '.68rem' }}>(optional)</span></label>
                <select
                  className={s.geoSelect}
                  value={selectedCounty}
                  onChange={(e) => setSelectedCounty(e.target.value)}
                >
                  <option value="">Select county…</option>
                  {counties.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <div className={s.uploadIcon}>📄</div>
          <p className={s.uploadLabel}>Drop your bill here, or</p>
          <button onClick={() => inputRef.current?.click()} className={s.uploadBtn}>
            Choose file
          </button>
          <p className={s.uploadHint}>PDF, JPEG, or PNG — max 20MB</p>
        </>
      )}

      {uploadState.status === 'validating' && (
        <p className={s.uploadStatusText}>Checking file…</p>
      )}

      {uploadState.status === 'uploading' && (
        <p className={s.uploadStatusText}>Uploading… {uploadState.progress}%</p>
      )}

      {uploadState.status === 'analyzing' && (
        <>
          <div className={s.uploadSpinner} />
          <p className={s.uploadStatusText}>Analyzing your bill — this takes about 30 seconds…</p>
        </>
      )}

      {uploadState.status === 'error' && (
        <>
          <p className={s.uploadError}>{uploadState.error.detail}</p>
          <button onClick={reset} className={s.retryBtn}>Try again</button>
        </>
      )}
    </div>
  );
}
