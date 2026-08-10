# Task Creation: residual-state diversity dataset

## Goal

現行方策が訪れる似た積付状態だけで学習器を訓練する循環を切り、合法候補から
幾何・支持・属性上異なる残余状態を物理的に生成する。Transformer採否より先に、
残余状態から将来のplaced/fillを学べるデータ分布が存在するかを検証する。

## Context inspected

- `scripts/build_replay_dataset.py`: 同一snapshot候補の層化抽出とH0物理replay
- `scripts/measure_anchor_recall.py`: 観測・物理snapshotと候補母集団
- `docs/REPLAY_DATASET.md`: sampling/join/物理ラベル契約
- `docs/MULTI_AXIS_SELECTOR.md`: 一手静的Paretoが軌道価値にならない実測
- `HANDOFF.md`: live方策、否定済み価値proxy、公式評価上の制約

## Requirements inventory

### Critical requirements

- live policyと最終holdoutを変更しないoffline専用経路にする。
- population inference用の確率抽出とstate coverage用抽出を混同しない。
- 選択候補を常に含め、同一候補を重複replayしない。
- 物理candidate replayは公式validator順序とstate isolationを維持する。
- 残余記述子を価値と呼ばず、coverage用途だけに限定する。
- H3ラベルはPython側状態まで独立復元できるまで生成しない。

### Non-functional requirements

- Python 3.12/Linux CIを正式環境とする。
- 抽出は固定budgetで決定的、manifestからcommit/config/modeを再現可能にする。
- `agent/agent.py` と `simulator/agent.py` はこのdataset-only sliceでは変更しない。
- raw物理データはartifact、compact coverage結果はgitへ残す。

### Good-to-haves

- symmetry-aware deduplication。
- 合成container/item stream生成。
- GBDT/Deep Sets/Transformer共通schema。

### Stack and architecture context

- Python、NumPy、PyBullet、公式`GroundHandlingEnv`。
- 候補生成は現行`PlacementCore`、抽出とラベル付与はscripts層が所有する。
- 推論時は既存generatorを維持し、将来の学習器はretained portfolioだけを読む。

### Unknowns and assumptions

- Unknown: 残余proxy距離が物理settle後の状態coverageも増やすか。
- Unknown: H3 continuationのprefix再生がsnapshot tolerance内で決定的か。
- Assumption: 同一親状態内では候補占有領域とpredicted-contact特徴が、分岐候補を
  選ぶ一次proxyとして十分である。価値予測力は仮定しない。

## Iteration layering

### Iteration 1: deterministic H0 diversity sampling

- Outcome: 既存候補母集団から異なるafterstate proxyをmaximin抽出し、H0物理
  ラベルとcoverage telemetryを保存する。
- Deferred: multi-step continuation、学習、live ranking。

### Iteration 2: independently replayable branches

- Outcome: prefix action列を独立envへ再生し、親snapshot一致を検証後に候補分岐を
  commitできる。
- Deferred: 大規模scenario生成。

### Iteration 3: H3 labels and learnability audit

- Outcome: additional placed/volume、failure、attribute/stabilityをH0/H3で保存し、
  lookup/GBDT/Deep Setsをscenario holdoutで比較する。
- Deferred: Transformerとlive enforce。

## Vertical slices

1. Residual-proxy maximin sampler
   - Value: score近傍ではない候補を同じ物理replay予算へ入れられる。
   - Acceptance: deterministic、forced inclusion、null probability contract、既定mode不変。
   - Verification: `tests.test_build_replay_dataset`。

2. Coverage telemetry and pilot comparison
   - Value: randomより実際にcoverageが増えたかを数値で棄却できる。
   - Acceptance: 同一母集団・同一sample数で最近傍距離と空間セル数を比較可能。
   - Verification: Linuxの同一snapshot paired run。

3. Prefix trace and branch-state identity
   - Value: H3ラベルを別状態の比較にしない。
   - Acceptance: action prefix再生後のpool、packed items、pose/quaternionがtolerance内一致。
   - Verification: 3つ以上のmid/late snapshotでintegration test。

4. H3 continuation labels
   - Value: 一手安全性と将来placed/fillを分離する。
   - Acceptance: 同じfuture stream/budgetでbaseline/proposedを対にし、失敗を空データ扱いしない。
   - Verification: branch pair manifestと物理ラベル監査。

5. Learnability audit
   - Value: Transformerを作る前に残余状態の予測余地を判定する。
   - Acceptance: scenario単位split、template lookup/GBDT/Deep Sets、oracle regret、
     pattern内分散を報告する。
   - Verification: holdout指標とdata leakage監査。

6. Model shadow and constrained selector
   - Value: 学習価値をplaced/stability制約下でlive候補選択へ接続する。
   - Acceptance: OFF hash一致、shadow無干渉、full-vector guard、既定OFF。
   - Verification: 7-case Linux物理比較後にchange review。

## Risks and dependencies

- proxy diversityがactual settled diversityへ移らない場合は署名を物理afterstate由来へ変更する。
- branch env再構築が非決定的ならH3は停止し、同一processでPython状態を明示保存する。
- 現行2配布ケースだけでは公式汎化を示せない。モデル段階前に合成scenarioが必要。
- coverage改善をscore改善と解釈しない。Iteration 1の成功はデータ分布の拡張だけ。

## Handoff

Next module: `implementation`。Iteration 1を既存replay datasetの別sampling modeとして
実装し、live agentを変更せずにnegative controlを作れるため。
