# M2 Robotiq 2F-85 Gazebo Notes

本文件記錄 UR5 + Robotiq 2F-85 在 ROS 2 Humble、Gazebo Classic、`gazebo_ros2_control` 中的整合經驗。重點是說明第一版夾爪 URDF 為什麼會在 Gazebo 失敗，以及後續如何避開 mimic joint/passive joint 問題。

## 目前可用狀態

- Gazebo 可以載入 UR5 + Robotiq 2F-85。
- `/controller_manager` 可以正常啟動。
- controller 狀態應包含：

```text
joint_state_broadcaster    joint_state_broadcaster/JointStateBroadcaster          active
ur5_arm_controller         joint_trajectory_controller/JointTrajectoryController  active
robotiq_gripper_controller joint_trajectory_controller/JointTrajectoryController  active
```

- 測試腳本：

```bash
cd /home/r2-public-pc/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run ur5_gazebo send_gripper_open_close.py
```

預期順序為 open `0.0`、close `0.8`、open `0.0`。

## 第一版為什麼失敗

第一版使用 PickNik `ros2_robotiq_gripper` 的 2F-85 description 直接接進 Gazebo。這份 description 適合做 ROS/MoveIt 描述基礎，但在 Gazebo Classic 裡直接用 mimic joint 表達 2F-85 的四連桿閉合機構時，會遇到幾個問題。

### 1. Gazebo Classic 不會自然模擬 URDF mimic 約束

URDF 的 `<mimic joint="..." multiplier="..." offset="..."/>` 主要是 kinematic description。`robot_state_publisher` 和部分 planning tool 會理解 mimic 關係，但 Gazebo Classic 的物理引擎不會自動把 mimic 當成剛性的機械耦合約束來解。

結果是：

- 主動關節會照 controller 指令動。
- mimic/passive 關節若沒有被 Gazebo constraint、plugin 或 controller 實際約束，就可能只是一組自由或半自由的物理關節。
- 夾爪指節在重力、碰撞、數值誤差下會漂移、抖動、分離，甚至整個爪體掉落。

### 2. ros2_control 只控制列入 `<ros2_control>` 的 joint

如果 controller 只控制一個主關節，而其他 mimic/passive joints 沒有被硬體介面或 Gazebo plugin 同步，Gazebo 端不會自動把它們帶到正確位置。

典型症狀：

- RViz/TF 看起來可能合理，Gazebo 物理卻分解。
- 開合時只有一側動作接近正確，另一側 passive link 飄掉。
- 沒有動力的連桿在半空中搖晃或受重力落下。

### 3. 自製 mimic plugin 容易只修到位置，沒有修好物理閉鏈

曾嘗試用自製 Gazebo plugin 同步 mimic joint position。這可以讓某些關節看起來跟著主關節走，但 2F-85 是近似四連桿閉鏈機構，不只是單純把多個 joint position 設成同一個值。

如果 plugin 沒有完整處理：

- 關節方向與倍率。
- effort/constraint 穩定性。
- fixed joint preserve。
- collision 導致的反力。
- controller command 與 joint limit。

就容易變成「馬達在動，但被動連桿仍被物理引擎拉開」。

### 4. 錯誤的 joint command sign 會直接造成 abort

改用 IFRA 2F-85 macro 後，曾沿用 IFRA `joint_specifications.yaml` 的 `JointsVector: [1.0, -1.0, 1.0, 1.0, -1.0, 1.0]`。但目前專案中的 IFRA URDF 版本已把 active joints 改成 `revolute` 並加上 joint limit，實際可接受的閉合方向要以 URDF limit 和 SRDF pose 為準。

目前 joint limits 重點如下：

```text
robotiq_85_left_knuckle_joint        -0.05  to  0.80285
robotiq_85_right_knuckle_joint       -0.05  to  0.80285
robotiq_85_left_inner_knuckle_joint  -0.05  to  0.80285
robotiq_85_right_inner_knuckle_joint -0.05  to  0.80285
robotiq_85_left_finger_tip_joint     -0.80285 to 0.05
robotiq_85_right_finger_tip_joint    -0.80285 to 0.05
```

因此 close `0.8` 時正確命令方向是：

```text
[1, 1, 1, 1, -1, -1]
```

錯用 `[1, -1, 1, 1, -1, 1]` 會讓：

- `right_knuckle_joint = -0.8`，低於 lower limit `-0.05`。
- `right_finger_tip_joint = 0.8`，高於 upper limit `0.05`。

這會造成 `joint_trajectory_controller` abort，測試腳本出現：

```text
Gripper command failed with action status 6
```

Gazebo 畫面則會看到一側被動關節被拉開。

## 最終採用的解法

目前採用「六關節同步控制」而不是依賴 URDF mimic。

### 1. 改用 IFRA 2F-85 Gazebo-friendly model

參考來源：

- `IFRA-Cranfield/ros2_SimRealRobotControl`
- `IFRA-Cranfield/ros2_RobotiqGripper`
- `IFRA-Cranfield/IFRA_LinkAttacher`

本專案將 IFRA 的 2F-85 mesh 與 xacro 搬到：

```text
src/ur5_description/meshes/robotiq_2f85_ifra/
src/ur5_description/urdf/ifra_robotiq_2f85_macro.urdf.xacro
```

UR5 主 xacro 以 `include_gripper:=true` 將 2F-85 接到 `tool0`。

### 2. 不讓 Gazebo 依賴 mimic joint 解被動機構

