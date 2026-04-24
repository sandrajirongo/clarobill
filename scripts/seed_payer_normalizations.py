"""Create and seed the BigQuery payer_name_aliases table.

Maps raw payer name strings as they appear in hospital MRF files to canonical
payer_group keys. This allows negotiated rate lookups to use exact string matching
instead of CONTAINS_SUBSTR, eliminating false misses and false positives from
inconsistent MRF naming conventions.

The table has three columns:
  alias        — the payer name exactly as it appears in an MRF file
  payer_group  — normalized key (snake_case, stable across MRF variations)
  payer_display — human-readable name shown in reports

--- Usage ---

  # Create the table and seed from built-in aliases (safe to re-run):
  python scripts/seed_payer_normalizations.py --project clarobill-prd

  # Add a new alias discovered in an MRF without re-seeding everything:
  python scripts/seed_payer_normalizations.py --project clarobill-prd \\
    --add-alias "BlueCross Preferred PPO" --group blue_cross_blue_shield \\
    --display "Blue Cross Blue Shield"

  # Dry run — print what would be inserted without writing:
  python scripts/seed_payer_normalizations.py --project clarobill-prd --dry-run

  # Discover unmapped payer names in your hospital_charges table:
  python scripts/seed_payer_normalizations.py --project clarobill-prd --audit

--- Authentication ---

  Local:    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
  Cloud Run: uses the attached service account via ADC (no key file needed)
"""

import argparse
import logging
import sys

from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

DATASET = "hospital_prices"
TABLE = "payer_name_aliases"

