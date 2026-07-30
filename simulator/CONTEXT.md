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

診断用step metricsには、物理契約を変更せず、targetからsettle後までの
位置変位、角度差、最終位置・quaternion、最終AABB寸法を記録する。
安全判定の閾値は公式設定どおりで、診断追加によってvalidatorの合否は変えない。
各step開始時にsettle telemetryをresetし、搬入失敗などplace未試行のstepへ
直前の配置結果を持ち越さない。

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

## Task B benchmark

`sample_config.json`のCase 001は `optimize=false`、pool 10のTask B proxy。
GitHub Actionsではこのcaseを基にpool 3/10/20/40、policy timeout 8秒のconfigを
生成し、各条件を3回screeningする。job別artifactに段階別・class別coverageと
failure modeを保存し、aggregate jobがmean/median/std/min/maxと停止原因回数を出す。
benchmark modeはsimulator processとevaluation構造が正常なら成功とし、
全荷物完遂は別のstrict physics validationとして記録する。固定fallbackによる
途中終了を隠さず、CI infrastructure failureとalgorithm benchmark failureを分ける。
agent内候補枯渇は`no_safe_action`として意味論を分け、外部APIへ返す固定座標は
`unsafe_protocol_fallback`と診断する。policy timeout時にsimulatorが返すrandom
actionも安全性非保証のprotocol fallbackであり、現時点では削除しない。

