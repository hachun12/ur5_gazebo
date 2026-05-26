cmake_minimum_required(VERSION 3.8)
project(task_executor)

find_package(ament_cmake REQUIRED)

install(PROGRAMS
  scripts/execute_skill_plan.py
  scripts/generate_skill_plan.py
  scripts/web_task_ui.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY examples
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
