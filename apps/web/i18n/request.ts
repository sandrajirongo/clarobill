import { getRequestConfig } from 'next-intl/server';
import { cookies } from 'next/headers';
import { LOCALES, type Locale } from './routing';

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const raw = cookieStore.get('cb_locale')?.value ?? 'en';
  const locale: Locale = (LOCALES as readonly string[]).includes(raw)
    ? (raw as Locale)
    : 'en';

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
