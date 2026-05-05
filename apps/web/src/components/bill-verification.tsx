'use client';

import Link from 'next/link';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { US_STATES, COUNTIES_BY_STATE } from '@/lib/utils/county-data';
import {
  getMedicaidBrandName,
  MEDICAID_PLAN_TYPES,
  MEDICAID_MCOS_BY_STATE,
  MEDICAID_MCOS_NATIONAL,
  MEDICARE_PLAN_TYPES,
  TRICARE_PLAN_TYPES,
} from '@/lib/utils/insurance-constants';
import { useCardScan } from '@/lib/hooks/use-card-scan';
import {
  ErrorResponseSchema,
  MemberCreatedResponseSchema,
  MembersListResponseSchema,
  PlanCreatedResponseSchema,
  StatusResponseSchema,
  parseJsonResponse,
} from '@/lib/api/parsers';
import { CameraIcon } from '@/components/icons';
import s from './bill-verification.module.css';

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
    const { members: rawMembers } = await parseJsonResponse(res, MembersListResponseSchema);
    // Inner shape is locally-typed snake_case ProfileMember (M10 territory:
    // converting to camelCase happens in a later commit alongside the API
    // route that produces the response).
    const data = rawMembers as ProfileMember[];
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
    const { member } = await parseJsonResponse(res, MemberCreatedResponseSchema);
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
    const { plan } = await parseJsonResponse(res, PlanCreatedResponseSchema);
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
          const { status } = await parseJsonResponse(res, StatusResponseSchema);
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
      const { error } = await parseJsonResponse(res, ErrorResponseSchema);
      setPhase('error'); setErrorMsg(error?.detail ?? 'Something went wrong. Please try again.');
      return;
    }
    await poll();
  }

  // ── Analyzing screen ─────────────────────────────────────────────────────
  const ANALYSIS_STEPS = [
    'Reading your bill',
    'Extracting charge codes',
    'Running pricing checks',
    'Running coding checks',
    'Scanning for duplicate charges',
    'Finalizing your report',
  ];

  if (phase === 'analyzing') {
    return (
      <main className={s.main}>
        <div className={s.inner}>
          <div className={s.analyzingWrap}>
            <p className={s.analyzingTitle}>Analyzing your bill…</p>
            <p className={s.analyzingNote}>Running 10 billing checks. This takes a few minutes.</p>
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
            We run every line through our billing-error checks. This takes a few minutes. Just
            tell us who this bill is for.
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
                            <CameraIcon size={13} />
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
                          <p className={s.scanWarn}>Some fields may be uncertain. Please review before saving.</p>
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
                                  ? `Plans in ${selectedMember.state}. Start typing…`
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
                          <div className={s.checkboxField}>
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
                            Use the plan name as it appears on your insurance card. It helps us
                            tailor the audit to your coverage.
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
