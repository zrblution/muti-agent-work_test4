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

The worker is deliberately still a gate. Direct invocation preserves stdout/stderr/exit code/env/git/failure artifacts and does not create `raw_outputs.jsonl`. This removes the missing-script gap while keeping the real Qwen3-VL + POPE smoke blocked until reviewed runtime adapter methods and process-submission authorization exist.

## Worker Validation Gate Follow-Up

The worker now applies the same validate-only model and benchmark checks before it reaches the not-implemented stub. If `REMOTE_MODEL_ROOT`, `REMOTE_BENCHMARK_ROOT`, or required inventory files are missing, direct invocation records `failure_type: landmark_worker_validation_gate_not_ready` with `validate-model` and `validate-benchmark` gate payloads.

This keeps the whitelisted target self-gating even if a future process-submitting RemoteRunner calls it directly. It still does not load models, run benchmarks, submit jobs, or write `raw_outputs.jsonl`.

## Worker Runtime Gate Follow-Up

After model and benchmark validation pass, the worker checks whether the configured Qwen3-VL and POPE adapters still inherit validate-only runtime methods. Qwen3-VL now has reviewed local `load`, `generate`, and `unload` methods, and POPE has local parsing, normalization, metrics, and failure-case extraction.

When runtime methods are missing, direct invocation records `failure_type: landmark_worker_runtime_gate_not_ready`. For the current Qwen3-VL + POPE target, the adapter runtime gate now passes and direct invocation advances into the reviewed execution loop.

## Qwen3-VL Runtime Follow-Up

`Qwen3VLAdapter` now implements local runtime methods. `load()` validates approved local inventory and runtime dependencies first, loads the processor and model with `local_files_only: true`, and honors configured precision and device map. `generate()` builds a local-image multimodal chat request, decodes only newly generated tokens, and returns a `GenerationOutput` carrying model, benchmark, sample, and generation metadata. `unload()` releases adapter references.

This enables the adapter contract only; it does not execute a real smoke by itself.

## Qwen3-VL Dependency Preflight Follow-Up

`Qwen3VLAdapter.validate_environment()` now adds a no-load `runtime_dependencies` check after local path and inventory validation pass. It checks Transformers, Torch, `AutoProcessor`, a supported Qwen-compatible model class, and configured precision dtype support without calling `from_pretrained`, downloading files, loading weights, or generating outputs.

This moves runtime dependency gaps into `needs_setup` before the whitelisted worker reaches model loading, preserving the Phase 5 rule that missing dependencies must stop at `needs_attention` instead of hard-running a real smoke.

## Runtime Diagnostics Follow-Up

`validate-model-runtime <model_id>` now exposes model-specific runtime dependency checks without requiring model files or a configured model root. `phase5-readiness` includes the result as `model_runtime_dependencies`, so missing `REMOTE_MODEL_ROOT` no longer hides whether the Qwen execution environment has Torch, Transformers, processor, model-class, and dtype support ready.

This is still read-only: it does not read `.env`, download model files, load weights, run generation, submit jobs, or write raw outputs.

## Candidate Path Probe Follow-Up

`phase5-probe-paths` now validates candidate `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT` values by temporarily applying them only inside the validation process. It runs config validation, inventory discovery, model runtime dependency checks, model validation, and benchmark validation, then restores the caller environment.

This lets the server test candidate roots before exporting env vars or changing config. It remains read-only: no `.env` read, no config mutation, no model load, no benchmark execution, no job submission, and no raw outputs.

## Model Candidate Discovery Follow-Up

`phase5-discover-model-candidates` now performs bounded read-only discovery under explicit `--search-root` values. For Qwen3-VL it classifies exact configured-root candidates that can satisfy `${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct`, incomplete HuggingFace cache bases, HuggingFace snapshots that need a reviewed config override, and output-like result directories that must not be used as model roots.

