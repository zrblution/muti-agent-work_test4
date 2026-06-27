from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from experiments.fake.evaluator import MODEL_ADAPTERS, validate_benchmark, validate_model, validate_model_runtime
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


def build_phase5_explicit_model_path_probe(
    *,
    model_id: str,
    benchmark_id: str,
    model_path: str | Path,
    benchmark_root: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    benchmark_env = _configured_root_env("benchmarks.yaml", "benchmarks", benchmark_id, "benchmark_root_env", ("path",))
    candidate_benchmark_env = {benchmark_env: str(benchmark_root)}
    model_path_value = Path(model_path)
    with _temporary_env(candidate_benchmark_env):
        checks = {
            "config": validate_config(),
            "model_runtime_dependencies": validate_model_runtime(model_id),
            "model_explicit_path_validation": _validate_model_explicit_path(model_id, model_path_value),
            "benchmark_inventory_discovery": discover_benchmark_inventory(benchmark_id),
            "benchmark_validation": validate_benchmark(benchmark_id),
        }
    status = _checks_status(checks)
    configured_dir = _configured_model_dir(model_id)
    contract_satisfied = model_path_value.name == configured_dir
    report = {
        "phase": "Phase 5",
        "mode": "explicit_model_path_probe",
        "status": status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "target": {
            "model_id": model_id,
            "benchmark_id": benchmark_id,
        },
        "candidate_model_path": str(model_path_value),
        "candidate_benchmark_env": candidate_benchmark_env,
        "configured_root_contract": {
            "model_dir": configured_dir,
            "satisfied": contract_satisfied,
            "message": (
                "Candidate path matches the configured model directory name."
                if contract_satisfied
                else "Candidate path is an explicit model path and does not satisfy the configured root/subdirectory contract."
            ),
        },
        "requires_human_approval": not contract_satisfied,
        "checks": checks,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _explicit_model_path_next_actions(status, checks, contract_satisfied),
    }
    if output is not None:
        write_json(Path(output), report)
    return report


def build_phase5_model_path_decision_request(
    *,
    model_id: str,
    benchmark_id: str,
    model_path: str | Path,
    benchmark_root: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    probe = build_phase5_explicit_model_path_probe(
        model_id=model_id,
        benchmark_id=benchmark_id,
        model_path=model_path,
        benchmark_root=benchmark_root,
    )
    bundle = {
        "phase": "Phase 5",
        "mode": "model_path_decision_request",
        "status": "needs_attention",
        "approval_status": "pending",
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "target": {
            "model_id": model_id,
            "benchmark_id": benchmark_id,
            "model_path": str(Path(model_path)),
            "benchmark_root": str(Path(benchmark_root)),
        },
        "probe": probe,
        "requested_decision": {
            "question": "Approve this exact model path as the Phase 5 Qwen3-VL path, reject it, or provide the base model root.",
            "allowed_decisions": [
                "approve_variant_path",
                "reject_variant_path",
                "provide_base_model_root",
            ],
            "approval_record_template": {
                "decision": None,
                "approver": None,
                "approved_model_path": str(Path(model_path)),
                "approved_benchmark_root": str(Path(benchmark_root)),
                "rationale": None,
            },
        },
        "safety_flags": dict(SAFETY_FLAGS),
        "do_not_continue_reason": (
            "Human approval is pending for a non-contract model path."
            if probe.get("requires_human_approval")
            else "Human review is pending before this model path is used for execution."
        ),
        "next_actions": [
            "Review the exact model-path probe and decide whether this path is an approved Phase 5 target.",
            "Do not open process submission or run the real smoke until the decision is recorded and config representation is reviewed.",
        ],
    }
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    write_json(output_path / "phase5_model_path_decision_request.json", bundle)
    write_text(output_path / "phase5_model_path_decision_request.md", _model_path_decision_request_markdown(bundle))
    return bundle


def validate_phase5_model_path_decision(
    *,
    request_path: str | Path,
    decision_record_path: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    request_file = Path(request_path)
    decision_file = Path(decision_record_path)
    request = json.loads(request_file.read_text(encoding="utf-8"))
    decision_record = json.loads(decision_file.read_text(encoding="utf-8"))
    target = request.get("target", {})
    probe = request.get("probe", {})
    requested_decision = request.get("requested_decision", {})
    allowed_decisions = requested_decision.get("allowed_decisions", [])
    decision = str(decision_record.get("decision", ""))
    checks = _decision_validation_checks(
        request=request,
        decision_record=decision_record,
        target=target,
        probe=probe,
        allowed_decisions=allowed_decisions,
        decision=decision,
    )
    status = _decision_validation_status(checks, decision)
    approval_status = _decision_approval_status(status, decision)
    report = {
        "phase": "Phase 5",
        "mode": "model_path_decision_validation",
        "status": status,
        "approval_status": approval_status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "request_path": str(request_file),
        "decision_record_path": str(decision_file),
        "target": {
            "model_id": target.get("model_id"),
            "benchmark_id": target.get("benchmark_id"),
            "model_path": target.get("model_path"),
            "benchmark_root": target.get("benchmark_root"),
        },
        "decision": decision_record,
        "checks": checks,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _decision_validation_next_actions(status, decision),
        "do_not_continue_reason": _decision_validation_stop_reason(status, decision),
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


def _decision_validation_checks(
    *,
    request: dict[str, Any],
    decision_record: dict[str, Any],
    target: dict[str, Any],
    probe: dict[str, Any],
    allowed_decisions: Any,
    decision: str,
) -> dict[str, dict[str, Any]]:
    allowed = allowed_decisions if isinstance(allowed_decisions, list) else []
    checks: dict[str, dict[str, Any]] = {
        "request_mode": _check(
            request.get("mode") == "model_path_decision_request",
            "Request is a Phase 5 model-path decision request.",
        ),
        "request_pending": _check(
            request.get("approval_status") == "pending",
            "Request is still pending human decision.",
        ),
        "decision_allowed": _check(
            decision in allowed,
            "Decision is one of the options declared by the request.",
        ),
        "approver_present": _check(
            bool(str(decision_record.get("approver", "")).strip()),
            "Decision record names a human approver.",
        ),
        "rationale_present": _check(
            bool(str(decision_record.get("rationale", "")).strip()),
            "Decision record includes a rationale.",
        ),
    }
    if decision == "approve_variant_path":
        checks.update(
            {
                "probe_passed": _check(
                    probe.get("status") == "passed",
                    "Approval can only reference a passed explicit model-path probe.",
                ),
                "approved_model_path_matches": _check(
                    decision_record.get("approved_model_path") == target.get("model_path"),
                    "Approved model path must match the pending request target exactly.",
                ),
                "approved_benchmark_root_matches": _check(
                    decision_record.get("approved_benchmark_root") == target.get("benchmark_root"),
                    "Approved benchmark root must match the pending request target exactly.",
                ),
            }
        )
    elif decision == "provide_base_model_root":
        checks["provided_model_root_present"] = _check(
            bool(str(decision_record.get("provided_model_root", "")).strip()),
            "A provided base model root is required for this decision.",
        )
    return checks


def _check(passed: bool, summary: str) -> dict[str, str]:
    return {"status": "passed" if passed else "failed", "summary": summary}


def _decision_validation_status(checks: dict[str, dict[str, Any]], decision: str) -> str:
    if any(check.get("status") == "failed" for check in checks.values()):
        return "failed"
    if decision == "approve_variant_path":
        return "passed"
    return "needs_attention"


def _decision_approval_status(status: str, decision: str) -> str:
    if status == "failed":
        return "invalid"
    if decision == "approve_variant_path":
        return "approved"
    if decision == "reject_variant_path":
        return "rejected"
    if decision == "provide_base_model_root":
        return "base_model_root_provided"
    return "pending"


def _decision_validation_next_actions(status: str, decision: str) -> list[str]:
    if status == "failed":
        return ["Fix the decision record and rerun the validation command before changing config or execution gates."]
    if decision == "approve_variant_path":
        return [
            "Review the config representation for the approved exact path before any real smoke attempt.",
            "Keep remote execution and process submission closed until readiness is rerun with the approved representation.",
        ]
    if decision == "reject_variant_path":
        return ["Choose a different exact model path or provide a base model root that satisfies the configured contract."]
    if decision == "provide_base_model_root":
        return ["Probe the provided base model root with phase5-probe-paths before exporting env vars or editing config."]
    return ["Record a valid Phase 5 model-path decision before continuing."]


def _decision_validation_stop_reason(status: str, decision: str) -> str | None:
    if status == "failed":
        return "The model-path decision record is invalid."
    if decision == "approve_variant_path":
        return None
    return "A valid approval for an executable Phase 5 model path has not been recorded."


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


def _explicit_model_path_next_actions(status: str, checks: dict[str, dict[str, Any]], contract_satisfied: bool) -> list[str]:
    actions: list[str] = []
    if status == "passed":
        if contract_satisfied:
            actions.append("Review the exact model path, then prefer phase5-probe-paths with the configured root contract before execution.")
        else:
            actions.append("Treat this as a review-only variant path; obtain explicit approval before any config-path override or real smoke attempt.")
        actions.append("Rerun phase5-readiness or a controlled worker plan only after the approved model and benchmark paths are represented in config.")
        return actions
    if checks["model_explicit_path_validation"].get("status") != "passed":
        actions.append("Choose an exact model path whose no-load model validation passes.")
    if checks["benchmark_validation"].get("status") != "passed":
        actions.append("Choose a benchmark root whose configured benchmark subdirectory passes validate-benchmark.")
    if checks["model_runtime_dependencies"].get("status") != "passed":
        actions.append("Install or activate model runtime dependencies before probing exact model paths again.")
    if not actions:
        actions.append("Review failed checks before using this explicit model path.")
    return actions


def _validate_model_explicit_path(model_id: str, model_path: Path) -> dict[str, Any]:
    adapter_class = MODEL_ADAPTERS.get(model_id)
    if adapter_class is None:
        return {"model_id": model_id, "status": "failed", "checks": [], "summary": "Unknown model id."}
    config = dict(_config_entry(REPO_ROOT / "project_config" / "models.yaml", "models", model_id))
    config["local_path"] = str(model_path)
    config.pop("path", None)
    report = adapter_class(config).validate_environment()
    return {"model_id": model_id, **report.to_dict()}


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


def _configured_model_dir(model_id: str) -> str | None:
    entry = _config_entry(REPO_ROOT / "project_config" / "models.yaml", "models", model_id)
    for field in ("local_path", "path"):
        raw_path = entry.get(field)
        if raw_path:
            return Path(str(raw_path)).name
    return None


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


def _model_path_decision_request_markdown(bundle: dict[str, Any]) -> str:
    target = bundle["target"]
    probe = bundle["probe"]
    contract = probe["configured_root_contract"]
    safety_lines = [
        f"- {name}: `{str(value).lower()}`"
        for name, value in bundle["safety_flags"].items()
    ]
    decision_lines = [f"- `{decision}`" for decision in bundle["requested_decision"]["allowed_decisions"]]
    check_lines = [
        f"- {name}: `{payload.get('status')}`"
        for name, payload in probe["checks"].items()
    ]
    return (
        "# Phase 5 Model Path Decision Request\n\n"
        f"Status: `{bundle['status']}`\n\n"
        f"approval_status: `{bundle['approval_status']}`\n\n"
        "## Target\n\n"
        f"- model: `{target['model_id']}`\n"
        f"- benchmark: `{target['benchmark_id']}`\n"
        f"- model_path: `{target['model_path']}`\n"
        f"- benchmark_root: `{target['benchmark_root']}`\n\n"
        "## Probe\n\n"
        f"- status: `{probe['status']}`\n"
        f"- requires_human_approval: `{str(probe['requires_human_approval']).lower()}`\n"
        f"- configured_model_dir: `{contract.get('model_dir')}`\n"
        f"- contract_satisfied: `{str(contract.get('satisfied')).lower()}`\n\n"
        "## Checks\n\n"
        + "\n".join(check_lines)
        + "\n\n"
        "## Requested Decision\n\n"
        + "\n".join(decision_lines)
        + "\n\n"
        "## Safety Flags\n\n"
        + "\n".join(safety_lines)
        + "\n\n"
        "## Stop Reason\n\n"
        f"{bundle['do_not_continue_reason']}\n"
    )
