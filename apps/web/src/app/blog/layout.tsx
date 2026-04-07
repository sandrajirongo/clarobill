import Link from 'next/link';
import { Logo } from '@/components/logo';

export default function BlogLayout({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className="min-h-screen bg-white font-[family-name:var(--font-geist-sans)]">
      <header className="border-b border-gray-100">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/">
            <Logo size="sm" />
          </Link>
          <Link
            href="/auth/sign-in"
            className="text-sm font-medium bg-gray-900 text-white px-4 py-2 rounded-lg hover:bg-gray-700 transition-colors"
          >
            Analyze my bill
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-12">
        {children}
      </main>

      <footer className="border-t border-gray-100 mt-16">
        <div className="max-w-3xl mx-auto px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-gray-400">
          <span>© {new Date().getFullYear()} Flow Financial Group. All rights reserved.</span>
          <nav className="flex gap-6">
            <Link href="/legal/terms" className="hover:text-gray-700">Terms</Link>
            <Link href="/legal/privacy" className="hover:text-gray-700">Privacy</Link>
            <Link href="/legal/disclaimer" className="hover:text-gray-700">Disclaimer</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
