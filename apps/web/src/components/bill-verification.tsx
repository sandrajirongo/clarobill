'use client';

import Link from 'next/link';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import s from './bill-verification.module.css';

interface InsurancePlan {
  id: string;
  payer_name: string;
  plan_name: string;
  plan_type: string;
  is_primary_plan: boolean;
}

interface ProfileMember {
  id: string;
  full_name: string;
  date_of_birth: string;
  state: string | null;
  county: string | null;
  zip_code: string | null;
  is_primary: boolean;
  insurance_plans: InsurancePlan[];
}

interface BillVerificationProps {
  billId: string;
  fileName: string;
  // OCR-extracted hospital name (may be empty/null if not yet extracted)
  ocrHospitalName: string | null;
}

const POLL_INTERVAL_MS = 2500;
const MAX_POLLS = 80; // ~3.5 minutes

export function BillVerification({ billId, fileName, ocrHospitalName }: BillVerificationProps): JSX.Element {
  const router = useRouter();

  const [members, setMembers] = useState<ProfileMember[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(true);

  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [hospitalName, setHospitalName] = useState(ocrHospitalName ?? '');

  const [phase, setPhase] = useState<'form' | 'analyzing' | 'error'>('form');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Load the user's profile members on mount, and pre-select the primary member
  useEffect(() => {
    fetch('/api/profile/members')
      .then((r) => r.json())
      .then(({ members: data }: { members: ProfileMember[] }) => {
        setMembers(data);
        const primary = data.find((m) => m.is_primary) ?? data[0];
        if (primary) {
          setSelectedMemberId(primary.id);
          const primaryPlan = primary.insurance_plans.find((p) => p.is_primary_plan)
            ?? primary.insurance_plans[0];
          if (primaryPlan) setSelectedPlanId(primaryPlan.id);
        }
      })
      .finally(() => setLoadingMembers(false));
  }, []);

  // When member changes, reset plan selection and pick the primary plan for the new member
  function handleSelectMember(memberId: string): void {
    setSelectedMemberId(memberId);
    const member = members.find((m) => m.id === memberId);
    if (member) {
      const primary = member.insurance_plans.find((p) => p.is_primary_plan)
        ?? member.insurance_plans[0];
      setSelectedPlanId(primary?.id ?? null);
    } else {
      setSelectedPlanId(null);
    }
  }

  const selectedMember = members.find((m) => m.id === selectedMemberId) ?? null;
  const selectedPlan = selectedMember?.insurance_plans.find((p) => p.id === selectedPlanId) ?? null;

  const canRun = Boolean(selectedMember && selectedPlan);

  const poll = useCallback(async (): Promise<void> => {
    let polls = 0;
    await new Promise<void>((resolve) => {
      const interval = setInterval(async () => {
        polls += 1;
        if (polls > MAX_POLLS) {
          clearInterval(interval);
          setPhase('error');
          setErrorMsg('Analysis is taking longer than expected. Check back in a moment.');
          resolve();
          return;
        }
        try {
          const res = await fetch(`/api/bills/${billId}`);
          if (!res.ok) return; // transient — keep polling
          const { status } = await res.json() as { status: string };
          if (status === 'complete') {
            clearInterval(interval);
            router.push(`/dashboard/bills/${billId}`);
            resolve();
          } else if (status === 'failed') {
            clearInterval(interval);
            setPhase('error');
            setErrorMsg('We could not analyze your bill. Please ensure the file is a clear image or PDF and try again.');
            resolve();
          }
        } catch {
          // network blip — keep polling
        }
      }, POLL_INTERVAL_MS);
    });
  }, [billId, router]);

  async function handleRunAnalysis(): Promise<void> {
    if (!selectedMember || !selectedPlan) return;
    setPhase('analyzing');
    setErrorMsg(null);

    const res = await fetch(`/api/bills/${billId}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profileMemberId: selectedMember.id,
        payerName: selectedPlan.payer_name,
        planName: selectedPlan.plan_name,
        hospitalName: hospitalName.trim() || null,
      }),
    });

    if (!res.ok) {
      const { error } = await res.json() as { error: { detail: string } };
      setPhase('error');
      setErrorMsg(error?.detail ?? 'Something went wrong. Please try again.');
      return;
    }

    // Engine is running — poll for completion
    await poll();
  }

  if (phase === 'analyzing') {
    return (
      <main className={s.main}>
        <div className={s.inner}>
          <div className={s.analyzingWrap}>
            <div className={s.spinner} />
            <p className={s.analyzingTitle}>Analyzing your bill…</p>
            <p className={s.analyzingNote}>
              We're running 10 billing checks against Medicare benchmarks,<br />
              your hospital's published rates, and your insurer's contracted rates.<br />
              This takes about 30 seconds.
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className={s.main}>
      <div className={s.inner}>

        <div>
          <Link href="/dashboard" className={s.backLink}>← My Bills</Link>
          <h1 className={s.pageTitle}>Confirm Bill Details</h1>
          <p className={s.pageSub}>
            We need a few details to run the most accurate analysis — including checking
            your insurer's exact contracted rates for each procedure.
          </p>
          <p className={s.fileName}>{fileName}</p>
        </div>

        {phase === 'error' && errorMsg && (
          <div className={s.errorNote}>
            {errorMsg}
          </div>
        )}

        {/* Step 1: Patient */}
        <div className={s.stepCard} data-complete={String(Boolean(selectedMember))}>
          <div className={s.stepHeader}>
            <span className={s.stepNum}>1</span>
            <span className={s.stepTitle}>Who is this bill for?</span>
            {selectedMember && (
              <span className={s.stepSummary}>{selectedMember.full_name}</span>
            )}
          </div>
          <div className={s.stepBody}>
            {loadingMembers ? (
              <p style={{ fontSize: '.84rem', color: 'var(--txt3)' }}>Loading members…</p>
            ) : members.length === 0 ? (
              <p className={s.noMembersNote}>
                No members found on your profile.{' '}
                <Link href="/dashboard/profile" className={s.profileLink}>Add yourself first →</Link>
              </p>
            ) : (
              <div className={s.memberList}>
                {members.map((member) => {
                  const locationParts = [member.county, member.state].filter(Boolean);
                  const dob = new Date(member.date_of_birth + 'T00:00:00').toLocaleDateString('en-US', {
                    month: 'short', day: 'numeric', year: 'numeric',
                  });
                  return (
                    <div
                      key={member.id}
                      className={s.memberOption}
                      data-selected={String(selectedMemberId === member.id)}
                      onClick={() => handleSelectMember(member.id)}
                      role="radio"
                      aria-checked={selectedMemberId === member.id}
                    >
                      <div>
                        <p className={s.memberOptionName}>{member.full_name}</p>
                        <p className={s.memberOptionMeta}>
                          DOB {dob}
                          {locationParts.length > 0 && ` · ${locationParts.join(', ')}`}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Step 2: Insurance Plan */}
        <div className={s.stepCard} data-complete={String(Boolean(selectedPlan))}>
          <div className={s.stepHeader}>
            <span className={s.stepNum}>2</span>
            <span className={s.stepTitle}>Which insurance plan?</span>
            {selectedPlan && (
              <span className={s.stepSummary}>
                {selectedPlan.payer_name}<br />{selectedPlan.plan_name}
              </span>
            )}
          </div>
          <div className={s.stepBody}>
            {!selectedMember ? (
              <p style={{ fontSize: '.84rem', color: 'var(--txt3)' }}>Select a member above first.</p>
            ) : selectedMember.insurance_plans.length === 0 ? (
              <p className={s.noPlansNote}>
                No insurance plans on file for {selectedMember.full_name}.{' '}
                <Link href="/dashboard/profile" className={s.profileLink}>Add a plan →</Link>
                <br />
                <span style={{ fontSize: '.78rem' }}>
                  Without an insurance plan we can't check if your provider billed above your contracted rate.
                </span>
              </p>
            ) : (
              <div className={s.planList}>
                {selectedMember.insurance_plans.map((plan) => (
                  <div
                    key={plan.id}
                    className={s.planOption}
                    data-selected={String(selectedPlanId === plan.id)}
                    onClick={() => setSelectedPlanId(plan.id)}
                    role="radio"
                    aria-checked={selectedPlanId === plan.id}
                  >
                    <div>
                      <p className={s.planPayer}>{plan.payer_name}</p>
                      <p className={s.planName}>{plan.plan_name}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Step 3: Hospital */}
        <div className={s.stepCard} data-complete={String(hospitalName.trim().length > 0)}>
          <div className={s.stepHeader}>
            <span className={s.stepNum}>3</span>
            <span className={s.stepTitle}>Which hospital or provider?</span>
            {hospitalName.trim() && (
              <span className={s.stepSummary}>{hospitalName.trim()}</span>
            )}
          </div>
          <div className={s.stepBody}>
            <input
              className={s.hospitalInput}
              type="text"
              placeholder="e.g. Cedars-Sinai Medical Center"
              value={hospitalName}
              onChange={(e) => setHospitalName(e.target.value)}
            />
            <p className={s.inputHint}>
              This helps us find your provider's published price list for comparison. Optional but recommended.
            </p>
          </div>
        </div>

        {/* Step 4: Service Dates */}
        <div className={s.stepCard} data-complete="true">
          <div className={s.stepHeader}>
            <span className={s.stepNum}>4</span>
            <span className={s.stepTitle}>Service dates</span>
            <span className={s.stepCheck}>✓ Extracted from bill</span>
          </div>
          <div className={s.stepBody}>
            <p className={s.datesNote}>
              We extract service dates directly from your bill. Our analysis automatically
              selects the Medicare fee schedules and rates effective on your date of service —
              so even historical bills are benchmarked against the correct rates.
            </p>
          </div>
        </div>

        {/* Run CTA */}
        <div className={s.ctaRow}>
          <p className={s.ctaNote}>
            {!canRun
              ? 'Select a member and insurance plan to continue.'
              : 'Ready to run 10 billing accuracy checks.'}
          </p>
          <button
            className={s.ctaBtn}
            disabled={!canRun}
            onClick={() => void handleRunAnalysis()}
          >
            Run Analysis
          </button>
        </div>

      </div>
    </main>
  );
}
