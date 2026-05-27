#!/usr/bin/env python3

import argparse
import cgi
import json
import os
import subprocess
import tempfile
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UR5 Task Console</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f5f7;
      --panel: #ffffff;
      --ink: #172026;
      --muted: #5f6f78;
      --line: #d8e0e4;
      --accent: #0f766e;
      --accent-dark: #115e59;
      --danger: #b42318;
      --danger-bg: #fff0ed;
      --ok: #147a3d;
      --ok-bg: #ecfdf3;
      --warn: #9a6700;
      --warn-bg: #fff8db;
      --run: #1d4ed8;
      --run-bg: #eff6ff;
      --code: #101820;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    header {
      min-height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
    }
    main {
      display: grid;
      grid-template-columns: minmax(320px, 390px) minmax(520px, 1fr);
      gap: 16px;
      padding: 16px;
      height: calc(100vh - 56px);
      min-height: 640px;
    }
    section {
      min-width: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .control-panel, .workspace {
      overflow: auto;
    }
    .stack {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .row {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }
    label {
      display: block;
      font-size: 13px;
      font-weight: 650;
      color: var(--muted);
      margin-bottom: 6px;
    }
    textarea, input, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 11px;
      font: inherit;
      background: #fff;
      color: var(--ink);
    }
    textarea {
      min-height: 86px;
      resize: vertical;
      line-height: 1.45;
    }
    textarea#plan {
      min-height: 150px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }
    button {
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 0 12px;
      font-weight: 650;
      cursor: pointer;
    }
    button.ghost {
      color: var(--muted);
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    button.primary:hover { background: var(--accent-dark); }
    button.recording {
      background: var(--danger);
      border-color: var(--danger);
      color: #fff;
    }
    button:disabled {
      opacity: 0.55;
      cursor: wait;
    }
    .status {
      min-height: 24px;
      color: var(--muted);
      font-size: 13px;
    }
    .status.error { color: var(--danger); }
    pre {
      margin: 0;
      min-height: 120px;
      max-height: 260px;
      overflow: auto;
      border-radius: 6px;
      padding: 12px;
      background: var(--code);
      color: #e8f1f2;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .grid-two, .model-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .toolbar {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }
    .voice-box {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfcfd;
    }
    .voice-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 120px;
      gap: 8px;
      align-items: end;
    }
    .transcript {
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 9px 10px;
      color: var(--ink);
      font-size: 14px;
      line-height: 1.4;
      overflow-wrap: anywhere;
    }
    .plan-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .plan-title {
      min-width: 0;
    }
    .plan-title h2 {
      margin: 0;
      font-size: 17px;
      line-height: 1.25;
    }
    .plan-meta {
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
    }
    .step-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }
    .step-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 10px;
      min-height: 122px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .step-card.ok {
      border-color: #9bd4af;
      background: var(--ok-bg);
    }
    .step-card.failed {
      border-color: #ffb4a8;
      background: var(--danger-bg);
    }
    .step-card.running {
      border-color: #9bbcff;
      background: var(--run-bg);
    }
    .step-card.pending {
      background: #fbfcfd;
    }
    .step-card.dirty {
      border-color: #f6c76f;
      background: var(--warn-bg);
    }
    .step-top {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: center;
    }
    .step-controls {
      display: flex;
      gap: 6px;
      align-items: center;
      flex-wrap: nowrap;
    }
    .icon-btn {
      width: 30px;
      height: 30px;
      padding: 0;
      display: inline-grid;
      place-items: center;
      font-size: 15px;
      line-height: 1;
    }
    .icon-btn.danger {
      color: var(--danger);
      border-color: #ffb4a8;
      background: var(--danger-bg);
    }
    .step-fields {
      display: grid;
      gap: 8px;
    }
    .step-field-label {
      margin: 0;
      font-size: 11px;
      letter-spacing: 0;
    }
    .skill-input {
      height: 34px;
      padding: 7px 9px;
      font-size: 13px;
      font-weight: 650;
    }
    textarea.args-input {
      min-height: 78px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.4;
      resize: vertical;
    }
    .step-card.invalid {
      border-color: #ffb4a8;
      background: var(--danger-bg);
    }
    .step-name {
      font-weight: 750;
      overflow-wrap: anywhere;
    }
    .badge {
      border-radius: 999px;
      border: 1px solid var(--line);
      padding: 3px 8px;
      font-size: 12px;
      line-height: 1;
      white-space: nowrap;
      background: #fff;
      color: var(--muted);
    }
    .badge.ok {
      border-color: #9bd4af;
      color: var(--ok);
    }
    .badge.failed {
      border-color: #ffb4a8;
      color: var(--danger);
    }
    .badge.running {
      border-color: #9bbcff;
      color: var(--run);
    }
    .step-args {
      margin: 0;
      min-height: 42px;
      max-height: none;
      background: #172026;
      color: #eef5f4;
      font-size: 11px;
      padding: 8px;
    }
    .step-error {
      color: var(--danger);
      font-size: 12px;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }
    .log-panel {
      position: sticky;
      bottom: 0;
      border-top: 1px solid var(--line);
      background: var(--panel);
      padding-top: 12px;
    }
    #log {
      min-height: 190px;
      max-height: 190px;
    }
    .empty {
      min-height: 260px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      display: grid;
      place-items: center;
      color: var(--muted);
      text-align: center;
      padding: 20px;
    }
    @media (max-width: 920px) {
      main {
        grid-template-columns: 1fr;
        height: auto;
      }
      .grid-two, .model-grid { grid-template-columns: 1fr; }
      .voice-grid { grid-template-columns: 1fr; }
      .log-panel { position: static; }
    }
  </style>
