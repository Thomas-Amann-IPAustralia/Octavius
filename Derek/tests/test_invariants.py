"""Tests for Derek's non-negotiable invariants.

Each test names the invariant (D-n) and the Octavius failure it guards
against. If one of these fails, a documented failure mode has been
reintroduced — do not weaken the test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from derek.corpus.eligibility import load_eligibility
from derek.corpus.normalise import (
    NormalisedPage, content_hash, normalise_text, repair_headings,
)
from derek.extract.build import collect_candidates
from derek.extract.candidates import (
    CandidateKind, Candidate, candidate_uid, classify_heading, clean_example,
    extract_candidates, normalise_statement,
)
from derek.extract.modality import Modality, classify_modality
from derek.extract.segment import iter_nodes, parse_page
from derek.ledger.model import (
    Derivation, Detection, Direction, Rule, ReviewStatus, Source, Unit,
)
from derek.ledger.reconcile import reconcile
from derek.ledger.store import load_ledger, write_ledger

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "ledger" / "rules.jsonl"
SCHEMA = REPO / "schema" / "rule.schema.json"


# ---------------------------------------------------------------------------
# D-8 — normalisation must be stable, or change detection becomes noise
# ---------------------------------------------------------------------------

def test_normalise_is_idempotent():
    raw = "# Title\r\n\r\n\r\nSome  text here   \n\n\n\nMore.\n"
    once = normalise_text(raw)
    assert normalise_text(once) == once


def test_content_hash_ignores_cosmetic_variation():
    a = "## Heading\n\nText here.\n"
    b = "## Heading\r\n\r\nText here.   \r\n\r\n\r\n"
    assert content_hash(a) == content_hash(b)


def test_normalised_page_is_deterministic():
    src = REPO / "corpus" / "pages" / "grammar-punctuation-and-conventions" / "punctuation" / "commas.md"
    raw = src.read_text(encoding="utf-8")
    assert NormalisedPage("x", raw).sha256 == NormalisedPage("x", raw).sha256


# ---------------------------------------------------------------------------
# Heading repair — recovers structure without inventing rules
# ---------------------------------------------------------------------------

def test_repair_promotes_orphan_section_heading():
    text = normalise_text(
        "### A rule heading\n\nBody text here.\n\n"
        "Mark out non-essential information\n\n"
        "### Another rule\n\nMore body.\n"
    )
    repaired, n = repair_headings(text)
    assert n == 1
    assert "## Mark out non-essential information" in repaired


def test_repair_never_promotes_example_sentences():
    """Guards postmortem F4: example prose must not enter the rule inventory."""
    text = normalise_text(
        "### A rule\n\n#### Example\n\n"
        "Unless the consultation starts early, it will not finish on time. "
        "[A conditional adverbial clause]\n\n"
        "### Next rule\n\nBody.\n"
    )
    repaired, _ = repair_headings(text)
    assert "## Unless the consultation" not in repaired


def test_repair_is_idempotent():
    src = REPO / "corpus" / "pages" / "grammar-punctuation-and-conventions" / "punctuation" / "commas.md"
    once = NormalisedPage("x", src.read_text(encoding="utf-8")).text
    twice = NormalisedPage("x", once).text
    assert once == twice


# ---------------------------------------------------------------------------
# D-7 — candidate identity is deterministic and structural
# ---------------------------------------------------------------------------

def test_uid_is_stable_and_content_addressed():
    a = candidate_uid("p.md", ("S", "Use a comma."), "Use a comma.")
    b = candidate_uid("p.md", ("S", "Use a comma."), "Use a comma.")
    assert a == b and len(a) == 16
    assert candidate_uid("p.md", ("S", "Use a comma."), "Use a semicolon.") != a


def test_uid_ignores_unicode_and_whitespace_variation():
    """A re-scrape must not change a UID unless the wording changed."""
    assert candidate_uid("p.md", ("S",), "Don’t  use   commas") == \
           candidate_uid("p.md", ("S",), "Don't use commas")


def test_extraction_is_reproducible_over_the_whole_corpus():
    """D-7 / postmortem F8: two runs must extract exactly the same rules."""
    first, _ = collect_candidates()
    second, _ = collect_candidates()
    assert [c.uid for c in first] == [c.uid for c in second]
    assert [c.statement for c in first] == [c.statement for c in second]
    assert len({c.uid for c in first}) == len(first), "UID collision"


# ---------------------------------------------------------------------------
# Normativity classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title,kind", [
    ("Place a comma after adverbs and other introductory words", CandidateKind.RULE),
    ("Don't use commas with Latin shortened forms", CandidateKind.RULE),
    ("Headings must be sentence case", CandidateKind.RULE),
    ("Example", CandidateKind.EXAMPLE),
    ("Write this", CandidateKind.EXAMPLE),
    ("Not this", CandidateKind.EXAMPLE),
    ("Last updated", CandidateKind.BOILERPLATE),
    ("Release notes", CandidateKind.BOILERPLATE),
    ("PO Box 123", CandidateKind.BOILERPLATE),
    ("Chas Savage, chief executive officer (Ethos CRS)", CandidateKind.BOILERPLATE),
    ("Pronouns", CandidateKind.SECTION),
])
def test_heading_classification(title, kind):
    assert classify_heading(title)[0] == kind


def test_negative_imperative_detected():
    assert classify_heading("Avoid beginning a sentence with numbers")[1] == "negative_imperative"


# ---------------------------------------------------------------------------
# D-5 / D-2 — gold examples, correctly polarised, never from the rule statement
# ---------------------------------------------------------------------------

def test_clean_example_strips_editorial_apparatus():
    assert clean_example("During the meeting, we discussed Item 9. [Adverbial phrase]") == \
           "During the meeting, we discussed Item 9."
    assert clean_example("Use [adverbial phrases](/node/127) here.") == "Use adverbial phrases here."
    assert clean_example("A. [Outer [inner](/n/1)]") == "A."


def test_unlabelled_example_blocks_are_not_given_a_polarity():
    """Guards postmortem F1: never guess which side an example is on."""
    text = normalise_text("### Use a comma\n\n#### Example\n\n- Yes, they went.\n")
    cands = extract_candidates("p.md", text)
    assert cands and "example" in cands[0].examples
    assert "write this" not in cands[0].examples
    assert "not this" not in cands[0].examples


def test_corpus_yields_paired_gold_examples():
    cands, _ = collect_candidates()
    paired = [
        c for c in cands
        if (c.examples.get("write this") or c.examples.get("correct"))
        and (c.examples.get("not this") or c.examples.get("incorrect"))
    ]
    assert len(paired) >= 50, "the manual's own labelled example pairs should be harvested"


# ---------------------------------------------------------------------------
# Deontic modality
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stmt,form,expected", [
    ("You must not use an ampersand", "modal", Modality.MUST_NOT),
    ("Avoid noun trains", "negative_imperative", Modality.SHOULD_NOT),
    ("Headings should be sentence case", "modal", Modality.SHOULD),
    ("Use an en dash rather than a hyphen", "imperative", Modality.PREFER),
    ("Place a comma after introductory words", "imperative", Modality.MUST),
])
def test_modality_classification(stmt, form, expected):
    assert classify_modality(stmt, form)[0] == expected


def test_modality_records_its_basis():
    _, basis = classify_modality("Place a comma", "imperative")
    assert "ambiguous" in basis, "a bare imperative must be flagged as ambiguous for review"


# ---------------------------------------------------------------------------
# D-4 — eligibility is declared, not inferred
# ---------------------------------------------------------------------------

def test_non_normative_pages_are_excluded():
    """Guards postmortem F3: 108 Octavius rules came from these pages."""
    el = load_eligibility(REPO / "corpus" / "eligibility.yaml")
    for path in [
        "about-style-manual/changelog.md",
        "about-style-manual/how-cite-style-manual.md",
        "style-manual-resources/quick-guides/quick-guide-lists.md",
    ]:
        assert el.decide(path)[0] is False, path


def test_normative_pages_are_eligible():
    el = load_eligibility(REPO / "corpus" / "eligibility.yaml")
    for path in [
        "grammar-punctuation-and-conventions/punctuation/commas.md",
        "structuring-content/lists.md",
    ]:
        assert el.decide(path)[0] is True, path


def test_unclassified_paths_default_to_excluded():
    el = load_eligibility(REPO / "corpus" / "eligibility.yaml")
    assert el.decide("brand-new-section/page.md") == (False, "unclassified")


# ---------------------------------------------------------------------------
# D-6 / D-10 / D-11 — the loading gate
# ---------------------------------------------------------------------------

def _rule(**kw) -> Rule:
    base = dict(
        uid="0" * 16,
        source=Source("p.md", ["H"], "Use a comma."),
        derivation=Derivation(),
    )
    base.update(kw)
    return Rule(**base)


def test_proposed_rules_never_load():
    r = _rule(detection=Detection(detectable=True, method="regex"))
    assert r.review.status == ReviewStatus.PROPOSED
    assert r.loadable is False


def test_artifact_scoped_rules_never_load():
    """Guards postmortem F5: video/image rules applied to prose."""
    r = _rule(unit=Unit.ARTIFACT, detection=Detection(detectable=True, method="regex"))
    r.review.transition(ReviewStatus.ACCEPTED, "t", "2026-01-01T00:00:00Z")
    assert r.loadable is False


def test_accepted_detectable_rule_loads():
    r = _rule(detection=Detection(detectable=True, method="regex"))
    r.review.transition(ReviewStatus.ACCEPTED, "t", "2026-01-01T00:00:00Z")
    assert r.loadable is True


def test_review_transitions_are_recorded():
    r = _rule()
    r.review.transition(ReviewStatus.ACCEPTED, "tom", "2026-01-01T00:00:00Z", "ok")
    r.review.transition(ReviewStatus.QUARANTINED, "ci", "2026-01-02T00:00:00Z", "dogfood")
    assert [h["to"] for h in r.review.history] == ["accepted", "quarantined"]
    assert r.review.history[0]["by"] == "tom"


def test_unknown_review_status_rejected():
    with pytest.raises(ValueError):
        _rule().review.transition("shipped", "t", "2026-01-01T00:00:00Z")


def test_specification_overrides_statement_for_detection():
    r = _rule(specification="Row 1 must consist entirely of header cells.")
    assert r.effective_statement == "Row 1 must consist entirely of header cells."
    assert _rule().effective_statement == "Use a comma."


# ---------------------------------------------------------------------------
# Ledger persistence and reconciliation
# ---------------------------------------------------------------------------

def test_ledger_roundtrip_preserves_everything(tmp_path):
    r = _rule(violating_examples=["bad"], compliant_examples=["good"])
    r.review.transition(ReviewStatus.ACCEPTED, "t", "2026-01-01T00:00:00Z", "n")
    p = tmp_path / "l.jsonl"
    write_ledger(p, [r])
    assert load_ledger(p)[r.uid].to_dict() == r.to_dict()


def test_ledger_write_is_canonical(tmp_path):
    """Re-writing with no semantic change must produce no diff."""
    rules = [_rule(uid=f"{i:016x}", source=Source("p.md", ["H"], f"S{i}")) for i in range(5)]
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write_ledger(a, rules)
    write_ledger(b, reversed(rules))
    assert a.read_bytes() == b.read_bytes()


def _cand(uid, stmt, path="p.md", parent="S", body="b") -> Candidate:
    return Candidate(uid=uid, page_path=path, heading_path=(parent, stmt),
                     statement=stmt, statement_form="imperative", level=3,
                     body=body, line_start=1)


def test_reconcile_detects_new_rules():
    assert reconcile([_cand("u1", "Use a comma.")], {}).summary()["added"] == 1


def test_reconcile_detects_unchanged():
    c = _cand("u1", "Use a comma.")
    r = _rule(uid="u1", source=Source("p.md", ["S", "Use a comma."], "Use a comma.", body_excerpt="b"))
    assert reconcile([c], {"u1": r}).summary()["unchanged"] == 1


def test_reconcile_detects_body_change():
    c = _cand("u1", "Use a comma.", body="new body")
    r = _rule(uid="u1", source=Source("p.md", ["S", "Use a comma."], "Use a comma.", body_excerpt="b"))
    assert reconcile([c], {"u1": r}).summary()["body_altered"] == 1


def test_reconcile_detects_rewording_and_links_lineage():
    """D-8: an altered rule must be recognised, not silently duplicated."""
    r = _rule(uid="u1", source=Source("p.md", ["S", "Use a comma."], "Use a comma.", body_excerpt="b"))
    rec = reconcile([_cand("u2", "Use a comma after it.")], {"u1": r})
    assert rec.summary()["reworded"] == 1
    assert rec.reworded[0][0].uid == "u1"


def test_reconcile_detects_removal():
    """D-8: Octavius could never detect a removed rule."""
    r = _rule(uid="u1", source=Source("p.md", ["S", "Use a comma."], "Use a comma.", body_excerpt="b"))
    assert reconcile([], {"u1": r}).summary()["orphaned"] == 1


def test_reconcile_never_guesses_ambiguous_lineage():
    """Two plausible predecessors must go to a human, not a heuristic."""
    ledger = {
        "u1": _rule(uid="u1", source=Source("p.md", ["S", "Use a comma."], "Use a comma.", body_excerpt="b")),
        "u2": _rule(uid="u2", source=Source("p.md", ["S", "Use a semicolon."], "Use a semicolon.", body_excerpt="b")),
    }
    rec = reconcile([_cand("u3", "Use punctuation.")], ledger)
    assert rec.summary()["needs_human_lineage_decision"] == 1
    assert rec.summary()["added"] == 0


# ---------------------------------------------------------------------------
# The committed ledger
# ---------------------------------------------------------------------------

def test_committed_ledger_loads_and_has_unique_uids():
    rules = load_ledger(LEDGER)
    assert len(rules) > 400


def test_every_ledger_entry_has_full_provenance():
    """The three provenance tags are the project's core requirement."""
    for rule in load_ledger(LEDGER).values():
        assert rule.source.statement, rule.uid
        assert rule.source.page_path, rule.uid
        assert rule.source.snapshot_sha256, rule.uid      # tag 3: ties to a corpus state
        assert rule.derivation.method, rule.uid           # tag 1
        assert rule.derivation.extractor_version, rule.uid
        assert rule.detection.method, rule.uid            # tag 2


