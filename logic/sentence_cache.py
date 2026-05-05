"""Process-local FIFO sentence-hash cache (Phase 1).

Phase 4 will reuse this cache across dispatcher invocations to avoid
re-running per-sentence rule logic for sentences that have already been
linted in this process.

Lifecycle
---------
* The cache is **process-local**: it lives in instance state on a
  :class:`SentenceCache` object created at module import time by the
  caller (typically the indexed dispatcher in Phase 4). It is *not*
  shared between worker processes.
* Eviction is FIFO with a configurable upper bound (default 10,000
  entries). Insertion order is preserved by ``OrderedDict`` so the
  oldest entry is always the one popped on overflow.
* The cache stores whatever ``compute(sentence)`` returns. It does no
  cloning, so callers must not mutate returned :class:`Finding`
  objects in place.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Any, Callable


class SentenceCache:
    """FIFO cache keyed by SHA-256 truncated to 16 hex chars."""

    def __init__(self, max_entries: int = 10_000) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._store: OrderedDict[str, list[Any]] = OrderedDict()

    @staticmethod
    def _key(sentence: str) -> str:
        return hashlib.sha256(sentence.encode("utf-8")).hexdigest()[:16]

    def get_or_compute(
        self,
        sentence: str,
        compute: Callable[[str], list[Any]],
    ) -> list[Any]:
        key = self._key(sentence)
        cached = self._store.get(key)
        if cached is not None:
            return cached
        value = compute(sentence)
        self._store[key] = value
        if len(self._store) > self.max_entries:
            self._store.popitem(last=False)
        return value

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, sentence: str) -> bool:
        return self._key(sentence) in self._store

    def clear(self) -> None:
        self._store.clear()


__all__ = ["SentenceCache"]
