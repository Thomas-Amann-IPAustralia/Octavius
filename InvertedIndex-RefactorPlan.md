# Inverted-Index Refactor — Master Plan

This document is the complete, self-contained plan. Each Phase prompt is paste-ready; the friend's design feedback has been folded in throughout (renamed `MASK_*` → `EXEMPT_*`, added `ANCESTOR_*` and `REL_*`, dropped thresholds from feature names, added `mutation_class` as a rule column, deferred `COUNT_*` / `COST_*` / additional `PATTERN_*` with explicit revisit triggers).

---

# 1. Overview

```
Phase 0  Foundations             — schema, vocab, decision log, dead-code sweep    ½ day
Phase 1  Preprocessing layer     — markdown segmentation, ancestry, exemptions,    1 day
                                   sentence cache, counts
Phase 2  Feature extractor       — spaCy + regex + structural + relations          1–2 days
Phase 3  Authoring batch         — LLM run for required_features + mutation_class  ½ day + batch wait
Phase 4  Indexed dispatcher      — inverted index, dedup, firing budget, env flag  1–2 days
Phase 5  Corpus + telemetry      — calibration corpus, scoring, precision events   1 day
Phase 6  Frontend + cutover      — React per-mutation-class actions, default flip  1 day
```

Each phase = one Claude Code session = one branch + one PR into the long-lived integration branch.

---

# 2. Cross-cutting decisions

## 2.1 Branching

- **Integration branch:** `claude/inverted-index-refactor` (created from `main`).
- **Per-phase branch:** `claude/iir-phase-{N}-{slug}` → PR into integration branch.
- **Final merge:** integration branch → `main` after Phase 6 verification.

## 2.2 Decision log

Create `docs/REFACTOR_LOG.md` in Phase 0 and append a section at the end of every phase. Format below (Phase 0 prompt seeds it).

## 2.3 Migration flag

- `OCTAVIUS_DISPATCHER` env var, values `legacy | indexed`.
- `routes/check.py` reads it at startup and resolves the dispatcher module.
- Default `legacy` until Phase 6 flips it.
- Both dispatchers must satisfy `run_rules(text, disabled_rule_ids=None, disabled_taxonomies=None) -> list[Finding]`.

## 2.4 Architectural rules (enforced in every phase)

1. **No thresholds in feature names.** Forbidden suffixes: `_25P`, `_GE_3`, `_PLUS`, any digits at the end. Thresholds live in extractor parameters. `validate_feature` rejects any name matching `r"_(GE|GT|LT|LE)?_?\d+P?$"`.
2. **`EXEMPT_*` features may only appear in a rule's `none_of` slot.** Putting them in `all_of`/`any_of` is meaningless ("apply this rule only on URLs we masked out"). Rejected at LLM-batch validation time and again at dispatcher load time.
3. **No new dependencies without justification in commit message.** Polars and DuckDB are explicitly out of scope at this rule count.
4. **No bare `except`, no swallowed errors, no silent fallbacks** other than the documented `required_features=None` → "always retrieve" path.
5. **`pytest tests/ -v` must pass at every commit.**
6. **One namespace.** No `OBS_*`/`INTERP_*` two-layer split. Features describe observations *or* derived booleans; thresholds are policy on the extractor side.

## 2.5 Feature vocabulary (frozen at Phase 0)

```
ZONE_*     (segment's own kind, from markdown tree)
  ZONE_HEADING, ZONE_PARAGRAPH, ZONE_LIST_BULLET, ZONE_LIST_NUMBERED,
  ZONE_TABLE_CELL, ZONE_BLOCKQUOTE, ZONE_CODE_FENCE, ZONE_INLINE_CODE,
  ZONE_FOOTNOTE, ZONE_REFERENCE_LIST

ANCESTOR_*  (segment lineage)
  ANCESTOR_BLOCKQUOTE, ANCESTOR_LIST, ANCESTOR_TABLE,
  ANCESTOR_FOOTNOTE, ANCESTOR_HEADING_SECTION

HAS_*       (lexical / token observations)
  HAS_CARDINAL, HAS_ORDINAL, HAS_PERCENT, HAS_CURRENCY, HAS_DATE,
  HAS_TIME, HAS_URL, HAS_EMAIL, HAS_ABBREVIATION, HAS_ACRONYM,
  HAS_ROMAN_NUMERAL, HAS_EM_DASH, HAS_EN_DASH, HAS_HYPHEN,
  HAS_COLON, HAS_SEMICOLON, HAS_STRAIGHT_QUOTE, HAS_CURLY_QUOTE,
  HAS_DOUBLE_SPACE, HAS_PARENTHESES

LING_*      (linguistic, from spaCy; thresholds in extractor params)
  LING_PASSIVE_VOICE, LING_MODAL_VERB, LING_FIRST_PERSON,
  LING_SECOND_PERSON, LING_IMPERATIVE, LING_PROPER_NOUN,
  LING_TITLE_CASE_SEQUENCE, LING_ALL_CAPS_TOKEN, LING_NEGATION,
  LING_LONG_SENTENCE

PATTERN_*   (deliberately small starter set; Phase 3 surfaces gaps)
  PATTERN_NUMERIC_RANGE, PATTERN_CITATION_PARENS,
  PATTERN_HEADING_TITLE_CASE, PATTERN_HEADING_SENTENCE_CASE,
  PATTERN_BULLET_ENDS_WITH_PERIOD, PATTERN_REGNAL_NUMERAL_SHAPE

REL_*       (cross-segment relations, tightly scoped)
  REL_BULLET_AFTER_COLON, REL_ACRONYM_DEFINED_ON_FIRST_USE,
  REL_HEADING_FOLLOWED_BY_LIST, REL_CITATION_AFTER_QUOTE

APS_*       (domain-specific lookup)
  APS_LEGISLATION_REFERENCE, APS_DEPARTMENT_NAME,
  APS_MINISTERIAL_TITLE, APS_DATE_LONGFORM, APS_COMMONWEALTH_ENTITY

EXEMPT_*    (negative; only in `none_of`)
  EXEMPT_URL, EXEMPT_FILEPATH, EXEMPT_BRANCHNAME, EXEMPT_IDENTIFIER,
  EXEMPT_ENV_VAR, EXEMPT_PRODUCT_NAME, EXEMPT_MENTION_OR_HASHTAG,
  EXEMPT_CODE_SNIPPET, EXEMPT_QUOTED_CONTENT

DOC_*       (document-scope booleans only; numeric counts live on
             PreprocessedDoc.counts, not as features)
  DOC_HAS_HEADINGS, DOC_HAS_LISTS, DOC_HAS_CITATIONS, DOC_LANGUAGE_EN
```

## 2.6 Schema additions (parquet)

