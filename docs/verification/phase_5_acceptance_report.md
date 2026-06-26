# Phase 5 Acceptance Report

Status: `needs_attention`

## Target

- Model: `qwen3_vl_2b_instruct`
- Benchmark: `pope`
- Limit: `8`
- Instrumentation: `none`

## Decision

The real smoke was blocked before execution. This is the correct outcome under the project rules because required setup and execution gates are missing.

Continuation update: a structured `run-landmark` validation gate now exists. It records a `needs_attention` run directory without loading models, running benchmarks, or starting GPU work.

Path-template update: real model and benchmark configs now use `${REMOTE_MODEL_ROOT}` and `${REMOTE_BENCHMARK_ROOT}` templates. Validation reports a missing env var when those are unset, and validation continues to a lightweight offline inventory gate when the env vars point to existing directories. This does not read `.env`, download models, or execute benchmarks.

Inventory update: model validation now requires an offline `config.json` in the resolved model directory. Benchmark validation now honors configured `required_files` when present, and otherwise requires at least one shallow metadata or sample-like file with an accepted suffix such as `.json`, `.jsonl`, `.tsv`, `.csv`, `.txt`, `.yaml`, or `.yml`. The fallback benchmark check is intentionally generic and does not assume a POPE-specific filename.

Run-validation update: `validate-run --run-id` now validates recorded run directories without executing models or benchmarks. It checks safe run IDs, manifests, declared outputs, failure artifacts for `failed`/`needs_attention` runs, and artifact hashes.

Run-lifecycle CLI update: top-level `poll --run-id` and `parse-results --run-id` commands now inspect recorded run directories without submitting jobs, loading models, running benchmarks, or recomputing metrics. `poll` reports the recorded manifest status; `parse-results` validates the artifact bundle and reads the declared metrics file when one exists, while preserving `needs_attention` when the real-smoke gate has no outputs to score.

Failure-diagnostics update: new `run-landmark` `needs_attention` bundles now include `stdout_tail`, `stderr_tail`, `reproduction_command`, `config_snapshot`, and `state_snapshot` in `failure.json`, while still preserving `stdout.log`, `stderr.log`, `exit_code.txt`, `env_snapshot.json`, and `git_commit.txt`.

Remote gate update: `RemoteRunner.submit()` now reads `project_config/server.yaml` and `project_config/experiment_budget.yaml` and reports structured gate failures for `runner_mode`, `allow_real_gpu_jobs`, and `allow_process_submission`. It still does not submit real remote or GPU work.

Remote plan update: when the remote-mode and GPU-budget config gates are opened in a controlled test but process submission remains closed, `RemoteRunner.submit()` returns a reviewable `execution_plan` with whitelisted argv, `submits_process: false`, and a `process_submission` gate failure. This narrows the remaining remote-execution gap without launching a process.

Worker-entry update: the whitelisted `experiments/landmark_baselines/run_landmark.py` target now exists and is non-recursive. It records a durable `needs_attention` bundle with `failure_type: landmark_worker_not_implemented`, exits nonzero, and does not load models, run benchmarks, or write raw outputs. The reviewable `RemoteRunner` plan now points at this worker path instead of re-entering the top-level `run-landmark` gate.

Remote-gate diagnostics update: `run-landmark` now has separate next-action guidance for the path where model and benchmark validation pass but remote execution is still closed. That branch preserves the validated path setup and points to remote gate, GPU budget, and process-submission approval instead of asking to reconfigure paths again.

## Evidence

