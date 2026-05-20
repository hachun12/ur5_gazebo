from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_gui = LaunchConfiguration("use_gui")
    model = PathJoinSubstitution([
        FindPackageShare("ur5_description"),
        "urdf",
        "ur5.urdf.xacro",
    ])
    rviz_config = PathJoinSubstitution([
        FindPackageShare("ur5_description"),
        "rviz",
        "ur5_display.rviz",
    ])

    robot_description = {
        "robot_description": Command(["xacro ", model, " use_ros2_control:=false"])
    }

    return LaunchDescription([
        DeclareLaunchArgument("use_gui", default_value="true"),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            parameters=[robot_description],
            output="screen",
        ),
        Node(
            package="joint_state_publisher_gui",
            executable="joint_state_publisher_gui",
            condition=IfCondition(use_gui),
            output="screen",
        ),
        Node(
            package="joint_state_publisher",
            executable="joint_state_publisher",
            condition=UnlessCondition(use_gui),
            output="screen",
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            arguments=["-d", rviz_config],
            output="screen",
        ),
    ])
