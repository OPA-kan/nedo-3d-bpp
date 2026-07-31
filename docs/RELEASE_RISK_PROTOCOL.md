# Release risk 評価プロトコル(凍結版 v1)

作成: 2026-07-31。以後の replay データ追加生成・モデル比較は本プロトコルに
従う。変更する場合は本ファイルを更新し、変更点と理由をコミットメッセージに
明記する(過去の数値との比較可能性が壊れるため、黙って変えない)。

## 現時点の結論(要引用時の正しい言い方)

- **既存Φには回転危険(`rotated_over_30`)の予測信号があるが、
  snapshot間外挿が不安定で係数は未確定**(LOSO AUC 0.699 [0.581, 0.804]、
  case外挿 0.784 / 0.676、pool外挿 0.745 / 0.646)。
- **水平変位は未解決**。item属性の結合で binary AUC 0.614→0.693 と改善する
  が、連続 d_xy の held-out Spearman は 0.176 と弱い。
- `support_ratio >= 0.6` は**低危険率領域**(rotation 0.004 [0.000, 0.016])
  であり、安全証明ではない。hard-accept 則としては実装しない。

## 1. 特徴集合(凍結)

回転リスク `Phi_rot`(この6項目・この順序・この変換):

| # | 特徴 | 変換 |
|--:|---|---|
| 1 | `support_ratio` | そのまま |
| 2 | `com_margin` | そのまま |
| 3 | `drop_normalized` | そのまま |
| 4 | `support_imbalance` | **絶対値** |
| 5 | `left_right_imbalance` | **絶対値** |
| 6 | `front_back_imbalance` | **絶対値** |

- `overhang_ratio` は `1 - support_ratio` と同一情報のため入れない。
- `initial_tilt_deg` は恒等的に 0 の placeholder のため学習に使わない
  (`phi_availability` を機械的に確認する)。
- 滑り評価用の拡張特徴 `Phi_slide` = `Phi_rot` + item属性
  (`mass`, `lateralFriction`, `restitution`, `is_soft`,
  `density = mass/volume`, `min_extent/max_extent`)。
  state snapshot の `observation.pool_list` から `item_index` で結合する。
  再生成は不要。

## 2. モデル(凍結)

- 標準化ロジスティック回帰: 訓練foldで各特徴を `(x - mean) / std` に標準化、
  切片あり、batch勾配降下 3000 epoch、学習率 0.5、正則化なし、クリップ
  |z| <= 30。実装は `scripts/evaluate_release_risk.py::fit_logistic_np`。
- これより複雑なモデル(木、GBM等)を試す場合も、この logistic を
  **必ずベースラインとして並記**する。

## 3. 評価(凍結)

### 3.1 データ分割(manifestの `split` フィールドで機械的に判定)

| split | 構成 | 用途 |
|---|---|---|
| `development` | b000-k20, b000-k40, b001-k20 とその追加step、新trajectory(b000-k15, b001-k30 等) | 係数fit・特徴選択・診断 |
| `validation` | b000-k10 | λ選択・モデル比較の検証(fitには使わない) |
| `final_holdout` | b001-k40(既存run含む)、b001-k10 | 最終報告で**一度だけ**開く |

- 各データセットの `manifest.json` に `split` を記録する。生成時は
  `build_replay_dataset.py --split` で指定する(既定 `development`)。
- **`final_holdout` は学習・特徴選択・λ選択・通常分析から機械的に除外**
  される: `analyze_replay_dataset.py` / `evaluate_release_risk.py` は
  manifest の `split == "final_holdout"` を読み飛ばし、明示フラグ
  `--open-final-holdout` を渡したときだけ読む。このフラグは§7の最終評価
  以外で渡してはならない。
- 既存の b001-k40 の2 run は provisional v1 の fit に混入済み(既知の汚染)。
  `final_holdout` に指定した時点から先は一切使わず、最終評価の報告時に
  この汚染を注記する。

1. **LOSO(leave-one-snapshot-out)**: development 内の診断・モデル比較用。
   全ての行は自分の snapshot を見ていないモデルで採点される。
2. **validation**: development で fit した係数を固定し、λ・特徴集合・
   モデル形の選択だけを validation で行う。
3. **不確実性**: 率・AUCとも snapshot-clustered bootstrap 1000回、
   percentile 2.5/97.5。行単位bootstrapは使わない(クラスタ相関を消すため)。
4. **重み付け**: 母集団率は必ず `sampling.sampling_weight` で
   Horvitz-Thompson 再重み付けし、raw件数を併記する。

## 4. 主要指標(凍結)

