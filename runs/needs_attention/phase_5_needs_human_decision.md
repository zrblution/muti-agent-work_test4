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
- The whitelisted worker entry point exists, is non-recursive, and now has a reviewed execution loop that calls Qwen3-VL and POPE runtime methods after validation and process-submission gates pass. With missing Qwen runtime dependencies it records `landmark_worker_validation_gate_not_ready`; with monkeypatched runtime adapters it writes the full success artifact set. No real server smoke has been accepted yet.
- `Qwen3VLAdapter.validate_environment()` now checks Transformers, Torch, `AutoProcessor`, a supported Qwen-compatible model class, and precision dtype support after offline inventory validation. Missing dependencies return `needs_setup` before model loading.
- `validate-model-runtime qwen3_vl_2b_instruct` now reports Qwen runtime dependency status without requiring `REMOTE_MODEL_ROOT` or model files, and `phase5-readiness` includes the result as `model_runtime_dependencies`.
- `phase5-probe-paths` now validates candidate model and benchmark roots without mutating env, editing config, loading weights, running benchmarks, submitting jobs, or writing raw outputs.
- `phase5-discover-model-candidates` now scans only explicit bounded roots and classifies reviewable Qwen model path candidates without mutating env, editing config, downloading, loading weights, or submitting jobs.

## Human Decisions Required

- Provide approved server environment values for `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT` without committing secrets or large artifacts.
- Review `phase5-discover-model-candidates` output before approving any `REMOTE_MODEL_ROOT` value.
- Confirm the resolved Qwen3-VL directory contains the required offline model inventory, including `config.json`.
- Confirm the resolved POPE directory contains benchmark metadata or sample files with an accepted suffix such as `.json`, `.jsonl`, `.tsv`, `.csv`, `.txt`, `.yaml`, or `.yml`.
- Confirm runtime dependencies pass `validate-model` for the approved local Qwen3-VL path, then enable process submission only for the reviewed worker to collect a real success bundle or reviewed execution-failure bundle.
- Explicitly authorize opening the remote execution gate and GPU budget after validation passes.
- Approve the transition from reviewable `execution_plan` to actual process submission by setting `allow_process_submission: true` only after validation passes and the real-smoke worker is reviewed.

## Commands To Resume

```bash
python -m stable_core.cli validate-config
python -m stable_core.cli validate-model-runtime qwen3_vl_2b_instruct
python -m stable_core.cli phase5-discover-model-candidates qwen3_vl_2b_instruct --search-root <bounded_model_search_root> --output /tmp/phase5_model_candidates.json
python -m stable_core.cli phase5-probe-paths --model qwen3_vl_2b_instruct --benchmark pope --model-root <candidate_REMOTE_MODEL_ROOT> --benchmark-root <candidate_REMOTE_BENCHMARK_ROOT> --output /tmp/phase5_candidate_paths.json
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