| Column | Type | Set by | Notes |
|---|---|---|---|
| `required_features` | `struct<all_of: list<string>, any_of: list<string>, none_of: list<string>>` | Phase 3 | Null = "always retrieve" |
| `mutation_class` | `string` (one of `safe_replace | requires_rewrite | human_review`) | Phase 3 | Null = frontend renders fallback "Acknowledge" button |

## 2.7 Schema additions (Python types)

- `Finding`: add optional `grouped_rules: list[str] | None` and `mutation_class: str | None`.
- `CompiledRule`: add optional `required_features: FeatureRequirements | None` and `mutation_class: str | None`.
- New TypedDict `FeatureRequirements` with `all_of`, `any_of`, `none_of` (each `list[str]`).
- `PreprocessedDoc.counts: dict[str, int]` (added in Phase 1; consumed by no rule yet — reserved for the future `min_count` requirement type).

## 2.8 Deferred features (revisit triggers)

These appear as a fixed section in `REFACTOR_LOG.md`:

- **`COUNT_*` family.** Revisit if Phase 5 telemetry shows ranking failures that boolean count thresholds would fix. Replacement plan: integer counts already exist in `PreprocessedDoc.counts`; add a `min_count: dict[str, int]` slot to `FeatureRequirements`.
- **`COST_*` execution classes.** Revisit if Phase 4 latency tests miss the 200 ms p50 target. Existing `taxonomy` column is a usable proxy until then.
- **Additional `PATTERN_*` features.** Add as Phase 3's batch surfaces gaps in its responses.
- **General relational sub-language.** Only the four `REL_*` features ship in Phase 0; expand only if telemetry justifies it.

## 2.9 Latency budget

700 ms p95 hard cap, 200 ms p50 target. Each phase reports measured cost in the log.

---

# 3. Phase prompts

Paste each into a fresh Claude Code session.

---

## Phase 0 — Foundations

```text
Task: lay the groundwork for the inverted-index refactor of the Octavius
linter.

Context. Octavius is a plain-language linter (FastAPI backend in main.py +
routes/, React frontend in frontend/, ~801 rules in
published/rulebook.parquet loaded via logic/dispatcher.py). We are starting
a multi-phase refactor that replaces the current "run every rule against
every text" dispatch with a feature-based inverted index. This phase ships
ZERO behaviour change — it is foundations only.

Branch. Create `claude/iir-phase-0-foundations` off the integration branch
`claude/inverted-index-refactor` (create the integration branch off main if
it does not yet exist). Open a PR back to the integration branch.

Deliverables.

1. Create `docs/REFACTOR_LOG.md` with this template:

       # Inverted-Index Refactor — Decision Log

       ## Phase 0 — Foundations (YYYY-MM-DD)
       ### Shipped
       ### Deferred
       ### Surprises
       ### Follow-ups for next phase

       ## Deferred features (revisit triggers)
       - COUNT_* family: revisit if Phase 5 telemetry shows ranking
         failures that boolean count thresholds would fix. Replacement
         plan = integer counts in PreprocessedDoc.counts plus a
         `min_count` slot on FeatureRequirements.
       - COST_* execution classes: revisit if Phase 4 latency tests miss
         the 200 ms p50 target.
       - Additional PATTERN_* features: add as Phase 3's batch surfaces
         gaps in its responses.
       - General relational sub-language: only the four REL_* features
         ship in Phase 0; expand if telemetry justifies it.

   Append actual notes under the Phase 0 headings at the end of the phase.

2. Create `logic/features/__init__.py` and `logic/features/vocabulary.py`.
   `vocabulary.py`:
   - Defines the feature vocabulary as a `Final[frozenset[str]]`.
   - Exports `validate_feature(name: str) -> None` raising `ValueError`
     on unknown names AND on names matching the regex
     `r"_(GE|GT|LT|LE)?_?\d+P?$"` (regression guard for the
     no-thresholds-in-names rule).
   - Module docstring states the two architectural rules:
     (a) thresholds must NEVER appear in feature names;
     (b) numeric counts live on `PreprocessedDoc.counts: dict[str, int]`
     (added in Phase 1) and are not features in this phase.

   Vocabulary contents — copy verbatim:

       # Structural — segment's own kind
       ZONE_HEADING, ZONE_PARAGRAPH, ZONE_LIST_BULLET, ZONE_LIST_NUMBERED,
       ZONE_TABLE_CELL, ZONE_BLOCKQUOTE, ZONE_CODE_FENCE, ZONE_INLINE_CODE,
       ZONE_FOOTNOTE, ZONE_REFERENCE_LIST

       # Segment lineage
       ANCESTOR_BLOCKQUOTE, ANCESTOR_LIST, ANCESTOR_TABLE,
       ANCESTOR_FOOTNOTE, ANCESTOR_HEADING_SECTION

       # Lexical observations
       HAS_CARDINAL, HAS_ORDINAL, HAS_PERCENT, HAS_CURRENCY, HAS_DATE,
       HAS_TIME, HAS_URL, HAS_EMAIL, HAS_ABBREVIATION, HAS_ACRONYM,
       HAS_ROMAN_NUMERAL, HAS_EM_DASH, HAS_EN_DASH, HAS_HYPHEN,
       HAS_COLON, HAS_SEMICOLON, HAS_STRAIGHT_QUOTE, HAS_CURLY_QUOTE,
       HAS_DOUBLE_SPACE, HAS_PARENTHESES

       # Linguistic — thresholds live in extractor parameters
       LING_PASSIVE_VOICE, LING_MODAL_VERB, LING_FIRST_PERSON,
       LING_SECOND_PERSON, LING_IMPERATIVE, LING_PROPER_NOUN,
       LING_TITLE_CASE_SEQUENCE, LING_ALL_CAPS_TOKEN, LING_NEGATION,
       LING_LONG_SENTENCE

       # Multi-token patterns — deliberately small starter set
       PATTERN_NUMERIC_RANGE, PATTERN_CITATION_PARENS,
       PATTERN_HEADING_TITLE_CASE, PATTERN_HEADING_SENTENCE_CASE,
       PATTERN_BULLET_ENDS_WITH_PERIOD, PATTERN_REGNAL_NUMERAL_SHAPE

       # Cross-segment relations — tightly scoped
       REL_BULLET_AFTER_COLON, REL_ACRONYM_DEFINED_ON_FIRST_USE,
       REL_HEADING_FOLLOWED_BY_LIST, REL_CITATION_AFTER_QUOTE

       # Domain-specific lookups
       APS_LEGISLATION_REFERENCE, APS_DEPARTMENT_NAME,
       APS_MINISTERIAL_TITLE, APS_DATE_LONGFORM, APS_COMMONWEALTH_ENTITY

       # Exemptions — only used in a rule's `none_of` slot
       EXEMPT_URL, EXEMPT_FILEPATH, EXEMPT_BRANCHNAME, EXEMPT_IDENTIFIER,
       EXEMPT_ENV_VAR, EXEMPT_PRODUCT_NAME, EXEMPT_MENTION_OR_HASHTAG,
       EXEMPT_CODE_SNIPPET, EXEMPT_QUOTED_CONTENT

       # Document-scope booleans only
       DOC_HAS_HEADINGS, DOC_HAS_LISTS, DOC_HAS_CITATIONS, DOC_LANGUAGE_EN

   Also export `EXEMPT_FEATURES: Final[frozenset[str]]` containing the
   `EXEMPT_*` subset, for downstream validation that they only appear in
   `none_of`.

3. Extend `logic/rulebook/types.py`:
   - Add `grouped_rules: list[str] | None` to `Finding` (optional, default
     None).
   - Add `mutation_class: Literal["safe_replace", "requires_rewrite",
     "human_review"] | None` to `Finding` (optional, default None — Phase
     4 will copy this from the rule onto each finding so the frontend can
     render the right action button).
   - Add `required_features: dict[str, list[str]] | None` to
     `CompiledRule` (optional, default None — Phase 3 populates).
   - Add `mutation_class` to `CompiledRule` with the same Literal type
     (optional, default None — Phase 3 populates).
   - Add a TypedDict `FeatureRequirements` with keys `all_of`, `any_of`,
     `none_of`, each `list[str]`.

4. Extend `logic/rulebook/loader.py` to read `required_features` and
   `mutation_class` parquet columns when present, passing them through to
   `CompiledRule`. Missing columns default to `None` (do not fail).

5. Delete the stale Streamlit path:
   - Delete `app.py`, `logic/engine.py`, `logic/rules.py`,
     `octavius_component.py`, and `pages/` if it only contains Streamlit
     pages.
   - Update `README.md` and `CLAUDE.md` to remove references to
     `streamlit run app.py`. The runtime entry point is now
     `uvicorn main:app`.
   - Search the repo for remaining imports of deleted modules and either
     remove or migrate them onto `logic.dispatcher`. `tests/test_engine.py`
     may need to be deleted or rewritten; document the choice.

6. Add `OCTAVIUS_DISPATCHER` env-flag plumbing to `routes/check.py`:
   - Read at module load.
   - For now both `legacy` and `indexed` resolve to `logic.dispatcher`.
     Log a WARNING if `indexed` is requested in Phase 0.
   - Add a unit test asserting the resolution logic.

Acceptance.

- `pytest tests/ -v` passes.
- `uvicorn main:app` boots; `POST /check` with the noisy example
  ("Step 1 — Merge this branch to main\nThe changes just pushed need to be
  on main before Render deploys them.") still returns its current ~33
  findings (no behaviour change).
- These imports work:
      from logic.features.vocabulary import (
          ZONE_PARAGRAPH, ANCESTOR_BLOCKQUOTE, EXEMPT_URL,
          REL_BULLET_AFTER_COLON, EXEMPT_FEATURES, validate_feature,
      )
- `validate_feature("NOT_A_REAL_FEATURE")` raises ValueError.
- `validate_feature("LING_LONG_SENTENCE_25P")` raises ValueError.
- `grep -r "streamlit" --include="*.py"` returns nothing in runtime
  paths (`archive/` matches are fine).

Constraints. No preprocessing, feature extractor, or indexed dispatcher
in this phase. No feature names containing numeric thresholds.

Reporting. Append Phase 0 entry to `docs/REFACTOR_LOG.md`. PR.
```

