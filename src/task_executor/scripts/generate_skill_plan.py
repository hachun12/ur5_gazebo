#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory


DEFAULT_OBJECTS = {
    "red_block": {"type": "block", "color": "red", "stackable": True},
    "green_block": {"type": "block", "color": "green", "stackable": True},
    "blue_block": {"type": "block", "color": "blue", "stackable": True},
    "green_ball": {"type": "sphere", "color": "green", "stackable": False},
}

ATOMIC_SKILLS = {
    "observe_scene",
    "move_ready",
    "open_gripper",
    "close_gripper",
    "move_above_object",
    "move_to_object",
    "move_to_region",
    "lift",
    "attach_object",
    "detach_object",
    "verify_relation",
    "verify_region",
}


class PlanValidationError(RuntimeError):
    pass


def load_skill_registry():
    share = Path(get_package_share_directory("skill_library"))
    skills_dir = share / "config" / "skills"
    registry = {}
    for skill_file in sorted(skills_dir.glob("*.yaml")):
        with skill_file.open("r", encoding="utf-8") as stream:
            skill = yaml.safe_load(stream)
        registry[skill["skill_id"]] = skill
    return registry


def load_world_state(path):
    if path is None:
        return {
            "frame_id": "world",
            "source": "symbolic_default",
            "objects": DEFAULT_OBJECTS,
            "regions": ["left_region", "center_region", "right_region", "front_region"],
        }

    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def validate_plan(plan, registry, require_atomic=True):
    if not isinstance(plan, dict):
        raise PlanValidationError("plan must be a JSON object")
    if "plan" not in plan or not isinstance(plan["plan"], list):
        raise PlanValidationError("plan must contain a list field named 'plan'")

    expected_step = 1
    for step in plan["plan"]:
        if step.get("step") != expected_step:
            raise PlanValidationError(f"step number must be consecutive; expected {expected_step}")
        expected_step += 1

        skill_id = step.get("skill")
        if skill_id not in registry:
            raise PlanValidationError(f"unknown skill: {skill_id}")
        if require_atomic and skill_id not in ATOMIC_SKILLS:
            raise PlanValidationError(f"LLM plan should use atomic skills; got composite skill: {skill_id}")

        args = step.get("args", {})
        if not isinstance(args, dict):
            raise PlanValidationError(f"{skill_id}.args must be an object")

        spec = registry[skill_id].get("parameters") or {}
        for name, parameter in spec.items():
            if parameter.get("required", False) and name not in args:
                raise PlanValidationError(f"{skill_id} missing required arg: {name}")
            if name in args:
                validate_arg(skill_id, name, parameter, args[name])


def validate_arg(skill_id, name, parameter, value):
    expected_type = parameter.get("type")
    if expected_type == "string" and not isinstance(value, str):
        raise PlanValidationError(f"{skill_id}.{name} must be a string")
    if expected_type == "number" and not isinstance(value, (int, float)):
        raise PlanValidationError(f"{skill_id}.{name} must be a number")
    if expected_type == "object" and not isinstance(value, dict):
        raise PlanValidationError(f"{skill_id}.{name} must be an object")

    allowed = parameter.get("enum")
    if allowed and value not in allowed:
        raise PlanValidationError(f"{skill_id}.{name} must be one of {allowed}")


def compact_skill_registry(registry, atomic_only=True):
    compact = {}
    for skill_id, skill in registry.items():
        if atomic_only and skill_id not in ATOMIC_SKILLS:
            continue
        compact[skill_id] = {
            "parameters": skill.get("parameters") or {},
        }
    return compact


def build_prompt(user_command, world_state, registry, validation_error=None, previous_output=None):
    prompt = {
        "role": "robot_task_planner",
        "rules": [
            "Return one JSON object and nothing else.",
            "Use only skills listed in skill_registry.",
            "Prefer atomic skills. Do not use composite/debug skills unless explicitly allowed.",
            "Do not invent object names, region names, ROS topics, or skill names.",
            "Spatial relation values are strings. Use \"on\", not bare YAML-style on.",
            "Use consecutive integer step numbers starting at 1.",
            "For pick: observe_scene, open_gripper, move_above_object, move_to_object, close_gripper, attach_object, lift.",
            "For place in region: move_to_region, detach_object, open_gripper, verify_region.",
            "For stack A on B: observe_scene, open_gripper, move_above_object(A, z_offset=0.16), move_to_object(A, z_offset=0.04), close_gripper(position=0.3), attach_object(A), lift(height=0.15), move_above_object(B, z_offset=0.205), move_to_object(B, z_offset=0.105), detach_object, open_gripper, verify_relation(on, A, B).",
        ],
        "default_parameters": {
            "pick_approach_z_offset": 0.16,
            "pick_contact_z_offset": 0.04,
            "grasp_close_position": 0.3,
            "lift_height": 0.15,
            "stack_approach_z_offset": 0.205,
            "stack_place_z_offset": 0.105,
            "move_to_region_tcp_z": 0.09,
        },
        "available_atomic_skills": sorted(ATOMIC_SKILLS),
        "skill_registry": compact_skill_registry(registry),
        "world_state": world_state,
        "user_command": user_command,
        "output_schema": {
            "task_id": "short_snake_case_id",
            "user_command": "original user command",
            "plan": [{"step": 1, "skill": "observe_scene", "args": {}}],
        },
    }
    if validation_error:
        prompt["previous_output"] = previous_output
        prompt["validation_error"] = validation_error
        prompt["repair_instruction"] = "Fix the JSON plan so it passes validation. Return only corrected JSON."
    return json.dumps(prompt, ensure_ascii=False, indent=2)


