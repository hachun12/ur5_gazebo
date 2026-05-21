# M4 MoveIt2 RViz Control

本文件記錄目前 UR5 Gazebo + MoveIt2 + RViz2 的啟動與操作方式。

## 目前範圍

已新增 `ur5_moveit_config` package，內容包含：

- MoveIt SRDF：`config/ur5.srdf`
- KDL kinematics：`config/kinematics.yaml`
- OMPL planning：`config/ompl_planning.yaml`
- MoveIt controller mapping：`config/moveit_controllers.yaml`
- RViz launch：`launch/moveit_rviz.launch.py`

MoveIt planning group：

```text
ur_manipulator
```

Planning chain：

```text
base_link -> gripper_tcp
```

目前 MoveIt 只控制 UR5 六軸：

```text
shoulder_pan_joint
shoulder_lift_joint
elbow_joint
wrist_1_joint
wrist_2_joint
wrist_3_joint
```

Robotiq 2F-85 仍由 Gazebo gripper controller / adapter 控制，不放進 MoveIt arm planning group。

## 啟動順序

Terminal 1：啟動 Gazebo + ros2_control。

```bash
cd /home/r2-public-pc/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch ur5_gazebo sim.launch.py
```

如果目前的遠端桌面或顯示環境無法建立 OpenGL/GLX context，先用 headless Gazebo：

```bash
ros2 launch ur5_gazebo sim.launch.py gui:=false
```

若仍有 GLX 問題，改用 Mesa software rendering：

```bash
ros2 launch ur5_gazebo sim.launch.py gui:=false software_rendering:=true
```

確認 controller active：

```bash
ros2 control list_controllers
```

預期：

```text
joint_state_broadcaster    active
ur5_arm_controller         active
robotiq_gripper_controller active
```

Terminal 2：啟動 MoveIt2 + RViz2。

```bash
cd /home/r2-public-pc/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch ur5_moveit_config moveit_rviz.launch.py
```

如果 RViz 顯示 `Failed to create an OpenGL context`，先試：

```bash
ros2 launch ur5_moveit_config moveit_rviz.launch.py software_rendering:=true
```

如果只是要啟動 `move_group` 測試，不開 RViz：

```bash
ros2 launch ur5_moveit_config moveit_rviz.launch.py launch_rviz:=false
```

如果只想測 `move_group`，不開 RViz：

```bash
ros2 launch ur5_moveit_config moveit_rviz.launch.py launch_rviz:=false
```

## 在 RViz 中移動手臂

1. 左側 MotionPlanning panel 中，確認 Planning Group 是 `ur_manipulator`。
2. 如果沒有看到互動 marker，可在 MotionPlanning panel 的 Planning Request 區塊確認 `Query Goal State` 已啟用。
3. 拖曳橘色 goal marker 到目標姿態。
4. 點 `Plan`。
5. 軌跡看起來正常後點 `Execute`。

MoveIt 會透過：

```text
/ur5_arm_controller/follow_joint_trajectory
```

把軌跡送到 Gazebo 中的 UR5。

## Gripper 與物件

夾爪目前不透過 MoveIt 控制。測試夾爪：

```bash
ros2 run ur5_gazebo send_gripper_open_close.py
```

測試 sim attach/detach：

```bash
ros2 run ur5_gazebo grasp_target.py attach red_block
ros2 run ur5_gazebo grasp_target.py detach
```

後續 skill executor 會把這些低階動作包成：

```text
move_tcp(...)
set_gripper(width)
attach_object(object_id)
detach_object()
```

## 已驗證

在此環境中已驗證：

```bash
colcon build --symlink-install --packages-select ur5_moveit_config
check_urdf /tmp/ur5_moveit_test.urdf
ros2 launch ur5_moveit_config moveit_rviz.launch.py launch_rviz:=false
```

`move_group` 成功載入 robot model、OMPL、KDL、MoveIt simple controller manager，並找到 `ur5_arm_controller`。

## 注意事項

- MoveIt 啟動時可能顯示 `No 3D sensor plugin(s) defined for octomap updates`，目前可忽略，D435i perception 尚未接入。
- `EE_robotiq_2f85` 是一個 tiny visual link，沒有 collision geometry，MoveIt 會警告但不影響 arm planning。
- 如果 RViz 裡 plan 成功但 execute 沒反應，先確認 Gazebo 的 `ur5_arm_controller` 是 active。
- 如果 start state 報錯，先等 `/joint_states` 穩定發布，再按 RViz 的 current/start state 更新。
