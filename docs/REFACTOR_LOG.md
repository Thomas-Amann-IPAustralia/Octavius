# Inverted-Index Refactor — Decision Log

## Phase 0 — Foundations (2026-05-04)
### Shipped
- New `logic/features/` package containing `vocabulary.py`. The vocabulary
  is a `Final[frozenset[str]]` covering the eight feature families
  (ZONE_*, ANCESTOR_*, HAS_*, LING_*, PATTERN_*, REL_*, APS_*, EXEMPT_*,
  DOC_*) plus a `validate_feature()` callable that rejects both unknown
  names and any name matching the threshold-suffix regression guard
  (`r"_(GE|GT|LT|LE)?_?\d+P?$"`). `EXEMPT_FEATURES` is also exported as
  a sub-frozenset for the eventual `none_of`-only validation.
- `logic/rulebook/types.py` extended with `MutationClass` literal,
  `FeatureRequirements` TypedDict, and three new `NotRequired` fields:
  `Finding.grouped_rules`, `Finding.mutation_class`,
  `CompiledRule.required_features`, `CompiledRule.mutation_class`. All
  default to `None` until the phases that populate them ship.
- `logic/rulebook/loader.py` reads `required_features` and
  `mutation_class` parquet columns when present; missing columns default
  to `None` (loader does not fail on the current parquet, which lacks
  both columns).
- `OCTAVIUS_DISPATCHER` env-flag plumbing in `routes/check.py`. Both
  `legacy` and `indexed` resolve to `logic.dispatcher` for now, with a
  warning logged when `indexed` is requested. Unit tests cover the
  resolution logic in `tests/test_routes_check_dispatcher_flag.py`.
- Streamlit path deleted: `app.py`, `logic/engine.py`, `logic/rules.py`,
  `octavius_component.py`, `pages/1_Developer.py` (and the now-empty
  `pages/` directory) all removed; `tests/test_engine.py` deleted because
  it asserted against the removed spaCy/Doc-shaped engine and the
  parquet-driven dispatcher is already covered by `test_dispatcher.py`,
  `test_routes_check.py`, and the per-adapter tests. `streamlit` and
  `st-annotated-text` removed from `requirements.txt`.
- `README.md` and `CLAUDE.md` updated: runtime entry point is
  `uvicorn main:app`, references to `streamlit run app.py`,
  `logic/engine.py`, and `logic/rules.py` are gone. CLAUDE.md key-files
  table now reflects the dispatcher / rulebook layout and adds the new
  `docs/REFACTOR_LOG.md` and `logic/features/vocabulary.py` entries.
- `docs/REFACTOR_LOG.md` created (this file).

### Deferred
- No preprocessing layer, no feature extractors, and no indexed
  dispatcher in this phase — explicitly out of scope.
- `COUNT_*` features and `min_count`-style requirement slots: not added;
  tracked in the "Deferred features" section below.
- `mutation_class` and `required_features` plumbing through to the JSON
  response shape in `routes/check.py`: deferred to Phase 4 when the
  frontend will need them.

### Surprises
- The published parquet does not yet have a `required_features` or
  `mutation_class` column, so the loader change is a pure no-op against
  the current data. That is fine for Phase 0 (the columns will be added
  by Phase 3) but means we have no end-to-end test for the pass-through
  yet — covered indirectly by `test_rulebook_loader.py` continuing to
  pass.
- `TypedDict` total=True classes can be safely extended with optional
  fields using `typing.NotRequired` (Python 3.11+), avoiding the need to
  flip the existing definitions to `total=False` and re-declare every
  required field.

### Follow-ups for next phase
- Phase 1 introduces `PreprocessedDoc` (with `.counts: dict[str, int]`)
  and the segmenter/feature-extraction pipeline. The vocabulary import
  surface in `logic/features/__init__.py` is the entry point those
  modules should target.
- Phase 3 will start writing `required_features` and `mutation_class`
  into the parquet; at that point add a loader test that asserts the
  pass-through with a synthetic row.
- Phase 2/3 should also add a CI check that runs `validate_feature` over
  every name in every rule's `required_features` slot.


## Deferred features (revisit triggers)
- COUNT_* family: revisit if Phase 5 telemetry shows ranking failures that boolean count thresholds would fix. Replacement plan = integer counts in PreprocessedDoc.counts plus a `min_count` slot on FeatureRequirements.
- COST_* execution classes: revisit if Phase 4 latency tests miss the 200 ms p50 target.
- Additional PATTERN_* features: add as Phase 3's batch surfaces gaps in its responses.
- General relational sub-language: only the four REL_* features ship in Phase 0; expand if telemetry justifies it.