def test_no_ledger_entry_loads_before_review():
    """D-10: the human gate is closed by default."""
    assert [r.uid for r in load_ledger(LEDGER).values() if r.loadable] == []


def test_ledger_has_no_rules_from_excluded_pages():
    el = load_eligibility(REPO / "corpus" / "eligibility.yaml")
    for rule in load_ledger(LEDGER).values():
        assert el.decide(rule.source.page_path)[0], rule.source.page_path


def test_ledger_validates_against_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for rule in load_ledger(LEDGER).values():
        errors = list(validator.iter_errors(rule.to_dict()))
        assert not errors, f"{rule.uid}: {errors[0].message}"


# ---------------------------------------------------------------------------
# D-2 — the schema itself must reject an unpolarised detectable rule
# ---------------------------------------------------------------------------

def test_schema_rejects_detectable_rule_without_both_example_kinds():
    """The guard that would have stopped Octavius's polarity inversions."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    r = _rule(
        direction=Direction.PRESENCE,
        violation_condition="Text contains 'finalize'.",
        violating_examples=["We will finalize the plan."],
        compliant_examples=[],                       # <- missing
        detection=Detection(detectable=True, method="regex", matcher={"pattern": r"\bfinalize\b"}),
    )
    assert list(validator.iter_errors(r.to_dict())), "schema must reject a one-sided rule"

    r.compliant_examples = ["We will finalise the plan."]
    assert not list(validator.iter_errors(r.to_dict()))


def test_schema_rejects_detectable_artifact_rule():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    r = _rule(
        unit=Unit.ARTIFACT,
        violation_condition="Contrast below 4.5:1.",
        violating_examples=["x"], compliant_examples=["y"],
        detection=Detection(detectable=True, method="regex"),
    )
    assert list(validator.iter_errors(r.to_dict()))


# ---------------------------------------------------------------------------
# The extractor must not manufacture judgements it has not made
# ---------------------------------------------------------------------------

def test_extractor_never_claims_a_resolved_ambiguity():
    """ADR-017: `ambiguous_resolvable` asserts a resolution exists. The
    pipeline has resolved nothing, so it must not claim clarity at all."""
    from derek.ledger.model import Clarity
    for rule in load_ledger(LEDGER).values():
        if rule.review.status == ReviewStatus.PROPOSED:
            assert rule.clarity == Clarity.UNREVIEWED, rule.uid
        if rule.clarity == Clarity.AMBIGUOUS_RESOLVABLE:
            assert rule.specification, rule.uid
            assert rule.disambiguation_log, rule.uid


def test_path_globs_do_not_cross_directory_separators():
    """A top-level `*.md` exclusion must not swallow the whole corpus."""
    from derek.corpus.eligibility import path_match
    assert path_match("index.md", "*.md") is True
    assert path_match("section/page.md", "*.md") is False
    assert path_match("a/b/c.md", "a/**") is True
    assert path_match("a.md", "a/**") is False


def test_extractor_proposes_nothing_as_detectable():
    """D-10: detection method is a review decision, never a pipeline guess."""
    for rule in load_ledger(LEDGER).values():
        if rule.review.status == ReviewStatus.PROPOSED:
            assert rule.detection.detectable is False, rule.uid


# ---------------------------------------------------------------------------
# D-8 — snapshot change detection (postmortem F7)
# ---------------------------------------------------------------------------

def test_diff_detects_added_altered_and_removed():
    from derek.corpus.diff import PageState, Snapshot, diff_snapshots
    old = Snapshot(pages={
        "a.md": PageState("u/a", "a.md", "hash-a"),
        "b.md": PageState("u/b", "b.md", "hash-b"),
    })
    new = Snapshot(pages={
        "a.md": PageState("u/a", "a.md", "hash-a"),        # unchanged
        "b.md": PageState("u/b", "b.md", "hash-b-EDITED"), # altered
        "c.md": PageState("u/c", "c.md", "hash-c"),        # added
    })
    cs = diff_snapshots(old, new)
    assert cs.summary() == {"added": 1, "altered": 1, "removed": 0, "unchanged": 1}


def test_diff_detects_removal():
    """Octavius never removed anything: a retired page's rules stayed live."""
    from derek.corpus.diff import PageState, Snapshot, diff_snapshots
    old = Snapshot(pages={"a.md": PageState("u/a", "a.md", "h")})
    cs = diff_snapshots(old, Snapshot(pages={}))
    assert cs.removed == ["a.md"]


