#include <memory>
#include <sstream>
#include <string>

#include <moveit/move_group_interface/move_group_interface.h>
#include <rclcpp/rclcpp.hpp>

#include "moveit_skill_server/srv/move_to_pose.hpp"

class MoveItSkillServer : public rclcpp::Node
{
public:
  using MoveToPose = moveit_skill_server::srv::MoveToPose;

  explicit MoveItSkillServer(const rclcpp::NodeOptions & options)
  : Node("moveit_skill_server", options)
  {
  }

  void initialize()
  {
    move_group_ = std::make_shared<moveit::planning_interface::MoveGroupInterface>(
      shared_from_this(), "ur_manipulator");
    move_group_->setEndEffectorLink("gripper_tcp");
    move_group_->setPlannerId("RRTConnectkConfigDefault");
    move_group_->allowReplanning(true);
    move_group_->setNumPlanningAttempts(10);

    move_to_pose_service_ = create_service<MoveToPose>(
      "~/move_to_pose",
      std::bind(&MoveItSkillServer::moveToPose, this, std::placeholders::_1, std::placeholders::_2));

    RCLCPP_INFO(get_logger(), "moveit_skill_server ready for group ur_manipulator");
  }

private:
  void moveToPose(
    const std::shared_ptr<MoveToPose::Request> request,
    std::shared_ptr<MoveToPose::Response> response)
  {
    const std::string link_name = request->link_name.empty() ? "gripper_tcp" : request->link_name;
    const double planning_time = request->planning_time > 0.0 ? request->planning_time : 5.0;
    const double velocity_scaling = clampScaling(request->velocity_scaling, 0.25);
    const double acceleration_scaling = clampScaling(request->acceleration_scaling, 0.25);

    move_group_->setStartStateToCurrentState();
    move_group_->setPlanningTime(planning_time);
    move_group_->setMaxVelocityScalingFactor(velocity_scaling);
    move_group_->setMaxAccelerationScalingFactor(acceleration_scaling);
    move_group_->setPoseReferenceFrame(request->target_pose.header.frame_id);
    move_group_->setEndEffectorLink(link_name);
    move_group_->setPoseTarget(request->target_pose, link_name);

    RCLCPP_INFO(
      get_logger(),
      "move_to_pose target %s in %s: x=%.3f y=%.3f z=%.3f qx=%.4f qy=%.4f qz=%.4f qw=%.4f",
      link_name.c_str(),
      request->target_pose.header.frame_id.c_str(),
      request->target_pose.pose.position.x,
      request->target_pose.pose.position.y,
      request->target_pose.pose.position.z,
      request->target_pose.pose.orientation.x,
      request->target_pose.pose.orientation.y,
      request->target_pose.pose.orientation.z,
      request->target_pose.pose.orientation.w);

    moveit::planning_interface::MoveGroupInterface::Plan plan;
    const auto plan_result = move_group_->plan(plan);
    if (plan_result != moveit::core::MoveItErrorCode::SUCCESS) {
      response->success = false;
      response->message = "MoveIt planning failed";
      move_group_->clearPoseTargets();
      return;
    }

    if (request->execute) {
      const auto execute_result = move_group_->execute(plan);
      if (execute_result != moveit::core::MoveItErrorCode::SUCCESS) {
        response->success = false;
        response->message = "MoveIt execution failed";
        move_group_->clearPoseTargets();
        return;
      }
    }

    response->success = true;
    response->message = request->execute ? "planned and executed" : "planned";
    move_group_->clearPoseTargets();
  }

  static double clampScaling(double value, double fallback)
  {
    if (value <= 0.0 || value > 1.0) {
      return fallback;
    }
    return value;
  }

  std::shared_ptr<moveit::planning_interface::MoveGroupInterface> move_group_;
  rclcpp::Service<MoveToPose>::SharedPtr move_to_pose_service_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<MoveItSkillServer>(
    rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));
  node->initialize();
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(node);
  executor.spin();
  rclcpp::shutdown();
  return 0;
}
