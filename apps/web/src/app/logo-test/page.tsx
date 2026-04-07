// Temporary page to preview logo concepts — delete before launch

export default function LogoTestPage(): JSX.Element {
  return (
    <div className="min-h-screen bg-white p-16 font-[family-name:var(--font-geist-sans)]">
      <p className="text-sm text-gray-400 mb-16 uppercase tracking-widest">Logo concepts — delete this page before launch</p>

      <div className="space-y-20">

        {/* Concept A — Wordmark with teal accent on "Claro" */}
        <LogoSection label="A — Wordmark, split color">
          <div className="flex items-center gap-0">
            <span className="text-3xl font-bold text-teal-600">Claro</span>
            <span className="text-3xl font-bold text-gray-900">bill</span>
          </div>
          <div className="flex items-center gap-0 mt-4">
            <span className="text-xl font-bold text-teal-600">Claro</span>
            <span className="text-xl font-bold text-gray-900">bill</span>
          </div>
          <div className="flex items-center gap-0 mt-4">
            <span className="text-sm font-bold text-teal-600">Claro</span>
            <span className="text-sm font-bold text-gray-900">bill</span>
          </div>
        </LogoSection>

        {/* Concept B — Icon + wordmark: magnifying glass */}
        <LogoSection label="B — Icon mark: magnifying glass">
          <div className="flex items-center gap-3">
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="15" cy="15" r="10" stroke="#0d9488" strokeWidth="3" fill="none"/>
              <line x1="22.5" y1="22.5" x2="31" y2="31" stroke="#0d9488" strokeWidth="3" strokeLinecap="round"/>
              <line x1="11" y1="15" x2="19" y2="15" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
              <line x1="15" y1="11" x2="15" y2="19" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span className="text-3xl font-bold text-gray-900">Clarobill</span>
          </div>
          <div className="flex items-center gap-2 mt-4">
            <svg width="24" height="24" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="15" cy="15" r="10" stroke="#0d9488" strokeWidth="3" fill="none"/>
              <line x1="22.5" y1="22.5" x2="31" y2="31" stroke="#0d9488" strokeWidth="3" strokeLinecap="round"/>
              <line x1="11" y1="15" x2="19" y2="15" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
              <line x1="15" y1="11" x2="15" y2="19" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span className="text-xl font-bold text-gray-900">Clarobill</span>
          </div>
        </LogoSection>

        {/* Concept C — Icon + wordmark: document with checkmark */}
        <LogoSection label="C — Icon mark: document + check">
          <div className="flex items-center gap-3">
            <svg width="32" height="36" viewBox="0 0 32 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="2" width="28" height="32" rx="4" stroke="#111827" strokeWidth="2.5" fill="none"/>
              <line x1="8" y1="12" x2="24" y2="12" stroke="#d1d5db" strokeWidth="2" strokeLinecap="round"/>
              <line x1="8" y1="18" x2="20" y2="18" stroke="#d1d5db" strokeWidth="2" strokeLinecap="round"/>
              <circle cx="22" cy="26" r="7" fill="#0d9488"/>
              <polyline points="18.5,26 21,28.5 25.5,23.5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <span className="text-3xl font-bold text-gray-900">Clarobill</span>
          </div>
          <div className="flex items-center gap-2 mt-4">
            <svg width="22" height="26" viewBox="0 0 32 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="2" width="28" height="32" rx="4" stroke="#111827" strokeWidth="2.5" fill="none"/>
              <line x1="8" y1="12" x2="24" y2="12" stroke="#d1d5db" strokeWidth="2" strokeLinecap="round"/>
              <line x1="8" y1="18" x2="20" y2="18" stroke="#d1d5db" strokeWidth="2" strokeLinecap="round"/>
              <circle cx="22" cy="26" r="7" fill="#0d9488"/>
              <polyline points="18.5,26 21,28.5 25.5,23.5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <span className="text-xl font-bold text-gray-900">Clarobill</span>
          </div>
        </LogoSection>

        {/* Concept D — Monogram mark: C in a circle */}
        <LogoSection label="D — Monogram: C in a pill">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-teal-600 flex items-center justify-center">
              <span className="text-white font-bold text-xl">C</span>
            </div>
            <span className="text-3xl font-bold text-gray-900">Clarobill</span>
          </div>
          <div className="flex items-center gap-2 mt-4">
            <div className="w-7 h-7 rounded-lg bg-teal-600 flex items-center justify-center">
              <span className="text-white font-bold text-sm">C</span>
            </div>
            <span className="text-xl font-bold text-gray-900">Clarobill</span>
          </div>
          {/* Dark background variant */}
          <div className="flex items-center gap-3 mt-6 bg-gray-900 p-4 rounded-xl w-fit">
            <div className="w-10 h-10 rounded-xl bg-teal-500 flex items-center justify-center">
              <span className="text-white font-bold text-xl">C</span>
            </div>
            <span className="text-3xl font-bold text-white">Clarobill</span>
          </div>
        </LogoSection>

        {/* Concept E — Light beam / clarity mark */}
        <LogoSection label="E — Icon mark: light ray (clarity)">
          <div className="flex items-center gap-3">
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="18" cy="18" r="6" fill="#0d9488"/>
              {/* Rays */}
              <line x1="18" y1="2" x2="18" y2="8" stroke="#0d9488" strokeWidth="2.5" strokeLinecap="round"/>
              <line x1="18" y1="28" x2="18" y2="34" stroke="#0d9488" strokeWidth="2.5" strokeLinecap="round"/>
              <line x1="2" y1="18" x2="8" y2="18" stroke="#0d9488" strokeWidth="2.5" strokeLinecap="round"/>
              <line x1="28" y1="18" x2="34" y2="18" stroke="#0d9488" strokeWidth="2.5" strokeLinecap="round"/>
              <line x1="6.5" y1="6.5" x2="10.7" y2="10.7" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
              <line x1="25.3" y1="25.3" x2="29.5" y2="29.5" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
              <line x1="29.5" y1="6.5" x2="25.3" y2="10.7" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
              <line x1="10.7" y1="25.3" x2="6.5" y2="29.5" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span className="text-3xl font-bold text-gray-900">Clarobill</span>
          </div>
          <div className="flex items-center gap-2 mt-4">
            <svg width="24" height="24" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="18" cy="18" r="6" fill="#0d9488"/>
              <line x1="18" y1="2" x2="18" y2="8" stroke="#0d9488" strokeWidth="2.5" strokeLinecap="round"/>
              <line x1="18" y1="28" x2="18" y2="34" stroke="#0d9488" strokeWidth="2.5" strokeLinecap="round"/>
              <line x1="2" y1="18" x2="8" y2="18" stroke="#0d9488" strokeWidth="2.5" strokeLinecap="round"/>
              <line x1="28" y1="18" x2="34" y2="18" stroke="#0d9488" strokeWidth="2.5" strokeLinecap="round"/>
              <line x1="6.5" y1="6.5" x2="10.7" y2="10.7" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
              <line x1="25.3" y1="25.3" x2="29.5" y2="29.5" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
              <line x1="29.5" y1="6.5" x2="25.3" y2="10.7" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
              <line x1="10.7" y1="25.3" x2="6.5" y2="29.5" stroke="#0d9488" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span className="text-xl font-bold text-gray-900">Clarobill</span>
          </div>
        </LogoSection>

      </div>
    </div>
  );
}

function LogoSection({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <div>
      <p className="text-xs text-gray-400 uppercase tracking-widest mb-6">{label}</p>
      <div className="flex flex-wrap items-end gap-12">
        {children}
      </div>
    </div>
  );
}