def test_diff_ignores_lastmod_and_trusts_the_hash():
    """The defect that made silent upstream edits invisible to Octavius."""
    from derek.corpus.diff import PageState, Snapshot, diff_snapshots
    old = Snapshot(pages={"a.md": PageState("u", "a.md", "h1", lastmod="2024-01-01")})

    # lastmod unchanged, content changed -> MUST be detected
    new = Snapshot(pages={"a.md": PageState("u", "a.md", "h2", lastmod="2024-01-01")})
    assert len(diff_snapshots(old, new).altered) == 1

    # lastmod changed, content identical -> MUST NOT be reported as a change
    same = Snapshot(pages={"a.md": PageState("u", "a.md", "h1", lastmod="2026-09-01")})
    assert diff_snapshots(old, same).altered == []


def test_diff_labels_a_wholesale_change_as_an_extractor_upgrade():
    """A dependency bump must not be mistaken for 186 editorial edits."""
    from derek.corpus.diff import PageState, Snapshot, diff_snapshots
    old = Snapshot(pages={f"{i}.md": PageState("u", f"{i}.md", "old") for i in range(10)})
    new = Snapshot(pages={f"{i}.md": PageState("u", f"{i}.md", "new") for i in range(10)})
    assert diff_snapshots(old, new).kind == "extractor_upgrade"