</head>
<body>
  <header>
    <h1>UR5 Task Console</h1>
    <div id="status" class="status">idle</div>
  </header>
  <main>
    <section class="stack control-panel">
      <div>
        <label for="command">Task</label>
        <textarea id="command">把藍色方塊疊到綠色方塊上</textarea>
      </div>
      <div class="voice-box stack">
        <div class="voice-grid">
          <div>
            <label for="sttModel">STT Model</label>
            <select id="sttModel">
              <option value="tiny" selected>tiny</option>
              <option value="base">base</option>
              <option value="small">small</option>
              <option value="medium">medium</option>
            </select>
          </div>
          <button id="recordBtn">Record</button>
        </div>
        <div class="toolbar">
          <button id="stopBtn" disabled>Stop</button>
          <button id="useTranscriptBtn">Use Text</button>
        </div>
        <div id="transcript" class="transcript"></div>
      </div>
      <div class="model-grid">
        <div>
          <label for="provider">Provider</label>
          <select id="provider">
            <option value="ollama" selected>Ollama</option>
            <option value="openai">OpenAI API</option>
          </select>
        </div>
        <div>
          <label for="model">Model</label>
          <select id="model"></select>
        </div>
      </div>
      <div class="toolbar">
        <button id="worldBtn">Refresh World</button>
        <button id="promptBtn">Prompt</button>
        <button id="generateBtn" class="primary">Generate Plan</button>
      </div>
      <div class="toolbar">
        <button id="validateBtn">Validate</button>
        <button id="executeBtn" class="primary">Execute</button>
        <button id="clearBtn" class="ghost">Clear Log</button>
      </div>
      <div>
        <label for="plan">Plan JSON</label>
        <textarea id="plan"></textarea>
      </div>
      <div>
        <label>World State</label>
        <pre id="world">{}</pre>
      </div>
    </section>
    <section class="stack workspace">
      <div class="plan-header">
        <div class="plan-title">
          <h2 id="planName">Generated Plan</h2>
          <div id="planMeta" class="plan-meta">No plan generated yet</div>
        </div>
        <div class="toolbar">
          <button id="addStepBtn">Add Step</button>
          <span id="planState" class="badge">idle</span>
        </div>
      </div>
      <div id="steps" class="step-grid">
        <div class="empty">Generate a plan to inspect skill order and arguments.</div>
      </div>
      <div class="log-panel stack">
        <label>Log</label>
        <pre id="log"></pre>
      </div>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const status = $("status");
    const modelOptions = {
      ollama: ["gemma4:latest", "qwen3.5:27b-q4_K_M"],
      openai: ["gpt-5.2", "gpt-5.1", "gpt-4.1"]
    };
    const availableSkills = [
      "attach_object",
      "close_gripper",
      "detach_object",
      "lift",
      "move_above_object",
      "move_ready",
      "move_to_object",
      "move_to_region",
      "observe_scene",
      "open_gripper",
      "pick",
      "place",
      "push",
      "stack",
      "verify_region",
      "verify_relation"
    ];
    let currentPlan = null;
    let stepStates = [];
    let mediaRecorder = null;
    let audioChunks = [];
    let latestTranscript = "";

    function appendLog(title, payload=null) {
      const now = new Date().toLocaleTimeString();
      const lines = [`[${now}] ${title}`];
      if (payload !== null && payload !== undefined && payload !== "") {
        lines.push(typeof payload === "string" ? payload : pretty(payload));
      }
      $("log").textContent = `${lines.join("\\n")}\\n\\n${$("log").textContent}`.trim();
    }

    function setPlanBadge(text, kind="") {
      $("planState").textContent = text;
      $("planState").className = `badge ${kind}`.trim();
    }

    function refreshModels() {
      const provider = $("provider").value;
      const selected = $("model").value;
      $("model").innerHTML = "";
      for (const model of modelOptions[provider]) {
        const option = document.createElement("option");
        option.value = model;
        option.textContent = model;
        $("model").appendChild(option);
      }
      if (modelOptions[provider].includes(selected)) {
        $("model").value = selected;
      }
    }

    function setBusy(text) {
      status.textContent = text;
      status.className = "status";
      allButtons().forEach((button) => button.disabled = true);
    }

    function setDone(text, error=false) {
      status.textContent = text;
      status.className = error ? "status error" : "status";
      allButtons().forEach((button) => button.disabled = false);
    }

    function pretty(value) {
      if (typeof value === "string") return value;
      return JSON.stringify(value, null, 2);
    }

    function allButtons() {
      return Array.from(document.querySelectorAll("button"));
    }

    function escapeHTML(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function renderSkillOptions(selected) {
      const options = availableSkills.includes(selected) ? availableSkills : [selected, ...availableSkills].filter(Boolean);
      return options.map((skill) => {
        const isSelected = skill === selected ? " selected" : "";
        return `<option value="${escapeHTML(skill)}"${isSelected}>${escapeHTML(skill)}</option>`;
      }).join("");
    }

    async function api(path, body=null, allowError=false) {
      const response = await fetch(path, {
        method: body ? "POST" : "GET",
        headers: body ? {"Content-Type": "application/json"} : {},
        body: body ? JSON.stringify(body) : null,
      });
      const data = await response.json();
      data.http_ok = response.ok;
      if (!response.ok && !allowError) throw data;
      return data;
    }

    async function uploadSTT(blob) {
      const data = new FormData();
      data.append("audio", blob, "command.webm");
      data.append("model", $("sttModel").value);
      data.append("language", "zh");
      const response = await fetch("/api/stt", {method: "POST", body: data});
      const payload = await response.json();
      payload.http_ok = response.ok;
      if (!response.ok) throw payload;
      return payload;
    }

    function sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    async function run(label, fn) {
      setBusy(label);
      appendLog(label);
      try {
        await fn();
        setDone("done");
      } catch (err) {
        appendLog("failed", err);
        setDone("failed", true);
      }
    }

    function planSteps(plan) {
      return plan && Array.isArray(plan.plan) ? plan.plan : [];
    }

    function initializeStepStates(plan, state="pending") {
      return planSteps(plan).map((step) => ({
        step: step.step,
        skill: step.skill,
        state,
        message: ""
      }));
    }

    function statusText(state) {
      return {
        pending: "pending",
        running: "running",
        ok: "ok",
        failed: "failed"
      }[state] || state;
    }

    function normalizePlanSteps(plan) {
      if (!plan || !Array.isArray(plan.plan)) return plan;
      plan.plan = plan.plan.map((step, index) => ({
        ...step,
        step: index + 1,
        args: step.args && typeof step.args === "object" && !Array.isArray(step.args) ? step.args : {}
      }));
      return plan;
    }

    function ensurePlan() {
      if (currentPlan && typeof currentPlan === "object") return currentPlan;
      const command = $("command").value;
      currentPlan = {
        task_id: "manual_plan",
        user_command: command,
        plan: []
      };
      return currentPlan;
    }

    function syncPlanText(plan=currentPlan) {
      if (!plan) return;
      normalizePlanSteps(plan);
      $("plan").value = pretty(plan);
      $("planName").textContent = plan.task_id || "Generated Plan";
      $("planMeta").textContent = `${planSteps(plan).length} skill step(s) | ${plan.user_command || $("command").value}`;
    }

    function markPlanEdited() {
      setPlanBadge("edited", "running");
      stepStates = initializeStepStates(currentPlan);
    }

    function setStepValidation(index, message) {
      const card = $("steps").querySelector(`[data-step-index="${index}"]`);
      if (!card) return;
      card.classList.toggle("invalid", Boolean(message));
      const error = card.querySelector(".step-error");
      if (error) error.textContent = message || "";
    }

    function renderPlan(plan, states=null) {
      currentPlan = normalizePlanSteps(plan);
      stepStates = states || initializeStepStates(plan);
      syncPlanText(currentPlan);
      const stateByStep = new Map(stepStates.map((item) => [item.step, item]));
      $("steps").innerHTML = "";
      for (const step of planSteps(plan)) {
        const index = step.step - 1;
        const state = stateByStep.get(step.step) || {state: "pending", message: ""};
        const card = document.createElement("article");
        card.className = `step-card ${state.state || "pending"}`;
        card.dataset.stepIndex = String(index);
        card.innerHTML = `
          <div class="step-top">
            <div class="step-name">Step ${escapeHTML(step.step)}</div>
            <div class="step-controls">
              <button class="icon-btn" data-action="up" data-index="${index}" title="Move up" aria-label="Move step up">↑</button>
              <button class="icon-btn" data-action="down" data-index="${index}" title="Move down" aria-label="Move step down">↓</button>
              <button class="icon-btn danger" data-action="delete" data-index="${index}" title="Delete" aria-label="Delete step">×</button>
              <span class="badge ${state.state || "pending"}">${statusText(state.state || "pending")}</span>
            </div>
          </div>
          <div class="step-fields">
            <div>
              <label class="step-field-label" for="skill-${index}">Skill</label>
              <select id="skill-${index}" class="skill-input" data-field="skill" data-index="${index}">
                ${renderSkillOptions(step.skill || "")}
              </select>
            </div>
            <div>
              <label class="step-field-label" for="args-${index}">Args JSON</label>
              <textarea id="args-${index}" class="args-input" data-field="args" data-index="${index}">${escapeHTML(pretty(step.args || {}))}</textarea>
            </div>
          </div>
          <div class="step-error">${state.message ? escapeHTML(state.message) : ""}</div>
        `;
        $("steps").appendChild(card);
      }
      if (planSteps(plan).length === 0) {
        $("steps").innerHTML = `<div class="empty">Add a skill step or generate a plan.</div>`;
      }
    }

    function parsePlanFromText() {
      const invalidEditor = $("steps").querySelector(".step-card.invalid");
      if (invalidEditor) {
        throw {error: "fix invalid skill args before validating or executing"};
      }
      const plan = JSON.parse($("plan").value);
      renderPlan(normalizePlanSteps(plan));
      return plan;
    }

    $("steps").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button || !currentPlan) return;
      const index = Number(button.dataset.index);
      const steps = planSteps(currentPlan);
      if (!Number.isInteger(index) || index < 0 || index >= steps.length) return;

      if (button.dataset.action === "delete") {
        steps.splice(index, 1);
      } else if (button.dataset.action === "up" && index > 0) {
        [steps[index - 1], steps[index]] = [steps[index], steps[index - 1]];
      } else if (button.dataset.action === "down" && index < steps.length - 1) {
        [steps[index], steps[index + 1]] = [steps[index + 1], steps[index]];
      }
      normalizePlanSteps(currentPlan);
      markPlanEdited();
      renderPlan(currentPlan, stepStates);
    });

    $("steps").addEventListener("input", (event) => {
      const target = event.target;
      if (!target.dataset || !target.dataset.field) return;
      const plan = ensurePlan();
      const index = Number(target.dataset.index);
      const step = planSteps(plan)[index];
      if (!step) return;

      if (target.dataset.field === "skill") {
        step.skill = target.value.trim();
        setStepValidation(index, "");
      } else if (target.dataset.field === "args") {
        try {
          const args = JSON.parse(target.value || "{}");
          if (!args || typeof args !== "object" || Array.isArray(args)) {
            throw new Error("args must be a JSON object");
          }
          step.args = args;
          setStepValidation(index, "");
        } catch (err) {
          setStepValidation(index, err.message);
          setPlanBadge("invalid args", "failed");
          return;
        }
      }
      normalizePlanSteps(plan);
      syncPlanText(plan);
      markPlanEdited();
    });

    $("addStepBtn").onclick = () => {
      const plan = ensurePlan();
      plan.plan.push({
        step: plan.plan.length + 1,
        skill: "observe_scene",
        args: {}
      });
      normalizePlanSteps(plan);
      markPlanEdited();
      renderPlan(plan, stepStates);
    };

    $("worldBtn").onclick = () => run("reading world", async () => {
      const data = await api("/api/world_state");
      $("world").textContent = pretty(data.world_state);
      appendLog("world state updated", data.stderr || data.world_state);
    });

    $("promptBtn").onclick = () => run("building prompt", async () => {
      const data = await api("/api/prompt", {command: $("command").value, provider: $("provider").value, model: $("model").value});
      appendLog("prompt", data.prompt);
    });

    $("generateBtn").onclick = () => run("generating plan", async () => {
      const data = await api("/api/generate_plan", {command: $("command").value, provider: $("provider").value, model: $("model").value});
      renderPlan(data.plan, data.step_statuses);
      setPlanBadge("generated", "ok");
      appendLog("generated plan", data.stdout || data.plan);
    });

    $("validateBtn").onclick = () => run("validating", async () => {
      const plan = parsePlanFromText();
      const data = await api("/api/validate_plan", {plan}, true);
      renderPlan(plan, data.step_statuses);
      setPlanBadge(data.returncode === 0 ? "valid" : "invalid", data.returncode === 0 ? "ok" : "failed");
      appendLog("validation result", data.stdout || data.stderr || data);
      if (data.returncode !== 0) throw data;
    });

    $("executeBtn").onclick = () => run("executing", async () => {
      const plan = parsePlanFromText();
      renderPlan(plan, initializeStepStates(plan).map((state, index) => ({
        ...state,
        state: index === 0 ? "running" : "pending"
      })));
      setPlanBadge("executing", "running");
      const start = await api("/api/execute_plan_async", {plan});
      let lastLogLength = 0;
      while (true) {
        const job = await api(`/api/execution/${start.job_id}`, null, true);
        renderPlan(plan, job.step_statuses);
        if (job.log && job.log.length > lastLogLength) {
          appendLog("execution update", job.log.slice(lastLogLength));
          lastLogLength = job.log.length;
        }
        if (job.done) {
          setPlanBadge(job.returncode === 0 ? "executed" : "execute failed", job.returncode === 0 ? "ok" : "failed");
          if (job.returncode !== 0) throw job;
          return;
        }
        await sleep(500);
      }
    });

    $("clearBtn").onclick = () => {
      $("log").textContent = "";
    };

    $("recordBtn").onclick = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({audio: true});
        audioChunks = [];
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) audioChunks.push(event.data);
        };
        mediaRecorder.onstop = async () => {
          stream.getTracks().forEach((track) => track.stop());
          $("recordBtn").classList.remove("recording");
          $("recordBtn").disabled = false;
          $("stopBtn").disabled = true;
          const blob = new Blob(audioChunks, {type: "audio/webm"});
          await run("transcribing audio", async () => {
            const data = await uploadSTT(blob);
            latestTranscript = data.text || "";
            $("transcript").textContent = latestTranscript;
            appendLog("stt result", data);
          });
        };
        mediaRecorder.start();
        $("recordBtn").classList.add("recording");
        $("recordBtn").disabled = true;
        $("stopBtn").disabled = false;
        $("transcript").textContent = "recording...";
        appendLog("recording started");
      } catch (err) {
        appendLog("recording failed", err);
        setDone("failed", true);
      }
    };

    $("stopBtn").onclick = () => {
      if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
      }
    };

    $("useTranscriptBtn").onclick = () => {
      if (latestTranscript) {
        $("command").value = latestTranscript;
        appendLog("transcript copied to task", latestTranscript);
      }
    };

    $("provider").onchange = refreshModels;
    refreshModels();
    setPlanBadge("idle");
  </script>
