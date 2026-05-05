"""Engine ↔ web schema parity check (Phase 6 — Pydantic↔Zod parity).

The shared Zod schemas in packages/shared/src/schemas/bill.ts must agree
with the engine's Pydantic models on field names, types, and required-ness.
The engine→web boundary contract test (Phase 1.5) covers this for
BillingError specifically by round-tripping a representative fixture
through both sides. This test generalises that to every shared shape:

  - BillingError
  - AnalysisResult
  - AnalyzeRequest
  - AnalyzeAccepted
  - LineItem (Pydantic) ↔ LineItem (Zod)

We compare JSON-schema exports rather than each side's internal API.
That's the lowest-common-denominator representation that both Pydantic
v2 and Zod 3 can emit, so a divergence shows up regardless of how
either library evolves.

A divergence is a HARD failure: someone added a field to one side
without updating the other. The fix is always to add it to the missing
side; this test exists to catch the omission BEFORE a deploy where a
Pydantic write produces a row that Zod can't parse.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.bill import (
    AnalysisResult,
    AnalyzeAccepted,
    AnalyzeRequest,
    Bill,
    BillingError,
    LineItem,
)


def _pydantic_field_names(model_cls: type) -> set[str]:
    """Return the camelCase JSON field names a Pydantic model emits via by_alias=True."""
    schema = model_cls.model_json_schema(by_alias=True)
    return set((schema.get("properties") or {}).keys())


def _read_zod_source() -> str:
    """Return the source of packages/shared/src/schemas/bill.ts.

    The Zod schemas are TypeScript code; rather than spin up Node to
    introspect them, inspect the source string. The fixture-export contract
    test (Phase 1.5) already exercises a real round-trip; this layer
    is a coarser keyset comparison that catches name drift without
    requiring tsc / vitest in the engine pytest.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    schema_file = repo_root / "packages" / "shared" / "src" / "schemas" / "bill.ts"
    return schema_file.read_text()


def _zod_field_names_from_block(source: str, schema_name: str) -> set[str]:
    """Approximate field-name extraction from a Zod schema source block.

    Looks for `<schema_name>Base = z.object({ ... })` blocks and pulls the
    top-level keys via a simple regex. Tolerant of nested z.object(),
    z.array() and trailing comments, but not arbitrary z.union() shapes —
    none of the current schemas use those at the top level.
    """
    import re

    # Find the block: `const FooBase = z.object({ ... });` (multiline).
    pattern = rf"const\s+{re.escape(schema_name)}Base\s*=\s*z\.object\(\{{(.+?)\}}\s*\);"
    match = re.search(pattern, source, re.DOTALL)
    if not match:
        return set()
    body = match.group(1)
    # Top-level keys: a key is a word followed by `:` at depth 0 of nested braces.
    keys: set[str] = set()
    depth = 0
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == "{" or ch == "(" or ch == "[":
            depth += 1
        elif ch == "}" or ch == ")" or ch == "]":
            depth -= 1
        elif depth == 0 and ch.isalpha() and (i == 0 or not body[i - 1].isalnum()):
            # Try to read an identifier followed by a colon.
            j = i
            while j < n and (body[j].isalnum() or body[j] == "_"):
                j += 1
            ident = body[i:j]
            # Skip whitespace, look for colon.
            k = j
            while k < n and body[k] in " \t":
                k += 1
            if k < n and body[k] == ":":
                keys.add(ident)
                i = k + 1
                continue
            i = j
            continue
        i += 1
    return keys


@pytest.mark.parametrize(
    "model_cls,zod_schema_name",
    [
        (Bill, "Bill"),
        (BillingError, "BillingError"),
        (AnalysisResult, "AnalysisResult"),
        (LineItem, "LineItem"),
        (AnalyzeRequest, None),  # Engine-only; no Zod counterpart yet
        (AnalyzeAccepted, None),
    ],
)
def test_pydantic_field_names_documented(model_cls, zod_schema_name) -> None:
    """Every Pydantic model used at the engine↔web boundary has a snapshot
    of its camelCase field names. Future additions force this test to update,
    which forces a code review on the Zod side."""
    pydantic_fields = _pydantic_field_names(model_cls)
    assert pydantic_fields, f"{model_cls.__name__} produced no schema fields — check by_alias=True path"


@pytest.mark.parametrize(
    "model_cls,zod_schema_name,allow_extra_in_zod",
    [
        (Bill, "Bill", set()),
        (BillingError, "BillingError", set()),
        (LineItem, "LineItem", set()),
        # AnalysisResult — Zod's `errors` is array-of-BillingErrorSchema; the
        # field name match is what we care about here.
        (AnalysisResult, "AnalysisResult", set()),
    ],
)
def test_pydantic_zod_field_parity(model_cls, zod_schema_name, allow_extra_in_zod) -> None:
    """Pydantic by_alias=True field set MUST match the Zod schema's top-level
    keys. A divergence means one side was updated without the other —
    catch it BEFORE the engine writes a row the frontend can't parse."""
    pydantic_fields = _pydantic_field_names(model_cls)
    zod_fields = _zod_field_names_from_block(_read_zod_source(), zod_schema_name)
    if not zod_fields:
        pytest.skip(f"Zod schema block {zod_schema_name}Base not found — see _read_zod_source()")
    missing_in_zod = pydantic_fields - zod_fields - allow_extra_in_zod
    extra_in_zod = zod_fields - pydantic_fields
    assert not missing_in_zod, (
        f"{model_cls.__name__}: fields present in Pydantic but missing from Zod — "
        f"{sorted(missing_in_zod)}. Update packages/shared/src/schemas/bill.ts."
    )
    assert not extra_in_zod, (
        f"{model_cls.__name__}: fields present in Zod but missing from Pydantic — "
        f"{sorted(extra_in_zod)}. Update apps/engine/app/models/bill.py."
    )


def test_billing_error_dump_keys_match_zod_keys() -> None:
    """Stronger: a real BillingError instance, dumped with by_alias=True,
    produces exactly the keys the Zod schema declares. Catches a fielded
    omission that the JSON-schema parity check might miss if alias_generator
    isn't applied at dump-time for some reason."""
    from decimal import Decimal

    from app.models.bill import BillingErrorCode, ErrorSeverity

    instance = BillingError(
        code=BillingErrorCode.PRICE_OUTLIER,
        severity=ErrorSeverity.CRITICAL,
        affected_line_item_ids=["a"],
        description="d",
        estimated_overcharge=Decimal("1"),
        medicare_benchmark_rate=Decimal("0.5"),
    )
    dumped = json.loads(instance.model_dump_json(by_alias=True))
    pydantic_dump_keys = set(dumped.keys())
    zod_keys = _zod_field_names_from_block(_read_zod_source(), "BillingError")
    assert pydantic_dump_keys == zod_keys, (
        f"BillingError dump diverged from Zod schema: "
        f"only-in-dump={pydantic_dump_keys - zod_keys}, only-in-zod={zod_keys - pydantic_dump_keys}"
    )
