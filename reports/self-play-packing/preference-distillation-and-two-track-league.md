# Design record: incumbent-preference distillation and the two-track league

Date: 2026-08-25 (design review, third round — after league match 002).
Direction set by the project owner; this file freezes the decisions.

## Why behavior cloning lost

Match 002 measured it: the current policy is already right ~90 % of
the time, so `s -> teacher's action` cross-entropy rewards reproducing
the incumbent and starves the rare deviations that carry all the
value. Scaling data 36→100 cells made this *worse* (g0 collapsed to
rank-0). The thing to learn is not "what did the teacher pick" but
**"is this alternate really better than the incumbent?"**

## The preference objective

For each root with a genuine incumbent terminal: for every alternate
A_j with a genuine terminal, the label is

    beats_incumbent(A_j) = dominates(terminal(A_j), terminal(A_0))

under the SAME 5-head dominance rule the search executes with
(`DOMINANCE_HEADS` in `run_vector_mcts.py`) — dominance-derived,
never a synthesized scalar. Ties/trade-offs are label 0 ("not clearly
better"); censored terminals are masked. Wave-4 corpus: 1803 pairs,
129 positive (7.2 %).

The model is the existing candidate-set scorer; training applies a
pairwise logistic loss on score deltas against the incumbent, so

    P(A_j beats A_0 | s) = sigmoid(score_j - score_0)

is antisymmetric by construction and the incumbent's own probability
is exactly 0.5. Execution: keep the incumbent unless some alternate's
probability clears the switch threshold (default 0.5; calibrate only
on training cells). No scalar Q object is ever materialized.

## The two-track league

The old structure made `pi0 + terminal search` the champion, so a
distilled SLA-compliant network had to beat the SLA-noncompliant
oracle-ish arm just to record a generation. That conflates two
different bars. New structure (registry restructured in place):

- **Production champion line**: `pi0-legacy -> pi1 -> pi2 -> ...` —
  the main gate and promotions live here; every member is a policy we
  could actually ship.
- **Teacher benchmark**: `pi0-search` (and future search-augmented
  arms) hold role `benchmark`: never gate, never veto, but every match
  reports the challenger's standing against them.

Distinguishable outcomes per match:

| result | meaning |
|---|---|
| challenger > production champion | generation succeeded (promote) |
| challenger ≈ benchmark | search compressed into the network |
| challenger > benchmark | major breakthrough |

Anchor/previous/milestone collapse detection is unchanged (aggregate
thresholds only). Under this structure, match 002's pi1-geometry-w3
(1-0-7-2 over pi0-legacy) would have promoted; the bar it failed was
the benchmark bar, which is now reported instead of gating.

## Spectator system (added same day)

`scripts/build_spectator_data.py` turns a match's two episode-manifest
trees + the frozen scenario geometry + the league report into one
replay JSON (side-by-side placement sequences with rotated dims,
first-divergence turn, switch confidences, auto-extracted highlights);
`reports/league/spectator/shell.html` is the broadcast UI (league top,
match center with isometric canvas replay, policy lineage tree) that
embeds it. **Spectating is read-only by contract**: league results and
replays are for watching and debugging comprehension only — training
matrices are never tuned from them, because the frozen eval set would
leak through the human. Research decisions come from training-side
diagnostics alone.
