from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ConversationItem:
    role: str  # "system" | "user" | "assistant"
    text: str
    ts: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)


class ConversationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: List[ConversationItem] = []

    def add(self, role: str, text: str, **meta: Any) -> None:
        with self._lock:
            self._items.append(
                ConversationItem(role=role, text=text, ts=time.time(), meta=dict(meta))
            )

    def items(self) -> List[ConversationItem]:
        with self._lock:
            return list(self._items)

    def to_openai_messages(
        self, *, include_system: bool = True, tail_rounds: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Convert to OpenAI-compatible message list (text only).
        'tail_rounds' counts assistant turns.
        """
        items = self._tail_items_by_rounds(tail_rounds)
        out: List[Dict[str, Any]] = []
        for it in items:
            if it.role == "system" and not include_system:
                continue
            out.append({"role": it.role, "content": it.text})
        return out

    def _tail_items_by_rounds(self, tail_rounds: int) -> List[ConversationItem]:
        with self._lock:
            items = list(self._items)

        assistant_seen = 0
        start_idx = 0
        for i in range(len(items) - 1, -1, -1):
            if items[i].role == "assistant":
                assistant_seen += 1
                if assistant_seen >= tail_rounds:
                    start_idx = i
                    break
        # Ensure we include the user prompt that triggered the first assistant turn.
        if start_idx > 0 and items[start_idx].role == "assistant":
            if items[start_idx - 1].role == "user":
                start_idx -= 1
        return items[start_idx:] if items else []

    def tail_rounds(self, tail_rounds: int) -> List[Dict[str, Any]]:
        sliced = self._tail_items_by_rounds(tail_rounds)
        return [
            {
                "role": it.role,
                "text": it.text,
                "ts": it.ts,
                "meta": it.meta,
            }
            for it in sliced
        ]
