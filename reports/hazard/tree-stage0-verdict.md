# Tree search stage 0 (shadow wave): PASS

Run 31991177016, 42/42 episodes. Gates per
visible-tree-search-protocol.md:

- Mechanism alive: would_change on 96/404 steps (23.8%; bar 5%).
- Budget: shadow 0.33 s/step mean, 0.43 max vs base 0.32/0.48 —
  indistinguishable, inside the shipped budget (118 deadline-clamped
  search slices did their job).
- Negative control: the two deterministic configs are exactly
  identical across all episodes (b001-k30 17x6, c001-k1 21x6);
  every other config's shadow mean sits within its baseline floor
  except b000-k20 (+2.0 vs floor 1.97), where the gap is a base-side
  low outlier (12 placed) and in the direction log-only compute
  cannot cause. Read as noise; the enforce wave's tree_null arm
  re-measures this control with power.

Stage 1 (enforce A/B: base / tree_null / tree_search) is licensed.
