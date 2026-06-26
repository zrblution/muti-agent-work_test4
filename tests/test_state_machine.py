import json
import subprocess
import sys
import uuid
from pathlib import Path

from stable_core.state_machine.state_manager import StateManager


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stable_core.cli", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_create_update_heartbeat_and_mark_failed(tmp_path: Path) -> None:
    manager = StateManager(tmp_path)

    state = manager.init_workflow("wf_test", current_state="preflight_validation")

    assert state.workflow_id == "wf_test"
    assert state.status == "pending"
    assert (tmp_path / "wf_test" / "state.json").exists()

    running = manager.update_status("wf_test", status="running", current_state="codex_mvp_build")
    assert running.current_state == "codex_mvp_build"

    heartbeat = manager.heartbeat("wf_test")
    assert heartbeat.last_heartbeat is not None

    failed = manager.mark_failed("wf_test", reason="unit test failure")
    assert failed.status == "failed"
    assert failed.failure["failure_message"] == "unit test failure"


def test_checkpoint_retry_and_heartbeat_timeout(tmp_path: Path) -> None:
    manager = StateManager(tmp_path)
    manager.init_workflow("wf_timeout")
    manager.update_status("wf_timeout", status="running", remote_job={"job_id": "job_1", "status": "running"})

    checkpoint = manager.checkpoint("wf_timeout", outputs=[{"kind": "metrics", "path": "runs/x/metrics.json"}])
    assert checkpoint.outputs[0]["kind"] == "metrics"

    timed_out = manager.check_heartbeat_timeout("wf_timeout", timeout_seconds=0)
    assert timed_out.status == "needs_attention"
    assert timed_out.failure["failure_type"] == "heartbeat_timeout"

    retried = manager.retry("wf_timeout", reason="operator approved retry")
    assert retried.attempt == 2
    assert retried.status == "pending"
    assert retried.failure is None


def test_resume_preserves_existing_state(tmp_path: Path) -> None:
    manager = StateManager(tmp_path)
    manager.init_workflow("wf_resume")
    manager.update_status("wf_resume", status="running", current_state="fake_end_to_end_test")

    resumed = manager.resume("wf_resume")

    assert resumed.workflow_id == "wf_resume"
    assert resumed.current_state == "fake_end_to_end_test"
    assert "poll_job" in resumed.next_allowed_actions


def test_workflow_cli_commands_create_and_read_state() -> None:
    workflow_id = f"phase3_cli_test_{uuid.uuid4().hex}"

    init_result = run_cli("workflow", "init", "--workflow-id", workflow_id)
    assert init_result.returncode == 0, init_result.stderr
    assert json.loads(init_result.stdout)["workflow_id"] == workflow_id

    status_result = run_cli("workflow", "status", "--workflow-id", workflow_id)
    assert status_result.returncode == 0, status_result.stderr
    assert json.loads(status_result.stdout)["workflow_id"] == workflow_id

    resume_result = run_cli("workflow", "resume", "--workflow-id", workflow_id)
    assert resume_result.returncode == 0, resume_result.stderr
    assert json.loads(resume_result.stdout)["status"] in {"pending", "running"}

    failed_result = run_cli("workflow", "mark-failed", "--workflow-id", workflow_id, "--reason", "cli failure")
    assert failed_result.returncode == 0, failed_result.stderr
    assert json.loads(failed_result.stdout)["failure"]["failure_message"] == "cli failure"
