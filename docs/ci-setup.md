# CI/CD setup — GitHub Actions + Supabase

One-time setup for the workflows added in `.github/workflows/`.

## What runs and when

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | every push to `main`; every PR | Full regression gate — engine ruff/mypy/pytest, web typecheck/lint/test/build, plus the engine→web boundary contract |
| `migration-check.yml` | PRs touching `supabase/migrations/**` | Boots a local Supabase stack via Docker, applies every migration in order, tests reversibility against `supabase/migrations_down/*.down.sql`, runs engine pytest against the live DB |

## Migration folder layout

```
supabase/
├── migrations/         ← up migrations only (Supabase CLI applies these in lex order)
├── migrations_down/    ← matching <version>_<name>.down.sql siblings (CLI ignores)
└── config.toml
```

Down migrations are deliberately stored in a sibling folder so the Supabase CLI doesn't pick them up as additional migrations to apply. The reversibility test in `migration-check.yml` looks for `supabase/migrations_down/<filename>.down.sql` for each touched up-migration. Add a down sibling whenever the migration is reversible — the workflow emits a `::warning::` if one is missing.

## Local setup (one-time)

```bash
# Already installed at /opt/homebrew/bin/supabase — verify
supabase --version

# Browser-based login (saves token to ~/.supabase/access-token)
supabase login

# Link this repo to your cloud project. The ref comes from the Supabase
# project URL: https://kqecgxxxvvkffjwxxuwp.supabase.co
cd /Users/sandrajirongo/Projects/ClaroBill
supabase link --project-ref kqecgxxxvvkffjwxxuwp
```

After `link`, the CLI knows which cloud project this repo targets, and you can run:
- `supabase db push` — apply pending migrations to the linked cloud DB
- `supabase db pull` — generate a migration file from the cloud DB's current state
- `supabase db start` / `db stop` — boot a local Docker copy for testing

## GitHub Actions secrets (one-time)

Add these as **Repository secrets** at **GitHub repo → Settings → Secrets and variables → Actions → New repository secret**.

(Don't use Environment secrets unless you later want approval gates or per-env tokens; don't use Organization secrets — this is a single-repo setup.)

| Secret name | How to obtain | Used by |
|---|---|---|
| `SUPABASE_ACCESS_TOKEN` | macOS: `security find-generic-password -s "Supabase CLI" -w` (the CLI stores the token in Keychain, not on disk). OR generate a fresh CI-scoped token at <https://supabase.com/dashboard/account/tokens>. | migration-check.yml (CLI auth in future preview-DB iterations) |
| `SUPABASE_PROJECT_REF` | Literal value: `kqecgxxxvvkffjwxxuwp` (the project URL prefix). | future preview-DB workflows |

The secrets are referenced in the workflows via `${{ secrets.SUPABASE_ACCESS_TOKEN }}`. They are NOT logged.

> **Recommendation:** generate a fresh dashboard token rather than reusing the CLI's local one. The dashboard token is scoped to CI, can be named (e.g. `github-actions-clarobill`), and revoked independently of your local CLI session — so a credential leak in one place doesn't compromise the other.

> **Note:** The current workflows DON'T require either secret yet — `supabase db start` boots locally via Docker and doesn't touch the cloud project. The secrets are pre-staged for the next iteration which adds preview-DB-per-PR (Supabase Branching).

## Branch protection on `main`

Enforces both workflows pass before merge.

1. **GitHub repo → Settings → Branches → Add branch ruleset**
2. Branch name pattern: `main`
3. Tick **Require status checks to pass before merging**
4. Search & add:
   - `Engine (Python)`
   - `Web (Next.js)`
   - `Engine→web boundary contract`
   - `Apply, verify, reverse migrations` (only required when the PR touches `supabase/migrations/**` — GitHub respects the workflow's `paths:` filter)
5. Tick **Require branches to be up to date before merging**
6. Save

## Supabase Database Branching (optional, recommended)

Sandra's intent: enable the Supabase ↔ GitHub integration on the Supabase dashboard's Integrations page. This automatically creates an ephemeral preview database per PR and applies the PR's migrations to it. It complements the local-Docker check in `migration-check.yml` by also running the migrations against a real Supabase environment (matching cloud-only quirks like extensions and IAM).

Steps:
1. **Supabase dashboard → Project → Integrations → GitHub** → Connect repo
2. Pick the `clarobill` repo, branch `main`
3. Tick **Database Branching** → Enable
4. Set the migration directory to `supabase/migrations/`
5. Save

Costs (per Rule 16, verified 2026-05-04 from supabase.com/pricing): preview branches are billed per branch-day. The Pro plan includes 1 free preview branch slot; subsequent slots are $0.32 GB/day for storage and $0.01344/hour for compute (~$0.32/day for the smallest instance). Beta-volume PRs spend <$1/month here. Source: <https://supabase.com/pricing> (verify before relying on these numbers — pricing changes).

## Verifying CI works

After committing the workflow files:

1. Push a PR with a no-op change (e.g. fix a comment typo).
2. Watch the Actions tab — both `Engine (Python)` and `Web (Next.js)` should run, each ~3-5 min.
3. The `Engine→web boundary contract` job should run after both succeed.
4. Push a PR that adds a SQL file under `supabase/migrations/` — the migration-check workflow should also fire.
5. If anything reds, check the job logs for the actual error before merging.

## Cost expectations (per Rule 16)

GitHub Actions on a public repo is free; on a private repo, `ubuntu-latest` minutes count against the included tier (3,000/month for Pro, 2,000/month for Free). One full CI run is ~10 minutes total (engine + web + boundary). At 5 PRs/day with 3 reruns each = 750 min/month. Comfortable headroom on either tier.

The migration-check workflow only fires on PRs that touch migration files — typically 1-2 PRs/month — so its cost is negligible.

Sources verified 2026-05-04: <https://github.com/pricing>, <https://supabase.com/pricing>.

