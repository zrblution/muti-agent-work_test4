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

Server variant discovery result: after the model-like classifier update, server discovery returned `needs_setup` with 27 candidates: 1 incomplete HF cache base, 8 output directories, and 18 `model_like_variant` directories with direct weight files under `/home/vepfs/data/LLM_HM_3_models`. None is usable with the current configured-root contract; each variant would require an explicit human decision before any config-path override or smoke attempt.

Variant direct validation result: each of the 18 server `model_like_variant` paths passed `Qwen3VLAdapter.validate_environment()` when used as an explicit `local_path`. This check did not load weights, download files, run generation, or mutate config. The blocker is therefore a policy/config decision: variants are technically present but are not approved substitutes for the configured base `Qwen3-VL-2B-Instruct` target.

Explicit model-path probe update: `phase5-probe-explicit-model-path --model <id> --benchmark <id> --model-path <path> --benchmark-root <path>` now validates an exact model path plus a benchmark root without requiring `REMOTE_MODEL_ROOT`. This is for review-only variant diagnostics; when the path does not match the configured `${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct` contract, the report sets `requires_human_approval: true`. It does not mutate config, export env vars, read `.env`, load weights, run generation, submit jobs, run benchmarks, or write raw outputs.

Server explicit-path probe result: probing `/home/vepfs/data/LLM_HM_3_models/output-model/Qwen3-VL-2B-3epoch/Ours` with benchmark root `/home/vepfs/data/work1/auto-research-test1/benchmarks` returned `passed` for no-load model validation, model runtime dependencies, benchmark inventory, and benchmark validation. The report also set `requires_human_approval: true` because the model path does not satisfy the configured base-model root contract; all execution safety flags remained false.

Model-path decision request update: `phase5-model-path-decision-request --model <id> --benchmark <id> --model-path <path> --benchmark-root <path> --output-dir <dir>` now writes a pending human-review packet around the explicit path probe. The packet records `approval_status: pending`, allowed decisions, an approval-record template, per-decision `decision_record_templates` for approve/reject/provide-base-root choices, the probe result, and all safety flags. It does not approve the path, mutate config, read `.env`, load weights, run generation, submit jobs, run benchmarks, or write raw outputs.

Server decision-request result: generating a packet for `/home/vepfs/data/LLM_HM_3_models/output-model/Qwen3-VL-2B-3epoch/Ours` with benchmark root `/home/vepfs/data/work1/auto-research-test1/benchmarks` wrote `/tmp/phase5_model_path_decision_request_server/phase5_model_path_decision_request.json` and `.md`. A committed copy now lives under `runs/needs_attention/phase_5_model_path_decision_request/` for review, with separate unfilled template files under `decision_record_templates/`. The JSON reports `status: needs_attention`, `approval_status: pending`, `probe.status: passed`, `requires_human_approval: true`, allowed decisions `approve_variant_path`, `reject_variant_path`, and `provide_base_model_root`, plus matching decision-record templates, with all execution safety flags false.

Model-path decision validation update: `phase5-validate-model-path-decision --request <decision_request.json> --decision-record <human_record.json> --output <report.json>` now validates a human-supplied decision record against a pending request. It can validate a matching approval record as `passed` but still does not mutate config, export env vars, open execution gates, read `.env`, load weights, run generation, submit jobs, run benchmarks, or write raw outputs. Rejection and base-root decisions remain `needs_attention`; invalid or mismatched approval records fail.

Committed current gate-audit update: `runs/needs_attention/phase_5_gate_audit_current/` now stores the current read-only gate audit package for the committed pending model-path decision request. The JSON and Markdown both report `next_missing_gate: model_path_decision_validation`, include the filled human decision-record handoff, point to `phase5-validate-model-path-decision`, record source artifact path plus sha256 provenance for the decision request, and preserve all no-execution safety flags.

Gate-audit verifier update: `phase5-verify-gate-audit --audit <phase5_gate_audit.json> --output <report.json>` now verifies a recorded Phase 5 gate audit package before human action. It checks the package identity, non-executing safety flags, structured `next_action_packet`, current existence plus sha256 of every recorded source artifact, and the sibling Markdown sidecar's critical human-facing fields. This is read-only and does not edit config, export env vars, open gates, read `.env`, load weights, run generation, submit jobs, run benchmarks, or write raw outputs.

