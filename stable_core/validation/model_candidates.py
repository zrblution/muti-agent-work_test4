from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from stable_core.storage.run_directory import current_git_commit, utc_now, write_json
from stable_core.validation.preflight import REPO_ROOT, parse_simple_yaml


WEIGHT_SUFFIXES = {".bin", ".safetensors"}
OUTPUT_HINT_FILES = {
    "artifact_manifest.json",
    "experiment_summary.md",
    "failure_cases.jsonl",
    "metrics.json",
    "normalized_outputs.jsonl",
    "raw_outputs.jsonl",
    "run_config.json",
    "run_manifest.json",
}
_ENV_TEMPLATE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def discover_phase5_model_candidates(
    model_id: str,
    *,
    search_roots: list[str | Path],
    output: str | Path | None = None,
    max_depth: int = 6,
    max_candidates: int = 40,
    max_entries: int = 20000,
) -> dict[str, Any]:
    config = _config_entry(REPO_ROOT / "project_config" / "models.yaml", "models", model_id)
    if not config:
        report = {
            "phase": "Phase 5",
            "mode": "model_candidate_discovery",
            "model_id": model_id,
            "status": "failed",
            "summary": "Unknown model id.",
            "write_config": False,
            "load_attempted": False,
            "candidates": [],
        }
        _write_optional(output, report)
        return report

    configured_dir = _configured_model_dir(config)
    root_env = _configured_root_env(config)
    if configured_dir is None or root_env is None:
        report = {
            "phase": "Phase 5",
            "mode": "model_candidate_discovery",
            "model_id": model_id,
            "status": "failed",
            "summary": "Model config does not expose a reviewable root environment and model directory.",
            "write_config": False,
            "load_attempted": False,
            "candidates": [],
        }
        _write_optional(output, report)
        return report

    candidates: list[dict[str, Any]] = []
    searched_roots: list[dict[str, Any]] = []
    for raw_root in search_roots:
        if len(candidates) >= max_candidates:
            break
        root = Path(raw_root).expanduser()
        if not root.is_dir():
            searched_roots.append({"path": str(root), "status": "needs_setup", "reason": "search root is missing or is not a directory"})
            continue
        root_candidates, scanned_entries, truncated = _scan_root(
            root,
            configured_dir=configured_dir,
            root_env=root_env,
            max_depth=max_depth,
            max_candidates=max_candidates - len(candidates),
            max_entries=max_entries,
        )
        searched_roots.append(
            {
                "path": str(root),
                "status": "passed",
                "scanned_entries": scanned_entries,
                "truncated": truncated,
            }
        )
        candidates.extend(root_candidates)

    status = "passed" if any(_is_usable_passed_candidate(candidate) for candidate in candidates) else "needs_setup"
    report = {
        "phase": "Phase 5",
        "mode": "model_candidate_discovery",
        "model_id": model_id,
        "status": status,
        "created_at": utc_now(),
        "git_commit": current_git_commit(Path.cwd()),
        "configured_model_dir": configured_dir,
        "configured_root_env": root_env,
        "searched_roots": searched_roots,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "write_config": False,
        "load_attempted": False,
        "summary": _summary(status, candidates),
        "next_actions": _next_actions(status, candidates, root_env),
    }
    _write_optional(output, report)
    return report