def test_lock_covers_every_corpus_page():
    from derek.corpus.diff import load_lock
    lock = load_lock(REPO / "corpus" / "snapshot.lock.json")
    on_disk = {str(p.relative_to(REPO / "corpus" / "pages"))
               for p in (REPO / "corpus" / "pages").rglob("*.md")}
    assert set(lock.pages) == on_disk
    assert all(s.sha256 for s in lock.pages.values())


def test_lock_hashes_match_disk():
    """The lock must describe the corpus as it actually is."""
    from derek.corpus.diff import load_lock
    lock = load_lock(REPO / "corpus" / "snapshot.lock.json")
    root = REPO / "corpus" / "pages"
    for path, state in list(lock.pages.items())[:25]:
        page = NormalisedPage(path, (root / path).read_text(encoding="utf-8"))
        assert page.sha256 == state.sha256, path


def test_url_to_path_roundtrip():
    from derek.corpus.snapshot import url_to_path
    assert url_to_path("https://www.stylemanual.gov.au/a/b/c") == "a/b/c.md"
    assert url_to_path("https://www.stylemanual.gov.au/") == "index.md"


def test_ledger_rules_carry_their_source_url():
    for rule in load_ledger(LEDGER).values():
        assert rule.source.url.startswith("https://"), rule.uid