The command writes an optional JSON report with `write_config: false` and `load_attempted: false`. It is a diagnostic step before `phase5-probe-paths`; it does not export env vars, mutate config, read `.env`, download files, load weights, submit jobs, or write raw outputs.

Server verification of this command returned `needs_setup` with 9 candidates. The only Qwen3-VL cache base found under `/home/vepfs/data/cache/huggingface/hub` was incomplete, and the other qwen-like paths were classified as output directories. No candidate was usable with the current configured-root contract. The scan of `/home/vepfs/data/work1/auto-research-test1` and `/home/vepfs/data/LLM_HM_3_models` reached the configured entry cap, so the result narrows the blocker but does not prove the model is absent everywhere.

After that server run, discovery was tightened so classified candidate directories are terminal traversal nodes. This prevents qwen-like output directories from consuming the entry cap with artifact children and gives future scans more budget for sibling directories that may contain a usable model root.

Discovery now also reports qwen-like directories with `config.json` as `model_like_variant` candidates. This is intended for the server paths under `/home/vepfs/data/LLM_HM_3_models` that look like training or output model directories. They remain non-runnable until a human reviews whether a config-path override is appropriate.

Server verification after this classifier returned 27 candidates: 1 incomplete HF cache base, 8 output directories, and 18 model-like variants with direct weight files. The blocker remains: no candidate is usable under the current configured-root contract, and substituting any variant would be a separate human decision.

Direct no-load validation of those 18 variant paths passed with `Qwen3VLAdapter.validate_environment()`. That proves the variants are technically present enough for the adapter preflight, but it does not authorize using them for Phase 5 because the configured target still resolves to `${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct`.

## Explicit Model Path Probe Follow-Up

`phase5-probe-explicit-model-path` now validates an exact model path together with a candidate benchmark root. This supports review-only diagnostics for server variant paths that cannot be represented as `${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct`.

The command marks non-contract paths with `requires_human_approval: true`, restores the caller environment after temporary benchmark-root validation, and records all safety flags as false. It does not mutate config, export env vars, read `.env`, load weights, run generation, submit jobs, run benchmarks, or write raw outputs.

Server verification passed for `/home/vepfs/data/LLM_HM_3_models/output-model/Qwen3-VL-2B-3epoch/Ours` with the POPE benchmark root `/home/vepfs/data/work1/auto-research-test1/benchmarks`. That proves this particular variant path and benchmark root can pass no-load validation together. It remains blocked from real execution until a human explicitly approves using this variant and the config representation is reviewed.

## Model Path Decision Request Follow-Up

`phase5-model-path-decision-request` now wraps an explicit model-path probe into a pending review packet. The output JSON and Markdown record `approval_status: pending`, the allowed human decisions, an approval-record template, per-decision record templates for approve/reject/provide-base-root choices, the probe evidence, and false execution safety flags.

This does not resolve the Phase 5 blocker. The command does not approve the variant, mutate config, read `.env`, load weights, run generation, submit jobs, run benchmarks, or write raw outputs. It only creates the artifact needed for a human to approve a variant path, reject it, or provide a base model root that satisfies the existing configured-root contract.

Server verification generated `/tmp/phase5_model_path_decision_request_server/phase5_model_path_decision_request.json` and `.md` for `/home/vepfs/data/LLM_HM_3_models/output-model/Qwen3-VL-2B-3epoch/Ours` plus `/home/vepfs/data/work1/auto-research-test1/benchmarks`. A committed review copy now lives under `runs/needs_attention/phase_5_model_path_decision_request/`, with unfilled JSON handoff files under `decision_record_templates/`. The packet remains `approval_status: pending`, with `probe.status: passed`, `requires_human_approval: true`, and all execution safety flags false.

## Model Path Decision Validation Follow-Up

`phase5-validate-model-path-decision` now validates an external human decision record against a pending request. A matching `approve_variant_path` record validates as `passed` only when the approved model path and benchmark root exactly match the request, and mismatched approvals fail as `approval_status: invalid`.

