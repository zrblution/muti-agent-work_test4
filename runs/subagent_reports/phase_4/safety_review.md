# Phase 4 Safety Review

Status: needs attention before Phase 4 acceptance
Report date: 2026-06-26
Scope: read-only inspection plus this report file

`.env` was not read. This review did not intentionally edit code or config. While the review was in progress, other Phase 4 files appeared in the worktree; this report reflects the current tree observed after those concurrent changes.

## Findings

1. **Blocking: `.gitignore` hides `adapters/models/` source files.**
   `git check-ignore -v adapters/models/base.py adapters/models/fake.py adapters/models/qwen3_vl.py adapters/models/internvl.py adapters/models/_skeleton.py` reports `.gitignore:8:models/` for every model adapter file. This means the newly present Phase 4 model adapter source is ignored as if it were a model-weight directory. Normal `git status --short` does not show these files, so they could be omitted from commits and review. Fix by anchoring the artifact rule to the repo-level model artifact directory or explicitly unignoring `adapters/models/`.

2. **Needs attention: `validate-model` and `validate-benchmark` are safe, but not yet true path/config validation.**
   `experiments/fake/evaluator.py` instantiates adapters with no config in `validate_model()` and `validate_benchmark()` (`adapter_class().validate_environment()` and `adapter_class().validate_paths()`). The validate-only adapter classes support config dictionaries, but the CLI does not pass the selected `project_config/models.yaml` or `project_config/benchmarks.yaml` entry. This is safe because it does not download, load, or run anything, but it does not yet validate configured paths or `download_allowed` values.

3. **Mostly satisfied: real model skeletons do not download or load real models.**
   `adapters/models/_skeleton.py` imports only `Path`, typing, and schema types. `validate_environment()` checks a configured path if provided, records `download_allowed` and `load_attempted` as not attempted, and returns `needs_setup` when no path is configured. `load()` and `generate()` raise runtime errors for real skeletons. `adapters/models/qwen3_vl.py` and `adapters/models/internvl.py` only subclass this validate-only adapter.

4. **Mostly satisfied: real benchmark skeletons are path-only and cannot run real benchmarks.**
   `adapters/benchmarks/_skeleton.py` checks only a configured benchmark path. `build_requests()`, `normalize_prediction()`, `compute_metrics()`, and `extract_failure_cases()` all raise runtime errors for real benchmark skeletons. `POPEAdapter`, `CHAIRAdapter`, `AMBERAdapter`, and `MMEAdapter` only subclass this validate-only adapter.

5. **Mostly satisfied: `run-eval` fake path does not execute arbitrary shell.**
   `stable_core/cli.py` exposes `run-eval`, but delegates to `run_fake_eval()`. `experiments/fake/evaluator.py` rejects anything except `fake_model + fake_benchmark`, does not call `subprocess`, does not accept script or command arguments, and writes deterministic fake run artifacts in-process. Existing `ensure_run_dir()` still protects `run_id` from path traversal.

6. **Needs attention: validate `limit` before creating a run directory.**
   `FakeBenchmarkAdapter.build_requests()` rejects negative limits, but `run_fake_eval()` creates the run directory and writes `command_manifest.json`, `env_snapshot.json`, and `git_commit.txt` before calling `build_requests()`. This is not arbitrary shell execution, but bad input should fail before writing artifacts or calling `model.load()`.

7. **Needs attention: default preflight secret scanning still omits Phase 4 code paths.**
   `run_preflight()` scans `docs`, `project_config`, `stable_core`, `tests`, `.env.example`, `.gitignore`, `AGENTS.md`, and `README.md`, but not `adapters/`, `idea_plugins/`, `instrumentation/`, `experiments/`, or run `.md`/`.json` artifacts. The security spec requires scanning those areas. Phase 4 acceptance should run an expanded scan over all new Phase 4 code and generated artifacts.

8. **Mostly satisfied: large artifacts remain out of git, but current run artifacts need review before commit.**
   `.gitignore` blocks `.env`, key files, `.pkl`, `.pt`, `.pth`, `.safetensors`, raw tensor directories, full attention/hidden/KV directories, browser traces, and `runs/**/large_artifacts/`. Metadata inspection found no files over 1 MB in the repo. Current untracked fake run directories under `runs/` are small text artifacts, but they should be intentionally selected or left untracked by the implementing agent. The `models/` ignore issue above must be fixed without allowing real model weights into git.

## Phase 4 Contract Used

There is a phase-numbering mismatch across the specs: `08_CODEX_BUILD_PLAN_AND_TASKS.md` puts Qwen/POPE adapter work before its browser-review Phase 4, while `LOCAL_CODEX_IMPLEMENTATION_PROMPT.md` defines Phase 4 as "Model / Benchmark Adapter Skeletons + Fake End-to-End". This review follows the local implementation prompt because it matches the requested safety scope.

Relevant requirements:

- Implement `FakeModelAdapter`, `FakeBenchmarkAdapter`, Qwen/InternVL skeletons, and POPE/CHAIR/AMBER/MME skeletons.
- Do not download models in this phase.
- Do not force real benchmark execution in this phase.
- First complete an end-to-end flow using `fake_model + fake_benchmark`.
- Add CLI surfaces for `validate-model`, `validate-benchmark`, and `run-eval`.
- Produce `raw_outputs.jsonl`, `normalized_outputs.jsonl`, `metrics.json`, `failure_cases.jsonl`, `artifact_manifest.json`, and `experiment_summary.md`.

## Current Evidence

Observed current implementation:

