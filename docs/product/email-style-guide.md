# ClaroBill Weekly Email Style Guide

Canonical format for "This week from ClaroBill" newsletter campaigns sent via Loops.
Use this for every weekly send. It encodes the layout, voice, brand tokens, technical
guardrails, and pre-send checklist so each campaign feels like part of a series and
nothing has to be re-decided from scratch.

> **Repo rule.** Per `feedback_email_files_not_committed`, do not commit MJML files,
> rendered HTML, or campaign copy to the repo. Build the MJML on the Desktop, zip it,
> upload to Loops. This guide is documentation only — it tells you how to assemble
> each campaign, not what to send.

---

## 1. Voice and tone rules

These are non-negotiable. They apply to every line of every email.

| Rule | Why |
|---|---|
| No em-dashes (`—`). Use periods, commas, or "and." | Em-dashes are an AI-tell that erodes trust. |
| No emojis anywhere. Use brand-approved icons or HTML entities only. | Brand consistency. SMS/inbox previews mangle emojis. |
| No vendor names (Supabase, Stripe, Google, Vercel, Loops, etc.) in body copy. | Public-facing surfaces use categories only. |
| No methodology references (Medicare fee schedule, NCCI edits, fee benchmarks). | IP protection. Describe outcomes. |
| Recommend the itemized bill in every email. | Itemized bills are the only ones with the data we can analyze. |
| Plain English. Read every sentence aloud. If it sounds like a press release, rewrite. | The audience is patients, not procurement. |
| One CTA per section, two maximum per email. | More CTAs reduce overall click-through. |

---

## 2. Brand tokens (must match exactly)

| Token | Value | Used for |
|---|---|---|
| Cream background | `#F4F2EC` | Page background, "QUICK HITS" card |
| White | `#ffffff` | Main email wrapper background |
| Sage dark | `#2D4A2A` | Top accent bar, buttons, eyebrow text, italic ClaroBill mark |
| Lime accent | `#C8F060` | The "C" in the logo bug, nothing else |
| Ink (text dark) | `#1A1A14` | Headlines, bolded bullet leads |
| Body text | `#5A5A50` | All paragraph copy |
| Muted | `#9A9A8E` | Eyebrows ("THIS WEEK FROM"), footer, captions |
| Border | `#E2DDD4` | Dividers, footer top border |

| Font | When |
|---|---|
| `'Helvetica Neue', Helvetica, Arial, sans-serif` | Default for body, eyebrows, bullets, sign-off, the inline "ClaroBill" mention in prose |
| `Georgia, 'Times New Roman', serif` | Logo wordmark only, and major headlines |

**Critical:** Inside running prose (the eyebrow, the sign-off, the QUICK HITS body),
"ClaroBill" appears as **plain unstyled text** — same font, same weight, same color
as the surrounding body copy. No bold, no italic, no serif, no color shift. The
italic serif treatment is reserved exclusively for the logo block at the top of
the email. Stylizing the brand name inline reads as performative and breaks the
conversational tone.

| Layout | Default alignment |
|---|---|
| Eyebrow `THIS WEEK FROM CLAROBILL` | Left-aligned. Plain uppercase muted sans-serif. No special treatment on "CLAROBILL". |
| Lead headline (Georgia serif) | Left-aligned. |
| Lead paragraph | Left-aligned. |
| Category eyebrow (`EXPLAINER`, `GUIDE`, etc.) | Left-aligned. |
| Article title | Left-aligned. |
| Article body paragraphs | Left-aligned. |
| QUICK HITS card contents | Left-aligned. |
| Sign-off paragraph | Left-aligned. |
| Buttons (CTA) | Center-aligned (the only centered element below the logo). |

**The logo is the only centered element above the divider.** Everything else flows
left-aligned, matching standard newsletter reading patterns.

---

## 3. Dark-mode protection (mandatory technical scaffold)

Every campaign MUST start with this exact head + wrapper structure. Gmail iOS, Apple
Mail dark mode, and Outlook will otherwise invert the cream background into near-black.
This scaffold is the only reliable fix in 2026.

