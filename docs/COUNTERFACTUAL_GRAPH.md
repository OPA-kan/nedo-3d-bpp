# 3–5手 counterfactual graph 契約

## 目的

一手の候補安全性だけでなく、配置後にどの残余状態へ分岐し、その後の
`placed / volume / CoG / stability / priority / soft` がどう変化するかを教師データにする。
最初から価値関数やTransformerを決めず、まず同じ親状態から生じる3〜5手の分岐と
物理結果を再現可能なDAGとして保存する。

## 保存単位

1 graphは1つのroot snapshotを持つ。

- node: 観測されたsettle後状態。`depth`, board fingerprint, visible pool,
  future-stream offset, 累積結果、終了理由を持つ。
- edge: 実行したcommand action。candidate ID、即時物理結果、policy選択有無と順位を持つ。
- 同じdepthで同じboard fingerprintへ到達した枝は同じnodeへ合流できる。したがって
  treeではなくDAGである。
- edgeは必ずdepthを1だけ進める。horizonは3〜5に限定する。

IDは内容から決定的に生成する。複数runのUUIDや列挙順には依存させない。

## 公平な未来の契約

兄弟枝は同じfuture item streamと同じ計算budgetを使う。各graphは
`future_stream_id`、commit、config、policy、branch factor、node/edge上限を保存する。
raw candidate数が異なっても、枝ごとの探索量を壁時計ではなく固定attempt数で揃える。

## 状態復元

既存の`step-NNN-state.json`は監査用であり、独立checkpointではない。
PyBulletの`saveState/restoreState`だけでは`ItemStreamManager`、containerの
`packed_items`、step metricsを復元できないため、multi-step siblingへそのまま使わない。

物理executorは各枝について次を行う。

1. 新しい`GroundHandlingEnv`を同じconfig/seed/item orderで作る。
2. episode先頭からrootまでのcompetition-equivalent action prefixを再生する。
3. rootのpool、packed itemの位置・quaternion、container状態をfingerprintで照合する。
4. その枝のaction列を実行し、各settle後nodeを記録する。
5. siblingは必ず別envから開始する。前の枝のPython状態を継承しない。

root一致に失敗した枝はラベルを作らず、`reconstruction_mismatch`としてdatasetを
非成功にする。空データや途中graphも学習成功扱いにしない。

## ラベル

各edgeは最低限、次を分離して保存する。

- command: item/pool/container/orientation/`p_cmd`
- physical: included, transport-valid, placed-safe, settle angle, `d_xy`, `d_z`
- immediate objective: placed delta, volume delta, CoG proxy, surface/stability proxy,
  priority delta, soft-item delta
- selection provenance: policy-selected, item内順位, item間順位, sampler/portfolio

nodeにはそれらの累積値とterminal reasonを保存する。公式に存在しないproxyを公式scoreと
呼ばない。

## 段階的実装

1. `scripts/counterfactual_graph.py`でschema、決定的ID、DAG合流、budgetを固定する。
2. 通常runにaction prefixとroot fingerprintを保存する（agentのrankingは変更しない）。
3. 独立env prefix replayを3つ以上のmid/late rootで検証する。
4. branch factor 2〜3、horizon 3から物理graphを生成し、計算量を見て最大5へ拡張する。
5. raw graphはartifact、compact manifest/集計/evidenceだけgitへ残す。

最終holdoutは開かず、development/validation scenarioで先に再現性と識別力を確認する。

## 初版の分岐アルゴリズム

`scripts/build_counterfactual_graph.py`はbreadth-firstにDAGを展開する。

1. nodeのaction pathを、毎回新しいenvでepisode先頭から再生する。
2. board fingerprintがnodeと一致しなければ即時停止する。
3. deadlineを使わず、可視itemごとに同じ固定attempt budgetで
   `PlacementCore.top_candidates`を走査器として使う。settled優先を保ったまま
   荷物ごとの最良候補を残し、異なる荷物から上位B件を得る。同一荷物の近接pose
   だけで幅を消費せず、置きやすい先頭itemが全budgetを消費することも防ぐ。settledを
   先に並べるが、幅が余れば別荷物のreleaseで補う。releaseの危険性は事前に
   消さず、物理edgeの失敗ラベルとして残す。
4. 各候補をさらに別の新しいenvで再構築してから1回だけ実行する。
5. settle後のfingerprintをchild node、commandと物理結果をedgeとして記録する。
6. 同じdepth・同じfingerprintは合流し、終了枝は展開しない。

初版はlive selectionを変えるアルゴリズムではなく、将来価値を学習・比較するための
offline graph生成アルゴリズムである。候補生成は現行Ranker順だが、計算量と再現性を
固定するためwall-clock deadlineは使わない。

