import s from './how-we-know.module.css';

interface HowWeKnowProps {
  rule: string;
  source: string;
  effectiveDate: string;
  url?: string;
}

export function HowWeKnow({ rule, source, effectiveDate, url }: HowWeKnowProps): JSX.Element {
  return (
    <aside className={s.box} aria-label="Source citation">
      <svg className={s.icon} viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8 7v4M8 5h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <div className={s.content}>
        <span className={s.label}>How we know</span>
        <span className={s.rule}>Rule: {rule}</span>
        <span className={s.meta}>
          Source:{' '}
          {url ? (
            <a href={url} target="_blank" rel="noopener noreferrer">{source}</a>
          ) : (
            source
          )}
          {' '}&middot; Effective {effectiveDate}
        </span>
      </div>
    </aside>
  );
}
