from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from experiments.fake.evaluator import MODEL_ADAPTERS, validate_benchmark, validate_model, validate_model_runtime
from stable_core.config import validate_config
from stable_core.runner.remote import RemoteRunner
from stable_core.storage.run_validator import validate_run_artifacts
from stable_core.storage.run_directory import current_git_commit, sha256_file, utc_now, write_json, write_text
from stable_core.validation.inventory_discovery import discover_benchmark_inventory, discover_model_inventory
from stable_core.validation.preflight import REPO_ROOT, parse_simple_yaml


SAFETY_FLAGS = {
    "executed_real_model": False,
    "executed_real_benchmark": False,
    "submitted_remote_job": False,
    "raw_outputs_written": False,
    "write_config": False,
}

_ENV_TEMPLATE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def build_phase5_readiness_bundle(
    *,
    model_id: str,
    benchmark_id: str,
    limit: int,
    instrumentation_mode: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if instrumentation_mode not in {"none", "light", "deep"}:
        raise ValueError("instrumentation_mode must be one of none, light, deep")

    checks = {
        "config": validate_config(),
        "model_inventory_discovery": discover_model_inventory(model_id),
        "benchmark_inventory_discovery": discover_benchmark_inventory(benchmark_id),
        "model_runtime_dependencies": validate_model_runtime(model_id),
        "model_validation": validate_model(model_id),
        "benchmark_validation": validate_benchmark(benchmark_id),
    }
    execution_authorization = RemoteRunner().submit(
        {
            "action": "run_model_smoke_test",
            "allowed_script": "experiments/landmark_baselines/run_landmark.py",
            "model_id": model_id,
            "benchmark_id": benchmark_id,
            "limit": limit,
            "instrumentation_mode": instrumentation_mode,
        },
        plan_only=True,
    )
    status = _readiness_status(checks, execution_authorization)
    bundle = {
        "phase": "Phase 5",
        "status": status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "target": {
            "model_id": model_id,
            "benchmark_id": benchmark_id,
            "limit": limit,
            "instrumentation_mode": instrumentation_mode,
        },
        "checks": checks,
        "execution_authorization": execution_authorization,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _next_actions(checks, execution_authorization),
        "do_not_continue_reason": _do_not_continue_reason(status, checks, execution_authorization),
    }
    if output_dir is not None:
        _write_bundle(Path(output_dir), bundle)
    return bundle


def build_phase5_path_probe(
    *,
    model_id: str,
    benchmark_id: str,
    model_root: str | Path,
    benchmark_root: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    model_env = _configured_root_env("models.yaml", "models", model_id, "model_root_env", ("local_path", "path"))
    benchmark_env = _configured_root_env("benchmarks.yaml", "benchmarks", benchmark_id, "benchmark_root_env", ("path",))
    candidate_env = {
        model_env: str(model_root),
        benchmark_env: str(benchmark_root),
    }
    with _temporary_env(candidate_env):
        checks = {
            "config": validate_config(),
            "model_inventory_discovery": discover_model_inventory(model_id),
            "benchmark_inventory_discovery": discover_benchmark_inventory(benchmark_id),
            "model_runtime_dependencies": validate_model_runtime(model_id),
            "model_validation": validate_model(model_id),
            "benchmark_validation": validate_benchmark(benchmark_id),
        }
    status = _checks_status(checks)
    report = {
        "phase": "Phase 5",
        "mode": "path_probe",
        "status": status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "target": {
            "model_id": model_id,
            "benchmark_id": benchmark_id,
        },
        "candidate_env": candidate_env,
        "checks": checks,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _path_probe_next_actions(status, checks, candidate_env),
    }
    if output is not None:
        write_json(Path(output), report)
    return report


def build_phase5_explicit_model_path_probe(
    *,
    model_id: str,
    benchmark_id: str,
    model_path: str | Path,
    benchmark_root: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    benchmark_env = _configured_root_env("benchmarks.yaml", "benchmarks", benchmark_id, "benchmark_root_env", ("path",))
    candidate_benchmark_env = {benchmark_env: str(benchmark_root)}
    model_path_value = Path(model_path)
    with _temporary_env(candidate_benchmark_env):
        checks = {
            "config": validate_config(),
            "model_runtime_dependencies": validate_model_runtime(model_id),
            "model_explicit_path_validation": _validate_model_explicit_path(model_id, model_path_value),
            "benchmark_inventory_discovery": discover_benchmark_inventory(benchmark_id),
            "benchmark_validation": validate_benchmark(benchmark_id),
        }
    status = _checks_status(checks)
    configured_dir = _configured_model_dir(model_id)
    contract_satisfied = model_path_value.name == configured_dir
    report = {
        "phase": "Phase 5",
        "mode": "explicit_model_path_probe",
        "status": status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "target": {
            "model_id": model_id,
            "benchmark_id": benchmark_id,
        },
        "candidate_model_path": str(model_path_value),
        "candidate_benchmark_env": candidate_benchmark_env,
        "configured_root_contract": {
            "model_dir": configured_dir,
            "satisfied": contract_satisfied,
            "message": (
                "Candidate path matches the configured model directory name."
                if contract_satisfied
                else "Candidate path is an explicit model path and does not satisfy the configured root/subdirectory contract."
            ),
        },
        "requires_human_approval": not contract_satisfied,
        "checks": checks,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _explicit_model_path_next_actions(status, checks, contract_satisfied),
    }
    if output is not None:
        write_json(Path(output), report)
    return report


def build_phase5_model_path_decision_request(
    *,
    model_id: str,
    benchmark_id: str,
    model_path: str | Path,
    benchmark_root: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    probe = build_phase5_explicit_model_path_probe(
        model_id=model_id,
        benchmark_id=benchmark_id,
        model_path=model_path,
        benchmark_root=benchmark_root,
    )
    bundle = {
        "phase": "Phase 5",
        "mode": "model_path_decision_request",
        "status": "needs_attention",
        "approval_status": "pending",
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "target": {
            "model_id": model_id,
            "benchmark_id": benchmark_id,
            "model_path": str(Path(model_path)),
            "benchmark_root": str(Path(benchmark_root)),
        },
        "probe": probe,
        "requested_decision": {
            "question": "Approve this exact model path as the Phase 5 Qwen3-VL path, reject it, or provide the base model root.",
            "allowed_decisions": [
                "approve_variant_path",
                "reject_variant_path",
                "provide_base_model_root",
            ],
            "approval_record_template": {
                "decision": None,
                "approver": None,
                "approved_model_path": str(Path(model_path)),
                "approved_benchmark_root": str(Path(benchmark_root)),
                "rationale": None,
            },
            "decision_record_templates": _model_path_decision_record_templates(
                model_path=Path(model_path),
                benchmark_root=Path(benchmark_root),
            ),
        },
        "safety_flags": dict(SAFETY_FLAGS),
        "do_not_continue_reason": (
            "Human approval is pending for a non-contract model path."
            if probe.get("requires_human_approval")
            else "Human review is pending before this model path is used for execution."
        ),
        "next_actions": [
            "Review the exact model-path probe and decide whether this path is an approved Phase 5 target.",
            "Do not open process submission or run the real smoke until the decision is recorded and config representation is reviewed.",
        ],
    }
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    write_json(output_path / "phase5_model_path_decision_request.json", bundle)
    write_text(output_path / "phase5_model_path_decision_request.md", _model_path_decision_request_markdown(bundle))
    return bundle


def validate_phase5_model_path_decision(
    *,
    request_path: str | Path,
    decision_record_path: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    request_file = Path(request_path)
    decision_file = Path(decision_record_path)
    request = json.loads(request_file.read_text(encoding="utf-8"))
    decision_record = json.loads(decision_file.read_text(encoding="utf-8"))
    target = request.get("target", {})
    probe = request.get("probe", {})
    requested_decision = request.get("requested_decision", {})
    allowed_decisions = requested_decision.get("allowed_decisions", [])
    decision = str(decision_record.get("decision", ""))
    checks = _decision_validation_checks(
        request=request,
        decision_record=decision_record,
        target=target,
        probe=probe,
        allowed_decisions=allowed_decisions,
        decision=decision,
    )
    status = _decision_validation_status(checks, decision)
    approval_status = _decision_approval_status(status, decision)
    report = {
        "phase": "Phase 5",
        "mode": "model_path_decision_validation",
        "status": status,
        "approval_status": approval_status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "request_path": str(request_file),
        "decision_record_path": str(decision_file),
        "target": {
            "model_id": target.get("model_id"),
            "benchmark_id": target.get("benchmark_id"),
            "model_path": target.get("model_path"),
            "benchmark_root": target.get("benchmark_root"),
        },
        "decision": decision_record,
        "checks": checks,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _decision_validation_next_actions(status, decision),
        "do_not_continue_reason": _decision_validation_stop_reason(status, decision),
    }
    if output is not None:
        write_json(Path(output), report)
    return report


def inspect_phase5_model_path_decision_records(
    *,
    request_path: str | Path,
    records_dir: str | Path,
    audit_path: str | Path | None = None,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    request_file = Path(request_path)
    records_path = Path(records_dir)
    request = json.loads(request_file.read_text(encoding="utf-8"))
    target = request.get("target", {})
    probe = request.get("probe", {})
    requested_decision = request.get("requested_decision", {})
    allowed_decisions = requested_decision.get("allowed_decisions", [])
    records = [
        _inspect_phase5_decision_record(path, request, target, probe, allowed_decisions)
        for path in sorted(records_path.glob("*.json"))
        if path.is_file()
    ]
    filled_candidates = [record for record in records if record.get("classification") == "filled_candidate"]
    template_unfilled = [record for record in records if record.get("classification") == "template_unfilled"]
    invalid_candidates = [record for record in records if record.get("classification") == "invalid_candidate"]
    filled_candidate_decision_counts = _decision_record_counts(filled_candidates)
    ambiguous_decisions = sorted(
        decision for decision, count in filled_candidate_decision_counts.items() if count > 1
    )
    gate_audit_verification = verify_phase5_gate_audit_package(audit_path=audit_path) if audit_path is not None else None
    gate_audit_check = _decision_record_gate_audit_check(gate_audit_verification, request_file)
    ready_for_decision_validation = (
        len(filled_candidates) == 1
        and not invalid_candidates
        and gate_audit_check["ready_for_decision_validation"]
    )
    if gate_audit_check["status"] == "failed" or invalid_candidates or len(filled_candidates) > 1:
        status = "failed"
    elif ready_for_decision_validation:
        status = "passed"
    else:
        status = "needs_attention"
    selected_path = filled_candidates[0]["path"] if ready_for_decision_validation else None
    report = {
        "phase": "Phase 5",
        "mode": "model_path_decision_record_status",
        "status": status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "request_path": str(request_file),
        "records_dir": str(records_path),
        "allowed_decisions": allowed_decisions if isinstance(allowed_decisions, list) else [],
        "record_count": len(records),
        "filled_candidate_count": len(filled_candidates),
        "template_unfilled_count": len(template_unfilled),
        "invalid_candidate_count": len(invalid_candidates),
        "filled_candidate_decision_counts": filled_candidate_decision_counts,
        "ambiguous_decisions": ambiguous_decisions,
        "gate_audit_path": str(Path(audit_path)) if audit_path is not None else None,
        "gate_audit_verification_status": gate_audit_check["verification_status"],
        "gate_audit_next_missing_gate": gate_audit_check["next_missing_gate"],
        "gate_audit_ready_for_decision_validation": gate_audit_check["ready_for_decision_validation"],
        "gate_audit_verification": gate_audit_verification,
        "ready_for_decision_validation": ready_for_decision_validation,
        "ready_for_real_smoke": False,
        "write_config": False,
        "exports_applied": False,
        "selected_decision_record_path": selected_path,
        "records": records,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _decision_record_status_next_actions(status, filled_candidates, invalid_candidates, gate_audit_check),
        "do_not_continue_reason": _decision_record_status_stop_reason(status, filled_candidates, invalid_candidates, gate_audit_check),
    }
    if output is not None:
        write_json(Path(output), report)
    if output_dir is not None:
        _write_decision_record_status_package(Path(output_dir), report)
    return report


def build_phase5_approved_decision_readiness(
    *,
    decision_validation_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    validation_file = Path(decision_validation_path)
    validation_report = json.loads(validation_file.read_text(encoding="utf-8"))
    checks = _approved_decision_readiness_checks(validation_report)
    status = "failed" if any(check.get("status") == "failed" for check in checks.values()) else "needs_attention"
    target = validation_report.get("target", {})
    decision = validation_report.get("decision", {})
    bundle = {
        "phase": "Phase 5",
        "mode": "approved_model_path_readiness",
        "status": status,
        "approval_status": validation_report.get("approval_status", "unknown"),
        "ready_for_real_smoke": False,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "decision_validation_path": str(validation_file),
        "target": {
            "model_id": target.get("model_id"),
            "benchmark_id": target.get("benchmark_id"),
        },
        "approved_paths": {
            "model_path": decision.get("approved_model_path") or target.get("model_path"),
            "benchmark_root": decision.get("approved_benchmark_root") or target.get("benchmark_root"),
        },
        "decision_validation": validation_report,
        "checks": checks,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _approved_decision_readiness_next_actions(status),
        "do_not_continue_reason": _approved_decision_readiness_stop_reason(status),
    }
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    write_json(output_path / "phase5_approved_decision_readiness.json", bundle)
    write_text(output_path / "phase5_approved_decision_readiness.md", _approved_decision_readiness_markdown(bundle))
    return bundle


def build_phase5_config_representation_proposal(
    *,
    approved_readiness_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    readiness_file = Path(approved_readiness_path)
    readiness = json.loads(readiness_file.read_text(encoding="utf-8"))
    target = readiness.get("target", {})
    approved_paths = readiness.get("approved_paths", {})
    model_id = str(target.get("model_id", ""))
    benchmark_id = str(target.get("benchmark_id", ""))
    model_path = str(approved_paths.get("model_path", ""))
    benchmark_root = str(approved_paths.get("benchmark_root", ""))
    checks = _config_representation_checks(readiness, model_id, benchmark_id, model_path, benchmark_root)
    status = "failed" if any(check.get("status") == "failed" for check in checks.values()) else "needs_attention"
    representation_options = _config_representation_options(model_id, model_path)
    bundle = {
        "phase": "Phase 5",
        "mode": "config_representation_proposal",
        "status": status,
        "approval_status": readiness.get("approval_status", "unknown"),
        "ready_for_real_smoke": False,
        "write_config": False,
        "exports_applied": False,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "approved_readiness_path": str(readiness_file),
        "target": {
            "model_id": model_id,
            "benchmark_id": benchmark_id,
        },
        "approved_paths": {
            "model_path": model_path,
            "benchmark_root": benchmark_root,
        },
        "proposed_env": _config_representation_env(model_id, benchmark_id, model_path, benchmark_root),
        "representation_options": representation_options,
        "decision_record_templates": _config_representation_decision_templates(
            representation_options=representation_options,
            benchmark_root=benchmark_root,
        ),
        "checks": checks,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _config_representation_next_actions(status),
        "do_not_continue_reason": _config_representation_stop_reason(status),
    }
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    write_json(output_path / "phase5_config_representation_proposal.json", bundle)
    write_text(output_path / "phase5_config_representation_proposal.md", _config_representation_markdown(bundle))
    return bundle


def validate_phase5_config_representation_decision(
    *,
    proposal_path: str | Path,
    decision_record_path: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    proposal_file = Path(proposal_path)
    decision_file = Path(decision_record_path)
    proposal = json.loads(proposal_file.read_text(encoding="utf-8"))
    decision_record = json.loads(decision_file.read_text(encoding="utf-8"))
    selected_name = str(decision_record.get("selected_option", ""))
    selected_option = _find_representation_option(proposal.get("representation_options", []), selected_name)
    checks = _config_representation_decision_checks(
        proposal=proposal,
        decision_record=decision_record,
        selected_option=selected_option,
    )
    status = "failed" if any(check.get("status") == "failed" for check in checks.values()) else "passed"
    report = {
        "phase": "Phase 5",
        "mode": "config_representation_decision_validation",
        "status": status,
        "config_review_status": "approved" if status == "passed" else "invalid",
        "ready_for_real_smoke": False,
        "write_config": False,
        "exports_applied": False,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "proposal_path": str(proposal_file),
        "decision_record_path": str(decision_file),
        "target": proposal.get("target", {}),
        "approved_paths": proposal.get("approved_paths", {}),
        "selected_option": selected_option if selected_option is not None else {"name": selected_name},
        "decision": decision_record,
        "checks": checks,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _config_representation_decision_next_actions(status),
        "do_not_continue_reason": _config_representation_decision_stop_reason(status),
    }
    if output is not None:
        write_json(Path(output), report)
    return report


def build_phase5_gate_audit(
    *,
    model_id: str,
    benchmark_id: str,
    limit: int,
    instrumentation_mode: str,
    decision_request_path: str | Path | None = None,
    decision_validation_path: str | Path | None = None,
    approved_readiness_path: str | Path | None = None,
    config_proposal_path: str | Path | None = None,
    config_decision_validation_path: str | Path | None = None,
    readiness_path: str | Path | None = None,
    smoke_run_id: str | None = None,
    runs_root: str | Path = Path("runs"),
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    target = {
        "model_id": model_id,
        "benchmark_id": benchmark_id,
        "limit": limit,
        "instrumentation_mode": instrumentation_mode,
    }
    gate_checks = {
        "model_path_decision_request": _audit_artifact_gate(
            decision_request_path,
            lambda report: _audit_model_path_decision_request(report, target),
            "Phase 5 model-path decision request was not provided.",
        ),
        "model_path_decision_validation": _audit_artifact_gate(
            decision_validation_path,
            lambda report: _audit_model_path_decision_validation(report, target),
            "Phase 5 model-path decision validation was not provided.",
        ),
        "approved_decision_readiness": _audit_artifact_gate(
            approved_readiness_path,
            lambda report: _audit_approved_decision_readiness(report, target),
            "Phase 5 approved-decision readiness bundle was not provided.",
        ),
        "config_representation_proposal": _audit_artifact_gate(
            config_proposal_path,
            lambda report: _audit_config_representation_proposal(report, target),
            "Phase 5 config representation proposal was not provided.",
        ),
        "config_representation_decision": _audit_artifact_gate(
            config_decision_validation_path,
            lambda report: _audit_config_representation_decision(report, target),
            "Phase 5 config representation decision validation was not provided.",
        ),
        "phase5_readiness": _audit_artifact_gate(
            readiness_path,
            lambda report: _audit_phase5_readiness(report, target),
            "Phase 5 readiness bundle was not provided.",
        ),
        "real_smoke_result": _audit_real_smoke_result(
            smoke_run_id=smoke_run_id,
            runs_root=runs_root,
            target=target,
        ),
    }
    next_missing_gate = _next_incomplete_gate(gate_checks)
    terminal_outcome = _gate_audit_terminal_outcome(gate_checks)
    status = _gate_audit_status(gate_checks, terminal_outcome)
    report = {
        "phase": "Phase 5",
        "mode": "gate_audit",
        "status": status,
        "phase5_terminal_outcome": terminal_outcome,
        "ready_for_real_smoke": False,
        "write_config": False,
        "exports_applied": False,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "target": target,
        "source_artifacts": _gate_audit_source_artifacts(
            {
                "model_path_decision_request": decision_request_path,
                "model_path_decision_validation": decision_validation_path,
                "approved_decision_readiness": approved_readiness_path,
                "config_representation_proposal": config_proposal_path,
                "config_representation_decision": config_decision_validation_path,
                "phase5_readiness": readiness_path,
            }
        ),
        "gate_checks": gate_checks,
        "next_missing_gate": next_missing_gate,
        "safety_flags": dict(SAFETY_FLAGS),
        "next_actions": _gate_audit_next_actions(next_missing_gate, status, terminal_outcome),
        "next_action_packet": _gate_audit_next_action_packet(
            next_missing_gate=next_missing_gate,
            status=status,
            terminal_outcome=terminal_outcome,
            target=target,
        ),
        "do_not_continue_reason": _gate_audit_stop_reason(next_missing_gate, status, terminal_outcome),
    }
    if output is not None:
        write_json(Path(output), report)
    if output_dir is not None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        write_json(output_path / "phase5_gate_audit.json", report)
        write_text(output_path / "phase5_gate_audit.md", _gate_audit_markdown(report))
    return report


def verify_phase5_gate_audit_package(
    *,
    audit_path: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(audit_path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    audit = loaded if isinstance(loaded, dict) else {}
    source_artifact_checks = _verify_gate_audit_source_artifacts(audit.get("source_artifacts", {}))
    markdown_sidecar_check = _verify_gate_audit_markdown_sidecar(path, audit)
    checks = {
        "audit_identity": _verify_gate_audit_identity(audit),
        "non_executing_safety": _verify_gate_audit_non_executing_safety(audit),
        "next_action_packet": _verify_gate_audit_next_action_packet(audit.get("next_action_packet")),
        "source_artifacts": _verify_gate_audit_source_artifact_status(source_artifact_checks),
        "markdown_sidecar": markdown_sidecar_check,
    }
    status = _checks_status(checks)
    report = {
        "phase": "Phase 5",
        "mode": "gate_audit_verification",
        "status": status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "audit_path": str(path),
        "audit_status": audit.get("status"),
        "next_missing_gate": audit.get("next_missing_gate"),
        "ready_for_real_smoke": audit.get("ready_for_real_smoke"),
        "write_config": audit.get("write_config"),
        "exports_applied": audit.get("exports_applied"),
        "safety_flags": audit.get("safety_flags") if isinstance(audit.get("safety_flags"), dict) else {},
        "source_artifact_count": len(source_artifact_checks),
        "checks": checks,
        "source_artifacts": source_artifact_checks,
        "markdown_sidecar": markdown_sidecar_check,
        "next_actions": _verify_gate_audit_next_actions(status),
        "do_not_continue_reason": _verify_gate_audit_stop_reason(status, checks),
    }
    if output is not None:
        write_json(Path(output), report)
    return report


def verify_phase5_decision_record_status_package(
    *,
    status_path: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(status_path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    status_report = loaded if isinstance(loaded, dict) else {}
    source_path_checks = _verify_decision_record_status_source_paths(status_report)
    gate_audit_verification = _verify_decision_record_status_gate_audit(status_report)
    markdown_sidecar_check = _verify_decision_record_status_markdown_sidecar(path, status_report)
    checks = {
        "status_identity": _verify_decision_record_status_identity(status_report),
        "non_executing_safety": _verify_decision_record_status_non_executing_safety(status_report),
        "source_paths": _verify_decision_record_status_source_path_status(source_path_checks),
        "gate_audit_verification": _verify_decision_record_status_gate_audit_status(gate_audit_verification),
        "markdown_sidecar": markdown_sidecar_check,
    }
    status = _checks_status(checks)
    report = {
        "phase": "Phase 5",
        "mode": "decision_record_status_verification",
        "status": status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "status_report_path": str(path),
        "status_report_status": status_report.get("status"),
        "ready_for_decision_validation": status_report.get("ready_for_decision_validation"),
        "ready_for_real_smoke": status_report.get("ready_for_real_smoke"),
        "write_config": status_report.get("write_config"),
        "exports_applied": status_report.get("exports_applied"),
        "safety_flags": status_report.get("safety_flags") if isinstance(status_report.get("safety_flags"), dict) else {},
        "record_count": len(status_report.get("records", [])) if isinstance(status_report.get("records"), list) else 0,
        "checks": checks,
        "source_paths": source_path_checks,
        "gate_audit_verification": gate_audit_verification,
        "markdown_sidecar": markdown_sidecar_check,
        "next_actions": _verify_decision_record_status_next_actions(status),
        "do_not_continue_reason": _verify_decision_record_status_stop_reason(status, checks),
    }
    if output is not None:
        write_json(Path(output), report)
    return report


def _readiness_status(checks: dict[str, dict[str, Any]], execution_authorization: dict[str, Any]) -> str:
    statuses = [str(check.get("status")) for check in checks.values()]
    execution_status = str(execution_authorization.get("status"))
    if "failed" in statuses or execution_status == "failed":
        return "failed"
    if all(status == "passed" for status in statuses) and execution_status == "passed":
        return "passed"
    return "needs_attention"


def _checks_status(checks: dict[str, dict[str, Any]]) -> str:
    statuses = [str(check.get("status")) for check in checks.values()]
    if "failed" in statuses:
        return "failed"
    if all(status == "passed" for status in statuses):
        return "passed"
    return "needs_attention"


def _decision_validation_checks(
    *,
    request: dict[str, Any],
    decision_record: dict[str, Any],
    target: dict[str, Any],
    probe: dict[str, Any],
    allowed_decisions: Any,
    decision: str,
) -> dict[str, dict[str, Any]]:
    allowed = allowed_decisions if isinstance(allowed_decisions, list) else []
    checks: dict[str, dict[str, Any]] = {
        "request_mode": _check(
            request.get("mode") == "model_path_decision_request",
            "Request is a Phase 5 model-path decision request.",
        ),
        "request_pending": _check(
            request.get("approval_status") == "pending",
            "Request is still pending human decision.",
        ),
        "decision_allowed": _check(
            decision in allowed,
            "Decision is one of the options declared by the request.",
        ),
        "approver_present": _check(
            _has_text(decision_record.get("approver")),
            "Decision record names a human approver.",
        ),
        "rationale_present": _check(
            _has_text(decision_record.get("rationale")),
            "Decision record includes a rationale.",
        ),
    }
    if decision == "approve_variant_path":
        checks.update(
            {
                "probe_passed": _check(
                    probe.get("status") == "passed",
                    "Approval can only reference a passed explicit model-path probe.",
                ),
                "approved_model_path_matches": _check(
                    decision_record.get("approved_model_path") == target.get("model_path"),
                    "Approved model path must match the pending request target exactly.",
                ),
                "approved_benchmark_root_matches": _check(
                    decision_record.get("approved_benchmark_root") == target.get("benchmark_root"),
                    "Approved benchmark root must match the pending request target exactly.",
                ),
            }
        )
    elif decision == "provide_base_model_root":
        checks["provided_model_root_present"] = _check(
            _has_text(decision_record.get("provided_model_root")),
            "A provided base model root is required for this decision.",
        )
    return checks


def _model_path_decision_record_templates(*, model_path: Path, benchmark_root: Path) -> list[dict[str, Any]]:
    model_path_value = str(model_path)
    benchmark_root_value = str(benchmark_root)
    return [
        {
            "decision": "approve_variant_path",
            "approver": None,
            "approved_model_path": model_path_value,
            "approved_benchmark_root": benchmark_root_value,
            "rationale": None,
        },
        {
            "decision": "reject_variant_path",
            "approver": None,
            "rejected_model_path": model_path_value,
            "approved_model_path": None,
            "approved_benchmark_root": None,
            "rationale": None,
        },
        {
            "decision": "provide_base_model_root",
            "approver": None,
            "provided_model_root": None,
            "approved_benchmark_root": benchmark_root_value,
            "rationale": None,
        },
    ]


def _check(passed: bool, summary: str) -> dict[str, str]:
    return {"status": "passed" if passed else "failed", "summary": summary}


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _decision_validation_status(checks: dict[str, dict[str, Any]], decision: str) -> str:
    if any(check.get("status") == "failed" for check in checks.values()):
        return "failed"
    if decision == "approve_variant_path":
        return "passed"
    return "needs_attention"


def _decision_approval_status(status: str, decision: str) -> str:
    if status == "failed":
        return "invalid"
    if decision == "approve_variant_path":
        return "approved"
    if decision == "reject_variant_path":
        return "rejected"
    if decision == "provide_base_model_root":
        return "base_model_root_provided"
    return "pending"


def _inspect_phase5_decision_record(
    path: Path,
    request: dict[str, Any],
    target: dict[str, Any],
    probe: dict[str, Any],
    allowed_decisions: Any,
) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "path": str(path),
            "status": "failed",
            "classification": "invalid_candidate",
            "summary": f"Decision record could not be parsed as JSON: {exc}",
        }
    if not isinstance(loaded, dict):
        return {
            "path": str(path),
            "status": "failed",
            "classification": "invalid_candidate",
            "summary": "Decision record must be a JSON object.",
        }
    decision = str(loaded.get("decision", ""))
    checks = _decision_validation_checks(
        request=request,
        decision_record=loaded,
        target=target,
        probe=probe,
        allowed_decisions=allowed_decisions,
        decision=decision,
    )
    failed_checks = [name for name, check in checks.items() if check.get("status") == "failed"]
    validation_status = _decision_validation_status(checks, decision)
    approval_status = _decision_approval_status(validation_status, decision)
    if path.name.endswith(".template.json") and {"approver_present", "rationale_present"}.intersection(failed_checks):
        classification = "template_unfilled"
        status = "needs_attention"
        summary = "Decision record template is still unfilled."
    elif failed_checks:
        classification = "invalid_candidate"
        status = "failed"
        summary = f"Decision record failed checks: {', '.join(failed_checks)}."
    else:
        classification = "filled_candidate"
        status = validation_status
        summary = "Decision record is ready for phase5-validate-model-path-decision."
    return {
        "path": str(path),
        "status": status,
        "classification": classification,
        "decision": decision,
        "decision_validation_status": validation_status,
        "approval_status": approval_status,
        "checks": checks,
        "summary": summary,
    }


def _decision_record_gate_audit_check(
    gate_audit_verification: dict[str, Any] | None,
    request_file: Path,
) -> dict[str, Any]:
    if gate_audit_verification is None:
        return {
            "status": "not_provided",
            "verification_status": "not_provided",
            "next_missing_gate": None,
            "ready_for_decision_validation": True,
            "summary": "No gate audit was supplied; preserving legacy decision-record status behavior.",
        }
    verification_status = str(gate_audit_verification.get("status"))
    next_missing_gate = gate_audit_verification.get("next_missing_gate")
    source_artifacts = gate_audit_verification.get("source_artifacts", {})
    model_path_request = source_artifacts.get("model_path_decision_request", {}) if isinstance(source_artifacts, dict) else {}
    recorded_request_path = model_path_request.get("path") if isinstance(model_path_request, dict) else None
    path_matches = False
    if _has_text(recorded_request_path):
        path_matches = Path(str(recorded_request_path)).resolve() == request_file.resolve()
    ready = verification_status == "passed" and next_missing_gate == "model_path_decision_validation" and path_matches
    failed_reasons = []
    if verification_status != "passed":
        failed_reasons.append("gate audit verification did not pass")
    if next_missing_gate != "model_path_decision_validation":
        failed_reasons.append("gate audit does not point to model_path_decision_validation")
    if not path_matches:
        failed_reasons.append("gate audit source request does not match the requested decision packet")
    return {
        "status": "passed" if ready else "failed",
        "verification_status": verification_status,
        "next_missing_gate": next_missing_gate,
        "ready_for_decision_validation": ready,
        "summary": "Gate audit is current for model-path decision validation." if ready else "; ".join(failed_reasons),
    }


def _decision_record_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        decision = str(record.get("decision", "")).strip()
        if not decision:
            continue
        counts[decision] = counts.get(decision, 0) + 1
    return dict(sorted(counts.items()))


def _decision_record_status_next_actions(
    status: str,
    filled_candidates: list[dict[str, Any]],
    invalid_candidates: list[dict[str, Any]],
    gate_audit_check: dict[str, Any],
) -> list[str]:
    if gate_audit_check["status"] == "failed":
        return [
            "Regenerate or repair the Phase 5 gate audit package before using this decision record for human action.",
            "Do not run phase5-validate-model-path-decision until the audit package verifies as current.",
        ]
    if invalid_candidates:
        return ["Fix or remove invalid decision record candidates before validating the Phase 5 model-path decision."]
    if len(filled_candidates) == 1:
        return [
            (
                "Run python -m stable_core.cli phase5-validate-model-path-decision "
                "--request <phase5_model_path_decision_request.json> "
                f"--decision-record {filled_candidates[0]['path']} "
                "--output <phase5_model_path_decision_validation.json>"
            ),
            "Do not edit config, export env vars, or run the real smoke from this status report.",
        ]
    if len(filled_candidates) > 1:
        return ["Keep exactly one filled decision record before running phase5-validate-model-path-decision."]
    return ["Fill exactly one copied decision record template before running phase5-validate-model-path-decision."]


def _decision_record_status_stop_reason(
    status: str,
    filled_candidates: list[dict[str, Any]],
    invalid_candidates: list[dict[str, Any]],
    gate_audit_check: dict[str, Any],
) -> str:
    if status == "passed":
        return "Exactly one filled decision record is ready for non-executing validation."
    if gate_audit_check["status"] == "failed":
        return f"The Phase 5 gate audit is not current for this decision handoff: {gate_audit_check['summary']}."
    if invalid_candidates:
        return "At least one decision record candidate is invalid."
    if len(filled_candidates) > 1:
        return "More than one filled decision record candidate was found."
    return "No filled Phase 5 model-path decision record was found."


def _decision_validation_next_actions(status: str, decision: str) -> list[str]:
    if status == "failed":
        return ["Fix the decision record and rerun the validation command before changing config or execution gates."]
    if decision == "approve_variant_path":
        return [
            "Review the config representation for the approved exact path before any real smoke attempt.",
            "Keep remote execution and process submission closed until readiness is rerun with the approved representation.",
        ]
    if decision == "reject_variant_path":
        return ["Choose a different exact model path or provide a base model root that satisfies the configured contract."]
    if decision == "provide_base_model_root":
        return ["Probe the provided base model root with phase5-probe-paths before exporting env vars or editing config."]
    return ["Record a valid Phase 5 model-path decision before continuing."]


def _decision_validation_stop_reason(status: str, decision: str) -> str | None:
    if status == "failed":
        return "The model-path decision record is invalid."
    if decision == "approve_variant_path":
        return None
    return "A valid approval for an executable Phase 5 model path has not been recorded."


def _approved_decision_readiness_checks(validation_report: dict[str, Any]) -> dict[str, dict[str, str]]:
    decision = validation_report.get("decision", {})
    return {
        "decision_validation": _check(
            validation_report.get("mode") == "model_path_decision_validation"
            and validation_report.get("status") == "passed",
            "Decision validation report must be a passed Phase 5 model-path decision validation.",
        ),
        "approval_status": _check(
            validation_report.get("approval_status") == "approved",
            "Decision validation must record approval_status approved.",
        ),
        "decision_type": _check(
            decision.get("decision") == "approve_variant_path",
            "Readiness can only be prepared for an approved exact variant path.",
        ),
        "approved_model_path_present": _check(
            _has_text(decision.get("approved_model_path")),
            "Approved model path must be present.",
        ),
        "approved_benchmark_root_present": _check(
            _has_text(decision.get("approved_benchmark_root")),
            "Approved benchmark root must be present.",
        ),
    }


def _approved_decision_readiness_next_actions(status: str) -> list[str]:
    if status == "failed":
        return ["Fix or regenerate the decision validation report before preparing Phase 5 path readiness."]
    return [
        "Review how the approved exact model path will be represented before changing config.",
        "Rerun safe path probes and phase5-readiness after config representation is reviewed.",
        "Open remote, GPU, and process-submission gates only after readiness and config review pass.",
    ]


def _approved_decision_readiness_stop_reason(status: str) -> str:
    if status == "failed":
        return "The approved-decision readiness bundle could not validate the human decision report."
    return "The approved path still needs config representation review and gated readiness before any real smoke."


def _config_representation_checks(
    readiness: dict[str, Any],
    model_id: str,
    benchmark_id: str,
    model_path: str,
    benchmark_root: str,
) -> dict[str, dict[str, str]]:
    model_configured_dir = _configured_model_dir(model_id)
    model_contract_satisfied = bool(model_path) and model_configured_dir is not None and Path(model_path).name == model_configured_dir
    return {
        "approved_readiness": _check(
            readiness.get("mode") == "approved_model_path_readiness"
            and readiness.get("approval_status") == "approved"
            and readiness.get("status") == "needs_attention",
            "Approved readiness bundle must be valid and still non-executing.",
        ),
        "approved_model_path_present": _check(
            bool(model_path),
            "Approved model path must be present before proposing config representation.",
        ),
        "approved_benchmark_root_present": _check(
            bool(benchmark_root),
            "Approved benchmark root must be present before proposing config representation.",
        ),
        "model_configured_root_contract": {
            "status": "passed" if model_contract_satisfied else "needs_review",
            "summary": (
                "Approved model path already satisfies the configured root/subdirectory contract."
                if model_contract_satisfied
                else "Approved model path does not satisfy the current configured root/subdirectory contract."
            ),
        },
        "benchmark_configured_root_contract": _check(
            bool(benchmark_id) and bool(benchmark_root),
            "Benchmark root can be represented through the configured benchmark root environment variable.",
        ),
    }


def _config_representation_env(
    model_id: str,
    benchmark_id: str,
    model_path: str,
    benchmark_root: str,
) -> dict[str, dict[str, str]]:
    proposed: dict[str, dict[str, str]] = {"model": {}, "benchmark": {}}
    model_configured_dir = _configured_model_dir(model_id)
    if model_path and model_configured_dir and Path(model_path).name == model_configured_dir:
        proposed["model"][_configured_root_env("models.yaml", "models", model_id, "model_root_env", ("local_path", "path"))] = str(Path(model_path).parent)
    if benchmark_root:
        proposed["benchmark"][_configured_root_env("benchmarks.yaml", "benchmarks", benchmark_id, "benchmark_root_env", ("path",))] = benchmark_root
    return proposed


def _config_representation_options(model_id: str, model_path: str) -> list[dict[str, Any]]:
    configured_dir = _configured_model_dir(model_id)
    options: list[dict[str, Any]] = []
    if model_path and configured_dir and Path(model_path).name == configured_dir:
        options.append(
            {
                "name": "configured_root_env",
                "requires_config_review": False,
                "summary": "Use the existing configured root environment variable contract.",
                "proposed_models_yaml": {
                    "local_path": f"${{{_configured_root_env('models.yaml', 'models', model_id, 'model_root_env', ('local_path', 'path'))}}}/{configured_dir}",
                },
            }
        )
    if model_path:
        options.append(
            {
                "name": "explicit_local_path_override",
                "requires_config_review": True,
                "summary": "Represent the approved exact model path directly in model config after review.",
                "proposed_models_yaml": {
                    "local_path": model_path,
                },
            }
        )
    if configured_dir:
        options.append(
            {
                "name": "materialize_under_configured_root",
                "requires_config_review": True,
                "summary": "Place or link the approved model under a reviewed root using the configured model directory name.",
                "proposed_models_yaml": {
                    "local_path": f"${{{_configured_root_env('models.yaml', 'models', model_id, 'model_root_env', ('local_path', 'path'))}}}/{configured_dir}",
                },
            }
        )
    return options


def _config_representation_decision_templates(
    *,
    representation_options: list[dict[str, Any]],
    benchmark_root: str,
) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    for option in representation_options:
        proposed_models_yaml = option.get("proposed_models_yaml", {})
        local_path = ""
        if isinstance(proposed_models_yaml, dict):
            local_path = str(proposed_models_yaml.get("local_path", ""))
        templates.append(
            {
                "selected_option": option.get("name"),
                "reviewer": None,
                "approved_model_path": local_path or None,
                "approved_benchmark_root": benchmark_root or None,
                "approved_models_yaml": dict(proposed_models_yaml) if isinstance(proposed_models_yaml, dict) else {},
                "approved_env": {"REMOTE_BENCHMARK_ROOT": benchmark_root} if benchmark_root else {},
                "rationale": None,
            }
        )
    return templates


def _config_representation_next_actions(status: str) -> list[str]:
    if status == "failed":
        return ["Fix approved readiness inputs before reviewing config representation."]
    return [
        "Choose one representation option and review it before editing project_config.",
        "After config representation review, rerun phase5-probe-paths or phase5-probe-explicit-model-path as appropriate.",
        "Rerun phase5-readiness and keep process submission closed until all gates pass.",
    ]


def _config_representation_stop_reason(status: str) -> str:
    if status == "failed":
        return "Config representation proposal could not validate the approved readiness bundle."
    return "Config representation is proposed for review only; no config or execution gate has changed."


def _find_representation_option(options: Any, selected_name: str) -> dict[str, Any] | None:
    if not isinstance(options, list):
        return None
    for option in options:
        if isinstance(option, dict) and option.get("name") == selected_name:
            return option
    return None


def _config_representation_decision_checks(
    *,
    proposal: dict[str, Any],
    decision_record: dict[str, Any],
    selected_option: dict[str, Any] | None,
) -> dict[str, dict[str, str]]:
    selected_name = str(decision_record.get("selected_option", ""))
    expected_model_path = _selected_option_model_path(selected_option)
    expected_benchmark_root = str(proposal.get("approved_paths", {}).get("benchmark_root", ""))
    approved_model_path = _decision_approved_model_path(decision_record)
    approved_benchmark_root = _decision_approved_benchmark_root(decision_record)
    checks = {
        "proposal_mode": _check(
            proposal.get("mode") == "config_representation_proposal",
            "Proposal is a Phase 5 config representation proposal.",
        ),
        "proposal_status": _check(
            proposal.get("status") == "needs_attention",
            "Proposal must be a review-only needs_attention artifact.",
        ),
        "proposal_non_executing": _check(
            proposal.get("ready_for_real_smoke") is False
            and proposal.get("write_config") is False
            and proposal.get("exports_applied") is False,
            "Proposal must not already mark execution, config writes, or env exports as ready.",
        ),
        "selected_option_declared": _check(
            selected_option is not None,
            "Selected option must be one of the representation options declared by the proposal.",
        ),
        "reviewer_present": _check(
            bool(_decision_reviewer(decision_record)),
            "Decision record names a human reviewer.",
        ),
        "rationale_present": _check(
            _has_text(decision_record.get("rationale")),
            "Decision record includes a rationale.",
        ),
    }
    if selected_option is not None and expected_model_path:
        checks["approved_model_path_matches"] = _check(
            approved_model_path == expected_model_path,
            "Approved model path or models.yaml local_path must match the selected proposal option exactly.",
        )
    if selected_option is not None and expected_benchmark_root:
        checks["approved_benchmark_root_matches"] = _check(
            approved_benchmark_root == expected_benchmark_root,
            "Approved benchmark root must match the proposal exactly.",
        )
    if not selected_name:
        checks["selected_option_present"] = _check(False, "Decision record must name selected_option.")
    return checks


def _selected_option_model_path(selected_option: dict[str, Any] | None) -> str:
    if selected_option is None:
        return ""
    proposed_models_yaml = selected_option.get("proposed_models_yaml", {})
    if isinstance(proposed_models_yaml, dict):
        return str(proposed_models_yaml.get("local_path", ""))
    return ""


def _decision_approved_model_path(decision_record: dict[str, Any]) -> str:
    if decision_record.get("approved_model_path"):
        return str(decision_record.get("approved_model_path"))
    approved_models_yaml = decision_record.get("approved_models_yaml", {})
    if isinstance(approved_models_yaml, dict):
        return str(approved_models_yaml.get("local_path", ""))
    return ""


def _decision_approved_benchmark_root(decision_record: dict[str, Any]) -> str:
    if decision_record.get("approved_benchmark_root"):
        return str(decision_record.get("approved_benchmark_root"))
    approved_env = decision_record.get("approved_env", {})
    if isinstance(approved_env, dict):
        return str(approved_env.get("REMOTE_BENCHMARK_ROOT", ""))
    return ""


def _decision_reviewer(decision_record: dict[str, Any]) -> str:
    return str(decision_record.get("reviewer") or decision_record.get("approver") or "").strip()


def _config_representation_decision_next_actions(status: str) -> list[str]:
    if status == "failed":
        return ["Fix the config representation decision record before editing project_config or exporting env vars."]
    return [
        "Treat the selected representation as reviewed input only; this command did not edit config or export env vars.",
        "After any separate config/env change, rerun safe path probes, phase5-readiness, and validation gates.",
        "Keep remote, GPU, and process-submission gates closed until the full Phase 5 readiness gate passes.",
    ]


def _config_representation_decision_stop_reason(status: str) -> str:
    if status == "failed":
        return "The config representation decision record is invalid."
    return "Config representation review is validated, but no config, env, or execution gate has changed."


def _audit_artifact_gate(
    artifact_path: str | Path | None,
    validator: Any,
    missing_summary: str,
) -> dict[str, Any]:
    if artifact_path is None:
        return {"status": "missing", "path": None, "summary": missing_summary}
    path = Path(artifact_path)
    if not path.exists():
        return {"status": "missing", "path": str(path), "summary": "Artifact path does not exist."}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "failed", "path": str(path), "summary": f"Artifact is not valid JSON: {exc}"}
    check = validator(report)
    return {"path": str(path), **check}


def _audit_model_path_decision_request(report: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    return _audit_required_conditions(
        [
            (report.get("mode") == "model_path_decision_request", "Artifact is a model-path decision request."),
            (report.get("approval_status") == "pending", "Decision request remains pending for external review."),
            (_audit_target_matches(report, target), "Artifact target matches the Phase 5 audit target."),
            (_audit_safety_flags_false(report), "Artifact records no execution, raw-output, or config-write side effects."),
        ],
        "Model-path decision request is reviewable.",
    )


def _audit_model_path_decision_validation(report: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    return _audit_required_conditions(
        [
            (report.get("mode") == "model_path_decision_validation", "Artifact is a model-path decision validation."),
            (report.get("status") == "passed", "Model-path decision validation passed."),
            (report.get("approval_status") == "approved", "Model-path decision approval is recorded."),
            (_audit_target_matches(report, target), "Artifact target matches the Phase 5 audit target."),
            (_audit_safety_flags_false(report), "Artifact records no execution, raw-output, or config-write side effects."),
        ],
        "Model-path decision validation is approved.",
    )


def _audit_approved_decision_readiness(report: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    return _audit_required_conditions(
        [
            (report.get("mode") == "approved_model_path_readiness", "Artifact is an approved-decision readiness bundle."),
            (report.get("status") == "needs_attention", "Approved readiness remains non-executing."),
            (report.get("approval_status") == "approved", "Approved readiness references an approved decision."),
            (report.get("ready_for_real_smoke") is False, "Approved readiness does not authorize the real smoke."),
            (_audit_target_matches(report, target), "Artifact target matches the Phase 5 audit target."),
            (_audit_safety_flags_false(report), "Artifact records no execution, raw-output, or config-write side effects."),
        ],
        "Approved-decision readiness is reviewable.",
    )


def _audit_config_representation_proposal(report: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    return _audit_required_conditions(
        [
            (report.get("mode") == "config_representation_proposal", "Artifact is a config representation proposal."),
            (report.get("status") == "needs_attention", "Config representation proposal remains review-only."),
            (report.get("ready_for_real_smoke") is False, "Config representation proposal does not authorize the real smoke."),
            (report.get("write_config") is False, "Config representation proposal did not write config."),
            (report.get("exports_applied") is False, "Config representation proposal did not export environment values."),
            (_audit_target_matches(report, target), "Artifact target matches the Phase 5 audit target."),
            (_audit_safety_flags_false(report), "Artifact records no execution, raw-output, or config-write side effects."),
        ],
        "Config representation proposal is reviewable.",
    )


def _audit_config_representation_decision(report: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    return _audit_required_conditions(
        [
            (report.get("mode") == "config_representation_decision_validation", "Artifact is a config representation decision validation."),
            (report.get("status") == "passed", "Config representation decision validation passed."),
            (report.get("config_review_status") == "approved", "Config representation review is approved."),
            (report.get("ready_for_real_smoke") is False, "Config representation decision does not authorize the real smoke."),
            (report.get("write_config") is False, "Config representation decision did not write config."),
            (report.get("exports_applied") is False, "Config representation decision did not export environment values."),
            (_audit_target_matches(report, target), "Artifact target matches the Phase 5 audit target."),
            (_audit_safety_flags_false(report), "Artifact records no execution, raw-output, or config-write side effects."),
        ],
        "Config representation decision validation is approved.",
    )


def _audit_phase5_readiness(report: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    base_conditions = [
        (report.get("phase") == "Phase 5", "Artifact is a Phase 5 readiness bundle."),
        (_audit_target_matches(report, target, include_limit=True), "Artifact target matches the Phase 5 audit target."),
        (_audit_safety_flags_false(report), "Artifact records no execution, raw-output, or config-write side effects."),
    ]
    base_check = _audit_required_conditions(base_conditions, "Phase 5 readiness target and safety metadata are valid.")
    if base_check["status"] != "passed":
        return base_check
    if report.get("status") == "passed":
        return {"status": "passed", "summary": "Phase 5 readiness passed."}
    if report.get("status") == "failed":
        return {"status": "failed", "summary": "Phase 5 readiness failed."}
    return {"status": "needs_attention", "summary": "Phase 5 readiness has not passed."}


def _audit_real_smoke_result(
    *,
    smoke_run_id: str | None,
    runs_root: str | Path,
    target: dict[str, Any],
) -> dict[str, Any]:
    if smoke_run_id is None:
        return {
            "status": "missing",
            "run_id": None,
            "summary": "Phase 5 real-smoke run id was not provided.",
            "outcome": "none",
        }
    validation = validate_run_artifacts(run_id=smoke_run_id, runs_root=runs_root)
    if validation.get("status") != "passed":
        return {
            "status": "failed",
            "run_id": smoke_run_id,
            "runs_root": str(runs_root),
            "summary": "Real-smoke run artifacts did not pass validation.",
            "run_validation": validation,
            "outcome": "invalid_run_artifacts",
        }
    run_dir = Path(runs_root) / smoke_run_id
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    target_check = _audit_run_manifest_target(manifest, target)
    if target_check["status"] != "passed":
        return {
            "status": "failed",
            "run_id": smoke_run_id,
            "runs_root": str(runs_root),
            "summary": target_check["summary"],
            "run_validation": validation,
            "outcome": "target_mismatch",
            "failed_conditions": target_check.get("failed_conditions", []),
        }
    manifest_status = str(manifest.get("status", ""))
    if manifest_status == "succeeded":
        return {
            "status": "passed",
            "run_id": smoke_run_id,
            "runs_root": str(runs_root),
            "summary": "Phase 5 real-smoke success bundle passed artifact validation.",
            "run_validation": validation,
            "outcome": "validated_real_smoke_success",
        }
    failure = json.loads((run_dir / "failure.json").read_text(encoding="utf-8"))
    failure_type = str(failure.get("failure_type", ""))
    if failure_type == "landmark_worker_execution_failed":
        return {
            "status": "passed",
            "run_id": smoke_run_id,
            "runs_root": str(runs_root),
            "summary": "Phase 5 real-execution failure bundle passed artifact validation.",
            "run_validation": validation,
            "outcome": "reviewed_real_execution_failure",
            "failure_type": failure_type,
        }
    return {
        "status": "needs_attention",
        "run_id": smoke_run_id,
        "runs_root": str(runs_root),
        "summary": f"Run failure_type `{failure_type}` is not a reviewed real-execution failure.",
        "run_validation": validation,
        "outcome": "pre_execution_gate_failure",
        "failure_type": failure_type,
    }


def _audit_run_manifest_target(manifest: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    return _audit_required_conditions(
        [
            (manifest.get("run_type") == "landmark_baseline", "Run manifest is a landmark baseline run."),
            (manifest.get("model_id") == target.get("model_id"), "Run model_id matches the audit target."),
            (manifest.get("benchmark_id") == target.get("benchmark_id"), "Run benchmark_id matches the audit target."),
            (manifest.get("limit") == target.get("limit"), "Run limit matches the audit target."),
            (
                manifest.get("instrumentation_mode") == target.get("instrumentation_mode"),
                "Run instrumentation mode matches the audit target.",
            ),
        ],
        "Run manifest target matches the Phase 5 audit target.",
    )


def _gate_audit_source_artifacts(paths: dict[str, str | Path | None]) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for name, value in paths.items():
        if value is None:
            continue
        path = Path(value)
        artifact: dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
        }
        if path.is_file():
            artifact["sha256"] = sha256_file(path)
        artifacts[name] = artifact
    return artifacts


def _verify_gate_audit_identity(audit: dict[str, Any]) -> dict[str, Any]:
    return _audit_required_conditions(
        [
            (audit.get("phase") == "Phase 5", "Audit package phase is Phase 5."),
            (audit.get("mode") == "gate_audit", "Audit package mode is gate_audit."),
            (_has_text(audit.get("status")), "Audit package records a status."),
        ],
        "Audit package identity is a Phase 5 gate audit.",
    )


def _verify_gate_audit_non_executing_safety(audit: dict[str, Any]) -> dict[str, Any]:
    safety_flags = audit.get("safety_flags")
    conditions = [
        (audit.get("ready_for_real_smoke") is False, "ready_for_real_smoke remains false."),
        (audit.get("write_config") is False, "write_config remains false."),
        (audit.get("exports_applied") is False, "exports_applied remains false."),
        (isinstance(safety_flags, dict), "safety_flags is recorded as an object."),
    ]
    if isinstance(safety_flags, dict):
        conditions.extend(
            (safety_flags.get(name) is False, f"{name} remains false.")
            for name in SAFETY_FLAGS
        )
    return _audit_required_conditions(
        conditions,
        "Gate audit package preserves all non-executing safety flags.",
    )


def _verify_gate_audit_next_action_packet(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return {
            "status": "failed",
            "summary": "next_action_packet must be an object.",
            "failed_conditions": ["next_action_packet must be an object."],
        }
    return _audit_required_conditions(
        [
            (_has_text(packet.get("gate")), "next_action_packet records a gate."),
            (isinstance(packet.get("required_inputs"), list), "required_inputs is a list."),
            (isinstance(packet.get("safe_command_templates"), list), "safe_command_templates is a list."),
            (isinstance(packet.get("expected_artifacts"), list), "expected_artifacts is a list."),
            (isinstance(packet.get("forbidden_actions"), list), "forbidden_actions is a list."),
        ],
        "Gate audit package includes a structured next_action_packet.",
    )


def _verify_gate_audit_source_artifacts(source_artifacts: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, dict):
        return {
            "__source_artifacts__": {
                "status": "failed",
                "summary": "source_artifacts must be an object.",
            }
        }
    checks: dict[str, dict[str, Any]] = {}
    for name, artifact in source_artifacts.items():
        check_name = str(name)
        if not isinstance(artifact, dict):
            checks[check_name] = {
                "status": "failed",
                "summary": "Source artifact entry must be an object.",
            }
            continue
        raw_path = artifact.get("path")
        if not _has_text(raw_path):
            checks[check_name] = {
                "status": "failed",
                "path": raw_path,
                "summary": "Source artifact path is missing.",
            }
            continue
        path = Path(str(raw_path))
        actual_exists = path.exists()
        expected_exists = artifact.get("exists")
        expected_sha256 = artifact.get("sha256")
        actual_sha256 = sha256_file(path) if path.is_file() else None
        check = {
            "path": str(raw_path),
            "expected_exists": expected_exists,
            "actual_exists": actual_exists,
            "expected_sha256": expected_sha256,
            "actual_sha256": actual_sha256,
        }
        if expected_exists is not True:
            checks[check_name] = {
                **check,
                "status": "failed",
                "summary": "Source artifact was not recorded as existing.",
            }
            continue
        if not actual_exists:
            checks[check_name] = {
                **check,
                "status": "failed",
                "summary": "Source artifact path no longer exists.",
            }
            continue
        if expected_sha256 and expected_sha256 != actual_sha256:
            checks[check_name] = {
                **check,
                "status": "failed",
                "summary": "Source artifact sha256 mismatch.",
            }
            continue
        checks[check_name] = {
            **check,
            "status": "passed",
            "summary": "Source artifact matches recorded provenance.",
        }
    return checks


def _verify_gate_audit_source_artifact_status(source_checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    failed = [
        f"{name}: {check.get('summary')}"
        for name, check in source_checks.items()
        if check.get("status") != "passed"
    ]
    if failed:
        return {
            "status": "failed",
            "summary": failed[0],
            "failed_conditions": failed,
        }
    return {
        "status": "passed",
        "summary": "All recorded source artifacts match current files.",
    }


def _verify_decision_record_status_identity(status_report: dict[str, Any]) -> dict[str, Any]:
    return _audit_required_conditions(
        [
            (status_report.get("phase") == "Phase 5", "Status report phase is Phase 5."),
            (
                status_report.get("mode") == "model_path_decision_record_status",
                "Status report mode is model_path_decision_record_status.",
            ),
            (
                status_report.get("status") in {"needs_attention", "passed", "failed"},
                "Status report records a recognized status.",
            ),
        ],
        "Decision-record status package identity is valid.",
    )


def _verify_decision_record_status_non_executing_safety(status_report: dict[str, Any]) -> dict[str, Any]:
    safety_flags = status_report.get("safety_flags")
    conditions = [
        (status_report.get("ready_for_real_smoke") is False, "ready_for_real_smoke remains false."),
        (status_report.get("write_config") is False, "write_config remains false."),
        (status_report.get("exports_applied") is False, "exports_applied remains false."),
        (isinstance(safety_flags, dict), "safety_flags is recorded as an object."),
    ]
    if isinstance(safety_flags, dict):
        conditions.extend(
            (safety_flags.get(name) is False, f"{name} remains false.")
            for name in SAFETY_FLAGS
        )
    return _audit_required_conditions(
        conditions,
        "Decision-record status package preserves all non-executing safety flags.",
    )


def _verify_decision_record_status_source_paths(status_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = status_report.get("records")
    records = records if isinstance(records, list) else []
    checks = {
        "request_path": _verify_existing_file_path(status_report.get("request_path"), "Request path"),
        "records_dir": _verify_existing_dir_path(status_report.get("records_dir"), "Records directory"),
        "record_files": _verify_decision_record_status_record_files(status_report.get("records_dir"), records),
    }
    gate_audit_path = status_report.get("gate_audit_path")
    if _has_text(gate_audit_path):
        checks["gate_audit_path"] = _verify_existing_file_path(gate_audit_path, "Gate audit path")
    return checks


def _verify_existing_file_path(raw_path: Any, label: str) -> dict[str, Any]:
    if not _has_text(raw_path):
        return {
            "status": "failed",
            "path": raw_path,
            "summary": f"{label} is missing.",
        }
    path = Path(str(raw_path))
    return {
        "status": "passed" if path.is_file() else "failed",
        "path": str(raw_path),
        "exists": path.exists(),
        "summary": f"{label} exists." if path.is_file() else f"{label} does not exist as a file.",
    }


def _verify_existing_dir_path(raw_path: Any, label: str) -> dict[str, Any]:
    if not _has_text(raw_path):
        return {
            "status": "failed",
            "path": raw_path,
            "summary": f"{label} is missing.",
        }
    path = Path(str(raw_path))
    return {
        "status": "passed" if path.is_dir() else "failed",
        "path": str(raw_path),
        "exists": path.exists(),
        "summary": f"{label} exists." if path.is_dir() else f"{label} does not exist as a directory.",
    }


def _verify_decision_record_status_record_files(records_dir: Any, records: list[Any]) -> dict[str, Any]:
    recorded_paths = [
        str(record.get("path"))
        for record in records
        if isinstance(record, dict) and _has_text(record.get("path"))
    ]
    recorded_path_set = set(recorded_paths)
    missing_record_paths = sorted(path for path in recorded_path_set if not Path(path).is_file())
    current_path_set: set[str] = set()
    if _has_text(records_dir):
        directory = Path(str(records_dir))
        if directory.is_dir():
            current_path_set = {str(path) for path in sorted(directory.glob("*.json")) if path.is_file()}
    extra_current_paths = sorted(current_path_set - recorded_path_set)
    omitted_current_paths = sorted(recorded_path_set - current_path_set)
    failed_conditions: list[str] = []
    if missing_record_paths:
        failed_conditions.append(f"Recorded decision files are missing: {missing_record_paths}")
    if extra_current_paths:
        failed_conditions.append(f"Records directory contains unreported JSON files: {extra_current_paths}")
    if omitted_current_paths:
        failed_conditions.append(f"Recorded decision files are not present in records_dir: {omitted_current_paths}")
    if failed_conditions:
        return {
            "status": "failed",
            "recorded_paths": recorded_paths,
            "current_paths": sorted(current_path_set),
            "missing_record_paths": missing_record_paths,
            "extra_current_paths": extra_current_paths,
            "omitted_current_paths": omitted_current_paths,
            "summary": failed_conditions[0],
            "failed_conditions": failed_conditions,
        }
    return {
        "status": "passed",
        "recorded_paths": recorded_paths,
        "current_paths": sorted(current_path_set),
        "summary": "Recorded decision files match the current records directory.",
    }


def _verify_decision_record_status_source_path_status(source_checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    failed = [
        f"{name}: {check.get('summary')}"
        for name, check in source_checks.items()
        if check.get("status") != "passed"
    ]
    if failed:
        return {
            "status": "failed",
            "summary": failed[0],
            "failed_conditions": failed,
        }
    return {
        "status": "passed",
        "summary": "Decision-record status source paths match current files.",
    }


def _verify_decision_record_status_gate_audit(status_report: dict[str, Any]) -> dict[str, Any]:
    gate_audit_path = status_report.get("gate_audit_path")
    if not _has_text(gate_audit_path):
        return {
            "status": "passed",
            "verification_status": "not_provided",
            "next_missing_gate": None,
            "ready_for_decision_validation": status_report.get("gate_audit_ready_for_decision_validation"),
            "summary": "No gate audit path was recorded.",
        }
    verification = verify_phase5_gate_audit_package(audit_path=str(gate_audit_path))
    conditions = [
        (
            verification.get("status") == status_report.get("gate_audit_verification_status"),
            "Gate audit verification status matches the recorded status report.",
        ),
        (
            verification.get("next_missing_gate") == status_report.get("gate_audit_next_missing_gate"),
            "Gate audit next missing gate matches the recorded status report.",
        ),
        (
            verification.get("status") == "passed"
            if status_report.get("gate_audit_ready_for_decision_validation") is True
            else True,
            "Gate audit readiness flag is consistent with a passed gate audit.",
        ),
    ]
    consistency = _audit_required_conditions(
        conditions,
        "Gate audit verification matches the recorded decision-record status report.",
    )
    return {
        **verification,
        "status": consistency["status"],
        "summary": consistency["summary"],
        "failed_conditions": consistency.get("failed_conditions", []),
        "recorded_verification_status": status_report.get("gate_audit_verification_status"),
        "recorded_next_missing_gate": status_report.get("gate_audit_next_missing_gate"),
        "recorded_ready_for_decision_validation": status_report.get("gate_audit_ready_for_decision_validation"),
        "current_verification_status": verification.get("status"),
        "current_next_missing_gate": verification.get("next_missing_gate"),
    }


def _verify_decision_record_status_gate_audit_status(verification: dict[str, Any]) -> dict[str, Any]:
    if verification.get("status") != "passed":
        return {
            "status": "failed",
            "summary": verification.get("summary", "Gate audit verification did not match the status package."),
            "failed_conditions": verification.get("failed_conditions", []),
        }
    return {
        "status": "passed",
        "summary": "Gate audit verification matches the status package.",
    }


def _verify_decision_record_status_markdown_sidecar(status_path: Path, status_report: dict[str, Any]) -> dict[str, Any]:
    markdown_path = status_path.with_suffix(".md")
    if not markdown_path.exists():
        return {
            "status": "failed",
            "path": str(markdown_path),
            "exists": False,
            "summary": "Markdown sidecar is missing.",
            "failed_conditions": ["Markdown sidecar is missing."],
        }
    text = markdown_path.read_text(encoding="utf-8")
    conditions = [
        ("# Phase 5 Decision Record Status" in text, "Markdown sidecar title is present."),
        (_markdown_field_matches(text, "Status", status_report.get("status")), "Markdown sidecar status matches JSON."),
        (_markdown_field_matches(text, "request_path", status_report.get("request_path")), "Markdown sidecar request_path matches JSON."),
        (_markdown_field_matches(text, "records_dir", status_report.get("records_dir")), "Markdown sidecar records_dir matches JSON."),
        (_markdown_field_matches(text, "gate_audit_path", status_report.get("gate_audit_path")), "Markdown sidecar gate_audit_path matches JSON."),
        (
            _markdown_field_matches(text, "ready_for_decision_validation", status_report.get("ready_for_decision_validation")),
            "Markdown sidecar ready_for_decision_validation matches JSON.",
        ),
        (
            _markdown_field_matches(text, "ready_for_real_smoke", status_report.get("ready_for_real_smoke")),
            "Markdown sidecar ready_for_real_smoke matches JSON.",
        ),
        (_markdown_field_matches(text, "write_config", status_report.get("write_config")), "Markdown sidecar write_config matches JSON."),
        (
            _markdown_field_matches(text, "exports_applied", status_report.get("exports_applied")),
            "Markdown sidecar exports_applied matches JSON.",
        ),
        (
            f"filled_candidate_count: `{status_report.get('filled_candidate_count')}`" in text,
            "Markdown sidecar filled_candidate_count matches JSON.",
        ),
        (
            f"template_unfilled_count: `{status_report.get('template_unfilled_count')}`" in text,
            "Markdown sidecar template_unfilled_count matches JSON.",
        ),
        (
            f"invalid_candidate_count: `{status_report.get('invalid_candidate_count')}`" in text,
            "Markdown sidecar invalid_candidate_count matches JSON.",
        ),
        (
            _markdown_field_matches(text, "gate_audit_verification_status", status_report.get("gate_audit_verification_status")),
            "Markdown sidecar gate_audit_verification_status matches JSON.",
        ),
        (
            _markdown_field_matches(text, "gate_audit_next_missing_gate", status_report.get("gate_audit_next_missing_gate")),
            "Markdown sidecar gate_audit_next_missing_gate matches JSON.",
        ),
    ]
    records = status_report.get("records", [])
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict) or not _has_text(record.get("path")):
                continue
            expected_line = f"- {Path(str(record['path'])).name}: `{record.get('classification')}` / `{record.get('status')}`"
            conditions.append(
                (
                    expected_line in text,
                    f"Markdown sidecar record line for `{Path(str(record['path'])).name}` matches JSON.",
                )
            )
    next_actions = status_report.get("next_actions", [])
    if isinstance(next_actions, list):
        for action in next_actions:
            if _has_text(action):
                conditions.append((f"- {action}" in text, "Markdown sidecar next action matches JSON."))
    result = _audit_required_conditions(
        conditions,
        "Markdown sidecar matches recorded decision-record status JSON.",
    )
    return {
        **result,
        "path": str(markdown_path),
        "exists": True,
    }


def _verify_decision_record_status_next_actions(status: str) -> list[str]:
    if status == "passed":
        return ["Use this decision-record status package only for the recorded source artifact revisions."]
    return ["Regenerate the decision-record status package before using it for human decision validation."]


def _verify_decision_record_status_stop_reason(status: str, checks: dict[str, dict[str, Any]]) -> str:
    if status == "passed":
        return "Decision-record status package provenance and Markdown checks passed."
    failed = [
        f"{name}: {check.get('summary')}"
        for name, check in checks.items()
        if check.get("status") == "failed"
    ]
    if failed:
        return failed[0]
    return "Decision-record status package verification needs attention."


def _verify_gate_audit_markdown_sidecar(audit_path: Path, audit: dict[str, Any]) -> dict[str, Any]:
    markdown_path = audit_path.with_suffix(".md")
    if not markdown_path.exists():
        return {
            "status": "failed",
            "path": str(markdown_path),
            "exists": False,
            "summary": "Markdown sidecar is missing.",
            "failed_conditions": ["Markdown sidecar is missing."],
        }
    text = markdown_path.read_text(encoding="utf-8")
    packet = audit.get("next_action_packet", {})
    source_artifacts = audit.get("source_artifacts", {})
    conditions = [
        ("# Phase 5 Gate Audit" in text, "Markdown sidecar title is present."),
        (_markdown_field_matches(text, "Status", audit.get("status")), "Markdown sidecar status matches JSON."),
        (
            _markdown_field_matches(text, "ready_for_real_smoke", audit.get("ready_for_real_smoke")),
            "Markdown sidecar ready_for_real_smoke matches JSON.",
        ),
        (
            _markdown_field_matches(text, "write_config", audit.get("write_config")),
            "Markdown sidecar write_config matches JSON.",
        ),
        (
            _markdown_field_matches(text, "exports_applied", audit.get("exports_applied")),
            "Markdown sidecar exports_applied matches JSON.",
        ),
        (
            _markdown_field_matches(text, "next_missing_gate", audit.get("next_missing_gate")),
            "Markdown sidecar next_missing_gate matches JSON.",
        ),
        (
            _markdown_field_matches(text, "phase5_terminal_outcome", audit.get("phase5_terminal_outcome")),
            "Markdown sidecar phase5_terminal_outcome matches JSON.",
        ),
    ]
    if isinstance(packet, dict) and _has_text(packet.get("gate")):
        conditions.append(
            (
                f"- gate: `{packet['gate']}`" in text,
                "Markdown sidecar next_action_packet gate matches JSON.",
            )
        )
        conditions.extend(_markdown_packet_list_conditions(text, packet, "required_inputs", quoted=True))
        conditions.extend(_markdown_packet_list_conditions(text, packet, "safe_command_templates", quoted=True))
        conditions.extend(_markdown_packet_list_conditions(text, packet, "expected_artifacts", quoted=True))
        conditions.extend(_markdown_packet_list_conditions(text, packet, "forbidden_actions", quoted=False))
    if isinstance(source_artifacts, dict):
        for name, artifact in source_artifacts.items():
            if not isinstance(artifact, dict):
                continue
            artifact_path = artifact.get("path")
            sha256 = artifact.get("sha256")
            if _has_text(artifact_path):
                conditions.append(
                    (
                        f"- {name}: `{artifact_path}`" in text,
                        f"Markdown sidecar source artifact `{name}` path matches JSON.",
                    )
                )
            if _has_text(sha256):
                conditions.append(
                    (
                        f"sha256 `{sha256}`" in text,
                        f"Markdown sidecar source artifact `{name}` sha256 matches JSON.",
                    )
                )
    result = _audit_required_conditions(
        conditions,
        "Markdown sidecar matches recorded gate audit JSON.",
    )
    return {
        **result,
        "path": str(markdown_path),
        "exists": True,
    }


def _markdown_field_matches(text: str, label: str, value: Any) -> bool:
    if isinstance(value, bool):
        expected_value = str(value).lower()
    elif _has_text(value):
        expected_value = str(value)
    else:
        return False
    return f"{label}: `{expected_value}`" in text


def _markdown_packet_list_conditions(
    text: str,
    packet: dict[str, Any],
    field: str,
    *,
    quoted: bool,
) -> list[tuple[bool, str]]:
    values = packet.get(field)
    if not isinstance(values, list):
        return []
    conditions: list[tuple[bool, str]] = []
    for value in values:
        if not _has_text(value):
            continue
        expected_line = f"- `{value}`" if quoted else f"- {value}"
        conditions.append(
            (
                expected_line in text,
                f"Markdown sidecar next_action_packet {field} item matches JSON.",
            )
        )
    return conditions


def _verify_gate_audit_next_actions(status: str) -> list[str]:
    if status == "passed":
        return ["Use this gate audit handoff as current only for the recorded source artifact revisions."]
    return ["Regenerate or repair the Phase 5 gate audit package before using it for human action."]


def _verify_gate_audit_stop_reason(status: str, checks: dict[str, dict[str, Any]]) -> str:
    if status == "passed":
        return "Gate audit package provenance and non-executing safety checks passed."
    failed = [
        f"{name}: {check.get('summary')}"
        for name, check in checks.items()
        if check.get("status") == "failed"
    ]
    if failed:
        return failed[0]
    return "Gate audit package verification needs attention."


def _audit_required_conditions(conditions: list[tuple[bool, str]], success_summary: str) -> dict[str, Any]:
    failed = [summary for passed, summary in conditions if not passed]
    if failed:
        return {"status": "failed", "summary": failed[0], "failed_conditions": failed}
    return {"status": "passed", "summary": success_summary}


def _audit_target_matches(report: dict[str, Any], target: dict[str, Any], *, include_limit: bool = False) -> bool:
    artifact_target = report.get("target", {})
    if not isinstance(artifact_target, dict):
        return False
    if artifact_target.get("model_id") != target.get("model_id"):
        return False
    if artifact_target.get("benchmark_id") != target.get("benchmark_id"):
        return False
    if include_limit:
        if artifact_target.get("limit") != target.get("limit"):
            return False
        if artifact_target.get("instrumentation_mode") != target.get("instrumentation_mode"):
            return False
    return True


def _audit_safety_flags_false(report: dict[str, Any]) -> bool:
    flags = report.get("safety_flags", {})
    if not isinstance(flags, dict):
        return False
    return all(flags.get(name) is False for name in SAFETY_FLAGS)


def _next_incomplete_gate(gate_checks: dict[str, dict[str, Any]]) -> str:
    for name, check in gate_checks.items():
        if check.get("status") != "passed":
            return name
    return "none"


def _gate_audit_terminal_outcome(gate_checks: dict[str, dict[str, Any]]) -> str:
    if any(check.get("status") == "failed" for check in gate_checks.values()):
        return "none"
    real_smoke = gate_checks.get("real_smoke_result", {})
    outcome = str(real_smoke.get("outcome", "none"))
    if real_smoke.get("status") == "passed" and outcome in {
        "validated_real_smoke_success",
        "reviewed_real_execution_failure",
    }:
        return outcome
    return "none"


def _gate_audit_status(gate_checks: dict[str, dict[str, Any]], terminal_outcome: str) -> str:
    if any(check.get("status") == "failed" for check in gate_checks.values()):
        return "failed"
    if terminal_outcome == "validated_real_smoke_success":
        return "passed"
    return "needs_attention"


def _gate_audit_next_actions(next_missing_gate: str, status: str, terminal_outcome: str) -> list[str]:
    if status == "failed":
        return ["Fix the invalid Phase 5 gate artifact before changing config, exporting env vars, or running the real smoke."]
    if terminal_outcome == "validated_real_smoke_success":
        return ["Review and archive the validated Phase 5 real-smoke bundle before moving to later phases."]
    if terminal_outcome == "reviewed_real_execution_failure":
        return ["Review the preserved real-execution failure diagnostics before deciding whether to retry or continue."]
    if next_missing_gate == "real_smoke_result":
        return ["Provide a validated controlled run directory from the Phase 5 worker before continuing."]
    return [f"Provide or fix the `{next_missing_gate}` artifact before continuing toward the Phase 5 real smoke."]


def _gate_audit_next_action_packet(
    *,
    next_missing_gate: str,
    status: str,
    terminal_outcome: str,
    target: dict[str, Any],
) -> dict[str, Any]:
    forbidden_actions = [
        "Do not run the real model or benchmark from this gate audit.",
        "Do not edit project_config or export environment variables from this gate audit.",
        "Do not submit remote jobs or write raw_outputs.jsonl from this gate audit.",
        "Do not treat unfilled template files as human approval.",
        "Do not treat model-path approval as permission to run the real smoke.",
        "Do not apply approved paths to project_config or environment variables from this gate audit.",
    ]
    if status == "failed":
        return {
            "gate": next_missing_gate,
            "status": status,
            "required_inputs": ["fixed_phase5_gate_artifact"],
            "safe_command_templates": [],
            "expected_artifacts": [],
            "forbidden_actions": forbidden_actions,
        }
    if terminal_outcome == "validated_real_smoke_success":
        return {
            "gate": "none",
            "status": status,
            "required_inputs": [],
            "safe_command_templates": [],
            "expected_artifacts": [],
            "forbidden_actions": forbidden_actions,
        }
    if next_missing_gate == "model_path_decision_request":
        model_id = target["model_id"]
        benchmark_id = target["benchmark_id"]
        return {
            "gate": "model_path_decision_request",
            "status": "needs_attention",
            "required_inputs": [
                "reviewed_variant_or_exact_model_path",
                "candidate_REMOTE_BENCHMARK_ROOT",
                "decision_request_output_dir",
            ],
            "safe_command_templates": [
                (
                    "python -m stable_core.cli phase5-model-path-decision-request "
                    f"--model {model_id} --benchmark {benchmark_id} "
                    "--model-path <reviewed_variant_or_exact_model_path> "
                    "--benchmark-root <candidate_REMOTE_BENCHMARK_ROOT> "
                    "--output-dir <decision_request_output_dir>"
                )
            ],
            "expected_artifacts": [
                "phase5_model_path_decision_request.json",
                "phase5_model_path_decision_request.md",
            ],
            "forbidden_actions": forbidden_actions,
        }
    if next_missing_gate == "model_path_decision_validation":
        return {
            "gate": "model_path_decision_validation",
            "status": "needs_attention",
            "required_inputs": [
                "phase5_model_path_decision_request.json",
                "filled_human_decision_record.json",
                "phase5_model_path_decision_validation_output",
            ],
            "safe_command_templates": [
                (
                    "python -m stable_core.cli phase5-validate-model-path-decision "
                    "--request <phase5_model_path_decision_request.json> "
                    "--decision-record <filled_human_decision_record.json> "
                    "--output <phase5_model_path_decision_validation_output>"
                ),
                (
                    "Fill exactly one JSON file copied from "
                    "runs/needs_attention/phase_5_model_path_decision_request/decision_record_templates/ "
                    "before validation."
                ),
            ],
            "expected_artifacts": [
                "phase5_model_path_decision_validation.json",
            ],
            "forbidden_actions": forbidden_actions,
        }
    if next_missing_gate == "approved_decision_readiness":
        return {
            "gate": "approved_decision_readiness",
            "status": "needs_attention",
            "required_inputs": [
                "phase5_model_path_decision_validation.json",
                "approved_decision_readiness_output_dir",
            ],
            "safe_command_templates": [
                (
                    "python -m stable_core.cli phase5-approved-decision-readiness "
                    "--decision-validation <phase5_model_path_decision_validation.json> "
                    "--output-dir <approved_decision_readiness_output_dir>"
                )
            ],
            "expected_artifacts": [
                "phase5_approved_decision_readiness.json",
                "phase5_approved_decision_readiness.md",
            ],
            "forbidden_actions": forbidden_actions,
        }
    if next_missing_gate == "config_representation_proposal":
        return {
            "gate": "config_representation_proposal",
            "status": "needs_attention",
            "required_inputs": [
                "phase5_approved_decision_readiness.json",
                "config_representation_proposal_output_dir",
            ],
            "safe_command_templates": [
                (
                    "python -m stable_core.cli phase5-config-representation-proposal "
                    "--approved-readiness <phase5_approved_decision_readiness.json> "
                    "--output-dir <config_representation_proposal_output_dir>"
                )
            ],
            "expected_artifacts": [
                "phase5_config_representation_proposal.json",
                "phase5_config_representation_proposal.md",
            ],
            "forbidden_actions": forbidden_actions,
        }
    if next_missing_gate == "config_representation_decision":
        return {
            "gate": "config_representation_decision",
            "status": "needs_attention",
            "required_inputs": [
                "phase5_config_representation_proposal.json",
                "filled_config_representation_decision_record.json",
                "phase5_config_representation_decision_validation_output",
            ],
            "safe_command_templates": [
                (
                    "python -m stable_core.cli phase5-validate-config-representation-decision "
                    "--proposal <phase5_config_representation_proposal.json> "
                    "--decision-record <filled_config_representation_decision_record.json> "
                    "--output <phase5_config_representation_decision_validation_output>"
                ),
                (
                    "Fill exactly one JSON file copied from the config proposal "
                    "decision_record_templates before validation."
                ),
            ],
            "expected_artifacts": [
                "phase5_config_representation_decision_validation.json",
            ],
            "forbidden_actions": forbidden_actions,
        }
    if next_missing_gate == "phase5_readiness":
        model_id = target["model_id"]
        benchmark_id = target["benchmark_id"]
        limit = target["limit"]
        instrumentation_mode = target["instrumentation_mode"]
        return {
            "gate": "phase5_readiness",
            "status": "needs_attention",
            "required_inputs": [
                "reviewed_config_or_env_representation",
                "phase5_readiness_output_dir",
            ],
            "safe_command_templates": [
                (
                    "python -m stable_core.cli phase5-readiness "
                    f"--model {model_id} --benchmark {benchmark_id} "
                    f"--limit {limit} --instrumentation {instrumentation_mode} "
                    "--output-dir <phase5_readiness_output_dir>"
                )
            ],
            "expected_artifacts": [
                "phase5_readiness.json",
                "phase5_readiness.md",
            ],
            "forbidden_actions": forbidden_actions,
        }
    if next_missing_gate == "real_smoke_result":
        model_id = target["model_id"]
        benchmark_id = target["benchmark_id"]
        limit = target["limit"]
        instrumentation_mode = target["instrumentation_mode"]
        return {
            "gate": "real_smoke_result",
            "status": "needs_attention",
            "required_inputs": [
                "controlled_worker_run_id",
                "runs_root",
                "validated_run_artifact_bundle",
            ],
            "safe_command_templates": [
                "python -m stable_core.cli validate-run --run-id <controlled_worker_run_id>",
                (
                    "python -m stable_core.cli phase5-gate-audit "
                    f"--model {model_id} --benchmark {benchmark_id} "
                    f"--limit {limit} --instrumentation {instrumentation_mode} "
                    "--decision-request <phase5_model_path_decision_request.json> "
                    "--decision-validation <phase5_model_path_decision_validation.json> "
                    "--approved-readiness <phase5_approved_decision_readiness.json> "
                    "--config-proposal <phase5_config_representation_proposal.json> "
                    "--config-decision-validation <phase5_config_representation_decision_validation.json> "
                    "--readiness <phase5_readiness.json> "
                    "--smoke-run-id <controlled_worker_run_id> "
                    "--runs-root <runs_root> "
                    "--output-dir <phase5_gate_audit_output_dir>"
                ),
            ],
            "expected_artifacts": [
                "run_manifest.json",
                "artifact_manifest.json",
                "raw_outputs.jsonl_or_failure_diagnostics",
            ],
            "forbidden_actions": forbidden_actions,
        }
    return {
        "gate": next_missing_gate,
        "status": "needs_attention",
        "required_inputs": [f"{next_missing_gate}_artifact"],
        "safe_command_templates": [],
        "expected_artifacts": [],
        "forbidden_actions": forbidden_actions,
    }


def _gate_audit_stop_reason(next_missing_gate: str, status: str, terminal_outcome: str) -> str:
    if status == "failed":
        return "At least one Phase 5 gate artifact is invalid."
    if next_missing_gate == "phase5_readiness":
        return "Phase 5 readiness has not passed."
    if terminal_outcome == "validated_real_smoke_success":
        return "No missing Phase 5 gate: the real-smoke success bundle is validated."
    if terminal_outcome == "reviewed_real_execution_failure":
        return "Phase 5 has a reviewed real-execution failure bundle; the real smoke did not succeed."
    if next_missing_gate == "real_smoke_result":
        return "No validated real-smoke success or reviewed real-execution failure bundle has been provided."
    return f"Phase 5 gate `{next_missing_gate}` is missing or incomplete."


def _gate_audit_markdown(report: dict[str, Any]) -> str:
    target = report["target"]
    next_action_packet = report.get("next_action_packet", {})
    source_artifacts = report.get("source_artifacts", {})
    gate_lines = [
        f"- {name}: `{payload.get('status')}`"
        for name, payload in report["gate_checks"].items()
    ]
    safety_lines = [
        f"- {name}: `{str(value).lower()}`"
        for name, value in report["safety_flags"].items()
    ]
    next_action_lines = [f"- {action}" for action in report["next_actions"]]
    required_input_lines = [
        f"- `{value}`"
        for value in next_action_packet.get("required_inputs", [])
    ]
    command_lines = [
        f"- `{value}`"
        for value in next_action_packet.get("safe_command_templates", [])
    ]
    expected_artifact_lines = [
        f"- `{value}`"
        for value in next_action_packet.get("expected_artifacts", [])
    ]
    forbidden_action_lines = [
        f"- {value}"
        for value in next_action_packet.get("forbidden_actions", [])
    ]
    source_lines: list[str] = []
    if isinstance(source_artifacts, dict):
        for name, artifact in source_artifacts.items():
            if not isinstance(artifact, dict):
                continue
            path = artifact.get("path")
            exists = str(artifact.get("exists")).lower()
            sha256 = artifact.get("sha256")
            if sha256:
                source_lines.append(f"- {name}: `{path}` sha256 `{sha256}`")
            else:
                source_lines.append(f"- {name}: `{path}` exists `{exists}`")
    source_section = ""
    if source_lines:
        source_section = "## Source Artifacts\n\n" + "\n".join(source_lines) + "\n\n"
    return (
        "# Phase 5 Gate Audit\n\n"
        f"Status: `{report['status']}`\n\n"
        f"ready_for_real_smoke: `{str(report['ready_for_real_smoke']).lower()}`\n\n"
        f"write_config: `{str(report['write_config']).lower()}`\n\n"
        f"exports_applied: `{str(report['exports_applied']).lower()}`\n\n"
        f"next_missing_gate: `{report['next_missing_gate']}`\n\n"
        f"phase5_terminal_outcome: `{report['phase5_terminal_outcome']}`\n\n"
        "## Target\n\n"
        f"- model: `{target['model_id']}`\n"
        f"- benchmark: `{target['benchmark_id']}`\n"
        f"- limit: `{target['limit']}`\n"
        f"- instrumentation: `{target['instrumentation_mode']}`\n\n"
        "## Gate Checks\n\n"
        + "\n".join(gate_lines)
        + "\n\n"
        "## Safety Flags\n\n"
        + "\n".join(safety_lines)
        + "\n\n"
        + source_section
        + "## Next Actions\n\n"
        + "\n".join(next_action_lines)
        + "\n\n"
        "## Next Action Packet\n\n"
        f"- gate: `{next_action_packet.get('gate')}`\n\n"
        "### Required Inputs\n\n"
        + "\n".join(required_input_lines)
        + "\n\n"
        "### Safe Command Templates\n\n"
        + "\n".join(command_lines)
        + "\n\n"
        "### Expected Artifacts\n\n"
        + "\n".join(expected_artifact_lines)
        + "\n\n"
        "### Forbidden Actions\n\n"
        + "\n".join(forbidden_action_lines)
        + "\n\n"
        "## Stop Reason\n\n"
        f"{report['do_not_continue_reason']}\n"
    )


def _write_decision_record_status_package(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "phase5_decision_record_status.json", report)
    write_text(output_dir / "phase5_decision_record_status.md", _decision_record_status_markdown(report))


def _decision_record_status_markdown(report: dict[str, Any]) -> str:
    safety_lines = [
        f"- {name}: `{str(value).lower()}`"
        for name, value in report["safety_flags"].items()
    ]
    allowed_decision_lines = [
        f"- `{decision}`"
        for decision in report.get("allowed_decisions", [])
    ]
    record_lines = [
        (
            f"- {Path(record['path']).name}: `{record.get('classification')}` / `{record.get('status')}`"
            f" decision `{record.get('decision')}`"
        )
        for record in report.get("records", [])
    ]
    next_action_lines = [
        f"- {action}"
        for action in report.get("next_actions", [])
    ]
    selected_path = report.get("selected_decision_record_path")
    selected_display = selected_path if selected_path is not None else "none"
    return (
        "# Phase 5 Decision Record Status\n\n"
        f"Status: `{report['status']}`\n\n"
        f"request_path: `{report['request_path']}`\n\n"
        f"records_dir: `{report['records_dir']}`\n\n"
        f"gate_audit_path: `{report['gate_audit_path']}`\n\n"
        f"ready_for_decision_validation: `{str(report['ready_for_decision_validation']).lower()}`\n\n"
        f"ready_for_real_smoke: `{str(report['ready_for_real_smoke']).lower()}`\n\n"
        f"write_config: `{str(report['write_config']).lower()}`\n\n"
        f"exports_applied: `{str(report['exports_applied']).lower()}`\n\n"
        f"filled_candidate_count: `{report['filled_candidate_count']}`\n\n"
        f"template_unfilled_count: `{report['template_unfilled_count']}`\n\n"
        f"invalid_candidate_count: `{report['invalid_candidate_count']}`\n\n"
        f"filled_candidate_decision_counts: `{json.dumps(report['filled_candidate_decision_counts'], sort_keys=True)}`\n\n"
        f"ambiguous_decisions: `{json.dumps(report['ambiguous_decisions'])}`\n\n"
        f"selected_decision_record_path: `{selected_display}`\n\n"
        f"gate_audit_verification_status: `{report.get('gate_audit_verification_status')}`\n\n"
        f"gate_audit_next_missing_gate: `{report.get('gate_audit_next_missing_gate')}`\n\n"
        f"gate_audit_ready_for_decision_validation: `{str(report['gate_audit_ready_for_decision_validation']).lower()}`\n\n"
        "## Allowed Decisions\n\n"
        + ("\n".join(allowed_decision_lines) if allowed_decision_lines else "- none")
        + "\n\n"
        "## Records\n\n"
        + ("\n".join(record_lines) if record_lines else "- none")
        + "\n\n"
        "## Safety Flags\n\n"
        + "\n".join(safety_lines)
        + "\n\n"
        "## Next Actions\n\n"
        + ("\n".join(next_action_lines) if next_action_lines else "- none")
        + "\n\n"
        "## Stop Reason\n\n"
        f"{report['do_not_continue_reason']}\n"
    )


def _next_actions(checks: dict[str, dict[str, Any]], execution_authorization: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if checks["model_validation"].get("status") != "passed":
        actions.append("Configure and populate the approved model path, then rerun validate-model.")
    if checks["model_runtime_dependencies"].get("status") != "passed":
        actions.append("Install or activate the approved model runtime dependencies, then rerun validate-model-runtime.")
    if checks["benchmark_validation"].get("status") != "passed":
        actions.append("Configure and populate the approved benchmark path, then rerun validate-benchmark.")
    if execution_authorization.get("status") != "passed":
        actions.append("Open reviewed remote execution, GPU budget, and process-submission gates only after validation passes.")
    if not actions:
        actions.append("Run the controlled Phase 5 real smoke through the reviewed RemoteRunner path.")
    return actions


def _path_probe_next_actions(status: str, checks: dict[str, dict[str, Any]], candidate_env: dict[str, str]) -> list[str]:
    if status == "passed":
        exports = " ".join(f"{name}={value}" for name, value in candidate_env.items())
        return [
            f"Review and approve these candidate environment values before exporting them: {exports}",
            "After approval, rerun validate-model, validate-benchmark, and phase5-readiness in the server execution environment.",
        ]
    actions: list[str] = []
    if checks["model_validation"].get("status") != "passed":
        actions.append("Choose a model root whose configured model subdirectory passes validate-model.")
    if checks["benchmark_validation"].get("status") != "passed":
        actions.append("Choose a benchmark root whose configured benchmark subdirectory passes validate-benchmark.")
    if checks["model_runtime_dependencies"].get("status") != "passed":
        actions.append("Install or activate model runtime dependencies before probing candidate roots again.")
    if not actions:
        actions.append("Review failed checks before using these candidate roots.")
    return actions


def _explicit_model_path_next_actions(status: str, checks: dict[str, dict[str, Any]], contract_satisfied: bool) -> list[str]:
    actions: list[str] = []
    if status == "passed":
        if contract_satisfied:
            actions.append("Review the exact model path, then prefer phase5-probe-paths with the configured root contract before execution.")
        else:
            actions.append("Treat this as a review-only variant path; obtain explicit approval before any config-path override or real smoke attempt.")
        actions.append("Rerun phase5-readiness or a controlled worker plan only after the approved model and benchmark paths are represented in config.")
        return actions
    if checks["model_explicit_path_validation"].get("status") != "passed":
        actions.append("Choose an exact model path whose no-load model validation passes.")
    if checks["benchmark_validation"].get("status") != "passed":
        actions.append("Choose a benchmark root whose configured benchmark subdirectory passes validate-benchmark.")
    if checks["model_runtime_dependencies"].get("status") != "passed":
        actions.append("Install or activate model runtime dependencies before probing exact model paths again.")
    if not actions:
        actions.append("Review failed checks before using this explicit model path.")
    return actions


def _validate_model_explicit_path(model_id: str, model_path: Path) -> dict[str, Any]:
    adapter_class = MODEL_ADAPTERS.get(model_id)
    if adapter_class is None:
        return {"model_id": model_id, "status": "failed", "checks": [], "summary": "Unknown model id."}
    config = dict(_config_entry(REPO_ROOT / "project_config" / "models.yaml", "models", model_id))
    config["local_path"] = str(model_path)
    config.pop("path", None)
    report = adapter_class(config).validate_environment()
    return {"model_id": model_id, **report.to_dict()}


def _do_not_continue_reason(
    status: str,
    checks: dict[str, dict[str, Any]],
    execution_authorization: dict[str, Any],
) -> str | None:
    if status == "passed":
        return None
    if any(check.get("status") != "passed" for check in checks.values()):
        return "Required validation, inventory, or runtime dependency checks are not all passed."
    if execution_authorization.get("status") != "passed":
        return "Remote execution authorization is not open."
    return "Phase 5 readiness is not complete."


def _configured_root_env(
    config_name: str,
    section: str,
    item_id: str,
    env_field: str,
    path_fields: tuple[str, ...],
) -> str:
    entry = _config_entry(REPO_ROOT / "project_config" / config_name, section, item_id)
    env_name = entry.get(env_field)
    if env_name:
        return str(env_name)
    for field in path_fields:
        match = _ENV_TEMPLATE.search(str(entry.get(field, "")))
        if match is not None:
            return match.group(1)
    raise ValueError(f"{item_id} does not declare {env_field} or a path template environment variable.")


def _configured_model_dir(model_id: str) -> str | None:
    entry = _config_entry(REPO_ROOT / "project_config" / "models.yaml", "models", model_id)
    for field in ("local_path", "path"):
        raw_path = entry.get(field)
        if raw_path:
            return Path(str(raw_path)).name
    return None


def _config_entry(config_path: Path, section: str, item_id: str) -> dict[str, Any]:
    data = parse_simple_yaml(config_path)
    items = data.get(section, {})
    if not isinstance(items, dict):
        return {}
    entry = items.get(item_id, {})
    return entry if isinstance(entry, dict) else {}


class _temporary_env:
    def __init__(self, updates: dict[str, str]) -> None:
        self.updates = updates
        self.previous: dict[str, str | None] = {}

    def __enter__(self) -> None:
        for name, value in self.updates.items():
            self.previous[name] = os.environ.get(name)
            os.environ[name] = value

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        for name, value in self.previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _write_bundle(output_dir: Path, bundle: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "phase5_readiness.json", bundle)
    write_text(output_dir / "phase5_readiness.md", _markdown_summary(bundle))


def _markdown_summary(bundle: dict[str, Any]) -> str:
    target = bundle["target"]
    check_lines = [
        f"- {name}: `{payload.get('status')}`"
        for name, payload in bundle["checks"].items()
    ]
    gate_names = [
        failure.get("name", "unknown")
        for failure in bundle["execution_authorization"].get("gate_failures", [])
    ]
    gate_text = ", ".join(f"`{name}`" for name in gate_names) if gate_names else "`none`"
    safety_lines = [
        f"- {name}: `{str(value).lower()}`"
        for name, value in bundle["safety_flags"].items()
    ]
    next_action_lines = [f"- {action}" for action in bundle["next_actions"]]
    return (
        "# Phase 5 Readiness\n\n"
        f"Status: `{bundle['status']}`\n\n"
        "## Target\n\n"
        f"- model: `{target['model_id']}`\n"
        f"- benchmark: `{target['benchmark_id']}`\n"
        f"- limit: `{target['limit']}`\n"
        f"- instrumentation: `{target['instrumentation_mode']}`\n\n"
        "## Checks\n\n"
        + "\n".join(check_lines)
        + "\n\n"
        "## Execution Authorization\n\n"
        f"- status: `{bundle['execution_authorization'].get('status')}`\n"
        f"- gate_failures: {gate_text}\n\n"
        "## Safety Flags\n\n"
        + "\n".join(safety_lines)
        + "\n\n"
        "## Next Actions\n\n"
        + "\n".join(next_action_lines)
        + "\n\n"
        "## Stop Reason\n\n"
        f"{bundle.get('do_not_continue_reason') or 'None'}\n"
    )


def _model_path_decision_request_markdown(bundle: dict[str, Any]) -> str:
    target = bundle["target"]
    probe = bundle["probe"]
    contract = probe["configured_root_contract"]
    safety_lines = [
        f"- {name}: `{str(value).lower()}`"
        for name, value in bundle["safety_flags"].items()
    ]
    decision_lines = [f"- `{decision}`" for decision in bundle["requested_decision"]["allowed_decisions"]]
    template_lines = [
        _model_path_template_markdown_line(template)
        for template in bundle["requested_decision"].get("decision_record_templates", [])
    ]
    check_lines = [
        f"- {name}: `{payload.get('status')}`"
        for name, payload in probe["checks"].items()
    ]
    return (
        "# Phase 5 Model Path Decision Request\n\n"
        f"Status: `{bundle['status']}`\n\n"
        f"approval_status: `{bundle['approval_status']}`\n\n"
        "## Target\n\n"
        f"- model: `{target['model_id']}`\n"
        f"- benchmark: `{target['benchmark_id']}`\n"
        f"- model_path: `{target['model_path']}`\n"
        f"- benchmark_root: `{target['benchmark_root']}`\n\n"
        "## Probe\n\n"
        f"- status: `{probe['status']}`\n"
        f"- requires_human_approval: `{str(probe['requires_human_approval']).lower()}`\n"
        f"- configured_model_dir: `{contract.get('model_dir')}`\n"
        f"- contract_satisfied: `{str(contract.get('satisfied')).lower()}`\n\n"
        "## Checks\n\n"
        + "\n".join(check_lines)
        + "\n\n"
        "## Requested Decision\n\n"
        + "\n".join(decision_lines)
        + "\n\n"
        "## Decision Record Templates\n\n"
        + "\n".join(template_lines)
        + "\n\n"
        "## Safety Flags\n\n"
        + "\n".join(safety_lines)
        + "\n\n"
        "## Stop Reason\n\n"
        f"{bundle['do_not_continue_reason']}\n"
    )


def _model_path_template_markdown_line(template: dict[str, Any]) -> str:
    decision = template.get("decision")
    if decision == "approve_variant_path":
        return f"- approve_variant_path: model_path `{template.get('approved_model_path')}`"
    if decision == "reject_variant_path":
        return f"- reject_variant_path: rejected_model_path `{template.get('rejected_model_path')}`"
    if decision == "provide_base_model_root":
        return f"- provide_base_model_root: provided_model_root `{template.get('provided_model_root')}`"
    return f"- {decision}: template available"


def _approved_decision_readiness_markdown(bundle: dict[str, Any]) -> str:
    approved_paths = bundle["approved_paths"]
    check_lines = [
        f"- {name}: `{payload.get('status')}`"
        for name, payload in bundle["checks"].items()
    ]
    safety_lines = [
        f"- {name}: `{str(value).lower()}`"
        for name, value in bundle["safety_flags"].items()
    ]
    next_action_lines = [f"- {action}" for action in bundle["next_actions"]]
    return (
        "# Phase 5 Approved Decision Readiness\n\n"
        f"Status: `{bundle['status']}`\n\n"
        f"approval_status: `{bundle['approval_status']}`\n\n"
        f"ready_for_real_smoke: `{str(bundle['ready_for_real_smoke']).lower()}`\n\n"
        "## Approved Paths\n\n"
        f"- model_path: `{approved_paths.get('model_path')}`\n"
        f"- benchmark_root: `{approved_paths.get('benchmark_root')}`\n\n"
        "## Checks\n\n"
        + "\n".join(check_lines)
        + "\n\n"
        "## Safety Flags\n\n"
        + "\n".join(safety_lines)
        + "\n\n"
        "## Next Actions\n\n"
        + "\n".join(next_action_lines)
        + "\n\n"
        "## Stop Reason\n\n"
        f"{bundle['do_not_continue_reason']}\n"
    )


def _config_representation_markdown(bundle: dict[str, Any]) -> str:
    approved_paths = bundle["approved_paths"]
    check_lines = [
        f"- {name}: `{payload.get('status')}`"
        for name, payload in bundle["checks"].items()
    ]
    option_lines = [
        f"- {option['name']}: requires_config_review `{str(option.get('requires_config_review')).lower()}`"
        for option in bundle["representation_options"]
    ]
    template_lines = [
        f"- {template['selected_option']}: approved_model_path `{template.get('approved_model_path')}`"
        for template in bundle.get("decision_record_templates", [])
    ]
    safety_lines = [
        f"- {name}: `{str(value).lower()}`"
        for name, value in bundle["safety_flags"].items()
    ]
    return (
        "# Phase 5 Config Representation Proposal\n\n"
        f"Status: `{bundle['status']}`\n\n"
        f"ready_for_real_smoke: `{str(bundle['ready_for_real_smoke']).lower()}`\n\n"
        f"write_config: `{str(bundle['write_config']).lower()}`\n\n"
        f"exports_applied: `{str(bundle['exports_applied']).lower()}`\n\n"
        "## Approved Paths\n\n"
        f"- model_path: `{approved_paths.get('model_path')}`\n"
        f"- benchmark_root: `{approved_paths.get('benchmark_root')}`\n\n"
        "## Checks\n\n"
        + "\n".join(check_lines)
        + "\n\n"
        "## Representation Options\n\n"
        + "\n".join(option_lines)
        + "\n\n"
        "## Decision Record Templates\n\n"
        + "\n".join(template_lines)
        + "\n\n"
        "## Safety Flags\n\n"
        + "\n".join(safety_lines)
        + "\n\n"
        "## Stop Reason\n\n"
        f"{bundle['do_not_continue_reason']}\n"
    )
