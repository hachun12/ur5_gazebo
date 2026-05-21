import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def load_yaml(package_name, relative_path):
    package_path = get_package_share_directory(package_name)
    absolute_path = os.path.join(package_path, relative_path)
    with open(absolute_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_text(package_name, relative_path):
    package_path = get_package_share_directory(package_name)
    absolute_path = os.path.join(package_path, relative_path)
    with open(absolute_path, "r", encoding="utf-8") as file:
        return file.read()


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    launch_rviz = LaunchConfiguration("launch_rviz")
    software_rendering = LaunchConfiguration("software_rendering")

    robot_xacro = PathJoinSubstitution([
        FindPackageShare("ur5_description"),
        "urdf",
        "ur5.urdf.xacro",
    ])
    ur5_description_share = FindPackageShare("ur5_description")
    gripper_mesh_prefix = PathJoinSubstitution([
        ur5_description_share,
        "meshes",
        "robotiq_2f85_ifra",
    ])

    robot_description = {
        "robot_description": ParameterValue(
            Command([
                "xacro ",
                robot_xacro,
                " use_ros2_control:=false",
                " mesh_prefix:=file://",
                ur5_description_share,
                " use_fixed_world_joint:=true",
                " include_gripper:=true",
                " gripper_mesh_prefix:=file://",
                gripper_mesh_prefix,
            ]),
            value_type=str,
        )
    }

    robot_description_semantic = {
        "robot_description_semantic": load_text("ur5_moveit_config", "config/ur5.srdf")
    }
    robot_description_kinematics = {
        "robot_description_kinematics": load_yaml("ur5_moveit_config", "config/kinematics.yaml")
    }
    joint_limits = load_yaml("ur5_moveit_config", "config/joint_limits.yaml")
    ompl_planning_pipeline_config = {
        "move_group": {
            "planning_plugin": "ompl_interface/OMPLPlanner",
            "request_adapters": (
                "default_planner_request_adapters/AddTimeOptimalParameterization "
                "default_planner_request_adapters/FixWorkspaceBounds "
                "default_planner_request_adapters/FixStartStateBounds "
                "default_planner_request_adapters/FixStartStateCollision "
                "default_planner_request_adapters/FixStartStatePathConstraints"
            ),
            "start_state_max_bounds_error": 0.1,
        }
    }
    ompl_planning_pipeline_config["move_group"].update(
        load_yaml("ur5_moveit_config", "config/ompl_planning.yaml")
    )

    trajectory_execution = load_yaml("ur5_moveit_config", "config/trajectory_execution.yaml")
    moveit_controllers = load_yaml("ur5_moveit_config", "config/moveit_controllers.yaml")

    planning_scene_monitor_parameters = {
        "publish_planning_scene": True,
        "publish_geometry_updates": True,
        "publish_state_updates": True,
        "publish_transforms_updates": True,
        "publish_robot_description": True,
        "publish_robot_description_semantic": True,
    }

    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            robot_description,
            robot_description_semantic,
            robot_description_kinematics,
            joint_limits,
            ompl_planning_pipeline_config,
            trajectory_execution,
            moveit_controllers,
            planning_scene_monitor_parameters,
            {"use_sim_time": use_sim_time},
        ],
    )

    moveit_skill_server = Node(
        package="moveit_skill_server",
        executable="moveit_skill_server_node",
        output="screen",
        parameters=[
            robot_description,
            robot_description_semantic,
            robot_description_kinematics,
            joint_limits,
            ompl_planning_pipeline_config,
            trajectory_execution,
            moveit_controllers,
            planning_scene_monitor_parameters,
            {"use_sim_time": use_sim_time},
        ],
    )

    rviz_config = PathJoinSubstitution([
        FindPackageShare("ur5_moveit_config"),
        "rviz",
        "moveit.rviz",
    ])
    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2_moveit",
        output="screen",
        arguments=["-d", rviz_config],
        condition=IfCondition(launch_rviz),
        parameters=[
            robot_description,
            robot_description_semantic,
            robot_description_kinematics,
            {"use_sim_time": use_sim_time},
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        DeclareLaunchArgument("launch_rviz", default_value="true"),
        DeclareLaunchArgument("software_rendering", default_value="false"),
        SetEnvironmentVariable(
            name="LIBGL_ALWAYS_SOFTWARE",
            value="1",
            condition=IfCondition(software_rendering),
        ),
        SetEnvironmentVariable(
            name="QT_XCB_GL_INTEGRATION",
            value="none",
            condition=IfCondition(software_rendering),
        ),
        move_group,
        moveit_skill_server,
        rviz,
    ])