---

## Phase 1 — Preprocessing layer

```text
Task: build the preprocessing layer that will feed the future feature
extractor.

Context. Phase 0 shipped. Vocabulary is frozen in
`logic/features/vocabulary.py`. `Finding` has `grouped_rules` and
`mutation_class`. `CompiledRule` has `required_features` and
`mutation_class`. Legacy dispatcher unchanged. This phase adds
preprocessing as a standalone module — NOT yet wired into the dispatcher
(that's Phase 4).

Branch. `claude/iir-phase-1-preprocessing` off integration branch.

Deliverables.

1. Add `markdown-it-py` to requirements.txt (pinned).

2. Create `logic/preprocess.py` exporting:

       @dataclass
       class Segment:
           kind: Literal["heading", "paragraph", "list_bullet",
                         "list_numbered", "blockquote", "code_fence",
                         "inline_code", "table_cell", "footnote",
                         "reference_list"]
           text: str
           offset: int                 # char offset back into original
           lintable: bool              # False for code_fence / inline_code
           ancestors: list[str]        # outermost → immediate parent kind,
                                       # used by Phase 2 for ANCESTOR_*

       @dataclass
       class PreprocessedDoc:
           original: str
           masked: str                 # same length as original
           segments: list[Segment]
           mask_map: list[tuple[int, int, str, str]]
                                       # (start, end, original,
                                       #  exemption_kind) where
                                       # exemption_kind is one of:
                                       # "url" | "filepath" | "branchname"
                                       # | "identifier" | "env_var"
                                       # | "product_name"
                                       # | "mention_or_hashtag"
                                       # | "code_snippet"
                                       # | "quoted_content"
           counts: dict[str, int]      # see deliverable 6
           sentence_count: int
           has_structure: bool
           language: str
           spacy_doc: Any              # cached for Phase 2

       def preprocess(text: str) -> PreprocessedDoc: ...

   The `mask_map` exemption_kind values map 1:1 to `EXEMPT_*` features in
   Phase 2. Internally we still mask bytes (the field is named `mask_map`
   for accuracy of the implementation), but the kind names are the
   semantic exemption category.

3. Markdown-aware segmentation via markdown-it-py. Walk the token stream
   and:
   - Emit a Segment per heading / paragraph / list item / blockquote /
     code fence / table cell / footnote / reference list.
   - Track ancestors during the walk; populate `Segment.ancestors` with
     the chain of containing zone kinds.
   - Code fences and inline code are emitted as Segments with
     `lintable=False`.
   - Blockquote bodies emit child Segments with their own `kind` (e.g.
     a paragraph inside a blockquote → kind="paragraph",
     ancestors=["blockquote"]).

4. Token masking. Replace each non-prose region with a same-length run of
   the sentinel `\uE000`. Patterns and their exemption_kinds (from the
   vocabulary; mask_map kinds drop the EXEMPT_ prefix and lowercase):
   - url:                `https?://\S+`, `www\.\S+`
   - filepath:           absolute and relative paths, common file
                         extensions
   - branchname:         `main`, `master`, `develop`, `feature/...`,
                         `release/...`, `hotfix/...`
   - identifier:         snake_case (≥2 underscores), camelCase (≥3
                         chars), dotted.identifiers
   - env_var:            `[A-Z][A-Z0-9_]{2,}` not at sentence start
   - product_name:       `Title-Case-Hyphenated` chains length ≥2
   - mention_or_hashtag: `@\w+`, `#\w+`
   - code_snippet:       backticked text, lines starting `$ ` or `>>> `
   - quoted_content:     paired straight (`"…"`, `'…'`) or curly
                         (`"…"`, `'…'`) quotes inside paragraphs

   Each mask preserves byte offsets exactly:
   `len(masked) == len(original)`.

