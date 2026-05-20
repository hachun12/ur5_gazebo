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

## Smoke Tests

Arm trajectory:

```bash
ros2 run ur5_gazebo send_ready_trajectory.py
```

Gripper open/close:

```bash
ros2 run ur5_gazebo send_gripper_open_close.py
```

## Notes

See `docs/m2_robotiq_2f85_gazebo_notes.md` for why the simulation controls the Robotiq gripper as six synchronized joints in Gazebo, and why the real robot deployment should hide this behind a gripper adapter.
