from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adapters.benchmarks.amber import AMBERAdapter
from adapters.benchmarks.chair import CHAIRAdapter
from adapters.benchmarks.fake import FakeBenchmarkAdapter
from adapters.benchmarks.mme import MMEAdapter
from adapters.benchmarks.pope import POPEAdapter
from adapters.models.fake import FakeModelAdapter
from adapters.models.internvl import InternVLAdapter
from adapters.models.qwen3_vl import Qwen3VLAdapter
from stable_core.storage.run_directory import (
    artifact_manifest_for,
    collect_env_snapshot,
    current_git_commit,
    ensure_run_dir,
    utc_now,
    validate_run_id,
    write_json,
    write_text,
)
from stable_core.validation.preflight import REPO_ROOT, parse_simple_yaml


MODEL_ADAPTERS = {
    "fake_model": FakeModelAdapter,
    "qwen3_vl_2b_instruct": Qwen3VLAdapter,
    "internvl3_5_4b": InternVLAdapter,
}

BENCHMARK_ADAPTERS = {
    "fake_benchmark": FakeBenchmarkAdapter,
    "pope": POPEAdapter,
    "chair": CHAIRAdapter,
    "amber": AMBERAdapter,
    "mme": MMEAdapter,
}


def validate_model(model_id: str) -> dict[str, Any]:
    adapter_class = MODEL_ADAPTERS.get(model_id)
    if adapter_class is None:
        return {"model_id": model_id, "status": "failed", "checks": [], "summary": "Unknown model id."}
    report = adapter_class(_config_entry(REPO_ROOT / "project_config" / "models.yaml", "models", model_id)).validate_environment()
    return {"model_id": model_id, **report.to_dict()}


def validate_model_runtime(model_id: str) -> dict[str, Any]:
    adapter_class = MODEL_ADAPTERS.get(model_id)
    if adapter_class is None:
        return {"model_id": model_id, "status": "failed", "checks": [], "summary": "Unknown model id."}
    adapter = adapter_class(_config_entry(REPO_ROOT / "project_config" / "models.yaml", "models", model_id))
    validator = getattr(adapter, "validate_runtime_dependencies", None)
    if validator is None:
        return {
            "model_id": model_id,
            "status": "skipped",
            "checks": [{"name": "runtime_dependencies", "status": "skipped"}],
            "summary": "No model-specific runtime dependency preflight is defined.",
        }
    report = validator()
    return {"model_id": model_id, **report.to_dict()}


def validate_benchmark(benchmark_id: str) -> dict[str, Any]:
    adapter_class = BENCHMARK_ADAPTERS.get(benchmark_id)
    if adapter_class is None:
        return {"benchmark_id": benchmark_id, "status": "failed", "checks": [], "summary": "Unknown benchmark id."}
    report = adapter_class(_config_entry(REPO_ROOT / "project_config" / "benchmarks.yaml", "benchmarks", benchmark_id)).validate_paths()
    return {"benchmark_id": benchmark_id, **report.to_dict()}


