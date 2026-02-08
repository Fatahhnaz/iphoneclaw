"""L0 in-run memoization cache: fingerprint -> known-good actions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from iphoneclaw.automation.fingerprint import hamming_distance
from iphoneclaw.types import PredictionParsed


@dataclass
class L0CacheEntry:
    """One cached screen -> action mapping."""

    fingerprint: int
    actions: List[PredictionParsed]
    post_fingerprint: Optional[int] = None
    hit_count: int = 0
    last_step: int = 0
    succeeded: bool = True


class L0Cache:
    """In-run fingerprint -> action cache with near-match lookup.

    Linear scan is fine for <= *max_entries* entries (64-bit XOR + popcount).
    """

    def __init__(
        self,
        *,
        hash_threshold: int = 5,
        max_reuse: int = 3,
        max_entries: int = 256,
    ) -> None:
        self.hash_threshold = hash_threshold
        self.max_reuse = max_reuse
        self.max_entries = max_entries
        self._entries: Dict[int, L0CacheEntry] = {}

    def lookup(self, fingerprint: int) -> Optional[L0CacheEntry]:
        """Find a cache entry within hamming threshold.

        Skips entries that have failed or exhausted their reuse budget.
        Returns the closest match or ``None``.
        """
        best: Optional[L0CacheEntry] = None
        best_dist = self.hash_threshold + 1

        for entry in self._entries.values():
            if not entry.succeeded:
                continue
            if entry.hit_count >= self.max_reuse:
                continue
            dist = hamming_distance(fingerprint, entry.fingerprint)
            if dist < best_dist:
                best_dist = dist
                best = entry

        return best

    def record_hit(self, entry: L0CacheEntry, step: int) -> None:
        """Increment hit count after a successful cache replay."""
        entry.hit_count += 1
        entry.last_step = step

    def store(
        self,
        fingerprint: int,
        actions: List[PredictionParsed],
        post_fingerprint: Optional[int],
        step: int,
    ) -> None:
        """Store a new cache entry after a successful VLM-driven action."""
        if len(self._entries) >= self.max_entries and fingerprint not in self._entries:
            oldest_fp = min(self._entries, key=lambda fp: self._entries[fp].last_step)
            del self._entries[oldest_fp]

        self._entries[fingerprint] = L0CacheEntry(
            fingerprint=fingerprint,
            actions=actions,
            post_fingerprint=post_fingerprint,
            hit_count=0,
            last_step=step,
            succeeded=True,
        )

    def evict(self, entry: L0CacheEntry) -> None:
        """Remove a cache entry (verification failed)."""
        self._entries.pop(entry.fingerprint, None)

    def mark_failed(self, entry: L0CacheEntry) -> None:
        """Mark entry as failed so lookup will skip it."""
        entry.succeeded = False

    def stats(self) -> Dict[str, int]:
        """Cache statistics for logging."""
        total = len(self._entries)
        failed = sum(1 for e in self._entries.values() if not e.succeeded)
        exhausted = sum(1 for e in self._entries.values() if e.hit_count >= self.max_reuse)
        return {"total": total, "failed": failed, "exhausted": exhausted}
