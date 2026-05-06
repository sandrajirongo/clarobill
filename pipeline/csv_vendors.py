"""CMS Price Transparency CSV column detection and payer-group extraction.

All hospital MRFs in CSV format in the ClaroBill archive follow the CMS
standard schema (v1.x / v2.x). The standard has three header rows:

  Row 1: hospital metadata column names
  Row 2: hospital metadata values (includes last_updated_on, NPI, etc.)
  Row 3: charge data column names (description, code|1, standard_charge|gross,
          and one group of 6 columns per payer+plan pair)
  Row 4+: charge data rows

This module detects the standard format, discovers payer groups from row 3
headers, and provides the exception raised when no known format matches.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class CsvVendorNotIdentified(Exception):
    """Raised by stream_charges_csv when header doesn't match any known schema."""


class PayerGroup(NamedTuple):
    """One (payer, plan) column group discovered from a CMS wide-format header."""

    payer_name: str
    plan_name: str
    dollar_col: str | None         # standard_charge|<p>|<pl>|negotiated_dollar
    pct_col: str | None            # standard_charge|<p>|<pl>|negotiated_percentage
    algorithm_col: str | None      # standard_charge|<p>|<pl>|negotiated_algorithm
    estimated_col: str | None      # estimated_amount|<p>|<pl>
    methodology_col: str | None    # standard_charge|<p>|<pl>|methodology


_CHARGE_RE = re.compile(
    r"^standard_charge\|(.+?)\|(.+?)\|(negotiated_dollar|negotiated_percentage"
    r"|negotiated_algorithm|methodology)$"
)
_ESTIMATED_RE = re.compile(r"^estimated_amount\|(.+?)\|(.+?)$")

_CMS_REQUIRED_COLS = frozenset({"description", "standard_charge|gross", "standard_charge|discounted_cash"})

# Non-standard column name variants → their CMS v2 equivalents.
# Hospitals using pre-v2 tooling, state-specific formats, or home-grown exports
# often use these names in place of the standard pipe-delimited names.
_COLUMN_ALIASES: dict[str, str] = {
    # Gross charge variants
    "gross_charge":                 "standard_charge|gross",
    "gross_charges":                "standard_charge|gross",
    "charge_amount":                "standard_charge|gross",
    "charge":                       "standard_charge|gross",
    "total_charge":                 "standard_charge|gross",
    "chargeamount":                 "standard_charge|gross",
    "gross":                        "standard_charge|gross",
    # Discounted cash / self-pay variants
    "discounted_cash_price":        "standard_charge|discounted_cash",
    "discounted_cash":              "standard_charge|discounted_cash",
    "cash_price":                   "standard_charge|discounted_cash",
    "self_pay":                     "standard_charge|discounted_cash",
    "self_pay_price":               "standard_charge|discounted_cash",
    "self_pay_rate":                "standard_charge|discounted_cash",
    # Code variants
    "cpt_code":                     "code|1",
    "hcpcs_code":                   "code|1",
    "procedure_code":               "code|1",
    "item_number":                  "code|1",
    "charge_code":                  "code|1",
    "revenue_code":                 "code|1",
    "rev_code":                     "code|1",
    "ms_drg":                       "code|1",
    # Description variants
    "item_description":             "description",
    "procedure_description":        "description",
    "charge_description":           "description",
    "service_description":          "description",
    "service_name":                 "description",
    "item_name":                    "description",
    "procedure_name":               "description",
    "chargedescription":            "description",
}


def normalize_col(col: str) -> str:
    """Map a non-standard column name to its CMS v2 equivalent, or lowercase as-is.

    Tries both the raw lowercased name and a space→underscore variant so that
    column headers with spaces (e.g. "Item Number") match underscore aliases
    (e.g. "item_number") without requiring duplicate alias entries.
    """
    key = col.strip().lower()
    if key in _COLUMN_ALIASES:
        return _COLUMN_ALIASES[key]
    key_under = key.replace(" ", "_")
    return _COLUMN_ALIASES.get(key_under, key)


def normalize_cols(raw_cols: list[str]) -> list[str]:
    """Apply alias normalization to a full column header list."""
    return [normalize_col(c) for c in raw_cols]


def is_cms_standard_csv(cols: list[str]) -> bool:
    """True if cols look like the CMS standard charge CSV row-3 header."""
    return _CMS_REQUIRED_COLS.issubset(set(cols))


def detect_payer_groups(cols: list[str]) -> list[PayerGroup]:
    """Return one PayerGroup per (payer, plan) pair in a CMS wide-format header.

    Order is preserved (insertion order of first seen column per pair).
    """
    groups: dict[tuple[str, str], dict[str, str]] = {}

    for col in cols:
        m = _CHARGE_RE.match(col)
        if m:
            key = (m.group(1), m.group(2))
            groups.setdefault(key, {})[m.group(3)] = col
            continue

        m = _ESTIMATED_RE.match(col)
        if m:
            key = (m.group(1), m.group(2))
            groups.setdefault(key, {})["estimated"] = col

    return [
        PayerGroup(
            payer_name=payer,
            plan_name=plan,
            dollar_col=grp.get("negotiated_dollar"),
            pct_col=grp.get("negotiated_percentage"),
            algorithm_col=grp.get("negotiated_algorithm"),
            estimated_col=grp.get("estimated"),
            methodology_col=grp.get("methodology"),
        )
        for (payer, plan), grp in groups.items()
    ]
