from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adapters.inventory import BENCHMARK_METADATA_SUFFIXES, discover_benchmark_metadata
from adapters.path_resolution import resolve_env_path
from stable_core.validation.preflight import REPO_ROOT, parse_simple_yaml


def discover_benchmark_inventory(
    benchmark_id: str,
    *,
    output: str | Path | None = None,
    max_files: int = 20,
) -> dict[str, Any]:
    config = _config_entry(REPO_ROOT / "project_config" / "benchmarks.yaml", "benchmarks", benchmark_id)
    if not config:
        report = {"benchmark_id": benchmark_id, "status": "failed", "summary": "Unknown benchmark id.", "write_config": False}
        _write_optional(output, report)
        return report

    path_value = config.get("path")
    if not path_value:
        report = {
            "benchmark_id": benchmark_id,
            "status": "needs_setup",
            "summary": "No benchmark path configured.",
            "write_config": False,
            "discovered_files": [],
        }
        _write_optional(output, report)
        return report

    resolved = resolve_env_path(str(path_value))
    if resolved.missing_env_var is not None:
        report = {
            "benchmark_id": benchmark_id,
            "status": "needs_setup",
            "raw_path": resolved.raw_value,
            "missing_env_var": resolved.missing_env_var,
            "summary": "Required benchmark path environment variable is not set.",
            "write_config": False,
            "discovered_files": [],
        }
        _write_optional(output, report)
        return report

    benchmark_path = resolved.path or Path(str(path_value))
    if not benchmark_path.exists() or not benchmark_path.is_dir():
        report = {
            "benchmark_id": benchmark_id,
            "status": "needs_setup",
            "raw_path": resolved.raw_value,
            "path": str(benchmark_path),
            "summary": "Benchmark path is missing or is not a directory.",
            "write_config": False,
            "discovered_files": [],
        }
        _write_optional(output, report)
        return report

    discovered_files = discover_benchmark_metadata(benchmark_path, max_files=max_files)
    status = "passed" if discovered_files else "needs_setup"
    report = {
        "benchmark_id": benchmark_id,
        "status": status,
        "raw_path": resolved.raw_value,
        "path": str(benchmark_path),
        "accepted_suffixes": sorted(BENCHMARK_METADATA_SUFFIXES),
        "discovered_files": discovered_files,
        "write_config": False,
        "summary": (
            "Review discovered_files before copying any entries into project_config/benchmarks.yaml required_files."
            if discovered_files
            else "No shallow benchmark metadata or sample files were discovered."
        ),
    }
    _write_optional(output, report)
    return report


def _config_entry(config_path: Path, section: str, item_id: str) -> dict[str, Any]:
    data = parse_simple_yaml(config_path)
    items = data.get(section, {})
    if not isinstance(items, dict):
        return {}
    entry = items.get(item_id, {})
    return entry if isinstance(entry, dict) else {}


def _write_optional(output: str | Path | None, report: dict[str, Any]) -> None:
    if output is None:
        return
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
