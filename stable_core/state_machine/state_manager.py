from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stable_core.storage.run_directory import collect_git_snapshot, ensure_run_dir, read_json, utc_now, write_json


WORKFLOW_STATES: tuple[str, ...] = (
    "preflight_validation",
    "context_building",
    "baseline_code_research",
    "external_framework_research",
    "recent_paper_research",
    "architecture_design",
    "interface_contract_design",
    "codex_mvp_build",
    "pro_framework_review_browser",
    "framework_revision",
    "fake_end_to_end_test",
    "qwen_pope_landmark_smoke",
    "landmark_baseline_eval_full",
    "pro_idea_generation_browser",
    "evidence_grounded_agent_review",
    "arbiter_decision",
    "minimal_experiment_design",
    "codex_idea_implementation",
    "gpu_experiment",
    "phenomenon_analysis",
    "failure_driven_refinement",
    "convergence_check",
)

JOB_STATUSES: tuple[str, ...] = (
    "pending",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "needs_attention",
    "skipped_due_to_cache",
    "blocked_by_gate",
)

WORKFLOW_STATE_SCHEMA: dict[str, Any] = {
    "title": "WorkflowState",
    "type": "object",
    "required": [
        "workflow_id",
        "current_state",
        "state_version",
        "round_id",
        "attempt",
        "status",
        "created_at",
        "updated_at",
        "last_heartbeat",
        "git",
        "inputs",
        "outputs",
        "run_dir",
        "remote_job",
        "failure",
        "next_allowed_actions",
    ],
}


@dataclass
class WorkflowState:
    workflow_id: str
    current_state: str = "preflight_validation"
    state_version: int = 1
    round_id: str = "round_0001"
    attempt: int = 1
    status: str = "pending"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    last_heartbeat: str | None = None
    git: dict[str, Any] = field(default_factory=dict)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    run_dir: str | None = None
    remote_job: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None
    next_allowed_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkflowState":
        return cls(**payload)


