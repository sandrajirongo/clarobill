'use client';

import Link from 'next/link';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { US_STATES, COUNTIES_BY_STATE } from '@/lib/utils/county-data';
import { useCardScan } from '@/lib/hooks/use-card-scan';
import s from './bill-verification.module.css';

// ─── Insurance plan type constants ────────────────────────────────────────────

// Medicaid state brand names — states that have named their program differently.
// For all other states we show "[State] Medicaid" in the plan type dropdown.
const MEDICAID_STATE_BRANDS: Record<string, string> = {
  'California':    'Medi-Cal',
  'Tennessee':     'TennCare',
  'Arizona':       'AHCCCS',
  'Massachusetts': 'MassHealth',
  'Oregon':        'Oregon Health Plan',
  'Washington':    'Apple Health',
  'Hawaii/Guam':   'Med-QUEST',
  'Minnesota':     'Medical Assistance (MA)',
  'Pennsylvania':  'Medical Assistance (MA)',
  'Indiana':       'HIP / Indiana Medicaid',
  'Colorado':      'Health First Colorado',
  'Nevada':        'Nevada Medicaid',
  'Kentucky':      'Kentucky Medicaid',
};

function getMedicaidBrandName(state: string | null | undefined): string {
  if (!state) return 'Medicaid';
  return MEDICAID_STATE_BRANDS[state] ?? `${state} Medicaid`;
}

// Medicaid program sub-types — delivery mechanism defines which rate schedule applies.
// Fee-for-Service → published state Medicaid fee schedule.
// Managed Care → MCO-specific contracted rates (varies by insurer + state).
const MEDICAID_PLAN_TYPES = [
  { value: 'Fee-for-Service Medicaid',         label: 'Fee-for-Service — state pays providers directly'       },
  { value: 'Medicaid Managed Care',            label: 'Managed Care — private MCO manages your coverage'     },
  { value: 'CHIP',                             label: 'CHIP — Children\'s Health Insurance Program'           },
  { value: 'Dual Eligible (Medicare + Medicaid)', label: 'Dual Eligible — both Medicare and Medicaid cover you' },
  { value: 'Long-Term Services and Supports',  label: 'Long-Term Care / LTSS waiver'                         },
  { value: 'Medicaid Home & Community Waiver', label: 'Home & Community-Based Services waiver'               },
];

// State-specific MCO lists for Medicaid Managed Care — shown as autocomplete suggestions.
// Users in states not listed fall back to the national list.
const MEDICAID_MCOS_BY_STATE: Record<string, string[]> = {
  'California':    ['L.A. Care Health Plan', 'Health Net Medi-Cal', 'Molina Healthcare of California', 'Anthem Blue Cross', 'Kaiser Permanente', 'IEHP (Inland Empire)', 'CalOptima', 'Alameda Alliance'],
  'Texas':         ['Molina Healthcare', 'UnitedHealthcare Community Plan', 'Superior HealthPlan (Centene)', 'Aetna Better Health of Texas', 'BCBS of Texas'],
  'New York':      ['Fidelis Care', 'Healthfirst', 'Amerigroup (Elevance)', 'WellCare Health Plans', 'Molina Healthcare', 'UnitedHealthcare Community Plan', 'MetroPlus'],
  'Florida':       ['Simply Healthcare (Centene)', 'Molina Healthcare of Florida', 'Staywell (Centene)', 'Humana Medicaid', 'UnitedHealthcare Community Plan'],
  'Pennsylvania':  ['Gateway Health (Highmark)', 'UPMC for You', 'Aetna Better Health of PA', 'Geisinger Health Plan', 'Molina Healthcare'],
  'Ohio':          ['Buckeye Health Plan (Centene)', 'CareSource', 'Molina Healthcare', 'UnitedHealthcare Community Plan', 'Paramount Advantage'],
  'Illinois':      ['CountyCare (Cook County)', 'Meridian Health Plan (Centene)', 'Molina Healthcare', 'BlueCross Community Options (BCBS IL)', 'IlliniCare Health'],
  'Michigan':      ['Molina Healthcare', 'UnitedHealthcare Community Plan', 'Meridian Health Plan (Centene)', 'HAP Midwest Health Plan'],
  'Georgia':       ['Amerigroup (Elevance)', 'Peach State Health (Centene)', 'UnitedHealthcare Community Plan', 'WellCare', 'CareSource Georgia'],
  'North Carolina':['BCBS of NC', 'Aetna Better Health of NC', 'Healthy Blue (BCBS)', 'UnitedHealthcare Community Plan', 'WellCare of NC'],
  'Washington':    ['Molina Healthcare of Washington', 'UnitedHealthcare Community Plan', 'Amerigroup Washington', 'Community Health Plan of WA'],
  'Arizona':       ['Mercy Care (Cenpatico)', 'UnitedHealthcare Community Plan', 'Molina Healthcare of Arizona', 'Aetna Better Health of AZ', 'Health Choice Arizona'],
  'Virginia':      ['Aetna Better Health of Virginia', 'Anthem HealthKeepers Plus', 'Molina Healthcare of Virginia', 'Optima Health Community Care', 'UnitedHealthcare Community Plan'],
  'Indiana':       ['Anthem (Elevance)', 'MDwise (Centene)', 'Molina Healthcare', 'CareSource Indiana'],
  'Massachusetts': ['Fallon Health', 'BMC HealthNet Plan', 'Tufts Health Together', 'UnitedHealthcare Community Plan', 'Aetna Better Health of MA'],
  'Tennessee':     ['Amerigroup Tennessee (Elevance)', 'BlueCare Tennessee (BCBS)', 'United American Insurance (UHC)'],
  'New Jersey':    ['Aetna Better Health', 'AmeriHealth Caritas NJ', 'Horizon NJ Health', 'UnitedHealthcare Community Plan', 'WellCare of NJ'],
  'Colorado':      ['Colorado Access', 'Rocky Mountain Health Plans', 'Anthem (Elevance)', 'Denver Health Medical Plan', 'Bright Health Plan'],
  'Oregon':        ['CareOregon', 'PacificSource Community Solutions', 'Trillium Community Health Plan', 'Umpqua Health Alliance', 'Yamhill Community Care'],
  'Minnesota':     ['UCare', 'Blue Plus (BCBS MN)', 'Medica', 'HealthPartners', 'Hennepin Health'],
};