SCHEMA = [
    bigquery.SchemaField("alias", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("payer_group", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("payer_display", "STRING", mode="REQUIRED"),
]

# Canonical alias list — covers the major national payers and their most common
# MRF naming variations. These were compiled from CMS MRF survey data and manual
# review of hospital price transparency files from the top 100 US hospitals.
#
# To add a new alias: use --add-alias (incremental) or add it here and re-run.
# To discover what's in your database: use --audit.
SEED_ALIASES: list[tuple[str, str, str]] = [
    # (alias_as_in_mrf, payer_group, payer_display)

    # Blue Cross Blue Shield (national + state plans — all map to bcbs_*)
    ("BCBS", "bcbs_national", "Blue Cross Blue Shield"),
    ("Blue Cross Blue Shield", "bcbs_national", "Blue Cross Blue Shield"),
    ("Blue Cross Blue Shield Association", "bcbs_national", "Blue Cross Blue Shield"),
    ("BlueCross BlueShield", "bcbs_national", "Blue Cross Blue Shield"),
    ("Anthem Blue Cross", "bcbs_ca", "Anthem Blue Cross (California)"),
    ("Anthem Blue Cross Blue Shield", "bcbs_national", "Anthem Blue Cross Blue Shield"),
    ("Anthem BCBS", "bcbs_national", "Anthem Blue Cross Blue Shield"),
    ("Blue Cross Blue Shield of California", "bcbs_ca", "Anthem Blue Cross (California)"),
    ("BCBS CA", "bcbs_ca", "Anthem Blue Cross (California)"),
    ("Blue Shield of California", "blue_shield_ca", "Blue Shield of California"),
    ("Blue Shield CA", "blue_shield_ca", "Blue Shield of California"),
    ("BlueCross of California", "bcbs_ca", "Anthem Blue Cross (California)"),
    ("Blue Cross Blue Shield of Texas", "bcbs_tx", "Blue Cross Blue Shield of Texas"),
    ("BCBS TX", "bcbs_tx", "Blue Cross Blue Shield of Texas"),
    ("Blue Cross Blue Shield of Illinois", "bcbs_il", "Blue Cross Blue Shield of Illinois"),
    ("BCBS IL", "bcbs_il", "Blue Cross Blue Shield of Illinois"),
    ("Blue Cross Blue Shield of Florida", "bcbs_fl", "Florida Blue"),
    ("Florida Blue", "bcbs_fl", "Florida Blue"),
    ("Blue Cross Blue Shield of Michigan", "bcbs_mi", "Blue Cross Blue Shield of Michigan"),
    ("BCBS MI", "bcbs_mi", "Blue Cross Blue Shield of Michigan"),
    ("Blue Cross Blue Shield of Massachusetts", "bcbs_ma", "Blue Cross Blue Shield of Massachusetts"),
    ("BCBS MA", "bcbs_ma", "Blue Cross Blue Shield of Massachusetts"),
    ("Highmark Blue Cross Blue Shield", "bcbs_pa", "Highmark Blue Cross Blue Shield"),
    ("Highmark BCBS", "bcbs_pa", "Highmark Blue Cross Blue Shield"),
    ("Independence Blue Cross", "bcbs_pa_independence", "Independence Blue Cross"),
    ("Independence BCBS", "bcbs_pa_independence", "Independence Blue Cross"),
    ("Wellmark Blue Cross Blue Shield", "bcbs_ia", "Wellmark Blue Cross Blue Shield"),
    ("BCBS NC", "bcbs_nc", "Blue Cross Blue Shield of North Carolina"),
    ("Blue Cross Blue Shield of North Carolina", "bcbs_nc", "Blue Cross Blue Shield of North Carolina"),
    ("Premera Blue Cross", "bcbs_wa", "Premera Blue Cross (Washington)"),
    ("Regence BlueCross BlueShield", "bcbs_wa_regence", "Regence BlueCross BlueShield"),

    # UnitedHealth Group
    ("UnitedHealthcare", "unitedhealthcare", "UnitedHealthcare"),
    ("UnitedHealth", "unitedhealthcare", "UnitedHealthcare"),
    ("United Healthcare", "unitedhealthcare", "UnitedHealthcare"),
    ("United Health Care", "unitedhealthcare", "UnitedHealthcare"),
    ("UHC", "unitedhealthcare", "UnitedHealthcare"),
    ("UHG", "unitedhealthcare", "UnitedHealthcare"),
    ("UnitedHealthcare Choice Plus", "unitedhealthcare", "UnitedHealthcare"),
    ("UnitedHealthcare Choice", "unitedhealthcare", "UnitedHealthcare"),
    ("UnitedHealthcare Options PPO", "unitedhealthcare", "UnitedHealthcare"),
    ("United Healthcare Community Plan", "unitedhealthcare_medicaid", "UnitedHealthcare Community Plan"),
    ("United Behavioral Health", "unitedhealthcare", "UnitedHealthcare"),
    ("Optum", "unitedhealthcare", "UnitedHealthcare / Optum"),
    ("AARP Medicare Advantage from UnitedHealthcare", "unitedhealthcare_ma", "UnitedHealthcare Medicare Advantage"),

    # Aetna / CVS Health
    ("Aetna", "aetna", "Aetna"),
    ("AETNA", "aetna", "Aetna"),
    ("Aetna Health", "aetna", "Aetna"),
    ("AETNA HEALTH INC", "aetna", "Aetna"),
    ("Aetna PPO", "aetna", "Aetna"),
    ("Aetna HMO", "aetna", "Aetna"),
    ("Aetna Better Health", "aetna_medicaid", "Aetna Better Health (Medicaid)"),
    ("Aetna Medicare", "aetna_ma", "Aetna Medicare Advantage"),
    ("CVS Aetna", "aetna", "Aetna"),

    # Cigna
    ("Cigna", "cigna", "Cigna"),
    ("CIGNA", "cigna", "Cigna"),
    ("Cigna Healthcare", "cigna", "Cigna"),
    ("Cigna Health", "cigna", "Cigna"),
    ("Cigna PPO", "cigna", "Cigna"),
    ("Cigna HMO", "cigna", "Cigna"),
    ("Cigna-HealthSpring", "cigna_ma", "Cigna Medicare Advantage"),
    ("Cigna Medicare", "cigna_ma", "Cigna Medicare Advantage"),
    ("Evernorth", "cigna", "Cigna / Evernorth"),

    # Humana
    ("Humana", "humana", "Humana"),
    ("HUMANA", "humana", "Humana"),
    ("Humana Health", "humana", "Humana"),
    ("Humana PPO", "humana", "Humana"),
    ("Humana HMO", "humana", "Humana"),
    ("Humana Medicare Advantage", "humana_ma", "Humana Medicare Advantage"),
    ("Humana Gold Plus", "humana_ma", "Humana Medicare Advantage"),

    # Kaiser Permanente
    ("Kaiser Permanente", "kaiser", "Kaiser Permanente"),
    ("Kaiser", "kaiser", "Kaiser Permanente"),
    ("Kaiser Foundation", "kaiser", "Kaiser Permanente"),
    ("KP", "kaiser", "Kaiser Permanente"),

    # Centene / WellCare / Ambetter
    ("Centene", "centene", "Centene"),
    ("WellCare", "wellcare", "WellCare (Centene)"),
    ("Wellcare", "wellcare", "WellCare (Centene)"),
    ("Ambetter", "ambetter", "Ambetter (Centene)"),
    ("Peach State Health Management", "centene_medicaid", "Peach State Health (Centene)"),

    # Molina Healthcare
    ("Molina Healthcare", "molina", "Molina Healthcare"),
    ("Molina", "molina", "Molina Healthcare"),
    ("MOLINA", "molina", "Molina Healthcare"),

    # Health Net (Centene)
    ("Health Net", "health_net", "Health Net (Centene)"),
    ("HealthNet", "health_net", "Health Net (Centene)"),

    # Elevance Health (Anthem national plans)
    ("Elevance Health", "elevance", "Elevance Health (Anthem)"),
    ("Anthem", "elevance", "Anthem / Elevance Health"),
    ("ANTHEM", "elevance", "Anthem / Elevance Health"),
    ("Anthem Inc", "elevance", "Anthem / Elevance Health"),

    # Medicare & Medicaid (used in MRFs for benchmark rates)
    ("Medicare", "medicare", "Medicare"),
    ("CMS Medicare", "medicare", "Medicare"),
    ("Medicaid", "medicaid", "Medicaid"),
    ("Managed Medicaid", "medicaid", "Medicaid"),

    # TRICARE (DoD)
    ("TRICARE", "tricare", "TRICARE"),
    ("Tricare", "tricare", "TRICARE"),
    ("TriCare", "tricare", "TRICARE"),
    ("TRICARE Prime", "tricare", "TRICARE"),
    ("TRICARE Select", "tricare", "TRICARE"),

    # Self-pay / uninsured
    ("Self Pay", "self_pay", "Self-Pay / Uninsured"),
    ("Self-Pay", "self_pay", "Self-Pay / Uninsured"),
    ("Uninsured", "self_pay", "Self-Pay / Uninsured"),
    ("Cash Pay", "self_pay", "Self-Pay / Uninsured"),
]


def _table_ref(client: bigquery.Client) -> str:
    return f"{client.project}.{DATASET}.{TABLE}"


def create_table(client: bigquery.Client) -> None:
    """Create payer_name_aliases if it doesn't already exist."""
    table_id = _table_ref(client)
    table = bigquery.Table(table_id, schema=SCHEMA)
    table.clustering_fields = ["payer_group"]
    try:
        client.create_table(table)
        logger.info("Created table %s", table_id)
    except Exception:
        logger.info("Table %s already exists — skipping creation", table_id)


def seed_aliases(client: bigquery.Client, dry_run: bool = False) -> None:
    """Insert or update all seed aliases using MERGE (idempotent)."""
    if dry_run:
        logger.info("Dry run — would insert %d alias rows", len(SEED_ALIASES))
        for alias, group, display in SEED_ALIASES:
            logger.info("  %-60s → %-35s (%s)", alias, group, display)
        return

    table_id = _table_ref(client)
    rows = [{"alias": a, "payer_group": g, "payer_display": d} for a, g, d in SEED_ALIASES]

    errors = client.insert_rows_json(table_id, rows)
    if errors:
        logger.error("Insert errors: %s", errors)
        sys.exit(1)
    logger.info("Inserted %d alias rows into %s", len(rows), table_id)


def add_alias(
    client: bigquery.Client,
    alias: str,
    group: str,
    display: str,
    dry_run: bool = False,
) -> None:
    """Insert a single new alias row."""
    if dry_run:
        logger.info("Dry run — would insert alias '%s' → %s (%s)", alias, group, display)
        return
    table_id = _table_ref(client)
    errors = client.insert_rows_json(table_id, [{"alias": alias, "payer_group": group, "payer_display": display}])
    if errors:
        logger.error("Insert errors: %s", errors)
        sys.exit(1)
    logger.info("Inserted alias '%s' → %s", alias, group)


def audit_unmapped(client: bigquery.Client) -> None:
    """Print payer names in hospital_charges that have no alias in the table."""
    query = f"""
        SELECT hc.payer_name, COUNT(*) AS row_count
        FROM `{client.project}.{DATASET}.hospital_charges` hc
        LEFT JOIN `{client.project}.{DATASET}.{TABLE}` a
          ON hc.payer_name = a.alias
        WHERE a.alias IS NULL
          AND hc.payer_name IS NOT NULL
          AND hc.payer_name != ''
        GROUP BY hc.payer_name
        ORDER BY row_count DESC
        LIMIT 200
    """
    logger.info("Running audit query — this may take a few seconds...")
    rows = list(client.query(query).result())
    if not rows:
        logger.info("All payer names in hospital_charges are mapped.")
        return
    logger.info("Unmapped payer names (%d found):", len(rows))
    for row in rows:
        print(f"  {row['row_count']:>8,}  {row['payer_name']}")
    print()
    print("Use --add-alias to register new aliases, or add them to SEED_ALIASES and re-run.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed payer_name_aliases in BigQuery")
    parser.add_argument("--project", required=True, help="GCP project ID (e.g. clarobill-prd)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without writing")
    parser.add_argument("--audit", action="store_true", help="Show unmapped payer names in hospital_charges")
    parser.add_argument("--add-alias", metavar="ALIAS", help="Add a single new alias string")
    parser.add_argument("--group", metavar="PAYER_GROUP", help="payer_group for --add-alias")
    parser.add_argument("--display", metavar="DISPLAY_NAME", help="payer_display for --add-alias")
    args = parser.parse_args()

    client = bigquery.Client(project=args.project)

    if args.add_alias:
        if not args.group or not args.display:
            parser.error("--add-alias requires --group and --display")
        add_alias(client, args.add_alias, args.group, args.display, dry_run=args.dry_run)
        return

    if args.audit:
        audit_unmapped(client)
        return

    create_table(client)
    seed_aliases(client, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
