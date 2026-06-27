# Phase 5 Execution Authorization Request

Status: `needs_attention`

## Target

- model: `qwen3_vl_2b_instruct`
- benchmark: `pope`
- limit: `8`
- instrumentation: `none`

## Validated Inputs

- `REMOTE_MODEL_ROOT`: `/home/tos_lx/basemodel`
- `REMOTE_BENCHMARK_ROOT`: `/home/vepfs/data/work1/auto-research-test1/benchmarks`
- model inventory: `/home/tos_lx/basemodel/Qwen3-VL-2B-Instruct`
- benchmark inventory: `/home/vepfs/data/work1/auto-research-test1/benchmarks/POPE`
- model runtime dependencies: `passed`
- no-load model validation: `passed`
- benchmark validation: `passed`

## Current Closed Gates

- `runner_mode: local_only`
- `allow_real_gpu_jobs: false`
- `allow_process_submission: false`
- `submitted_process: false`

## Decision Needed

Fill exactly one template under `decision_record_templates/`:

- `authorize_remote_execution.template.json`: approve config/env representation plus opening the reviewed remote, GPU, and process-submission gates for only this Phase 5 smoke.
- `keep_execution_closed.template.json`: keep Phase 5 stopped at `needs_attention` and record why execution remains closed.

This request is not itself approval. It does not edit config, export env vars, load a model, run a benchmark, submit a process, write raw outputs, or open execution gates.

## Source Artifacts

- `runs/needs_attention/phase_5_base_model_root_decision_current/phase5_provided_base_model_root_probe.json`
- `runs/needs_attention/phase_5_base_model_root_decision_current/phase5_readiness/phase5_readiness.json`
- `runs/needs_attention/phase_5_base_model_root_decision_current/phase5_model_path_decision_validation.json`

## Safety Flags

- `executed_real_model: false`
- `executed_real_benchmark: false`
- `submitted_remote_job: false`
- `raw_outputs_written: false`
- `write_config: false`
- `exports_applied: false`

Do not proceed to Phase 6 until Phase 5 has either a validated real-smoke success bundle or a reviewed real-execution failure bundle.
