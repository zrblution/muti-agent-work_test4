# Phase 5 Patch Summary

Status: `needs_attention`

## Scope

This phase now contains two related records:

- the original audited Phase 5 stop condition for the first real smoke target;
- a follow-up framework improvement adding a structured `run-landmark` validation gate that still stops safely at `needs_attention`.
- a follow-up config improvement resolving `${REMOTE_MODEL_ROOT}` and `${REMOTE_BENCHMARK_ROOT}` path templates without reading `.env`.
- a follow-up inventory improvement that rejects empty model and benchmark directories before any real execution can start.
- a follow-up run-artifact validator for auditing recorded run directories without re-running models or benchmarks.
- a follow-up failure-diagnostics improvement for `run-landmark` `needs_attention` bundles.
- a follow-up config-driven remote execution gate that keeps real execution closed by default.
- a follow-up reviewable remote execution plan for open config gates, still with no process submission.
- a follow-up branch-specific diagnostic for the path where model and benchmark validation pass but remote execution remains closed.
- a follow-up recorded-run lifecycle CLI for `poll` and `parse-results`, still with no model, benchmark, or job execution.
- a follow-up whitelisted landmark worker entry point that records `needs_attention` without re-entering the top-level gate or executing real model/benchmark work.

- model: `qwen3_vl_2b_instruct`
- benchmark: `pope`
- limit: `8`
- instrumentation: `none`

## Code Added After Initial Stop

- `experiments/landmark_baselines/runner.py`
- `experiments/landmark_baselines/__init__.py`
- `stable_core.cli run-landmark`
- `tests/test_landmark_gate.py`
- `adapters/path_resolution.py`
- `adapters/inventory.py`
- `stable_core.storage.run_validator`
- `stable_core.cli validate-run`
- path-template handling in validate-only model and benchmark skeletons
- offline model inventory validation requiring `config.json` by default
- offline benchmark inventory discovery for shallow metadata/sample files
- recorded run validation for manifests, declared outputs, failure artifacts, and artifact hashes
- `run-landmark` `failure.json` now includes log tails, reproduction command, config snapshot, and state snapshot
- `RemoteRunner.submit()` now reports `runner_mode` and `allow_real_gpu_jobs` gate failures from config
- `RemoteRunner.submit()` now returns a whitelisted `execution_plan` with `submits_process: false` when config gates are open in tests
- `RemoteRunner.submit()` reviewable plans now target `experiments/landmark_baselines/run_landmark.py` directly instead of recursively invoking `stable_core.cli run-landmark`
- `experiments/landmark_baselines/run_landmark.py` now exists as a controlled non-executing worker stub that records `landmark_worker_not_implemented`
- `run-landmark` now records remote-gate-specific recommended next actions once model and benchmark validation pass
- `stable_core.storage.run_results` reads recorded run manifests and metrics without recomputation
- `stable_core.cli poll`
- `stable_core.cli parse-results`

## Gate Commands

- `python -m stable_core.cli validate-config`
  - exit code: `0`
  - status: `passed`
  - log: `runs/phase_5_gate_logs/validate_config.json`
- `python -m stable_core.cli preflight --dry-run`
  - exit code: `0`
  - status: `needs_setup`
  - log: `runs/phase_5_gate_logs/preflight_dry_run.json`
- `python -m stable_core.cli validate-model qwen3_vl_2b_instruct`
  - exit code: `0`
  - status: `needs_setup`
  - log: `runs/phase_5_gate_logs/validate_model_qwen3_vl.json`
- `python -m stable_core.cli validate-benchmark pope`
  - exit code: `0`
  - status: `needs_setup`
  - log: `runs/phase_5_gate_logs/validate_benchmark_pope.json`
- `python -m stable_core.cli run-landmark --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none`
  - exit code: `2`
  - stderr: `runs/phase_5_gate_logs/run_landmark_attempt.stderr`
- `python -m stable_core.cli run-landmark --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --run-id qwen3vl_pope_limit8_gate`
  - exit code: `1`
  - status: `needs_attention`
  - log: `runs/phase_5_gate_logs/run_landmark_gate.json`
- `python -m stable_core.cli validate-run --run-id qwen3vl_pope_limit8_gate`
  - exit code: `0`
  - status: `passed`
- `python -m stable_core.cli run-landmark --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --run-id qwen_pope_gate_diagnostic_check`
  - exit code: `1`
  - status: `needs_attention`
  - purpose: verify enhanced failure diagnostics on a temporary run directory
- `python -m stable_core.cli validate-run --run-id qwen_pope_gate_diagnostic_check`
  - exit code: `0`
  - status: `passed`
