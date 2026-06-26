from __future__ import annotations

from adapters.benchmarks._skeleton import ValidateOnlyBenchmarkAdapter


class POPEAdapter(ValidateOnlyBenchmarkAdapter):
    benchmark_id = "pope"
    display_name = "POPE"
    task_type = "yes_no_vqa"