Approved-decision readiness update: `phase5-approved-decision-readiness --decision-validation <report.json> --output-dir <dir>` now turns a validated approval report into a non-executing readiness bundle. It records the approved exact paths and next actions for config representation review, but always sets `ready_for_real_smoke: false` because remote/GPU/process gates and reviewed config representation must still be handled separately. It does not mutate config, export env vars, open execution gates, read `.env`, load weights, run generation, submit jobs, run benchmarks, or write raw outputs.

Config representation proposal update: `phase5-config-representation-proposal --approved-readiness <report.json> --output-dir <dir>` now writes a read-only proposal for representing approved exact paths. It reports whether the approved model path satisfies the existing `${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct` contract, proposes benchmark root env representation, lists reviewable model representation options such as explicit local path override or materializing under the configured root, and emits per-option decision-record templates for the next validation step. It does not edit `project_config`, export env vars, open execution gates, read `.env`, load weights, run generation, submit jobs, run benchmarks, or write raw outputs.

Config representation decision validation update: `phase5-validate-config-representation-decision --proposal <proposal.json> --decision-record <human_record.json> --output <report.json>` now validates an external human choice against the config representation proposal. It verifies the selected option is declared by the proposal, the reviewer and rationale are present, and the approved model path plus benchmark root match the selected option exactly. It does not edit `project_config`, export env vars, open execution gates, read `.env`, load weights, run generation, submit jobs, run benchmarks, or write raw outputs, and it keeps `ready_for_real_smoke: false`.

Gate audit update: `phase5-gate-audit --model <id> --benchmark <id> --limit <n> --instrumentation <mode> [artifact paths...] --output <report.json>` now consolidates the Phase 5 review chain into a read-only gate report. It identifies the next missing or incomplete gate across model-path decision request, model-path decision validation, approved-decision readiness, config representation proposal, config representation decision validation, Phase 5 readiness, and final real-smoke evidence. It records source artifact paths and sha256 hashes for supplied review/readiness JSON files so handoff packages can be checked for drift. It can also write a reviewable JSON plus Markdown package with `--output-dir <dir>`, including a structured `next_action_packet` with required human inputs, safe command templates, expected artifacts, and forbidden actions for the next gate. When a pending model-path decision request is already present, the packet points to the required filled human decision record, the non-executing `phase5-validate-model-path-decision` command template, and the committed template directory as a handoff aid. When a validated approval is present but approved-decision readiness is missing, the packet points to `phase5-approved-decision-readiness` and explicitly forbids treating approval as permission to run. When approved-decision readiness exists but config representation proposal is missing, the packet points to `phase5-config-representation-proposal` and forbids applying approved paths to config or env vars from the audit. When the config proposal exists, the packet points to `phase5-validate-config-representation-decision`; when that decision validation exists, it points to the non-executing `phase5-readiness` bundle; when readiness passes but no run evidence is supplied, it points to `validate-run` plus a final `phase5-gate-audit --smoke-run-id` handoff. It does not edit `project_config`, export env vars, open execution gates, read `.env`, load weights, run generation, submit jobs, run benchmarks, or write raw outputs, and it keeps `ready_for_real_smoke: false`.

