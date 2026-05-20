# M1 Gazebo Bringup

本文件記錄目前第一階段 UR5 Gazebo + ros2_control bringup 的安裝、啟動與驗收方式。

## 目前已完成

- 新增 `ur5_gazebo` package。
- 新增 Gazebo world：`empty_workcell.world`。
- 新增 controller 設定：`ros2_controllers.yaml`。
- 新增 Gazebo launch：`sim.launch.py`。
- 修改 UR5 xacro，可用參數切換 ros2_control hardware plugin。
- 新增簡單 trajectory 測試節點：`send_ready_trajectory.py`。

## 需要的系統套件

目前這台環境缺 Gazebo/ros2_control 相關 ROS 套件。請在本機 terminal 執行：

```bash
sudo apt-get update
sudo apt-get install -y \
  ros-humble-gazebo-ros-pkgs \
  ros-humble-gazebo-ros2-control \
  ros-humble-ros2-control \
  ros-humble-ros2-controllers \
  ros-humble-joint-trajectory-controller \
  ros-humble-joint-state-broadcaster
```

確認：

```bash
source /opt/ros/humble/setup.bash
ros2 pkg prefix gazebo_ros
ros2 pkg prefix gazebo_ros2_control
ros2 pkg prefix controller_manager
ros2 pkg prefix joint_trajectory_controller
```

## Build

```bash
cd /home/r2-public-pc/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

## 啟動模擬

```bash
ros2 launch ur5_gazebo sim.launch.py
```

預期會啟動：

- Gazebo
- `robot_state_publisher`
- `spawn_entity.py`
- `joint_state_broadcaster`
- `ur5_arm_controller`

## 控制器檢查

```bash
ros2 control list_controllers
```

預期：

```text
joint_state_broadcaster active
ur5_arm_controller active
```

檢查 action server：

```bash
ros2 action list | grep follow_joint_trajectory
```

預期：

```text
/ur5_arm_controller/follow_joint_trajectory
```

## Gazebo 中看不到 UR5 時

如果左側 model list 有 `ur5`，但右側畫面看不到模型，先確認 Gazebo entity 位置：

```bash
ros2 service call /gazebo/get_entity_state gazebo_msgs/srv/GetEntityState "{name: ur5, reference_frame: world}"
```

預期位置大約是：

```text
x: 0.0
y: 0.0
z: 0.0
```

也可以在 Gazebo 左側 model list 對 `ur5` 按右鍵，選擇 move to / follow 類似功能，讓視角移到模型附近。

目前 launch 會把 UR5 base 固定到 world，桌子放在 UR5 前方，world 也設定了預設 camera 與光源，方便肉眼確認。

如果 UR5 啟動後像被推走一樣沿著 x 方向快速消失，代表 base 沒有固定到 Gazebo world，或一開始與桌子/地面嚴重碰撞。目前 Gazebo launch 會傳入 `use_fixed_world_joint:=true`，在 URDF 中新增 `world-base_link` fixed joint，避免整台手臂被物理引擎推走。

## 若卡在 controller_manager/load_controller

如果看到類似訊息：

```text
Could not contact service /controller_manager/load_controller
waiting for service /controller_manager/load_controller to become available...
```

代表 controller spawner 找不到 Gazebo 裡由 `gazebo_ros2_control` 建立的 `/controller_manager`。請先檢查：

```bash
ros2 node list | grep controller
ros2 service list | grep controller_manager
ros2 topic echo /clock --once
```

如果 `/clock` 有資料，但沒有 `/controller_manager`，通常是 Gazebo model 內的 ros2_control plugin 沒載入成功。請回頭看啟動 terminal 中 Gazebo 的錯誤，常見原因：

- `gazebo_ros2_control` 套件未安裝或沒有 source 到。
- `libgazebo_ros2_control.so` 找不到。
- controller YAML 路徑錯誤。
- URDF 的 `<ros2_control>` joint/interface 與 controller YAML joint name 不一致。
- robot entity 沒有成功 spawn 到 Gazebo。
- Gazebo world 重複載入 `gazebo_ros_init` / `gazebo_ros_factory` 為錯誤 plugin type。
- Gazebo 找不到 UR5 mesh，例如 `model://ur5_description/meshes/...`。launch 需要設定 `GAZEBO_MODEL_PATH` 指到 `ur5_description` 的 share parent。

目前 launch 已使用 `controller_manager spawner`，並等待 `/controller_manager` 最多 120 秒。如果仍然等待，重點就不是 spawner 太早，而是 Gazebo plugin 沒有成功起來。

## 測試手臂移動

另開一個 terminal：

```bash
cd /home/r2-public-pc/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run ur5_gazebo send_ready_trajectory.py
```

預期 UR5 會先小幅移動到 visible test pose，再回到 ready-like pose：

```text
visible test pose:
shoulder_pan_joint: 0.35
shoulder_lift_joint: -1.35
elbow_joint: 1.25
wrist_1_joint: -1.45
wrist_2_joint: -pi/2
wrist_3_joint: 0.25
```

最後回到 ready-like pose：

```text
shoulder_pan_joint: 0.0
shoulder_lift_joint: -pi/2
elbow_joint: pi/2
wrist_1_joint: -pi/2
wrist_2_joint: -pi/2
wrist_3_joint: 0.0
```

Gazebo 初始 joint state 也設定成同一組 ready-like pose，避免 UR5 以全零關節角啟動時呈現怪異姿態。

## M1 完成條件

- [ ] `colcon build --symlink-install` 成功。
- [ ] `ros2 launch ur5_gazebo sim.launch.py` 成功。
- [ ] Gazebo 中看得到 UR5 與工作桌。
- [ ] `joint_state_broadcaster` active。
- [ ] `ur5_arm_controller` active。
- [ ] `/joint_states` 正常發布。
- [ ] `/ur5_arm_controller/follow_joint_trajectory` 存在。
- [ ] `ros2 run ur5_gazebo send_ready_trajectory.py` 可移動 UR5。

## 已知限制

- 目前只有 UR5 與桌子，尚未加入 Robotiq 2F-85。
- 已完成 M2，Gazebo launch 會載入本專案內建的 IFRA 2F-85 mesh。
- 目前尚未加入 D435i。
- 目前尚未加入桌面三色物件。
- 此階段只驗證 Gazebo + ros2_control 控制閉環，不包含 MoveIt2。
