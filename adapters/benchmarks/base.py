from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from stable_core.schemas.common import GenerationOutput, GenerationRequest, ValidationReport


@runtime_checkable
class BenchmarkAdapter(Protocol):
    benchmark_id: str

    def validate_paths(self) -> ValidationReport:
        """Check dataset path, annotation files, scripts, and metadata."""

    def build_requests(self, split: str, limit: int | None) -> list[GenerationRequest]:
        """Convert benchmark samples into canonical generation requests."""

    def normalize_prediction(self, raw_output: GenerationOutput) -> dict:
        """Convert raw output into benchmark-specific normalized prediction."""

    def compute_metrics(self, normalized_outputs_path: Path) -> dict:
        """Compute metrics from normalized outputs only."""

    def extract_failure_cases(self, normalized_outputs_path: Path) -> list[dict]:
        """Return case-level failures with enough evidence for analysis."""
