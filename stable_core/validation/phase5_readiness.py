from __future__ import annotations

from pathlib import Path
from typing import Any

from experiments.fake.evaluator import validate_benchmark, validate_model
from stable_core.config import validate_config
from stable_core.runner.remote import RemoteRunner
from stable_core.storage.run_directory import current_git_commit, utc_now, write_json, write_text
from stable_core.validation.inventory_discovery import discover_benchmark_inventory, discover_model_inventory


SAFETY_FLAGS = {
    "executed_real_model": False,
    "executed_real_benchmark": False,
    "submitted_remote_job": False,
    "raw_outputs_written": False,
    "write_config": False,
}


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


def _readiness_status(checks: dict[str, dict[str, Any]], execution_authorization: dict[str, Any]) -> str:
    statuses = [str(check.get("status")) for check in checks.values()]
    execution_status = str(execution_authorization.get("status"))
    if "failed" in statuses or execution_status == "failed":
        return "failed"
    if all(status == "passed" for status in statuses) and execution_status == "passed":
        return "passed"
    return "needs_attention"


def _next_actions(checks: dict[str, dict[str, Any]], execution_authorization: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if checks["model_validation"].get("status") != "passed":
        actions.append("Configure and populate the approved model path, then rerun validate-model.")
    if checks["benchmark_validation"].get("status") != "passed":
        actions.append("Configure and populate the approved benchmark path, then rerun validate-benchmark.")
    if execution_authorization.get("status") != "passed":
        actions.append("Open reviewed remote execution, GPU budget, and process-submission gates only after validation passes.")
    if not actions:
        actions.append("Run the controlled Phase 5 real smoke through the reviewed RemoteRunner path.")
    return actions


def _do_not_continue_reason(
    status: str,
    checks: dict[str, dict[str, Any]],
    execution_authorization: dict[str, Any],
) -> str | None:
    if status == "passed":
        return None
    if any(check.get("status") != "passed" for check in checks.values()):
        return "Required validation or inventory checks are not all passed."
    if execution_authorization.get("status") != "passed":
        return "Remote execution authorization is not open."
    return "Phase 5 readiness is not complete."


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