def call_ollama(prompt, model, ollama_url, timeout_sec, num_predict):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "think": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "num_predict": num_predict,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"failed to call Ollama at {ollama_url}: HTTP {exc.code}: {body}") from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        raise RuntimeError(f"failed to call Ollama at {ollama_url}: {exc}") from exc

    result = json.loads(body)
    return result.get("response") or result.get("thinking", "")


def plan_json_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["task_id", "user_command", "plan"],
        "properties": {
            "task_id": {"type": "string"},
            "user_command": {"type": "string"},
            "plan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["step", "skill", "args"],
                    "properties": {
                        "step": {"type": "integer"},
                        "skill": {"type": "string"},
                        "args": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                    },
                },
            },
        },
    }


def call_openai(prompt, model, api_base, timeout_sec, num_predict):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": num_predict,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "skill_plan",
                "schema": plan_json_schema(),
                "strict": False,
            }
        },
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/responses",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"failed to call OpenAI API: HTTP {exc.code}: {body}") from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        raise RuntimeError(f"failed to call OpenAI API: {exc}") from exc

    result = json.loads(body)
    if result.get("output_text"):
        return result["output_text"]

    chunks = []
    for item in result.get("output", []):
        for content in item.get("content", []):
            if "text" in content:
                chunks.append(content["text"])
    if chunks:
        return "".join(chunks)
    raise RuntimeError(f"OpenAI response did not contain output text: {body}")


def parse_json_object(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def make_output_path(path):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", help="Natural-language task command.")
    parser.add_argument(
        "--provider",
        choices=["openai", "ollama"],
        default="openai",
        help="LLM provider to call.",
    )
    parser.add_argument("--model", default="gpt-5.2", help="Model name for the selected provider.")
    parser.add_argument("--openai-api-base", default="https://api.openai.com/v1", help="OpenAI API base URL.")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama base URL.")
    parser.add_argument("--world-state-file", help="JSON world state file. Defaults to symbolic scene.")
    parser.add_argument("--output", help="Write generated plan JSON to this path.")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt only; do not call the LLM provider.")
    parser.add_argument("--allow-composite", action="store_true", help="Allow composite/debug skills in output.")
    parser.add_argument("--repair-attempts", type=int, default=1, help="Validation repair attempts.")
    parser.add_argument("--timeout-sec", type=float, default=60.0, help="Ollama request timeout.")
    parser.add_argument("--num-predict", type=int, default=1200, help="Maximum model output tokens.")
    return parser.parse_args()


def main():
    args = parse_args()
    registry = load_skill_registry()
    world_state = load_world_state(args.world_state_file)
    prompt = build_prompt(args.command, world_state, registry)

    if args.dry_run:
        print(prompt)
        return

    previous_output = None
    validation_error = None
    for attempt in range(args.repair_attempts + 1):
        if attempt > 0:
            prompt = build_prompt(args.command, world_state, registry, validation_error, previous_output)

        try:
            if args.provider == "ollama":
                response_text = call_ollama(
                    prompt,
                    args.model,
                    args.ollama_url,
                    args.timeout_sec,
                    args.num_predict,
                )
            else:
                response_text = call_openai(
                    prompt,
                    args.model,
                    args.openai_api_base,
                    args.timeout_sec,
                    args.num_predict,
                )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        previous_output = response_text
        try:
            plan = parse_json_object(response_text)
            validate_plan(plan, registry, require_atomic=not args.allow_composite)
            if args.output:
                output_path = make_output_path(args.output)
                with output_path.open("w", encoding="utf-8") as stream:
                    json.dump(plan, stream, indent=2, ensure_ascii=False)
                    stream.write("\n")
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return
        except (json.JSONDecodeError, PlanValidationError) as exc:
            validation_error = str(exc)

    print(f"failed to generate a valid plan: {validation_error}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
