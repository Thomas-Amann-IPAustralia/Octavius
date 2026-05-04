"""Load and compile the published rulebook from Parquet.

Entry point: ``load_rules(parquet_path)`` → ``list[CompiledRule]``.

Loud failures
-------------
- Missing parquet  → ``FileNotFoundError``
- Unknown taxonomy  → ``ValueError``
- Bad trigger code  → ``SyntaxError`` / ``ValueError`` (propagated from adapters)
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

from logic.rulebook.adapters import compile_lookup, compile_regex, compile_structural
from logic.rulebook.types import CompiledRule

logger = logging.getLogger(__name__)

_PARQUET_PATH = Path(__file__).parent.parent.parent / "published" / "rulebook.parquet"

_ADAPTER_MAP = {
    "regex": compile_regex,
    "lookup": compile_lookup,
    "structural": compile_structural,
}


def load_rules(parquet_path: str | Path | None = None) -> list[CompiledRule]:
    """Read the parquet, filter ``test_result == 'pass'``, compile every rule.

    Parameters
    ----------
    parquet_path:
        Path to the Parquet file.  Defaults to ``published/rulebook.parquet``
        relative to the repository root.

    Returns
    -------
    list[CompiledRule]
        One entry per passing rule, in parquet row order.
    """
    path = Path(parquet_path) if parquet_path is not None else _PARQUET_PATH

    if not path.exists():
        raise FileNotFoundError(f"Rulebook parquet not found: {path}")

    table = pq.read_table(str(path))
    mask = pc.equal(table.column("test_result"), "pass")
    table = table.filter(mask)

    column_names: list[str] = table.schema.names
    n_rows = len(table)

    # Pre-extract columns as Python lists for fast row access
    columns: dict[str, list] = {
        col: table.column(col).to_pylist() for col in column_names
    }

    rules: list[CompiledRule] = []
    for i in range(n_rows):
        row = {col: columns[col][i] for col in column_names}
        taxonomy: str = row.get("taxonomy") or ""

        adapter = _ADAPTER_MAP.get(taxonomy)
        if adapter is None:
            raise ValueError(
                f"Unknown taxonomy '{taxonomy}' for rule '{row.get('rule_id')}'. "
                f"Supported: {list(_ADAPTER_MAP)}"
            )

        rules.append(adapter(row))

    counts = Counter(r["taxonomy"] for r in rules)
    logger.info(
        "Loaded %d rules: %d lookup, %d regex, %d structural",
        len(rules),
        counts.get("lookup", 0),
        counts.get("regex", 0),
        counts.get("structural", 0),
    )
    return rules
