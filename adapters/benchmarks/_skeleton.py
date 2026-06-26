from __future__ import annotations

from pathlib import Path
from typing import Any

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
        benchmark_path = Path(str(path_value))
        if not benchmark_path.exists():
            checks.append({"name": "benchmark_path", "status": "needs_setup", "path": str(benchmark_path)})
            return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} path is not present; no benchmark was run.")
        checks.append({"name": "benchmark_path", "status": "passed", "path": str(benchmark_path)})
        return ValidationReport(status="passed", checks=checks, summary=f"{self.display_name} path exists; sample parsing is a later gate.")

    def build_requests(self, split: str, limit: int | None) -> list[GenerationRequest]:
        raise RuntimeError(f"{self.display_name} is validate-only in Phase 4; real sample parsing is disabled.")

    def normalize_prediction(self, raw_output: GenerationOutput) -> dict:
        raise RuntimeError(f"{self.display_name} is validate-only in Phase 4; prediction normalization is disabled for {raw_output.request_id}.")

    def compute_metrics(self, normalized_outputs_path: Path) -> dict:
        raise RuntimeError(f"{self.display_name} is validate-only in Phase 4; metric computation is disabled for {normalized_outputs_path}.")

    def extract_failure_cases(self, normalized_outputs_path: Path) -> list[dict]:
        raise RuntimeError(f"{self.display_name} is validate-only in Phase 4; failure extraction is disabled for {normalized_outputs_path}.")
