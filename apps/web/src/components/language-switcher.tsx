'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useLocale } from 'next-intl';
import { updateLocale } from '@/lib/i18n/actions';
import { LOCALES, type Locale } from '../../i18n/routing';
import s from './language-switcher.module.css';

const LANGUAGE_OPTIONS: Record<Locale, { native: string; english: string }> = {
  en: { native: 'English',      english: 'English'    },
  es: { native: 'Español',      english: 'Spanish'    },
  zh: { native: '中文',          english: 'Chinese'    },
  tl: { native: 'Filipino',     english: 'Filipino'   },
  vi: { native: 'Tiếng Việt',   english: 'Vietnamese' },
};

export function LanguageSwitcher(): JSX.Element {
  const router = useRouter();
  const currentLocale = useLocale() as Locale;
  const [pending, setPending] = useState<Locale | null>(null);

  async function handleChange(locale: Locale): Promise<void> {
    if (locale === currentLocale || pending) return;
    setPending(locale);
    await updateLocale(locale);
    router.refresh();
  }

  return (
    <div className={s.grid}>
      {LOCALES.map((locale) => {
        const { native, english } = LANGUAGE_OPTIONS[locale];
        const active = locale === (pending ?? currentLocale);
        return (
          <button
            key={locale}
            onClick={() => handleChange(locale)}
            disabled={!!pending}
            className={`${s.btn} ${active ? s.btnActive : ''}`}
          >
            <span className={s.native}>{native}</span>
            {locale !== 'en' && <span className={s.english}>{english}</span>}
          </button>
        );
      })}
    </div>
  );
}
