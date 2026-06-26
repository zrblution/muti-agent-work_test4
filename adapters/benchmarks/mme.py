from __future__ import annotations

from adapters.benchmarks._skeleton import ValidateOnlyBenchmarkAdapter


class MMEAdapter(ValidateOnlyBenchmarkAdapter):
    benchmark_id = "mme"
    display_name = "MME"
    task_type = "multi_task_mllm_eval"
