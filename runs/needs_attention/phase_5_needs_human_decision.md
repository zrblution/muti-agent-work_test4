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
- Latest server discovery returned `needs_setup`: the known HF cache base for Qwen3-VL-2B-Instruct is incomplete, discovered qwen-like paths are output directories, and no usable configured-root model candidate was found in the bounded scan.
- Updated server discovery now also surfaces 18 qwen3-vl-2b-like variant model directories with direct weights under `/home/vepfs/data/LLM_HM_3_models`; these are `needs_review` and are not usable without a reviewed config-path decision.
- Direct no-load validation of those 18 variant paths passed, so the remaining decision is whether any variant is an acceptable Phase 5 target and how to represent that path without silently changing the configured base model.
- `phase5-probe-explicit-model-path` can now validate an exact variant model path plus benchmark root as a review-only diagnostic. It marks non-contract paths as requiring human approval and keeps all execution safety flags false.
- Server exact-path probe passed for `/home/vepfs/data/LLM_HM_3_models/output-model/Qwen3-VL-2B-3epoch/Ours` plus `/home/vepfs/data/work1/auto-research-test1/benchmarks`, but it is still review-only because it does not satisfy the configured base-model root contract.
- `phase5-model-path-decision-request` can now package an exact-path probe into a JSON and Markdown decision request with `approval_status: pending`, allowed decisions, and an approval-record template. This is still review-only and does not approve a path, mutate config, run a model, run a benchmark, submit a job, or write raw outputs.

## Human Decisions Required

- Provide approved server environment values for `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT` without committing secrets or large artifacts.
- Review `phase5-discover-model-candidates` output before approving any `REMOTE_MODEL_ROOT` value.
- Decide whether any `model_like_variant` path is an acceptable substitute for the configured base `Qwen3-VL-2B-Instruct`; do not treat variants as the Phase 5 target without explicit approval.
- If a variant is being considered, review the `phase5-model-path-decision-request` packet and record one of the allowed decisions: `approve_variant_path`, `reject_variant_path`, or `provide_base_model_root`.
- Provide a narrower approved model search root if the existing broad roots are not exhaustive enough; two broad roots hit the discovery entry cap.
- Confirm the resolved Qwen3-VL directory contains the required offline model inventory, including `config.json`.
- Confirm the resolved POPE directory contains benchmark metadata or sample files with an accepted suffix such as `.json`, `.jsonl`, `.tsv`, `.csv`, `.txt`, `.yaml`, or `.yml`.
- Confirm runtime dependencies pass `validate-model` for the approved local Qwen3-VL path, then enable process submission only for the reviewed worker to collect a real success bundle or reviewed execution-failure bundle.
- Explicitly authorize opening the remote execution gate and GPU budget after validation passes.
- Approve the transition from reviewable `execution_plan` to actual process submission by setting `allow_process_submission: true` only after validation passes and the real-smoke worker is reviewed.

## Commands To Resume

```bash
python -m stable_core.cli validate-config
python -m stable_core.cli validate-model-runtime qwen3_vl_2b_instruct
python -m stable_core.cli phase5-discover-model-candidates qwen3_vl_2b_instruct --search-root /home/vepfs/data/cache/huggingface/hub --search-root /home/vepfs/data/work1/auto-research-test1 --search-root /home/vepfs/data/work1/Base_Model_Testing --search-root /home/vepfs/data/LLM_HM_3_models --output /tmp/phase5_model_candidates.json --max-depth 8 --max-candidates 80 --max-entries 50000
python -m stable_core.cli phase5-probe-explicit-model-path --model qwen3_vl_2b_instruct --benchmark pope --model-path <reviewed_variant_or_exact_model_path> --benchmark-root <candidate_REMOTE_BENCHMARK_ROOT> --output /tmp/phase5_explicit_model_path_probe.json
python -m stable_core.cli phase5-model-path-decision-request --model qwen3_vl_2b_instruct --benchmark pope --model-path <reviewed_variant_or_exact_model_path> --benchmark-root <candidate_REMOTE_BENCHMARK_ROOT> --output-dir /tmp/phase5_model_path_decision_request
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
