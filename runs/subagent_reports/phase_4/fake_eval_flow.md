# Phase 4 Fake Evaluation Flow Verification Plan

Agent: FakeEvalFlowAgent
Status: PARTIAL PASS / ACCEPTANCE TEST GAPS
System root: `/Users/zrblution/Documents/桌面文件夹/博士阶段/MLLM幻觉消除/work1_test4/phase_work/muti-agent-work_test4`
Report date: 2026-06-26

## Scope

This read-only verification-planning pass focused on the fake end-to-end evaluation path for Phase 4:

- CLI contracts: `validate-model`, `validate-benchmark`, `run-eval`
- Fake pair: `fake_model` + `fake_benchmark`
- Required run artifacts:
  - `raw_outputs.jsonl`
  - `normalized_outputs.jsonl`
  - `metrics.json`
  - `failure_cases.jsonl`
  - `artifact_manifest.json`
  - `experiment_summary.md`

No `.env` file was read. No real model was downloaded or loaded. No real benchmark data was accessed or executed.

## Current Repository State

Phase 4 is now partially functional in the workspace. The fake model, fake benchmark, evaluator, CLI commands, and at least one fake run artifact bundle are present. The remaining issues are contract hardening and acceptance-test coverage, especially around raw-output preservation.

Observed commands:

- `python3 -m stable_core.cli --help` exits `0` and lists `validate-model`, `validate-benchmark`, and `run-eval`.
- `python3 -m stable_core.cli validate-config` exits `0` with `status: passed`.
- `python3 -m stable_core.cli validate-model fake_model` exits `0` with `status: passed`.
- `python3 -m stable_core.cli validate-benchmark fake_benchmark` exits `0` with `status: passed`.
- `python3 -m stable_core.cli run-eval --model fake_model --benchmark fake_benchmark --run-id phase4_fake_probe --limit 2` exited `0` with `status: succeeded`; the generated probe directory was removed after verification.

Observed existing fake run bundle:

- `runs/fake_cli_phase4/` contains `raw_outputs.jsonl`, `normalized_outputs.jsonl`, `metrics.json`, `failure_cases.jsonl`, `artifact_manifest.json`, and `experiment_summary.md`.
- `raw_outputs.jsonl` has one flat JSON object per request with `request_id`, `sample_id`, `model_id`, `benchmark_id`, `raw_text`, `tokens`, `latency_ms`, `generation_config`, `plugin_id`, and `created_at`.
- `normalized_outputs.jsonl` includes `raw_text_ref` values such as `raw_outputs.jsonl:line_1`.
- `artifact_manifest.json` hashes the required artifacts and also includes `command_manifest.json`, `env_snapshot.json`, `git_commit.txt`, and `run_manifest.json`.
- `failure_cases.jsonl` is present and empty for the observed perfect fake run.

Relevant existing support:

- `stable_core/schemas/common.py` already defines `GenerationRequest`, `GenerationOutput`, `ExperimentSpec`, `ExperimentResult`, `RunManifest`, `ArtifactManifest`, and `ValidationReport`.
- `adapters/models/base.py` defines the expected model adapter protocol: `validate_environment`, `load`, `generate`, `unload`, and `supports_instrumentation`.
- `adapters/benchmarks/base.py` defines the expected benchmark adapter protocol: `validate_paths`, `build_requests`, `normalize_prediction`, `compute_metrics`, and `extract_failure_cases`.
- `adapters/models/fake.py` now provides `FakeModelAdapter` with no external weights.
- `adapters/benchmarks/fake.py` now provides `FakeBenchmarkAdapter` with embedded samples and metrics.
- `experiments/fake/evaluator.py` now provides `validate_model`, `validate_benchmark`, and `run_fake_eval`.
- `stable_core/storage/run_directory.py` already provides safe run ID validation, JSON/text writing helpers, SHA-256 file hashing, and artifact manifest generation.
- `stable_core/runner/remote.py` already whitelists `run_fake_benchmark` and `experiments/fake/run_fake_benchmark.py`.
- `stable_core/runner/local.py` currently writes Phase 3 dummy-job run artifacts, but it intentionally marks benchmark artifacts as missing.

Current contract gaps:

