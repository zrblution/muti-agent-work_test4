from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_run_id(run_id: str) -> str:
    if not run_id or run_id.strip() != run_id:
        raise ValueError("run_id must be non-empty and must not contain leading or trailing whitespace")
    if run_id in {".", ".."} or "/" in run_id or "\\" in run_id or ".." in run_id:
        raise ValueError("run_id must be a single safe path segment")
    return run_id


def ensure_run_dir(runs_root: str | Path, run_id: str) -> Path:
    safe_run_id = validate_run_id(run_id)
    run_dir = Path(runs_root) / safe_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_json(path: str | Path, payload: dict[str, Any] | list[Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(output_path)


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def tail_text(text: str, *, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_git(args: Sequence[str], *, repo_root: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)


def collect_git_snapshot(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    branch = _run_git(["branch", "--show-current"], repo_root=repo_root).stdout.strip()
    commit = _run_git(["rev-parse", "HEAD"], repo_root=repo_root).stdout.strip()
    status = _run_git(["status", "--porcelain"], repo_root=repo_root).stdout.splitlines()
    return {
        "repo_path": str(repo_root),
        "branch": branch,
        "commit": commit,
        "working_tree_clean": not status,
        "dirty_paths": status,
    }


def current_git_commit(repo_root: Path = REPO_ROOT) -> str:
    return _run_git(["rev-parse", "HEAD"], repo_root=repo_root).stdout.strip()


def collect_env_snapshot(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    usage = shutil.disk_usage(repo_root)
    return {
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "cwd": str(repo_root),
        "cuda_visible_devices_set": "CUDA_VISIBLE_DEVICES" in os.environ,
        "disk_free_bytes": usage.free,
    }


def artifact_manifest_for(run_dir: Path, run_id: str) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    for path in sorted(run_dir.iterdir()):
        if path.is_file() and path.name != "artifact_manifest.json":
            artifacts.append(
                {
                    "path": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return {"run_id": run_id, "artifacts": artifacts}
