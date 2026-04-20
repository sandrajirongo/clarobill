import { getTranslations } from 'next-intl/server';
import s from '@/app/dashboard/dashboard.module.css';

export async function DashboardFooter(): Promise<JSX.Element> {
  const t = await getTranslations('dashboard.footer');
  return (
    <footer className={s.footer}>
      <div className={s.footerInner}>
        <p className={s.footerNote}>{t('security')}</p>
        <div className={s.footerLinks}>
          <a href="/legal/privacy" className={s.footerLink}>{t('privacy')}</a>
          <a href="/legal/terms" className={s.footerLink}>{t('terms')}</a>
          <span className={s.footerLink}>© {new Date().getFullYear()} Claro<em style={{ fontStyle: 'italic' }}>Bill</em></span>
        </div>
      </div>
    </footer>
  );
}
