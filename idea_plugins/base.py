from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from adapters.benchmarks.base import BenchmarkAdapter
from adapters.models.base import ModelAdapter
from stable_core.schemas.common import GenerationOutput, GenerationRequest, ValidationReport


@runtime_checkable
class IdeaPlugin(Protocol):
    idea_id: str
    version: str

    def validate_compatibility(self, model_adapter: ModelAdapter, benchmark_adapter: BenchmarkAdapter) -> ValidationReport:
        """Check whether this plugin can work with a model/benchmark pair."""

    def prepare(self, run_dir: Path, config: dict) -> dict:
        """Prepare plugin state and write plugin manifest data."""

    def modify_request(self, request: GenerationRequest, context: dict) -> GenerationRequest:
        """Optionally modify a request and record changes in context."""

    def wrap_generation(self, model_adapter: ModelAdapter, request: GenerationRequest, context: dict) -> GenerationOutput:
        """Optionally wrap generation for decoding/logit/attention intervention."""

    def collect_artifacts(self, run_dir: Path) -> list[dict]:
        """Return artifact refs; large files must be referenced by manifest."""
