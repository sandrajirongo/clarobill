# ClaroBill Brand & Design Guidelines

Version 1.0 — April 2026

---

## 1. Brand Identity

### Mission
ClaroBill helps people find errors in their medical bills through AI-powered analysis, plain-English reporting, and ready-to-send dispute letters. The brand communicates **trust, competence, and calm authority** — we are the professional, measured advocate in a confusing system.

### Personality
- **Expert without being cold.** We speak plainly and confidently. Not clinical, not casual.
- **Honest without being alarming.** We surface serious errors without sensationalizing.
- **Modern and precise.** The design is clean and intentional, not decorated.

### Voice
- **Active voice.** "We found three errors" not "Three errors were found."
- **Specific.** "Your bill has a $340 duplicate charge for CPT 99213" not "There may be an issue."
- **No jargon in user-facing copy.** Medical codes are explained, not assumed.
- **Short sentences in UI.** Longer explanations belong in reports and documentation.

---

## 2. Logo

### Wordmark
The primary identifier is the **ClaroBill wordmark**: "Claro" in Fraunces roman, "Bill" in Fraunces italic. The period after the wordmark is optional (used in the nav) and signals confident finality.

```
Claro*Bill*.
```

### Logo Mark
A 38×38px rounded square (border-radius: 10px) in Sage (`#2D4A2A`) containing the letter "C" in Fraunces italic, Lime (`#C8F060`). Used in auth pages, emails, and favicon-adjacent contexts.

### Clear Space
The wordmark must have at least its cap-height of clear space on all sides. Never place the logo on a background that reduces contrast below 4.5:1.

### Don't
- Don't change the weight relationship (Claro = 700 roman, Bill = 700 italic)
- Don't recolor individual letters
- Don't stretch or compress
- Don't use the period in body copy or buttons

---

## 3. Color System

All colors are defined as CSS custom properties in `apps/web/src/app/globals.css`.

### Primary Palette

| Token | Hex | Usage |
|---|---|---|
| `--sage` | `#2D4A2A` | Primary action color. Buttons, active nav, highlights. |
| `--sage-l` | `#3A5E37` | Sage hover state. |
| `--sage-dark` | `#1E3019` | Dark text on lime, footer background, deepest brand color. |
| `--accent` | `#C8F060` | Lime green. CTA buttons on dark backgrounds, savings badges, highlight elements. |
| `--accent-h` | `#D4F570` | Lime hover state. |
| `--green-em` | `#1A5C1A` | Italic em emphasis in hero headline only. |

### Neutral Palette

| Token | Hex | Usage |
|---|---|---|
| `--cream` | `#F4F2EC` | Page background. |
| `--cream2` | `#EDE9DF` | Secondary backgrounds, tab bars, inactive pills. |
| `--cream3` | `#E3DED3` | Step numbers, subtle dividers. |
| `--white` | `#FFFFFF` | Cards, inputs, upload zones. |
| `--border` | `#E2DDD4` | All borders. |
| `--txt` | `#1A1A14` | Primary text. |
| `--txt2` | `#5A5A50` | Secondary/body text. |
| `--txt3` | `#9A9A8E` | Placeholder, footer fine print, disabled states. |

### Status Colors

| Usage | Background | Foreground |
|---|---|---|
| Pending/Uploading | `var(--cream2)` | `var(--txt2)` |
| Processing (Reading/Analyzing) | `#EFF6FF` | `#1D4ED8` |
| Ready/Complete | `rgba(200, 240, 96, .25)` | `var(--sage-dark)` |
| Error/Failed | `#FEF2F2` | `#B91C1C` |
| Success message | `rgba(200, 240, 96, .2)` | `var(--sage-dark)` |
| Onboarding nudge | `rgba(200, 240, 96, .12)` | `var(--sage-dark)` (title) / `var(--txt2)` (body) |

### Color Rules
- **Never use lime (`--accent`) on a white background for text** — contrast is insufficient.
- **Sage on white passes AA** for text at 16px+. Always verify with WCAG 2.1 AA (4.5:1).
- **The hero gradient** behind stats uses: `linear-gradient(135deg, #E6F5D0 0%, #D4F0E4 45%, #C8EDF5 100%)` — do not replicate elsewhere; this is a landmark section treatment.

---

## 4. Typography

### Font Stack

| Role | Font | Token |
|---|---|---|
| Display / headings | Fraunces | `var(--fd)` |
| Body / UI | Syne | `var(--fb)` |

Both fonts are loaded via Google Fonts in the root layout. **Never substitute system fonts in production UI.**

### Fraunces (Display)
- Serif with optical size axis. Use for: page titles, hero headlines, section headings, the wordmark.
- Weights used: 700 (headings), 600 (subheadings in bold contexts).
- Italic is expressive — reserve for brand-name "Bill", hero emphasis `<em>`, and editorial callouts.
- Letter-spacing: `-0.020em` to `-0.025em` at large sizes, `-0.020em` at smaller display.

