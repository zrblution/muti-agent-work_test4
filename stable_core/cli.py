from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from research_tools.baseline_indexer import research_status, write_baseline_reports
from experiments.fake.evaluator import run_fake_eval, validate_benchmark, validate_model
from stable_core.config import export_schemas, list_agents, list_benchmarks, list_models, validate_config
from stable_core.evidence.registry import add_record_from_args, init_registry, list_registry
from stable_core.runner.local import LocalRunner
from stable_core.state_machine.state_manager import StateManager
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

    validate_benchmark_parser = subparsers.add_parser("validate-benchmark", help="Validate a configured benchmark without running it.")
    validate_benchmark_parser.add_argument("benchmark_id")

    run_eval = subparsers.add_parser("run-eval", help="Run a controlled evaluation path.")
    run_eval.add_argument("--model", required=True)
    run_eval.add_argument("--benchmark", required=True)
    run_eval.add_argument("--limit", type=int, default=3)
    run_eval.add_argument("--run-id", default=None)
    run_eval.add_argument("--instrumentation", default="none")

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
    if args.command == "validate-benchmark":
        report = validate_benchmark(args.benchmark_id)
        print(json.dumps({"command": "validate-benchmark", **report}, ensure_ascii=False))
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
    if args.command == "research-status":
        print(json.dumps({"command": "research-status", **research_status(Path("."))}, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
