import type { Metadata, Viewport } from 'next';
import { Fraunces, Syne } from 'next/font/google';
import { Suspense } from 'react';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages, getLocale } from 'next-intl/server';
import { PostHogProvider } from '@/components/posthog-provider';
import './globals.css';

// Fraunces: optical-size axis required for variable font
const fraunces = Fraunces({
  subsets: ['latin'],
  axes: ['opsz'],
  variable: '--font-fraunces',
  display: 'swap',
});

const syne = Syne({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-syne',
  display: 'swap',
});

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',       // lets content extend under iPhone home indicator
  themeColor: '#2D4A2A',
};

// Required for Next.js to construct absolute URLs for the auto-generated
// opengraph-image.tsx route. Without metadataBase, social platforms (iMessage,
// WhatsApp, Slack, Twitter) can't fetch the OG image and render a blank
// preview card. Use the www. canonical URL since the apex redirects there —
// pointing metadataBase at the apex would make og:image URLs hit a redirect
// before reaching the actual image, and many scrapers don't follow redirects
// for image sub-resources. Override locally with NEXT_PUBLIC_SITE_URL when
// previewing shares against a tunnel or staging deployment.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://www.clarobill.com';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: 'ClaroBill: Find Errors in Your Medical Bill',
  description: 'AI-powered medical bill analysis. Find overcharges, duplicate charges, and billing errors in minutes.',
  openGraph: {
    title: 'ClaroBill: Find Errors in Your Medical Bill',
    description: 'AI-powered medical bill analysis. Find overcharges, duplicate charges, and billing errors in minutes.',
    siteName: 'ClaroBill',
    type: 'website',
    url: SITE_URL,
    images: [
      {
        url: '/opengraph-image',
        width: 1200,
        height: 630,
        alt: 'ClaroBill: Find Errors in Your Medical Bill',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'ClaroBill: Find Errors in Your Medical Bill',
    description: 'AI-powered medical bill analysis. Find overcharges, duplicate charges, and billing errors in minutes.',
    images: ['/opengraph-image'],
  },
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    // lang="en" — article and medical bill content is English; browser auto-translate
    // detects this correctly and offers to translate for non-English users.
    // next-intl locale is passed via NextIntlClientProvider for UI string translation.
    <html lang="en" className={`${fraunces.variable} ${syne.variable}`}>
      <body>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <Suspense>
            <PostHogProvider>{children}</PostHogProvider>
          </Suspense>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
