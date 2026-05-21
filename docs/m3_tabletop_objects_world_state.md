# M3 Tabletop Objects And World State

本文件記錄目前 Gazebo 桌面物件場景與 ground-truth world state 查詢方式。這是後續 YOLO + D435i perception、TAMP world model、skill executor 的基準版本。

## 目前場景

`src/ur5_gazebo/worlds/empty_workcell.world` 內已包含：

- `work_table`
- `red_block`
- `green_block`
- `blue_block`
- `green_ball`

桌面高度為 `z = 0.0`。UR5 base 固定在 world 原點，物件放在手臂前方桌面上。

## 物件初始狀態

| name | type | color | size/radius | initial pose |
| --- | --- | --- | --- | --- |
| `red_block` | block | red | `0.05 x 0.05 x 0.05 m` | `x=0.35, y=-0.12, z=0.025` |
| `green_block` | block | green | `0.05 x 0.05 x 0.05 m` | `x=0.35, y=0.00, z=0.025` |
| `blue_block` | block | blue | `0.05 x 0.05 x 0.05 m` | `x=0.35, y=0.12, z=0.025` |
| `green_ball` | sphere | green | `r=0.03 m` | `x=0.48, y=0.00, z=0.03` |

方塊質量目前為 `0.08 kg`，球為 `0.04 kg`。這些值是為了先讓桌面互動穩定，之後可依實際物件修改。

## Ground-Truth World State

World file 會載入 `libgazebo_ros_state.so`，並在 `/gazebo` namespace 提供 entity state service：

```bash
ros2 service list | grep get_entity_state
```

預期可看到：

```text
/gazebo/get_entity_state
```

啟動 Gazebo 後可查詢目前物件狀態：

```bash
cd /home/r2-public-pc/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run ur5_gazebo print_world_state.py
```

輸出格式：

```json
{
  "frame_id": "world",
  "source": "gazebo_ground_truth",
  "objects": {
    "red_block": {
      "type": "block",
      "color": "red",
      "size": [0.05, 0.05, 0.05],
      "frame_id": "world",
      "pose": {
        "position": {"x": 0.35, "y": -0.12, "z": 0.025},
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
      },
      "twist": {
        "linear": {"x": 0.0, "y": 0.0, "z": 0.0},
        "angular": {"x": 0.0, "y": 0.0, "z": 0.0}
      }
    }
  }
}
```

這個 JSON schema 之後應該成為 TAMP 和 UI 使用的穩定 world-state interface。來源可以先是 Gazebo ground truth，之後換成：

- YOLO color/object detector
- D435i depth pose estimation
- AprilTag/ArUco calibration
- Gazebo ground truth fallback

## 為什麼先做 Ground Truth

目前任務規劃重點是先把 skill execution pipeline 跑通。若一開始就把 perception noise、相機遮擋、物件追蹤一起混入，會很難判斷錯誤來源。

建議順序：

1. Gazebo ground truth 驗證 `pick/place/stack/push` skill。
2. 加入簡化 perception，輸出同一份 world-state schema。
3. 用 perception state 取代 ground truth。
4. 保留 ground truth 作為 regression test 和 debug 對照。

## 下一步

目前物件只是可互動 collision model，還沒有「穩定抓取」機制。下一步建議做：

- `gripper_adapter`：對外只暴露 `open/close/set_width`。
- `grasp_detector`：根據 gripper width、finger contact、object pose 判斷是否 grasped。
- `attach/detach`：在 sim 中固定被抓物體，避免純摩擦抓取不穩。
- `world_state_publisher`：定期 publish 同一份 object state，而不是只用 CLI 查詢。

純 Gazebo Classic friction grasp 可以測，但對小方塊容易滑、彈、穿透。TAMP 驗證階段建議用 attach/detach 讓語意結果穩定，之後再逐步提高物理真實度。

## Sim Grasp Adapter

目前已新增 `sim_grasp_adapter.py`。它不是實機控制方式，而是 Gazebo 專用的穩定抓取 adapter。

實作方式：

1. 透過 TF 讀取 `world -> gripper_tcp`。
2. attach 時讀取目標物件當下的 world pose。
3. 記錄 `object_in_tcp` 相對位姿。
4. attach 後定期呼叫 `/gazebo/set_entity_state`，讓物件跟隨 `gripper_tcp`。
5. detach 後停止更新物件 pose。

launch Gazebo 後，可用 service 呼叫：

```bash
ros2 service call /sim_grasp_adapter/attach_target std_srvs/srv/Trigger {}
ros2 service call /sim_grasp_adapter/detach std_srvs/srv/Trigger {}
```

預設目標是 `red_block`。也可以用 CLI 包裝腳本：

```bash
ros2 run ur5_gazebo grasp_target.py attach red_block
ros2 run ur5_gazebo grasp_target.py attach green_block
ros2 run ur5_gazebo grasp_target.py detach
```

若物件距離 `gripper_tcp` 超過 `attach_distance`，adapter 會拒絕 attach。預設距離是 `0.16 m`，可用參數調整：

```bash
ros2 param set /sim_grasp_adapter attach_distance 0.20
```

這個 adapter 的目標是讓 `pick/place/stack/push` 的語意流程先穩定，不代表真實 Robotiq 2F-85 的力學模型。實機部署時應改由 Robotiq driver 的 object detection/current/position state 產生 grasp state。
