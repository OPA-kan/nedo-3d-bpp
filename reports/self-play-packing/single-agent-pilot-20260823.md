# Phase 2 complete: the mainline is single-agent

Date: 2026-08-23 (Linux, PyBullet 3.2.7)
Contract: `single-agent-mainline-contract.md`
Data: `reports/self-play-paired-physical/single-agent-pilot-20260823/`

## Verification gates

1. **Unit tests** on the pure single-agent semantics pass (no game
   heads anywhere; component deltas censor missing metrics;
   suffix targets gated on genuine termination).
2. **Physical identity, full episodes**: on both pilot cells the
   single-agent runner reproduces the two-player rank-0 executed action
   sequence exactly, from reset to genuine termination
   (`single-empty-noshelf-original`: 10 steps,
   `dual-shelf-mixed-original`: 15 steps, both
   `no_retained_candidate`). The reference runs used a *different game
   seed* than any the single-agent runner ever sees — direct proof that
   handoff chance was pure bookkeeping and that every collected rank-0
   trajectory is reinterpretable as single-agent data.
3. **Schema v3 flows end to end** (`behavior_contract =
   single_agent_v1`): per-step union measurement produced 75
   legacy-safe and 65 coverage-safe component outcome rows plus 1135
   unsafe coverage attempts retained as negative support evidence; all
   25 visited states carry eligible suffix value targets, including
   measured terminal stability (post-shake), because both episodes
   terminated genuinely.

## What the mainline now is

```
state -> legacy top-k ∪ coverage (48 samples, volume z) ->
one bounded physical step per candidate (fresh replay) ->
JointOutcomeSample v3 (+ negatives) -> execute rank-0 legacy -> repeat
```

No players, no handoff, no zero-sum bookkeeping, no terminal prize, no
scalar objective. ExogenousWorld remains as the address of the unseen
stream suffix and is declared `degenerate_deterministic_stream` in dev
configs.

## Cost

~51 fresh preview replays per step (3 legacy + 48 coverage);
full episodes ran in a few minutes per cell. The coverage safe rate
(65/1200 = 5.4%) matches the Phase 1B manifold measurement.

## Phase status and next

Phases 1A, 1B, 2 are closed. Next per the frozen roadmap:
**Phase 3 — learned proposal beta on the union support.** Its training
data is exactly what this runner now emits per episode: positive rows
(safe placements with provenance and component outcomes) and negative
rows (physically rejected coverage actions), all off-policy-declared.
Scale-up of collection and the beta contract are the next two slices.
