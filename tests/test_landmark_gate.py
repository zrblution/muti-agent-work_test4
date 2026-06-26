import json
import os
import subprocess
import sys
import types
import uuid
from pathlib import Path

import pytest

import experiments.landmark_baselines.run_landmark as worker_script
from experiments.landmark_baselines.runner import run_landmark
from stable_core.schemas.common import GenerationOutput, GenerationRequest, ValidationReport
from stable_core.storage.run_validator import validate_run_artifacts


REPO_ROOT = Path(__file__).resolve().parents[1]


def _install_fake_qwen_dependency_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTorch:
        bfloat16 = "bf16-dtype"
        float16 = "fp16-dtype"
        float32 = "fp32-dtype"

    class FakeProcessor:
        pass

    class FakeModel:
        pass

    monkeypatch.setitem(sys.modules, "torch", FakeTorch)
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        types.SimpleNamespace(AutoProcessor=FakeProcessor, AutoModelForMultimodalLM=FakeModel),
    )


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


def test_run_landmark_manifest_carries_artifact_contract_for_validation(tmp_path: Path) -> None:
    run_landmark(
        run_id="qwen_pope_contract_gate",
        model_id="qwen3_vl_2b_instruct",
        benchmark_id="pope",
        limit=8,
        instrumentation_mode="none",
        runs_root=tmp_path,
    )

    run_dir = tmp_path / "qwen_pope_contract_gate"
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    validation = validate_run_artifacts(run_id="qwen_pope_contract_gate", runs_root=tmp_path)

    assert manifest["artifact_contract"]["failure_outputs"] == [
        "run_manifest.json",
        "stdout.log",
        "stderr.log",
        "exit_code.txt",
        "env_snapshot.json",
        "failure.json",
        "failure_report.md",
        "artifact_manifest.json",
    ]
    assert any(
        check["name"] == "artifact_contract_failure_outputs" and check["status"] == "passed"
        for check in validation["checks"]
    )


def test_run_landmark_reports_remote_gate_after_validation_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_qwen_dependency_runtime(monkeypatch)
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
    _install_fake_qwen_dependency_runtime(monkeypatch)
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


