# UR5 Gazebo MoveIt2 LLM-TAMP 開發流程檢核文件

本文件用來追蹤 ROS2 Humble 專案從目前僅有 `ur5_description`，逐步擴充到可在 Gazebo 模擬中用 Whisper 語音輸入、LLM 產生 skill plan，並透過 MoveIt2 控制 UR5 + Robotiq 2F-85 操作桌面物件的完整流程。

目標系統：

- Robot：UR5
- Simulator：Gazebo，ROS2 Humble 階段可先用 Gazebo Classic + `gazebo_ros2_control`
- Motion planning：MoveIt2
- Controller：`ros2_control`
- Gripper：Robotiq 2F-85
- Camera：Intel RealSense D435i RGBD
- LLM：OpenAI API 快速概念驗證；Ollama Qwen 作為未來本地端部署路線
- Local STT：Whisper / faster-whisper
- UI：Web frontend + backend API
- TAMP：LLM 產生結構化 skill sequence，validator 檢查後由 skill executor 執行

## 0. 建議專案結構

預計 workspace：

```text
ur5_gazebo/
  docs/
  src/
    ur5_description/
    robotiq_2f85_description/
    d435i_description/
    ur5_workcell_description/
    ur5_gazebo/
    ur5_moveit_config/
    perception_pipeline/
    world_state_manager/
    skill_library/
    tamp_planner/
    task_executor/
    voice_interface/
    web_backend/
    web_frontend/
```

檢核：

- [ ] 所有 package 可用 `colcon build` 建置。
- [ ] 每個 package 有明確 README 或 package-level 說明。
- [ ] launch 檔可由上層 bringup 一次啟動完整模擬。

## 1. 機械模型整合

### 1.1 UR5 現況盤點

目前已有：

```text
src/ur5_description/
  urdf/ur5.urdf.xacro
  urdf/ur5_ros2_control.xacro
  meshes/
  launch/display.launch.py
```

檢核：

- [ ] `robot_state_publisher` 可正常發布 UR5 TF。
- [ ] RViz 可正常顯示 UR5 visual/collision。
- [ ] 所有 UR5 joint name 與後續 controller / MoveIt 設定一致。

### 1.2 加入 Robotiq 2F-85

新增：

```text
src/robotiq_2f85_description/
  urdf/robotiq_2f85.urdf.xacro
  meshes/
```

需要定義：

- gripper base link
- left/right finger links
- mimic joints 或可控 joint
- TCP frame：`gripper_tcp`
- collision geometry
- inertial
- ros2_control command/state interfaces

建議 TF：

```text
wrist_3_link
  └── tool0
        └── robotiq_base_link
              └── gripper_tcp
```

檢核：

- [ ] 夾爪可正確接到 UR5 flange。
- [ ] `gripper_tcp` 位於兩指中心前方。
- [ ] open / close joint limits 合理。
- [ ] Gazebo 中沒有模型爆開、抖動、穿透。

### 1.3 加入 D435i

新增：

```text
src/d435i_description/
  urdf/d435i.urdf.xacro
  meshes/
```

MVP 建議先採固定式 eye-to-hand，相機架在桌邊；之後再改 eye-in-hand。

固定式 TF：

```text
world
  └── d435i_link
        ├── d435i_color_optical_frame
        └── d435i_depth_optical_frame
```

Gazebo sensor 需輸出：

```text
/camera/color/image_raw
/camera/color/camera_info
/camera/depth/image_raw
/camera/depth/camera_info
/camera/depth/points
```

檢核：

- [ ] RGB image topic 正常。
- [ ] Depth image topic 正常。
- [ ] PointCloud2 topic 正常。
- [ ] optical frame 方向符合 ROS camera convention。

### 1.4 建立 workcell description

新增：

```text
src/ur5_workcell_description/
  urdf/ur5_workcell.urdf.xacro
```

此 package 組合：

- UR5
- Robotiq 2F-85
- D435i
- table
- world/base fixed joints

檢核：

- [ ] 單一 xacro 可產生完整 robot/workcell description。
- [ ] TF tree 沒有斷裂。
- [ ] MoveIt、Gazebo、RViz 使用同一份模型來源。

## 2. Gazebo 模擬環境

新增：

