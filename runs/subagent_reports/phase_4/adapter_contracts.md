# Phase 4 Adapter Contracts Exploration

Agent: AdapterContractsAgent
Status: partial_implementation_present_needs_attention
Report date: 2026-06-26

## Scope

Read-only inspection of the target repository, except for this requested report artifact.

Inspected areas:

- `adapters/`
- `experiments/`
- `stable_core/schemas/common.py`
- `stable_core/config.py`
- `stable_core/cli.py`
- `stable_core/runner/`
- `stable_core/storage/run_directory.py`
- `project_config/`
- `tests/`
- `runs/subagent_reports/`

`.env` was not read. I did not download models, load models, run real benchmarks, or execute GPU jobs.

Note: while this report was being prepared, additional uncommitted Phase 4 files appeared in the worktree. This report reflects the final observed worktree state and calls out which gaps remain. I did not modify those implementation/test files.

## Existing Contracts

### Core schemas

`stable_core/schemas/common.py` already defines the canonical dataclass payloads Phase 4 should reuse:

- `ExperimentSpec`: `experiment_id`, `model_id`, `benchmark_id`, `limit`, `instrumentation_mode`, optional `idea_id`, and `metadata`.
- `ExperimentResult`: `experiment_id`, validated `status`, `metrics`, optional evidence refs, and optional `run_id`.
- `RunManifest`: `run_id`, `run_type`, validated `status`, optional `model_id`, `benchmark_id`, `idea_id`, and `outputs`.
- `ArtifactManifest`: `run_id` plus artifact records.
- `ValidationReport`: validated `status`, `checks`, and `summary`.
- `GenerationRequest`: `request_id`, optional `image_path`, `prompt`, `benchmark_id`, `sample_id`, and `metadata`.
- `GenerationOutput`: `request_id`, `raw_text`, optional `tokens`, optional `logits_topk`, optional `latency_ms`, and `metadata`.

The fake end-to-end path should keep using `GenerationRequest` and `GenerationOutput`. Because `GenerationOutput` has no top-level `sample_id`, `sample_id` must be preserved in metadata or through request correlation before normalization.

### Adapter protocols

`adapters/benchmarks/base.py` defines `BenchmarkAdapter` with:

- `benchmark_id`
- `validate_paths() -> ValidationReport`
- `build_requests(split, limit) -> list[GenerationRequest]`
- `normalize_prediction(raw_output) -> dict`
- `compute_metrics(normalized_outputs_path) -> dict`
- `extract_failure_cases(normalized_outputs_path) -> list[dict]`

`adapters/models/base.py` now exists in the current worktree and defines `ModelAdapter` with:

- `model_id`
- `validate_environment() -> ValidationReport`
- `load() -> object`
- `generate(request) -> GenerationOutput`
- `unload() -> None`
- `supports_instrumentation(mode) -> bool`

This satisfies the method contract expected by `tests/test_architecture_contracts.py` and `idea_plugins/base.py`.

### Storage and runner contracts

`stable_core/storage/run_directory.py` provides the reusable run helpers Phase 4 should use:

- safe `run_id` validation via `validate_run_id()`
- `ensure_run_dir()`
- atomic `write_json()`
- UTF-8 `write_text()`
- safe `collect_env_snapshot()`
- git provenance via `current_git_commit()` and `collect_git_snapshot()`
- `artifact_manifest_for()` with path, size, and SHA-256 entries

`stable_core/runner/remote.py` already whitelists `run_fake_benchmark` and `experiments/fake/run_fake_benchmark.py`. The whitelisted script is still missing in the current worktree.

`LocalRunner` remains Phase 3 dummy-job oriented. It writes command/env/git/run/artifact manifests and failure artifacts, but it does not run benchmark evaluation.

### Config and CLI contracts

Current `project_config/models.yaml` has been modified in the worktree to include:

- `fake_model`
- `qwen3_vl_2b_instruct`
- `internvl3_5_4b`

Current `project_config/benchmarks.yaml` has been modified in the worktree to include:

- `fake_benchmark`
- `pope`
- `chair`
- `amber`
- `mme`

`stable_core/cli.py` has also been modified in the worktree to add:

- `validate-model`
- `validate-benchmark`
- `run-eval`

The command shapes match the untracked Phase 4 tests: positional model/benchmark IDs for validation and `--model`, `--benchmark`, `--limit`, `--run-id` for `run-eval`.

### Test patterns

Existing tests prefer:

