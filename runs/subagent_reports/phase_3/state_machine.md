# Phase 3 StateMachineAgent Read-Only Verification

## Scope

- System root: `/home/vepfs/data/work1/muti-agent-work_test4`
- Spec checked locally: `05_STATE_MACHINE_AND_DURABLE_RUNNER.md`
- Remote files inspected only from the requested safe set:
  - `stable_core/state_machine`
  - `stable_core/storage/run_directory.py`
  - `stable_core/cli.py`
  - `tests/test_state_machine.py`
  - `runs/*/state.json`
- `.env` was not read.

## Status

`blocked_missing_implementation`

The expected Phase 3 state-machine implementation files are not present at the requested system root, and no generated `runs/*/state.json` files exist to validate. The only present safe implementation file, `stable_core/cli.py`, does not expose the Phase 3 workflow commands required for init/status/resume/mark-failed behavior.

## Evidence

Remote existence checks showed:

- Missing: `stable_core/state_machine`
- Missing: `stable_core/storage/run_directory.py`
- Missing: `tests/test_state_machine.py`
- Present: `stable_core/cli.py`
- Generated state files: `0` matches for `runs/*/state.json`

`stable_core/cli.py` currently defines commands for preflight, doctor, config validation/listing, schema export, evidence registry operations, baseline indexing, and research status. It does not define workflow lifecycle commands such as `workflow init`, `workflow status`, `workflow resume`, `workflow mark-failed`, or the spec-listed `resume --workflow-id` runner command.

## Findings

### P0 - State-machine implementation is absent

The expected `stable_core/state_machine` package/file is missing, so there is no inspectable implementation for durable workflow states, state transitions, heartbeats, resume logic, or failure handling.

### P0 - Run-directory state support is absent

`stable_core/storage/run_directory.py` is missing. There is no inspectable storage abstraction for creating `runs/<workflow_id>/state.json`, preserving run artifacts, or coordinating durable state updates.

### P0 - State-machine tests are absent

`tests/test_state_machine.py` is missing. The Phase 3 acceptance cases from the spec are therefore not covered in the requested test file:

- `test_create_new_workflow_state`
- `test_resume_after_process_kill`
- `test_resume_after_partial_metrics_written`
- `test_no_duplicate_job_submission`
- `test_preserve_raw_outputs_on_reparse`
- `test_failed_job_preserves_stdout_stderr`
- `test_secret_scan_blocks_commit`
- `test_dirty_git_blocks_experiment_start`

### P0 - No generated state schema samples exist

No `runs/*/state.json` files exist under the system root. Schema coverage cannot be verified against generated artifacts.

Required `state.json` fields from the spec that are not currently evidenced by generated files include:

- `workflow_id`
- `current_state`
- `state_version`
- `round_id`
- `attempt`
- `status`
- `created_at`
- `updated_at`
- `last_heartbeat`
- `git`
- `inputs`
- `outputs`
- `run_dir`
- `remote_job`
- `failure`
- `next_allowed_actions`

### P0 - Workflow lifecycle commands are not implemented in CLI

The inspected `stable_core/cli.py` does not provide workflow init/status/resume/mark-failed commands. It also does not implement the spec-listed runner commands `run-fake`, `validate-model`, `validate-benchmark`, `run-landmark`, `poll`, `resume --workflow-id`, or `parse-results`.

### P1 - Heartbeat preservation behavior is not verifiable

Because no state-machine implementation or generated state exists, there is no evidence that `last_heartbeat` is written, updated, preserved across resume, or used to move timed-out remote jobs to `needs_attention` instead of blindly rerunning.

### P1 - Failure preservation behavior is not verifiable

Because no state-machine implementation, run-directory module, tests, or generated failure artifacts exist, there is no evidence that failed jobs preserve stdout/stderr tails, raw outputs, state snapshots, reproduction commands, or `failure.json` / `failure_report.md` as required by the spec.

## Conclusion

Phase 3 cannot be verified as implemented from the allowed files. The current result is a blocking implementation gap, not a behavioral pass/fail on a present state machine.
