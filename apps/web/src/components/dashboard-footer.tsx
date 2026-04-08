import s from '@/app/dashboard/dashboard.module.css';

export function DashboardFooter(): JSX.Element {
  return (
    <footer className={s.footer}>
      <div className={s.footerInner}>
        <p className={s.footerNote}>
          Your bills are encrypted at rest (AES-256) and in transit (TLS 1.3).
          Raw files are permanently deleted after 60 days. We never sell or share your data.
        </p>
        <div className={s.footerLinks}>
          <a href="/legal/privacy" className={s.footerLink}>Privacy</a>
          <a href="/legal/terms" className={s.footerLink}>Terms</a>
          <span className={s.footerLink}>© {new Date().getFullYear()} Clarobill</span>
        </div>
      </div>
    </footer>
  );
}
