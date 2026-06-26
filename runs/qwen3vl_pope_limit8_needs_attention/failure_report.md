# Phase 5 Failure Report

Status: `needs_attention`

## Current Phase

Phase 5: Minimal Real Smoke, `qwen3_vl_2b_instruct + pope`, `limit=8`.

## Result

The real smoke was not run. The framework stopped before model loading, benchmark execution, or GPU work.

## Failed Or Blocking Commands

- `python -m stable_core.cli preflight --dry-run`
  - exit code: `0`
  - payload status: `needs_setup`
  - log: `runs/phase_5_gate_logs/preflight_dry_run.json`
- `python -m stable_core.cli validate-model qwen3_vl_2b_instruct`
  - exit code: `0`
  - payload status: `needs_setup`
  - log: `runs/phase_5_gate_logs/validate_model_qwen3_vl.json`
- `python -m stable_core.cli validate-benchmark pope`
  - exit code: `0`
  - payload status: `needs_setup`
  - log: `runs/phase_5_gate_logs/validate_benchmark_pope.json`
- `python -m stable_core.cli run-landmark --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none`
  - exit code: `2`
  - stderr: `runs/phase_5_gate_logs/run_landmark_attempt.stderr`

## Root Cause Hypothesis

- `qwen3_vl_2b_instruct` has no configured local model path.
- `pope` has no configured benchmark path.
- The project currently has validate-only real adapter skeletons.
- `run-landmark` is not implemented in `stable_core.cli`.
- Remote runner execution remains disabled: `server.runner_mode` is `local_only`, `RemoteRunner.submit()` returns `needs_attention`, and real GPU jobs are disabled in the experiment budget.

## Fix Suggestions

- Configure approved local model and benchmark paths through `project_config` or environment-derived config without committing secrets.
- Add offline model-path validation for Qwen3-VL files before any load smoke.
- Add offline POPE path/sample validation before request building.
- Implement a structured `run-landmark` command or equivalent controlled runner entry point.
- Preserve stdout, stderr, env snapshot, git snapshot, command manifest, run manifest, and failure artifacts for any future real smoke attempt.

## Why Phase 6 Should Not Start Yet

The user rules require stopping at `needs_attention`. Continuing would either skip the first real-smoke gate or fabricate model/benchmark success. No real benchmark result is available.
