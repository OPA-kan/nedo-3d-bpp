# シミュレーター解体書 (Simulator Functions Guide)

このドキュメントは提供されたスクリプトで、シミュレータ内の公開クラス・
メソッドを自動抽出した索引です。private methodや実際の分岐条件を網羅しないため、
物理・判定契約では `simulator/src/ground_handling/` の実ソースを優先してください。

- 移植日: 2026-07-28
- 元ファイル: `simulator_guide.md`
- Drive ID: `17hFll5JNSV_Jhnz6Cj1WCTxP41NRT8ot`
- 対応する固定ソース: `simulator/src/ground_handling/`

## 📁 File: `ground_handling/evaluator.py`

### Class: `Evaluator`
- **概要**: コンテナ内の積載状態を計算する評価モジュール

- **Method**: `Evaluator.__init__(self, client, config)`
  - 説明: No docstring
- **Method**: `Evaluator.calculate_fill_rate(self, containers)`
  - 説明: 充填率の計算. コンテナ内に完全に収まっている荷物のみを抽出する
- **Method**: `Evaluator.evaluate(self, containers, total_items)`
  - 説明: 現在のコンテナの評価を辞書形式で返す

---

## 📁 File: `ground_handling/camera.py`

### Class: `Camera`
- **概要**: コンテナの状態を撮影し, ハイトマップ(高さ画像)を生成するクラス

- **Method**: `Camera.__init__(self, client, config)`
  - 説明: config:     target_pos (list): カメラが注視する中心座標 [x, y, z]     distance (float): 注視点からの距離     yaw, pitch, roll (float): カメラの回転角度（度）。                               pitch=-90で真下(トップダウン)を見る。                               横から見る場合は pitch=0 などに調整。     img_width, img_height (int): 出力画像の解像度     fov (float): 視野角     near_val, far_val (float): 撮影範囲の最小・最大距離
- **Method**: `Camera.get_heightmap(self, center, lwh)`
  - 説明: 現在のコンテナ状態を撮影し、デプスマップを返す  Returns:     np.array: 形状 (height, width) の2次元配列。値はメートル単位の高さ。
- **Method**: `Camera.get_rgb_image(self)`
  - 説明: デバッグ確認用のRGB画像取得(人間が見る用)

---

## 📁 File: `ground_handling/runner.py`

### Class: `TimedAgentRunner`
- **概要**: No docstring

- **Method**: `TimedAgentRunner.__init__(self, agent_factory, allowed_methods, max_mem, verbose)`
  - 説明: No docstring
- **Method**: `TimedAgentRunner.call(self, method_name, time_out_sec, fallback, restart_on_timeout)`
  - 説明: agent.method_name(*args, **kwargs) を timeout 付きで呼ぶ。 timeout 時は fallback を返す。  fallback:   - 値そのもの   - callable の場合 fallback(*args, **kwargs) として呼ぶ
- **Method**: `TimedAgentRunner.close(self)`
  - 説明: No docstring
### Class: `TimeOutError`
- **概要**: No docstring


---

## 📁 File: `ground_handling/items.py`

### Class: `Item`
- **概要**: 単一の荷物(直方体)の物理プロパティとPyBullet上の実体を管理するクラス

- **Method**: `Item.get_info(self)`
  - 説明: 物理空間における最新の位置や姿勢情報を取得する
- **Method**: `Item.spawn(self, client, initial_pos, initial_orn)`
  - 説明: PyBulletの物理空間に荷物を生成(スポーン)する. 物理空間上のIDが付与される
- **Method**: `Item.remove(self, client)`
  - 説明: 物理空間から生成した手荷物を削除
- **Method**: `Item.set_pose(self, client, pos, orn)`
  - 説明: シミュレーションの時間を進めずに指定された座標・姿勢へ瞬時にワープさせる
- **Method**: `Item.get_pose(self, client)`
  - 説明: 現在の座標(pos)と姿勢(orn: クォータニオン)を取得する
- **Method**: `Item.register_pos_orn(self, container_index, pos, orn)`
  - 説明: No docstring
### Class: `ItemStreamManager`
- **概要**: あらかじめ全荷物情報を保持し, コンベア上の k 個の荷物をプールとして管理・供給するクラス

