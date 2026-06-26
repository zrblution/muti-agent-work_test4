import json
import subprocess
import sys
from pathlib import Path

import pytest

from stable_core.runner.local import LocalRunner
from stable_core.runner.remote import RemoteAction, validate_remote_action


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stable_core.cli", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_local_runner_writes_success_artifacts(tmp_path: Path) -> None:
    runner = LocalRunner(runs_root=tmp_path)

    result = runner.run_dummy(run_id="dummy_success", message="hello", fail=False)

    run_dir = tmp_path / "dummy_success"
    assert result["status"] == "succeeded"
    assert (run_dir / "stdout.log").read_text(encoding="utf-8").strip() == "hello"
    assert (run_dir / "stderr.log").exists()
    assert json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))["status"] == "succeeded"
    assert (run_dir / "env_snapshot.json").exists()
    assert (run_dir / "git_commit.txt").exists()


def test_local_runner_preserves_failure_artifacts(tmp_path: Path) -> None:
    runner = LocalRunner(runs_root=tmp_path)

    result = runner.run_dummy(run_id="dummy_failed", message="bad", fail=True)

    run_dir = tmp_path / "dummy_failed"
    assert result["status"] == "failed"
    assert (run_dir / "failure_report.md").exists()
    failure = json.loads((run_dir / "failure.json").read_text(encoding="utf-8"))
    assert failure["failure_type"] == "local_runner_exit_nonzero"
    assert "bad" in failure["stdout_tail"]


def test_remote_action_whitelist_blocks_arbitrary_shell() -> None:
    action = RemoteAction(action="rm -rf /", allowed_script="danger.sh")

    with pytest.raises(ValueError, match="not whitelisted"):
        validate_remote_action(action)


def test_run_local_cli_executes_dummy_job() -> None:
    run_id = "dummy_phase3_cli"

    result = run_cli("run-local", "--run-id", run_id, "--action", "dummy_job", "--message", "cli ok")

