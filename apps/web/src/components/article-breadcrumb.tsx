import Link from 'next/link';
import s from '../app/blog/blog.module.css';

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface ArticleBreadcrumbProps {
  items: BreadcrumbItem[];
}

export function ArticleBreadcrumb({ items }: ArticleBreadcrumbProps): JSX.Element {
  return (
    <nav aria-label="Breadcrumb" className={s.breadcrumb}>
      {items.map((item, i) => (
        <span key={item.label} className={s.breadcrumbItem}>
          {i > 0 && <span className={s.breadcrumbSep} aria-hidden="true">/</span>}
          {item.href ? (
            <Link href={item.href} className={s.breadcrumbLink}>{item.label}</Link>
          ) : (
            <span className={s.breadcrumbCurrent} aria-current="page">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
