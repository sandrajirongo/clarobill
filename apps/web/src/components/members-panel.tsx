'use client';

import { useState, useEffect, useCallback } from 'react';
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
import { CameraIcon } from '@/components/icons';
import s from '@/app/dashboard/dashboard.module.css';

interface InsurancePlan {
  id: string;
  profile_member_id: string;
  payer_name: string;
  plan_name: string;
  member_id: string | null;
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

export function MembersPanel(): JSX.Element {
  const [members, setMembers] = useState<ProfileMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddMember, setShowAddMember] = useState(false);
  const [addingPlanFor, setAddingPlanFor] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Add member form state
  const [newName, setNewName] = useState('');
  const [newDob, setNewDob] = useState('');
  const [newState, setNewState] = useState('');
  const [newCounty, setNewCounty] = useState('');
  const [newZip, setNewZip] = useState('');

  // Add plan form state — mirrors bill-verification.tsx
  const [newPayer, setNewPayer]           = useState('');
  const [newPlan, setNewPlan]             = useState('');
  const [newPlanType, setNewPlanType]     = useState('commercial');
  const [newMemberId, setNewMemberId]     = useState('');
  const [newMedicaidType, setNewMedicaidType] = useState('');
  const [newMedicaidMCO, setNewMedicaidMCO]   = useState('');
  const [newMedicareType, setNewMedicareType] = useState('');
  const [newMedicareMAName, setNewMedicareMAName] = useState('');
  const [newTricareType, setNewTricareType]   = useState('');
  const [newIsPrimary, setNewIsPrimary]   = useState(false);

  const { scanState, inputRef: cardInputRef, openFilePicker, handleFile, reset: resetScan } = useCardScan();

  const loadMembers = useCallback(async (): Promise<void> => {
    const res = await fetch('/api/profile/members');
    if (res.ok) {
      const { members: data } = await res.json() as { members: ProfileMember[] };
      setMembers(data);
    }
    setLoading(false);
  }, []);

  useEffect(() => { void loadMembers(); }, [loadMembers]);

  // Pre-fill plan form from card scan result
  useEffect(() => {
    if (scanState.status !== 'done') return;
    const r = scanState.result;
    if (r.payerName) setNewPayer(r.payerName);
    if (r.planName)  setNewPlan(r.planName);
    if (r.planType)  setNewPlanType(r.planType);
    if (r.memberId)  setNewMemberId(r.memberId);
  }, [scanState]);

  function resetPlanForm(): void {
    setNewPayer(''); setNewPlan(''); setNewPlanType('commercial'); setNewMemberId('');
    setNewMedicaidType(''); setNewMedicaidMCO('');
    setNewMedicareType(''); setNewMedicareMAName('');
    setNewTricareType(''); setNewIsPrimary(false);
    resetScan();
  }

