# ArchitectureContractAgent Phase 1 Report

## Inputs Read

Remote implementation inspected under `SYSTEM_ROOT=/home/vepfs/data/work1/muti-agent-work_test4`, limited to the requested safe paths:

- `stable_core/schemas/__init__.py`
- `stable_core/schemas/common.py`
- `stable_core/runner/__init__.py`
- `stable_core/runner/base.py`
- `adapters/__init__.py`
- `adapters/models/__init__.py`
- `adapters/models/base.py`
- `adapters/benchmarks/__init__.py`
- `adapters/benchmarks/base.py`
- `adapters/metrics/__init__.py`
- `idea_plugins/base.py`
- `instrumentation/__init__.py`
- `instrumentation/base.py`
- `instrumentation/*/.gitkeep`
- `project_config/agents.yaml`
- `project_config/benchmarks.yaml`
- `project_config/experiment_budget.yaml`
- `project_config/git_policy.yaml`
- `project_config/instrumentation.yaml`
- `project_config/models.yaml`
- `project_config/paths.yaml`
- `project_config/security.yaml`
- `project_config/server.yaml`
- `tests/test_architecture_contracts.py`
- `tests/test_config_cli.py`
- `stable_core/cli.py`

Static boundary checks performed inside the same allowed code/config/test paths:

- Checked inspected `stable_core`, adapter, plugin, instrumentation, CLI files for project-specific absolute paths.
- Checked benchmark adapters do not import model adapters and model adapters do not import benchmark adapters.
- Checked inspected files/config/tests for obvious key/token-like patterns.

`.env` was not read. `stable_core.config` was not inspected because it is outside the safe-file list, even though `stable_core/cli.py` imports it.

## Coverage Matrix

| Contract area | Expected Phase 1 coverage | Observed implementation | Status |
|---|---|---|---|
| Server framework directories | Contract packages under `stable_core`, `adapters`, `idea_plugins`, `instrumentation`, and `project_config` | Required server-side contract directories/files now exist in the allowed inspection set | Covered |
| Core schemas | `Idea`, `EvidenceRef`, `AgentReview`, `ExperimentSpec`, `ExperimentResult`, `PhenomenonObservation`, `ConvergenceDecision`, `RunManifest`, `ArtifactManifest`, `ValidationReport`, plus generation request/output objects | `stable_core/schemas/common.py` defines these dataclasses, `to_dict()`, literal validation for key status fields, and `export_schema_registry()` | Covered with minor schema-depth risk |
| Model adapter interface | `validate_environment`, `load`, `generate`, `unload`, `supports_instrumentation`; raw text preserved by `GenerationOutput` | `adapters/models/base.py` defines a runtime-checkable `ModelAdapter` protocol with the required method names and canonical schema imports | Covered |
| Benchmark adapter interface | `validate_paths`, `build_requests`, `normalize_prediction`, `compute_metrics`, `extract_failure_cases` | `adapters/benchmarks/base.py` defines a runtime-checkable `BenchmarkAdapter` protocol with the required method names and no model imports | Covered |
| Idea plugin interface | `validate_compatibility`, `prepare`, `modify_request`, `wrap_generation`, `collect_artifacts` | `idea_plugins/base.py` defines a runtime-checkable `IdeaPlugin` protocol with the required method names | Covered |
| Probe / instrumentation interface | `attach`, `capture`, `flush`, `detach` | `instrumentation/base.py` defines a runtime-checkable `Probe` protocol with the required method names; probe subdirectories are represented by `.gitkeep` placeholders | Covered |
| Runner interface | `validate`, `submit`, `poll`, `resume`, `cancel` | `stable_core/runner/base.py` defines a runtime-checkable `ExperimentRunner` protocol with the required method names | Covered |
| Phase 1 CLI surface | `validate-config`, `list-models`, `list-benchmarks`, `list-agents`, `export-schemas` | `stable_core/cli.py` now registers and dispatches all required commands | Covered statically; dynamic behavior not verified because helper module is outside safe list |
| Config-driven listings | Config entries for models, benchmarks, agent providers, instrumentation, server policy, budget, paths | `project_config/*.yaml` contains expected model IDs, benchmark IDs, provider IDs, instrumentation defaults, budget, server action whitelist, security scan paths, git policy, and explicit roots | Covered |
| Stable-core path hygiene | No project-specific absolute paths in stable code | Static grep across allowed `stable_core/schemas`, `stable_core/runner`, `stable_core/cli.py`, adapters, plugin base, and instrumentation base returned no matches | Covered for inspected files |
| Adapter dependency boundary | Benchmark adapters should not import model adapters; model adapters should not import benchmark adapters | Static grep across `adapters/benchmarks` and `adapters/models` returned no cross-import matches | Covered |
| Architecture/config tests | Tests for schema serialization, protocol method presence, registry export, path hygiene, adapter boundaries, and CLI config commands | `tests/test_architecture_contracts.py` and `tests/test_config_cli.py` cover these surfaces | Covered statically |
| Fake end-to-end requirement | `08`/`09` describe Phase/MVP-1 as including fake end-to-end; local prompt defines Phase 1 as interface contracts and moves fake end-to-end later | No fake end-to-end requirement applied to this Phase 1 verdict; phase-numbering conflict remains documented | Not a Phase 1 blocker under local prompt |

