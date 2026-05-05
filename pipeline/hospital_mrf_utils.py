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

import csv
import gzip
import io
import logging
import re
from dataclasses import dataclass
from typing import Any, BinaryIO, Generator, Iterator
from urllib.parse import unquote, urlparse

import ijson

from csv_vendors import (
    CsvVendorNotIdentified,
    PayerGroup,
    detect_payer_groups,
    is_cms_standard_csv,
)

_UTF8_BOM = b"\xef\xbb\xbf"


def _strip_bom(file_obj: BinaryIO) -> BinaryIO:
    """Sniff the first 3 bytes for a UTF-8 BOM and return a stream that skips it.

    Some hospital MRFs are exported from Windows tools that prepend a UTF-8
    BOM (EF BB BF). ijson silently emits zero items when it sees a BOM at the
    start of the stream — losing the entire hospital's pricing data.

    This wrapper reads the first 3 bytes; if they match the BOM, those bytes
    are dropped and only the post-BOM content is exposed to downstream code.
    Otherwise the original stream is returned at position 0.

    SF3 (Phase 8.2): when the BOM is present AND the underlying stream is
    seekable, the post-BOM content is materialised into a `BytesIO` so that
    `seek(0)` on the returned stream rewinds to post-BOM-position-0 (not
    pre-BOM). Pre-SF3 the alternate-root-key retry at the call site
    re-exposed the BOM bytes to ijson, causing UTF-8-BOM hospitals using
    the longer `standard_charge_information_and_modifiers` key to be
    silently skipped — permanent coverage hole for that cohort.

    For non-seekable streams (gzip-wrapped reads), the BufferedReader path
    is preserved; the alt-key retry is already a no-op for those (see the
    seek-best-effort guard in extract_charge_rows).
    """
    head = file_obj.read(len(_UTF8_BOM))
    if head == _UTF8_BOM:
        # SF3: materialise the post-BOM content for seekable streams so
        # rewinds land at post-BOM-position-0. The cost is one full-file
        # read; MRF JSONs are typically <500 MB so this fits comfortably
        # in memory on Cloud Run (4 GiB tier). Larger files will fall back
        # to the BufferedReader path below.
        if file_obj.seekable():
            try:
                rest = file_obj.read()
                return io.BytesIO(rest)
            except (MemoryError, OSError) as exc:
                logger.warning(
                    "BOM strip into BytesIO failed (%s) — falling back to "
                    "BufferedReader; alt-key retry will not work for this file",
                    exc,
                )
        # BOM consumed — wrap the rest of the original stream so downstream
        # ijson can keep reading from where we left off. Alt-key retries
        # via seek(0) will re-expose the BOM; first-key probes are
        # already 95%+ reliable.
        return io.BufferedReader(file_obj)  # type: ignore[arg-type]
    # No BOM — concatenate the bytes we already read back onto the stream.
    return io.BufferedReader(_PrefixedStream(head, file_obj))  # type: ignore[arg-type]


class _PrefixedStream(io.RawIOBase):
    """Tiny shim that prepends `prefix` bytes to an existing binary stream.

    Used by _strip_bom when no BOM was found — restores the bytes we sniffed
    so ijson can read the full file from the start.
    """

    def __init__(self, prefix: bytes, stream: BinaryIO) -> None:
        self._prefix = prefix
        self._stream = stream
        self._prefix_consumed = 0

    def readable(self) -> bool:
        return True

    def readinto(self, b):  # type: ignore[no-untyped-def]
        n = len(b)
        offset = 0
        if self._prefix_consumed < len(self._prefix):
            remaining = self._prefix[self._prefix_consumed:]
            take = min(len(remaining), n)
            b[:take] = remaining[:take]
            self._prefix_consumed += take
            offset += take
            if offset == n:
                return n
        chunk = self._stream.read(n - offset)
        b[offset:offset + len(chunk)] = chunk
        return offset + len(chunk)

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
    """One normalised charge row ready for BigQuery insertion.

    Phase 4 schema: day-level effective_date is gone — pricing_effective_year
    is the date dimension. source_mrf_url + source_gcs_uri provide row-level
    provenance back to the immutable archive blob in clarobill-mrf-archive-uscentral.
    """

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
    source_mrf_url: str | None
    source_gcs_uri: str | None
    scraped_at: str  # ISO datetime string (UTC)

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
            "source_mrf_url": self.source_mrf_url,
            "source_gcs_uri": self.source_gcs_uri,
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


