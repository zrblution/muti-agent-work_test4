import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from experiments.fake.evaluator import run_fake_eval


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stable_core.cli", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_fake_runner_writes_run_manifest_raw_and_metrics(tmp_path: Path) -> None:
    result = run_fake_eval(run_id="fake_unit", limit=3, runs_root=tmp_path)
    run_dir = tmp_path / "fake_unit"

    assert result["status"] == "succeeded"
    for name in [
        "run_manifest.json",
        "raw_outputs.jsonl",
        "normalized_outputs.jsonl",
        "metrics.json",
        "failure_cases.jsonl",
        "artifact_manifest.json",
        "experiment_summary.md",
    ]:
        assert (run_dir / name).exists(), name

    raw_rows = read_jsonl(run_dir / "raw_outputs.jsonl")
    normalized_rows = read_jsonl(run_dir / "normalized_outputs.jsonl")
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))

    assert len(raw_rows) == 3
    assert len(normalized_rows) == 3
    assert metrics["sample_count"] == 3
    assert metrics["metrics"]["accuracy"] >= 0.0


def test_fake_runner_does_not_overwrite_raw_outputs(tmp_path: Path) -> None:
    run_fake_eval(run_id="fake_once", limit=1, runs_root=tmp_path)

    with pytest.raises(FileExistsError, match="raw_outputs"):
        run_fake_eval(run_id="fake_once", limit=1, runs_root=tmp_path)


def test_fake_runner_rejects_bad_input_before_writing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="limit"):
        run_fake_eval(run_id="negative_limit", limit=-1, runs_root=tmp_path)
    with pytest.raises(ValueError, match="single safe path segment"):
        run_fake_eval(run_id="../bad", limit=1, runs_root=tmp_path)
    with pytest.raises(ValueError, match="only supports fake_model"):
        run_fake_eval(run_id="real_model", model_id="qwen3_vl_2b_instruct", benchmark_id="fake_benchmark", limit=1, runs_root=tmp_path)

    assert not (tmp_path / "negative_limit").exists()
    assert not (tmp_path / "real_model").exists()


def test_validate_model_benchmark_and_run_eval_clis() -> None:
    run_id = f"fake_cli_phase4_{uuid.uuid4().hex}"

    model_result = run_cli("validate-model", "fake_model")
    benchmark_result = run_cli("validate-benchmark", "fake_benchmark")
    eval_result = run_cli("run-eval", "--model", "fake_model", "--benchmark", "fake_benchmark", "--limit", "2", "--run-id", run_id)

    assert model_result.returncode == 0, model_result.stderr
    assert json.loads(model_result.stdout)["status"] == "passed"
    assert benchmark_result.returncode == 0, benchmark_result.stderr
    assert json.loads(benchmark_result.stdout)["status"] == "passed"
    assert eval_result.returncode == 0, eval_result.stderr
    payload = json.loads(eval_result.stdout)
    assert payload["status"] == "succeeded"
    assert (REPO_ROOT / "runs" / run_id / "raw_outputs.jsonl").exists()
