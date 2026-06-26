# Phase 3 Acceptance Report

Status: passed

## Implemented Requirements

- Workflow state machine: `StateManager` persists `runs/<workflow_id>/state.json`.
- `state.json` schema: `WorkflowState` includes workflow ID, current state, version, round, attempt, status, timestamps, heartbeat, git snapshot, inputs, outputs, run dir, remote job, failure, and next allowed actions.
- Run directory management: `stable_core/storage/run_directory.py` creates safe run directories and writes JSON/text artifacts atomically.
- Checkpoint/resume/retry/heartbeat/failure preservation:
  - `checkpoint()` records outputs and remote job state.
  - `resume()` reloads and preserves existing state.
  - `retry()` increments attempts and clears prior failure after operator action.
  - `heartbeat()` updates `last_heartbeat`.
  - `check_heartbeat_timeout()` moves stale running workflows to `needs_attention`.
  - `mark_failed()` preserves structured failure details.
- Local runner: `LocalRunner.run_dummy()` writes stdout, stderr, exit code, command manifest, env snapshot, git commit, run manifest, artifact manifest, and failure artifacts on nonzero exit.
- Remote runner interface: `RemoteAction` and `RemoteRunner` validate structured whitelist actions only; no real remote execution is enabled in this phase.
- CLI:
  - `workflow init`
  - `workflow status`
  - `workflow resume`
  - `workflow mark-failed`
  - `run-local`
- Tests:
  - `tests/test_state_machine.py`
  - `tests/test_runner.py`

## Verification Results

- `python -m pytest tests/test_state_machine.py tests/test_runner.py -q`: `8 passed`.
- `python -m pytest tests/test_state_machine.py tests/test_runner.py tests/test_evidence_registry.py tests/test_research_indexing.py -q`: `15 passed`.
- `python -m pytest -q`: `36 passed`.
- CLI smoke for workflow lifecycle and dummy local run exited `0`.
- Secret scan exited `0`.

## Subagent Integration

All three phase 3 subagents reported missing implementation before the patch. The reports were consistent and are recorded under `runs/subagent_reports/phase_3/`. The integration summary records how each finding was addressed.

## Boundaries

- No model was downloaded or loaded.
- No GPU benchmark was run.
- No arbitrary shell command is accepted by the local or remote runner surfaces.
- No large artifacts are committed.
