# Phase 4 Patch Summary

Status: passed

## Scope

- Added model adapter protocol and fake/validate-only model adapters under `adapters/models/`.
- Added fake and validate-only benchmark adapters under `adapters/benchmarks/`.
- Added fake in-process evaluation runner under `experiments/fake/`.
- Extended config with `fake_model`, `fake_benchmark`, and adapter paths.
- Added CLI commands: `validate-model`, `validate-benchmark`, and `run-eval`.
- Added curated fake run artifacts under `runs/fake_phase4_acceptance/`.
- Added Phase 4 tests in `tests/test_fake_adapters.py` and `tests/test_fake_runner.py`.
- Expanded default secret scan coverage for new code paths and run metadata.

## Verification

- Red-state checkpoint:
  - `python -m pytest tests/test_fake_adapters.py tests/test_fake_runner.py -q`
  - Result before implementation: failed collection with missing fake adapter and evaluator modules.
- Focused Phase 4 tests:
  - `/tmp/maes_phase4_venv312/bin/python -m pytest tests/test_fake_adapters.py tests/test_fake_runner.py tests/test_architecture_contracts.py tests/test_config_cli.py -q`
  - Result: `18 passed`.
- Full suite:
  - `/tmp/maes_phase4_venv312/bin/python -m pytest -q`
  - Result: `44 passed`.
- Compile check:
  - `/tmp/maes_phase4_venv312/bin/python -m py_compile adapters/models/base.py adapters/models/_skeleton.py adapters/models/fake.py adapters/models/qwen3_vl.py adapters/models/internvl.py adapters/benchmarks/_skeleton.py adapters/benchmarks/fake.py adapters/benchmarks/pope.py adapters/benchmarks/chair.py adapters/benchmarks/amber.py adapters/benchmarks/mme.py experiments/fake/evaluator.py stable_core/cli.py stable_core/validation/preflight.py`
  - Result: passed.
- CLI smoke:
  - `validate-model fake_model`: passed.
  - `validate-model qwen3_vl_2b_instruct`: `needs_setup`, with no download/load attempted.
  - `validate-benchmark fake_benchmark`: passed.
  - `validate-benchmark pope`: `needs_setup`, with no benchmark execution attempted.
  - `run-eval --model fake_model --benchmark fake_benchmark --limit 3 --run-id fake_phase4_acceptance`: succeeded.
- Secret scan:
  - `/tmp/maes_phase4_venv312/bin/python -m stable_core.security.secret_scan --paths docs project_config stable_core research_tools evidence tests scripts runs adapters experiments idea_plugins instrumentation .env.example .gitignore AGENTS.md README.md --output runs/preflight/secret_scan_report.json`
  - Result: exited `0`.

## Artifacts

- `runs/fake_phase4_acceptance/raw_outputs.jsonl`
- `runs/fake_phase4_acceptance/normalized_outputs.jsonl`
- `runs/fake_phase4_acceptance/metrics.json`
- `runs/fake_phase4_acceptance/failure_cases.jsonl`
- `runs/fake_phase4_acceptance/artifact_manifest.json`
- `runs/fake_phase4_acceptance/experiment_summary.md`

## Safety

- Real adapter skeletons validate paths/config only.
- Fake eval is in-process and accepts no shell/script arguments.
- Bad fake eval inputs are rejected before run artifacts are created.
- Raw outputs are never overwritten on rerun with the same run ID.