- `validate-config`: `passed`
- `preflight --dry-run`: `needs_setup`
- `validate-model qwen3_vl_2b_instruct`: `needs_setup`
- `validate-benchmark pope`: `needs_setup`
- historical `run-landmark` attempt before the gate existed: argparse exit code `2`
- current `run-landmark --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --run-id qwen3vl_pope_limit8_gate`: exit code `1`, JSON status `needs_attention`
- `validate-model qwen3_vl_2b_instruct` with a temporary `REMOTE_MODEL_ROOT` pointing to an existing but empty `Qwen3-VL-2B-Instruct` directory: `needs_setup`, missing `config.json`
- `validate-benchmark pope` with a temporary `REMOTE_BENCHMARK_ROOT` pointing to an existing but empty `POPE` directory: `needs_setup`, missing shallow metadata/sample files
- `validate-model qwen3_vl_2b_instruct` with a temporary `REMOTE_MODEL_ROOT` pointing to a `Qwen3-VL-2B-Instruct` directory containing `config.json`: `passed`
- `validate-benchmark pope` with a temporary `REMOTE_BENCHMARK_ROOT` pointing to a `POPE` directory containing `samples.jsonl`: `passed`
- `POPEAdapter({"required_files": ["annotations/random.json"]})` with the file missing: `needs_setup`, missing configured file
- `POPEAdapter({"required_files": ["annotations/random.json"]})` with the file present: `passed`
- `validate-run --run-id qwen3vl_pope_limit8_gate`: `passed`, validating the recorded `needs_attention` artifact bundle
- `validate-run --run-id fake_phase4_acceptance`: `passed`, validating the recorded fake acceptance artifact bundle
- temporary diagnostic `run-landmark` rerun with missing env vars: exit code `1`, JSON status `needs_attention`, no real model or benchmark execution
- `validate-run --run-id qwen_pope_gate_diagnostic_check`: `passed` before the temporary run directory was removed
- current diagnostic `run-landmark --run-id qwen3vl_pope_limit8_gate_diagnostics`: exit code `1`, JSON status `needs_attention`, no real model or benchmark execution
- `validate-run --run-id qwen3vl_pope_limit8_gate_diagnostics`: `passed`, validating the enhanced failure-diagnostics artifact bundle
- `poll --run-id qwen3vl_pope_limit8_gate_diagnostics`: reports recorded run status `needs_attention`
- `parse-results --run-id qwen3vl_pope_limit8_gate_diagnostics`: preserves status `needs_attention` and reports validated missing metrics instead of computing benchmark results
- direct `experiments/landmark_baselines/run_landmark.py` worker invocation with a temporary run root: exit code `1`, JSON status `needs_attention`, failure type `landmark_worker_not_implemented`, no real model or benchmark execution
- `run_landmark(...)` with temporary valid model and POPE inventory: JSON status `needs_attention`, failure type `landmark_remote_runner_not_enabled`, no real model or benchmark execution

Logs are stored in `runs/phase_5_gate_logs/`.

Current structured gate artifacts are stored in `runs/qwen3vl_pope_limit8_gate/`.

Current enhanced diagnostic gate artifacts are stored in `runs/qwen3vl_pope_limit8_gate_diagnostics/`.

The human decision record is stored in `runs/needs_attention/phase_5_needs_human_decision.md`.

## Root Cause Hypothesis

- `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT` are not configured in the server execution environment.
- The current Qwen3-VL and POPE adapters are validate-only skeletons.
- The structured `run-landmark` gate exists, but it correctly stops before real execution because model and benchmark validations are `needs_setup`.
- The whitelisted worker entry point exists and is non-recursive, but it is intentionally a `needs_attention` stub until the real Qwen3-VL + POPE worker is reviewed.
- Remote runner execution is config-gated: `project_config/server.yaml` still sets `runner_mode: local_only`.
- Real GPU jobs are config-gated: `project_config/experiment_budget.yaml` still sets `allow_real_gpu_jobs: false`.
- Process submission is config-gated: `project_config/experiment_budget.yaml` still sets `allow_process_submission: false`.
- Even if the remote-mode, GPU-budget, and process-submission config gates are opened later, the current reviewed path only returns an execution plan with `submits_process: false`; no process-submitting executor is enabled yet, and the worker itself still records `landmark_worker_not_implemented`.

## Required Fixes Before Resuming Phase 5

- Configure approved local model and POPE paths without committing secrets or large artifacts.
- Populate the approved local model and benchmark directories so offline inventory validation passes.
- Replace the current worker stub with a reviewed non-recursive real-smoke worker that loads the approved Qwen3-VL path, reads approved POPE samples, and preserves raw outputs exactly once.
- Extend the controlled `run-landmark` gate from reviewable execution plan to reviewed process submission only after validation passes and `allow_process_submission` is explicitly set to `true`.
- Preserve all run/failure artifacts for any future real smoke attempt.
- Keep using `validate-run --run-id <run_id>` before accepting any recorded run artifact bundle.
- Use `poll --run-id <run_id>` and `parse-results --run-id <run_id>` only as recorded-artifact inspection steps until a reviewed process-submitting remote executor exists.
- Explicitly approve real GPU execution only after validation gates pass.

## Why Work Stops Here

The user instruction requires stopping at `needs_attention`. Continuing to Phase 6 would skip the first real-smoke gate and risk fabricating benchmark readiness or results.

## Boundaries

- No `.env` was read.
- No model was downloaded or loaded.
- No real benchmark was executed.
- No GPU job was started.
- No large artifact was committed.
