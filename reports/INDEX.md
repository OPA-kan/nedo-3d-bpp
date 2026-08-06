# reports/ index

**このファイルは生成物である。** 手で編集しない。
`python scripts/index_reports.py --write` で再生成する。

状態は `context/evidence.json` から導出している。台帳に active な主張が
1件でも紐付いていれば `active`、紐付く主張が全て superseded なら
`superseded`、1件も紐付かないなら `uncited`。**`uncited` は「古い」の
意味ではない** — 生出力である・台帳より前に書かれた・主張が撤回され
たまま置き換えられていない、の3つを索引は区別できないので、事実だけ
を出して理由は推定しない。

## 結論を書いたレポート

| 状態 | 最終更新 | ファイル | 根拠となっている台帳エントリ |
|---|---|---|---|
| active | 2026-08-05 | `reports/hazard/dominated-choices-retracted.md` | `the-fatal-choice-is-the-argmax`, `heightmap-drop-heights-must-not-score` |
| active | 2026-08-05 | `reports/hazard/step-confound.md` | `afterstate-features-are-a-clock-not-fullness` |
| active | 2026-08-03 | `reports/l3-l4/morning-summary.md` | `death-band-mitigated-adoption-candidate`, `death-band-shipped-on-by-default` (superseded) |
| active | 2026-08-02 | `reports/replay-analysis/board-value-f1-findings.md` | `board-value-f1-discriminates-not-predicts`, `taskc-collapse-is-non-gradual-tie-break-line-dead` (superseded) |
| active | 2026-07-31 | `reports/replay-analysis/findings-20260730.md` | `gate-high-recall-low-precision` |
| active | 2026-07-31 | `reports/replay-analysis/loss-structure.md` | `official-loss-step-in-angle` |
| active | 2026-07-31 | `reports/replay-analysis/mechanics-features.md` | `mechanics-features-dominate-static` (superseded), `mechanics-features-dominate-static-33snap` |
| active | 2026-07-31 | `reports/replay-analysis/residual-capacity-calibration.md` | `capacity-instrument-calibration` |
| active | 2026-07-31 | `reports/replay-analysis/residual-capacity-stage-a.md` | `stage-a-settled-only-negative` (superseded), `stage-a-calibrated-negative` |
| active | 2026-07-31 | `reports/replay-analysis/risk-evaluation.md` | `rotation-signal-coefficients-unfrozen`, `support06-low-risk-region`, `dxy-unresolved` (superseded), `shadow-rerank-low-live-leverage` (superseded), `shadow-rerank-low-live-leverage-33snap` |
| active | 2026-07-31 | `reports/replay-analysis/risk-rule-comparison.md` | `risk-rule-family-comparison` (superseded), `risk-rule-family-comparison-33snap` |
| active | 2026-07-31 | `reports/replay-analysis/slide-equivariant.md` | `dxy-equivariant-s0` |
| active | 2026-08-01 | `reports/replay-analysis/terminal-failures.md` | `terminal-failure-channels`, `transport-now-leading-death-channel` |
| active | 2026-08-01 | `reports/risk-ablation/summary.md` | `online-ablation-round2-positive`, `risk-freeze-mech-lambda1`, `final-holdout-passed-default-switch` |
| active | 2026-08-04 | `reports/scenario-matrix/taskb-ci-10mm-30865228317.md` | `lateral-guard-buys-settle-survival` |
| active | 2026-08-04 | `reports/scenario-matrix/taskb-ci-2mm-30865196936.md` | `lateral-guard-buys-settle-survival` |
| active | 2026-08-06 | `reports/stowage/attr-guard-verdict.md` | `attribute-guard-trades-placed-for-priority` |
| active | 2026-08-06 | `reports/stowage/support-creation-verdict.md` | `elevated-support-cannot-grow` |
| active | 2026-08-05 | `reports/stowage/support-exhaustion.md` | `support-exhaustion-is-the-terminal-state` |
| active | 2026-08-05 | `reports/stowage/zone-order-verdict.md` | `zone-loading-order-refuted` |
| active | 2026-08-01 | `reports/task-a-rollout/history/30717998654/analysis.md` | `task-a-offline-budget-starved-by-unbounded-scan`, `task-a-bounded128-adopted`, `task-a-offline-proxy-is-relative-only`, `task-a-bounded128-replicated` (superseded) |
| active | 2026-08-02 | `reports/task-c/anchor-fallback/depth-sweep.md` | `task-c-endgame-is-anchor-order-not-unit-coverage`, `task-c-interleave-rejected` |
| active | 2026-08-02 | `reports/task-c/anchor-fallback/interleave.md` | `task-c-interleave-rejected` |
| active | 2026-08-02 | `reports/task-c/anchor-fallback/summary.md` | `task-c-baseline-restated-with-load-dependent-determinism`, `anchor-fallback-first-task-c-ablation`, `task-b-guard-not-reproducible-off-ci`, `anchor-fallback-task-b-local-arm-comparison`, `task-c-after-first-pass-256` (superseded) |
| active | 2026-08-02 | `reports/task-c/baseline/summary.md` | `task-c-baseline-fallback-is-the-only-death` (superseded), `task-c-baseline-restated-with-load-dependent-determinism` |
| active | 2026-08-03 | `reports/task-c/ceiling/summary.md` | `task-c-search-ceiling-is-low-and-the-wall-is-real` (superseded), `board-receptivity-is-not-a-feasibility-predictor`, `task-c-wall-is-anchor-parameterisation-not-the-board` |
| active | 2026-08-02 | `reports/task-c/fatal-oracle/post-fallback.md` | `task-c-post-fallback-terminal-is-a-coverage-gap` (superseded), `task-c-after-first-pass-256` (superseded), `task-c-endgame-is-anchor-order-not-unit-coverage` |
| active | 2026-08-03 | `reports/task-c/true-envelope/branch-rerun.md` | `taskc-box-wall-at-step-19-was-an-artifact`, `c001-k1-true-terminal-at-step-21-certified`, `taskc-collapse-is-non-gradual-tie-break-line-dead` (superseded), `c001-k1-selection-problem-exists-features-are-blind` (superseded) |
| active | 2026-08-03 | `reports/task-c/true-envelope/summary.md` | `true-envelope-first-task-c-ablation`, `true-envelope-shipped-without-the-task-b-guard` |
| active | 2026-08-03 | `reports/task-c/wall-is-not-a-wall.md` | `task-c-wall-is-anchor-parameterisation-not-the-board`, `anchor-envelope-is-a-box-approximation` (superseded), `anchor-envelope-ignores-the-real-container-shape` (superseded), `anchor-envelope-y-bound-is-one-thickness-too-tight` |
| superseded | 2026-08-02 | `reports/task-c/anchor-fallback/after-merge.md` | `task-c-after-first-pass-256` (superseded) |
| superseded | 2026-08-02 | `reports/task-c/fatal-oracle/summary.md` | `task-c-fatal-oracle-two-classes` (superseded), `task-c-post-fallback-terminal-is-a-coverage-gap` (superseded) |
| uncited | 2026-07-28 | `reports/README.md` | — |
| uncited | 2026-08-02 | `reports/attribute-placement/summary.md` | — |
| uncited | 2026-08-02 | `reports/board-receptivity/summary.md` | — |
| uncited | 2026-08-02 | `reports/branch-labels/b000-k20/summary.md` | — |
| uncited | 2026-08-02 | `reports/branch-labels/diff-step4/summary.md` | — |
| uncited | 2026-08-02 | `reports/branch-labels/validity-b000-k20/summary.md` | — |
| uncited | 2026-07-28 | `reports/colab-migration-20260726.md` | — |
| uncited | 2026-08-01 | `reports/cross-step-incumbent/history/30706832092/summary.md` | — |
| uncited | 2026-08-01 | `reports/cross-step-incumbent/history/30707120494/summary.md` | — |
| uncited | 2026-07-28 | `reports/github-actions-30317807712.md` | — |
| uncited | 2026-08-05 | `reports/hazard/dominated-choices.md` | — |
| uncited | 2026-08-05 | `reports/hazard/regime-dependence.md` | — |
| uncited | 2026-08-04 | `reports/hazard/summary.md` | — |
| uncited | 2026-08-04 | `reports/l3-l4/two-container-smoke.md` | — |
| uncited | 2026-08-03 | `reports/latest.md` | — |
| uncited | 2026-08-01 | `reports/live-interleave/local-20260801-screening/summary.md` | — |
| uncited | 2026-07-28 | `reports/lookahead/README.md` | — |
| uncited | 2026-07-28 | `reports/lookahead/history/30322018380/summary.md` | — |
| uncited | 2026-07-28 | `reports/lookahead/history/30329819161/summary.md` | — |
| uncited | 2026-07-28 | `reports/lookahead/history/30331700531/summary.md` | — |
| uncited | 2026-07-28 | `reports/lookahead/history/30334277618/summary.md` | — |
| uncited | 2026-07-28 | `reports/lookahead/history/30337216417/summary.md` | — |
| uncited | 2026-07-28 | `reports/lookahead/history/30338524490/summary.md` | — |
| uncited | 2026-07-28 | `reports/lookahead/history/30340049061/summary.md` | — |
| uncited | 2026-07-28 | `reports/lookahead/latest-summary.md` | — |
| uncited | 2026-08-02 | `reports/replay-analysis/board-value-f1.md` | — |
| uncited | 2026-08-02 | `reports/replay-analysis/kappa-siblings-stage-b/summary.md` | — |
| uncited | 2026-07-31 | `reports/replay-analysis/latest.md` | — |
| uncited | 2026-08-02 | `reports/replay-analysis/option-damage/summary.md` | — |
| uncited | 2026-08-01 | `reports/replay-analysis/safe-capacity-stage-a/summary.md` | — |
| uncited | 2026-08-01 | `reports/rescue-scan/ci-30698074510/summary.md` | — |
| uncited | 2026-08-01 | `reports/rescue-scan/ci-30698434932/summary.md` | — |
| uncited | 2026-08-01 | `reports/rescue-scan/ci-30698558132/summary.md` | — |
| uncited | 2026-08-01 | `reports/rollout-saturation/b000-k15-divergence/report.md` | — |
| uncited | 2026-08-01 | `reports/rollout-saturation/b000-k15-stride4/summary.md` | — |
| uncited | 2026-08-01 | `reports/rollout-saturation/local-20260801/report.md` | — |
| uncited | 2026-08-05 | `reports/stowage/section-audit.md` | — |
| uncited | 2026-08-01 | `reports/task-a-rollout/history/30717533328/summary.md` | — |
| uncited | 2026-08-01 | `reports/task-a-rollout/history/30717848749/summary.md` | — |
| uncited | 2026-08-01 | `reports/task-a-rollout/history/30717998654/summary.md` | — |
| uncited | 2026-08-01 | `reports/task-a-rollout/history/30719944050/summary.md` | — |
| uncited | 2026-08-01 | `reports/task-a-rollout/history/30721071243/summary.md` | — |
| uncited | 2026-08-01 | `reports/task-a-rollout/history/30723404603/summary.md` | — |
| uncited | 2026-08-01 | `reports/task-a-rollout/history/30723789332/summary.md` | — |
| uncited | 2026-08-01 | `reports/task-a-rollout/history/30723997567/summary.md` | — |
| uncited | 2026-08-02 | `reports/task-a-rollout/history/30730465706/summary.md` | — |
| uncited | 2026-08-02 | `reports/task-a-rollout/history/30730755813/summary.md` | — |
| uncited | 2026-08-02 | `reports/task-a-rollout/history/30730942781/summary.md` | — |
| uncited | 2026-08-02 | `reports/task-a-rollout/history/30731189432/summary.md` | — |
| uncited | 2026-08-02 | `reports/task-a-rollout/history/30733207487/summary.md` | — |
| uncited | 2026-08-02 | `reports/task-a-rollout/history/30737102164/summary.md` | — |
| uncited | 2026-08-03 | `reports/task-a-rollout/history/30820870931/summary.md` | — |
| uncited | 2026-08-03 | `reports/task-a-rollout/history/30822981451/summary.md` | — |
| uncited | 2026-08-04 | `reports/task-b/history/30865228317/aggregate.md` | — |
| uncited | 2026-08-03 | `reports/task-c/tilt-margin/summary.md` | — |
| uncited | 2026-08-02 | `reports/visible-pool-rollout/b000-k20-step009-d3-a128/report.md` | — |
| uncited | 2026-08-02 | `reports/visible-pool-rollout/b000-k20-step009-d3-a256/report.md` | — |
| uncited | 2026-08-02 | `reports/visible-pool-rollout/b000-k20-step009-d3-a512/report.md` | — |
| uncited | 2026-08-02 | `reports/visible-pool-rollout/b000-k20-step009-d3-a64/report.md` | — |
| uncited | 2026-08-01 | `reports/visible-pool-rollout/history/30708670700/summary.md` | — |
| uncited | 2026-08-01 | `reports/visible-pool-rollout/history/30708961145/summary.md` | — |
| uncited | 2026-08-01 | `reports/visible-pool-rollout/history/30715760647/summary.md` | — |
| uncited | 2026-08-01 | `reports/visible-pool-rollout/history/30716230811/summary.md` | — |
| uncited | 2026-08-01 | `reports/visible-pool-rollout/history/30716558143/summary.md` | — |

## 生の計測出力（散文なし）

以下は結論ではなく入力データである。読むのは人ではなく右の解析器。

| ディレクトリ | 追跡ファイル数 | 容量 | 読む側 |
|---|---:|---:|---|
| `reports/attribute-placement/` | 12 | 3.6 MB | `scripts/fit_hazard_model.py` |
| `reports/board-receptivity/` | 108 | 102.7 MB | `scripts/fit_hazard_model.py` |
| `reports/first-pass-depth/` | 92 | 50.8 MB | `scripts/analyze_first_pass_depth.py` |
| `reports/first-pass-depth-taskA/` | 7 | 1.3 MB | `scripts/analyze_first_pass_depth.py` |
| `reports/merge-taskA/` | 7 | 1.8 MB | `scripts/fit_hazard_model.py` |
| `reports/stability-tradeoff/` | 62 | 37.0 MB | `scripts/analyze_stability_tradeoff.py` |

追跡下の `reports/` 全体: 1000 ファイル / 223.0 MB。内訳と、これが clone コストではない理由は `docs/REPO_AUDIT.md` §D。