```text
src/ur5_gazebo/
  launch/sim.launch.py
  worlds/table_blocks.world
  config/ros2_controllers.yaml
  models/
```

### 2.1 World

場景包含：

- table
- red block
- green block
- blue block
- optional green ball
- UR5 workcell

物件需有：

- visual
- collision
- inertial
- stable friction/contact parameters

檢核：

- [ ] Gazebo 開啟後桌子與物件位置固定且合理。
- [ ] 方塊可被夾取、推動、堆疊。
- [ ] 物件命名穩定，例如 `red_block_1`。

### 2.2 Gazebo 發布/訂閱介面

Gazebo 發布：

```text
/clock
/joint_states
/tf
/tf_static
/camera/color/image_raw
/camera/color/camera_info
/camera/depth/image_raw
/camera/depth/camera_info
/camera/depth/points
/world_state                      # 由 world_state_manager 發布，不一定由 Gazebo 直接發布
```

Gazebo / controller 接收：

```text
/ur5_arm_controller/joint_trajectory
/ur5_arm_controller/follow_joint_trajectory
/robotiq_gripper_controller/gripper_cmd
```

可能需要的服務：

```text
/spawn_entity
/delete_entity
/reset_simulation
/pause_physics
/unpause_physics
```

檢核：

- [ ] `ros2 topic list` 可看到控制器與 camera topics。
- [ ] `ros2 topic echo /joint_states` 正常。
- [ ] 可用命令送 trajectory 讓手臂移動。
- [ ] 可用命令開關夾爪。

## 3. ros2_control

### 3.1 UR5 controller

必要 controllers：

```text
joint_state_broadcaster
ur5_arm_controller
```

`ur5_arm_controller`：

```text
type: joint_trajectory_controller/JointTrajectoryController
command_interfaces: [position]
state_interfaces: [position, velocity]
joints:
  - shoulder_pan_joint
  - shoulder_lift_joint
  - elbow_joint
  - wrist_1_joint
  - wrist_2_joint
  - wrist_3_joint
```

檢核：

- [ ] `ros2 control list_controllers` 顯示 active。
- [ ] `joint_state_broadcaster` active。
- [ ] `ur5_arm_controller` active。
- [ ] FollowJointTrajectory action server 存在。

### 3.2 Robotiq controller

MVP 可用：

```text
position_controllers/GripperActionController
```

或簡化成：

```text
forward_command_controller/ForwardCommandController
```

檢核：

- [ ] gripper controller active。
- [ ] open/close 動作可在 Gazebo 中觀察。
- [ ] 夾爪位置回饋合理。

## 4. MoveIt2

新增：

```text
src/ur5_moveit_config/
```

必要設定：

- SRDF
- kinematics.yaml
- joint_limits.yaml
- ompl_planning.yaml
- moveit_controllers.yaml
- planning scene monitor
- RViz config

Planning groups：

```text
ur_manipulator
gripper
```

End effector：

```text
name: robotiq_2f85
parent_link: tool0
tcp_link: gripper_tcp
```

MoveIt 需要對接：

```text
/ur5_arm_controller/follow_joint_trajectory
/robotiq_gripper_controller/gripper_cmd
```

檢核：

- [ ] RViz 中可規劃到 named pose。
- [ ] RViz 中 execute 可驅動 Gazebo UR5。
- [ ] planning scene 有 table collision object。
- [ ] 可 add/remove/attach/detach object。
- [ ] Cartesian path 可用於 approach、retreat、push。

## 5. World State 與感知

### 5.1 統一 world state schema

所有 perception backend 都必須輸出相同 schema。

```json
{
  "stamp": "ros_time",
  "frame_id": "world",
  "robot": {
    "holding": null,
    "pose": "optional"
  },
  "objects": [
    {
      "id": "red_block_1",
      "label": "block",
      "color": "red",
      "shape": "cube",
      "pose": {
        "frame_id": "world",
        "position": [0.45, 0.12, 0.76],
        "orientation": [0, 0, 0, 1]
      },
      "size": [0.04, 0.04, 0.04],
      "confidence": 1.0,
      "graspable": true,
      "pushable": true,
      "stackable": true,
      "clear": true,
      "source": "gazebo_ground_truth"
    }
  ],
  "relations": [
    {
      "type": "on_table",
      "object": "red_block_1"
    }
  ]
}
```

