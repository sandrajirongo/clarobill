"""Shared utilities for parsing CMS Hospital Price Transparency MRF files.

Supports CMS standard JSON schema v2.0.0 (effective July 2024+).
Pre-v2.0.0 formats are intentionally skipped — the format chaos of earlier
versions is not worth the complexity for the ~5% of hospitals still on them.

The v2.0.0 schema nests charges as:
  standard_charge_information[]
    .code_information[]     (one or more CPT/HCPCS/DRG/etc. codes)
    .standard_charges[]     (one per setting: inpatient/outpatient/both)
      .payers_information[] (one per payer+plan)

Normalisation flattens this into rows, one per
  code × setting × payer_or_null combination.
"""

import logging
from dataclasses import dataclass
from typing import Any, BinaryIO, Generator

import ijson

logger = logging.getLogger(__name__)

# CMS v2.0.0 root key for charge data.
# Some early v2.0.0 implementations used the longer key name.
_CHARGE_INFO_KEYS = ("standard_charge_information", "standard_charge_information_and_modifiers")

# Field name variants across hospital MRF implementations for the same concept.
# Each tuple is tried in order; first non-None wins.
_CASH_PRICE_KEYS = ("discounted_cash", "discounted_cash_price", "cash_price")
_MIN_RATE_KEYS = ("minimum", "min", "minimum_negotiated_rate")
_MAX_RATE_KEYS = ("maximum", "max", "maximum_negotiated_rate")
_NEGOTIATED_DOLLAR_KEYS = ("standard_charge_dollar", "estimated_amount", "negotiated_rate")
_METHODOLOGY_KEYS = ("methodology", "standard_charge_type")


@dataclass(frozen=True)
class ChargeRow:
    """One normalised charge row ready for BigQuery insertion."""

    # Phase 4: partition key. Every row carries the year of the MRF it came
    # from so the rules engine can join 2026 bills to 2026 charges (and a
    # fallback to 2025 if no 2026 data exists for that hospital). Resolved
    # by pipeline.effective_year.resolve_year() at parse time.
    pricing_effective_year: int
    hospital_npi: str
    code_type: str
    code: str
    description: str
    gross_charge: float | None
    discounted_cash_price: float | None
    min_negotiated: float | None
    max_negotiated: float | None
    payer_name: str | None
    plan_name: str | None
    negotiated_charge: float | None
    negotiated_type: str | None
    setting: str
    effective_date: str  # ISO date string (YYYY-MM-DD)
    scraped_at: str      # ISO datetime string (UTC)

    def to_bq_row(self) -> dict[str, Any]:
        """Serialise to a BigQuery-compatible dict."""
        return {
            "pricing_effective_year": self.pricing_effective_year,
            "hospital_npi": self.hospital_npi,
            "code_type": self.code_type,
            "code": self.code,
            "description": self.description,
            "gross_charge": self.gross_charge,
            "discounted_cash_price": self.discounted_cash_price,
            "min_negotiated": self.min_negotiated,
            "max_negotiated": self.max_negotiated,
            "payer_name": self.payer_name,
            "plan_name": self.plan_name,
            "negotiated_charge": self.negotiated_charge,
            "negotiated_type": self.negotiated_type,
            "setting": self.setting,
            "effective_date": self.effective_date,
            "scraped_at": self.scraped_at,
        }


def extract_npi_from_mrf_root(root: dict[str, Any]) -> str | None:
    """Extract a 10-digit NPI from MRF root object metadata.

    CMS v2.0.0 files include the hospital NPI in the root under various key
    names depending on the vendor.  This checks the most common variants and
    validates the result is exactly 10 digits before returning it.

    Args:
        root: The root-level dict of a parsed MRF JSON file.

    Returns:
        A 10-digit NPI string, or None if not found or not parseable.
    """
    candidates = [
        root.get("hospital_npi"),
        root.get("npi"),
        root.get("provider_npi"),
    ]
    # Some vendors nest location info: root["hospital_location"][0]["hospital_npi"]
    location = root.get("hospital_location")
    if isinstance(location, list) and location:
        candidates.append(location[0].get("hospital_npi"))
        candidates.append(location[0].get("npi"))

    for val in candidates:
        if val is None:
            continue
        digits = str(val).strip().replace("-", "")
        if len(digits) == 10 and digits.isdigit():
            return digits

    return None


