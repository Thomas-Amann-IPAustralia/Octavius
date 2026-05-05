"""Tests for the OCTAVIUS_DISPATCHER env-flag resolution in routes/check.py."""

from __future__ import annotations

import logging

import logic.dispatcher as legacy_dispatcher
from routes.check import _resolve_dispatcher


def test_default_resolves_to_legacy():
    assert _resolve_dispatcher(None) is legacy_dispatcher


def test_legacy_explicit_resolves_to_legacy():
    assert _resolve_dispatcher("legacy") is legacy_dispatcher


def test_legacy_is_case_insensitive_and_trim():
    assert _resolve_dispatcher("  LEGACY  ") is legacy_dispatcher


def test_indexed_falls_back_to_legacy_with_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="routes.check"):
        resolved = _resolve_dispatcher("indexed")
    assert resolved is legacy_dispatcher
    assert any(
        "indexed" in rec.message.lower() and "phase 0" in rec.message.lower()
        for rec in caplog.records
    )


def test_unknown_value_warns_and_falls_back(caplog):
    with caplog.at_level(logging.WARNING, logger="routes.check"):
        resolved = _resolve_dispatcher("nonsense")
    assert resolved is legacy_dispatcher
    assert any("not recognised" in rec.message for rec in caplog.records)
