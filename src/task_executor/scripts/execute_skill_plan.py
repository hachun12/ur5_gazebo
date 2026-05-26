#!/usr/bin/env python3

import argparse
import json
import math
import sys
from pathlib import Path

import rclpy
import yaml
from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from control_msgs.action import FollowJointTrajectory
from gazebo_msgs.srv import GetEntityState
from geometry_msgs.msg import Pose
from moveit_msgs.action import ExecuteTrajectory, MoveGroup
from moveit_msgs.msg import Constraints, JointConstraint, MotionPlanRequest, OrientationConstraint, PositionConstraint
from moveit_msgs.srv import GetCartesianPath, GetPositionIK
from rcl_interfaces.srv import SetParameters
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.time import Time
from sensor_msgs.msg import JointState
from shape_msgs.msg import SolidPrimitive
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformException, TransformListener
from trajectory_msgs.msg import JointTrajectoryPoint


OBJECTS = {
    "red_block": {"class": "block", "color": "red"},
    "green_block": {"class": "block", "color": "green"},
    "blue_block": {"class": "block", "color": "blue"},
    "green_ball": {"class": "ball", "color": "green"},
}

REGIONS = {
    "left_region": {"x": 0.35, "y": 0.22},
    "center_region": {"x": 0.35, "y": 0.0},
    "right_region": {"x": 0.35, "y": -0.22},
    "front_region": {"x": 0.50, "y": 0.0},
}

ARM_JOINTS = [
    "shoulder_pan_joint",
    "shoulder_lift_joint",
    "elbow_joint",
    "wrist_1_joint",
    "wrist_2_joint",
    "wrist_3_joint",
]

READY_POSE = [
    0.0,
    -math.pi / 2.0,
    math.pi / 2.0,
    -math.pi / 2.0,
    -math.pi / 2.0,
    0.0,
]

GRIPPER_JOINTS = [
    "robotiq_85_left_knuckle_joint",
    "robotiq_85_right_knuckle_joint",
    "robotiq_85_left_inner_knuckle_joint",
    "robotiq_85_right_inner_knuckle_joint",
    "robotiq_85_left_finger_tip_joint",
    "robotiq_85_right_finger_tip_joint",
]

GRIPPER_SIGNS = [1.0, 1.0, 1.0, 1.0, -1.0, -1.0]


class PlanValidationError(RuntimeError):
    pass