# Standalone 10-digit NPI: bounded by non-digit characters so we don't pick
# the middle of a longer numeric string (e.g. a SAS token or hash).
_NPI_RE = re.compile(r"(?<!\d)(\d{10})(?!\d)")


def extract_npi_from_url(url: str) -> str | None:
    """Extract a 10-digit hospital NPI from an MRF source URL.

    CMS does not require NPI in the URL, but virtually every observed
    publishing pattern embeds it in the filename — typically as a leading
    `{npi}_{slug}_standardcharges.json` prefix (Dignity Health, Saint Lukes,
    Providence, BJC). When MRFs are produced by health-system tooling, the
    URL is the most reliable extraction surface — JSON internals sometimes
    carry the parent organisation's NPI rather than the facility's.

    Strategy:
      1. Strip the query string (SAS tokens, signed-URL params).
      2. Decode percent-encoding so `%20` directories don't hide digits.
      3. Search the URL basename first — that's where the NPI is in 95%+
         of observed real-world URLs (filename-leading position).
      4. Fall back to the full URL path so directory-based layouts like
         `/mrf/{npi}/charges.json` still resolve.
      5. 9-digit numbers (EINs in `XX-XXXXXXX` format) are NOT returned —
         a small subset of small/critical-access hospitals publish only
         their EIN. Those need separate handling and a dedicated tax_id
         column; silently treating EIN as NPI corrupts downstream joins.

    Returns a 10-digit NPI string or None.
    """
    if not url:
        return None
    parsed = urlparse(url)
    # Path only — query strings often contain digit runs from SAS tokens.
    path = unquote(parsed.path or "")
    if not path:
        return None
    # Basename first: the dominant publishing pattern.
    basename = path.rsplit("/", 1)[-1]
    match = _NPI_RE.search(basename)
    if match:
        return match.group(1)
    # Path fallback: catches /mrf/1234567890/charges.json layouts.
    match = _NPI_RE.search(path)
    if match:
        return match.group(1)
    return None


