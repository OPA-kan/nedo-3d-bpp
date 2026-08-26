"""In-memory checkpoint/restore for a live ``GroundHandlingEnv``.

``client.saveState()``/``client.restoreState(stateId=...)`` round-trip
PyBullet's own physics state, but nothing else: the environment also
carries mutable Python-side bookkeeping -- ``stream_manager`` (visible
pool, stream cursor), ``container_manager.containers`` (packed items
per container), ``step_metrics``, ``num_step``, and
``validator.last_settle_metrics`` -- none of which ``saveState``
touches (see ``docs/COUNTERFACTUAL_GRAPH.md`` section on why sibling
branches use fresh env reconstruction instead of PyBullet checkpoints
alone). This module captures and restores that combined state so a
single already-alive env can be reused across many branches instead of
each branch paying full ``reset() + replay`` from scratch.

PyBullet's ``restoreState`` (both the in-memory ``stateId`` form and the
file-based ``fileName`` form -- both were probed) rejects a restore if
the *number* of bodies in the world has changed since the snapshot was
taken (``btMultiBodyWorldImporter::convertAllObjects error: expected N
multibodies, got M``). Placing an item always creates a new PyBullet
body, so every branch this module exists to support changes the body
count. The fix is not a different PyBullet API -- it is removing
whatever bodies were created after the snapshot, by id, before calling
``restoreState``; with the count restored to what it was at capture
time, ``restoreState`` succeeds and the state id remains reusable
across any number of further branches. ``capture`` therefore records
the live body id set alongside the physics state id, and ``restore``
diffs against the current id set and ``removeBody``s anything new
before invoking PyBullet's own restore.

None of the captured objects reference the live PyBullet client
(``Item``/``Container`` only carry integer body ids, stable across
``restoreState`` within one client connection), so ordinary
``copy.deepcopy`` is safe and sufficient for the Python-side half.

This module is purely additive: it does not change ``simulator/``
(the frozen official-simulator snapshot) and does not change what any
existing caller computes -- it only gives callers a cheaper way to
reach a state they could already reach by full replay. Correctness is
enforced by ``tests/test_env_checkpoint.py``, which asserts a
checkpoint+restore branch reproduces byte-identical results to the
existing fresh-reconstruction path for the same action sequence.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any


@dataclasses.dataclass
class EnvCheckpoint:
    """One captured (PyBullet state id, Python-side snapshot) pair.

    Belongs to exactly the client/env it was captured from -- PyBullet
    state ids are not portable across separate physics connections (a
    different ``GroundHandlingEnv`` has a different ``client``).
    """

    state_id: int
    body_ids: frozenset
    stream_manager: Any
    containers: list
    num_step: int
    step_metrics: list
    last_settle_metrics: Any
    removed: bool = False


def _live_body_ids(env) -> frozenset:
    return frozenset(
        env.client.getBodyUniqueId(index)
        for index in range(env.client.getNumBodies())
    )


def capture(env) -> EnvCheckpoint:
    """Snapshot ``env``'s full state (physics + Python bookkeeping)."""
    return EnvCheckpoint(
        state_id=env.client.saveState(),
        body_ids=_live_body_ids(env),
        stream_manager=copy.deepcopy(env.stream_manager),
        containers=copy.deepcopy(env.container_manager.containers),
        num_step=env.num_step,
        step_metrics=copy.deepcopy(env.step_metrics),
        last_settle_metrics=copy.deepcopy(
            env.validator.last_settle_metrics
        ),
    )


def restore(checkpoint: EnvCheckpoint, env) -> None:
    """Reset ``env`` (same client the checkpoint was captured from) to
    exactly the state ``capture`` recorded."""
    if checkpoint.removed:
        raise ValueError("checkpoint state was already released")
    for body_id in _live_body_ids(env) - checkpoint.body_ids:
        env.client.removeBody(body_id)
    env.client.restoreState(stateId=checkpoint.state_id)
    env.stream_manager = copy.deepcopy(checkpoint.stream_manager)
    env.container_manager.containers = copy.deepcopy(checkpoint.containers)
    env.num_step = checkpoint.num_step
    env.step_metrics = copy.deepcopy(checkpoint.step_metrics)
    env.validator.last_settle_metrics = copy.deepcopy(
        checkpoint.last_settle_metrics
    )


def release(checkpoint: EnvCheckpoint, env) -> None:
    """Free the PyBullet-side state slot. Safe to call once; the
    checkpoint must not be restored afterward."""
    if checkpoint.removed:
        return
    env.client.removeState(checkpoint.state_id)
    checkpoint.removed = True
