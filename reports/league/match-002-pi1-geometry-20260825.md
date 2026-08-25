# League match 002: the first distilled challengers fail the gate

Date: 2026-08-25. Champion: **pi0-search** (generation 1). Two
learned-arm challenges ran the frozen 10-episode eval set end to end —
the first executions of a neural policy through the league. Neither
promoted; the registry stays at generation 1. Both are honest FAILs of
the breakthrough gate, recorded with their teachers and run ids.

Both challengers are allocator ensembles (3 members, geometry-only
candidate tokens, no H1 outcome inputs, no value function) executing
pure argmax over physically safe candidates — no terminal rollouts at
decision time, so wall-clock per decision is trivially inside the 10 s
SLA (whole 10-episode matrix: ~2.5 min).

## pi1-geometry-w3 (smoke arm, 36-cell teacher, run 32825836044)

vs champion pi0-search: **1 win – 2 losses** – 2 equal – 5
incomparable → gate failed (wins must exceed losses). Aggregate:
placed 112 vs 110 (+2), violations 1 vs 3 (−2), fill 98.08 vs 98.74
(−0.67). Win at dual-shelf-mixed-181; losses at dual-shelf-mixed-167
and -173 (the champion's fill gains).

vs anchor pi0-legacy: **1 win – 0 losses – 7 equal – 2 incomparable**
— the 36-cell network already weakly dominates the original hand-coded
production policy on this set, with no search at decision time.

## pi1-geometry-g0 (100-cell teacher, corrected run 32826951027, match run 32841336693)

Teacher quality was the best yet measured (group-OOF over 926 roots /
100 cells / 96 interventions: top-1 selected-action agreement 0.894,
intervention alternative-top-1 recall 0.792).

vs champion pi0-search: **0 wins – 2 losses** – 3 equal – 5
incomparable → gate failed. Aggregate: placed 111 vs 110 (+1),
violations 2 vs 3 (−1), fill 96.85 vs 98.74 (−1.89). Same two losing
cells (dual-shelf-mixed-167, -173); the w3 win at dsm-181 regressed to
equal.

vs anchor pi0-legacy: 0 – 0 – 8 equal – 2 incomparable: g0 collapsed
toward reproducing rank-0 almost everywhere.

League collapse checks passed for both (anchor: no collapse); no
promotion, registry untouched — the instrument behaved exactly per
contract on its first neural challengers.

## Reading, stated carefully

1. **The loop is mechanically closed.** Teacher factory → distillation
   → frozen model artifact → league challenge now runs end to end with
   no manual steps, and the gate correctly refuses a policy that does
   not yet beat the champion.
2. **More data made the policy more conservative, not stronger.**
   ~90 % of teacher selections are the incumbent action; scaling the
   corpus 36→100 cells raised OOF agreement but pushed executed
   behavior toward pure rank-0 (w3: 1 win + 1 win vs legacy; g0: all
   equal vs legacy). Argmax execution converts "agree with the search
   90 % of the time" into "almost never deviate" — the interventions
   that cash out (fill gains on dual-shelf-mixed) are exactly the rare
   moves lost.
3. Both challengers place more items with fewer violations than the
   champion in aggregate but lose on fill where the champion's
   terminal search wins its episodes — the fill trade-off is the
   distillation target that matters next.

## Preregistered next steps (in order)

- Rebalance the distillation loss toward intervention roots (weight or
  oversample the 96 intervention rows) so the argmax stops collapsing
  to the incumbent; gate again through this same league.
- If reweighting is insufficient: execute with an explicit
  deviation-margin rule (switch only when the ensemble's preference
  over the incumbent exceeds a calibrated threshold) — tuned on
  training cells only, never on the eval set.
- Next teacher wave should oversample the dual-shelf-mixed family at
  states where π_1's argmax disagrees with the executed search choice
  (the loop's selective-fork criterion, now measurable from these
  manifests).
