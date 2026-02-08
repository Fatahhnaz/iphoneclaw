"""Tests for iphoneclaw.automation.cache (L0 in-run memoization cache)."""
from __future__ import annotations

import pytest

from iphoneclaw.automation.cache import L0Cache, L0CacheEntry
from iphoneclaw.types import ActionInputs, PredictionParsed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pred(action_type: str = "click", raw: str = "click(start_box='(500,500)')") -> PredictionParsed:
    return PredictionParsed(
        action_type=action_type,
        action_inputs=ActionInputs(start_box="(500,500)"),
        thought="test",
        raw_action=raw,
    )


# ---------------------------------------------------------------------------
# L0Cache
# ---------------------------------------------------------------------------

class TestL0CacheStore:
    def test_store_and_exact_lookup(self):
        cache = L0Cache(hash_threshold=5, max_reuse=3)
        actions = [_pred()]
        cache.store(1000, actions, post_fingerprint=2000, step=1)

        entry = cache.lookup(1000)
        assert entry is not None
        assert entry.fingerprint == 1000
        assert entry.actions == actions
        assert entry.hit_count == 0

    def test_near_match_within_threshold(self):
        cache = L0Cache(hash_threshold=5, max_reuse=3)
        cache.store(1000, [_pred()], post_fingerprint=2000, step=1)

        # Hamming distance 1 (flip one bit)
        entry = cache.lookup(1001)
        assert entry is not None
        assert entry.fingerprint == 1000

    def test_miss_beyond_threshold(self):
        cache = L0Cache(hash_threshold=0, max_reuse=3)
        cache.store(1000, [_pred()], post_fingerprint=2000, step=1)

        # Exact match only (threshold=0), so 1001 should miss.
        entry = cache.lookup(1001)
        assert entry is None

    def test_exact_match_with_threshold_zero(self):
        cache = L0Cache(hash_threshold=0, max_reuse=3)
        cache.store(1000, [_pred()], post_fingerprint=2000, step=1)
        entry = cache.lookup(1000)
        assert entry is not None


class TestL0CacheReuse:
    def test_max_reuse_exhaustion(self):
        cache = L0Cache(hash_threshold=5, max_reuse=2)
        cache.store(1000, [_pred()], post_fingerprint=2000, step=1)

        entry = cache.lookup(1000)
        assert entry is not None
        cache.record_hit(entry, step=2)

        entry = cache.lookup(1000)
        assert entry is not None
        cache.record_hit(entry, step=3)

        # Now hit_count == 2 == max_reuse, should not be returned.
        entry = cache.lookup(1000)
        assert entry is None

    def test_record_hit_increments(self):
        cache = L0Cache(hash_threshold=5, max_reuse=10)
        cache.store(1000, [_pred()], post_fingerprint=2000, step=1)

        entry = cache.lookup(1000)
        assert entry is not None
        assert entry.hit_count == 0
        cache.record_hit(entry, step=2)
        assert entry.hit_count == 1
        assert entry.last_step == 2


class TestL0CacheEvict:
    def test_evict(self):
        cache = L0Cache(hash_threshold=5, max_reuse=3)
        cache.store(1000, [_pred()], post_fingerprint=2000, step=1)

        entry = cache.lookup(1000)
        assert entry is not None
        cache.evict(entry)

        assert cache.lookup(1000) is None

    def test_mark_failed(self):
        cache = L0Cache(hash_threshold=5, max_reuse=3)
        cache.store(1000, [_pred()], post_fingerprint=2000, step=1)

        entry = cache.lookup(1000)
        assert entry is not None
        cache.mark_failed(entry)

        # Failed entries should be skipped by lookup.
        assert cache.lookup(1000) is None


class TestL0CacheCapacity:
    def test_max_entries_eviction(self):
        cache = L0Cache(hash_threshold=0, max_reuse=3, max_entries=3)

        cache.store(100, [_pred()], post_fingerprint=200, step=1)
        cache.store(200, [_pred()], post_fingerprint=300, step=2)
        cache.store(300, [_pred()], post_fingerprint=400, step=3)

        # Cache is full (3 entries). Storing a new one should evict the oldest.
        cache.store(400, [_pred()], post_fingerprint=500, step=4)

        # 100 was oldest (step=1), should be evicted.
        assert cache.lookup(100) is None
        # Others should still be there.
        assert cache.lookup(200) is not None
        assert cache.lookup(300) is not None
        assert cache.lookup(400) is not None

    def test_overwrite_existing_fingerprint_no_eviction(self):
        cache = L0Cache(hash_threshold=0, max_reuse=3, max_entries=2)
        cache.store(100, [_pred("click")], post_fingerprint=200, step=1)
        cache.store(200, [_pred("scroll")], post_fingerprint=300, step=2)

        # Overwrite existing fingerprint -- should NOT evict.
        cache.store(100, [_pred("drag")], post_fingerprint=400, step=3)

        assert cache.lookup(100) is not None
        assert cache.lookup(100).actions[0].action_type == "drag"
        assert cache.lookup(200) is not None


class TestL0CacheStats:
    def test_stats_empty(self):
        cache = L0Cache()
        s = cache.stats()
        assert s == {"total": 0, "failed": 0, "exhausted": 0}

    def test_stats_counts(self):
        cache = L0Cache(max_reuse=1)
        cache.store(100, [_pred()], post_fingerprint=200, step=1)
        cache.store(200, [_pred()], post_fingerprint=300, step=2)

        entry1 = cache.lookup(100)
        cache.record_hit(entry1, step=3)  # Now exhausted (hit_count=1 >= max_reuse=1)

        entry2 = cache.lookup(200)
        cache.mark_failed(entry2)

        s = cache.stats()
        assert s["total"] == 2
        assert s["failed"] == 1
        assert s["exhausted"] == 1
