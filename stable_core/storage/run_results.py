from __future__ import annotations

from pathlib import Path
from typing import Any

from stable_core.storage.run_directory import read_json, validate_run_id
from stable_core.storage.run_validator import validate_run_artifacts


def poll_recorded_run(*, run_id: str, runs_root: str | Path = Path("runs")) -> dict[str, Any]:
    try:
        validate_run_id(run_id)
    except ValueError as exc:
        return {"status": "failed", "run_id": run_id, "message": str(exc)}

    run_dir = Path(runs_root) / run_id
    manifest_path = run_dir / "run_manifest.json"
    if not run_dir.is_dir():
        return {
            "status": "needs_attention",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "message": "Run directory not found.",
        }
    if not manifest_path.is_file():
        return {
            "status": "needs_attention",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "run_manifest": str(manifest_path),
            "message": "run_manifest.json not found.",
        }
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        return {
            "status": "failed",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "run_manifest": str(manifest_path),
            "message": f"Invalid run_manifest.json: {exc}",
        }

    return {
        "status": "recorded",
        "run_id": run_id,
        "run_status": manifest.get("status"),
        "run_dir": str(run_dir),
        "run_manifest": str(manifest_path),
    }


def parse_recorded_results(*, run_id: str, runs_root: str | Path = Path("runs")) -> dict[str, Any]:
    validation = validate_run_artifacts(run_id=run_id, runs_root=runs_root)
    if validation["status"] != "passed":
        return {
            "status": "failed",
            "run_id": run_id,
            "artifact_validation_status": validation["status"],
            "artifact_validation_summary": validation["summary"],
            "checks": validation["checks"],
        }

    run_dir = Path(runs_root) / run_id
    manifest = read_json(run_dir / "run_manifest.json")
    run_status = str(manifest.get("status", ""))
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    missing_outputs = manifest.get("missing_outputs") if isinstance(manifest.get("missing_outputs"), dict) else {}
    metrics_relative = outputs.get("metrics")

    base_payload: dict[str, Any] = {
        "run_id": run_id,
        "run_status": run_status,
        "artifact_validation_status": validation["status"],
        "artifact_validation_summary": validation["summary"],
        "missing_outputs": missing_outputs,
    }

    if not metrics_relative:
        if run_status in {"failed", "needs_attention"}:
            return {"status": run_status, **base_payload}
        return {
            "status": "failed",
            **base_payload,
            "message": "Run manifest does not declare a metrics output.",
        }

    metrics_path = Path(str(metrics_relative))
    if metrics_path.is_absolute() or ".." in metrics_path.parts:
        return {"status": "failed", **base_payload, "message": "Run manifest metrics path is unsafe."}

    absolute_metrics_path = run_dir / metrics_path
    if not absolute_metrics_path.is_file():
        if run_status in {"failed", "needs_attention"}:
            return {"status": run_status, **base_payload}
        return {"status": "failed", **base_payload, "message": "Declared metrics output is missing."}

    try:
        metrics = read_json(absolute_metrics_path)
    except Exception as exc:
        return {
            "status": "failed",
            **base_payload,
            "metrics_path": str(absolute_metrics_path),
            "message": f"Invalid metrics JSON: {exc}",
        }

    return {
        "status": "passed",
        **base_payload,
        "metrics_path": str(absolute_metrics_path),
        "metrics": metrics,
    }
