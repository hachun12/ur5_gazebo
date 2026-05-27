# M7 Web UI MVP

本階段新增一個本地 Web UI，讓使用者用瀏覽器操作 skill planning workflow。

## Start UI

Terminal 1：啟動 Gazebo。

```bash
cd ~/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch ur5_gazebo sim.launch.py
```

Terminal 2：啟動 MoveIt/RViz。

```bash
cd ~/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch ur5_moveit_config moveit_rviz.launch.py
```

Terminal 3：啟動 Web UI。

```bash
cd ~/workspace/ur5_gazebo
source /opt/ros/humble/setup.bash
source install/setup.bash
export OPENAI_API_KEY="你的 API key"
ros2 run task_executor web_task_ui.py
```

瀏覽器開啟：

```text
http://127.0.0.1:8080
```

若 8080 被佔用：

```bash
ros2 run task_executor web_task_ui.py --port 8081
```

## UI Functions

目前提供：

- 文字任務輸入。
- Provider 選擇：OpenAI API 或 Ollama。
- Model 欄位。
- Refresh World：呼叫 `ur5_gazebo print_world_state.py`。
- Prompt：呼叫 `task_executor generate_skill_plan.py --dry-run`。
- Generate Plan：呼叫所選 LLM provider 產生 JSON plan。
- Plan editor：生成後可在右側調整 skill block，包含新增、刪除、上下移動、選擇 skill，以及修改 args JSON；修改會同步回左側 `Plan JSON`。
- Validate：呼叫 `task_executor execute_skill_plan.py <plan> --validate-only`。
- Execute：呼叫 `task_executor execute_skill_plan.py <plan>`。

## Backend API

UI backend 使用 Python 標準庫 `http.server`，避免新增 FastAPI/Flask 依賴。

Endpoints：

```text
GET  /
GET  /api/world_state
POST /api/prompt
POST /api/generate_plan
POST /api/validate_plan
POST /api/execute_plan
POST /api/execute_plan_async
GET  /api/execution/<job_id>
POST /api/stt
```

## OpenAI API Requirement

快速概念驗證建議先使用 OpenAI API。若按 Generate Plan 時出現 `OPENAI_API_KEY is not set`，代表啟動 Web UI 的 terminal 還沒有設定 API key。

```bash
export OPENAI_API_KEY="你的 API key"
```

預設 model 是：

```text
gpt-5.2
```

若 API 帳號沒有該 model 權限，可直接在 UI 的 model 欄位改成可用模型。

## Ollama Requirement

若 Provider 選 Ollama 且按 Generate Plan 時出現連線錯誤，代表 Ollama 沒有啟動或模型名稱不對。

檢查：

```bash
curl http://localhost:11434/api/tags
```

啟動服務與模型範例：

```bash
ollama serve
ollama pull qwen3.5:27b-q4_K_M
```

若模型名稱不同，直接在 UI 的 model 欄位修改。

## MVP Limitation

UI 的 Execute 會直接執行目前 `Plan JSON` 裡的 plan。右側 plan editor 的變更會同步回 `Plan JSON`，Validate/Execute 前仍會由 executor 做 schema 驗證。實機部署前需要再加入：

- confirmed execution gate
- speed/workspace safety limits
- E-stop 狀態顯示
- user/session log
- plan diff/review history
