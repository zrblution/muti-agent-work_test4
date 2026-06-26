from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from stable_core.runner.remote import RemoteAction, validate_remote_action
from stable_core.schemas.common import ValidationReport
from stable_core.storage.run_directory import (
    REPO_ROOT,
    artifact_manifest_for,
    collect_env_snapshot,
    current_git_commit,
    ensure_run_dir,
    tail_text,
    utc_now,
    write_json,
    write_text,
)


class LocalRunner:
    def __init__(self, runs_root: str | Path = Path("runs"), repo_root: str | Path = REPO_ROOT) -> None:
        self.runs_root = Path(runs_root)
        self.repo_root = Path(repo_root)

    def validate(self, experiment_spec: dict[str, Any]) -> ValidationReport:
        action_name = str(experiment_spec.get("action", ""))
        try:
            validate_remote_action(RemoteAction(action=action_name, allowed_script="scripts/dummy_job.py"))
        except Exception as exc:
            return ValidationReport(status="failed", checks=[{"name": "local_action", "error": str(exc)}], summary="Local action rejected")
        if action_name != "dummy_job":
            return ValidationReport(
                status="failed",
                checks=[{"name": "local_action", "error": "Phase 3 LocalRunner only supports dummy_job"}],
                summary="Local action rejected",
            )
        return ValidationReport(status="passed", checks=[{"name": "local_action", "status": "passed"}], summary="Local action accepted")

    def submit(self, experiment_spec: dict[str, Any]) -> dict[str, Any]:
        report = self.validate(experiment_spec)
        if report.status != "passed":
            return {"status": "failed", "validation": report.to_dict()}
        return self.run_dummy(
            run_id=str(experiment_spec["run_id"]),
            message=str(experiment_spec.get("message", "dummy job")),
            fail=bool(experiment_spec.get("fail", False)),
        )

    def poll(self, job_id: str) -> dict[str, Any]:
        run_dir = self.runs_root / job_id
        manifest = run_dir / "run_manifest.json"
        if not manifest.exists():
            return {"job_id": job_id, "status": "needs_attention", "message": "run_manifest.json not found"}
        return {"job_id": job_id, "status": "recorded", "run_manifest": str(manifest)}

    def resume(self, workflow_id: str) -> dict[str, Any]:
        return {"workflow_id": workflow_id, "status": "needs_attention", "message": "LocalRunner resume is handled by StateManager in Phase 3."}

    def cancel(self, job_id: str) -> dict[str, Any]:
        return {"job_id": job_id, "status": "needs_attention", "message": "Completed local dummy jobs cannot be cancelled."}

    def run_dummy(self, *, run_id: str, message: str = "dummy job", fail: bool = False) -> dict[str, Any]:
        run_dir = ensure_run_dir(self.runs_root, run_id)
        started_at = utc_now()
        command = [sys.executable, str(self.repo_root / "scripts" / "dummy_job.py"), "--message", message]
        if fail:
            command.append("--fail")

        write_json(
            run_dir / "command_manifest.json",
            {
                "run_id": run_id,
                "action": "dummy_job",
                "argv": command,
                "controlled": True,
                "started_at": started_at,
            },
        )
        write_json(run_dir / "env_snapshot.json", collect_env_snapshot(self.repo_root))
        write_text(run_dir / "git_commit.txt", current_git_commit(self.repo_root) + "\n")

        result = subprocess.run(command, cwd=self.repo_root, text=True, capture_output=True, check=False)
        finished_at = utc_now()
        status = "succeeded" if result.returncode == 0 else "failed"

        write_text(run_dir / "stdout.log", result.stdout)
        write_text(run_dir / "stderr.log", result.stderr)
        write_text(run_dir / "exit_code.txt", f"{result.returncode}\n")
        run_manifest = {
            "run_id": run_id,
            "run_type": "preflight",
            "model_id": None,
            "benchmark_id": None,
            "idea_id": None,
            "limit": None,
            "instrumentation_mode": "none",
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "config_snapshot_sha256": None,
            "git_commit": current_git_commit(self.repo_root),
            "outputs": {
                "stdout": "stdout.log",
                "stderr": "stderr.log",
                "exit_code": "exit_code.txt",
            },
            "missing_outputs": {
                "raw_outputs": "dummy job does not produce benchmark raw outputs",
                "normalized_outputs": "dummy job does not produce benchmark normalized outputs",
                "metrics": "dummy job does not compute benchmark metrics",
                "failure_cases": "dummy job does not run benchmark failure-case extraction",
            },
        }
        write_json(run_dir / "run_manifest.json", run_manifest)

        if status == "failed":
            failure = {
                "failure_type": "local_runner_exit_nonzero",
                "failure_message": f"Controlled dummy job exited with code {result.returncode}",
                "stack_trace": None,
                "stdout_tail": tail_text(result.stdout),
                "stderr_tail": tail_text(result.stderr),
                "reproduction_command": " ".join(command),
                "config_snapshot": {},
                "state_snapshot": run_manifest,
                "recommended_next_action": "Inspect stdout.log and stderr.log, then rerun the same controlled dummy action if appropriate.",
            }
            write_json(run_dir / "failure.json", failure)
            write_text(
                run_dir / "failure_report.md",
                "# Failure Report\n\n"
                f"- failure_type: `{failure['failure_type']}`\n"
                f"- failure_message: {failure['failure_message']}\n"
                f"- reproduction_command: `{failure['reproduction_command']}`\n",
            )

        write_json(run_dir / "artifact_manifest.json", artifact_manifest_for(run_dir, run_id))
        return {"run_id": run_id, "run_dir": str(run_dir), "status": status, "exit_code": result.returncode}