採用判断は AUC と score 損失だけでは行わない。**changed snapshot
(shadow rerank が baseline と異なる候補を選んだ step)上のペア比較**が
主要指標である。両候補とも counterfactual 物理ラベルが強制包含で
付いているため、直接差が取れる。

| 指標 | 定義 |
|---|---|
| 主 | changed snapshot 上の**回転危険差**: baseline の `rotated_over_30` 数 − shadow 選択の `rotated_over_30` 数 |
| 主 | changed snapshot 上の **placed-safe 差**: shadow 選択の placed-safe 数 − baseline の placed-safe 数 |
| 主 | **安全→危険の逆転数**: baseline が safe かつ shadow 選択が dangerous になった snapshot 数(この逆転は 0 に近いことが採用条件) |
| 主 | validation AUC(`rotated_over_30`) |
| 副 | オフライン再ランキング: λ∈{0.5, 1.0} での選択回転数の削減と平均score機会損失(snapshot単位) |
| 副 | LOSO AUC + 95% CI(`rotated_over_30`, `not_placed_safe`) |
| 副 | gate pass / reject 別の重み付き危険率 + CI |
| 副 | 連続 d_xy の held-out Spearman(`Phi_slide`) |

判断基準(目安、変更時は本文書を更新): validation AUC が 0.70 を下回る
場合は係数を凍結しない。score 損失 5% 超を要する λ は採用しない。
安全→危険の逆転が回転危険削減を上回る λ は採用しない。
**実 action の risk-adjusted への切り替えは、final_holdout 評価が
完了するまで行わない。**

## 5. データ追加の優先順位(凍結)

**候補行数を増やすことに価値はない。増やすのは独立性の軸:**

1. **独立 snapshot**(未使用の step、特に終了直前)
2. **独立 trajectory**(別の look_ahead、別の policy_timeout、
   `--seed` 違いの抽出ではなく軌道自体が変わる構成。
   development 用の新構成例: b000-k15, b001-k30)
3. **未使用 case 構成** — ただし §3.1 の split 割当に従う:
   b000-k10 は validation、b001-k10 / b001-k40 は final_holdout であり
   development の追加データにはならない。

追加生成は `RELEASE_RISK_SHADOW_RERANK=1` を併用し、changed=true の
snapshot では baseline 候補と shadow 候補の counterfactual ラベルが
**ペアで**保存されることを確認する(step summary の
`shadow_pair`、行の `selected` / `shadow_rerank_selected`)。

per-stratum は 8 のままでよい。1構成あたり数十行×snapshot数で足りる。

## 6. Shadow reranking(実装済み・計測手順)

`agent/agent.py` に環境変数ゲートで実装(実 action は不変):

- `RELEASE_RISK_SHADOW_RERANK=1` で有効化、
  `RELEASE_RISK_RERANK_LAMBDA`(既定 1.0)。
- baseline の選択が release candidate のときだけ、**現行 selection stack
  そのもの**(settled優先 + lookahead + 同一の探索)を risk調整score
  `Q - λ·P̂_rot` で再実行し、`diagnostics["shadow_rerank"]` に
  baseline / risk_selection / changed / p_rot を記録する。
  settled 選択時は risk 項が選択に影響し得ないため再探索しない。
- P̂ は `RELEASE_RISK_LOGISTIC_V1`(provisional、本プロトコルの
  refit手順で更新するまで係数は暫定)。
- `scripts/build_replay_dataset.py` は shadow 選択候補を
  `forced_reason: shadow_rerank_selection` で強制包含し、行に
  `shadow_rerank_selected` を付ける。→ 仮想選択の counterfactual
  物理ラベルが実選択と同じ列で手に入る。
- step summary に `shadow_rerank` / `shadow_rerank_matched` を記録。

計測実行例:

```bash
RELEASE_RISK_SHADOW_RERANK=1 RELEASE_RISK_RERANK_LAMBDA=1.0 \
python scripts/build_replay_dataset.py \
  --config <task-b config> --case <id> --steps <mid..late> \
  --per-stratum 8 --risk-gate-mode shadow
```

注意: shadow 再探索は release 選択 step の政策時間を最大2倍にする。
オンライン提出経路では必ず無効(既定値 0)のままにする。

## 7. 係数の refit / 凍結手順

1. 追加データ生成(§5の優先順位、holdout構成には触れない)。
2. `scripts/evaluate_release_risk.py` で LOSO + 外挿 + bootstrap を再計算。
3. §4 の基準を満たしたら、非holdoutデータ全体で refit し、
   `RELEASE_RISK_LOGISTIC_V1` を新バージョン名で置き換える
   (旧係数はgit履歴に残る)。
4. holdout 評価は**一度だけ**行い、結果を findings に記録する。
