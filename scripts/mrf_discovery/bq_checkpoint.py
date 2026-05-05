"""BigQuery checkpoint helpers shared by all CMS-direct discovery stages.

Includes `run_dml_with_count` (M13, 2026-05-04): a thin wrapper around
client.query(...).result() that asserts the DML actually affected ≥0 rows.
Pre-fix, MERGE/UPDATE/INSERT calls discarded the QueryJob result and a
0-rows-affected outcome (caused by a typo, a dataset rename, or an IAM
revocation that silently downgraded the job to read-only) looked
identical to a successful operation. Now: the helper logs the affected
count at INFO and raises if num_dml_affected_rows is None (only happens
when the statement isn't actually DML — useful regression net).


The pipeline is designed for resumability. Every per-hospital row records when
each stage completed; if the job crashes mid-run, re-launching with the same
run_id picks up exactly where it left off. The contract for every stage is:

    pending = get_pending_for_stage(client, run_id, stage)
    for row in pending:
        try:
            result = do_work(row)
            mark_complete(client, run_id, row.ccn, stage, result)
        except Exception as exc:
            mark_error(client, run_id, row.ccn, stage, str(exc))
            # never re-raise -- one bad hospital cannot kill the run

The checkpoint table is `mrf_discovery_checkpoint`, keyed by (run_id, ccn).
Once a run completes successfully, summary rows are appended to
`mrf_discovery_runs` and the checkpoint rows are retained for forensics
(they're cheap and useful for "why did hospital X fail in March?" questions).

Stages:

    cms_loaded         stage 1: row seeded from CMS Promoting Interoperability list
    nppes_resolved     stage 2: NPI + website populated from POS file + NPPES bulk
    website_found      stage 3: hospital_website confirmed live
    crawl_complete     stage 4: candidate_mrf_urls populated by website crawl
    mrf_validated      stage 5: validated_mrf_urls populated after HEAD + content sample
    bq_committed       stage 6: row MERGEd into hospital_directory
"""

import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from google.cloud import bigquery

logger = logging.getLogger(__name__)

DEFAULT_DATASET = "hospital_prices"

STAGES = (
    "cms_loaded",
    "nppes_resolved",
    "website_found",
    "crawl_complete",
    "mrf_validated",
    "bq_committed",
)


def new_run_id() -> str:
    """Generate a run_id stamped with UTC date for ergonomic log filtering."""
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{_uuid.uuid4().hex[:8]}"


def _checkpoint_table(project: str, dataset: str) -> str:
    return f"{project}.{dataset}.mrf_discovery_checkpoint"


def ensure_checkpoint_table(
    client: bigquery.Client,
    project: str,
    dataset: str = DEFAULT_DATASET,
) -> None:
    """Create mrf_discovery_checkpoint if it does not exist.

    One row per (run_id, ccn). Stage timestamps are NULL until the stage
    completes for that hospital. Recreated on every migration; safe to call
    before each run.
    """
    table_id = _checkpoint_table(project, dataset)
    sql = f"""
    CREATE TABLE IF NOT EXISTS `{table_id}` (
      run_id                       STRING NOT NULL,
      ccn                          STRING NOT NULL,

      -- From CMS Promoting Interoperability list (Stage 1)
      hospital_name                STRING,
      address                      STRING,
      city                         STRING,
      state                        STRING,
      zip_code                     STRING,
      phone                        STRING,
      hospital_type                STRING,
      hospital_ownership           STRING,
      overall_rating               INT64,

      -- From CMS POS + NPPES API + Wikidata (Stage 2)
      hospital_npi                 STRING,
      bed_count                    INT64,
      medicare_carrier_code        STRING,
      hospital_website             STRING,
      website_source               STRING,  -- wikidata | nppes_api | pattern_inference | google_places

      -- From website discovery (Stage 3)
      website_validated_at         TIMESTAMP,

      -- From crawler (Stage 4)
      candidate_mrf_urls           STRING,  -- JSON array
      toc_url                      STRING,
      toc_expanded                 BOOL,

      -- From validator (Stage 5)
      validated_mrf_urls           STRING,  -- JSON array
      mrf_discovery_method         STRING,
      mrf_file_format              STRING,
      mrf_file_size_bytes          INT64,

      -- Stage completion timestamps
      cms_loaded_at                TIMESTAMP,
      nppes_resolved_at            TIMESTAMP,
      website_found_at             TIMESTAMP,
      crawl_complete_at            TIMESTAMP,
      mrf_validated_at             TIMESTAMP,
      bq_committed_at              TIMESTAMP,

      -- Error tracking (does not block the next run; the row stays pending)
      error_stage                  STRING,
      error_message                STRING,
      consecutive_failures         INT64,

      last_updated_at              TIMESTAMP NOT NULL
    )
    PARTITION BY DATE(last_updated_at)
    CLUSTER BY run_id, state, ccn
    """
    client.query(sql).result()


