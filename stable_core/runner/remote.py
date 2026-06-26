from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from stable_core.schemas.common import ValidationReport
from stable_core.storage.run_directory import validate_run_id
from stable_core.validation.preflight import REPO_ROOT, parse_simple_yaml


ALLOWED_REMOTE_ACTIONS: frozenset[str] = frozenset(
    {
        "validate_paths",
        "collect_env",
        "run_fake_benchmark",
        "run_model_smoke_test",
        "run_benchmark_adapter",
        "parse_results",
        "cancel_job",
        "poll_job",
        "dummy_job",
    }
)

ALLOWED_REMOTE_SCRIPTS: frozenset[str] = frozenset(
    {
        "scripts/dummy_job.py",
        "experiments/fake/run_fake_benchmark.py",
        "experiments/landmark_baselines/run_landmark.py",
    }
)

DEFAULT_SERVER_CONFIG = REPO_ROOT / "project_config" / "server.yaml"
DEFAULT_BUDGET_CONFIG = REPO_ROOT / "project_config" / "experiment_budget.yaml"
GPU_ACTIONS: frozenset[str] = frozenset({"run_model_smoke_test", "run_benchmark_adapter"})
PROCESS_ACTIONS: frozenset[str] = frozenset(
    {"run_fake_benchmark", "run_model_smoke_test", "run_benchmark_adapter"}
)
LANDMARK_SMOKE_ARTIFACT_CONTRACT: dict[str, Any] = {
    "success_outputs": [
        "run_manifest.json",
        "raw_outputs.jsonl",
        "normalized_outputs.jsonl",
        "metrics.json",
        "failure_cases.jsonl",
        "artifact_manifest.json",
        "experiment_summary.md",
    ],
    "failure_outputs": [
        "run_manifest.json",
        "stdout.log",
        "stderr.log",
        "exit_code.txt",
        "env_snapshot.json",
        "failure.json",
        "failure_report.md",
        "artifact_manifest.json",
    ],
    "never_overwrite": ["raw_outputs.jsonl"],
    "large_artifact_policy": "manifest_only",
}


@dataclass(frozen=True)
class RemoteAction:
    action: str
    experiment_id: str | None = None
    allowed_script: str | None = None
    model_id: str | None = None
    benchmark_id: str | None = None
    limit: int | None = None
    instrumentation_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_remote_action(action: RemoteAction) -> RemoteAction:
    if action.action not in ALLOWED_REMOTE_ACTIONS:
        raise ValueError(f"remote action {action.action!r} is not whitelisted")
    if action.experiment_id is not None:
        try:
            validate_run_id(str(action.experiment_id))
        except ValueError as exc:
            raise ValueError(f"experiment_id must be a safe run id: {exc}") from exc
    if action.allowed_script is not None:
        if action.allowed_script.startswith("/") or ".." in action.allowed_script or "\\" in action.allowed_script:
            raise ValueError("allowed_script must be a safe repository-relative path")
        if action.allowed_script not in ALLOWED_REMOTE_SCRIPTS:
            raise ValueError(f"allowed_script {action.allowed_script!r} is not whitelisted")
    if action.limit is not None and action.limit < 0:
        raise ValueError("limit must be non-negative")
    return action


