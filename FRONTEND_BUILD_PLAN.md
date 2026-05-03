# Octavius Frontend Build Plan

**Goal:** Stand up a public-facing Octavius interface that applies the ~800 rules whose `test_result == "pass"` in the rulebook, in line with `octavius_frontend_spec.md` and the V1 scope agreed in `A-synch_SuggestionForApproach.md`.

**Author:** Repository audit + plan, prepared for execution by Claude Code.
**Branch:** `claude/create-frontend-interface-gHRNo`

---

## 1. Repository audit

### 1.1 What already exists (and is reusable)

| Layer | File(s) | Status |
|---|---|---|
| FastAPI backend | `main.py` | Already present. Exposes `POST /check` and `GET /groups`. Wires `logic.engine.lint_text` to a single hard-coded rule list. CORS open to `*`. |
| Rule engine | `logic/engine.py` | spaCy-based; expects every rule to provide `check(doc) -> [{start_char, end_char, suggestion}]`. Returns a `Finding` with offsets. |
| Hard-coded rule | `logic/rules.py` | Single passive-voice rule (`PASSIVE-VOICE-001`) used as the vertical-slice proof. |
| Code sandbox | `logic/sandbox.py` | Restricted-builtins `exec()` namespace ready for executing generated rule code. |
| Static frontend | `index.html` (single file, 861 lines) | Vanilla HTML/CSS/JS implementation of the spec: textarea + overlay div for highlights, debounced fetch with `AbortController`, tabbed sidebar (Issues / Rules), tooltip on hover, banner for cold-start / errors. Hits `/groups` and `/check`. |
| Streamlit shell | `app.py`, `pages/1_Developer.py`, `octavius_component.py`, `frontend/` (React build) | Legacy UI used during the vertical-slice phase. Kept for the Developer rule-authoring screen. |
| Render config | `render.yaml` | Targets `uvicorn main:app`. Sufficient for the new backend. |
| Rulebook artefact | `published/rulebook.parquet` (+ `rulebook_metadata.json`) | 3,114 rules, snappy-compressed Parquet, list-typed columns normalised. The deploy-time source of truth. |
| Working draft | `rules_working_draft.jsonl` | 6.4 MB JSONL. The mutable Phase 2–5 format; **not** what the runtime should consume. |
| Pipeline | `src/*.py` + `.github/workflows/phase*.yml` | Six-phase OpenAI-batch pipeline that produces the rulebook. Untouched by this work. |

### 1.2 Rulebook content (verified counts)

```
test_result == pass    : 801
test_result == skip    : 2,064 (semantic/discretionary/multi-modal — out of V1 scope)
test_result == fail    : 61
test_result == frozen  : 188
```

Pass-set by taxonomy:

```
lookup     : 415   def check_rule(text: str, lookup_list: list[str]) -> list[str]
regex      : 124   bare regex pattern string (no def)
structural : 262   def check_rule(text: str) -> list[str]   (signature varies; helper fns common)
spacy      :   0   (no passing spaCy rules yet — taxonomy reserved)
```

### 1.3 Critical gap between trigger-code output and the existing `Finding` schema

The existing `logic/engine.py` and `frontend` both assume each rule returns **character offsets**. The Phase 3 trigger code does **not**:

- `regex` rules are bare patterns — offsets are trivially recoverable via `re.finditer`.
- `lookup` rules return matched terms (strings). Offsets must be recovered by re-searching the input text for each returned term (`\b` + `re.escape(term)` + `\b`, case-insensitive).
- `structural` rules return arbitrary descriptive strings (e.g. `'in-text citation and reference list citation present'`). These are usually **not** present verbatim in the input, so a span cannot always be recovered. They must be surfaced as **document-level** findings (no inline highlight; listed in the side panel only).

This adapter layer is the single most important new piece of code.

### 1.4 What the spec asks for that doesn't exist yet

