# Agent context

## 役割

`agent/agent.py`は提出コードの正本で、公開入口は次の3メソッド。

- `get_init_states(init_states)`: コンテナ形状・棚・lookaheadを初期化
- `optimize(item_list)`: Task1の積付順序を返す
- `policy(observation)`: Task2の逐次配置行動を返す

## 固定契約

- 配置候補はコンテナローカル座標、観測済み荷物は世界座標。
- local/world変換はX軸のコンテナoffsetだけ。
- 棚寸法はsimulatorの生成式から導出する。
- 境界は16 mm、搬入経路と側面は16 mmを内部安全量として使う。
- 支持面との垂直接触には搬入クリアランスを要求しない。
- 配置後の観測姿勢から既配置荷物のAABBを再構成する。
- soft/priority荷物を後続荷物の支持面にしない。

詳細は `docs/GEOMETRY_RULES.md` が正本。

## 探索

- 構築順序を共通配置コアでdry-runする。
- Or-opt、swap、2個の逐次再生可能部分列テンプレートを併用する。
- 評価は配置失敗を最優先し、その後に充填・支持・重心を比較する。
- 単品近傍はマクロ近傍で置き換えない。
- オンラインlookaheadは `LOOKAHEAD_SELECTION_MODE` で切替可能。
  `weighted` は既定互換、`depth2` は次手可行性を辞書式優先、
  `pool_resilience` は次に配置可能な可視荷物数を最優先する。
  詳細は `python scripts/context.py show preview-value`。
- コンテナ半空間から姿勢・`(x,y)`ごとの`Zmin/Zmax`を解析的にキャッシュし、
  水平支持候補が全滅した姿勢には低高度の`release_candidate`を生成する。
  release候補は投下点で支持率を要求せず、包含・静的干渉・搬入を通した後、
  PyBullet settle結果を真値とする。
- 候補生成はdeadline-awareなlazy streamとし、戦略順の荷物、底面積の大きい姿勢、
  残余体積の大きいコンテナから優先する。各三組を64 anchorずつ浅く一巡後、
  256 anchor単位で深掘りし、時間切れ時も最良の検証済みincumbentを返す。
- settled列挙の末尾まで到達しないとrelease候補が出ない退行を避けるため、
  各三組をsettled/releaseの独立unitに分け、同じ浅い一巡で両方を探索する。
- 現段階では旧Cartesian anchor集合を維持しているため、跨ぎ支持候補の損失はない。
  支持面ローカルanchorへ縮約するときは旧列挙をoffline oracleとして
  anchor recall、best-score regret、replay配置数差を測る。

## 現在の状態

- 回帰テストは `python scripts/run_checks.py` で一括実行する。
- GitHub Actions上でCPUシミュレータを再現可能。
- run 30331700531では各ケース7個配置後に失敗し、LD3斜面を水平支持面として
  表現できないことが主要な偽陰性と判明した。
- release候補実装後のrun 30334277618ではCase 000/001とも13個まで配置した
  （旧runは各7個、合計14→26）。release後の変位は概ね鉛直52 mm、
  姿勢変化は0〜0.1度で、斜面での顕著な滑り・傾きは観測されなかった。
- 両ケースともstep 13で終了した。Case 000は8秒のpolicy timeout後に
  simulatorのrandom fallbackが失敗、Case 001は候補を受理できず固定fallbackが失敗した。
  次の共通ボトルネックは直積アンカー列挙の時間と後半のstatic/support/corridor棄却。
- run 30337216417では最大policy時間が9.87秒から6.52秒へ下がり外部timeoutを
  解消した一方、release候補がsettled全列挙の末尾に隠れてCase 000/001が
  12/7個へ退行した。release独立unit修正後の物理結果は未検証。
- 診断には探索unitの開始数/総数、round数、deadline到達、incumbent更新数を保存する。
- 3方式は引き続き同一履歴であり、30個前後へ届くまでlookahead比較・重み調整は保留する。

## Release fallback ordering

- Settled and release candidates are searched as independent units so that a
  release probe cannot be hidden behind exhaustive settled-anchor enumeration.
- Their incumbents are kept separately. If any validated settled candidate
  exists, it is chosen regardless of the release candidate's heuristic score.
- A release candidate is returned only when the search found no settled
  candidate. This is a safety ordering: run 30338524490 reached 14 placements
  in Case 000, but Case 001 selected a high-scoring release at step 4 and
  failed after settling by 0.638 m with a 90-degree rotation.
