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

## 4. Prompts to give Claude Code (one per session)

### 4.0 Why split this across sessions

A single prompt for the full build is risky:

- **Context budget.** Reading the spec, the A-synch doc, the plan, `main.py`, `index.html`, `logic/sandbox.py`, sample parquet rows, plus generating the new modules and tests, will eat a large fraction of any single session's context.
- **Verifiability.** Each phase has a clean external check (`python -c "from logic.dispatcher import run_rules; ..."` for S1, `curl localhost:8000/check` for S2, opening `index.html` in a browser for S3). You — the user — should run that check between sessions and only proceed if it passes.
- **Scope discipline.** Three focused sessions are far less likely to drift into "while I'm here, let me also..." territory than one open-ended one.

The work is split into three sessions, each with its own self-contained prompt below. **Run them in order.** Each session commits and pushes its own slice, then stops. Hand the next prompt to a **fresh Claude Code session** — do not continue in the same session, since the value of the split is the context reset.

| Session | Slice | Definition of done |
|---|---|---|
| **S1 — Engine** | `logic/rulebook/` loader + adapters + spans + types, `logic/dispatcher.py`, plus their unit tests. No FastAPI changes, no frontend changes. | `pytest tests/` green, and `python -c "from logic.dispatcher import run_rules; print(len(run_rules('The cat was chased by the dog.')))"` returns a non-empty list. |
| **S2 — Service** | Rewrite `main.py`, add `routes/check.py` and `routes/rules.py`, `pyarrow` in `requirements.txt`. Backend smoke tests via curl. | `uvicorn main:app` boots in <5 s, `curl /rules` returns 800 entries, `curl -X POST /check` returns findings with the new additive fields, legacy `rule_groups` payload still accepted. |
| **S3 — Delivery** | Extend `index.html`, add `.github/workflows/deploy_pages.yml`, end-to-end smoke test in a browser. | One regex highlight, one lookup highlight, and one structural document-level finding visible in the UI; per-rule and per-taxonomy disable persists across reload. Branch pushed. |

