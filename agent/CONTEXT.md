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

## 現在の状態

- 回帰テストは `python scripts/run_checks.py` で一括実行する。
- GitHub Actions上でCPUシミュレータを再現可能。
- sample_configでは各ケース7個配置後に物理妥当性・安全性で失敗する。
- agentの次の修正は、シミュレータログから最初の不正遷移を再現して行う。
  API索引だけを根拠に配置ロジックを書き換えない。
