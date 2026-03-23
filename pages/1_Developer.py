"""Octavius — Rule Builder for iterative rule authoring and testing."""

from __future__ import annotations

import re as _re
from typing import Any

import streamlit as st

from logic.engine import get_spacy_status, lint_text
from logic.excel_import import extract_fire_skip, parse_spreadsheet
from logic.sandbox import build_regex_check, execute_rule_code, translate_error
from octavius_component import st_octavius_editor

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(page_title="Octavius — Rule Builder", layout="wide")


# ── Helpers ──────────────────────────────────────────────────────────
def _make_rule_id(title: str) -> str:
    """Convert a human title to a slug-style rule ID, e.g. MY-RULE-001."""
    slug = _re.sub(r"[^a-zA-Z0-9]+", "-", title).upper().strip("-")
    return f"{slug}-001" if slug else "MY-RULE-001"


_SEVERITY_LABELS = {"Warning": "warn", "Error": "error", "Info": "info"}
_SEVERITY_LABEL_DEFAULT = "Warning"


def _batch_test_row(
    row: dict[str, Any],
    fire_text: str,
    skip_text: str,
) -> dict[str, Any]:
    """Compile and test a single rule row against its FIRE and SKIP examples.

    Returns a result dict with keys:
      status      "pass" | "fail" | "error"
      error       str | None
      fire_n      int — findings in FIRE text
      skip_n      int — findings in SKIP text
      fire_ok     bool
      skip_ok     bool
      fire_text   str — the FIRE text used (for replay display)
      fire_findings list[dict]
      rule_meta   dict — id/title/severity for the React editor
    """
    part1: str = (row.get("Part 1 \u2014 Check function") or "").strip()
    rule_id: str = row.get("rule_id") or "UNKNOWN"
    severity: str = row.get("severity") or "warn"
    title: str = row.get("rule_summary") or rule_id

    if not part1:
        return {
            "status": "error",
            "error": "Part 1 (Check function) is empty for this rule.",
            "fire_n": 0, "skip_n": 0,
            "fire_ok": False, "skip_ok": False,
            "fire_text": fire_text, "fire_findings": [],
            "rule_meta": {"id": rule_id, "title": title, "severity": severity},
        }

    rule_meta = {"id": rule_id, "title": title, "message": title, "severity": severity}
    rule, error = execute_rule_code(part1, rule_meta)
    if error:
        return {
            "status": "error",
            "error": translate_error(error),
            "fire_n": 0, "skip_n": 0,
            "fire_ok": False, "skip_ok": False,
            "fire_text": fire_text, "fire_findings": [],
            "rule_meta": {"id": rule_id, "title": title, "severity": severity},
        }

    fire_findings = lint_text(fire_text, [rule]) if fire_text.strip() else []
    skip_findings = lint_text(skip_text, [rule]) if skip_text.strip() else []

    fire_n = len(fire_findings)
    skip_n = len(skip_findings)
    fire_ok = (fire_n > 0) if fire_text.strip() else True
    skip_ok = skip_n == 0

    return {
        "status": "pass" if (fire_ok and skip_ok) else "fail",
        "error": None,
        "fire_n": fire_n,
        "skip_n": skip_n,
        "fire_ok": fire_ok,
        "skip_ok": skip_ok,
        "fire_text": fire_text,
        "fire_findings": [dict(f) for f in fire_findings],
        "rule_meta": {"id": rule_id, "title": title, "severity": severity},
    }


def _format_rule_option(row: dict[str, Any], results: dict[str, Any]) -> str:
    rid = row.get("rule_id", "?")
    result = results.get(rid)
    if result is None:
        icon = "⚪"
    elif result["status"] == "pass":
        icon = "✅"
    elif result["status"] == "error":
        icon = "🔴"
    else:
        icon = "❌"
    title = row.get("rule_summary") or ""
    short_title = title[:55] + "…" if len(title) > 55 else title
    return f"{icon}  {rid}  —  {short_title}"


# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Octavius")
    st.caption("Rule Builder")
    st.divider()
    st.markdown(
        """
**Rule Builder tab:**

1. Describe your rule in **Step 1**
2. Copy the AI prompt in **Step 2** and paste it into Claude or ChatGPT
3. Paste the code back into **Step 3**
4. Click **Test Rule** in **Step 4** to see it in action
5. Copy the export block in **Step 5**

**Batch Test tab:**

Upload a rules spreadsheet (.xlsx) to test all rules at once.
"""
    )
    with st.expander("System status"):
        spacy_ok = get_spacy_status()
        st.metric("spaCy model", "loaded" if spacy_ok else "missing")
        if not spacy_ok:
            st.error(
                "spaCy model missing — run:\npython -m spacy download en_core_web_sm"
            )


# ── Session state defaults ───────────────────────────────────────────
_DEFAULTS: dict = {
    # Rule Builder tab
    "dev_text": "The report was written by the team. Mistakes were made.",
    "dev_findings": [],
    "dev_error": None,
    "dev_rule": None,
    "dev_code": "",
    "dev_title": "My custom rule",
    "dev_message": "This pattern was detected.",
    "dev_severity_label": _SEVERITY_LABEL_DEFAULT,
    # Batch Test tab
    "batch_rows": [],
    "batch_filename": None,
    "batch_results": {},
    "batch_selected_idx": 0,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Layout ───────────────────────────────────────────────────────────
st.header("Rule Builder")

tab_builder, tab_batch = st.tabs(["🔧 Rule Builder", "📋 Batch Test"])


# ════════════════════════════════════════════════════════════════════
# TAB 1 — Rule Builder (original single-rule workflow)
# ════════════════════════════════════════════════════════════════════
with tab_builder:

    left_col, right_col = st.columns(2, gap="large")

    # ── LEFT: Step-by-step workflow ──────────────────────────────────
    with left_col:

        # Step 1 — Describe your rule
        st.subheader("Step 1 — Describe your rule")

        meta_title = st.text_input(
            "Rule name",
            value=st.session_state["dev_title"],
            key="dev_title",
            help="A short name for the rule, e.g. 'Passive voice' or 'Jargon words'.",
        )
        meta_message = st.text_area(
            "What should it tell the user?",
            value=st.session_state["dev_message"],
            key="dev_message",
            height=80,
            help="The message shown when the rule fires.",
        )
        severity_label = st.selectbox(
            "How serious is this issue?",
            list(_SEVERITY_LABELS.keys()),
            index=list(_SEVERITY_LABELS.keys()).index(
                st.session_state["dev_severity_label"]
            ),
            key="dev_severity_label",
            help="**Warning** — common style issue. **Error** — must fix. **Info** — helpful note.",
        )
        meta_severity = _SEVERITY_LABELS[severity_label]
        rule_id = _make_rule_id(meta_title)
        st.caption(f"Rule ID (auto-generated): `{rule_id}`")

        rule_meta = {
            "id": rule_id,
            "title": meta_title,
            "message": meta_message,
            "severity": meta_severity,
        }

        st.divider()

        # Step 2 — Get code from an AI assistant
        st.subheader("Step 2 — Get the code from an AI assistant")
        st.markdown(
            "Copy the prompt below and paste it into **Claude** or **ChatGPT**. "
            "It's already filled in with what you entered above."
        )

        ai_prompt = f"""\
Write a Python function for a plain-language linter rule called "{meta_title}".

The function must:
- Be named check_something (any name starting with check_)
- Accept a single argument: doc (a spaCy Doc object)
- Return a list of dicts, each with: start_char (int), end_char (int), and optionally suggestion (str)

Rule purpose: {meta_message}

Use spaCy token attributes such as token.dep_, token.pos_, token.lemma_, token.text, and token.idx.
To highlight a span of tokens: use span.start_char and span.end_char.
Do not import anything — spaCy's Doc, re, and standard Python builtins are already available.

Return only the Python function, no explanation needed.\
"""

        st.code(ai_prompt, language=None)
        st.divider()

        # Step 3 — Paste the generated code
        st.subheader("Step 3 — Paste the generated code")
        st.markdown("Paste the code you received from your AI assistant into the box below.")

        code = st.text_area(
            "Generated rule code",
            value=st.session_state["dev_code"],
            key="dev_code",
            height=260,
            placeholder="def check_my_rule(doc):\n    results = []\n    # ... paste here ...\n    return results",
            label_visibility="collapsed",
        )

        st.divider()

        # Step 4 — Test the rule
        st.subheader("Step 4 — Test the rule")
        st.markdown(
            "Enter some example sentences below. "
            "Anything the rule should flag will be highlighted in the preview on the right."
        )

        st.text_area(
            "Test text",
            key="dev_text",
            height=100,
            label_visibility="collapsed",
        )

        if st.button("▶  Test Rule", type="primary", use_container_width=True):
            if not code.strip():
                st.session_state["dev_error"] = (
                    "The code box is empty. "
                    "Complete Step 2 to get code from an AI assistant, then paste it in Step 3."
                )
                st.session_state["dev_findings"] = []
                st.session_state["dev_rule"] = None
            else:
                rule, error = execute_rule_code(code, rule_meta)
                if error:
                    st.session_state["dev_error"] = translate_error(error)
                    st.session_state["dev_findings"] = []
                    st.session_state["dev_rule"] = None
                else:
                    st.session_state["dev_error"] = None
                    st.session_state["dev_rule"] = rule
                    st.session_state["dev_findings"] = lint_text(
                        st.session_state["dev_text"], [rule]
                    )
            st.rerun()

        if st.session_state["dev_error"]:
            st.error(st.session_state["dev_error"])
        elif st.session_state["dev_rule"] is not None:
            n = len(st.session_state["dev_findings"])
            if n:
                st.success(
                    f"✅ Rule compiled and found {n} match{'es' if n != 1 else ''} in your test text."
                )
            else:
                st.info(
                    "✅ Rule compiled. No matches in the test text — "
                    "try different sentences, or check that the rule logic is correct."
                )

        st.divider()

        # Step 5 — Copy for export
        st.subheader("Step 5 — Copy for export")

        dev_rule = st.session_state["dev_rule"]
        if dev_rule is None:
            st.info("Complete Steps 1–4 first. Once your rule works, the export block will appear here.")
        else:
            st.success(
                "Your rule is working! Copy the two blocks below and send them to your developer."
            )

            check_fn_name = dev_rule["check"].__name__

            st.markdown("**The rule function** (from Step 3):")
            st.code(code, language="python")

            st.markdown("**The rule registration block** (add this to `logic/rules.py`):")
            export_block = (
                f'{{\n'
                f'    "id": "{dev_rule["id"]}",\n'
                f'    "title": "{dev_rule["title"]}",\n'
                f'    "message": "{dev_rule["message"]}",\n'
                f'    "severity": "{dev_rule["severity"]}",\n'
                f'    "category": "Custom",\n'
                f'    "suggestion": None,\n'
                f'    "check": {check_fn_name},\n'
                f'}}'
            )
            st.code(export_block, language="python")

        st.divider()

        # Advanced (collapsed)
        with st.expander("Advanced — Regex mode and spaCy reference"):
            st.markdown(
                "**Regex mode** — if your AI assistant gives you a regex pattern instead of a function, "
                "enter it here and click Test."
            )
            pattern = st.text_input(
                "Regex pattern",
                value=r"\b\w+ed\b",
                help="Python `re` syntax. Each match is flagged as a finding.",
            )
            if st.button("Test Regex", use_container_width=True):
                try:
                    check_fn = build_regex_check(pattern)
                    adv_rule = {
                        "id": rule_meta["id"],
                        "title": rule_meta["title"],
                        "message": rule_meta["message"],
                        "severity": rule_meta["severity"],
                        "suggestion": None,
                        "check": check_fn,
                    }
                    st.session_state["dev_error"] = None
                    st.session_state["dev_rule"] = adv_rule
                    st.session_state["dev_findings"] = lint_text(
                        st.session_state["dev_text"], [adv_rule]
                    )
                except _re.error as exc:
                    st.session_state["dev_error"] = f"Invalid regex pattern: {exc}"
                    st.session_state["dev_findings"] = []
                    st.session_state["dev_rule"] = None
                st.rerun()

            st.markdown(
                """
---
**spaCy token attributes** (use on `token` in a `for token in doc` loop):

| Attribute | Example value | Meaning |
|-----------|---------------|---------|
| `token.text` | `"written"` | Surface form |
| `token.lemma_` | `"write"` | Base form |
| `token.pos_` | `"VERB"` | Coarse POS tag |
| `token.tag_` | `"VBN"` | Fine-grained POS |
| `token.dep_` | `"auxpass"` | Dependency relation |
| `token.idx` | `4` | Character start offset |
| `token.head` | `Token` | Syntactic head token |

**Common dependency labels:** `nsubj`, `dobj`, `auxpass`, `aux`, `amod`, `prep`

**Span from tokens:**
```python
span = doc[start_token_i : end_token_i + 1]
start_char = span.start_char
end_char   = span.end_char
```
"""
            )

    # ── RIGHT: Visual preview ────────────────────────────────────────
    with right_col:
        st.subheader("Preview")

        dev_rule = st.session_state["dev_rule"]
        rules_meta_for_editor = (
            [
                {
                    "id": dev_rule["id"],
                    "title": dev_rule["title"],
                    "severity": dev_rule["severity"],
                }
            ]
            if dev_rule is not None
            else []
        )

        result = st_octavius_editor(
            text=st.session_state["dev_text"],
            findings=[dict(f) for f in st.session_state["dev_findings"]],
            rules=rules_meta_for_editor,
            key="dev_editor",
        )

        if result is not None:
            new_text: str = result.get("text", "")
            st.session_state["dev_text"] = new_text

            if st.session_state["dev_rule"] is not None:
                st.session_state["dev_findings"] = lint_text(
                    new_text, [st.session_state["dev_rule"]]
                )
            else:
                st.session_state["dev_findings"] = []
                st.session_state["dev_error"] = (
                    "Test your rule first (Step 4) before using the Analyse button."
                )

            st.rerun()

        if dev_rule is None and not st.session_state["dev_error"]:
            st.info("Complete Step 4 to see findings highlighted here.")


# ════════════════════════════════════════════════════════════════════
# TAB 2 — Batch Test (spreadsheet import workflow)
# ════════════════════════════════════════════════════════════════════
with tab_batch:

    # ── Upload ───────────────────────────────────────────────────────
    st.markdown(
        "Upload your Octavius rules spreadsheet. "
        "Each row's **Part 1** code will be tested against its **Part 3** examples."
    )

    uploaded = st.file_uploader(
        "Choose a .xlsx file",
        type=["xlsx"],
        label_visibility="collapsed",
    )

    if uploaded is not None and uploaded.name != st.session_state["batch_filename"]:
        with st.spinner("Parsing spreadsheet…"):
            rows = parse_spreadsheet(uploaded.read())
        st.session_state["batch_rows"] = rows
        st.session_state["batch_filename"] = uploaded.name
        st.session_state["batch_results"] = {}
        st.session_state["batch_selected_idx"] = 0
        st.rerun()

    rows: list[dict[str, Any]] = st.session_state["batch_rows"]

    if not rows:
        st.info("No spreadsheet loaded yet. Upload an .xlsx file above to get started.")
        st.stop()

    # ── Summary bar ──────────────────────────────────────────────────
    results: dict[str, Any] = st.session_state["batch_results"]
    n_total = len(rows)
    n_pass = sum(1 for r in results.values() if r["status"] == "pass")
    n_fail = sum(1 for r in results.values() if r["status"] in ("fail", "error"))
    n_untested = n_total - len(results)

    st.caption(f"Loaded: **{st.session_state['batch_filename']}** — {n_total} rule{'s' if n_total != 1 else ''}")

    sum_c1, sum_c2, sum_c3, sum_c4 = st.columns([1, 1, 1, 2])
    sum_c1.metric("✅ Passed", n_pass)
    sum_c2.metric("❌ Failed", n_fail)
    sum_c3.metric("⚪ Untested", n_untested)

    with sum_c4:
        if st.button("Test All Rules", type="primary", use_container_width=True):
            bar = st.progress(0, text="Starting…")
            for i, row in enumerate(rows):
                rid = row.get("rule_id") or f"ROW_{i}"
                fire_key = f"batch_fire_{rid}"
                skip_key = f"batch_skip_{rid}"

                # Use edited text if present, otherwise extract from Part 3
                fire_text = st.session_state.get(fire_key)
                skip_text = st.session_state.get(skip_key)
                if fire_text is None or skip_text is None:
                    raw_fire, raw_skip = extract_fire_skip(
                        row.get("Part 3 \u2014 Test examples") or ""
                    )
                    if fire_text is None:
                        fire_text = raw_fire
                        st.session_state[fire_key] = fire_text
                    if skip_text is None:
                        skip_text = raw_skip
                        st.session_state[skip_key] = skip_text

                results[rid] = _batch_test_row(row, fire_text, skip_text)
                bar.progress((i + 1) / n_total, text=f"Tested {rid} ({i + 1}/{n_total})")

            st.session_state["batch_results"] = results
            st.rerun()

    st.divider()

    # ── Rule navigator ───────────────────────────────────────────────
    idx: int = max(0, min(st.session_state["batch_selected_idx"], n_total - 1))

    nav_prev, nav_select, nav_next = st.columns([1, 6, 1])

    with nav_prev:
        if st.button("◀", use_container_width=True, disabled=(idx == 0), key="batch_prev"):
            st.session_state["batch_selected_idx"] = idx - 1
            st.rerun()

    with nav_next:
        if st.button("▶", use_container_width=True, disabled=(idx == n_total - 1), key="batch_next"):
            st.session_state["batch_selected_idx"] = idx + 1
            st.rerun()

    with nav_select:
        new_idx = st.selectbox(
            "Rule",
            range(n_total),
            index=idx,
            format_func=lambda i: _format_rule_option(rows[i], results),
            label_visibility="collapsed",
            key="_batch_selectbox",
        )
        if new_idx != idx:
            st.session_state["batch_selected_idx"] = new_idx
            st.rerun()

    st.caption(f"Rule {idx + 1} of {n_total}")

    selected_row = rows[idx]
    rid = selected_row.get("rule_id") or f"ROW_{idx}"
    severity = selected_row.get("severity") or "warn"
    impl_type = selected_row.get("implementation_type") or "spacy"
    part1_code = (selected_row.get("Part 1 \u2014 Check function") or "").strip()
    part2_block = (selected_row.get("Part 2 \u2014 RULES entry") or "").strip()
    part3_code = selected_row.get("Part 3 \u2014 Test examples") or ""

    # Initialise per-rule text areas from Part 3 on first visit
    fire_key = f"batch_fire_{rid}"
    skip_key = f"batch_skip_{rid}"
    if fire_key not in st.session_state or skip_key not in st.session_state:
        raw_fire, raw_skip = extract_fire_skip(part3_code)
        if fire_key not in st.session_state:
            st.session_state[fire_key] = raw_fire
        if skip_key not in st.session_state:
            st.session_state[skip_key] = raw_skip

    # ── Detail view ──────────────────────────────────────────────────
    detail_left, detail_right = st.columns([11, 9], gap="large")

    with detail_left:
        # Rule metadata chips
        sev_colour = {"error": "🔴", "warn": "🟡", "info": "🔵"}.get(severity, "⚪")
        st.markdown(
            f"`{rid}` &nbsp; {sev_colour} {severity} &nbsp; `{impl_type}`",
            unsafe_allow_html=True,
        )

        # Part 1 — collapsible code viewer
        with st.expander("Part 1 — Check function (code)", expanded=False):
            if part1_code:
                st.code(part1_code, language="python")
            else:
                st.warning("Part 1 is empty for this rule.")

        # FIRE examples
        st.markdown(
            "**FIRE examples** — the rule *should* flag these sentences:"
        )
        fire_text: str = st.text_area(
            "FIRE",
            key=fire_key,
            height=150,
            label_visibility="collapsed",
            placeholder="Paste sentences that should trigger this rule, one per line.",
        )

        # SKIP examples
        st.markdown(
            "**SKIP examples** — the rule should *not* flag these:"
        )
        skip_text: str = st.text_area(
            "SKIP",
            key=skip_key,
            height=120,
            label_visibility="collapsed",
            placeholder="Paste sentences that should NOT trigger this rule, one per line.",
        )

        if st.button(
            "▶  Run Tests",
            type="primary",
            use_container_width=True,
            key=f"run_{rid}",
        ):
            if not part1_code:
                st.error("Part 1 (Check function) is empty — nothing to test.")
            else:
                with st.spinner("Running…"):
                    res = _batch_test_row(selected_row, fire_text, skip_text)
                st.session_state["batch_results"][rid] = res
                st.rerun()

    with detail_right:
        result = results.get(rid)

        if result is None:
            st.info("Click **▶ Run Tests** to test this rule, or use **Test All Rules** above.")

        elif result["status"] == "error":
            st.error(f"**Compilation error:**\n\n{result['error']}")
            st.markdown(
                "Check Part 1 code for syntax issues. "
                "You can edit the FIRE/SKIP text on the left while you investigate."
            )

        else:
            # FIRE result
            fire_n = result["fire_n"]
            if result["fire_ok"]:
                st.success(
                    f"✅ **FIRE** — {fire_n} match{'es' if fire_n != 1 else ''} found "
                    f"(rule fires correctly)"
                )
            else:
                st.error(
                    "❌ **FIRE** — rule did not fire on any FIRE examples. "
                    "Check the code logic or adjust the test sentences."
                )

            # React editor showing FIRE text with highlights
            if result["fire_text"].strip():
                st_octavius_editor(
                    text=result["fire_text"],
                    findings=result["fire_findings"],
                    rules=[result["rule_meta"]],
                    key=f"batch_preview_{rid}",
                )

            st.divider()

            # SKIP result
            skip_n = result["skip_n"]
            if result["skip_ok"]:
                st.success("✅ **SKIP** — no false positives")
            else:
                st.error(
                    f"❌ **SKIP** — {skip_n} false positive{'s' if skip_n != 1 else ''} found. "
                    "The rule is flagging text it shouldn't."
                )

            # Export block — only shown when the rule passes both tests
            if result["status"] == "pass" and part2_block:
                st.divider()
                st.markdown("**Part 2 — RULES entry** (ready to add to `logic/rules.py`):")
                st.code(part2_block, language="python")

    # ── Export all passing rules ─────────────────────────────────────
    passing = [r for r in rows if results.get(r.get("rule_id"), {}).get("status") == "pass"]
    if passing:
        st.divider()
        with st.expander(f"Export all {len(passing)} passing rule(s)", expanded=False):
            st.markdown(
                "Copy the blocks below and send to your developer to add to `logic/rules.py`."
            )
            combined_parts = []
            for row in passing:
                p1 = (row.get("Part 1 \u2014 Check function") or "").strip()
                p2 = (row.get("Part 2 \u2014 RULES entry") or "").strip()
                rid_exp = row.get("rule_id", "")
                combined_parts.append(
                    f"# ── {rid_exp} ──────────────────────────────────────────\n\n"
                    f"{p1}\n\n"
                    f"# RULES entry:\n{p2}"
                )
            st.code("\n\n\n".join(combined_parts), language="python")