const MEDICAID_MCOS_NATIONAL = [
  'Molina Healthcare', 'UnitedHealthcare Community Plan', 'Aetna Better Health',
  'Centene / WellCare', 'Humana Medicaid', 'Anthem / Elevance Health',
  'CareSource', 'AmeriHealth Caritas',
];

// Medicare sub-types — Original Medicare uses CMS fee schedules we have loaded.
// Medicare Advantage (Part C) is a private plan with insurer-negotiated rates.
const MEDICARE_PLAN_TYPES = [
  { value: 'Original Medicare (Parts A + B)',      label: 'Original Medicare (Parts A + B) — government pays providers directly'  },
  { value: 'Medicare Advantage (Part C)',           label: 'Medicare Advantage (Part C) — private HMO or PPO plan'                },
  { value: 'Medicare + Medigap Supplement',         label: 'Medicare + Medigap Supplement — Original Medicare with gap coverage'  },
  { value: 'Dual Eligible (Medicare + Medicaid)',   label: 'Dual Eligible — both Medicare and Medicaid cover you'                 },
  { value: 'Medicare Part A Only',                  label: 'Part A Only — inpatient/hospital, no outpatient Part B'               },
];

// TRICARE sub-types — Prime uses MTF/PCM rates; For Life wraps Medicare; Select is PPO-like.
const TRICARE_PLAN_TYPES = [
  { value: 'TRICARE Prime',          label: 'TRICARE Prime — HMO-like, must use MTF or assigned PCM'    },
  { value: 'TRICARE Select',         label: 'TRICARE Select — PPO-like, direct access to providers'     },
  { value: 'TRICARE For Life',       label: 'TRICARE For Life — Medicare supplement for retired military' },
  { value: 'TRICARE Reserve Select', label: 'TRICARE Reserve Select — Guard and Reserve members'        },
  { value: 'TRICARE Overseas (TOP)', label: 'TRICARE Overseas Program'                                   },
  { value: 'CHAMPVA',                label: 'CHAMPVA — VA coverage for veterans\' family members'        },
];

