from __future__ import annotations

from pathlib import Path
from typing import Any

from stable_core.storage.run_directory import read_json, sha256_file, validate_run_id


def validate_run_artifacts(*, run_id: str, runs_root: str | Path = Path("runs")) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        validate_run_id(run_id)
    except ValueError as exc:
        return _report("failed", [{"name": "run_id", "status": "failed", "message": str(exc)}], "Run id is not safe.")

    run_dir = Path(runs_root) / run_id
    if not run_dir.is_dir():
        checks.append({"name": "run_dir", "status": "failed", "path": str(run_dir), "message": "Run directory not found."})
        return _report("failed", checks, "Run directory is missing.")
    checks.append({"name": "run_dir", "status": "passed", "path": str(run_dir)})

    manifest = _read_required_json(run_dir / "run_manifest.json", checks, "run_manifest")
    if manifest is None:
        return _report("failed", checks, "run_manifest.json is missing or invalid.")

    if manifest.get("run_id") != run_id:
        checks.append({"name": "run_manifest_run_id", "status": "failed", "expected": run_id, "actual": manifest.get("run_id")})
    else:
        checks.append({"name": "run_manifest_run_id", "status": "passed", "value": run_id})

    manifest_status = str(manifest.get("status", ""))
    if manifest_status not in {"succeeded", "failed", "needs_attention"}:
        checks.append({"name": "run_manifest_status", "status": "failed", "value": manifest_status})
    else:
        checks.append({"name": "run_manifest_status", "status": "passed", "value": manifest_status})

    _check_support_files(run_dir, checks)
    _check_declared_outputs(run_dir, manifest, checks)
    _check_failure_artifacts(run_dir, manifest_status, checks)
    _check_artifact_contract(run_dir, manifest, manifest_status, checks)
    _check_artifact_manifest(run_dir, run_id, checks)

    status = "failed" if any(check["status"] == "failed" for check in checks) else "passed"
    summary = "Run artifacts passed validation." if status == "passed" else "Run artifact validation failed."
    return _report(status, checks, summary)


def _read_required_json(path: Path, checks: list[dict[str, Any]], check_name: str) -> dict[str, Any] | None:
    if not path.is_file():
        checks.append({"name": check_name, "status": "failed", "path": str(path), "message": "Required JSON artifact not found."})
        return None
    try:
        payload = read_json(path)
    except Exception as exc:
        checks.append({"name": check_name, "status": "failed", "path": str(path), "message": f"Invalid JSON: {exc}"})
        return None
    checks.append({"name": check_name, "status": "passed", "path": str(path)})
    return payload


def _check_support_files(run_dir: Path, checks: list[dict[str, Any]]) -> None:
    required = ["command_manifest.json", "env_snapshot.json", "git_commit.txt"]
    missing = [name for name in required if not (run_dir / name).is_file()]
    checks.append({"name": "support_files", "status": "failed" if missing else "passed", "missing": missing})


def _check_declared_outputs(run_dir: Path, manifest: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    outputs = manifest.get("outputs") or {}
    if not isinstance(outputs, dict):
        checks.append({"name": "declared_outputs", "status": "failed", "message": "Manifest outputs must be an object."})
        return
    missing = []
    unsafe = []
    for output_name, relative_path in outputs.items():
        path = Path(str(relative_path))
        if path.is_absolute() or ".." in path.parts:
            unsafe.append({"output": output_name, "path": str(relative_path)})
            continue
        if not (run_dir / path).is_file():
            missing.append({"output": output_name, "path": str(relative_path)})
    status = "failed" if missing or unsafe else "passed"
    checks.append({"name": "declared_outputs", "status": status, "missing": missing, "unsafe_paths": unsafe})


def _check_failure_artifacts(run_dir: Path, manifest_status: str, checks: list[dict[str, Any]]) -> None:
    if manifest_status not in {"failed", "needs_attention"}:
        checks.append({"name": "failure_artifacts", "status": "skipped", "reason": "Run did not fail or request attention."})
        return
    missing = [name for name in ["failure.json", "failure_report.md"] if not (run_dir / name).is_file()]
    checks.append({"name": "failure_artifacts", "status": "failed" if missing else "passed", "missing": missing})


def _check_artifact_contract(run_dir: Path, manifest: dict[str, Any], manifest_status: str, checks: list[dict[str, Any]]) -> None:
    contract = manifest.get("artifact_contract")
    if not isinstance(contract, dict):
        checks.append({"name": "artifact_contract", "status": "skipped", "reason": "No artifact contract declared."})
        return
    checks.append({"name": "artifact_contract", "status": "passed"})

    if manifest_status in {"failed", "needs_attention"}:
        _check_contract_outputs(run_dir, contract.get("failure_outputs"), checks, "artifact_contract_failure_outputs")
    elif manifest_status == "succeeded":
        _check_contract_outputs(run_dir, contract.get("success_outputs"), checks, "artifact_contract_success_outputs")


def _check_contract_outputs(
    run_dir: Path,
    outputs: Any,
    checks: list[dict[str, Any]],
    check_name: str,
) -> None:
    if not isinstance(outputs, list):
        checks.append({"name": check_name, "status": "failed", "message": "Contract outputs must be a list."})
        return
    missing = []
    unsafe = []
    for relative_path in outputs:
        path = Path(str(relative_path))
        if path.is_absolute() or ".." in path.parts:
            unsafe.append(str(relative_path))
            continue
        if not (run_dir / path).is_file():
            missing.append(str(relative_path))
    checks.append({"name": check_name, "status": "failed" if missing or unsafe else "passed", "missing": missing, "unsafe_paths": unsafe})


def _check_artifact_manifest(run_dir: Path, run_id: str, checks: list[dict[str, Any]]) -> None:
    artifact_manifest = _read_required_json(run_dir / "artifact_manifest.json", checks, "artifact_manifest")
    if artifact_manifest is None:
        return
    if artifact_manifest.get("run_id") != run_id:
        checks.append({"name": "artifact_manifest_run_id", "status": "failed", "expected": run_id, "actual": artifact_manifest.get("run_id")})
    artifacts = artifact_manifest.get("artifacts")
    if not isinstance(artifacts, list):
        checks.append({"name": "artifact_manifest_entries", "status": "failed", "message": "artifacts must be a list."})
        return

    problems: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            problems.append({"path": None, "message": "Artifact entry must be an object."})
            continue
        relative_path = artifact.get("path")
        path = Path(str(relative_path))
        if path.is_absolute() or ".." in path.parts:
            problems.append({"path": str(relative_path), "message": "Artifact path must stay inside run directory."})
            continue
        artifact_path = run_dir / path
        if not artifact_path.is_file():
            problems.append({"path": str(relative_path), "message": "Artifact file is missing."})
            continue
        expected_sha = artifact.get("sha256")
        actual_sha = sha256_file(artifact_path)
        if expected_sha != actual_sha:
            problems.append({"path": str(relative_path), "message": "sha256 mismatch.", "expected": expected_sha, "actual": actual_sha})
    checks.append({"name": "artifact_hashes", "status": "failed" if problems else "passed", "problems": problems})


def _report(status: str, checks: list[dict[str, Any]], summary: str) -> dict[str, Any]:
    return {"status": status, "checks": checks, "summary": summary}
