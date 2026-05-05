# Agent review playbook — full-codebase audits

Reference for the multi-agent review pattern used on 2026-05-04 (29 findings,
became Phases 0-7 of the bug-fix campaign) and re-run on 2026-05-05.

`/ultrareview` reviews **diffs** — your current branch vs main, or a
specific PR. It cannot scan a whole codebase as a single review. For
full-codebase audits, dispatch parallel `Agent` tool calls instead. This
doc is the menu of which agent types do what, the prompt patterns that
work, and how to glue their findings into a single bug list.

## TL;DR — how to ask Claude to run this

Give Claude one of these prompts and it will dispatch the agents:

> "Spawn the 5/4 audit pattern: code-reviewer over engine core,
> silent-failure-hunter over the MRF pipeline, type-design-analyzer over
> the API boundary. Run them in parallel and synthesize a prioritized bug
> list."

> "Run a security-focused audit. Spawn silent-failure-hunter on the
> auth/payment surfaces and code-reviewer with a security focus on the
> request handlers. Then summarize."

> "I want a deep-review of `apps/engine/app/services/rules_engine.py`.
> Use code-reviewer with the rules-engine-specific prompt from the
> playbook."

Claude has the playbook in context — it'll pick the right agent types
and prompt shape from the table below.

---

## Available agents for code review

These are the `subagent_type` values Claude passes to the `Agent` tool.
Each one specializes in a different review angle.

### Primary review agents (use these for full-codebase audits)

| `subagent_type` | What it's good at | When to use it |
|---|---|---|
| `pr-review-toolkit:code-reviewer` | Bugs, logic errors, security vulnerabilities, project-conventions adherence (CLAUDE.md). Confidence-filtered — only reports findings it's ≥70% sure are real. | The main "find me bugs" agent. Run it on the largest / highest-blast-radius surface (`bills.py`, `rules_engine.py`, request handlers). |
| `pr-review-toolkit:silent-failure-hunter` | Bare `except`, swallowed errors, retries that mask bugs, DML writes without row-count verification, "transient" errors branded permanent or vice versa, unbounded reads, stale state after partial failure. | Anywhere correctness depends on error-path behaviour. The MRF pipeline, payment webhooks, background tasks, anything Cloud-Run-async. |
| `pr-review-toolkit:type-design-analyzer` | Encapsulation, invariant expression, type-system load-bearing-ness across boundaries (Pydantic ↔ Zod ↔ TS, DB schema ↔ application types). Rates encapsulation / invariants / usefulness / enforcement quantitatively. | Anytime a new shape crosses a process boundary, or after a type-truth migration (Phase 6 was driven by this agent). |
| `pr-review-toolkit:comment-analyzer` | Comment accuracy vs the code they describe, comment rot, stale TODOs, multi-paragraph docstrings that drift. | After generating large doc blocks; before a PR with significant comment changes; or as a "comment hygiene pass" once a year. |
| `pr-review-toolkit:pr-test-analyzer` | Test coverage gaps in a PR, edge cases that aren't asserted, untested error paths. | Pre-merge gate on a non-trivial PR. Less useful for whole-codebase audits — the Phase 7 inventory served that role. |

### Specialist review agents (narrower scope)

| `subagent_type` | What it's good at |
|---|---|
| `feature-dev:code-reviewer` | Same posture as `pr-review-toolkit:code-reviewer` but scoped to feature-dev workflows (less project-convention sensitive, more standard SWE-best-practices). Use when CLAUDE.md isn't the right rubric. |
| `pr-review-toolkit:code-simplifier` | Identifies redundant logic, unnecessary abstraction, code that could be 30% shorter without losing function. **Triggers code changes** — not just findings. Use after a feature lands, before merge. |

### Supporting agents (not review per-se, but useful in audit workflows)

