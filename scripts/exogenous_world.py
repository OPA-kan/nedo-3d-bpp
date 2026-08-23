"""Deterministic exogenous chance worlds for paired physical continuations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


def _stable_digest(namespace: str, payload: dict[str, Any]) -> bytes:
    encoded = json.dumps(
        {"namespace": namespace, "payload": payload},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).digest()


class _EventRandom:
    """Minimal ``random.Random``-compatible stream scoped to one event."""

    def __init__(
        self, world: "ExogenousWorld", event_type: str, event_index: int,
    ) -> None:
        self._world = world
        self._event_type = event_type
        self._event_index = event_index
        self._draw_index = 0

    def random(self) -> float:
        value = self._world.uniform(
            self._event_type, self._event_index,
            draw_index=self._draw_index,
        )
        self._draw_index += 1
        return value


@dataclass(frozen=True)
class ExogenousWorld:
    """One reusable future realization shared across sibling root actions.

    Draws are addressed by semantic event coordinates instead of consuming one
    mutable RNG. Different action paths can therefore skip or reorder event
    types without shifting the chance values used by their siblings.
    """

    base_seed: int
    root_id: str
    sample_index: int
    future_stream_id: str | None

    def __post_init__(self) -> None:
        if not self.root_id:
            raise ValueError("root_id must be non-empty")
        if self.sample_index < 0:
            raise ValueError("sample_index must be non-negative")

    @property
    def world_id(self) -> str:
        return "world-" + _stable_digest("exogenous-world-v1", self.identity).hex()[:24]

    @property
    def identity(self) -> dict[str, Any]:
        return {
            "contract_version": 1,
            "base_seed": int(self.base_seed),
            "root_id": self.root_id,
            "sample_index": int(self.sample_index),
            "future_stream_id": self.future_stream_id,
            "event_addressing": "event_type+event_index+draw_index",
        }

    def uniform(
        self, event_type: str, event_index: int, *, draw_index: int = 0,
    ) -> float:
        if not event_type:
            raise ValueError("event_type must be non-empty")
        if event_index < 0 or draw_index < 0:
            raise ValueError("event and draw indices must be non-negative")
        digest = _stable_digest("exogenous-event-v1", {
            "world": self.identity,
            "event_type": event_type,
            "event_index": int(event_index),
            "draw_index": int(draw_index),
        })
        # The midpoint mapping avoids returning exactly 0 or 1 while retaining
        # 64 deterministic random bits.
        integer = int.from_bytes(digest[:8], "big")
        return (integer + 0.5) / float(1 << 64)

    def event_rng(self, event_type: str, event_index: int) -> _EventRandom:
        return _EventRandom(self, event_type, event_index)
