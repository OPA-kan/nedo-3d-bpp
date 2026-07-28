# Anchor recall oracle

## 目的

anytime探索がdeadline内にsettled候補を見逃しているのか、現在状態に
settled候補が本当に存在しないのかを、同一のpre-action状態で判定する。
通常の提出動作は変更せず、専用のオフライン計測時だけcandidate auditを有効にする。

## 実行

Case 001のstep 0〜4を完全計測する例:

```bash
python scripts/measure_anchor_recall.py \
  --case 001 \
  --steps 0 1 2 3 4 \
  --mode weighted
```

出力先を指定する場合:

```bash
python scripts/measure_anchor_recall.py \
  --case 001 \
  --steps 3 4 \
  --output-dir reports/anchor-recall/case001-steps3-4
```

開発時のsmoke testでは候補数を制限できる。

```bash
python scripts/measure_anchor_recall.py \
  --case 001 \
  --steps 0 \
  --oracle-limit 20 \
  --physical-limit 5
```

`--oracle-limit`または`--physical-limit`で打ち切った結果は
`oracle_complete=false`または`physics_complete=false`となり、
`physical_recall`を確定値として出さない。

## 保存状態

各対象stepのaction実行前に、独立して再確認できる状態を
`step-NNN-state.json`へ保存する。

- pool内荷物の全属性
- 全配置済み荷物の世界座標位置と観測quaternion
- 配置済み荷物の線速度・角速度
- コンテナのhalf-space境界 (`points`, `n_vecs`)
- 棚属性とコンテナ寸法
- validator閾値とorientation契約
- policyへ渡したdepth map

候補生成が使う座標はコンテナlocal、配置済み荷物はworldであることも
snapshot内に明記する。

## 分母と分子

同一状態で次を実行する。

1. 現行anytime policyを6.5秒予算で実行し、実際に受理したsettled候補を記録
2. 同じ状態でdeadlineなし・accepted limitなしの旧Cartesian列挙を実行
3. oracle候補を重複除去
4. 各oracle候補をlive PyBullet状態へ一件ずつ適用
5. `saveState/restoreState`で各試行後に完全に元の物理状態へ戻す
6. 公式inclusion判定と公式300-step settle判定を通った候補を分母とする
7. そのうちanytimeが発見していた候補を分子とする

候補はagent側ですでに包含・静的干渉・支持・搬入経路を通過している。
物理oracleでは、そのうち公式inclusionとsettle安全性を再確認する。
候補ごとの搬入経路をPyBulletで再生成するとcollision shapeを大量生成するため、
offline oracleの物理分母はsettle安全性を対象とする。結果には
`transport_contract=agent_geometry_prevalidated`を明記する。

## 出力

- `summary.json`: run設定とstep別集計
- `step-NNN-state.json`: 完全なpre-action観測・物理snapshot
- `step-NNN-summary.json`: recall、regret、分類
- `step-NNN-candidates.jsonl`: oracle候補、anytime発見有無、物理結果

主要指標:

| 指標 | 意味 |
|---|---|
| `oracle_settled_count` | unlimited列挙で受理した幾何settled候補数 |
| `anytime_settled_count` | 実policyがdeadline内に発見したsettled候補数 |
| `oracle_physical_settled_count` | 公式inclusion・settleを通ったoracle候補数 |
| `anytime_physical_settled_count` | 上記のうちanytimeが発見した数 |
| `physical_recall` | 物理的に安全なsettled候補のrecall |
| `best_score_regret` | oracle最良safe scoreとanytime最良safe scoreの差 |
| `time_to_first_anytime_settled` | anytimeの最初のsettled発見時間 |
| `policy_elapsed_seconds` | audit有効時のpolicy実測時間 |

candidate auditは候補受理時に小さなrecordを追加するため、完全にゼロコストではない。
`policy_elapsed_seconds`を通常runと比較し、計装による探索量低下が無視できる範囲か
確認する。差が大きい場合は、同一snapshot上でauditあり・なしの時間比較を追加する。

## 判定

