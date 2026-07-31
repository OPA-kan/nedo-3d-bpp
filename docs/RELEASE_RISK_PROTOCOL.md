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

1. **LOSO(leave-one-snapshot-out)**: 診断・モデル比較用。全ての行は
   自分の snapshot を見ていないモデルで採点される。
2. **完全holdout**: 最終報告用。以下は**学習・チューニングに一切使わない**:
   - **holdout case**: source case `001` × pool 40(`b001-k40` 系の全step)
   - **holdout pool**: 新規生成する pool 10(`b000-k10` / `b001-k10`)
   既存の b001-k40 データは今後の係数fitから除外する(今回のprovisional v1
   は全データfitなので、次回refitからこの規律を適用する)。
3. **不確実性**: 率・AUCとも snapshot-clustered bootstrap 1000回、
   percentile 2.5/97.5。行単位bootstrapは使わない(クラスタ相関を消すため)。
4. **重み付け**: 母集団率は必ず `sampling.sampling_weight` で
   Horvitz-Thompson 再重み付けし、raw件数を併記する。

## 4. 主要指標(凍結)

| 指標 | 定義 |
|---|---|
| 主 | holdout AUC(`rotated_over_30`、LOSO予測ではなくholdout予測) |
| 主 | オフライン再ランキング: λ∈{0.5, 1.0} での選択回転数の削減と平均score機会損失(snapshot単位) |
| 副 | LOSO AUC + 95% CI(`rotated_over_30`, `not_placed_safe`) |
| 副 | gate pass / reject 別の重み付き危険率 + CI |
| 副 | 連続 d_xy の held-out Spearman(`Phi_slide`) |

判断基準(目安、変更時は本文書を更新): holdout AUC が 0.70 を下回る場合は
係数を凍結しない。オフライン再ランキングで score 損失 5% 超を要する場合は
λ を採用しない。

## 5. データ追加の優先順位(凍結)

**候補行数を増やすことに価値はない。増やすのは独立性の軸:**

1. **独立 snapshot**(未使用の step、特に終了直前)
2. **独立 trajectory**(別の look_ahead、別の policy_timeout、
   `--seed` 違いの抽出ではなく軌道自体が変わる構成)
3. **未使用 case 構成**(pool 10 の task-b、元の case 000(k=1)/
   001(k=10)構成)

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
