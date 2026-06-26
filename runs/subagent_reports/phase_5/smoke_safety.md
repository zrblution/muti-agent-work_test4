# Phase 5 Smoke Safety Report

- Repository inspected: `/home/vepfs/data/work1/muti-agent-work_test4` on SSH alias `server`
- Target smoke requested for assessment only: `qwen3_vl_2b_instruct + pope`, `limit=8`
- Safety constraints followed: did not read `.env`; did not download or load models; did not run real benchmarks, GPU jobs, or runner execution. Only CLI help, runner/source code, configs, and file presence were inspected.

## Verdict

Phase 5 should enter `needs_attention`, not proceed to a real smoke run.

The framework does not currently expose a safe structured real-smoke CLI command for `qwen3_vl_2b_instruct + pope --limit 8`. The only evaluation CLI surface is `run-eval`, and runner code restricts it to the in-repo fake model and fake benchmark. Remote action validation has a whitelisted action/script shape for future landmark work, but remote execution is intentionally disabled and the whitelisted landmark script is not present in the repository.

## Direct Answers

- Does `run-landmark` exist? **No.** `python -m stable_core.cli --help` lists `preflight`, `doctor`, `validate-config`, `list-models`, `list-benchmarks`, `list-agents`, `export-schemas`, `evidence`, `index-baselines`, `workflow`, `run-local`, `validate-model`, `validate-benchmark`, `run-eval`, and `research-status`; it does not list `run-landmark`. `stable_core/cli.py` likewise defines `run-local`, `validate-model`, `validate-benchmark`, and `run-eval`, but no `run-landmark` parser or handler.
- Is remote runner execution enabled? **No.** `project_config/server.yaml` sets `runner_mode: local_only`. `RemoteRunner.submit()` validates the action and then returns `status: needs_attention` with message `Remote execution is intentionally disabled in Phase 3.` `poll`, `resume`, and `cancel` also return `needs_attention` placeholders.
- Is there a safe structured real-smoke command for `qwen3_vl_2b_instruct + pope limit=8`? **No.** A structured validation shape exists in `RemoteAction`, but there is no executable CLI command and no enabled runner path for this real smoke.

## Evidence

### CLI surface

- `stable_core/cli.py:21-99` builds the argparse command set. It includes `run-local`, `validate-model`, `validate-benchmark`, and `run-eval`, but no `run-landmark`.
- `stable_core/cli.py:91-96` defines `run-eval --model --benchmark --limit --run-id --instrumentation`.
- `stable_core/cli.py:177-190` sends `run-eval` to `run_fake_eval(...)` and reports exceptions as failed CLI results.
- Observed help output from `PYTHONPATH=/home/vepfs/data/work1/muti-agent-work_test4 python -m stable_core.cli --help` confirmed the command list above and did not include `run-landmark`.

### Evaluation path is fake-only

- `experiments/fake/evaluator.py:59-69` implements `run_fake_eval(...)` and raises `ValueError("Phase 4 run-eval only supports fake_model with fake_benchmark.")` unless `model_id == "fake_model"` and `benchmark_id == "fake_benchmark"`.
- Therefore the apparent command shape `stable_core run-eval --model qwen3_vl_2b_instruct --benchmark pope --limit 8` is not a valid real-smoke command; the runner code rejects it before execution.

### Real model and benchmark adapters are validate-only

- `adapters/models/qwen3_vl.py:6-8` maps `qwen3_vl_2b_instruct` to `ValidateOnlyModelAdapter`.
- `adapters/models/_skeleton.py:17-31` validates configuration/path state without loading. `adapters/models/_skeleton.py:33-37` raises if `load()` or `generate()` is called.
- `adapters/benchmarks/pope.py:6-9` maps `pope` to `ValidateOnlyBenchmarkAdapter`.
- `adapters/benchmarks/_skeleton.py:17-28` validates path state without running sample parsing. `adapters/benchmarks/_skeleton.py:30-40` raises for `build_requests`, normalization, metrics, and failure extraction.
- `project_config/models.yaml:8-14` records `qwen3_vl_2b_instruct` as `needs_setup` with `path: null` and a note that no download/load is attempted.
- `project_config/benchmarks.yaml:6-10` records `pope` as `needs_setup` with `path: null`.

### Remote runner status

- `stable_core/runner/remote.py:9-20` whitelists remote action names including `run_model_smoke_test`.
- `stable_core/runner/remote.py:23-29` whitelists scripts including `experiments/landmark_baselines/run_landmark.py`.
- `stable_core/runner/remote.py:45-55` validates only the action name, script path safety/whitelist membership, and non-negative limit. It does not validate that the model/benchmark pair is executable or that the script exists.
- `stable_core/runner/remote.py:58-63` documents the remote runner as a placeholder where real SSH/GPU execution is deferred behind later gates.
- `stable_core/runner/remote.py:80-84` returns `needs_attention` instead of submitting remote work.
- `project_config/server.yaml:1-11` sets `runner_mode: local_only` even though it lists allowed remote action names.

### Landmark script presence

- `find /home/vepfs/data/work1/muti-agent-work_test4/experiments/landmark_baselines -maxdepth 2 -type f` returned only `.gitkeep`.
- `test -f /home/vepfs/data/work1/muti-agent-work_test4/experiments/landmark_baselines/run_landmark.py` exited non-zero.
- So the whitelisted `experiments/landmark_baselines/run_landmark.py` target is a future placeholder, not an available runnable script.

## Recommended Gate Decision

Set Phase 5 to `needs_attention` until all of the following exist and pass review without model loading during inspection:

1. A first-class structured CLI surface such as `run-landmark --model qwen3_vl_2b_instruct --benchmark pope --limit 8` or an equivalent subcommand with explicit choices and dry-run validation.
2. A present, reviewed `experiments/landmark_baselines/run_landmark.py` or equivalent controlled entry point.
3. Runner integration that records command manifest, config snapshot, env snapshot, git snapshot, stdout/stderr, exit code, failure diagnostics, and artifact manifest for real smoke attempts.
4. Explicit remote execution gating that distinguishes validation-only, dry-run, and real execution modes, with remote execution disabled by default unless the gate is intentionally opened.

## Follow-Up Status

After this read-only report, the main implementation added the structured `run-landmark` validation gate and then added `experiments/landmark_baselines/run_landmark.py` as the whitelisted worker entry point. The worker entry point is intentionally non-recursive and non-executing. It first records validation-gate failures when paths or inventory are missing, and after temporary valid inventory is present it now records `failure_type: landmark_worker_runtime_gate_not_ready` because Qwen3-VL still inherits validate-only `load` and `generate` runtime methods. POPE local sample parsing, normalization, metrics, and failure-case extraction are now implemented, but the worker still exits nonzero and does not load models, run benchmarks, start GPU work, or write raw outputs.

The original gate decision remains in force. Phase 5 still requires approved model and benchmark paths, a reviewed real-smoke worker implementation, process-submission authorization, and a validated real-smoke run or reviewed real-execution failure bundle before later phases can start.
