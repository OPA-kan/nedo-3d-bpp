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
