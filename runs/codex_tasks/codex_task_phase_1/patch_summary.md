# Patch Summary: Phase 1 Architecture Skeleton and Interface Contracts

## Changed Files
Server `SYSTEM_ROOT`:
- Added server-side packages and contracts under `adapters/`, `idea_plugins/`, `instrumentation/`, `stable_core/schemas/`, and `stable_core/runner/`.
- Added config utilities and CLI commands in `stable_core/config.py` and `stable_core/cli.py`.
- Added project config files: `project_config/server.yaml`, `project_config/experiment_budget.yaml`, `project_config/instrumentation.yaml`, `project_config/git_policy.yaml`.
- Added tests: `tests/test_architecture_contracts.py`, `tests/test_config_cli.py`.
- Generated schema exports under `runs/schema_exports/`.

Local `LOCAL_AGENT_SYSTEM_ROOT`:
- Added `agents/`, `prompts/`, `evidence/`, `orchestration/`, and run placeholder directories.
- Added local contracts: `agents/types.py`, `agents/providers/base.py`, `agents/pro_bridge/base.py`.

## Why Changed
Phase 1 establishes stable interface boundaries before implementing fake runs or real experiments. It gives later phases common schema objects, adapter protocols, runner protocols, and config-discovery CLI commands.

## Verification Commands Run
```bash
python -m pytest tests/test_architecture_contracts.py tests/test_config_cli.py tests/test_secret_scan.py tests/test_preflight.py -q
python -m stable_core.cli validate-config
python -m stable_core.cli list-models
python -m stable_core.cli list-benchmarks
python -m stable_core.cli list-agents
python -m stable_core.cli export-schemas --output runs/schema_exports
python -m stable_core.security.secret_scan --paths docs project_config stable_core adapters idea_plugins instrumentation experiments tests runs .env.example .gitignore AGENTS.md README.md --output runs/preflight/secret_scan_report.json
python3 -m py_compile <local AgentProvider/ProBridge files>
```

## Results
- Server tests: `21 passed`.
- Config validation: `passed`.
- Schema export: generated 12 JSON files.
- Secret scan: `passed`, no findings.
- Local contract compile check: passed.

## Remaining Risks
- Exported JSON schemas are shallow and should be strengthened before strict external use.
- Fake end-to-end runner is intentionally not implemented in this phase.
- Local agent skeleton changes are not part of the server Git repository.

## Next Task Recommendation
Proceed to Phase 2 Evidence Registry and Research Indexing only after this server patch is committed and pushed. Phase 2 should connect EvidenceRef usage to a real registry and baseline indexing without fabricating research results.

## Git Commit
Planned commit message: `feat: add architecture skeleton and interface contracts`.