class StateManager:
    def __init__(self, runs_root: str | Path = Path("runs"), repo_root: str | Path | None = None) -> None:
        self.runs_root = Path(runs_root)
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]

    def init_workflow(
        self,
        workflow_id: str,
        *,
        current_state: str = "preflight_validation",
        round_id: str = "round_0001",
        inputs: list[dict[str, Any]] | None = None,
        force: bool = False,
    ) -> WorkflowState:
        self._validate_state_name(current_state)
        run_dir = ensure_run_dir(self.runs_root, workflow_id)
        state_path = run_dir / "state.json"
        if state_path.exists() and not force:
            return self.load(workflow_id)
        now = utc_now()
        state = WorkflowState(
            workflow_id=workflow_id,
            current_state=current_state,
            round_id=round_id,
            created_at=now,
            updated_at=now,
            git=collect_git_snapshot(self.repo_root),
            inputs=inputs or [],
            run_dir=str(run_dir),
            next_allowed_actions=self._next_allowed_actions("pending", None),
        )
        return self.save(state)

    def load(self, workflow_id: str) -> WorkflowState:
        run_dir = ensure_run_dir(self.runs_root, workflow_id)
        state_path = run_dir / "state.json"
        if not state_path.exists():
            raise FileNotFoundError(f"workflow state not found: {state_path}")
        payload = read_json(state_path)
        return WorkflowState.from_dict(payload)

    def save(self, state: WorkflowState) -> WorkflowState:
        self._validate_status(state.status)
        self._validate_state_name(state.current_state)
        run_dir = ensure_run_dir(self.runs_root, state.workflow_id)
        state.run_dir = state.run_dir or str(run_dir)
        state.updated_at = utc_now()
        state.next_allowed_actions = self._next_allowed_actions(state.status, state.remote_job)
        write_json(run_dir / "state.json", state.to_dict())
        return state

    def update_status(
        self,
        workflow_id: str,
        *,
        status: str,
        current_state: str | None = None,
        remote_job: dict[str, Any] | None = None,
        outputs: list[dict[str, Any]] | None = None,
    ) -> WorkflowState:
        self._validate_status(status)
        state = self.load(workflow_id)
        if current_state is not None:
            self._validate_state_name(current_state)
            state.current_state = current_state
        state.status = status
        if remote_job is not None:
            state.remote_job = remote_job
        if outputs is not None:
            state.outputs = outputs
        if status == "running" and state.last_heartbeat is None:
            state.last_heartbeat = utc_now()
        return self.save(state)

    def heartbeat(self, workflow_id: str) -> WorkflowState:
        state = self.load(workflow_id)
        state.last_heartbeat = utc_now()
        return self.save(state)

    def checkpoint(
        self,
        workflow_id: str,
        *,
        outputs: list[dict[str, Any]] | None = None,
        remote_job: dict[str, Any] | None = None,
    ) -> WorkflowState:
        state = self.load(workflow_id)
        if outputs is not None:
            state.outputs = outputs
        if remote_job is not None:
            state.remote_job = remote_job
        return self.save(state)

    def retry(self, workflow_id: str, *, reason: str | None = None) -> WorkflowState:
        state = self.load(workflow_id)
        state.attempt += 1
        state.status = "pending"
        state.remote_job = None
        state.failure = None
        if reason:
            state.outputs.append({"kind": "retry_note", "message": reason, "recorded_at": utc_now()})
        return self.save(state)

    def check_heartbeat_timeout(self, workflow_id: str, *, timeout_seconds: int) -> WorkflowState:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        state = self.load(workflow_id)
        if state.status != "running" or state.last_heartbeat is None:
            return state
        heartbeat_at = _parse_utc(state.last_heartbeat)
        elapsed = datetime.now(timezone.utc) - heartbeat_at
        if elapsed.total_seconds() > timeout_seconds:
            state.status = "needs_attention"
            state.failure = {
                "failure_type": "heartbeat_timeout",
                "failure_message": f"Workflow heartbeat exceeded {timeout_seconds} seconds.",
                "recorded_at": utc_now(),
                "current_state": state.current_state,
                "remote_job": state.remote_job,
                "recommended_next_action": "Poll the remote job and inspect logs before any retry.",
            }
        return self.save(state)

    def mark_failed(self, workflow_id: str, *, reason: str, failure_type: str = "manual_mark_failed") -> WorkflowState:
        state = self.load(workflow_id)
        state.status = "failed"
        state.failure = {
            "failure_type": failure_type,
            "failure_message": reason,
            "recorded_at": utc_now(),
            "current_state": state.current_state,
            "recommended_next_action": "Inspect failure artifacts, then resume only after the cause is fixed.",
        }
        return self.save(state)

    def resume(self, workflow_id: str) -> WorkflowState:
        state = self.load(workflow_id)
        if state.status == "cancelled":
            state.status = "needs_attention"
            state.failure = state.failure or {
                "failure_type": "resume_cancelled_workflow",
                "failure_message": "Cancelled workflows require explicit operator review before resume.",
                "recorded_at": utc_now(),
                "recommended_next_action": "Create a new workflow or manually mark an approved next state.",
            }
        return self.save(state)

    def _next_allowed_actions(self, status: str, remote_job: dict[str, Any] | None) -> list[str]:
        if status == "running":
            actions = ["poll_job", "mark_failed"]
            if remote_job:
                actions.append("cancel_job")
            return actions
        if status == "pending":
            return ["resume", "mark_failed"]
        if status == "failed":
            return ["resume", "mark_failed"]
        if status == "needs_attention":
            return ["mark_failed"]
        return []

    def _validate_state_name(self, current_state: str) -> None:
        if current_state not in WORKFLOW_STATES:
            raise ValueError(f"current_state must be one of {sorted(WORKFLOW_STATES)}, got {current_state!r}")

    def _validate_status(self, status: str) -> None:
        if status not in JOB_STATUSES:
            raise ValueError(f"status must be one of {sorted(JOB_STATUSES)}, got {status!r}")


def _parse_utc(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)
