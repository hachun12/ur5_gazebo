cmake_minimum_required(VERSION 3.8)
project(moveit_skill_server)

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/MoveToPose.srv"
  DEPENDENCIES geometry_msgs
)

add_executable(moveit_skill_server_node src/moveit_skill_server_node.cpp)
ament_target_dependencies(moveit_skill_server_node
  moveit_ros_planning_interface
  rclcpp
)

rosidl_get_typesupport_target(cpp_typesupport_target
  ${PROJECT_NAME}
  "rosidl_typesupport_cpp"
)
target_link_libraries(moveit_skill_server_node "${cpp_typesupport_target}")

install(TARGETS moveit_skill_server_node
  DESTINATION lib/${PROJECT_NAME}
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