interface InsurancePlan {
  id: string;
  payer_name: string;
  plan_name: string;
  plan_type: string;
  member_id: string | null;
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

interface Props {
  billId: string;
  fileName: string;
  ocrHospitalName: string | null;
}

const POLL_MS = 2500;
const MAX_POLLS = 80;

export function BillVerification({ billId, fileName, ocrHospitalName }: Props): JSX.Element {
  const router = useRouter();

  const [members, setMembers]           = useState<ProfileMember[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(true);
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
  const [selectedPlanId, setSelectedPlanId]     = useState<string | null>(null);
  // hospitalName is sourced from OCR — not user-editable on the verify page.
  // The engine can extract it from the file; we pass it for BigQuery price-list lookup only.

  // 'compact': returning user summary card | 'expanded': step-by-step
  const [formMode, setFormMode] = useState<'compact' | 'expanded'>('expanded');
  const [phase, setPhase]       = useState<'form' | 'analyzing' | 'error'>('form');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Inline member creation form state
  const [showAddMember, setShowAddMember] = useState(false);
  const [newName, setNewName]   = useState('');
  const [newDob, setNewDob]     = useState('');
  const [newState, setNewState] = useState('');
  const [newCounty, setNewCounty] = useState('');
  const [newZip, setNewZip]     = useState('');
  const [addingMember, setAddingMember] = useState(false);

  // Inline plan creation form state
  const [showAddPlan, setShowAddPlan] = useState(false);
  const [newPayer, setNewPayer]       = useState('');
  const [newPlan, setNewPlan]         = useState('');
  const [newPlanType, setNewPlanType] = useState('commercial');
  const [newMemberId, setNewMemberId] = useState('');
  const [newMedicaidType, setNewMedicaidType] = useState('');
  const [newMedicaidMCO, setNewMedicaidMCO]   = useState('');
  const [newMedicareType, setNewMedicareType] = useState('');
  const [newMedicareMAName, setNewMedicareMAName] = useState('');
  const [newTricareType, setNewTricareType]   = useState('');
  const [newIsPrimary, setNewIsPrimary] = useState(false);
  const [addingPlan, setAddingPlan]   = useState(false);

  const { scanState, inputRef: cardInputRef, openFilePicker, handleFile, reset: resetScan } = useCardScan();

  const [formError, setFormError] = useState<string | null>(null);

  // Progress steps shown during analysis — advance on a timer to give feedback
  // while the engine runs. Each step is a real check; timing is approximate.
  const [analysisStep, setAnalysisStep] = useState(0);

  const loadMembers = useCallback(async (): Promise<void> => {
    const res = await fetch('/api/profile/members');
    if (!res.ok) { setLoadingMembers(false); return; }
    const { members: data } = await res.json() as { members: ProfileMember[] };
    setMembers(data);
    setLoadingMembers(false);

    // Auto-select primary member + plan; switch to compact mode if everything is ready
    const primary = data.find((m) => m.is_primary) ?? data[0];
    if (primary) {
      setSelectedMemberId(primary.id);
      const primaryPlan = primary.insurance_plans.find((p) => p.is_primary_plan) ?? primary.insurance_plans[0];
      if (primaryPlan) {
        setSelectedPlanId(primaryPlan.id);
        setFormMode('compact'); // returning user — show summary by default
      }
    }
  }, []);

  useEffect(() => { void loadMembers(); }, [loadMembers]);

  useEffect(() => {
    if (phase !== 'analyzing') return;
    setAnalysisStep(0);
    // Advance through 5 visual steps at ~6s intervals while the engine runs.
    // These mirror the real checks in rules_engine.py — not faked, just pre-shown.
    const timeouts = [6000, 12000, 18000, 24000, 30000].map((ms, i) =>
      setTimeout(() => setAnalysisStep(i + 1), ms)
    );
    return () => timeouts.forEach(clearTimeout);
  }, [phase]);

  // Pre-fill plan form fields when a card scan completes
  useEffect(() => {
    if (scanState.status !== 'done') return;
    const r = scanState.result;
    if (r.payerName) setNewPayer(r.payerName);
    if (r.planName)  setNewPlan(r.planName);
    if (r.planType)  setNewPlanType(r.planType);
    if (r.memberId)  setNewMemberId(r.memberId);
  }, [scanState]);

  function handleSelectMember(memberId: string): void {
    setSelectedMemberId(memberId);
    const m = members.find((x) => x.id === memberId);
    const plan = m?.insurance_plans.find((p) => p.is_primary_plan) ?? m?.insurance_plans[0];
    setSelectedPlanId(plan?.id ?? null);
    setShowAddPlan(false);
  }

  const selectedMember = members.find((m) => m.id === selectedMemberId) ?? null;
  const selectedPlan   = selectedMember?.insurance_plans.find((p) => p.id === selectedPlanId) ?? null;
  const canRun = Boolean(selectedMember && selectedPlan);

  // ── Inline add member ────────────────────────────────────────────────────
  async function handleAddMember(): Promise<void> {
    if (!newName.trim() || !newDob) { setFormError('Name and date of birth are required.'); return; }
    setAddingMember(true); setFormError(null);
    const res = await fetch('/api/profile/members', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fullName: newName, dateOfBirth: newDob,
        state: newState || null, county: newCounty || null, zipCode: newZip || null,
        isPrimary: members.length === 0,
      }),
    });
    setAddingMember(false);
    if (!res.ok) { setFormError('Could not save member. Try again.'); return; }
    const { member } = await res.json() as { member: { id: string } };
    setNewName(''); setNewDob(''); setNewState(''); setNewCounty(''); setNewZip('');
    setShowAddMember(false);
    await loadMembers();
    setSelectedMemberId(member.id);
    setShowAddPlan(true); // prompt to add a plan for this new member
  }

  // ── Inline add plan ──────────────────────────────────────────────────────
  async function handleAddPlan(): Promise<void> {
    if (!selectedMemberId) return;
    // Government plans don't require explicit payer/plan names — the API fills defaults.
    // Commercial plans must have both.
    const isGovPlan = newPlanType !== 'commercial';
    if (!isGovPlan && (!newPayer.trim() || !newPlan.trim())) {
      setFormError('Insurer name and plan name are required.');
      return;
    }
    setAddingPlan(true); setFormError(null);

    // Derive the most specific payer_name and plan_name from the sub-type selections.
    // The backend fills defaults for anything left null, but these give better analysis context.
    let resolvedPayerName = newPayer.trim() || null;
    let resolvedPlanName  = newPlan.trim()  || null;

    if (newPlanType === 'medicaid') {
      const brand = getMedicaidBrandName(selectedMember?.state);
      if (newMedicaidType === 'Medicaid Managed Care' && newMedicaidMCO.trim()) {
        resolvedPayerName ??= newMedicaidMCO.trim();
        resolvedPlanName  ??= newMedicaidType;
      } else {
        resolvedPayerName ??= brand;
        resolvedPlanName  ??= newMedicaidType || null;
      }
    } else if (newPlanType === 'medicare') {
      if (newMedicareType === 'Medicare Advantage (Part C)') {
        resolvedPayerName ??= newMedicareMAName.trim() || 'Medicare Advantage';
      } else {
        resolvedPayerName ??= 'Medicare';
      }
      resolvedPlanName ??= newMedicareType || null;
    } else if (newPlanType === 'tricare') {
      resolvedPayerName ??= 'TRICARE';
      resolvedPlanName  ??= newTricareType || null;
    }

    const res = await fetch(`/api/profile/members/${selectedMemberId}/plans`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        payerName: resolvedPayerName,
        planName: resolvedPlanName,
        planType: newPlanType,
        memberId: newMemberId || null,
        isPrimaryPlan: newIsPrimary,
      }),
    });
    setAddingPlan(false);
    if (!res.ok) { setFormError('Could not save plan. Try again.'); return; }
    const { plan } = await res.json() as { plan: { id: string } };
    setNewPayer(''); setNewPlan(''); setNewPlanType('commercial'); setNewMemberId('');
    setNewMedicaidType(''); setNewMedicaidMCO('');
    setNewMedicareType(''); setNewMedicareMAName('');
    setNewTricareType(''); setNewIsPrimary(false);
    setShowAddPlan(false);
    resetScan();
    await loadMembers();
    setSelectedPlanId(plan.id);
  }

  // ── Analysis polling ─────────────────────────────────────────────────────
  const poll = useCallback(async (): Promise<void> => {
    let polls = 0;
    await new Promise<void>((resolve) => {
      const id = setInterval(async () => {
        polls++;
        if (polls > MAX_POLLS) {
          clearInterval(id);
          setPhase('error');
          setErrorMsg('Analysis is taking longer than expected. Check back shortly.');
          resolve(); return;
        }
        try {
          const res = await fetch(`/api/bills/${billId}`);
          if (!res.ok) return;
          const { status } = await res.json() as { status: string };
          if (status === 'complete') { clearInterval(id); router.push(`/dashboard/bills/${billId}`); resolve(); }
          else if (status === 'failed') {
            clearInterval(id);
            setPhase('error');
            setErrorMsg('We could not analyze your bill. Make sure the file is a clear image or PDF and try again.');
            resolve();
          }
        } catch { /* network blip */ }
      }, POLL_MS);
    });
  }, [billId, router]);

  async function handleRunAnalysis(): Promise<void> {
    if (!selectedMember || !selectedPlan) return;
    setPhase('analyzing'); setErrorMsg(null);
    const res = await fetch(`/api/bills/${billId}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profileMemberId: selectedMember.id,
        payerName: selectedPlan.payer_name,
        planName: selectedPlan.plan_name,
        hospitalName: ocrHospitalName ?? null,
      }),
    });
    if (!res.ok) {
      const { error } = await res.json() as { error: { detail: string } };
      setPhase('error'); setErrorMsg(error?.detail ?? 'Something went wrong. Please try again.');
      return;
    }
    await poll();
  }

  // ── Analyzing screen ─────────────────────────────────────────────────────
  const ANALYSIS_STEPS = [
    'Reading your bill',
    'Extracting charge codes',
    'Comparing against Medicare benchmarks',
    'Checking your insurer\'s contracted rates',
    'Scanning for duplicate charges',
    'Finalizing your report',
  ];

  if (phase === 'analyzing') {
    return (
      <main className={s.main}>
        <div className={s.inner}>
          <div className={s.analyzingWrap}>
            <p className={s.analyzingTitle}>Analyzing your bill…</p>
            <p className={s.analyzingNote}>Running 10 billing checks. About 30 seconds.</p>
            <div className={s.analysisSteps}>
              {ANALYSIS_STEPS.map((label, i) => {
                const isDone   = i < analysisStep;
                const isActive = i === analysisStep;
                return (
                  <div key={i} className={`${s.analysisStep} ${isDone ? s.analysisStepDone : isActive ? s.analysisStepActive : s.analysisStepPending}`}>
                    <span className={s.analysisStepDot}>
                      {isDone ? '✓' : isActive ? <span className={s.analysisStepPulse} /> : null}
                    </span>
                    <span className={s.analysisStepText}>{label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </main>
    );
  }

  const newMemberCounties = newState ? (COUNTIES_BY_STATE[newState] ?? []) : [];

  // ── Form screen ──────────────────────────────────────────────────────────
  return (
    <main className={s.main}>
      <div className={s.inner}>

        <div>
          <Link href="/dashboard" className={s.backLink}>← My Bills</Link>
          <h1 className={s.pageTitle}>Before we analyze your bill</h1>
          <p className={s.pageSub}>
            We compare every charge against Medicare benchmarks and your insurer&apos;s
            contracted rates. Takes about 30 seconds — just tell us who this bill is for.
          </p>
          <p className={s.fileName}>{fileName}</p>
        </div>

        {phase === 'error' && errorMsg && <div className={s.errorNote}>{errorMsg}</div>}
        {formError && <div className={s.errorNote}>{formError}</div>}

        {loadingMembers ? (
          <div className={s.stepCard}><div className={s.stepBody} style={{ padding: '1.5rem' }}><p style={{ fontSize: '.84rem', color: 'var(--txt3)' }}>Loading your profile…</p></div></div>
        ) : formMode === 'compact' && selectedMember && selectedPlan ? (
          // ── COMPACT MODE (returning user) ──────────────────────────────
          <div className={s.compactCard}>
            <div className={s.compactRow}>
              <div className={s.compactField}>
                <span className={s.compactLabel}>Patient</span>
                <span className={s.compactValue}>{selectedMember.full_name}</span>
              </div>
              <div className={s.compactDivider} />
              <div className={s.compactField}>
                <span className={s.compactLabel}>Insurance</span>
                <span className={s.compactValue}>{selectedPlan.payer_name}</span>
                <span className={s.compactSub}>{selectedPlan.plan_name}</span>
              </div>
            </div>
            <button className={s.changeLink} onClick={() => setFormMode('expanded')}>
              Change member or insurance →
            </button>
          </div>
        ) : (
          // ── EXPANDED MODE (new user or changing details) ───────────────
          <>
            {/* Step 1: Patient */}
            <div className={s.stepCard} data-complete={String(Boolean(selectedMember))}>
              <div className={s.stepHeader}>
                <span className={s.stepNum}>1</span>
                <span className={s.stepTitle}>Who is this bill for?</span>
                {selectedMember && <span className={s.stepSummary}>{selectedMember.full_name}</span>}
              </div>
              <div className={s.stepBody}>
                {members.length > 0 && (
                  <div className={s.memberList}>
                    {members.map((m) => (
                      <div
                        key={m.id}
                        className={s.memberOption}
                        data-selected={String(selectedMemberId === m.id)}
                        onClick={() => handleSelectMember(m.id)}
                        role="radio"
                        aria-checked={selectedMemberId === m.id}
                      >
                        <div>
                          <p className={s.memberOptionName}>{m.full_name}</p>
                          <p className={s.memberOptionMeta}>
                            DOB {new Date(m.date_of_birth + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                            {m.state && ` · ${m.state}`}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {!showAddMember ? (
                  <button className={s.addInlineBtn} onClick={() => { setShowAddMember(true); setFormError(null); }}>
                    {members.length === 0 ? '+ Add yourself' : '+ Add another member'}
                  </button>
                ) : (
                  <div className={s.inlineFormBox}>
                    <p className={s.inlineFormTitle}>New member</p>
                    <div className={s.formRow}>
                      <div className={s.formField} style={{ flex: 2 }}>
                        <label className={s.formLabel}>Full name *</label>
                        <input className={s.formInput} placeholder="Jane Smith" value={newName} onChange={(e) => setNewName(e.target.value)} autoFocus />
                      </div>
                      <div className={s.formField}>
                        <label className={s.formLabel}>Date of birth *</label>
                        <input type="date" className={s.formInput} value={newDob} onChange={(e) => setNewDob(e.target.value)} />
                      </div>
                    </div>
                    <div className={s.formRow}>
                      <div className={s.formField}>
                        <label className={s.formLabel}>State <span className={s.optionalTag}>(for rate lookup)</span></label>
                        <select className={s.formSelect} value={newState} onChange={(e) => { setNewState(e.target.value); setNewCounty(''); }}>
                          <option value="">Select state…</option>
                          {US_STATES.map((st) => <option key={st} value={st}>{st}</option>)}
                        </select>
                      </div>
                      {newMemberCounties.length > 0 && (
                        <div className={s.formField}>
                          <label className={s.formLabel}>County <span className={s.optionalTag}>(optional)</span></label>
                          <select className={s.formSelect} value={newCounty} onChange={(e) => setNewCounty(e.target.value)}>
                            <option value="">Select county…</option>
                            {newMemberCounties.map((c) => <option key={c} value={c}>{c}</option>)}
                          </select>
                        </div>
                      )}
                      <div className={s.formField}>
                        <label className={s.formLabel}>ZIP <span className={s.optionalTag}>(optional)</span></label>
                        <input className={s.formInput} placeholder="90210" maxLength={5} value={newZip} onChange={(e) => setNewZip(e.target.value.replace(/\D/g, ''))} />
                      </div>
                    </div>
                    <div className={s.formActions}>
                      <button className={s.cancelBtn} onClick={() => { setShowAddMember(false); setFormError(null); }}>Cancel</button>
                      <button className={s.saveBtn} disabled={addingMember} onClick={() => void handleAddMember()}>
                        {addingMember ? 'Saving…' : 'Save'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Step 2: Insurance plan */}
            <div className={s.stepCard} data-complete={String(Boolean(selectedPlan))}>
              <div className={s.stepHeader}>
                <span className={s.stepNum}>2</span>
                <span className={s.stepTitle}>Which insurance plan?</span>
                {selectedPlan && <span className={s.stepSummary}>{selectedPlan.payer_name} · {selectedPlan.plan_name}</span>}
              </div>
              <div className={s.stepBody}>
                {!selectedMember ? (
                  <p className={s.stepHint}>Select a member above first.</p>
                ) : (
                  <>
                    {selectedMember.insurance_plans.length > 0 && (
                      <div className={s.planList}>
                        {selectedMember.insurance_plans.map((p) => (
                          <div
                            key={p.id}
                            className={s.planOption}
                            data-selected={String(selectedPlanId === p.id)}
                            onClick={() => setSelectedPlanId(p.id)}
                            role="radio"
                            aria-checked={selectedPlanId === p.id}
                          >
                            <div style={{ flex: 1 }}>
                              <p className={s.planPayer}>{p.payer_name}</p>
                              <p className={s.planName}>{p.plan_name}</p>
                            </div>
                            {p.is_primary_plan ? (
                              <span className={s.planBadgePrimary}>Primary</span>
                            ) : selectedMember.insurance_plans.length > 1 ? (
                              <span className={s.planBadgeSecondary}>Secondary</span>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    )}

                    {!showAddPlan ? (
                      <button
                        className={s.addInlineBtn}
                        onClick={() => {
                          setShowAddPlan(true);
                          setFormError(null);
                          // Default new plan to primary if the member has none yet
                          setNewIsPrimary(selectedMember.insurance_plans.length === 0);
                        }}
                      >
                        {selectedMember.insurance_plans.length === 0 ? '+ Add insurance plan' : '+ Add another plan'}
                      </button>
                    ) : (
                      <div className={s.inlineFormBox}>
                        {/* Header row: title + scan card button */}
                        <div className={s.inlineFormHeader}>
                          <p className={s.inlineFormTitle}>Insurance plan</p>
                          <button
                            type="button"
                            className={s.scanBtn}
                            onClick={openFilePicker}
                            disabled={scanState.status === 'scanning'}
                          >
                            {scanState.status === 'scanning' ? 'Reading card…' : 'Scan card'}
                          </button>
                        </div>

                        {/* Hidden file input — opened programmatically by scan button */}
                        <input
                          ref={cardInputRef}
                          type="file"
                          accept="image/*"
                          capture="environment"
                          style={{ display: 'none' }}
                          onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleFile(f); }}
                        />

                        {/* Scan status feedback */}
                        {scanState.status === 'error' && (
                          <p className={s.scanError}>{scanState.message}</p>
                        )}
                        {scanState.status === 'done' && !scanState.result.confident && (
                          <p className={s.scanWarn}>Some fields may be uncertain — please review before saving.</p>
                        )}
                        {scanState.status === 'done' && scanState.result.note && (
                          <p className={s.scanNote}>{scanState.result.note}</p>
                        )}

                        {/* Plan type — label shows state Medicaid brand name when known */}
                        <div className={s.formRow}>
                          <div className={s.formField}>
                            <label className={s.formLabel}>Plan type</label>
                            <select
                              className={s.formSelect}
                              value={newPlanType}
                              onChange={(e) => {
                                setNewPlanType(e.target.value);
                                setNewMedicaidType(''); setNewMedicaidMCO('');
                                setNewMedicareType(''); setNewMedicareMAName('');
                                setNewTricareType('');
                              }}
                            >
                              <option value="commercial">Commercial Insurance</option>
                              <option value="medicare">Medicare</option>
                              <option value="medicaid">{getMedicaidBrandName(selectedMember?.state)} (Medicaid)</option>
                              <option value="tricare">TRICARE / Military</option>
                              <option value="self_pay">Self-Pay / Uninsured</option>
                            </select>
                          </div>
                        </div>

                        {/* Medicare sub-types — determines which rate schedule applies */}
                        {newPlanType === 'medicare' && (
                          <div className={s.formRow}>
                            <div className={s.formField}>
                              <label className={s.formLabel}>Medicare type <span className={s.optionalTag}>(helps with analysis)</span></label>
                              <select
                                className={s.formSelect}
                                value={newMedicareType}
                                onChange={(e) => { setNewMedicareType(e.target.value); setNewMedicareMAName(''); }}
                              >
                                <option value="">Select type…</option>
                                {MEDICARE_PLAN_TYPES.map(({ value, label }) => (
                                  <option key={value} value={value}>{label}</option>
                                ))}
                              </select>
                            </div>
                          </div>
                        )}

                        {/* Medicare Advantage: need insurer name + specific plan for rate lookup */}
                        {newPlanType === 'medicare' && newMedicareType === 'Medicare Advantage (Part C)' && (
                          <div className={s.formRow}>
                            <div className={s.formField}>
                              <label className={s.formLabel}>MA insurer *</label>
                              <input
                                className={s.formInput}
                                placeholder="e.g. Humana, Aetna, UnitedHealthcare, BCBS"
                                value={newMedicareMAName}
                                onChange={(e) => setNewMedicareMAName(e.target.value)}
                              />
                            </div>
                            <div className={s.formField}>
                              <label className={s.formLabel}>Plan name <span className={s.optionalTag}>(optional)</span></label>
                              <input
                                className={s.formInput}
                                placeholder="e.g. HumanaChoice PPO, Aetna Gold"
                                value={newPlan}
                                onChange={(e) => setNewPlan(e.target.value)}
                              />
                            </div>
                          </div>
                        )}

                        {/* Medicaid program sub-type */}
                        {newPlanType === 'medicaid' && (
                          <div className={s.formRow}>
                            <div className={s.formField}>
                              <label className={s.formLabel}>Program type <span className={s.optionalTag}>(helps with analysis)</span></label>
                              <select
                                className={s.formSelect}
                                value={newMedicaidType}
                                onChange={(e) => { setNewMedicaidType(e.target.value); setNewMedicaidMCO(''); }}
                              >
                                <option value="">Select program…</option>
                                {MEDICAID_PLAN_TYPES.map(({ value, label }) => (
                                  <option key={value} value={value}>{label}</option>
                                ))}
                              </select>
                            </div>
                          </div>
                        )}

                        {/* Managed Care: MCO name with state-specific autocomplete suggestions */}
                        {newPlanType === 'medicaid' && newMedicaidType === 'Medicaid Managed Care' && (
                          <div className={s.formRow}>
                            <div className={s.formField}>
                              <label className={s.formLabel}>Health plan / MCO <span className={s.optionalTag}>(optional)</span></label>
                              <input
                                className={s.formInput}
                                list="mco-suggestions"
                                placeholder={selectedMember?.state
                                  ? `Plans in ${selectedMember.state} — start typing…`
                                  : 'Start typing your plan name…'}
                                value={newMedicaidMCO}
                                onChange={(e) => setNewMedicaidMCO(e.target.value)}
                              />
                              <datalist id="mco-suggestions">
                                {(MEDICAID_MCOS_BY_STATE[selectedMember?.state ?? ''] ?? MEDICAID_MCOS_NATIONAL).map((mco) => (
                                  <option key={mco} value={mco} />
                                ))}
                              </datalist>
                            </div>
                          </div>
                        )}

                        {/* TRICARE program sub-types */}
                        {newPlanType === 'tricare' && (
                          <div className={s.formRow}>
                            <div className={s.formField}>
                              <label className={s.formLabel}>TRICARE program <span className={s.optionalTag}>(optional)</span></label>
                              <select
                                className={s.formSelect}
                                value={newTricareType}
                                onChange={(e) => setNewTricareType(e.target.value)}
                              >
                                <option value="">Select program…</option>
                                {TRICARE_PLAN_TYPES.map(({ value, label }) => (
                                  <option key={value} value={value}>{label}</option>
                                ))}
                              </select>
                            </div>
                          </div>
                        )}

                        {/* Commercial insurance: payer + plan name are required */}
                        {newPlanType === 'commercial' && (
                          <div className={s.formRow}>
                            <div className={s.formField}>
                              <label className={s.formLabel}>Insurance company *</label>
                              <input
                                className={`${s.formInput} ${scanState.status === 'done' && !scanState.result.confident && scanState.result.payerName ? s.formInputUncertain : ''}`}
                                placeholder="Blue Cross Blue Shield"
                                value={newPayer}
                                onChange={(e) => setNewPayer(e.target.value)}
                                autoFocus
                              />
                            </div>
                            <div className={s.formField}>
                              <label className={s.formLabel}>Plan name *</label>
                              <input
                                className={`${s.formInput} ${scanState.status === 'done' && !scanState.result.confident && scanState.result.planName ? s.formInputUncertain : ''}`}
                                placeholder="PPO Gold"
                                value={newPlan}
                                onChange={(e) => setNewPlan(e.target.value)}
                              />
                            </div>
                          </div>
                        )}

                        {/* Member ID + primary plan toggle */}
                        <div className={s.formRow}>
                          <div className={s.formField}>
                            <label className={s.formLabel}>
                              Member ID <span className={s.optionalTag}>(for dispute letters)</span>
                            </label>
                            <input
                              className={`${s.formInput} ${scanState.status === 'done' && !scanState.result.confident && scanState.result.memberId ? s.formInputUncertain : ''}`}
                              placeholder="e.g. XYZ123456789"
                              value={newMemberId}
                              onChange={(e) => setNewMemberId(e.target.value)}
                            />
                          </div>
                          <div className={s.formField}>
                            <label className={s.checkboxLabel}>
                              <input
                                type="checkbox"
                                checked={newIsPrimary}
                                onChange={(e) => setNewIsPrimary(e.target.checked)}
                              />
                              Primary insurance
                            </label>
                          </div>
                        </div>

                        {newPlanType === 'commercial' && (
                          <p className={s.planHint}>
                            Use the plan name as it appears on your insurance card — it&apos;s used to
                            look up your insurer&apos;s contracted rate in hospital price transparency data.
                          </p>
                        )}

                        <div className={s.formActions}>
                          <button className={s.cancelBtn} onClick={() => { setShowAddPlan(false); setFormError(null); resetScan(); }}>Cancel</button>
                          <button className={s.saveBtn} disabled={addingPlan} onClick={() => void handleAddPlan()}>
                            {addingPlan ? 'Saving…' : 'Save plan'}
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>

          </>
        )}

        {/* CTA */}
        <div className={s.ctaRow}>
          {!canRun && !loadingMembers && (
            <p className={s.ctaNote}>
              {members.length === 0
                ? 'Add yourself above to continue.'
                : !selectedMember
                ? 'Select a member to continue.'
                : 'Add an insurance plan to continue.'}
            </p>
          )}
          <button
            className={s.ctaBtn}
            disabled={!canRun}
            onClick={() => void handleRunAnalysis()}
            style={{ marginLeft: canRun ? 'auto' : undefined }}
          >
            Run Analysis
          </button>
        </div>

      </div>
    </main>
  );
}
