import { redirect } from 'next/navigation';
import { getAuthenticatedUser } from '@/lib/supabase/server';
import { DashboardNav } from '@/components/dashboard-nav';
import { DashboardFooter } from '@/components/dashboard-footer';
import s from './dashboard.module.css';

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}): Promise<JSX.Element> {
  const user = await getAuthenticatedUser();
  if (!user) redirect('/auth/sign-in');

  return (
    <div className={s.shell}>
      <DashboardNav email={user.email ?? ''} />
      <div style={{ flex: 1 }}>{children}</div>
      <DashboardFooter />
    </div>
  );
}
