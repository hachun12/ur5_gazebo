#!/usr/bin/env python3

import math
import sys

import rclpy
from control_msgs.action import FollowJointTrajectory
from rclpy.action import ActionClient
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectoryPoint


class ReadyTrajectorySender(Node):
    def __init__(self):
        super().__init__("send_ready_trajectory")
        self.client = ActionClient(
            self,
            FollowJointTrajectory,
            "/ur5_arm_controller/follow_joint_trajectory",
        )

    def send(self):
        if not self.client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error("FollowJointTrajectory action server is not available.")
            return False

        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = [
            "shoulder_pan_joint",
            "shoulder_lift_joint",
            "elbow_joint",
            "wrist_1_joint",
            "wrist_2_joint",
            "wrist_3_joint",
        ]

        ready_pose = [
            0.0,
            -math.pi / 2.0,
            math.pi / 2.0,
            -math.pi / 2.0,
            -math.pi / 2.0,
            0.0,
        ]

        visible_test_pose = [
            0.35,
            -1.35,
            1.25,
            -1.45,
            -math.pi / 2.0,
            0.25,
        ]

        point_1 = JointTrajectoryPoint()
        point_1.positions = visible_test_pose
        point_1.time_from_start.sec = 3
        goal.trajectory.points.append(point_1)

        point_2 = JointTrajectoryPoint()
        point_2.positions = ready_pose
        point_2.time_from_start.sec = 6
        goal.trajectory.points.append(point_2)

        future = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        goal_handle = future.result()
        if not goal_handle or not goal_handle.accepted:
            self.get_logger().error("Trajectory goal was rejected.")
            return False

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result()
        if result.status != 4:
            self.get_logger().error(f"Trajectory failed with action status {result.status}.")
            return False

        self.get_logger().info("Visible test trajectory completed.")
        return True


def main():
    rclpy.init()
    node = ReadyTrajectorySender()
    ok = node.send()
    node.destroy_node()
    rclpy.shutdown()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
