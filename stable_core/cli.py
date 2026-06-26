from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from research_tools.baseline_indexer import research_status, write_baseline_reports
from experiments.fake.evaluator import run_fake_eval, validate_benchmark, validate_model, validate_model_runtime
from experiments.landmark_baselines.runner import run_landmark
from stable_core.config import export_schemas, list_agents, list_benchmarks, list_models, validate_config
from stable_core.evidence.registry import add_record_from_args, init_registry, list_registry
from stable_core.runner.local import LocalRunner
from stable_core.state_machine.state_manager import StateManager
from stable_core.storage.run_results import parse_recorded_results, poll_recorded_run
from stable_core.storage.run_validator import validate_run_artifacts
from stable_core.validation.inventory_discovery import discover_benchmark_inventory, discover_model_inventory
from stable_core.validation.model_candidates import discover_phase5_model_candidates
from stable_core.validation.phase5_readiness import build_phase5_path_probe, build_phase5_readiness_bundle
from stable_core.validation.preflight import run_preflight

DEFAULT_REGISTRY = Path("evidence/registry.jsonl")
DEFAULT_RESEARCH_DIR = Path("docs/research")
DEFAULT_RUNS_ROOT = Path("runs")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stable_core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Run Phase 0 preflight checks.")
    preflight.add_argument("--dry-run", action="store_true", help="Record missing setup without running remote jobs.")
    preflight.add_argument("--output-dir", default="runs/preflight", help="Directory for preflight artifacts.")

    subparsers.add_parser("doctor", help="Print machine-readable preflight status.")
    subparsers.add_parser("validate-config", help="Validate project configuration structure.")
    subparsers.add_parser("list-models", help="List configured model ids.")
    subparsers.add_parser("list-benchmarks", help="List configured benchmark ids.")
    subparsers.add_parser("list-agents", help="List configured agent providers.")

    export = subparsers.add_parser("export-schemas", help="Export schema JSON files.")
    export.add_argument("--output", required=True, help="Output directory for schema JSON files.")

    evidence = subparsers.add_parser("evidence", help="Manage the JSONL evidence registry.")
    evidence_subparsers = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_init = evidence_subparsers.add_parser("init", help="Create an evidence registry file.")
    evidence_init.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    evidence_add = evidence_subparsers.add_parser("add", help="Append one evidence record.")
    evidence_add.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    evidence_add.add_argument("--evidence-id", required=True)
    evidence_add.add_argument("--source-type", required=True)
    evidence_add.add_argument("--source-name", required=True)
    evidence_add.add_argument("--claim-supported", required=True)
    evidence_add.add_argument("--claim-scope", required=True)
    evidence_add.add_argument("--confidence", required=True)
    evidence_add.add_argument("--created-by", required=True)
    evidence_add.add_argument("--path", default=None)
    evidence_add.add_argument("--url", default=None)
    evidence_add.add_argument("--commit", default=None)
    evidence_add.add_argument("--line-start", type=int, default=None)
    evidence_add.add_argument("--line-end", type=int, default=None)
    evidence_add.add_argument("--run-id", default=None)
    evidence_add.add_argument("--artifact-id", default=None)
    evidence_list = evidence_subparsers.add_parser("list", help="List evidence records.")
    evidence_list.add_argument("--registry", default=str(DEFAULT_REGISTRY))

    index = subparsers.add_parser("index-baselines", help="Index baseline MANIFEST.tsv into research outputs.")
    index.add_argument("--manifest", required=True)
    index.add_argument("--output-dir", default=str(DEFAULT_RESEARCH_DIR))
    index.add_argument("--registry", default=str(DEFAULT_REGISTRY))

    workflow = subparsers.add_parser("workflow", help="Manage durable workflow state.")
    workflow_subparsers = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_init = workflow_subparsers.add_parser("init", help="Create runs/<workflow_id>/state.json.")
    workflow_init.add_argument("--workflow-id", required=True)
    workflow_init.add_argument("--current-state", default="preflight_validation")
    workflow_status = workflow_subparsers.add_parser("status", help="Read workflow state.")
    workflow_status.add_argument("--workflow-id", required=True)
    workflow_resume = workflow_subparsers.add_parser("resume", help="Resume from existing workflow state.")
    workflow_resume.add_argument("--workflow-id", required=True)
    workflow_failed = workflow_subparsers.add_parser("mark-failed", help="Mark a workflow failed with a preserved reason.")
    workflow_failed.add_argument("--workflow-id", required=True)
    workflow_failed.add_argument("--reason", required=True)

    run_local = subparsers.add_parser("run-local", help="Run a controlled local Phase 3 action.")
    run_local.add_argument("--run-id", required=True)
    run_local.add_argument("--action", required=True, choices=["dummy_job"])
    run_local.add_argument("--message", default="dummy job")
    run_local.add_argument("--fail", action="store_true")

    validate_model_parser = subparsers.add_parser("validate-model", help="Validate a configured model without loading weights.")
    validate_model_parser.add_argument("model_id")

    validate_model_runtime_parser = subparsers.add_parser("validate-model-runtime", help="Validate model runtime dependencies without requiring model files or loading weights.")
    validate_model_runtime_parser.add_argument("model_id")

    discover_model_inventory_parser = subparsers.add_parser("discover-model-inventory", help="Discover model metadata candidates without loading weights or modifying config.")
    discover_model_inventory_parser.add_argument("model_id")
    discover_model_inventory_parser.add_argument("--output", default=None, help="Optional JSON report path.")
    discover_model_inventory_parser.add_argument("--max-files", type=int, default=20)

    validate_benchmark_parser = subparsers.add_parser("validate-benchmark", help="Validate a configured benchmark without running it.")
    validate_benchmark_parser.add_argument("benchmark_id")

    discover_benchmark_inventory_parser = subparsers.add_parser("discover-benchmark-inventory", help="Discover benchmark metadata/sample candidates without modifying config.")
    discover_benchmark_inventory_parser.add_argument("benchmark_id")
    discover_benchmark_inventory_parser.add_argument("--output", default=None, help="Optional JSON report path.")
    discover_benchmark_inventory_parser.add_argument("--max-files", type=int, default=20)

    run_eval = subparsers.add_parser("run-eval", help="Run a controlled evaluation path.")
    run_eval.add_argument("--model", required=True)
    run_eval.add_argument("--benchmark", required=True)
    run_eval.add_argument("--limit", type=int, default=3)
    run_eval.add_argument("--run-id", default=None)
    run_eval.add_argument("--instrumentation", default="none")

    run_landmark_parser = subparsers.add_parser("run-landmark", help="Run or gate a controlled landmark evaluation.")
    run_landmark_parser.add_argument("--model", required=True)
    run_landmark_parser.add_argument("--benchmark", required=True)
    run_landmark_parser.add_argument("--limit", type=int, required=True)
    run_landmark_parser.add_argument("--instrumentation", default="none")
    run_landmark_parser.add_argument("--run-id", default=None)

    phase5_readiness_parser = subparsers.add_parser("phase5-readiness", help="Write a read-only Phase 5 readiness bundle.")
    phase5_readiness_parser.add_argument("--model", required=True)
    phase5_readiness_parser.add_argument("--benchmark", required=True)
    phase5_readiness_parser.add_argument("--limit", type=int, required=True)
    phase5_readiness_parser.add_argument("--instrumentation", default="none")
    phase5_readiness_parser.add_argument("--output-dir", required=True)

    phase5_probe_parser = subparsers.add_parser("phase5-probe-paths", help="Probe candidate Phase 5 model and benchmark roots without mutating config or environment.")
    phase5_probe_parser.add_argument("--model", required=True)
    phase5_probe_parser.add_argument("--benchmark", required=True)
    phase5_probe_parser.add_argument("--model-root", required=True)
    phase5_probe_parser.add_argument("--benchmark-root", required=True)
    phase5_probe_parser.add_argument("--output", default=None)

    phase5_discover_model_parser = subparsers.add_parser("phase5-discover-model-candidates", help="Discover reviewable Phase 5 model path candidates under explicit search roots.")
    phase5_discover_model_parser.add_argument("model_id")
    phase5_discover_model_parser.add_argument("--search-root", action="append", required=True, help="Bounded root to scan. Repeat for multiple roots.")
    phase5_discover_model_parser.add_argument("--output", default=None)
    phase5_discover_model_parser.add_argument("--max-depth", type=int, default=6)
    phase5_discover_model_parser.add_argument("--max-candidates", type=int, default=40)
    phase5_discover_model_parser.add_argument("--max-entries", type=int, default=20000)

    poll_parser = subparsers.add_parser("poll", help="Poll a recorded run directory without executing jobs.")
    poll_parser.add_argument("--run-id", required=True)
    poll_parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))

    parse_results_parser = subparsers.add_parser("parse-results", help="Read and summarize recorded run results.")
    parse_results_parser.add_argument("--run-id", required=True)
    parse_results_parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))

    validate_run_parser = subparsers.add_parser("validate-run", help="Validate a recorded run directory.")
    validate_run_parser.add_argument("--run-id", required=True)
    validate_run_parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))

    subparsers.add_parser("research-status", help="Report research artifact status.")
    return parser