5. Sentence counting via spaCy on unmasked paragraph segments (not
   headings). Cache the spaCy Doc on the result so Phase 2 reuses it.
   Set `sentence_count` and `has_structure` (True iff any heading / list
   / fence exists).

6. `counts: dict[str, int]` populated via lightweight regex counting on
   the original text. Required keys: `sentence`, `cardinal`, `acronym`,
   `proper_noun_likely`, `paren_pair`. These are reserved for a future
   `min_count` requirement type and are NOT consumed by any rule in this
   phase. Document this clearly in the docstring.

7. Language detection. Use `langdetect` (or a regex-based ASCII heuristic
   if you'd rather avoid the dep — justify in commit message). Default
   to "en" on any failure; log INFO. Never raise.

8. Sentence-hash cache in `logic/sentence_cache.py`:

       class SentenceCache:
           def __init__(self, max_entries: int = 10_000): ...
           def get_or_compute(self, sentence: str,
                              compute: Callable[[str], list[Finding]]
                             ) -> list[Finding]: ...

   FIFO eviction, SHA-256 truncated to 16 hex chars as key.
   Process-local; document lifecycle.

Tests (`tests/test_preprocess.py`).

- `test_offsets_preserved`: 20 hand-crafted inputs;
  `len(masked) == len(original)` and unmasked chars match.
- `test_code_fence_segments_unlintable`: fenced block → kind="code_fence",
  lintable=False.
- `test_inline_code_masked`: backticked region in mask_map with
  exemption_kind="code_snippet".
- `test_quoted_content_masked`: smart and straight quotes both produce
  mask_map entries with kind="quoted_content".
- `test_url_filepath_branchname_masking`: each pattern produces the right
  kind.
- `test_ancestors_populated`: a paragraph inside a blockquote inside a
  list item has ancestors=["list_bullet", "blockquote"] (or the correct
  shape per your walker).
- `test_step_1_example_segments`: the noisy example produces one
  paragraph segment with `lintable=True`; `Render`, `main`, and any
  branch-shaped tokens appear in mask_map.
- `test_counts_populated`: counts dict has all required keys and each is
  ≥0.
- `test_sentence_cache_fifo`: insert 10_001 sentences; first is evicted.
- `test_language_detection_default_en`: empty input returns "en".
- `tests/test_preprocess_perf.py`: 500-word document preprocesses in
  <50 ms.

Acceptance.

- `pytest tests/ -v` passes.
- `python -c "from logic.preprocess import preprocess;
   d = preprocess('# H\nFoo bar.\n');
   print(d.segments, d.counts)"` runs.

Constraints. Do not modify the dispatcher, adapters, loader, or rule
trigger code. Preprocessing is standalone in this phase.

Reporting. Append Phase 1 entry to `docs/REFACTOR_LOG.md` — especially
masking edge cases punted on. PR.
```

---

## Phase 2 — Feature extractor

```text
Task: build the deterministic feature extractor that maps a
PreprocessedDoc to a FeatureSet over the frozen vocabulary.

Context. Phase 1 produced `logic/preprocess.py` with `PreprocessedDoc`
including `segments` (each carrying `ancestors`), `mask_map` (exemption
kinds), `counts`, and a cached spaCy Doc. This phase consumes that and
emits features. No retrieval yet — that's Phase 4.

Branch. `claude/iir-phase-2-feature-extractor` off integration branch.

Deliverables.

1. `logic/features/extractor.py` exporting:

       @dataclass(frozen=True)
       class FeatureSet:
           document: frozenset[str]
           per_segment: list[frozenset[str]]   # aligned to doc.segments

       def extract(doc: PreprocessedDoc, nlp: spacy.Language,
                   long_sentence_threshold: int = 25,
                  ) -> FeatureSet: ...

   `long_sentence_threshold` is the canonical example of "thresholds live
   on extractor parameters, not in feature names". It controls whether
   `LING_LONG_SENTENCE` fires.

2. One sub-extractor per feature family, all small and independent:
   - `logic/features/zones.py` — ZONE_* from `segment.kind`, ANCESTOR_*
     from `segment.ancestors`.
   - `logic/features/lexical.py` — HAS_* via regex.
   - `logic/features/linguistic.py` — LING_* via spaCy (passive via
     `nsubjpass`/`auxpass` deps; modals via `tag_=="MD"`; first/second
     person via lemma; imperative via root verb with no nsubj at sentence
     start; LING_LONG_SENTENCE uses the threshold parameter).
   - `logic/features/patterns.py` — PATTERN_* multi-token regexes.
   - `logic/features/relations.py` — REL_* features. This sub-extractor
     receives the full `PreprocessedDoc` (not a single segment) because
     relations are cross-segment by definition. Implement the four
     starter relations:
        REL_BULLET_AFTER_COLON: a list-bullet segment whose preceding
            sibling segment ends with a colon.
        REL_ACRONYM_DEFINED_ON_FIRST_USE: an acronym appears in
            "Full Name (ACRO)" form on or before its first standalone use.
        REL_HEADING_FOLLOWED_BY_LIST: a heading segment immediately
            followed by a list_bullet or list_numbered segment.
        REL_CITATION_AFTER_QUOTE: a citation pattern appears within ~5
            tokens after a quoted_content mask region.
   - `logic/features/aps.py` — APS_* via lookup against word lists in
     `logic/features/data/`. Provide starter wordlists for legislation
     and Commonwealth entities by parsing relevant files in
     `library_of_rules/`. Other APS_* lists may start empty with TODO
     markers.
   - `logic/features/exemptions.py` — EXEMPT_* derived from
     `doc.mask_map` kinds. Each unique exemption_kind in mask_map maps
     to the corresponding EXEMPT_<KIND> feature in BOTH the segment that
     contains it AND the document feature set.
   - `logic/features/document.py` — DOC_HAS_HEADINGS, DOC_HAS_LISTS,
     DOC_HAS_CITATIONS (true if any APS_LEGISLATION_REFERENCE or
     PATTERN_CITATION_PARENS feature appeared anywhere), DOC_LANGUAGE_EN
     (from `doc.language == "en"`).

3. Each sub-extractor exposes a clean `extract(...)` function. The
   orchestrator in `extractor.py` calls them in order and assembles the
   final `FeatureSet`.

4. The orchestrator validates every emitted feature name via
   `vocabulary.validate_feature`. An undeclared feature is a hard error,
   not a warning.

5. The orchestrator must not re-parse spaCy. It uses `doc.spacy_doc`
   from Phase 1.

Tests (`tests/test_features/`).

One file per sub-extractor plus integration:
- `test_zones.py`: a doc with heading + bullet → ZONE_HEADING and
  ZONE_LIST_BULLET in document features.
- `test_ancestors.py`: a paragraph inside a blockquote produces
  ANCESTOR_BLOCKQUOTE in that segment's feature set; a top-level
  paragraph does not.
- `test_lexical.py`: 20 cases covering each HAS_* with positive and
  negative examples.
- `test_linguistic.py`: passive vs active, imperative vs declarative,
  first/second person, LING_LONG_SENTENCE fires only when sentence ≥
  threshold (test with threshold=10 and threshold=50).
- `test_patterns.py`: each PATTERN_* with one positive and one negative
  example.
- `test_relations.py`: one fixture per REL_* feature; assert positive
  and negative cases. Critically, REL_BULLET_AFTER_COLON does NOT fire
  on a bullet that follows a non-colon paragraph.
- `test_aps.py`: at least one positive case per APS_* with the starter
  wordlist.
- `test_exemptions.py`: a doc with masked URL → EXEMPT_URL appears in
  both the containing segment's features AND the document feature set.
- `test_extractor_integration.py`: the noisy "Step 1" example produces
  the snapshot feature set you compute. Lock it as a regression test;
  the exact contents will depend on your implementation but must
  include EXEMPT_BRANCHNAME and EXEMPT_PRODUCT_NAME.
- `test_undeclared_feature_raises`: a fake sub-extractor emitting
  "ZONE_FAKE" causes `extract()` to raise ValueError.

Performance.
- `tests/test_features_perf.py`: 500-word document extracts features in
  <100 ms. Document numbers in REFACTOR_LOG.md.

Acceptance.
- `pytest tests/ -v` passes.
- `python -c "from logic.features.extractor import extract; ..."` smoke
  test runs.

Constraints. No dispatcher changes. No parquet changes. No rule trigger
code changes.

Reporting. Append Phase 2 entry to `docs/REFACTOR_LOG.md` — especially
features defined in vocabulary.py that proved expensive or unreliable to
extract (mark deferred so Phase 3's prompt does not encourage the LLM to
require them).
```

---

## Phase 3 — `required_features` + `mutation_class` authoring batch

```text
Task: add a Phase 3.5 to the GitHub Actions pipeline that uses an LLM
batch to populate BOTH `required_features` and `mutation_class` for
every passing rule.

Context. Phases 0–2 shipped. Feature vocabulary frozen and the extractor
proves which features are reliably computable. This phase emits two new
columns in the JSONL → parquet pipeline; the indexed dispatcher in
Phase 4 reads both. Both columns are populated in a single batch
because they share per-rule reasoning context — running two batches
would double cost for no benefit.

Branch. `claude/iir-phase-3-feature-authoring` off integration branch.

Deliverables.

1. New script `src/extract_features.py` modelled on
   `src/extract_rules.py` and `src/correct_rules.py`. It:
   - Reads `rules_working_draft.jsonl`.
   - For each rule with `test_result == "pass"`, builds an LLM batch
     request with the prompt template in deliverable 2.
   - Submits the batch via the existing infrastructure (same client and
     model as Phase 5 — gpt-4o-mini).
   - On collection, parses each response as strict JSON with two top-level
     keys: `required_features` (object: `all_of`, `any_of`, `none_of` —
     each list[str]) and `mutation_class` (one of `safe_replace`,
     `requires_rewrite`, `human_review`).
   - Validates:
     (a) every feature name via
         `logic.features.vocabulary.validate_feature`;
     (b) `EXEMPT_*` features appear ONLY in `none_of` (use
         `vocabulary.EXEMPT_FEATURES`);
     (c) `mutation_class` is one of the three allowed values.
   - Writes both fields back to the JSONL on success. On any failure,
     logs the offending value and writes `required_features: null,
     mutation_class: null`.
   - Phase 4 falls back to "always retrieve" for null
     `required_features`. Phase 6 falls back to a generic "Acknowledge"
     button for null `mutation_class`.

2. Prompt template `prompts/features.md`. Inputs interpolated per rule:
   rule_summary, rule_detail, taxonomy, source_url, lookup_list, trigger_code,
   ui_flag, test_fire, test_no_fire.

   Sections:
   - **Vocabulary** — generated programmatically from
     `logic/features/vocabulary.py` so it stays in sync. Each feature gets
     a one-line description.
   - **Slots** — describe `all_of`, `any_of`, `none_of`. State explicitly:
     "EXEMPT_* features may ONLY appear in `none_of`. Putting them in
     `all_of` or `any_of` will be rejected."
   - **Mutation classes**:
       safe_replace      — fix is a deterministic textual replacement
                           (e.g. `-` → `–`, `1` → `one`)
       requires_rewrite  — fix needs the user to rephrase (passive voice,
                           bureaucratic tone)
       human_review      — judgment call where no single replacement is
                           correct
   - **Conservatism** — encourage `none_of` to include relevant EXEMPT_*
     features whenever the rule should not fire on identifiers, code,
     URLs, or quoted content.
   - **Worked examples** — include all four below so the model sees each
     mutation class:

       Example 1 — regnal-number rule (safe_replace)
         required_features:
           all_of:  [HAS_CARDINAL, PATTERN_REGNAL_NUMERAL_SHAPE]
           any_of:  []
           none_of: [EXEMPT_IDENTIFIER, EXEMPT_BRANCHNAME,
                     EXEMPT_CODE_SNIPPET]
         mutation_class: safe_replace

       Example 2 — passive-voice rule (requires_rewrite)
         required_features:
           all_of:  [LING_PASSIVE_VOICE]
           any_of:  [ZONE_PARAGRAPH, ZONE_LIST_BULLET]
           none_of: [EXEMPT_QUOTED_CONTENT, ANCESTOR_BLOCKQUOTE]
         mutation_class: requires_rewrite

       Example 3 — date-format rule (safe_replace)
         required_features:
           all_of:  [HAS_DATE]
           any_of:  []
           none_of: [EXEMPT_CODE_SNIPPET, EXEMPT_QUOTED_CONTENT]
         mutation_class: safe_replace

       Example 4 — bureaucratic-tone rule (human_review)
         required_features:
           all_of:  []
           any_of:  [LING_PASSIVE_VOICE, LING_LONG_SENTENCE,
                     LING_MODAL_VERB]
           none_of: [ANCESTOR_BLOCKQUOTE, EXEMPT_QUOTED_CONTENT]
         mutation_class: human_review

   - **Output schema** — embed a JSON schema and instruct the model to
     return only conformant JSON. Reject non-conformant during parsing.

3. Two GitHub Actions workflows mirroring Phase 5's shape:
   - `.github/workflows/phase3_5_submit.yml`
   - `.github/workflows/phase3_5_collect.yml`
   Reuse Phase 5's secrets and runner config.

4. Update `src/publish.py` to include both new columns:
   - `required_features`: store as
     `struct<all_of: list<string>, any_of: list<string>,
              none_of: list<string>>`. If the struct path is awkward in
     PyArrow, fall back to three separate `list<string>` columns
     (`required_features_all_of`, `..._any_of`, `..._none_of`) and update
     `loader.py` accordingly. Document the choice in REFACTOR_LOG.md.
   - `mutation_class`: nullable `string`.

5. Update `CLAUDE.md` "Rulebook schema" table with both new columns.

6. Run the batch and merge the regenerated `rulebook.parquet` into the
   integration branch in this PR (matching repo convention — direct or
   LFS).

Tests.

- `tests/test_extract_features.py`:
  - Fixture: 6 hand-crafted rule rows (one per worked example, plus 2
    edge cases).
  - Mock the LLM client with canned JSON responses.
  - Assert correct JSONL output for valid responses.
  - Assert null + error-log for: EXEMPT_* in `all_of`; unknown feature
    name; unknown `mutation_class`; non-JSON output.
- `tests/test_publish_required_features.py`: round-trip a fully-populated
  rule (all three slots + `mutation_class="safe_replace"`) through
  `src/publish.py` and `loader.py`.

Acceptance.

- `pytest tests/ -v` passes.
- `python -c "import pyarrow.parquet as pq;
   t = pq.read_table('published/rulebook.parquet');
   ns = t.schema.names;
   print('required_features' in ns or 'required_features_all_of' in ns,
         'mutation_class' in ns)"` prints `True True`.
- ≥80% of passing rules have non-null `required_features`.
- ≥80% of passing rules have non-null `mutation_class`.
- Failures listed in REFACTOR_LOG.md with the model's failure mode.
- Top-10 candidate new PATTERN_* features the model wished existed
  (validation-failure reasons) captured in REFACTOR_LOG.md as the queue
  for a Phase 3 round 2.

Constraints. No dispatcher changes. No hand-edits to features in JSONL
outside fixture tests. Production values come from the batch.

Reporting. Phase 3 log entry covers:
- Total rules processed.
- % validated for required_features and mutation_class.
- Mutation_class distribution (counts by class).
- Top 10 most-required and most-forbidden features.
- Vocabulary features no rule asked for (candidates for removal in
  Phase 6).
- Top 10 candidate new PATTERN_* features the LLM tried to invent.

Cost note. Estimate batch cost in your PR description before running.
The mutation_class addition should not meaningfully increase tokens —
reuse the same prompt context.
```

---

## Phase 4 — Indexed dispatcher

```text
Task: build the inverted-index dispatcher and wire it behind the
OCTAVIUS_DISPATCHER env flag.

Context. Phases 0–3 shipped. `published/rulebook.parquet` carries
`required_features` and `mutation_class` for ~80%+ of passing rules.
Legacy dispatcher remains the default.

Branch. `claude/iir-phase-4-indexed-dispatcher` off integration branch.

Deliverables.

1. `logic/indexed_dispatcher.py`:

       def run_rules(text: str,
                     disabled_rule_ids: set[str] | None = None,
                     disabled_taxonomies: set[str] | None = None
                    ) -> list[Finding]: ...

   Signature-compatible with the legacy dispatcher. Steps:
   a. `preprocess(text)`.
   b. `extract(doc, nlp)` → FeatureSet.
   c. For each lintable segment, compute the feature set
      (segment_features ∪ document_features) and intersect with the
      inverted index → candidate rule_ids.
   d. Rules with `required_features=None` are in the always-run set.
   e. Execute candidate rules' trigger code on the segment text;
      translate offsets back via `segment.offset`; drop findings whose
      span overlaps a `mask_map` entry.
   f. Use the SentenceCache from Phase 1 to short-circuit unchanged
      sentences.
   g. **Copy `mutation_class` from the rule onto each Finding.**
   h. Post-firing logic:
      - Drop findings with `start_char == 0 and end_char == 0`
        (document-level) when `not has_structure or sentence_count < 3`.
      - Span deduplication: collapse exact `(start, end, rule_id)`;
        group same-span across different rules into one Finding with
        `grouped_rules` populated. The grouped Finding's
        `mutation_class` is the most conservative of its members
        (`human_review` > `requires_rewrite` > `safe_replace`).
      - Per-rule firing budget: cap each rule_id at 5 spanned findings
        per document; the 6th+ collapse into a single document-level
        summary Finding ("rule X fired N times — review pattern") that
        survives the document-level gating in step h.

2. Inverted index built at module load:

       _INDEX_ALL_OF: dict[str, frozenset[str]]   # feature → rule_ids
       _INDEX_ANY_OF: dict[str, frozenset[str]]
       _INDEX_NONE_OF: dict[str, frozenset[str]]
       _UNCONSTRAINED: frozenset[str]             # required_features=None

   At index-build time, reject any rule that has an EXEMPT_* feature in
   its `all_of` or `any_of` slot (defense in depth — Phase 3 should have
   caught this; log loudly and skip the rule).

   Candidate-set algorithm per segment:

       candidates = set(_UNCONSTRAINED)
       # any_of: rule retrieves if at least one of its any_of features
       # is present (or any_of is empty)
       # all_of: rule retrieves only if all of its all_of features are
       # present
       # none_of: rule does NOT retrieve if any of its none_of features
       # are present
       for rule in rules_with_explicit_requirements:
           if rule.all_of and not (rule.all_of <= features): continue
           if rule.any_of and not (rule.any_of & features): continue
           if rule.none_of and (rule.none_of & features):     continue
           candidates.add(rule.rule_id)

   Document the algorithm in the module docstring; verify with tests.

3. Update `routes/check.py`:
   - Read `OCTAVIUS_DISPATCHER` at module load.
   - Resolve to `logic.dispatcher` (legacy) or `logic.indexed_dispatcher`
     (indexed).
   - Default remains `legacy` until Phase 6.

4. Add a debug endpoint `GET /debug/explain` that returns: extracted
   features (document and per-segment), the candidate rule_ids per
   segment, and the firing trace for a specific rule_id if provided.
   Behind `OCTAVIUS_DEBUG_ENDPOINTS=1` env flag. This is the
   "why didn't rule X fire?" tool.

Tests (`tests/test_indexed_dispatcher.py`).

- `test_step_1_example_quiet`: noisy example produces ≤6 findings under
  the indexed dispatcher.
- `test_unconstrained_rules_still_run`: rule with required_features=None
  fires on a matching input.
- `test_none_of_blocks_retrieval`: rule with `none_of=[EXEMPT_BRANCHNAME]`
  is not retrieved when the segment masked `main`.
- `test_all_of_strict`: rule with
  `all_of=[LING_PASSIVE_VOICE, HAS_CARDINAL]` only retrieves when both
  are present.
- `test_any_of_loose`: rule with
  `any_of=[ZONE_PARAGRAPH, ZONE_LIST_BULLET]` retrieves when either is
  present.
- `test_exempt_in_all_of_rejected_at_load`: synthesise a rule with
  `EXEMPT_URL` in `all_of`; assert the loader logs an error and skips
  it.
- `test_mutation_class_propagated`: a fired finding carries the rule's
  `mutation_class`.
- `test_grouped_finding_takes_most_conservative_mutation`: two rules on
  the same span with classes `safe_replace` and `human_review` →
  grouped finding has `mutation_class="human_review"`.
- `test_firing_budget_summary`: synth input fires one rule 10× → 5
  spanned findings + 1 summary.
- `test_span_grouping`: two rules on the same span → 1 finding with
  `grouped_rules` length 2.
- `test_document_level_gating_short_input`: 1-sentence input emits zero
  document-level findings.
- `test_legacy_parity_baseline`: run both dispatchers on a 10-doc
  corpus; report Jaccard similarity of `(rule_id, start, end)` tuples.
  Don't assert a threshold yet — Phase 5 turns this into a calibrated
  metric.

Performance.
- `tests/test_indexed_perf.py`: 500-word doc lints in <300 ms cold,
  <100 ms warm. Capture numbers in REFACTOR_LOG.md.

Acceptance.
- `pytest tests/ -v` passes.
- `OCTAVIUS_DISPATCHER=indexed uvicorn main:app` boots; the noisy
  example via POST /check returns ≤6 findings.
- `OCTAVIUS_DISPATCHER=legacy uvicorn main:app` returns the original
  ~33.

Constraints. No parquet changes. No LLM-pipeline changes. No frontend
changes. Both dispatchers must remain functional.

Reporting. Phase 4 log entry:
- Step 1 example: legacy N findings → indexed N findings.
- Cold/warm latency.
- Jaccard parity on the 10-doc corpus.
- Any rules that retrieved on every segment despite required_features
  (debug fodder for Phase 5).
```

---

## Phase 5 — Calibration corpus + telemetry

```text
Task: build the calibration corpus, the precision-scoring harness, and
the telemetry path that justifies the Phase 6 cutover.

Context. Phases 0–4 shipped. Indexed dispatcher works behind the flag.
Need quantitative evidence it is at least as good as legacy on real
documents.

Branch. `claude/iir-phase-5-calibration` off integration branch.

Deliverables.

1. `corpus/` directory with subdirs:
   - `corpus/should_not_fire/` — 80–120 short docs (~2–6 sentences).
     Mix:
     - 20 manually-collected real samples: README excerpts, Slack
       messages, commit messages, code comments, dev-team notes,
       internal email snippets.
     - 60+ LLM-generated synthetic samples across content types
       (Slack, email, code review, ticket comment, blog intro, recipe,
       meeting notes, dev-runbook step, error-message body).
     Generate via `corpus/generate_should_not_fire.py` calling the same
     LLM client as the pipeline. Save to
     `corpus/should_not_fire/synthetic/` with a manifest JSON listing
     prompt-per-file.
   - `corpus/should_fire/` — 30–50 hand-crafted samples explicitly
     targeting known rules (passive voice, regnal numerals, numeric
     ranges, ANCESTOR_*-sensitive rules, REL_*-sensitive rules).
     Sidecar `<name>.expected.json` listing expected rule_ids.

2. `scripts/score_dispatchers.py`:
   - Loads the corpus.
   - Runs both dispatchers over every doc.
   - For `should_not_fire/`: per-rule false-positive rate, per-doc
     finding count.
   - For `should_fire/`: per-rule recall vs expected.
   - Writes `corpus/REPORT.md` with:
     - Headline: legacy mean findings/doc vs indexed.
     - Top 20 noisiest rules under each dispatcher.
     - Recall delta per rule between dispatchers (must be ≥0 for
       cutover safety).
     - Latency p50/p95 per dispatcher.
     - Mutation_class distribution among findings (sanity check).

3. Telemetry. `logic/telemetry.py`:

       def log_finding_event(
           event: Literal["fired", "dismissed", "accepted",
                          "not_applicable"],
           rule_id: str,
           doc_hash: str,
           features: frozenset[str],
           mutation_class: str | None,
       ) -> None: ...

   Default sink: append-only JSONL at
   `${OCTAVIUS_TELEMETRY_DIR:-/tmp/octavius_telemetry}/events.jsonl`.
   Wire `fired` events into `logic/indexed_dispatcher.py` (one per
   finding, after dedup). Other event kinds will be triggered by the
   frontend in Phase 6.

4. `scripts/aggregate_telemetry.py` reads the JSONL, produces per-rule
   precision estimates (using accept/dismiss events; firings alone are
   insufficient). Output: `corpus/PRECISION.md`. Even with no user data
   yet, run on the corpus's `should_not_fire` runs (every fire = synthetic
   dismissal) to seed precision priors. Bucket precision by
   `mutation_class` so we can see whether `requires_rewrite` and
   `human_review` rules are systematically noisier (they often are).