檢核：

- [ ] `/world_state` 穩定發布。
- [ ] UI 可顯示物件列表與 pose。
- [ ] LLM prompt generator 可讀取 world state。
- [ ] MoveIt planning scene 可由 world state 更新。

### 5.2 Gazebo ground truth backend

MVP 先做：

```text
Gazebo entity states -> world_state_manager -> /world_state
```

檢核：

- [ ] 三色物件 pose 正確。
- [ ] 物件被移動後 world state 會更新。
- [ ] 可推導 left/right/front/back/on/clear 等 relation。

### 5.3 YOLO + RGBD backend

後續擴充：

```text
RGB image -> YOLO detections
Depth/PointCloud -> 3D pose estimation
Object tracking -> stable object ids
World state builder -> /world_state
Scene descriptor -> /scene_description
```

ROS topics：

```text
/perception/detections_2d
/perception/detected_objects
/world_state
/scene_description
```

檢核：

- [ ] YOLO 可辨識 block/ball。
- [ ] RGBD crop 可估算 3D centroid。
- [ ] table plane removal 可用。
- [ ] Gazebo ground truth 與 YOLO backend 可替換。

### 5.4 Scene description

提供給 LLM prompt 的文字描述：

```text
There are three objects on the table:
- red_block_1 is a red cube, graspable, pushable, stackable, and clear.
- green_ball_1 is a green sphere, pushable but not stackable.
- blue_block_1 is a blue cube, graspable, pushable, stackable, and clear.

Spatial relations:
- red_block_1 is left of green_ball_1.
- blue_block_1 is behind red_block_1.
```

檢核：

- [ ] `/scene_description` 與 `/world_state` 一致。
- [ ] 物件不存在或辨識低信心時會明確描述。

## 6. Skill Library

新增：

```text
src/skill_library/
  config/skills/
    observe_scene.yaml
    pick.yaml
    place.yaml
    push.yaml
    stack.yaml
    verify_relation.yaml
    verify_region.yaml
```

### 6.1 Skill schema

每個 skill 必須包含：

```yaml
skill_id:
description:
category:
parameters:
preconditions:
effects:
motion_requirements:
ros_interfaces:
failure_modes:
recovery_policy:
```

檢核：

- [ ] skill YAML 可被 parser 載入。
- [ ] 每個 skill 有參數型別。
- [ ] 每個 skill 有 preconditions/effects。
- [ ] skill registry 可輸出給 prompt generator。

### 6.2 MVP skills

必要 skills：

```text
observe_scene()
move_home()
open_gripper()
close_gripper()
pick(object)
place(object, target)
push(object, direction, distance)
stack(top_object, bottom_object)
verify_relation(relation, object_a, object_b)
verify_region(object, region)
```

檢核：

- [ ] `pick(red_block_1)` 可成功 attach object。
- [ ] `place(red_block_1, left_region)` 可成功 detach object。
- [ ] `stack(red_block_1, green_block_1)` 可成功完成 on relation。
- [ ] `push(green_ball_1, forward, 0.15)` 可成功位移。

## 7. TAMP / LLM Planner

### 7.1 LLM Provider

LLM 節點只負責：

- 理解自然語言
- 選擇合法 skill
- 排列 skill sequence
- 產生 JSON plan

LLM 不負責：

- joint trajectory
- gripper raw command
- 發明不存在 skill
- 直接執行 ROS action

OpenAI interface 用於快速概念驗證：

```text
POST https://api.openai.com/v1/responses
model: gpt-5.2
```

Ollama interface 用於未來本地端部署：

```text
POST http://localhost:11434/api/generate
model: qwen3.5:27b-q4_K_M
```

檢核：

- [ ] OpenAI API key 可用於快速 PoC。
- [ ] Ollama server 本地可用。
- [ ] Qwen model 可回應。
- [ ] planner 可設定 timeout。
- [ ] LLM output 可被 JSON parser 解析。

### 7.2 Prompt generator

Prompt 必須包含：

```text
Robot capabilities
Available skills
Skill schemas
Current world state
Scene description
Object ontology
Task rules
Output JSON schema
User command
```

檢核：

