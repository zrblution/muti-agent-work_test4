# Landmark Gate Failure

Status: `needs_attention`

- failure_type: `landmark_validation_gate_not_ready`
- failure_message: Landmark validation gates did not pass; no real model or benchmark execution was attempted.
- reproduction_command: `python -m stable_core.cli run-landmark --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --run-id qwen3vl_pope_limit8_gate_diagnostics`
- executed_real_model: `false`
- executed_real_benchmark: `false`