  async function handleAddMember(): Promise<void> {
    if (!newName.trim() || !newDob) {
      setError('Name and date of birth are required.');
      return;
    }
    setSaving(true);
    setError(null);
    const res = await fetch('/api/profile/members', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fullName: newName,
        dateOfBirth: newDob,
        state: newState || null,
        county: newCounty || null,
        zipCode: newZip || null,
        isPrimary: members.length === 0,
      }),
    });
    setSaving(false);
    if (!res.ok) {
      setError('Failed to add member. Please try again.');
      return;
    }
    setNewName(''); setNewDob(''); setNewState(''); setNewCounty(''); setNewZip('');
    setShowAddMember(false);
    void loadMembers();
  }

  async function handleDeleteMember(memberId: string): Promise<void> {
    if (!confirm('Delete this member and all their insurance plans?')) return;
    await fetch(`/api/profile/members/${memberId}`, { method: 'DELETE' });
    void loadMembers();
  }

  async function handleAddPlan(memberId: string): Promise<void> {
    const isGovPlan = newPlanType !== 'commercial';
    if (!isGovPlan && (!newPayer.trim() || !newPlan.trim())) {
      setError('Insurer name and plan name are required.');
      return;
    }
    setSaving(true);
    setError(null);

    // Derive the most specific payer_name and plan_name from sub-type selections.
    // The API fills defaults for anything left null, but these give better analysis context.
    let resolvedPayerName = newPayer.trim() || null;
    let resolvedPlanName  = newPlan.trim()  || null;

    const member = members.find((m) => m.id === memberId);
    if (newPlanType === 'medicaid') {
      const brand = getMedicaidBrandName(member?.state);
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

    const res = await fetch(`/api/profile/members/${memberId}/plans`, {
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
    setSaving(false);
    if (!res.ok) {
      setError('Failed to add plan. Please try again.');
      return;
    }
    resetPlanForm();
    setAddingPlanFor(null);
    void loadMembers();
  }

  async function handleDeletePlan(planId: string): Promise<void> {
    await fetch(`/api/profile/plans/${planId}`, { method: 'DELETE' });
    void loadMembers();
  }

  const countiesForNewState = newState ? (COUNTIES_BY_STATE[newState] ?? []) : [];

  if (loading) {
    return (
      <div className={s.card}>
        <div className={s.cardHeader}><p className={s.cardTitle}>Members & Insurance</p></div>
        <div className={s.cardBody}><p className={s.emptyText}>Loading…</p></div>
      </div>
    );
  }

  return (
    <div className={s.card}>
      <div className={s.cardHeader}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <p className={s.cardTitle}>Members & Insurance</p>
          {!showAddMember && (
            <button onClick={() => { setShowAddMember(true); setError(null); }} className={s.addBtn}>
              + Add member
            </button>
          )}
        </div>
        <p style={{ fontSize: '.78rem', color: 'var(--txt3)', marginTop: '.3rem' }}>
          Add yourself and any dependents. We use your insurance details to find your insurer's exact contracted rates.
        </p>
      </div>

      <div className={s.cardBody}>
        {error && <p className={s.formError}>{error}</p>}

        {members.length === 0 && !showAddMember && (
          <p className={s.emptyText}>No members yet. Add yourself to enable negotiated-rate analysis.</p>
        )}

        {members.map((member) => {
          const isAddingPlan = addingPlanFor === member.id;
          const dobFormatted = new Date(member.date_of_birth + 'T00:00:00').toLocaleDateString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric',
          });
          const locationParts = [member.county, member.state].filter(Boolean);

          return (
            <div key={member.id} className={s.memberCard}>
              <div className={s.memberHeader}>
                <div style={{ minWidth: 0 }}>
                  <p className={s.memberName}>
                    {member.full_name}
                    {member.is_primary && <span className={s.primaryBadge}>Primary</span>}
                  </p>
                  <p className={s.memberMeta}>
                    DOB {dobFormatted}
                    {locationParts.length > 0 && ` · ${locationParts.join(', ')}`}
                    {member.zip_code && ` ${member.zip_code}`}
                  </p>
                </div>
                <button
                  onClick={() => handleDeleteMember(member.id)}
                  className={s.removeBtn}
                  aria-label="Remove member"
                >✕</button>
              </div>

              {/* Insurance plans list */}
              <div className={s.plansSection}>
                {member.insurance_plans.length > 0 ? (
                  <div className={s.plansList}>
                    {member.insurance_plans.map((plan) => (
                      <div key={plan.id} className={s.planRow}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <span className={s.planPayer}>{plan.payer_name}</span>
                          <span className={s.planName}> · {plan.plan_name}</span>
                          {plan.is_primary_plan
                            ? <span className={s.planPrimaryBadge}>Primary</span>
                            : member.insurance_plans.length > 1
                            ? <span className={s.planSecondaryBadge}>Secondary</span>
                            : null}
                          {plan.member_id && <span className={s.planMemberId}>ID: {plan.member_id}</span>}
                        </div>
                        <button
                          onClick={() => handleDeletePlan(plan.id)}
                          className={s.removeBtn}
                          aria-label="Remove plan"
                        >✕</button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className={s.noPlansText}>No insurance plans yet</p>
                )}

                {/* ── Add plan form ──────────────────────────────────────── */}
                {!isAddingPlan ? (
                  <button
                    onClick={() => {
                      setAddingPlanFor(member.id);
                      setError(null);
                      setNewIsPrimary(member.insurance_plans.length === 0);
                    }}
                    className={s.addPlanBtn}
                  >
                    + Add insurance plan
                  </button>
                ) : (
                  <div className={s.inlineForm}>
                    {/* Header: title + scan button */}
                    <div className={s.inlineFormHeader}>
                      <p className={s.inlineFormTitle}>Add insurance plan</p>
                      <button
                        type="button"
                        className={s.scanBtn}
                        onClick={openFilePicker}
                        disabled={scanState.status === 'scanning'}
                      >
                        <CameraIcon size={13} />
                        {scanState.status === 'scanning' ? 'Reading card\u2026' : 'Scan or upload card'}
                      </button>
                    </div>

                    {/* No capture attribute — lets user choose between camera and gallery */}
                    <input
                      ref={cardInputRef}
                      type="file"
                      accept="image/*,application/pdf"
                      style={{ display: 'none' }}
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleFile(f); }}
                    />

                    {/* Scan status */}
                    {scanState.status === 'error' && (
                      <p className={s.scanError}>{scanState.message}</p>
                    )}
                    {scanState.status === 'done' && (
                      scanState.result.confident
                        ? <p className={s.scanSuccess}>Card read — fields auto-filled. Review before saving.</p>
                        : <p className={s.scanWarn}>Card read with low confidence — please review all fields carefully.</p>
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
                          <option value="medicaid">{getMedicaidBrandName(member.state)} (Medicaid)</option>
                          <option value="tricare">TRICARE / Military</option>
                          <option value="self_pay">Self-Pay / Uninsured</option>
                        </select>
                      </div>
                    </div>

                    {/* Medicare sub-types */}
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

                    {/* Medicare Advantage: insurer + plan name */}
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

                    {/* Medicaid Managed Care: MCO name with state autocomplete */}
                    {newPlanType === 'medicaid' && newMedicaidType === 'Medicaid Managed Care' && (
                      <div className={s.formRow}>
                        <div className={s.formField}>
                          <label className={s.formLabel}>Health plan / MCO <span className={s.optionalTag}>(optional)</span></label>
                          <input
                            className={s.formInput}
                            list="panel-mco-suggestions"
                            placeholder={member.state ? `Plans in ${member.state}…` : 'Start typing your plan name…'}
                            value={newMedicaidMCO}
                            onChange={(e) => setNewMedicaidMCO(e.target.value)}
                          />
                          <datalist id="panel-mco-suggestions">
                            {(MEDICAID_MCOS_BY_STATE[member.state ?? ''] ?? MEDICAID_MCOS_NATIONAL).map((mco) => (
                              <option key={mco} value={mco} />
                            ))}
                          </datalist>
                        </div>
                      </div>
                    )}

                    {/* TRICARE sub-types */}
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

                    {/* Commercial: payer + plan name required */}
                    {newPlanType === 'commercial' && (
                      <div className={s.formRow}>
                        <div className={s.formField}>
                          <label className={s.formLabel}>Insurance company *</label>
                          <input
                            className={`${s.formInput}${scanState.status === 'done' && !scanState.result.confident && scanState.result.payerName ? ` ${s.formInputUncertain}` : ''}`}
                            placeholder="e.g. Blue Cross Blue Shield"
                            value={newPayer}
                            onChange={(e) => setNewPayer(e.target.value)}
                          />
                        </div>
                        <div className={s.formField}>
                          <label className={s.formLabel}>Plan name *</label>
                          <input
                            className={`${s.formInput}${scanState.status === 'done' && !scanState.result.confident && scanState.result.planName ? ` ${s.formInputUncertain}` : ''}`}
                            placeholder="e.g. PPO Gold"
                            value={newPlan}
                            onChange={(e) => setNewPlan(e.target.value)}
                          />
                        </div>
                      </div>
                    )}

                    {/* Member ID + isPrimary */}
                    <div className={s.formRow}>
                      <div className={s.formField}>
                        <label className={s.formLabel}>Member ID <span className={s.optionalTag}>(for dispute letters)</span></label>
                        <input
                          className={`${s.formInput}${scanState.status === 'done' && !scanState.result.confident && scanState.result.memberId ? ` ${s.formInputUncertain}` : ''}`}
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

                    <div className={s.formActions}>
                      <button
                        onClick={() => { setAddingPlanFor(null); resetPlanForm(); setError(null); }}
                        className={s.cancelBtn}
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => void handleAddPlan(member.id)}
                        disabled={saving}
                        className={s.saveBtn}
                      >
                        {saving ? 'Saving…' : 'Save plan'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Add member form */}
        {showAddMember && (
          <div className={s.inlineForm}>
            <p className={s.inlineFormTitle}>Add member</p>
            <div className={s.formRow}>
              <div className={s.formField} style={{ flex: 2 }}>
                <label className={s.formLabel}>Full name *</label>
                <input
                  className={s.formInput}
                  placeholder="e.g. Jane Smith"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  autoFocus
                />
              </div>
              <div className={s.formField}>
                <label className={s.formLabel}>Date of birth *</label>
                <input
                  type="date"
                  className={s.formInput}
                  value={newDob}
                  onChange={(e) => setNewDob(e.target.value)}
                />
              </div>
            </div>
            <div className={s.formRow}>
              <div className={s.formField}>
                <label className={s.formLabel}>State <span className={s.optionalTag}>(for rate lookup)</span></label>
                <select
                  className={s.formSelect}
                  value={newState}
                  onChange={(e) => { setNewState(e.target.value); setNewCounty(''); }}
                >
                  <option value="">Select state…</option>
                  {US_STATES.map((st) => <option key={st} value={st}>{st}</option>)}
                </select>
              </div>
              {countiesForNewState.length > 0 && (
                <div className={s.formField}>
                  <label className={s.formLabel}>County <span className={s.optionalTag}>(optional)</span></label>
                  <select
                    className={s.formSelect}
                    value={newCounty}
                    onChange={(e) => setNewCounty(e.target.value)}
                  >
                    <option value="">Select county…</option>
                    {countiesForNewState.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              )}
              <div className={s.formField}>
                <label className={s.formLabel}>ZIP code <span className={s.optionalTag}>(optional)</span></label>
                <input
                  className={s.formInput}
                  placeholder="5-digit ZIP"
                  maxLength={5}
                  value={newZip}
                  onChange={(e) => setNewZip(e.target.value.replace(/\D/g, ''))}
                />
              </div>
            </div>
            <div className={s.formActions}>
              <button
                onClick={() => { setShowAddMember(false); setNewName(''); setNewDob(''); setNewState(''); setNewCounty(''); setNewZip(''); setError(null); }}
                className={s.cancelBtn}
              >
                Cancel
              </button>
              <button onClick={handleAddMember} disabled={saving} className={s.saveBtn}>
                {saving ? 'Saving…' : 'Save member'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
