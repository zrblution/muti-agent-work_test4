from __future__ import annotations

from typing import Any

from stable_core.schemas.common import GenerationOutput, GenerationRequest, ValidationReport


class FakeModelAdapter:
    model_id = "fake_model"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self._loaded = False

    def validate_environment(self) -> ValidationReport:
        return ValidationReport(
            status="passed",
            checks=[
                {"name": "model_id", "status": "passed", "value": self.model_id},
                {"name": "external_weights", "status": "skipped", "message": "Fake model has no weights."},
            ],
            summary="Fake model is available without external files.",
        )

    def load(self) -> object:
        self._loaded = True
        return self

    def generate(self, request: GenerationRequest) -> GenerationOutput:
        if not self._loaded:
            raise RuntimeError("FakeModelAdapter.load() must be called before generate().")
        reference = str(request.metadata.get("reference_answer", "yes")).lower()
        prediction = "yes" if reference == "yes" else "no"
        return GenerationOutput(
            request_id=request.request_id,
            raw_text=f"{prediction}. fake response for {request.sample_id}",
            latency_ms=0.0,
            metadata={
                **request.metadata,
                "model_id": self.model_id,
                "benchmark_id": request.benchmark_id,
                "sample_id": request.sample_id,
            },
        )

    def unload(self) -> None:
        self._loaded = False

    def supports_instrumentation(self, mode: str) -> bool:
        return mode in {"none", "light"}
