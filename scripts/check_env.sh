#!/usr/bin/env bash
set -u

ROS_DISTRO="${ROS_DISTRO:-humble}"
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILURES=0

check_cmd() {
  local name="$1"
  local cmd="$2"
  if bash -lc "$cmd" >/dev/null 2>&1; then
    echo "[ok] ${name}"
  else
    echo "[missing] ${name}"
    FAILURES=$((FAILURES + 1))
  fi
}

check_path() {
  local name="$1"
  local path="$2"
  if [[ -e "$path" ]]; then
    echo "[ok] ${name}: ${path}"
  else
    echo "[missing] ${name}: ${path}"
    FAILURES=$((FAILURES + 1))
  fi
}

echo "Workspace: ${WORKSPACE_DIR}"
echo "Expected ROS distro: ${ROS_DISTRO}"
echo

check_path "ROS setup" "/opt/ros/${ROS_DISTRO}/setup.bash"
check_cmd "ros2 CLI" "source /opt/ros/${ROS_DISTRO}/setup.bash && command -v ros2"
check_cmd "colcon" "command -v colcon"
check_cmd "gazebo_ros package" "source /opt/ros/${ROS_DISTRO}/setup.bash && ros2 pkg prefix gazebo_ros"
check_cmd "gazebo_ros2_control package" "source /opt/ros/${ROS_DISTRO}/setup.bash && ros2 pkg prefix gazebo_ros2_control"
check_cmd "moveit_ros_move_group package" "source /opt/ros/${ROS_DISTRO}/setup.bash && ros2 pkg prefix moveit_ros_move_group"
check_cmd "moveit_ros_planning_interface package" "source /opt/ros/${ROS_DISTRO}/setup.bash && ros2 pkg prefix moveit_ros_planning_interface"
check_cmd "xacro package" "source /opt/ros/${ROS_DISTRO}/setup.bash && ros2 pkg prefix xacro"

if [[ -f "${WORKSPACE_DIR}/install/setup.bash" ]]; then
  check_cmd "ur5_gazebo package" "source /opt/ros/${ROS_DISTRO}/setup.bash && source ${WORKSPACE_DIR}/install/setup.bash && ros2 pkg prefix ur5_gazebo"
  check_cmd "ur5_moveit_config package" "source /opt/ros/${ROS_DISTRO}/setup.bash && source ${WORKSPACE_DIR}/install/setup.bash && ros2 pkg prefix ur5_moveit_config"
  check_cmd "task_executor package" "source /opt/ros/${ROS_DISTRO}/setup.bash && source ${WORKSPACE_DIR}/install/setup.bash && ros2 pkg prefix task_executor"
else
  echo "[missing] workspace build: ${WORKSPACE_DIR}/install/setup.bash"
  FAILURES=$((FAILURES + 1))
fi

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  echo "[ok] OPENAI_API_KEY is set"
else
  echo "[missing] OPENAI_API_KEY is not set"
fi

echo
if [[ "${FAILURES}" -eq 0 ]]; then
  echo "Environment looks ready."
else
  echo "Environment has ${FAILURES} missing required item(s)."
fi

exit "${FAILURES}"
