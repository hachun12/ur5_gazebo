# System Architecture

本文件整理目前 UR5 Gazebo 專案的系統架構、資料流、prompt/skill 設計，以及未來擴充 skill 的位置。

## Goal

目前系統目標是讓使用者用自然語言描述桌面操作任務，例如「把藍色方塊疊到綠色方塊上」，系統將任務轉成一串可驗證的 robot skills，並在 Gazebo + MoveIt2 模擬環境中逐步執行。

系統刻意把「任務規劃」和「機器人控制」分開：

- LLM planner 只負責產生 JSON skill plan。
- Validator 只負責檢查 skill 名稱、順序與參數 schema。
- Executor 才負責呼叫 ROS 2 / Gazebo / MoveIt2 執行動作。

這樣做可以降低 LLM 直接控制機器人的風險，也方便未來替換模型、調整 prompt 或新增 skill。

## High-Level Flow

```text
User
  |
  v
Web Task UI / CLI
  |
  v
generate_skill_plan.py
  | reads
  |-- skill_library/config/skills/*.yaml
  |-- skill_library/config/planning/prompt_policy.yaml
  |
  v
LLM provider
  |-- OpenAI API
  |-- Ollama local model
  |
  v
JSON skill plan
  |
  v
execute_skill_plan.py
  | validates with skill YAML schemas
  | executes skill_<skill_id>() handlers
  |
  v
ROS 2 / Gazebo / MoveIt2
  |-- Gazebo entity state
  |-- ros2_control trajectory controllers
  |-- MoveIt2 planning and execution
  |-- sim grasp attach/detach adapter
```

## ROS Packages

### `ur5_description`

Defines the robot model:

- UR5 URDF/xacro.
- Robotiq 2F-85 gripper model.
- Meshes and RViz display config.
- ros2_control tags used by simulation controllers.

Important paths:

```text
src/ur5_description/urdf/
src/ur5_description/meshes/
src/ur5_description/rviz/
```

### `ur5_gazebo`

Owns the simulation bringup:

- Gazebo world.
- ros2_control controller config.
- UR5 + gripper simulation launch.
- Full bringup launch that can start Gazebo, MoveIt2, and RViz2 together.
- Utility scripts for smoke tests and simulated grasp attach/detach.

Important entry points:

```bash
ros2 launch ur5_gazebo sim.launch.py
ros2 launch ur5_gazebo full_bringup.launch.py
ros2 run ur5_gazebo print_world_state.py
ros2 run ur5_gazebo grasp_target.py attach blue_block
ros2 run ur5_gazebo grasp_target.py detach
```

### `ur5_moveit_config`

Contains MoveIt2 configuration:

- SRDF.
- Kinematics config.
- OMPL planning config.
- MoveIt controller config.
- RViz MoveIt launch.

Important entry point:

```bash
ros2 launch ur5_moveit_config moveit_rviz.launch.py
```

### `moveit_skill_server`

Provides a small MoveIt service wrapper:

```text
src/moveit_skill_server/srv/MoveToPose.srv
src/moveit_skill_server/src/moveit_skill_server_node.cpp
```

It wraps `MoveGroupInterface` for `ur_manipulator` and exposes a `move_to_pose` style service. The current Python executor mostly talks to MoveIt actions/services directly, but this package remains useful as a future clean interface for pose-level skills.

### `skill_library`

Defines the skill catalog and planning policy. This package does not execute skills by itself. It stores metadata used by the planner and executor.

Skill schemas:

```text
src/skill_library/config/skills/*.yaml
```

Prompt policy:

```text
src/skill_library/config/planning/prompt_policy.yaml
```

`CMakeLists.txt` installs the whole `config/` directory into the ROS package share path, so `ros2 run` tools can load these files after `colcon build`.

### `task_executor`

Contains the task-level tools:

```text
src/task_executor/scripts/generate_skill_plan.py
src/task_executor/scripts/execute_skill_plan.py
src/task_executor/scripts/web_task_ui.py
src/task_executor/examples/*.json
```

Responsibilities:

- Generate skill plans from natural language.
- Validate skill plans against `skill_library`.
- Execute skill plans in ROS 2.
- Provide a Web UI for plan generation, validation, execution status, logs, and local speech-to-text.

