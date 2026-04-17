/**
 * Shared insurance plan type constants.
 *
 * Used in both the pre-analysis verification flow (bill-verification.tsx)
 * and the profile plan management panel (members-panel.tsx). Keep these in
 * sync with the plan_type CHECK constraint in the insurance_plans table.
 */

// ─── Medicaid ────────────────────────────────────────────────────────────────

/**
 * States with distinct brand names for their Medicaid program.
 * For all other states we render "[State] Medicaid" in the UI.
 */
export const MEDICAID_STATE_BRANDS: Record<string, string> = {
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

export function getMedicaidBrandName(state: string | null | undefined): string {
  if (!state) return 'Medicaid';
  return MEDICAID_STATE_BRANDS[state] ?? `${state} Medicaid`;
}

/**
 * Medicaid program delivery types. Fee-for-Service uses the published state
 * fee schedule; Managed Care uses MCO-negotiated rates.
 */
export const MEDICAID_PLAN_TYPES: { value: string; label: string }[] = [
  { value: 'Fee-for-Service Medicaid',            label: 'Fee-for-Service — state pays providers directly'        },
  { value: 'Medicaid Managed Care',               label: 'Managed Care — private MCO manages your coverage'      },
  { value: 'CHIP',                                label: 'CHIP — Children\'s Health Insurance Program'            },
  { value: 'Dual Eligible (Medicare + Medicaid)', label: 'Dual Eligible — both Medicare and Medicaid cover you'  },
  { value: 'Long-Term Services and Supports',     label: 'Long-Term Care / LTSS waiver'                          },
  { value: 'Medicaid Home & Community Waiver',    label: 'Home & Community-Based Services waiver'                },
];

/**
 * Major MCOs active in each state for Medicaid Managed Care autocomplete.
 * Users in unlisted states fall back to MEDICAID_MCOS_NATIONAL.
 */
export const MEDICAID_MCOS_BY_STATE: Record<string, string[]> = {
  'California':     ['L.A. Care Health Plan', 'Health Net Medi-Cal', 'Molina Healthcare of California', 'Anthem Blue Cross', 'Kaiser Permanente', 'IEHP (Inland Empire)', 'CalOptima', 'Alameda Alliance'],
  'Texas':          ['Molina Healthcare', 'UnitedHealthcare Community Plan', 'Superior HealthPlan (Centene)', 'Aetna Better Health of Texas', 'BCBS of Texas'],
  'New York':       ['Fidelis Care', 'Healthfirst', 'Amerigroup (Elevance)', 'WellCare Health Plans', 'Molina Healthcare', 'UnitedHealthcare Community Plan', 'MetroPlus'],
  'Florida':        ['Simply Healthcare (Centene)', 'Molina Healthcare of Florida', 'Staywell (Centene)', 'Humana Medicaid', 'UnitedHealthcare Community Plan'],
  'Pennsylvania':   ['Gateway Health (Highmark)', 'UPMC for You', 'Aetna Better Health of PA', 'Geisinger Health Plan', 'Molina Healthcare'],
  'Ohio':           ['Buckeye Health Plan (Centene)', 'CareSource', 'Molina Healthcare', 'UnitedHealthcare Community Plan', 'Paramount Advantage'],
  'Illinois':       ['CountyCare (Cook County)', 'Meridian Health Plan (Centene)', 'Molina Healthcare', 'BlueCross Community Options (BCBS IL)', 'IlliniCare Health'],
  'Michigan':       ['Molina Healthcare', 'UnitedHealthcare Community Plan', 'Meridian Health Plan (Centene)', 'HAP Midwest Health Plan'],
  'Georgia':        ['Amerigroup (Elevance)', 'Peach State Health (Centene)', 'UnitedHealthcare Community Plan', 'WellCare', 'CareSource Georgia'],
  'North Carolina': ['BCBS of NC', 'Aetna Better Health of NC', 'Healthy Blue (BCBS)', 'UnitedHealthcare Community Plan', 'WellCare of NC'],
  'Washington':     ['Molina Healthcare of Washington', 'UnitedHealthcare Community Plan', 'Amerigroup Washington', 'Community Health Plan of WA'],
  'Arizona':        ['Mercy Care (Cenpatico)', 'UnitedHealthcare Community Plan', 'Molina Healthcare of Arizona', 'Aetna Better Health of AZ', 'Health Choice Arizona'],
  'Virginia':       ['Aetna Better Health of Virginia', 'Anthem HealthKeepers Plus', 'Molina Healthcare of Virginia', 'Optima Health Community Care', 'UnitedHealthcare Community Plan'],
  'Indiana':        ['Anthem (Elevance)', 'MDwise (Centene)', 'Molina Healthcare', 'CareSource Indiana'],
  'Massachusetts':  ['Fallon Health', 'BMC HealthNet Plan', 'Tufts Health Together', 'UnitedHealthcare Community Plan', 'Aetna Better Health of MA'],
  'Tennessee':      ['Amerigroup Tennessee (Elevance)', 'BlueCare Tennessee (BCBS)', 'United American Insurance (UHC)'],
  'New Jersey':     ['Aetna Better Health', 'AmeriHealth Caritas NJ', 'Horizon NJ Health', 'UnitedHealthcare Community Plan', 'WellCare of NJ'],
  'Colorado':       ['Colorado Access', 'Rocky Mountain Health Plans', 'Anthem (Elevance)', 'Denver Health Medical Plan', 'Bright Health Plan'],
  'Oregon':         ['CareOregon', 'PacificSource Community Solutions', 'Trillium Community Health Plan', 'Umpqua Health Alliance', 'Yamhill Community Care'],
  'Minnesota':      ['UCare', 'Blue Plus (BCBS MN)', 'Medica', 'HealthPartners', 'Hennepin Health'],
};

export const MEDICAID_MCOS_NATIONAL: string[] = [
  'Molina Healthcare', 'UnitedHealthcare Community Plan', 'Aetna Better Health',
  'Centene / WellCare', 'Humana Medicaid', 'Anthem / Elevance Health',
  'CareSource', 'AmeriHealth Caritas',
];

// ─── Medicare ────────────────────────────────────────────────────────────────

/**
 * Medicare program types. Original Medicare (Parts A+B) uses the CMS fee
 * schedule we have loaded. Medicare Advantage (Part C) is a private plan
 * with insurer-negotiated rates — requires the insurer name for rate lookup.
 */
export const MEDICARE_PLAN_TYPES: { value: string; label: string }[] = [
  { value: 'Original Medicare (Parts A + B)',     label: 'Original Medicare (Parts A + B) — government pays providers directly'  },
  { value: 'Medicare Advantage (Part C)',          label: 'Medicare Advantage (Part C) — private HMO or PPO plan'                },
  { value: 'Medicare + Medigap Supplement',        label: 'Medicare + Medigap Supplement — Original Medicare with gap coverage'  },
  { value: 'Dual Eligible (Medicare + Medicaid)',  label: 'Dual Eligible — both Medicare and Medicaid cover you'                 },
  { value: 'Medicare Part A Only',                 label: 'Part A Only — inpatient/hospital, no outpatient Part B'               },
];

// ─── TRICARE ─────────────────────────────────────────────────────────────────

/**
 * TRICARE program types. Prime uses MTF/PCM rates; For Life wraps Medicare;
 * Select is a PPO-like direct-access plan.
 */
export const TRICARE_PLAN_TYPES: { value: string; label: string }[] = [
  { value: 'TRICARE Prime',          label: 'TRICARE Prime — HMO-like, must use MTF or assigned PCM'     },
  { value: 'TRICARE Select',         label: 'TRICARE Select — PPO-like, direct access to providers'      },
  { value: 'TRICARE For Life',       label: 'TRICARE For Life — Medicare supplement for retired military' },
  { value: 'TRICARE Reserve Select', label: 'TRICARE Reserve Select — Guard and Reserve members'         },
  { value: 'TRICARE Overseas (TOP)', label: 'TRICARE Overseas Program'                                    },
  { value: 'CHAMPVA',                label: 'CHAMPVA — VA coverage for veterans\' family members'         },
];
