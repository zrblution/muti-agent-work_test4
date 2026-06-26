from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from experiments.fake.evaluator import validate_benchmark, validate_model, validate_model_runtime
from stable_core.config import validate_config
from stable_core.runner.remote import RemoteRunner
from stable_core.storage.run_directory import current_git_commit, utc_now, write_json, write_text
from stable_core.validation.inventory_discovery import discover_benchmark_inventory, discover_model_inventory
from stable_core.validation.preflight import REPO_ROOT, parse_simple_yaml


SAFETY_FLAGS = {
    "executed_real_model": False,
    "executed_real_benchmark": False,
    "submitted_remote_job": False,
    "raw_outputs_written": False,
    "write_config": False,
}

_ENV_TEMPLATE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def build_phase5_readiness_bundle(
    *,
    model_id: str,
    benchmark_id: str,
    limit: int,
    instrumentation_mode: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if instrumentation_mode not in {"none", "light", "deep"}:
        raise ValueError("instrumentation_mode must be one of none, light, deep")

    checks = {
        "config": validate_config(),
        "model_inventory_discovery": discover_model_inventory(model_id),
        "benchmark_inventory_discovery": discover_benchmark_inventory(benchmark_id),
        "model_runtime_dependencies": validate_model_runtime(model_id),
        "model_validation": validate_model(model_id),
        "benchmark_validation": validate_benchmark(benchmark_id),
    }
    execution_authorization = RemoteRunner().submit(
        {
            "action": "run_model_smoke_test",
            "allowed_script": "experiments/landmark_baselines/run_landmark.py",
            "model_id": model_id,
            "benchmark_id": benchmark_id,
            "limit": limit,
            "instrumentation_mode": instrumentation_mode,
        },
        plan_only=True,
    )
    status = _readiness_status(checks, execution_authorization)
    bundle = {
        "phase": "Phase 5",
        "status": status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "target": {
            "model_id": model_id,
            "benchmark_id": benchmark_id,
            "limit": limit,
            "instrumentation_mode": instrumentation_mode,
        },
        "checks": checks,
        "execution_authorization": execution_authorization,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _next_actions(checks, execution_authorization),
        "do_not_continue_reason": _do_not_continue_reason(status, checks, execution_authorization),
    }
    if output_dir is not None:
        _write_bundle(Path(output_dir), bundle)
    return bundle


def build_phase5_path_probe(
    *,
    model_id: str,
    benchmark_id: str,
    model_root: str | Path,
    benchmark_root: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    model_env = _configured_root_env("models.yaml", "models", model_id, "model_root_env", ("local_path", "path"))
    benchmark_env = _configured_root_env("benchmarks.yaml", "benchmarks", benchmark_id, "benchmark_root_env", ("path",))
    candidate_env = {
        model_env: str(model_root),
        benchmark_env: str(benchmark_root),
    }
    with _temporary_env(candidate_env):
        checks = {
            "config": validate_config(),
            "model_inventory_discovery": discover_model_inventory(model_id),
            "benchmark_inventory_discovery": discover_benchmark_inventory(benchmark_id),
            "model_runtime_dependencies": validate_model_runtime(model_id),
            "model_validation": validate_model(model_id),
            "benchmark_validation": validate_benchmark(benchmark_id),
        }
    status = _checks_status(checks)
    report = {
        "phase": "Phase 5",
        "mode": "path_probe",
        "status": status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "target": {
            "model_id": model_id,
            "benchmark_id": benchmark_id,
        },
        "candidate_env": candidate_env,
        "checks": checks,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _path_probe_next_actions(status, checks, candidate_env),
    }
    if output is not None:
        write_json(Path(output), report)
    return report


def _readiness_status(checks: dict[str, dict[str, Any]], execution_authorization: dict[str, Any]) -> str:
    statuses = [str(check.get("status")) for check in checks.values()]
    execution_status = str(execution_authorization.get("status"))
    if "failed" in statuses or execution_status == "failed":
        return "failed"
    if all(status == "passed" for status in statuses) and execution_status == "passed":
        return "passed"
    return "needs_attention"


def _checks_status(checks: dict[str, dict[str, Any]]) -> str:
    statuses = [str(check.get("status")) for check in checks.values()]
    if "failed" in statuses:
        return "failed"
    if all(status == "passed" for status in statuses):
        return "passed"
    return "needs_attention"


def _next_actions(checks: dict[str, dict[str, Any]], execution_authorization: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if checks["model_validation"].get("status") != "passed":
        actions.append("Configure and populate the approved model path, then rerun validate-model.")
    if checks["model_runtime_dependencies"].get("status") != "passed":
        actions.append("Install or activate the approved model runtime dependencies, then rerun validate-model-runtime.")
    if checks["benchmark_validation"].get("status") != "passed":
        actions.append("Configure and populate the approved benchmark path, then rerun validate-benchmark.")
    if execution_authorization.get("status") != "passed":
        actions.append("Open reviewed remote execution, GPU budget, and process-submission gates only after validation passes.")
    if not actions:
        actions.append("Run the controlled Phase 5 real smoke through the reviewed RemoteRunner path.")
    return actions


def _path_probe_next_actions(status: str, checks: dict[str, dict[str, Any]], candidate_env: dict[str, str]) -> list[str]:
    if status == "passed":
        exports = " ".join(f"{name}={value}" for name, value in candidate_env.items())
        return [
            f"Review and approve these candidate environment values before exporting them: {exports}",
            "After approval, rerun validate-model, validate-benchmark, and phase5-readiness in the server execution environment.",
        ]
    actions: list[str] = []
    if checks["model_validation"].get("status") != "passed":
        actions.append("Choose a model root whose configured model subdirectory passes validate-model.")
    if checks["benchmark_validation"].get("status") != "passed":
        actions.append("Choose a benchmark root whose configured benchmark subdirectory passes validate-benchmark.")
    if checks["model_runtime_dependencies"].get("status") != "passed":
        actions.append("Install or activate model runtime dependencies before probing candidate roots again.")
    if not actions:
        actions.append("Review failed checks before using these candidate roots.")
    return actions


def _do_not_continue_reason(
    status: str,
    checks: dict[str, dict[str, Any]],
    execution_authorization: dict[str, Any],
) -> str | None:
    if status == "passed":
        return None
    if any(check.get("status") != "passed" for check in checks.values()):
        return "Required validation, inventory, or runtime dependency checks are not all passed."
    if execution_authorization.get("status") != "passed":
        return "Remote execution authorization is not open."
    return "Phase 5 readiness is not complete."


def _configured_root_env(
    config_name: str,
    section: str,
    item_id: str,
    env_field: str,
    path_fields: tuple[str, ...],
) -> str:
    entry = _config_entry(REPO_ROOT / "project_config" / config_name, section, item_id)
    env_name = entry.get(env_field)
    if env_name:
        return str(env_name)
    for field in path_fields:
        match = _ENV_TEMPLATE.search(str(entry.get(field, "")))
        if match is not None:
            return match.group(1)
    raise ValueError(f"{item_id} does not declare {env_field} or a path template environment variable.")


def _config_entry(config_path: Path, section: str, item_id: str) -> dict[str, Any]:
    data = parse_simple_yaml(config_path)
    items = data.get(section, {})
    if not isinstance(items, dict):
        return {}
    entry = items.get(item_id, {})
    return entry if isinstance(entry, dict) else {}


class _temporary_env:
    def __init__(self, updates: dict[str, str]) -> None:
        self.updates = updates
        self.previous: dict[str, str | None] = {}

    def __enter__(self) -> None:
        for name, value in self.updates.items():
            self.previous[name] = os.environ.get(name)
            os.environ[name] = value

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        for name, value in self.previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _write_bundle(output_dir: Path, bundle: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "phase5_readiness.json", bundle)
    write_text(output_dir / "phase5_readiness.md", _markdown_summary(bundle))


def _markdown_summary(bundle: dict[str, Any]) -> str:
    target = bundle["target"]
    check_lines = [
        f"- {name}: `{payload.get('status')}`"
        for name, payload in bundle["checks"].items()
    ]
    gate_names = [
        failure.get("name", "unknown")
        for failure in bundle["execution_authorization"].get("gate_failures", [])
    ]
    gate_text = ", ".join(f"`{name}`" for name in gate_names) if gate_names else "`none`"
    safety_lines = [
        f"- {name}: `{str(value).lower()}`"
        for name, value in bundle["safety_flags"].items()
    ]
    next_action_lines = [f"- {action}" for action in bundle["next_actions"]]
    return (
        "# Phase 5 Readiness\n\n"
        f"Status: `{bundle['status']}`\n\n"
        "## Target\n\n"
        f"- model: `{target['model_id']}`\n"
        f"- benchmark: `{target['benchmark_id']}`\n"
        f"- limit: `{target['limit']}`\n"
        f"- instrumentation: `{target['instrumentation_mode']}`\n\n"
        "## Checks\n\n"
        + "\n".join(check_lines)
        + "\n\n"
        "## Execution Authorization\n\n"
        f"- status: `{bundle['execution_authorization'].get('status')}`\n"
        f"- gate_failures: {gate_text}\n\n"
        "## Safety Flags\n\n"
        + "\n".join(safety_lines)
        + "\n\n"
        "## Next Actions\n\n"
        + "\n".join(next_action_lines)
        + "\n\n"
        "## Stop Reason\n\n"
        f"{bundle.get('do_not_continue_reason') or 'None'}\n"
    )
