import type { Metadata } from 'next';
import Link from 'next/link';
import { getTranslations, getLocale } from 'next-intl/server';
import s from './blog.module.css';

export const metadata: Metadata = {
  title: 'Medical Billing Resources: Clarobill',
  description: 'Guides on reading medical bills, understanding CPT codes, and disputing billing errors. Plain English, no jargon.',
  alternates: {
    canonical: 'https://www.clarobill.com/blog',
    languages: { 'en': 'https://www.clarobill.com/blog', 'x-default': 'https://www.clarobill.com/blog' },
  },
};

interface Article {
  slug: string;
  title: string;
  description: string;
  date: string;
  readMins: number;
}

// Article titles/descriptions per locale — dates and readMins are locale-independent
const ARTICLES_EN: Omit<Article, 'date'>[] = [
  {
    slug: 'how-to-dispute-a-hospital-bill',
    title: 'How to Dispute a Hospital Bill: A Step-by-Step Guide',
    description: 'A practical guide to disputing hospital billing errors. From requesting your itemized bill to writing a dispute letter that actually gets results.',
    readMins: 9,
  },
  {
    slug: 'medical-billing-advocates',
    title: 'Medical Billing Advocates: What They Do, What They Charge, and Whether You Need One',
    description: 'Advocates can recover real money from billing errors. But they typically keep 25–35% of what they save you. Here is when hiring one makes sense.',
    readMins: 7,
  },
  {
    slug: 'how-to-read-an-itemized-medical-bill',
    title: 'How to Read an Itemized Medical Bill',
    description: 'What the columns, codes, and dollar amounts actually mean. Plus how to spot the line items that should not be there.',
    readMins: 7,
  },
  {
    slug: 'common-medical-billing-errors',
    title: 'The Most Common Medical Billing Errors (And How to Dispute Them)',
    description: 'Duplicate charges, upcoded visits, unbundled procedures. Here is what each one looks like on a real bill and what to say when you dispute it.',
    readMins: 8,
  },
  {
    slug: 'what-are-cpt-codes',
    title: "What Are CPT Codes? A Patient's Guide",
    description: 'The five-digit numbers on your bill determine what you pay. Here is how they work, why they get abused, and how to check whether yours are right.',
    readMins: 6,
  },
];

const ARTICLES_ES: Omit<Article, 'date'>[] = [
  {
    slug: 'how-to-dispute-a-hospital-bill',
    title: 'Cómo Disputar una Factura Hospitalaria: Guía Paso a Paso',
    description: 'Una guía práctica para disputar errores en facturas hospitalarias. Desde solicitar tu factura detallada hasta escribir una carta de disputa que realmente funciona.',
    readMins: 9,
  },
  {
    slug: 'medical-billing-advocates',
    title: 'Defensores de Facturación Médica: Qué Hacen, Cuánto Cobran y Si Los Necesitas',
    description: 'Los defensores pueden recuperar dinero real de errores de facturación. Pero típicamente retienen el 25–35% de lo que te ahorran. Aquí te explicamos cuándo tiene sentido contratar uno.',
    readMins: 7,
  },
  {
    slug: 'how-to-read-an-itemized-medical-bill',
    title: 'Cómo Leer una Factura Médica Detallada',
    description: 'Lo que realmente significan las columnas, códigos y montos. Además, cómo identificar los cargos que no deberían estar ahí.',
    readMins: 7,
  },
  {
    slug: 'common-medical-billing-errors',
    title: 'Los Errores de Facturación Médica Más Comunes (Y Cómo Disputarlos)',
    description: 'Cargos duplicados, visitas sobrecodificadas, procedimientos desglosados. Así es como se ve cada uno en una factura real y qué decir cuando lo disputas.',
    readMins: 8,
  },
  {
    slug: 'what-are-cpt-codes',
    title: '¿Qué Son los Códigos CPT? Una Guía para Pacientes',
    description: 'Los números de cinco dígitos en tu factura determinan lo que pagas. Así es como funcionan, por qué se abusan y cómo verificar si los tuyos son correctos.',
    readMins: 6,
  },
];

const ARTICLES_ZH: Omit<Article, 'date'>[] = [
  {
    slug: 'how-to-dispute-a-hospital-bill',
    title: '如何对医院账单提出异议：分步指南',
    description: '一份对医院账单错误提出异议的实用指南。从索取明细账单到撰写真正有效的异议信。',
    readMins: 9,
  },
  {
    slug: 'medical-billing-advocates',
    title: '医疗账单顾问：他们的工作、收费以及您是否需要他们',
    description: '顾问可以从账单错误中追回真实的钱款。但他们通常从为您节省的金额中收取25–35%的费用。以下是雇用顾问合适的情况。',
    readMins: 7,
  },
  {
    slug: 'how-to-read-an-itemized-medical-bill',
    title: '如何阅读医疗明细账单',
    description: '各列、代码和金额的实际含义。以及如何发现不应出现的项目。',
    readMins: 7,
  },
  {
    slug: 'common-medical-billing-errors',
    title: '最常见的医疗账单错误（以及如何提出异议）',
    description: '重复收费、过度计费的就诊、拆分的手术。以下是每种情况在真实账单上的样子，以及提出异议时该说什么。',
    readMins: 8,
  },
  {
    slug: 'what-are-cpt-codes',
    title: '什么是CPT代码？患者指南',
    description: '账单上的五位数字决定了您需要支付多少。以下是它们的工作原理、为何会被滥用，以及如何检查您的代码是否正确。',
    readMins: 6,
  },
];

