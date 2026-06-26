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

Inventory update: model validation now requires an offline `config.json` in the resolved model directory. Benchmark validation now requires at least one shallow metadata or sample-like file with an accepted suffix such as `.json`, `.jsonl`, `.tsv`, `.csv`, `.txt`, `.yaml`, or `.yml`. The benchmark check is intentionally generic and does not assume a POPE-specific filename.

Run-validation update: `validate-run --run-id` now validates recorded run directories without executing models or benchmarks. It checks safe run IDs, manifests, declared outputs, failure artifacts for `failed`/`needs_attention` runs, and artifact hashes.

Failure-diagnostics update: new `run-landmark` `needs_attention` bundles now include `stdout_tail`, `stderr_tail`, `reproduction_command`, `config_snapshot`, and `state_snapshot` in `failure.json`, while still preserving `stdout.log`, `stderr.log`, `exit_code.txt`, `env_snapshot.json`, and `git_commit.txt`.

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
- `validate-run --run-id qwen3vl_pope_limit8_gate`: `passed`, validating the recorded `needs_attention` artifact bundle
- `validate-run --run-id fake_phase4_acceptance`: `passed`, validating the recorded fake acceptance artifact bundle
- temporary diagnostic `run-landmark` rerun with missing env vars: exit code `1`, JSON status `needs_attention`, no real model or benchmark execution
- `validate-run --run-id qwen_pope_gate_diagnostic_check`: `passed` before the temporary run directory was removed

Logs are stored in `runs/phase_5_gate_logs/`.

Current structured gate artifacts are stored in `runs/qwen3vl_pope_limit8_gate/`.

The human decision record is stored in `runs/needs_attention/phase_5_needs_human_decision.md`.

## Root Cause Hypothesis

- `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT` are not configured in the server execution environment.
- The current Qwen3-VL and POPE adapters are validate-only skeletons.
- The structured `run-landmark` gate exists, but it correctly stops before real execution because model and benchmark validations are `needs_setup`.
- Remote runner execution is disabled and returns `needs_attention`.
- Real GPU jobs are disabled in `project_config/experiment_budget.yaml`.

## Required Fixes Before Resuming Phase 5

- Configure approved local model and POPE paths without committing secrets or large artifacts.
- Populate the approved local model and benchmark directories so offline inventory validation passes.
- Extend the controlled `run-landmark` gate with reviewed real execution only after validation passes.
- Preserve all run/failure artifacts for any future real smoke attempt.
- Keep using `validate-run --run-id <run_id>` before accepting any recorded run artifact bundle.
- Explicitly approve real GPU execution only after validation gates pass.

## Why Work Stops Here

The user instruction requires stopping at `needs_attention`. Continuing to Phase 6 would skip the first real-smoke gate and risk fabricating benchmark readiness or results.

## Boundaries

- No `.env` was read.
- No model was downloaded or loaded.
- No real benchmark was executed.
- No GPU job was started.
- No large artifact was committed.
