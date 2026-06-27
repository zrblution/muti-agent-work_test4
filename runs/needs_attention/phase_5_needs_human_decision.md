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
- `phase5-model-path-decision-request` can now package an exact-path probe into a JSON and Markdown decision request with `approval_status: pending`, allowed decisions, an approval-record template, and per-decision `decision_record_templates` for approve/reject/provide-base-root choices. This is still review-only and does not approve a path, mutate config, run a model, run a benchmark, submit a job, or write raw outputs.
- Server packet generation for `/home/vepfs/data/LLM_HM_3_models/output-model/Qwen3-VL-2B-3epoch/Ours` plus `/home/vepfs/data/work1/auto-research-test1/benchmarks` wrote a committed pending-review copy under `runs/needs_attention/phase_5_model_path_decision_request/`. The packet is still `approval_status: pending`, with `probe.status: passed`, `requires_human_approval: true`, separate unfilled `decision_record_templates/*.template.json` files for all allowed choices, and all execution safety flags false.
- `phase5-validate-model-path-decision` can now validate a human-supplied decision record against the pending request. A matching approval record can validate as `passed`, but this command still does not approve by itself, mutate config, open execution gates, load a model, run a benchmark, submit a job, or write raw outputs.
- `phase5-approved-decision-readiness` can now create a non-executing readiness bundle from a validated approval report. It records approved exact paths and next actions, but keeps `ready_for_real_smoke: false` until config representation, readiness, and execution gates are reviewed.
- `runs/needs_attention/phase_5_gate_audit_current/` now stores the current committed gate-audit package for the pending model-path decision request. It reports `next_missing_gate: model_path_decision_validation`, lists the filled human decision-record input, and points to the non-executing `phase5-validate-model-path-decision` handoff.
- `phase5-config-representation-proposal` can now propose how approved paths could be represented in config or env without editing `project_config`, exporting env vars, opening gates, loading a model, running a benchmark, submitting a job, or writing raw outputs. It also emits per-option `decision_record_templates` that can be filled and passed to the config-representation decision validator.
- `phase5-validate-config-representation-decision` can now validate an external human selection from the config representation proposal. A matching decision record can validate as `passed`, but the command still does not edit config, export env vars, open gates, load a model, run a benchmark, submit a job, or write raw outputs.
- `phase5-gate-audit` can now consolidate the review chain and report the next missing or incomplete Phase 5 gate without editing config, exporting env vars, opening gates, loading a model, running a benchmark, submitting a job, or writing raw outputs. It can write a JSON plus Markdown audit package with `--output-dir`, including a `next_action_packet` for the required inputs, safe command template, expected artifacts, and forbidden actions for the next gate. With the committed pending decision request, that packet points to the filled human decision record and the safe `phase5-validate-model-path-decision` handoff. After a validated model-path approval, it points to the non-executing `phase5-approved-decision-readiness` handoff and forbids treating approval as permission to run. After approved-decision readiness, it points to the read-only `phase5-config-representation-proposal` handoff and forbids applying approved paths to config or env vars from the audit. After the config proposal, it points to `phase5-validate-config-representation-decision`; after config decision validation, it points to the non-executing `phase5-readiness` bundle; after readiness passes, it points to recorded run validation and final `--smoke-run-id` audit evidence. It can also validate an optional final run bundle with `--smoke-run-id` / `--runs-root`.

## Human Decisions Required