Final run-bundle audit update: `phase5-gate-audit --smoke-run-id <run_id> --runs-root <runs_root>` can now validate the final Phase 5 run evidence after the review/readiness chain. It accepts a recorded success bundle as `phase5_terminal_outcome: validated_real_smoke_success`, accepts only `landmark_worker_execution_failed` as a reviewed real-execution failure bundle, and keeps validation/runtime/setup gate failures incomplete as `next_missing_gate: real_smoke_result`. This is a read-only validation step; it does not run, rerun, or mutate the recorded run.

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
- server `phase5-discover-model-candidates` after variant classification: `needs_setup`, candidate count `27`, candidate types `hf_cache_base: 1`, `run_output_dir: 8`, `model_like_variant: 18`, all execution flags false
- direct no-load validation of all 18 server `model_like_variant` paths: `passed`; no model load, generation, config mutation, job submission, or raw output write
- `phase5-probe-explicit-model-path` with a temporary qwen-like variant path, temporary POPE root, and monkeypatched runtime modules: `passed`, `requires_human_approval: true`, all safety flags false, and no raw outputs
- `build_phase5_explicit_model_path_probe(...)` with existing caller environment values: restores `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT` after validation
- server `phase5-probe-explicit-model-path` for variant `/home/vepfs/data/LLM_HM_3_models/output-model/Qwen3-VL-2B-3epoch/Ours` and POPE benchmark root: `passed`, `requires_human_approval: true`, all execution flags false
- `phase5-model-path-decision-request` with a temporary qwen-like variant path, temporary POPE root, and monkeypatched runtime modules: writes JSON and Markdown decision-request artifacts with `status: needs_attention`, `approval_status: pending`, per-decision record templates for approve/reject/provide-base-root choices, `probe.status: passed`, `requires_human_approval: true`, and all execution safety flags false
- `build_phase5_model_path_decision_request(...)` with existing caller environment values: restores `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT`, keeps `write_config: false`, and records no approval
- server `phase5-model-path-decision-request` for variant `/home/vepfs/data/LLM_HM_3_models/output-model/Qwen3-VL-2B-3epoch/Ours` and POPE benchmark root: wrote JSON and Markdown decision artifacts under `/tmp/phase5_model_path_decision_request_server`, with `status: needs_attention`, `approval_status: pending`, `probe.status: passed`, `requires_human_approval: true`, and all execution flags false
- committed `runs/needs_attention/phase_5_model_path_decision_request/phase5_model_path_decision_request.json`: `approval_status: pending`, `probe.status: passed`, `requires_human_approval: true`, all execution safety flags false, and accepted by `phase5-gate-audit` as the model-path decision-request gate while still stopping at `model_path_decision_validation`
- `phase5-gate-audit` with the committed pending decision request: `next_action_packet.gate` is `model_path_decision_validation`, the packet lists the pending request, a filled human decision record, the validation output, the `phase5-validate-model-path-decision` command template, and a forbidden action against treating unfilled templates as approval
- committed `runs/needs_attention/phase_5_gate_audit_current/phase5_gate_audit.json` and `.md`: `needs_attention`, next missing gate `model_path_decision_validation`, current `next_action_packet` points to the filled human decision-record validation handoff, `source_artifacts.model_path_decision_request` records the decision request sha256, and all execution safety flags remain false
- `phase5-verify-gate-audit` with the committed current handoff: `passed`, source artifact count `1`, package identity/next-action/safety/source-artifact/Markdown-sidecar checks passed, and all execution safety flags remained false; with a copied audit whose source-artifact sha256 was stale, the verifier returned `failed` with expected and actual sha256 values; with a copied package whose Markdown sidecar had a stale `next_missing_gate`, the verifier returned `failed`
- committed `runs/needs_attention/phase_5_model_path_decision_request/decision_record_templates/*.template.json`: extracted unfilled approve/reject/provide-base-root decision templates; unfilled approval/base-root templates fail validation until a human fills `approver`, `rationale`, and required decision fields
- `phase5-validate-model-path-decision` with a temporary matching human approval record: `passed`, `approval_status: approved`, exact model path and benchmark root checks passed, all execution safety flags false, and no raw outputs
- `validate_phase5_model_path_decision(...)` with a mismatched approved model path: `failed`, `approval_status: invalid`, mismatch check failed, benchmark-root match passed, and no config write
- `phase5-gate-audit` with temporary decision request and validated model-path approval but no approved-decision readiness bundle: `next_action_packet.gate` is `approved_decision_readiness`, the packet lists the decision-validation report, output directory, `phase5-approved-decision-readiness` command template, expected readiness JSON/Markdown, and a forbidden action against treating approval as run permission
- `phase5-approved-decision-readiness` with a temporary approved validation report: writes JSON and Markdown readiness artifacts with `status: needs_attention`, `approval_status: approved`, `ready_for_real_smoke: false`, approved paths recorded, and all execution safety flags false
- `phase5-gate-audit` with temporary decision request, validated model-path approval, and approved-decision readiness but no config representation proposal: `next_action_packet.gate` is `config_representation_proposal`, the packet lists the approved readiness bundle, output directory, `phase5-config-representation-proposal` command template, expected proposal JSON/Markdown, and a forbidden action against applying paths to config or env vars
- `phase5-gate-audit` with temporary review-chain artifacts through config representation proposal but no config decision validation: `next_action_packet.gate` is `config_representation_decision`, the packet lists the proposal, filled config decision record, validation output, `phase5-validate-config-representation-decision` command template, and config/env mutation forbidden action
- `phase5-gate-audit` with temporary review-chain artifacts through config representation decision validation but no readiness bundle: `next_action_packet.gate` is `phase5_readiness`, the packet lists the reviewed config/env representation, readiness output directory, `phase5-readiness` command template, expected readiness JSON/Markdown, and process/raw-output forbidden action
- `phase5-gate-audit` with temporary review-chain artifacts through passed readiness but no smoke run id: `next_action_packet.gate` is `real_smoke_result`, the packet lists the controlled worker run id, runs root, validated artifact bundle, `validate-run` handoff, final `--smoke-run-id` audit command, and process/raw-output forbidden action
- `build_phase5_approved_decision_readiness(...)` with an invalid validation report: writes a `failed` readiness artifact with `ready_for_real_smoke: false` and no config write
- `phase5-config-representation-proposal` with a temporary approved readiness report: writes JSON and Markdown proposal artifacts with `status: needs_attention`, `ready_for_real_smoke: false`, `write_config: false`, `exports_applied: false`, benchmark env proposal, model representation options requiring review, and decision-record templates for the next validator
- `build_phase5_config_representation_proposal(...)` with an invalid approved-readiness report: writes a `failed` proposal artifact with `ready_for_real_smoke: false` and no config write
- `phase5-validate-config-representation-decision` with a temporary proposal and matching explicit override decision record: `passed`, `config_review_status: approved`, selected option `explicit_local_path_override`, `ready_for_real_smoke: false`, `write_config: false`, `exports_applied: false`, and all execution safety flags false
- `validate_phase5_config_representation_decision(...)` with a mismatched approved model path: `failed`, `config_review_status: invalid`, model-path check failed, benchmark-root check passed, and no config/env/execution change
- `phase5-gate-audit` with no review artifact paths: `needs_attention`, next missing gate `model_path_decision_request`, `ready_for_real_smoke: false`, no config write, no env export, no execution, and no raw outputs
- `phase5-gate-audit --output-dir` with no review artifact paths: writes `phase5_gate_audit.json` and `phase5_gate_audit.md`, both reporting `needs_attention`, next missing gate `model_path_decision_request`, a `next_action_packet` for generating the model-path decision request, `ready_for_real_smoke: false`, no config write, no env export, no execution, and no raw outputs
- `phase5-gate-audit` with temporary review-chain artifacts but a `needs_attention` readiness bundle: `needs_attention`, review-chain checks passed through config representation decision validation, next missing gate `phase5_readiness`, and all execution safety flags false
- `phase5-gate-audit --smoke-run-id` with temporary passed review-chain artifacts and a validated `landmark_worker_execution_failed` run bundle: `needs_attention`, `next_missing_gate: none`, `phase5_terminal_outcome: reviewed_real_execution_failure`, and no new raw outputs from the audit
- `phase5-gate-audit --smoke-run-id` with temporary passed review-chain artifacts and a validation-gate `landmark_worker_validation_gate_not_ready` bundle: `needs_attention`, `next_missing_gate: real_smoke_result`, `phase5_terminal_outcome: none`, proving setup failures are not accepted as reviewed real-execution failures
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

The current committed gate-audit handoff is stored in `runs/needs_attention/phase_5_gate_audit_current/`.

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
- Use `phase5-probe-explicit-model-path` only for review-only variant diagnostics; do not use a variant path for the first real smoke without explicit approval and a reviewed config representation.
- Use `phase5-model-path-decision-request` to create a pending approval packet for any exact variant path being considered; the packet is not itself an approval.
- Use `phase5-validate-model-path-decision` to validate an external human decision record before changing config representation or opening any execution gate.
- Use `phase5-approved-decision-readiness` after a validated approval to generate the non-executing config-review and gate checklist; do not treat it as permission to run.
- Use `phase5-config-representation-proposal` to review how approved paths could be represented before editing `project_config` or exporting env vars.
- Use `phase5-validate-config-representation-decision` to validate the external config representation decision before any config edit or env export; a passed validation is still not permission to execute the smoke.
- Use `phase5-gate-audit` to identify the next missing or incomplete Phase 5 gate before any config edit, env export, gate opening, readiness run, or real smoke attempt; after readiness passes, use its real-smoke-result packet to validate recorded worker evidence before accepting any outcome.
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