def _scan_root(
    root: Path,
    *,
    configured_dir: str,
    root_env: str,
    max_depth: int,
    max_candidates: int,
    max_entries: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    candidates: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    pending: list[tuple[Path, int]] = [(root, 0)]
    scanned_entries = 0
    truncated = False

    while pending and len(candidates) < max_candidates:
        directory, depth = pending.pop(0)
        try:
            resolved_directory = directory.resolve()
        except OSError:
            resolved_directory = directory
        if resolved_directory in seen_paths:
            continue
        seen_paths.add(resolved_directory)

        if directory.name == configured_dir:
            candidates.append(_configured_root_candidate(directory, root_env))
            if len(candidates) >= max_candidates:
                break
        if _is_hf_cache_base(directory, configured_dir):
            for candidate in _hf_cache_candidates(directory):
                candidates.append(candidate)
                if len(candidates) >= max_candidates:
                    break
        elif _looks_like_model_output_dir(directory, configured_dir):
            candidates.append(_output_dir_candidate(directory))
            if len(candidates) >= max_candidates:
                break

        if depth >= max_depth:
            continue
        try:
            children = sorted(directory.iterdir())
        except OSError:
            continue
        for child in children:
            scanned_entries += 1
            if scanned_entries > max_entries:
                truncated = True
                pending.clear()
                break
            if child.is_dir() and not child.is_symlink():
                pending.append((child, depth + 1))

    if pending and len(candidates) >= max_candidates:
        truncated = True
    return candidates, scanned_entries, truncated


def _configured_root_candidate(model_path: Path, root_env: str) -> dict[str, Any]:
    weight_files = _direct_weight_files(model_path)
    has_config = (model_path / "config.json").is_file()
    status = "passed" if has_config else "needs_setup"
    return {
        "candidate_type": "configured_root",
        "status": status,
        "path": str(model_path),
        "candidate_env": {root_env: str(model_path.parent)},
        "usable_with_current_config": status == "passed",
        "has_config": has_config,
        "has_weights": bool(weight_files),
        "weight_files_sample": weight_files[:5],
        "reason": (
            "contains config.json and matches the configured model subdirectory"
            if has_config
            else "matches the configured model subdirectory but is missing config.json"
        ),
        "write_config": False,
        "load_attempted": False,
    }


def _hf_cache_candidates(cache_base: Path) -> list[dict[str, Any]]:
    snapshots = cache_base / "snapshots"
    if not snapshots.is_dir():
        return [
            {
                "candidate_type": "hf_cache_base",
                "status": "needs_setup",
                "path": str(cache_base),
                "usable_with_current_config": False,
                "has_config": False,
                "has_weights": False,
                "reason": "missing snapshots directory or snapshot entries",
                "write_config": False,
                "load_attempted": False,
            }
        ]

    snapshot_dirs = [path for path in sorted(snapshots.iterdir()) if path.is_dir()]
    if not snapshot_dirs:
        return [
            {
                "candidate_type": "hf_cache_base",
                "status": "needs_setup",
                "path": str(cache_base),
                "usable_with_current_config": False,
                "has_config": False,
                "has_weights": False,
                "reason": "missing snapshots directory or snapshot entries",
                "write_config": False,
                "load_attempted": False,
            }
        ]

    candidates: list[dict[str, Any]] = [
        {
            "candidate_type": "hf_cache_base",
            "status": "needs_review",
            "path": str(cache_base),
            "snapshot_count": len(snapshot_dirs),
            "usable_with_current_config": False,
            "reason": "HuggingFace cache base exists, but current config expects an explicit model root plus model subdirectory.",
            "write_config": False,
            "load_attempted": False,
        }
    ]
    for snapshot in snapshot_dirs[:8]:
        weight_files = _direct_weight_files(snapshot)
        has_config = (snapshot / "config.json").is_file()
        candidates.append(
            {
                "candidate_type": "hf_snapshot",
                "status": "needs_review" if has_config and weight_files else "needs_setup",
                "path": str(snapshot),
                "usable_with_current_config": False,
                "requires_config_path_override": True,
                "has_config": has_config,
                "has_weights": bool(weight_files),
                "weight_files_sample": weight_files[:5],
                "reason": (
                    "snapshot contains model-like files but does not satisfy the current root/subdirectory config contract"
                    if has_config and weight_files
                    else "snapshot is missing config.json or direct weight files"
                ),
                "write_config": False,
                "load_attempted": False,
            }
        )
    return candidates


def _output_dir_candidate(directory: Path) -> dict[str, Any]:
    hint_files = sorted(name for name in OUTPUT_HINT_FILES if (directory / name).is_file())
    return {
        "candidate_type": "run_output_dir",
        "status": "ignored",
        "path": str(directory),
        "usable_with_current_config": False,
        "hint_files": hint_files,
        "reason": "directory looks like an evaluation output directory, not a loadable model directory",
        "write_config": False,
        "load_attempted": False,
    }


def _direct_weight_files(directory: Path) -> list[str]:
    try:
        return sorted(path.name for path in directory.iterdir() if path.is_file() and path.suffix.lower() in WEIGHT_SUFFIXES)
    except OSError:
        return []


def _is_hf_cache_base(directory: Path, configured_dir: str) -> bool:
    name = directory.name
    return name.startswith("models--") and name.endswith(f"--{configured_dir}")


def _looks_like_model_output_dir(directory: Path, configured_dir: str) -> bool:
    lower_name = directory.name.lower()
    normalized_config_name = configured_dir.lower().replace("-", "").replace("_", "")
    normalized_dir_name = lower_name.replace("-", "").replace("_", "")
    if "qwen" not in lower_name and normalized_config_name not in normalized_dir_name:
        return False
    return any((directory / name).is_file() for name in OUTPUT_HINT_FILES)


def _is_usable_passed_candidate(candidate: dict[str, Any]) -> bool:
    return candidate.get("candidate_type") == "configured_root" and candidate.get("status") == "passed" and candidate.get("usable_with_current_config") is True


def _configured_model_dir(config: dict[str, Any]) -> str | None:
    path_value = config.get("local_path") or config.get("path")
    if not path_value:
        return None
    name = Path(str(path_value)).name
    return name or None


def _configured_root_env(config: dict[str, Any]) -> str | None:
    env_name = config.get("model_root_env")
    if env_name:
        return str(env_name)
    path_value = str(config.get("local_path") or config.get("path") or "")
    match = _ENV_TEMPLATE.search(path_value)
    return match.group(1) if match is not None else None


def _summary(status: str, candidates: list[dict[str, Any]]) -> str:
    if status == "passed":
        return "At least one candidate matches the current configured root/subdirectory contract; review candidate_env before use."
    if candidates:
        return "Model-like paths were found, but none are directly usable with the current config contract."
    return "No model candidates were found under the provided search roots."


def _next_actions(status: str, candidates: list[dict[str, Any]], root_env: str) -> list[str]:
    if status == "passed":
        return [
            f"Review the passed configured_root candidate and export {root_env} only after approval.",
            "Rerun phase5-probe-paths with the approved model root and benchmark root before opening execution gates.",
        ]
    if any(candidate.get("candidate_type") == "hf_cache_base" for candidate in candidates):
        return [
            "Complete or locate a full HuggingFace snapshot, or provide a reviewed config override for a complete snapshot path.",
            "Do not run the real smoke until validate-model passes against an approved model path.",
        ]
    return [
        "Search a bounded, approved filesystem root that may contain the configured model directory.",
        "Do not run the real smoke until a configured_root candidate passes validate-model.",
    ]


def _config_entry(config_path: Path, section: str, item_id: str) -> dict[str, Any]:
    data = parse_simple_yaml(config_path)
    items = data.get(section, {})
    if not isinstance(items, dict):
        return {}
    entry = items.get(item_id, {})
    return entry if isinstance(entry, dict) else {}


def _write_optional(output: str | Path | None, report: dict[str, Any]) -> None:
    if output is not None:
        write_json(Path(output), report)
