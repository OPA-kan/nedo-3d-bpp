# Ranker first-divergence report

`scripts/analyze_ranker_divergence.py` compares two saved evaluation
trajectories at their first different action.  It reconstructs the candidate
population from the pre-action snapshot and writes:

- every additive `Ranker.score` term (`12V`, `2R`, depth, x, z-mass, route);
- release-only `P_rot`, `P_slide`, `Q_old`, and the configured live score;
- old-score and live-score candidate, item, and within-item ranks;
- margins from both selected candidates;
- left/right search membership and `new_search_only`;
- a next-state static candidate-survival proxy.

The report is useful for both policy and cache comparisons.  A policy change
normally appears as rank movement among candidates reached by both searches.
A cache/search change normally appears as different search membership.  Do
not infer the second from a stratified replay sample alone: candidates absent
from a sample are recorded as unknown, not as absent from the search.

`within_item_rank` orders placements of the same item.  `item_rank` orders
items by each item's best candidate score.  `across_candidate_rank` orders the
entire candidate population.  Each is emitted for both `Q_old` and the live
risk-adjusted score.

## Example

```bash
python3 scripts/analyze_ranker_divergence.py \
  --left-evaluation reports/risk-ablation/runs/b000-k20-base-r0/evaluation_results.json \
  --right-evaluation reports/risk-ablation/runs/b000-k20-base-r7/evaluation_results.json \
  --case b000-k20 \
  --snapshot reports/replay-dataset/<dataset>/step-009-state.json \
  --left-search-jsonl reports/replay-dataset/<dataset>/step-009-candidates.jsonl \
  --collect-current-search-seconds 6.5 \
  --next-count selected \
  --output-dir reports/ranker-divergence/b000-k20-step009
```

Omitting `--candidate-jsonl` invokes the unlimited settled/release oracle and
therefore produces the full policy-item candidate population.  Supplying a
candidate JSONL is faster, but its rank and membership conclusions apply only
to those rows.

Use `--left-search-complete` or `--right-search-complete` only when the JSONL
is a complete reached-candidate audit and absence from it proves that the
candidate was not reached.  A stratified replay dataset is not complete.

## Output and limits

- `report.md` is a bounded frontier view with a selected-candidate summary.
- `candidates.csv` and `report.json` contain every reconstructed candidate.
- `new_search_only` is three-valued: true, false, or null when evidence is
  incomplete.
- `next_valid_candidate_count` is not the official simulator's next-step
  candidate count.  It applies the same virtual packed-AABB update used by
  lookahead and revalidates the already-enumerated universe.  It neither
  generates new anchors nor runs PyBullet settle.  Treat it as a residual
  feasibility proxy, not as a physical counterfactual.
- `--collect-current-search-seconds` is a fresh timed rerun.  It does not
  reconstruct the exact historical deadline scheduling unless that run's
  complete candidate audit was saved.
