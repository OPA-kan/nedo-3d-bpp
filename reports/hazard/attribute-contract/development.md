# 属性契約（両側）— 開発裁定

Protocol: `reports/hazard/attribute-contract-protocol.md`（波の投入前に凍結）。placed の床は `reports/benchmarks/baseline.json`。

## 構成ごと（base 対 attr_contract、同一run ペア）

| 構成 | base | contract | 差 | 床 | 判定 |
|---|---:|---:|---:|---:|---|
| `b000-k15` | 21.00 | 17.00 | -4.00 | 5.23 | inside_floor |
| `b000-k20` | 20.00 | 12.33 | -7.67 | 2.23 | breaches |
| `b000-k40` | 21.00 | 14.67 | -6.33 | 3.93 | breaches |
| `b001-k20` | 18.67 | 14.00 | -4.67 | 4.22 | breaches |
| `b001-k30` | 17.00 | 13.00 | -4.00 | - | no_floor |
| `c000-k1` | 19.67 | 22.00 | +2.33 | 7.10 | inside_floor |
| `c001-k1` | 19.33 | 21.00 | +1.67 | - | no_floor |

## プール（4アーム）

| 量 | `base` | `attr_support_rule` | `attr_guard_priority` | `attr_contract` |
|---|---|---|---|---|
| episodes | 21 | 21 | 21 | 21 |
| placed 合計 | 410 | 405 | 343 | 342 |
| 優先違反 | 20 | 11 | 9 | 12 |
| soft 違反 | 4 | 2 | 5 | 8 |
| 物理死 | 8 | 5 | 16 | 14 |
| shake 最大ずれ | 0.3334 | 0.2619 | 0.2289 | 0.2100 |
| shake ピーク運動E | 46.9562 | 23.3704 | 75.7219 | 67.8023 |

## ゲート

| ゲート | 結果 |
|---|---|
| A 優先違反が base 比 50% 以上減 | 40.0% 減 → **fail** |
| P どの構成でも床を負方向に割らない | 割った構成 ['b000-k20', 'b000-k40', 'b001-k20'] → **fail** |
| S shake が悪化しない | **fail** |
| N 両方の単独に勝つ | 違反<支持則単独 False、placed>ガード単独 False → **fail** |

## 開発判定: **FAIL**

不採用。落ちたゲートが結果であり、閾値は動かさず、このストリームで再調整もしない。
