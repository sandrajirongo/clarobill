import { redirect } from 'next/navigation';
import { getAuthenticatedUser } from '@/lib/supabase/server';
import { BillUploader } from '@/components/bill-uploader';

// Server Component — auth is checked server-side, no client flash.
export default async function DashboardPage(): Promise<JSX.Element> {
  const user = await getAuthenticatedUser();

  if (!user) {
    redirect('/auth/sign-in');
  }

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Your Bills</h1>
        <p className="text-sm text-gray-500 mb-8">Signed in as {user.email}</p>
        <BillUploader />
      </div>
    </main>
  );
}