- subprocess-based CLI smoke tests using `python -m stable_core.cli ...`
- `tmp_path` for generated run artifacts
- JSON stdout from CLI commands
- no real model/benchmark execution
- stable architecture tests for protocol method names
- adapter package separation: benchmark adapters must not import model adapters, and model adapters must not import benchmark adapters

Two untracked Phase 4 tests are present:

- `tests/test_fake_adapters.py`
- `tests/test_fake_runner.py`

They encode the expected fake model, fake benchmark, skeleton validation, fake run artifacts, no raw-output overwrite, and CLI behavior.

## Current Phase 4 Worktree State

Currently present in the worktree:

- `adapters/models/__init__.py` on disk, but ignored by git
- `adapters/models/base.py` on disk, but ignored by git
- `adapters/models/_skeleton.py` on disk, but ignored by git
- `adapters/models/fake.py` on disk, but ignored by git
- `adapters/models/qwen3_vl.py` on disk, but ignored by git
- `adapters/models/internvl.py` on disk, but ignored by git
- `adapters/benchmarks/_skeleton.py`
- `adapters/benchmarks/fake.py`
- `adapters/benchmarks/pope.py`
- `adapters/benchmarks/chair.py`
- `adapters/benchmarks/amber.py`
- `adapters/benchmarks/mme.py`
- `experiments/fake/__init__.py`
- `experiments/fake/evaluator.py`
- CLI changes for `validate-model`, `validate-benchmark`, and `run-eval`
- config changes adding fake adapter entries
- generated sample run artifacts under `runs/fake_cli_phase4/`

Still missing or incomplete in the current worktree:

- `experiments/fake/run_fake_benchmark.py`, despite being listed in the remote whitelist.
- A neutral adapter registry module. Current registry mappings live inside `experiments/fake/evaluator.py`, while `stable_core/cli.py` imports directly from that experiment module.
- Explicit tests for `InternVLAdapter`, `CHAIRAdapter`, `AMBERAdapter`, and `MMEAdapter`; the current untracked skeleton test checks only Qwen3-VL and POPE.
- A strict no-overwrite check for empty pre-existing `raw_outputs.jsonl`; current evaluator only rejects when the file exists and has size greater than zero.
- Durable raw-output preservation before downstream processing; current evaluator accumulates rows in memory and writes `raw_outputs.jsonl` after generation and normalization loops finish.
- A failure artifact path for partial fake-eval failures.

Files that were missing from the initially inspected base before concurrent worktree changes:

- `adapters/models/`
- fake model adapter
- fake benchmark adapter
- Qwen3-VL and InternVL skeletons
- POPE, CHAIR, AMBER, and MME skeletons
- fake evaluator
- Phase 4 CLI commands
- fake run artifacts

## Recommended Minimal File Layout

The current worktree is close to the minimal layout. Recommended final layout:

```text
adapters/
  models/
    __init__.py
    base.py
    _skeleton.py
    fake.py
    qwen3_vl.py
    internvl.py
  benchmarks/
    base.py
    _skeleton.py
    fake.py
    pope.py
    chair.py
    amber.py
    mme.py

experiments/
  fake/
    __init__.py
    evaluator.py
    run_fake_benchmark.py

stable_core/
  adapter_registry.py
  cli.py

tests/
  test_architecture_contracts.py
  test_fake_adapters.py
  test_fake_runner.py
```

Recommended responsibilities:

- `adapters/models/base.py`: keep the `ModelAdapter` protocol only; no heavy imports.
- `adapters/models/fake.py`: deterministic fake model with no external weights, network, GPU, or `.env` dependency.
- `adapters/models/_skeleton.py`: validate-only base class for real model skeletons.
- `adapters/models/qwen3_vl.py` and `adapters/models/internvl.py`: skeleton classes returning `needs_setup` when local paths are not configured; real `load()` and `generate()` remain disabled.
- `adapters/benchmarks/fake.py`: embedded deterministic samples, request construction, normalization, metrics, and failure extraction.
- `adapters/benchmarks/_skeleton.py`: validate-only base class for real benchmark skeletons.
- `adapters/benchmarks/{pope,chair,amber,mme}.py`: skeleton classes returning `needs_setup` when benchmark paths are absent; no real benchmark scripts are run.
- `stable_core/adapter_registry.py`: map IDs to adapter constructors and optionally pass config entries into skeleton adapters. This keeps CLI and evaluator from owning registry concerns.
- `experiments/fake/evaluator.py`: orchestrate fake model plus fake benchmark, write JSONL artifacts, compute metrics, write manifests and summary.
- `experiments/fake/run_fake_benchmark.py`: controlled script wrapper around `run_fake_eval()`, matching the already whitelisted path.
- `stable_core/cli.py`: keep JSON-emitting `validate-model`, `validate-benchmark`, and `run-eval`.

