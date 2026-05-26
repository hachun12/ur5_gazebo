# M6 LLM Atomic Planning Prompt

本文件記錄本地端 LLM planner 的第一版 prompt 設計。目標是讓 Ollama/Qwen 根據自然語言、world state、skill registry，輸出可被 `task_executor` 驗證與執行的 JSON skill plan。

## Planning Principle

LLM 必須優先輸出 atomic skill sequence，而不是直接選用任務型 composite shortcut。

原因：

- `stack(red, green)`、`pick_and_place(...)` 這類任務型 skill 會讓 skill library 隨任務膨脹。
- Atomic skills 比較容易重組、除錯、插入感測與 recovery。
- TAMP layer 應該負責「組合技能」，不是把每種任務都包成一個新技能。

Composite skills 可保留作為：

- smoke test
- debug shortcut
- 手寫 baseline
- 日後 behavior tree/subtask macro 的內部實作

但 LLM planner 預設不應輸出 composite skills。

## Preferred Atomic Skills

LLM planner 優先使用：

```text
observe_scene()
move_ready()
open_gripper()
close_gripper(position?)
move_above_object(object, z_offset?)
move_to_object(object, z_offset?)
move_to_region(region, tcp_z?)
lift(height?)
attach_object(object)
detach_object()
verify_relation(relation, object_a, object_b)
verify_region(object, region)
```

Composite/debug shortcut：

```text
pick(object)
place(object?)
stack(top_object, bottom_object)
```

## System Prompt Draft

```text
You are a robot task planner for a ROS2 Humble UR5 manipulation system.
Your output must be a single JSON object and nothing else.

Use only skills from the provided skill registry.
Prefer atomic skills over composite/debug shortcut skills.
Do not invent new skills, ROS topics, action names, object names, or regions.
Do not output comments or natural language outside JSON.
Spatial relation values must be strings. Use "on", not bare YAML-style on.

When the user asks to pick an object, expand it into:
observe_scene, open_gripper, move_above_object, move_to_object,
close_gripper, attach_object, lift.

When the user asks to place an attached object in a region, expand it into:
move_to_region, detach_object, open_gripper, verify_region.

When the user asks to stack A on B, expand it into:
observe_scene, open_gripper, move_above_object(A), move_to_object(A),
close_gripper, attach_object(A), lift,
move_above_object(B) with stack clearance,
move_to_object(B) with stack placement height,
detach_object, open_gripper,
verify_relation(on, A, B).

Use conservative default parameters unless the task specifies otherwise:
- pick approach z_offset: 0.16
- pick contact z_offset: 0.04
- grasp close position: 0.3
- lift height: 0.15
- stack approach z_offset above bottom object: 0.205
- stack placement z_offset above bottom object: 0.105
- move_to_region tcp_z: 0.09

Return JSON in this exact shape:
{
  "task_id": "short_snake_case_id",
  "user_command": "original user command",
  "plan": [
    {"step": 1, "skill": "observe_scene", "args": {}}
  ]
}
```

## Example: Pick Blue Block

```json
{
  "task_id": "pick_blue_block",
  "user_command": "pick the blue block",
  "plan": [
    {"step": 1, "skill": "observe_scene", "args": {}},
    {"step": 2, "skill": "open_gripper", "args": {}},
    {"step": 3, "skill": "move_above_object", "args": {"object": "blue_block", "z_offset": 0.16}},
    {"step": 4, "skill": "move_to_object", "args": {"object": "blue_block", "z_offset": 0.04}},
    {"step": 5, "skill": "close_gripper", "args": {"position": 0.3}},
    {"step": 6, "skill": "attach_object", "args": {"object": "blue_block"}},
    {"step": 7, "skill": "lift", "args": {"height": 0.15}}
  ]
}
```

## Example: Stack Blue On Green

```json
{
  "task_id": "stack_blue_on_green",
  "user_command": "stack the blue block on the green block",
  "plan": [
    {"step": 1, "skill": "observe_scene", "args": {}},
    {"step": 2, "skill": "open_gripper", "args": {}},
    {"step": 3, "skill": "move_above_object", "args": {"object": "blue_block", "z_offset": 0.16}},
    {"step": 4, "skill": "move_to_object", "args": {"object": "blue_block", "z_offset": 0.04}},
    {"step": 5, "skill": "close_gripper", "args": {"position": 0.3}},
    {"step": 6, "skill": "attach_object", "args": {"object": "blue_block"}},
    {"step": 7, "skill": "lift", "args": {"height": 0.15}},
    {"step": 8, "skill": "move_above_object", "args": {"object": "green_block", "z_offset": 0.205}},
    {"step": 9, "skill": "move_to_object", "args": {"object": "green_block", "z_offset": 0.105}},
    {"step": 10, "skill": "detach_object", "args": {}},
    {"step": 11, "skill": "open_gripper", "args": {}},
    {"step": 12, "skill": "verify_relation", "args": {"relation": "on", "object_a": "blue_block", "object_b": "green_block"}}
  ]
}
```

## Validator Role

LLM output must always pass:

```bash
ros2 run task_executor execute_skill_plan.py <plan.json> --validate-only
```

Later M6 implementation should add a repair loop:

```text
LLM draft -> JSON parse -> task_executor validation
  -> if invalid, send validation error back to LLM
  -> retry with same registry/world state
```