- `stable_core.cli` supports positional `validate-model fake_model` and `validate-benchmark fake_benchmark`, plus `run-eval --model ... --benchmark ...`, but it does not currently support `--model-id` or `--benchmark-id` aliases.
- `experiments/fake/evaluator.py` accumulates raw rows in memory, normalizes in the same loop, and writes `raw_outputs.jsonl` after the loop. For the strict raw-preservation contract, raw output should be durably written before downstream normalization and metric computation, or tests must prove that no downstream step can mutate or discard it.
- `FakeBenchmarkAdapter.normalize_prediction()` copies `raw_output.raw_text` into normalized metadata. For cleaner artifact boundaries, normalized rows should primarily reference raw lines rather than duplicating raw text.
- Current artifacts do not include a `schema_version` field.
- Current `metrics.json` does not include `status`, `normalized_count`, `failure_count`, or input artifact SHA references.
- Current `experiment_summary.md` names the run and metrics, but does not yet include the no-real-model/no-real-benchmark statement, artifact table, SHA-256 hashes, failure-case count, or reproduction command.
- The current fake model predicts the embedded reference answer, so `failure_cases.jsonl` can be empty in the happy path. A dedicated fake failure mode is still needed to test failure-case preservation.

## Recommended CLI Contract

All three commands should print one machine-readable JSON object to stdout and use stable exit codes.

### `validate-model`

Command:

```bash
python3 -m stable_core.cli validate-model fake_model
```

Recommended aliases:

```bash
python3 -m stable_core.cli validate-model --model-id fake_model
```

Successful fake response:

```json
{
  "command": "validate-model",
  "status": "passed",
  "model_id": "fake_model",
  "mode": "fake",
  "checks": [
    {
      "name": "model_registry",
      "status": "passed",
      "message": "fake_model is registered as an in-process deterministic fake model"
    },
    {
      "name": "no_model_download",
      "status": "passed",
      "message": "fake_model does not require model_root, network access, GPU, or weights"
    }
  ]
}
```

Failure response for an unsupported model:

```json
{
  "command": "validate-model",
  "status": "failed",
  "model_id": "unknown_model",
  "checks": [
    {
      "name": "model_registry",
      "status": "failed",
      "message": "unknown_model is not configured"
    }
  ]
}
```

Exit code contract:

- `0` for `passed`
- `1` for `failed`
- `2` for CLI argument errors

### `validate-benchmark`

Command:

```bash
python3 -m stable_core.cli validate-benchmark fake_benchmark
```

Recommended aliases:

```bash
python3 -m stable_core.cli validate-benchmark --benchmark-id fake_benchmark
```

Successful fake response:

```json
{
  "command": "validate-benchmark",
  "status": "passed",
  "benchmark_id": "fake_benchmark",
  "mode": "fake",
  "checks": [
    {
      "name": "benchmark_registry",
      "status": "passed",
      "message": "fake_benchmark is registered as an in-process deterministic fake benchmark"
    },
    {
      "name": "no_dataset_access",
      "status": "passed",
      "message": "fake_benchmark does not require benchmark_root, downloads, or external annotations"
    }
  ]
}
```

Exit code contract should match `validate-model`.

### `run-eval`

Command:

```bash
python3 -m stable_core.cli run-eval \
  --model fake_model \
  --benchmark fake_benchmark \
  --run-id phase4_fake_eval \
  --limit 2
```

Recommended aliases: accept `--model-id` for `--model` and `--benchmark-id` for `--benchmark`.

Required behavior:

- Validate the model and benchmark before writing result artifacts.
- Reject unsafe `run_id` values using the existing safe path segment rules.
- Create `runs/<run_id>/`.
- Produce exactly the required six artifacts for the fake eval flow.
- Preserve raw model output before normalization or metric computation.
- Use deterministic fake data and deterministic fake model responses.
- Never read real benchmark roots, model roots, API keys, remote runners, GPUs, or network resources.

Successful stdout:

```json
{
  "command": "run-eval",
  "status": "succeeded",
  "run_id": "phase4_fake_eval",
  "run_dir": "runs/phase4_fake_eval",
  "model_id": "fake_model",
  "benchmark_id": "fake_benchmark",
  "limit": 2,
  "artifacts": {
    "raw_outputs": "raw_outputs.jsonl",
    "normalized_outputs": "normalized_outputs.jsonl",
    "metrics": "metrics.json",
    "failure_cases": "failure_cases.jsonl",
    "artifact_manifest": "artifact_manifest.json",
    "experiment_summary": "experiment_summary.md"
  }
}
```