| `subagent_type` | Use case |
|---|---|
| `feature-dev:code-explorer` | Map an unfamiliar subsystem before reviewing it. Cheap context-builder; spawn this first if the audit target spans multiple files and you don't know the architecture. |
| `Explore` | Same posture but read-only and faster. Best for "where is X defined / which files reference Y". |
| `Plan` | Synthesize the audit findings into an implementation plan. The 5/4 audit's Plan agent produced the 38-commit, 8-week design that became the bug-fix campaign. |
| `general-purpose` | Last-resort for compound queries that don't fit a specialized agent. Slower and broader. |

### Built-in skills for security-only reviews

These run as `Skill` invocations (slash commands), not `Agent` calls:

| Skill | Triggers as |
|---|---|
| `/security-review` | Security-focused review of pending changes on the current branch. Diff-based like `/ultrareview`. |
| `/review` | General PR review. Diff-based. |
| `/init` | Generates a new CLAUDE.md from codebase analysis (one-time). |

---

## The 5/4 audit pattern (recipe — re-run as needed)

This is the exact 3-agent fan-out that produced the 29 findings the
bug-fix campaign closed.

```
                     ┌─ pr-review-toolkit:code-reviewer
                     │     scope: engine core services + API surface
Sandra asks Claude ──┼─ pr-review-toolkit:silent-failure-hunter
                     │     scope: MRF pipeline (scrape + parse + discovery)
                     └─ pr-review-toolkit:type-design-analyzer
                           scope: Pydantic ↔ Zod ↔ TS boundary

  ↓ (run in parallel, async)

Claude consolidates findings + ranks severity → prioritized bug list
  ↓
(optional) Plan agent synthesizes a phased fix plan
  ↓
Sandra approves; auto-mode executes phase by phase
```

### When to re-run

- After a subsystem rewrite (post-Phase 4 the MRF pipeline was rebuilt;
  post-Phase 6 the type boundary was consolidated — both warranted a
  new audit pass)
- Before a major launch (e.g., GA flip on 2026-07-02 — re-audit auth +
  payment + RLS surfaces)
- Every quarter regardless, as a "drift check" against new code that
  bypassed the per-PR `/ultrareview` gate
- After a significant infra change (new external API, new DB schema,
  new background-task framework)

### Cost shape (rough)

Each agent runs ~5-15 minutes wall-clock and consumes proportional tokens.
Three parallel agents on a codebase the size of ClaroBill (~25K LOC of
non-test code) cost roughly the same as one focused 30-minute coding
session with Claude. Cheaper than a single human-engineer review hour;
finds things the human would miss too.

---

## Prompt patterns that work

Each agent has a personality. Generic prompts produce generic findings.
The patterns below are what the 5/4 audit used (lifted from the saved
session at `~/.claude/projects/.../4a61fe70-ae12-4e0a-b92a-5477a1040c6e/`).

### Pattern: code-reviewer (full-codebase audit, not diff-based)

```
Perform a deep, holistic code review of <scope>. This is a full-codebase
audit, NOT a PR-diff review — read the files in their current state on
`main` (HEAD = <commit>).

Scope (in priority order):
1. <highest-blast-radius file> — <one line on what it does>
2. <next file>
...

Look for:
- Bugs (logic errors, off-by-ones, missing edge cases, wrong defaults)
- Silent failure paths (exceptions swallowed without telemetry)
- Race conditions (background-task ordering, concurrent writes)
- Security issues (PHI in logs, prompt injection, SSRF, parameterless SQL)
- Type-safety regressions
- Pre-existing TODOs that aren't tracked anywhere
- Dead code from past migrations

Skip: <things you don't want re-flagged>

Use confidence-based filtering — only report findings ≥70% confident,
with file_path:line_number references. Group by severity:
STOP-THE-LINE / HIGH / MEDIUM / LOW. Tag every finding with a short ID
(e.g. `S1`, `H4`) for traceability to fix commits.

Reference docs: docs/playbooks/bug-fix-campaign.md (29 findings already
closed; do NOT re-flag these), CLAUDE.md (the 16 engineering rules —
flag rule violations explicitly).
```

### Pattern: silent-failure-hunter

