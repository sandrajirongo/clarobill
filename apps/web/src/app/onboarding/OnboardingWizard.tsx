'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { LogoWithMark } from '@/components/logo';
import { US_STATES } from '@/lib/utils/county-data';
import { saveOnboarding } from '@/lib/i18n/actions';
import { CardScanner } from '@/components/card-scanner';
import type { InsuranceCardExtraction } from '@/app/api/insurance-card/extract/route';
import s from './onboarding.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

type Locale = 'en' | 'es' | 'zh' | 'tl' | 'vi';
type Step = 'language' | 'profile' | 'primer';
type InsuranceType = 'commercial' | 'medicare' | 'medicaid' | 'tricare' | 'self_pay';

const VALID_INSURANCE_TYPES: InsuranceType[] = ['commercial', 'medicare', 'medicaid', 'tricare', 'self_pay'];

interface InsuranceMessages {
  commercial: string; commercialSub: string;
  medicare: string;   medicareSub: string;
  medicaid: string;   medicaidSub: string;
  tricare: string;    tricareSub: string;
  selfPay: string;    selfPaySub: string;
}

interface ProfileErrors {
  nameRequired: string; dobRequired: string;
  stateRequired: string; zipRequired: string;
  zipInvalid: string; insuranceRequired: string;
}

interface Messages {
  language: { title: string; subtitle: string; continue: string };
  profile: {
    title: string; subtitle: string;
    nameLabel: string; namePlaceholder: string;
    dobLabel: string;
    stateLabel: string; statePlaceholder: string;
    zipLabel: string; zipPlaceholder: string;
    insuranceLabel: string;
    insurance: InsuranceMessages;
    continue: string; back: string;
    errors: ProfileErrors;
  };
  primer: {
    title: string; subtitle: string;
    step1: { title: string; body: string };
    step2: { title: string; body: string };
    step3: { title: string; body: string };
    nav: { reports: string; billing: string };
    cta: string; back: string;
  };
  saving: string;
  error: string;
}

// ── Translations (bundled for instant switching) ──────────────────────────────

