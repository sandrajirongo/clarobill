// Smoke test: confirms @clarobill/shared types are resolvable from mobile.
// This file exists only to fail typecheck if the workspace link is broken.
// Safe to delete once we start using the shared types in real screens.

import type { AnalysisResult, BillingError } from '@clarobill/shared';

export type _MobileSharedSmoke = {
  result: AnalysisResult;
  error: BillingError;
};