- [ ] prompt 中只列出目前可用 skills。
- [ ] prompt 中包含最新 world state。
- [ ] prompt 明確要求 output only JSON。
- [ ] prompt 明確禁止 invented skills/objects。

### 7.3 LLM output schema

標準輸出：

```json
{
  "task_id": "task_001",
  "user_command": "把紅色疊到綠色上面",
  "goal": {
    "type": "relation",
    "relation": "on",
    "object_a": "red_block_1",
    "object_b": "green_block_1"
  },
  "plan": [
    {
      "step": 1,
      "skill": "pick",
      "args": {
        "object": "red_block_1"
      }
    },
    {
      "step": 2,
      "skill": "place",
      "args": {
        "object": "red_block_1",
        "target": {
          "type": "on_top_of",
          "reference_object": "green_block_1"
        }
      }
    },
    {
      "step": 3,
      "skill": "verify_relation",
      "args": {
        "relation": "on",
        "object_a": "red_block_1",
        "object_b": "green_block_1"
      }
    }
  ]
}
```

檢核：

- [ ] 所有 plan step 有連續 step number。
- [ ] 所有 skill 存在於 skill registry。
- [ ] 所有 args 符合 skill schema。
- [ ] goal 可轉成 validator 可檢查的條件。

### 7.4 Plan validator

檢查：

- JSON syntax
- skill existence
- argument schema
- object existence
- preconditions
- ontology/task rules
- target region validity
- MoveIt reachability
- collision feasibility

檢核：

- [ ] 不合法 skill 被拒絕。
- [ ] 不存在物件被拒絕或要求澄清。
- [ ] 球類 stack 被拒絕。
- [ ] 抓取不可達物件被拒絕。
- [ ] validator 會產生清楚 error code。

## 8. Task Executor

新增：

```text
src/task_executor/
```

負責：

- 接收 validated plan
- 逐步執行 skill
- 每步前後更新 world state
- 發布執行狀態
- 失敗 recovery 或中止

ROS 介面建議：

```text
/task_executor/execute_plan        # action 或 service
/task_executor/cancel              # service
/task_executor/status              # topic
/task_executor/events              # topic
```

狀態：

```text
IDLE
PLANNING
VALIDATING
EXECUTING
PAUSED
FAILED
SUCCEEDED
CANCELED
```

檢核：

- [ ] 可逐步執行 plan。
- [ ] UI 可看到目前 step。
- [ ] 執行失敗時停止後續 step。
- [ ] 每步執行後重新讀取 world state。
- [ ] 支援 cancel/stop。

## 9. Whisper STT

新增：

```text
src/voice_interface/
```

MVP 流程：

```text
Web UI 錄音 -> backend upload audio -> faster-whisper -> text -> planner
```

API：

```text
POST /api/stt
```

檢核：

- [ ] 本地端 Whisper/faster-whisper 可轉中文語音。
- [ ] UI 可錄音並上傳。
- [ ] STT 結果可手動修正後送出。
- [ ] 不依賴雲端服務。

## 10. Web UI

新增：

```text
src/web_backend/
src/web_frontend/
```

建議：

- Frontend：React + Vite + TypeScript
- Backend：FastAPI
- ROS integration：backend 內用 rclpy，或獨立 ros_api_server
- Realtime：WebSocket

### 10.1 UI 主要區塊

第一版操作台：

```text
左側：文字/語音指令
中間：LLM plan / validation / execution progress
右側：world state / object list / relations
下方：ROS、MoveIt、Gazebo log
```

必要功能：

- 文字指令輸入
- 錄音按鈕
- STT 結果顯示與編輯
- Generate Plan
- Validate Plan
- Execute
- Stop / Cancel
- Retry
- JSON plan inspector
- world state viewer
- camera stream viewer
- execution event log

### 10.2 Backend API

```text
GET  /api/health
GET  /api/world_state
GET  /api/scene_description
GET  /api/skills
POST /api/stt
POST /api/plan
POST /api/validate
POST /api/execute
POST /api/cancel
WS   /ws/events
```

檢核：

- [ ] UI 可直接操作完整任務流程。
- [ ] UI 顯示 LLM 原始 JSON。
- [ ] UI 顯示 validator 結果。
- [ ] UI 顯示每個 skill 的執行狀態。
- [ ] UI 顯示目前物件位置與 relation。

