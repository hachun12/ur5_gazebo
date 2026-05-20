#!/usr/bin/env python3

import sys

import rclpy
from control_msgs.action import FollowJointTrajectory
from rclpy.action import ActionClient
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectoryPoint


class GripperOpenCloseSender(Node):
    def __init__(self):
        super().__init__("send_gripper_open_close")
        self.client = ActionClient(
            self,
            FollowJointTrajectory,
            "/robotiq_gripper_controller/follow_joint_trajectory",
        )

    def command(self, grip_position):
        joint_vector = [1.0, 1.0, 1.0, 1.0, -1.0, -1.0]

        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = [
            "robotiq_85_left_knuckle_joint",
            "robotiq_85_right_knuckle_joint",
            "robotiq_85_left_inner_knuckle_joint",
            "robotiq_85_right_inner_knuckle_joint",
            "robotiq_85_left_finger_tip_joint",
            "robotiq_85_right_finger_tip_joint",
        ]

        point = JointTrajectoryPoint()
        point.positions = [grip_position * sign for sign in joint_vector]
        point.time_from_start.sec = 2
        goal.trajectory.points.append(point)

        future = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        goal_handle = future.result()
        if not goal_handle or not goal_handle.accepted:
            self.get_logger().error(f"Gripper command {grip_position:.3f} was rejected.")
            return False

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result()
        if result.status != 4:
            self.get_logger().error(f"Gripper command failed with action status {result.status}.")
            return False

        self.get_logger().info(f"Gripper command {grip_position:.3f} completed.")
        return True

    def send(self):
        if not self.client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error("Gripper FollowJointTrajectory action server is not available.")
            return False

        return self.command(0.0) and self.command(0.8) and self.command(0.0)


def main():
    rclpy.init()
    node = GripperOpenCloseSender()
    ok = node.send()
    node.destroy_node()
    rclpy.shutdown()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
