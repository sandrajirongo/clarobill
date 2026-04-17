'use client';

import { useState, useEffect, useCallback } from 'react';
import { US_STATES, COUNTIES_BY_STATE } from '@/lib/utils/county-data';
import s from '@/app/dashboard/dashboard.module.css';

const PLAN_TYPE_LABELS: Record<string, string> = {
  commercial: 'Commercial',
  medicare: 'Medicare',
  medicaid: 'Medicaid',
  tricare: 'TRICARE',
  self_pay: 'Self-Pay',
};

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

  // Add plan form state
  const [newPayer, setNewPayer] = useState('');
  const [newPlan, setNewPlan] = useState('');
  const [newPlanType, setNewPlanType] = useState('commercial');
  const [newMemberId, setNewMemberId] = useState('');

  const loadMembers = useCallback(async (): Promise<void> => {
    const res = await fetch('/api/profile/members');
    if (res.ok) {
      const { members: data } = await res.json() as { members: ProfileMember[] };
      setMembers(data);
    }
    setLoading(false);
  }, []);

  useEffect(() => { void loadMembers(); }, [loadMembers]);

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
    if (!newPayer.trim() || !newPlan.trim()) {
      setError('Insurer name and plan name are required.');
      return;
    }
    setSaving(true);
    setError(null);
    const res = await fetch(`/api/profile/members/${memberId}/plans`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        payerName: newPayer,
        planName: newPlan,
        planType: newPlanType,
        memberId: newMemberId || null,
        isPrimaryPlan: false,
      }),
    });
    setSaving(false);
    if (!res.ok) {
      setError('Failed to add plan. Please try again.');
      return;
    }
    setNewPayer(''); setNewPlan(''); setNewPlanType('commercial'); setNewMemberId('');
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
            <button
              onClick={() => { setShowAddMember(true); setError(null); }}
              className={s.addBtn}
            >
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
          <p className={s.emptyText}>
            No members yet. Add yourself to enable negotiated-rate analysis.
          </p>
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
                >
                  ✕
                </button>
              </div>

              {/* Insurance plans */}
              <div className={s.plansSection}>
                {member.insurance_plans.length > 0 ? (
                  <div className={s.plansList}>
                    {member.insurance_plans.map((plan) => (
                      <div key={plan.id} className={s.planRow}>
                        <div style={{ minWidth: 0 }}>
                          <span className={s.planPayer}>{plan.payer_name}</span>
                          <span className={s.planName}> · {plan.plan_name}</span>
                          <span className={s.planTypeBadge}>{PLAN_TYPE_LABELS[plan.plan_type] ?? plan.plan_type}</span>
                          {plan.member_id && (
                            <span className={s.planMemberId}>ID: {plan.member_id}</span>
                          )}
                        </div>
                        <button
                          onClick={() => handleDeletePlan(plan.id)}
                          className={s.removeBtn}
                          aria-label="Remove plan"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className={s.noPlansText}>No insurance plans yet</p>
                )}

                {!isAddingPlan ? (
                  <button
                    onClick={() => { setAddingPlanFor(member.id); setError(null); }}
                    className={s.addPlanBtn}
                  >
                    + Add insurance plan
                  </button>
                ) : (
                  <div className={s.inlineForm}>
                    <p className={s.inlineFormTitle}>Add insurance plan</p>
                    <div className={s.formRow}>
                      <div className={s.formField}>
                        <label className={s.formLabel}>Insurance company *</label>
                        <input
                          className={s.formInput}
                          placeholder="e.g. Blue Cross Blue Shield"
                          value={newPayer}
                          onChange={(e) => setNewPayer(e.target.value)}
                        />
                      </div>
                      <div className={s.formField}>
                        <label className={s.formLabel}>Plan name *</label>
                        <input
                          className={s.formInput}
                          placeholder="e.g. PPO Gold"
                          value={newPlan}
                          onChange={(e) => setNewPlan(e.target.value)}
                        />
                      </div>
                    </div>
                    <div className={s.formRow}>
                      <div className={s.formField}>
                        <label className={s.formLabel}>Plan type</label>
                        <select
                          className={s.formSelect}
                          value={newPlanType}
                          onChange={(e) => setNewPlanType(e.target.value)}
                        >
                          {Object.entries(PLAN_TYPE_LABELS).map(([v, l]) => (
                            <option key={v} value={v}>{l}</option>
                          ))}
                        </select>
                      </div>
                      <div className={s.formField}>
                        <label className={s.formLabel}>Member ID <span className={s.optionalTag}>(optional)</span></label>
                        <input
                          className={s.formInput}
                          placeholder="For dispute letters"
                          value={newMemberId}
                          onChange={(e) => setNewMemberId(e.target.value)}
                        />
                      </div>
                    </div>
                    <div className={s.formActions}>
                      <button
                        onClick={() => { setAddingPlanFor(null); setNewPayer(''); setNewPlan(''); setNewPlanType('commercial'); setNewMemberId(''); setError(null); }}
                        className={s.cancelBtn}
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => handleAddPlan(member.id)}
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
                  {US_STATES.map((st) => (
                    <option key={st} value={st}>{st}</option>
                  ))}
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
                    {countiesForNewState.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
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
              <button
                onClick={handleAddMember}
                disabled={saving}
                className={s.saveBtn}
              >
                {saving ? 'Saving…' : 'Save member'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
