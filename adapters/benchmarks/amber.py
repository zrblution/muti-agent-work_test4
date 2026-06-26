from __future__ import annotations

from adapters.benchmarks._skeleton import ValidateOnlyBenchmarkAdapter


class AMBERAdapter(ValidateOnlyBenchmarkAdapter):
    benchmark_id = "amber"
    display_name = "AMBER"
    task_type = "mllm_hallucination_eval"
