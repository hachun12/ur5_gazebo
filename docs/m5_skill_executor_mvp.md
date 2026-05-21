# M5 Skill Executor MVP

本文件記錄第一版 skill layer。目標是讓後續 LLM/TAMP 只輸出結構化 skill plan，不直接輸出 ROS topic、action 或 joint command。

## Packages

新增兩個 package：

```text
src/skill_library/
  config/skills/*.yaml

src/task_executor/
  scripts/execute_skill_plan.py
  examples/*.json
```

`skill_library` 是 registry。每個 skill YAML 固定包含：

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

`task_executor` 目前提供 CLI executor：

```bash
ros2 run task_executor execute_skill_plan.py <plan.json>
ros2 run task_executor execute_skill_plan.py <plan.json> --validate-only
```

## MVP Skill Support

目前可執行：

```text
observe_scene()
move_ready()
open_gripper()
close_gripper()
attach_object(object)
detach_object()
pick(object)
place(object, target?)
verify_relation(relation, object_a, object_b)
verify_region(object, region)
```

已註冊但尚未實作自動運動：

```text
push(object, direction, distance)
stack(top_object, bottom_object)
```

## Important MVP Assumption

目前 `pick(object)` 已經會自動呼叫 MoveIt pose-goal 做分段接近，但仍是 MVP。

`pick(object)` 流程：

```text
open_gripper
move_above_object(object, z_offset=0.16)
move_to_object(object, z_offset=0.035)
close_gripper(position=0.70)
attach_object(object)
lift(height=0.15)
```

`move_above_object` 目前採用 seeded IK + joint-space OMPL：先用目前 `/joint_states` 當 IK seed 求 `gripper_tcp` 目標 pose 的 IK 解，再將這組明確 joint goal 交給 MoveIt `/move_action` 規劃。這保留避障規劃能力，同時避免純 pose-goal sampler 抽到 wrist flip / elbow branch 的怪解。

`move_to_object` 與 `lift` 則透過 `/compute_cartesian_path` 產生直線段，再用 `/execute_trajectory` 執行。這樣接近物件與抬升時不讓 OMPL 自由繞路。

為了保守，executor 會保留目前 `gripper_tcp` 姿態，只改 TCP 位置。這避免第一版就硬編一個可能與 URDF TCP 軸向不一致的 grasp quaternion。

注意：物件在手指中間時，不應命令 Robotiq trajectory controller 全閉到 `0.8`。Gazebo 中手指接觸方塊後 joint 無法到達全閉目標，`joint_trajectory_controller` 會回報 `PATH_TOLERANCE_VIOLATED`。MVP pick 目前使用 `position=0.70` 作為抓取閉合量。

`place(...)` 目前仍是假設使用者已透過 RViz/MoveIt 或未來的 pose skill 將已附著物件移到目標上方：

```text
detach_object
open_gripper
```

下一步會加入 `move_to_region(region)` 與 stack 專用的 `move_above_object_for_stack(top_object, bottom_object)`，把 place/stack 也自動化。

## Example

Terminal 1：啟動 Gazebo。

```bash
cd ~/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch ur5_gazebo sim.launch.py
```

Terminal 2：啟動 MoveIt/RViz 或只啟動 MoveIt。Executor 會呼叫 MoveIt 的 Cartesian path 與 trajectory execution 介面。

```bash
cd ~/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch ur5_moveit_config moveit_rviz.launch.py
```

Terminal 3：執行 plan。

```bash
cd ~/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 run task_executor execute_skill_plan.py \
  install/task_executor/share/task_executor/examples/auto_pick_blue_mvp.json
```

只驗證 JSON 與 skill schema：

```bash
ros2 run task_executor execute_skill_plan.py \
  install/task_executor/share/task_executor/examples/auto_pick_blue_mvp.json \
  --validate-only
```

## Plan JSON Schema

第一版 plan 至少需要：

```json
{
  "task_id": "manual_pick_blue_mvp",
  "user_command": "pick blue block from current gripper pose",
  "plan": [
    {
      "step": 1,
      "skill": "open_gripper",
      "args": {}
    },
    {
      "step": 2,
      "skill": "pick",
      "args": {
        "object": "blue_block"
      }
    }
  ]
}
```

Validator 會檢查：

- `plan` 必須是 list。
- `step` 必須從 1 連續遞增。
- `skill` 必須存在於 `skill_library/config/skills`。
- 必填 args 必須存在。
- arg type 與 enum 必須符合 YAML schema。

## Next Step

已新增 seeded IK transit skill：

```text
move_above_object(object, z_offset)
move_to_region(region, tcp_z)
```

已新增 Cartesian segment skills：

```text
move_to_object(object)
lift(height)
```

下一步應新增：

```text
move_above_object_for_stack(top_object, bottom_object)
```

## Named Regions

目前 `move_to_region(region, tcp_z)` 先使用固定桌面區域：

```text
left_region:   x=0.35, y= 0.22
center_region: x=0.35, y= 0.00
right_region:  x=0.35, y=-0.22
front_region:  x=0.50, y= 0.00
```

`tcp_z` 預設是 `0.09`。這個值和目前抓取時 object-to-TCP offset 有關，若放置高度不準，可以在 JSON plan 裡調整。

範例：

```bash
ros2 run task_executor execute_skill_plan.py \
  install/task_executor/share/task_executor/examples/auto_pick_place_blue_left_mvp.json
```
