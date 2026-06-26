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

Inventory safety update: configured model and benchmark `required_files` must now be relative paths that remain inside the resolved inventory root. Absolute paths, Windows absolute paths, empty entries, and `..` parent traversal are rejected with `status: failed` before any file existence check is attempted.

Config validation update: `validate-config` now includes an `inventory` subreport and rejects unsafe model or benchmark `required_files` entries even before model or benchmark paths are resolved. This covers both inline YAML lists and block-list YAML entries.

Benchmark discovery update: `discover-benchmark-inventory <benchmark_id>` now writes a read-only JSON report of shallow benchmark metadata/sample candidates when the configured benchmark path resolves. It does not modify `project_config`, does not assume POPE-specific filenames, and reports `needs_setup` when the benchmark root env var is missing.

Model discovery update: `discover-model-inventory <model_id>` now writes a read-only JSON report of shallow model metadata candidates when the configured model path resolves. It does not modify `project_config`, does not download or load model weights, excludes weight-like files, and reports `needs_setup` when the model root env var is missing.

Readiness bundle update: `phase5-readiness --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --output-dir <dir>` now writes a consolidated read-only JSON and Markdown bundle for Phase 5. It collects config validation, model and benchmark inventory discovery, model and benchmark validation, and the current RemoteRunner execution gate. It records `executed_real_model: false`, `executed_real_benchmark: false`, `submitted_remote_job: false`, `raw_outputs_written: false`, and `write_config: false`.

Runtime dependency diagnostics update: `validate-model-runtime <model_id>` now checks model-specific runtime dependencies without requiring model files, loading weights, downloading files, or reading `.env`. `phase5-readiness` includes this as `model_runtime_dependencies`, so a missing model path no longer hides whether the execution environment has the Qwen runtime dependencies available.

Candidate path probe update: `phase5-probe-paths --model <id> --benchmark <id> --model-root <path> --benchmark-root <path>` now validates candidate root directories by temporarily applying the configured root environment variables inside the process. It does not mutate the caller environment, does not modify config, does not read `.env`, does not load weights, does not submit jobs, and does not write raw outputs.

Model candidate discovery update: `phase5-discover-model-candidates <model_id> --search-root <path>` now scans only explicit bounded roots for reviewable model path candidates. It identifies configured-root candidates compatible with `${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct`, incomplete HuggingFace cache bases, HuggingFace snapshots that would need a reviewed config override, and output-like directories that must not be used as model roots. It does not mutate config, export env vars, read `.env`, download files, load weights, or submit jobs.

Server candidate discovery result: on the server, `phase5-discover-model-candidates qwen3_vl_2b_instruct` over `/home/vepfs/data/cache/huggingface/hub`, `/home/vepfs/data/work1/auto-research-test1`, `/home/vepfs/data/work1/Base_Model_Testing`, and `/home/vepfs/data/LLM_HM_3_models` returned `needs_setup` with 9 candidates. It found an incomplete HuggingFace cache base for `models--Qwen--Qwen3-VL-2B-Instruct` and several output-like result directories, but no `configured_root` candidate usable with the current `${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct` contract. The two broad result roots hit the `max_entries=50000` cap, so this is diagnostic evidence, not an exhaustive filesystem proof.

Discovery pruning update: once the scanner classifies an exact configured model directory, a HuggingFace cache base, or an output-like result directory, it now treats that directory as terminal for traversal. This preserves scan budget for sibling paths and avoids spending `max_entries` inside known non-model artifact trees.

Model-like variant update: discovery now reports qwen-like directories containing `config.json` as `model_like_variant` candidates when they do not match the configured `${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct` contract. These candidates are `needs_review` only, require a reviewed config-path decision, and are not treated as runnable configured roots.

Run-validation update: `validate-run --run-id` now validates recorded run directories without executing models or benchmarks. It checks safe run IDs, manifests, declared outputs, failure artifacts for `failed`/`needs_attention` runs, and artifact hashes.

Run-lifecycle CLI update: top-level `poll --run-id` and `parse-results --run-id` commands now inspect recorded run directories without submitting jobs, loading models, running benchmarks, or recomputing metrics. `poll` reports the recorded manifest status; `parse-results` validates the artifact bundle and reads the declared metrics file when one exists, while preserving `needs_attention` when the real-smoke gate has no outputs to score.

Failure-diagnostics update: new `run-landmark` `needs_attention` bundles now include `stdout_tail`, `stderr_tail`, `reproduction_command`, `config_snapshot`, and `state_snapshot` in `failure.json`, while still preserving `stdout.log`, `stderr.log`, `exit_code.txt`, `env_snapshot.json`, and `git_commit.txt`.

