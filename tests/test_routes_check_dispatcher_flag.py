"""Tests for the OCTAVIUS_DISPATCHER env-flag resolution in routes/check.py."""

from __future__ import annotations

import logging

import logic.dispatcher as legacy_dispatcher
import logic.indexed_dispatcher as indexed_dispatcher
from routes.check import _resolve_dispatcher


def test_default_resolves_to_legacy():
    assert _resolve_dispatcher(None) is legacy_dispatcher


def test_legacy_explicit_resolves_to_legacy():
    assert _resolve_dispatcher("legacy") is legacy_dispatcher


def test_legacy_is_case_insensitive_and_trim():
    assert _resolve_dispatcher("  LEGACY  ") is legacy_dispatcher


def test_indexed_resolves_to_indexed_dispatcher():
    resolved = _resolve_dispatcher("indexed")
    assert resolved is indexed_dispatcher


def test_indexed_is_case_insensitive():
    assert _resolve_dispatcher("  INDEXED  ") is indexed_dispatcher


def test_unknown_value_warns_and_falls_back(caplog):
    with caplog.at_level(logging.WARNING, logger="routes.check"):
        resolved = _resolve_dispatcher("nonsense")
    assert resolved is legacy_dispatcher
    assert any("not recognised" in rec.message for rec in caplog.records)


def test_indexed_has_run_rules():
    """Confirm the indexed dispatcher module exposes run_rules()."""
    resolved = _resolve_dispatcher("indexed")
    assert callable(getattr(resolved, "run_rules", None))