| 結果 | 次の実装 |
|---|---|
| oracleにsafe settledあり、anytimeにはなし | per-support-plane anchor化 |
| 両方にsafe settledあり、regretが大きい | Rankerまたは探索優先順 |
| failure stepではoracleもゼロ、以前のstepで分岐 | 残余空間価値・以前の配置選択 |
| 最初からoracleもゼロ | release risk gateと安全release生成 |

per-support-plane化へ進む場合、同高・隣接面の初期間隔閾値は
搬入クリアランスと同じ16 mmから開始し、跨ぎ支持recallをoracleで再評価する。
なお、現行の鉛直接触許容 `CONTACT_TOLERANCE` は6 mmであり、別パラメータである。

## Per-support-plane generator

既定のsettled候補生成は `support_plane` modeである。旧方式へ戻す場合だけ
`ANCHOR_GENERATOR_MODE=cartesian` を指定する。offline oracleは環境変数に
依存せず、常に `generator_mode="cartesian"` を明示する。

支持面は上面高さの差が6 mm以内で、辺方向の水平隙間が16 mm以下の場合に
同じ連結成分へまとめる。角だけで近接する面は連結しない。連結成分の支持率は
各矩形との重なりのunion面積で計算するため、2荷物に跨る支持を評価できる。

面のpriority round-robin順序:

| 順 | 面 | 根拠 |
|---:|---|---|
| 1 | 床 | 安定し、落下距離が短い |
| 2 | 大面積上面 | 支持率が高く、次の支持面を作りやすい |
| 3 | 奥側の面 | 手前を塞がず、後続の搬入経路を維持する |
| 4 | 低い上面 | 高い壁と到達不能な空隙を作りにくい |

各探索の `support_plane_searches` には次を保存する。

- `adjacency_threshold`
- `surface_count` / `component_count`
- `connected_anchor_count`
- `unconnected_anchor_count`
- `component_order` の面積、奥行き、高さ、床フラグ

これにより、16 mm連結による候補数増減と、面順序を変更した根拠をrunごとに
追跡できる。

run 30348998307の保存snapshotを使った非物理replayでは、step 4のsettled試行を
116,008から10,438へ91.0%削減し、旧oracleの最良scoreを保持した。実policyの
deadline内settled発見数はstep 3で0から349、step 4で0から427へ増えた。
新しいtrajectoryの公式PyBullet結果は、別のLinux simulator runで確認する。

## Failure-step dual oracle

後半の固定fallbackを、deadline内の到達失敗と候補モデル内の行き止まりに
分離するため、oracle schema version 2では次の3集合を同じpre-action stateで
列挙する。

1. legacy Cartesianのsettled候補
2. per-support-planeのsettled候補
3. Cartesian release候補

settledの2集合はcandidate keyでdedupeし、各recordの
`oracle_generators` に `cartesian` / `support_plane` のprovenanceを残す。
summaryの `oracle_stats` はgenerator別件数、共通件数、片側だけの件数、
列挙時間を保存する。release集合は別のJSONLと `release_oracle` に保存し、
settledと混ぜずにPyBullet検証する。

policy側は各stepで次を `policy_log` に保存する。

- `action_source` / `candidate_kind`
- deadline内のaccepted settled / release件数
- top candidate数
- 探索unitの開始・完了数、round数、deadline到達
- incumbent更新数

固定fallback stepの `failure_classification` は次のいずれかになる。

| classification | 意味 |
|---|---|
| `deadline_missed_safe_settled` | oracleには安全settledがあるがanytimeは0件 |
| `safe_release_only` | settledは0件で、安全releaseだけが存在 |
| `no_safe_candidate_in_oracle_sets` | dual settled/release集合とも安全候補0件 |
| `incumbent_invariant_violation` | accepted候補があるのに固定fallback |
| `incomplete` | 列挙または物理検証が上限・skipで未完了 |

GitHub ActionsはCase 000のstep 13/14、Case 001のstep 9/10を測り、
`reports/anchor-recall/history/<run-id>/case-000|001/` にcompact summaryを
commitする。候補JSONLと完全state snapshotはartifactにだけ保存する。
