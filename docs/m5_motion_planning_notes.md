# M5 Motion Planning Notes

本文件記錄 `task_executor` 自動化 MoveIt motion 時遇到的路徑規劃問題、原因分析與目前採用的處理方式。這段很重要，因為後續 LLM/TAMP skill 若直接把 pose goal 丟給 MoveIt，很容易重新踩到同樣問題。

## 問題現象

使用者在 RViz MotionPlanning UI 中，手動拖曳 `gripper_tcp` 到同一個目標點後按 Plan/Execute，UR5 路徑正常。

但在 `task_executor` 中直接用程式送出相同 `gripper_tcp` 目標 pose 時，曾出現：

- 手臂反向繞一大圈。
- wrist / elbow branch 選錯。
- planned path 看起來整個亂轉。
- controller 最後回報：

```text
PATH_TOLERANCE_VIOLATED
MoveIt execution failed
```

也曾在加上 orientation path constraint 後出現：

```text
MoveGroup action failed with status 6
Planning request aborted
```

## 為什麼 RViz 正常，程式直接 call pose goal 卻不正常

兩者看似都是「把同一個 TCP pose 給 MoveIt」，但實際上不完全等價。

### 1. 同一個 TCP pose 有多組 IK 解

UR5 對同一個 `gripper_tcp` pose 可能有多個 joint solution：

- shoulder 不同繞法
- elbow-up / elbow-down
- wrist flip
- joint 繞接近 `2*pi`

RViz interactive marker 在拖曳時會即時求 IK，通常會以目前 robot state 作為 seed，並由使用者視覺上排除怪姿態。等使用者按 Plan 時，goal state 往往已經是一組看起來合理的 joint configuration。

程式直接使用 pose goal 或手刻 `PositionConstraint + OrientationConstraint` 時，MoveIt / OMPL 的 goal sampler 只需要找到「滿足 pose constraint」的 goal state，不保證選到與 RViz marker 相同的 IK branch。

### 2. Pose goal 是 constraint，不是唯一 goal state

程式若呼叫：

```text
setPoseTarget(target_pose, "gripper_tcp")
```

或直接送：

```text
PositionConstraint + OrientationConstraint
```

本質上是告訴 MoveIt：

```text
終點 TCP 滿足這個 pose 即可
```

這不是一組明確的六軸 joint goal。OMPL 可以在 constraint manifold 裡取樣，抽到數學上合法但動作很不自然的解。

### 3. RViz 有互動狀態，程式 raw request 沒有

RViz MotionPlanning panel 有自己的 start state、goal state、query state、interactive marker state。拖曳 marker 的過程已經先建立了一個具體 goal state。

程式若只是 raw `/move_action` 或低階 request，沒有這個互動過程，也不會自動保證「接近目前 joint state 的 IK 解」。

### 4. 加 path orientation constraint 不一定會變好

曾嘗試在 raw `MotionPlanRequest` 中加入：

```text
goal orientation constraint
path orientation constraint
```

這可讓姿態限制變嚴格，但會把 OMPL 帶入更困難的 constrained planning 問題。結果可能是：

- constrained space 取樣困難
- path 繞得更怪
- 規劃直接 abort

因此不能把「加更嚴格 orientation constraint」當成萬用解。

## 嘗試過但不適合當完整解法的方法

### 方法 A：全部改成 Cartesian path

將 `move_above_object`、`move_to_object`、`lift` 全部改成：

```text
/compute_cartesian_path
-> /execute_trajectory
```

優點：

- TCP 路徑很可控。
- 下探和抬升不會亂繞。

缺點：

- 繞過了 OMPL 的避障規劃能力。
- 未來遇到障礙物、桌面邊界、其他物件、實機 workspace 限制時不可接受。

結論：

Cartesian path 適合短距離 approach / retreat，不適合作為所有 transit motion 的替代品。

### 方法 B：MoveGroupInterface 直接 setPoseTarget

新增過 `moveit_skill_server`，使用 C++：

```cpp
move_group.setStartStateToCurrentState();
move_group.setPoseTarget(target_pose, "gripper_tcp");
move_group.plan(plan);
move_group.execute(plan);
```

