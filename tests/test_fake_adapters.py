from pathlib import Path

from adapters.benchmarks.fake import FakeBenchmarkAdapter
from adapters.benchmarks.pope import POPEAdapter
from adapters.models.fake import FakeModelAdapter
from adapters.models.qwen3_vl import Qwen3VLAdapter
from stable_core.schemas.common import GenerationOutput


def test_fake_model_generate() -> None:
    model = FakeModelAdapter()
    request = FakeBenchmarkAdapter().build_requests(split="validation", limit=1)[0]

    report = model.validate_environment()
    model.load()
    output = model.generate(request)

    assert report.status == "passed"
    assert output.request_id == request.request_id
    assert output.raw_text.lower().startswith(("yes", "no"))
    assert output.metadata["model_id"] == "fake_model"


def test_fake_benchmark_build_requests_and_metrics(tmp_path: Path) -> None:
    benchmark = FakeBenchmarkAdapter()

    requests = benchmark.build_requests(split="validation", limit=3)

    assert len(requests) == 3
    assert requests[0].benchmark_id == "fake_benchmark"
    assert requests[0].metadata["reference_answer"] in {"yes", "no"}

    normalized_path = tmp_path / "normalized_outputs.jsonl"
    rows = []
    for request in requests:
        raw = GenerationOutput(
            request_id=request.request_id,
            raw_text=request.metadata["reference_answer"],
            metadata={**request.metadata, "sample_id": request.sample_id},
        )
        rows.append(benchmark.normalize_prediction(raw))
    normalized_path.write_text("\n".join(__import__("json").dumps(row) for row in rows) + "\n", encoding="utf-8")

    metrics = benchmark.compute_metrics(normalized_path)

    assert metrics["sample_count"] == 3
    assert metrics["metrics"]["accuracy"] == 1.0
    assert benchmark.extract_failure_cases(normalized_path) == []


def test_real_adapter_skeletons_validate_without_loading() -> None:
    model_report = Qwen3VLAdapter().validate_environment()
    benchmark_report = POPEAdapter().validate_paths()

    assert model_report.status == "needs_setup"
    assert "download" in model_report.summary.lower() or "path" in model_report.summary.lower()
    assert benchmark_report.status == "needs_setup"


def test_validate_only_skeletons_use_configured_paths(tmp_path: Path) -> None:
    model_path = tmp_path / "model"
    benchmark_path = tmp_path / "benchmark"
    model_path.mkdir()
    benchmark_path.mkdir()

    model_report = Qwen3VLAdapter({"path": str(model_path), "download_allowed": False}).validate_environment()
    benchmark_report = POPEAdapter({"path": str(benchmark_path)}).validate_paths()

    assert model_report.status == "passed"
    assert model_report.checks[-1]["path"] == str(model_path)
    assert benchmark_report.status == "passed"
    assert benchmark_report.checks[-1]["path"] == str(benchmark_path)
