"""Inverted-index dispatcher — Phase 4.

Algorithm
---------
Each rule declares a ``required_features`` gate with three slots:

    all_of: list[str]   # ALL must be present  (empty → no constraint)
    any_of: list[str]   # AT LEAST ONE present  (empty → no constraint)
    none_of: list[str]  # NONE may be present   (empty → no constraint)

Rules with ``required_features = None`` are *unconstrained* and always
retrieved.  The inverted index is built once at import time from ``_RULES``;
``run_rules`` does three filtering passes per segment to produce its candidate
set::

    candidates = set(_UNCONSTRAINED)

    for rule_id in _CONSTRAINED_IDS:
        all_of = _RULE_ALL_OF[rule_id]
        any_of = _RULE_ANY_OF[rule_id]
        none_of = _RULE_NONE_OF[rule_id]
        if all_of and not (all_of <= features): continue
        if any_of and not (any_of & features): continue
        if none_of and (none_of & features):   continue
        candidates.add(rule_id)

Index structures kept for introspection and the ``/debug/explain`` endpoint:

    _INDEX_ALL_OF: dict[str, frozenset[str]]   # feature → rule_ids requiring it
    _INDEX_ANY_OF: dict[str, frozenset[str]]
    _INDEX_NONE_OF: dict[str, frozenset[str]]
    _UNCONSTRAINED: frozenset[str]             # required_features=None

Post-firing logic
-----------------
1. **Firing budget**: each rule fires at most :data:`_FIRING_BUDGET` spanned
   findings per document; the 6th+ collapse into one document-level summary
   Finding that bypasses document-level gating.
2. **Span deduplication**: exact ``(start, end, rule_id)`` triples → one
   Finding.
3. **Span grouping**: different rules on the same ``(start, end)`` → one
   Finding with ``grouped_rules`` populated; ``mutation_class`` is the most
   conservative of its members
   (``human_review`` > ``requires_rewrite`` > ``safe_replace``).
4. **Document-level gating**: ``(start=0, end=0)`` findings are dropped when
   ``not has_structure or sentence_count < 3``, EXCEPT budget-overflow
   summaries which always survive gating.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from logic.features.extractor import extract
from logic.features.vocabulary import EXEMPT_FEATURES
from logic.preprocess import Segment, preprocess
from logic.rulebook.loader import load_rules
from logic.rulebook.types import CompiledRule, Finding, MutationClass
from logic.sentence_cache import SentenceCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIRING_BUDGET = 5  # max spanned findings per rule per document

# Conservatism ordering — lower index wins (human_review is most conservative).
_MUTATION_ORDER: dict[str | None, int] = {
    "human_review": 0,
    "requires_rewrite": 1,
    "safe_replace": 2,
    None: 3,
}

# ---------------------------------------------------------------------------
# Rule registry — loaded once at import time
# ---------------------------------------------------------------------------

_RULES: list[CompiledRule] = load_rules()
_RULE_BY_ID: dict[str, CompiledRule] = {r["rule_id"]: r for r in _RULES}

# Per-rule requirement caches (frozensets for O(1) set operations)
_RULE_ALL_OF: dict[str, frozenset[str]] = {}
_RULE_ANY_OF: dict[str, frozenset[str]] = {}
_RULE_NONE_OF: dict[str, frozenset[str]] = {}
_CONSTRAINED_IDS: list[str] = []

# Inverted index: feature → frozenset[rule_id]
_INDEX_ALL_OF: dict[str, frozenset[str]] = {}
_INDEX_ANY_OF: dict[str, frozenset[str]] = {}
_INDEX_NONE_OF: dict[str, frozenset[str]] = {}

# Rules with required_features=None; populated by _build_index()
_UNCONSTRAINED: frozenset[str]

# Process-local segment cache (reused across requests)
_CACHE = SentenceCache(max_entries=10_000)


def _build_index() -> frozenset[str]:
    """Build the inverted index from ``_RULES``; return the unconstrained set.

    Rejects any rule that has an ``EXEMPT_*`` feature in its ``all_of`` or
    ``any_of`` slot (defense in depth — Phase 3.5 should have caught this).
    Logs loudly and skips the offending rule entirely.
    """
    unconstrained: set[str] = set()
    all_of_build: dict[str, set[str]] = defaultdict(set)
    any_of_build: dict[str, set[str]] = defaultdict(set)
    none_of_build: dict[str, set[str]] = defaultdict(set)

    for rule in _RULES:
        rule_id = rule["rule_id"]
        rf = rule.get("required_features")

        if rf is None:
            unconstrained.add(rule_id)
            continue

        all_of = set(rf.get("all_of") or [])
        any_of = set(rf.get("any_of") or [])
        none_of = set(rf.get("none_of") or [])

        # Defense in depth: EXEMPT_* must only appear in none_of.
        bad = (all_of | any_of) & EXEMPT_FEATURES
        if bad:
            logger.error(
                "Rule %r has EXEMPT_* feature(s) in all_of or any_of — "
                "skipping rule (Phase 3.5 should have caught this): %s",
                rule_id,
                sorted(bad),
            )
            continue  # rule is silently dropped — it will never fire

        _RULE_ALL_OF[rule_id] = frozenset(all_of)
        _RULE_ANY_OF[rule_id] = frozenset(any_of)
        _RULE_NONE_OF[rule_id] = frozenset(none_of)
        _CONSTRAINED_IDS.append(rule_id)

        for f in all_of:
            all_of_build[f].add(rule_id)
        for f in any_of:
            any_of_build[f].add(rule_id)
        for f in none_of:
            none_of_build[f].add(rule_id)

    for f, ids in all_of_build.items():
        _INDEX_ALL_OF[f] = frozenset(ids)
    for f, ids in any_of_build.items():
        _INDEX_ANY_OF[f] = frozenset(ids)
    for f, ids in none_of_build.items():
        _INDEX_NONE_OF[f] = frozenset(ids)

    logger.info(
        "Indexed dispatcher built: %d unconstrained, %d constrained rules",
        len(unconstrained),
        len(_CONSTRAINED_IDS),
    )
    return frozenset(unconstrained)


_UNCONSTRAINED = _build_index()


# ---------------------------------------------------------------------------
# NLP singleton — reuse the one initialised by logic.preprocess
# ---------------------------------------------------------------------------

def _get_nlp() -> Any:
    from logic.preprocess import _get_nlp as _preprocess_get_nlp
    return _preprocess_get_nlp()


# ---------------------------------------------------------------------------
# Candidate computation
# ---------------------------------------------------------------------------

def _compute_candidates(features: frozenset[str]) -> frozenset[str]:
    """Return the rule_ids to evaluate for a segment with *features*.

    See the module docstring for the full algorithm.
    """
    candidates: set[str] = set(_UNCONSTRAINED)

    for rule_id in _CONSTRAINED_IDS:
        all_of = _RULE_ALL_OF[rule_id]
        any_of = _RULE_ANY_OF[rule_id]
        none_of = _RULE_NONE_OF[rule_id]

        if all_of and not (all_of <= features):
            continue
        if any_of and not (any_of & features):
            continue
        if none_of and (none_of & features):
            continue
        candidates.add(rule_id)

    return frozenset(candidates)


# ---------------------------------------------------------------------------
# Mask-overlap check
# ---------------------------------------------------------------------------

def _overlaps_mask(
    start: int,
    end: int,
    mask_map: list[tuple[int, int, str, str]],
) -> bool:
    """Return ``True`` if ``[start, end)`` overlaps any masked region."""
    for m_start, m_end, _orig, _kind in mask_map:
        if start < m_end and end > m_start:
            return True
    return False


# ---------------------------------------------------------------------------
# Mutation-class conservatism helper
# ---------------------------------------------------------------------------

def _most_conservative(
    classes: list[MutationClass | None],
) -> MutationClass | None:
    """Return the most conservative mutation class from *classes*."""
    return min(classes, key=lambda c: _MUTATION_ORDER.get(c, 3))


# ---------------------------------------------------------------------------
# Per-segment rule execution (with segment cache)
# ---------------------------------------------------------------------------

def _run_candidates_on_segment(
    seg: Segment,
    candidates: frozenset[str],
    features: frozenset[str],
    mask_map: list[tuple[int, int, str, str]],
) -> tuple[list[Finding], list[Finding]]:
    """Execute candidate rules on *seg*.

    Returns ``(spanned_findings, doc_level_findings)``.  Spanned findings
    carry document-absolute ``start_char`` / ``end_char`` (``seg.offset``
    added).  Document-level findings (``start=end=0``) are returned as-is.
    Rule failures are caught and logged; they never propagate.
    """
    cache_key = (
        seg.text
        + "\x00"
        + ",".join(sorted(features))
        + "\x00"
        + ",".join(sorted(candidates))
    )

    def _compute(_: str) -> list[Finding]:
        """Return segment-relative raw findings before offset translation."""
        raw: list[Finding] = []
        for rule_id in candidates:
            rule = _RULE_BY_ID[rule_id]
            try:
                rule_findings = rule["check"](seg.text)
            except Exception:
                logger.exception(
                    "Rule %s raised during indexed execution — skipping", rule_id
                )
                continue
            for f in rule_findings:
                raw.append(
                    Finding(
                        start_char=f["start_char"],
                        end_char=f["end_char"],
                        rule_id=f["rule_id"],
                        taxonomy=f["taxonomy"],
                        ui_flag=f["ui_flag"],
                        rule_summary=f["rule_summary"],
                        source_url=f["source_url"],
                        severity=f["severity"],
                        document_level=f["document_level"],
                        grouped_rules=None,
                        mutation_class=rule.get("mutation_class"),
                    )
                )
        return raw

    raw_findings = _CACHE.get_or_compute(cache_key, _compute)

    spanned: list[Finding] = []
    doc_level: list[Finding] = []

    for f in raw_findings:
        is_doc_level = f["document_level"] or (
            f["start_char"] == 0 and f["end_char"] == 0
        )
        if is_doc_level:
            doc_level.append(f)
        else:
            abs_start = seg.offset + f["start_char"]
            abs_end = seg.offset + f["end_char"]
            if _overlaps_mask(abs_start, abs_end, mask_map):
                continue
            spanned.append(
                Finding(
                    start_char=abs_start,
                    end_char=abs_end,
                    rule_id=f["rule_id"],
                    taxonomy=f["taxonomy"],
                    ui_flag=f["ui_flag"],
                    rule_summary=f["rule_summary"],
                    source_url=f["source_url"],
                    severity=f["severity"],
                    document_level=False,
                    grouped_rules=None,
                    mutation_class=f.get("mutation_class"),
                )
            )

    return spanned, doc_level


# ---------------------------------------------------------------------------
# Post-firing helpers
# ---------------------------------------------------------------------------

def _apply_firing_budget(
    spanned: list[Finding],
) -> tuple[list[Finding], list[Finding]]:
    """Cap each rule_id at ``_FIRING_BUDGET`` spanned findings per document.

    Returns ``(kept, summaries)`` where ``summaries`` are document-level
    overrun Findings that bypass document-level gating in ``run_rules``.
    """
    per_rule: dict[str, list[Finding]] = defaultdict(list)
    for f in spanned:
        per_rule[f["rule_id"]].append(f)

    kept: list[Finding] = []
    summaries: list[Finding] = []

    for rule_id, rule_findings in per_rule.items():
        if len(rule_findings) <= _FIRING_BUDGET:
            kept.extend(rule_findings)
        else:
            kept.extend(rule_findings[:_FIRING_BUDGET])
            n = len(rule_findings)
            rule = _RULE_BY_ID.get(rule_id)
            summaries.append(
                Finding(
                    start_char=0,
                    end_char=0,
                    rule_id=rule_id,
                    taxonomy=rule["taxonomy"] if rule else "",
                    ui_flag=f"Rule '{rule_id}' fired {n} times — review pattern",
                    rule_summary=rule["rule_summary"] if rule else "",
                    source_url=rule["source_url"] if rule else "",
                    severity=rule["severity"] if rule else "warning",
                    document_level=True,
                    grouped_rules=[rule_id],  # non-None marks this as a budget summary
                    mutation_class=rule.get("mutation_class") if rule else None,
                )
            )

    return kept, summaries


def _dedup_spanned(findings: list[Finding]) -> list[Finding]:
    """Collapse exact ``(start, end, rule_id)`` duplicates."""
    seen: set[tuple[int, int, str]] = set()
    result: list[Finding] = []
    for f in findings:
        key = (f["start_char"], f["end_char"], f["rule_id"])
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result


def _group_by_span(findings: list[Finding]) -> list[Finding]:
    """Group findings at the same ``(start, end)`` across different rules.

    The grouped Finding takes the most conservative ``mutation_class`` of
    its members and carries ``grouped_rules`` with all contributing rule IDs.
    Single-rule spans are returned unchanged.
    """
    span_groups: dict[tuple[int, int], list[Finding]] = defaultdict(list)
    for f in findings:
        span_groups[(f["start_char"], f["end_char"])].append(f)

    result: list[Finding] = []
    for (start, end), group in span_groups.items():
        if len(group) == 1:
            result.append(group[0])
        else:
            mc = _most_conservative([f.get("mutation_class") for f in group])
            rep = group[0]
            result.append(
                Finding(
                    start_char=start,
                    end_char=end,
                    rule_id=rep["rule_id"],
                    taxonomy=rep["taxonomy"],
                    ui_flag=rep["ui_flag"],
                    rule_summary=rep["rule_summary"],
                    source_url=rep["source_url"],
                    severity=rep["severity"],
                    document_level=False,
                    grouped_rules=[f["rule_id"] for f in group],
                    mutation_class=mc,
                )
            )
    return result


def _dedup_doc_level(findings: list[Finding]) -> list[Finding]:
    """Deduplicate document-level findings by rule_id."""
    seen: set[str] = set()
    result: list[Finding] = []
    for f in findings:
        if f["rule_id"] not in seen:
            seen.add(f["rule_id"])
            result.append(f)
    return result


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def run_rules(
    text: str,
    disabled_rule_ids: set[str] | None = None,
    disabled_taxonomies: set[str] | None = None,
) -> list[Finding]:
    """Run all enabled rules against *text* via the inverted-index dispatcher.

    Parameters
    ----------
    text:
        The document text to analyse.
    disabled_rule_ids:
        Rule IDs to skip (exact match on ``rule_id``).
    disabled_taxonomies:
        Taxonomy names to skip entirely (e.g. ``{"structural"}``).

    Returns
    -------
    list[Finding]
        All findings, sorted by ``(start_char, rule_id)``.  Single-rule
        failures are caught and logged; they never propagate to the caller.
    """
    skip_ids = disabled_rule_ids or set()
    skip_taxs = disabled_taxonomies or set()

    # --- Preprocess ---
    doc = preprocess(text)

    # --- Extract features ---
    nlp = _get_nlp()
    fs = extract(doc, nlp)

    # --- Per-segment candidate selection and rule execution ---
    all_spanned: list[Finding] = []
    all_doc_level: list[Finding] = []

    for i, seg in enumerate(doc.segments):
        if not seg.lintable:
            continue

        seg_features = fs.per_segment[i] | fs.document
        candidates = _compute_candidates(seg_features)

        # Apply disabled filters
        if skip_ids or skip_taxs:
            candidates = frozenset(
                rid for rid in candidates
                if rid not in skip_ids
                and _RULE_BY_ID[rid]["taxonomy"] not in skip_taxs
            )

        if not candidates:
            continue

        spanned, doc_level = _run_candidates_on_segment(
            seg, candidates, seg_features, doc.mask_map
        )
        all_spanned.extend(spanned)
        all_doc_level.extend(doc_level)

    # --- Post-firing logic ---

    # 1. Firing budget — cap each rule at _FIRING_BUDGET spanned findings
    kept_spanned, budget_summaries = _apply_firing_budget(all_spanned)

    # 2. Span deduplication
    kept_spanned = _dedup_spanned(kept_spanned)

    # 3. Span grouping (same span, multiple rules → one Finding)
    grouped_spanned = _group_by_span(kept_spanned)

    # 4. Document-level deduplication
    deduped_doc = _dedup_doc_level(all_doc_level)

    # 5. Document-level gating: drop (start=0, end=0) for short/simple docs
    if doc.has_structure and doc.sentence_count >= 3:
        gated_doc = deduped_doc
    else:
        gated_doc = []

    # Budget summaries always survive gating
    findings = grouped_spanned + gated_doc + budget_summaries

    findings.sort(key=lambda f: (f["start_char"], f["rule_id"]))
    return findings


def get_rules() -> list[CompiledRule]:
    """Return the cached compiled rule list (read-only reference)."""
    return _RULES
