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

export const metadata: Metadata = {
  title: 'ClaroBill — Find Errors in Your Medical Bill',
  description: 'AI-powered medical bill analysis. Find overcharges, duplicate charges, and billing errors in minutes.',
  openGraph: {
    title: 'ClaroBill — Find Errors in Your Medical Bill',
    description: 'AI-powered medical bill analysis. Find overcharges, duplicate charges, and billing errors in minutes.',
    siteName: 'ClaroBill',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'ClaroBill — Find Errors in Your Medical Bill',
    description: 'AI-powered medical bill analysis. Find overcharges, duplicate charges, and billing errors in minutes.',
  },
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} className={`${fraunces.variable} ${syne.variable}`}>
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
