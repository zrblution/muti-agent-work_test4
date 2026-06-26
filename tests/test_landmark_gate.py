import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

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


def test_run_landmark_reports_remote_gate_after_validation_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model_root = tmp_path / "models"
    benchmark_root = tmp_path / "benchmarks"
    model_path = model_root / "Qwen3-VL-2B-Instruct"
    benchmark_path = benchmark_root / "POPE"
    model_path.mkdir(parents=True)
    benchmark_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (benchmark_path / "samples.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("REMOTE_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("REMOTE_BENCHMARK_ROOT", str(benchmark_root))

    result = run_landmark(
        run_id="qwen_pope_remote_gate",
        model_id="qwen3_vl_2b_instruct",
        benchmark_id="pope",
        limit=8,
        instrumentation_mode="none",
        runs_root=tmp_path,
    )

    run_dir = tmp_path / "qwen_pope_remote_gate"
    failure = json.loads((run_dir / "failure.json").read_text(encoding="utf-8"))
    remote_payload = failure["gate_failures"][0]["payload"]

    assert result["status"] == "needs_attention"
    assert failure["failure_type"] == "landmark_remote_runner_not_enabled"
    assert remote_payload["runner_mode"] == "local_only"
    assert remote_payload["allow_real_gpu_jobs"] is False
    assert "Configure approved model and benchmark paths." not in failure["recommended_next_action"]
    assert "Open the reviewed remote execution gate." in failure["recommended_next_action"]
    assert not (run_dir / "raw_outputs.jsonl").exists()


def test_run_landmark_remote_plan_preserves_requested_run_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model_root = tmp_path / "models"
    benchmark_root = tmp_path / "benchmarks"
    model_path = model_root / "Qwen3-VL-2B-Instruct"
    benchmark_path = benchmark_root / "POPE"
    model_path.mkdir(parents=True)
    benchmark_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (benchmark_path / "samples.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("REMOTE_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("REMOTE_BENCHMARK_ROOT", str(benchmark_root))

    run_landmark(
        run_id="qwen_pope_requested_run_id",
        model_id="qwen3_vl_2b_instruct",
        benchmark_id="pope",
        limit=8,
        instrumentation_mode="none",
        runs_root=tmp_path,
    )

    failure = json.loads((tmp_path / "qwen_pope_requested_run_id" / "failure.json").read_text(encoding="utf-8"))
    plan = failure["gate_failures"][0]["payload"]["execution_plan"]

    assert plan["experiment_id"] == "qwen_pope_requested_run_id"
    assert plan["argv"][-1] == "qwen_pope_requested_run_id"


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


def test_landmark_worker_script_records_needs_attention_without_reentering_gate(tmp_path: Path) -> None:
    run_id = "qwen_worker_gate"

    result = subprocess.run(
        [
            sys.executable,
            "experiments/landmark_baselines/run_landmark.py",
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
            "--runs-root",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    run_dir = tmp_path / run_id
    failure = json.loads((run_dir / "failure.json").read_text(encoding="utf-8"))

    assert result.returncode == 1
    assert payload["status"] == "needs_attention"
    assert payload["failure_type"] == "landmark_worker_not_implemented"
    assert failure["executed_real_model"] is False
    assert failure["executed_real_benchmark"] is False
    assert "experiments/landmark_baselines/run_landmark.py" in failure["reproduction_command"]
    assert "stable_core.cli run-landmark" not in failure["reproduction_command"]
    assert not (run_dir / "raw_outputs.jsonl").exists()
