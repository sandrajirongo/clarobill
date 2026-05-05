# Deployment runbook

How code reaches production for each component, plus rollback procedures.

## Engine (FastAPI on Cloud Run)

### Auto-deploy (default path)

Every push to `main` that touches `apps/engine/**` triggers Cloud Build:

```
git push origin main          → GitHub
                              → Cloud Build trigger (engine-deploy-on-push)
                              → docker build, push to Artifact Registry
                              → gcloud run deploy → clarobill-engine
                              ≈ 3-5 min wall clock
```

Build config: `apps/engine/cloudbuild.yaml`. The trigger watches the
`apps/engine/**` path filter in the Cloud Build console.

### Verify after deploy

```bash
# 1. Health check
curl -s https://<engine-url>/health
# expected: {"status": "ok"}

# 2. Confirm the new revision is serving
gcloud run services describe clarobill-engine \
  --region us-central1 --format=json \
  | jq '.status.traffic[0].revisionName'
# matches the latest revision created by the build

# 3. Smoke test from the Sentry side
# Browse Sentry dashboard for the last 5 min; confirm no spike of 5xx

# 4. PostHog event check
# Confirm "bill analysis started" events still flowing (any test user can trigger)
```

### Manual deploy (skipping the trigger)

```bash
gcloud builds submit \
  --config apps/engine/cloudbuild.yaml \
  --project clarobill-prd
```

Same as auto-deploy but doesn't require a new commit.

### Rollback

```bash
# 1. Find the prior commit SHA
git log --oneline -20

# 2. Re-deploy the prior image (Artifact Registry retains every SHA)
gcloud run services update clarobill-engine \
  --image us-central1-docker.pkg.dev/clarobill-prd/cloud-run-source-deploy/clarobill-engine:<PRIOR_SHA> \
  --region us-central1 \
  --project clarobill-prd

# 3. Verify (steps 1-4 above)
```

The `:latest` tag will lag the production revision after a rollback —
that's fine; auto-deploy on the next push fixes it.

### Skip auto-deploy on a commit

Add `[skip ci]` to the commit message subject. Cloud Build trigger respects this.

### Emergency: kill all engine traffic

```bash
gcloud run services update clarobill-engine \
  --no-traffic --region us-central1
```

Returns 503 to every request. Use sparingly — the web layer surfaces this
as a generic error.

## Web (Next.js on Vercel)

### Auto-deploy

Every push to `main` triggers Vercel production deploy. Every PR triggers
a Vercel preview deploy (unique URL per PR commit).

### Verify after deploy

```bash
# Hit the production URL
curl -s https://clarobill.com/api/health 2>&1 | head -5
# Manual: load the dashboard, confirm rendering, click through to a bill
```

### Rollback

In the Vercel dashboard:
1. Project → Deployments
2. Find the prior production deploy
3. Click "Promote to Production"
4. Verify

Vercel retains every deploy indefinitely; rollback is one click.

### Preview-per-PR

Every PR gets a Vercel preview URL posted as a comment on the PR. The
preview uses the same env vars as production. **Never test PHI flows
against the preview URL** — PHI ends up in the Vercel deployment's
preview environment which has different retention policies than prod.

## MRF pipeline (Cloud Run Jobs)

Deploy script: `pipeline/deploy.sh`.

```bash
bash pipeline/deploy.sh
```

What it does:
1. Builds the Docker image from `pipeline/Dockerfile` (build context = repo root)
2. Pushes to Artifact Registry repo `clarobill-pipeline`
3. Updates / creates two Cloud Run Jobs (scraper + parser)
4. Updates / creates two Cloud Schedulers (Feb 15 + Aug 15)

This is run by hand — there's no auto-deploy on `pipeline/**` changes.
Sandra runs it after pipeline code changes.

### Manual trigger of a pipeline run

```bash
# Scraper
gcloud run jobs execute mrf-scraper --region us-central1

# Parser
gcloud run jobs execute mrf-parser --region us-central1

# Discovery (Stages 1-4 — manual run only, currently)
cd scripts/mrf_discovery
python stage1_cms_hospital_list.py --run-id $(date +%Y%m%d)
python stage2_pos_file.py --run-id $(date +%Y%m%d)
# ...etc
```

