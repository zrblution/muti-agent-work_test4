from __future__ import annotations

from typing import Protocol, runtime_checkable

from stable_core.schemas.common import GenerationOutput, GenerationRequest, ValidationReport


@runtime_checkable
class ModelAdapter(Protocol):
    model_id: str

    def validate_environment(self) -> ValidationReport:
        """Validate paths, dependencies, device availability, and access without loading the model."""

    def load(self) -> object:
        """Load model resources after validation gates pass."""

    def generate(self, request: GenerationRequest) -> GenerationOutput:
        """Generate one response for a canonical request."""

    def unload(self) -> None:
        """Release loaded resources."""

    def supports_instrumentation(self, mode: str) -> bool:
        """Return whether the adapter can run with the requested instrumentation mode."""
