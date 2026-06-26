from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from stable_core.schemas.common import ValidationReport
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


@dataclass(frozen=True)
class RemoteAction:
    action: str
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

    def submit(self, experiment_spec: dict[str, Any]) -> dict[str, Any]:
        report = self.validate(experiment_spec)
        if report.status != "passed":
            return {"status": "failed", "validation": report.to_dict()}
        server = parse_simple_yaml(self.server_config).get("server", {})
        budget = parse_simple_yaml(self.budget_config).get("budget", {})
        runner_mode = str(server.get("runner_mode", "local_only"))
        allow_real_gpu_jobs = _as_bool(budget.get("allow_real_gpu_jobs"), default=False)

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
        if str(experiment_spec.get("action")) in GPU_ACTIONS and not allow_real_gpu_jobs:
            gate_failures.append(
                {
                    "name": "real_gpu_budget",
                    "status": "needs_attention",
                    "expected": True,
                    "actual": allow_real_gpu_jobs,
                }
            )
        if gate_failures:
            return {
                "status": "needs_attention",
                "runner_mode": runner_mode,
                "allow_real_gpu_jobs": allow_real_gpu_jobs,
                "gate_failures": gate_failures,
                "message": "Remote execution gate is closed by configuration.",
            }
        return {
            "status": "needs_attention",
            "runner_mode": runner_mode,
            "allow_real_gpu_jobs": allow_real_gpu_jobs,
            "gate_failures": [
                {
                    "name": "remote_executor",
                    "status": "needs_attention",
                    "message": "No reviewed remote executor implementation is enabled yet.",
                }
            ],
            "message": "Remote execution config gates are open, but no reviewed executor is implemented.",
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
