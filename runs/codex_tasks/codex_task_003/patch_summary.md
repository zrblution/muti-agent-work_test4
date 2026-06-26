# Patch Summary: codex_task_003

## Changed Files
- Added server execution rules and spec pointer docs: `AGENTS.md`, `docs/specs_pointer.md`.
- Added security/config files: `.gitignore`, `.env.example`, `project_config/agents.yaml`, `project_config/paths.yaml`, `project_config/security.yaml`, `project_config/models.yaml`, `project_config/benchmarks.yaml`.
- Added Phase 0 implementation: `stable_core/security/secret_scan.py`, `stable_core/validation/preflight.py`, `stable_core/cli.py`.
- Added tests: `tests/test_secret_scan.py`, `tests/test_preflight.py`.
- Generated preflight/subagent artifacts under `runs/preflight/`, `runs/subagent_reports/phase_0/`, and `runs/artifacts/.gitkeep`.

## Why Changed
Phase 0 requires a safe, auditable startup gate before any model download, GPU benchmark, browser bridge, or multi-agent review work. The implementation validates paths, Git hygiene, provider secret handling, environment status, GPU status, model/benchmark setup status, and key-like secret leakage.

## Verification Commands Run
```bash
python -m pytest tests/test_secret_scan.py tests/test_preflight.py -q
python -m stable_core.cli preflight --dry-run
python -m stable_core.cli doctor
python -m stable_core.security.secret_scan --paths docs project_config stable_core tests runs .env.example .gitignore AGENTS.md README.md --output runs/preflight/secret_scan_report.json
ls runs/preflight/path_check.json runs/preflight/git_check.json runs/preflight/env_check.json runs/preflight/gpu_check.json runs/preflight/model_check.json runs/preflight/benchmark_check.json runs/preflight/secret_scan_report.json runs/preflight/preflight_summary.md
```

## Results
- Unit tests: `11 passed`.
- Preflight CLI: completed with status `needs_setup` because model and benchmark roots are not configured.
- Doctor CLI: completed with `preflight_status: needs_setup`.
- Secret scan: `status: passed`, no findings.
- Required preflight artifacts: generated.

## Remaining Risks
- Model root and benchmark root are still intentionally unconfigured. Later phases must not run real model/benchmark work until these paths validate.
- `git_check.json` records the working tree state at pre-commit preflight time. Final commit/push status is verified separately by Git commands.
- The initial test-verification subagent report was stale because it ran before implementation; the retry report supersedes it.

## Next Task Recommendation
Proceed to Phase 1 only after this Phase 0 patch is committed and pushed. Phase 1 should add architecture skeletons and interface contracts without downloading models or running real benchmarks.

## Git Commit
Planned commit message: `feat: add security preflight and config validation`.
