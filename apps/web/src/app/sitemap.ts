import type { MetadataRoute } from 'next';

const BASE = 'https://www.clarobill.com';
const NOW = new Date();

const BLOG_SLUGS = [
  'common-medical-billing-errors',
  'how-to-dispute-a-hospital-bill',
  'how-to-read-an-itemized-medical-bill',
  'medical-billing-advocates',
  'what-are-cpt-codes',
];

export default function sitemap(): MetadataRoute.Sitemap {
  const staticRoutes: MetadataRoute.Sitemap = [
    {
      url: BASE,
      lastModified: NOW,
      changeFrequency: 'weekly',
      priority: 1.0,
    },
    {
      url: `${BASE}/pricing`,
      lastModified: NOW,
      changeFrequency: 'monthly',
      priority: 0.9,
    },
    {
      url: `${BASE}/how-it-works`,
      lastModified: NOW,
      changeFrequency: 'monthly',
      priority: 0.8,
    },
    {
      url: `${BASE}/free-medical-bill-check`,
      lastModified: NOW,
      changeFrequency: 'monthly',
      priority: 0.9,
    },
    {
      url: `${BASE}/methodology`,
      lastModified: NOW,
      changeFrequency: 'monthly',
      priority: 0.8,
    },
    {
      url: `${BASE}/about`,
      lastModified: NOW,
      changeFrequency: 'monthly',
      priority: 0.6,
    },
    {
      url: `${BASE}/learn`,
      lastModified: NOW,
      changeFrequency: 'weekly',
      priority: 0.8,
    },
    {
      url: `${BASE}/blog`,
      lastModified: NOW,
      changeFrequency: 'weekly',
      priority: 0.7,
    },
    {
      url: `${BASE}/legal/privacy`,
      lastModified: NOW,
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: `${BASE}/legal/terms`,
      lastModified: NOW,
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: `${BASE}/legal/disclaimer`,
      lastModified: NOW,
      changeFrequency: 'yearly',
      priority: 0.3,
    },
  ];

  const blogRoutes: MetadataRoute.Sitemap = BLOG_SLUGS.map((slug) => ({
    url: `${BASE}/blog/${slug}`,
    lastModified: NOW,
    changeFrequency: 'monthly' as const,
    priority: 0.7,
  }));

  // /learn/*, /compare/*, /cpt/*, /hospital/*, /state/* routes will be
  // added here as those page groups are built (T-012, T-024, T-025, T-027,
  // T-035, T-046).

  return [...staticRoutes, ...blogRoutes];
}
