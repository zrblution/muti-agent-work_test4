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
- `RemoteRunner.submit()` reports config-driven gate failures for `runner_mode: local_only` and `allow_real_gpu_jobs: false`.
- With open config gates in tests, `RemoteRunner.submit()` returns a whitelisted `execution_plan` with `submits_process: false`.

## Human Decisions Required

- Provide approved server environment values for `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT` without committing secrets or large artifacts.
- Confirm the resolved Qwen3-VL directory contains the required offline model inventory, including `config.json`.
- Confirm the resolved POPE directory contains benchmark metadata or sample files with an accepted suffix such as `.json`, `.jsonl`, `.tsv`, `.csv`, `.txt`, `.yaml`, or `.yml`.
- Explicitly authorize opening the remote execution gate and GPU budget after validation passes.
- Approve the transition from reviewable `execution_plan` to actual process submission before any real GPU job is submitted.

## Commands To Resume

```bash
python -m stable_core.cli validate-config
python -m stable_core.cli validate-model qwen3_vl_2b_instruct
python -m stable_core.cli validate-benchmark pope
python -m stable_core.cli validate-run --run-id qwen3vl_pope_limit8_gate_diagnostics
python -m stable_core.cli run-landmark --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --run-id qwen3vl_pope_limit8_real_smoke
python -m stable_core.cli validate-run --run-id qwen3vl_pope_limit8_real_smoke
```

## Do Not Continue Automatically

Do not start the Pro review, idea plugin, or landmark expansion phases until this first real-smoke gate either succeeds with a validated run bundle or records a reviewed real-execution failure bundle.