def sniff_mrf_format(
    prefix_bytes: bytes,
    content_type: str | None = None,
    url: str | None = None,
) -> str:
    """Identify the format of an MRF response from its first bytes + headers.

    Returns one of: 'json', 'csv', 'zip', 'xlsx', 'xml', 'pdf', 'html',
    'empty', 'unknown'.

    The 5/3 postmortem traced ~16,000 garbage blobs in mrf-archive to the
    scraper writing whatever the HTTP response body was — HTML 404 pages,
    hospital marketing landing pages, an Evangelical Lutheran Church
    grants page, a utility billing page — all saved as `.json.gz`. The
    parser then spent 5–10 seconds per blob trying to ijson-stream them
    before failing.

    This sniff is the scrape-side gate: if the response is not a real data
    format (json/csv/zip/xlsx/xml), the scraper rejects it before writing
    to staging or archive. Without this, every scheduled scrape would
    re-pollute the archive with the same garbage.

    Detection order:
      1. Magic bytes — most reliable for binary formats (zip, xlsx, pdf, gzip-of-json).
      2. URL extension — for csv (no magic bytes) when the URL is unambiguous.
      3. Content-Type header — fallback for csv/xml when bytes are inconclusive.
      4. First-byte heuristic — `<` ⇒ html, `{`/`[` ⇒ json (after BOM strip).
    """
    if not prefix_bytes:
        return "empty"

    # Strip optional UTF-8 BOM before character checks.
    stripped = prefix_bytes.lstrip(b"\xef\xbb\xbf").lstrip()

    # --- Magic-bytes (most reliable) ---
    if prefix_bytes.startswith(b"PK\x03\x04"):
        # ZIP container; can be xlsx (xlsx are zip + Office XML inside) or a
        # plain zip of MRF files. Trust URL extension to distinguish.
        if url and url.lower().split("?", 1)[0].endswith(".xlsx"):
            return "xlsx"
        return "zip"
    if prefix_bytes.startswith(b"%PDF"):
        return "pdf"
    if prefix_bytes.startswith(b"\x1f\x8b"):
        # gzip — try to peek at the decompressed first byte to classify the
        # underlying format (json.gz vs csv.gz vs anything.gz).
        try:
            decoded = gzip.GzipFile(fileobj=io.BytesIO(prefix_bytes)).read(64)
            if decoded:
                inner = decoded.lstrip(b"\xef\xbb\xbf").lstrip()
                if inner.startswith((b"{", b"[")):
                    return "json"
                if inner.startswith(b"<"):
                    return "xml" if b"<?xml" in inner[:64] else "html"
        except (OSError, EOFError):
            pass
        # Default for unknown gzip content: classify by URL/content-type.
        if url and ".csv" in url.lower():
            return "csv"
        return "unknown"

    # --- Text formats (no magic bytes) ---
    if stripped.startswith(b"<?xml"):
        return "xml"
    if stripped.startswith(b"<"):
        return "html"
    if stripped.startswith((b"{", b"[")):
        return "json"

    # --- URL/Content-Type fallbacks for CSV (no magic bytes) ---
    url_lower = (url or "").lower().split("?", 1)[0]
    ct_lower = (content_type or "").lower()
    if url_lower.endswith(".csv") or "csv" in ct_lower:
        return "csv"
    if url_lower.endswith(".xml") or "xml" in ct_lower:
        return "xml"

    return "unknown"


# Formats the scrape-time validator considers real MRF data and will accept
# into staging/archive. Anything outside this set is rejected at scrape time.
# json/csv/zip/xlsx/xml are formats hospitals legitimately publish in;
# html/pdf/empty/unknown are the rejection bucket. PDF is always rejected
# because in the entire historic archive we found zero real chargemaster
# PDFs — they were all landing pages, good-faith-estimate notices, or
# patient-billing brochures.
ACCEPTED_MRF_FORMATS = frozenset({"json", "csv", "zip", "xlsx", "xml"})


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
    scraped_at: str,
    source_mrf_url: str | None = None,
    source_gcs_uri: str | None = None,
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
    # Many hospital MRFs are exported from Windows tools that prepend a UTF-8
    # BOM (EF BB BF). ijson chokes silently on the BOM and emits zero items,
    # which would lose the entire hospital. Sniff and strip the BOM once at
    # the start of the stream before handing it to ijson.
    file_obj = _strip_bom(file_obj)

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
                        scraped_at, source_mrf_url, source_gcs_uri,
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
            # File ended prematurely or wrong key — try next candidate.
            # 2026-05-01 fix: gzip-wrapped streams (json.gz files) aren't
            # seekable; the prior unconditional seek(0) raised
            # io.UnsupportedOperation and crashed the whole parse for any
            # gzip MRF whose first root-key probe failed. Make the rewind
            # best-effort: if we can't seek, we can't try the next variant
            # for this file — log and give up cleanly. Caller's per-blob
            # try/except then marks parse_status='failed' on archive_index
            # and moves on. Most MRFs (~95%) use the first key variant so
            # the data loss from this branch is small.
            try:
                file_obj.seek(0)
            except (io.UnsupportedOperation, OSError, ValueError) as seek_exc:
                logger.warning(
                    "NPI %s: stream not seekable (gzip?) — cannot retry "
                    "alternate root key after %s failed: %s",
                    hospital_npi, root_key, seek_exc,
                )
                return
            continue
        except Exception as exc:  # noqa: BLE001 — robustness over strictness
            # ijson can raise UnicodeDecodeError, JSONDecodeError, or vendor-
            # specific errors on truly broken files. Try the next root key
            # before giving up entirely. Same seek-safety as above.
            logger.warning(
                "Unexpected error parsing NPI %s with key=%s: %s — trying next variant",
                hospital_npi, root_key, exc,
            )
            try:
                file_obj.seek(0)
            except Exception:
                # Can't rewind — give up on this file rather than crash.
                return
            continue

    logger.warning("No standard_charge_information found for NPI %s", hospital_npi)