## Expected Artifact Schema

The run directory should be `runs/<run_id>/`, where `<run_id>` is a single safe path segment.

### `raw_outputs.jsonl`

One JSON object per attempted generation. This file is the source of truth for model output and must be written before normalization.

Required fields per line:

```json
{
  "schema_version": 1,
  "run_id": "phase4_fake_eval",
  "model_id": "fake_model",
  "benchmark_id": "fake_benchmark",
  "request": {
    "request_id": "fake_benchmark_0001",
    "sample_id": "sample_0001",
    "benchmark_id": "fake_benchmark",
    "image_path": null,
    "prompt": "Does the image contain a cat?",
    "metadata": {
      "split": "fake",
      "expected_answer": "yes"
    }
  },
  "generation": {
    "request_id": "fake_benchmark_0001",
    "raw_text": "yes",
    "tokens": null,
    "logits_topk": null,
    "latency_ms": 0.0,
    "metadata": {
      "fake_model_version": 1
    }
  },
  "status": "succeeded",
  "created_at": "2026-06-26T00:00:00Z"
}
```

Rules:

- `generation.raw_text` must preserve the fake model's emitted text exactly as a JSON string value.
- The raw file must not contain normalized labels, metric decisions, or post-processed predictions outside metadata needed to reproduce the request.
- Failed generations should still create a raw line with `status: failed`, `generation.raw_text` set to the exact captured partial output or `""`, and an `error` object.

### `normalized_outputs.jsonl`

One JSON object per raw output that reached normalization.

Required fields per line:

```json
{
  "schema_version": 1,
  "run_id": "phase4_fake_eval",
  "model_id": "fake_model",
  "benchmark_id": "fake_benchmark",
  "request_id": "fake_benchmark_0001",
  "sample_id": "sample_0001",
  "prediction": {
    "answer": "yes"
  },
  "target": {
    "answer": "yes"
  },
  "is_correct": true,
  "raw_output_ref": {
    "path": "raw_outputs.jsonl",
    "line_number": 1,
    "sha256": "<sha256-of-raw_outputs-jsonl-at-normalization-time>"
  }
}
```

Rules:

- Normalization reads `raw_outputs.jsonl`; it does not regenerate fake model output.
- Each normalized line must point back to the raw line with a stable 1-based line number.
- Any skipped raw line should be represented in `failure_cases.jsonl` or a structured failure artifact, not silently dropped.

### `metrics.json`

Required top-level fields:

```json
{
  "schema_version": 1,
  "run_id": "phase4_fake_eval",
  "model_id": "fake_model",
  "benchmark_id": "fake_benchmark",
  "status": "succeeded",
  "sample_count": 2,
  "normalized_count": 2,
  "failure_count": 1,
  "metrics": {
    "accuracy": 0.5
  },
  "inputs": {
    "normalized_outputs": {
      "path": "normalized_outputs.jsonl",
      "sha256": "<sha256>"
    }
  }
}
```

Rules:

- Metrics must be computed from `normalized_outputs.jsonl`, matching the `BenchmarkAdapter.compute_metrics(normalized_outputs_path)` contract.
- The file must not depend on raw text except through normalized output references.

### `failure_cases.jsonl`

Zero or more JSON objects. For the fake benchmark, the happy path may produce an empty file. Add a dedicated fake failure mode or fixture so failure preservation is tested without making the default smoke path fail.

Required fields per failure line:

```json
{
  "schema_version": 1,
  "run_id": "phase4_fake_eval",
  "model_id": "fake_model",
  "benchmark_id": "fake_benchmark",
  "request_id": "fake_benchmark_0002",
  "sample_id": "sample_0002",
  "failure_type": "incorrect_prediction",
  "prediction": {
    "answer": "yes"
  },
  "target": {
    "answer": "no"
  },
  "raw_output_ref": {
    "path": "raw_outputs.jsonl",
    "line_number": 2,
    "sha256": "<sha256>"
  }
}
```

Rules:

- Failure extraction must read `normalized_outputs.jsonl`, matching the benchmark protocol.
- Failure cases should preserve enough identifiers to retrieve the raw output without copying or mutating it.

### `artifact_manifest.json`