目前 `ur5_ros2_control.xacro` 將 2F-85 六個運動關節全部列入同一個 `ros2_control` system：

```text
robotiq_85_left_knuckle_joint
robotiq_85_right_knuckle_joint
robotiq_85_left_inner_knuckle_joint
robotiq_85_right_inner_knuckle_joint
robotiq_85_left_finger_tip_joint
robotiq_85_right_finger_tip_joint
```

每個 joint 都提供：

```xml
<command_interface name="position"/>
<state_interface name="position"/>
<state_interface name="velocity"/>
```

這樣 Gazebo 中每個會動的夾爪 joint 都由 controller 明確命令，不再期待 mimic 自動生效。

### 3. 使用 JointTrajectoryController 同步送六個 joint

`ros2_controllers.yaml` 中：

```yaml
robotiq_gripper_controller:
  ros__parameters:
    joints:
      - robotiq_85_left_knuckle_joint
      - robotiq_85_right_knuckle_joint
      - robotiq_85_left_inner_knuckle_joint
      - robotiq_85_right_inner_knuckle_joint
      - robotiq_85_left_finger_tip_joint
      - robotiq_85_right_finger_tip_joint
    command_interfaces:
      - position
    state_interfaces:
      - position
      - velocity
```

測試腳本使用 `/robotiq_gripper_controller/follow_joint_trajectory`，並用以下向量產生目標：

```python
joint_vector = [1.0, 1.0, 1.0, 1.0, -1.0, -1.0]
positions = [grip_position * sign for sign in joint_vector]
```

對應：

```text
open:  [0, 0, 0, 0, 0, 0]
close: [0.8, 0.8, 0.8, 0.8, -0.8, -0.8]
```

### 4. 保留穩定的 fixed endpoint

IFRA model 有一個微小 TCP/endpoint link：

```text
EE_robotiq_2f85
```

目前加上：

```xml
<gazebo reference="${prefix}EE_robotiq_2f85">
  <preserveFixedJoint>true</preserveFixedJoint>
</gazebo>
```

並額外建立：

```text
gripper_tcp
```

方便後續 MoveIt、skill executor、TAMP 使用一致的 tool frame。

## 交接給其他 agent 的除錯流程

如果其他專案也出現「Robotiq mimic joint 在 Gazebo 分解、掉落、半空中搖晃」問題，建議按以下順序處理。

### Step 1：先分清楚 RViz 問題還是 Gazebo 物理問題

檢查：

```bash
ros2 topic echo /joint_states --once
ros2 run tf2_tools view_frames
```

如果 TF/RViz 正常但 Gazebo 中 link 分離，問題通常在 Gazebo 物理約束，而不是 mesh 或 TF。

### Step 2：確認 controller 真的控制了所有會動的 Gazebo joint

檢查：

```bash
ros2 control list_controllers
ros2 control list_joints
ros2 control list_hardware_interfaces
```

若 passive/mimic joint 沒有 command interface，也沒有可靠 Gazebo mimic plugin，Gazebo 不會替你維持閉合機構。

### Step 3：不要只相信 `mimic` tag

Gazebo Classic 中，URDF mimic tag 不等於物理約束。可行策略通常有三種：

- 將每個運動 joint 都列入 controller，使用同步 trajectory 控制。
- 使用已驗證的 Gazebo mimic/closed-chain plugin，但必須確認支援 ROS 2 Humble + Gazebo Classic。
- 簡化 gripper，將被動機構改成 fixed 或 visual-only，只保留一個可控 jaw joint。

目前本專案選第一種，最透明也最容易 debug。

### Step 4：命令前先用 joint limit 推導 sign

不要直接照搬別的 repo 的 `JointsVector`。先看目前實際 URDF 的 joint limits：

```bash
ros2 param get /robot_state_publisher robot_description
```

或展開 xacro 後搜尋：

```bash
xacro src/ur5_description/urdf/ur5.urdf.xacro include_gripper:=true
```

命令 close 時，所有 joint position 必須落在 limit 內。本專案的正確 close 是：

```text
[0.8, 0.8, 0.8, 0.8, -0.8, -0.8]
```

若 action 回 `status 6`，優先檢查目標是否超出 limit。

### Step 5：若 controller 成功但 link 還是被碰撞拉開

下一步再處理 collision：

- 關閉相鄰 gripper links 的 self-collision。
- 降低 collision mesh 複雜度。
- 增加 damping/friction。
- 檢查 fixed joint 是否需要 `<preserveFixedJoint>true</preserveFixedJoint>`。
- 確認初始姿態沒有 interpenetration。

不要一開始就調 PID 或 effort。若 mimic/passive joint 沒被約束，調 PID 只會掩蓋問題。

## 本專案相關檔案

- `src/ur5_description/urdf/ur5.urdf.xacro`
- `src/ur5_description/urdf/ur5_ros2_control.xacro`
- `src/ur5_description/urdf/ifra_robotiq_2f85_macro.urdf.xacro`
- `src/ur5_gazebo/config/ros2_controllers.yaml`
- `src/ur5_gazebo/scripts/send_gripper_open_close.py`
- `src/ur5_description/meshes/robotiq_2f85_ifra/`

## 目前判定

第一版失敗不是單純 mesh 或 controller spawner 問題，而是 Gazebo Classic 對 mimic/passive mechanism 的物理支援不足，加上部分 command sign 超出 joint limit。有效解法是把 2F-85 當成六個可控 revolute joints，在 trajectory controller 中同步命令，並用 URDF/SRDF/limit 驗證 close vector。