def detect_mrf_version(root: dict[str, Any]) -> str | None:
    """Return the schema version string from an MRF root dict, or None.

    CMS v2.0.0 files include a top-level "version" key.
    Earlier formats often omit it or use different field names.
    """
    return root.get("version") or root.get("schema_version")


def extract_mrf_date(root: dict[str, Any]) -> str | None:
    """Return the effective/last-updated date from an MRF root dict.

    Returns an ISO date string (YYYY-MM-DD) suitable for the effective_date
    column in hospital_charges, or None if not present.
    """
    raw = root.get("last_updated_on") or root.get("last_updated") or root.get("version_date")
    if not raw:
        return None
    # Normalise: take the first 10 chars (YYYY-MM-DD) to drop any time component.
    return str(raw).strip()[:10]


def _parse_float(value: Any) -> float | None:
    """Coerce a raw MRF charge value to float, returning None for empty/non-numeric."""
    if value is None:
        return None
    try:
        result = float(value)
        # Negative charges are data errors — treat as missing rather than propagating.
        return result if result >= 0 else None
    except (TypeError, ValueError):
        return None


def _first(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first non-None value from d for the given key candidates."""
    for key in keys:
        val = d.get(key)
        if val is not None:
            return val
    return None


def stream_charges_v2(
    file_obj: BinaryIO,
    hospital_npi: str,
    pricing_effective_year: int,
    effective_date: str,
    scraped_at: str,
) -> Generator[ChargeRow, None, None]:
    """Stream ChargeRow objects from a v2.0.0 MRF file without loading it entirely.

    Uses ijson for incremental JSON parsing so files larger than available RAM
    are handled correctly (some hospital MRFs exceed 1 GB uncompressed).

    Emits one row per (code × setting × payer) combination. When a charge has
    no payer-specific rates, emits one row with payer_name=None so that gross
    charge and cash price data is not lost.

    Phase 4 (Sandra Q5b — "make parsing as functional as possible"):
      - Per-item try/except so a single malformed charge entry doesn't kill
        the rest of the file. We log the error and keep streaming.
      - File-level fallback chain: if both _CHARGE_INFO_KEYS variants fail,
        we log the structural reason rather than silently emitting zero rows.

    Args:
        file_obj: Binary file-like object pointing to an MRF JSON file.
        hospital_npi: The NPI of the hospital this file belongs to.
        pricing_effective_year: Year the MRF's prices apply to. Resolved by
            pipeline.effective_year.resolve_year() — see that module for the
            three-source fallback (JSON last_updated_on, HTTP Last-Modified,
            current calendar year).
        effective_date: ISO date string to use as effective_date on all rows.
        scraped_at: ISO datetime string (UTC) to use as scraped_at on all rows.

    Yields:
        ChargeRow instances ready for BigQuery insertion.
    """
    # Try both key variants; ijson.items raises IncompleteJSONError for wrong paths,
    # so we probe the file with the first key and fall back to the second.
    for root_key in _CHARGE_INFO_KEYS:
        try:
            items = ijson.items(file_obj, f"{root_key}.item")
            row_count = 0
            bad_items = 0
            for item in items:
                # Per-item tolerance: a single weird charge object (missing
                # required keys, wrong types, etc.) does not abort the whole
                # file. We log and skip to the next item. At ~13k hospitals,
                # one bad item per file would be a survivable rounding error;
                # one bad item killing a whole hospital is a data outage.
                try:
                    yield from _expand_charge_item(
                        item, hospital_npi, pricing_effective_year,
                        effective_date, scraped_at,
                    )
                    row_count += 1
                except Exception as exc:  # noqa: BLE001 — see comment above
                    bad_items += 1
                    if bad_items <= 5:
                        logger.warning(
                            "Skipping malformed charge item for NPI %s: %s",
                            hospital_npi, exc,
                        )
            if bad_items:
                logger.warning(
                    "NPI %s: %d malformed items skipped out of %d total",
                    hospital_npi, bad_items, row_count + bad_items,
                )
            logger.info(
                "Parsed %d charge items for NPI %s (key=%s)",
                row_count,
                hospital_npi,
                root_key,
            )
            return
        except (ijson.IncompleteJSONError, StopIteration):
            # File ended prematurely or wrong key — try next candidate
            file_obj.seek(0)
            continue
        except Exception as exc:  # noqa: BLE001 — robustness over strictness
            # ijson can raise UnicodeDecodeError, JSONDecodeError, or vendor-
            # specific errors on truly broken files. Try the next root key
            # before giving up entirely.
            logger.warning(
                "Unexpected error parsing NPI %s with key=%s: %s — trying next variant",
                hospital_npi, root_key, exc,
            )
            try:
                file_obj.seek(0)
            except Exception:
                pass
            continue

    logger.warning("No standard_charge_information found for NPI %s", hospital_npi)


def _expand_charge_item(
    item: dict[str, Any],
    hospital_npi: str,
    pricing_effective_year: int,
    effective_date: str,
    scraped_at: str,
) -> Generator[ChargeRow, None, None]:
    """Expand one standard_charge_information item into ChargeRow objects.

    A single charge item can have multiple code_information entries (e.g. the same
    procedure coded as both CPT and HCPCS) and multiple standard_charges entries
    (one per setting). Each combination is emitted as its own row so queries can
    filter by code or setting independently.
    """
    description = str(item.get("description") or "").strip()
    code_infos = item.get("code_information") or []
    charges = item.get("standard_charges") or []

    # If a charge item has no code_information, emit with code="" so data isn't lost.
    if not code_infos:
        code_infos = [{}]

    for code_info in code_infos:
        code = str(code_info.get("code") or "").strip()
        code_type = str(code_info.get("type") or "UNKNOWN").strip().upper()

        for charge in charges:
            setting = str(charge.get("setting") or "both").strip().lower()
            gross = _parse_float(charge.get("gross_charge"))
            cash = _parse_float(_first(charge, _CASH_PRICE_KEYS))
            min_neg = _parse_float(_first(charge, _MIN_RATE_KEYS))
            max_neg = _parse_float(_first(charge, _MAX_RATE_KEYS))
            payers = charge.get("payers_information") or []

            if payers:
                for payer in payers:
                    yield ChargeRow(
                        pricing_effective_year=pricing_effective_year,
                        hospital_npi=hospital_npi,
                        code_type=code_type,
                        code=code,
                        description=description,
                        gross_charge=gross,
                        discounted_cash_price=cash,
                        min_negotiated=min_neg,
                        max_negotiated=max_neg,
                        payer_name=str(payer.get("payer_name") or "").strip() or None,
                        plan_name=str(payer.get("plan_name") or "").strip() or None,
                        negotiated_charge=_parse_float(_first(payer, _NEGOTIATED_DOLLAR_KEYS)),
                        negotiated_type=str(_first(payer, _METHODOLOGY_KEYS) or "").strip() or None,
                        setting=setting,
                        effective_date=effective_date,
                        scraped_at=scraped_at,
                    )
            else:
                # No payer rates — emit a single row with gross charge + cash price only.
                # These are still valuable for ABOVE_GROSS_CHARGE comparisons.
                yield ChargeRow(
                    pricing_effective_year=pricing_effective_year,
                    hospital_npi=hospital_npi,
                    code_type=code_type,
                    code=code,
                    description=description,
                    gross_charge=gross,
                    discounted_cash_price=cash,
                    min_negotiated=min_neg,
                    max_negotiated=max_neg,
                    payer_name=None,
                    plan_name=None,
                    negotiated_charge=None,
                    negotiated_type=None,
                    setting=setting,
                    effective_date=effective_date,
                    scraped_at=scraped_at,
                )
