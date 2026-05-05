"""Conftest for api tests — stubs runtime dependencies at import time.

Two dependencies fail without Cloud Run infrastructure:
  1. google-cloud-bigquery / google-cloud-vision: not installed in the test venv.
     Inject MagicMock stubs for these specific submodules before collection begins.
  2. pydantic Settings: requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY env vars.
     Set dummy values before any test module is imported.

IMPORTANT: We intentionally do NOT replace the `google` namespace package or
`google.auth` — google-auth IS installed and must remain intact for other
imports (e.g. google.oauth2.service_account used in ocr.py).
"""

import importlib
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

# ── 1. Env vars ───────────────────────────────────────────────────────────────
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("SENDGRID_API_KEY", "SG.test")
os.environ.setdefault("SENDGRID_FROM_EMAIL", "test@clarobill.com")

# ── 2. Google namespace stubs ─────────────────────────────────────────────────
# Force the real google namespace package and google-auth to load first so that
# `from google.oauth2 import service_account` (in ocr.py) continues to work.
importlib.import_module("google")
importlib.import_module("google.auth")
importlib.import_module("google.oauth2")
importlib.import_module("google.oauth2.service_account")

# Now add the missing google.cloud.* submodules that are not installed in the venv.
if "google.cloud" not in sys.modules:
    _gcloud_mod = ModuleType("google.cloud")
    sys.modules["google.cloud"] = _gcloud_mod
    # Attach as attribute to the google package so `from google.cloud import X` works
    sys.modules["google"].cloud = _gcloud_mod  # type: ignore[attr-defined]

_MISSING_CLOUD_PKGS = (
    "google.cloud.bigquery",
    "google.cloud.vision",
    "google.cloud.vision_v1",
    "google.cloud.vision_v1.types",
)
for _pkg in _MISSING_CLOUD_PKGS:
    if _pkg not in sys.modules:
        _stub = MagicMock()
        sys.modules[_pkg] = _stub

# Attach cloud submodule stubs as attributes on google.cloud
_gcloud = sys.modules["google.cloud"]
for _attr in ("bigquery", "vision", "vision_v1"):
    if not hasattr(_gcloud, _attr):
        setattr(_gcloud, _attr, sys.modules.get(f"google.cloud.{_attr}", MagicMock()))

# ── 3. Optional runtime-only packages ─────────────────────────────────────────
# fpdf2 and python-docx are not installed in the test venv. slowapi IS
# installed and must remain real — see tests/api/conftest.py for rationale.
for _opt_pkg in ("fpdf", "docx", "docx.shared"):
    if _opt_pkg not in sys.modules:
        try:
            importlib.import_module(_opt_pkg)
        except ImportError:
            sys.modules[_opt_pkg] = MagicMock()