## Planner Architecture

Planner entry point:

```bash
ros2 run task_executor generate_skill_plan.py "<task>"
```

The planner performs these steps:

1. Load skill schemas from `skill_library/config/skills/*.yaml`.
2. Load prompt policy from `skill_library/config/planning/prompt_policy.yaml`.
3. Load world state from `--world-state-file`, or use a built-in tabletop default.
4. Build a prompt containing:
   - user command
   - available objects and regions
   - allowed skill registry
   - atomic skill policy
   - task recipes
5. Send prompt to OpenAI API or local Ollama.
6. Parse LLM output as JSON.
7. Validate plan locally.
8. Optionally repair invalid output by asking the model again.
9. Print or save the final JSON skill plan.

Supported providers:

```bash
--provider openai
--provider ollama
```

Useful commands:

```bash
ros2 run task_executor generate_skill_plan.py \
  "把藍色方塊疊到綠色方塊上" \
  --provider ollama \
  --model gemma4:latest \
  --output /tmp/stack_blue_on_green.json
```

Dry-run only prints the prompt:

```bash
ros2 run task_executor generate_skill_plan.py \
  "把藍色方塊疊到綠色方塊上" \
  --dry-run
```

## Prompt Policy

Prompt behavior is configured here:

```text
src/skill_library/config/planning/prompt_policy.yaml
```

This file controls:

- Planner role.
- General rules.
- Atomic skill allow-list.
- Default numeric parameters.
- Recipes for common tasks such as pick, place, and stack.

Example responsibilities:

```yaml
atomic_skills:
  - observe_scene
  - move_above_object
  - move_to_object
  - close_gripper
  - attach_object
  - lift
  - detach_object
  - verify_relation
```

The prompt policy is where we teach the LLM how to combine skills. The skill YAML files define what skills exist and what arguments they accept.

## Skill Library

Each skill YAML file defines a skill id, description, and argument schema. Example:

```text
src/skill_library/config/skills/move_above_object.yaml
src/skill_library/config/skills/close_gripper.yaml
src/skill_library/config/skills/attach_object.yaml
```

The YAML files are used by:

- `generate_skill_plan.py` to tell the LLM which skills are available.
- `generate_skill_plan.py` local validation after LLM output.
- `execute_skill_plan.py` validation before execution.
- Web UI validation and execution endpoints through the same scripts.

They do not execute robot motion by themselves. Execution is implemented in Python methods named:

```text
skill_<skill_id>()
```

inside:

```text
src/task_executor/scripts/execute_skill_plan.py
```

For example:

```text
skill_move_above_object()
skill_move_to_object()
skill_close_gripper()
skill_attach_object()
skill_verify_relation()
```

## Skill Plan Format

A generated plan is a JSON object with consecutive numbered steps:

```json
{
  "task_id": "stack_blue_on_green",
  "user_command": "把藍色方塊疊到綠色方塊上",
  "plan": [
    {
      "step": 1,
      "skill": "observe_scene",
      "args": {}
    },
    {
      "step": 2,
      "skill": "move_above_object",
      "args": {
        "object": "blue_block",
        "z_offset": 0.16
      }
    }
  ]
}
```

Validation checks:

- `plan` must be a list.
- Step numbers must start at 1 and be consecutive.
- Skill id must exist in `skill_library`.
- Required args must be present.
- Arg types and enum values must match the YAML schema.
- By default, only atomic skills are allowed during LLM planning.

## Executor Architecture

Executor entry point:

```bash
ros2 run task_executor execute_skill_plan.py /tmp/plan.json
```

Validation only:

```bash
ros2 run task_executor execute_skill_plan.py /tmp/plan.json --validate-only
```

Execution flow:

1. Load skill registry from `skill_library`.
2. Validate plan schema.
3. For each step, find `skill_<skill_id>()`.
4. Execute the skill handler.
5. Log each step for CLI and Web UI status tracking.

Current executor interfaces include:

- `/gazebo/get_entity_state` for object poses.
- `/ur5_arm_controller/follow_joint_trajectory` for arm joint commands.
- `/robotiq_gripper_controller/follow_joint_trajectory` for gripper commands.
- `/move_action`, `/execute_trajectory`, `/compute_cartesian_path`, `/compute_ik` for MoveIt2 planning/execution.
- `/sim_grasp_adapter/detach` and related attach/detach behavior for simulated grasping.
- `/joint_states` and TF for current robot state.

