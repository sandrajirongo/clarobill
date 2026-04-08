export function DashboardFooter(): JSX.Element {
  return (
    <footer className="border-t border-slate-100 mt-auto py-6 px-6">
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
        <p className="text-2xs text-slate-400 text-center sm:text-left leading-relaxed">
          🔒 Your bills are encrypted at rest (AES-256) and in transit (TLS 1.3). Raw files are permanently deleted after 60 days. We never sell or share your data.
        </p>
        <div className="flex items-center gap-4 text-2xs text-slate-400 shrink-0">
          <a href="/privacy" className="hover:text-slate-600 transition-colors">Privacy Policy</a>
          <a href="/terms" className="hover:text-slate-600 transition-colors">Terms</a>
          <span>© {new Date().getFullYear()} Clarobill</span>
        </div>
      </div>
    </footer>
  );
}