Recommended run directory:

```text
runs/<run_id>/
  command_manifest.json
  env_snapshot.json
  git_commit.txt
  run_manifest.json
  raw_outputs.jsonl
  normalized_outputs.jsonl
  metrics.json
  failure_cases.jsonl
  experiment_summary.md
  artifact_manifest.json
```

Recommended artifact notes:

- `artifact_manifest.json` should be written last.
- `run_manifest.json` should include all required outputs, including `experiment_summary` and `artifact_manifest` if downstream consumers expect a complete manifest map.
- `run_type` should be a Phase 4-specific value such as `fake_eval`; current generated `runs/fake_cli_phase4/run_manifest.json` uses `landmark_baseline`, which can confuse later real-baseline gates.
- `raw_outputs.jsonl` should be written durably before normalization and metric computation.
- `failure_cases.jsonl` should exist even when empty.

## Risks

1. `adapters/models/` is currently git-ignored.
   `.gitignore` contains `models/`, and `git check-ignore -v adapters/models/base.py` reports that this pattern ignores the model adapter package. Unless the ignore pattern is narrowed or force-add is used intentionally, the required `ModelAdapter`, fake model, and real model skeletons can be left out of commits while tests pass locally.

2. The remote whitelist references a missing script.
   `experiments/fake/run_fake_benchmark.py` is whitelisted in `stable_core/runner/remote.py` but does not exist. This leaves controlled script execution incomplete.

3. CLI imports experiment code directly.
   `stable_core/cli.py` now imports `run_fake_eval`, `validate_model`, and `validate_benchmark` from `experiments.fake.evaluator`. A small `stable_core/adapter_registry.py` would keep core CLI code from depending directly on one experiment package.

4. Config now includes fake IDs.
   The current worktree updates `project_config/models.yaml`, `project_config/benchmarks.yaml`, and `tests/test_config_cli.py` to include fake IDs. That may be acceptable, but it changes production-facing listing behavior. If fake IDs should remain test-only, keep them in a registry instead of config.

5. Skeleton adapters do not consume config paths yet.
   `Qwen3VLAdapter()` and `InternVLAdapter()` default to empty config, so future configured paths will not affect validation unless the registry passes config values into constructors.

6. Raw-output preservation is not fully durable.
   The evaluator accumulates raw and normalized rows in memory, then writes files after the loop. A crash during generation/normalization can lose raw outputs. For the Phase 4 contract, write raw rows incrementally or write raw JSONL immediately after each generation before normalization.

7. No-overwrite behavior should check existence, not non-empty size.
   The current evaluator rejects only when `raw_outputs.jsonl` exists and has size greater than zero. A pre-existing empty raw file would be overwritten.

8. Failure preservation is incomplete.
   The fake evaluator does not appear to write `failure.json` or `failure_report.md` for partial failures. Phase 3 runner patterns already preserve failure diagnostics and should be reused if fake evaluation can fail after creating a run directory.

9. Generated run artifacts are present in the worktree.
   `runs/fake_cli_phase4/` contains generated artifacts. These are useful smoke evidence but should be intentionally handled before commit according to the repo policy on generated run artifacts.

10. Adapter cross-import constraints still apply.
   Keep benchmark adapters from importing model adapters and model adapters from importing benchmark adapters. Orchestration should stay in evaluator or registry code.

11. The YAML parser is shallow.
    `parse_simple_yaml()` skips list items and does not implement full YAML. Phase 4 config should stay simple or the parser should be replaced with tests.

## Verification Notes

I did not run the test suite or execute `run-eval` during this report pass, because the requested task was read-only exploration plus report writing. The existing `runs/fake_cli_phase4/` artifacts were already present when inspected after concurrent worktree changes.

## Conclusion

The target repo now has a partial uncommitted Phase 4 implementation in the worktree. The core contracts are mostly in place on disk: schemas, model protocol, benchmark protocol, fake adapters, skeleton adapters, fake evaluator, generated artifacts, and CLI commands. Remaining concerns are mainly integration polish and safety: fix the `adapters/models/` ignore issue, add the missing whitelisted fake script, separate adapter registry concerns from the experiment evaluator, make raw-output preservation stricter, harden no-overwrite behavior, pass config into skeleton validators, and decide whether fake IDs belong in production config lists.
