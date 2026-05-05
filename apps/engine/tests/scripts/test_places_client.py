"""Unit tests for PlacesClient — Tier 3 cost-control logic.

Every test runs without a real API key and without making any network calls.
The HTTP layer is mocked so we can assert exactly what the client would do
in each scenario without spending a cent.

These tests must all pass before any real Places API call is made.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mrf_discovery.places_client import (  # noqa: E402
    BudgetExceeded,
    COST_PER_PLACE_DETAILS,
    COST_PER_TEXT_SEARCH,
    CostMeter,
    MAX_VERIFY_CANDIDATES,
    PLACE_DETAILS_FIELD_MASK,
    PlacesClient,
    PlacesLookupResult,
    TEXT_SEARCH_FIELD_MASK,
    is_lookupable,
)


class TestCostConstants:
    def test_text_search_cost(self):
        # Regression guard if Google updates pricing or someone "tidies" the constant.
        # Sourced from Places "New" pricing 2026-04: Essentials SKU = $5/1000 calls.
        assert COST_PER_TEXT_SEARCH == 0.005

    def test_details_cost(self):
        # Enterprise SKU (websiteUri) = $25/1000 calls.
        assert COST_PER_PLACE_DETAILS == 0.025

    def test_text_search_field_mask_is_essentials(self):
        # Narrow mask = Essentials SKU pricing. If anyone widens this, cost
        # silently 6.4× — this test fails before the Google bill arrives.
        assert TEXT_SEARCH_FIELD_MASK == "places.id,places.displayName.text"

    def test_place_details_field_mask_includes_website(self):
        # The whole point of Details calls is to get websiteUri.
        assert "websiteUri" in PLACE_DETAILS_FIELD_MASK

    def test_max_verify_candidates_capped_at_3(self):
        # Decision 3 in cost-design doc: ambiguous lookups cost 1 search +
        # 3 details = $0.080 max. If anyone increases this, ambiguous-lookup
        # cost grows linearly.
        assert MAX_VERIFY_CANDIDATES == 3


class TestCostMeter:
    def test_book_text_search_increments_running(self):
        m = CostMeter(budget_usd=10.0)
        m.book_text_search()
        assert m.running_usd == COST_PER_TEXT_SEARCH
        assert m.text_search_calls == 1
        assert m.details_calls == 0

    def test_book_details_increments_running(self):
        m = CostMeter(budget_usd=10.0)
        m.book_details()
        assert m.running_usd == COST_PER_PLACE_DETAILS
        assert m.details_calls == 1
        assert m.text_search_calls == 0

    def test_check_budget_raises_when_exceeded(self):
        m = CostMeter(budget_usd=0.01)
        with pytest.raises(BudgetExceeded):
            m.check_budget(0.025)

    def test_book_text_search_raises_when_exceeded(self):
        m = CostMeter(budget_usd=0.001)  # less than one search
        with pytest.raises(BudgetExceeded):
            m.book_text_search()
        # Critically: the call MUST NOT have incremented the meter.
        # (Defensive book-before-call assumes we'd be charged; refuse-before-book
        # assumes we wouldn't. We refuse here.)
        assert m.running_usd == 0.0

    def test_book_details_raises_when_exceeded(self):
        m = CostMeter(budget_usd=0.001)
        with pytest.raises(BudgetExceeded):
            m.book_details()
        assert m.running_usd == 0.0

    def test_zero_budget_blocks_everything(self):
        m = CostMeter(budget_usd=0.0)
        with pytest.raises(BudgetExceeded):
            m.book_text_search()

    def test_exact_budget_allows_exactly_one_call(self):
        m = CostMeter(budget_usd=COST_PER_TEXT_SEARCH)
        m.book_text_search()
        assert m.running_usd == COST_PER_TEXT_SEARCH
        # Second call should fail
        with pytest.raises(BudgetExceeded):
            m.book_text_search()


class TestIsLookupable:
    def test_full_input_is_lookupable(self):
        assert is_lookupable("Mayo Clinic", "MN", "Rochester") is True

    def test_short_name_rejected(self):
        assert is_lookupable("VA", "TX", "Dallas") is False

    def test_missing_state_rejected(self):
        assert is_lookupable("Mayo Clinic", None, "Rochester") is False
        assert is_lookupable("Mayo Clinic", "", "Rochester") is False

    def test_missing_city_rejected(self):
        assert is_lookupable("Mayo Clinic", "MN", None) is False
        assert is_lookupable("Mayo Clinic", "MN", "") is False

    def test_missing_name_rejected(self):
        assert is_lookupable(None, "MN", "Rochester") is False
        assert is_lookupable("", "MN", "Rochester") is False

    def test_generic_name_rejected(self):
        assert is_lookupable("Hospital", "MN", "Rochester") is False
        assert is_lookupable("Medical Center", "MN", "Rochester") is False


class TestPlacesClientCacheKey:
    def test_uppercase_normalisation(self):
        assert PlacesClient.cache_key("Mayo Clinic", "MN", "Rochester") == "MAYO CLINIC|MN|ROCHESTER"
        assert PlacesClient.cache_key("mayo clinic", "mn", "rochester") == "MAYO CLINIC|MN|ROCHESTER"

    def test_missing_city_handled(self):
        assert PlacesClient.cache_key("Mayo Clinic", "MN") == "MAYO CLINIC|MN|"


class TestPlacesClientInit:
    def test_requires_api_key(self):
        m = CostMeter(budget_usd=10.0)
        with pytest.raises(ValueError):
            PlacesClient(api_key="", cost_meter=m)
        with pytest.raises(ValueError):
            PlacesClient(api_key=None, cost_meter=m)


class TestPlacesClientLookupCacheHit:
    def test_cache_hit_no_api_call_no_cost(self):
        m = CostMeter(budget_usd=10.0)
        seed = {
            "MAYO CLINIC|MN|ROCHESTER": {
                "place_id": "ChIJabc",
                "website": "https://mayoclinic.org",
                "formatted_address": "200 1st St SW, Rochester, MN",
                "matched_via": "single_result",
                "candidates_seen": 1,
                "checked_at": "2026-04-28T00:00:00Z",
            }
        }
        c = PlacesClient(api_key="fake", cost_meter=m, cache=seed, min_interval=0)
        result = c.lookup("Mayo Clinic", "MN", "Rochester")
        assert result.matched_via == "cache"
        assert result.website == "https://mayoclinic.org"
        # Critical: zero cost incurred for cache hits
        assert m.running_usd == 0.0
        assert m.text_search_calls == 0
        assert m.details_calls == 0


class TestPlacesClientInvalidInput:
    def test_invalid_input_no_api_call(self):
        m = CostMeter(budget_usd=10.0)
        c = PlacesClient(api_key="fake", cost_meter=m, min_interval=0)
        result = c.lookup("", "MN", "Rochester")
        assert result.matched_via == "invalid_input"
        assert m.running_usd == 0.0


class TestPlacesClientSearchHappy:
    def _mock_search(self, places):
        """Build a mock JSON body for Text Search with N place dicts."""
        return {"places": [{"id": p["id"], "displayName": {"text": p["name"]}} for p in places]}

    def test_single_result_calls_search_then_one_details(self):
        m = CostMeter(budget_usd=10.0)
        c = PlacesClient(api_key="fake", cost_meter=m, min_interval=0)

        with patch.object(c._session, "post") as mock_post, \
             patch.object(c._session, "get") as mock_get:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = self._mock_search([
                {"id": "ChIJabc", "name": "Mayo Clinic"},
            ])
            mock_post.return_value.raise_for_status = MagicMock()

            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "id": "ChIJabc",
                "websiteUri": "https://mayoclinic.org",
                "formattedAddress": "200 1st St SW, Rochester, MN, USA",
            }
            mock_get.return_value.raise_for_status = MagicMock()

            result = c.lookup("Mayo Clinic", "MN", "Rochester")

        assert result.matched_via == "single_result"
        assert result.website == "https://mayoclinic.org"
        assert m.text_search_calls == 1
        assert m.details_calls == 1
        assert m.running_usd == COST_PER_TEXT_SEARCH + COST_PER_PLACE_DETAILS

    def test_zero_results_no_details_call(self):
        m = CostMeter(budget_usd=10.0)
        c = PlacesClient(api_key="fake", cost_meter=m, min_interval=0)

        with patch.object(c._session, "post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"places": []}
            mock_post.return_value.raise_for_status = MagicMock()

            result = c.lookup("Mayo Clinic", "MN", "Rochester")

        assert result.matched_via == "no_result"
        assert result.website is None
        assert m.text_search_calls == 1
        assert m.details_calls == 0  # no details call wasted
        assert m.running_usd == COST_PER_TEXT_SEARCH


class TestPlacesClientBudgetEnforcement:
    def test_search_blocked_by_budget(self):
        m = CostMeter(budget_usd=0.001)  # less than one search
        c = PlacesClient(api_key="fake", cost_meter=m, min_interval=0)
        with pytest.raises(BudgetExceeded):
            c.lookup("Mayo Clinic", "MN", "Rochester")
        assert m.running_usd == 0.0

    def test_details_blocked_after_search(self):
        # Budget allows search but not details
        m = CostMeter(budget_usd=COST_PER_TEXT_SEARCH + 0.001)
        c = PlacesClient(api_key="fake", cost_meter=m, min_interval=0)

        with patch.object(c._session, "post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "places": [{"id": "ChIJabc", "displayName": {"text": "Mayo"}}],
            }
            mock_post.return_value.raise_for_status = MagicMock()

            with pytest.raises(BudgetExceeded):
                c.lookup("Mayo Clinic", "MN", "Rochester")

        # Search was charged; details was refused.
        assert m.text_search_calls == 1
        assert m.details_calls == 0
        assert m.running_usd == COST_PER_TEXT_SEARCH


class TestCostBookingOnNetworkErrors:
    """H4 fix (2026-05-04): the cost meter must NOT increment on
    connection-level failures (DNS / TLS / connect-refused) because the
    request never reached Google's LB and is therefore never billed by
    Google. Pre-fix, the meter was incremented BEFORE every HTTP request,
    overcounting Sandra's recorded budget by the network-error rate.

    Per https://developers.google.com/maps/documentation/places/web-service/usage-and-billing
    only requests Google actually receives (2xx + 5xx) count against quota.
    Authentication failures and connection-level errors are not billed."""

    def test_text_search_connection_error_does_not_book(self):
        """ConnectionError = never reached Google = no charge."""
        import requests as _requests

        m = CostMeter(budget_usd=10.0)
        c = PlacesClient(api_key="fake", cost_meter=m, min_interval=0)

        with patch.object(
            c._session, "post",
            side_effect=_requests.ConnectionError("dns failed"),
        ):
            candidates = c._text_search("Mayo Clinic", "MN", "Rochester")

        assert candidates == []
        assert m.text_search_calls == 0
        assert m.running_usd == 0.0

    def test_text_search_timeout_books_defensively(self):
        """Timeout could be connect-timeout (no charge) or read-timeout
        (Google may have served the request). Conservative: book."""
        import requests as _requests

        m = CostMeter(budget_usd=10.0)
        c = PlacesClient(api_key="fake", cost_meter=m, min_interval=0)

        with patch.object(c._session, "post", side_effect=_requests.Timeout("read timeout")):
            candidates = c._text_search("Mayo Clinic", "MN", "Rochester")

        assert candidates == []
        assert m.text_search_calls == 1  # booked defensively
        assert m.running_usd == COST_PER_TEXT_SEARCH

    def test_text_search_4xx_response_still_books(self):
        """A 4xx response means Google received the request — book the cost
        even though we treat it as a no-result. Conservative re Google's
        billing docs (4xx is mixed; some count, some don't)."""
        m = CostMeter(budget_usd=10.0)
        c = PlacesClient(api_key="fake", cost_meter=m, min_interval=0)

        import requests as _requests

        resp = MagicMock()
        resp.status_code = 400
        resp.raise_for_status.side_effect = _requests.HTTPError("bad request")
        with patch.object(c._session, "post", return_value=resp):
            candidates = c._text_search("Mayo Clinic", "MN", "Rochester")

        assert candidates == []
        assert m.text_search_calls == 1
        assert m.running_usd == COST_PER_TEXT_SEARCH

    def test_place_details_connection_error_does_not_book(self):
        import requests as _requests

        m = CostMeter(budget_usd=10.0)
        c = PlacesClient(api_key="fake", cost_meter=m, min_interval=0)

        with patch.object(
            c._session, "get",
            side_effect=_requests.ConnectionError("dns failed"),
        ):
            details = c._place_details("ChIJabc")

        assert details == {}
        assert m.details_calls == 0
        assert m.running_usd == 0.0

    def test_place_details_timeout_books_defensively(self):
        import requests as _requests

        m = CostMeter(budget_usd=10.0)
        c = PlacesClient(api_key="fake", cost_meter=m, min_interval=0)

        with patch.object(c._session, "get", side_effect=_requests.Timeout("read timeout")):
            details = c._place_details("ChIJabc")

        assert details == {}
        assert m.details_calls == 1
        assert m.running_usd == COST_PER_PLACE_DETAILS


class TestCacheHitWritesCorrectly:
    def test_no_result_caches(self):
        m = CostMeter(budget_usd=10.0)
        c = PlacesClient(api_key="fake", cost_meter=m, min_interval=0)
        with patch.object(c._session, "post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"places": []}
            mock_post.return_value.raise_for_status = MagicMock()
            c.lookup("Mayo Clinic", "MN", "Rochester")

        # Second call hits cache, no new API calls
        with patch.object(c._session, "post") as mock_post2:
            result = c.lookup("Mayo Clinic", "MN", "Rochester")
            assert mock_post2.called is False
        assert result.matched_via == "cache"
        # Total cost: only the original search
        assert m.text_search_calls == 1
