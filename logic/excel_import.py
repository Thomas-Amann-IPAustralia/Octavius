"""Utilities for importing Octavius rule spreadsheets in the Developer interface."""

from __future__ import annotations

import ast
import io
import re
from typing import Any


def parse_spreadsheet(file_bytes: bytes) -> list[dict[str, Any]]:
    """Parse an Octavius rule spreadsheet and return a list of row dicts.

    Expects the first row to be column headers matching the standard
    Octavius rulebook format (rule_id, Part 1 — Check function, etc.).
    """
    import openpyxl

    wb = openpyxl.load_workbook(
        io.BytesIO(file_bytes), read_only=True, data_only=True
    )
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)

    raw_headers = next(rows_iter, None)
    if raw_headers is None:
        return []
    headers = [str(h).strip() if h is not None else "" for h in raw_headers]

    results: list[dict[str, Any]] = []
    for row in rows_iter:
        if not any(row):
            continue
        row_dict = {headers[i]: v for i, v in enumerate(row) if i < len(headers)}
        if not row_dict.get("rule_id"):
            continue
        results.append(row_dict)

    wb.close()
    return results


def extract_fire_skip(part3_code: str) -> tuple[str, str]:
    """Extract FIRE and SKIP test strings from a Part 3 code cell.

    Returns ``(fire_text, skip_text)`` as plain strings with inline Python
    comments stripped.  Either value may be empty if the corresponding
    variable is absent from the cell.
    """
    if not part3_code:
        return "", ""
    return (
        _extract_string_var(part3_code, "FIRE"),
        _extract_string_var(part3_code, "SKIP"),
    )


def _extract_string_var(code: str, suffix: str) -> str:
    """Find the first triple-quoted string assigned to a variable ending in *suffix*."""
    for quote in ('"""', "'''"):
        q = re.escape(quote)
        pattern = rf'_\w+_{suffix}\s*=\s*({q}[\s\S]*?{q})'
        m = re.search(pattern, code)
        if m:
            try:
                value: str = ast.literal_eval(m.group(1))
                return _strip_comments(value)
            except Exception:
                pass
    return ""


def _strip_comments(text: str) -> str:
    """Remove trailing inline ``# ...`` comments from each line; drop blank lines.

    Only strips ``# ...`` preceded by at least two spaces so that Markdown
    headings (``## Background``) are preserved.
    """
    lines = []
    for line in text.splitlines():
        clean = re.sub(r"  #.*$", "", line)
        if clean.strip():
            lines.append(clean)
    return "\n".join(lines)