def _exit_code(status: str) -> int:
    return 1 if status == "failed" else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "preflight":
        report = run_preflight(output_dir=Path(args.output_dir), dry_run=args.dry_run)
        print(json.dumps({"command": "preflight", "status": report["status"]}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    if args.command == "doctor":
        report = run_preflight(output_dir=Path("runs/preflight"), dry_run=True)
        print(json.dumps({"command": "doctor", "preflight_status": report["status"]}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    if args.command == "validate-config":
        report = validate_config()
        print(json.dumps({"command": "validate-config", **report}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    if args.command == "list-models":
        print(json.dumps({"command": "list-models", "models": list_models()}, ensure_ascii=False))
        return 0
    if args.command == "list-benchmarks":
        print(json.dumps({"command": "list-benchmarks", "benchmarks": list_benchmarks()}, ensure_ascii=False))
        return 0
    if args.command == "list-agents":
        print(json.dumps({"command": "list-agents", "providers": list_agents()}, ensure_ascii=False))
        return 0
    if args.command == "export-schemas":
        schemas = export_schemas(Path(args.output))
        print(json.dumps({"command": "export-schemas", "schemas": schemas}, ensure_ascii=False))
        return 0
    if args.command == "evidence":
        if args.evidence_command == "init":
            print(json.dumps({"command": "evidence init", **init_registry(args.registry)}, ensure_ascii=False))
            return 0
        if args.evidence_command == "add":
            print(json.dumps({"command": "evidence add", **add_record_from_args(args)}, ensure_ascii=False))
            return 0
        if args.evidence_command == "list":
            print(json.dumps({"command": "evidence list", **list_registry(args.registry)}, ensure_ascii=False))
            return 0
    if args.command == "index-baselines":
        summary = write_baseline_reports(args.manifest, args.output_dir, args.registry)
        print(json.dumps({"command": "index-baselines", **summary}, ensure_ascii=False))
        return 0
    if args.command == "workflow":
        manager = StateManager(DEFAULT_RUNS_ROOT)
        if args.workflow_command == "init":
            state = manager.init_workflow(args.workflow_id, current_state=args.current_state)
            print(json.dumps({"command": "workflow init", **state.to_dict()}, ensure_ascii=False))
            return 0
        if args.workflow_command == "status":
            state = manager.load(args.workflow_id)
            print(json.dumps({"command": "workflow status", **state.to_dict()}, ensure_ascii=False))
            return 0
        if args.workflow_command == "resume":
            state = manager.resume(args.workflow_id)
            print(json.dumps({"command": "workflow resume", **state.to_dict()}, ensure_ascii=False))
            return 0
        if args.workflow_command == "mark-failed":
            state = manager.mark_failed(args.workflow_id, reason=args.reason)
            print(json.dumps({"command": "workflow mark-failed", **state.to_dict()}, ensure_ascii=False))
            return 0
    if args.command == "run-local":
        result = LocalRunner(DEFAULT_RUNS_ROOT).run_dummy(run_id=args.run_id, message=args.message, fail=args.fail)
        print(json.dumps({"command": "run-local", **result}, ensure_ascii=False))
        return 0 if result["status"] == "succeeded" else 1
    if args.command == "validate-model":
        report = validate_model(args.model_id)
        print(json.dumps({"command": "validate-model", **report}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    if args.command == "validate-model-runtime":
        report = validate_model_runtime(args.model_id)
        print(json.dumps({"command": "validate-model-runtime", **report}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    if args.command == "discover-model-inventory":
        report = discover_model_inventory(args.model_id, output=args.output, max_files=args.max_files)
        print(json.dumps({"command": "discover-model-inventory", **report}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    if args.command == "validate-benchmark":
        report = validate_benchmark(args.benchmark_id)
        print(json.dumps({"command": "validate-benchmark", **report}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    if args.command == "discover-benchmark-inventory":
        report = discover_benchmark_inventory(args.benchmark_id, output=args.output, max_files=args.max_files)
        print(json.dumps({"command": "discover-benchmark-inventory", **report}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    if args.command == "run-eval":
        run_id = args.run_id or f"{args.model}_{args.benchmark}_fake_eval"
        try:
            result = run_fake_eval(
                run_id=run_id,
                model_id=args.model,
                benchmark_id=args.benchmark,
                limit=args.limit,
                runs_root=DEFAULT_RUNS_ROOT,
                instrumentation_mode=args.instrumentation,
            )
        except Exception as exc:
            print(json.dumps({"command": "run-eval", "status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps({"command": "run-eval", **result}, ensure_ascii=False))
        return 0
    if args.command == "run-landmark":
        run_id = args.run_id or f"{args.model}_{args.benchmark}_limit{args.limit}"
        try:
            result = run_landmark(
                run_id=run_id,
                model_id=args.model,
                benchmark_id=args.benchmark,
                limit=args.limit,
                runs_root=DEFAULT_RUNS_ROOT,
                instrumentation_mode=args.instrumentation,
            )
        except Exception as exc:
            print(json.dumps({"command": "run-landmark", "status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps({"command": "run-landmark", **result}, ensure_ascii=False))
        return 0 if result["status"] == "succeeded" else 1
    if args.command == "phase5-readiness":
        try:
            report = build_phase5_readiness_bundle(
                model_id=args.model,
                benchmark_id=args.benchmark,
                limit=args.limit,
                instrumentation_mode=args.instrumentation,
                output_dir=args.output_dir,
            )
        except Exception as exc:
            print(json.dumps({"command": "phase5-readiness", "status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        safety_flags = report["safety_flags"]
        print(
            json.dumps(
                {
                    "command": "phase5-readiness",
                    "status": report["status"],
                    "model_id": args.model,
                    "benchmark_id": args.benchmark,
                    "limit": args.limit,
                    "instrumentation_mode": args.instrumentation,
                    **safety_flags,
                },
                ensure_ascii=False,
            )
        )
        return _exit_code(str(report["status"]))
    if args.command == "phase5-probe-paths":
        try:
            report = build_phase5_path_probe(
                model_id=args.model,
                benchmark_id=args.benchmark,
                model_root=args.model_root,
                benchmark_root=args.benchmark_root,
                output=args.output,
            )
        except Exception as exc:
            print(json.dumps({"command": "phase5-probe-paths", "status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        safety_flags = report["safety_flags"]
        print(
            json.dumps(
                {
                    "command": "phase5-probe-paths",
                    "status": report["status"],
                    "model_id": args.model,
                    "benchmark_id": args.benchmark,
                    **safety_flags,
                },
                ensure_ascii=False,
            )
        )
        return _exit_code(str(report["status"]))
    if args.command == "phase5-discover-model-candidates":
        try:
            report = discover_phase5_model_candidates(
                args.model_id,
                search_roots=args.search_root,
                output=args.output,
                max_depth=args.max_depth,
                max_candidates=args.max_candidates,
                max_entries=args.max_entries,
            )
        except Exception as exc:
            print(json.dumps({"command": "phase5-discover-model-candidates", "status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(
            json.dumps(
                {
                    "command": "phase5-discover-model-candidates",
                    "status": report["status"],
                    "model_id": args.model_id,
                    "candidate_count": report.get("candidate_count", 0),
                    "write_config": report.get("write_config", False),
                    "load_attempted": report.get("load_attempted", False),
                },
                ensure_ascii=False,
            )
        )
        return _exit_code(str(report["status"]))
    if args.command == "poll":
        report = poll_recorded_run(run_id=args.run_id, runs_root=args.runs_root)
        print(json.dumps({"command": "poll", **report}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    if args.command == "parse-results":
        report = parse_recorded_results(run_id=args.run_id, runs_root=args.runs_root)
        print(json.dumps({"command": "parse-results", **report}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    if args.command == "validate-run":
        report = validate_run_artifacts(run_id=args.run_id, runs_root=args.runs_root)
        print(json.dumps({"command": "validate-run", "run_id": args.run_id, **report}, ensure_ascii=False))
        return 0 if report["status"] == "passed" else 1
    if args.command == "research-status":
        print(json.dumps({"command": "research-status", **research_status(Path("."))}, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
