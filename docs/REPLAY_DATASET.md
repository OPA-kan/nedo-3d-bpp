# 層化counterfactual replayデータセット

`scripts/build_replay_dataset.py` が生成する候補単位のデータセットの仕様。

## 何のためにあるか

通常のTask B runで物理ラベルが付くのは、**rankingが実際に選択した候補だけ**である。
そこから計算した混同行列は選択に条件づけられており、gate全体の
precision / recallではない。反復回数を増やしてもこの条件づけは解消しない。

このデータセットは、同一snapshotから候補母集団を列挙し、そこを層化抽出して
**選ばれなかった候補にも物理ラベルを付ける**。目的は

\[
\Phi(s,a)\;\longmapsto\;(x^{+},\,\Delta\theta,\,d_{xy},\,d_z,\,Y)
\]

の同定であり、新しい特徴の追加ではない。

## 1行の中身

`step-<nnn>-candidates.jsonl` の1行が1候補。

| 群 | フィールド |
|---|---|
| s | `case_id`, `step`, `snapshot_path`（`step-<nnn>-state.json` を指す） |
| a | `pool_index`, `item_index`, `container_index`, `orientation`, `kind`, `center`, `size`, `action_center`, `candidate_id` |
| Φ | `phi`（`release_risk_features` の全項目）, `gate_passed`, `gate_reasons` |
| Q | `score_immediate`（`Ranker.score`）, `score_rank`, `score_population`, `preview` |
| selected | `selected`, `found_by_anytime` |
| 抽出設計 | `stratum`, `sampling` |
| ラベル | `physical` |

`physical` の内訳:

- `is_included` / `is_valid` / `is_placed_safe`: 公式validatorの3判定
- `x_plus`: settle後の `position` / `quaternion` / `aabb_dimensions`
- `delta_theta_deg`, `d_xy`, `d_z`, `d_norm`, `footprint`: 回帰ターゲット
- `Y`: 分離ラベル（`rotated_over_30`, `displaced_over_half_footprint`,
  `horizontal_displaced_over_half_footprint`, `not_placed_safe`,
  `not_valid`, `not_included`, `physically_dangerous`）

`Y` の定義は `scripts/summarize_task_b.separated_physical_labels` を
そのまま呼んでいる。ベンチマークとデータセットでラベル定義が食い違わないように、
定義は1か所にしか置かない。`physically_dangerous` は過去系列との継続性のための
旧複合指標であり、モデル化には分離ラベルを使う。

## 抽出設計

**層** は3軸の直積:

| 軸 | 値 |
|---|---|
| `kind` | `candidate`（静止候補） / `release_candidate` |
| `gate` | `pass` / `reject` / `not_applicable`（静止候補はgateを通らない） |
| `score_band` | `top1` / `top10` / `top10pct` / `tail` |

`score_band` のrankingは**kindごと**に取る。静止候補とrelease候補は同じ
`Ranker.score` で採点されるが母集団が別だからである。

**gateで層化しないと成立しない。** rankingの上位にはreject候補がほとんど
現れないので、層化しなければFP/TPのセルが推定できないまま終わる。

各層から最大 `--per-stratum` 件を非復元で一様抽出する。各行は

- `sampling.stratum_size`: 層の母集団サイズ
- `sampling.stratum_sampled`: その層から取った件数
- `sampling.inclusion_probability`: 抽出確率
- `sampling.sampling_weight`: `1 / p`（Horvitz-Thompson用）
- `sampling.forced` / `forced_reason`

を持つ。**行はそのまま母集団の比率として読めない。** 率を出すときは
必ず `sampling_weight` で再重み付けする。

policyが実際に選んだ候補は確率1で必ず含める（`forced: true`）。その層の
残り枠はforced分を差し引いてから抽出するので、設計は不等確率抽出のまま
保たれ、上位への偏った上乗せにはならない。

## ラベルの契約

replayは `GroundHandlingEnv.step` と**同じ順序**で公式validatorを呼ぶ。

1. `check_inclusion`
2. `check_transport_path`（公式のY→X掃引）
3. `place_item`（settle 300 step）

anchor recall oracleは搬入掃引を省略して `transport_contract:
agent_geometry_prevalidated` と記録するが、こちらは省略しない。`is_valid` が
収集対象のラベルそのものだからである。その分1候補あたりのコストは高い。

各候補のreplayは `saveState` / `restoreState` で挟む。step自体は最後に
policyが返した行動で進めるので、軌道は competition-equivalent のまま。

`--risk-gate-mode enforce` は拒否する。enforceは抽出前に母集団から
reject候補を消してしまい、このデータセットの存在意義を壊すため。
`shadow` を使う。

## Q列について

`score_immediate` は全候補に付く。一方 `weighted` / `depth2` が実際に使う

\[
Q = q_{\text{immediate}} + \gamma\,q_{\text{best next}}
\]

の未来項は、候補ごとにvisible poolの可行性走査を1回要する。全候補に付けると
コストが跳ねるので既定では計算しない。`--preview-limit N` を指定すると、
抽出済み候補のうちscore上位N件だけ `preview`
(`feasible_next_items` / `total_next_items` / `best_next_score`) を埋める。
未計算の行では `preview: null`。マニフェストに `requested` と `computed` を残す。

## 実行

```bash
python scripts/build_replay_dataset.py \
  --case 000 --steps 13 14 \
  --per-stratum 16 \
  --risk-gate-mode shadow
```

出力は `reports/replay-dataset/<timestamp>-<case>-<mode>/` に

- `manifest.json`: 実行条件、層ごとの母集団と抽出件数、所要時間
- `step-<nnn>-state.json`: s のスナップショット
- `step-<nnn>-candidates.jsonl`: 候補単位の行

Python 3.12が必要（simulatorがPEP 701のf-string構文を使う）。
