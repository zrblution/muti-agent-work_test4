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
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (benchmark_path / "samples.jsonl").write_text("{}", encoding="utf-8")

    model_report = Qwen3VLAdapter({"path": str(model_path), "download_allowed": False}).validate_environment()
    benchmark_report = POPEAdapter({"path": str(benchmark_path)}).validate_paths()

    assert model_report.status == "passed"
    assert model_report.checks[-1]["path"] == str(model_path)
    assert benchmark_report.status == "passed"
    assert benchmark_report.checks[-1]["path"] == str(benchmark_path)


def test_validate_only_skeletons_reject_empty_inventory_dirs(tmp_path: Path) -> None:
    model_path = tmp_path / "empty_model"
    benchmark_path = tmp_path / "empty_benchmark"
    model_path.mkdir()
    benchmark_path.mkdir()

    model_report = Qwen3VLAdapter({"path": str(model_path), "download_allowed": False}).validate_environment()
    benchmark_report = POPEAdapter({"path": str(benchmark_path)}).validate_paths()

    assert model_report.status == "needs_setup"
    assert model_report.checks[-1]["name"] == "model_inventory"
    assert "config.json" in model_report.checks[-1]["missing_files"]
    assert benchmark_report.status == "needs_setup"
    assert benchmark_report.checks[-1]["name"] == "benchmark_inventory"


def test_benchmark_inventory_honors_configured_required_files(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "pope"
    benchmark_path.mkdir()
    (benchmark_path / "samples.jsonl").write_text("{}\n", encoding="utf-8")

    report = POPEAdapter({"path": str(benchmark_path), "required_files": ["annotations/random.json"]}).validate_paths()

    assert report.status == "needs_setup"
    assert report.checks[-1]["name"] == "benchmark_inventory"
    assert report.checks[-1]["missing_files"] == ["annotations/random.json"]


def test_benchmark_inventory_accepts_configured_required_files(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "pope"
    annotation_path = benchmark_path / "annotations" / "random.json"
    annotation_path.parent.mkdir(parents=True)
    annotation_path.write_text("[]\n", encoding="utf-8")

    report = POPEAdapter({"path": str(benchmark_path), "required_files": ["annotations/random.json"]}).validate_paths()

    assert report.status == "passed"
    assert report.checks[-1]["name"] == "benchmark_inventory"
    assert report.checks[-1]["required_files"] == ["annotations/random.json"]


def test_validate_only_skeletons_resolve_env_templates(monkeypatch, tmp_path: Path) -> None:
    model_root = tmp_path / "model_root"
    benchmark_root = tmp_path / "benchmark_root"
    model_path = model_root / "Qwen3-VL-2B-Instruct"
    benchmark_path = benchmark_root / "POPE"
    model_path.mkdir(parents=True)
    benchmark_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (benchmark_path / "pope_samples.json").write_text("[]", encoding="utf-8")
    monkeypatch.setenv("REMOTE_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("REMOTE_BENCHMARK_ROOT", str(benchmark_root))

    model_report = Qwen3VLAdapter({"local_path": "${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct"}).validate_environment()
    benchmark_report = POPEAdapter({"path": "${REMOTE_BENCHMARK_ROOT}/POPE"}).validate_paths()

    assert model_report.status == "passed"
    assert model_report.checks[-1]["path"] == str(model_path)
    assert benchmark_report.status == "passed"
    assert benchmark_report.checks[-1]["path"] == str(benchmark_path)


def test_validate_only_skeletons_report_missing_env_templates() -> None:
    model_report = Qwen3VLAdapter({"local_path": "${MISSING_MODEL_ROOT}/Qwen3-VL-2B-Instruct"}).validate_environment()
    benchmark_report = POPEAdapter({"path": "${MISSING_BENCHMARK_ROOT}/POPE"}).validate_paths()

    assert model_report.status == "needs_setup"
    assert model_report.checks[-1]["env_var"] == "MISSING_MODEL_ROOT"
    assert benchmark_report.status == "needs_setup"
    assert benchmark_report.checks[-1]["env_var"] == "MISSING_BENCHMARK_ROOT"
