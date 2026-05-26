from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    world = LaunchConfiguration("world")
    gui = LaunchConfiguration("gui")
    launch_rviz = LaunchConfiguration("launch_rviz")
    software_rendering = LaunchConfiguration("software_rendering")
    moveit_start_delay = LaunchConfiguration("moveit_start_delay")

    sim_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("ur5_gazebo"),
                "launch",
                "sim.launch.py",
            ])
        ]),
        launch_arguments={
            "use_sim_time": use_sim_time,
            "world": world,
            "gui": gui,
            "software_rendering": software_rendering,
        }.items(),
    )

    moveit_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("ur5_moveit_config"),
                "launch",
                "moveit_rviz.launch.py",
            ])
        ]),
        launch_arguments={
            "use_sim_time": use_sim_time,
            "launch_rviz": launch_rviz,
            "software_rendering": software_rendering,
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        DeclareLaunchArgument("gui", default_value="true"),
        DeclareLaunchArgument("launch_rviz", default_value="true"),
        DeclareLaunchArgument("software_rendering", default_value="false"),
        DeclareLaunchArgument("moveit_start_delay", default_value="8.0"),
        DeclareLaunchArgument(
            "world",
            default_value=PathJoinSubstitution([
                FindPackageShare("ur5_gazebo"),
                "worlds",
                "empty_workcell.world",
            ]),
        ),
        sim_launch,
        TimerAction(
            period=moveit_start_delay,
            actions=[moveit_launch],
        ),
    ])