- `project_config/models.yaml` now includes `fake_model`, `qwen3_vl_2b_instruct`, and `internvl3_5_4b` adapter entries.
- `project_config/benchmarks.yaml` now includes `fake_benchmark` and the four real benchmark adapter entries.
- `adapters/models/base.py`, `_skeleton.py`, `fake.py`, `qwen3_vl.py`, and `internvl.py` exist locally but are ignored by git because of `.gitignore:8`.
- `adapters/benchmarks/_skeleton.py`, `fake.py`, `pope.py`, `chair.py`, `amber.py`, and `mme.py` exist and are visible as untracked files.
- `experiments/fake/evaluator.py` implements the fake end-to-end flow.
- `stable_core/cli.py` now exposes `validate-model`, `validate-benchmark`, and `run-eval`.
- `tests/test_fake_adapters.py` and `tests/test_fake_runner.py` exist as untracked files.

Existing safety controls to preserve:

- `LocalRunner` only accepts the controlled `dummy_job` action.
- `RemoteRunner` validates structured whitelist actions and does not execute remote jobs in the current implementation.
- `project_config/server.yaml` has `runner_mode: local_only`.
- `project_config/experiment_budget.yaml` has `allow_real_gpu_jobs: false`.
- `project_config/instrumentation.yaml` has `allow_full_tensors: false`.
- `project_config/agents.yaml` uses environment variable names, not inline secrets.
- `stable_core/storage/run_directory.py` validates `run_id` as a single safe path segment.
- `runs/preflight/secret_scan_report.json` currently reports `passed`.

## Required Acceptance Gates

### Model skeletons

- Real model adapters must remain validate-only in Phase 4.
- No module import may call heavyweight or network loaders such as `AutoModel.from_pretrained`, `AutoProcessor.from_pretrained`, `snapshot_download`, `hf_hub_download`, `pipeline`, or `torch.load`.
- `validate-model` must parse the selected `project_config/models.yaml` entry and pass it to the adapter.
- `download_allowed` must default to false and be enforced.
- `load()` and `generate()` for Qwen/InternVL skeletons must remain blocked until the later real-smoke phase.
- Tests should monkeypatch common loader/network functions to fail if touched.

### Benchmark validation

- `validate-benchmark` must parse the selected `project_config/benchmarks.yaml` entry and pass it to the adapter.
- Missing benchmark roots or required files should produce `needs_setup`, not execution.
- Real benchmark adapters must not import benchmark repo code, run external scripts, scan full image trees deeply, or compute real metrics during validation.
- `required_files` should be discovered or reported as unknown/missing; do not invent benchmark-specific filenames.
- Fake benchmark metrics may operate only on small fake JSONL.

### Fake `run-eval`

- Phase 4 `run-eval` must continue to allow only `fake_model + fake_benchmark`.
- It must not accept command strings, script paths, shell fragments, arbitrary environment variables, or user-controlled executable paths.
- It should validate `limit`, `run_id`, model id, benchmark id, and instrumentation before creating any run directory or loading the fake model.
- Prefer keeping fake eval in-process. If a subprocess is introduced later, it must use fixed argv, `shell=False`, and a whitelisted repository-relative script only.
- Tests should cover rejected real model ids, real benchmark ids, path-traversal run ids, negative limits, and shell-like strings.

### Secrets

- Do not read `.env` in adapters, CLI validation, or fake evaluation.
- Config files may reference only environment variable names.
- Environment snapshots must continue recording metadata and presence flags only, never full environment values.
- CLI errors, run manifests, summaries, and logs must not echo provider keys, Hugging Face tokens, SSH material, cookies, or session data.
- Phase 4 secret scan should include `adapters`, `experiments`, `idea_plugins`, `instrumentation`, `project_config`, `stable_core`, `tests`, `docs`, `runs/**/*.md`, and `runs/**/*.json`, while excluding `.git`, `.venv`, real model directories, downloaded datasets, raw tensors, and large artifacts.

### Git and artifacts

- Fix the `models/` ignore rule so `adapters/models/` source files are visible to git while real model-weight directories remain ignored.
- Keep fake run outputs small and text-based.
- Do not commit model weights, datasets, raw tensors, full image dumps, full attention/hidden/KV dumps, browser traces, cookies, sessions, or raw long logs.
- Before commit, verify tracked file sizes and fail if any non-approved tracked file exceeds a small threshold such as 5 MB.
- `artifact_manifest.json` should list external or large artifacts by path, size, sha256, kind, and `tracked_in_git: false` when applicable.

## Verification Performed

Read-only inspection commands included:

- `rg` and `find` searches excluding `.env`.
- `git status --short` and `git status --short --untracked-files=all`.
- `git check-ignore -v` for `.env`, weight patterns, run artifact directories, and `adapters/models/*`.
- `find . -path './.git' -prune -o -name '.env' -prune -o -type f -size +1M -print`.
- Targeted reads of specs, config files, adapter skeletons, fake evaluator, CLI, runner, preflight, secret scanner, and tests.

No tests were run by this review because the task was report-only and several tests/CLI paths write generated artifacts under `runs/`.

## Recommendation

Do not accept Phase 4 yet. The core adapter and fake-eval safety direction is sound, but acceptance should be blocked until:

1. `adapters/models/` is no longer hidden by the generic `models/` ignore rule.
2. `validate-model` and `validate-benchmark` validate actual project config entries.
3. `run-eval` validates all user inputs before writing artifacts.
4. Secret scanning covers Phase 4 code and generated report/run artifacts.
5. The implementer intentionally selects which small fake artifacts, if any, belong in git, and confirms no large artifacts are tracked.
