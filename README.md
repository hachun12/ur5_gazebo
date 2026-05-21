# UR5 Gazebo ROS 2 Humble Workcell

ROS 2 Humble + Gazebo Classic bringup for a UR5 workcell with a Robotiq 2F-85 gripper.

The current simulation uses:

- `ur5_description`: UR5 URDF/xacro, meshes, ros2_control tags, and the IFRA-style Robotiq 2F-85 model.
- `ur5_gazebo`: Gazebo world, launch file, ros2_control controller config, and smoke-test scripts.
- `docs/`: development checklist and troubleshooting notes, including the Gazebo mimic/passive joint issue for Robotiq 2F-85.

## Dependencies

```bash
sudo apt-get update
sudo apt-get install -y \
  ros-humble-gazebo-ros-pkgs \
  ros-humble-gazebo-ros2-control \
  ros-humble-ros2-control \
  ros-humble-ros2-controllers \
  ros-humble-joint-trajectory-controller \
  ros-humble-joint-state-broadcaster \
  ros-humble-xacro
```

## Build

```bash
cd ~/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

## Launch Gazebo

```bash
ros2 launch ur5_gazebo sim.launch.py
```

Headless or software-rendered Gazebo:

```bash
ros2 launch ur5_gazebo sim.launch.py gui:=false
ros2 launch ur5_gazebo sim.launch.py gui:=false software_rendering:=true
```

## Launch MoveIt2 + RViz2

Start Gazebo first, then in another terminal:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch ur5_moveit_config moveit_rviz.launch.py
```

If RViz cannot create an OpenGL context:

```bash
ros2 launch ur5_moveit_config moveit_rviz.launch.py software_rendering:=true
```

## Smoke Tests

Arm trajectory:

```bash
ros2 run ur5_gazebo send_ready_trajectory.py
```

Gripper open/close:

```bash
ros2 run ur5_gazebo send_gripper_open_close.py
```

Ground-truth tabletop world state:

```bash
ros2 run ur5_gazebo print_world_state.py
```

Sim-only grasp attach/detach:

```bash
ros2 run ur5_gazebo grasp_target.py attach red_block
ros2 run ur5_gazebo grasp_target.py detach
```

## Notes

See `docs/m2_robotiq_2f85_gazebo_notes.md` for why the simulation controls the Robotiq gripper as six synchronized joints in Gazebo, and why the real robot deployment should hide this behind a gripper adapter.
See `docs/m3_tabletop_objects_world_state.md` for the tabletop object layout and the world-state JSON schema.
See `docs/m4_moveit2_rviz_control.md` for RViz planning and execution.
