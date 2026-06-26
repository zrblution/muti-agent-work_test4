# Phase 5 Needs Human Decision

Status: `needs_attention`

## Current Phase

Phase 5: minimal real smoke for `qwen3_vl_2b_instruct` + `pope` with `limit=8` and `instrumentation=none`.

## What Is Ready

- `run-landmark` exists as a structured validation gate.
- `validate-model` resolves `${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct`.
- `validate-benchmark` resolves `${REMOTE_BENCHMARK_ROOT}/POPE`.
- Offline inventory validation rejects empty model and benchmark directories.
- `validate-run --run-id qwen3vl_pope_limit8_gate` validates the recorded `needs_attention` artifact bundle.
- `validate-run --run-id qwen3vl_pope_limit8_gate_diagnostics` validates the enhanced failure-diagnostics artifact bundle.
- `poll --run-id qwen3vl_pope_limit8_gate_diagnostics` inspects the recorded manifest status without submitting a job.
- `parse-results --run-id qwen3vl_pope_limit8_gate_diagnostics` validates the artifact bundle and preserves `needs_attention` because no real-smoke metrics exist.
- `RemoteRunner.submit()` reports config-driven gate failures for `runner_mode: local_only`, `allow_real_gpu_jobs: false`, and `allow_process_submission: false`.
- With remote mode and GPU budget open but process submission closed in tests, `RemoteRunner.submit()` returns a whitelisted `execution_plan` targeting `experiments/landmark_baselines/run_landmark.py` with `submits_process: false` and a `process_submission` gate failure.
- The whitelisted worker entry point exists, is non-recursive, and records `landmark_worker_runtime_gate_not_ready` after validation passes because Qwen3-VL still inherits validate-only `load` and `generate` runtime methods. POPE local sample parsing, normalization, metrics, and failure-case extraction are now implemented, but the worker still does not load models or run benchmarks.

## Human Decisions Required

- Provide approved server environment values for `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT` without committing secrets or large artifacts.
- Confirm the resolved Qwen3-VL directory contains the required offline model inventory, including `config.json`.
- Confirm the resolved POPE directory contains benchmark metadata or sample files with an accepted suffix such as `.json`, `.jsonl`, `.tsv`, `.csv`, `.txt`, `.yaml`, or `.yml`.
- Implement reviewed Qwen3-VL load/generate methods before enabling process submission for a real smoke.
- Explicitly authorize opening the remote execution gate and GPU budget after validation passes.
- Approve the transition from reviewable `execution_plan` to actual process submission by setting `allow_process_submission: true` only after validation passes and the real-smoke worker is reviewed.

## Commands To Resume

```bash
python -m stable_core.cli validate-config
python -m stable_core.cli validate-model qwen3_vl_2b_instruct
python -m stable_core.cli validate-benchmark pope
python -m stable_core.cli validate-run --run-id qwen3vl_pope_limit8_gate_diagnostics
python -m stable_core.cli poll --run-id qwen3vl_pope_limit8_gate_diagnostics
python -m stable_core.cli parse-results --run-id qwen3vl_pope_limit8_gate_diagnostics
python -m stable_core.cli run-landmark --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --run-id qwen3vl_pope_limit8_real_smoke
python -m stable_core.cli validate-run --run-id qwen3vl_pope_limit8_real_smoke
python -m stable_core.cli poll --run-id qwen3vl_pope_limit8_real_smoke
python -m stable_core.cli parse-results --run-id qwen3vl_pope_limit8_real_smoke
```

## Do Not Continue Automatically

Do not start the Pro review, idea plugin, or landmark expansion phases until this first real-smoke gate either succeeds with a validated run bundle or records a reviewed real-execution failure bundle.
