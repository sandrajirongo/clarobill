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
  | 'DATE_INCONSISTENCY';

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
