from __future__ import annotations

from pathlib import Path
from typing import Any

from adapters.inventory import BENCHMARK_METADATA_SUFFIXES, discover_benchmark_metadata, missing_required_files
from adapters.path_resolution import resolve_env_path
from stable_core.schemas.common import GenerationOutput, GenerationRequest, ValidationReport


class ValidateOnlyBenchmarkAdapter:
    benchmark_id = "abstract_benchmark"
    display_name = "Abstract benchmark"
    task_type = "unknown"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def validate_paths(self) -> ValidationReport:
        path_value = self.config.get("path")
        checks: list[dict[str, Any]] = [{"name": "adapter", "status": "passed", "value": type(self).__name__}]
        if not path_value:
            checks.append({"name": "benchmark_path", "status": "needs_setup", "message": "No benchmark path configured."})
            return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} is validate-only; benchmark path is not configured.")
        resolved = resolve_env_path(str(path_value))
        if resolved.missing_env_var is not None:
            checks.append(
                {
                    "name": "benchmark_path",
                    "status": "needs_setup",
                    "raw_path": resolved.raw_value,
                    "env_var": resolved.missing_env_var,
                    "message": "Required path environment variable is not set.",
                }
            )
            return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} path template needs environment setup; no benchmark was run.")
        benchmark_path = resolved.path or Path(str(path_value))
        if not benchmark_path.exists():
            checks.append({"name": "benchmark_path", "status": "needs_setup", "raw_path": resolved.raw_value, "path": str(benchmark_path)})
            return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} path is not present; no benchmark was run.")
        if not benchmark_path.is_dir():
            checks.append({"name": "benchmark_path", "status": "needs_setup", "raw_path": resolved.raw_value, "path": str(benchmark_path), "message": "Benchmark path must be a directory."})
            return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} path is not a directory; no benchmark was run.")
        checks.append({"name": "benchmark_path", "status": "passed", "raw_path": resolved.raw_value, "path": str(benchmark_path)})
        required_files = list(self.config.get("required_files") or [])
        if required_files:
            missing = missing_required_files(benchmark_path, required_files)
            if missing:
                checks.append({"name": "benchmark_inventory", "status": "needs_setup", "path": str(benchmark_path), "missing_files": missing})
                return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} configured inventory is incomplete; no benchmark was run.")
            checks.append({"name": "benchmark_inventory", "status": "passed", "path": str(benchmark_path), "required_files": required_files})
            return ValidationReport(status="passed", checks=checks, summary=f"{self.display_name} configured inventory exists; sample parsing is a later gate.")
        discovered_files = discover_benchmark_metadata(benchmark_path)
        if not discovered_files:
            checks.append(
                {
                    "name": "benchmark_inventory",
                    "status": "needs_setup",
                    "path": str(benchmark_path),
                    "message": "No shallow metadata/sample files discovered.",
                    "accepted_suffixes": sorted(BENCHMARK_METADATA_SUFFIXES),
                }
            )
            return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} inventory is incomplete; no benchmark was run.")
        checks.append({"name": "benchmark_inventory", "status": "passed", "path": str(benchmark_path), "discovered_files": discovered_files})
        return ValidationReport(status="passed", checks=checks, summary=f"{self.display_name} path exists; sample parsing is a later gate.")

    def build_requests(self, split: str, limit: int | None) -> list[GenerationRequest]:
        raise RuntimeError(f"{self.display_name} is validate-only in Phase 4; real sample parsing is disabled.")

    def normalize_prediction(self, raw_output: GenerationOutput) -> dict:
        raise RuntimeError(f"{self.display_name} is validate-only in Phase 4; prediction normalization is disabled for {raw_output.request_id}.")

    def compute_metrics(self, normalized_outputs_path: Path) -> dict:
        raise RuntimeError(f"{self.display_name} is validate-only in Phase 4; metric computation is disabled for {normalized_outputs_path}.")

    def extract_failure_cases(self, normalized_outputs_path: Path) -> list[dict]:
        raise RuntimeError(f"{self.display_name} is validate-only in Phase 4; failure extraction is disabled for {normalized_outputs_path}.")