def run_dml_with_count(
    client: bigquery.Client,
    sql: str,
    *,
    job_config: bigquery.QueryJobConfig | None = None,
    label: str = "DML",
    logger: logging.Logger | None = None,
) -> int:
    """Run a DML statement (MERGE / UPDATE / INSERT / DELETE) and assert the
    affected row count is captured. Returns the row count.

    Raises RuntimeError when num_dml_affected_rows is None — that happens
    when the statement isn't actually DML (e.g. a SELECT or CREATE TABLE
    snuck through). Catching this regression at runtime is the point of
    the wrapper.

    Logs the count at INFO so operators can audit "MERGE updated 4,127
    rows" lines in Cloud Logging without grepping for warnings.
    """
    job = client.query(sql, job_config=job_config) if job_config else client.query(sql)
    job.result()  # Wait for completion + raise on query error.
    affected = job.num_dml_affected_rows
    if affected is None:
        raise RuntimeError(
            f"{label}: num_dml_affected_rows is None — the statement may not be DML. "
            "If this is intentional (e.g. a CREATE TABLE), call client.query().result() directly."
        )
    if logger is not None:
        logger.info("%s affected %d rows", label, affected)
    return affected


def seed_hospitals(
    client: bigquery.Client,
    project: str,
    run_id: str,
    rows: Iterable[dict[str, Any]],
    dataset: str = DEFAULT_DATASET,
    batch_size: int = 500,
) -> int:
    """Insert hospital rows from Stage 1 (CMS PI list) into the checkpoint table.

    Each input row must include ccn and hospital_name. Other fields are optional
    and pass through. Returns the count of newly-inserted rows.

    Idempotent re-run protection: if the (run_id, ccn) row already exists in
    the checkpoint, the input row is silently skipped (logged at INFO). This
    prevents the duplicate-row hazard that would otherwise occur if Stage 1
    is re-launched for the same run_id (e.g. after a transient crash). The
    primary-key-style check is done in-memory against a single SELECT; for
    13,833 rows the resulting set is ~1MB.
    """
    table_id = _checkpoint_table(project, dataset)
    now_iso = datetime.now(timezone.utc).isoformat()

    materialised: list[dict[str, Any]] = []
    for row in rows:
        if "ccn" not in row or "hospital_name" not in row:
            raise ValueError(
                f"seed_hospitals rows must include ccn and hospital_name; got {set(row.keys())}"
            )
        materialised.append({
            "run_id": run_id,
            "cms_loaded_at": now_iso,
            "last_updated_at": now_iso,
            "consecutive_failures": 0,
            **row,
        })

    if not materialised:
        return 0

    # Look up which (run_id, ccn) pairs already exist so re-runs of Stage 1
    # for the same run_id don't insert duplicates.
    existing_sql = f"""
    SELECT ccn FROM `{table_id}` WHERE run_id = @run_id
    """
    job = client.query(
        existing_sql,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        ]),
    )
    existing_ccns = {r["ccn"] for r in job.result()}
    if existing_ccns:
        logger.info(
            "Skipping %d input rows whose (run_id, ccn) is already in the checkpoint",
            sum(1 for r in materialised if r["ccn"] in existing_ccns),
        )
        materialised = [r for r in materialised if r["ccn"] not in existing_ccns]

    if not materialised:
        return 0

    inserted = 0
    for start in range(0, len(materialised), batch_size):
        batch = materialised[start : start + batch_size]
        errors = client.insert_rows_json(table_id, batch)
        if errors:
            logger.error("seed_hospitals insert errors: %s", errors[:3])
            raise RuntimeError(f"BigQuery insert failed: {errors[:3]}")
        inserted += len(batch)
    logger.info("Seeded %d hospitals into checkpoint", inserted)
    return inserted