Remote gate update: `RemoteRunner.submit()` now reads `project_config/server.yaml` and `project_config/experiment_budget.yaml` and reports structured gate failures for `runner_mode`, `allow_real_gpu_jobs`, and `allow_process_submission`. It still does not submit real remote or GPU work.

Remote plan update: when the remote-mode and GPU-budget config gates are opened in a controlled test but process submission remains closed, `RemoteRunner.submit()` returns a reviewable `execution_plan` with whitelisted argv, `submits_process: false`, and a `process_submission` gate failure. This narrows the remaining remote-execution gap without launching a process.

Process executor update: `RemoteRunner.submit()` now has a reviewed synchronous subprocess path for whitelisted scripts only after `runner_mode: remote_enabled`, `allow_real_gpu_jobs: true`, and `allow_process_submission: true` are all set, and only when the caller is not using `plan_only`. Non-process actions such as `poll_job` return `needs_attention` without process submission. `phase5-readiness` always uses `plan_only`, so readiness bundles cannot submit processes. In tests, the executor can launch the whitelisted worker against temporary inventory and a temporary run root. If Qwen runtime dependencies are missing, the worker records `landmark_worker_validation_gate_not_ready`; if validation passes and execution raises, it records `landmark_worker_execution_failed`. In both cases diagnostics are preserved and raw outputs are not written unless the worker succeeds.

Artifact-contract update: the reviewable landmark smoke execution plan now declares `artifact_contract` for successful and failed runs. It lists required success outputs, required failure outputs, `never_overwrite: ["raw_outputs.jsonl"]`, and `large_artifact_policy: manifest_only` so the process-submitting path remains auditable against Phase 5 artifact rules.

Recorded-contract update: landmark `needs_attention` manifests now carry the same artifact contract, and `validate-run` checks the declared failure outputs when a run is `failed` or `needs_attention`. This makes recorded failure bundles auditable against the plan contract rather than only against a small fixed failure-artifact list.

Run-id propagation update: once model and benchmark validation pass, `run-landmark` now passes the requested outer `run_id` into the RemoteRunner experiment spec. The reviewable execution plan therefore uses the same run id in `execution_plan.experiment_id` and the worker `--run-id` argument, preventing future real-smoke artifacts from drifting into a derived default run directory.

Remote plan safety update: RemoteRunner now validates an explicit `experiment_id` with the same safe run-id rules used by run directories before it can build an execution plan. Unsafe values such as parent traversal are rejected with `status: failed` and no `execution_plan`.

Worker-entry update: the whitelisted `experiments/landmark_baselines/run_landmark.py` target now exists and is non-recursive. It records durable `needs_attention` bundles, exits nonzero, and does not load models, run benchmarks, or write raw outputs. The reviewable `RemoteRunner` plan now points at this worker path instead of re-entering the top-level `run-landmark` gate.

Worker validation update: the whitelisted worker now runs the same validate-only model and benchmark gates before reaching the current not-implemented stub. Missing or unapproved inventory records `failure_type: landmark_worker_validation_gate_not_ready`, preserves the failure bundle, exits nonzero, and still does not load models, run benchmarks, or write raw outputs.

Worker runtime update: after model and benchmark validation pass, the worker checks whether the configured runtime adapters still inherit validate-only methods. Before the POPE runtime follow-up this branch recorded both `model-runtime` and `benchmark-runtime`; after the POPE update it recorded only `model-runtime`. After the Qwen3-VL runtime update, both configured adapters have reviewed runtime methods, so the adapter runtime gate now passes for Qwen3-VL + POPE.

POPE runtime update: `POPEAdapter` now implements local JSON/JSONL sample parsing, canonical request construction, yes/no prediction normalization, metrics, and failure-case extraction. This is file-local adapter logic only; it does not load a model, submit a runner job, or execute a real benchmark smoke. This first narrowed the worker runtime gate to Qwen3-VL; after the Qwen3-VL runtime update below, the current target advances past adapter runtime checks.

Qwen3-VL runtime update: `Qwen3VLAdapter` now implements `load`, `generate`, and `unload` methods for approved local model paths. Loading forces `local_files_only: true` and uses configured precision/device settings; validation only performs the no-load preflight described below. Generation constructs a local-image multimodal chat request, decodes only newly generated tokens, and preserves raw text in `GenerationOutput`.

