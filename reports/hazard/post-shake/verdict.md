# Post-shake instrument: fidelity gate adjudication

Protocol: `reports/hazard/post-shake-instrument-protocol.md` (frozen
before any result was opened). Instrument:
`scripts/measure_post_shake.py`. Raw joined table:
`reports/hazard/post-shake/fidelity.md` / `fidelity.json`.

## Validation data

63 recorded episodes -- the full attribute-filter wave (workflow
`physics-probe-fidelity.yml`, run 32019553323, head 4d757ca): 7
development configs x arms {base, quiet_guard, guard_attr} x 3
replicates. This satisfies the protocol's ">= 40 recorded episodes
spanning base and quiet_guard arms" (21 + 21, plus 21 guard_attr
episodes that add power to the per-episode gates). Every episode's
`evaluation_results.json` carries the bundled evaluator's own
end-of-run `shake_response`; the recorded quiet_guard-over-base peak-KE
excess computed from these rows is +23.9%, matching the +24% the
protocol names, which confirms the join hit the intended wave.

## Gate results (preregistered thresholds, no constant tuned)

| gate | threshold | measured | result |
|---|---|---|---|
| Spearman cloned vs recorded shake_max_shift | >= 0.8 | 0.256 | **fail** |
| Spearman cloned vs recorded shake_items_shifted | >= 0.8 | 0.820 | pass |
| shake_items_toppled within +-1 | >= 80% of episodes | 50/63 = 79.4% | **fail** |
| quiet_guard peak-KE excess sign | matches recorded (+) | cloned -32.6% | **fail** |

## Verdict: FAIL -- the instrument is not trusted

Per the protocol's fail branch: the gap between the rebuilt world and
the bundled shake is itself the finding, recorded here; official
submissions remain the only reliable soft readout, the instrument does
NOT become a wave-adjudication column, and rung 3's label generator
does not exist yet.

## The finding: where the gap lives

The reconstruction is the failure, not the shake clone. The only pose
record an episode leaves is each item's settled pose AT ITS OWN
PLACEMENT STEP (`step_metrics[i].settle_final_position/quaternion`);
nothing re-records an item after later placements -- including the
300-step settle of a terminal UNSAFE attempt -- disturb it. Evidence,
all in `fidelity.json`:

1. Reconstruction drift is large and one-sided. Rebuilding from the
   recorded poses and re-settling moves at least one item > 0.3 m in
   31/63 episodes (median max drift 0.256 m, worst 1.97 m). Where
   drift is large, the recorded live world held precarious structures
   that the rebuild collapses BEFORE the shake, so the clone
   systematically under-reads the recorded response: every off-by->1
   topple row but one has recorded > cloned (e.g. b001-k20-base-r1:
   recorded 4 topples, 1.38 m max shift, peak KE 185 against cloned 0,
   0.10 m, 9.1).
2. The failure does not vanish on the clean half. Restricting to the
   32 episodes with drift <= 0.3 m (non-binding diagnostic in
   fidelity.md) still gives Spearman(max_shift) 0.04 and toppled match
   78.1%: max_shift is dominated by single-item tails that the exact
   end-state, not the per-step record, determines.
3. What DOES survive reconstruction is the bulk count: items_shifted
   correlates at 0.82-0.89 in every stratum. The instrument can rank
   arms by how many items a shake moves, but not by how far the worst
   item goes, how many topple, or how much kinetic energy the shake
   releases -- and peak KE was the one axis the audit
   (`soft-axis-is-the-single-blind-instrument`) flagged as the early
   warning. The cloned sign for the guard contrast is negative
   (-32.6% vs recorded +23.9%) precisely because the guard's
   longer-lived, fuller, more precarious final boards are what the
   per-step pose record cannot reproduce.

A subtlety recorded for honesty: with the plain single 480-step
re-settle the direction check nominally matched (+206%), but only
through one episode whose rebuilt world was still moving at shake
start (cloned KE 994 vs recorded 13 -- rebuild motion, not shake
response). Requiring the builder's own 1 mm/s quiescence criterion
before shaking (bounded at 5 rounds; 49/63 episodes still never fully
quiesce, soft-contact micro-jitter keeps summed velocities above the
threshold) removes that artifact and the sign flips negative. Neither
variant passes the gate; the quiescent one is reported because a shake
launched over rebuild motion measures the rebuild.

## What would close the gap

The blocker is data, not physics: the harness records no end-of-episode
per-item poses. A future wave that captures the final settled pose of
EVERY packed item (one extra snapshot at evaluate() time, in the
simulator's own settled_snapshot format -- an official-side change this
task is not allowed to make) would let the same instrument rebuild the
exact pre-shake world; the shake procedure itself is the official code
by import and cannot drift. Until then, post-shake soft/priority
coverage stays unmeasurable locally and the official submission remains
the only soft readout.

## Reproduction

```
# configs (deterministic from the committed sample_config):
python scripts/build_task_b_config.py --source-case 000 --task-id b000-k15 --look-ahead 15 --policy-timeout 8 --output <cfg>/b000-k15.json
# ... (b000-k20/k40, b001-k20/k30 from 001, c000-k1 from 000, c001-k1 from 001)

# episodes: run-32019553323 artifacts probe-fidelity-<case>-<arm>-r<n>,
# each containing runs/<label>/evaluation_results.json

/root/venv312/bin/python scripts/measure_post_shake.py \
  --runs '<episodes>/*/runs/*' --configs '<cfg>/*.json' --validate \
  --output-json reports/hazard/post-shake/fidelity.json \
  --output-md reports/hazard/post-shake/fidelity.md
```