The manifest should remain compatible with the existing `ArtifactManifest` shape while adding useful artifact metadata.

Required fields:

```json
{
  "run_id": "phase4_fake_eval",
  "artifacts": [
    {
      "path": "raw_outputs.jsonl",
      "kind": "raw_outputs",
      "size_bytes": 1000,
      "sha256": "<sha256>",
      "required": true,
      "line_count": 2
    }
  ]
}
```

Required artifact entries:

- `raw_outputs.jsonl`
- `normalized_outputs.jsonl`
- `metrics.json`
- `failure_cases.jsonl`
- `experiment_summary.md`

Rules:

- `artifact_manifest.json` should not include itself unless the project intentionally changes the existing manifest convention.
- Every required artifact should have `path`, `size_bytes`, and `sha256`.
- JSONL artifacts should include `line_count`.
- Required artifact paths must be relative to the run directory.

### `experiment_summary.md`

Required content:

- Title with run ID.
- `model_id`, `benchmark_id`, `limit`, status, start time, finish time.
- Statement that this was a fake-only run with no model downloads and no real benchmark access.
- Metrics table.
- Artifact table with paths and SHA-256 hashes.
- Failure-case count and brief list of failure sample IDs.
- Reproduction command.

## Recommended Acceptance Tests

Add a focused Phase 4 test module, for example `tests/test_fake_eval_flow.py`.

### CLI registration and validation

1. `test_validate_model_accepts_fake_model_without_model_root`
   - Run `python3 -m stable_core.cli validate-model fake_model`.
   - Expect exit `0`.
   - Assert stdout JSON has `command: validate-model`, `status: passed`, `model_id: fake_model`.
   - Assert at least one check states no download, no GPU, or no weights are required.
   - Also run `python3 -m stable_core.cli validate-model --model-id fake_model` if the alias is supported.

2. `test_validate_model_rejects_unknown_model`
   - Run `python3 -m stable_core.cli validate-model unknown_model`.
   - Expect exit `1`.
   - Assert stdout JSON has `status: failed`.

3. `test_validate_benchmark_accepts_fake_benchmark_without_dataset_root`
   - Run `python3 -m stable_core.cli validate-benchmark fake_benchmark`.
   - Expect exit `0`.
   - Assert stdout JSON has `command: validate-benchmark`, `status: passed`, `benchmark_id: fake_benchmark`.
   - Assert no benchmark root is required.
   - Also run `python3 -m stable_core.cli validate-benchmark --benchmark-id fake_benchmark` if the alias is supported.

4. `test_validate_benchmark_rejects_unknown_benchmark`
   - Run `python3 -m stable_core.cli validate-benchmark unknown_benchmark`.
   - Expect exit `1`.
   - Assert stdout JSON has `status: failed`.

### End-to-end fake run

5. `test_run_eval_fake_pair_writes_required_artifacts`
   - Run `python3 -m stable_core.cli run-eval --model fake_model --benchmark fake_benchmark --run-id <unique_safe_id> --limit 2`.
   - Expect exit `0`.
   - Assert the run directory exists.
   - Assert all six required artifacts exist.
   - Assert stdout JSON points to the same artifact filenames.
   - Also cover `--model-id fake_model --benchmark-id fake_benchmark` if those aliases are supported.

6. `test_run_eval_limit_controls_jsonl_line_counts`
   - Run with `--limit 2`.
   - Assert `raw_outputs.jsonl` has exactly 2 lines.
   - Assert `normalized_outputs.jsonl` has exactly 2 lines when both fake generations normalize.

7. `test_run_eval_artifact_manifest_hashes_required_outputs`
   - Load `artifact_manifest.json`.
   - Assert entries exist for each required artifact except the manifest itself.
   - Recompute SHA-256 for each listed path and compare with manifest values.
   - Assert `size_bytes` matches `Path.stat().st_size`.

8. `test_experiment_summary_contains_metrics_and_reproduction_command`
   - Read `experiment_summary.md`.
   - Assert it names `fake_model`, `fake_benchmark`, the run ID, metrics, artifact hashes, and the exact `run-eval` command.
   - Assert it states that no real model or real benchmark was used.

### Raw output preservation

9. `test_raw_outputs_preserve_exact_fake_model_text`
   - Configure a fake sample whose model response includes leading spaces, trailing spaces, quotes, escaped newlines, and punctuation.
   - Assert `raw_outputs.jsonl` preserves the exact `generation.raw_text` value after JSON decode.
   - Assert `normalized_outputs.jsonl` stores only normalized predictions and references the raw line.

