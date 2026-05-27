# M6 LLM Planner

本階段新增 LLM plan generator。它不直接控制 ROS action/topic，只負責把自然語言任務轉成 JSON skill plan，再交給 `task_executor` 驗證與執行。

目前支援兩條路線：

- `openai`：快速概念驗證用，預設 provider。
- `ollama`：未來本地端部署用，保留同一套 prompt/validator。

## Package Entry Point

```bash
ros2 run task_executor generate_skill_plan.py "<user command>"
```

預設設定：

```text
provider: openai
model: gpt-5.2
output policy: atomic skills only
```

使用 OpenAI API 前需設定：

```bash
export OPENAI_API_KEY="你的 API key"
```

快速產生 plan：

```bash
ros2 run task_executor generate_skill_plan.py \
  "把藍色方塊疊到綠色方塊上" \
  --provider openai \
  --model gpt-5.2
```

若要切回本地 Ollama：

```bash
ros2 run task_executor generate_skill_plan.py \
  "把藍色方塊疊到綠色方塊上" \
  --provider ollama \
  --model gemma4:latest
```

若尚未確認 LLM provider 可用，可以先只印 prompt：

```bash
ros2 run task_executor generate_skill_plan.py \
  "把藍色方塊疊到綠色方塊上" \
  --dry-run
```

## Generate And Save Plan

```bash
ros2 run task_executor generate_skill_plan.py \
  "把藍色方塊疊到綠色方塊上" \
  --provider openai \
  --output /tmp/stack_blue_on_green.json
```

生成後再次用 executor 驗證：

```bash
ros2 run task_executor execute_skill_plan.py \
  /tmp/stack_blue_on_green.json \
  --validate-only
```

Gazebo + MoveIt 啟動後執行：

```bash
ros2 run task_executor execute_skill_plan.py \
  /tmp/stack_blue_on_green.json
```

## World State Input

M6 初版若不提供 world state file，會使用固定 tabletop symbolic scene：

```text
red_block
green_block
blue_block
green_ball
left_region
center_region
right_region
front_region
```

若要使用 Gazebo ground truth，可先輸出 world state：

```bash
ros2 run ur5_gazebo print_world_state.py > /tmp/world_state.json
```

再提供給 planner：

```bash
ros2 run task_executor generate_skill_plan.py \
  "把藍色方塊拿到左邊" \
  --provider openai \
  --world-state-file /tmp/world_state.json \
  --output /tmp/blue_left.json
```

## Atomic Skill Policy

`generate_skill_plan.py` 預設會拒絕 composite/debug skill，例如：

```text
pick
place
stack
```

LLM 應輸出 atomic skill sequence，例如 stack：

```text
observe_scene
open_gripper
move_above_object(blue_block)
move_to_object(blue_block)
close_gripper
attach_object(blue_block)
lift
move_above_object(green_block)
move_to_object(green_block)
detach_object
open_gripper
verify_relation(on, blue_block, green_block)
```

若只是人工 debug shortcut，可加：

```bash
--allow-composite
```

## Prompt Policy Configuration

Planner prompt policy is loaded from:

```text
src/skill_library/config/planning/prompt_policy.yaml
```

This file controls:

- base planner rules
- atomic skill allow-list
- default planning parameters
- task recipes such as pick, place, and stack

`generate_skill_plan.py` still reads each skill schema from:

```text
src/skill_library/config/skills/*.yaml
```

The skill YAML files define the available skill ids and argument schemas. The
prompt policy explains how the planner should combine those skills for common
tasks.

To test a modified prompt policy without installing it:

```bash
ros2 run task_executor generate_skill_plan.py \
  "把藍色方塊疊到綠色方塊上" \
  --provider ollama \
  --model gemma4:latest \
  --prompt-policy-file src/skill_library/config/planning/prompt_policy.yaml \
  --dry-run
```

After changing the installed policy, rebuild:

```bash
colcon build --symlink-install --packages-select skill_library task_executor
source install/setup.bash
```

## Adding A Skill

Minimum steps:

1. Add `src/skill_library/config/skills/<skill_id>.yaml`.
2. Implement `skill_<skill_id>()` in `src/task_executor/scripts/execute_skill_plan.py`.
3. If the LLM may use it directly, add the skill id to `atomic_skills` in `prompt_policy.yaml`.
4. If it is part of a common task, add or update a recipe in `prompt_policy.yaml`.
5. Run `generate_skill_plan.py --dry-run`, then generate and validate a plan.

## Validation And Repair

Planner 會先做本地 JSON/schema validation：

- plan 必須是 JSON object。
- `plan` 必須是 list。
- step 必須從 1 連續遞增。
- skill 必須存在於 `skill_library`。
- 預設只能使用 atomic skills。
- 必填 args、型別、enum 必須符合 YAML schema。

若 LLM 第一次輸出不合法，`--repair-attempts` 會把錯誤訊息與前次輸出送回 LLM 修正：

```bash
ros2 run task_executor generate_skill_plan.py \
  "把藍色方塊疊到綠色方塊上" \
  --repair-attempts 2
```

## Notes

這個 planner 目前是 prompt engineering + validator 的 MVP。OpenAI provider 用來快速驗證 TAMP/skill pipeline 是否合理；Ollama provider 則用來保留未來離線部署能力。下一步會接 Web UI，讓使用者可以：

- 輸入文字任務。
- 查看 world state。
- 查看 LLM 產生的 JSON plan。
- 先 validate，再按鈕執行。
