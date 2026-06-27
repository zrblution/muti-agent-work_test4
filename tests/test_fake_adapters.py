import json
from pathlib import Path

import pytest

from adapters.benchmarks.fake import FakeBenchmarkAdapter
from adapters.benchmarks.pope import POPEAdapter
from adapters.models.fake import FakeModelAdapter
from adapters.models.internvl import InternVLAdapter
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

    model_report = InternVLAdapter({"path": str(model_path), "download_allowed": False}).validate_environment()
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


def test_pope_adapter_builds_canonical_requests_from_jsonl(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "pope"
    benchmark_path.mkdir()
    (benchmark_path / "samples.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "sample_id": "pope_random_0001",
                        "subset": "random",
                        "image_path": "images/0001.jpg",
                        "question": "Is there a cat in the image?",
                        "reference_answer": "yes",
                    }
                ),
                json.dumps(
                    {
                        "question_id": "pope_popular_0002",
                        "category": "popular",
                        "image": "images/0002.jpg",
                        "text": "Is there a bus in the image?",
                        "label": "no",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    requests = POPEAdapter({"path": str(benchmark_path), "required_files": ["samples.jsonl"]}).build_requests(
        split="validation",
        limit=2,
    )

    assert [request.sample_id for request in requests] == ["pope_random_0001", "pope_popular_0002"]
    assert requests[0].request_id == "pope_req_0001"
    assert requests[0].benchmark_id == "pope"
    assert requests[0].prompt == "Is there a cat in the image?"
    assert requests[0].metadata["reference_answer"] == "yes"
    assert requests[0].metadata["task_type"] == "yes_no_vqa"
    assert requests[1].metadata["subset"] == "popular"
    assert requests[1].image_path == str(benchmark_path / "images/0002.jpg")


def test_pope_adapter_builds_requests_from_json_suffix_line_delimited_objects(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "pope"
    benchmark_path.mkdir()
    (benchmark_path / "samples.json").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "question_id": "pope_random_0001",
                        "image_id": "images/0001.jpg",
                        "question": "Is there a dog in the image?",
                        "answer": "yes",
                    }
                ),
                json.dumps(
                    {
                        "question_id": "pope_random_0002",
                        "image_id": "images/0002.jpg",
                        "question": "Is there a train in the image?",
                        "answer": "no",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    requests = POPEAdapter({"path": str(benchmark_path), "required_files": ["samples.json"]}).build_requests(
        split="validation",
        limit=2,
    )

    assert [request.sample_id for request in requests] == ["pope_random_0001", "pope_random_0002"]
    assert requests[0].metadata["reference_answer"] == "yes"
    assert requests[1].metadata["reference_answer"] == "no"


def test_pope_adapter_prefers_coco_pope_samples_and_resolves_official_images(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "pope"
    caption_path = benchmark_path / "caption_data"
    output_path = benchmark_path / "output" / "coco"
    image_path = benchmark_path / "images" / "coco_official_val2014"
    caption_path.mkdir(parents=True)
    output_path.mkdir(parents=True)
    image_path.mkdir(parents=True)
    (caption_path / "Instruction1_instructblip.json").write_text(
        json.dumps({"question_id": 0, "image_id": 40468, "prompt": "caption", "text": "caption text"}) + "\n",
        encoding="utf-8",
    )
    (output_path / "coco_pope_random.json").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "question_id": 1,
                        "image": "COCO_val2014_000000310196.jpg",
                        "text": "Is there a snowboard in the image?",
                        "label": "yes",
                    }
                ),
                json.dumps(
                    {
                        "question_id": 2,
                        "image": "COCO_val2014_000000405762.jpg",
                        "text": "Is there a dog in the image?",
                        "label": "no",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (image_path / "COCO_val2014_000000310196.jpg").write_bytes(b"image")
    (image_path / "COCO_val2014_000000405762.jpg").write_bytes(b"image")

    requests = POPEAdapter({"path": str(benchmark_path)}).build_requests(split="validation", limit=2)

    assert [request.sample_id for request in requests] == ["1", "2"]
    assert requests[0].prompt == "Is there a snowboard in the image?"
    assert requests[0].metadata["reference_answer"] == "yes"
    assert requests[0].metadata["source_file"] == "output/coco/coco_pope_random.json"
    assert requests[0].image_path == str(image_path / "COCO_val2014_000000310196.jpg")
    assert requests[1].image_path == str(image_path / "COCO_val2014_000000405762.jpg")


def test_pope_adapter_normalizes_metrics_and_failure_cases(tmp_path: Path) -> None:
    adapter = POPEAdapter()
    rows = [
        adapter.normalize_prediction(
            GenerationOutput(
                request_id="pope_req_0001",
                raw_text="Yes, there is.",
                metadata={"sample_id": "pope_0001", "reference_answer": "yes"},
            )
        ),
        adapter.normalize_prediction(
            GenerationOutput(
                request_id="pope_req_0002",
                raw_text="yes",
                metadata={"sample_id": "pope_0002", "reference_answer": "no"},
            )
        ),
        adapter.normalize_prediction(
            GenerationOutput(
                request_id="pope_req_0003",
                raw_text="unclear",
                metadata={"sample_id": "pope_0003", "reference_answer": "yes"},
            )
        ),
    ]
    normalized_path = tmp_path / "normalized_outputs.jsonl"
    normalized_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    metrics = adapter.compute_metrics(normalized_path)
    failures = adapter.extract_failure_cases(normalized_path)

    assert rows[0]["normalized_prediction"] == "yes"
    assert rows[0]["is_correct"] is True
    assert rows[1]["hallucination_label"] is True
    assert rows[2]["normalized_prediction"] == "other"
    assert metrics["sample_count"] == 3
    assert metrics["metrics"]["accuracy"] == 1 / 3
    assert metrics["metrics"]["yes_rate"] == 2 / 3
    assert metrics["metrics"]["hallucination_rate"] == 2 / 3
    assert [failure["sample_id"] for failure in failures] == ["pope_0002", "pope_0003"]


def test_pope_adapter_build_requests_rejects_unsafe_required_files(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "pope"
    benchmark_path.mkdir()
    outside_path = tmp_path / "outside.json"
    outside_path.write_text('{"sample_id": "outside"}\n', encoding="utf-8")

    adapter = POPEAdapter({"path": str(benchmark_path), "required_files": ["../outside.json"]})

    with pytest.raises(RuntimeError, match="unsafe required file"):
        adapter.build_requests(split="validation", limit=1)


def test_model_inventory_rejects_parent_traversal_required_files(tmp_path: Path) -> None:
    model_path = tmp_path / "model"
    model_path.mkdir()
    (tmp_path / "outside-config.json").write_text("{}", encoding="utf-8")

    report = Qwen3VLAdapter({"path": str(model_path), "required_files": ["../outside-config.json"]}).validate_environment()

    assert report.status == "failed"
    assert report.checks[-1]["name"] == "model_inventory"
    assert report.checks[-1]["status"] == "failed"
    assert report.checks[-1]["unsafe_files"] == ["../outside-config.json"]


def test_benchmark_inventory_rejects_absolute_required_files(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "pope"
    benchmark_path.mkdir()
    outside_file = tmp_path / "outside.json"
    outside_file.write_text("[]\n", encoding="utf-8")

    report = POPEAdapter({"path": str(benchmark_path), "required_files": [str(outside_file)]}).validate_paths()

    assert report.status == "failed"
    assert report.checks[-1]["name"] == "benchmark_inventory"
    assert report.checks[-1]["status"] == "failed"
    assert report.checks[-1]["unsafe_files"] == [str(outside_file)]


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

    model_report = InternVLAdapter({"local_path": "${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct"}).validate_environment()
    benchmark_report = POPEAdapter({"path": "${REMOTE_BENCHMARK_ROOT}/POPE"}).validate_paths()

    assert model_report.status == "passed"
    assert model_report.checks[-1]["path"] == str(model_path)
    assert benchmark_report.status == "passed"
    assert benchmark_report.checks[-1]["path"] == str(benchmark_path)


def test_validate_only_skeletons_report_missing_env_templates() -> None:
    model_report = InternVLAdapter({"local_path": "${MISSING_MODEL_ROOT}/Qwen3-VL-2B-Instruct"}).validate_environment()
    benchmark_report = POPEAdapter({"path": "${MISSING_BENCHMARK_ROOT}/POPE"}).validate_paths()

    assert model_report.status == "needs_setup"
    assert model_report.checks[-1]["env_var"] == "MISSING_MODEL_ROOT"
    assert benchmark_report.status == "needs_setup"
    assert benchmark_report.checks[-1]["env_var"] == "MISSING_BENCHMARK_ROOT"
