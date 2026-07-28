# Simulator context

## 実行フロー

`EvaluationApp.run`がagentを別プロセスで起動し、概ね次の順で呼ぶ。

1. `GroundHandlingEnv.reset`
2. `Agent.get_init_states`
3. 必要な課題では `Agent.optimize` と `set_item_order`
4. 各ステップで `Agent.policy`
5. `GroundHandlingEnv.step`
6. 全体終了時に `GroundHandlingEnv.evaluate`

## 1ステップの判定

`env.py`と`validator.py`が正本。概略は次の順。

1. action index・姿勢・コンテナの範囲
2. 目標位置でのコンテナ包含
3. 横開口からの搬入経路
4. PyBulletによる配置とsettle
5. 配置後の包含・経路妥当性・安全性
6. 安全な荷物だけをpacked itemsへ登録

プロセスの `status=success` は物理配置成功を意味しない。
`place_states.is_included`、`is_valid`、`is_placed_safe`も確認する。

## ソース地図

- `app.py`: 評価全体とtimeout呼び出し
- `env.py`: observation、step、評価遷移
- `validator.py`: 包含、搬入、settle
- `containers.py`: LD3形状、棚、local/global変換
- `items.py`: 荷物streamと物理姿勢
- `evaluator.py`: fill等の評価値
- `runner.py`: agent別プロセス、時間・メモリ制限

`docs/simulator/API_REFERENCE.md`は提供された自動抽出索引。概要把握には使えるが、
private methodと実際の分岐条件はソースを読む。

