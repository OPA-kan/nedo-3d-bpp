# Exhibition 001 — シュンヒバリ (pi2-pref-w6-online) vs プリフヒバリ

Date: 2026-08-26. Preregistered in
`reports/self-play-packing/two-timescale-learning-and-diverse-actors.md`.
Match run 32913831956 (mode=exhibition — full paired report, promotion
structurally disabled, registry untouched). Same 10 frozen eval
streams, same seeds. **The two arms share identical weights**: the
clone is the generation-2 champion plus an in-match preference-head
adapter (phi starts at 0, learns only from strict-dominance A/B
terminal forks, discarded at episode end; fork budget 4/episode,
uncertainty band 0.15, lr 0.05 x 2 steps, trust radius 1.0).

## Result: the online clone beats its own frozen weights

| pairing | W-L-D-∥ | note |
|---|---|---|
| vs pi2-pref-w6 (frozen champion, same theta) | **1**-0-8-1 | gate-equivalent verdict: would have passed |
| vs pi0-search (benchmark) | 1-3-3-3 | below_benchmark, hard heads non-worse |

Aggregates are identical to the champion's (placed 112, fill proxy
99.80, priority covered 1) except the strict win: **dsm-001-173**, the
same cell that crowned プリフヒバリ in match 005.

## The mechanism did exactly what it was designed to do

14 forks were spent across the 10 episodes; 3 resolved to strict
dominance and produced updates; 11 resolved to ties/censored terminals
and correctly taught nothing. The decisive sequence:

- **dsm-173, turn 4** — the adapted model was uncertain at p=0.474
  (below threshold: on its own it would have KEPT the incumbent, and
  the frozen champion, holding the same weights, did exactly that).
  The fork physically played both branches to terminal: the alternate
  strictly dominates. The clone executed the alternate and calibrated
  the pair 0.474 → 0.797 on the spot. That fork-driven switch is the
  divergence that wins the cell.
- dpd-191, turn 0: fork → alternate dominates → switch, 0.589 → 0.819.
- dpd-191, turn 1: fork → incumbent dominates → keep, 0.637 → 0.417
  (the model wanted to switch; physics said no; it learned the no).

## Reading

- At equal weights, in-match counterfactual adaptation is worth at
  least one strict win on this eval set with zero strict losses —
  evidence the two-timescale design adds value, exactly as the
  preregistered read-out defined it.
- The value came primarily from the fork's *decision authority*
  (physics outranking an uncertain model), with calibration as the
  learning by-product; with only ~1.4 forks/episode, most in-episode
  updates arrive too late to compound. Longer-horizon value of the
  *updates themselves* is the open question for the distillation path
  (fork outcomes are ordinary preference pairs for the next
  generation's corpus).
- Status unchanged: the clone is SLA-exempt (mid-match terminal forks)
  and can never gate, veto, or hold the title. No matrix or
  hyperparameter may be tuned from this exhibition; this was the one
  preregistered look.

## Eval-set accounting note (same day)

The wave-7 title-match finalizer failed twice after its verdict
(spectator-builder import bug, fixed in-repo) and the match was
resumed once; the wave-7 challenger evaluation therefore executed
three times with identical deterministic inputs. Recorded here for
look-counting honesty; verdicts are identical across executions.
