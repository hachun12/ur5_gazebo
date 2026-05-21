#!/usr/bin/env python3

import argparse
import sys

import rclpy
from rcl_interfaces.srv import SetParameters
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_srvs.srv import Trigger


class GraspTargetClient(Node):
    def __init__(self):
        super().__init__("grasp_target")

    def set_target_object(self, object_name):
        client = self.create_client(SetParameters, "/sim_grasp_adapter/set_parameters")
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError("/sim_grasp_adapter/set_parameters service is not available")

        request = SetParameters.Request()
        request.parameters = [
            Parameter("target_object", Parameter.Type.STRING, object_name).to_parameter_msg()
        ]
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        result = future.result()
        if result is None or not result.results[0].successful:
            reason = "" if result is None else result.results[0].reason
            raise RuntimeError(f"failed to set target_object: {reason}")

    def trigger(self, service_name):
        client = self.create_client(Trigger, service_name)
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError(f"{service_name} service is not available")

        future = client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future)
        result = future.result()
        if result is None:
            raise RuntimeError(f"{service_name} returned no response")
        return result


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["attach", "detach", "status"])
    parser.add_argument("object", nargs="?", default="red_block")
    return parser.parse_args()


def main():
    args = parse_args()
    rclpy.init()
    node = GraspTargetClient()
    try:
        if args.command == "attach":
            node.set_target_object(args.object)
            result = node.trigger("/sim_grasp_adapter/attach_target")
        elif args.command == "detach":
            result = node.trigger("/sim_grasp_adapter/detach")
        else:
            result = node.trigger("/sim_grasp_adapter/status")
    except RuntimeError as exc:
        node.get_logger().error(str(exc))
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    if result.success:
        node.get_logger().info(result.message)
    else:
        node.get_logger().error(result.message)

    node.destroy_node()
    rclpy.shutdown()
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