```mjml
<mj-head>
  <mj-attributes>
    <mj-all font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" />
    <mj-text font-size="15px" color="#5A5A50" line-height="1.6" padding="0" />
  </mj-attributes>
  <mj-raw>
    <meta name="color-scheme" content="light only">
    <meta name="supported-color-schemes" content="light">
  </mj-raw>
  <mj-style>
    :root, body { color-scheme: light only; }
    @media (prefers-color-scheme: dark) {
      body, .email-body { background-color: #F4F2EC !important; }
    }
  </mj-style>
</mj-head>

<mj-body background-color="#F4F2EC" css-class="email-body">
  <mj-raw><div style="color-scheme:light only;display:block;"></mj-raw>
  ... content ...
  <mj-raw></div></mj-raw>
</mj-body>
```

Three independent mechanisms (head meta, scoped CSS, inline-styled wrapper div) are
required because each email client picks a different one. Removing any one will break
dark-mode rendering somewhere.

---

## 4. Section anatomy (recurring weekly template)

Sections appear in this exact order. Some are optional per the table; most are fixed.

| # | Section | Required | Notes |
|---|---|---|---|
| 1 | Top sage accent bar | yes | 5px sage bar at the very top |
| 2 | Logo block | yes | Centered. Lime "C" bug + Georgia italic wordmark. Only centered block. |
| 3 | Eyebrow `THIS WEEK FROM CLAROBILL` | yes | **Left-aligned.** Plain uppercase muted sans-serif. No italic serif on the brand name. |
| 4 | Lead headline (Georgia serif) | yes | **Left-aligned.** One sentence brand-promise statement. Avoid hyphenated compounds (`5-digit`, `30-second`) that wrap awkwardly. |
| 5 | Lead paragraph | yes | **Left-aligned.** One short paragraph setting up the week's content. |
| 6 | Divider rule | yes | Thin `#E2DDD4` border, full content width. |
| 7 | Category eyebrow | yes | **Left-aligned.** One of: `EXPLAINER`, `GUIDE`, `STORY`, `UPDATE`, `Q&A` |
| 8 | Article title (Georgia serif) | yes | **Left-aligned.** The actual content title for this week. |
| 9 | Article body | yes | **Left-aligned.** 2 to 4 short paragraphs. Conversational. |
| 10 | Optional video block | no | Caption + button, no thumbnail. See §5. |
| 11 | Primary CTA button | yes | Centered. "Read the full guide" or equivalent. Sage background, white text, pill shape. |
| 12 | QUICK HITS card | yes | Cream rounded card, contents left-aligned, 3 to 5 bolded-lead bullets. See §6. |
| 13 | Sign-off paragraph | yes | **Left-aligned.** Warmth + plain unstyled "ClaroBill" (no bold, no italic, matches body). See §7. |
| 14 | Footer | yes | Privacy / Terms / Support / `{unsubscribe_link}`. See §8. |

---

## 5. Video embedding (when the week's content includes a video)

Email clients do not render `<iframe>`. **Do not use YouTube thumbnail hotlinks.**
`img.youtube.com` is consistently blocked by:

- The Loops dashboard preview pane
- Corporate Outlook gateways
- Many image-proxy services used by privacy-focused inboxes

When the thumbnail breaks, you get a broken-image icon and dangling alt text. That
looks worse than no thumbnail at all.

**The pattern that works in every client** is button-only:

1. **Caption line** (muted text, left-aligned with the surrounding paragraphs):
   `Watch the video. 30 seconds, no jargon.`
2. **Play button** (centered, sage-white pill, label: `Play the video`)

The button links to `https://www.youtube.com/watch?v=<VIDEO_ID>`.

**If you really need a thumbnail in a future campaign** (because the visual is the
point), the only reliable path is to self-host:

1. Download `https://img.youtube.com/vi/<VIDEO_ID>/hqdefault.jpg`
2. Upload to a public Supabase Storage bucket (or any CDN)
3. Use that hosted URL in `mj-image src=`

Never reference `img.youtube.com` directly.

---

## 6. QUICK HITS card

A cream-background rounded card with 3 to 5 bullets. Each bullet follows this pattern:

> **\<Bold lead phrase ending with a period.\>** \<One sentence of follow-through copy.\>

The bold lead is the takeaway. The follow-through gives just enough context to make
it actionable. No nested bullets. No "click to learn more" links inside the card —
the card is the synthesis, the full guide is reached via the primary CTA above it.

Examples (anchor-style, for shape only — do not reuse verbatim):

