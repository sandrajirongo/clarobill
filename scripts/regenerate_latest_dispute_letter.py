"""One-off: regenerate Sandra's latest dispute letter against the post-2af533a engine.

Why this exists
---------------
On 2026-05-02 Sandra's most recent dispute letter shipped truncated mid-sentence
in Dispute 4. Root cause: `_call_gemini` returned `response.text` regardless of
`finish_reason`, so a non-STOP termination (MAX_TOKENS / SAFETY mid-stream / etc.)
silently produced partial output that was emailed and saved. Commit 2af533a fixes
the engine. This script forces re-generation for the already-shipped letter:

  1. Resolves Sandra's user_id from Supabase Auth (jirongo.sandie@gmail.com).
  2. Picks her most recently created bill that has an analysis_results row.
  3. Deletes the cached `report.pdf` + `dispute-letter.docx` from the
     `reports` bucket (storage is the source of truth for the idempotency
     check at apps/engine/app/api/v1/bills.py:1539).
  4. NULLs `report_url` and `dispute_letter_url` on the analysis_results row.
  5. Fetches the prod engine URL via `gcloud run services describe`,
     mints a Cloud Run ID token, POSTs to /api/v1/bills/{id}/report,
     polls until `dispute_letter_url` repopulates.

Requires:
  - apps/engine/.env containing SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
  - gcloud authenticated to clarobill-prd (run `gcloud auth login` if expired)

Usage:
  python3 scripts/regenerate_latest_dispute_letter.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# ── Bootstrap config from apps/engine/.env without importing the engine ─────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENGINE_ENV = _REPO_ROOT / "apps" / "engine" / ".env"


def _load_env(path: Path) -> dict[str, str]:
    """Parse a shell-style .env file into a dict.

    Handles backslash line continuations (`KEY="value" \\`) by globally
    matching `KEY="..."` or `KEY=value` pairs across the joined text rather
    than relying on line-by-line iteration. Quotes around values are stripped.
    """
    raw = path.read_text()
    joined = re.sub(r"\\\s*\n\s*", " ", raw)
    out: dict[str, str] = {}
    # Match KEY="quoted value" or KEY=unquoted_value (terminated by whitespace
    # or line end). Comments (# at start of line) are stripped first.
    cleaned = "\n".join(
        line for line in joined.splitlines() if not line.strip().startswith("#")
    )
    for m in re.finditer(
        r'(?:^|\s)([A-Z][A-Z0-9_]*)\s*=\s*(?:"([^"]*)"|(\S+))',
        cleaned,
    ):
        key = m.group(1)
        value = m.group(2) if m.group(2) is not None else m.group(3)
        out[key] = value
    return out


env = _load_env(_ENGINE_ENV)
SUPABASE_URL = env.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = env.get("SUPABASE_SERVICE_ROLE_KEY", "")
if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in apps/engine/.env")

USER_EMAIL = "jirongo.sandie@gmail.com"

# Cloud Run service that serves /api/v1/bills/{id}/report.
GCP_PROJECT = "clarobill-prd"
GCP_REGION = "us-central1"
GCP_ENGINE_SERVICE = "clarobill-engine"

# ── Imports that depend on the venv being available ─────────────────────────
from supabase import create_client  # noqa: E402
import urllib.request  # noqa: E402
import urllib.error  # noqa: E402


def _gcloud(*args: str) -> str:
    result = subprocess.run(
        ["gcloud", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> int:
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 1. Resolve user_id by email via Supabase Admin API.
    user_resp = sb.auth.admin.list_users()
    sandra = next(
        (u for u in user_resp if (u.email or "").lower() == USER_EMAIL.lower()),
        None,
    )
    if not sandra:
        sys.exit(f"No Supabase user found for {USER_EMAIL}")
    user_id = sandra.id
    print(f"User found: {user_id}")

    # 2. Pick most recent bill with an analysis row.
    bills = (
        sb.table("bills")
        .select("id,file_name,created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    if not bills.data:
        sys.exit("No bills found for this user")

    bill_id: str | None = None
    bill_name: str | None = None
    for b in bills.data:
        a = (
            sb.table("analysis_results")
            .select("id,dispute_letter_url,report_url")
            .eq("bill_id", b["id"])
            .limit(1)
            .execute()
        )
        if a.data:
            bill_id = b["id"]
            bill_name = b["file_name"]
            print(f"Latest analyzed bill: {bill_id}  ({bill_name}, {b['created_at']})")
            print(f"  current report_url={a.data[0].get('report_url')}")
            print(f"  current dispute_letter_url={a.data[0].get('dispute_letter_url')}")
            break
    if not bill_id:
        sys.exit("No analyzed bills found for this user")

    # 3. Delete cached files from storage. The /report idempotency check looks
    #    for `report.pdf` specifically; clearing both cached outputs forces a
    #    full regeneration on the next /report POST.
    folder = f"{user_id}/{bill_id}"
    targets = [f"{folder}/report.pdf", f"{folder}/dispute-letter.docx"]
    print(f"Removing cached files: {targets}")
    sb.storage.from_("reports").remove(targets)

    # 4. NULL the URLs.
    print("Clearing report_url + dispute_letter_url on analysis_results")
    sb.table("analysis_results").update(
        {"report_url": None, "dispute_letter_url": None}
    ).eq("bill_id", bill_id).execute()

    # 5. Trigger regeneration against the new engine image.
    engine_url = _gcloud(
        "run", "services", "describe", GCP_ENGINE_SERVICE,
        "--region", GCP_REGION, "--project", GCP_PROJECT,
        "--format", "value(status.url)",
    )
    print(f"Engine URL: {engine_url}")
    # User-credential ID tokens reject --audiences (only service-account tokens
    # support audience binding). Cloud Run accepts a user-bound ID token as long
    # as the user has roles/run.invoker on the engine service.
    id_token = _gcloud("auth", "print-identity-token")

    # The engine also enforces X-Engine-Api-Key (shared secret with Vercel).
    # Pull from Secret Manager so this script doesn't ship a hard-coded key.
    engine_api_key = _gcloud(
        "secrets", "versions", "access", "latest",
        "--secret=ENGINE_API_KEY", f"--project={GCP_PROJECT}",
    )

    payload = json.dumps({"user_id": user_id, "user_email": USER_EMAIL}).encode()
    req = urllib.request.Request(
        f"{engine_url}/api/v1/bills/{bill_id}/report",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {id_token}",
            "X-Engine-Api-Key": engine_api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"POST /report → {resp.status}: {resp.read().decode()}")
    except urllib.error.HTTPError as exc:
        sys.exit(f"Engine /report POST failed: {exc.code} {exc.read().decode()}")

    # 6. Poll analysis_results until dispute_letter_url repopulates.
    print("Waiting for dispute letter regeneration (up to 5 min) …")
    for tick in range(60):
        time.sleep(5)
        a = (
            sb.table("analysis_results")
            .select("dispute_letter_url,report_url")
            .eq("bill_id", bill_id)
            .single()
            .execute()
        )
        d = a.data or {}
        if d.get("dispute_letter_url") and d.get("report_url"):
            print(f"Done after {(tick + 1) * 5}s")
            print(f"  report_url={d['report_url']}")
            print(f"  dispute_letter_url={d['dispute_letter_url']}")
            return 0
    sys.exit("Timed out waiting for regeneration; check engine logs")


if __name__ == "__main__":
    sys.exit(main())