Tests.
- `tests/test_score_dispatchers.py`: end-to-end on a 5-doc miniature
  corpus, asserts the report renders.
- `tests/test_telemetry.py`: log events, read back, aggregate.

Acceptance.
- `pytest tests/ -v` passes.
- `python scripts/score_dispatchers.py` runs and produces
  `corpus/REPORT.md`.
- Indexed mean findings/doc on `should_not_fire/` is ≥70% lower than
  legacy. If not, do not proceed to Phase 6 — investigate and document
  in REFACTOR_LOG.md.
- Recall on `should_fire/` is ≥90% under indexed (ideally ~equal to
  legacy). Recall regressions identify rules whose `required_features`
  are too strict; document them as candidates for either (a) loosening
  in a follow-up batch, or (b) flipping `required_features=null` for
  those rules.

Constraints. No dispatcher logic changes except the telemetry hook. Do
not flip the env flag default.

Reporting. Phase 5 log entry:
- Headline numbers from REPORT.md.
- Recall regressions (if any) and proposed remediations.
- Precision-by-mutation_class table.
- Go/no-go recommendation for Phase 6.
```

---

## Phase 6 — Frontend updates + cutover

```text
Task: update the React component for the new finding shape (including
mutation_class-driven actions), flip the default dispatcher to
`indexed`, and remove the legacy code.

