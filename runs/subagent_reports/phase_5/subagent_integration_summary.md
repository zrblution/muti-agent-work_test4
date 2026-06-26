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

## Configured Benchmark Inventory Follow-Up

Benchmark validation now honors `required_files` when a benchmark config provides that list. If the list is empty, validation keeps the generic shallow metadata/sample discovery fallback required by the spec, so Codex still does not assume POPE-specific filenames before preflight discovery.

## Inventory Path Safety Follow-Up

Configured model and benchmark `required_files` entries now must be relative paths confined to the resolved model or benchmark root. Absolute paths, Windows absolute paths, empty entries, and `..` parent traversal return `failed` with `unsafe_files` before any file existence check. This prevents a config from satisfying inventory validation by pointing at files elsewhere on the server filesystem.

`validate-config` now performs the same safety check as an `inventory` subreport, so unsafe `required_files` are rejected before path templates, model roots, or benchmark roots are resolved. The check covers both inline YAML lists and block-list YAML entries.

## Benchmark Inventory Discovery Follow-Up

`discover-benchmark-inventory <benchmark_id>` now performs read-only shallow discovery of benchmark metadata/sample candidates when the configured benchmark path resolves. It writes an optional JSON report with `discovered_files` and `write_config: false`, and returns `needs_setup` when required path environment variables are missing. This supports the spec requirement that benchmark `required_files` can be discovered and reviewed before being copied into config, without guessing POPE-specific filenames or executing a benchmark.

## Model Inventory Discovery Follow-Up

`discover-model-inventory <model_id>` now performs read-only shallow discovery of model metadata candidates when the configured model path resolves. It writes an optional JSON report with `discovered_files`, `write_config: false`, and `load_attempted: false`, and returns `needs_setup` when required path environment variables are missing. This supports reviewing Qwen3-VL local metadata before any real-smoke worker is allowed to download, load, or generate.

## Run Artifact Validation Follow-Up

The framework now exposes `validate-run --run-id <run_id>` for recorded run directories. It validates safe run IDs, run manifests, declared output paths, required failure artifacts for `failed` or `needs_attention` runs, and `artifact_manifest.json` hashes.

This closes the Task 011 validation-command gap without re-running the model or benchmark. It does not change the remaining Phase 5 blocker: the real Qwen3-VL + POPE smoke still needs approved paths, inventory, and execution authorization.

## Failure Diagnostics Follow-Up

New `run-landmark` `needs_attention` bundles now include `stdout_tail`, `stderr_tail`, `reproduction_command`, `config_snapshot`, and `state_snapshot` in `failure.json`. This aligns the landmark gate with the AGENTS.md failure-preservation requirements while keeping real model and benchmark execution disabled until the validation and authorization gates pass.

## Remote Gate Follow-Up

`RemoteRunner.submit()` now reads `project_config/server.yaml` and `project_config/experiment_budget.yaml` before returning `needs_attention`. It reports structured gate failures for `runner_mode: local_only` and `allow_real_gpu_jobs: false`, rather than a stale hard-coded Phase 3 message. Real remote execution remains closed.

## Worker Entry Follow-Up

The whitelisted `experiments/landmark_baselines/run_landmark.py` path now exists. `RemoteRunner.submit()` reviewable plans target that script directly instead of recursively invoking `stable_core.cli run-landmark`.

The worker is deliberately still a gate: direct invocation records a `needs_attention` run with `failure_type: landmark_worker_not_implemented`, preserves stdout/stderr/exit code/env/git/failure artifacts, and does not create `raw_outputs.jsonl`. This removes the missing-script gap while keeping the real Qwen3-VL + POPE smoke blocked until a reviewed non-recursive worker implementation and process-submission authorization exist.

## Process Submission Gate Follow-Up

`project_config/experiment_budget.yaml` now includes `allow_process_submission: false` by default. `RemoteRunner.submit()` reports this as a distinct `process_submission` gate failure before any process could be submitted. When remote mode, GPU budget, and process submission are all opened in tests, the runner still stops at `remote_executor` with `submits_process: false` because no reviewed process-submitting executor exists.

## Phase 5 Readiness Bundle Follow-Up

`phase5-readiness` now consolidates the safe Phase 5 checks into one auditable bundle. It collects `validate-config`, read-only model and benchmark inventory discovery, validate-only model and benchmark checks, and the current `RemoteRunner.submit()` authorization gate.

The bundle writes `phase5_readiness.json` and `phase5_readiness.md` to the requested output directory. It explicitly records `executed_real_model: false`, `executed_real_benchmark: false`, `submitted_remote_job: false`, `raw_outputs_written: false`, and `write_config: false`.

This does not resolve the Phase 5 blocker. With temporary valid inventory, model and benchmark validation can pass, but top-level readiness still remains `needs_attention` because the remote execution gate is closed and the reviewed execution plan still has `submits_process: false`.