### Syne (Body/UI)
- Geometric sans-serif. Use for: all body copy, buttons, labels, nav, form inputs, badges.
- Weights used: 400 (body), 500 (nav links, secondary labels), 600 (button labels), 700 (primary buttons, bold UI).
- Letter-spacing: `0` for body; `+0.01em` for buttons; `+0.03–0.07em` for ALL-CAPS labels.

### Scale

| Usage | Size | Weight | Font |
|---|---|---|---|
| Hero h1 | `clamp(2.5rem, 6vw, 3.8rem)` | 700 | Fraunces |
| Section h2 | `clamp(1.85rem, 4.5vw, 2.6rem)` | 700 | Fraunces |
| FAQ / CTA h2 | `clamp(1.9rem, 4.5vw, 2.5rem)` | 700 | Fraunces |
| Card title (auth) | `clamp(1.55rem, 4vw, 1.85rem)` | 700 | Fraunces |
| Page title (dashboard) | `clamp(1.5rem, 4vw, 1.9rem)` | 700 | Fraunces |
| Section h4 | `0.95rem` | 700 | Syne |
| Body (standard) | `0.875rem–0.92rem` | 400 | Syne |
| Body (small) | `0.84rem` | 400 | Syne |
| Labels (ALL-CAPS) | `0.72–0.80rem` | 600 | Syne |
| Fine print / note | `0.72–0.74rem` | 400 | Syne |

---

## 5. Spacing & Layout

### Grid
- **Max content width:** 760px (dashboard content), 640px (landing sections), 620px (how-it-works/what-you-get)
- **Horizontal padding:** `clamp(1rem, 4vw, 2rem)` (dashboard), `clamp(1.25rem, 5vw, 2.75rem)` (landing)

### Section Padding
- **Landing sections:** `clamp(3rem, 7vw, 5rem)` vertical
- **Stats/hero sections:** `clamp(2.75rem, 6vw, 4.5rem)` vertical
- **Dashboard page gap:** `1.75rem`

### Border Radius

| Token | Value | Usage |
|---|---|---|
| `--r-full` | `999px` | Pills, buttons, all-rounded elements |
| `--r-xl` | `1.25rem` | Cards, badges, modals, inputs |
| Cards (large) | `1.75rem` | Auth card, stats card |
| Upload zone | `1.5rem` | Upload drop target |

### Shadows
- **Cards:** `0 4px 40px rgba(0,0,0,.06)` — auth card
- **Stats card:** `0 2px 28px rgba(0,0,0,.06)`
- **Nav:** `border-bottom: 1px solid var(--border)` only — no drop shadow

---

## 6. Icon System

All icons live in `apps/web/src/components/icons.tsx`.

### Spec
- **ViewBox:** 24×24
- **Stroke:** `currentColor` (inherits from CSS `color`)
- **Stroke width:** 1.75px (2.5px for `CheckIcon`)
- **Caps/Joins:** `round` / `round`
- **Fill:** `none`
- **Render size:** controlled by `size` prop (default 20px for most, 16px for CheckIcon)

### Available Icons

| Export | Visual | Default size | Primary use |
|---|---|---|---|
| `UploadIcon` | Arrow up from tray | 20px | Upload zone, bill uploader |
| `ReportIcon` | Document with check | 20px | "What you get" — error report card |
| `LetterIcon` | Envelope | 20px | "What you get" — dispute letter card |
| `SpeedIcon` | Lightning bolt | 20px | "What you get" — speed card |
| `CheckIcon` | Checkmark | 16px | Feature lists, benefit items, confirmation |
| `FileTextIcon` | File with text lines | 20px | Bill/document references |

### Icon Containers

**Circular icon chip (sage background, white icon):**
```css
width: 44px; height: 44px; border-radius: 50%;
background: var(--sage); color: #fff;
display: flex; align-items: center; justify-content: center;
```
Used on: landing "What you get" cards, benefit items.

**Circular icon container (cream background, sage icon):**
```css
width: 52px; height: 52px; border-radius: 50%;
background: var(--cream); border: 1.5px solid var(--border);
color: var(--sage);
display: flex; align-items: center; justify-content: center;
```
Used on: upload zone idle state.

**Small benefit chip (20px, sage background):**
```css
width: 20px; height: 20px; border-radius: 50%;
background: var(--sage); color: #fff;
display: flex; align-items: center; justify-content: center;
```
Used on: auth page benefit list items.

### Adding New Icons
1. Add the export to `apps/web/src/components/icons.tsx` following the existing pattern
2. Use 24×24 viewBox and the `base` spread object
3. Use `round` linecap and linejoin
4. Prefer outline/stroke style (no filled shapes except polygons)
5. Test at 16px, 20px, and 24px render sizes

---

## 7. Components

### Buttons

