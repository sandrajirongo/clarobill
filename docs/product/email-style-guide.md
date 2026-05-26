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
| `'Helvetica Neue', Helvetica, Arial, sans-serif` | Default for body, eyebrows, bullets |
| `Georgia, 'Times New Roman', serif` | Logo wordmark, all major headlines, the italic "ClaroBill" inline mark |

The italic serif "ClaroBill" inline mark is a recurring signature element. Wherever the
brand name appears inside running prose (the eyebrow, the sign-off), it should render
in Georgia italic at the sage color, not in the default sans-serif body font.

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
| 2 | Logo block | yes | Centered. Lime "C" bug + Georgia italic wordmark. |
| 3 | Eyebrow `THIS WEEK FROM ClaroBill` | yes | Centered, muted caps, italic serif sage on the brand name |
| 4 | Lead headline (Georgia serif, centered) | yes | The week's theme statement. One sentence. Brand promise, not article title. |
| 5 | Lead paragraph (centered) | yes | One short paragraph setting up the week's content. |
| 6 | Divider rule | yes | Thin `#E2DDD4` border |
| 7 | Category eyebrow | yes | One of: `EXPLAINER`, `GUIDE`, `STORY`, `UPDATE`, `Q&A` |
| 8 | Article title (Georgia serif, left-aligned) | yes | The actual content title for this week |
| 9 | Article body (left-aligned paragraphs) | yes | 2 to 4 short paragraphs. Conversational. |
| 10 | Optional inline media | no | Video thumbnail, image, or pull quote. If a video, see §5. |
| 11 | Primary CTA button (centered) | yes | "Read the full guide" or equivalent. Sage background, white text, pill shape. |
| 12 | QUICK HITS card | yes | Cream rounded card, 3 to 5 bolded-lead bullets. See §6. |
| 13 | Sign-off paragraph (centered) | yes | Warmth + "ClaroBill" italic serif mark. See §7. |
| 14 | Footer | yes | Privacy / Terms / Support / `{unsubscribe_link}`. See §8. |

---

## 5. Video embedding (when the week's content includes a video)

Email clients do not render `<iframe>`. The universal pattern is:

1. **Thumbnail image** linked to the watch URL.
   Use `https://img.youtube.com/vi/<VIDEO_ID>/hqdefault.jpg` (always available, every video).
   Not `maxresdefault.jpg` — that only exists for HD uploads and silently breaks on shorts.
2. **Caption line** under the thumbnail: `"30 seconds, no jargon"` style. Muted color, small.
3. **Play button** below the caption. Same sage-white pill as other CTAs. Label states the
   duration: `Play the 30-second video`.
4. **Center-align** the entire video block (image, caption, button).

The thumbnail and the button both link to the same `youtube.com/watch?v=...` URL.
Two click targets is intentional — image-blocked clients still get the button.

If a real send shows a broken thumbnail (some corporate gateways blacklist
`img.youtube.com`), the fallback is to download the thumbnail, upload it to a public
Supabase Storage bucket, and reference your own hosted copy in the `src=`.

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