例（新形式snapshotが必要）:

```powershell
python3 scripts/build_counterfactual_graph.py `
  --snapshot reports/replay-dataset/<run>/step-009-state.json `
  --config simulator/configs/sample_config.json --case 000 `
  --split development --horizon 3 --branch-factor 2 `
  --attempt-budget 256 --output reports/raw/graph-b000-step9.json
```

branch factor 2・horizon 3でも最大14 edge、horizon 5では最大62 edgeになる。
各edgeがrootからの物理再生を伴うため、まずH3でroot一致率と実時間を測ってからH5へ
広げる。

## H3 condition-matrix gate

`.github/workflows/counterfactual-graph-scale.yml` runs eight bounded H3/B2
conditions spanning one/two containers, shelf presence, preloading, dedicated
containers, pool widths 10/20/40 and multiple stream lengths. Aggregation
refuses a partial matrix. `scripts/summarize_counterfactual_graph_signal.py`
then compares every sibling's descendant-leaf ranges while keeping placed,
fill, CoG, surface variation, priority and soft-item outcomes separate.

A lower-score branch having a better reachable leaf is only an existence claim
inside the bounded graph. It is not a probability, competition-score total or
learned value. Exact immediate-score ties are counted without an arbitrary
near-tie threshold. The committed audit is
`reports/counterfactual-graph-scale/signal.md`; its training-readiness verdict
remains negative until a larger replicated H3 set demonstrates held-out
separation. H5 is gated on that evidence.

## Pairwise teacher export

`scripts/build_counterfactual_teacher_pairs.py` converts audited sibling
subtrees into one label per outcome axis. It never combines placed, fill, CoG,
surface, priority or soft labels into a weighted target. The discovery/late
split is inherited from the preregistered root-step boundary. Exact-score or
otherwise outcome-identical pairs are retained separately as controls.

The export is now a complete pairwise model input. Each informative row joins
permutation-ready container, settled-item and visible-pool sets from the
source node with both candidate actions. Settled poses are container-local;
the action keeps the official command frame. Step index and future/outcome
labels are excluded. `model_training_ready=true` means only that this structural
contract and both preregistered splits are present; it does not claim adequate
sample size or official-score validity.

## First late-root baseline

`scripts/evaluate_counterfactual_teacher_baseline.py` fits feature scaling and
1-NN labels on discovery roots only, then evaluates directional labels on the
late-root split once. It reports exact per-axis counts, excludes equal labels
from directional accuracy, and compares immediate score, discovery majority,
action-only 1-NN and state+action 1-NN. The committed result is
`reports/counterfactual-teacher-baseline/summary.md`. It is a small-sample
diagnostic and must not be described as generalization or policy improvement.
The consecutive-run comparison is in
`reports/counterfactual-teacher-baseline/replication.md`: candidate-action signal
against immediate score replicated on fill and surface, while the incremental
benefit of the current source-state summary did not. Treat residual-state value
as an open modelling question, not an established result.

## Discovery-only representation gate

`scripts/evaluate_counterfactual_teacher_discovery.py` never accepts a late
file. It holds out complete physical graphs inside discovery, compares action,
global-set summary and candidate-local geometry, and rotates source states only
inside each training fold as a negative control. The fixed policy is selected
per axis before a new physical matrix: action-only ridge for fill,
candidate-local ridge for CoG and surface variation, and abstention elsewhere.
The next new late split is a one-shot confirmation, not another tuning set.

That one-shot confirmation ran as Actions 31565624982 and failed its frozen
gate: candidate-local versus action-only was CoG 3/8 versus 5/8 and surface
6/8 versus 5/8, pooled 9 versus 10. Do not tune or scale this hand-designed
local representation. The negative result does not invalidate the teacher
contract or the action-only signal.

## Jointly attainable Pareto teachers

Per-axis best leaves may come from different futures and cannot be combined as
if one trajectory attained them all. Schema v3 therefore stores each sibling
subtree's complete attainable outcome vectors, removes internally dominated
vectors, and compares the two Pareto frontiers by set coverage. The relation is
lower-dominates, higher-dominates, equivalent or incomparable; no axis weight
is introduced.

The latest matrix had 10 strict dominance and 52 incomparable informative
pairs. In four-run held-out late evaluation, strict dominance appeared only
nine times; immediate score was correct 9/9 and the geometry utility delta 6/9.
This is too sparse to justify a learned live selector. See
`reports/counterfactual-teacher-cross-run/summary.md`.

## Physical afterstate continuation teachers