const T: Record<Locale, Messages> = {
  en: {
    language: { title: 'Choose your language', subtitle: 'You can change this anytime in your profile', continue: 'Continue' },
    profile: {
      title: 'Tell us about yourself', subtitle: 'This helps us accurately benchmark your charges',
      nameLabel: 'Full name', namePlaceholder: 'Jane Smith',
      dobLabel: 'Date of birth',
      stateLabel: 'State', statePlaceholder: 'Select your state',
      zipLabel: 'ZIP code', zipPlaceholder: 'e.g. 90210',
      insuranceLabel: 'What type of insurance do you have?',
      insurance: { commercial: 'Commercial', commercialSub: 'Employer or marketplace plan', medicare: 'Medicare', medicareSub: 'Federal health insurance (65+)', medicaid: 'Medicaid', medicaidSub: 'State health insurance', tricare: 'TRICARE', tricareSub: 'Military & veteran coverage', selfPay: 'Self-Pay', selfPaySub: 'No insurance' },
      continue: 'Continue', back: 'Back',
      errors: { nameRequired: 'Please enter your full name', dobRequired: 'Please enter your date of birth', stateRequired: 'Please select your state', zipRequired: 'Please enter your ZIP code', zipInvalid: 'ZIP code must be 5 digits', insuranceRequired: 'Please select your insurance type' },
    },
    primer: {
      title: "You're all set", subtitle: 'Here\'s how ClaroBill works',
      step1: { title: 'Upload your bill', body: 'Drop in a PDF or photo of your medical bill, EOB, or superbill' },
      step2: { title: 'We find the errors', body: 'Every charge is benchmarked against Medicare rates and checked for duplicates and coding errors' },
      step3: { title: 'Get your report', body: 'Download a full analysis report and a ready-to-send dispute letter' },
      nav: { reports: 'Your reports live in Reports', billing: 'Payment receipts are in Billing' },
      cta: 'Upload my first bill', back: 'Back',
    },
    saving: 'Setting up your account\u2026', error: 'Something went wrong. Please try again.',
  },
  es: {
    language: { title: 'Elige tu idioma', subtitle: 'Puedes cambiarlo en cualquier momento en tu perfil', continue: 'Continuar' },
    profile: {
      title: 'Cuéntanos sobre ti', subtitle: 'Esto nos ayuda a comparar tus cargos con precisión',
      nameLabel: 'Nombre completo', namePlaceholder: 'Jane Smith',
      dobLabel: 'Fecha de nacimiento',
      stateLabel: 'Estado', statePlaceholder: 'Selecciona tu estado',
      zipLabel: 'Código postal', zipPlaceholder: 'ej. 90210',
      insuranceLabel: '¿Qué tipo de seguro tienes?',
      insurance: { commercial: 'Comercial', commercialSub: 'Plan del empleador o mercado', medicare: 'Medicare', medicareSub: 'Seguro federal de salud (65+)', medicaid: 'Medicaid', medicaidSub: 'Seguro estatal de salud', tricare: 'TRICARE', tricareSub: 'Cobertura militar y veteranos', selfPay: 'Pago directo', selfPaySub: 'Sin seguro' },
      continue: 'Continuar', back: 'Atrás',
      errors: { nameRequired: 'Por favor ingresa tu nombre completo', dobRequired: 'Por favor ingresa tu fecha de nacimiento', stateRequired: 'Por favor selecciona tu estado', zipRequired: 'Por favor ingresa tu código postal', zipInvalid: 'El código postal debe tener 5 dígitos', insuranceRequired: 'Por favor selecciona tu tipo de seguro' },
    },
    primer: {
      title: 'Todo listo', subtitle: 'Así funciona ClaroBill',
      step1: { title: 'Sube tu factura', body: 'Carga un PDF o foto de tu factura médica, EOB o superbill' },
      step2: { title: 'Encontramos los errores', body: 'Cada cargo se compara con las tarifas de Medicare y se revisa en busca de duplicados y errores de codificación' },
      step3: { title: 'Obtén tu informe', body: 'Descarga un análisis completo y una carta de disputa lista para enviar' },
      nav: { reports: 'Tus informes están en Informes', billing: 'Los recibos de pago están en Facturación' },
      cta: 'Subir mi primera factura', back: 'Atrás',
    },
    saving: 'Configurando tu cuenta\u2026', error: 'Algo salió mal. Por favor intenta de nuevo.',
  },
  zh: {
    language: { title: '选择语言', subtitle: '您可以随时在个人资料中更改', continue: '继续' },
    profile: {
      title: '告诉我们关于您的信息', subtitle: '这有助于我们准确比对您的费用',
      nameLabel: '全名', namePlaceholder: '张三',
      dobLabel: '出生日期',
      stateLabel: '州', statePlaceholder: '选择您的州',
      zipLabel: '邮政编码', zipPlaceholder: '如：90210',
      insuranceLabel: '您有哪种类型的保险？',
      insurance: { commercial: '商业保险', commercialSub: '雇主或市场计划', medicare: 'Medicare', medicareSub: '联邦医疗保险（65岁以上）', medicaid: 'Medicaid', medicaidSub: '州医疗救助', tricare: 'TRICARE', tricareSub: '军人及退伍军人保障', selfPay: '自费', selfPaySub: '无保险' },
      continue: '继续', back: '返回',
      errors: { nameRequired: '请输入您的全名', dobRequired: '请输入您的出生日期', stateRequired: '请选择您的州', zipRequired: '请输入您的邮政编码', zipInvalid: '邮政编码必须为5位数字', insuranceRequired: '请选择您的保险类型' },
    },
    primer: {
      title: '一切就绪', subtitle: '以下是ClaroBill的使用方式',
      step1: { title: '上传您的账单', body: '上传医疗账单、EOB或superbill的PDF或照片' },
      step2: { title: '我们找出错误', body: '每项费用都与Medicare标准进行比对，并检查重复收费和编码错误' },
      step3: { title: '获取您的报告', body: '下载完整分析报告和可直接发送的争议信函' },
      nav: { reports: '您的报告在「报告」中', billing: '付款收据在「账单」中' },
      cta: '上传我的第一张账单', back: '返回',
    },
    saving: '正在设置您的账户\u2026', error: '出现错误，请重试。',
  },
  tl: {
    language: { title: 'Piliin ang iyong wika', subtitle: 'Maaari mo itong baguhin anumang oras sa iyong profile', continue: 'Magpatuloy' },
    profile: {
      title: 'Sabihin sa amin ang tungkol sa iyo', subtitle: 'Tinutulungan kami nito na maihambing nang tumpak ang iyong mga singil',
      nameLabel: 'Buong pangalan', namePlaceholder: 'Juan dela Cruz',
      dobLabel: 'Petsa ng kapanganakan',
      stateLabel: 'Estado', statePlaceholder: 'Piliin ang iyong estado',
      zipLabel: 'ZIP code', zipPlaceholder: 'hal. 90210',
      insuranceLabel: 'Anong uri ng insurance ang mayroon ka?',
      insurance: { commercial: 'Komersyal', commercialSub: 'Plano ng employer o marketplace', medicare: 'Medicare', medicareSub: 'Federal na health insurance (65+)', medicaid: 'Medicaid', medicaidSub: 'Health insurance ng estado', tricare: 'TRICARE', tricareSub: 'Coverage para sa militar at beterano', selfPay: 'Self-Pay', selfPaySub: 'Walang insurance' },
      continue: 'Magpatuloy', back: 'Bumalik',
      errors: { nameRequired: 'Pakiusap ilagay ang iyong buong pangalan', dobRequired: 'Pakiusap ilagay ang iyong petsa ng kapanganakan', stateRequired: 'Pakiusap pumili ng estado', zipRequired: 'Pakiusap ilagay ang iyong ZIP code', zipInvalid: 'Ang ZIP code ay dapat na 5 digit', insuranceRequired: 'Pakiusap pumili ng uri ng insurance' },
    },
    primer: {
      title: 'Handa ka na', subtitle: 'Narito kung paano gumagana ang ClaroBill',
      step1: { title: 'I-upload ang iyong bill', body: 'Mag-upload ng PDF o larawan ng iyong medical bill, EOB, o superbill' },
      step2: { title: 'Hinahanap namin ang mga error', body: 'Ang bawat singil ay inihahambing sa mga rate ng Medicare at sinusuri para sa mga duplicate at coding error' },
      step3: { title: 'Kunin ang iyong ulat', body: 'I-download ang kumpletong ulat ng pagsusuri at isang dispute letter na handang ipadala' },
      nav: { reports: 'Ang iyong mga ulat ay nasa Reports', billing: 'Ang mga resibo ng bayad ay nasa Billing' },
      cta: 'I-upload ang aking unang bill', back: 'Bumalik',
    },
    saving: 'Ino-set up ang iyong account\u2026', error: 'May nangyaring mali. Pakisubukan ulit.',
  },
  vi: {
    language: { title: 'Chọn ngôn ngữ của bạn', subtitle: 'Bạn có thể thay đổi điều này bất cứ lúc nào trong hồ sơ của bạn', continue: 'Tiếp tục' },
    profile: {
      title: 'Cho chúng tôi biết về bạn', subtitle: 'Điều này giúp chúng tôi so sánh chính xác các khoản phí của bạn',
      nameLabel: 'Họ và tên', namePlaceholder: 'Nguyễn Văn A',
      dobLabel: 'Ngày sinh',
      stateLabel: 'Tiểu bang', statePlaceholder: 'Chọn tiểu bang của bạn',
      zipLabel: 'Mã ZIP', zipPlaceholder: 'vd. 90210',
      insuranceLabel: 'Bạn có loại bảo hiểm nào?',
      insurance: { commercial: 'Thương mại', commercialSub: 'Gói của nhà tuyển dụng hoặc thị trường', medicare: 'Medicare', medicareSub: 'Bảo hiểm y tế liên bang (65+)', medicaid: 'Medicaid', medicaidSub: 'Bảo hiểm y tế tiểu bang', tricare: 'TRICARE', tricareSub: 'Bảo hiểm quân nhân và cựu chiến binh', selfPay: 'Tự chi trả', selfPaySub: 'Không có bảo hiểm' },
      continue: 'Tiếp tục', back: 'Quay lại',
      errors: { nameRequired: 'Vui lòng nhập họ và tên đầy đủ của bạn', dobRequired: 'Vui lòng nhập ngày sinh của bạn', stateRequired: 'Vui lòng chọn tiểu bang của bạn', zipRequired: 'Vui lòng nhập mã ZIP của bạn', zipInvalid: 'Mã ZIP phải gồm 5 chữ số', insuranceRequired: 'Vui lòng chọn loại bảo hiểm của bạn' },
    },
    primer: {
      title: 'Bạn đã sẵn sàng', subtitle: 'Đây là cách ClaroBill hoạt động',
      step1: { title: 'Tải lên hóa đơn của bạn', body: 'Tải lên PDF hoặc ảnh chụp hóa đơn y tế, EOB hoặc superbill của bạn' },
      step2: { title: 'Chúng tôi tìm ra lỗi', body: 'Mỗi khoản phí được so sánh với mức giá Medicare và kiểm tra các khoản trùng lặp và lỗi mã hóa' },
      step3: { title: 'Nhận báo cáo của bạn', body: 'Tải xuống báo cáo phân tích đầy đủ và thư khiếu nại sẵn sàng gửi đi' },
      nav: { reports: 'Báo cáo của bạn nằm trong Reports', billing: 'Biên lai thanh toán nằm trong Billing' },
      cta: 'Tải lên hóa đơn đầu tiên của tôi', back: 'Quay lại',
    },
    saving: 'Đang thiết lập tài khoản của bạn\u2026', error: 'Đã xảy ra lỗi. Vui lòng thử lại.',
  },
};

