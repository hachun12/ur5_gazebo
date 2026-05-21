from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, RegisterEventHandler, SetEnvironmentVariable, TimerAction
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    world = LaunchConfiguration("world")
    gui = LaunchConfiguration("gui")
    software_rendering = LaunchConfiguration("software_rendering")

    robot_xacro = PathJoinSubstitution([
        FindPackageShare("ur5_description"),
        "urdf",
        "ur5.urdf.xacro",
    ])
    render_urdf = PathJoinSubstitution([
        FindPackageShare("ur5_gazebo"),
        "..",
        "..",
        "lib",
        "ur5_gazebo",
        "render_urdf.py",
    ])
    controllers_file = PathJoinSubstitution([
        FindPackageShare("ur5_gazebo"),
        "config",
        "ros2_controllers.yaml",
    ])
    ur5_description_share = FindPackageShare("ur5_description")
    gripper_mesh_prefix = PathJoinSubstitution([
        ur5_description_share,
        "meshes",
        "robotiq_2f85_ifra",
    ])
    robot_description_content = ParameterValue(
        Command([
            render_urdf,
            " ",
            robot_xacro,
            " use_ros2_control:=true",
            " ros2_control_hardware_plugin:=gazebo_ros2_control/GazeboSystem",
            " ros2_control_parameters:=",
            controllers_file,
            " mesh_prefix:=file://",
            ur5_description_share,
            " use_fixed_world_joint:=true",
            " include_gripper:=true",
            " gripper_mesh_prefix:=file://",
            gripper_mesh_prefix,
        ]),
        value_type=str,
    )
    robot_description = {
        "robot_description": robot_description_content
    }

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("gazebo_ros"),
                "launch",
                "gazebo.launch.py",
            ])
        ]),
        launch_arguments={
            "world": world,
            "verbose": "true",
            "gui": gui,
            "init": "true",
            "factory": "true",
            "force_system": "true",
        }.items(),
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[robot_description, {"use_sim_time": use_sim_time}],
        output="screen",
    )

    spawn_robot = Node(
        package="gazebo_ros",
        executable="spawn_entity.py",
        arguments=[
            "-topic",
            "robot_description",
            "-entity",
            "ur5",
            "-x",
            "0.0",
            "-y",
            "0.0",
            "-z",
            "0.0",
            "-timeout",
            "120",
        ],
        output="screen",
    )

    spawn_joint_state_broadcaster = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager",
            "/controller_manager",
            "--controller-manager-timeout",
            "120",
        ],
        output="screen",
    )

    spawn_arm_controller = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "ur5_arm_controller",
            "--controller-manager",
            "/controller_manager",
            "--controller-manager-timeout",
            "120",
        ],
        output="screen",
    )

    spawn_gripper_controller = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "robotiq_gripper_controller",
            "--controller-manager",
            "/controller_manager",
            "--controller-manager-timeout",
            "120",
        ],
        output="screen",
    )

    sim_grasp_adapter = Node(
        package="ur5_gazebo",
        executable="sim_grasp_adapter.py",
        parameters=[{
            "use_sim_time": use_sim_time,
            "target_object": "red_block",
            "world_frame": "world",
            "tcp_frame": "gripper_tcp",
        }],
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        DeclareLaunchArgument("gui", default_value="true"),
        DeclareLaunchArgument("software_rendering", default_value="false"),
        DeclareLaunchArgument(
            "world",
            default_value=PathJoinSubstitution([
                FindPackageShare("ur5_gazebo"),
                "worlds",
                "empty_workcell.world",
            ]),
        ),
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
        gazebo,
        robot_state_publisher,
        sim_grasp_adapter,
        spawn_robot,
        RegisterEventHandler(
            OnProcessExit(
                target_action=spawn_robot,
                on_exit=[
                    TimerAction(
                        period=5.0,
                        actions=[
                            spawn_joint_state_broadcaster,
                            spawn_arm_controller,
                            spawn_gripper_controller,
                        ],
                    )
                ],
            )
        ),
    ])
