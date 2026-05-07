// Renders one or more JSON-LD blocks as <script type="application/ld+json"> tags.
// Server-only — no 'use client' directive. Import in server components and layouts.
// JSON.stringify escapes special characters; no additional sanitization needed
// because the content never enters the DOM as HTML.

export type SchemaOrg =
  | OrganizationSchema
  | WebSiteSchema
  | ArticleSchema
  | BreadcrumbListSchema
  | FAQPageSchema
  | HowToSchema
  | ProductSchema
  | PersonSchema
  | DefinedTermSchema
  | DefinedTermSetSchema
  | GovernmentServiceSchema;

export interface OrganizationSchema {
  '@type': 'Organization';
  name: string;
  url: string;
  logo?: string;
  description?: string;
  sameAs?: string[];
}

export interface WebSiteSchema {
  '@type': 'WebSite';
  name: string;
  url: string;
  potentialAction?: {
    '@type': 'SearchAction';
    target: string;
    'query-input': string;
  };
}

export interface ArticleSchema {
  '@type': 'Article' | 'MedicalWebPage';
  headline: string;
  description?: string;
  datePublished: string;
  dateModified: string;
  author: { '@type': 'Person'; name: string; url?: string };
  publisher?: { '@type': 'Organization'; name: string; logo?: string };
  image?: string;
  url?: string;
}

export interface BreadcrumbListSchema {
  '@type': 'BreadcrumbList';
  itemListElement: { '@type': 'ListItem'; position: number; name: string; item?: string }[];
}

export interface FAQPageSchema {
  '@type': 'FAQPage';
  mainEntity: {
    '@type': 'Question';
    name: string;
    acceptedAnswer: { '@type': 'Answer'; text: string };
  }[];
}

export interface HowToSchema {
  '@type': 'HowTo';
  name: string;
  description?: string;
  step: { '@type': 'HowToStep'; name: string; text: string; url?: string }[];
}

export interface ProductSchema {
  '@type': 'Product';
  name: string;
  description?: string;
  brand?: { '@type': 'Brand'; name: string };
  offers: {
    '@type': 'Offer';
    name?: string;
    price: string;
    priceCurrency: string;
    availability?: string;
  }[];
}

export interface PersonSchema {
  '@type': 'Person';
  name: string;
  url?: string;
  jobTitle?: string;
  description?: string;
  sameAs?: string[];
}

export interface DefinedTermSchema {
  '@type': 'DefinedTerm';
  name: string;
  description: string;
  inDefinedTermSet?: string;
}

export interface DefinedTermSetSchema {
  '@type': 'DefinedTermSet';
  name: string;
  hasDefinedTerm: DefinedTermSchema[];
}

export interface GovernmentServiceSchema {
  '@type': 'GovernmentService';
  name: string;
  description?: string;
  url?: string;
  provider?: { '@type': 'GovernmentOrganization'; name: string };
}

interface JsonLdProps {
  schema: SchemaOrg | SchemaOrg[];
}

export function JsonLd({ schema }: JsonLdProps): React.ReactElement {
  const schemas = Array.isArray(schema) ? schema : [schema];
  return (
    <>
      {schemas.map((s, i) => (
        <script
          key={i}
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({ '@context': 'https://schema.org', ...s }),
          }}
        />
      ))}
    </>
  );
}