// Language options shown on the first step
const LANGUAGE_OPTIONS: { locale: Locale; native: string; english: string }[] = [
  { locale: 'en', native: 'English',    english: 'English'    },
  { locale: 'es', native: 'Español',    english: 'Spanish'    },
  { locale: 'zh', native: '中文',        english: 'Chinese'    },
  { locale: 'tl', native: 'Filipino',   english: 'Tagalog'    },
  { locale: 'vi', native: 'Tiếng Việt', english: 'Vietnamese' },
];

const INSURANCE_OPTIONS: {
  type: InsuranceType;
  label: (ins: InsuranceMessages) => string;
  sub: (ins: InsuranceMessages) => string;
}[] = [
  { type: 'commercial', label: (i) => i.commercial, sub: (i) => i.commercialSub },
  { type: 'medicare',   label: (i) => i.medicare,   sub: (i) => i.medicareSub   },
  { type: 'medicaid',   label: (i) => i.medicaid,   sub: (i) => i.medicaidSub   },
  { type: 'tricare',    label: (i) => i.tricare,    sub: (i) => i.tricareSub    },
  { type: 'self_pay',   label: (i) => i.selfPay,    sub: (i) => i.selfPaySub    },
];

// ── Component ─────────────────────────────────────────────────────────────────

export function OnboardingWizard(): JSX.Element {
  const router = useRouter();

  const [step, setStep]     = useState<Step>('language');
  const [locale, setLocale] = useState<Locale>('en');

  // Profile form state
  const [fullName, setFullName]       = useState('');
  const [dateOfBirth, setDateOfBirth] = useState('');
  const [state, setState]             = useState('');
  const [zipCode, setZipCode]         = useState('');
  const [insurance, setInsurance]     = useState<InsuranceType | ''>('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [saving, setSaving]       = useState(false);
  const [saveError, setSaveError] = useState('');

  const [showScanner, setShowScanner] = useState(false);
  const [lastScan, setLastScan] = useState<{ confident: boolean } | null>(null);

  function handleScanExtracted(result: InsuranceCardExtraction): void {
    const scanned = result.planType;
    if (scanned && (VALID_INSURANCE_TYPES as string[]).includes(scanned)) {
      setInsurance(scanned as InsuranceType);
    }
    setLastScan({ confident: result.confident });
    setShowScanner(false);
  }

  const t = T[locale];

  // Required fields are complete — gates the Continue button
  const profileReady =
    fullName.trim().length > 0 &&
    dateOfBirth.length > 0 &&
    state.length > 0 &&
    /^\d{5}$/.test(zipCode.trim());

  // ── Handlers ────────────────────────────────────────────────────────────────

  function validateProfile(): boolean {
    const errors: Record<string, string> = {};
    if (!fullName.trim())   errors.fullName    = t.profile.errors.nameRequired;
    if (!dateOfBirth)       errors.dateOfBirth = t.profile.errors.dobRequired;
    if (!state)             errors.state       = t.profile.errors.stateRequired;
    if (!zipCode.trim())    errors.zipCode     = t.profile.errors.zipRequired;
    else if (!/^\d{5}$/.test(zipCode.trim())) errors.zipCode = t.profile.errors.zipInvalid;
    // Insurance is optional — user can add it later in profile
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  function handleProfileContinue() {
    if (validateProfile()) setStep('primer');
  }

  function handleSkipInsurance() {
    setInsurance('');
    // Validate everything except insurance before proceeding
    const errors: Record<string, string> = {};
    if (!fullName.trim())   errors.fullName    = t.profile.errors.nameRequired;
    if (!dateOfBirth)       errors.dateOfBirth = t.profile.errors.dobRequired;
    if (!state)             errors.state       = t.profile.errors.stateRequired;
    if (!zipCode.trim())    errors.zipCode     = t.profile.errors.zipRequired;
    else if (!/^\d{5}$/.test(zipCode.trim())) errors.zipCode = t.profile.errors.zipInvalid;
    setFieldErrors(errors);
    if (Object.keys(errors).length === 0) setStep('primer');
  }

  async function handleFinish() {
    setSaving(true);
    setSaveError('');

    const result = await saveOnboarding({
      fullName:      fullName.trim(),
      dateOfBirth,
      state,
      zipCode:       zipCode.trim(),
      insuranceType: insurance,
      locale,
    });

    if (result.error) {
      setSaveError(t.error);
      setSaving(false);
      return;
    }

    router.push('/dashboard');
  }

  // ── Language step ────────────────────────────────────────────────────────────

  if (step === 'language') {
    return (
      <div className={s.page}>
        <div className={s.card}>
          <div className={s.logoRow}>
            <LogoWithMark />
          </div>

          <div>
            <h1 className={s.stepTitle}>{t.language.title}</h1>
            <p className={s.langPolyglot}>English · Español · 中文 · Filipino · Tiếng Việt</p>
            <p className={s.stepSubtitle}>{t.language.subtitle}</p>
          </div>

          <div className={s.langGrid}>
            {LANGUAGE_OPTIONS.map((opt) => (
              <button
                key={opt.locale}
                className={`${s.langBtn} ${locale === opt.locale ? s.langBtnActive : ''}`}
                onClick={() => setLocale(opt.locale)}
                type="button"
              >
                <span className={s.langNative}>{opt.native}</span>
                <span className={s.langEnglish}>{opt.english}</span>
              </button>
            ))}
          </div>

          <button className={s.primaryBtn} onClick={() => setStep('profile')} type="button">
            {t.language.continue}
          </button>
        </div>

        <div className={s.dots}>
          <span className={`${s.dot} ${s.dotActive}`} />
          <span className={s.dot} />
          <span className={s.dot} />
        </div>
      </div>
    );
  }

  // ── Profile step ─────────────────────────────────────────────────────────────

  if (step === 'profile') {
    return (
      <div className={s.page}>
        <div className={s.card}>
          <div className={s.logoRow}>
            <LogoWithMark />
          </div>

          <div>
            <h1 className={s.stepTitle}>{t.profile.title}</h1>
            <p className={s.stepSubtitle}>{t.profile.subtitle}</p>
          </div>

          <div className={s.formSection}>
            {/* Full name — full width */}
            <div className={s.formField}>
              <label className={s.formLabel} htmlFor="ob-name">{t.profile.nameLabel}</label>
              <input
                id="ob-name"
                className={`${s.formInput} ${fieldErrors.fullName ? s.formInputError : ''}`}
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder={t.profile.namePlaceholder}
                autoComplete="name"
              />
              {fieldErrors.fullName && <span className={s.fieldError}>{fieldErrors.fullName}</span>}
            </div>

            {/* Date of birth — full width, own row so it's always a large tap target */}
            <div className={s.formField}>
              <label className={s.formLabel} htmlFor="ob-dob">{t.profile.dobLabel}</label>
              <input
                id="ob-dob"
                className={`${s.formInput} ${fieldErrors.dateOfBirth ? s.formInputError : ''}`}
                type="date"
                value={dateOfBirth}
                onChange={(e) => setDateOfBirth(e.target.value)}
                max={new Date().toISOString().split('T')[0]}
              />
              {fieldErrors.dateOfBirth && <span className={s.fieldError}>{fieldErrors.dateOfBirth}</span>}
            </div>

            {/* State + ZIP — side by side, wraps on very small screens */}
            <div className={s.formRow}>
              <div className={s.formField}>
                <label className={s.formLabel} htmlFor="ob-state">{t.profile.stateLabel}</label>
                <select
                  id="ob-state"
                  className={`${s.formSelect} ${fieldErrors.state ? s.formInputError : ''}`}
                  value={state}
                  onChange={(e) => setState(e.target.value)}
                >
                  <option value="">{t.profile.statePlaceholder}</option>
                  {US_STATES.map((st) => (
                    <option key={st} value={st}>{st}</option>
                  ))}
                </select>
                {fieldErrors.state && <span className={s.fieldError}>{fieldErrors.state}</span>}
              </div>

              <div className={s.formField} style={{ maxWidth: '140px' }}>
                <label className={s.formLabel} htmlFor="ob-zip">{t.profile.zipLabel}</label>
                <input
                  id="ob-zip"
                  className={`${s.formInput} ${fieldErrors.zipCode ? s.formInputError : ''}`}
                  type="text"
                  inputMode="numeric"
                  maxLength={5}
                  value={zipCode}
                  onChange={(e) => setZipCode(e.target.value.replace(/\D/g, ''))}
                  placeholder={t.profile.zipPlaceholder}
                  autoComplete="postal-code"
                />
                {fieldErrors.zipCode && <span className={s.fieldError}>{fieldErrors.zipCode}</span>}
              </div>
            </div>

            {/* Insurance type */}
            <div className={s.insuranceSection}>
              <div className={s.insuranceHeader}>
                <p className={s.insuranceLabel}>{t.profile.insuranceLabel}</p>
                <span className={s.optionalBadge}>Optional</span>
              </div>

              {/* Scan card button */}
              <button
                type="button"
                className={s.scanBtn}
                onClick={() => setShowScanner(true)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                  <circle cx="12" cy="13" r="4"/>
                </svg>
                Scan or upload insurance card
              </button>

              {lastScan !== null && (
                <p className={s.scanSuccess}>
                  {insurance
                    ? `Card read \u2014 ${INSURANCE_OPTIONS.find((o) => o.type === insurance)?.label(t.profile.insurance) ?? insurance} auto-selected`
                    : 'Card read \u2014 select your plan type below'}
                </p>
              )}

              <div className={s.insuranceGrid}>
                {INSURANCE_OPTIONS.map((opt) => (
                  <button
                    key={opt.type}
                    type="button"
                    className={`${s.insuranceBtn} ${insurance === opt.type ? s.insuranceBtnActive : ''}`}
                    onClick={() => setInsurance(opt.type)}
                  >
                    <span className={s.insuranceName}>{opt.label(t.profile.insurance)}</span>
                    <span className={s.insuranceSub}>{opt.sub(t.profile.insurance)}</span>
                  </button>
                ))}
              </div>

              <p className={s.insuranceSkip}>
                No insurance info yet?{' '}
                <button type="button" className={s.skipLink} onClick={handleSkipInsurance}>
                  Skip for now
                </button>
                {' '}— add it in your profile later.
              </p>
            </div>
          </div>

          <div className={s.formActions}>
            <button className={s.ghostBtn} onClick={() => setStep('language')} type="button">
              {t.profile.back}
            </button>
            <button
              className={s.primaryBtn}
              onClick={handleProfileContinue}
              type="button"
              disabled={!profileReady}
            >
              {t.profile.continue}
            </button>
          </div>
        </div>

        <div className={s.dots}>
          <span className={s.dot} />
          <span className={`${s.dot} ${s.dotActive}`} />
          <span className={s.dot} />
        </div>

        {showScanner && (
          <CardScanner
            onExtracted={handleScanExtracted}
            onClose={() => setShowScanner(false)}
          />
        )}
      </div>
    );
  }

  // ── Primer step ──────────────────────────────────────────────────────────────

  return (
    <div className={s.page}>
      <div className={s.card}>
        <div className={s.logoRow}>
          <LogoWithMark />
        </div>

        <div>
          <h1 className={s.stepTitle}>{t.primer.title}</h1>
          <p className={s.stepSubtitle}>{t.primer.subtitle}</p>
        </div>

        <div className={s.primerSteps}>
          {[t.primer.step1, t.primer.step2, t.primer.step3].map((primerStep, i) => (
            <div key={i} className={s.primerStep}>
              <div className={s.primerNum}>{i + 1}</div>
              <div>
                <p className={s.primerStepTitle}>{primerStep.title}</p>
                <p className={s.primerStepBody}>{primerStep.body}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Nav pointers — icons match the dashboard bottom tab bar */}
        <div className={s.navHints}>
          <div className={s.navHint}>
            <svg className={s.navHintIcon} viewBox="0 0 24 24" fill="none" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <path d="M3 9h18M9 21V9"/>
            </svg>
            <span>{t.primer.nav.reports}</span>
          </div>
          <div className={s.navHint}>
            <svg className={s.navHintIcon} viewBox="0 0 24 24" fill="none" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="2" y="5" width="20" height="14" rx="2"/>
              <path d="M2 10h20"/>
            </svg>
            <span>{t.primer.nav.billing}</span>
          </div>
        </div>

        {saveError && <p className={s.saveError}>{saveError}</p>}

        <div className={s.formActions}>
          <button className={s.ghostBtn} onClick={() => setStep('profile')} type="button" disabled={saving}>
            {t.primer.back}
          </button>
          <button className={s.primaryBtn} onClick={handleFinish} type="button" disabled={saving}>
            {saving ? t.saving : t.primer.cta}
          </button>
        </div>
      </div>

      <div className={s.dots}>
        <span className={s.dot} />
        <span className={s.dot} />
        <span className={`${s.dot} ${s.dotActive}`} />
      </div>
    </div>
  );
}
