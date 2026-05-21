#!/usr/bin/env python3

import math
from threading import Event

import rclpy
from gazebo_msgs.msg import EntityState
from gazebo_msgs.srv import GetEntityState, GetLinkProperties, SetEntityState, SetLinkProperties
from geometry_msgs.msg import Pose
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.time import Time
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformException, TransformListener


def quat_normalize(q):
    norm = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
    if norm == 0.0:
        return (0.0, 0.0, 0.0, 1.0)
    return (q[0] / norm, q[1] / norm, q[2] / norm, q[3] / norm)


def quat_conjugate(q):
    return (-q[0], -q[1], -q[2], q[3])


def quat_multiply(a, b):
    return quat_normalize(quat_multiply_raw(a, b))


def quat_multiply_raw(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def rotate_vector(q, v):
    vector_quat = (v[0], v[1], v[2], 0.0)
    rotated = quat_multiply_raw(quat_multiply_raw(q, vector_quat), quat_conjugate(q))
    return (rotated[0], rotated[1], rotated[2])


def compose_pose(parent, child):
    parent_q = pose_quat(parent)
    child_q = pose_quat(child)
    rotated_child_position = rotate_vector(parent_q, pose_xyz(child))
    pose = Pose()
    pose.position.x = parent.position.x + rotated_child_position[0]
    pose.position.y = parent.position.y + rotated_child_position[1]
    pose.position.z = parent.position.z + rotated_child_position[2]
    q = quat_multiply(parent_q, child_q)
    pose.orientation.x = q[0]
    pose.orientation.y = q[1]
    pose.orientation.z = q[2]
    pose.orientation.w = q[3]
    return pose


def inverse_pose(pose):
    q_inv = quat_conjugate(pose_quat(pose))
    negative_position = (-pose.position.x, -pose.position.y, -pose.position.z)
    rotated_position = rotate_vector(q_inv, negative_position)
    result = Pose()
    result.position.x = rotated_position[0]
    result.position.y = rotated_position[1]
    result.position.z = rotated_position[2]
    result.orientation.x = q_inv[0]
    result.orientation.y = q_inv[1]
    result.orientation.z = q_inv[2]
    result.orientation.w = q_inv[3]
    return result


def pose_xyz(pose):
    return (pose.position.x, pose.position.y, pose.position.z)


def pose_quat(pose):
    return quat_normalize((
        pose.orientation.x,
        pose.orientation.y,
        pose.orientation.z,
        pose.orientation.w,
    ))


def distance(a, b):
    ax, ay, az = pose_xyz(a)
    bx, by, bz = pose_xyz(b)
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


class SimGraspAdapter(Node):
    def __init__(self):
        super().__init__("sim_grasp_adapter")
        self.declare_parameter("target_object", "red_block")
        self.declare_parameter("world_frame", "world")
        self.declare_parameter("tcp_frame", "gripper_tcp")
        self.declare_parameter("attach_distance", 0.16)
        self.declare_parameter("update_rate", 50.0)
        self.declare_parameter(
            "debug_updates",
            False,
            ParameterDescriptor(description="Log successful attached-object pose updates."),
        )

        self.callback_group = ReentrantCallbackGroup()
        self.get_entity_client = self.create_client(
            GetEntityState,
            "/gazebo/get_entity_state",
            callback_group=self.callback_group,
        )
        self.set_entity_client = self.create_client(
            SetEntityState,
            "/gazebo/set_entity_state",
            callback_group=self.callback_group,
        )
        self.get_link_properties_client = self.create_client(
            GetLinkProperties,
            "/gazebo/get_link_properties",
            callback_group=self.callback_group,
        )
        self.set_link_properties_client = self.create_client(
            SetLinkProperties,
            "/gazebo/set_link_properties",
            callback_group=self.callback_group,
        )
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.attached_object = None
        self.object_in_tcp = None
        self.attached_link_properties = None
        self.last_set_error = ""
        self.last_link_properties_error = ""
        self.update_count = 0

        self.create_service(
            Trigger,
            "~/attach_target",
            self.attach_target,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "~/detach",
            self.detach,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "~/status",
            self.status,
            callback_group=self.callback_group,
        )

        update_rate = self.get_parameter("update_rate").value
        self.timer = self.create_timer(
            1.0 / update_rate,
            self.update_attached_object,
            callback_group=self.callback_group,
        )

    def get_tcp_pose(self):
        world_frame = self.get_parameter("world_frame").value
        tcp_frame = self.get_parameter("tcp_frame").value
        transform = self.tf_buffer.lookup_transform(
            world_frame,
            tcp_frame,
            Time(),
            timeout=Duration(seconds=0.2),
        )
        pose = Pose()
        pose.position.x = transform.transform.translation.x
        pose.position.y = transform.transform.translation.y
        pose.position.z = transform.transform.translation.z
        pose.orientation = transform.transform.rotation
        return pose

    def get_entity_pose(self, name):
        if not self.get_entity_client.wait_for_service(timeout_sec=1.0):
            raise RuntimeError("/gazebo/get_entity_state service is not available")

        request = GetEntityState.Request()
        request.name = name
        request.reference_frame = self.get_parameter("world_frame").value
        future = self.get_entity_client.call_async(request)
        done = Event()
        future.add_done_callback(lambda _: done.set())
        if not done.wait(timeout=1.0):
            raise RuntimeError(f"timed out waiting for entity state for {name}")
        response = future.result()
        if response is None or not response.success:
            message = "" if response is None else response.status_message
            raise RuntimeError(f"failed to get entity state for {name}: {message}")
        return response.state.pose

    def set_entity_pose(self, name, pose):
        if not self.set_entity_client.wait_for_service(timeout_sec=0.2):
            self.last_set_error = "/gazebo/set_entity_state service is not available"
            self.get_logger().warn(self.last_set_error)
            return False

        state = EntityState()
        state.name = name
        state.reference_frame = self.get_parameter("world_frame").value
        state.pose = pose
        state.twist.linear.x = 0.0
        state.twist.linear.y = 0.0
        state.twist.linear.z = 0.0
        state.twist.angular.x = 0.0
        state.twist.angular.y = 0.0
        state.twist.angular.z = 0.0

        request = SetEntityState.Request()
        request.state = state
        future = self.set_entity_client.call_async(request)
        future.add_done_callback(lambda done: self._on_set_entity_done(done, name, pose))
        return True

    def scoped_link_name(self, model_name):
        return f"{model_name}::link"

    def get_link_properties(self, model_name):
        if not self.get_link_properties_client.wait_for_service(timeout_sec=1.0):
            raise RuntimeError("/gazebo/get_link_properties service is not available")

        request = GetLinkProperties.Request()
        request.link_name = self.scoped_link_name(model_name)
        future = self.get_link_properties_client.call_async(request)
        done = Event()
        future.add_done_callback(lambda _: done.set())
        if not done.wait(timeout=1.0):
            raise RuntimeError(f"timed out waiting for link properties for {model_name}")

        response = future.result()
        if response is None or not response.success:
            message = "" if response is None else response.status_message
            raise RuntimeError(f"failed to get link properties for {model_name}: {message}")
        return response

    def set_link_gravity(self, model_name, gravity_mode, properties=None):
        if not self.set_link_properties_client.wait_for_service(timeout_sec=1.0):
            self.last_link_properties_error = "/gazebo/set_link_properties service is not available"
            self.get_logger().warn(self.last_link_properties_error)
            return False

        if properties is None:
            properties = self.get_link_properties(model_name)

        request = SetLinkProperties.Request()
        request.link_name = self.scoped_link_name(model_name)
        request.com = properties.com
        request.gravity_mode = gravity_mode
        request.mass = properties.mass
        request.ixx = properties.ixx
        request.ixy = properties.ixy
        request.ixz = properties.ixz
        request.iyy = properties.iyy
        request.iyz = properties.iyz
        request.izz = properties.izz

        future = self.set_link_properties_client.call_async(request)
        future.add_done_callback(
            lambda done: self._on_set_link_properties_done(done, model_name, gravity_mode)
        )
        return True

    def _on_set_link_properties_done(self, future, model_name, gravity_mode):
        try:
            result = future.result()
        except Exception as exc:
            self.last_link_properties_error = f"set_link_properties raised for {model_name}: {exc}"
            self.get_logger().warn(self.last_link_properties_error)
            return

        if not result.success:
            self.last_link_properties_error = (
                f"set_link_properties failed for {model_name}: {result.status_message}"
            )
            self.get_logger().warn(self.last_link_properties_error)
            return

        self.last_link_properties_error = ""
        self.get_logger().info(
            f"set {self.scoped_link_name(model_name)} gravity_mode={str(gravity_mode).lower()}"
        )

    def _on_set_entity_done(self, future, name, pose):
        try:
            result = future.result()
        except Exception as exc:
            self.last_set_error = f"set_entity_state raised for {name}: {exc}"
            self.get_logger().warn(self.last_set_error)
            return

        if not result.success:
            self.last_set_error = f"set_entity_state failed for {name}: {result.status_message}"
            self.get_logger().warn(self.last_set_error)
            return

        self.last_set_error = ""
        self.update_count += 1
        if self.get_parameter("debug_updates").value:
            self.get_logger().info(
                f"set {name} pose to x={pose.position.x:.3f} "
                f"y={pose.position.y:.3f} z={pose.position.z:.3f}"
            )

    def attach_target(self, request, response):
        del request
        target_object = self.get_parameter("target_object").value
        try:
            tcp_pose = self.get_tcp_pose()
            object_pose = self.get_entity_pose(target_object)
        except (RuntimeError, TransformException) as exc:
            response.success = False
            response.message = str(exc)
            return response

        attach_distance = self.get_parameter("attach_distance").value
        object_distance = distance(tcp_pose, object_pose)
        if object_distance > attach_distance:
            response.success = False
            response.message = (
                f"{target_object} is {object_distance:.3f} m from gripper_tcp; "
                f"attach_distance is {attach_distance:.3f} m"
            )
            return response

        self.object_in_tcp = compose_pose(inverse_pose(tcp_pose), object_pose)
        self.attached_object = target_object
        try:
            self.attached_link_properties = self.get_link_properties(target_object)
            self.set_link_gravity(target_object, False, self.attached_link_properties)
        except RuntimeError as exc:
            self.last_link_properties_error = str(exc)
            self.get_logger().warn(str(exc))
        self.update_count = 0
        self.set_entity_pose(self.attached_object, object_pose)
        response.success = True
        response.message = f"attached {target_object} to gripper_tcp"
        return response

    def detach(self, request, response):
        del request
        if self.attached_object is None:
            response.success = True
            response.message = "no object is currently attached"
            return response

        detached_object = self.attached_object
        detached_properties = self.attached_link_properties
        self.attached_object = None
        self.object_in_tcp = None
        self.attached_link_properties = None
        if detached_properties is not None:
            self.set_link_gravity(
                detached_object,
                detached_properties.gravity_mode,
                detached_properties,
            )
        response.success = True
        response.message = f"detached {detached_object}"
        return response

    def status(self, request, response):
        del request
        if self.attached_object is None:
            response.success = True
            response.message = "attached_object: none"
            return response

        try:
            tcp_pose = self.get_tcp_pose()
            object_pose = self.get_entity_pose(self.attached_object)
            object_distance = distance(tcp_pose, object_pose)
            response.success = True
            response.message = (
                f"attached_object: {self.attached_object}, "
                f"tcp_to_object: {object_distance:.3f} m, "
                f"updates: {self.update_count}, "
                f"last_set_error: {self.last_set_error or 'none'}, "
                f"last_link_properties_error: {self.last_link_properties_error or 'none'}"
            )
        except (RuntimeError, TransformException) as exc:
            response.success = False
            response.message = str(exc)
        return response

    def update_attached_object(self):
        if self.attached_object is None or self.object_in_tcp is None:
            return

        try:
            tcp_pose = self.get_tcp_pose()
        except TransformException as exc:
            self.get_logger().warn(f"cannot update attached object: {exc}")
            return

        object_pose = compose_pose(tcp_pose, self.object_in_tcp)
        self.set_entity_pose(self.attached_object, object_pose)


def main():
    rclpy.init()
    node = SimGraspAdapter()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    executor.remove_node(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
