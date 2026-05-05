"""Tests for the Phase 1 preprocessing layer (`logic.preprocess`)."""

from __future__ import annotations

from logic.preprocess import MASK_CHAR, Segment, preprocess
from logic.sentence_cache import SentenceCache


# ---------------------------------------------------------------------------
# Offset preservation
# ---------------------------------------------------------------------------


_OFFSET_INPUTS = [
    "",
    "Plain text only.",
    "# Heading\nA paragraph.",
    "## Hello\n\nWorld.",
    "Visit https://example.com today.",
    "See `inline code` works.",
    "Path: ./src/foo.py exists.",
    "Run on the main branch please.",
    "Use feature/foo-bar branch.",
    "Set PATH=/usr/bin and DEBUG_MODE on.",
    "He said \"hello world\" to her.",
    "She said 'goodbye there' calmly.",
    "Curly “double quoted” phrase.",
    "Curly ‘single quoted’ phrase.",
    "Snake variable user_name_value here.",
    "CamelCase identifier camelCaseValue here.",
    "Dotted module os.path.join used.",
    "Mention @alice and #topic both.",
    "```\nfenced code\nblock\n```\nAfter.",
    "- item one\n- item two\n",
    "> quote line one\n> quote line two\n",
]


def test_offsets_preserved():
    for text in _OFFSET_INPUTS:
        doc = preprocess(text)
        assert len(doc.masked) == len(doc.original), text
        for i, c in enumerate(text):
            if doc.masked[i] != MASK_CHAR:
                assert doc.masked[i] == c, (i, text)


# ---------------------------------------------------------------------------
# Segment kinds and ancestors
# ---------------------------------------------------------------------------


def test_code_fence_segments_unlintable():
    text = "Intro paragraph.\n\n```python\nprint('hi')\n```\nAfter.\n"
    doc = preprocess(text)
    fences = [s for s in doc.segments if s.kind == "code_fence"]
    assert len(fences) == 1
    assert fences[0].lintable is False


def test_inline_code_masked():
    text = "Run `pytest -v` to test."
    doc = preprocess(text)
    inline_entries = [e for e in doc.mask_map if e[3] == "code_snippet"]
    assert any(e[2] == "`pytest -v`" for e in inline_entries)
    inline_segs = [s for s in doc.segments if s.kind == "inline_code"]
    assert len(inline_segs) == 1
    assert inline_segs[0].lintable is False


def test_quoted_content_masked():
    straight = preprocess('She said "hello there" loudly.')
    assert any(
        e[3] == "quoted_content" and e[2] == '"hello there"'
        for e in straight.mask_map
    )

    curly = preprocess("She said “hello there” loudly.")
    assert any(
        e[3] == "quoted_content" and e[2] == "“hello there”"
        for e in curly.mask_map
    )

    single_curly = preprocess("She wrote ‘hello there’ quietly.")
    assert any(
        e[3] == "quoted_content" and e[2] == "‘hello there’"
        for e in single_curly.mask_map
    )


def test_url_filepath_branchname_masking():
    text = (
        "See https://example.com/path for details. "
        "Open ./src/foo.py first. "
        "Use feature/awesome-thing branch. "
        "Merge to main when done."
    )
    doc = preprocess(text)
    kinds = {e[3] for e in doc.mask_map}
    assert "url" in kinds
    assert "filepath" in kinds
    assert "branchname" in kinds

    url_entries = [e for e in doc.mask_map if e[3] == "url"]
    assert any("https://example.com" in e[2] for e in url_entries)

    branch_entries = [e for e in doc.mask_map if e[3] == "branchname"]
    branch_strs = {e[2] for e in branch_entries}
    assert "main" in branch_strs
    assert any(b.startswith("feature/") for b in branch_strs)


def test_ancestors_populated():
    text = "- A bullet item\n\n  > A quoted line inside the bullet.\n"
    doc = preprocess(text)
    quoted_paragraphs = [
        s
        for s in doc.segments
        if s.kind == "paragraph" and "blockquote" in s.ancestors
    ]
    assert quoted_paragraphs, doc.segments
    seg = quoted_paragraphs[0]
    assert seg.ancestors == ["list_bullet", "blockquote"]


# ---------------------------------------------------------------------------
# The Step 1 noisy example
# ---------------------------------------------------------------------------


def test_step_1_example_segments():
    text = (
        "Step 1 — Merge this branch to main\n"
        "The changes just pushed need to be on main before Render deploys them."
    )
    doc = preprocess(text)

    paragraphs = [s for s in doc.segments if s.kind == "paragraph"]
    assert len(paragraphs) == 1
    assert paragraphs[0].lintable is True

    masked_strings = {e[2] for e in doc.mask_map}
    assert "Render" in masked_strings
    assert "main" in masked_strings

    branch_entries = [e for e in doc.mask_map if e[3] == "branchname"]
    assert len(branch_entries) >= 1
    assert all(e[2] == "main" for e in branch_entries)


# ---------------------------------------------------------------------------
# Counts and language detection
# ---------------------------------------------------------------------------


def test_counts_populated():
    text = (
        "Acme Corp shipped 3 features. NASA approved the launch. "
        "(Optional aside.) John Smith waved."
    )
    doc = preprocess(text)
    for key in ("sentence", "cardinal", "acronym", "proper_noun_likely", "paren_pair"):
        assert key in doc.counts
        assert isinstance(doc.counts[key], int)
        assert doc.counts[key] >= 0
    assert doc.counts["cardinal"] >= 1
    assert doc.counts["acronym"] >= 1
    assert doc.counts["paren_pair"] >= 1


def test_language_detection_default_en():
    assert preprocess("").language == "en"
    assert preprocess("Plain English text here.").language == "en"


# ---------------------------------------------------------------------------
# Sentence cache
# ---------------------------------------------------------------------------


def test_sentence_cache_fifo():
    cache = SentenceCache(max_entries=10_000)
    calls = {"n": 0}

    def compute(s: str) -> list:
        calls["n"] += 1
        return [s]

    sentences = [f"Sentence number {i}." for i in range(10_001)]
    for s in sentences:
        cache.get_or_compute(s, compute)

    assert len(cache) == 10_000
    assert sentences[0] not in cache
    assert sentences[1] in cache
    assert sentences[-1] in cache

    cache.get_or_compute(sentences[1], compute)
    assert calls["n"] == 10_001


def test_sentence_cache_returns_cached_value():
    cache = SentenceCache(max_entries=4)
    seen = []

    def compute(s: str) -> list:
        seen.append(s)
        return [f"finding-for:{s}"]

    out1 = cache.get_or_compute("hello", compute)
    out2 = cache.get_or_compute("hello", compute)
    assert out1 == out2
    assert seen == ["hello"]


# ---------------------------------------------------------------------------
# has_structure / acceptance
# ---------------------------------------------------------------------------


def test_has_structure_flat_paragraph():
    doc = preprocess("Just a paragraph with no markdown structure.")
    assert doc.has_structure is False


def test_has_structure_with_heading():
    doc = preprocess("# Heading\n\nBody.\n")
    assert doc.has_structure is True


def test_acceptance_smoke():
    doc = preprocess("# H\nFoo bar.\n")
    assert any(s.kind == "heading" for s in doc.segments)
    assert any(s.kind == "paragraph" for s in doc.segments)
    assert doc.counts["sentence"] >= 1