def _expand_charge_item(
    item: dict[str, Any],
    hospital_npi: str,
    pricing_effective_year: int,
    scraped_at: str,
    source_mrf_url: str | None,
    source_gcs_uri: str | None,
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
                        source_mrf_url=source_mrf_url,
                        source_gcs_uri=source_gcs_uri,
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
                    source_mrf_url=source_mrf_url,
                    source_gcs_uri=source_gcs_uri,
                    scraped_at=scraped_at,
                )


def _extract_npi_from_csv_meta(header_row: list[str], values_row: list[str]) -> str:
    """Pull a 10-digit NPI from a CMS CSV metadata row pair (rows 1 and 2)."""
    headers = [h.strip().lower() for h in header_row]
    for col in ("type_2_npi", "hospital_npi", "npi"):
        try:
            idx = headers.index(col)
        except ValueError:
            continue
        if idx < len(values_row):
            val = values_row[idx].strip()
            if len(val) == 10 and val.isdigit():
                return val
    return ""


def _expand_csv_row(
    row: dict[str, str],
    payer_groups: list[PayerGroup],
    hospital_npi: str,
    pricing_effective_year: int,
    scraped_at: str,
    source_mrf_url: str | None,
    source_gcs_uri: str | None,
) -> Iterator[ChargeRow]:
    """Expand one CMS standard CSV data row into ChargeRow objects.

    Emits one row per (code × payer). code|2 is treated as a second code entry
    matching the same behaviour as _expand_charge_item for JSON files. If no
    payer groups are present (or all have empty charge columns), emits a single
    row with payer_name=None carrying gross and discounted_cash values.
    """
    description = row.get("description", "").strip()
    setting = (row.get("setting") or "both").strip().lower() or "both"
    gross = _parse_float(row.get("standard_charge|gross"))
    cash = _parse_float(row.get("standard_charge|discounted_cash"))
    min_neg = _parse_float(
        row.get("standard_charge|min") or row.get("standard_charge|minimum")
    )
    max_neg = _parse_float(
        row.get("standard_charge|max") or row.get("standard_charge|maximum")
    )

    codes: list[tuple[str, str]] = []
    code1 = row.get("code|1", "").strip()
    type1 = (row.get("code|1|type", "") or "UNKNOWN").strip().upper()
    if code1:
        codes.append((code1, type1))
    code2 = row.get("code|2", "").strip()
    type2 = (row.get("code|2|type", "") or "UNKNOWN").strip().upper()
    if code2:
        codes.append((code2, type2))
    if not codes:
        codes = [("", "UNKNOWN")]

    def _pg_val(col: str | None) -> str:
        # payer_group column names are in original case (e.g. "standard_charge|Aetna|PPO|...")
        # but the row dict was built with lowercased keys, so lower() before lookup.
        return row.get(col.lower() if col else "") or ""

    emitted = False
    for code, code_type in codes:
        for pg in payer_groups:
            neg_charge = _parse_float(_pg_val(pg.dollar_col))
            methodology = _pg_val(pg.methodology_col).strip() or None
            pct = _pg_val(pg.pct_col).strip()
            algo = _pg_val(pg.algorithm_col).strip()
            estimated = _parse_float(_pg_val(pg.estimated_col))

            # Determine negotiated_type: prefer explicit methodology, then derive
            # from whichever rate expression is present.
            neg_type = methodology
            if neg_type is None:
                if pct:
                    neg_type = f"percentage:{pct}"
                elif algo:
                    neg_type = f"algorithm:{algo}"

            # Skip payer columns that are entirely empty — they represent
            # contracted payers not applicable to this service row.
            if neg_charge is None and neg_type is None and estimated is None:
                continue

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
                payer_name=pg.payer_name or None,
                plan_name=pg.plan_name or None,
                negotiated_charge=neg_charge,
                negotiated_type=neg_type,
                setting=setting,
                source_mrf_url=source_mrf_url,
                source_gcs_uri=source_gcs_uri,
                scraped_at=scraped_at,
            )
            emitted = True

        if not payer_groups or not emitted:
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
                source_mrf_url=source_mrf_url,
                source_gcs_uri=source_gcs_uri,
                scraped_at=scraped_at,
            )
            emitted = True