## 11. 任務測試集

### 11.1 基本任務

- [ ] 「把紅方塊拿到左邊」
- [ ] 「把藍方塊拿到右邊」
- [ ] 「把紅色疊到綠色上面」
- [ ] 「把綠球往前推」

### 11.2 複合任務

- [ ] 「先把紅色疊到綠色上面，再把藍色放到右邊」
- [ ] 「把三個方塊排成紅綠藍」
- [ ] 「把紅方塊移到綠方塊左邊」

### 11.3 錯誤與澄清任務

- [ ] 「把方塊拿過去」應要求澄清。
- [ ] 「把不存在的黃色方塊拿起來」應拒絕。
- [ ] 「把綠球疊到紅方塊上」應拒絕或要求改任務。
- [ ] MoveIt 規劃失敗時應回報 failure reason。

每個測試記錄：

```text
command
world_state
prompt
LLM output
validator result
execution result
final world_state
pass/fail
notes
```

## 12. 開發里程碑

### M1：UR5 Gazebo 啟動

完成條件：

- [x] 新增 `ur5_gazebo` package、Gazebo world、controller YAML、bringup launch。
- [x] UR5 xacro 可切換 `gazebo_ros2_control/GazeboSystem`。
- [x] `colcon build --symlink-install` 成功。
- [x] xacro 可展開含 Gazebo ros2_control plugin 的 URDF。
- [ ] 安裝 Gazebo/ros2_control 系統套件。
- [ ] UR5 spawn 到 Gazebo。
- [ ] `joint_states` 正常。
- [ ] TF 正常。
- [ ] controller active。
- [ ] 可送 trajectory 移動 UR5。

### M2：Robotiq 夾爪整合

完成條件：

- [x] clone PickNik `ros2_robotiq_gripper` 作為初始參考。
- [x] 初期參考 `robotiq_description`，最終改為內建 IFRA 2F-85 mesh/xacro，避免 repo 依賴不必要外部 package。
- [x] 參考 IFRA `ros2_SimRealRobotControl`，改用 IFRA 2F-85 mesh/xacro 接到 UR5 `tool0`。
- [x] 新增 `gripper_tcp`。
- [x] 新增 `robotiq_gripper_controller` 設定。
- [x] 參考 IFRA SRDF 夾爪姿態，改用六關節同步 trajectory controller，命令向量為 `[1, 1, 1, 1, -1, -1]`。
- [x] Gazebo 中看得到 2F-85。
- [x] gripper controller active。
- [x] open/close 正常。
- [x] 文件化 Gazebo mimic/passive joint 失敗原因與解法：`docs/m2_robotiq_2f85_gazebo_notes.md`。

### M3：桌面與物件

完成條件：

- [x] table + 三色方塊 + 球可 spawn。
- [ ] 物理穩定。
- [x] ground truth world state 查詢工具：`ros2 run ur5_gazebo print_world_state.py`。
- [x] 文件化 M3 場景與 world-state schema：`docs/m3_tabletop_objects_world_state.md`。
- [x] 新增 Gazebo 專用 sim grasp adapter，可 attach/detach 物件到 `gripper_tcp`。

### M4：MoveIt2 控制 Gazebo

完成條件：

- [x] 新增 `ur5_moveit_config` package。
- [x] `move_group` 可載入 UR5 + 2F-85 robot model。
- [x] MoveIt controller mapping 指到 `/ur5_arm_controller/follow_joint_trajectory`。
- [ ] RViz 規劃成功。
- [ ] execute 可驅動 Gazebo。
- [ ] planning scene 有 table/object。
- [x] 文件化 MoveIt2/RViz 啟動與操作：`docs/m4_moveit2_rviz_control.md`。

### M5：Skill executor MVP

完成條件：

