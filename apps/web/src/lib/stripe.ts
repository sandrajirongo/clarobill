import Stripe from 'stripe';

// Server-side Stripe client — never import this in Client Components
export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2024-06-20',
  typescript: true,
});

export const REPORT_PRICE_CENTS = parseInt(process.env.STRIPE_REPORT_PRICE_CENTS ?? '1999', 10);