- A loader that reads `published/rulebook.parquet`, filters `test_result == "pass"`, compiles trigger code once at startup, and exposes a uniform `check(text) -> list[Finding]` interface.
- Per-`rule_id` and per-`taxonomy` filtering on `/check` (the A-synch doc explicitly requires this; current `/groups` only filters by category, which doesn't exist on the new rulebook).
- `/rules` endpoint returning the full catalogue (id, taxonomy, ui_flag, summary, source URL) so the sidebar can list and search 800 rules.
- A frontend Rules-panel upgrade: search, taxonomy bulk toggle, per-rule checkbox, persisted state.
- `pyarrow` (or `pandas`) added to `requirements.txt` so Render can read the parquet.
- Deployment target for the static frontend: GitHub Pages workflow that publishes `index.html` from `main` → `gh-pages`.

---

## 2. Architectural plan

### 2.1 Guiding principles

1. **Don't fork the schema.** The existing `Finding` shape (`start_char`, `end_char`, `rule_id`, `message`, `severity`, `suggestion`) and the API contract from the spec stay the same. New fields are additive (`taxonomy`, `ui_flag`, `source_url`).
2. **Dispatch on `taxonomy`.** A single registry maps taxonomy → adapter. Adding `semantic`, `contextual`, `multi-modal` later is one new branch.
3. **Compile once.** Trigger code is `compile()`d at startup, never per request. Regex patterns are precompiled. Lookup lists are pre-lowered.
4. **Pure functions, message-passed results.** Rules never mutate shared state. The dispatcher maps `text -> list[Finding]` and is safe to fan out via `concurrent.futures` later.
5. **Future Aho-Corasick is an optimisation, not an architecture change.** Lookup rules go through one adapter; swapping it for an automaton is a single file change.
6. **The published parquet is the runtime source of truth.** The JSONL is the authoring format. The pipeline keeps owning it.
7. **No backend changes when Option C (React) lands.** Same `/check` and `/rules` contract.

### 2.2 Backend layout (new files in italics)

```
main.py                         FastAPI app + route wiring (rewritten, slim)
logic/
  engine.py                     unchanged for legacy single-rule path
  rules.py                      unchanged
  sandbox.py                    reused for restricted exec
  rulebook/
    __init__.py
    loader.py        (new)      read parquet → list[CompiledRule]
    adapters.py      (new)      regex / lookup / structural → uniform check(text)
    spans.py         (new)      offset recovery helpers
    types.py         (new)      CompiledRule TypedDict
  dispatcher.py      (new)      run_rules(text, rule_ids|taxonomies) -> list[Finding]
routes/
  __init__.py
  check.py           (new)      POST /check
  rules.py           (new)      GET /rules, GET /taxonomies
tests/
  test_rulebook_loader.py (new)
  test_adapters.py        (new)
  test_dispatcher.py      (new)
```

### 2.3 Adapter contracts

```python
# logic/rulebook/types.py
class CompiledRule(TypedDict):
    rule_id: str
    taxonomy: Literal["regex", "lookup", "structural"]
    ui_flag: str
    rule_summary: str
    source_url: str
    severity: str                 # default "warning"
    check: Callable[[str], list[Finding]]   # taxonomy-agnostic
```

- `adapters.compile_regex(rule)` → wraps `re.compile(pattern, re.IGNORECASE).finditer` and yields `Finding` per match.
- `adapters.compile_lookup(rule)` → captures `lookup_list`; runs the trigger code's `check_rule(text, lookup_list)` to detect, then re-locates each returned term via `\b` + escaped + `\b` to attach offsets. If no offset found, emits a document-level `Finding` (`start=0, end=0`).
- `adapters.compile_structural(rule)` → executes trigger code in the `logic.sandbox` namespace, calls `check_rule(text)`. Truthy return → one `Finding` per returned item; if the item's text appears in the input, recover its offsets, otherwise emit document-level.

Severity defaults to `"warning"`; `discretionary_flag == True` → `"info"`.

### 2.4 API contract (final)

`GET /rules` →
```json
[{"rule_id": "...", "taxonomy": "lookup", "ui_flag": "...", "rule_summary": "...", "source_url": "..."}]
```

`GET /taxonomies` →
```json
[{"id": "lookup", "rule_count": 415}, {"id": "regex", "rule_count": 124}, {"id": "structural", "rule_count": 262}]
```

`POST /check` body:
```json
{
  "text": "...",
  "disabled_rule_ids": ["..."],
  "disabled_taxonomies": ["structural"]
}
```
The defaults are *enable everything*. Disable lists are sent so the rulebook can grow without forcing the client to re-list 800 ids.

`POST /check` response (additive vs. spec):
```json
[{
  "rule_id": "how-cite-style-manual-007",
  "taxonomy": "regex",
  "group": "regex",
  "message": "Style Manual citation contains a duplicate inner reference.",
  "ui_flag": "Duplicate citation reference detected.",
  "source_url": "https://www.stylemanual.gov.au/...",
  "start": 42,
  "end": 71,
  "severity": "warning",
  "document_level": false
}]
```

The fields the spec already requires (`rule_id`, `group`, `message`, `start`, `end`, `severity`) are preserved so the existing `index.html` keeps working without a frontend change.

### 2.5 Frontend changes (extend, don't rebuild)

Keep `index.html` as the single deployable artefact. Changes:

- **Rules panel:** search box, taxonomy section headers with "Disable all in this taxonomy" toggles, per-rule checkboxes (virtualised — 800 DOM nodes is fine but list virtualisation keeps scroll snappy).
- **Persisted state:** `localStorage["octavius.disabledRuleIds"]` and `localStorage["octavius.disabledTaxonomies"]`. Migrate the legacy `octavius-groups` key on first load.
- **Findings panel:** show `ui_flag` as the headline, `rule_summary` as secondary text, link the rule_id to `source_url`. For `document_level: true` findings show a "Document" badge instead of a scroll target.
- **API_BASE toggle:** read from `window.OCTAVIUS_API_BASE` if set (allows GitHub Pages deploy to point at Render without editing the file each release; the workflow injects this).

### 2.6 Performance posture for V1

- Compile trigger code at startup; reject malformed rules loudly so failures don't surface only on a user request.
- Run all enabled rules in a single thread per request. 800 short regexes on a few-paragraph document on a Render free instance is well under the 300 ms debounce budget; benchmark and add a `concurrent.futures.ThreadPoolExecutor` only if the median crosses ~200 ms.
- **Do not** implement Aho-Corasick, dirty-range tracking, vector embeddings, or LLM stages. The A-synch doc is explicit that those are out of V1 scope. Leave the dispatcher's lookup branch as the single seam where they will land.

### 2.7 Future-proofing checklist

- Adding a new taxonomy → one new function in `adapters.py` + one branch in the loader's dispatch table.
- Switching lookup to Aho-Corasick → replace `compile_lookup` only; `CompiledRule.check` signature unchanged.
- Adding spaCy/Doc-level rules → loader sees `requires: ["spacy"]`, lazily loads `nlp`, passes `doc` to the adapter; engine cache keyed on text hash.
- Adding semantic/LLM stages → new taxonomy branches; the dispatcher already returns a uniform `list[Finding]`.
- Replacing the static frontend with React (Option C) → `index.html` stays in the repo as the fallback; React calls the same endpoints.

---

## 3. Build sequence (what Claude Code should actually do)

1. **Add the parquet reader.** New `logic/rulebook/loader.py`. Add `pyarrow` to `requirements.txt`. Loader filters `test_result == "pass"` and returns `list[CompiledRule]`. Loud failure on a missing or unreadable parquet — never silent fallback to the legacy `logic.rules.RULES`.
2. **Implement the three adapters.** `regex` first (easiest), then `lookup`, then `structural`. Each adapter is a pure function `dict -> CompiledRule`. Trigger code runs through `logic.sandbox`-style restricted globals, not bare `exec`.
3. **Implement `dispatcher.run_rules(text, disabled_rule_ids, disabled_taxonomies)`** returning `list[Finding]` sorted by `(start, rule_id)`.
4. **Rewrite `main.py`** around the dispatcher. Keep the existing `/check` shape backwards compatible (additive fields only) and accept the new `disabled_*` body fields as well as the legacy `rule_groups` (treat the legacy field as ignored with a deprecation log line).
5. **Add `/rules` and `/taxonomies`.** Route file lives in `routes/`.
6. **Tests.** `tests/test_rulebook_loader.py` asserts every passing rule compiles. Per-taxonomy adapter tests run a handful of rules' own `test_fire` / `test_no_fire` examples through the engine and assert the expected fire / no-fire behaviour. A dispatcher-level smoke test runs all 800 rules over a mid-sized text and asserts no exceptions and a sane runtime ceiling.
7. **Frontend update.** Extend `index.html` only — add the rule search/filter UI, swap `/groups` consumption for `/rules` + `/taxonomies`, switch to the new disabled-id payload. Add `window.OCTAVIUS_API_BASE` override.
8. **Deploy plumbing.** Add `.github/workflows/deploy_pages.yml` that copies `index.html` to `gh-pages` on push to main. Confirm `render.yaml` still works (it should — only `requirements.txt` grew).
9. **Smoke test end-to-end** with `uvicorn main:app` locally and `index.html` opened in a browser. Verify a `lookup` hit highlights, a `regex` hit highlights, a `structural` hit appears as a document-level finding.
10. **Commit and push to `claude/create-frontend-interface-gHRNo`.** Do not open a PR unless asked.

Out of scope for this branch: Aho-Corasick, web workers, vector embeddings, LLM stages, auth, document persistence, mobile layout, React migration.

---

## 4. Prompt to give Claude Code

Paste the block below as a single prompt. It is self-contained — do not rely on chat history. Read it once, then send it.

> **Build the Octavius V1 rulebook frontend on branch `claude/create-frontend-interface-gHRNo`.**
>
> **Context — read these first, in this order:**
> 1. `octavius_frontend_spec.md` — the contract for the frontend (Option A, FastAPI + static HTML, debounced `/check`, overlay highlights, GitHub Pages + Render).
> 2. `A-synch_SuggestionForApproach.md` — note the "Important note" at the bottom: V1 scope is **only** the rules whose `test_result == "pass"`, with per-`rule_id` and per-taxonomy disable controls. Do **not** implement the Aho-Corasick / vector / LLM waterfall — those are explicitly future state.
> 3. `FRONTEND_BUILD_PLAN.md` — the architectural plan and build sequence. Follow the file layout in §2.2 and the build sequence in §3 unless you find a specific reason not to (state the reason if so).
> 4. `CLAUDE.md` — project conventions, commands, rule schema.
>
> **Inputs you can rely on:**
> - `published/rulebook.parquet` (3,114 rows; filter `test_result == "pass"` → 801 rules: 415 lookup, 124 regex, 262 structural).
> - Existing `main.py` (FastAPI), `index.html` (vanilla frontend), `logic/engine.py`, `logic/sandbox.py`, `render.yaml`. **Extend, do not rewrite from scratch.**
>
> **Deliverables (one branch, one push, no PR unless I ask):**
> 1. New backend module tree under `logic/rulebook/` (`loader.py`, `adapters.py`, `spans.py`, `types.py`) and `routes/` (`check.py`, `rules.py`).
> 2. A `dispatcher.run_rules(text, disabled_rule_ids, disabled_taxonomies)` that returns `list[Finding]`, sorted by `(start, rule_id)`.
> 3. Three taxonomy adapters:
>    - `regex`: precompile the bare pattern, `finditer` for spans.
>    - `lookup`: execute the trigger code's `check_rule(text, lookup_list)`; for each returned term, recover offsets via `\b<re.escape(term)>\b` (case-insensitive); if no span recoverable, emit a **document-level** finding (`start=0, end=0, document_level=true`).
>    - `structural`: execute `check_rule(text)` inside a restricted-builtins namespace patterned on `logic/sandbox.py`; treat returned items the same way as lookup — span if recoverable, document-level otherwise.
> 4. Rewrite `main.py` so it composes the new routes, keeps CORS open, and **fails loudly on parquet load errors** (no silent fallback to `logic.rules.RULES`).
> 5. New endpoints: `GET /rules` (full catalogue: `rule_id, taxonomy, ui_flag, rule_summary, source_url`), `GET /taxonomies` (counts). `POST /check` accepts `{ text, disabled_rule_ids?, disabled_taxonomies? }` and returns the legacy spec fields plus additive fields (`taxonomy, ui_flag, source_url, document_level`). Keep accepting the legacy `rule_groups` field but ignore it with a single deprecation log line on startup.
> 6. Extend `index.html` (do **not** introduce a build step):
>    - Replace the Rules panel's group checkboxes with a searchable, taxonomy-grouped list of all rules. Per-rule checkbox + per-taxonomy bulk toggle. Persist `octavius.disabledRuleIds` and `octavius.disabledTaxonomies` in `localStorage`. Migrate the legacy `octavius-groups` key on first load.
>    - Findings panel shows `ui_flag` as the headline, `rule_summary` underneath, and links the `rule_id` to `source_url`. Document-level findings render with a "Document" badge instead of scroll-to.
>    - Add `window.OCTAVIUS_API_BASE` override (defaults to the existing constant) so GitHub Pages can point at Render without editing the file.
> 7. Tests under `tests/`:
>    - `test_rulebook_loader.py`: every passing rule compiles; loader is loud on bad input.
>    - `test_adapters_regex.py`, `test_adapters_lookup.py`, `test_adapters_structural.py`: pick 5 rules per taxonomy, run their own `test_fire` examples through the adapter and assert at least one finding; run their `test_no_fire` examples and assert none.
>    - `test_dispatcher.py`: smoke-run all 800 rules over a multi-paragraph document; assert no exceptions and that disabling a taxonomy zeroes its findings.
>    Run `pytest tests/ -v` and make every test pass before you commit.
> 8. Add `pyarrow` to `requirements.txt`. Verify `render.yaml` still works (no edits expected).
> 9. Add `.github/workflows/deploy_pages.yml` that publishes `index.html` to the `gh-pages` branch on push to `main`. Do **not** trigger it from this branch.
> 10. Manually smoke-test locally: `uvicorn main:app --reload`, open `index.html` in a browser, type sentences that should fire one rule from each taxonomy, confirm highlights for `regex`/`lookup` and a document-level entry for `structural`. Note the smoke-test results in your final summary.
>
> **Hard constraints:**
> - Develop only on `claude/create-frontend-interface-gHRNo`. Commit in logical chunks (loader+adapters → dispatcher+routes → frontend → tests → workflow). Push when done. Do **not** open a PR.
> - Do not modify the `src/` pipeline, the `.github/workflows/phase*.yml` files, the `archive/` directory, the `library_of_rules/` content, or `rules_working_draft.jsonl`.
> - Do not introduce any V1.5/V2 features (Aho-Corasick, web workers, embeddings, LLM stages, auth, persistence, React).
> - The published parquet is the runtime source of truth. Do **not** read `rules_working_draft.jsonl` at runtime.
> - Keep the `Finding` field set additive: existing `index.html` users (and any later React port) must keep working without changes.
>
> **Definition of done:** all tests pass, `uvicorn main:app` boots in <5 s with the 800-rule rulebook loaded, the local smoke test highlights findings from each taxonomy, and the branch is pushed. Reply with a short summary listing files added, files changed, test counts, and any deviations from this plan.

---

*End of plan. Save this file (`FRONTEND_BUILD_PLAN.md`) and use the §4 prompt to drive the implementation in a fresh Claude Code session.*
