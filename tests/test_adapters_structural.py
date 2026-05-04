"""Adapter tests — structural taxonomy (5 rules × test_fire + test_no_fire)."""

from __future__ import annotations

import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest

from logic.rulebook.adapters import compile_structural


def _load_sample_rows(taxonomy: str = "structural", n: int = 5) -> list[dict]:
    table = pq.read_table("published/rulebook.parquet")
    mask = pc.and_(
        pc.equal(table.column("test_result"), "pass"),
        pc.equal(table.column("taxonomy"), taxonomy),
    )
    sub = table.filter(mask)
    names = sub.schema.names
    rows: list[dict] = []
    for i in range(len(sub)):
        row = {c: sub.column(c)[i].as_py() for c in names}
        if row.get("test_fire") and row.get("test_no_fire"):
            rows.append(row)
        if len(rows) == n:
            break
    return rows


_SAMPLE_ROWS = _load_sample_rows()
_IDS = [r["rule_id"] for r in _SAMPLE_ROWS]


@pytest.mark.parametrize("row", _SAMPLE_ROWS, ids=_IDS)
def test_fire(row: dict) -> None:
    """Structural rule must produce ≥ 1 finding (possibly document-level) on test_fire examples."""
    rule = compile_structural(row)
    for text in row["test_fire"]:
        findings = rule["check"](text)
        assert len(findings) >= 1, (
            f"Rule {row['rule_id']} should fire on: {text!r}"
        )


@pytest.mark.parametrize("row", _SAMPLE_ROWS, ids=_IDS)
def test_no_fire(row: dict) -> None:
    rule = compile_structural(row)
    for text in row["test_no_fire"]:
        findings = rule["check"](text)
        assert len(findings) == 0, (
            f"Rule {row['rule_id']} should NOT fire on: {text!r}"
        )
