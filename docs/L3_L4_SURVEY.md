# L3(配分)/ L4(順序)現状調査と変更候補

Date: 2026-08-03. Branch `claude/l3-l4-allocation-ordering`。
層の定義: L0 計器 / L1 候補生成 / L2 選択 / L3 配分(どのコンテナへ) /
L4 順序(どの荷物・姿勢・種別から試すか)。本書は L3/L4 の現状機構と、
測定可能な変更候補の在庫である。設計変更はここからの事前登録 ablation でのみ行う。

## L3 配分 — 現状

**結論: 配分は「層」として存在しない。探索順序の副作用である。**

| 機構 | 場所 | 内容 |
|---|---|---|
| 資格フィルタ | `eligible_container_indices` (agent.py:3664) | priority 荷物 → priority コンテナ群(無ければ全て)。それ以外は全コンテナ資格あり |
| 訪問順 | `prioritized_search_units` (:3901) | 資格コンテナを `estimated_remaining_container_volume` 降順(同率は index 昇順)で訪問 |
| 残容量推定 | `estimated_remaining_container_volume` (:3859) | 有効容積 − Σ packed 体積。**幾何を見ない**(断片化・到達可能性を区別しない) |
| 確定 | `PlacementCore.choose` | 最初に安全 pose が見つかったコンテナに置かれる。コンテナ間の比較・将来配分の概念は無い |
| 毒経路 | `policy` fallback (:7283) | 資格リストの先頭コンテナを機械的に選ぶ |

### L3 変更候補

- **L3-1: 残容量推定の幾何化。** 体積差引きを、release-drop heightmap(L0 で実装済みの
  `_heightmap`/`_drop_height`、`measure_dead_end_branch.py`)由来の「置ける床面積・最大受け入れ高さ」
  に置換。体積は断片化を見ないため、詰まったコンテナを「まだ広い」と誤認して訪問順を歪める。
  型カタログ非依存。測定: Task B 2コンテナ構成で placed/fill、arm 1本。
- **L3-2: 配分の明示化(コンテナ間バランス)。** 現状は roomiest-first の貪欲。
  「先に片方を使い切る」vs「並行に埋める」は一度も測定されていない。
  soft/priority の将来支持面制約(HANDOFF 不変条件)とも相互作用する。
  測定: 訪問順を fill-one-first / balance に固定した2 arm。
- **L3-3: priority 資格の fallback 撤去検証。** priority コンテナが満杯のとき通常コンテナへ
  落ちる(`or indices`)。placement_score の減点(優先誤配)と placed の得の比較は未測定。
  公式配点上 placement は最悪2成分の一つ(OFFICIAL_SCORE_LOG)。

## L4 順序 — 現状

| 機構 | 場所 | 内容 |
|---|---|---|
| online 荷物順 | `online_item_order` (:3676) | (group: 通常0 < soft1 < priority2, mass 降順, volume 降順)。**priority が最後**=スタック上部に載る設計 |
| pool cap | `capped_online_items` (:3700) + `MAX_POOL_ITEMS_EVALUATED=10` + `ITEM_COVERAGE_MODE=class_aware` | 40個中10個へ絞る。class-aware 化が本リポジトリ最大の実測改善(placed 10.67→17.00) |
| 姿勢順 | `prioritized_search_units` | 接地面積の大きい orientation から |
| 種別順 | 同上 | settled → release の固定順 |
| offline 順(Task A) | `constructive_order` (:3835) | group 内を composite = 0.45·vol + 0.30·base_area + 0.25·mass − 0.05·cutout_filler で降順 |

### L4 変更候補

- **L4-1: `constructive_order` の composite 撤去(最有力・最安)。**
  係数 0.45/0.30/0.25/0.05 は ADR-001 に数値の記録が無く(実装が勝手に決めた)、
  volume 単独ソートに 3 seed 中 2 で負ける実測が既にある(並行スレッド測定)。
  AGENT_OPERATIONS §5.1 違反の最も弱い立場。候補: 辞書式 (group, −volume, −mass, index)。
  base_area と mass の相関 0.94(カタログ性質)により composite の3項は実質1軸。
  cutout_filler の連続閾値(≤0.30/≤0.44/≤10kg)はカタログ適合であり、7型が評価契約でない
  以上そのままでは根拠が無い — 撤去 arm と保持 arm を分けて測る。
  測定: Task A rollout(オフラインなので CPU 依存が小さく再現性が高い)。
- **L4-2: online 順の mass-first の検証。** (mass, volume) 降順は「重い物を下に」の物理直観だが
  事前登録測定は無い。volume-first・base-area-first との3 arm。Task B 開発スイートで。
  注意: L4-1 と違い deadline 依存なので CI guard が必要。
- **L4-3: 種別順 settled→release の反転検証。** 壁際バンド(envelope 修正で開いた領域)は
  release でしか届かない事が多い。release-first が placed に効くかは未測定。
- **L4-4: pool cap の class_aware の Task C 無関係性の明文化。** Task C は pool=1 で
  L4 online は自明(選択肢が無い)。L4 の主戦場は Task A(offline 全順序)と Task B(pool 10/40)。

## 優先順(根拠の弱い順 × 測定の安い順)

1. **L4-1** constructive composite → 辞書式。オフラインで再現性良、係数ゼロ化、既に負けている測定あり
2. **L3-1** 残容量の幾何化。L0 資産の再利用、型非依存
3. **L4-3** release-first。envelope 修正の帰結として自然な仮説
4. **L3-2 / L4-2** バランス配分・順序3 arm。CI guard 必要、後回し
5. **L3-3** priority fallback。公式 placement 成分に絡むため提出フィードバックと併読

## 既知の制約(全候補共通)

- 7型カタログは評価契約ではない(2026-08-03 確認)。型指定・カタログ閾値への依存は書かない
- 係数は §5.1: 外部由来か事前登録 ablation のみ。辞書式・順序統計を優先
- deadline 依存の層(L4 online, L3 訪問順)はローカル比較が壊れる
  (`task-b-guard-not-reproducible-off-ci`)。オフライン層(L4-1)から着手する理由でもある
- 新計器は §5.0: 検証(決定性/陰性対照/独立計器)を通すまで draft