這比 raw `/move_action` 更接近 RViz，但仍可能選到不好的 IK branch。原因是 `setPoseTarget()` 仍然是 pose goal，不是一組固定 joint goal。

結論：

MoveGroupInterface 可以保留給一般功能，但對桌面 pick 的 pre-grasp transit，仍需控制 IK branch。

## 目前採用的正確策略

目前對不同 motion 類型採用不同規劃策略：

```text
Transit motion:
  seeded IK -> joint goal -> OMPL joint-space planning

Approach / retreat motion:
  Cartesian path
```

### Transit：`move_above_object`

`move_above_object(object, z_offset)` 現在流程是：

```text
1. 讀 Gazebo object pose
2. 產生 gripper_tcp pre-grasp target pose
3. 讀目前 /joint_states
4. 呼叫 /compute_ik
   - group_name = ur_manipulator
   - ik_link_name = gripper_tcp
   - seed = current joint state
5. 取得一組接近目前姿態的 IK joint solution
6. 做 joint delta quality gate
7. 將 IK solution 轉成 JointConstraint goal
8. 呼叫 /move_action 讓 OMPL 做 joint-space planning
9. execute trajectory
```

這樣做的核心理由：

- `compute_ik` 用目前 joint state 當 seed，比較容易得到與目前姿態同 branch 的 IK 解。
- OMPL 收到的是明確 joint goal，不再需要在 pose constraint 裡亂抽 goal state。
- 仍保留 OMPL 的避障/自碰撞規劃能力。
- 行為更接近 RViz 中「人拖 marker 選好合理 IK 解後再 Plan」。

目前 `task_executor` 會印：

```text
seeded IK target gripper_tcp ...
seeded IK joint goal {...}
joint deltas {...}
```

若 IK 解離目前姿態太遠，會被 quality gate 拒絕：

```text
IK goal rejected by quality gate
```

### Approach：`move_to_object`

物件上方到抓取點的短距離下探，不用 OMPL 自由規劃，而是：

```text
/compute_cartesian_path
-> /execute_trajectory
```

原因：

- 這段應該保持 TCP 姿態。
- 這段應該近似直線。
- 不應讓 OMPL 繞路或翻腕。

### Retreat：`lift`

抓取後垂直抬升同樣使用 Cartesian path：

```text
/compute_cartesian_path
-> /execute_trajectory
```

原因：

- 抬升應該是局部直線。
- 保持抓取姿態比避障繞路更重要。

## 現行分段策略

目前 `pick(object)` 使用：

```text
open_gripper
move_above_object(object, z_offset=0.16)   # seeded IK + OMPL joint-space planning
move_to_object(object, z_offset=0.055)     # Cartesian descent
close_gripper
attach_object(object)
lift(height=0.15)                          # Cartesian retreat
```

## 後續建議

### 1. 保留 motion type 區分

不要把所有 motion 都統一成 pose goal，也不要把所有 motion 都統一成 Cartesian。

建議分層：

```text
move_transit_to_pose:
  seeded IK + joint-space OMPL

move_linear:
  Cartesian path

move_named_joint_goal:
  joint trajectory or MoveIt joint-space plan
```

### 2. 加強 quality gate

目前只做 joint delta gate。後續可加入：

- wrist flip detection
- max joint delta per joint
- trajectory first waypoint 是否接近 current joint state
- trajectory length / duration threshold
- minimum TCP z height
- joint limit margin
- collision result check

### 3. Planning scene 仍需要補齊

雖然目前桌面物件在 Gazebo 中存在，但 MoveIt planning scene 不一定知道桌子與物件。未來要做避障時，需要把 world state 轉成 MoveIt collision objects。

### 4. MoveGroupInterface server 可保留

`moveit_skill_server` 可保留給未來非 pick 的通用 motion service，但對 pick pre-grasp transit，應優先使用 seeded IK + joint goal。

## 目前狀態

使用者回報：

```text
seeded IK + joint-space OMPL 的 move_above_object 工作正常。
```

後續錯誤已轉移到夾取階段，代表 transit planning 的主要問題已初步解決。
