import json
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.fake.evaluator import run_fake_eval
from experiments.landmark_baselines.runner import run_landmark
from stable_core.runner.local import LocalRunner
from stable_core.runner.remote import RemoteAction, RemoteRunner, validate_remote_action
from stable_core.storage.run_validator import validate_run_artifacts


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


def test_remote_runner_reports_configured_execution_gates() -> None:
    result = RemoteRunner().submit(
        {
            "action": "run_model_smoke_test",
            "allowed_script": "experiments/landmark_baselines/run_landmark.py",
            "model_id": "qwen3_vl_2b_instruct",
            "benchmark_id": "pope",
            "limit": 8,
            "instrumentation_mode": "none",
        }
    )

    assert result["status"] == "needs_attention"
    assert result["runner_mode"] == "local_only"
    assert result["allow_real_gpu_jobs"] is False
    assert result["allow_process_submission"] is False
    assert {failure["name"] for failure in result["gate_failures"]} == {
        "runner_mode",
        "real_gpu_budget",
        "process_submission",
    }


def test_remote_runner_rejects_unsafe_experiment_id_before_planning() -> None:
    result = RemoteRunner().submit(
        {
            "experiment_id": "../escape",
            "action": "run_model_smoke_test",
            "allowed_script": "experiments/landmark_baselines/run_landmark.py",
            "model_id": "qwen3_vl_2b_instruct",
            "benchmark_id": "pope",
            "limit": 8,
            "instrumentation_mode": "none",
        }
    )

    assert result["status"] == "failed"
    assert result["validation"]["status"] == "failed"
    assert "experiment_id" in result["validation"]["checks"][0]["error"]
    assert "execution_plan" not in result


