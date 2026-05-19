import type { MetadataRoute } from 'next';
import { ANSWERS } from '@/lib/answers-data';

const BASE = 'https://answers.clarobill.com';

export default function sitemap(): MetadataRoute.Sitemap {
  const hub: MetadataRoute.Sitemap = [
    {
      url: BASE,
      lastModified: new Date('2026-05-18'),
      changeFrequency: 'weekly',
      priority: 1.0,
    },
  ];

  const articles: MetadataRoute.Sitemap = ANSWERS.map((article) => ({
    url: `${BASE}/${article.slug}`,
    lastModified: new Date(article.date),
    changeFrequency: 'monthly' as const,
    priority: 0.8,
  }));

  return [...hub, ...articles];
}