def run_fake_eval(
    *,
    run_id: str,
    model_id: str = "fake_model",
    benchmark_id: str = "fake_benchmark",
    limit: int | None = 3,
    runs_root: str | Path = Path("runs"),
    instrumentation_mode: str = "none",
) -> dict[str, Any]:
    if model_id != "fake_model" or benchmark_id != "fake_benchmark":
        raise ValueError("Phase 4 run-eval only supports fake_model with fake_benchmark.")
    if instrumentation_mode not in {"none", "light"}:
        raise ValueError("Unsupported instrumentation mode for fake evaluation.")
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    validate_run_id(run_id)
    run_dir = ensure_run_dir(runs_root, run_id)
    raw_outputs_path = run_dir / "raw_outputs.jsonl"
    if raw_outputs_path.exists() and raw_outputs_path.stat().st_size > 0:
        raise FileExistsError(f"raw_outputs already exists and will not be overwritten: {raw_outputs_path}")

    started_at = utc_now()
    model = FakeModelAdapter()
    benchmark = FakeBenchmarkAdapter()
    model_report = model.validate_environment()
    benchmark_report = benchmark.validate_paths()
    if model_report.status != "passed" or benchmark_report.status != "passed":
        raise RuntimeError("Fake model and benchmark validation should pass before execution.")

    write_json(run_dir / "command_manifest.json", {"run_id": run_id, "command": "run-eval", "model_id": model_id, "benchmark_id": benchmark_id, "limit": limit})
    write_json(run_dir / "env_snapshot.json", collect_env_snapshot(Path.cwd()))
    write_text(run_dir / "git_commit.txt", current_git_commit(Path.cwd()) + "\n")

    model.load()
    requests = benchmark.build_requests(split="validation", limit=limit)
    raw_rows: list[dict[str, Any]] = []
    normalized_rows: list[dict[str, Any]] = []
    try:
        for line_number, request in enumerate(requests, start=1):
            output = model.generate(request)
            raw_rows.append(
                {
                    "request_id": output.request_id,
                    "sample_id": request.sample_id,
                    "model_id": model_id,
                    "benchmark_id": benchmark_id,
                    "raw_text": output.raw_text,
                    "tokens": output.tokens,
                    "latency_ms": output.latency_ms,
                    "generation_config": {},
                    "plugin_id": None,
                    "created_at": utc_now(),
                }
            )
            normalized = benchmark.normalize_prediction(output)
            normalized["raw_text_ref"] = f"raw_outputs.jsonl:line_{line_number}"
            normalized_rows.append(normalized)
    finally:
        model.unload()

    _write_jsonl(raw_outputs_path, raw_rows)
    normalized_path = run_dir / "normalized_outputs.jsonl"
    _write_jsonl(normalized_path, normalized_rows)

    metric_payload = benchmark.compute_metrics(normalized_path)
    metrics = {
        "run_id": run_id,
        "benchmark_id": benchmark_id,
        "model_id": model_id,
        "sample_count": metric_payload["sample_count"],
        "metrics": metric_payload["metrics"],
        "parser_version": benchmark.normalizer_version,
        "computed_at": utc_now(),
    }
    write_json(run_dir / "metrics.json", metrics)
    _write_jsonl(run_dir / "failure_cases.jsonl", benchmark.extract_failure_cases(normalized_path))

    finished_at = utc_now()
    write_json(
        run_dir / "run_manifest.json",
        {
            "run_id": run_id,
            "run_type": "landmark_baseline",
            "model_id": model_id,
            "benchmark_id": benchmark_id,
            "idea_id": None,
            "limit": limit,
            "instrumentation_mode": instrumentation_mode,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": "succeeded",
            "config_snapshot_sha256": None,
            "git_commit": current_git_commit(Path.cwd()),
            "outputs": {
                "raw_outputs": "raw_outputs.jsonl",
                "normalized_outputs": "normalized_outputs.jsonl",
                "metrics": "metrics.json",
                "failure_cases": "failure_cases.jsonl",
            },
        },
    )
    write_text(
        run_dir / "experiment_summary.md",
        "\n".join(
            [
                "# Fake Evaluation Summary",
                "",
                f"- run_id: `{run_id}`",
                f"- model_id: `{model_id}`",
                f"- benchmark_id: `{benchmark_id}`",
                f"- sample_count: `{metrics['sample_count']}`",
                f"- accuracy: `{metrics['metrics']['accuracy']}`",
            ]
        )
        + "\n",
    )
    write_json(run_dir / "artifact_manifest.json", artifact_manifest_for(run_dir, run_id))
    return {"run_id": run_id, "run_dir": str(run_dir), "status": "succeeded", "sample_count": metrics["sample_count"], "metrics": metrics["metrics"]}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _config_entry(config_path: Path, section: str, item_id: str) -> dict[str, Any]:
    data = parse_simple_yaml(config_path)
    items = data.get(section, {})
    if not isinstance(items, dict):
        return {}
    entry = items.get(item_id, {})
    return entry if isinstance(entry, dict) else {}