## Findings

1. **Phase 1 interface contract files now exist and match the required method surfaces.** The inspected `ModelAdapter`, `BenchmarkAdapter`, `IdeaPlugin`, `Probe`, and `ExperimentRunner` protocols expose the method names specified by the architecture and durable-runner contracts.

2. **Core schema objects are now present and serializable.** `stable_core/schemas/common.py` defines the expected Phase 1 schema objects, includes `GenerationRequest`/`GenerationOutput`, validates several literal status fields, and provides a schema registry export path.

3. **Phase 1 CLI commands are now registered.** `stable_core/cli.py` includes `validate-config`, `list-models`, `list-benchmarks`, `list-agents`, and `export-schemas`; however, the implementation behind those commands lives in `stable_core.config`, which was outside the allowed inspection boundary and was not read.

4. **Config coverage is now broad enough for the contract layer.** `project_config` includes explicit path modeling, model/benchmark/provider registries, server action whitelist, instrumentation defaults, experiment budget, security scan settings, and git policy.

5. **Static boundary checks passed within the inspected file set.** No project-specific absolute paths were found in the inspected stable-core/adapter/plugin/instrumentation/CLI code; no model/benchmark adapter cross-imports were found; no obvious secret-like values were found in inspected files.

## Risks

- This was a read-only/static inspection. I did not run pytest or CLI commands because execution may read modules outside the safe-file list and may create cache/output files.
- `stable_core/cli.py` depends on `stable_core.config`, but that file was not included in the allowed inspection paths. CLI command registration is covered; runtime correctness of config parsing/export is not independently verified here.
- The schema implementation is intentionally lightweight dataclass-based. It covers object presence, serialization, and some literal validation, but generated JSON schemas are shallow and do not provide rich nested constraints or examples.
- Local-agent-side Phase 1 interfaces such as `AgentProvider` and `ProBridge` remain outside this server-only inspection scope.
- Fake end-to-end remains a documented phase-numbering conflict between `08`/`09` and `LOCAL_CODEX_IMPLEMENTATION_PROMPT.md`; it should be verified in the later phase defined by the local prompt.

## Acceptance Recommendation

Final verdict: **Accept Phase 1 server-side architecture/interface-contract static coverage, with dynamic verification deferred to the main TestVerificationAgent or integration step.**

The previously missing contract files and CLI surfaces are now present in the approved inspection paths. For full phase closure, run the relevant test commands in a non-read-only verification step, especially `pytest tests/test_architecture_contracts.py tests/test_config_cli.py`, and confirm the `stable_core.config` implementation that backs the CLI commands.
