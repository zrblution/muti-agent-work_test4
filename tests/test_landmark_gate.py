import json
import subprocess
import sys
import uuid
from pathlib import Path

from experiments.landmark_baselines.runner import run_landmark


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stable_core.cli", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_run_landmark_records_needs_attention_without_real_execution(tmp_path: Path) -> None:
    result = run_landmark(
        run_id="qwen_pope_gate",
        model_id="qwen3_vl_2b_instruct",
        benchmark_id="pope",
        limit=8,
        instrumentation_mode="none",
        runs_root=tmp_path,
    )

    run_dir = tmp_path / "qwen_pope_gate"
    failure = json.loads((run_dir / "failure.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))

    assert result["status"] == "needs_attention"
    assert result["executed_real_model"] is False
    assert result["executed_real_benchmark"] is False
    assert failure["failure_type"] == "landmark_validation_gate_not_ready"
    assert failure["stdout_tail"] == ""
    assert "Landmark validation gates did not pass" in failure["stderr_tail"]
    assert "run-landmark --model qwen3_vl_2b_instruct --benchmark pope --limit 8" in failure["reproduction_command"]
    assert failure["state_snapshot"]["status"] == "needs_attention"
    assert manifest["status"] == "needs_attention"
    assert manifest["outputs"]["stdout"] == "stdout.log"
    assert manifest["outputs"]["stderr"] == "stderr.log"
    assert manifest["outputs"]["exit_code"] == "exit_code.txt"
    assert not (run_dir / "raw_outputs.jsonl").exists()
    assert (run_dir / "failure_report.md").exists()


def test_run_landmark_cli_is_validation_gate() -> None:
    run_id = f"qwen_pope_gate_{uuid.uuid4().hex}"

    result = run_cli(
        "run-landmark",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--run-id",
        run_id,
    )

    payload = json.loads(result.stdout)
    run_dir = REPO_ROOT / "runs" / run_id

    assert result.returncode == 1
    assert payload["status"] == "needs_attention"
    assert payload["run_id"] == run_id
    assert (run_dir / "failure.json").exists()
    assert not (run_dir / "raw_outputs.jsonl").exists()