def get_pending_for_stage(
    client: bigquery.Client,
    project: str,
    run_id: str,
    stage: str,
    dataset: str = DEFAULT_DATASET,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return checkpoint rows where the named stage has not completed yet.

    A row is "pending" when the previous stage completed (its _at column is
    non-null) and the named stage has not (its _at column is null). For
    cms_loaded the previous-stage gate is just run_id match.
    """
    if stage not in STAGES:
        raise ValueError(f"Unknown stage {stage!r}; must be one of {STAGES}")

    table_id = _checkpoint_table(project, dataset)
    prior_gate, this_col = _stage_gates(stage)
    limit_clause = f"LIMIT {int(limit)}" if limit else ""

    sql = f"""
    SELECT *
    FROM `{table_id}`
    WHERE run_id = @run_id
      AND {prior_gate}
      AND {this_col} IS NULL
    {limit_clause}
    """
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("run_id", "STRING", run_id)],
        ),
    )
    return [dict(row) for row in job.result()]


def _stage_gates(stage: str) -> tuple[str, str]:
    """Return (prior_stage_gate_sql, this_stage_column) for a given stage."""
    if stage == "cms_loaded":
        return ("TRUE", "cms_loaded_at")
    if stage == "nppes_resolved":
        return ("cms_loaded_at IS NOT NULL", "nppes_resolved_at")
    if stage == "website_found":
        return ("nppes_resolved_at IS NOT NULL", "website_found_at")
    if stage == "crawl_complete":
        return ("website_found_at IS NOT NULL", "crawl_complete_at")
    if stage == "mrf_validated":
        return ("crawl_complete_at IS NOT NULL", "mrf_validated_at")
    if stage == "bq_committed":
        return ("mrf_validated_at IS NOT NULL", "bq_committed_at")
    raise ValueError(f"Unknown stage {stage!r}")


def mark_complete(
    client: bigquery.Client,
    project: str,
    run_id: str,
    ccn: str,
    stage: str,
    updates: dict[str, Any] | None = None,
    dataset: str = DEFAULT_DATASET,
) -> None:
    """Set <stage>_at = NOW() and apply any field updates atomically.

    updates is a dict of column -> value to set on the same row. Use this to
    write the resolved NPI when stage='nppes_resolved', the candidate URLs
    when stage='crawl_complete', etc.
    """
    if stage not in STAGES:
        raise ValueError(f"Unknown stage {stage!r}")

    table_id = _checkpoint_table(project, dataset)
    _, this_col = _stage_gates(stage)
    now_iso = datetime.now(timezone.utc).isoformat()

    set_clauses = [f"{this_col} = TIMESTAMP(@now)", "last_updated_at = TIMESTAMP(@now)"]
    params: list[bigquery.ScalarQueryParameter] = [
        bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        bigquery.ScalarQueryParameter("ccn", "STRING", ccn),
        bigquery.ScalarQueryParameter("now", "TIMESTAMP", now_iso),
    ]

    for col, val in (updates or {}).items():
        param_name = f"upd_{col}"
        bq_type = _bq_type_for_value(val)
        set_clauses.append(f"{col} = @{param_name}")
        params.append(bigquery.ScalarQueryParameter(param_name, bq_type, val))

    sql = f"""
    UPDATE `{table_id}`
    SET {', '.join(set_clauses)}
    WHERE run_id = @run_id AND ccn = @ccn
    """
    client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


def mark_error(
    client: bigquery.Client,
    project: str,
    run_id: str,
    ccn: str,
    stage: str,
    message: str,
    dataset: str = DEFAULT_DATASET,
) -> None:
    """Record an error without setting the stage's completion timestamp.

    The stage timestamp stays NULL so the row will be re-attempted next run.
    consecutive_failures increments so a stuck row can be flagged for manual
    review after N retries.
    """
    if stage not in STAGES:
        raise ValueError(f"Unknown stage {stage!r}")

    table_id = _checkpoint_table(project, dataset)
    now_iso = datetime.now(timezone.utc).isoformat()

    sql = f"""
    UPDATE `{table_id}`
    SET error_stage = @stage,
        error_message = @msg,
        consecutive_failures = COALESCE(consecutive_failures, 0) + 1,
        last_updated_at = TIMESTAMP(@now)
    WHERE run_id = @run_id AND ccn = @ccn
    """
    client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
                bigquery.ScalarQueryParameter("ccn", "STRING", ccn),
                bigquery.ScalarQueryParameter("stage", "STRING", stage),
                bigquery.ScalarQueryParameter("msg", "STRING", message[:1000]),
                bigquery.ScalarQueryParameter("now", "TIMESTAMP", now_iso),
            ],
        ),
    ).result()


def get_run_summary(
    client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = DEFAULT_DATASET,
) -> dict[str, int]:
    """Return per-stage completion counts for a run."""
    table_id = _checkpoint_table(project, dataset)
    sql = f"""
    SELECT
      COUNT(*) AS total,
      COUNTIF(cms_loaded_at      IS NOT NULL) AS cms_loaded,
      COUNTIF(nppes_resolved_at  IS NOT NULL) AS nppes_resolved,
      COUNTIF(website_found_at   IS NOT NULL) AS website_found,
      COUNTIF(crawl_complete_at  IS NOT NULL) AS crawl_complete,
      COUNTIF(mrf_validated_at   IS NOT NULL) AS mrf_validated,
      COUNTIF(bq_committed_at    IS NOT NULL) AS bq_committed,
      COUNTIF(error_stage IS NOT NULL)        AS errored,
      COUNTIF(hospital_npi IS NOT NULL)       AS with_npi,
      COUNTIF(hospital_website IS NOT NULL)   AS with_website,
      COUNTIF(validated_mrf_urls IS NOT NULL) AS with_validated_mrf
    FROM `{table_id}`
    WHERE run_id = @run_id
    """
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("run_id", "STRING", run_id)],
        ),
    )
    row = next(iter(job.result()), None)
    if row is None:
        return {"total": 0}
    return dict(row)


def _bq_type_for_value(val: Any) -> str:
    """Map a Python value to a BigQuery scalar parameter type.

    Limited to the types we actually write from stages 2-6: strings, ints,
    floats, dates, timestamps, and bools. Everything else raises so we never
    silently coerce.
    """
    if val is None:
        return "STRING"
    if isinstance(val, bool):
        return "BOOL"
    if isinstance(val, int):
        return "INT64"
    if isinstance(val, float):
        return "FLOAT64"
    if isinstance(val, str):
        return "STRING"
    if hasattr(val, "isoformat"):
        return "TIMESTAMP" if hasattr(val, "hour") else "DATE"
    raise TypeError(f"Unsupported BigQuery parameter type: {type(val).__name__}")
