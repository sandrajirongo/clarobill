import type { MetadataRoute } from 'next';

const BASE = 'https://www.clarobill.com';
const NOW = new Date();

const LEARN_SLUGS = [
  'common-medical-billing-errors',
  'how-to-dispute-a-hospital-bill',
  'how-to-read-an-itemized-medical-bill',
  'medical-billing-advocates',
  'what-are-cpt-codes',
  'why-bill-exceeds-insurer-negotiated-rate',
  'hospital-machine-readable-files-explained',
  'ncci-edits-explained-for-patients',
];

export default function sitemap(): MetadataRoute.Sitemap {
  const staticRoutes: MetadataRoute.Sitemap = [
    {
      url: `${BASE}/authors/sandra-jirongo`,
      lastModified: NOW,
      changeFrequency: 'monthly' as const,
      priority: 0.6,
    },
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
      url: `${BASE}/upload`,
      lastModified: NOW,
      changeFrequency: 'monthly' as const,
      priority: 0.9,
    },
    {
      url: `${BASE}/learn`,
      lastModified: NOW,
      changeFrequency: 'weekly',
      priority: 0.8,
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

  const learnRoutes: MetadataRoute.Sitemap = LEARN_SLUGS.map((slug) => ({
    url: `${BASE}/learn/${slug}`,
    lastModified: NOW,
    changeFrequency: 'monthly' as const,
    priority: 0.7,
  }));

  const compareRoutes: MetadataRoute.Sitemap = [
    'goodbill-vs-clarobill',
    'resolve-vs-clarobill',
    'medical-bill-app-vs-human-advocate',
    'price-shopping-vs-bill-review',
    'best-medical-bill-apps',
  ].map((slug) => ({
    url: `${BASE}/compare/${slug}`,
    lastModified: NOW,
    changeFrequency: 'monthly' as const,
    priority: 0.7,
  }));

  const stateRoutes: MetadataRoute.Sitemap = [
    'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
    'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
    'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana',
    'maine', 'maryland', 'massachusetts', 'michigan', 'minnesota',
    'mississippi', 'missouri', 'montana', 'nebraska', 'nevada',
    'new-hampshire', 'new-jersey', 'new-mexico', 'new-york',
    'north-carolina', 'north-dakota', 'ohio', 'oklahoma', 'oregon',
    'pennsylvania', 'rhode-island', 'south-carolina', 'south-dakota',
    'tennessee', 'texas', 'utah', 'vermont', 'virginia', 'washington',
    'west-virginia', 'wisconsin', 'wyoming',
  ].map((slug) => ({
    url: `${BASE}/learn/state/${slug}/patient-billing-rights`,
    lastModified: NOW,
    changeFrequency: 'monthly' as const,
    priority: 0.6,
  }));

  return [...staticRoutes, ...learnRoutes, ...compareRoutes, ...stateRoutes];
}
