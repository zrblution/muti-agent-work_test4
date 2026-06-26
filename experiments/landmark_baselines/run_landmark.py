from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from adapters.benchmarks._skeleton import ValidateOnlyBenchmarkAdapter
from adapters.models._skeleton import ValidateOnlyModelAdapter
from experiments.fake.evaluator import BENCHMARK_ADAPTERS, MODEL_ADAPTERS, validate_benchmark, validate_model
from experiments.landmark_baselines.runner import _write_needs_attention
from stable_core.storage.run_directory import (
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
        payload = record_worker_not_implemented(
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
    return 1


def record_worker_not_implemented(
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
                "Implement Qwen3-VL adapter load and generate methods for the approved local model path.",
                "Implement POPE sample parsing, normalization, metrics, and failure-case extraction.",
                "Keep the worker behind the reviewed RemoteRunner process submission gate.",
            ],
        )

    message = "Reviewed real-smoke worker is not implemented; no real model or benchmark execution was attempted."
    write_text(run_dir / "stderr.log", message + "\n")
    write_text(run_dir / "exit_code.txt", "1\n")

    result = _write_needs_attention(
        run_dir=run_dir,
        run_id=run_id,
        command=command,
        failure_type="landmark_worker_not_implemented",
        failure_message=message,
        gate_failures=[
            {
                "gate": "landmark-worker",
                "payload": {
                    "status": "needs_attention",
                    "message": "Implement the reviewed Qwen3-VL + POPE worker before process submission is enabled.",
                },
            }
        ],
        started_at=started_at,
        recommended_next_action=[
            "Implement the non-recursive worker that loads the approved model and benchmark paths.",
            "Keep raw output overwrite protection enabled.",
            "Run the worker only through the reviewed RemoteRunner process submission gate.",
        ],
    )
    return result


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
