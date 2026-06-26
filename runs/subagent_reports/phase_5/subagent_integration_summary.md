# Phase 5 Subagent Integration Summary

Status: `needs_attention`

## Inputs

- Spec: `06_MODELS_BENCHMARKS_EXPERIMENTS.md`
- Acceptance plan: `09_ACCEPTANCE_TESTS_AND_MVP.md`
- Preflight readiness report: `runs/subagent_reports/phase_5/preflight_readiness.md`
- Model/benchmark readiness report: `runs/subagent_reports/phase_5/model_benchmark_readiness.md`
- Smoke safety report: `runs/subagent_reports/phase_5/smoke_safety.md`
- Gate logs: `runs/phase_5_gate_logs/`

## Subagent Findings

- PreflightReadinessAgent reported `preflight --dry-run` status `needs_setup`. Its commit value is stale because the server was fast-forwarded from Phase 3 to Phase 4 while Phase 5 checks were starting, but the preflight result remains consistent with the current gate logs.
- ModelBenchmarkReadinessAgent confirmed the current Phase 4 commit `2237f00` is present and both `validate-model qwen3_vl_2b_instruct` and `validate-benchmark pope` return JSON status `needs_setup`.
- SmokeSafetyAgent confirmed `run-landmark` did not exist at the time of its read-only report, remote execution was not enabled, and there was no safe structured real-smoke command for Qwen3-VL + POPE `limit=8`.

## Main-Agent Gate Decision

Phase 5 must stop at `needs_attention`.

The gate failures are consistent:

- model path missing,
- benchmark path missing,
- the original real smoke CLI was missing; the follow-up implementation now adds a validation-only `run-landmark` gate,
- remote runner execution disabled,
- real GPU jobs disabled.

No real model was loaded, no benchmark was run, and no benchmark result was fabricated.

## Follow-Up Required Before Resuming

- Provide or configure approved local model and benchmark paths.
- Implement offline validation for those paths.
- Extend the reviewed `run-landmark` validation gate with controlled real execution only after validation passes.
- Explicitly open the real execution gate only after validation passes.

## Follow-Up Implementation

After the subagent reports, the main agent added a structured `run-landmark` command and `experiments/landmark_baselines/runner.py`. The command creates an auditable `needs_attention` run at `runs/qwen3vl_pope_limit8_gate/` and explicitly records `executed_real_model: false` and `executed_real_benchmark: false`.

The Phase 5 blocker is reduced but not resolved: model and benchmark paths are still not configured, and real execution remains gated off.

## Path Template Follow-Up

The framework now supports config values such as `${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct` and `${REMOTE_BENCHMARK_ROOT}/POPE` in validate-only adapters. Missing env vars are reported as `needs_setup` with the exact env var name, and existing directories validate as `passed`.

This removes the previous `path: null` framework limitation.

## Offline Inventory Follow-Up

The validate-only adapters now perform a lightweight offline inventory gate after path resolution. Model validation requires `config.json` by default. Benchmark validation requires at least one shallow metadata or sample-like file with an accepted suffix such as `.json`, `.jsonl`, `.tsv`, `.csv`, `.txt`, `.yaml`, or `.yml`.

This removes the previous "existing empty directory passes validation" limitation. The remaining blocker is external environment setup, populated local model and benchmark directories, and real execution authorization.

## Run Artifact Validation Follow-Up

The framework now exposes `validate-run --run-id <run_id>` for recorded run directories. It validates safe run IDs, run manifests, declared output paths, required failure artifacts for `failed` or `needs_attention` runs, and `artifact_manifest.json` hashes.

This closes the Task 011 validation-command gap without re-running the model or benchmark. It does not change the remaining Phase 5 blocker: the real Qwen3-VL + POPE smoke still needs approved paths, inventory, and execution authorization.

## Failure Diagnostics Follow-Up

New `run-landmark` `needs_attention` bundles now include `stdout_tail`, `stderr_tail`, `reproduction_command`, `config_snapshot`, and `state_snapshot` in `failure.json`. This aligns the landmark gate with the AGENTS.md failure-preservation requirements while keeping real model and benchmark execution disabled until the validation and authorization gates pass.
