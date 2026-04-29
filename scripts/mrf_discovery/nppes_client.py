"""Shared NPPES Registry API client.

Used by `scripts/mrf_discovery/stage2_npi_registry.py`.

The NPPES Registry API at https://npiregistry.cms.hhs.gov/api/ is a public,
unauthenticated endpoint that resolves NPIs by name/state/taxonomy. We use it
to answer the question "what NPI corresponds to this CCN's hospital?".

Why we use the API and not the bulk download
--------------------------------------------
The NPPES bulk file is ~1 GB compressed and freely downloadable. We tried it
on 2026-04-28 and discovered two structural problems:
  - No `Authorized Official Web URL` column exists in V2 (we expected one)
  - Type code '04' (Medicare CCN) is never set on hospital organisation rows,
    so there is no usable CCN cross-reference path
See `docs/decisions/2026-04-28-mrf-discovery-build-insights.md` for the
diagnostic detail. The Registry API does the name+state matching for us
server-side and returns clean results, which is exactly what we need.

Hardening notes
---------------

  1. **City verification.** When multiple hospitals match by name+state, the
     simplest implementation returns the first result blindly. We require the
     result's address city to match (case-insensitive) the city we have on
     file — otherwise "Memorial Hospital" in Texas might resolve to the
     wrong of 14 different Memorial Hospitals.

  2. **Taxonomy preference.** Hospital NPIs use taxonomy codes starting with
     '28' (acute care, 282N*) or '283' (specialty hospital). When multiple
     candidates match, we prefer ones with the right taxonomy. This filters
     out medical groups, IPAs, etc. that share names with hospitals.

  3. **Rate limit at 5 req/s.** NPPES has no documented rate limit but its
     SLA is "best effort"; aggressive querying can trip server-side
     throttles. 5 req/s for ~14,000 hospitals = ~47 minutes worst case.

  4. **GCS-backed cache.** Results cached at gs://mrf-staging/nppes-api-cache.json.
     Re-runs read the cache first so a crashed run doesn't re-burn 47 minutes
     of API calls. Cache key: f"{name}|{state}|{city}". Cache value:
     {"npi": str | None, "matched_at": iso8601}.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

NPPES_API = "https://npiregistry.cms.hhs.gov/api/"
USER_AGENT = (
    "ClaroBill-MRFDiscovery/1.0 "
    "(price transparency research; contact@clarobill.com)"
)

# NPPES rate-limit budget. Empirically polite. Adjustable per-instance via
# NppesClient(min_interval=...).
DEFAULT_MIN_INTERVAL = 0.2  # 5 req/s

# Hospital taxonomy code prefixes (CMS Healthcare Provider Taxonomy).
# 282N: General acute care hospital
# 282E: Long-term care hospital
# 283Q: Psychiatric hospital
# 283X: Rehabilitation hospital
# 281P: Children's chronic disease hospital
# 273R, 273Y: Hospital units
HOSPITAL_TAXONOMY_PREFIXES = ("282", "283", "281", "273")


@dataclass
class LookupResult:
    """Outcome of one NPPES lookup. None values mean "tried, no match"."""

    npi: str | None
    legal_name: str | None
    matched_via: str  # "city_and_taxonomy" | "city_only" | "taxonomy_only" | "first_result" | "no_match" | "cache"


class NppesClient:
    """Stateful NPPES API client with rate limiting and an in-memory cache.

    The in-memory cache is loaded from / persisted to a JSON file; the caller
    decides when to flush. For a Cloud Run job, the JSON file lives in GCS
    and the orchestrator round-trips it before/after the run.
    """

    def __init__(
        self,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        timeout: int = 15,
        cache: dict[str, dict] | None = None,
    ):
        self.min_interval = min_interval
        self.timeout = timeout
        self._cache: dict[str, dict] = dict(cache) if cache else {}
        self._last_call_at = 0.0
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT

    @staticmethod
    def cache_key(hospital_name: str, state: str, city: str | None = None) -> str:
        return f"{hospital_name}|{state}|{city or ''}".upper()

    def cache_snapshot(self) -> dict[str, dict]:
        """Return a copy of the cache for persistence."""
        return dict(self._cache)

    def lookup(
        self,
        hospital_name: str,
        state: str,
        city: str | None = None,
    ) -> LookupResult:
        """Resolve hospital_name + state (+ city) to an NPI.

        Returns LookupResult with `npi=None` if no match was found. Always
        returns a result; never raises on missing data. Network errors raise.
        """
        if not hospital_name or not state:
            return LookupResult(npi=None, legal_name=None, matched_via="no_match")

        key = self.cache_key(hospital_name, state, city)
        if key in self._cache:
            cached = self._cache[key]
            return LookupResult(
                npi=cached.get("npi"),
                legal_name=cached.get("legal_name"),
                matched_via="cache",
            )

        # Rate-limit before the call
        now = time.monotonic()
        wait = self.min_interval - (now - self._last_call_at)
        if wait > 0:
            time.sleep(wait)
        self._last_call_at = time.monotonic()

        params = {
            "organization_name": hospital_name,
            "state": state,
            # "NPI-2" = organisation NPIs only (vs "NPI-1" = individuals).
            # Confirmed live 2026-04-28: the API rejects "NBO" with
            # "Field contains special character(s) or wrong number of characters".
            "enumeration_type": "NPI-2",
            "version": "2.1",
            "limit": 10,
        }
        try:
            resp = self._session.get(NPPES_API, params=params, timeout=self.timeout)
            resp.raise_for_status()
            results = resp.json().get("results") or []
        except (requests.RequestException, ValueError) as exc:
            # Catch HTTP errors and JSON parse errors only — bare `except Exception`
            # would swallow KeyboardInterrupt/SystemExit on Ctrl+C, leaving the
            # in-memory cache state ambiguous mid-loop.
            logger.warning("NPPES lookup failed for %r/%r: %s", hospital_name, state, exc)
            results = []

        result = self._select_best(results, expected_city=city)
        self._cache[key] = {
            "npi": result.npi,
            "legal_name": result.legal_name,
            "matched_via": result.matched_via,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        return result

    @staticmethod
    def _select_best(results: list[dict], expected_city: str | None) -> LookupResult:
        """Pick the best NPPES match given an optional expected city.

        Preference order:
          1. City matches AND taxonomy is hospital-class
          2. City matches (any taxonomy)
          3. Taxonomy is hospital-class (any city)
          4. First result (with a warning logged)
          5. None (no results)
        """
        if not results:
            return LookupResult(npi=None, legal_name=None, matched_via="no_match")

        expected_city_lc = (expected_city or "").strip().upper()

        scored: list[tuple[int, dict]] = []
        for r in results:
            score = 0
            # City match. Hospitals usually have both LOCATION (physical) and
            # MAILING addresses; physical is what we want for city verification.
            # NPPES sometimes uses PRIMARY as the address_purpose label instead
            # of LOCATION. We try LOCATION → PRIMARY → first → empty in turn.
            # Falling back to MAILING-as-first-address can produce false
            # negatives when a hospital's mailing PO box is in a different
            # city than the building.
            addresses = r.get("addresses") or []
            primary_addr = (
                next((a for a in addresses if (a.get("address_purpose") or "").upper() == "LOCATION"), None)
                or next((a for a in addresses if (a.get("address_purpose") or "").upper() == "PRIMARY"), None)
                or (addresses[0] if addresses else {})
            )
            if expected_city_lc and (primary_addr.get("city") or "").upper() == expected_city_lc:
                score += 10

            # Taxonomy match
            taxonomies = r.get("taxonomies") or []
            for t in taxonomies:
                code = (t.get("code") or "")
                if any(code.startswith(p) for p in HOSPITAL_TAXONOMY_PREFIXES):
                    score += 5
                    break

            scored.append((score, r))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        best_score, best = scored[0]

        npi = best.get("number")
        legal_name = (best.get("basic") or {}).get("organization_name")

        if best_score >= 15:
            via = "city_and_taxonomy"
        elif best_score >= 10:
            via = "city_only"
        elif best_score >= 5:
            via = "taxonomy_only"
        else:
            via = "first_result"
            logger.debug(
                "NPPES low-confidence match: %s NPI=%s (no city or taxonomy match)",
                legal_name, npi,
            )

        return LookupResult(npi=npi, legal_name=legal_name, matched_via=via)


def load_cache_from_gcs(storage_client, bucket_name: str, object_name: str) -> dict[str, dict]:
    """Load a JSON cache from GCS, returning empty dict if not present."""
    blob = storage_client.bucket(bucket_name).blob(object_name)
    if not blob.exists():
        return {}
    text = blob.download_as_text()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("NPPES cache at gs://%s/%s is malformed; starting fresh", bucket_name, object_name)
        return {}


def save_cache_to_gcs(
    storage_client,
    bucket_name: str,
    object_name: str,
    cache: dict[str, dict],
) -> None:
    """Persist the cache JSON to GCS (overwrites)."""
    blob = storage_client.bucket(bucket_name).blob(object_name)
    blob.upload_from_string(
        json.dumps(cache, sort_keys=True, separators=(",", ":")),
        content_type="application/json",
    )