10. `test_normalization_does_not_rewrite_raw_outputs`
    - Compute SHA-256 of `raw_outputs.jsonl` immediately after generation.
    - Run normalization and metrics.
    - Compute SHA-256 again.
    - Assert the hash is unchanged.

11. `test_reparse_preserves_existing_raw_outputs`
    - Create a fake run through raw generation.
    - Re-run only parse or resume logic if Phase 4 exposes it; otherwise call the internal parse function in tests.
    - Assert raw line count and SHA-256 are unchanged.
    - Assert normalized outputs and metrics are regenerated from the existing raw file.

12. `test_failed_generation_preserves_partial_raw_and_failure_artifacts`
    - Use a fake model mode that returns one successful output and one controlled failure.
    - Assert `raw_outputs.jsonl` includes both attempts.
    - Assert the failed line has `status: failed`, an `error` object, and any exact partial `raw_text`.
    - Assert `failure_cases.jsonl`, `metrics.json`, or a structured failure report references the failed request.

### Safety and contract boundaries

13. `test_run_eval_rejects_real_model_benchmark_pair_in_phase4_fake_mode`
    - Attempt `run-eval` with a configured real model such as `qwen3_vl_2b_instruct` and `pope`.
    - Expect a gate failure unless an explicit later-phase flag is introduced.
    - Assert no required eval artifacts are produced for the rejected run.

14. `test_run_eval_rejects_unsafe_run_id`
    - Try run IDs containing `/`, `..`, whitespace padding, or `\`.
    - Expect a nonzero exit.
    - Assert no directory is created outside `runs/`.

15. `test_run_eval_existing_run_dir_does_not_overwrite_raw_outputs_by_default`
    - Run a fake eval once.
    - Re-run with the same `run_id` and no explicit `--overwrite` or `--resume`.
    - Expect failure or a documented resume mode.
    - Assert original `raw_outputs.jsonl` SHA-256 remains unchanged.

16. `test_fake_eval_does_not_call_network_gpu_or_remote_runner`
    - In unit tests, monkeypatch common network and subprocess entry points used for downloads or remote execution to raise immediately.
    - Run the fake eval.
    - Expect success, proving the fake flow is in-process and isolated.

## Raw Output Preservation Edge Cases

Phase 4 should treat raw output preservation as a first-class contract, not an implementation detail.

Required edge cases:

- Empty model output: preserve `raw_text: ""` and make normalization decide whether it is invalid.
- Leading and trailing whitespace: preserve exact spaces in `generation.raw_text`.
- Newlines and tabs: preserve as JSON string escapes and verify equality after JSON decode.
- Quotes, braces, and JSON-like text: do not parse raw text as JSON unless the model adapter explicitly declares a structured response format.
- Very long fake output: preserve full text in `raw_outputs.jsonl`; summary files may tail or truncate only with explicit labels.
- Duplicate sample IDs: either reject duplicate request IDs before writing or preserve line-index references so failures remain traceable.
- Generation failure after partial text: write the raw attempt before marking the case failed.
- Normalization failure: preserve raw output, write a structured failure record, and avoid claiming successful metrics for missing normalized rows.
- Metrics failure: preserve raw and normalized outputs, write failure diagnostics, and leave artifact hashes available for debugging.
- Re-run with same run ID: never overwrite raw outputs by default.
- Reparse or resume: read existing raw outputs and regenerate downstream artifacts without mutating the raw file.
- Manifest timing: compute the raw output SHA-256 after raw generation and reference it from normalized outputs and failure cases.

## Acceptance Gate

Phase 4 should be accepted only when:

- The three CLI commands are registered and documented through `--help`.
- `fake_model` and `fake_benchmark` validate without model roots, benchmark roots, GPU, network, or remote execution.
- `run-eval` for `fake_model` + `fake_benchmark` creates all six required artifacts in one safe run directory.
- Raw outputs are written first, preserved exactly, and referenced by normalized outputs and failure cases.
- Metrics are computed from normalized outputs only.
- `artifact_manifest.json` hashes every required artifact.
- The focused Phase 4 acceptance tests pass without downloading real models or reading real benchmarks.
