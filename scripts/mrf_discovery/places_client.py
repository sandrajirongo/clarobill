"""Google Places API (New) client for Stage 3 Tier 3.

This module is the only place in ClaroBill that spends real money. Every
design decision here is documented at:
    docs/decisions/2026-04-28-google-places-cost-design.md

Cost control is the primary concern; correctness is the second. Performance
is irrelevant — we're rate-limited well below the network throughput.

Two-call structure
------------------
For each hospital lookup:

    1. Text Search (Essentials SKU, $0.005/call)
       - Field mask: places.id, places.displayName.text
       - Returns at most 3 candidates
    2. Place Details (Enterprise SKU, $0.025/call)
       - ONLY fired if Search returned ≥1 candidate
       - Field mask: id, websiteUri, formattedAddress
       - Fired up to 3 times for ambiguous (multi-result) lookups

Verification (free)
-------------------
For multi-result lookups: HEAD-fetch each candidate's websiteUri and confirm
the hospital name appears in the page title or H1. The first candidate that
verifies wins; tie-break by formattedAddress city match.

Cost accounting
---------------
The CostMeter class tracks running spend client-side. Every call is recorded
BEFORE it's made (defensive — if the call crashes mid-flight, the cost is
still booked). If running_cost + worst_case_next_call_cost > budget, the
client raises BudgetExceeded which the caller catches to halt cleanly.

Cache
-----
Per-hospital results cached in memory; the orchestrator persists to GCS at
gs://mrf-staging/places-api-cache.json every 200 lookups + at end of run.
Annual immutable snapshot at gs://clarobill-mrf-archive-uscentral/places-api-cache-snapshots/{year}.json.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

# Google Places "New" API
PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS_URL_TEMPLATE = "https://places.googleapis.com/v1/places/{place_id}"

# Field masks. ORDER MATTERS — these strings determine SKU pricing.
# DO NOT change without updating the cost constants below in sync.
TEXT_SEARCH_FIELD_MASK = "places.id,places.displayName.text"
PLACE_DETAILS_FIELD_MASK = "id,websiteUri,formattedAddress,displayName.text"

# Per-call costs in USD, indexed by SKU. Sourced from Google's pricing
# documentation as of 2026-04. If Google updates pricing, these constants
# need to update — and the test_cost_calculator regression test will catch
# any silent change.
COST_PER_TEXT_SEARCH = 0.005   # Essentials SKU, narrow field mask
COST_PER_PLACE_DETAILS = 0.025  # Enterprise SKU (websiteUri lives here)

# Maximum candidates we'll verify in an ambiguous Text Search response.
# 3 keeps the worst-case lookup at $0.005 + 3*$0.025 = $0.080 — see
# Decision 3 in the cost-design doc.
MAX_VERIFY_CANDIDATES = 3

# Politeness rate limit. Google's Places API is robust to ~50 req/s but
# being conservative is free and avoids any throttle escalation.
DEFAULT_MIN_INTERVAL = 0.1  # 10 req/s


class BudgetExceeded(Exception):
    """Raised by CostMeter when a planned call would exceed the budget."""


@dataclass
class CostMeter:
    """Track running USD spend; refuse calls that would breach the budget.

    Defensive: cost is booked BEFORE the call is made. If the HTTP call
    crashes mid-flight, the cost is still recorded (we may have been billed
    even if we didn't see the response). False positives (charged less than
    we recorded) are safer than false negatives (charged more than we
    recorded).
    """

    budget_usd: float
    running_usd: float = 0.0
    text_search_calls: int = 0
    details_calls: int = 0

    def check_budget(self, planned_cost: float) -> None:
        """Raise BudgetExceeded if running + planned > budget."""
        if self.running_usd + planned_cost > self.budget_usd:
            raise BudgetExceeded(
                f"Budget {self.budget_usd:.2f} would be exceeded by "
                f"running {self.running_usd:.4f} + planned {planned_cost:.4f}"
            )

    def book_text_search(self) -> None:
        self.check_budget(COST_PER_TEXT_SEARCH)
        self.running_usd += COST_PER_TEXT_SEARCH
        self.text_search_calls += 1

    def book_details(self) -> None:
        self.check_budget(COST_PER_PLACE_DETAILS)
        self.running_usd += COST_PER_PLACE_DETAILS
        self.details_calls += 1


@dataclass
class PlacesLookupResult:
    """Outcome of one full Tier 3 lookup. None values mean "tried, no match"."""

    place_id: str | None
    website: str | None
    formatted_address: str | None
    matched_via: str = ""  # "single_result" | "ambiguous_verified" | "ambiguous_no_verify" | "no_result" | "cache" | "error"
    candidates_seen: int = 0


@dataclass
class _PlaceCandidate:
    """Internal: one candidate from a Text Search response."""

    place_id: str
    display_name: str


class PlacesClient:
    """Google Places API client with cost tracking and rate limiting.

    Designed for a single-process, single-thread loop. Concurrency would
    require careful synchronisation of CostMeter — explicitly out of scope.
    """

    def __init__(
        self,
        api_key: str,
        cost_meter: CostMeter,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        timeout: int = 15,
        cache: dict[str, dict] | None = None,
    ):
        if not api_key:
            raise ValueError("Places API key is required")
        self._api_key = api_key
        self.cost_meter = cost_meter
        self.min_interval = min_interval
        self.timeout = timeout
        self._cache: dict[str, dict] = dict(cache) if cache else {}
        self._last_call_at = 0.0
        self._session = requests.Session()

    @staticmethod
    def cache_key(hospital_name: str, state: str, city: str | None = None) -> str:
        """Same shape as NppesClient.cache_key for consistency."""
        return f"{hospital_name}|{state}|{city or ''}".upper()

    def cache_snapshot(self) -> dict[str, dict]:
        return dict(self._cache)

    def lookup(
        self,
        hospital_name: str,
        state: str,
        city: str | None = None,
    ) -> PlacesLookupResult:
        """Resolve a hospital to a website via Places API.

        Sequence:
          1. Cache check (free)
          2. Text Search — Essentials SKU
          3. If 0 results: cache no-result, return
          4. If 1 result: Place Details, cache, return
          5. If 2-3 results: Place Details for each, verify by name in page,
             cache the winner

        Raises BudgetExceeded if any planned call would exceed the budget.
        Network errors are caught and returned as a `matched_via='error'`
        result (cached so a re-run skips the failure unless the cache is wiped).
        """
        if not hospital_name or not state:
            return PlacesLookupResult(None, None, None, "invalid_input")

        key = self.cache_key(hospital_name, state, city)
        if key in self._cache:
            cached = self._cache[key]
            return PlacesLookupResult(
                place_id=cached.get("place_id"),
                website=cached.get("website"),
                formatted_address=cached.get("formatted_address"),
                matched_via="cache",
                candidates_seen=cached.get("candidates_seen", 0),
            )

        # Step 2: Text Search
        candidates = self._text_search(hospital_name, state, city)
        if not candidates:
            self._cache_result(key, None, None, None, "no_result", 0)
            return PlacesLookupResult(None, None, None, "no_result", 0)

        # Step 4: single result
        if len(candidates) == 1:
            details = self._place_details(candidates[0].place_id)
            result = PlacesLookupResult(
                place_id=candidates[0].place_id,
                website=details.get("websiteUri"),
                formatted_address=details.get("formattedAddress"),
                matched_via="single_result",
                candidates_seen=1,
            )
            self._cache_result(key, result.place_id, result.website,
                               result.formatted_address, result.matched_via, 1)
            return result

        # Step 5: 2-3 results — fetch details for each, then verify
        verify_pool = candidates[:MAX_VERIFY_CANDIDATES]
        verified = []
        for cand in verify_pool:
            details = self._place_details(cand.place_id)
            url = details.get("websiteUri")
            if url and self._verify_name_in_page(url, hospital_name):
                verified.append({
                    "place_id": cand.place_id,
                    "website": url,
                    "formatted_address": details.get("formattedAddress"),
                })

        if not verified:
            # No candidate's website mentioned the hospital — log for review
            self._cache_result(key, None, None, None, "ambiguous_no_verify",
                               len(verify_pool))
            return PlacesLookupResult(
                None, None, None, "ambiguous_no_verify", len(verify_pool),
            )

        # Tie-break: prefer the one whose formatted_address city matches our city
        winner = self._pick_by_city(verified, city) if city else verified[0]
        self._cache_result(
            key, winner["place_id"], winner["website"],
            winner["formatted_address"], "ambiguous_verified", len(verify_pool),
        )
        return PlacesLookupResult(
            place_id=winner["place_id"],
            website=winner["website"],
            formatted_address=winner["formatted_address"],
            matched_via="ambiguous_verified",
            candidates_seen=len(verify_pool),
        )

    def _text_search(
        self, hospital_name: str, state: str, city: str | None,
    ) -> list[_PlaceCandidate]:
        """One Text Search call. Books cost via cost_meter when the request
        reached Google's servers (so Google may have billed us).

        H4 fix (2026-05-04): pre-fix, the cost meter was incremented BEFORE
        the HTTP request — every ConnectionError, DNS fail, or TLS handshake
        failure inflated Sandra's recorded budget without Google having
        charged anything. Per
        https://developers.google.com/maps/documentation/places/web-service/usage-and-billing
        Google only bills requests that reach their LB; connection-level
        failures are never billed. Book the cost AFTER we've established
        contact, refund pre-flight failures.
        """
        self._rate_limit()

        # Construct a focused query. Adding "hospital" as a term improves
        # taxonomy match (Google's index biases hospital results higher).
        query_parts = [hospital_name, "hospital"]
        if city:
            query_parts.append(city)
        query_parts.append(state)
        text_query = " ".join(query_parts)

        body = {"textQuery": text_query, "maxResultCount": MAX_VERIFY_CANDIDATES}
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": TEXT_SEARCH_FIELD_MASK,
        }

        try:
            resp = self._session.post(
                PLACES_TEXT_SEARCH_URL, json=body, headers=headers,
                timeout=self.timeout,
            )
        except requests.ConnectionError as exc:
            # Never reached Google — no charge incurred. Don't book.
            logger.warning(
                "Places Text Search did not reach Google for %r/%r — not booking cost: %s",
                hospital_name, state, type(exc).__name__,
            )
            return []
        except requests.Timeout as exc:
            # Timeouts split into connect-timeout (no charge) and read-timeout
            # (Google may have served the request). requests doesn't expose a
            # clean way to tell them apart, so book defensively — preserve
            # spend visibility at the cost of a small over-count.
            self.cost_meter.book_text_search()
            logger.warning(
                "Places Text Search timed out for %r/%r — booking cost defensively: %s",
                hospital_name, state, type(exc).__name__,
            )
            return []

        # Got a response from Google — book the cost regardless of status.
        # 2xx and 5xx both count against quota per Google's billing docs;
        # 4xx is mixed but conservative-book is the safer default.
        self.cost_meter.book_text_search()

        try:
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            # Redacted log: we never include the full exception message
            # because it may contain header values (which include the API
            # key when there's a header validation error). Log only the
            # exception type and the input identifier.
            logger.warning(
                "Places Text Search failed for %r/%r: %s",
                hospital_name, state, type(exc).__name__,
            )
            return []

        places = data.get("places", []) or []
        candidates = []
        for p in places:
            place_id = p.get("id")
            display = (p.get("displayName") or {}).get("text", "")
            if place_id:
                candidates.append(_PlaceCandidate(place_id=place_id, display_name=display))
        return candidates

    def _place_details(self, place_id: str) -> dict:
        """One Place Details call. Books cost via cost_meter when Google
        actually received the request (see _text_search docstring for H4)."""
        self._rate_limit()

        url = PLACES_DETAILS_URL_TEMPLATE.format(place_id=place_id)
        headers = {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": PLACE_DETAILS_FIELD_MASK,
        }
        try:
            resp = self._session.get(url, headers=headers, timeout=self.timeout)
        except requests.ConnectionError as exc:
            logger.warning(
                "Places Details did not reach Google for place_id=%s — not booking cost: %s",
                place_id, type(exc).__name__,
            )
            return {}
        except requests.Timeout as exc:
            self.cost_meter.book_details()
            logger.warning(
                "Places Details timed out for place_id=%s — booking cost defensively: %s",
                place_id, type(exc).__name__,
            )
            return {}

        self.cost_meter.book_details()

        try:
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            # Same redaction as text search — log type only, not full exception.
            logger.warning(
                "Places Details failed for place_id=%s: %s",
                place_id, type(exc).__name__,
            )
            return {}

    @staticmethod
    def _verify_name_in_page(url: str, hospital_name: str) -> bool:
        """Free homepage GET; check for hospital name keywords in body.

        Reuses the same logic shape as Stage 3 Tier 2's verify_hospital_in_page
        but inlined here to avoid cross-module dependency.
        """
        keywords = _hospital_name_keywords(hospital_name)
        if not keywords:
            return False
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ClaroBill-Verify)"},
                timeout=10, stream=True, allow_redirects=True,
            )
            if resp.status_code >= 400:
                resp.close()
                return False
            body = resp.raw.read(65536, decode_content=True)
            resp.close()
        except Exception:
            # Broad except is correct here. Verification can only ever fail
            # silently — there's no recovery, and a crash here would kill
            # the worker and cascade-fail the entire Tier 3 run.
            #
            # Sandra's 2026-04-28 incident: a hospital server sent malformed
            # HTTP headers ("Content-Security-Policy : base-uri" with space
            # before colon). urllib3 raised HeaderParsingError which is NOT
            # a subclass of requests.RequestException, bypassing the
            # specific exception clauses we had before. One bad server's
            # response shouldn't terminate a 50-minute production run.
            return False

        body_upper = body.decode("utf-8", errors="replace").upper()
        return any(kw in body_upper for kw in keywords)

    @staticmethod
    def _pick_by_city(
        verified: list[dict], target_city: str,
    ) -> dict:
        """Tie-break verified candidates by formatted_address city match."""
        target_upper = target_city.upper()
        for v in verified:
            addr = (v.get("formatted_address") or "").upper()
            if target_upper in addr:
                return v
        # No city match — fall back to the first verified
        return verified[0]

    def _rate_limit(self) -> None:
        now = time.monotonic()
        wait = self.min_interval - (now - self._last_call_at)
        if wait > 0:
            time.sleep(wait)
        self._last_call_at = time.monotonic()

    def _cache_result(
        self,
        key: str,
        place_id: str | None,
        website: str | None,
        formatted_address: str | None,
        matched_via: str,
        candidates_seen: int,
    ) -> None:
        self._cache[key] = {
            "place_id": place_id,
            "website": website,
            "formatted_address": formatted_address,
            "matched_via": matched_via,
            "candidates_seen": candidates_seen,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


# --- Helpers for pre-call validation and verification ---

# Names too short or too generic to lookup safely. These produce noise, not matches.
_GENERIC_LOWER = frozenset({
    "hospital", "medical center", "health center", "health system",
    "healthcare", "clinic",
})

_KEYWORD_GENERICS = frozenset({
    "HOSPITAL", "MEDICAL", "CENTER", "CENTRE",
    "HEALTH", "HEALTHCARE", "SYSTEM", "SYSTEMS",
    "MEMORIAL", "REGIONAL", "GENERAL", "COMMUNITY",
    "AT", "OF", "THE", "AND", "INC", "LLC", "LLP",
})

_NAME_MIN_LEN = 5


def is_lookupable(hospital_name: str | None, state: str | None, city: str | None) -> bool:
    """Pre-call validator. Returns False if a Places lookup would be wasteful.

    Decision rules (per cost-design doc Layer 5):
      - state IS NULL → reject (API requires state)
      - city IS NULL → reject (we lose disambiguator)
      - name length < 5 → reject (too generic)
      - name is itself a generic phrase (e.g. "Hospital") → reject
    """
    if not state or not city or not hospital_name:
        return False
    name = hospital_name.strip()
    if len(name) < _NAME_MIN_LEN:
        return False
    if name.lower() in _GENERIC_LOWER:
        return False
    return True


def _hospital_name_keywords(name: str, min_word_len: int = 5) -> list[str]:
    """Extract distinctive keywords for verification. Same shape as Tier 2."""
    words = re.split(r"\s+", name.upper())
    return [w for w in words if len(w) >= min_word_len and w not in _KEYWORD_GENERICS]
