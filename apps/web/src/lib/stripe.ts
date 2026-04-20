import Stripe from 'stripe';

// Server-side Stripe client — never import this in Client Components
export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2024-06-20',
  typescript: true,
});

// Re-export tier helpers so server routes only need one import
export { getPriceTier, PRICING_TIERS } from './pricing';
