# Email Campaign: After You Send a Dispute Letter

**Audience:** All subscribers + registered users  
**Trigger:** Newsletter broadcast OR 1-day delay after `disputeLetterSent` event  
**Article link:** https://www.clarobill.com/learn/what-happens-after-you-dispute-a-medical-bill

---

## Subject line options (pick one or A/B test)

**A (specific, creates urgency):**
> You sent the dispute letter. Here is what happens in the next 30 days.

**B (curiosity-first):**
> The step most people skip after sending a dispute letter

**C (direct pain point):**
> Your dispute letter is sitting somewhere. Here is how to make sure it does not disappear.

---

## Preview text

> Most hospitals have a 30-day review window. Most patients wait and hope. Here is what to do instead.

---

## Email body

---

**[LOGO BLOCK]**
ClaroBill wordmark, centered, white background

---

**[HEADLINE BLOCK]**

You sent the letter. The clock is running.

---

**[TEXT BLOCK 1]**

Most hospitals run dispute letters through an internal billing review that takes 2 to 4 weeks. You will not hear much during that window. That silence is not a sign the dispute is going well or badly. It just means a coder has not gotten to it yet.

What you do in the next 30 days determines whether your dispute gets resolved or quietly closed.

---

**[TEXT BLOCK 2 — Three things to do right now]**

**Pay the part you are not disputing.**  
Do not withhold the full bill. Withholding everything looks like non-payment, not a dispute. Pay what you agree is correct and isolate the contested amount in writing.

**Document the date and method you sent it.**  
Certified mail tracking number, email read receipt, fax confirmation. If the hospital later claims they never received it, you need proof of delivery.

**Set a reminder for day 30.**  
If you have not heard back by then, call. Ask for the name of the person handling your dispute and request a written status update by a specific date. Every follow-up needs a deadline.

---

**[TEXT BLOCK 3]**

There are three ways a dispute can come back: full resolution, partial resolution, or denial. A denial at the billing department level is not a final answer. It is a prompt to escalate. Your insurer's appeals process, your state insurance commissioner, and the hospital's own patient advocate are all escalation paths most people never use because they do not know they exist.

The full breakdown is in our guide, including what to say, who to call, and what to do if the hospital sends the bill to collections while your dispute is still pending.

---

**[CTA BUTTON]**
Text: Read the full guide  
URL: https://www.clarobill.com/learn/what-happens-after-you-dispute-a-medical-bill  
Style: Sage (#2D4A2A) background, white text, 16px, full-width on mobile

---

**[DIVIDER]**

---

**[FOOTER TEXT]**

ClaroBill finds errors in medical bills and writes the dispute letter for you.  
Free to analyze. No percentage of savings taken.

[Unsubscribe] · [Privacy Policy](https://www.clarobill.com/legal/privacy)

ClaroBill · hello@clarobill.com

---

## Loops setup notes

- **Campaign type:** Broadcast (send to all) OR Journey step (1 day after `disputeLetterSent` event)
- **From name:** ClaroBill
- **From address:** hello@clarobill.com
- **Reply-to:** hello@clarobill.com
- **List:** All subscribers (newsletter list) + registered users with `disputeLetterSent` property
- **Personalization variable available:** `{{firstName}}` — if you want to open with "Hi {{firstName}}," swap the headline for a personalized greeting and move the current headline into the first text block
- **UTM params to add to CTA URL:**
  `?utm_source=loops&utm_medium=email&utm_campaign=after-dispute-letter`

---

## Personalized variant (if sending to users who have a dispute letter)

Swap the headline block for:

> Your dispute letter is in. Here is what to expect.

And open the first text block with:

> You sent your dispute letter through ClaroBill. Now there is a waiting period most people are not prepared for.

Everything else stays the same.
