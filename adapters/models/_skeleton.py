from __future__ import annotations

from pathlib import Path
from typing import Any

from adapters.inventory import missing_required_files
from adapters.path_resolution import resolve_env_path
from stable_core.schemas.common import GenerationOutput, GenerationRequest, ValidationReport


class ValidateOnlyModelAdapter:
    model_id = "abstract_model"
    display_name = "Abstract model"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self._loaded = False

    def validate_environment(self) -> ValidationReport:
        path_value = self.config.get("path") or self.config.get("local_path")
        checks: list[dict[str, Any]] = [
            {"name": "download_allowed", "status": "not_attempted", "value": self.config.get("download_allowed", False)},
            {"name": "load_attempted", "status": "not_attempted"},
        ]
        if not path_value:
            checks.append({"name": "model_path", "status": "needs_setup", "message": "No local model path configured."})
            return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} is a validate-only skeleton; model path is not configured.")
        resolved = resolve_env_path(str(path_value))
        if resolved.missing_env_var is not None:
            checks.append(
                {
                    "name": "model_path",
                    "status": "needs_setup",
                    "raw_path": resolved.raw_value,
                    "env_var": resolved.missing_env_var,
                    "message": "Required path environment variable is not set.",
                }
            )
            return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} path template needs environment setup; no download or load was attempted.")
        model_path = resolved.path or Path(str(path_value))
        if not model_path.exists():
            checks.append({"name": "model_path", "status": "needs_setup", "raw_path": resolved.raw_value, "path": str(model_path)})
            return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} path is not present; no download or load was attempted.")
        if not model_path.is_dir():
            checks.append({"name": "model_path", "status": "needs_setup", "raw_path": resolved.raw_value, "path": str(model_path), "message": "Model path must be a directory."})
            return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} path is not a directory; no download or load was attempted.")
        checks.append({"name": "model_path", "status": "passed", "raw_path": resolved.raw_value, "path": str(model_path)})
        required_files = list(self.config.get("required_files") or ["config.json"])
        missing = missing_required_files(model_path, required_files)
        if missing:
            checks.append({"name": "model_inventory", "status": "needs_setup", "path": str(model_path), "missing_files": missing})
            return ValidationReport(status="needs_setup", checks=checks, summary=f"{self.display_name} model inventory is incomplete; no download or load was attempted.")
        checks.append({"name": "model_inventory", "status": "passed", "path": str(model_path), "required_files": required_files})
        return ValidationReport(status="passed", checks=checks, summary=f"{self.display_name} path exists; load smoke is a later gate.")

    def load(self) -> object:
        raise RuntimeError(f"{self.display_name} is validate-only in Phase 4; real loading is disabled.")

    def generate(self, request: GenerationRequest) -> GenerationOutput:
        raise RuntimeError(f"{self.display_name} is validate-only in Phase 4; generation is disabled for {request.request_id}.")

    def unload(self) -> None:
        self._loaded = False

    def supports_instrumentation(self, mode: str) -> bool:
        return mode == "none"