```
Hunt silent failures across <pipeline / subsystem>.

Scope: <specific files>

Specifically hunt for:
- bare `except Exception` blocks that log a warning and continue
- Retries that hide a deterministic bug
- DML writes that don't verify affected_rows
- Empty-result handling that should be a warning but is silent
- Boolean status flags set to True before work succeeds
- File / blob writes that don't fsync or verify
- Pagination loops without a hard cap
- "Transient" failures branded permanent or vice versa
- Stale state retention after partial failure
- Memory unbounded reads

For each finding give:
- File path + line number(s)
- The exception/state path being silenced
- The user-visible consequence
- Severity (STOP-THE-LINE / HIGH / MEDIUM / LOW)

Don't re-flag findings already closed in
docs/playbooks/bug-fix-campaign.md. Confidence ≥ 70%.
```

### Pattern: type-design-analyzer

```
Audit the type design across <boundary>.

Scope:
1. <Pydantic models file>
2. <TS interfaces file>
3. <Zod schemas file>
4. <DB CHECK constraints>
5. <mappers / parsers>

Evaluate each cross-cutting type for:
- Encapsulation — does the type hide its construction invariants?
- Invariant expression — are constraints expressible in the type system?
- Usefulness — does the type prevent past bug classes?
- Enforcement — is the constraint actually enforced at the boundary?
- Drift surface — where could Pydantic and TS get out of sync without
  the contract test catching it?

Also flag any `any`, `as`, `# type: ignore`, `@ts-ignore`, `cast` that
survives without a documented reason.

For each finding give:
- type / file path / line numbers
- The invariant not currently expressed
- The bug class it would catch
- Severity (HIGH / MEDIUM / LOW)

Skip type concerns already closed in
docs/playbooks/bug-fix-campaign.md. Confidence ≥ 70%.
```

---

## After the agents return

Claude does this synthesis automatically when the agents complete:

1. **Dedupe** findings — two agents often flag the same issue from
   different angles (a silent failure can also be a type-system gap)
2. **Tag** with stable IDs for traceability (`S1`, `H4`, `M2`, `T3`,
   `SF7`) — these become commit-message references later
3. **Severity-sort:** STOP-THE-LINE → HIGH → MEDIUM → LOW
4. **Estimate effort** per finding (1-line fix, < 1 hour, < 1 day, multi-day)
5. **Optionally** spawn a `Plan` agent to convert the punch list into a
   phased commit sequence (Phase 0 = regression gate, Phase 1 = stop-
   the-line, etc. — the 5/4 audit followed this shape)

The 2026-05-04 audit's consolidated finding list lives in the campaign
tracker at `docs/playbooks/bug-fix-campaign.md` — that's the canonical
shape of the output.

---

## Anti-patterns

- **Single mega-agent** — one general-purpose agent told to "review the
  whole codebase" produces shallow generic findings. Use specialists.
- **Sequential instead of parallel** — agents are independent; running
  them serially wastes wall-clock time without reducing tokens.
- **No "skip already-closed" instruction** — without it, agents
  re-discover the bugs you already fixed and waste output bandwidth.
- **No confidence threshold** — without `≥70% confident`, the agents
  emit dozens of "would prefer X over Y" cosmetic findings that drown
  the real bugs.
- **No severity tagging** — findings without severity / IDs are hard to
  triage into commit phases later.

---

## Cross-references

- `docs/playbooks/bug-fix-campaign.md` — the canonical output shape
  (5/4 audit's 29 findings → 7 phases → 100% closed)
- `docs/archive/2026-05-04-test-coverage-gaps.md` — Phase 7.1 inventory
  (different shape; coverage gap audit, not bug audit)
- `~/.claude/projects/-Users-sandrajirongo-Projects-ClaroBill/<session_id>/subagents/`
  — the saved JSONL transcript of every audit agent run. To find which
  agents fired in a past session: `ls .../subagents/` and read the
  `*.meta.json` files for `{"agentType": ..., "description": ...}`.
- `CLAUDE.md` Rule 13 — the regression gate. Audit agents typically
  surface gate failures as STOP-THE-LINE.