Context. Phases 0–5 shipped. Indexed dispatcher meets the acceptance
bar in `corpus/REPORT.md`. Frontend still treats every Finding
identically.

Branch. `claude/iir-phase-6-frontend-cutover` off integration branch.

Deliverables.

1. Update `frontend/src/types.ts`:
   - Add `groupedRules?: string[]` to `Finding`.
   - Add `mutationClass?: 'safe_replace' | 'requires_rewrite'
     | 'human_review' | null` to `Finding`.
   - Add `documentLevel?: boolean`.
   - Confirm `severity` exists with the four-tier union; add if missing.

2. Update `frontend/src/components/FindingCard.tsx`:
   - When `groupedRules.length >= 2`, render a "N rules flagged this
     phrase" header with click-to-expand list.
   - When `documentLevel === true`, render in a separate
     "Document-level suggestions" pane at the bottom of FindingsPanel
     (no inline highlight — there's no span).
   - Render the action button per `mutationClass`:
       safe_replace      → "Apply fix" (primary)
       requires_rewrite  → "Suggest rewrite" (opens textarea)
       human_review      → "Acknowledge" (secondary)
       null / undefined  → "Acknowledge" (fallback)

3. Update `frontend/src/components/FindingsPanel.tsx`:
   - Severity-tier filter: tri-state toggle ("Errors only / Errors +
     warnings / All"); default = "Errors + warnings".
   - Wire to a state hook.

4. Three-state per-finding action: accept / dismiss / not-applicable.
   Each click POSTs to a new endpoint:
   - `routes/feedback.py` exposing `POST /feedback` with
     `{event, rule_id, doc_hash, features, mutation_class}` and calling
     `logic.telemetry.log_finding_event`.
   - Wire React buttons to the endpoint with optimistic UI.

5. Flip the default. In `routes/check.py`, change the
   `OCTAVIUS_DISPATCHER` default from `legacy` to `indexed`. Document
   the rollback procedure in `docs/REFACTOR_LOG.md`
   ("set OCTAVIUS_DISPATCHER=legacy and redeploy").

6. Removal sweep (after local + Render verification):
   - Delete `logic/dispatcher.py` (legacy).
   - Rename `logic/indexed_dispatcher.py` → `logic/dispatcher.py`.
   - Remove env-flag branching from `routes/check.py`.
   - Remove vocabulary entries that no rule ever required (per Phase 3
     report).
   - Update `CLAUDE.md` to describe the new architecture; remove legacy
     references.

Tests.
- `frontend/src/components/__tests__/FindingCard.test.tsx`: rendering
  cases for grouped findings, document-level findings, severity tiers,
  AND each mutation_class (including null fallback).
- `tests/test_feedback_route.py`: POST /feedback → telemetry event
  written.
- Re-run `scripts/score_dispatchers.py` in CI as a smoke test (legacy
  path still works pre-removal; remove that case in the same PR as the
  removal sweep).

Acceptance.
- `pytest tests/ -v` passes.
- `cd frontend && npm test` passes.
- `cd frontend && npm run build` succeeds.
- Manual smoke test: lint the Step 1 example through the running app;
  verify ≤6 findings rendered, with correct grouping, correct
  document-level separation, and correct action button per
  mutation_class.
- Latency: p50 <200 ms, p95 <700 ms on the corpus. Capture in
  REFACTOR_LOG.md.

Constraints. Do the frontend updates and cutover in TWO commits where
possible: commit 1 = frontend supports both shapes; commit 2 = flip
default and remove legacy. The PR can contain both.

Reporting. Final REFACTOR_LOG.md entry:
- What shipped end-to-end.
- Final corpus numbers (legacy vs indexed).
- Rules quarantined / removed.
- Vocabulary features actually used vs defined.
- Open follow-ups (embedding prefilter, SLM verifier, override graph,
  COUNT_* family, COST_* classes).
- Mark refactor complete.

Then merge integration branch into main.
```

---

# 4. Risks and mitigations

| Risk | Surfaces in | Mitigation |
|---|---|---|
| Feature vocabulary wrong / under-specified | Phase 2, 3 | Vocabulary frozen Phase 0; `validate_feature` enforces; Phase 3 batch surfaces gaps as candidate `PATTERN_*` queue |
| LLM mis-tags `required_features`, killing recall | Phase 3, 5 | Null fallback = always-run; Phase 5 measures recall on `should_fire/` corpus before any cutover |
| LLM mis-tags `mutation_class` | Phase 3, 6 | Null fallback = "Acknowledge" button; Phase 5 telemetry buckets precision by class to detect systematic errors |
| `EXEMPT_*` accidentally placed in `all_of` | Phase 3, 4 | Validated at batch parse AND at dispatcher load (defense in depth) |
| Threshold creep into feature names | Phase 0–2 | `validate_feature` rejects regex `r"_(GE|GT|LT|LE)?_?\d+P?$"`; thresholds parameterised on extractor functions |
| Legacy and indexed diverge silently | Phase 4, 5 | Both dispatchers live until Phase 6; Phase 5 parity report mandatory before flip |
| Latency regresses | Phase 4, 6 | Per-phase perf tests; final p50/p95 gate in Phase 6 acceptance |
| Frontend breaks on new fields | Phase 6 | All new fields optional; cutover is two commits |
| `ANCESTOR_*` / `REL_*` extractors are slow | Phase 2 | `<100 ms` perf test on 500-word doc; relations sub-extractor scoped to four cases only |
| Spec drift between sessions | All | `docs/REFACTOR_LOG.md` is mandatory output of every phase |
| Ontology sprawl over time | Post-refactor | Phase 6 removes vocabulary entries no rule asked for; "deferred features" section in log gates additions to evidence |

---

# 5. Inter-session checklist

After each PR:
1. Read the agent's `REFACTOR_LOG.md` entry.
2. Skim the diff — especially any guardrails the agent bent or tests it weakened.
3. If acceptance criteria met, merge into `claude/inverted-index-refactor`.
4. If not, leave a review comment; the same branch can be iterated.
5. Start the next phase's session with a fresh context. The merged code + the decision log are sufficient handoff.

If the Phase 0 vocabulary needs to change after Phase 3 has run, that is a re-run of the Phase 3 batch — budget accordingly. Lock the vocabulary in Phase 0 and use the "Deferred features" section to capture additions for later.
