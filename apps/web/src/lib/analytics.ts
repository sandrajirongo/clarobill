// Client-side typed analytics events. Import only in Client Components.
// Thin wrapper around posthog.capture so call sites don't hardcode event strings.
import { posthog } from '@/lib/posthog';

export const Analytics = {
  billUploaded: (billId: string) =>
    posthog.capture('bill_uploaded', { bill_id: billId }),

  analysisStarted: (billId: string) =>
    posthog.capture('analysis_started', { bill_id: billId }),

  analysisCompleted: (billId: string) =>
    posthog.capture('analysis_completed', { bill_id: billId }),

  checkoutStarted: (billId: string) =>
    posthog.capture('checkout_started', { bill_id: billId }),

  onboardingCompleted: () =>
    posthog.capture('onboarding_completed'),

  guideDownloaded: () =>
    posthog.capture('guide_downloaded', { guide: 'billing_traps' }),
};
