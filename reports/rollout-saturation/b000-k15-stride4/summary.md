# b000-k15 first-divergence re-run at stride 4

Local Linux, PyBullet 3.2.7, 3 repeats per arm, one configuration
(`b000-k15`, source case 000, look-ahead 15, policy timeout 8 s).

| arm | placed (per repeat) | mean placed | mean fill | vs base |
| --- | --- | ---: | ---: | ---: |
| `base` | 17, 17, 17 | 17.0 | 23.119 | +0.0 placed / +0.0 fill |
| `rollout_enforce` | 11, 11, 11 | 11.0 | 13.228 | -6.0 placed / -9.891 fill |
| `rollout_enforce_stride4` | 20, 20, 21 | 20.333 | 26.018 | +3.333 placed / +2.899 fill |

## Per-arm decision trace

| arm | first enforced step | enforced steps | non-degenerate | step >= 10 non-degenerate | mean ms | max ms | final action source |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| `base` | - | - | - | - | - | - | `placement_core` |
| `rollout_enforce` | 3 | 3 | 7/12 | 0/2 | 77.1 | 184.7 | `placement_core` |
| `rollout_enforce_stride4` | 3 | 3, 5, 8, 13 | 14/20 | 5/10 | 176.0 | 278.8 | `unsafe_protocol_fallback` |

Repeat 1 shown; repeats 2 and 3 agree on every trace field, and on placed
except `rollout_enforce_stride4` repeat 3 (21 rather than 20).

## Reading

- `base` and `rollout_enforce` are bit-identical across all three repeats.
  `rollout_enforce` reproduces the reported -6.000 exactly.
- **Both enforce arms take the same first divergence** (step 3, item 12 ->
  item 3). The stride did not avoid a bad first action.
- The difference is everything after it. At stride 1 the rollout goes blind
  (`step >= 10` non-degeneracy 0/2) and enforces once in the whole episode;
  at stride 4 it keeps discriminating (5/10) and enforces at steps 5, 8 and
  13 as well. Those three later enforcements are the +9.333.
- `rollout_enforce_stride4` ends on `unsafe_protocol_fallback`, which is why
  its `is_valid` is false. That is the known fixed-coordinate fallback
  defect (`transport-deaths-are-fallback-poison`), reached after surviving
  nine more steps - a different termination channel from the settle topple
  that ends the other two arms, not a worse one.
- Cost rises from 77.1/184.7 to 176.0/278.8 ms per decision (mean/max). The
  enforce ablation's live shadow measured 111.1 mean and 617.6 max, so the
  maximum here is *below* what was already tolerated.

## Scope

One configuration, three repeats, local machine. This establishes what the
b000-k15 loss was, not that enforce should ship. Adoption needs the full
eight-configuration repeated ablation plus the
`reports/benchmarks/baseline.json` regression guard.
`VISIBLE_POOL_ROLLOUT_MODE` remains `off`.