Schema v4 joins each sibling edge to the physical tensor of its target node.
For every outcome axis it defines continuation value as the best reachable H3
leaf outcome minus that child state's cumulative H0 outcome. This subtraction
removes the first action's immediate contribution: the target is what remains
obtainable *from the settled afterstate*. Axes remain separate and no weighted
value scalar is introduced.

`scripts/evaluate_counterfactual_afterstate_value.py` trains on discovery roots
from four physical runs and holds out the fifth run, rotating training
afterstates as a negative control. The fresh schema-v4 matrix in Actions run
31595519595 completed all eight conditions and joined both physical child
states on 67/67 informative pairs. With continuous differences below 1e-12
treated as equal, across five runs afterstate summaries scored 15/16 on fill
continuation versus action geometry at 10/16 and a permuted maximum of 10/16.
The paired result is six wins, nine ties and one loss, with exact two-sided
p=0.125. Surface
does not transfer: afterstate scored 13/26 and was worse than immediate score
(2 wins, 13 ties, 11 losses; p=0.02246). The corpus now directly represents
state-value teachers and isolates a promising fill-only hypothesis, but
incremental value is not established at 5%. Do not build a live selector or
scale H5 from this result.

A fill-only selective policy is frozen in
`reports/counterfactual-afterstate-value/fill-policy.json`. The frozen policy
emits a fill preference only when fixed-L2 packed-only and packed+visible
models agree. Under the corrected numeric label contract, it retrospectively
scores 66/67 on discovery and 15/15 on the already-inspected late rows at 15/16
coverage.
Because the consensus was designed after examining those late errors, neither
number is confirmation evidence. Its first valid test is the complete late
split of the next physical matrix after the policy commit; it must cover at
least 75%, make zero errors, and not underperform either constituent or action
geometry on covered rows.

That confirmation completed in Actions run `31598349094`, generated from the
frozen-policy commit. All eight physical conditions and the aggregate passed.
Under the corrected numeric label contract (absolute tolerance 1e-12 for
continuous outcomes), consensus covered 4/4 directional fill rows and was
correct 4/4, versus action geometry at 2/4. The preregistered gate passed.

The unchanged policy then ran on a second independent physical matrix, Actions
`31600369286`; all eight conditions and aggregate again succeeded. It covered
3/3 directional late rows but was correct only 2/3, versus action geometry at
1/3, so the preregistered zero-error gate failed. Although the corrected pooled
counts are descriptively favorable (consensus 6/7, action 3/7), pooling cannot
erase a failed replication. The policy status is
`replication_failed_not_shadow_ready`; neither run may be used for retuning,
and H5, live shadowing, and enforcement remain closed.

The failure diagnosis uses only the original five discovery-training runs for
feature scaling and nearest-neighbor reference distances. The failed
`dual-preloaded-dedicated` row is not an unseen scenario (15 exact-axis
training rows exist), but it lies above the training leave-one-out p95 in both
fixed feature blocks: packed 6.380 versus 2.556, and packed+visible 7.986 versus
2.559. Every row in the first passing confirmation is within both p95 values.
This supports a sparse-afterstate-support hypothesis, not a retrospective pass:
abstaining on that row leaves only 2/3 coverage, below the original 75% gate.
The sealed-run-safe follow-up and stop conditions are fixed in
`reports/counterfactual-afterstate-value/next-support-experiment.json`.
The scale workflow accepts a declared `environment_seed`; it is recorded in
both the dataset manifest and each replay contract. Seed 42 remains the default
for backward compatibility, and repeating a seed is replication rather than
new trajectory support.

Four distinct-seed development matrices disproved that seed variation alone
creates independent model support. Runs `31655945368`, `31656259168`,
`31656261414`, and `31656617967` yielded 14 directional late fill rows but only
six unique exact packed/packed+visible afterstate-delta signatures; 13 rows
were in cross-run duplicate groups. The independence gate therefore fails and
these runs are not admitted to training. Future collection must vary the
model-visible trajectory through scenario/item-stream/order or policy changes,
then pass `scripts/audit_counterfactual_afterstate_collection.py` before any
refreeze or confirmation.

The next data-only intervention is preregistered before execution: use the
bundled case 001 stream, the reversed case 000 stream, and an interleaving of
both, with environment seed 42 and unchanged H3/B2 physics. The original
variant remains byte-compatible. Variant provenance is carried through config,
graph scenario axes, and teacher rows. No model evaluation is allowed unless
the collection first supplies at least 12 unique directional late signatures
at a unique fraction of at least 75%.

The stream intervention passed that admission gate. Across source-001,
reverse-000, and interleave, the graph-level recovered corpus has 28/30 unique
discovery signatures and 14/14 unique late signatures, with no cross-run
duplicate groups. Recovery admitted only graph artifacts that had already
passed strict reconstruction and validation; source-001 run `31658418482` and
interleave run `31658422923` still have failed workflow status, while
reverse-000 run `31658420380` passed completely.