class RemoteRunner:
    """Structured remote runner placeholder.

    Phase 3 intentionally validates remote actions only. Real SSH/GPU execution is
    introduced behind later validation gates so arbitrary shell cannot slip in here.
    """

    def __init__(
        self,
        *,
        server_config: str | Path = DEFAULT_SERVER_CONFIG,
        budget_config: str | Path = DEFAULT_BUDGET_CONFIG,
    ) -> None:
        self.server_config = Path(server_config)
        self.budget_config = Path(budget_config)

    def validate(self, experiment_spec: dict[str, Any]) -> ValidationReport:
        try:
            action = RemoteAction(
                action=str(experiment_spec.get("action", "")),
                experiment_id=experiment_spec.get("experiment_id"),
                allowed_script=experiment_spec.get("allowed_script"),
                model_id=experiment_spec.get("model_id"),
                benchmark_id=experiment_spec.get("benchmark_id"),
                limit=experiment_spec.get("limit"),
                instrumentation_mode=experiment_spec.get("instrumentation_mode"),
            )
            validate_remote_action(action)
        except Exception as exc:
            return ValidationReport(status="failed", checks=[{"name": "remote_action", "error": str(exc)}], summary="Remote action rejected")
        return ValidationReport(status="passed", checks=[{"name": "remote_action", "status": "passed"}], summary="Remote action accepted")

    def submit(self, experiment_spec: dict[str, Any], *, plan_only: bool = False) -> dict[str, Any]:
        report = self.validate(experiment_spec)
        if report.status != "passed":
            return {"status": "failed", "validation": report.to_dict()}
        server = parse_simple_yaml(self.server_config).get("server", {})
        budget = parse_simple_yaml(self.budget_config).get("budget", {})
        runner_mode = str(server.get("runner_mode", "local_only"))
        allow_real_gpu_jobs = _as_bool(budget.get("allow_real_gpu_jobs"), default=False)
        allow_process_submission = _as_bool(budget.get("allow_process_submission"), default=False)
        action_name = str(experiment_spec.get("action"))

        gate_failures = []
        if runner_mode != "remote_enabled":
            gate_failures.append(
                {
                    "name": "runner_mode",
                    "status": "needs_attention",
                    "expected": "remote_enabled",
                    "actual": runner_mode,
                }
            )
        if action_name in GPU_ACTIONS and not allow_real_gpu_jobs:
            gate_failures.append(
                {
                    "name": "real_gpu_budget",
                    "status": "needs_attention",
                    "expected": True,
                    "actual": allow_real_gpu_jobs,
                }
            )
        if action_name in PROCESS_ACTIONS and not allow_process_submission:
            gate_failures.append(
                {
                    "name": "process_submission",
                    "status": "needs_attention",
                    "expected": True,
                    "actual": allow_process_submission,
                }
            )
        execution_plan = _build_execution_plan(experiment_spec, submits_process=False)
        if gate_failures:
            return {
                "status": "needs_attention",
                "runner_mode": runner_mode,
                "allow_real_gpu_jobs": allow_real_gpu_jobs,
                "allow_process_submission": allow_process_submission,
                "submitted_process": False,
                "execution_plan": execution_plan,
                "gate_failures": gate_failures,
                "message": "Remote execution gate is closed by configuration.",
            }
        if plan_only:
            return {
                "status": "needs_attention",
                "runner_mode": runner_mode,
                "allow_real_gpu_jobs": allow_real_gpu_jobs,
                "allow_process_submission": allow_process_submission,
                "submitted_process": False,
                "execution_plan": execution_plan,
                "gate_failures": [
                    {
                        "name": "plan_only",
                        "status": "needs_attention",
                        "message": "Execution plan requested without process submission.",
                    }
                ],
                "message": "Remote execution plan generated without submitting a process.",
            }
        if action_name not in PROCESS_ACTIONS:
            return {
                "status": "needs_attention",
                "runner_mode": runner_mode,
                "allow_real_gpu_jobs": allow_real_gpu_jobs,
                "allow_process_submission": allow_process_submission,
                "submitted_process": False,
                "execution_plan": execution_plan,
                "gate_failures": [
                    {
                        "name": "non_process_action",
                        "status": "needs_attention",
                        "message": "This remote action is not handled by the subprocess executor.",
                    }
                ],
                "message": "Remote action is valid but is not a process-submitting action.",
            }
        execution_plan = _build_execution_plan(experiment_spec, submits_process=True)
        process_result = _submit_process(execution_plan)
        return {
            "status": _status_from_process(process_result),
            "runner_mode": runner_mode,
            "allow_real_gpu_jobs": allow_real_gpu_jobs,
            "allow_process_submission": allow_process_submission,
            "execution_plan": execution_plan,
            "gate_failures": [],
            **process_result,
        }

    def poll(self, job_id: str) -> dict[str, Any]:
        return {"job_id": job_id, "status": "needs_attention", "message": "No remote jobs are submitted in Phase 3."}

    def resume(self, workflow_id: str) -> dict[str, Any]:
        return {"workflow_id": workflow_id, "status": "needs_attention", "message": "Remote resume is not active in Phase 3."}

    def cancel(self, job_id: str) -> dict[str, Any]:
        return {"job_id": job_id, "status": "needs_attention", "message": "No remote job exists to cancel in Phase 3."}


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _build_execution_plan(experiment_spec: dict[str, Any], *, submits_process: bool) -> dict[str, Any]:
    action = str(experiment_spec.get("action"))
    allowed_script = str(experiment_spec.get("allowed_script"))
    experiment_id = str(experiment_spec.get("experiment_id") or _default_experiment_id(experiment_spec))
    plan: dict[str, Any] = {
        "experiment_id": experiment_id,
        "action": action,
        "allowed_script": allowed_script,
        "argv": _argv_for_action(experiment_spec, experiment_id),
        "cwd": ".",
        "submits_process": submits_process,
    }
    artifact_contract = _artifact_contract_for_action(action, allowed_script)
    if artifact_contract:
        plan["artifact_contract"] = artifact_contract
    return plan


