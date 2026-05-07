"""Preprocessing layer for the inverted-index pipeline (Phase 1).

This module is standalone — it is *not* yet wired into the dispatcher
(that happens in Phase 4). It accepts a free-form Markdown / plain-text
string and produces a :class:`PreprocessedDoc` containing:

* a list of :class:`Segment` blocks (heading, paragraph, list_bullet, …)
  walked from a markdown-it-py token stream and tagged with their
  ``ancestors`` chain;
* a *masked* copy of the original text where non-prose regions
  (URLs, file paths, branch names, identifiers, env vars, product names,
  mentions/hashtags, code snippets, quoted content) are replaced with
  the private-use sentinel ``\\uE000``;
* a ``mask_map`` of ``(start, end, original, exemption_kind)`` records
  whose ``exemption_kind`` values map 1-for-1 to the ``EXEMPT_*``
  feature names in :mod:`logic.features.vocabulary` (the names drop the
  ``EXEMPT_`` prefix and lowercase).

  Internally the module masks bytes (so byte offsets line up with the
  original) but the kind names are the semantic exemption category.

* a ``counts`` dictionary with the lightweight regex-derived integers
  (``sentence``, ``cardinal``, ``acronym``, ``proper_noun_likely``,
  ``paren_pair``). These are reserved for a future ``min_count``
  requirement type and are NOT consumed by any rule in this phase.
* a cached spaCy ``Doc`` (built from the unmasked paragraph text) for
  Phase 2 to reuse without re-parsing.
* boolean ``has_structure`` (any heading / list / fence) and a best-effort
  ``language`` string defaulting to ``"en"`` on any failure.

The mask preserves byte offsets exactly — ``len(masked) == len(original)``
for every input.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from markdown_it import MarkdownIt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

SegmentKind = Literal[
    "heading",
    "paragraph",
    "list_bullet",
    "list_numbered",
    "blockquote",
    "code_fence",
    "inline_code",
    "table_cell",
    "footnote",
    "reference_list",
]


ExemptionKind = Literal[
    "url",
    "filepath",
    "branchname",
    "identifier",
    "env_var",
    "product_name",
    "mention_or_hashtag",
    "code_snippet",
    "quoted_content",
]


@dataclass
class Segment:
    kind: SegmentKind
    text: str
    offset: int
    lintable: bool
    ancestors: list[str] = field(default_factory=list)


@dataclass
class PreprocessedDoc:
    original: str
    masked: str
    segments: list[Segment]
    mask_map: list[tuple[int, int, str, str]]
    counts: dict[str, int]
    sentence_count: int
    has_structure: bool
    language: str
    spacy_doc: Any = None


# ---------------------------------------------------------------------------
# Internals: parser and spaCy loader (lazy, process-local)
# ---------------------------------------------------------------------------

MASK_CHAR = ""

_MD = MarkdownIt("commonmark", {"html": False}).enable("table")

_NLP: Any = None


def _get_nlp() -> Any:
    """Return a process-local spaCy pipeline for sentence splitting and POS/dep parse.

    Uses ``en_core_web_sm`` with NER and lemmatizer disabled for quality
    sentence boundary detection and dependency labels (Phase 2 reuses
    ``doc.spacy_doc`` for per-segment linguistic feature extraction).
    """
    global _NLP
    if _NLP is None:
        try:
            import spacy  # type: ignore[import-untyped]

            _NLP = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
        except Exception:  # pragma: no cover - spaCy missing entirely
            _NLP = None
    return _NLP


# ---------------------------------------------------------------------------
# Markdown segmentation
# ---------------------------------------------------------------------------


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for i, c in enumerate(text):
        if c == "\n":
            starts.append(i + 1)
    starts.append(len(text))
    return starts


def _slice_for_map(
    text: str, line_starts: list[int], tok_map: list[int] | None
) -> tuple[int, int]:
    """Return ``(start, end)`` char offsets for a token's ``map`` line range.

    ``map`` is ``[start_line, end_line)`` (zero-based, exclusive end).
    """
    if not tok_map:
        return 0, 0
    start_line, end_line = tok_map[0], tok_map[1]
    last_line = len(line_starts) - 1
    start = line_starts[min(start_line, last_line)]
    end = line_starts[min(end_line, last_line)]
    if end > start and text[end - 1 : end] == "\n":
        end -= 1
    return start, end


def _segment_markdown(text: str) -> tuple[list[Segment], list[tuple[int, int]]]:
    """Walk markdown-it tokens; return segments and code-fence char ranges.

    The returned code-fence ranges are used by the mask pass to skip
    inline-code regex matching inside fenced blocks.
    """
    segments: list[Segment] = []
    code_ranges: list[tuple[int, int]] = []

    line_starts = _line_starts(text)
    tokens = _MD.parse(text)

    ancestors: list[str] = []
    list_kind_stack: list[str] = []

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        ttype = tok.type

        if ttype == "heading_open":
            start, end = _slice_for_map(text, line_starts, tok.map)
            segments.append(
                Segment(
                    kind="heading",
                    text=text[start:end],
                    offset=start,
                    lintable=True,
                    ancestors=list(ancestors),
                )
            )
        elif ttype == "paragraph_open":
            start, end = _slice_for_map(text, line_starts, tok.map)
            # Paragraphs inside a list item take the containing list's kind so
            # ZONE_LIST_BULLET / ZONE_LIST_NUMBERED fire correctly in Phase 2.
            if ancestors and ancestors[-1] in ("list_bullet", "list_numbered"):
                seg_kind: str = ancestors[-1]
            else:
                seg_kind = "paragraph"
            segments.append(
                Segment(
                    kind=seg_kind,
                    text=text[start:end],
                    offset=start,
                    lintable=True,
                    ancestors=list(ancestors),
                )
            )
        elif ttype in ("fence", "code_block"):
            start, end = _slice_for_map(text, line_starts, tok.map)
            segments.append(
                Segment(
                    kind="code_fence",
                    text=text[start:end],
                    offset=start,
                    lintable=False,
                    ancestors=list(ancestors),
                )
            )
            code_ranges.append((start, end))
        elif ttype == "bullet_list_open":
            list_kind_stack.append("list_bullet")
        elif ttype == "bullet_list_close":
            if list_kind_stack:
                list_kind_stack.pop()
        elif ttype == "ordered_list_open":
            list_kind_stack.append("list_numbered")
        elif ttype == "ordered_list_close":
            if list_kind_stack:
                list_kind_stack.pop()
        elif ttype == "list_item_open":
            ancestors.append(
                list_kind_stack[-1] if list_kind_stack else "list_bullet"
            )
        elif ttype == "list_item_close":
            if ancestors:
                ancestors.pop()
        elif ttype == "blockquote_open":
            ancestors.append("blockquote")
        elif ttype == "blockquote_close":
            if ancestors:
                ancestors.pop()
        elif ttype in ("th_open", "td_open"):
            close_type = ttype.replace("_open", "_close")
            j = i + 1
            depth = 1
            while j < len(tokens):
                if tokens[j].type == ttype:
                    depth += 1
                elif tokens[j].type == close_type:
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            tok_map = tok.map
            if not tok_map:
                # Fall back to the inline child's map.
                for k in range(i + 1, j):
                    if tokens[k].type == "inline" and tokens[k].map:
                        tok_map = tokens[k].map
                        break
            start, end = _slice_for_map(text, line_starts, tok_map)
            segments.append(
                Segment(
                    kind="table_cell",
                    text=text[start:end],
                    offset=start,
                    lintable=True,
                    ancestors=list(ancestors),
                )
            )
            i = j  # consumed up to the closing token
        i += 1

    return segments, code_ranges


# ---------------------------------------------------------------------------
# Inline code segments + masking
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
# File paths: posix-absolute, relative ./ or ../, or any path component with a
# common extension. Deliberately conservative — we'd rather under-mask than
# steal characters from prose.
_FILEPATH_RE = re.compile(
    r"(?:"
    r"(?:\./|\.\./)[\w./\-]+"
    r"|(?<![\w/])/[\w\-]+(?:/[\w.\-]+)+"
    r"|\b[\w\-]+(?:/[\w.\-]+)+"
    r"|\b[\w\-]+\.(?:py|md|txt|json|ya?ml|toml|ini|cfg|html?|css|jsx?|tsx?"
    r"|sh|bash|zip|tar|gz|csv|tsv|parquet|sql|xml|svg|png|jpe?g|gif"
    r"|pdf|docx?|xlsx?|pptx?)\b"
    r")"
)
_BRANCH_RE = re.compile(
    r"(?:feature|release|hotfix|bugfix)/[\w./\-]+"
    r"|\b(?:main|master|develop)\b"
)
_SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){2,}\b")
_CAMEL_RE = re.compile(r"\b[a-z][a-z0-9]*[A-Z][A-Za-z0-9]+\b")
_DOTTED_RE = re.compile(r"\b[a-z][a-z0-9_]+(?:\.[a-z][a-z0-9_]+)+\b")
_ENV_VAR_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_PRODUCT_RE = re.compile(r"\b[A-Z][a-z0-9]+(?:-[A-Z][a-z0-9]+)+\b")
# Standalone Title-Case word (≥5 letters) mid-sentence: heuristic for product
# / service names. Sentence-start words are filtered in the masking pass.
# Over-masks some proper nouns; documented in REFACTOR_LOG Phase 1.
_PRODUCT_STANDALONE_RE = re.compile(r"\b[A-Z][a-z]{4,}\b")
_MENTION_HASH_RE = re.compile(r"[@#]\w+")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_DOLLAR_LINE_RE = re.compile(r"(?m)^(?:\$|>>>) .*$")
_QUOTED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'"[^"\n]+?"'),
    re.compile(r"(?<!\w)'[^'\n]+?'(?!\w)"),
    re.compile("“[^“”\n]+?”"),
    re.compile("‘[^‘’\n]+?’"),
]


def _in_any(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    for r_start, r_end in ranges:
        if start >= r_start and end <= r_end:
            return True
    return False


def _is_sentence_start(text: str, idx: int) -> bool:
    """True when ``idx`` is the start of a sentence (text start or after .!?)."""
    j = idx - 1
    while j >= 0 and text[j].isspace():
        j -= 1
    if j < 0:
        return True
    return text[j] in ".!?"


def _build_masks_and_inline_segments(
    text: str, code_ranges: list[tuple[int, int]]
) -> tuple[str, list[tuple[int, int, str, str]], list[Segment]]:
    """Produce the masked string, mask_map, and inline_code Segments.

    Patterns are applied in priority order; later matches that overlap an
    already-masked region are skipped, guaranteeing each character belongs
    to at most one ``mask_map`` entry.
    """
    used = bytearray(len(text))
    mask_map: list[tuple[int, int, str, str]] = []
    inline_segments: list[Segment] = []

    def try_mask(start: int, end: int, kind: str) -> bool:
        if start >= end or end > len(text):
            return False
        for k in range(start, end):
            if used[k]:
                return False
        for k in range(start, end):
            used[k] = 1
        mask_map.append((start, end, text[start:end], kind))
        return True

    # 1. Inline code (skip ranges already inside fenced code segments).
    for m in _INLINE_CODE_RE.finditer(text):
        if _in_any(m.start(), m.end(), code_ranges):
            continue
        if try_mask(m.start(), m.end(), "code_snippet"):
            inline_segments.append(
                Segment(
                    kind="inline_code",
                    text=m.group(0),
                    offset=m.start(),
                    lintable=False,
                    ancestors=[],
                )
            )

    # 2. Shell-prompt / REPL lines.
    for m in _DOLLAR_LINE_RE.finditer(text):
        try_mask(m.start(), m.end(), "code_snippet")

    # Specific patterns first — generic identifier patterns last.
    for pattern, kind in (
        (_URL_RE, "url"),
        (_BRANCH_RE, "branchname"),
        (_FILEPATH_RE, "filepath"),
        (_MENTION_HASH_RE, "mention_or_hashtag"),
        (_PRODUCT_RE, "product_name"),
        (_SNAKE_RE, "identifier"),
        (_CAMEL_RE, "identifier"),
        (_DOTTED_RE, "identifier"),
    ):
        for m in pattern.finditer(text):
            if _in_any(m.start(), m.end(), code_ranges):
                continue
            try_mask(m.start(), m.end(), kind)

    # Env vars: skip when the match is at the start of a sentence.
    for m in _ENV_VAR_RE.finditer(text):
        if _in_any(m.start(), m.end(), code_ranges):
            continue
        if _is_sentence_start(text, m.start()):
            continue
        try_mask(m.start(), m.end(), "env_var")

    # Standalone Title-Case words mid-sentence (heuristic product name).
    for m in _PRODUCT_STANDALONE_RE.finditer(text):
        if _in_any(m.start(), m.end(), code_ranges):
            continue
        if _is_sentence_start(text, m.start()):
            continue
        try_mask(m.start(), m.end(), "product_name")

    # Quoted content last so quotes wrapping prose don't shadow earlier kinds.
    for pattern in _QUOTED_PATTERNS:
        for m in pattern.finditer(text):
            if _in_any(m.start(), m.end(), code_ranges):
                continue
            try_mask(m.start(), m.end(), "quoted_content")

    masked_chars = list(text)
    for k in range(len(text)):
        if used[k]:
            masked_chars[k] = MASK_CHAR
    masked = "".join(masked_chars)

    mask_map.sort(key=lambda r: r[0])
    inline_segments.sort(key=lambda s: s.offset)
    return masked, mask_map, inline_segments


# ---------------------------------------------------------------------------
# Counts, sentence splitting, language detection
# ---------------------------------------------------------------------------

_CARDINAL_RE = re.compile(r"\b\d+\b")
_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-z]+\b")
_PAREN_PAIR_RE = re.compile(r"\([^()\n]*\)")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+(?=\s|$)")


def _count_sentences_fallback(text: str) -> int:
    text = text.strip()
    if not text:
        return 0
    matches = list(_SENTENCE_SPLIT_RE.finditer(text))
    if not matches:
        return 1
    count = len(matches)
    if matches[-1].end() < len(text):
        count += 1
    return count


def _build_counts(text: str, sentence_count: int) -> dict[str, int]:
    return {
        "sentence": sentence_count,
        "cardinal": len(_CARDINAL_RE.findall(text)),
        "acronym": len(_ACRONYM_RE.findall(text)),
        "proper_noun_likely": len(_PROPER_NOUN_RE.findall(text)),
        "paren_pair": len(_PAREN_PAIR_RE.findall(text)),
    }


def _detect_language(text: str) -> str:
    """ASCII-letter heuristic. Returns ``"en"`` on any failure or for empty input.

    ``langdetect`` is not used here — its sdist failed to build in the
    project's CI environment (see commit message for Phase 1) and the
    Australian Public Service content this linter targets is overwhelmingly
    ASCII English. The heuristic returns ``"en"`` when ≥80% of letter
    characters are ASCII, ``"und"`` otherwise. Never raises.
    """
    try:
        if not text or not text.strip():
            return "en"
        letters = [c for c in text if c.isalpha()]
        if not letters:
            return "en"
        ascii_letters = sum(1 for c in letters if ord(c) < 128)
        ratio = ascii_letters / len(letters)
        return "en" if ratio >= 0.8 else "und"
    except Exception:
        logger.info("language detection failed; defaulting to 'en'")
        return "en"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def preprocess(text: str) -> PreprocessedDoc:
    """Tokenise, segment, mask, and decorate ``text`` for Phase 2.

    The function is pure: it never mutates global state (beyond a single
    lazy spaCy load) and never raises on malformed input.
    """
    if text is None:
        text = ""

    segments, code_ranges = _segment_markdown(text)
    masked, mask_map, inline_segments = _build_masks_and_inline_segments(
        text, code_ranges
    )
    segments.extend(inline_segments)
    segments.sort(key=lambda s: (s.offset, 0 if s.lintable else 1))

    paragraph_text = "\n\n".join(
        s.text for s in segments if s.kind == "paragraph"
    )
    spacy_doc = None
    sentence_count = 0
    nlp = _get_nlp()
    if nlp is not None and paragraph_text.strip():
        try:
            spacy_doc = nlp(paragraph_text)
            sentence_count = sum(1 for _ in spacy_doc.sents)
        except Exception:
            logger.info("spaCy parse failed; falling back to regex sentencizer")
            sentence_count = _count_sentences_fallback(paragraph_text)
    elif paragraph_text.strip():
        sentence_count = _count_sentences_fallback(paragraph_text)

    has_structure = any(
        s.kind in ("heading", "list_bullet", "list_numbered", "code_fence")
        or "list_bullet" in s.ancestors
        or "list_numbered" in s.ancestors
        for s in segments
    )

    counts = _build_counts(text, sentence_count)
    language = _detect_language(text)

    return PreprocessedDoc(
        original=text,
        masked=masked,
        segments=segments,
        mask_map=mask_map,
        counts=counts,
        sentence_count=sentence_count,
        has_structure=has_structure,
        language=language,
        spacy_doc=spacy_doc,
    )


def from_zones(text: str, zones: list[dict]) -> PreprocessedDoc:
    """Build a :class:`PreprocessedDoc` from frontend-supplied zone data.

    Skips markdown segmentation and uses the provided zone list directly as
    the segment list.  All other preprocessing steps run unchanged: masking,
    counts, language detection, and spaCy sentence parsing.

    Parameters
    ----------
    text:
        The plain text of the document (same string whose character offsets the
        zones reference).
    zones:
        A list of zone dicts matching the frontend Zone type:
        ``{kind, text, offset, length, ancestors, lintable}``.

    Notes on differences from the markdown path
    -------------------------------------------
    * ``blockquote`` zones are emitted with their own ``kind`` here (the
      Tiptap serialiser walks into blockquote children with
      ``ancestors=["blockquote"]``), whereas the markdown path promotes them to
      ``paragraph`` with ``ancestors=["blockquote"]``.  Rules that rely on
      ``ZONE_PARAGRAPH + ANCESTOR_BLOCKQUOTE`` will not fire on the zone path;
      rules that rely on ``ZONE_BLOCKQUOTE`` will.
    * Inline-code zones supplied by the frontend take precedence over the
      regex-derived ones; duplicates (same offset) are deduplicated.
    """
    if text is None:
        text = ""

    # Build code_ranges from code_fence / inline_code zones so the masker
    # skips inline-code detection inside those regions.
    segments: list[Segment] = []
    code_ranges: list[tuple[int, int]] = []

    for z in zones:
        kind: str = z.get("kind", "paragraph")
        offset: int = z.get("offset", 0)
        zone_text: str = z.get("text", "")
        lintable: bool = z.get("lintable", kind not in ("code_fence", "inline_code"))
        ancestors: list[str] = list(z.get("ancestors") or [])

        segments.append(
            Segment(
                kind=kind,  # type: ignore[arg-type]
                text=zone_text,
                offset=offset,
                lintable=lintable,
                ancestors=ancestors,
            )
        )
        if kind in ("code_fence", "inline_code"):
            code_ranges.append((offset, offset + len(zone_text)))

    masked, mask_map, inline_segs = _build_masks_and_inline_segments(
        text, code_ranges
    )

    # Merge regex-derived inline_code segments that the frontend didn't supply.
    existing_inline_offsets = {
        s.offset for s in segments if s.kind == "inline_code"
    }
    for seg in inline_segs:
        if seg.offset not in existing_inline_offsets:
            segments.append(seg)

    segments.sort(key=lambda s: (s.offset, 0 if s.lintable else 1))

    paragraph_text = "\n\n".join(
        s.text for s in segments if s.kind == "paragraph"
    )
    spacy_doc = None
    sentence_count = 0
    nlp = _get_nlp()
    if nlp is not None and paragraph_text.strip():
        try:
            spacy_doc = nlp(paragraph_text)
            sentence_count = sum(1 for _ in spacy_doc.sents)
        except Exception:
            logger.info("spaCy parse failed; falling back to regex sentencizer")
            sentence_count = _count_sentences_fallback(paragraph_text)
    elif paragraph_text.strip():
        sentence_count = _count_sentences_fallback(paragraph_text)

    has_structure = any(
        s.kind in ("heading", "list_bullet", "list_numbered", "code_fence")
        or "list_bullet" in s.ancestors
        or "list_numbered" in s.ancestors
        for s in segments
    )

    counts = _build_counts(text, sentence_count)
    language = _detect_language(text)

    return PreprocessedDoc(
        original=text,
        masked=masked,
        segments=segments,
        mask_map=mask_map,
        counts=counts,
        sentence_count=sentence_count,
        has_structure=has_structure,
        language=language,
        spacy_doc=spacy_doc,
    )


__all__ = [
    "Segment",
    "SegmentKind",
    "ExemptionKind",
    "PreprocessedDoc",
    "preprocess",
    "from_zones",
    "MASK_CHAR",
]