</body>
</html>
"""


EXECUTION_JOBS = {}
EXECUTION_LOCK = threading.Lock()
STT_MODELS = {}
STT_LOCK = threading.Lock()


class TaskUIHandler(BaseHTTPRequestHandler):
    server_version = "UR5TaskConsole/0.1"

    def do_GET(self):
        if self.path == "/":
            self.send_html(HTML)
        elif self.path == "/api/world_state":
            self.handle_world_state()
        elif self.path.startswith("/api/execution/"):
            self.handle_execution_status()
        else:
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        try:
            if self.path == "/api/prompt":
                self.handle_prompt()
            elif self.path == "/api/generate_plan":
                self.handle_generate_plan()
            elif self.path == "/api/validate_plan":
                self.handle_validate_plan()
            elif self.path == "/api/execute_plan":
                self.handle_execute_plan()
            elif self.path == "/api/execute_plan_async":
                self.handle_execute_plan_async()
            elif self.path == "/api/stt":
                self.handle_stt()
            else:
                self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except json.JSONDecodeError as exc:
            self.send_json({"error": f"invalid JSON request body: {exc}"}, HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_html(self, html):
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def run_command(self, command, timeout=120):
        env = os.environ.copy()
        env.setdefault("ROS_LOG_DIR", "/tmp/ros_logs")
        result = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=env,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": command,
        }

    def handle_world_state(self):
        result = self.run_command(["ros2", "run", "ur5_gazebo", "print_world_state.py"], timeout=20)
        if result["returncode"] != 0:
            self.send_json(result, HTTPStatus.BAD_GATEWAY)
            return
        try:
            world_state = json.loads(result["stdout"])
        except json.JSONDecodeError as exc:
            self.send_json({"error": str(exc), **result}, HTTPStatus.BAD_GATEWAY)
            return
        self.send_json({"world_state": world_state, "stderr": result["stderr"]})

    def handle_prompt(self):
        body = self.read_body()
        command = body.get("command", "")
        provider = body.get("provider", "openai")
        model = body.get("model") or self.default_model(provider)
        result = self.run_command(
            [
                "ros2",
                "run",
                "task_executor",
                "generate_skill_plan.py",
                command,
                "--provider",
                provider,
                "--model",
                model,
                "--dry-run",
            ],
            timeout=20,
        )
        if result["returncode"] != 0:
            self.send_json(result, HTTPStatus.BAD_GATEWAY)
            return
        self.send_json({"prompt": result["stdout"], "stderr": result["stderr"]})

    def handle_generate_plan(self):
        body = self.read_body()
        command = body.get("command", "")
        provider = body.get("provider", "openai")
        model = body.get("model") or self.default_model(provider)
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as stream:
            output_path = stream.name
        result = self.run_command(
            [
                "ros2",
                "run",
                "task_executor",
                "generate_skill_plan.py",
                command,
                "--provider",
                provider,
                "--model",
                model,
                "--timeout-sec",
                "180",
                "--output",
                output_path,
            ],
            timeout=210,
        )
        if result["returncode"] != 0:
            self.send_json(result, HTTPStatus.BAD_GATEWAY)
            return
        try:
            plan = json.loads(Path(output_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc), **result}, HTTPStatus.BAD_GATEWAY)
            return
        self.send_json({
            "plan": plan,
            "step_statuses": self.make_step_statuses(plan, "pending"),
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        })

    def default_model(self, provider):
        if provider == "ollama":
            return "gemma4:latest"
        return "gpt-5.2"

    def handle_validate_plan(self):
        body = self.read_body()
        plan = body.get("plan")
        result = self.run_plan_command(plan, ["--validate-only"], timeout=30)
        result["step_statuses"] = self.validation_statuses(plan, result)
        status = HTTPStatus.OK if result["returncode"] == 0 else HTTPStatus.BAD_REQUEST
        self.send_json(result, status)

    def handle_execute_plan(self):
        body = self.read_body()
        plan = body.get("plan")
        result = self.run_plan_command(plan, [], timeout=600)
        result["step_statuses"] = self.execution_statuses(plan, result)
        status = HTTPStatus.OK if result["returncode"] == 0 else HTTPStatus.BAD_GATEWAY
        self.send_json(result, status)

    def handle_execute_plan_async(self):
        body = self.read_body()
        plan = body.get("plan")
        if not self.plan_steps(plan):
            self.send_json({"error": "plan must contain steps"}, HTTPStatus.BAD_REQUEST)
            return
        job = self.start_execution_job(plan)
        self.send_json({
            "job_id": job["job_id"],
            "step_statuses": job["step_statuses"],
            "done": False,
            "log": "",
        })

    def handle_execution_status(self):
        job_id = self.path.rsplit("/", 1)[-1]
        with EXECUTION_LOCK:
            job = EXECUTION_JOBS.get(job_id)
            if job is None:
                self.send_json({"error": "execution job not found"}, HTTPStatus.NOT_FOUND)
                return
            payload = {
                "job_id": job["job_id"],
                "done": job["done"],
                "returncode": job["returncode"],
                "step_statuses": job["step_statuses"],
                "log": job["log"],
                "error": job["error"],
            }
        status = HTTPStatus.OK if payload["returncode"] in (None, 0) else HTTPStatus.BAD_GATEWAY
        self.send_json(payload, status)

    def handle_stt(self):
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self.send_json({"error": "POST /api/stt expects multipart/form-data"}, HTTPStatus.BAD_REQUEST)
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        audio = form["audio"] if "audio" in form else None
        if audio is None or not getattr(audio, "file", None):
            self.send_json({"error": "missing audio file field"}, HTTPStatus.BAD_REQUEST)
            return

        model_name = self.form_value(form, "model", "tiny")
        language = self.form_value(form, "language", "zh")
        suffix = Path(getattr(audio, "filename", "") or "audio.webm").suffix or ".webm"
        with tempfile.NamedTemporaryFile("wb", suffix=suffix, delete=False) as stream:
            stream.write(audio.file.read())
            audio_path = stream.name

        try:
            text, segments = self.transcribe_audio(audio_path, model_name, language)
        except ImportError as exc:
            self.send_json({
                "error": str(exc),
                "hint": "Install M8 dependencies with scripts/setup_m8_stt.sh, then restart the Web UI.",
            }, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        except Exception as exc:
            self.send_json({"error": f"STT failed: {exc}"}, HTTPStatus.BAD_GATEWAY)
            return

        self.send_json({
            "text": text,
            "model": model_name,
            "language": language,
            "segments": segments,
        })

    def form_value(self, form, name, default):
        if name not in form:
            return default
        value = form[name].value
        return value if value else default

    def transcribe_audio(self, audio_path, model_name, language):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ImportError("faster-whisper is not installed") from exc

        with STT_LOCK:
            model = STT_MODELS.get(model_name)
            if model is None:
                model = WhisperModel(model_name, device="cpu", compute_type="int8")
                STT_MODELS[model_name] = model

        segments_iter, info = model.transcribe(
            audio_path,
            language=language or None,
            vad_filter=True,
            beam_size=5,
        )
        segments = []
        texts = []
        for segment in segments_iter:
            text = segment.text.strip()
            if text:
                texts.append(text)
            segments.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": text,
            })
        return "".join(texts).strip(), segments

    def run_plan_command(self, plan, extra_args, timeout):
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            path = stream.name
        return self.run_command(
            ["ros2", "run", "task_executor", "execute_skill_plan.py", path, *extra_args],
            timeout=timeout,
        )

    def start_execution_job(self, plan):
        job_id = uuid.uuid4().hex
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            path = stream.name

        job = {
            "job_id": job_id,
            "plan": plan,
            "path": path,
            "done": False,
            "returncode": None,
            "log": "",
            "error": "",
            "current_step": None,
            "step_statuses": self.make_step_statuses(plan, "pending"),
        }
        with EXECUTION_LOCK:
            EXECUTION_JOBS[job_id] = job

        command = ["ros2", "run", "task_executor", "execute_skill_plan.py", path]
        env = os.environ.copy()
        env.setdefault("ROS_LOG_DIR", "/tmp/ros_logs")
        thread = threading.Thread(
            target=self.run_execution_job,
            args=(job_id, command, env),
            daemon=True,
        )
        thread.start()
        return job

    def run_execution_job(self, job_id, command, env):
        try:
            process = subprocess.Popen(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
        except OSError as exc:
            with EXECUTION_LOCK:
                job = EXECUTION_JOBS[job_id]
                job["done"] = True
                job["returncode"] = 127
                job["error"] = str(exc)
                job["log"] += f"{exc}\n"
                self.mark_running_failed(job, str(exc))
            return

        with process.stdout:
            for line in process.stdout:
                with EXECUTION_LOCK:
                    job = EXECUTION_JOBS[job_id]
                    job["log"] += line
                    self.update_execution_progress_from_line(job, line)

        returncode = process.wait()
        with EXECUTION_LOCK:
            job = EXECUTION_JOBS[job_id]
            job["returncode"] = returncode
            job["done"] = True
            if returncode == 0:
                for status in job["step_statuses"]:
                    status["state"] = "ok"
                    status["message"] = ""
            else:
                message = self.last_log_line(job["log"]) or f"command failed with return code {returncode}"
                job["error"] = message
                self.mark_running_failed(job, message)

    def update_execution_progress_from_line(self, job, line):
        steps = self.plan_steps(job["plan"])
        for step in steps:
            marker = f"step {step.get('step')}: {step.get('skill')}"
            if marker in line:
                step_number = step.get("step")
                previous = job.get("current_step")
                if previous is not None and previous != step_number:
                    self.set_step_state(job, previous, "ok")
                job["current_step"] = step_number
                self.set_step_state(job, step_number, "running")
                return

    def set_step_state(self, job, step_number, state, message=""):
        for status in job["step_statuses"]:
            if status.get("step") == step_number:
                status["state"] = state
                status["message"] = message
                return

    def mark_running_failed(self, job, message):
        failed_step = job.get("current_step")
        if failed_step is None and job["step_statuses"]:
            failed_step = job["step_statuses"][0].get("step")
        for status in job["step_statuses"]:
            step_number = status.get("step")
            if failed_step is not None and step_number < failed_step and status["state"] == "running":
                status["state"] = "ok"
            elif step_number == failed_step:
                status["state"] = "failed"
                status["message"] = message
            elif failed_step is not None and step_number > failed_step and status["state"] == "running":
                status["state"] = "pending"

    def last_log_line(self, log):
        lines = [line.strip() for line in log.splitlines() if line.strip()]
        for line in reversed(lines):
            if "[ERROR]" in line or "RuntimeError:" in line or "Traceback" in line:
                return line
        return lines[-1] if lines else ""

    def plan_steps(self, plan):
        if isinstance(plan, dict) and isinstance(plan.get("plan"), list):
            return plan["plan"]
        return []

    def make_step_statuses(self, plan, state, message=""):
        return [
            {
                "step": step.get("step"),
                "skill": step.get("skill"),
                "state": state,
                "message": message,
            }
            for step in self.plan_steps(plan)
        ]

    def validation_statuses(self, plan, result):
        if result["returncode"] == 0:
            return self.make_step_statuses(plan, "ok")
        failed_step = self.infer_failed_step(plan, result)
        message = self.result_message(result)
        statuses = []
        for step in self.plan_steps(plan):
            state = "failed" if step.get("step") == failed_step else "pending"
            statuses.append({
                "step": step.get("step"),
                "skill": step.get("skill"),
                "state": state,
                "message": message if state == "failed" else "",
            })
        return statuses

    def execution_statuses(self, plan, result):
        if result["returncode"] == 0:
            return self.make_step_statuses(plan, "ok")

        failed_step = self.infer_failed_step(plan, result)
        message = self.result_message(result)
        statuses = []
        for step in self.plan_steps(plan):
            step_number = step.get("step")
            if failed_step is None:
                state = "failed" if step_number == 1 else "pending"
            elif step_number < failed_step:
                state = "ok"
            elif step_number == failed_step:
                state = "failed"
            else:
                state = "pending"
            statuses.append({
                "step": step_number,
                "skill": step.get("skill"),
                "state": state,
                "message": message if state == "failed" else "",
            })
        return statuses

    def infer_failed_step(self, plan, result):
        text = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
        steps = self.plan_steps(plan)

        current_step = None
        for step in steps:
            marker = f"step {step.get('step')}: {step.get('skill')}"
            if marker in text:
                current_step = step.get("step")
        if current_step is not None and result.get("returncode") != 0:
            return current_step

        for step in steps:
            skill = str(step.get("skill"))
            if skill and skill in text:
                return step.get("step")
        return steps[0].get("step") if steps else None

    def result_message(self, result):
        for source in (result.get("stderr", ""), result.get("stdout", "")):
            lines = [line.strip() for line in source.splitlines() if line.strip()]
            if lines:
                return lines[-1]
        return f"command failed with return code {result.get('returncode')}"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    return parser.parse_args()


def main():
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), TaskUIHandler)
    print(f"UR5 Task Console: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