Qwen3-VL dependency preflight update: after offline path and inventory validation pass, `Qwen3VLAdapter.validate_environment()` now checks that Transformers, Torch, `AutoProcessor`, a supported Qwen-compatible model class, and the configured precision dtype are available. This check does not call `from_pretrained`, load weights, download files, or run generation. Missing runtime dependencies return `needs_setup` before the worker reaches model loading.

Worker loop update: the whitelisted worker now connects the reviewed model and benchmark runtime methods. On success it writes `raw_outputs.jsonl`, `normalized_outputs.jsonl`, `metrics.json`, `failure_cases.jsonl`, `artifact_manifest.json`, `experiment_summary.md`, `reproducibility_notes.md`, and a succeeded `run_manifest.json` with the artifact contract. It refuses to overwrite existing raw outputs. Execution exceptions produce `landmark_worker_execution_failed` bundles with stdout, stderr, exit code, env snapshot, failure report, and artifact manifest.

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
- model path and inventory validation with a temporary `REMOTE_MODEL_ROOT` pointing to a `Qwen3-VL-2B-Instruct` directory containing `config.json`: inventory passed; full Qwen validation now continues to runtime dependency preflight before it can return `passed`
- `validate-benchmark pope` with a temporary `REMOTE_BENCHMARK_ROOT` pointing to a `POPE` directory containing `samples.jsonl`: `passed`
- `POPEAdapter({"required_files": ["annotations/random.json"]})` with the file missing: `needs_setup`, missing configured file
- `POPEAdapter({"required_files": ["annotations/random.json"]})` with the file present: `passed`
- `Qwen3VLAdapter({"required_files": ["../outside-config.json"]})` with a root-external file present: `failed`, unsafe configured inventory path rejected
- `POPEAdapter({"required_files": ["/absolute/outside.json"]})` with a root-external file present: `failed`, unsafe configured inventory path rejected
- `POPEAdapter.build_requests(...)` with local JSONL samples: constructs canonical requests with stable request ids, sample ids, prompts, image paths, task type, and reference answers without model execution
- `POPEAdapter.normalize_prediction(...)`, `compute_metrics(...)`, and `extract_failure_cases(...)`: normalize yes/no outputs and compute sample count, accuracy, yes rate, hallucination rate, and failed samples from local normalized JSONL
- `POPEAdapter.build_requests(...)` with unsafe configured `required_files`: rejects parent-traversing paths before reading sample files
- `Qwen3VLAdapter.load(...)` with a monkeypatched local runtime: validates local inventory and runtime dependencies first, loads with `local_files_only: true`, honors precision/device config, and calls model `eval()`
- `Qwen3VLAdapter.validate_environment(...)` with a monkeypatched local runtime: validates local inventory and runtime dependency availability without calling processor or model `from_pretrained`
- `Qwen3VLAdapter.validate_runtime_dependencies(...)` with a monkeypatched local runtime and no model path: reports `passed` without calling processor or model `from_pretrained`
- `Qwen3VLAdapter.validate_environment(...)` with a missing Transformers dependency: returns `needs_setup` with a `runtime_dependencies` check and records that no model was loaded
- `Qwen3VLAdapter.generate(...)` with a monkeypatched local runtime: builds a local-image multimodal chat request, sends tensors to the model device, decodes only newly generated tokens, and returns `GenerationOutput` metadata without reading `.env` or loading a real model
- `validate-config` with temporary unsafe model and benchmark `required_files`: `failed`, inventory findings identify the unsafe entries
- `validate-config` with temporary unsafe block-list `required_files`: `failed`, inventory findings identify the unsafe entries
- `discover-benchmark-inventory pope` with `REMOTE_BENCHMARK_ROOT` unset: `needs_setup`, report records the missing env var and writes no config
- `discover-benchmark-inventory pope` with a temporary POPE directory containing shallow `.json` and `.jsonl` files: `passed`, report records candidate `discovered_files` and `write_config: false`
- `discover-model-inventory qwen3_vl_2b_instruct` with `REMOTE_MODEL_ROOT` unset: `needs_setup`, report records the missing env var, `load_attempted: false`, and writes no config
- `validate-model-runtime qwen3_vl_2b_instruct` with monkeypatched runtime modules and no `REMOTE_MODEL_ROOT`: `passed`, proving dependency readiness is reported independently from model path setup
- `phase5-probe-paths` with temporary candidate model and benchmark roots plus monkeypatched runtime modules: `passed`, proving candidate roots can be validated without exporting env vars, editing config, loading models, or running benchmarks
- `phase5-discover-model-candidates qwen3_vl_2b_instruct` with a temporary `Qwen3-VL-2B-Instruct` directory containing `config.json` and a weight placeholder: `passed`, report proposes `REMOTE_MODEL_ROOT` for review and records `write_config: false` and `load_attempted: false`
- `phase5-discover-model-candidates qwen3_vl_2b_instruct` with an incomplete HuggingFace cache base containing only `refs/main`: `needs_setup`, report records `candidate_type: hf_cache_base`, `usable_with_current_config: false`, and the missing snapshots reason
- server `phase5-discover-model-candidates qwen3_vl_2b_instruct` with bounded roots: `needs_setup`, candidate count `9`, no usable `configured_root`, incomplete HF cache base, output-like result directories, and no model load or config write
- `phase5-discover-model-candidates` with a qwen-like output directory containing many child artifact directories: `needs_setup`, output directory classified once, root scan not truncated at a low entry cap
- `phase5-discover-model-candidates` with a qwen-like variant directory containing `config.json` and a weight placeholder: `needs_setup`, candidate classified as `model_like_variant`, `requires_config_path_override: true`, and not usable with current config
- `discover-model-inventory qwen3_vl_2b_instruct` with a temporary Qwen directory containing shallow `.json` metadata and a `.safetensors` placeholder: `passed`, report records metadata candidates, excludes the weight file, and writes no config
- `phase5-readiness --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --output-dir /tmp/phase5_readiness_cli_smoke` with model and benchmark root env vars unset: `needs_attention`, report records missing `REMOTE_MODEL_ROOT`, missing `REMOTE_BENCHMARK_ROOT`, independent model runtime dependency status, closed `runner_mode`, `real_gpu_budget`, and `process_submission` gates, with no real execution or raw outputs
- `phase5-readiness` in tests with temporary model `config.json` and POPE `samples.jsonl`: model and benchmark validation pass, but top-level status remains `needs_attention` because remote execution authorization is still closed and the execution plan has `submits_process: false`
- `RemoteRunner.submit(...)` for the landmark smoke worker with remote mode and GPU budget open but process submission closed: execution plan includes required success outputs, failure outputs, raw-output no-overwrite policy, and manifest-only large artifact policy
- `RemoteRunner.submit(...)` with remote mode, GPU budget, process submission, temporary inventory, missing Qwen runtime dependencies, and a temporary run root: submits the whitelisted worker subprocess, exits code `1`, returns JSON status `needs_attention`, records `failure_type: landmark_worker_validation_gate_not_ready`, preserves diagnostics, and writes no raw outputs
- `RemoteRunner.submit(..., plan_only=True)` with all config gates open: returns `needs_attention` with `plan_only`, `submitted_process: false`, `submits_process: false`, and creates no run directory
- `run_landmark(...)` recorded `needs_attention` manifest now includes `artifact_contract.failure_outputs`, and `validate-run` reports `artifact_contract_failure_outputs: passed`
- `run_landmark(...)` with temporary valid model and POPE inventory and `run_id=qwen_pope_requested_run_id`: remote execution plan records `experiment_id=qwen_pope_requested_run_id` and worker argv ends with that same requested run id
- `RemoteRunner.submit(...)` with `experiment_id=../escape`: `failed`, validation error names `experiment_id`, and no execution plan is returned
- `validate-run --run-id qwen3vl_pope_limit8_gate`: `passed`, validating the recorded `needs_attention` artifact bundle
- `validate-run --run-id fake_phase4_acceptance`: `passed`, validating the recorded fake acceptance artifact bundle
- temporary diagnostic `run-landmark` rerun with missing env vars: exit code `1`, JSON status `needs_attention`, no real model or benchmark execution
- `validate-run --run-id qwen_pope_gate_diagnostic_check`: `passed` before the temporary run directory was removed
- current diagnostic `run-landmark --run-id qwen3vl_pope_limit8_gate_diagnostics`: exit code `1`, JSON status `needs_attention`, no real model or benchmark execution
- `validate-run --run-id qwen3vl_pope_limit8_gate_diagnostics`: `passed`, validating the enhanced failure-diagnostics artifact bundle
- `poll --run-id qwen3vl_pope_limit8_gate_diagnostics`: reports recorded run status `needs_attention`
- `parse-results --run-id qwen3vl_pope_limit8_gate_diagnostics`: preserves status `needs_attention` and reports validated missing metrics instead of computing benchmark results
- direct `experiments/landmark_baselines/run_landmark.py` worker invocation with temporary model and benchmark inventory but missing Qwen runtime dependencies: exit code `1`, JSON status `needs_attention`, failure type `landmark_worker_validation_gate_not_ready`, gate failure `validate-model`, no raw outputs
- direct worker invocation in tests with monkeypatched Qwen3-VL and POPE runtime adapters: JSON status `succeeded`, writes raw outputs, normalized outputs, metrics, failure cases, experiment summary, reproducibility notes, manifest, and artifact manifest; a second run with the same run id refuses to overwrite `raw_outputs.jsonl`
- direct `experiments/landmark_baselines/run_landmark.py` worker invocation with missing `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT`: exit code `1`, JSON status `needs_attention`, failure type `landmark_worker_validation_gate_not_ready`, gate failures `validate-model` and `validate-benchmark`, no raw outputs
- `run_landmark(...)` with temporary valid model and POPE inventory: JSON status `needs_attention`, failure type `landmark_remote_runner_not_enabled`, no real model or benchmark execution

