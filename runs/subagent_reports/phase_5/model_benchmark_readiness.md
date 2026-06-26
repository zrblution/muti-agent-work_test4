# Phase 5 Model/Benchmark Readiness Report

Generated: 2026-06-26
Repository: `/home/vepfs/data/work1/muti-agent-work_test4`
SSH alias: `server`
Scope: `qwen3_vl_2b_instruct` model readiness and `pope` benchmark readiness

## Summary

- Server repo reachable: yes.
- Report target: `/home/vepfs/data/work1/muti-agent-work_test4/runs/subagent_reports/phase_5/model_benchmark_readiness.md`.
- Phase 4 commit present: yes. Current inspected HEAD is `2237f00b370bf3fa5950e86461d6cf768279a99f`, `feat: add model and benchmark adapter skeletons`.
- Note: the remote branch advanced during inspection from `abd626e76753f1cb9a7e19aba1821fd384c2e814` to `2237f00b370bf3fa5950e86461d6cf768279a99f`. The final readiness findings are based on `2237f00`.
- Working tree was already dirty before this report write, with modified `runs/preflight/env_check.json`, modified `runs/preflight/git_check.json`, and untracked `runs/phase_5_gate_logs/` plus `runs/subagent_reports/phase_5/`.
- Model validation command exit code: `0`; JSON status: `needs_setup`.
- Benchmark validation command exit code: `0`; JSON status: `needs_setup`.
- Overall readiness: not ready for real model/benchmark execution. The Phase 4 skeleton wiring is present and safe, but required paths and real readiness gates are missing.

## Inspected Configuration

### `project_config/models.yaml`

`qwen3_vl_2b_instruct` is configured with:

```yaml
family: qwen3_vl
adapter: adapters.models.qwen3_vl.Qwen3VLAdapter
model_root_env: REMOTE_MODEL_ROOT
path: null
phase0_status: needs_setup
phase0_note: "Phase 0 records configuration only; no download or load attempted."
```

Finding: the adapter is wired, but no concrete local model path is configured.

### `project_config/benchmarks.yaml`

`pope` is configured with:

```yaml
adapter: adapters.benchmarks.pope.POPEAdapter
benchmark_root_env: REMOTE_BENCHMARK_ROOT
path: null
phase0_status: needs_setup
```

Finding: the adapter is wired, but no concrete benchmark path is configured.

## CLI Validation Inspection

- `stable_core/cli.py` defines `validate-model <model_id>` and `validate-benchmark <benchmark_id>`.
- `validate-model` delegates to `experiments.fake.evaluator.validate_model`.
- `validate-benchmark` delegates to `experiments.fake.evaluator.validate_benchmark`.
- `experiments.fake.evaluator` maps `qwen3_vl_2b_instruct` to `Qwen3VLAdapter` and `pope` to `POPEAdapter`.
- `Qwen3VLAdapter` inherits `ValidateOnlyModelAdapter`.
- `POPEAdapter` inherits `ValidateOnlyBenchmarkAdapter`.
- The validate-only model adapter records `download_allowed: not_attempted`, `load_attempted: not_attempted`, and checks only a configured `path` or `local_path`.
- The validate-only model adapter raises if `load()` or `generate()` is called.
- The validate-only benchmark adapter records adapter presence and checks only configured `path`.
- The validate-only benchmark adapter raises if sample parsing, normalization, metric computation, or failure extraction is called.

This is safe for the requested Phase 5 readiness probe because it does not download models, load models, run generation, run benchmarks, or start GPU work.

## Allowed Command Results

### Model Validation

Command:

```bash
python -m stable_core.cli validate-model qwen3_vl_2b_instruct
```

Exit code: `0`

Stdout/status payload:

```json
{"command": "validate-model", "model_id": "qwen3_vl_2b_instruct", "status": "needs_setup", "checks": [{"name": "download_allowed", "status": "not_attempted", "value": false}, {"name": "load_attempted", "status": "not_attempted"}, {"name": "model_path", "status": "needs_setup", "message": "No local model path configured."}], "summary": "Qwen3-VL-2B-Instruct is a validate-only skeleton; model path is not configured."}
```

Stderr: empty.

Interpretation: the model validation path is present and safe, but the model is not ready because no local path is configured.

### Benchmark Validation

Command:

```bash
python -m stable_core.cli validate-benchmark pope
```

Exit code: `0`

Stdout/status payload:

```json
{"command": "validate-benchmark", "benchmark_id": "pope", "status": "needs_setup", "checks": [{"name": "adapter", "status": "passed", "value": "POPEAdapter"}, {"name": "benchmark_path", "status": "needs_setup", "message": "No benchmark path configured."}], "summary": "POPE is validate-only; benchmark path is not configured."}
```

Stderr: empty.

Interpretation: the benchmark validation path is present and safe, but the benchmark is not ready because no local path is configured.

## Missing Gates

- Configure a concrete model path or local path for `qwen3_vl_2b_instruct`.
- Validate model path existence and expected file inventory without downloading.
- Add license/access, tokenizer/processor/config, and dependency checks for Qwen3-VL readiness.
- Add a separate explicit load-smoke gate before any real generation path is considered ready.
- Configure a concrete POPE dataset path.
- Validate POPE dataset file layout, annotation/image availability, and sample schema without running evaluation.
- Add POPE request construction, prediction normalization, metric computation, and failure-case extraction readiness checks.
- Ensure downstream automation treats JSON `status: needs_setup` as blocking. The current CLI returns exit code `0` for `needs_setup` because only `status: failed` maps to nonzero.

## Recommendation

Do not approve real `qwen3_vl_2b_instruct` x `pope` evaluation yet. Approve only the Phase 4 skeleton readiness result: the CLI commands exist, adapter wiring is present, and the validation path is safe under the no-download/no-load/no-benchmark constraint.

Next gate should require configured local paths plus offline existence/schema checks to return JSON `status: passed`. Real model loading, generation, GPU usage, and benchmark execution should remain blocked until a separate execution-readiness gate is explicitly authorized.

## Constraints Observed

- Did not read `.env`.
- Did not download models.
- Did not load models.
- Did not run benchmarks.
- Did not start GPU jobs.
- Only the two requested validation commands were executed after confirming the Phase 4 adapter skeleton commit was present.