If a session hits a real blocker (e.g. a rule's trigger code panics on import), record it in the commit message and stop — do not paper over it. The next session's prompt assumes the previous session's outputs are correct.

---

### 4.1 Session 1 — Engine (loader + adapters + dispatcher)

> **Octavius V1 frontend rebuild — Session 1 of 3 (Engine).**
>
> **Read in this order, then start coding:**
> 1. `FRONTEND_BUILD_PLAN.md` — read §1, §2, and §3 in full. The file layout in §2.2 and the adapter contracts in §2.3 are the authoritative spec for this session.
> 2. `octavius_frontend_spec.md` — context only; no API work in this session.
> 3. `A-synch_SuggestionForApproach.md` — **mandatory**: note the "Important note" at the bottom. V1 scope is **only** rules with `test_result == "pass"`. Do not implement Aho-Corasick, dirty-range tracking, vector embeddings, or LLM stages.
> 4. `CLAUDE.md` — project conventions.
> 5. `logic/engine.py`, `logic/rules.py`, `logic/sandbox.py` — the existing engine layer. Re-use the sandbox pattern; do not duplicate it.
> 6. `src/run_tests.py` — confirms the trigger-code calling conventions per taxonomy (`check_rule(text, lookup_list)` for lookup, `check_rule(text)` for structural, bare regex string for regex).
> 7. Inspect a few rows of `published/rulebook.parquet` (e.g. `python -c "import pyarrow.parquet as pq; t = pq.read_table('published/rulebook.parquet'); print(t.schema); print(t.to_pandas().head(2).to_dict())"`).
>
> **Branch:** Develop on `claude/create-frontend-interface-gHRNo`. It already exists; check it out.
>
> **Scope of this session — engine only. Do NOT touch `main.py`, `index.html`, or any FastAPI/route file.**
>
> **Deliverables:**
> 1. `logic/rulebook/__init__.py`, `logic/rulebook/types.py` (`CompiledRule` TypedDict matching §2.3).
> 2. `logic/rulebook/loader.py`:
>    - Reads `published/rulebook.parquet` via `pyarrow`.
>    - Filters `test_result == "pass"` → expect 801 rules (415 lookup, 124 regex, 262 structural). Log the counts at INFO level.
>    - Calls the right adapter per taxonomy and returns `list[CompiledRule]`.
>    - Fails loudly (raises) on missing parquet, unknown taxonomy, or any rule whose trigger code fails to compile. Never silently swallow.
> 3. `logic/rulebook/spans.py`:
>    - `find_term_spans(text: str, term: str) -> list[tuple[int, int]]` using `\b` + `re.escape(term)` + `\b`, case-insensitive.
> 4. `logic/rulebook/adapters.py` — three pure functions, each `dict -> CompiledRule`:
>    - `compile_regex(rule)` — precompile pattern with `re.IGNORECASE`; `check(text)` returns one Finding per `finditer` match.
>    - `compile_lookup(rule)` — `compile()` the trigger code once into a restricted namespace (mirror `logic/sandbox._SANDBOX_GLOBALS`); the cached `check_rule` is invoked with `(text, lookup_list)`; for each returned term, attach offsets via `spans.find_term_spans` (one Finding per occurrence). If a returned term yields no span, emit a single document-level Finding (`start=0, end=0, document_level=True`).
>    - `compile_structural(rule)` — same compile-once approach; call `check_rule(text)`; treat each returned item as lookup (span if recoverable, document-level otherwise).
>    - The Finding produced by every adapter must include: `start_char`, `end_char`, `rule_id`, `taxonomy`, `ui_flag`, `rule_summary`, `source_url`, `severity`, `document_level`. Default `severity` is `"warning"`; if `discretionary_flag == True`, use `"info"`.
> 5. `logic/dispatcher.py`:
>    - On import, calls the loader once and caches the rule list at module scope.
>    - `run_rules(text: str, disabled_rule_ids: set[str] | None = None, disabled_taxonomies: set[str] | None = None) -> list[Finding]` — runs every enabled rule sequentially; sorts findings by `(start_char, rule_id)`; never raises on a single rule failure (catch, log, continue — but the loader has already validated the rule list, so this is a defence-in-depth measure).
> 6. Add `pyarrow` to `requirements.txt`.
> 7. Tests under `tests/`:
>    - `test_rulebook_loader.py`: assert 801 rules load; assert taxonomy counts (415/124/262); assert loader raises on a tampered parquet path.
>    - `test_adapters_regex.py`, `test_adapters_lookup.py`, `test_adapters_structural.py`: for 5 rules per taxonomy, run each rule's own `test_fire` examples through the adapter and assert ≥1 finding; run `test_no_fire` examples and assert 0 findings. Use parametrize.
>    - `test_dispatcher.py`: smoke-run all 800 rules over a paragraph that includes at least one trigger phrase per taxonomy; assert no exceptions; assert `disabled_taxonomies={"structural"}` zeroes structural findings.
>
> **Run `pytest tests/ -v` and make every test pass before committing.**
>
> **Hard constraints:**
> - Do not modify `main.py`, `index.html`, `routes/`, `frontend/`, `app.py`, `pages/`, `src/`, `archive/`, `library_of_rules/`, or `rules_working_draft.jsonl`.
> - Do not introduce future-state features (Aho-Corasick, web workers, embeddings, LLM, spaCy/Doc rules — there are zero passing spaCy rules, so do not branch for them).
> - The published parquet is the runtime source of truth.
> - Keep `logic/engine.py` and `logic/rules.py` working as they are; the legacy single-rule path must still pass `pytest tests/test_engine.py`.
>
> **Commit and push:**
> - One or two commits is fine. Push to `claude/create-frontend-interface-gHRNo` with `git push -u origin claude/create-frontend-interface-gHRNo`.
> - Do **not** open a PR.
>
> **Definition of done — reply with this exact summary block:**
> ```
> S1 ENGINE — DONE
> rules loaded: <count> (<lookup>/<regex>/<structural>)
> tests:        <pass> passed, <fail> failed
> files added:  <list>
> files changed:<list>
> deviations:   <none | bullets>
> next:         hand off to S2 (Service)
> ```

---

### 4.2 Session 2 — Service (FastAPI routes)

> **Octavius V1 frontend rebuild — Session 2 of 3 (Service). S1 (Engine) is already complete on this branch — verify before extending.**
>
> **Read in this order:**
> 1. `FRONTEND_BUILD_PLAN.md` — re-read §2.4 (API contract) and §3 steps 4–5.
> 2. `octavius_frontend_spec.md` — §5 (API contract) is binding for backwards compatibility.
> 3. The S1 outputs on this branch: `logic/rulebook/`, `logic/dispatcher.py`. Confirm they import cleanly and that `pytest tests/test_rulebook_loader.py tests/test_adapters_*.py tests/test_dispatcher.py -v` is green. If anything is broken, fix it before continuing.
> 4. The current `main.py` and `index.html`, especially the existing `/check` and `/groups` shapes — `index.html` will keep talking to this backend until S3 ships the new frontend, so the old request shape must keep working.
>
> **Branch:** continue on `claude/create-frontend-interface-gHRNo`. Pull the latest first.
>
> **Scope of this session — backend service only. Do NOT touch `index.html` or any frontend file.**
>
> **Deliverables:**
> 1. `routes/__init__.py`, `routes/check.py`, `routes/rules.py`:
>    - `GET /rules` returns the full catalogue from the dispatcher's cached rule list — `rule_id, taxonomy, ui_flag, rule_summary, source_url, severity` per entry.
>    - `GET /taxonomies` returns `[{"id": "lookup", "rule_count": 415}, ...]`.
>    - `POST /check` accepts a Pydantic `CheckRequest` with `text: str`, optional `disabled_rule_ids: list[str]`, optional `disabled_taxonomies: list[str]`, and the legacy optional `rule_groups: list[str]` (accepted but ignored, with a single startup deprecation log).
>    - `POST /check` calls `dispatcher.run_rules` and returns objects shaped as: `{rule_id, group, taxonomy, ui_flag, rule_summary, source_url, message, start, end, severity, document_level}`. `group` mirrors `taxonomy` for legacy `index.html` compatibility. `message` is the `ui_flag` (so legacy frontends still surface something readable). `start`/`end` are the Finding's `start_char`/`end_char`.
> 2. Rewrite `main.py`:
>    - Compose the routes from `routes/`.
>    - Keep CORS `allow_origins=["*"]` for now (the spec allows narrowing later).
>    - On startup: import `logic.dispatcher` (forces the loader to run); on parquet failure, **fail boot** rather than starting in a broken state.
>    - Keep the legacy `GET /groups` route as a thin alias that returns the same shape `index.html` currently consumes (taxonomy id + name + rule_count) so the unmodified frontend keeps loading until S3.
>    - Remove the now-obsolete category-based logic that read `logic.rules.RULES` for `/groups` — but keep `logic/rules.py` itself untouched (S1 invariant).
> 3. New tests under `tests/`:
>    - `test_routes_rules.py`: `GET /rules` returns 800 entries with the expected fields. `GET /taxonomies` returns three taxonomies with correct counts.
>    - `test_routes_check.py`: `POST /check` with a sentence that fires one rule per taxonomy returns a finding for each; disabled_rule_ids removes a specific rule from the response; disabled_taxonomies removes a whole taxonomy; legacy `rule_groups` payload is accepted without error.
>    Use `fastapi.testclient.TestClient`. Run `pytest tests/ -v` and make every test pass.
> 4. **Manual smoke test** (record exact output in your final summary):
>    - `uvicorn main:app --port 8000` in the background.
>    - `curl -s localhost:8000/rules | python -m json.tool | head -40`.
>    - `curl -s localhost:8000/taxonomies`.
>    - `curl -s -X POST localhost:8000/check -H 'Content-Type: application/json' -d '{"text":"The meeting is on Tue and Thu. The cat was chased by the dog."}'`.
>    - Stop the server.
>
> **Hard constraints:**
> - Do not modify S1 outputs except to fix bugs you discover. Note any such fix in the summary.
> - Do not modify `index.html`, `frontend/`, `app.py`, `pages/`, `src/`, `archive/`, `library_of_rules/`, or `rules_working_draft.jsonl`.
> - The Finding field set is additive — never remove fields the legacy frontend reads (`rule_id`, `group`, `message`, `start`, `end`, `severity`).
>
> **Commit and push:** one commit per logical chunk (routes → main.py rewrite → tests). Push to `claude/create-frontend-interface-gHRNo`. Do not open a PR.
>
> **Definition of done — reply with this exact summary block:**
> ```
> S2 SERVICE — DONE
> uvicorn boot:    <seconds>
> /rules count:    <n>
> /taxonomies:     <list>
> /check sample:   <one-line excerpt of the smoke-test response>
> tests:           <pass> passed, <fail> failed
> files added:     <list>
> files changed:   <list>
> S1 fixes:        <none | bullets>
> deviations:      <none | bullets>
> next:            hand off to S3 (Delivery)
> ```

---

### 4.3 Session 3 — Delivery (frontend + deploy)

> **Octavius V1 frontend rebuild — Session 3 of 3 (Delivery). S1 (Engine) and S2 (Service) are already complete on this branch — verify before extending.**
>
> **Read in this order:**
> 1. `FRONTEND_BUILD_PLAN.md` — re-read §2.5 (frontend changes) and §3 steps 7–10.
> 2. `octavius_frontend_spec.md` — §6 (frontend behaviour) and §7 (build plan) are binding.
> 3. Current `index.html` end-to-end. The existing overlay-highlight rendering, debounce, AbortController, tabbed sidebar, and tooltip all stay. You are extending, not replacing.
> 4. The S2 outputs: `routes/`, the new `main.py`. Confirm `pytest tests/ -v` is green and that `uvicorn main:app` boots locally before changing the frontend.
>
> **Branch:** continue on `claude/create-frontend-interface-gHRNo`. Pull the latest first.
>
> **Scope of this session — frontend, deploy workflow, and end-to-end verification only. Do NOT change backend code unless you find a bug; if you do, note it in the summary.**
>
> **Deliverables:**
> 1. Extend `index.html` (single file, no build step):
>    - **API_BASE override.** At the top of the script: `const API_BASE = window.OCTAVIUS_API_BASE || '<existing constant>';` so a `<script>window.OCTAVIUS_API_BASE = '...'</script>` injected by the GitHub Pages build can retarget the backend without editing the HTML.
>    - **Rules panel.** Replace the current taxonomy-checkbox UI with: a search input (filters by `rule_id` / `ui_flag` substring, case-insensitive), three collapsible sections (one per taxonomy) each with a header-level "disable all in this taxonomy" toggle, and per-rule checkboxes inside each section. Source the catalogue from `GET /rules` and the counts from `GET /taxonomies`.
>    - **State persistence.** `localStorage["octavius.disabledRuleIds"]` and `localStorage["octavius.disabledTaxonomies"]`, each a JSON-stringified array. On load, if the legacy `octavius-groups` key exists, migrate it (treat each old "group" as a taxonomy disable if the user had unchecked it) and remove the legacy key.
>    - **Request shape.** `POST /check` body becomes `{ text, disabled_rule_ids: [...], disabled_taxonomies: [...] }`. Drop `rule_groups`.
>    - **Findings panel.** Each finding card shows `ui_flag` (headline), `rule_summary` (secondary), and a small "View source" link to `source_url` (target=`_blank`, `rel="noopener"`). Document-level findings (`document_level === true`) render with a "Document" pill instead of a click-to-scroll behaviour and do not draw an inline highlight.
>    - **Performance.** With 800 rules, do not render 800 raw DOM checkboxes naively if it makes the panel laggy. Acceptable shortcuts: render only the currently-filtered subset, or virtualise. Pick the simplest one that keeps interaction snappy.
> 2. `.github/workflows/deploy_pages.yml`:
>    - Triggers on `push` to `main` only — **not** on this branch.
>    - Copies `index.html` (and any sibling assets it references; right now it's standalone) to a `gh-pages` branch using `peaceiris/actions-gh-pages` or equivalent.
>    - Sets `window.OCTAVIUS_API_BASE` injection via a workflow secret `RENDER_API_BASE` (default to the existing constant if the secret is unset).
> 3. **End-to-end smoke test** (record verbatim in your final summary):
>    - Boot the backend: `uvicorn main:app --port 8000` in the background.
>    - Open `index.html` in a browser (`xdg-open` or `open`, or just print the file:// URL).
>    - Type a single paragraph that contains: a known regex trigger, a known lookup trigger (e.g. "The meeting is on Tue and Thu."), and a known structural trigger.
>    - Confirm: ≥1 inline highlight from regex; ≥1 inline highlight from lookup; ≥1 document-level entry from structural; the findings panel shows `ui_flag` headlines and `View source` links; toggling a rule's checkbox immediately removes it from the next `/check` response; reloading the page preserves the disabled state.
>    - Stop the server.
>    - If a browser is genuinely unavailable, fall back to `curl` against the running backend with the new payload shape and document that fallback explicitly.
>
> **Hard constraints:**
> - Do not introduce a build step. `index.html` must remain a single deployable file.
> - Do not modify backend code unless fixing a bug; note any such fix in the summary.
> - Do not introduce React, Vite, web workers, embeddings, or any V1.5+ feature.
> - Do not modify `src/`, `.github/workflows/phase*.yml`, `archive/`, `library_of_rules/`, `rules_working_draft.jsonl`, `app.py`, `pages/`, or `frontend/`.
> - The deploy workflow must trigger only on `main`, never on the build branch.
>
> **Commit and push:** one commit per logical chunk (frontend extension → deploy workflow → smoke-test notes if any). Push to `claude/create-frontend-interface-gHRNo`. Do not open a PR — the user will request one separately.
>
> **Definition of done — reply with this exact summary block:**
> ```
> S3 DELIVERY — DONE
> regex highlight:      <observed | n/a + reason>
> lookup highlight:     <observed | n/a + reason>
> structural doc-level: <observed | n/a + reason>
> persistence verified: <yes | no + reason>
> deploy workflow:      <path, trigger summary>
> files added:          <list>
> files changed:        <list>
> S1/S2 fixes:          <none | bullets>
> deviations:           <none | bullets>
> ready for PR:         <yes | no + reason>
> ```

---

*End of plan. Save this file (`FRONTEND_BUILD_PLAN.md`) as the source of truth. Run §4.1, §4.2, §4.3 in order, each in a fresh Claude Code session, verifying the prior session's output before the next begins.*
