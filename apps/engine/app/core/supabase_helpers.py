"""Narrowing helpers for Supabase response.data.

supabase-py types `APIResponse.data` as a broad union covering RPC scalars,
aggregate queries, and table rows. For our table queries it's always a
list of row dicts (for multi-row reads) or a single row dict (for `.single()`
and `.maybe_single()` reads). These helpers narrow the union at the boundary
so call sites can index rows without 200+ mypy errors per file.

The dict value type is `Any` rather than `object` because supabase-py does
not surface column types — every row field is implicitly typed by the schema,
not by the response. Tightening to per-query TypedDicts is tracked separately
(Phase 6 type-truth migration).
"""

from collections.abc import Mapping
from typing import Any


def as_rows(data: object) -> list[dict[str, Any]]:
    """Narrow `response.data` from a multi-row query to a list of row dicts.

    Returns an empty list when `data` is None (no rows returned). Raises
    TypeError if the shape is unexpected — guards against schema drift.
    """
    if data is None:
        return []
    if isinstance(data, list):
        return [as_row(item) for item in data]
    raise TypeError(f"expected list of rows from supabase, got {type(data).__name__}")


def as_row(data: object) -> dict[str, Any]:
    """Narrow a single row to a typed dict.

    Use after `.single()` / `.maybe_single()` (when guaranteed non-null) or
    when indexing into a list known to be non-empty. Raises TypeError if the
    value is not a mapping.
    """
    if isinstance(data, Mapping):
        return dict(data)
    raise TypeError(f"expected row dict from supabase, got {type(data).__name__}")


def as_optional_row(data: object) -> dict[str, Any] | None:
    """Narrow a single-row response that may be None.

    Use after `.maybe_single()` or after `if response.data:` guards.
    """
    if data is None:
        return None
    return as_row(data)
