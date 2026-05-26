#!/usr/bin/env bash
set -euo pipefail

echo "[1/2] Installing audio decode tooling"
sudo apt-get update
sudo apt-get install -y ffmpeg

echo "[2/2] Installing faster-whisper for the current user"
python3 -m pip install --user --upgrade faster-whisper

echo
echo "Done. Restart the Web UI after installation:"
echo "  source /opt/ros/humble/setup.bash"
echo "  source install/setup.bash"
echo "  ros2 run task_executor web_task_ui.py"
