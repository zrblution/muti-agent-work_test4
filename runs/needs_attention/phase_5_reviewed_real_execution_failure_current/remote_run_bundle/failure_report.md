# Landmark Gate Failure

Status: `needs_attention`

- failure_type: `landmark_worker_execution_failed`
- failure_message: Landmark worker execution failed; preserving failure diagnostics.
- reproduction_command: `python experiments/landmark_baselines/run_landmark.py --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --run-id qwen3vl_pope_limit8_real_smoke_authorized_retry_popeqa --runs-root runs`
- executed_real_model: `false`
- executed_real_benchmark: `false`
