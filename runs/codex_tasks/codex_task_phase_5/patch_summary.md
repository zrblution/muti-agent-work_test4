# Phase 5 Patch Summary

Status: `needs_attention`

## Scope

This phase now contains two related records:

- the original audited Phase 5 stop condition for the first real smoke target;
- a follow-up framework improvement adding a structured `run-landmark` validation gate that still stops safely at `needs_attention`.
- a follow-up config improvement resolving `${REMOTE_MODEL_ROOT}` and `${REMOTE_BENCHMARK_ROOT}` path templates without reading `.env`.

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
- path-template handling in validate-only model and benchmark skeletons

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

## Artifacts Added

- `runs/phase_5_gate_logs/`
- `runs/subagent_reports/phase_5/`
- `runs/qwen3vl_pope_limit8_needs_attention/`
- `runs/qwen3vl_pope_limit8_gate/`
- `docs/verification/phase_5_acceptance_report.md`

## Verification

- Expanded secret scan over docs, config, code, tests, scripts, runs, adapters, experiments, idea plugins, instrumentation, and top-level metadata passed.
- `python -m pytest tests/test_landmark_gate.py tests/test_fake_runner.py tests/test_runner.py tests/test_state_machine.py -q`: `14 passed`.
- `python -m pytest tests/test_fake_adapters.py -q`: `6 passed`.
- `python -m pytest -q`: `48 passed`.
- CLI validation with unset path env vars reports the missing env var names.
- CLI validation with temporary existing model and benchmark directories returns `passed`.
- No file over 5 MB was added.
- No `.env` file was read.
- No model was downloaded or loaded.
- No real benchmark or GPU job was run.
