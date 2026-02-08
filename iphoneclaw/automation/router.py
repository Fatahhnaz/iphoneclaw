"""L0 automation router: memoization-based action replay."""
from __future__ import annotations

from typing import List, Optional

from iphoneclaw.automation.cache import L0Cache, L0CacheEntry
from iphoneclaw.automation.fingerprint import dhash
from iphoneclaw.types import PredictionParsed

# Action types that should NOT be cached.
_UNCACHEABLE_ACTIONS = {"finished", "call_user", "error_env"}


class L0Router:
    """In-run memoization router.

    Typical usage from the agent loop::

        router = L0Router(hash_threshold=5, max_reuse=3)
        fp = router.fingerprint(shot.base64)
        hit = router.try_cache(fp, step)
        if hit is not None:
            # execute hit.actions, then:
            router.verify_and_commit(hit, post_fp, step, success=True)
        else:
            # normal VLM path, then on success:
            router.record(fp, actions, post_fp, step)
    """

    def __init__(
        self,
        *,
        hash_threshold: int = 5,
        max_reuse: int = 3,
        status_bar_frac: float = 0.08,
    ) -> None:
        self.cache = L0Cache(
            hash_threshold=hash_threshold,
            max_reuse=max_reuse,
        )
        self.status_bar_frac = status_bar_frac

    def fingerprint(self, b64: str) -> Optional[int]:
        """Compute dHash fingerprint from screenshot JPEG base64."""
        return dhash(b64, status_bar_frac=self.status_bar_frac)

    def try_cache(self, fp: Optional[int], step: int) -> Optional[L0CacheEntry]:
        """Look up a cache entry for *fp*.

        Returns the entry on hit, ``None`` on miss.  Does **not** increment
        ``hit_count`` — the caller must call :meth:`verify_and_commit` after
        executing the cached actions.
        """
        if fp is None:
            return None
        return self.cache.lookup(fp)

    def verify_and_commit(
        self,
        entry: L0CacheEntry,
        post_fp: Optional[int],
        step: int,
        success: bool,
    ) -> bool:
        """After executing cached actions, verify the screen changed.

        Returns ``True`` if verification passed.
        """
        if not success:
            self.cache.mark_failed(entry)
            return False

        # Screen must have changed (exact equality — even 1 bit flip is fine).
        if post_fp is not None and post_fp == entry.fingerprint:
            self.cache.evict(entry)
            return False

        self.cache.record_hit(entry, step)
        return True

    def should_cache_actions(self, actions: List[PredictionParsed]) -> bool:
        """Return ``True`` if *actions* are suitable for caching."""
        if not actions:
            return False
        return all(a.action_type not in _UNCACHEABLE_ACTIONS for a in actions)

    def record(
        self,
        fp: Optional[int],
        actions: List[PredictionParsed],
        post_fp: Optional[int],
        step: int,
    ) -> None:
        """Store a successful VLM-driven action for future cache hits."""
        if fp is None:
            return
        if not self.should_cache_actions(actions):
            return
        self.cache.store(fp, actions, post_fp, step)
