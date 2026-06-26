from __future__ import annotations

from adapters.benchmarks._skeleton import ValidateOnlyBenchmarkAdapter


class CHAIRAdapter(ValidateOnlyBenchmarkAdapter):
    benchmark_id = "chair"
    display_name = "CHAIR"
    task_type = "image_captioning_hallucination"