Logs are stored in `runs/phase_5_gate_logs/`.

Current structured gate artifacts are stored in `runs/qwen3vl_pope_limit8_gate/`.

Current enhanced diagnostic gate artifacts are stored in `runs/qwen3vl_pope_limit8_gate_diagnostics/`.

The human decision record is stored in `runs/needs_attention/phase_5_needs_human_decision.md`.

## Root Cause Hypothesis

- `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT` are not configured in the server execution environment.
- The current Qwen3-VL adapter now has reviewed local runtime methods, and the worker loop calls the model and benchmark runtime methods after validation and process-submission gates pass.
- Qwen3-VL validation now checks runtime dependency availability after local inventory validation. If Transformers, Torch, the supported Qwen model class, or precision dtype support is missing in the execution environment, validation must remain `needs_setup` before model loading is attempted.
- The structured `run-landmark` gate exists, but it correctly stops before real execution because model and benchmark validations are `needs_setup`.
- The whitelisted worker entry point exists and is non-recursive. The execution loop is implemented, but it has not yet been run successfully against approved real Qwen3-VL and POPE paths on the server.
- Configured inventory paths are now constrained to the model or benchmark root, so external setup still must populate approved directories instead of pointing validation at files elsewhere on the filesystem.
- Remote runner execution is config-gated: `project_config/server.yaml` still sets `runner_mode: local_only`.
- Real GPU jobs are config-gated: `project_config/experiment_budget.yaml` still sets `allow_real_gpu_jobs: false`.
- Process submission is config-gated: `project_config/experiment_budget.yaml` still sets `allow_process_submission: false`.
- Even if the remote-mode, GPU-budget, and process-submission config gates are opened later, the reviewed subprocess executor can only launch the whitelisted worker. A real Qwen3-VL + POPE smoke still cannot be accepted until approved model/benchmark paths and runtime dependencies produce a validated succeeded bundle or a reviewed real-execution failure bundle.

