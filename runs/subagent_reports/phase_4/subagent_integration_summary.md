# Phase 4 Subagent Integration Summary

Status: integrated

## Inputs

- Spec: `06_MODELS_BENCHMARKS_EXPERIMENTS.md`
- Acceptance plan: `09_ACCEPTANCE_TESTS_AND_MVP.md`
- AdapterContracts report: `runs/subagent_reports/phase_4/adapter_contracts.md`
- FakeEvalFlow report: `runs/subagent_reports/phase_4/fake_eval_flow.md`
- SafetyReview report: `runs/subagent_reports/phase_4/safety_review.md`

## Findings Integrated

- `adapters/models/` was ignored by `.gitignore` because `models/` matched any directory named `models`.
- Fake eval needed explicit raw-output preservation behavior and repeat-run protection.
- Real model and benchmark adapters must remain validate-only in Phase 4.
- `validate-model` and `validate-benchmark` should validate selected `project_config` entries, not empty defaults.
- `run-eval` should reject bad input before writing artifacts.
- Secret scanning should include Phase 4 code paths and generated text/json run artifacts.

## Resolution

- Changed `.gitignore` from `models/` to `/models/` so source files under `adapters/models/` are visible while the repository-level model artifact directory remains ignored.
- Added `ModelAdapter` protocol and model adapters:
  - `FakeModelAdapter`
  - `Qwen3VLAdapter` validate-only skeleton
  - `InternVLAdapter` validate-only skeleton
- Added benchmark adapters:
  - `FakeBenchmarkAdapter`
  - `POPEAdapter` validate-only skeleton
  - `CHAIRAdapter` validate-only skeleton
  - `AMBERAdapter` validate-only skeleton
  - `MMEAdapter` validate-only skeleton
- Added fake evaluation runner in `experiments/fake/evaluator.py`.
- Added CLI commands:
  - `validate-model`
  - `validate-benchmark`
  - `run-eval`
- Added tests for fake model generation, fake benchmark requests/metrics, fake eval artifacts, raw-output overwrite protection, skeleton validate-only behavior, and config-driven validation.
- Expanded default preflight secret scan paths to include `adapters`, `experiments`, `idea_plugins`, `instrumentation`, `research_tools`, `scripts`, and `runs`.

## Environment Note

The original remote `server` SSH port `29575` began resetting during Phase 4. Phase 4 was implemented in a fresh local clone of the pushed GitHub repository and pushed back to `origin/main`. Phase 5 requires the server filesystem/GPU path and should first verify that `server` is reachable and pull this commit.

## Safety Boundaries

- No `.env` file was read.
- No model was downloaded or loaded.
- No real benchmark path was traversed or executed.
- `run-eval` only allows `fake_model + fake_benchmark`.
- The curated fake acceptance run is small text/json/markdown only.
