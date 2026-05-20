cmake_minimum_required(VERSION 3.8)
project(ur5_gazebo)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config launch worlds
  DESTINATION share/${PROJECT_NAME}
)

install(PROGRAMS
  scripts/render_urdf.py
  scripts/send_ready_trajectory.py
  scripts/send_gripper_open_close.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