const ARTICLES_TL: Omit<Article, 'date'>[] = [
  {
    slug: 'how-to-dispute-a-hospital-bill',
    title: 'Paano Makipagtalo sa Isang Hospital Bill: Hakbang-hakbang na Gabay',
    description: 'Isang praktikal na gabay sa pagtatalo ng mga error sa hospital billing. Mula sa pag-request ng itemized bill hanggang sa pagsulat ng dispute letter na talagang nakakakuha ng resulta.',
    readMins: 9,
  },
  {
    slug: 'medical-billing-advocates',
    title: 'Mga Medical Billing Advocate: Ano ang Kanilang Ginagawa, Magkano ang Bayad, at Kung Kailangan Mo Sila',
    description: 'Ang mga advocate ay maaaring makakuha ng tunay na pera mula sa mga error sa billing. Ngunit karaniwang nagtatago sila ng 25–35% ng iyong natipid. Narito kung kailan makatuwirang kumuha ng isa.',
    readMins: 7,
  },
  {
    slug: 'how-to-read-an-itemized-medical-bill',
    title: 'Paano Basahin ang Isang Itemized na Medical Bill',
    description: 'Ang tunay na kahulugan ng mga column, code, at halaga ng pera. At kung paano matukoy ang mga line item na hindi dapat naroon.',
    readMins: 7,
  },
  {
    slug: 'common-medical-billing-errors',
    title: 'Ang Pinaka-Karaniwang Mga Error sa Medical Billing (At Paano Itutol Ang Mga Ito)',
    description: 'Mga duplicate na singil, naka-upcode na mga bisita, mga na-unbundle na pamamaraan. Narito kung ano ang hitsura ng bawat isa sa isang tunay na bill at kung ano ang sasabihin kapag itinututol mo ito.',
    readMins: 8,
  },
  {
    slug: 'what-are-cpt-codes',
    title: 'Ano ang Mga CPT Code? Isang Gabay para sa Pasyente',
    description: 'Ang limang-digit na mga numero sa iyong bill ang nagtatakda ng iyong babayaran. Narito kung paano sila gumagana, bakit sila inaaabuso, at kung paano suriin kung tama ang sa iyo.',
    readMins: 6,
  },
];

const ARTICLES_VI: Omit<Article, 'date'>[] = [
  {
    slug: 'how-to-dispute-a-hospital-bill',
    title: 'Cách Tranh Chấp Hóa Đơn Bệnh Viện: Hướng Dẫn Từng Bước',
    description: 'Hướng dẫn thực tế để tranh chấp các lỗi thanh toán bệnh viện. Từ yêu cầu hóa đơn chi tiết đến viết thư tranh chấp thực sự có hiệu quả.',
    readMins: 9,
  },
  {
    slug: 'medical-billing-advocates',
    title: 'Người Bảo Vệ Thanh Toán Y Tế: Những Gì Họ Làm, Những Gì Họ Tính, và Liệu Bạn Có Cần Không',
    description: 'Người bảo vệ có thể thu hồi tiền thực tế từ các lỗi thanh toán. Nhưng họ thường giữ 25–35% số tiền họ tiết kiệm cho bạn. Đây là khi nào nên thuê một người.',
    readMins: 7,
  },
  {
    slug: 'how-to-read-an-itemized-medical-bill',
    title: 'Cách Đọc Hóa Đơn Y Tế Chi Tiết',
    description: 'Các cột, mã và số tiền thực sự có nghĩa gì. Và cách phát hiện các mục không nên có.',
    readMins: 7,
  },
  {
    slug: 'common-medical-billing-errors',
    title: 'Các Lỗi Thanh Toán Y Tế Phổ Biến Nhất (Và Cách Tranh Chấp Chúng)',
    description: 'Phí trùng lặp, lần khám bị tính vượt mức, thủ thuật bị tách rời. Đây là những gì mỗi lỗi trông như thế nào trên hóa đơn thực và những gì cần nói khi tranh chấp.',
    readMins: 8,
  },
  {
    slug: 'what-are-cpt-codes',
    title: 'Mã CPT Là Gì? Hướng Dẫn Cho Bệnh Nhân',
    description: 'Các con số năm chữ số trên hóa đơn của bạn quyết định những gì bạn phải trả. Đây là cách chúng hoạt động, tại sao chúng bị lạm dụng và cách kiểm tra xem mã của bạn có đúng không.',
    readMins: 6,
  },
];

const DATES = [
  'April 17, 2026',
  'April 17, 2026',
  'April 7, 2026',
  'April 7, 2026',
  'April 7, 2026',
];

const ARTICLES_BY_LOCALE: Record<string, Omit<Article, 'date'>[]> = {
  en: ARTICLES_EN,
  es: ARTICLES_ES,
  zh: ARTICLES_ZH,
  tl: ARTICLES_TL,
  vi: ARTICLES_VI,
};

export default async function BlogIndexPage(): Promise<JSX.Element> {
  const [t, locale] = await Promise.all([
    getTranslations('resources'),
    getLocale(),
  ]);

  const articles = (ARTICLES_BY_LOCALE[locale] ?? ARTICLES_EN).map((a, i) => ({
    ...a,
    date: DATES[i] ?? '',
  }));

  return (
    <div>
      <h1 className={s.indexH1}>{t('title')}</h1>
      <p className={s.indexSub}>{t('subtitle')}</p>
      <div className={s.articleGrid}>
        {articles.map((article) => (
          <div key={article.slug} className={s.articleCard}>
            <Link href={`/blog/${article.slug}`} className={s.articleCardTitle}>
              {article.title}
            </Link>
            <p className={s.articleCardDesc}>{article.description}</p>
            <div className={s.byline}>
              <span>{article.date}</span>
              <span>·</span>
              <span>{t('minRead', { n: article.readMins })}</span>
              <span>·</span>
              <span>{t('team')}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