def stream_charges_csv(
    file_obj: BinaryIO,
    hospital_npi: str,
    pricing_effective_year: int,
    scraped_at: str,
    source_mrf_url: str | None = None,
    source_gcs_uri: str | None = None,
) -> Iterator[ChargeRow]:
    """Stream-parse a CMS-standard wide-format CSV MRF.

    The CMS Price Transparency standard CSV has three header rows before the
    charge data:
      Row 1: hospital metadata column names
      Row 2: hospital metadata values (last_updated_on, NPI, etc.)
      Row 3: charge column names including dynamic payer columns
      Row 4+: one charge row per procedure/item

    Payer columns are discovered dynamically from row 3, so this single
    function handles any hospital that follows the CMS standard schema.

    Raises CsvVendorNotIdentified if row 3 doesn't contain the required
    standard_charge|gross and standard_charge|discounted_cash columns.
    """
    file_obj = _strip_bom(file_obj)
    text_stream = io.TextIOWrapper(file_obj, encoding="utf-8", errors="replace")
    reader = csv.reader(text_stream)

    meta_header = next(reader, None)
    if meta_header is None:
        return

    meta_values = next(reader, None)
    if meta_values is None:
        return

    if not hospital_npi and meta_header and meta_values:
        hospital_npi = _extract_npi_from_csv_meta(meta_header, meta_values)

    charge_header = next(reader, None)
    if charge_header is None:
        return

    # raw_cols preserves the original case from the hospital's CSV file so that
    # payer names (e.g. "Blue Cross Blue Shield") are stored correctly in the
    # output rows. cols is the lowercased version used as dict keys when building
    # the per-row lookup dict, since fixed columns like "standard_charge|gross"
    # must be looked up case-insensitively.
    raw_cols = [c.strip() for c in charge_header]
    cols = [c.lower() for c in raw_cols]

    if not is_cms_standard_csv(cols):
        raise CsvVendorNotIdentified(
            "Header row 3 missing standard_charge|gross or "
            "standard_charge|discounted_cash — not a CMS standard CSV"
        )

    # Payer group column references use original-case column names so that
    # payer_name / plan_name in the emitted ChargeRow are correctly cased.
    # When looking up values in `row`, we lowercase the column name (see
    # _expand_csv_row). Fixed columns (description, code|1, etc.) are
    # already lowercase in `cols` so they look up cleanly with row.get().
    payer_groups = detect_payer_groups(raw_cols)

    row_count = 0
    bad_rows = 0
    for raw_row in reader:
        if not any(v.strip() for v in raw_row):
            continue
        row = dict(zip(cols, raw_row))
        try:
            for charge_row in _expand_csv_row(
                row, payer_groups, hospital_npi, pricing_effective_year,
                scraped_at, source_mrf_url, source_gcs_uri,
            ):
                yield charge_row
                row_count += 1
        except Exception as exc:  # noqa: BLE001
            bad_rows += 1
            if bad_rows <= 5:
                logger.warning(
                    "Skipping malformed CSV row for NPI %s: %s", hospital_npi, exc,
                )

    if bad_rows:
        logger.warning(
            "NPI %s CSV: %d bad rows skipped out of %d total",
            hospital_npi, bad_rows, row_count + bad_rows,
        )
    logger.info("Parsed %d CSV charge rows for NPI %s", row_count, hospital_npi)