- **Get the itemized bill.** Summary bills hide the codes. Without them you cannot verify anything.
- **Match codes to what happened.** Each line should map to an actual procedure from your visit.
- **Question, then dispute.** If something does not add up, ask for an explanation in writing.

Eyebrow above the card: `QUICK HITS` in sage caps, same styling as section eyebrows.

---

## 7. Sign-off

One short paragraph, centered, warm. Always references the brand name in the italic
serif sage mark. Always closes with a "we are here" sentiment. No exclamation points.

Template:

> Thanks for trusting **ClaroBill** to help you navigate your medical bills. We are here every step of the way.

Variations are fine. The voice should feel like a small team writing to one person.

---

## 8. Footer (fixed)

```
© 2026 ClaroBill · Privacy · Terms · support@clarobill.com · Unsubscribe
```

- 12px, muted color (`#9A9A8E`), single line.
- 1px top border in `#E2DDD4`.
- Privacy → `https://www.clarobill.com/legal/privacy`
- Terms → `https://www.clarobill.com/legal/terms`
- Support → `mailto:support@clarobill.com`
- Unsubscribe href: `{unsubscribe_link}` (Loops requires this exact placeholder; the
  campaign will be rejected without it).

---

## 9. Loops upload requirements

| Item | Requirement |
|---|---|
| File format | MJML (`.mjml`) zipped at the root (no parent folder inside the zip) |
| Filename | `index.mjml` |
| Build command | `cd <campaign-dir> && zip -j campaign.zip index.mjml` |
| Output location | Desktop or scratch dir. Never commit to repo. |
| Unsubscribe placeholder | `{unsubscribe_link}` (exact, with underscore) |
| Subject line | Set in Loops UI, not in MJML |
| Preview text | Set in Loops UI. 60 to 90 chars. Should not repeat the subject. |
| Audience | Filter by segment, not "all users." A free-tier-no-upload segment is the default. |

---

## 10. Pre-send checklist

Run this before clicking Send in Loops. Every item must pass.

- [ ] Dark-mode head scaffold present (meta + mj-style + mj-raw wrapper div)
- [ ] `{unsubscribe_link}` in the footer href
- [ ] Zero em-dashes (`grep —` returns 0)
- [ ] Zero emojis
- [ ] Zero vendor names in body copy
- [ ] Zero methodology terms (Medicare, NCCI, fee schedule, benchmark)
- [ ] Italic-serif "ClaroBill" mark used at least twice (eyebrow + sign-off)
- [ ] Primary CTA button is white-on-sage, pill shape, centered
- [ ] All headlines use Georgia serif; all body uses Helvetica Neue
- [ ] QUICK HITS card present, 3 to 5 bullets, bolded leads
- [ ] Test send to your own inbox on **mobile Gmail (iOS)** AND **desktop Apple Mail**
- [ ] On the mobile test, the background is cream, not dark
- [ ] On the mobile test, the video thumbnail loads (if a video is present)
- [ ] All links open the correct URL with no extra tracking parameters in the visible href
- [ ] Subject and preview text set in the Loops UI

---

## 11. Common pitfalls

- **YouTube `maxresdefault.jpg` broken.** Use `hqdefault.jpg` instead — always present.
- **Dark-mode preview pane unreliable.** Loops' in-dashboard preview blocks remote
  images and does not always reflect dark-mode CSS. Trust the real test send, not the preview.
- **Image hotlinks blocked by corporate gateways.** If multiple Outlook recipients
  report broken thumbnails, self-host the image in Supabase Storage.
- **Subject line truncation.** Gmail mobile cuts at ~50 chars, Apple Mail at ~60. Front-load.
- **Mismatched colors between dark and light.** Always set `background-color` explicitly
  on every section that needs the cream tone. Do not rely on body inheritance alone.
- **`align="left"` on buttons.** Defaults to left in MJML. Always set `align="center"`
  on the button itself, not just the parent column.

---

## 12. Workflow

1. **Plan the week's topic.** One core idea, one article, optional one video.
2. **Draft headline + lead paragraph** in plain text before opening any MJML.
3. **Copy last week's `index.mjml`** as the starting point. Replace the article block
   and the QUICK HITS card. Leave everything else alone.
4. **Run the §10 checklist.**
5. **Send a test to yourself** on at least two clients.
6. **Zip and upload to Loops.** Set subject, preview, audience.
7. **Schedule** for the standard weekly send slot.
