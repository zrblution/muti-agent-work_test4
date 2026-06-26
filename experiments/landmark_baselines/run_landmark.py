from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from adapters.benchmarks._skeleton import ValidateOnlyBenchmarkAdapter
from adapters.models._skeleton import ValidateOnlyModelAdapter
from experiments.fake.evaluator import BENCHMARK_ADAPTERS, MODEL_ADAPTERS, _config_entry, validate_benchmark, validate_model
from experiments.landmark_baselines.runner import LANDMARK_SMOKE_ARTIFACT_CONTRACT, _write_needs_attention
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_landmark_worker")
    parser.add_argument("--model", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--instrumentation", default="none")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", default="runs")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = run_worker(
            run_id=args.run_id,
            model_id=args.model,
            benchmark_id=args.benchmark,
            limit=args.limit,
            instrumentation_mode=args.instrumentation,
            runs_root=args.runs_root,
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("status") == "succeeded" else 1


def record_worker_not_implemented(**kwargs: Any) -> dict[str, object]:
    return run_worker(**kwargs)


def run_worker(
    *,
    run_id: str,
    model_id: str,
    benchmark_id: str,
    limit: int,
    instrumentation_mode: str,
    runs_root: str | Path = Path("runs"),
) -> dict[str, object]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    validate_run_id(run_id)
    if instrumentation_mode not in {"none", "light", "deep"}:
        raise ValueError("instrumentation_mode must be one of none, light, deep")

    run_dir = ensure_run_dir(runs_root, run_id)
    raw_outputs_path = run_dir / "raw_outputs.jsonl"
    if raw_outputs_path.exists() and raw_outputs_path.stat().st_size > 0:
        raise FileExistsError(f"raw_outputs already exists and will not be overwritten: {raw_outputs_path}")

    started_at = utc_now()
    command = {
        "run_id": run_id,
        "command": "landmark-worker",
        "model_id": model_id,
        "benchmark_id": benchmark_id,
        "limit": limit,
        "instrumentation_mode": instrumentation_mode,
        "controlled": True,
        "reproduction_command": _reproduction_command(
            run_id=run_id,
            model_id=model_id,
            benchmark_id=benchmark_id,
            limit=limit,
            instrumentation_mode=instrumentation_mode,
            runs_root=runs_root,
        ),
    }
    write_json(run_dir / "command_manifest.json", command)
    write_json(run_dir / "env_snapshot.json", collect_env_snapshot(Path.cwd()))
    write_text(run_dir / "git_commit.txt", current_git_commit(Path.cwd()) + "\n")
    write_text(run_dir / "stdout.log", "")

    model_report = validate_model(model_id)
    benchmark_report = validate_benchmark(benchmark_id)
    gate_failures = [
        {"gate": "validate-model", "payload": model_report}
        if model_report.get("status") != "passed"
        else None,
        {"gate": "validate-benchmark", "payload": benchmark_report}
        if benchmark_report.get("status") != "passed"
        else None,
    ]
    gate_failures = [item for item in gate_failures if item is not None]
    if gate_failures:
        message = "Landmark worker validation gates did not pass; no real model or benchmark execution was attempted."
        write_text(run_dir / "stderr.log", message + "\n")
        write_text(run_dir / "exit_code.txt", "1\n")
        return _write_needs_attention(
            run_dir=run_dir,
            run_id=run_id,
            command=command,
            failure_type="landmark_worker_validation_gate_not_ready",
            failure_message=message,
            gate_failures=gate_failures,
            started_at=started_at,
            recommended_next_action=[
                "Configure approved model and benchmark paths.",
                "Re-run validate-model and validate-benchmark until both return passed.",
                "Keep the worker behind the reviewed RemoteRunner process submission gate.",
            ],
        )

    runtime_gate_failures = _runtime_gate_failures(model_id=model_id, benchmark_id=benchmark_id)
    if runtime_gate_failures:
        message = "Landmark worker runtime gates did not pass; no real model or benchmark execution was attempted."
        write_text(run_dir / "stderr.log", message + "\n")
        write_text(run_dir / "exit_code.txt", "1\n")
        return _write_needs_attention(
            run_dir=run_dir,
            run_id=run_id,
            command=command,
            failure_type="landmark_worker_runtime_gate_not_ready",
            failure_message=message,
            gate_failures=runtime_gate_failures,
            started_at=started_at,
            recommended_next_action=[
                "Implement runtime methods for the adapters listed in gate_failures.",
                "Keep the worker behind the reviewed RemoteRunner process submission gate.",
            ],
        )

    try:
        return _execute_worker(
            run_dir=run_dir,
            run_id=run_id,
            command=command,
            model_id=model_id,
            benchmark_id=benchmark_id,
            limit=limit,
            instrumentation_mode=instrumentation_mode,
            started_at=started_at,
        )
    except Exception as exc:
        message = "Landmark worker execution failed; preserving failure diagnostics."
        write_text(run_dir / "stderr.log", message + "\n\n" + traceback.format_exc())
        write_text(run_dir / "exit_code.txt", "1\n")
        return _write_needs_attention(
            run_dir=run_dir,
            run_id=run_id,
            command=command,
            failure_type="landmark_worker_execution_failed",
            failure_message=message,
            gate_failures=[
                {
                    "gate": "worker-execution",
                    "payload": {
                        "status": "needs_attention",
                        "exception_type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            ],
            started_at=started_at,
            recommended_next_action=[
                "Inspect stderr.log and failure.json for the worker execution exception.",
                "Fix the model, benchmark, dependency, or worker-loop issue before retrying.",
                "Do not continue to later phases until this real-smoke run succeeds or has a reviewed failure bundle.",
            ],
        )


def _execute_worker(
    *,
    run_dir: Path,
    run_id: str,
    command: dict[str, Any],
    model_id: str,
    benchmark_id: str,
    limit: int,
    instrumentation_mode: str,
    started_at: str,
) -> dict[str, object]:
    model_class = MODEL_ADAPTERS[model_id]
    benchmark_class = BENCHMARK_ADAPTERS[benchmark_id]
    model = model_class(_config_entry(REPO_ROOT / "project_config" / "models.yaml", "models", model_id))
    benchmark = benchmark_class(_config_entry(REPO_ROOT / "project_config" / "benchmarks.yaml", "benchmarks", benchmark_id))

    stdout_lines = [
        f"Starting landmark worker run_id={run_id}",
        f"model_id={model_id}",
        f"benchmark_id={benchmark_id}",
        f"limit={limit}",
    ]
    model_loaded = False
    raw_rows: list[dict[str, Any]] = []
    normalized_rows: list[dict[str, Any]] = []
    try:
        model.load()
        model_loaded = True
        requests = benchmark.build_requests(split="validation", limit=limit)
        for line_number, request in enumerate(requests, start=1):
            output = model.generate(request)
            raw_rows.append(_raw_output_row(output=output, request=request, model_id=model_id, benchmark_id=benchmark_id))
            normalized_input = _normalizer_input(output=output, request=request)
            normalized = benchmark.normalize_prediction(normalized_input)
            normalized["raw_text_ref"] = f"raw_outputs.jsonl:line_{line_number}"
            normalized_rows.append(normalized)
        stdout_lines.append(f"generated_samples={len(raw_rows)}")
    finally:
        if model_loaded:
            model.unload()

    raw_outputs_path = run_dir / "raw_outputs.jsonl"
    if raw_outputs_path.exists() and raw_outputs_path.stat().st_size > 0:
        raise FileExistsError(f"raw_outputs already exists and will not be overwritten: {raw_outputs_path}")
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
        "parser_version": getattr(benchmark, "normalizer_version", "unknown"),
        "computed_at": utc_now(),
    }
    write_json(run_dir / "metrics.json", metrics)
    _write_jsonl(run_dir / "failure_cases.jsonl", benchmark.extract_failure_cases(normalized_path))
    write_text(run_dir / "stdout.log", "\n".join(stdout_lines) + "\n")
    write_text(run_dir / "stderr.log", "")
    _write_success_manifest(
        run_dir=run_dir,
        run_id=run_id,
        command=command,
        started_at=started_at,
        metrics=metrics,
    )
    write_json(run_dir / "artifact_manifest.json", artifact_manifest_for(run_dir, run_id))
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "status": "succeeded",
        "sample_count": metrics["sample_count"],
        "metrics": metrics["metrics"],
    }


def _raw_output_row(
    *,
    output: Any,
    request: Any,
    model_id: str,
    benchmark_id: str,
) -> dict[str, Any]:
    return {
        "request_id": output.request_id,
        "sample_id": request.sample_id,
        "model_id": model_id,
        "benchmark_id": benchmark_id,
        "raw_text": output.raw_text,
        "tokens": output.tokens,
        "latency_ms": output.latency_ms,
        "generation_config": output.metadata.get("generation_config", {}),
        "plugin_id": None,
        "created_at": utc_now(),
    }


def _normalizer_input(*, output: Any, request: Any) -> Any:
    output.metadata = {
        **request.metadata,
        **output.metadata,
        "sample_id": request.sample_id,
        "benchmark_id": request.benchmark_id,
    }
    return output


def _write_success_manifest(
    *,
    run_dir: Path,
    run_id: str,
    command: dict[str, Any],
    started_at: str,
    metrics: dict[str, Any],
) -> None:
    finished_at = utc_now()
    write_json(
        run_dir / "run_manifest.json",
        {
            "run_id": run_id,
            "run_type": "landmark_baseline",
            "model_id": command["model_id"],
            "benchmark_id": command["benchmark_id"],
            "idea_id": None,
            "limit": command["limit"],
            "instrumentation_mode": command["instrumentation_mode"],
            "started_at": started_at,
            "finished_at": finished_at,
            "status": "succeeded",
            "git_commit": current_git_commit(Path.cwd()),
            "outputs": {
                "raw_outputs": "raw_outputs.jsonl",
                "normalized_outputs": "normalized_outputs.jsonl",
                "metrics": "metrics.json",
                "failure_cases": "failure_cases.jsonl",
                "experiment_summary": "experiment_summary.md",
                "reproducibility_notes": "reproducibility_notes.md",
            },
            "artifact_contract": dict(LANDMARK_SMOKE_ARTIFACT_CONTRACT),
        },
    )
    write_text(
        run_dir / "experiment_summary.md",
        "\n".join(
            [
                "# Landmark Worker Summary",
                "",
                f"- run_id: `{run_id}`",
                f"- model_id: `{command['model_id']}`",
                f"- benchmark_id: `{command['benchmark_id']}`",
                f"- sample_count: `{metrics['sample_count']}`",
                f"- metrics: `{json.dumps(metrics['metrics'], sort_keys=True)}`",
            ]
        )
        + "\n",
    )
    write_text(
        run_dir / "reproducibility_notes.md",
        "\n".join(
            [
                "# Reproducibility Notes",
                "",
                f"- reproduction_command: `{command['reproduction_command']}`",
                f"- git_commit: `{current_git_commit(Path.cwd())}`",
                "- raw_outputs_policy: `never_overwrite`",
                "- large_artifact_policy: `manifest_only`",
            ]
        )
        + "\n",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _runtime_gate_failures(*, model_id: str, benchmark_id: str) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    model_class = MODEL_ADAPTERS.get(model_id)
    if model_class is None:
        failures.append(
            {
                "gate": "model-runtime",
                "payload": {
                    "status": "failed",
                    "model_id": model_id,
                    "message": "No model adapter is registered for runtime execution.",
                },
            }
        )
    else:
        unimplemented_model_methods = _inherited_methods(
            model_class,
            ValidateOnlyModelAdapter,
            ["load", "generate"],
        )
        if unimplemented_model_methods:
            failures.append(
                {
                    "gate": "model-runtime",
                    "payload": {
                        "status": "needs_attention",
                        "model_id": model_id,
                        "adapter": model_class.__name__,
                        "unimplemented_methods": unimplemented_model_methods,
                        "message": "Model adapter still inherits validate-only runtime methods.",
                    },
                }
            )

    benchmark_class = BENCHMARK_ADAPTERS.get(benchmark_id)
    if benchmark_class is None:
        failures.append(
            {
                "gate": "benchmark-runtime",
                "payload": {
                    "status": "failed",
                    "benchmark_id": benchmark_id,
                    "message": "No benchmark adapter is registered for runtime execution.",
                },
            }
        )
    else:
        unimplemented_benchmark_methods = _inherited_methods(
            benchmark_class,
            ValidateOnlyBenchmarkAdapter,
            ["build_requests", "normalize_prediction", "compute_metrics", "extract_failure_cases"],
        )
        if unimplemented_benchmark_methods:
            failures.append(
                {
                    "gate": "benchmark-runtime",
                    "payload": {
                        "status": "needs_attention",
                        "benchmark_id": benchmark_id,
                        "adapter": benchmark_class.__name__,
                        "unimplemented_methods": unimplemented_benchmark_methods,
                        "message": "Benchmark adapter still inherits validate-only runtime methods.",
                    },
                }
            )
    return failures


def _inherited_methods(adapter_class: type, base_class: type, method_names: list[str]) -> list[str]:
    return [
        method_name
        for method_name in method_names
        if getattr(adapter_class, method_name) is getattr(base_class, method_name)
    ]


def _reproduction_command(
    *,
    run_id: str,
    model_id: str,
    benchmark_id: str,
    limit: int,
    instrumentation_mode: str,
    runs_root: str | Path,
) -> str:
    return (
        "python experiments/landmark_baselines/run_landmark.py "
        f"--model {model_id} "
        f"--benchmark {benchmark_id} "
        f"--limit {limit} "
        f"--instrumentation {instrumentation_mode} "
        f"--run-id {run_id} "
        f"--runs-root {runs_root}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