def test_landmark_worker_writes_success_artifacts_with_runtime_adapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class WorkerSmokeModel:
        model_id = "qwen3_vl_2b_instruct"

        def __init__(self, config: dict | None = None) -> None:
            self.loaded = False

        def validate_environment(self) -> ValidationReport:
            return ValidationReport(status="passed", checks=[], summary="test model ready")

        def load(self) -> object:
            self.loaded = True
            return self

        def generate(self, request: GenerationRequest) -> GenerationOutput:
            if not self.loaded:
                raise RuntimeError("load required")
            return GenerationOutput(
                request_id=request.request_id,
                raw_text=str(request.metadata["reference_answer"]),
                metadata={
                    **request.metadata,
                    "model_id": self.model_id,
                    "benchmark_id": request.benchmark_id,
                    "sample_id": request.sample_id,
                },
            )

        def unload(self) -> None:
            self.loaded = False

    class WorkerSmokeBenchmark:
        benchmark_id = "pope"
        normalizer_version = "pope_test_v1"

        def __init__(self, config: dict | None = None) -> None:
            self.config = config or {}

        def validate_paths(self) -> ValidationReport:
            return ValidationReport(status="passed", checks=[], summary="test benchmark ready")

        def build_requests(self, split: str, limit: int | None) -> list[GenerationRequest]:
            samples = [
                ("pope_req_0001", "pope_0001", "yes"),
                ("pope_req_0002", "pope_0002", "no"),
            ]
            selected = samples if limit is None else samples[:limit]
            return [
                GenerationRequest(
                    request_id=request_id,
                    image_path=None,
                    prompt="Is the object present?",
                    benchmark_id=self.benchmark_id,
                    sample_id=sample_id,
                    metadata={"reference_answer": reference, "sample_id": sample_id},
                )
                for request_id, sample_id, reference in selected
            ]

        def normalize_prediction(self, raw_output: GenerationOutput) -> dict:
            prediction = raw_output.raw_text.strip().lower()
            reference = str(raw_output.metadata["reference_answer"]).lower()
            return {
                "request_id": raw_output.request_id,
                "sample_id": raw_output.metadata["sample_id"],
                "benchmark_id": self.benchmark_id,
                "raw_text_ref": raw_output.metadata.get("raw_text_ref"),
                "normalized_prediction": prediction,
                "reference_answer": reference,
                "is_correct": prediction == reference,
                "hallucination_label": prediction != reference,
                "answer_length": len(raw_output.raw_text.split()),
                "normalizer_version": self.normalizer_version,
                "metadata": {},
            }

        def compute_metrics(self, normalized_outputs_path: Path) -> dict:
            rows = [
                json.loads(line)
                for line in normalized_outputs_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            correct = sum(1 for row in rows if row["is_correct"])
            return {"sample_count": len(rows), "metrics": {"accuracy": correct / len(rows)}}

        def extract_failure_cases(self, normalized_outputs_path: Path) -> list[dict]:
            return [
                row
                for row in (
                    json.loads(line)
                    for line in normalized_outputs_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
                if not row["is_correct"]
            ]

    monkeypatch.setitem(worker_script.MODEL_ADAPTERS, "qwen3_vl_2b_instruct", WorkerSmokeModel)
    monkeypatch.setitem(worker_script.BENCHMARK_ADAPTERS, "pope", WorkerSmokeBenchmark)

    result = worker_script.run_worker(
        run_id="qwen_worker_success",
        model_id="qwen3_vl_2b_instruct",
        benchmark_id="pope",
        limit=2,
        instrumentation_mode="none",
        runs_root=tmp_path,
    )

    run_dir = tmp_path / "qwen_worker_success"
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    raw_rows = [json.loads(line) for line in (run_dir / "raw_outputs.jsonl").read_text(encoding="utf-8").splitlines()]
    normalized_rows = [
        json.loads(line) for line in (run_dir / "normalized_outputs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))

    assert result["status"] == "succeeded"
    assert result["sample_count"] == 2
    assert manifest["status"] == "succeeded"
    assert manifest["outputs"]["raw_outputs"] == "raw_outputs.jsonl"
    assert [row["sample_id"] for row in raw_rows] == ["pope_0001", "pope_0002"]
    assert [row["raw_text_ref"] for row in normalized_rows] == ["raw_outputs.jsonl:line_1", "raw_outputs.jsonl:line_2"]
    assert metrics["sample_count"] == 2
    assert metrics["metrics"]["accuracy"] == 1.0
    assert (run_dir / "failure_cases.jsonl").read_text(encoding="utf-8") == ""
    assert (run_dir / "artifact_manifest.json").exists()
    assert not (run_dir / "failure.json").exists()

    with pytest.raises(FileExistsError, match="raw_outputs"):
        worker_script.run_worker(
            run_id="qwen_worker_success",
            model_id="qwen3_vl_2b_instruct",
            benchmark_id="pope",
            limit=2,
            instrumentation_mode="none",
            runs_root=tmp_path,
        )


def test_landmark_worker_script_records_execution_failure_without_reentering_gate(tmp_path: Path) -> None:
    run_id = "qwen_worker_gate"
    model_root = tmp_path / "models"
    benchmark_root = tmp_path / "benchmarks"
    model_path = model_root / "Qwen3-VL-2B-Instruct"
    benchmark_path = benchmark_root / "POPE"
    model_path.mkdir(parents=True)
    benchmark_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (benchmark_path / "samples.jsonl").write_text("{}\n", encoding="utf-8")
    env = {
        **os.environ,
        "REMOTE_MODEL_ROOT": str(model_root),
        "REMOTE_BENCHMARK_ROOT": str(benchmark_root),
    }

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
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    run_dir = tmp_path / run_id
    failure = json.loads((run_dir / "failure.json").read_text(encoding="utf-8"))

    assert result.returncode == 1
    assert payload["status"] == "needs_attention"
    assert payload["failure_type"] == "landmark_worker_validation_gate_not_ready"
    assert failure["failure_type"] == "landmark_worker_validation_gate_not_ready"
    assert {item["gate"] for item in failure["gate_failures"]} == {"validate-model"}
    assert failure["executed_real_model"] is False
    assert failure["executed_real_benchmark"] is False
    assert failure["stderr_tail"]
    assert "experiments/landmark_baselines/run_landmark.py" in failure["reproduction_command"]
    assert "stable_core.cli run-landmark" not in failure["reproduction_command"]
    assert not (run_dir / "raw_outputs.jsonl").exists()


def test_landmark_worker_script_validates_model_and_benchmark_before_stub(tmp_path: Path) -> None:
    run_id = "qwen_worker_validation_gate"
    env = os.environ.copy()
    env.pop("REMOTE_MODEL_ROOT", None)
    env.pop("REMOTE_BENCHMARK_ROOT", None)

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
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    failure = json.loads((tmp_path / run_id / "failure.json").read_text(encoding="utf-8"))

    assert result.returncode == 1
    assert payload["status"] == "needs_attention"
    assert payload["failure_type"] == "landmark_worker_validation_gate_not_ready"
    assert failure["failure_type"] == "landmark_worker_validation_gate_not_ready"
    assert {item["gate"] for item in failure["gate_failures"]} == {"validate-model", "validate-benchmark"}
    assert failure["executed_real_model"] is False
    assert failure["executed_real_benchmark"] is False
    assert not (tmp_path / run_id / "raw_outputs.jsonl").exists()
