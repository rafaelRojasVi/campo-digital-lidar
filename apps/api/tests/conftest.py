"""Shared pytest configuration for Campo Digital API tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

# This unit-test suite is itself a local development entrypoint (like
# scripts/platform_local.py and make platform-worker): APP_ENV is now
# required and must fail closed if unset or invalid (see app.main and
# app.config.Settings), so this explicitly sets it here rather than relying
# on any implicit default, exactly as those other local launchers do.
# Individual tests may still monkeypatch.setenv/delenv APP_ENV to exercise
# other values or the unset/invalid cases; monkeypatch reverts after each
# test.
os.environ.setdefault("APP_ENV", "development")
