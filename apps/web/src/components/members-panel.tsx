'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { US_STATES, COUNTIES_BY_STATE } from '@/lib/utils/county-data';
import {
  getMedicaidBrandName,
  MEDICAID_PLAN_TYPES,
  MEDICAID_MCOS_BY_STATE,
  MEDICAID_MCOS_NATIONAL,
  MEDICARE_PLAN_TYPES,
  TRICARE_PLAN_TYPES,
} from '@/lib/utils/insurance-constants';
import { CardScanner } from '@/components/card-scanner';
import type { InsuranceCardExtraction } from '@/lib/api/parsers';
import { CameraIcon, PencilIcon } from '@/components/icons';
import s from '@/app/dashboard/dashboard.module.css';

// M10: shared camelCase types instead of snake_case redeclarations.
// API routes pass their rows through mapProfileMemberWithPlans + mapInsurancePlan.
import type { InsurancePlan } from '@clarobill/shared';
import type { ProfileMemberWithPlans as ProfileMember } from '@/lib/api/mappers';
import { MembersListResponseSchema, parseJsonResponse } from '@/lib/api/parsers';

export function MembersPanel(): JSX.Element {
  const t = useTranslations('profile.members');
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

  // Edit member form state
  const [editingMemberId, setEditingMemberId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editDob, setEditDob] = useState('');
  const [editState, setEditState] = useState('');
  const [editCounty, setEditCounty] = useState('');
  const [editZip, setEditZip] = useState('');

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

  // Edit plan form state
  const [editingPlanId, setEditingPlanId] = useState<string | null>(null);
  const [editPayerName, setEditPayerName] = useState('');
  const [editPlanName, setEditPlanName]   = useState('');
  const [editPlanType, setEditPlanType]   = useState('commercial');
  const [editMemberIdField, setEditMemberIdField] = useState('');
  const [editIsPrimary, setEditIsPrimary] = useState(false);

  const [showScanner, setShowScanner] = useState(false);
  const [lastScan, setLastScan] = useState<{ confident: boolean; note: string | null } | null>(null);

  const loadMembers = useCallback(async (): Promise<void> => {
    const res = await fetch('/api/profile/members');
    if (res.ok) {
      const { members: rawMembers } = await parseJsonResponse(res, MembersListResponseSchema);
      // Inner shape is now camelCase ProfileMemberWithPlans (M10) — the API
      // route runs every row through mapProfileMemberWithPlans before
      // returning, so casting here just narrows the wrapper-validated type.
      setMembers(rawMembers as ProfileMember[]);
    }
    setLoading(false);
  }, []);

  useEffect(() => { void loadMembers(); }, [loadMembers]);

  function handleScanExtracted(result: InsuranceCardExtraction): void {
    if (result.payerName) setNewPayer(result.payerName);
    if (result.planName)  setNewPlan(result.planName);
    if (result.planType)  setNewPlanType(result.planType);
    if (result.memberId)  setNewMemberId(result.memberId);

    if (result.planType === 'medicare' && result.planName) {
      const lower = result.planName.toLowerCase();
      if (lower.includes('advantage') || lower.includes('part c')) {
        setNewMedicareType('Medicare Advantage (Part C)');
        if (result.payerName) setNewMedicareMAName(result.payerName);
      }
    }

    if (result.planType === 'tricare' && result.planName) {
      const matched = TRICARE_PLAN_TYPES.find(
        (pt) => result.planName!.toLowerCase().includes(pt.value.toLowerCase())
      );
      if (matched) setNewTricareType(matched.value);
    }

    setLastScan({ confident: result.confident, note: result.note ?? null });
    setShowScanner(false);
  }

  function resetPlanForm(): void {
    setNewPayer(''); setNewPlan(''); setNewPlanType('commercial'); setNewMemberId('');
    setNewMedicaidType(''); setNewMedicaidMCO('');
    setNewMedicareType(''); setNewMedicareMAName('');
    setNewTricareType(''); setNewIsPrimary(false);
    setLastScan(null);
  }

  async function handleAddMember(): Promise<void> {
    if (!newName.trim() || !newDob) {
      setError(t('errorNameRequired'));
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
      setError(t('errorMemberFailed'));
      return;
    }
    setNewName(''); setNewDob(''); setNewState(''); setNewCounty(''); setNewZip('');
    setShowAddMember(false);
    void loadMembers();
  }

  function startEditMember(member: ProfileMember): void {
    setEditingMemberId(member.id);
    setEditName(member.fullName);
    setEditDob(member.dateOfBirth);
    setEditState(member.state ?? '');
    setEditCounty(member.county ?? '');
    setEditZip(member.zipCode ?? '');
    setError(null);
  }

  async function handleSaveMember(memberId: string): Promise<void> {
    if (!editName.trim() || !editDob) {
      setError(t('errorNameRequired'));
      return;
    }
    setSaving(true);
    setError(null);
    const res = await fetch(`/api/profile/members/${memberId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fullName: editName,
        dateOfBirth: editDob,
        state: editState || null,
        county: editCounty || null,
        zipCode: editZip || null,
      }),
    });
    setSaving(false);
    if (!res.ok) {
      setError(t('errorMemberFailed'));
      return;
    }
    setEditingMemberId(null);
    void loadMembers();
  }

  async function handleDeleteMember(memberId: string): Promise<void> {
    if (!confirm(t('deleteConfirm'))) return;
    await fetch(`/api/profile/members/${memberId}`, { method: 'DELETE' });
    void loadMembers();
  }

  function startEditPlan(plan: InsurancePlan): void {
    setEditingPlanId(plan.id);
    setEditPayerName(plan.payerName);
    setEditPlanName(plan.planName);
    setEditPlanType(plan.planType);
    setEditMemberIdField(plan.memberId ?? '');
    setEditIsPrimary(plan.isPrimaryPlan);
    setError(null);
  }

  async function handleSavePlan(planId: string): Promise<void> {
    setSaving(true);
    setError(null);
    const res = await fetch(`/api/profile/plans/${planId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        payerName: editPayerName,
        planName: editPlanName,
        planType: editPlanType,
        memberId: editMemberIdField || null,
        isPrimaryPlan: editIsPrimary,
      }),
    });
    setSaving(false);
    if (!res.ok) {
      setError(t('errorPlanFailed'));
      return;
    }
    setEditingPlanId(null);
    void loadMembers();
  }

  async function handleAddPlan(memberId: string): Promise<void> {
    const isGovPlan = newPlanType !== 'commercial';
    if (!isGovPlan && (!newPayer.trim() || !newPlan.trim())) {
      setError(t('errorPlanRequired'));
      return;
    }
    setSaving(true);
    setError(null);

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
      setError(t('errorPlanFailed'));
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
  const countiesForEditState = editState ? (COUNTIES_BY_STATE[editState] ?? []) : [];

  if (loading) {
    return (
      <div className={s.card}>
        <div className={s.cardHeader}><p className={s.cardTitle}>{t('title')}</p></div>
        <div className={s.cardBody}><p className={s.emptyText}>{t('loading')}</p></div>
      </div>
    );
  }

  return (
    <div className={s.card}>
      <div className={s.cardHeader}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <p className={s.cardTitle}>{t('title')}</p>
          {!showAddMember && (
            <button onClick={() => { setShowAddMember(true); setError(null); }} className={s.addBtn}>
              {t('addMember')}
            </button>
          )}
        </div>
        <p style={{ fontSize: '.78rem', color: 'var(--txt3)', marginTop: '.3rem' }}>
          {t('subtitle')}
        </p>
      </div>

      <div className={s.cardBody}>
        {error && <p className={s.formError}>{error}</p>}

        {members.length === 0 && !showAddMember && (
          <p className={s.emptyText}>{t('noMembers')}</p>
        )}

        {members.map((member) => {
          const isAddingPlan = addingPlanFor === member.id;
          const isEditingMember = editingMemberId === member.id;
          const dobFormatted = new Date(member.dateOfBirth + 'T00:00:00').toLocaleDateString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric',
          });
          const locationParts = [member.county, member.state].filter(Boolean);

          return (
            <div key={member.id} className={s.memberCard}>

              {/* ── Member header: display or edit form ─────────────── */}
              {isEditingMember ? (
                <div className={s.inlineForm} style={{ margin: '0', borderRadius: 0, background: 'var(--cream)', padding: '1rem' }}>
                  <p className={s.inlineFormTitle}>{t('editMemberTitle')}</p>
                  <div className={s.formRow}>
                    <div className={s.formField} style={{ flex: 2 }}>
                      <label className={s.formLabel}>{t('fullName')}</label>
                      <input
                        className={s.formInput}
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        autoFocus
                      />
                    </div>
                    <div className={s.formField}>
                      <label className={s.formLabel}>{t('dateOfBirth')}</label>
                      <input
                        type="date"
                        className={s.formInput}
                        value={editDob}
                        onChange={(e) => setEditDob(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className={s.formRow}>
                    <div className={s.formField}>
                      <label className={s.formLabel}>{t('state')} <span className={s.optionalTag}>{t('stateHint')}</span></label>
                      <select
                        className={s.formSelect}
                        value={editState}
                        onChange={(e) => { setEditState(e.target.value); setEditCounty(''); }}
                      >
                        <option value="">{t('selectState')}</option>
                        {US_STATES.map((st) => <option key={st} value={st}>{st}</option>)}
                      </select>
                    </div>
                    {countiesForEditState.length > 0 && (
                      <div className={s.formField}>
                        <label className={s.formLabel}>{t('county')} <span className={s.optionalTag}>{t('countyOptional')}</span></label>
                        <select
                          className={s.formSelect}
                          value={editCounty}
                          onChange={(e) => setEditCounty(e.target.value)}
                        >
                          <option value="">{t('selectCounty')}</option>
                          {countiesForEditState.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      </div>
                    )}
                    <div className={s.formField}>
                      <label className={s.formLabel}>{t('zip')} <span className={s.optionalTag}>{t('countyOptional')}</span></label>
                      <input
                        className={s.formInput}
                        placeholder={t('zipPlaceholder')}
                        maxLength={5}
                        value={editZip}
                        onChange={(e) => setEditZip(e.target.value.replace(/\D/g, ''))}
                      />
                    </div>
                  </div>
                  <div className={s.formActions}>
                    <button
                      onClick={() => { setEditingMemberId(null); setError(null); }}
                      className={s.cancelBtn}
                    >
                      {t('cancel')}
                    </button>
                    <button
                      onClick={() => void handleSaveMember(member.id)}
                      disabled={saving}
                      className={s.saveBtn}
                    >
                      {saving ? t('saving') : t('saveChanges')}
                    </button>
                  </div>
                </div>
              ) : (
                <div className={s.memberHeader}>
                  <div style={{ minWidth: 0 }}>
                    <p className={s.memberName}>
                      {member.fullName}
                      {member.isPrimary && <span className={s.primaryBadge}>{t('primary')}</span>}
                    </p>
                    <p className={s.memberMeta}>
                      {t('dob')} {dobFormatted}
                      {locationParts.length > 0 && ` · ${locationParts.join(', ')}`}
                      {member.zipCode && ` ${member.zipCode}`}
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: '.25rem', flexShrink: 0 }}>
                    <button
                      onClick={() => startEditMember(member)}
                      className={s.editBtn}
                      aria-label="Edit member"
                    >
                      <PencilIcon size={13} />
                    </button>
                    <button
                      onClick={() => handleDeleteMember(member.id)}
                      className={s.removeBtn}
                      aria-label="Remove member"
                    >✕</button>
                  </div>
                </div>
              )}

              {/* ── Insurance plans ──────────────────────────────────── */}
              {!isEditingMember && (
                <div className={s.plansSection}>
                  {member.insurancePlans.length > 0 ? (
                    <div className={s.plansList}>
                      {member.insurancePlans.map((plan) => {
                        const isEditingPlan = editingPlanId === plan.id;

                        if (isEditingPlan) {
                          return (
                            <div key={plan.id} className={s.inlineForm} style={{ margin: '.5rem 0 0', padding: '.85rem 1rem' }}>
                              <p className={s.inlineFormTitle} style={{ marginBottom: '.6rem' }}>{t('editPlanTitle')}</p>
                              <div className={s.formRow}>
                                <div className={s.formField}>
                                  <label className={s.formLabel}>{t('planType')}</label>
                                  <select
                                    className={s.formSelect}
                                    value={editPlanType}
                                    onChange={(e) => setEditPlanType(e.target.value)}
                                  >
                                    <option value="commercial">{t('commercial')}</option>
                                    <option value="medicare">{t('medicare')}</option>
                                    <option value="medicaid">{getMedicaidBrandName(member.state)} (Medicaid)</option>
                                    <option value="tricare">{t('tricare')}</option>
                                    <option value="self_pay">{t('selfPay')}</option>
                                  </select>
                                </div>
                              </div>
                              <div className={s.formRow}>
                                <div className={s.formField}>
                                  <label className={s.formLabel}>{t('insurer')}</label>
                                  <input
                                    className={s.formInput}
                                    value={editPayerName}
                                    onChange={(e) => setEditPayerName(e.target.value)}
                                  />
                                </div>
                                <div className={s.formField}>
                                  <label className={s.formLabel}>{t('planName')}</label>
                                  <input
                                    className={s.formInput}
                                    value={editPlanName}
                                    onChange={(e) => setEditPlanName(e.target.value)}
                                  />
                                </div>
                              </div>
                              <div className={s.formRow}>
                                <div className={s.formField}>
                                  <label className={s.formLabel}>{t('memberId')} <span className={s.optionalTag}>{t('memberIdHint')}</span></label>
                                  <input
                                    className={s.formInput}
                                    value={editMemberIdField}
                                    onChange={(e) => setEditMemberIdField(e.target.value)}
                                  />
                                </div>
                                <div className={s.checkboxField}>
                                  <label className={s.checkboxLabel}>
                                    <input
                                      type="checkbox"
                                      checked={editIsPrimary}
                                      onChange={(e) => setEditIsPrimary(e.target.checked)}
                                    />
                                    {t('primaryInsurance')}
                                  </label>
                                </div>
                              </div>
                              <div className={s.formActions}>
                                <button
                                  onClick={() => { setEditingPlanId(null); setError(null); }}
                                  className={s.cancelBtn}
                                >
                                  {t('cancel')}
                                </button>
                                <button
                                  onClick={() => void handleSavePlan(plan.id)}
                                  disabled={saving}
                                  className={s.saveBtn}
                                >
                                  {saving ? t('saving') : t('saveChanges')}
                                </button>
                              </div>
                            </div>
                          );
                        }

                        return (
                          <div key={plan.id} className={s.planRow}>
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <span className={s.planPayer}>{plan.payerName}</span>
                              <span className={s.planName}> · {plan.planName}</span>
                              {plan.isPrimaryPlan
                                ? <span className={s.planPrimaryBadge}>{t('primary')}</span>
                                : member.insurancePlans.length > 1
                                ? <span className={s.planSecondaryBadge}>{t('secondary')}</span>
                                : null}
                              {plan.memberId && <span className={s.planMemberId}>ID: {plan.memberId}</span>}
                            </div>
                            <div style={{ display: 'flex', gap: '.25rem', flexShrink: 0 }}>
                              <button
                                onClick={() => startEditPlan(plan)}
                                className={s.editBtn}
                                aria-label="Edit plan"
                              >
                                <PencilIcon size={13} />
                              </button>
                              <button
                                onClick={() => handleDeletePlan(plan.id)}
                                className={s.removeBtn}
                                aria-label="Remove plan"
                              >✕</button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className={s.noPlansText}>{t('noPlans')}</p>
                  )}

                  {/* ── Add plan form ──────────────────────────────────────── */}
                  {!isAddingPlan ? (
                    <button
                      onClick={() => {
                        setAddingPlanFor(member.id);
                        setError(null);
                        setNewIsPrimary(member.insurancePlans.length === 0);
                      }}
                      className={s.addPlanBtn}
                    >
                      {t('addPlan')}
                    </button>
                  ) : (
                    <div className={s.inlineForm}>
                      <div className={s.inlineFormHeader}>
                        <p className={s.inlineFormTitle}>{t('addPlanTitle')}</p>
                        <button
                          type="button"
                          className={s.scanBtn}
                          onClick={() => setShowScanner(true)}
                        >
                          <CameraIcon size={13} />
                          {t('scanCard')}
                        </button>
                      </div>

                      {lastScan !== null && (
                        lastScan.confident
                          ? <p className={s.scanSuccess}>{t('scanSuccess')}</p>
                          : <p className={s.scanWarn}>{t('scanWarn')}</p>
                      )}
                      {lastScan?.note && (
                        <p className={s.scanNote}>{lastScan.note}</p>
                      )}

                      <div className={s.formRow}>
                        <div className={s.formField}>
                          <label className={s.formLabel}>{t('planType')}</label>
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
                            <option value="commercial">{t('commercial')}</option>
                            <option value="medicare">{t('medicare')}</option>
                            <option value="medicaid">{getMedicaidBrandName(member.state)} (Medicaid)</option>
                            <option value="tricare">{t('tricare')}</option>
                            <option value="self_pay">{t('selfPay')}</option>
                          </select>
                        </div>
                      </div>

                      {newPlanType === 'medicare' && (
                        <div className={s.formRow}>
                          <div className={s.formField}>
                            <label className={s.formLabel}>{t('medicareType')} <span className={s.optionalTag}>{t('analysisHint')}</span></label>
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

                      {newPlanType === 'medicare' && newMedicareType === 'Medicare Advantage (Part C)' && (
                        <div className={s.formRow}>
                          <div className={s.formField}>
                            <label className={s.formLabel}>{t('maInsurer')}</label>
                            <input
                              className={s.formInput}
                              placeholder={t('maInsurerPlaceholder')}
                              value={newMedicareMAName}
                              onChange={(e) => setNewMedicareMAName(e.target.value)}
                            />
                          </div>
                          <div className={s.formField}>
                            <label className={s.formLabel}>{t('planName')} <span className={s.optionalTag}>{t('optional')}</span></label>
                            <input
                              className={s.formInput}
                              placeholder={t('planNamePlaceholder')}
                              value={newPlan}
                              onChange={(e) => setNewPlan(e.target.value)}
                            />
                          </div>
                        </div>
                      )}

                      {newPlanType === 'medicaid' && (
                        <div className={s.formRow}>
                          <div className={s.formField}>
                            <label className={s.formLabel}>{t('medicaidProgram')} <span className={s.optionalTag}>{t('analysisHint')}</span></label>
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

                      {newPlanType === 'medicaid' && newMedicaidType === 'Medicaid Managed Care' && (
                        <div className={s.formRow}>
                          <div className={s.formField}>
                            <label className={s.formLabel}>{t('medicaidMCO')} <span className={s.optionalTag}>{t('optional')}</span></label>
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

                      {newPlanType === 'tricare' && (
                        <div className={s.formRow}>
                          <div className={s.formField}>
                            <label className={s.formLabel}>{t('tricareProgram')} <span className={s.optionalTag}>{t('optional')}</span></label>
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

                      {newPlanType === 'commercial' && (
                        <div className={s.formRow}>
                          <div className={s.formField}>
                            <label className={s.formLabel}>{t('insurer')}</label>
                            <input
                              className={`${s.formInput}${lastScan !== null && !lastScan.confident && newPayer ? ` ${s.formInputUncertain}` : ''}`}
                              placeholder={t('insurerPlaceholder')}
                              value={newPayer}
                              onChange={(e) => setNewPayer(e.target.value)}
                            />
                          </div>
                          <div className={s.formField}>
                            <label className={s.formLabel}>{t('planName')} *</label>
                            <input
                              className={`${s.formInput}${lastScan !== null && !lastScan.confident && newPlan ? ` ${s.formInputUncertain}` : ''}`}
                              placeholder="e.g. PPO Gold"
                              value={newPlan}
                              onChange={(e) => setNewPlan(e.target.value)}
                            />
                          </div>
                        </div>
                      )}

                      <div className={s.formRow}>
                        <div className={s.formField}>
                          <label className={s.formLabel}>{t('memberId')} <span className={s.optionalTag}>{t('memberIdHint')}</span></label>
                          <input
                            className={`${s.formInput}${lastScan !== null && !lastScan.confident && newMemberId ? ` ${s.formInputUncertain}` : ''}`}
                            placeholder={t('memberIdPlaceholder')}
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
                            {t('primaryInsurance')}
                          </label>
                        </div>
                      </div>

                      <div className={s.formActions}>
                        <button
                          onClick={() => { setAddingPlanFor(null); resetPlanForm(); setError(null); }}
                          className={s.cancelBtn}
                        >
                          {t('cancel')}
                        </button>
                        <button
                          onClick={() => void handleAddPlan(member.id)}
                          disabled={saving}
                          className={s.saveBtn}
                        >
                          {saving ? t('saving') : t('savePlan')}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {/* Add member form */}
        {showAddMember && (
          <div className={s.inlineForm}>
            <p className={s.inlineFormTitle}>{t('addMemberTitle')}</p>
            <div className={s.formRow}>
              <div className={s.formField} style={{ flex: 2 }}>
                <label className={s.formLabel}>{t('fullName')}</label>
                <input
                  className={s.formInput}
                  placeholder={t('fullNamePlaceholder')}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  autoFocus
                />
              </div>
              <div className={s.formField}>
                <label className={s.formLabel}>{t('dateOfBirth')}</label>
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
                <label className={s.formLabel}>{t('state')} <span className={s.optionalTag}>{t('stateHint')}</span></label>
                <select
                  className={s.formSelect}
                  value={newState}
                  onChange={(e) => { setNewState(e.target.value); setNewCounty(''); }}
                >
                  <option value="">{t('selectState')}</option>
                  {US_STATES.map((st) => <option key={st} value={st}>{st}</option>)}
                </select>
              </div>
              {countiesForNewState.length > 0 && (
                <div className={s.formField}>
                  <label className={s.formLabel}>{t('county')} <span className={s.optionalTag}>{t('countyOptional')}</span></label>
                  <select
                    className={s.formSelect}
                    value={newCounty}
                    onChange={(e) => setNewCounty(e.target.value)}
                  >
                    <option value="">{t('selectCounty')}</option>
                    {countiesForNewState.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              )}
              <div className={s.formField}>
                <label className={s.formLabel}>{t('zip')} <span className={s.optionalTag}>{t('countyOptional')}</span></label>
                <input
                  className={s.formInput}
                  placeholder={t('zipPlaceholder')}
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
                {t('cancel')}
              </button>
              <button onClick={handleAddMember} disabled={saving} className={s.saveBtn}>
                {saving ? t('saving') : t('saveMember')}
              </button>
            </div>
          </div>
        )}
      </div>

      {showScanner && (
        <CardScanner
          onExtracted={handleScanExtracted}
          onClose={() => setShowScanner(false)}
          labels={{
            hint: t('scanner.hint'),
            hintLocked: t('scanner.hintLocked'),
            hintStarting: t('scanner.hintStarting'),
            capturing: t('scanner.capturing'),
            autoCapturing: t('scanner.autoCapturing'),
            holdOrTap: t('scanner.holdOrTap'),
            uploadPhoto: t('scanner.uploadPhoto'),
            tryAgain: t('scanner.tryAgain'),
            cancel: t('cancel'),
            permissionDenied: t('scanner.permissionDenied'),
            confirmTitle: t('scanner.confirmTitle'),
            confirmSubtitle: t('scanner.confirmSubtitle'),
            confirmInsurer: t('scanner.confirmInsurer'),
            confirmPlan: t('scanner.confirmPlan'),
            confirmMemberId: t('scanner.confirmMemberId'),
            confirmGroupId: t('scanner.confirmGroupId'),
            confirmPlanType: t('scanner.confirmPlanType'),
            confirmRxBin: t('scanner.confirmRxBin'),
            confirmBtn: t('scanner.confirmBtn'),
            retakeBtn: t('scanner.retakeBtn'),
            notDetected: t('scanner.notDetected'),
            lowConfidence: t('scanner.lowConfidence'),
            scanFailed: t('scanner.scanFailed'),
            imageTooLarge: t('scanner.imageTooLarge'),
          }}
        />
      )}
    </div>
  );
}