- **Method**: `ItemStreamManager.__init__(self, config)`
  - 説明: config:     - item_list: list[Item], 全手荷物のリスト     - lookahead: int,  見える手荷物の数の上限     - visible_pool: list[Item], プールされていて見えている手荷物一覧リスト
- **Method**: `ItemStreamManager.set_order(self, order)`
  - 説明: No docstring
- **Method**: `ItemStreamManager.get_items_of_visible_pool(self)`
  - 説明: No docstring
- **Method**: `ItemStreamManager.get_all_items(self)`
  - 説明: No docstring
- **Method**: `ItemStreamManager.reset(self)`
  - 説明: エピソード開始時にストリームをリセットし, 最初のk個をプールに設定する
- **Method**: `ItemStreamManager.get_item(self, pool_index)`
  - 説明: プール内の指定インデックスのアイテム実体を取得する
- **Method**: `ItemStreamManager.pop_and_refill(self, pool_index)`
  - 説明: プールの状態を更新（取られたときや補填するとき） 荷物を選択後, プールから取り除き奥から新しい荷物を補充する
- **Method**: `ItemStreamManager.is_empty(self)`
  - 説明: プール内のすべての荷物が処理され空になったか

---

## 📁 File: `ground_handling/env.py`

### Class: `GroundHandlingEnv`
- **概要**: PyBulletを用いた物理シミュレーションベースの3Dパッキング環境 横空きコンテナへの「押し込み配置」と強化学習用インターフェースを提供する

- **Method**: `GroundHandlingEnv.__init__(self, config, verbose, render_mode)`
  - 説明: No docstring
- **Method**: `GroundHandlingEnv.reset_settings(self)`
  - 説明: No docstring
- **Method**: `GroundHandlingEnv.reset_item_stream(self)`
  - 説明: No docstring
- **Method**: `GroundHandlingEnv.reset(self, seed, options)`
  - 説明: No docstring
- **Method**: `GroundHandlingEnv.get_init_states(self)`
  - 説明: No docstring
- **Method**: `GroundHandlingEnv.get_info_for_optimization(self)`
  - 説明: No docstring
- **Method**: `GroundHandlingEnv.set_item_order(self, order)`
  - 説明: No docstring
- **Method**: `GroundHandlingEnv.step(self, action)`
  - 説明: 1ステップの実行: 行動解析 -> 目標位置検証 -> 物理配置 -> 観測更新
- **Method**: `GroundHandlingEnv.evaluate(self)`
  - 説明: No docstring
- **Method**: `GroundHandlingEnv.close(self)`
  - 説明: No docstring

---

## 📁 File: `ground_handling/containers.py`

### Class: `Container`
- **概要**: 単一のコンテナの情報と状態を保持するデータクラス

- **Method**: `Container.create(self, client, save_obj)`
  - 説明: PyBullet上で1つの横空きコンテナを生成
- **Method**: `Container.create_cap(self, client)`
  - 説明: 蓋を生成する
- **Method**: `Container.local_to_global(self, local_pos)`
  - 説明: 相対座標をPyBullet上の世界座標に変換
- **Method**: `Container.global_to_local(self, global_pos)`
  - 説明: 世界座標から相対座標に変換
- **Method**: `Container.add_item(self, item)`
  - 説明: コンテナに手荷物を追加する
- **Method**: `Container.update_packed_items(self, client)`
  - 説明: No docstring
### Class: `MultiContainerManager`
- **概要**: 複数コンテナの生成と全体管理を行うマネージャクラス

- **Method**: `MultiContainerManager.__init__(self, client, config)`
  - 説明: No docstring
- **Method**: `MultiContainerManager.build(self)`
  - 説明: 指定された数の横空きコンテナをX軸に並べて構築する
- **Method**: `MultiContainerManager.get_item_info_in_containers(self)`
  - 説明: policy側に渡す観測情報の生成
- **Method**: `MultiContainerManager.get_container(self, index)`
  - 説明: 指定されたインデックスのコンテナオブジェクトを取得
