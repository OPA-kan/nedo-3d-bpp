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