class SkillPlanExecutor(Node):
    def __init__(self):
        super().__init__("skill_plan_executor")
        self.registry = self.load_skill_registry()
        self.arm_client = ActionClient(
            self,
            FollowJointTrajectory,
            "/ur5_arm_controller/follow_joint_trajectory",
        )
        self.gripper_client = ActionClient(
            self,
            FollowJointTrajectory,
            "/robotiq_gripper_controller/follow_joint_trajectory",
        )
        self.move_group_client = ActionClient(self, MoveGroup, "/move_action")
        self.execute_trajectory_client = ActionClient(
            self,
            ExecuteTrajectory,
            "/execute_trajectory",
        )
        self.get_entity_client = self.create_client(GetEntityState, "/gazebo/get_entity_state")
        self.cartesian_path_client = self.create_client(GetCartesianPath, "/compute_cartesian_path")
        self.compute_ik_client = self.create_client(GetPositionIK, "/compute_ik")
        self.latest_joint_state = None
        self.create_subscription(JointState, "/joint_states", self.on_joint_state, 10)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

    def on_joint_state(self, msg):
        if msg.name:
            self.latest_joint_state = msg

    def load_skill_registry(self):
        share = Path(get_package_share_directory("skill_library"))
        skills_dir = share / "config" / "skills"
        registry = {}
        for skill_file in sorted(skills_dir.glob("*.yaml")):
            with skill_file.open("r", encoding="utf-8") as stream:
                skill = yaml.safe_load(stream)
            registry[skill["skill_id"]] = skill
        return registry

    def validate_plan(self, plan):
        if "plan" not in plan or not isinstance(plan["plan"], list):
            raise PlanValidationError("plan must contain a list field named 'plan'")

        expected_step = 1
        for step in plan["plan"]:
            if step.get("step") != expected_step:
                raise PlanValidationError(f"step number must be consecutive; expected {expected_step}")
            expected_step += 1

            skill_id = step.get("skill")
            if skill_id not in self.registry:
                raise PlanValidationError(f"unknown skill: {skill_id}")

            args = step.get("args", {})
            if not isinstance(args, dict):
                raise PlanValidationError(f"{skill_id}.args must be an object")

            spec = self.registry[skill_id].get("parameters") or {}
            for name, parameter in spec.items():
                if parameter.get("required", False) and name not in args:
                    raise PlanValidationError(f"{skill_id} missing required arg: {name}")
                if name in args:
                    self.validate_arg(skill_id, name, parameter, args[name])

        return True

    def validate_arg(self, skill_id, name, parameter, value):
        expected_type = parameter.get("type")
        if expected_type == "string" and not isinstance(value, str):
            raise PlanValidationError(f"{skill_id}.{name} must be a string")
        if expected_type == "number" and not isinstance(value, (int, float)):
            raise PlanValidationError(f"{skill_id}.{name} must be a number")
        if expected_type == "object" and not isinstance(value, dict):
            raise PlanValidationError(f"{skill_id}.{name} must be an object")

        allowed = parameter.get("enum")
        if allowed and value not in allowed:
            raise PlanValidationError(f"{skill_id}.{name} must be one of {allowed}")

    def execute_plan(self, plan):
        self.validate_plan(plan)
        self.get_logger().info(f"validated {len(plan['plan'])} skill step(s)")

        for step in plan["plan"]:
            skill_id = step["skill"]
            args = step.get("args", {})
            self.get_logger().info(f"step {step['step']}: {skill_id} {json.dumps(args)}")
            handler = getattr(self, f"skill_{skill_id}", None)
            if handler is None:
                raise RuntimeError(f"{skill_id} is registered but not implemented in this executor")
            handler(args)

        self.get_logger().info("skill plan succeeded")

    def skill_observe_scene(self, args):
        del args
        state = {}
        for name, metadata in OBJECTS.items():
            pose = self.get_entity_pose(name)
            state[name] = {
                **metadata,
                "pose": {
                    "x": round(pose.position.x, 4),
                    "y": round(pose.position.y, 4),
                    "z": round(pose.position.z, 4),
                },
            }
        self.get_logger().info(json.dumps({"objects": state}, ensure_ascii=False))

    def skill_move_ready(self, args):
        del args
        self.send_trajectory(
            self.arm_client,
            ARM_JOINTS,
            READY_POSE,
            duration_sec=4,
            label="move_ready",
        )

    def skill_open_gripper(self, args):
        del args
        self.command_gripper(0.0, "open_gripper")

    def skill_close_gripper(self, args):
        position = float(args.get("position", 0.8))
        self.command_gripper(position, "close_gripper")

    def skill_attach_object(self, args):
        self.attach_object(args["object"])

    def skill_detach_object(self, args):
        del args
        self.trigger("/sim_grasp_adapter/detach")

    def skill_move_above_object(self, args):
        pose = self.get_entity_pose(args["object"])
        z_offset = float(args.get("z_offset", 0.16))
        self.move_tcp_seeded_ik_joint_goal(
            pose.position.x,
            pose.position.y,
            pose.position.z + z_offset,
            label=f"move_above_object({args['object']})",
            position_tolerance=0.015,
        )

    def skill_move_to_object(self, args):
        pose = self.get_entity_pose(args["object"])
        z_offset = float(args.get("z_offset", 0.055))
        self.move_tcp_cartesian_to_pose(
            pose.position.x,
            pose.position.y,
            pose.position.z + z_offset,
            label=f"move_to_object({args['object']})",
            position_tolerance=0.012,
        )

    def skill_lift(self, args):
        height = float(args.get("height", 0.15))
        tcp_pose = self.get_tcp_pose()
        self.move_tcp_cartesian_to_pose(
            tcp_pose.position.x,
            tcp_pose.position.y,
            tcp_pose.position.z + height,
            label=f"lift({height:.3f})",
            position_tolerance=0.015,
        )

    def skill_move_to_region(self, args):
        region = args["region"]
        if region not in REGIONS:
            raise RuntimeError(f"unknown region: {region}")

        tcp_z = float(args.get("tcp_z", 0.09))
        target = REGIONS[region]
        self.move_tcp_seeded_ik_joint_goal(
            target["x"],
            target["y"],
            tcp_z,
            label=f"move_to_region({region})",
            position_tolerance=0.02,
        )

    def skill_pick(self, args):
        self.command_gripper(0.0, "pick/open")
        self.skill_move_above_object({"object": args["object"], "z_offset": 0.16})
        self.skill_move_to_object({"object": args["object"], "z_offset": 0.04})
        self.command_gripper(0.30, "pick/close")
        self.attach_object(args["object"])
        self.skill_lift({"height": 0.15})

    def skill_place(self, args):
        del args
        # MVP assumption: MoveIt/RViz or a future pose skill has already moved the object to the target pose.
        self.trigger("/sim_grasp_adapter/detach")
        self.command_gripper(0.0, "place/open")

    def skill_verify_relation(self, args):
        relation = args["relation"]
        pose_a = self.get_entity_pose(args["object_a"])
        pose_b = self.get_entity_pose(args["object_b"])

        tolerance = 0.075
        if relation == "on":
            ok = abs(pose_a.position.x - pose_b.position.x) < tolerance
            ok = ok and abs(pose_a.position.y - pose_b.position.y) < tolerance
            ok = ok and pose_a.position.z > pose_b.position.z + 0.035
        elif relation == "left_of":
            ok = pose_a.position.y > pose_b.position.y + tolerance
        elif relation == "right_of":
            ok = pose_a.position.y < pose_b.position.y - tolerance
        elif relation == "in_front_of":
            ok = pose_a.position.x > pose_b.position.x + tolerance
        elif relation == "behind":
            ok = pose_a.position.x < pose_b.position.x - tolerance
        else:
            raise RuntimeError(f"unsupported relation: {relation}")

        if not ok:
            raise RuntimeError(
                f"relation check failed: {args['object_a']} {relation} {args['object_b']}"
            )
        self.get_logger().info(
            f"relation verified: {args['object_a']} {relation} {args['object_b']}"
        )

    def skill_verify_region(self, args):
        pose = self.get_entity_pose(args["object"])
        region = args["region"]
        if region == "left_region":
            ok = pose.position.y > 0.08
        elif region == "right_region":
            ok = pose.position.y < -0.08
        elif region == "center_region":
            ok = abs(pose.position.y) <= 0.08
        elif region == "front_region":
            ok = pose.position.x > 0.40
        else:
            raise RuntimeError(f"unsupported region: {region}")

        if not ok:
            raise RuntimeError(f"region check failed: {args['object']} not in {region}")
        self.get_logger().info(f"region verified: {args['object']} in {region}")

    def skill_push(self, args):
        raise RuntimeError(f"push is registered but not implemented yet: {args}")

    def skill_stack(self, args):
        top_object = args["top_object"]
        bottom_object = args["bottom_object"]
        if top_object == bottom_object:
            raise RuntimeError("stack requires two different objects")
        self.ensure_stackable_block(top_object)
        self.ensure_stackable_block(bottom_object)

        approach_clearance = float(args.get("approach_clearance", 0.10))
        place_tcp_z_offset = float(args.get("place_tcp_z_offset", 0.105))
        bottom_pose = self.get_entity_pose(bottom_object)
        place_tcp_z = bottom_pose.position.z + place_tcp_z_offset
        approach_tcp_z = place_tcp_z + approach_clearance

        self.get_logger().info(
            f"stack({top_object}, {bottom_object}): "
            f"place_tcp_z={place_tcp_z:.3f} approach_tcp_z={approach_tcp_z:.3f}"
        )
        self.skill_pick({"object": top_object})
        bottom_pose = self.get_entity_pose(bottom_object)
        self.move_tcp_seeded_ik_joint_goal(
            bottom_pose.position.x,
            bottom_pose.position.y,
            approach_tcp_z,
            label=f"stack/above({bottom_object})",
            position_tolerance=0.02,
        )
        self.move_tcp_cartesian_to_pose(
            bottom_pose.position.x,
            bottom_pose.position.y,
            place_tcp_z,
            label=f"stack/place_on({bottom_object})",
            position_tolerance=0.015,
        )
        self.skill_place({})
        self.skill_verify_relation(
            {
                "relation": "on",
                "object_a": top_object,
                "object_b": bottom_object,
            }
        )

    def ensure_stackable_block(self, object_name):
        metadata = OBJECTS.get(object_name)
        if metadata is None:
            raise RuntimeError(f"unknown object: {object_name}")
        if metadata.get("class") != "block":
            raise RuntimeError(f"{object_name} is not stackable in the MVP scene")

    def move_tcp_to_pose(self, x, y, z, label, position_tolerance=0.015):
        current_pose = self.get_tcp_pose()
        target = Pose()
        target.position.x = x
        target.position.y = y
        target.position.z = z
        target.orientation = current_pose.orientation

        self.get_logger().info(
            f"{label}: MoveGroupInterface target gripper_tcp "
            f"x={x:.3f} y={y:.3f} z={z:.3f} "
            f"qx={target.orientation.x:.4f} qy={target.orientation.y:.4f} "
            f"qz={target.orientation.z:.4f} qw={target.orientation.w:.4f}"
        )
        self.call_move_to_pose(target, label)

    def move_tcp_cartesian_to_pose(self, x, y, z, label, position_tolerance=0.015):
        current_pose = self.get_tcp_pose()
        target = Pose()
        target.position.x = x
        target.position.y = y
        target.position.z = z
        target.orientation = current_pose.orientation

        self.get_logger().info(
            f"{label}: Cartesian target gripper_tcp "
            f"x={x:.3f} y={y:.3f} z={z:.3f} "
            f"qx={target.orientation.x:.4f} qy={target.orientation.y:.4f} "
            f"qz={target.orientation.z:.4f} qw={target.orientation.w:.4f}"
        )
        self.compute_and_execute_cartesian_path(target, label)

    def get_tcp_pose(self):
        try:
            transform = self.tf_buffer.lookup_transform(
                "world",
                "gripper_tcp",
                Time(),
                timeout=Duration(seconds=1.0),
            )
        except TransformException as exc:
            raise RuntimeError(f"failed to lookup world->gripper_tcp: {exc}") from exc

        pose = Pose()
        pose.position.x = transform.transform.translation.x
        pose.position.y = transform.transform.translation.y
        pose.position.z = transform.transform.translation.z
        pose.orientation = transform.transform.rotation
        return pose

    def move_tcp_seeded_ik_joint_goal(self, x, y, z, label, position_tolerance=0.015):
        current_pose = self.get_tcp_pose()
        target = Pose()
        target.position.x = x
        target.position.y = y
        target.position.z = z
        target.orientation = current_pose.orientation

        self.get_logger().info(
            f"{label}: seeded IK target gripper_tcp "
            f"x={x:.3f} y={y:.3f} z={z:.3f} "
            f"qx={target.orientation.x:.4f} qy={target.orientation.y:.4f} "
            f"qz={target.orientation.z:.4f} qw={target.orientation.w:.4f}"
        )
        joint_goal = self.compute_seeded_ik(target, label)
        current_positions = self.current_arm_positions()
        self.check_joint_goal_quality(current_positions, joint_goal, label)
        self.send_joint_goal(joint_goal, label)

    def send_move_group_goal(self, target_pose, label, position_tolerance):
        if not self.move_group_client.wait_for_server(timeout_sec=10.0):
            raise RuntimeError(f"{label}: /move_action server is not available")

        goal = MoveGroup.Goal()
        goal.request = self.make_motion_plan_request(target_pose, position_tolerance)
        goal.planning_options.plan_only = False
        goal.planning_options.look_around = False
        goal.planning_options.replan = True
        goal.planning_options.replan_attempts = 2
        goal.planning_options.replan_delay = 0.2

        future = self.move_group_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        goal_handle = future.result()
        if not goal_handle or not goal_handle.accepted:
            raise RuntimeError(f"{label}: MoveGroup goal was rejected")

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result()
        if result.status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError(f"{label}: MoveGroup action failed with status {result.status}")
        if result.result.error_code.val != 1:
            raise RuntimeError(
                f"{label}: MoveIt failed with error_code {result.result.error_code.val}"
            )
        final_pose = self.get_tcp_pose()
        self.get_logger().info(
            f"{label}: final gripper_tcp "
            f"x={final_pose.position.x:.3f} y={final_pose.position.y:.3f} "
            f"z={final_pose.position.z:.3f} "
            f"qx={final_pose.orientation.x:.4f} qy={final_pose.orientation.y:.4f} "
            f"qz={final_pose.orientation.z:.4f} qw={final_pose.orientation.w:.4f}"
        )

    def compute_seeded_ik(self, target_pose, label):
        if not self.compute_ik_client.wait_for_service(timeout_sec=10.0):
            raise RuntimeError(f"{label}: /compute_ik service is not available")

        current_joint_state = self.get_current_joint_state()
        request = GetPositionIK.Request()
        request.ik_request.group_name = "ur_manipulator"
        request.ik_request.robot_state.joint_state = current_joint_state
        request.ik_request.avoid_collisions = False
        request.ik_request.ik_link_name = "gripper_tcp"
        request.ik_request.pose_stamped.header.frame_id = "world"
        request.ik_request.pose_stamped.pose = target_pose
        request.ik_request.timeout.sec = 1

        future = self.compute_ik_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        if response is None:
            raise RuntimeError(f"{label}: compute_ik returned no response")
        if response.error_code.val != 1:
            raise RuntimeError(f"{label}: compute_ik failed with error_code {response.error_code.val}")

        solution = {}
        for name, position in zip(response.solution.joint_state.name, response.solution.joint_state.position):
            if name in ARM_JOINTS:
                solution[name] = position
        missing = [joint for joint in ARM_JOINTS if joint not in solution]
        if missing:
            raise RuntimeError(f"{label}: IK solution missing joints: {missing}")

        self.get_logger().info(
            f"{label}: seeded IK joint goal "
            + json.dumps({joint: round(solution[joint], 4) for joint in ARM_JOINTS})
        )
        return solution

    def get_current_joint_state(self):
        deadline = self.get_clock().now() + Duration(seconds=5.0)
        while rclpy.ok() and self.latest_joint_state is None:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self.get_clock().now() > deadline:
                raise RuntimeError("timed out waiting for /joint_states")
        return self.latest_joint_state

    def current_arm_positions(self):
        joint_state = self.get_current_joint_state()
        positions = dict(zip(joint_state.name, joint_state.position))
        missing = [joint for joint in ARM_JOINTS if joint not in positions]
        if missing:
            raise RuntimeError(f"/joint_states missing arm joints: {missing}")
        return {joint: positions[joint] for joint in ARM_JOINTS}

    def check_joint_goal_quality(self, current_positions, joint_goal, label):
        deltas = {
            joint: abs(self.shortest_angular_distance(current_positions[joint], joint_goal[joint]))
            for joint in ARM_JOINTS
        }
        self.get_logger().info(
            f"{label}: joint deltas "
            + json.dumps({joint: round(deltas[joint], 4) for joint in ARM_JOINTS})
        )
        max_delta = max(deltas.values())
        if max_delta > 2.8:
            raise RuntimeError(
                f"{label}: IK goal rejected by quality gate; max joint delta {max_delta:.3f} rad"
            )

    @staticmethod
    def shortest_angular_distance(a, b):
        return math.atan2(math.sin(b - a), math.cos(b - a))

    def send_joint_goal(self, joint_goal, label):
        if not self.move_group_client.wait_for_server(timeout_sec=10.0):
            raise RuntimeError(f"{label}: /move_action server is not available")

        goal = MoveGroup.Goal()
        goal.request = self.make_joint_goal_motion_plan_request(joint_goal)
        goal.planning_options.plan_only = False
        goal.planning_options.look_around = False
        goal.planning_options.replan = True
        goal.planning_options.replan_attempts = 2
        goal.planning_options.replan_delay = 0.2

        future = self.move_group_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        goal_handle = future.result()
        if not goal_handle or not goal_handle.accepted:
            raise RuntimeError(f"{label}: joint-goal MoveGroup goal was rejected")

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result()
        if result.status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError(f"{label}: joint-goal MoveGroup action failed with status {result.status}")
        if result.result.error_code.val != 1:
            raise RuntimeError(
                f"{label}: joint-goal MoveIt failed with error_code {result.result.error_code.val}"
            )

        final_pose = self.get_tcp_pose()
        self.get_logger().info(
            f"{label}: final gripper_tcp "
            f"x={final_pose.position.x:.3f} y={final_pose.position.y:.3f} "
            f"z={final_pose.position.z:.3f} "
            f"qx={final_pose.orientation.x:.4f} qy={final_pose.orientation.y:.4f} "
            f"qz={final_pose.orientation.z:.4f} qw={final_pose.orientation.w:.4f}"
        )

    def make_joint_goal_motion_plan_request(self, joint_goal):
        request = MotionPlanRequest()
        request.group_name = "ur_manipulator"
        request.start_state.joint_state = self.get_current_joint_state()
        request.num_planning_attempts = 10
        request.allowed_planning_time = 5.0
        request.max_velocity_scaling_factor = 0.25
        request.max_acceleration_scaling_factor = 0.25
        request.workspace_parameters.header.frame_id = "world"
        request.workspace_parameters.min_corner.x = -1.0
        request.workspace_parameters.min_corner.y = -1.0
        request.workspace_parameters.min_corner.z = -0.1
        request.workspace_parameters.max_corner.x = 1.0
        request.workspace_parameters.max_corner.y = 1.0
        request.workspace_parameters.max_corner.z = 1.4

        constraints = Constraints()
        constraints.name = "seeded_ik_joint_goal"
        for joint in ARM_JOINTS:
            joint_constraint = JointConstraint()
            joint_constraint.joint_name = joint
            joint_constraint.position = joint_goal[joint]
            joint_constraint.tolerance_above = 0.01
            joint_constraint.tolerance_below = 0.01
            joint_constraint.weight = 1.0
            constraints.joint_constraints.append(joint_constraint)
        request.goal_constraints.append(constraints)
        return request

    def compute_and_execute_cartesian_path(self, target_pose, label):
        if not self.cartesian_path_client.wait_for_service(timeout_sec=10.0):
            raise RuntimeError(f"{label}: /compute_cartesian_path service is not available")

        request = GetCartesianPath.Request()
        request.header.frame_id = "world"
        request.start_state.is_diff = True
        request.group_name = "ur_manipulator"
        request.link_name = "gripper_tcp"
        request.waypoints = [target_pose]
        request.max_step = 0.005
        request.jump_threshold = 0.0
        request.avoid_collisions = False

        future = self.cartesian_path_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        if response is None:
            raise RuntimeError(f"{label}: compute_cartesian_path returned no response")
        if response.error_code.val != 1:
            raise RuntimeError(
                f"{label}: compute_cartesian_path failed with error_code {response.error_code.val}"
            )
        if response.fraction < 0.95:
            raise RuntimeError(f"{label}: Cartesian path fraction only {response.fraction:.3f}")

        self.execute_trajectory(response.solution, label)
        final_pose = self.get_tcp_pose()
        self.get_logger().info(
            f"{label}: final gripper_tcp "
            f"x={final_pose.position.x:.3f} y={final_pose.position.y:.3f} "
            f"z={final_pose.position.z:.3f} "
            f"qx={final_pose.orientation.x:.4f} qy={final_pose.orientation.y:.4f} "
            f"qz={final_pose.orientation.z:.4f} qw={final_pose.orientation.w:.4f}"
        )

    def execute_trajectory(self, trajectory, label):
        if not self.execute_trajectory_client.wait_for_server(timeout_sec=10.0):
            raise RuntimeError(f"{label}: /execute_trajectory action server is not available")

        goal = ExecuteTrajectory.Goal()
        goal.trajectory = trajectory
        future = self.execute_trajectory_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        goal_handle = future.result()
        if not goal_handle or not goal_handle.accepted:
            raise RuntimeError(f"{label}: ExecuteTrajectory goal was rejected")

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result()
        if result.status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError(f"{label}: ExecuteTrajectory failed with status {result.status}")
        if result.result.error_code.val != 1:
            raise RuntimeError(
                f"{label}: ExecuteTrajectory failed with error_code {result.result.error_code.val}"
            )

    def make_motion_plan_request(self, target_pose, position_tolerance):
        request = MotionPlanRequest()
        request.group_name = "ur_manipulator"
        request.start_state.is_diff = True
        request.num_planning_attempts = 10
        request.allowed_planning_time = 5.0
        request.max_velocity_scaling_factor = 0.25
        request.max_acceleration_scaling_factor = 0.25
        request.workspace_parameters.header.frame_id = "world"
        request.workspace_parameters.min_corner.x = -1.0
        request.workspace_parameters.min_corner.y = -1.0
        request.workspace_parameters.min_corner.z = -0.1
        request.workspace_parameters.max_corner.x = 1.0
        request.workspace_parameters.max_corner.y = 1.0
        request.workspace_parameters.max_corner.z = 1.4
        request.goal_constraints.append(self.make_pose_constraints(target_pose, position_tolerance))
        return request

    def make_pose_constraints(self, target_pose, position_tolerance):
        constraints = Constraints()
        constraints.name = "gripper_tcp_pose_goal"

        sphere = SolidPrimitive()
        sphere.type = SolidPrimitive.SPHERE
        sphere.dimensions = [position_tolerance]

        position_constraint = PositionConstraint()
        position_constraint.header.frame_id = "world"
        position_constraint.link_name = "gripper_tcp"
        position_constraint.constraint_region.primitives.append(sphere)
        position_constraint.constraint_region.primitive_poses.append(target_pose)
        position_constraint.weight = 1.0

        orientation_constraint = self.make_orientation_constraint(
            target_pose,
            tolerance=0.03,
            weight=1.0,
        )

        constraints.position_constraints.append(position_constraint)
        constraints.orientation_constraints.append(orientation_constraint)
        return constraints

    def make_orientation_constraint(self, target_pose, tolerance, weight):
        orientation_constraint = OrientationConstraint()
        orientation_constraint.header.frame_id = "world"
        orientation_constraint.link_name = "gripper_tcp"
        orientation_constraint.orientation = target_pose.orientation
        orientation_constraint.absolute_x_axis_tolerance = tolerance
        orientation_constraint.absolute_y_axis_tolerance = tolerance
        orientation_constraint.absolute_z_axis_tolerance = tolerance
        orientation_constraint.parameterization = OrientationConstraint.ROTATION_VECTOR
        orientation_constraint.weight = weight
        return orientation_constraint

    def command_gripper(self, position, label):
        positions = [position * sign for sign in GRIPPER_SIGNS]
        self.send_trajectory(
            self.gripper_client,
            GRIPPER_JOINTS,
            positions,
            duration_sec=2,
            label=label,
        )

    def send_trajectory(self, client, joints, positions, duration_sec, label):
        if not client.wait_for_server(timeout_sec=10.0):
            raise RuntimeError(f"{label}: FollowJointTrajectory action server is not available")

        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = joints
        point = JointTrajectoryPoint()
        point.positions = positions
        point.time_from_start.sec = duration_sec
        goal.trajectory.points.append(point)

        future = client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        goal_handle = future.result()
        if not goal_handle or not goal_handle.accepted:
            raise RuntimeError(f"{label}: trajectory goal was rejected")

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result()
        if result.status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError(f"{label}: trajectory failed with action status {result.status}")

    def attach_object(self, object_name):
        if object_name not in OBJECTS:
            raise RuntimeError(f"unknown object: {object_name}")

        set_parameters = self.create_client(SetParameters, "/sim_grasp_adapter/set_parameters")
        if not set_parameters.wait_for_service(timeout_sec=5.0):
            raise RuntimeError("/sim_grasp_adapter/set_parameters service is not available")

        request = SetParameters.Request()
        request.parameters = [
            Parameter("target_object", Parameter.Type.STRING, object_name).to_parameter_msg()
        ]
        future = set_parameters.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        result = future.result()
        if result is None or not result.results[0].successful:
            reason = "" if result is None else result.results[0].reason
            raise RuntimeError(f"failed to set target object: {reason}")

        self.trigger("/sim_grasp_adapter/attach_target")

    def trigger(self, service_name):
        client = self.create_client(Trigger, service_name)
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError(f"{service_name} service is not available")
        future = client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future)
        result = future.result()
        if result is None:
            raise RuntimeError(f"{service_name} returned no response")
        if not result.success:
            raise RuntimeError(f"{service_name} failed: {result.message}")
        self.get_logger().info(result.message)

    def get_entity_pose(self, name):
        if not self.get_entity_client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError("/gazebo/get_entity_state service is not available")
        request = GetEntityState.Request()
        request.name = name
        request.reference_frame = "world"
        future = self.get_entity_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        if response is None or not response.success:
            message = "no response" if response is None else "entity not found"
            raise RuntimeError(f"failed to read {name}: {message}")
        return response.state.pose


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_json", help="Path to a JSON skill plan.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the plan against skill_library without executing ROS actions/services.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    with open(args.plan_json, "r", encoding="utf-8") as stream:
        plan = json.load(stream)

    rclpy.init()
    node = SkillPlanExecutor()
    try:
        if args.validate_only:
            node.validate_plan(plan)
            node.get_logger().info("plan validation succeeded")
        else:
            node.execute_plan(plan)
    except (PlanValidationError, RuntimeError) as exc:
        node.get_logger().error(str(exc))
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