## Web UI Architecture

Web UI entry point:

```bash
ros2 run task_executor web_task_ui.py
```

Open:

```text
http://127.0.0.1:8080
```

The Web UI provides:

- Provider selection: OpenAI or Ollama.
- Model selection.
- Natural language task input.
- Local speech-to-text input.
- Generate plan.
- Validate plan.
- Execute plan.
- Skill cards showing step order and live status.
- Highlight for validation or execution failures.
- Fixed log panel.

The UI calls local HTTP endpoints in `web_task_ui.py`, which shell out to the same planner and executor scripts. This keeps CLI and UI behavior aligned.

Execution status is tracked from executor logs. When a step starts, the corresponding skill card becomes running. When the next step starts, the previous step is marked complete. If the process exits with an error, the current running step is marked failed.

## World State

Current world state support has two modes:

1. Built-in symbolic default used by `generate_skill_plan.py`.
2. Gazebo ground-truth export using:

```bash
ros2 run ur5_gazebo print_world_state.py > /tmp/world_state.json
```

Planner can consume the exported world state:

```bash
ros2 run task_executor generate_skill_plan.py \
  "把藍色方塊拿到左邊" \
  --world-state-file /tmp/world_state.json
```

The current object and region names are intentionally fixed so the LLM cannot invent arbitrary scene entities.

Objects:

```text
red_block
green_block
blue_block
green_ball
```

Regions:

```text
left_region
center_region
right_region
front_region
```

## Local LLM And OpenAI

The planner can use either remote or local models:

- OpenAI API for higher-quality cloud planning.
- Ollama for offline local planning.

OpenAI requires:

```bash
export OPENAI_API_KEY="your API key"
```

Ollama example:

```bash
ollama run gemma4:latest
```

Then:

```bash
ros2 run task_executor generate_skill_plan.py \
  "把藍色方塊疊到綠色方塊上" \
  --provider ollama \
  --model gemma4:latest
```

## Extension Guide

### Add A New Skill

1. Add a schema file:

```text
src/skill_library/config/skills/<skill_id>.yaml
```

2. Implement the executor handler:

```text
src/task_executor/scripts/execute_skill_plan.py
```

Handler name:

```text
skill_<skill_id>()
```

3. If the LLM should use it directly, add it to:

```text
src/skill_library/config/planning/prompt_policy.yaml
```

4. If it belongs to a common task, add or update a recipe in `prompt_policy.yaml`.

5. Rebuild:

```bash
colcon build --symlink-install --packages-select skill_library task_executor
source install/setup.bash
```

6. Test in stages:

```bash
ros2 run task_executor generate_skill_plan.py "<task>" --dry-run
ros2 run task_executor generate_skill_plan.py "<task>" --provider ollama --model gemma4:latest --output /tmp/test_plan.json
ros2 run task_executor execute_skill_plan.py /tmp/test_plan.json --validate-only
ros2 run task_executor execute_skill_plan.py /tmp/test_plan.json
```

### Adjust Prompt Behavior

For most prompt changes, edit only:

```text
src/skill_library/config/planning/prompt_policy.yaml
```

Use this for:

- Changing default offsets or heights.
- Rewriting pick/place/stack recipes.
- Preventing the model from using certain skills.
- Adding examples or stricter rules.

Avoid hardcoding new task-specific behavior directly into `generate_skill_plan.py` unless the behavior is truly part of planner logic rather than prompt policy.

## Current Design Boundaries

Current MVP assumptions:

- Scene objects and named regions are fixed.
- Grasping is simulated with attach/detach helpers.
- LLM planning is symbolic and skill-level, not motion-level.
- Safety is enforced mostly through schema validation and atomic skill allow-list.
- Web UI execution status is inferred from executor logs.

Likely future improvements:

- Replace fixed world state with perception or richer Gazebo state.
- Move more motion execution behind a dedicated skill server API.
- Add preconditions/effects to skill YAML files.
- Add richer validation for task semantics, not only argument schema.
- Store execution history and per-step result metadata.
- Add automated tests for planner output and executor validation.
