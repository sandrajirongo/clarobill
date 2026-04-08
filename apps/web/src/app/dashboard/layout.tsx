import { redirect } from 'next/navigation';
import { getAuthenticatedUser } from '@/lib/supabase/server';
import { DashboardNav } from '@/components/dashboard-nav';
import { DashboardFooter } from '@/components/dashboard-footer';

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}): Promise<JSX.Element> {
  const user = await getAuthenticatedUser();
  if (!user) redirect('/auth/sign-in');

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <DashboardNav email={user.email ?? ''} />
      <div className="flex-1">{children}</div>
      <DashboardFooter />
    </div>
  );
}