- **Method**: `MultiContainerManager.update_and_add_item_to_container(self, container_id, item)`
  - 説明: コンテナの中身の更新と安全に配置された手荷物を座標とともに登録
- **Method**: `MultiContainerManager.clear(self)`
  - 説明: No docstring

---

## 📁 File: `ground_handling/app.py`

### Class: `EvaluationApp`
- **概要**: No docstring

- **Method**: `EvaluationApp.__init__(self, config_path, module_path, agent_module, agent_class, result_dir, result_fname)`
  - 説明: No docstring
- **Method**: `EvaluationApp.run(self, render_mode, verbose)`
  - 説明: No docstring

---

## 📁 File: `ground_handling/validator.py`

### Class: `BaseValidator`
- **概要**: No docstring

- **Method**: `BaseValidator.__init__(self, client, config, render_mode)`
  - 説明: No docstring
- **Method**: `BaseValidator.check_action(self, action, action_config, num_containers, num_visible_items)`
  - 説明: No docstring
### Class: `PlacementValidator`
- **概要**: No docstring

- **Method**: `PlacementValidator.check_inclusion(self, container, item, target_pos, target_orn_idx)`
  - 説明: 目標位置において手荷物がコンテナの内部に含まれるかを判定する
- **Method**: `PlacementValidator.check_transport_path(self, container, item, target_pos, target_orn_idx, step_len)`
  - 説明: 目標位置(target_pos: 世界座標系)へ運ぶ軌道上で衝突がないか判定する 座標は絶対座標
- **Method**: `PlacementValidator.place_item(self, item, target_pos, target_orn_idx)`
  - 説明: No docstring

---

## 📁 File: `ground_handling/__init__.py`

### Class: `Agent`
- **概要**: 荷物配置エージェントの抽象基底クラス。 独自のエージェントを作成する際は、このクラスを継承して各メソッドを実装してください。

- **Method**: `Agent.__init__(self, module_path)`
  - 説明: No docstring
- **Method**: `Agent.get_init_states(self, init_states)`
  - 説明: 環境の初期状態を受け取る。  Args:     init_states: コンテナ情報や lookahead_k などの初期設定
- **Method**: `Agent.optimize(self, item_list)`
  - 説明: [オフライン最適化] 事前に全ての荷物情報を受け取り、積み込む最適な順序を計算する。  Args:     item_list: 全荷物の情報リスト Returns:     list[int]: 荷物のインデックスを並べ替えたリスト
- **Method**: `Agent.policy(self, observation)`
  - 説明: [オンライン最適化/逐次実行] 現在の観測状態から次の行動を決定する。  Args:     observation: 現在のプール内の荷物やコンテナの状況 Returns:     dict: 選択した荷物、コンテナ、座標、向きを含むアクション辞書

---

## 📁 File: `ground_handling/agent_factory.py`

### Class: `AgentFactory`
- **概要**: No docstring

- **Method**: `AgentFactory.__init__(self, module_name, class_name)`
  - 説明: No docstring

---

## 📁 File: `ground_handling/utils.py`

### Function: `get_half_ext(original_lwh, orn_idx)`
- **説明**: No docstring

### Function: `center_xy(poly, cx, cy)`
- **説明**: No docstring

### Function: `aff(origin, rot, intercept)`
- **説明**: No docstring

### Function: `line_intersection_2d(p1, d1, p2, d2)`
- **説明**: 2直線 p1+t*d1, p2+s*d2 の交点

### Function: `offset_convex_polygon_ccw(poly, offset)`
- **説明**: CCW順の凸多角形を、各辺から offset だけ内側へオフセット

### Function: `triangulate_fan(indices, reverse)`
- **説明**: No docstring

### Function: `write_open_cut_corner_cup_obj(file_path, width, height, cut_x, cut_y, depth, wall, bottom)`
- **説明**: 左上角を切り落とした五角形断面の、中空・上面開口・底あり形状をOBJ出力 断面はXY平面、奥行き方向はZ

### Function: `write_corner_lid_obj(file_path, width, height, cut_x, cut_y, depth, lid_thickness)`
- **説明**: 開口の欠け角を塞いで、見かけ上の開口を長方形にするための 薄い蓋パーツ（独立オブジェクト）


---
