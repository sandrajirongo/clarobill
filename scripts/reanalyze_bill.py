"""One-off: re-run the analyze pipeline on an existing bill.

Use case: an engine fix lands and we want to refresh findings on a bill
that was already analyzed under the old code. Clears the prior
analysis_results row, deletes any cached report/dispute output in
storage, and POSTs to the engine /analyze endpoint to start fresh.

Defaults to the most recent analyzed bill for jirongo.sandie@gmail.com
so the YC demo bill can be re-analyzed in one command after a deploy.

Usage:
  python3 scripts/reanalyze_bill.py
  python3 scripts/reanalyze_bill.py <bill_id>

Requires:
  - apps/engine/.env with SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
  - gcloud auth (for Cloud Run ID token + ENGINE_API_KEY secret access)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from supabase import create_client


_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> dict[str, str]:
    raw = path.read_text()
    joined = re.sub(r"\\\s*\n\s*", " ", raw)
    cleaned = "\n".join(
        line for line in joined.splitlines() if not line.strip().startswith("#")
    )
    out: dict[str, str] = {}
    for m in re.finditer(
        r'(?:^|\s)([A-Z][A-Z0-9_]*)\s*=\s*(?:"([^"]*)"|(\S+))',
        cleaned,
    ):
        out[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    return out


def _gcloud(*args: str) -> str:
    return subprocess.run(
        ["gcloud", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


GCP_PROJECT = "clarobill-prd"
GCP_REGION = "us-central1"
GCP_ENGINE_SERVICE = "clarobill-engine"
USER_EMAIL = "jirongo.sandie@gmail.com"


def main() -> int:
    env = _load_env(_REPO_ROOT / "apps" / "engine" / ".env")
    sb = create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])

    user = next(
        (u for u in sb.auth.admin.list_users() if (u.email or "").lower() == USER_EMAIL.lower()),
        None,
    )
    if not user:
        sys.exit(f"No user for {USER_EMAIL}")

    if len(sys.argv) >= 2:
        bill_id = sys.argv[1]
    else:
        bills = (
            sb.table("bills")
            .select("id,file_name,created_at")
            .eq("user_id", user.id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        bill_id = None
        for b in bills.data:
            a = (
                sb.table("analysis_results")
                .select("id")
                .eq("bill_id", b["id"])
                .limit(1)
                .execute()
            )
            if a.data:
                bill_id = b["id"]
                print(f"Using most recent analyzed bill: {bill_id} ({b['file_name']})")
                break
        if not bill_id:
            sys.exit("No analyzed bills found")

    # Wipe prior analysis_results row + cached outputs.
    print("Clearing prior analysis_results row …")
    sb.table("analysis_results").delete().eq("bill_id", bill_id).execute()

    folder = f"{user.id}/{bill_id}"
    targets = [f"{folder}/report.pdf", f"{folder}/dispute-letter.docx"]
    print(f"Removing cached files: {targets}")
    sb.storage.from_("reports").remove(targets)

    # Re-set bill status so the engine can re-run.
    sb.table("bills").update({"status": "analyzing"}).eq("id", bill_id).execute()

    engine_url = _gcloud(
        "run", "services", "describe", GCP_ENGINE_SERVICE,
        "--region", GCP_REGION, "--project", GCP_PROJECT,
        "--format", "value(status.url)",
    )
    id_token = _gcloud("auth", "print-identity-token")
    api_key = _gcloud(
        "secrets", "versions", "access", "latest",
        "--secret=ENGINE_API_KEY", f"--project={GCP_PROJECT}",
    )

    bill_row = (
        sb.table("bills")
        .select("id,file_path,user_id,payer_name,plan_name,plan_type,profile_member_id")
        .eq("id", bill_id)
        .single()
        .execute()
        .data
    )
    # state / county / zip_code come from the patient's profile member,
    # not from the bill (the bill's hospital_state is the provider's state).
    state = county = zip_code = None
    if bill_row.get("profile_member_id"):
        member = (
            sb.table("profile_members")
            .select("state,county,zip_code")
            .eq("id", bill_row["profile_member_id"])
            .single()
            .execute()
            .data
        )
        if member:
            state = member.get("state")
            county = member.get("county")
            zip_code = member.get("zip_code")
    body = {
        "bill_id": bill_id,
        "file_path": bill_row["file_path"],
        "user_id": bill_row["user_id"],
        "payer_name": bill_row.get("payer_name"),
        "plan_name": bill_row.get("plan_name"),
        "plan_type": bill_row.get("plan_type"),
        "state": state,
        "county": county,
        "zip_code": zip_code,
    }
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{engine_url}/api/v1/bills/{bill_id}/analyze",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {id_token}",
            "X-Engine-Api-Key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"POST /analyze → {resp.status}: {resp.read().decode()}")
    except urllib.error.HTTPError as exc:
        sys.exit(f"engine /analyze failed: {exc.code} {exc.read().decode()}")

    # Poll for the new analysis_results row.
    print("Waiting for re-analysis (up to 5 min) …")
    for tick in range(60):
        time.sleep(5)
        a = (
            sb.table("analysis_results")
            .select("id,errors,total_potential_savings")
            .eq("bill_id", bill_id)
            .execute()
        )
        if a.data:
            row = a.data[0]
            errors = row["errors"] or []
            print(f"Analyze done after {(tick + 1) * 5}s — {len(errors)} findings, "
                  f"${row['total_potential_savings']:.2f} total potential savings")
            for e in errors:
                print(f"  [{e.get('severity','').upper()}] {e['code']}  ${e['estimated_overcharge']:>9}")
                print(f"        {e['description'][:180]}")
            break
    else:
        sys.exit("timed out waiting for re-analysis")

    # Now trigger /report so the bill view stops showing the "Generating…"
    # spinner. Without this, the analyze step would leave a row with findings
    # and null URLs forever — exactly the stuck state Sandra hit.
    print("\nTriggering /report to generate PDF + dispute letter …")
    report_payload = json.dumps({"user_id": user.id, "user_email": USER_EMAIL}).encode()
    report_req = urllib.request.Request(
        f"{engine_url}/api/v1/bills/{bill_id}/report",
        data=report_payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {id_token}",
            "X-Engine-Api-Key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(report_req) as resp:
            print(f"POST /report → {resp.status}: {resp.read().decode()}")
    except urllib.error.HTTPError as exc:
        sys.exit(f"engine /report failed: {exc.code} {exc.read().decode()}")

    print("Waiting for report + dispute letter (up to 5 min) …")
    for tick in range(60):
        time.sleep(5)
        a = (
            sb.table("analysis_results")
            .select("report_url,dispute_letter_url")
            .eq("bill_id", bill_id)
            .single()
            .execute()
            .data or {}
        )
        if a.get("report_url") and a.get("dispute_letter_url"):
            print(f"Report ready after {(tick + 1) * 5}s")
            print(f"  report_url={a['report_url']}")
            print(f"  dispute_letter_url={a['dispute_letter_url']}")
            return 0
    sys.exit("timed out waiting for report generation")


if __name__ == "__main__":
    raise SystemExit(main())