def test_remote_runner_builds_reviewable_plan_when_process_submission_gate_closed(tmp_path: Path) -> None:
    server_config = tmp_path / "server.yaml"
    budget_config = tmp_path / "experiment_budget.yaml"
    server_config.write_text("server:\n  runner_mode: remote_enabled\n", encoding="utf-8")
    budget_config.write_text("budget:\n  allow_real_gpu_jobs: true\n", encoding="utf-8")

    result = RemoteRunner(server_config=server_config, budget_config=budget_config).submit(
        {
            "experiment_id": "qwen3vl_pope_limit8_real_smoke",
            "action": "run_model_smoke_test",
            "allowed_script": "experiments/landmark_baselines/run_landmark.py",
            "model_id": "qwen3_vl_2b_instruct",
            "benchmark_id": "pope",
            "limit": 8,
            "instrumentation_mode": "none",
        }
    )

    assert result["status"] == "needs_attention"
    assert result["allow_process_submission"] is False
    assert result["gate_failures"][0]["name"] == "process_submission"
    assert "job_id" not in result
    assert result["execution_plan"] == {
        "experiment_id": "qwen3vl_pope_limit8_real_smoke",
        "action": "run_model_smoke_test",
        "allowed_script": "experiments/landmark_baselines/run_landmark.py",
        "argv": [
            "python",
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
            "qwen3vl_pope_limit8_real_smoke",
        ],
        "cwd": ".",
        "submits_process": False,
        "artifact_contract": {
            "success_outputs": [
                "run_manifest.json",
                "raw_outputs.jsonl",
                "normalized_outputs.jsonl",
                "metrics.json",
                "failure_cases.jsonl",
                "artifact_manifest.json",
                "experiment_summary.md",
                "reproducibility_notes.md",
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
        },
    }


def test_remote_runner_reaches_executor_gate_after_process_submission_gate_opens(tmp_path: Path) -> None:
    server_config = tmp_path / "server.yaml"
    budget_config = tmp_path / "experiment_budget.yaml"
    server_config.write_text("server:\n  runner_mode: remote_enabled\n", encoding="utf-8")
    budget_config.write_text(
        "budget:\n  allow_real_gpu_jobs: true\n  allow_process_submission: true\n",
        encoding="utf-8",
    )

    result = RemoteRunner(server_config=server_config, budget_config=budget_config).submit(
        {
            "experiment_id": "qwen3vl_pope_limit8_real_smoke",
            "action": "run_model_smoke_test",
            "allowed_script": "experiments/landmark_baselines/run_landmark.py",
            "model_id": "qwen3_vl_2b_instruct",
            "benchmark_id": "pope",
            "limit": 8,
            "instrumentation_mode": "none",
        },
        plan_only=True,
    )

    assert result["status"] == "needs_attention"
    assert result["allow_process_submission"] is True
    assert result["gate_failures"][0]["name"] == "plan_only"
    assert result["execution_plan"]["submits_process"] is False
    assert "job_id" not in result


def test_remote_runner_submits_whitelisted_worker_after_all_gates_open(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    server_config = tmp_path / "server.yaml"
    budget_config = tmp_path / "experiment_budget.yaml"
    runs_root = tmp_path / "runs"
    model_root = tmp_path / "models"
    benchmark_root = tmp_path / "benchmarks"
    model_path = model_root / "Qwen3-VL-2B-Instruct"
    benchmark_path = benchmark_root / "POPE"
    model_path.mkdir(parents=True)
    benchmark_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}\n", encoding="utf-8")
    (benchmark_path / "samples.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("REMOTE_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("REMOTE_BENCHMARK_ROOT", str(benchmark_root))
    server_config.write_text("server:\n  runner_mode: remote_enabled\n", encoding="utf-8")
    budget_config.write_text(
        "budget:\n  allow_real_gpu_jobs: true\n  allow_process_submission: true\n",
        encoding="utf-8",
    )

    result = RemoteRunner(server_config=server_config, budget_config=budget_config).submit(
        {
            "experiment_id": "qwen3vl_pope_limit8_real_smoke",
            "action": "run_model_smoke_test",
            "allowed_script": "experiments/landmark_baselines/run_landmark.py",
            "model_id": "qwen3_vl_2b_instruct",
            "benchmark_id": "pope",
            "limit": 8,
            "instrumentation_mode": "none",
            "runs_root": str(runs_root),
        }
    )

    run_dir = runs_root / "qwen3vl_pope_limit8_real_smoke"
    failure = json.loads((run_dir / "failure.json").read_text(encoding="utf-8"))

    assert result["status"] == "needs_attention"
    assert result["submitted_process"] is True
    assert result["exit_code"] == 1
    assert result["worker_payload"]["failure_type"] == "landmark_worker_execution_failed"
    assert result["execution_plan"]["submits_process"] is True
    assert failure["failure_type"] == "landmark_worker_execution_failed"
    assert {item["gate"] for item in failure["gate_failures"]} == {"worker-execution"}
    assert failure["executed_real_model"] is False
    assert failure["executed_real_benchmark"] is False
    assert not (run_dir / "raw_outputs.jsonl").exists()


def test_remote_runner_plan_only_does_not_submit_when_all_gates_open(tmp_path: Path) -> None:
    server_config = tmp_path / "server.yaml"
    budget_config = tmp_path / "experiment_budget.yaml"
    runs_root = tmp_path / "runs"
    server_config.write_text("server:\n  runner_mode: remote_enabled\n", encoding="utf-8")
    budget_config.write_text(
        "budget:\n  allow_real_gpu_jobs: true\n  allow_process_submission: true\n",
        encoding="utf-8",
    )

    result = RemoteRunner(server_config=server_config, budget_config=budget_config).submit(
        {
            "experiment_id": "qwen3vl_pope_limit8_real_smoke",
            "action": "run_model_smoke_test",
            "allowed_script": "experiments/landmark_baselines/run_landmark.py",
            "model_id": "qwen3_vl_2b_instruct",
            "benchmark_id": "pope",
            "limit": 8,
            "instrumentation_mode": "none",
            "runs_root": str(runs_root),
        },
        plan_only=True,
    )

    assert result["status"] == "needs_attention"
    assert result["gate_failures"][0]["name"] == "plan_only"
    assert result["execution_plan"]["submits_process"] is False
    assert result["submitted_process"] is False
    assert not runs_root.exists()


def test_remote_runner_does_not_submit_non_process_action_when_remote_gate_open(tmp_path: Path) -> None:
    server_config = tmp_path / "server.yaml"
    budget_config = tmp_path / "experiment_budget.yaml"
    server_config.write_text("server:\n  runner_mode: remote_enabled\n", encoding="utf-8")
    budget_config.write_text("budget:\n  allow_real_gpu_jobs: true\n  allow_process_submission: true\n", encoding="utf-8")

    result = RemoteRunner(server_config=server_config, budget_config=budget_config).submit(
        {"action": "poll_job", "experiment_id": "qwen3vl_pope_poll"}
    )

    assert result["status"] == "needs_attention"
    assert result["submitted_process"] is False
    assert result["gate_failures"][0]["name"] == "non_process_action"
    assert "job_id" not in result


def test_remote_runner_landmark_plan_declares_artifact_contract(tmp_path: Path) -> None:
    server_config = tmp_path / "server.yaml"
    budget_config = tmp_path / "experiment_budget.yaml"
    server_config.write_text("server:\n  runner_mode: remote_enabled\n", encoding="utf-8")
    budget_config.write_text("budget:\n  allow_real_gpu_jobs: true\n", encoding="utf-8")

    result = RemoteRunner(server_config=server_config, budget_config=budget_config).submit(
        {
            "experiment_id": "qwen3vl_pope_limit8_real_smoke",
            "action": "run_model_smoke_test",
            "allowed_script": "experiments/landmark_baselines/run_landmark.py",
            "model_id": "qwen3_vl_2b_instruct",
            "benchmark_id": "pope",
            "limit": 8,
            "instrumentation_mode": "none",
        }
    )

    assert result["execution_plan"]["artifact_contract"] == {
        "success_outputs": [
            "run_manifest.json",
            "raw_outputs.jsonl",
            "normalized_outputs.jsonl",
            "metrics.json",
            "failure_cases.jsonl",
            "artifact_manifest.json",
            "experiment_summary.md",
            "reproducibility_notes.md",
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


def test_remote_runner_execution_plan_targets_existing_non_recursive_worker(tmp_path: Path) -> None:
    server_config = tmp_path / "server.yaml"
    budget_config = tmp_path / "experiment_budget.yaml"
    server_config.write_text("server:\n  runner_mode: remote_enabled\n", encoding="utf-8")
    budget_config.write_text("budget:\n  allow_real_gpu_jobs: true\n", encoding="utf-8")

    result = RemoteRunner(server_config=server_config, budget_config=budget_config).submit(
        {
            "experiment_id": "qwen3vl_pope_limit8_real_smoke",
            "action": "run_model_smoke_test",
            "allowed_script": "experiments/landmark_baselines/run_landmark.py",
            "model_id": "qwen3_vl_2b_instruct",
            "benchmark_id": "pope",
            "limit": 8,
            "instrumentation_mode": "none",
        }
    )

    plan = result["execution_plan"]
    assert (REPO_ROOT / plan["allowed_script"]).is_file()
    assert plan["argv"][0:2] == ["python", plan["allowed_script"]]
    assert "stable_core.cli" not in plan["argv"]


def test_run_local_cli_executes_dummy_job() -> None:
    run_id = "dummy_phase3_cli"

    result = run_cli("run-local", "--run-id", run_id, "--action", "dummy_job", "--message", "cli ok")
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "succeeded"


def test_validate_run_accepts_succeeded_fake_eval(tmp_path: Path) -> None:
    run_fake_eval(run_id="fake_success", runs_root=tmp_path, limit=2)

    report = validate_run_artifacts(run_id="fake_success", runs_root=tmp_path)

    assert report["status"] == "passed"
    assert report["checks"][-1]["name"] == "artifact_hashes"
    assert report["checks"][-1]["status"] == "passed"


def test_validate_run_accepts_needs_attention_landmark_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("REMOTE_MODEL_ROOT", raising=False)
    monkeypatch.delenv("REMOTE_BENCHMARK_ROOT", raising=False)
    run_landmark(
        run_id="qwen_gate",
        model_id="qwen3_vl_2b_instruct",
        benchmark_id="pope",
        limit=8,
        runs_root=tmp_path,
    )

    report = validate_run_artifacts(run_id="qwen_gate", runs_root=tmp_path)

    assert report["status"] == "passed"
    assert any(check["name"] == "failure_artifacts" and check["status"] == "passed" for check in report["checks"])


def test_validate_run_rejects_missing_declared_output(tmp_path: Path) -> None:
    run_fake_eval(run_id="fake_missing_output", runs_root=tmp_path, limit=2)
    (tmp_path / "fake_missing_output" / "metrics.json").unlink()

    report = validate_run_artifacts(run_id="fake_missing_output", runs_root=tmp_path)

    assert report["status"] == "failed"
    assert any(check["name"] == "declared_outputs" and check["status"] == "failed" for check in report["checks"])


def test_validate_run_cli_reports_artifact_status(tmp_path: Path) -> None:
    run_fake_eval(run_id="fake_cli_validate", runs_root=tmp_path, limit=1)

    result = run_cli("validate-run", "--run-id", "fake_cli_validate", "--runs-root", str(tmp_path))
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "passed"


def test_poll_cli_reports_recorded_run_manifest(tmp_path: Path) -> None:
    run_fake_eval(run_id="fake_cli_poll", runs_root=tmp_path, limit=1)

    result = run_cli("poll", "--run-id", "fake_cli_poll", "--runs-root", str(tmp_path))
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "recorded"
    assert payload["run_status"] == "succeeded"
    assert payload["run_manifest"].endswith("fake_cli_poll/run_manifest.json")


def test_parse_results_cli_reads_existing_metrics_without_execution(tmp_path: Path) -> None:
    run_fake_eval(run_id="fake_cli_parse", runs_root=tmp_path, limit=2)
    metrics_path = tmp_path / "fake_cli_parse" / "metrics.json"
    original_metrics = metrics_path.read_text(encoding="utf-8")

    result = run_cli("parse-results", "--run-id", "fake_cli_parse", "--runs-root", str(tmp_path))
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "passed"
    assert payload["run_status"] == "succeeded"
    assert payload["metrics"]["sample_count"] == 2
    assert payload["metrics"]["metrics"]["accuracy"] == 1.0
    assert metrics_path.read_text(encoding="utf-8") == original_metrics


def test_parse_results_cli_preserves_needs_attention_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("REMOTE_MODEL_ROOT", raising=False)
    monkeypatch.delenv("REMOTE_BENCHMARK_ROOT", raising=False)
    run_landmark(
        run_id="qwen_cli_parse_gate",
        model_id="qwen3_vl_2b_instruct",
        benchmark_id="pope",
        limit=8,
        runs_root=tmp_path,
    )

    result = run_cli("parse-results", "--run-id", "qwen_cli_parse_gate", "--runs-root", str(tmp_path))
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "needs_attention"
    assert payload["run_status"] == "needs_attention"
    assert payload["artifact_validation_status"] == "passed"
    assert "metrics" not in payload
    assert payload["missing_outputs"]["metrics"] == "No real smoke outputs exist to score."
