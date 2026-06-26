from __future__ import annotations

from pathlib import Path
from typing import Any

from experiments.fake.evaluator import validate_benchmark, validate_model
from stable_core.runner.remote import RemoteRunner
from stable_core.storage.run_directory import (
    artifact_manifest_for,
    collect_env_snapshot,
    current_git_commit,
    ensure_run_dir,
    tail_text,
    utc_now,
    validate_run_id,
    write_json,
    write_text,
)


def run_landmark(
    *,
    run_id: str,
    model_id: str,
    benchmark_id: str,
    limit: int,
    instrumentation_mode: str = "none",
    runs_root: str | Path = Path("runs"),
) -> dict[str, Any]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    validate_run_id(run_id)
    if instrumentation_mode not in {"none", "light", "deep"}:
        raise ValueError("instrumentation_mode must be one of none, light, deep")

    run_dir = ensure_run_dir(runs_root, run_id)
    raw_outputs_path = run_dir / "raw_outputs.jsonl"
    if raw_outputs_path.exists() and raw_outputs_path.stat().st_size > 0:
        raise FileExistsError(f"raw_outputs already exists and will not be overwritten: {raw_outputs_path}")

    started_at = utc_now()
    command = {
        "run_id": run_id,
        "command": "run-landmark",
        "model_id": model_id,
        "benchmark_id": benchmark_id,
        "limit": limit,
        "instrumentation_mode": instrumentation_mode,
        "controlled": True,
    }
    write_json(run_dir / "command_manifest.json", command)
    write_json(run_dir / "env_snapshot.json", collect_env_snapshot(Path.cwd()))
    write_text(run_dir / "git_commit.txt", current_git_commit(Path.cwd()) + "\n")
    write_text(run_dir / "stdout.log", "")

    model_report = validate_model(model_id)
    benchmark_report = validate_benchmark(benchmark_id)
    gate_failures = [
        {"gate": "validate-model", "payload": model_report}
        if model_report.get("status") != "passed"
        else None,
        {"gate": "validate-benchmark", "payload": benchmark_report}
        if benchmark_report.get("status") != "passed"
        else None,
    ]
    gate_failures = [item for item in gate_failures if item is not None]

    if gate_failures:
        message = "Landmark validation gates did not pass; no real model or benchmark execution was attempted."
        write_text(run_dir / "stderr.log", message + "\n")
        write_text(run_dir / "exit_code.txt", "1\n")
        return _write_needs_attention(
            run_dir=run_dir,
            run_id=run_id,
            command=command,
            failure_type="landmark_validation_gate_not_ready",
            failure_message=message,
            gate_failures=gate_failures,
            started_at=started_at,
            recommended_next_action=[
                "Configure approved model and benchmark paths.",
                "Re-run validate-model and validate-benchmark until both return passed.",
                "Open a reviewed remote execution gate before any real GPU run.",
            ],
        )

    remote_report = RemoteRunner().submit(
        {
            "experiment_id": run_id,
            "action": "run_model_smoke_test",
            "allowed_script": "experiments/landmark_baselines/run_landmark.py",
            "model_id": model_id,
            "benchmark_id": benchmark_id,
            "limit": limit,
            "instrumentation_mode": instrumentation_mode,
        }
    )
    message = "Remote landmark execution gate is not open; no real model or benchmark execution was attempted."
    write_text(run_dir / "stderr.log", message + "\n")
    write_text(run_dir / "exit_code.txt", "1\n")
    return _write_needs_attention(
        run_dir=run_dir,
        run_id=run_id,
        command=command,
        failure_type="landmark_remote_runner_not_enabled",
        failure_message=message,
        gate_failures=[{"gate": "remote-runner", "payload": remote_report}],
        started_at=started_at,
        recommended_next_action=[
            "Keep the validated model and benchmark paths configured.",
            "Open the reviewed remote execution gate.",
            "Approve GPU budget and process submission before rerunning the landmark smoke.",
        ],
    )


def _write_needs_attention(
    *,
    run_dir: Path,
    run_id: str,
    command: dict[str, Any],
    failure_type: str,
    failure_message: str,
    gate_failures: list[dict[str, Any]],
    started_at: str,
    recommended_next_action: list[str],
) -> dict[str, Any]:
    finished_at = utc_now()
    run_manifest = {
        "run_id": run_id,
        "run_type": "landmark_baseline",
        "model_id": command["model_id"],
        "benchmark_id": command["benchmark_id"],
        "idea_id": None,
        "limit": command["limit"],
        "instrumentation_mode": command["instrumentation_mode"],
        "started_at": started_at,
        "finished_at": finished_at,
        "status": "needs_attention",
        "git_commit": current_git_commit(Path.cwd()),
        "outputs": {
            "stdout": "stdout.log",
            "stderr": "stderr.log",
            "exit_code": "exit_code.txt",
        },
        "missing_outputs": {
            "raw_outputs": failure_message,
            "normalized_outputs": "No raw outputs exist to normalize.",
            "metrics": "No real smoke outputs exist to score.",
            "failure_cases": "No real benchmark outputs exist to inspect.",
        },
    }
    failure = {
        "phase": "Phase 5",
        "status": "needs_attention",
        "failure_type": failure_type,
        "failure_message": failure_message,
        "gate_failures": gate_failures,
        "stack_trace": None,
        "stdout_tail": _tail_file(run_dir / "stdout.log"),
        "stderr_tail": _tail_file(run_dir / "stderr.log"),
        "reproduction_command": command.get("reproduction_command") or _reproduction_command(command),
        "config_snapshot": command,
        "state_snapshot": run_manifest,
        "executed_real_model": False,
        "executed_real_benchmark": False,
        "recommended_next_action": recommended_next_action,
        "do_not_continue_reason": "Required validation and execution gates are not satisfied.",
    }
    write_json(run_dir / "run_manifest.json", run_manifest)
    write_json(run_dir / "failure.json", failure)
    write_text(
        run_dir / "failure_report.md",
        "# Landmark Gate Failure\n\n"
        "Status: `needs_attention`\n\n"
        f"- failure_type: `{failure_type}`\n"
        f"- failure_message: {failure_message}\n"
        f"- reproduction_command: `{failure['reproduction_command']}`\n"
        "- executed_real_model: `false`\n"
        "- executed_real_benchmark: `false`\n",
    )
    write_json(run_dir / "artifact_manifest.json", artifact_manifest_for(run_dir, run_id))
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "status": "needs_attention",
        "failure_type": failure_type,
        "executed_real_model": False,
        "executed_real_benchmark": False,
    }


def _reproduction_command(command: dict[str, Any]) -> str:
    return (
        "python -m stable_core.cli run-landmark "
        f"--model {command['model_id']} "
        f"--benchmark {command['benchmark_id']} "
        f"--limit {command['limit']} "
        f"--instrumentation {command['instrumentation_mode']} "
        f"--run-id {command['run_id']}"
    )


def _tail_file(path: Path) -> str:
    if not path.exists():
        return ""
    return tail_text(path.read_text(encoding="utf-8"))
