#!/usr/bin/env python3

import json
import sys

import rclpy
from gazebo_msgs.srv import GetEntityState
from rclpy.node import Node


OBJECTS = {
    "red_block": {
        "type": "block",
        "color": "red",
        "size": [0.05, 0.05, 0.05],
    },
    "green_block": {
        "type": "block",
        "color": "green",
        "size": [0.05, 0.05, 0.05],
    },
    "blue_block": {
        "type": "block",
        "color": "blue",
        "size": [0.05, 0.05, 0.05],
    },
    "green_ball": {
        "type": "sphere",
        "color": "green",
        "radius": 0.03,
    },
}


class WorldStatePrinter(Node):
    def __init__(self):
        super().__init__("print_world_state")
        self.client = self.create_client(GetEntityState, "/gazebo/get_entity_state")

    def get_entity(self, name):
        request = GetEntityState.Request()
        request.name = name
        request.reference_frame = "world"
        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        if response is None or not response.success:
            message = "" if response is None else response.status_message
            raise RuntimeError(f"failed to get entity state for {name}: {message}")
        return response.state

    def build_state(self):
        if not self.client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError("/gazebo/get_entity_state service is not available")

        objects = {}
        for name, metadata in OBJECTS.items():
            entity_state = self.get_entity(name)
            pose = entity_state.pose
            twist = entity_state.twist
            objects[name] = {
                **metadata,
                "frame_id": "world",
                "pose": {
                    "position": {
                        "x": pose.position.x,
                        "y": pose.position.y,
                        "z": pose.position.z,
                    },
                    "orientation": {
                        "x": pose.orientation.x,
                        "y": pose.orientation.y,
                        "z": pose.orientation.z,
                        "w": pose.orientation.w,
                    },
                },
                "twist": {
                    "linear": {
                        "x": twist.linear.x,
                        "y": twist.linear.y,
                        "z": twist.linear.z,
                    },
                    "angular": {
                        "x": twist.angular.x,
                        "y": twist.angular.y,
                        "z": twist.angular.z,
                    },
                },
            }

        return {
            "frame_id": "world",
            "source": "gazebo_ground_truth",
            "objects": objects,
        }


def main():
    rclpy.init()
    node = WorldStatePrinter()
    try:
        state = node.build_state()
        print(json.dumps(state, indent=2, sort_keys=True))
    except RuntimeError as exc:
        node.get_logger().error(str(exc))
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
