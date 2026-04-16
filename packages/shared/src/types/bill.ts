// ─── Bill & Line Item Types ───────────────────────────────────────────────────

export type BillStatus =
  | 'uploading'
  | 'ocr_processing'
  | 'analyzing'
  | 'complete'
  | 'failed';

export interface Bill {
  id: string;
  userId: string;
  fileName: string;
  filePath: string;
  fileSize: number;
  mimeType: 'application/pdf' | 'image/jpeg' | 'image/png';
  status: BillStatus;
  // OCR-extracted provider identity — confirmed during pre-analysis verification
  hospitalNpi: string | null;
  hospitalName: string | null;
  // Insurance confirmed by user at verification time — denormalized from insurance_plans
  profileMemberId: string | null;
  payerName: string | null;
  planName: string | null;
  // Timestamp when the user completed pre-analysis verification
  confirmedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

// ─── Profile Member & Insurance Types ────────────────────────────────────────

export type PlanType = 'commercial' | 'medicare' | 'medicaid' | 'tricare' | 'self_pay';

export interface ProfileMember {
  id: string;
  userId: string;
  fullName: string;
  dateOfBirth: string;
  state: string | null;
  county: string | null;
  zipCode: string | null;
  isPrimary: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface InsurancePlan {
  id: string;
  profileMemberId: string;
  payerName: string;
  planName: string;
  memberId: string | null;
  planType: PlanType;
  isPrimaryPlan: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface LineItem {
  id: string;
  billId: string;
  cptCode: string;
  description: string;
  serviceDate: string;
  quantity: number;
  unitCharge: number;
  totalCharge: number;
  modifier: string | null;
  diagnosisPointers: string[];
}

// ─── Analysis & Error Types ───────────────────────────────────────────────────

export type ErrorSeverity = 'critical' | 'warning' | 'info';

export type BillingErrorCode =
  | 'DUPLICATE_CHARGE'
  | 'PRICE_OUTLIER'
  | 'NCCI_UNBUNDLING'
  | 'INVALID_CPT_CODE'
  | 'UPCODING'
  | 'MISSING_MODIFIER'
  | 'DATE_INCONSISTENCY'
  | 'NON_PAYABLE_CODE'
  | 'TERMINATED_CODE_BILLED'
  | 'ANESTHESIA_OUTLIER'
  | 'FACILITY_CHARGE_OUTLIER'
  | 'AMBULANCE_CHARGE_OUTLIER'
  | 'HOSPITAL_CHARGE_OUTLIER'
  | 'NEGOTIATED_RATE_EXCEEDED';

export interface BillingError {
  code: BillingErrorCode;
  severity: ErrorSeverity;
  affectedLineItemIds: string[];
  description: string;
  estimatedOvercharge: number;
  // Medicare benchmark for comparison (if applicable)
  medicareBenchmarkRate: number | null;
}

export interface AnalysisResult {
  id: string;
  billId: string;
  errors: BillingError[];
  totalCharges: number;
  estimatedFairValue: number;
  totalPotentialSavings: number;
  aiSummary: string;
  disputeLetterUrl: string | null;
  reportUrl: string | null;
  createdAt: string;
}

// ─── API Response Types ───────────────────────────────────────────────────────

export interface BillUploadResponse {
  billId: string;
  uploadUrl: string;
}

export interface BillAnalysisResponse {
  bill: Bill;
  lineItems: LineItem[];
  analysis: AnalysisResult;
}

// ─── Error Types ─────────────────────────────────────────────────────────────

export type ClarobillError =
  | { code: 'OCR_FAILED'; detail: string; billId: string }
  | { code: 'INVALID_CPT_CODE'; detail: string; cptCode: string }
  | { code: 'PAYMENT_FAILED'; detail: string; stripeError: string }
  | { code: 'RATE_LIMIT'; detail: string; retryAfter: number }
  | { code: 'ANALYSIS_FAILED'; detail: string; step: string }
  | { code: 'UNAUTHORIZED'; detail: string }
  | { code: 'FILE_TOO_LARGE'; detail: string; maxBytes: number }
  | { code: 'INVALID_FILE_TYPE'; detail: string; receivedType: string };

export interface ApiErrorResponse {
  error: ClarobillError;
  requestId: string;
}