- `python -m stable_core.cli run-landmark --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --run-id qwen3vl_pope_limit8_gate_diagnostics`
  - exit code: `1`
  - status: `needs_attention`
  - artifact: `runs/qwen3vl_pope_limit8_gate_diagnostics/`
- `python -m stable_core.cli validate-run --run-id qwen3vl_pope_limit8_gate_diagnostics`
  - exit code: `0`
  - status: `passed`
- `python -m stable_core.cli poll --run-id qwen3vl_pope_limit8_gate_diagnostics`
  - status: recorded run status `needs_attention`
- `python -m stable_core.cli parse-results --run-id qwen3vl_pope_limit8_gate_diagnostics`
  - status: `needs_attention`
  - purpose: inspect the validated artifact bundle without recomputing missing benchmark metrics
- `python experiments/landmark_baselines/run_landmark.py --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --run-id <temporary> --runs-root <temporary>`
  - exit code: `1`
  - status: `needs_attention`
  - failure type: `landmark_worker_not_implemented`

## Artifacts Added

- `runs/phase_5_gate_logs/`
- `runs/subagent_reports/phase_5/`
- `runs/qwen3vl_pope_limit8_needs_attention/`
- `runs/qwen3vl_pope_limit8_gate/`
- `runs/qwen3vl_pope_limit8_gate_diagnostics/`
- `runs/needs_attention/phase_5_needs_human_decision.md`
- `docs/verification/phase_5_acceptance_report.md`

## Verification

- Expanded secret scan over docs, config, code, tests, scripts, runs, adapters, experiments, idea plugins, instrumentation, and top-level metadata passed.
- `python -m pytest tests/test_landmark_gate.py tests/test_fake_runner.py tests/test_runner.py tests/test_state_machine.py -q`: `14 passed`.
- `python -m pytest tests/test_fake_adapters.py -q`: `7 passed`.
- `python -m pytest tests/test_landmark_gate.py -q`: `3 passed`.
- `python -m pytest tests/test_runner.py tests/test_landmark_gate.py tests/test_fake_adapters.py -q`: `17 passed`.
- `python -m pytest tests/test_runner.py -q`: `10 passed`.
- `python -m pytest tests/test_landmark_gate.py tests/test_runner.py -q`: `13 passed`.
- `python -m pytest tests/test_runner.py -q`: `13 passed` after adding `poll` and `parse-results`.
- `python -m pytest tests/test_runner.py tests/test_landmark_gate.py -q`: `16 passed` after adding `poll` and `parse-results`.
- `python -m pytest tests/test_landmark_gate.py -q`: `2 passed` after the failure-diagnostics assertion update.
- `python -m pytest -q`: `56 passed`.
- `python -m pytest -q`: `59 passed` after adding `poll` and `parse-results`.
- `python -m pytest tests/test_runner.py::test_remote_runner_builds_reviewable_execution_plan_when_config_gates_open tests/test_runner.py::test_remote_runner_execution_plan_targets_existing_non_recursive_worker tests/test_landmark_gate.py::test_landmark_worker_script_records_needs_attention_without_reentering_gate -q`: `3 passed` after adding the worker stub.
- `python -m pytest tests/test_runner.py tests/test_landmark_gate.py -q`: `18 passed` after adding the worker stub.
- `python -m pytest -q`: `61 passed` after adding the worker stub.
- `python -m stable_core.cli validate-run --run-id qwen_worker_manual_check --runs-root /tmp/qwen_worker_manual_check_runs`: `passed`.
- `python -m stable_core.cli parse-results --run-id qwen_worker_manual_check --runs-root /tmp/qwen_worker_manual_check_runs`: `needs_attention` with artifact validation `passed`.
- `python -m stable_core.cli validate-config`: `passed`.
- Expanded secret scan after adding `poll` and `parse-results`: `passed`, no findings.
- Expanded secret scan after adding the worker stub: `passed`, no findings.
- Large-file scan after adding `poll` and `parse-results`: no files over 5 MB found.
- Large-file scan after adding the worker stub: no files over 5 MB found.
- `RemoteRunner().submit(...)`: `needs_attention` with `runner_mode: local_only` and `allow_real_gpu_jobs: false`.
- CLI validation with unset path env vars reports the missing env var names.
- CLI validation with temporary existing but empty model and benchmark directories returns `needs_setup` at the inventory gate.
- CLI validation with temporary model `config.json` and benchmark `samples.jsonl` returns `passed`.
- CLI `validate-run` passes for `qwen3vl_pope_limit8_gate` and `fake_phase4_acceptance`.
- No file over 5 MB was added.
- No `.env` file was read.
- No model was downloaded or loaded.
- No real benchmark or GPU job was run.