def _artifact_contract_for_action(action: str, allowed_script: str) -> dict[str, Any]:
    if action != "run_model_smoke_test" or allowed_script != "experiments/landmark_baselines/run_landmark.py":
        return {}
    return dict(LANDMARK_SMOKE_ARTIFACT_CONTRACT)


def _argv_for_action(experiment_spec: dict[str, Any], experiment_id: str) -> list[str]:
    action = str(experiment_spec.get("action"))
    allowed_script = str(experiment_spec.get("allowed_script"))
    if action == "run_model_smoke_test" and allowed_script == "experiments/landmark_baselines/run_landmark.py":
        argv = [
            "python",
            allowed_script,
            "--model",
            str(experiment_spec.get("model_id")),
            "--benchmark",
            str(experiment_spec.get("benchmark_id")),
            "--limit",
            str(experiment_spec.get("limit")),
            "--instrumentation",
            str(experiment_spec.get("instrumentation_mode") or "none"),
            "--run-id",
            experiment_id,
        ]
        if experiment_spec.get("runs_root") is not None:
            argv.extend(["--runs-root", str(experiment_spec["runs_root"])])
        return argv
    return ["python", allowed_script]


def _default_experiment_id(experiment_spec: dict[str, Any]) -> str:
    model_id = str(experiment_spec.get("model_id") or "model")
    benchmark_id = str(experiment_spec.get("benchmark_id") or "benchmark")
    limit = str(experiment_spec.get("limit") or "all")
    return f"{model_id}_{benchmark_id}_limit{limit}"


def _submit_process(execution_plan: dict[str, Any]) -> dict[str, Any]:
    argv = list(execution_plan["argv"])
    process_argv = [sys.executable, *argv[1:]] if argv and argv[0] == "python" else argv
    completed = subprocess.run(
        process_argv,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    worker_payload = _parse_worker_payload(completed.stdout)
    return {
        "submitted_process": True,
        "job_id": execution_plan["experiment_id"],
        "exit_code": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "worker_payload": worker_payload,
        "message": "Whitelisted remote worker process completed.",
    }


def _parse_worker_payload(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {"status": "failed", "error": "Worker produced no JSON stdout."}
    try:
        payload = json.loads(text.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return {"status": "failed", "error": f"Worker stdout was not valid JSON: {exc}"}
    return payload if isinstance(payload, dict) else {"status": "failed", "error": "Worker JSON stdout was not an object."}


def _status_from_process(process_result: dict[str, Any]) -> str:
    payload = process_result["worker_payload"]
    payload_status = str(payload.get("status"))
    if process_result["exit_code"] == 0 and payload_status == "succeeded":
        return "passed"
    if payload_status == "needs_attention":
        return "needs_attention"
    return "failed"