**Primary (Sage):**
```css
background: var(--sage); color: #fff;
font-family: var(--fb); font-weight: 700; font-size: .95rem;
padding: .9rem 1rem; border-radius: var(--r-full);
letter-spacing: .01em;
```
Hover: `background: var(--sage-l); transform: translateY(-1px)`
Disabled: `opacity: .55; cursor: not-allowed`

**CTA (Lime on Sage background):**
```css
background: var(--accent); color: var(--sage-dark);
font-weight: 700; font-size: .97rem;
padding: .95rem 2.35rem; border-radius: var(--r-full);
```
Hover: `background: var(--accent-h); transform: translateY(-1px)`

**Nav CTA:**
```css
background: var(--sage); color: #fff;
font-size: .85rem; font-weight: 600;
padding: .58rem 1.3rem; border-radius: var(--r-full);
```

**Ghost / Text link button:**
```css
background: none; border: none; color: var(--sage);
font-size: .82rem; font-weight: 500; cursor: pointer;
```

### Form Inputs
```css
border: 1.5px solid var(--border); border-radius: var(--r-xl);
padding: .8rem 1.1rem; font-size: .92rem;
background: var(--cream);
```
Focus: `border-color: var(--sage); box-shadow: 0 0 0 3px rgba(45, 74, 42, .1); background: var(--white)`

### Cards
```css
background: var(--white); border-radius: 1.75rem;
border: 1px solid var(--border);
box-shadow: 0 4px 40px rgba(0,0,0,.06);
padding: 2.5rem 2.25rem 2.25rem;
```

### Pills / Eyebrow labels
```css
display: inline-block; background: var(--cream2);
border: 1px solid var(--border); border-radius: var(--r-full);
font-size: .72rem; font-weight: 600;
letter-spacing: .07em; text-transform: uppercase;
padding: .35rem .9rem;
```

### Section structure
Every content section follows this pattern:
1. Eyebrow pill label (optional)
2. `h2` in Fraunces
3. Content (steps, grid, etc.)

---

## 8. Motion

- **Default transition:** `0.15s ease` for color, background, border-color, opacity
- **Button lift:** `transform: translateY(-1px)` on hover
- **Accordion open:** `max-height` transition `0.32s ease` (FAQ component)
- **Logo carousel:** `scroll-logos 22s linear infinite` keyframe, pauses on hover
- **Page reveals:** `Reveal` component in `apps/web/src/components/landing/reveal.tsx` — IntersectionObserver fade-up

### Rules
- No transitions on layout properties (width, height, padding) in interactive elements — too jarring
- No bounce/spring easing — we are authoritative, not playful
- Spinner: `0.8s linear infinite` rotate — strictly utilitarian

---

## 9. Navigation

### Desktop Nav
- Sticky, height 60px, `backdrop-filter: blur(14px)` on `rgba(244, 242, 236, .95)`
- Logo left, links center-left, right-side avatar/sign-out
- Active link: sage pill (`background: var(--sage); color: #fff`)
- Inactive links: transparent until hover (`background: var(--cream2)`)

### Mobile Nav
- Bottom tab bar at ≤639px, height 58px
- Same blur/cream background, `border-top` only
- Stroke icons (22px), ALL-CAPS labels at 0.6rem

---

## 10. Do / Don't Summary

| Do | Don't |
|---|---|
| Use SVG icons from `icons.tsx` | Use emojis anywhere in UI |
| Use Fraunces for all headings | Use system fonts as a fallback style |
| Use Syne for all body/UI copy | Mix heading fonts in body copy |
| Keep buttons pill-shaped (`--r-full`) | Use square or hard-radius buttons |
| Communicate status with the status badge system | Invent new status colors ad-hoc |
| Use `var(--border)` for all borders | Use hardcoded `#ccc` or similar |
| Use `--sage` for primary actions | Use lime for text on light backgrounds |
| Show specific numbers and findings | Use vague placeholder copy ("Some data") |
| Write active, specific copy | Write passive or jargon-heavy copy |
| Use `color: currentColor` on SVGs | Hardcode stroke/fill colors on icons |

---

## 11. File Locations

| Asset | Path |
|---|---|
| Design tokens (CSS vars) | `apps/web/src/app/globals.css` |
| Icon library | `apps/web/src/components/icons.tsx` |
| Landing page CSS | `apps/web/src/app/page.module.css` |
| Dashboard CSS | `apps/web/src/app/dashboard/dashboard.module.css` |
| Auth page CSS | `apps/web/src/app/auth/sign-in/sign-in.module.css` |
| Fonts (Google Fonts) | `apps/web/src/app/layout.tsx` |
| Logo mark (nav, auth) | Inline in component JSX — no separate asset file |
| Favicon / apple-icon | `apps/web/src/app/` (icon.tsx, apple-icon.tsx) |

---

*Maintained by the ClaroBill product team. Update this document whenever a design decision is codified in the codebase.*
