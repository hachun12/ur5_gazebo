#!/usr/bin/env bash
set -euo pipefail

ROS_DISTRO="${ROS_DISTRO:-humble}"
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(lsb_release -sc)" != "jammy" ]]; then
  echo "This workspace is configured for Ubuntu 22.04 (jammy) + ROS 2 Humble." >&2
  echo "Detected: $(lsb_release -ds)" >&2
  exit 1
fi

echo "[1/7] Installing base tools and enabling Ubuntu universe"
sudo apt-get update
sudo apt-get install -y \
  curl \
  git \
  gnupg \
  lsb-release \
  python3-pip \
  software-properties-common
sudo add-apt-repository -y universe

echo "[2/7] Enabling ROS 2 apt repository"
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  | sudo tee /etc/apt/keyrings/ros-archive-keyring.gpg >/dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list >/dev/null
sudo apt-get update

echo "[3/7] Installing ROS 2, Gazebo Classic, MoveIt 2, and controllers"
sudo apt-get install -y \
  ros-${ROS_DISTRO}-desktop \
  ros-${ROS_DISTRO}-gazebo-ros-pkgs \
  ros-${ROS_DISTRO}-gazebo-ros2-control \
  ros-${ROS_DISTRO}-moveit \
  ros-${ROS_DISTRO}-moveit-configs-utils \
  ros-${ROS_DISTRO}-moveit-kinematics \
  ros-${ROS_DISTRO}-moveit-planners-ompl \
  ros-${ROS_DISTRO}-moveit-ros-move-group \
  ros-${ROS_DISTRO}-moveit-ros-planning \
  ros-${ROS_DISTRO}-moveit-ros-planning-interface \
  ros-${ROS_DISTRO}-moveit-ros-visualization \
  ros-${ROS_DISTRO}-moveit-simple-controller-manager \
  ros-${ROS_DISTRO}-ros2-control \
  ros-${ROS_DISTRO}-ros2-controllers \
  ros-${ROS_DISTRO}-control-msgs \
  ros-${ROS_DISTRO}-joint-state-broadcaster \
  ros-${ROS_DISTRO}-joint-trajectory-controller \
  ros-${ROS_DISTRO}-robot-state-publisher \
  ros-${ROS_DISTRO}-rviz2 \
  ros-${ROS_DISTRO}-xacro \
  python3-colcon-common-extensions \
  python3-rosdep \
  python3-vcstool \
  python3-yaml

echo "[4/7] Initializing rosdep"
if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
  sudo rosdep init
fi
rosdep update

echo "[5/7] Installing package dependencies from package.xml"
set +u
source "/opt/ros/${ROS_DISTRO}/setup.bash"
set -u
rosdep install --from-paths "${WORKSPACE_DIR}/src" --ignore-src -r -y --rosdistro "${ROS_DISTRO}"

echo "[6/7] Building workspace"
cd "${WORKSPACE_DIR}"
colcon build --symlink-install

echo "[7/7] Adding workspace setup to ~/.bashrc if missing"
if ! grep -Fq "source /opt/ros/${ROS_DISTRO}/setup.bash" "${HOME}/.bashrc"; then
  echo "source /opt/ros/${ROS_DISTRO}/setup.bash" >> "${HOME}/.bashrc"
fi
if ! grep -Fq "source ${WORKSPACE_DIR}/install/setup.bash" "${HOME}/.bashrc"; then
  echo "source ${WORKSPACE_DIR}/install/setup.bash" >> "${HOME}/.bashrc"
fi

echo
echo "Done. Open a new terminal or run:"
echo "  source /opt/ros/${ROS_DISTRO}/setup.bash"
echo "  source ${WORKSPACE_DIR}/install/setup.bash"
echo
echo "For OpenAI planning, create .env from .env.example and export OPENAI_API_KEY."