This still does not resolve the Phase 5 blocker without an actual human decision. It does not mutate config, export env vars, read `.env`, load weights, run generation, submit jobs, run benchmarks, open process gates, or write raw outputs.

## Approved Decision Readiness Follow-Up

`phase5-approved-decision-readiness` now converts a validated approval report into a non-executing readiness bundle. It records the approved exact model path and benchmark root, plus the remaining config-review and gate-review actions.

The bundle deliberately keeps `ready_for_real_smoke: false`. A human approval record alone is not enough to run; config representation, safe path probes, `phase5-readiness`, and remote/GPU/process-submission gates still need separate review.

## Config Representation Proposal Follow-Up

`phase5-config-representation-proposal` now produces a read-only proposal for representing approved paths. It reports whether the approved model path satisfies the current `${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct` contract, proposes the benchmark root env value, and lists reviewable model representation options.

The proposal now also emits per-option `decision_record_templates` that match the fields consumed by `phase5-validate-config-representation-decision`, reducing ambiguity in the human handoff without editing config or exporting env vars.

The proposal does not edit `project_config`, export env vars, read `.env`, open gates, load weights, run generation, submit jobs, run benchmarks, or write raw outputs. It exists to prevent a validated approval from turning into an implicit config mutation.

## Config Representation Decision Validation Follow-Up

`phase5-validate-config-representation-decision` now validates an external human choice against a config representation proposal. It checks that the selected option is declared by the proposal, reviewer and rationale are present, and the approved model path plus benchmark root match the proposal exactly.

This still does not resolve the Phase 5 blocker. The validation output keeps `ready_for_real_smoke: false`, `write_config: false`, and `exports_applied: false`; it does not edit `project_config`, export env vars, read `.env`, open gates, load weights, run generation, submit jobs, run benchmarks, or write raw outputs.

## Phase 5 Gate Audit Follow-Up

`phase5-gate-audit` now reads the Phase 5 review/readiness artifact chain and reports the first missing or incomplete gate. It covers the model-path decision request, model-path decision validation, approved-decision readiness, config representation proposal, config representation decision validation, and Phase 5 readiness bundle.

The command now supports `--output-dir`, writing `phase5_gate_audit.json` plus `phase5_gate_audit.md` for human review. The package includes a structured `next_action_packet` for the next missing gate, with required inputs, safe command templates, expected artifacts, and forbidden actions. The packet now covers the initial model-path decision-request creation, the model-path decision validation handoff after a pending request exists, the approved-decision readiness handoff after a validated approval exists, and the config-representation proposal handoff after approved-decision readiness exists. The config-proposal packet points only to the read-only proposal command and keeps approved paths out of config/env mutation until a later validated representation decision.

It also supports `--smoke-run-id` with `--runs-root` to validate final recorded run evidence. A succeeded run bundle is classified as `validated_real_smoke_success`; a validated `landmark_worker_execution_failed` bundle is classified as `reviewed_real_execution_failure`; setup, validation, and runtime gate failures remain incomplete and report `next_missing_gate: real_smoke_result`.

This is an audit surface only. It keeps `ready_for_real_smoke: false`, `write_config: false`, and `exports_applied: false`, and it does not edit config, export env vars, read `.env`, open gates, load weights, run generation, submit jobs, run benchmarks, or write raw outputs.

## Worker Execution Loop Follow-Up

The whitelisted worker now calls the model and benchmark runtime methods after validation and adapter runtime gates pass. The success path writes raw outputs, normalized outputs, metrics, failure cases, experiment summary, reproducibility notes, run manifest, and artifact manifest. It refuses to overwrite existing `raw_outputs.jsonl`.

Execution exceptions now record `failure_type: landmark_worker_execution_failed` with stdout, stderr, exit code, env snapshot, failure report, and artifact manifest. This provides the reviewed real-execution failure bundle shape needed for Phase 5 without accepting incomplete setup as a successful smoke.