## Required Fixes Before Resuming Phase 5

- Configure approved local model and POPE paths without committing secrets or large artifacts.
- Use `phase5-discover-model-candidates` on bounded server roots to create a reviewable model-path audit before choosing `REMOTE_MODEL_ROOT`.
- Use `phase5-probe-paths` to validate any candidate `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT` before exporting them or enabling execution gates.
- Populate the approved local model and benchmark directories so offline inventory validation passes.
- Configure approved local model and POPE paths with Qwen3-VL runtime dependencies that pass `validate-model`, then run the non-recursive worker through the reviewed RemoteRunner gate to produce either a validated success bundle or a reviewed real-execution failure bundle.
- Keep `phase5-readiness` in `plan_only` mode, and use the reviewed subprocess executor only after validation passes and `allow_process_submission` is explicitly set to `true`.
- Preserve all run/failure artifacts for any future real smoke attempt.
- Keep using `validate-run --run-id <run_id>` before accepting any recorded run artifact bundle.
- Use `poll --run-id <run_id>` and `parse-results --run-id <run_id>` only as recorded-artifact inspection steps until a real-smoke worker has produced validated outputs.
- Use `phase5-readiness --output-dir <dir>` as the consolidated safe readiness report before any future real-smoke attempt.
- Explicitly approve real GPU execution only after validation gates pass.

## Why Work Stops Here

The user instruction requires stopping at `needs_attention`. Continuing to Phase 6 would skip the first real-smoke gate and risk fabricating benchmark readiness or results.

## Boundaries

- No `.env` was read.
- No model was downloaded or loaded.
- No real benchmark was executed.
- No GPU job was started.
- No remote job or process was submitted by the readiness bundle.
- No raw output was written by the readiness bundle.
- No large artifact was committed.