- [x] 新增 `skill_library` package 與固定 YAML skill registry。
- [x] 新增 `task_executor` package 與 JSON plan validator/executor CLI。
- [x] `observe_scene`
- [x] `move_ready`
- [x] `open_gripper`
- [x] `close_gripper`
- [x] `attach_object`
- [x] `detach_object`
- [x] `move_above_object`：讀 Gazebo object pose，呼叫 MoveIt `/move_action` 到物件上方。
- [x] `move_to_object`：分段下探到物件附近。
- [x] `lift`：相對目前 TCP 往上抬升。
- [x] `move_to_region`：移動到命名桌面區域，支援 left/center/right/front。
- [x] `pick` MVP：自動 open、move_above、move_to、close、attach、lift。
- [x] `place` MVP：假設 TCP 已在放置點，執行 detach/open。
- [x] `stack` MVP shortcut：保留為 debug/smoke test，但 LLM 預設不使用。
- [x] atomic stack plan example：用 open/move/approach/close/lift/move/approach/open/verify 組合完成堆疊。
- [ ] `push`
- [x] verify skills：`verify_relation`、`verify_region` 初版。
- [x] 文件化 M5：`docs/m5_skill_executor_mvp.md`。
- [x] 文件化 MoveIt pose-goal、RViz marker IK branch、seeded IK + joint-space OMPL、Cartesian approach/retreat 的差異與處理方式：`docs/m5_motion_planning_notes.md`。
- [x] 文件化 M6 atomic planning prompt 初版：`docs/m6_llm_atomic_planning_prompt.md`。

### M6：LLM plan

完成條件：

- [ ] OpenAI API 可產生合法 JSON plan。
- [ ] Ollama Qwen 可用於本地部署測試。
- [x] prompt generator 可用：`ros2 run task_executor generate_skill_plan.py "<command>" --dry-run`。
- [ ] LLM 產生 JSON plan：`generate_skill_plan.py "<command>" --output /tmp/plan.json`。
- [x] validator 可拒絕不合法 plan：預設拒絕 composite skill，檢查 required args/type/enum。
- [x] 文件化 M6 CLI：`docs/m6_local_llm_planner.md`。

### M7：Web UI MVP

完成條件：

- [x] 文字輸入任務。
- [x] 顯示 world state。
- [x] 顯示/驗證/執行 plan。
- [x] 顯示任務狀態與 log。
- [x] 文件化 M7 Web UI：`docs/m7_web_ui_mvp.md`。

### M8：Whisper STT

完成條件：

- [x] 網頁錄音。
- [x] 本地 Whisper 轉文字。
- [x] 可送入 planner。

### M9：D435i + YOLO/RGBD 感知

完成條件：

- [ ] RGBD topics 正常。
- [ ] YOLO detection 正常。
- [ ] 3D pose estimation 正常。
- [ ] 可替代 ground truth backend。

### M10：Sim-to-real 準備

完成條件：

- [ ] UR driver interface 抽象。
- [ ] Robotiq driver interface 抽象。
- [ ] RealSense ROS wrapper interface 抽象。
- [ ] hand-eye / camera-base calibration 流程文件化。
- [ ] speed、workspace、E-stop safety rules 定義。

## 13. 每次開發檢核流程

每次完成一個功能後執行：

```text
1. colcon build
2. source install/setup.bash
3. ros2 launch ur5_gazebo sim.launch.py
4. ros2 control list_controllers
5. ros2 topic list
6. ros2 topic echo /world_state
7. MoveIt plan + execute smoke test
8. UI smoke test
9. 任務測試集至少跑一個 pass case、一個 fail case
```

檢核紀錄建議放在：

```text
docs/test_runs/YYYY-MM-DD.md
```

## 14. 風險與決策紀錄

### Gazebo Classic vs modern Gazebo

ROS2 Humble 可先用 Gazebo Classic + `gazebo_ros2_control` 做 MVP，但 Gazebo Classic 已 EOL。若專案要長期維護，後續應規劃 modern Gazebo + `gz_ros2_control` 遷移。

決策：

- [ ] MVP 使用 Gazebo Classic。
- [ ] 穩定後評估 modern Gazebo 遷移。

### Ground truth vs YOLO

開發初期使用 Gazebo ground truth 加速 TAMP/MoveIt/UI 整合。感知介面統一後再加入 YOLO + RGBD backend。

決策：

- [ ] M3-M8 使用 ground truth backend。
- [ ] M9 加入 YOLO/RGBD backend。

### LLM 可靠性

LLM 只能產生 skill plan，不可直接執行機器人控制。所有輸出必須通過 validator。

決策：

- [ ] 所有 LLM output 只允許 JSON。
- [ ] 所有 plan 必須 validate 後才能 execute。