Detail in [pipeline-runbook.md](pipeline-runbook.md).

## Database migrations

PRs touching `supabase/migrations/**` trigger
`.github/workflows/migration-check.yml`. The workflow:

1. Boots a fresh Postgres in Docker via `supabase db start`
2. Applies every migration in order
3. Runs the down migration for any changed up migration
4. Re-applies the up migration
5. Asserts postcondition DO blocks (where present)

If the workflow goes red, the PR can't merge. Don't merge a migration PR
if the migration-check is failing — the schema state is what 100% of
production reads depend on.

### Migration deploy (production)

After merging:

```bash
supabase db push          # applies any new migrations to the linked project
```

Sandra runs this after merge. There's no auto-apply on push (intentional —
migrations are higher-blast-radius than code).

### Migration rollback

```bash
# Run the .down.sql for the most recent migration
psql "$SUPABASE_DB_URL" -f supabase/migrations_down/<filename>.down.sql
# Then mark schema_migrations as if the up was never applied
```

Some migrations are non-reversible (data backfills, dropped columns) —
these have a manually-written down that recreates the structure but
cannot recover lost data. **Always review the down before relying on it.**

## Reviewer checklist for migration PRs

- [ ] One migration per PR (don't combine)
- [ ] `*.down.sql` exists in `supabase/migrations_down/` and is real (not a TODO stub)
- [ ] Postcondition `DO $$ ... END $$` block at the end if the migration
      moves data
- [ ] No `CREATE EXTENSION` for dashboard-enabled extensions (pg_cron,
      pg_net, vector) — wrap any usage in `if exists (select 1 from pg_extension where extname = 'X')`
- [ ] CHECK constraints use closed sets, not stringly-typed
- [ ] FKs cascade correctly (delete a bill → delete line_items + analysis_results)
- [ ] RLS policy added if the table is user-scoped
- [ ] Index added if the new column will be queried

## Secrets

Engine secrets live in Cloud Run env vars (set via `gcloud run services
update --update-env-vars` or the Cloud Run console).

Web secrets live in Vercel project env vars (set via Vercel dashboard or
CLI).

GitHub Actions secrets (`SUPABASE_ACCESS_TOKEN`, `SUPABASE_PROJECT_REF`)
live in GitHub repo Settings → Secrets and variables → Actions.

### Rotation

| Secret | Where | Rotate when |
|---|---|---|
| `ENGINE_API_KEY` | Engine + Web | Quarterly or on suspected compromise |
| `SUPABASE_SERVICE_ROLE_KEY` | Engine | Suspected compromise only — disruptive |
| `STRIPE_SECRET_KEY` | Web | Stripe-side rotation |
| `STRIPE_WEBHOOK_SECRET` | Web | Stripe Dashboard rotation |
| `ANTHROPIC_API_KEY`, `POSTHOG_API_KEY`, etc. | Engine + Web | On suspected compromise |
| Service account JSONs (Cloud Run runtime SA) | Cloud Run | Use IAM identity binding instead of keys (already configured) |

## Breaking-change protocol

A "breaking change" = engine API contract changes incompatible with the
deployed web layer (or vice versa). Examples: removing a field, changing
an enum value, renaming an endpoint.

1. **Deploy the additive change first.** Add the new field alongside the
   old. Both web and engine accept either.
2. **Migrate consumers.** Move the web layer to use the new field.
   Deploy.
3. **Remove the old field.** Wait at least one full deploy cycle (most
   realistically: a day) before removing — gives Cloud Run cold-start
   instances time to roll.

Avoid breaking changes that fan out across many call sites — most can
be done as additive + deprecation.

## Cross-references

- [pipeline-runbook.md](pipeline-runbook.md) — pipeline-specific operations
- [ci-cd.md](ci-cd.md) — CI workflow detail
- [../playbooks/cost-discipline.md](../playbooks/cost-discipline.md) — cost gate before any infra change
- [../playbooks/security-phi.md](../playbooks/security-phi.md) — PHI handling on rollback / log purge
