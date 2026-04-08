import type { Metadata } from 'next';
import { Fraunces, Syne } from 'next/font/google';
import { Suspense } from 'react';
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

export const metadata: Metadata = {
  title: 'ClaroBill — Find Errors in Your Medical Bill',
  description: 'AI-powered medical bill analysis. Find overcharges, duplicate charges, and billing errors in minutes.',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${fraunces.variable} ${syne.variable}`}>
      <body>
        <Suspense>
          <PostHogProvider>{children}</PostHogProvider>
        </Suspense>
      </body>
    </html>
  );
}