## POPE Runtime Follow-Up

`POPEAdapter` now implements local JSON/JSONL sample parsing, canonical request construction, yes/no normalization, metrics, and failure-case extraction. This only enables adapter-level parsing and scoring from local files; it does not execute the first Qwen3-VL + POPE smoke, submit a job, or write raw outputs.

With temporary valid inventory, the worker runtime gate now passes for the current Qwen3-VL + POPE target and the worker enters the execution loop.

## Process Submission Gate Follow-Up

`project_config/experiment_budget.yaml` now includes `allow_process_submission: false` by default. `RemoteRunner.submit()` reports this as a distinct `process_submission` gate failure before any process could be submitted.

## Reviewed Subprocess Executor Follow-Up

`RemoteRunner.submit()` now includes a reviewed synchronous subprocess path for whitelisted scripts only. It can submit a process only after `runner_mode: remote_enabled`, `allow_real_gpu_jobs: true`, and `allow_process_submission: true` are all set, and only when the caller does not request `plan_only`.

`phase5-readiness` always calls `RemoteRunner.submit(..., plan_only=True)`, so readiness bundles stay read-only even if config gates are opened. In tests with temporary inventory, missing Qwen runtime dependencies, and a temporary run root, the executor launches only `experiments/landmark_baselines/run_landmark.py`; the worker records `landmark_worker_validation_gate_not_ready`, exits nonzero, preserves diagnostics, and does not write `raw_outputs.jsonl`.

## Phase 5 Readiness Bundle Follow-Up

`phase5-readiness` now consolidates the safe Phase 5 checks into one auditable bundle. It collects `validate-config`, read-only model and benchmark inventory discovery, validate-only model and benchmark checks, and the current `RemoteRunner.submit()` authorization gate.

The bundle writes `phase5_readiness.json` and `phase5_readiness.md` to the requested output directory. It explicitly records `executed_real_model: false`, `executed_real_benchmark: false`, `submitted_remote_job: false`, `raw_outputs_written: false`, and `write_config: false`.

This does not resolve the Phase 5 blocker. With temporary valid inventory, model and benchmark validation can pass, but top-level readiness still remains `needs_attention` because the remote execution gate is closed and the reviewed execution plan still has `submits_process: false`.

## Run ID Propagation Follow-Up

`run_landmark()` now passes its requested outer `run_id` into `RemoteRunner.submit()` as `experiment_id`. When validation passes but remote execution remains gated, the failure bundle's reviewable execution plan uses the same id in `execution_plan.experiment_id` and in the worker `--run-id` argument.

This keeps future controlled real-smoke artifacts aligned with the user-requested run directory instead of drifting to the default derived id.

## Remote Plan ID Safety Follow-Up

`RemoteRunner.submit()` now rejects unsafe explicit `experiment_id` values before building a reviewable execution plan. The validation reuses the run-directory `validate_run_id()` rule, so parent traversal, slashes, backslashes, empty values, and leading or trailing whitespace cannot become a future worker `--run-id`.

This keeps the currently non-submitting plan path aligned with the same artifact path safety rules required for real execution.

## Artifact Contract Follow-Up

The reviewable `RemoteRunner` plan for `run_model_smoke_test` targeting `experiments/landmark_baselines/run_landmark.py` now includes an `artifact_contract`.

The contract declares required success outputs, required failure outputs, `never_overwrite: ["raw_outputs.jsonl"]`, and `large_artifact_policy: manifest_only`. This makes the future process-submitting executor reviewable against Phase 5 artifact preservation rules before any real model, benchmark, GPU job, or remote process can run.

## Recorded Artifact Contract Follow-Up

Landmark `needs_attention` manifests now carry the same artifact contract used by the RemoteRunner plan. `validate-run` reads the contract and checks required failure outputs for `failed` and `needs_attention` runs.

This closes the gap where a reviewable plan declared preservation rules but recorded diagnostic bundles could only be validated through fixed generic checks.