Independence did not rescue the predictor. Holding out each stream variant in
full, the unchanged support-gated consensus covered 9/14 directional late
rows and was correct on 6/9. A declared audit of pooled summaries,
per-container summaries, 4x4 and 8x8 height grids, feature combinations, and
grid kNN variants found a best result of 10/14 and no zero-error
representation. Results are in `stream-variant-development.md` and
`spatial-representation-development.md`. The policy therefore remains closed.

Before changing the model or expanding to H5, the next preregistered test
rebuilds the erroneous roots at H3/B3. It asks whether B2's optimistic
continuation relation is stable when branch coverage grows. Roots, streams,
seed, axes, simulator, and strict reconstruction tolerances remain fixed; any
direction change makes branch-width label stability unresolved.

Actions run `31670257775` completed all four H3/B3 physical graphs but failed
that gate for a more fundamental reason: only one target pair was directly
comparable and retained its relation. Two B2 depth-1 parent paths and one B2
root sibling pair were absent after widening because the top-B candidate set
changed. Consequently, these B2 errors are not stable supervised examples
under a wider search. A valid next collector must force the preregistered
parent path and sibling pair, then widen only their continuation subtrees.

The forced-pair rerun `31671441984` completed 4/4 physical graphs and compared
all four intended pairs. Reverse dual-empty and interleave dual-preloaded kept
their directional relation. Source dual-empty and reverse dual-shelf changed
from `lower_afterstate_better` at B2 to `equal` at B3; neither reversed. This
proves that B2 optimistic continuation can manufacture directional training
labels from insufficient branch coverage. New state-value training data must
therefore be generated directly at H3/B3, kept separate from B2 targets, and
validated by whole-stream holdout before policy integration.

## Distributional afterstate teachers

Root reconstruction keeps item identity and visible pool exact. Repeated
source and interleave runs
(`31658418482`/`31718222625` and `31658422923`/`31718245113`) reproduced the
same prefix-specific quaternion-component deltas, 0.001409 and 0.001617. The
quaternion-component tolerance is therefore 0.002. Once those roots passed,
run `31720123521` exposed 1.310 mm of positional settle drift at a later root;
the position tolerance is therefore 2 mm. Larger deltas remain reconstruction
failures. These are measured deterministic replay allowances, not a relaxation
of physical placement validity.

Schema v5 replaces the optimistic maximum as the new experimental teacher
without deleting the schema-v4 label. Every physical continuation leaf is
retained, including duplicate outcomes and its terminal reason. A declared
search policy chooses uniformly among the searched actions at each future
node; path weights are the product of those conditional probabilities. These
weights describe the bounded search only and must not be interpreted as
calibrated arrival-stream or environment probabilities.

For each outcome axis, `distributional_continuation_labels` records the
search-policy-weighted mean, a pessimistic quantile (q25 for maximized axes and
q75 for minimized axes), and physical-failure rates for both sibling
afterstates. The comparison is lexicographic: pessimistic quantile, then lower
physical-failure rate, then mean. Axes remain separate. This removes the
single lucky-leaf target that changed under B2/B3 coverage while preserving
the existing optimistic label as a negative control.

The scale workflow now defaults to H3/B3. Export is rejected unless every
informative pair has both physical afterstate tensors and both continuation
distributions. Cross-run evaluation uses the existing whole-run holdout and
permuted-afterstate control:

The dedicated `distributional_discovery.jsonl` and
`distributional_late_holdout.jsonl` splits include directional distribution
comparisons even when the old optimistic maxima or immediate scores are tied.
The schema-v4-compatible `discovery.jsonl`, `late_holdout.jsonl`, and
`controls.jsonl` retain their previous membership.

```bash
python scripts/evaluate_counterfactual_afterstate_value.py \
  --teacher-dir <run-a>/teacher-pairs \
  --teacher-dir <run-b>/teacher-pairs \
  --label-family distributional_continuation_labels \
  --target-run-id <prospective-run-id> \
  --json-output reports/counterfactual-afterstate-value/distributional.json \
  --markdown-output reports/counterfactual-afterstate-value/distributional.md
```

Omit `--target-run-id` for leave-one-run-out evaluation of every loaded run.
For a preregistered prospective stream, supply it once so the evaluator trains
on every other loaded discovery split and computes only that unopened target
fold.

This is a dataset and learnability gate, not a live selector. Cap 10, physical
feasibility, and the final holdout remain unchanged. A model may advance only
after whole-stream held-out improvement over immediate score and action
geometry; episode-level confirmation is a later, separate gate.