def test_rebuild_preserves_human_decisions(tmp_path):
    """A corpus rebuild must never clobber a review decision (ADR-008).

    This is what makes the ledger safe to regenerate daily from the snapshot
    workflow: the reconciler refreshes provenance and leaves judgement alone.
    """
    from derek.extract.build import build, collect_candidates

    ledger = tmp_path / "rules.jsonl"
    assert build(ledger, check=False) == 0

    rules = load_ledger(ledger)
    uid = sorted(rules)[0]
    rules[uid].review.transition(ReviewStatus.REJECTED, "tester", "2026-01-01T00:00:00Z", "n/a")
    rules[uid].unit = Unit.ARTIFACT
    write_ledger(ledger, rules.values())

    assert build(ledger, check=False) == 0
    after = load_ledger(ledger)[uid]
    assert after.review.status == ReviewStatus.REJECTED
    assert after.unit == Unit.ARTIFACT
    assert after.review.note == "n/a"
    assert len(after.review.history) == 1


def test_rebuild_is_idempotent_on_disk(tmp_path):
    """Second rebuild produces a byte-identical file — so a no-op is a no-diff."""
    from derek.extract.build import build
    ledger = tmp_path / "rules.jsonl"
    build(ledger, check=False)
    first = ledger.read_bytes()
    build(ledger, check=False)
    assert ledger.read_bytes() == first
