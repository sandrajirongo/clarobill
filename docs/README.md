# ClaroBill docs

Start here. Every doc lives under one of the categories below.

## Quick reference — "where do I look for X?"

| Question | Folder | File |
|---|---|---|
| How does the rules engine work? | `architecture/` | [rules-engine.md](architecture/rules-engine.md) |
| What's in the database? | `architecture/` | [database-schema.md](architecture/database-schema.md) |
| Which GCP service does what? | `architecture/` | [gcp-resources.md](architecture/gcp-resources.md) |
| How do I run tests? | `playbooks/` | [testing-guide.md](playbooks/testing-guide.md) |
| How do I set up locally? | `playbooks/` | [local-dev-setup.md](playbooks/local-dev-setup.md) |
| Is this PHI / how do we handle it? | `playbooks/` | [security-phi.md](playbooks/security-phi.md) |
| What does X cost on GCP? | `playbooks/` | [cost-discipline.md](playbooks/cost-discipline.md) |
| How do I deploy? | `operations/` | [deployment-runbook.md](operations/deployment-runbook.md) |
| What do I do when the MRF pipeline fails? | `operations/` | [pipeline-runbook.md](operations/pipeline-runbook.md) |
| How does CI work? | `operations/` | [ci-cd.md](operations/ci-cd.md) |
| What does the user see? | `product/` | [user-workflow.md](product/user-workflow.md) |
| What's the price model? | `product/` | [pricing.md](product/pricing.md) |
| What's the SEO/GEO plan and task list? | `product/` | [seo-geo-plan.md](product/seo-geo-plan.md) |
| Why was X built that way? | `decisions/` | ADRs by date |
| What broke and why? | `postmortems/` | postmortems by date |
| What's next on the backlog? | `future-improvements/` | one file per backlog item |
| How do I run a full-codebase audit? | `playbooks/` | [agent-review.md](playbooks/agent-review.md) |
| Where's the bug-fix campaign tracker? | `playbooks/` | [bug-fix-campaign.md](playbooks/bug-fix-campaign.md) |

## Folders

| Folder | Purpose | Update cadence |
|---|---|---|
| [architecture/](architecture/) | System design — how the major pieces fit together | Living docs; update in place when a major piece changes |
| [operations/](operations/) | Runbooks — what to do when running the system | Living docs; update when a runbook step changes |
| [product/](product/) | Product surface — what users see and the rules around it | Living docs; update on product changes |
| [playbooks/](playbooks/) | Procedures and recipes — what to do when X | Living docs; update as patterns evolve |
| [reference/](reference/) | Lookup tables and data provenance | Updated when underlying reference data changes |
| [decisions/](decisions/) | Architecture Decision Records (ADRs) | **Immutable.** Add a `Status: SUPERSEDED-BY` header instead of editing |
| [postmortems/](postmortems/) | Incident records | **Immutable.** One file per incident, dated `YYYY-MM-DD` |
| [future-improvements/](future-improvements/) | Backlog of planned-but-not-done work | Edit freely; move to `archive/` when superseded |
| [applications/](applications/) | VC application material | Updated when applications change |
| [archive/](archive/) | Superseded historical docs | Read-only; kept for context |

## Conventions

- **Filenames:** kebab-case. `rules-engine.md`, not `rules_engine.md` or `RulesEngine.md`.
- **Folders:** kebab-case, plural. `postmortems/`, `future-improvements/`, `decisions/`.
- **Date stamps:** ADRs and postmortems use `YYYY-MM-DD-title.md`. Reference docs (rules-engine, brand-guidelines, etc.) use plain titles — they're living docs.
- **Status headers:** ADRs and archive files start with `**Status:** ACTIVE | SUPERSEDED-BY [link] | ARCHIVED`. Required on `decisions/*` and `archive/*`; optional elsewhere.
- **Cross-references:** Use relative paths from the file's location (`../decisions/2026-04-28-cms-direct-mrf-discovery.md`), not absolute.
- **What goes at repo root:** `CLAUDE.md`, `README.md`. Everything else lives under `docs/`.

## When you're not sure where to put something

| It's about... | Put it here |
|---|---|
| A decision being made now | `decisions/YYYY-MM-DD-title.md` |
| Something that broke and got fixed | `postmortems/YYYY-MM-DD-title.md` |
| A procedure ("how to X") | `playbooks/X.md` |
| A long-term system design | `architecture/X.md` |
| Day-to-day operating instructions | `operations/X.md` |
| User-visible product behavior | `product/X.md` |
| A reference lookup table | `reference/X.md` |
| A backlog item not yet started | `future-improvements/X.md` |

When in doubt, put it under `playbooks/` and move it later — that folder absorbs anything that doesn't fit cleanly elsewhere.

---

_Last reviewed: 2026-05-05_