- Provide approved server environment values for `REMOTE_MODEL_ROOT` and `REMOTE_BENCHMARK_ROOT` without committing secrets or large artifacts.
- Review `phase5-discover-model-candidates` output before approving any `REMOTE_MODEL_ROOT` value.
- Decide whether any `model_like_variant` path is an acceptable substitute for the configured base `Qwen3-VL-2B-Instruct`; do not treat variants as the Phase 5 target without explicit approval.
- If the committed variant packet is being considered, review `runs/needs_attention/phase_5_model_path_decision_request/phase5_model_path_decision_request.json` and fill exactly one file under `runs/needs_attention/phase_5_model_path_decision_request/decision_record_templates/` for `approve_variant_path`, `reject_variant_path`, or `provide_base_model_root`.
- Review `runs/needs_attention/phase_5_gate_audit_current/phase5_gate_audit.md` as the current committed gate handoff before filling or validating any human decision record.
- Run `phase5-gate-audit` with the committed decision request and inspect `next_action_packet` before validation; it must identify `model_path_decision_validation`, the filled decision record input, and the non-executing validation command. Do not treat an unfilled `.template.json` file as approval.
- Validate the filled model-path decision record with `phase5-validate-model-path-decision` before updating config representation or opening execution gates.
- Run `phase5-gate-audit` after model-path decision validation and inspect `next_action_packet`; if it identifies `approved_decision_readiness`, generate that bundle before any config representation work. Do not treat validated model-path approval as permission to run the real smoke.
- Generate `phase5-approved-decision-readiness` after a validated approval to review exact paths and remaining gate actions before any config or process-submission change.
- Run `phase5-gate-audit` after approved-decision readiness and inspect `next_action_packet`; if it identifies `config_representation_proposal`, generate the read-only proposal before any config edit or env export.
- Generate `phase5-config-representation-proposal` before editing `project_config` or exporting `REMOTE_MODEL_ROOT` / `REMOTE_BENCHMARK_ROOT`.
- Run `phase5-gate-audit` after config representation proposal and inspect `next_action_packet`; if it identifies `config_representation_decision`, fill exactly one config proposal decision record and validate it before any config edit or env export.
- Fill one `decision_record_templates` entry from the config representation proposal, then validate it with `phase5-validate-config-representation-decision` before any config edit or env export; a passed validation is review evidence only and does not authorize real smoke execution.
- Run `phase5-gate-audit` after config representation decision validation and inspect `next_action_packet`; if it identifies `phase5_readiness`, run only the non-executing `phase5-readiness` bundle before any process-submission change.
- Run `phase5-gate-audit` after readiness passes and inspect `next_action_packet`; if it identifies `real_smoke_result`, collect a controlled worker run id and validate the recorded artifact bundle before accepting any Phase 5 outcome.
- Run `phase5-gate-audit` after each review-chain artifact is produced to identify the next missing or incomplete gate and inspect its `next_action_packet` before any config edit, env export, or execution attempt.
- After a controlled worker run exists, rerun `phase5-gate-audit` with `--smoke-run-id <run_id> --runs-root <runs_root>` so the final evidence is classified as a validated real-smoke success, a reviewed `landmark_worker_execution_failed` bundle, or still incomplete setup/runtime failure.
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
python -m stable_core.cli phase5-validate-model-path-decision --request /tmp/phase5_model_path_decision_request/phase5_model_path_decision_request.json --decision-record <human_decision_record.json> --output /tmp/phase5_model_path_decision_validation.json
python -m stable_core.cli phase5-approved-decision-readiness --decision-validation /tmp/phase5_model_path_decision_validation.json --output-dir /tmp/phase5_approved_decision_readiness
python -m stable_core.cli phase5-config-representation-proposal --approved-readiness /tmp/phase5_approved_decision_readiness/phase5_approved_decision_readiness.json --output-dir /tmp/phase5_config_representation_proposal
python -m stable_core.cli phase5-validate-config-representation-decision --proposal /tmp/phase5_config_representation_proposal/phase5_config_representation_proposal.json --decision-record <human_config_representation_decision.json> --output /tmp/phase5_config_representation_decision_validation.json
python -m stable_core.cli phase5-gate-audit --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --decision-request /tmp/phase5_model_path_decision_request/phase5_model_path_decision_request.json --decision-validation /tmp/phase5_model_path_decision_validation.json --approved-readiness /tmp/phase5_approved_decision_readiness/phase5_approved_decision_readiness.json --config-proposal /tmp/phase5_config_representation_proposal/phase5_config_representation_proposal.json --config-decision-validation /tmp/phase5_config_representation_decision_validation.json --readiness /tmp/phase5_readiness/phase5_readiness.json --smoke-run-id <controlled_worker_run_id> --runs-root <runs_root> --output-dir /tmp/phase5_gate_audit
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
