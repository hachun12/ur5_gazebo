#!/usr/bin/env python3

import sys

import rclpy
from moveit_msgs.msg import RobotState
from moveit_msgs.srv import GetStateValidity
from rclpy.node import Node
from sensor_msgs.msg import JointState


class MoveItStartStateChecker(Node):
    def __init__(self):
        super().__init__("check_moveit_start_state")
        self.declare_parameter("group_name", "ur_manipulator")
        self.joint_state = None
        self.create_subscription(JointState, "/joint_states", self._on_joint_state, 10)
        self.client = self.create_client(GetStateValidity, "/check_state_validity")

    def _on_joint_state(self, msg):
        if msg.name:
            self.joint_state = msg

    def wait_for_joint_state(self):
        deadline = self.get_clock().now().nanoseconds + int(10.0 * 1e9)
        while rclpy.ok() and self.joint_state is None:
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.get_clock().now().nanoseconds > deadline:
                self.get_logger().error("Timed out waiting for /joint_states.")
                return False
        return True

    def check(self):
        if not self.client.wait_for_service(timeout_sec=10.0):
            self.get_logger().error("/check_state_validity service is not available. Is move_group running?")
            return 1
        if not self.wait_for_joint_state():
            return 1

        request = GetStateValidity.Request()
        request.group_name = self.get_parameter("group_name").value
        request.robot_state = RobotState()
        request.robot_state.joint_state = self.joint_state

        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if future.result() is None:
            self.get_logger().error("State validity request failed or timed out.")
            return 1

        response = future.result()
        if response.valid:
            self.get_logger().info("Current MoveIt start state is valid.")
            return 0

        self.get_logger().error("Current MoveIt start state is INVALID.")
        if response.contacts:
            self.get_logger().error("Reported collision contacts:")
            for contact in response.contacts[:30]:
                self.get_logger().error(
                    f"  {contact.contact_body_1} <-> {contact.contact_body_2} "
                    f"depth={contact.depth:.6f}"
                )
            if len(response.contacts) > 30:
                self.get_logger().error(f"  ... {len(response.contacts) - 30} more contacts omitted")
        else:
            self.get_logger().error(
                "MoveIt did not return contacts. Check joint bounds in RViz or run with verbose MoveIt logs."
            )
        return 2


def main():
    rclpy.init()
    node = MoveItStartStateChecker()
    try:
        code = node.check()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    sys.exit(code)


if __name__ == "__main__":
    main()
