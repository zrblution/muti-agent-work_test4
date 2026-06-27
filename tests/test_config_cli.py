import json
import os
import subprocess
import sys
from pathlib import Path

from stable_core import config as config_module
from stable_core.runner.remote import LANDMARK_SMOKE_ARTIFACT_CONTRACT
from stable_core.storage.run_directory import artifact_manifest_for, sha256_file
from stable_core.validation import phase5_readiness as phase5_module


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_fake_qwen_runtime_modules(module_root: Path) -> str:
    module_root.mkdir()
    (module_root / "transformers.py").write_text(
        "\n".join(
            [
                "class AutoProcessor:",
                "    pass",
                "",
                "class AutoModelForMultimodalLM:",
                "    pass",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (module_root / "torch.py").write_text(
        "\n".join(
            [
                "bfloat16 = 'bf16-dtype'",
                "float16 = 'fp16-dtype'",
                "float32 = 'fp32-dtype'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return str(module_root)


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stable_core.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _phase5_safety_flags() -> dict[str, bool]:
    return {
        "executed_real_model": False,
        "executed_real_benchmark": False,
        "submitted_remote_job": False,
        "raw_outputs_written": False,
        "write_config": False,
    }


def _write_passed_phase5_gate_chain(tmp_path: Path) -> dict[str, Path]:
    target = {"model_id": "qwen3_vl_2b_instruct", "benchmark_id": "pope"}
    safety_flags = _phase5_safety_flags()
    paths = {
        "decision_request": tmp_path / "phase5_model_path_decision_request.json",
        "decision_validation": tmp_path / "phase5_model_path_decision_validation.json",
        "approved_readiness": tmp_path / "phase5_approved_decision_readiness.json",
        "config_proposal": tmp_path / "phase5_config_representation_proposal.json",
        "config_decision_validation": tmp_path / "phase5_config_representation_decision_validation.json",
        "readiness": tmp_path / "phase5_readiness.json",
    }
    approved_paths = {"model_path": "/models/variant/Ours", "benchmark_root": "/benchmarks"}
    _write_json(
        paths["decision_request"],
        {
            "phase": "Phase 5",
            "mode": "model_path_decision_request",
            "status": "needs_attention",
            "approval_status": "pending",
            "target": {**target, **approved_paths},
            "safety_flags": safety_flags,
        },
    )
    _write_json(
        paths["decision_validation"],
        {
            "phase": "Phase 5",
            "mode": "model_path_decision_validation",
            "status": "passed",
            "approval_status": "approved",
            "target": {**target, **approved_paths},
            "decision": {
                "decision": "approve_variant_path",
                "approved_model_path": approved_paths["model_path"],
                "approved_benchmark_root": approved_paths["benchmark_root"],
            },
            "safety_flags": safety_flags,
        },
    )
    _write_json(
        paths["approved_readiness"],
        {
            "phase": "Phase 5",
            "mode": "approved_model_path_readiness",
            "status": "needs_attention",
            "approval_status": "approved",
            "ready_for_real_smoke": False,
            "target": target,
            "approved_paths": approved_paths,
            "safety_flags": safety_flags,
        },
    )
    _write_json(
        paths["config_proposal"],
        {
            "phase": "Phase 5",
            "mode": "config_representation_proposal",
            "status": "needs_attention",
            "ready_for_real_smoke": False,
            "write_config": False,
            "exports_applied": False,
            "target": target,
            "approved_paths": approved_paths,
            "representation_options": [
                {
                    "name": "explicit_local_path_override",
                    "proposed_models_yaml": {"local_path": approved_paths["model_path"]},
                }
            ],
            "safety_flags": safety_flags,
        },
    )
    _write_json(
        paths["config_decision_validation"],
        {
            "phase": "Phase 5",
            "mode": "config_representation_decision_validation",
            "status": "passed",
            "config_review_status": "approved",
            "ready_for_real_smoke": False,
            "write_config": False,
            "exports_applied": False,
            "target": target,
            "selected_option": {"name": "explicit_local_path_override"},
            "safety_flags": safety_flags,
        },
    )
    _write_json(
        paths["readiness"],
        {
            "phase": "Phase 5",
            "status": "passed",
            "target": {
                **target,
                "limit": 8,
                "instrumentation_mode": "none",
            },
            "execution_authorization": {
                "status": "passed",
                "execution_plan": {"submits_process": True},
            },
            "safety_flags": safety_flags,
        },
    )
    return paths


def _write_landmark_failure_run(runs_root: Path, run_id: str, *, failure_type: str) -> Path:
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True)
    command = {
        "run_id": run_id,
        "command": "landmark-worker",
        "model_id": "qwen3_vl_2b_instruct",
        "benchmark_id": "pope",
        "limit": 8,
        "instrumentation_mode": "none",
        "controlled": True,
    }
    run_manifest = {
        "run_id": run_id,
        "run_type": "landmark_baseline",
        "model_id": "qwen3_vl_2b_instruct",
        "benchmark_id": "pope",
        "idea_id": None,
        "limit": 8,
        "instrumentation_mode": "none",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
        "status": "needs_attention",
        "git_commit": "test",
        "outputs": {
            "stdout": "stdout.log",
            "stderr": "stderr.log",
            "exit_code": "exit_code.txt",
        },
        "artifact_contract": dict(LANDMARK_SMOKE_ARTIFACT_CONTRACT),
    }
    failure = {
        "phase": "Phase 5",
        "status": "needs_attention",
        "failure_type": failure_type,
        "failure_message": "Preserved failure diagnostics.",
        "gate_failures": [{"gate": "worker-execution", "payload": {"status": "needs_attention"}}],
        "stdout_tail": "",
        "stderr_tail": "traceback tail",
        "reproduction_command": "python experiments/landmark_baselines/run_landmark.py --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none --run-id "
        + run_id,
        "config_snapshot": command,
        "state_snapshot": run_manifest,
        "executed_real_model": False,
        "executed_real_benchmark": False,
        "recommended_next_action": ["Inspect preserved diagnostics."],
        "do_not_continue_reason": "Real smoke did not succeed.",
    }
    _write_json(run_dir / "command_manifest.json", command)
    _write_json(run_dir / "env_snapshot.json", {"env": {}})
    (run_dir / "git_commit.txt").write_text("test\n", encoding="utf-8")
    (run_dir / "stdout.log").write_text("", encoding="utf-8")
    (run_dir / "stderr.log").write_text("traceback tail\n", encoding="utf-8")
    (run_dir / "exit_code.txt").write_text("1\n", encoding="utf-8")
    _write_json(run_dir / "run_manifest.json", run_manifest)
    _write_json(run_dir / "failure.json", failure)
    (run_dir / "failure_report.md").write_text("# Failure\n", encoding="utf-8")
    _write_json(run_dir / "artifact_manifest.json", artifact_manifest_for(run_dir, run_id))
    return run_dir


def test_validate_config_cli_reports_passed() -> None:
    result = run_cli("validate-config")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "validate-config"
    assert payload["status"] == "passed"
    assert payload["providers"]["status"] == "passed"


def test_validate_config_rejects_unsafe_required_files(monkeypatch, tmp_path: Path) -> None:
    for name in [
        "paths.yaml",
        "security.yaml",
        "server.yaml",
        "experiment_budget.yaml",
        "instrumentation.yaml",
        "git_policy.yaml",
    ]:
        (tmp_path / name).write_text("{}\n", encoding="utf-8")
    (tmp_path / "agents.yaml").write_text(
        "\n".join(
            [
                "providers:",
                "  test_provider:",
                "    provider_type: openai_compatible",
                "    model: test-model",
                "    api_key_env: TEST_PROVIDER_API_KEY",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "models.yaml").write_text(
        "\n".join(
            [
                "models:",
                "  unsafe_model:",
                "    adapter: adapters.models.qwen3_vl.Qwen3VLAdapter",
                "    required_files: [\"../escape.json\"]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "benchmarks.yaml").write_text(
        "\n".join(
            [
                "benchmarks:",
                "  unsafe_benchmark:",
                "    adapter: adapters.benchmarks.pope.POPEAdapter",
                "    required_files: [\"/tmp/escape.json\"]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)

    report = config_module.validate_config()

    assert report["status"] == "failed"
    assert report["inventory"]["status"] == "failed"
    assert {
        "section": "models",
        "id": "unsafe_model",
        "field": "required_files",
        "value": "../escape.json",
        "message": "required_files entries must be relative paths inside the configured root",
    } in report["inventory"]["findings"]
    assert {
        "section": "benchmarks",
        "id": "unsafe_benchmark",
        "field": "required_files",
        "value": "/tmp/escape.json",
        "message": "required_files entries must be relative paths inside the configured root",
    } in report["inventory"]["findings"]


def test_validate_config_rejects_block_list_required_files(monkeypatch, tmp_path: Path) -> None:
    for name in [
        "paths.yaml",
        "security.yaml",
        "server.yaml",
        "experiment_budget.yaml",
        "instrumentation.yaml",
        "git_policy.yaml",
    ]:
        (tmp_path / name).write_text("{}\n", encoding="utf-8")
    (tmp_path / "agents.yaml").write_text(
        "\n".join(
            [
                "providers:",
                "  test_provider:",
                "    provider_type: openai_compatible",
                "    model: test-model",
                "    api_key_env: TEST_PROVIDER_API_KEY",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "models.yaml").write_text(
        "\n".join(
            [
                "models:",
                "  unsafe_model:",
                "    adapter: adapters.models.qwen3_vl.Qwen3VLAdapter",
                "    required_files:",
                "      - ../escape.json",
                "      - config.json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "benchmarks.yaml").write_text(
        "\n".join(
            [
                "benchmarks:",
                "  unsafe_benchmark:",
                "    adapter: adapters.benchmarks.pope.POPEAdapter",
                "    required_files:",
                "      - /tmp/escape.json",
                "      - annotations/random.json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)

    report = config_module.validate_config()

    assert report["status"] == "failed"
    assert {
        "section": "models",
        "id": "unsafe_model",
        "field": "required_files",
        "value": "../escape.json",
        "message": "required_files entries must be relative paths inside the configured root",
    } in report["inventory"]["findings"]
    assert {
        "section": "benchmarks",
        "id": "unsafe_benchmark",
        "field": "required_files",
        "value": "/tmp/escape.json",
        "message": "required_files entries must be relative paths inside the configured root",
    } in report["inventory"]["findings"]


def test_list_model_benchmark_and_agent_clis_read_config() -> None:
    models = json.loads(run_cli("list-models").stdout)
    benchmarks = json.loads(run_cli("list-benchmarks").stdout)
    agents = json.loads(run_cli("list-agents").stdout)

    assert models["models"] == ["fake_model", "internvl3_5_4b", "qwen3_vl_2b_instruct"]
    assert benchmarks["benchmarks"] == ["amber", "chair", "fake_benchmark", "mme", "pope"]
    assert agents["providers"] == ["deepseek_v4_pro", "opus4_8_proxy"]


def test_discover_benchmark_inventory_cli_reports_missing_env(tmp_path: Path) -> None:
    output_path = tmp_path / "pope_inventory.json"
    env = os.environ.copy()
    env.pop("REMOTE_BENCHMARK_ROOT", None)

    result = run_cli("discover-benchmark-inventory", "pope", "--output", str(output_path), env=env)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "discover-benchmark-inventory"
    assert payload["status"] == "needs_setup"
    assert payload["benchmark_id"] == "pope"
    assert payload["missing_env_var"] == "REMOTE_BENCHMARK_ROOT"
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "needs_setup"


def test_discover_benchmark_inventory_cli_writes_reviewable_candidates(tmp_path: Path) -> None:
    benchmark_root = tmp_path / "benchmarks"
    pope_path = benchmark_root / "POPE"
    (pope_path / "annotations").mkdir(parents=True)
    (pope_path / "samples.jsonl").write_text("{}\n", encoding="utf-8")
    (pope_path / "annotations" / "random.json").write_text("[]\n", encoding="utf-8")
    (pope_path / "image.jpg").write_text("not metadata\n", encoding="utf-8")
    output_path = tmp_path / "pope_inventory.json"
    env = {**os.environ, "REMOTE_BENCHMARK_ROOT": str(benchmark_root)}

    result = run_cli("discover-benchmark-inventory", "pope", "--output", str(output_path), env=env)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["benchmark_id"] == "pope"
    assert set(payload["discovered_files"]) == {"samples.jsonl", "annotations/random.json"}
    assert payload["write_config"] is False
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["discovered_files"] == payload["discovered_files"]


def test_discover_model_inventory_cli_reports_missing_env(tmp_path: Path) -> None:
    output_path = tmp_path / "qwen_inventory.json"
    env = os.environ.copy()
    env.pop("REMOTE_MODEL_ROOT", None)

    result = run_cli("discover-model-inventory", "qwen3_vl_2b_instruct", "--output", str(output_path), env=env)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "discover-model-inventory"
    assert payload["status"] == "needs_setup"
    assert payload["model_id"] == "qwen3_vl_2b_instruct"
    assert payload["missing_env_var"] == "REMOTE_MODEL_ROOT"
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "needs_setup"


def test_discover_model_inventory_cli_writes_reviewable_candidates(tmp_path: Path) -> None:
    model_root = tmp_path / "models"
    model_path = model_root / "Qwen3-VL-2B-Instruct"
    model_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}\n", encoding="utf-8")
    (model_path / "tokenizer_config.json").write_text("{}\n", encoding="utf-8")
    (model_path / "preprocessor_config.json").write_text("{}\n", encoding="utf-8")
    (model_path / "model.safetensors").write_text("large weight placeholder\n", encoding="utf-8")
    output_path = tmp_path / "qwen_inventory.json"
    env = {**os.environ, "REMOTE_MODEL_ROOT": str(model_root)}

    result = run_cli("discover-model-inventory", "qwen3_vl_2b_instruct", "--output", str(output_path), env=env)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["model_id"] == "qwen3_vl_2b_instruct"
    assert set(payload["discovered_files"]) == {"config.json", "tokenizer_config.json", "preprocessor_config.json"}
    assert "model.safetensors" not in payload["discovered_files"]
    assert payload["write_config"] is False
    assert payload["load_attempted"] is False
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["discovered_files"] == payload["discovered_files"]


def test_phase5_readiness_cli_writes_needs_attention_bundle_without_env(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("REMOTE_MODEL_ROOT", None)
    env.pop("REMOTE_BENCHMARK_ROOT", None)
    fake_runtime_path = _write_fake_qwen_runtime_modules(tmp_path / "fake_qwen_runtime")
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in [fake_runtime_path, os.environ.get("PYTHONPATH", "")] if item
    )

    result = run_cli(
        "phase5-readiness",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--output-dir",
        str(tmp_path),
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "phase5-readiness"
    assert payload["status"] == "needs_attention"
    assert payload["executed_real_model"] is False
    assert payload["executed_real_benchmark"] is False
    assert payload["submitted_remote_job"] is False
    assert payload["raw_outputs_written"] is False

    report_path = tmp_path / "phase5_readiness.json"
    summary_path = tmp_path / "phase5_readiness.md"
    assert report_path.exists()
    assert summary_path.exists()
    assert "raw_outputs.jsonl" not in {path.name for path in tmp_path.iterdir()}

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "needs_attention"
    assert report["checks"]["model_inventory_discovery"]["missing_env_var"] == "REMOTE_MODEL_ROOT"
    assert report["checks"]["benchmark_inventory_discovery"]["missing_env_var"] == "REMOTE_BENCHMARK_ROOT"
    assert report["checks"]["model_runtime_dependencies"]["status"] == "passed"
    assert report["checks"]["model_validation"]["status"] == "needs_setup"
    assert report["checks"]["benchmark_validation"]["status"] == "needs_setup"
    assert report["execution_authorization"]["status"] == "needs_attention"
    assert {failure["name"] for failure in report["execution_authorization"]["gate_failures"]} == {
        "runner_mode",
        "real_gpu_budget",
        "process_submission",
    }
    assert report["safety_flags"] == {
        "executed_real_model": False,
        "executed_real_benchmark": False,
        "submitted_remote_job": False,
        "raw_outputs_written": False,
        "write_config": False,
    }


def test_validate_model_runtime_cli_does_not_require_model_path(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("REMOTE_MODEL_ROOT", None)
    fake_runtime_path = _write_fake_qwen_runtime_modules(tmp_path / "fake_qwen_runtime")
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in [fake_runtime_path, os.environ.get("PYTHONPATH", "")] if item
    )

    result = run_cli("validate-model-runtime", "qwen3_vl_2b_instruct", env=env)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    runtime_check = next(check for check in payload["checks"] if check["name"] == "runtime_dependencies")
    assert payload["command"] == "validate-model-runtime"
    assert payload["model_id"] == "qwen3_vl_2b_instruct"
    assert payload["status"] == "passed"
    assert runtime_check["status"] == "passed"
    assert runtime_check["load_attempted"] is False


def test_phase5_readiness_cli_keeps_execution_closed_after_inventory_passes(tmp_path: Path) -> None:
    model_root = tmp_path / "models"
    model_path = model_root / "Qwen3-VL-2B-Instruct"
    model_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}\n", encoding="utf-8")
    benchmark_root = tmp_path / "benchmarks"
    benchmark_path = benchmark_root / "POPE"
    benchmark_path.mkdir(parents=True)
    (benchmark_path / "samples.jsonl").write_text("{}\n", encoding="utf-8")
    output_dir = tmp_path / "readiness"
    fake_runtime_path = _write_fake_qwen_runtime_modules(tmp_path / "fake_qwen_runtime")
    env = {
        **os.environ,
        "REMOTE_MODEL_ROOT": str(model_root),
        "REMOTE_BENCHMARK_ROOT": str(benchmark_root),
        "PYTHONPATH": os.pathsep.join(
            item for item in [fake_runtime_path, os.environ.get("PYTHONPATH", "")] if item
        ),
    }

    result = run_cli(
        "phase5-readiness",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--output-dir",
        str(output_dir),
        env=env,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads((output_dir / "phase5_readiness.json").read_text(encoding="utf-8"))
    runtime_check = next(
        check for check in report["checks"]["model_validation"]["checks"] if check["name"] == "runtime_dependencies"
    )
    assert report["checks"]["model_validation"]["status"] == "passed"
    assert report["checks"]["model_runtime_dependencies"]["status"] == "passed"
    assert runtime_check["status"] == "passed"
    assert report["checks"]["benchmark_validation"]["status"] == "passed"
    assert report["checks"]["model_inventory_discovery"]["status"] == "passed"
    assert report["checks"]["benchmark_inventory_discovery"]["status"] == "passed"
    assert report["status"] == "needs_attention"
    assert report["execution_authorization"]["execution_plan"]["submits_process"] is False
    assert "job_id" not in report["execution_authorization"]
    assert report["safety_flags"]["submitted_remote_job"] is False
    assert not (output_dir / "raw_outputs.jsonl").exists()


def test_phase5_probe_paths_cli_validates_candidate_roots_without_config_env(tmp_path: Path) -> None:
    model_root = tmp_path / "models"
    model_path = model_root / "Qwen3-VL-2B-Instruct"
    model_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}\n", encoding="utf-8")
    benchmark_root = tmp_path / "benchmarks"
    benchmark_path = benchmark_root / "POPE"
    benchmark_path.mkdir(parents=True)
    (benchmark_path / "samples.jsonl").write_text("{}\n", encoding="utf-8")
    fake_runtime_path = _write_fake_qwen_runtime_modules(tmp_path / "fake_qwen_runtime")
    output_path = tmp_path / "probe.json"
    env = os.environ.copy()
    env.pop("REMOTE_MODEL_ROOT", None)
    env.pop("REMOTE_BENCHMARK_ROOT", None)
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in [fake_runtime_path, os.environ.get("PYTHONPATH", "")] if item
    )

    result = run_cli(
        "phase5-probe-paths",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--model-root",
        str(model_root),
        "--benchmark-root",
        str(benchmark_root),
        "--output",
        str(output_path),
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["command"] == "phase5-probe-paths"
    assert payload["status"] == "passed"
    assert written["status"] == "passed"
    assert written["candidate_env"]["REMOTE_MODEL_ROOT"] == str(model_root)
    assert written["candidate_env"]["REMOTE_BENCHMARK_ROOT"] == str(benchmark_root)
    assert written["checks"]["model_validation"]["status"] == "passed"
    assert written["checks"]["benchmark_validation"]["status"] == "passed"
    assert written["safety_flags"]["write_config"] is False
    assert written["safety_flags"]["executed_real_model"] is False
    assert "raw_outputs.jsonl" not in {path.name for path in tmp_path.iterdir()}


def test_phase5_probe_paths_restores_existing_environment(monkeypatch, tmp_path: Path) -> None:
    model_root = tmp_path / "models"
    benchmark_root = tmp_path / "benchmarks"
    monkeypatch.setenv("REMOTE_MODEL_ROOT", "original-model-root")
    monkeypatch.setenv("REMOTE_BENCHMARK_ROOT", "original-benchmark-root")

    report = phase5_module.build_phase5_path_probe(
        model_id="qwen3_vl_2b_instruct",
        benchmark_id="pope",
        model_root=model_root,
        benchmark_root=benchmark_root,
    )

    assert report["candidate_env"]["REMOTE_MODEL_ROOT"] == str(model_root)
    assert report["candidate_env"]["REMOTE_BENCHMARK_ROOT"] == str(benchmark_root)
    assert os.environ["REMOTE_MODEL_ROOT"] == "original-model-root"
    assert os.environ["REMOTE_BENCHMARK_ROOT"] == "original-benchmark-root"
    assert report["safety_flags"]["write_config"] is False


def test_phase5_probe_explicit_model_path_cli_validates_variant_without_config_root(tmp_path: Path) -> None:
    model_path = tmp_path / "variant_models" / "Qwen3-VL-2B-3epoch" / "Ours"
    model_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}\n", encoding="utf-8")
    (model_path / "model.safetensors").write_text("weight placeholder\n", encoding="utf-8")
    benchmark_root = tmp_path / "benchmarks"
    benchmark_path = benchmark_root / "POPE"
    benchmark_path.mkdir(parents=True)
    (benchmark_path / "samples.jsonl").write_text("{}\n", encoding="utf-8")
    fake_runtime_path = _write_fake_qwen_runtime_modules(tmp_path / "fake_qwen_runtime")
    output_path = tmp_path / "explicit_probe.json"
    env = os.environ.copy()
    env.pop("REMOTE_MODEL_ROOT", None)
    env.pop("REMOTE_BENCHMARK_ROOT", None)
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in [fake_runtime_path, os.environ.get("PYTHONPATH", "")] if item
    )

    result = run_cli(
        "phase5-probe-explicit-model-path",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--model-path",
        str(model_path),
        "--benchmark-root",
        str(benchmark_root),
        "--output",
        str(output_path),
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["command"] == "phase5-probe-explicit-model-path"
    assert payload["status"] == "passed"
    assert written["status"] == "passed"
    assert written["candidate_model_path"] == str(model_path)
    assert written["configured_root_contract"]["satisfied"] is False
    assert written["requires_human_approval"] is True
    assert written["checks"]["model_explicit_path_validation"]["status"] == "passed"
    assert written["checks"]["benchmark_validation"]["status"] == "passed"
    assert written["safety_flags"] == {
        "executed_real_model": False,
        "executed_real_benchmark": False,
        "submitted_remote_job": False,
        "raw_outputs_written": False,
        "write_config": False,
    }
    assert "raw_outputs.jsonl" not in {path.name for path in tmp_path.iterdir()}


def test_phase5_probe_explicit_model_path_restores_existing_environment(monkeypatch, tmp_path: Path) -> None:
    model_path = tmp_path / "variant"
    benchmark_root = tmp_path / "benchmarks"
    monkeypatch.setenv("REMOTE_MODEL_ROOT", "original-model-root")
    monkeypatch.setenv("REMOTE_BENCHMARK_ROOT", "original-benchmark-root")

    report = phase5_module.build_phase5_explicit_model_path_probe(
        model_id="qwen3_vl_2b_instruct",
        benchmark_id="pope",
        model_path=model_path,
        benchmark_root=benchmark_root,
    )

    assert report["candidate_model_path"] == str(model_path)
    assert os.environ["REMOTE_MODEL_ROOT"] == "original-model-root"
    assert os.environ["REMOTE_BENCHMARK_ROOT"] == "original-benchmark-root"
    assert report["safety_flags"]["write_config"] is False


def test_phase5_model_path_decision_request_cli_writes_pending_review_packet(tmp_path: Path) -> None:
    model_path = tmp_path / "variant_models" / "Qwen3-VL-2B-3epoch" / "Ours"
    model_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}\n", encoding="utf-8")
    (model_path / "model.safetensors").write_text("weight placeholder\n", encoding="utf-8")
    benchmark_root = tmp_path / "benchmarks"
    benchmark_path = benchmark_root / "POPE"
    benchmark_path.mkdir(parents=True)
    (benchmark_path / "samples.jsonl").write_text("{}\n", encoding="utf-8")
    fake_runtime_path = _write_fake_qwen_runtime_modules(tmp_path / "fake_qwen_runtime")
    output_dir = tmp_path / "decision_request"
    env = os.environ.copy()
    env.pop("REMOTE_MODEL_ROOT", None)
    env.pop("REMOTE_BENCHMARK_ROOT", None)
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in [fake_runtime_path, os.environ.get("PYTHONPATH", "")] if item
    )

    result = run_cli(
        "phase5-model-path-decision-request",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--model-path",
        str(model_path),
        "--benchmark-root",
        str(benchmark_root),
        "--output-dir",
        str(output_dir),
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads((output_dir / "phase5_model_path_decision_request.json").read_text(encoding="utf-8"))
    markdown = (output_dir / "phase5_model_path_decision_request.md").read_text(encoding="utf-8")
    assert payload["command"] == "phase5-model-path-decision-request"
    assert payload["status"] == "needs_attention"
    assert payload["approval_status"] == "pending"
    assert report["status"] == "needs_attention"
    assert report["approval_status"] == "pending"
    assert report["requested_decision"]["allowed_decisions"] == [
        "approve_variant_path",
        "reject_variant_path",
        "provide_base_model_root",
    ]
    templates = {
        template["decision"]: template
        for template in report["requested_decision"]["decision_record_templates"]
    }
    assert set(templates) == {
        "approve_variant_path",
        "reject_variant_path",
        "provide_base_model_root",
    }
    assert templates["approve_variant_path"]["approved_model_path"] == str(model_path)
    assert templates["approve_variant_path"]["approved_benchmark_root"] == str(benchmark_root)
    assert templates["reject_variant_path"]["rejected_model_path"] == str(model_path)
    assert templates["reject_variant_path"]["approved_model_path"] is None
    assert templates["provide_base_model_root"]["provided_model_root"] is None
    assert templates["provide_base_model_root"]["approved_benchmark_root"] == str(benchmark_root)
    assert report["probe"]["status"] == "passed"
    assert report["probe"]["requires_human_approval"] is True
    assert report["safety_flags"]["write_config"] is False
    assert report["safety_flags"]["executed_real_model"] is False
    assert "approval_status: `pending`" in markdown
    assert "- approve_variant_path: model_path `" in markdown
    assert "- reject_variant_path: rejected_model_path `" in markdown
    assert "- provide_base_model_root: provided_model_root `None`" in markdown
    assert "raw_outputs.jsonl" not in {path.name for path in output_dir.iterdir()}


def test_phase5_model_path_decision_request_restores_existing_environment(monkeypatch, tmp_path: Path) -> None:
    model_path = tmp_path / "variant"
    benchmark_root = tmp_path / "benchmarks"
    output_dir = tmp_path / "decision_request"
    monkeypatch.setenv("REMOTE_MODEL_ROOT", "original-model-root")
    monkeypatch.setenv("REMOTE_BENCHMARK_ROOT", "original-benchmark-root")

    report = phase5_module.build_phase5_model_path_decision_request(
        model_id="qwen3_vl_2b_instruct",
        benchmark_id="pope",
        model_path=model_path,
        benchmark_root=benchmark_root,
        output_dir=output_dir,
    )

    assert report["approval_status"] == "pending"
    assert os.environ["REMOTE_MODEL_ROOT"] == "original-model-root"
    assert os.environ["REMOTE_BENCHMARK_ROOT"] == "original-benchmark-root"
    assert report["safety_flags"]["write_config"] is False


def test_phase5_validate_model_path_decision_cli_accepts_matching_human_approval_record(tmp_path: Path) -> None:
    model_path = tmp_path / "variant_models" / "Qwen3-VL-2B-3epoch" / "Ours"
    model_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}\n", encoding="utf-8")
    (model_path / "model.safetensors").write_text("weight placeholder\n", encoding="utf-8")
    benchmark_root = tmp_path / "benchmarks"
    benchmark_path = benchmark_root / "POPE"
    benchmark_path.mkdir(parents=True)
    (benchmark_path / "samples.jsonl").write_text("{}\n", encoding="utf-8")
    fake_runtime_path = _write_fake_qwen_runtime_modules(tmp_path / "fake_qwen_runtime")
    request_dir = tmp_path / "decision_request"
    env = os.environ.copy()
    env.pop("REMOTE_MODEL_ROOT", None)
    env.pop("REMOTE_BENCHMARK_ROOT", None)
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in [fake_runtime_path, os.environ.get("PYTHONPATH", "")] if item
    )
    request_result = run_cli(
        "phase5-model-path-decision-request",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--model-path",
        str(model_path),
        "--benchmark-root",
        str(benchmark_root),
        "--output-dir",
        str(request_dir),
        env=env,
    )
    assert request_result.returncode == 0, request_result.stderr
    request_path = request_dir / "phase5_model_path_decision_request.json"
    decision_path = tmp_path / "decision_record.json"
    decision_path.write_text(
        json.dumps(
            {
                "decision": "approve_variant_path",
                "approver": "human-reviewer",
                "approved_model_path": str(model_path),
                "approved_benchmark_root": str(benchmark_root),
                "rationale": "Approved exact temporary path for validation-gate coverage.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "decision_validation.json"

    result = run_cli(
        "phase5-validate-model-path-decision",
        "--request",
        str(request_path),
        "--decision-record",
        str(decision_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["command"] == "phase5-validate-model-path-decision"
    assert payload["status"] == "passed"
    assert payload["approval_status"] == "approved"
    assert report["status"] == "passed"
    assert report["approval_status"] == "approved"
    assert report["decision"]["decision"] == "approve_variant_path"
    assert report["checks"]["approved_model_path_matches"]["status"] == "passed"
    assert report["checks"]["approved_benchmark_root_matches"]["status"] == "passed"
    assert report["safety_flags"]["executed_real_model"] is False
    assert report["safety_flags"]["write_config"] is False
    assert "raw_outputs.jsonl" not in {path.name for path in tmp_path.iterdir()}


def test_phase5_validate_model_path_decision_rejects_mismatched_approval_path(tmp_path: Path) -> None:
    request_path = tmp_path / "decision_request.json"
    decision_path = tmp_path / "decision_record.json"
    output_path = tmp_path / "decision_validation.json"
    request_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "model_path_decision_request",
                "status": "needs_attention",
                "approval_status": "pending",
                "target": {
                    "model_id": "qwen3_vl_2b_instruct",
                    "benchmark_id": "pope",
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "probe": {
                    "status": "passed",
                    "requires_human_approval": True,
                },
                "requested_decision": {
                    "allowed_decisions": [
                        "approve_variant_path",
                        "reject_variant_path",
                        "provide_base_model_root",
                    ],
                },
                "safety_flags": {
                    "executed_real_model": False,
                    "executed_real_benchmark": False,
                    "submitted_remote_job": False,
                    "raw_outputs_written": False,
                    "write_config": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision_path.write_text(
        json.dumps(
            {
                "decision": "approve_variant_path",
                "approver": "human-reviewer",
                "approved_model_path": "/models/other/Ours",
                "approved_benchmark_root": "/benchmarks",
                "rationale": "This path should not match the pending request.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = phase5_module.validate_phase5_model_path_decision(
        request_path=request_path,
        decision_record_path=decision_path,
        output=output_path,
    )

    assert report["status"] == "failed"
    assert report["approval_status"] == "invalid"
    assert report["checks"]["approved_model_path_matches"]["status"] == "failed"
    assert report["checks"]["approved_benchmark_root_matches"]["status"] == "passed"
    assert report["safety_flags"]["write_config"] is False
    assert json.loads(output_path.read_text(encoding="utf-8"))["approval_status"] == "invalid"


def test_phase5_approved_decision_readiness_cli_writes_non_executing_bundle(tmp_path: Path) -> None:
    decision_validation_path = tmp_path / "decision_validation.json"
    output_dir = tmp_path / "approved_readiness"
    decision_validation_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "model_path_decision_validation",
                "status": "passed",
                "approval_status": "approved",
                "target": {
                    "model_id": "qwen3_vl_2b_instruct",
                    "benchmark_id": "pope",
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "decision": {
                    "decision": "approve_variant_path",
                    "approver": "human-reviewer",
                    "approved_model_path": "/models/variant/Ours",
                    "approved_benchmark_root": "/benchmarks",
                    "rationale": "Approved for readiness-planning test.",
                },
                "checks": {
                    "approved_model_path_matches": {"status": "passed"},
                    "approved_benchmark_root_matches": {"status": "passed"},
                },
                "safety_flags": {
                    "executed_real_model": False,
                    "executed_real_benchmark": False,
                    "submitted_remote_job": False,
                    "raw_outputs_written": False,
                    "write_config": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_cli(
        "phase5-approved-decision-readiness",
        "--decision-validation",
        str(decision_validation_path),
        "--output-dir",
        str(output_dir),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads((output_dir / "phase5_approved_decision_readiness.json").read_text(encoding="utf-8"))
    markdown = (output_dir / "phase5_approved_decision_readiness.md").read_text(encoding="utf-8")
    assert payload["command"] == "phase5-approved-decision-readiness"
    assert payload["status"] == "needs_attention"
    assert payload["approval_status"] == "approved"
    assert payload["ready_for_real_smoke"] is False
    assert report["status"] == "needs_attention"
    assert report["approval_status"] == "approved"
    assert report["ready_for_real_smoke"] is False
    assert report["approved_paths"]["model_path"] == "/models/variant/Ours"
    assert report["approved_paths"]["benchmark_root"] == "/benchmarks"
    assert report["checks"]["decision_validation"]["status"] == "passed"
    assert report["safety_flags"]["submitted_remote_job"] is False
    assert report["safety_flags"]["write_config"] is False
    assert "ready_for_real_smoke: `false`" in markdown
    assert "raw_outputs.jsonl" not in {path.name for path in output_dir.iterdir()}


def test_phase5_approved_decision_readiness_rejects_invalid_validation_report(tmp_path: Path) -> None:
    decision_validation_path = tmp_path / "decision_validation.json"
    output_dir = tmp_path / "approved_readiness"
    decision_validation_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "model_path_decision_validation",
                "status": "failed",
                "approval_status": "invalid",
                "target": {
                    "model_id": "qwen3_vl_2b_instruct",
                    "benchmark_id": "pope",
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "decision": {
                    "decision": "approve_variant_path",
                    "approved_model_path": "/models/other/Ours",
                    "approved_benchmark_root": "/benchmarks",
                },
                "checks": {
                    "approved_model_path_matches": {"status": "failed"},
                    "approved_benchmark_root_matches": {"status": "passed"},
                },
                "safety_flags": {
                    "executed_real_model": False,
                    "executed_real_benchmark": False,
                    "submitted_remote_job": False,
                    "raw_outputs_written": False,
                    "write_config": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = phase5_module.build_phase5_approved_decision_readiness(
        decision_validation_path=decision_validation_path,
        output_dir=output_dir,
    )

    assert report["status"] == "failed"
    assert report["approval_status"] == "invalid"
    assert report["ready_for_real_smoke"] is False
    assert report["checks"]["decision_validation"]["status"] == "failed"
    assert report["safety_flags"]["write_config"] is False
    assert json.loads((output_dir / "phase5_approved_decision_readiness.json").read_text(encoding="utf-8"))["status"] == "failed"


def test_phase5_config_representation_proposal_cli_writes_reviewable_options(tmp_path: Path) -> None:
    approved_readiness_path = tmp_path / "phase5_approved_decision_readiness.json"
    output_dir = tmp_path / "config_proposal"
    approved_readiness_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "approved_model_path_readiness",
                "status": "needs_attention",
                "approval_status": "approved",
                "ready_for_real_smoke": False,
                "target": {
                    "model_id": "qwen3_vl_2b_instruct",
                    "benchmark_id": "pope",
                },
                "approved_paths": {
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "checks": {
                    "decision_validation": {"status": "passed"},
                },
                "safety_flags": {
                    "executed_real_model": False,
                    "executed_real_benchmark": False,
                    "submitted_remote_job": False,
                    "raw_outputs_written": False,
                    "write_config": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_cli(
        "phase5-config-representation-proposal",
        "--approved-readiness",
        str(approved_readiness_path),
        "--output-dir",
        str(output_dir),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads((output_dir / "phase5_config_representation_proposal.json").read_text(encoding="utf-8"))
    markdown = (output_dir / "phase5_config_representation_proposal.md").read_text(encoding="utf-8")
    assert payload["command"] == "phase5-config-representation-proposal"
    assert payload["status"] == "needs_attention"
    assert payload["ready_for_real_smoke"] is False
    assert payload["write_config"] is False
    assert report["approved_paths"]["model_path"] == "/models/variant/Ours"
    assert report["checks"]["approved_readiness"]["status"] == "passed"
    assert report["checks"]["model_configured_root_contract"]["status"] == "needs_review"
    assert report["proposed_env"]["benchmark"]["REMOTE_BENCHMARK_ROOT"] == "/benchmarks"
    explicit_option = next(
        option for option in report["representation_options"] if option["name"] == "explicit_local_path_override"
    )
    explicit_template = next(
        template for template in report["decision_record_templates"] if template["selected_option"] == "explicit_local_path_override"
    )
    assert explicit_option["requires_config_review"] is True
    assert explicit_option["proposed_models_yaml"]["local_path"] == "/models/variant/Ours"
    assert explicit_template["reviewer"] is None
    assert explicit_template["rationale"] is None
    assert explicit_template["approved_model_path"] == "/models/variant/Ours"
    assert explicit_template["approved_benchmark_root"] == "/benchmarks"
    assert explicit_template["approved_models_yaml"]["local_path"] == "/models/variant/Ours"
    assert explicit_template["approved_env"]["REMOTE_BENCHMARK_ROOT"] == "/benchmarks"
    assert report["safety_flags"]["write_config"] is False
    assert report["exports_applied"] is False
    assert "## Decision Record Templates" in markdown
    assert "- explicit_local_path_override: approved_model_path `/models/variant/Ours`" in markdown
    assert "write_config: `false`" in markdown
    assert "raw_outputs.jsonl" not in {path.name for path in output_dir.iterdir()}


def test_phase5_config_representation_proposal_rejects_unapproved_readiness(tmp_path: Path) -> None:
    approved_readiness_path = tmp_path / "phase5_approved_decision_readiness.json"
    output_dir = tmp_path / "config_proposal"
    approved_readiness_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "approved_model_path_readiness",
                "status": "failed",
                "approval_status": "invalid",
                "ready_for_real_smoke": False,
                "target": {
                    "model_id": "qwen3_vl_2b_instruct",
                    "benchmark_id": "pope",
                },
                "approved_paths": {
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "safety_flags": {
                    "executed_real_model": False,
                    "executed_real_benchmark": False,
                    "submitted_remote_job": False,
                    "raw_outputs_written": False,
                    "write_config": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = phase5_module.build_phase5_config_representation_proposal(
        approved_readiness_path=approved_readiness_path,
        output_dir=output_dir,
    )

    assert report["status"] == "failed"
    assert report["checks"]["approved_readiness"]["status"] == "failed"
    assert report["ready_for_real_smoke"] is False
    assert report["safety_flags"]["write_config"] is False
    assert json.loads((output_dir / "phase5_config_representation_proposal.json").read_text(encoding="utf-8"))["status"] == "failed"


def test_phase5_validate_config_representation_decision_cli_accepts_explicit_override(tmp_path: Path) -> None:
    proposal_path = tmp_path / "phase5_config_representation_proposal.json"
    decision_path = tmp_path / "human_config_representation_decision.json"
    output_path = tmp_path / "phase5_config_representation_decision_validation.json"
    proposal_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "config_representation_proposal",
                "status": "needs_attention",
                "approval_status": "approved",
                "ready_for_real_smoke": False,
                "write_config": False,
                "exports_applied": False,
                "target": {
                    "model_id": "qwen3_vl_2b_instruct",
                    "benchmark_id": "pope",
                },
                "approved_paths": {
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "proposed_env": {
                    "model": {},
                    "benchmark": {"REMOTE_BENCHMARK_ROOT": "/benchmarks"},
                },
                "representation_options": [
                    {
                        "name": "explicit_local_path_override",
                        "requires_config_review": True,
                        "summary": "Represent the approved exact model path directly in model config after review.",
                        "proposed_models_yaml": {"local_path": "/models/variant/Ours"},
                    },
                    {
                        "name": "materialize_under_configured_root",
                        "requires_config_review": True,
                        "summary": "Place or link the approved model under a reviewed root.",
                        "proposed_models_yaml": {"local_path": "${REMOTE_MODEL_ROOT}/Qwen3-VL-2B-Instruct"},
                    },
                ],
                "checks": {
                    "approved_readiness": {"status": "passed"},
                    "model_configured_root_contract": {"status": "needs_review"},
                },
                "safety_flags": {
                    "executed_real_model": False,
                    "executed_real_benchmark": False,
                    "submitted_remote_job": False,
                    "raw_outputs_written": False,
                    "write_config": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision_path.write_text(
        json.dumps(
            {
                "selected_option": "explicit_local_path_override",
                "reviewer": "phase5-human-review",
                "approved_model_path": "/models/variant/Ours",
                "approved_benchmark_root": "/benchmarks",
                "rationale": "Use the reviewed exact path for the next config-representation step.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_cli(
        "phase5-validate-config-representation-decision",
        "--proposal",
        str(proposal_path),
        "--decision-record",
        str(decision_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["command"] == "phase5-validate-config-representation-decision"
    assert payload["status"] == "passed"
    assert payload["config_review_status"] == "approved"
    assert payload["selected_option"] == "explicit_local_path_override"
    assert payload["ready_for_real_smoke"] is False
    assert payload["write_config"] is False
    assert payload["exports_applied"] is False
    assert report["mode"] == "config_representation_decision_validation"
    assert report["selected_option"]["name"] == "explicit_local_path_override"
    assert report["checks"]["selected_option_declared"]["status"] == "passed"
    assert report["checks"]["approved_model_path_matches"]["status"] == "passed"
    assert report["checks"]["approved_benchmark_root_matches"]["status"] == "passed"
    assert report["safety_flags"]["write_config"] is False
    assert report["ready_for_real_smoke"] is False
    assert report["write_config"] is False
    assert report["exports_applied"] is False
    assert "raw_outputs.jsonl" not in {path.name for path in tmp_path.iterdir()}


def test_phase5_validate_config_representation_decision_rejects_mismatched_model_path(tmp_path: Path) -> None:
    proposal_path = tmp_path / "phase5_config_representation_proposal.json"
    decision_path = tmp_path / "human_config_representation_decision.json"
    output_path = tmp_path / "phase5_config_representation_decision_validation.json"
    proposal_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "config_representation_proposal",
                "status": "needs_attention",
                "ready_for_real_smoke": False,
                "write_config": False,
                "exports_applied": False,
                "target": {
                    "model_id": "qwen3_vl_2b_instruct",
                    "benchmark_id": "pope",
                },
                "approved_paths": {
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "proposed_env": {
                    "model": {},
                    "benchmark": {"REMOTE_BENCHMARK_ROOT": "/benchmarks"},
                },
                "representation_options": [
                    {
                        "name": "explicit_local_path_override",
                        "requires_config_review": True,
                        "proposed_models_yaml": {"local_path": "/models/variant/Ours"},
                    }
                ],
                "safety_flags": {
                    "executed_real_model": False,
                    "executed_real_benchmark": False,
                    "submitted_remote_job": False,
                    "raw_outputs_written": False,
                    "write_config": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision_path.write_text(
        json.dumps(
            {
                "selected_option": "explicit_local_path_override",
                "reviewer": "phase5-human-review",
                "approved_model_path": "/models/other/Ours",
                "approved_benchmark_root": "/benchmarks",
                "rationale": "Mismatch should be rejected.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = phase5_module.validate_phase5_config_representation_decision(
        proposal_path=proposal_path,
        decision_record_path=decision_path,
        output=output_path,
    )

    assert report["status"] == "failed"
    assert report["config_review_status"] == "invalid"
    assert report["checks"]["approved_model_path_matches"]["status"] == "failed"
    assert report["checks"]["approved_benchmark_root_matches"]["status"] == "passed"
    assert report["safety_flags"]["write_config"] is False
    assert report["write_config"] is False
    assert report["exports_applied"] is False
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "failed"


def test_phase5_gate_audit_cli_reports_missing_review_chain(tmp_path: Path) -> None:
    output_path = tmp_path / "phase5_gate_audit.json"

    result = run_cli(
        "phase5-gate-audit",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["command"] == "phase5-gate-audit"
    assert payload["status"] == "needs_attention"
    assert payload["ready_for_real_smoke"] is False
    assert payload["next_missing_gate"] == "model_path_decision_request"
    assert report["mode"] == "gate_audit"
    assert report["target"] == {
        "model_id": "qwen3_vl_2b_instruct",
        "benchmark_id": "pope",
        "limit": 8,
        "instrumentation_mode": "none",
    }
    assert report["gate_checks"]["model_path_decision_request"]["status"] == "missing"
    assert report["gate_checks"]["model_path_decision_validation"]["status"] == "missing"
    assert report["safety_flags"]["write_config"] is False
    assert report["exports_applied"] is False
    assert "raw_outputs.jsonl" not in {path.name for path in tmp_path.iterdir()}


def test_phase5_gate_audit_cli_writes_reviewable_markdown_package(tmp_path: Path) -> None:
    output_dir = tmp_path / "gate_audit"

    result = run_cli(
        "phase5-gate-audit",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--output-dir",
        str(output_dir),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads((output_dir / "phase5_gate_audit.json").read_text(encoding="utf-8"))
    markdown = (output_dir / "phase5_gate_audit.md").read_text(encoding="utf-8")
    assert payload["command"] == "phase5-gate-audit"
    assert payload["status"] == "needs_attention"
    assert payload["next_missing_gate"] == "model_path_decision_request"
    assert report["mode"] == "gate_audit"
    assert report["ready_for_real_smoke"] is False
    assert report["write_config"] is False
    assert report["exports_applied"] is False
    packet = report["next_action_packet"]
    assert packet["gate"] == "model_path_decision_request"
    assert packet["required_inputs"] == [
        "reviewed_variant_or_exact_model_path",
        "candidate_REMOTE_BENCHMARK_ROOT",
        "decision_request_output_dir",
    ]
    assert packet["expected_artifacts"] == [
        "phase5_model_path_decision_request.json",
        "phase5_model_path_decision_request.md",
    ]
    assert any(
        "phase5-model-path-decision-request --model qwen3_vl_2b_instruct --benchmark pope"
        in command
        for command in packet["safe_command_templates"]
    )
    assert "Do not run the real model or benchmark from this gate audit." in packet["forbidden_actions"]
    assert "# Phase 5 Gate Audit" in markdown
    assert "next_missing_gate: `model_path_decision_request`" in markdown
    assert "ready_for_real_smoke: `false`" in markdown
    assert "- model_path_decision_request: `missing`" in markdown
    assert "## Next Action Packet" in markdown
    assert "- gate: `model_path_decision_request`" in markdown
    assert "phase5-model-path-decision-request --model qwen3_vl_2b_instruct --benchmark pope" in markdown
    assert "raw_outputs.jsonl" not in {path.name for path in output_dir.iterdir()}


def test_phase5_committed_model_path_decision_request_advances_gate_audit(tmp_path: Path) -> None:
    artifact_dir = REPO_ROOT / "runs/needs_attention/phase_5_model_path_decision_request"
    decision_request_path = artifact_dir / "phase5_model_path_decision_request.json"
    decision_request_markdown = artifact_dir / "phase5_model_path_decision_request.md"
    output_path = tmp_path / "phase5_gate_audit.json"

    assert decision_request_path.exists()
    assert decision_request_markdown.exists()

    result = run_cli(
        "phase5-gate-audit",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--decision-request",
        str(decision_request_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    request = json.loads(decision_request_path.read_text(encoding="utf-8"))
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "needs_attention"
    assert payload["next_missing_gate"] == "model_path_decision_validation"
    assert request["approval_status"] == "pending"
    assert request["safety_flags"]["write_config"] is False
    assert request["safety_flags"]["executed_real_model"] is False
    assert request["requested_decision"]["decision_record_templates"]
    assert report["gate_checks"]["model_path_decision_request"]["status"] == "passed"
    assert report["gate_checks"]["model_path_decision_validation"]["status"] == "missing"
    packet = report["next_action_packet"]
    assert packet["gate"] == "model_path_decision_validation"
    assert packet["required_inputs"] == [
        "phase5_model_path_decision_request.json",
        "filled_human_decision_record.json",
        "phase5_model_path_decision_validation_output",
    ]
    assert packet["expected_artifacts"] == [
        "phase5_model_path_decision_validation.json",
    ]
    assert any(
        "phase5-validate-model-path-decision --request <phase5_model_path_decision_request.json>"
        in command
        for command in packet["safe_command_templates"]
    )
    assert any("decision_record_templates" in command for command in packet["safe_command_templates"])
    assert "Do not treat unfilled template files as human approval." in packet["forbidden_actions"]
    assert report["ready_for_real_smoke"] is False
    assert report["safety_flags"]["submitted_remote_job"] is False
    assert "approval_status: `pending`" in decision_request_markdown.read_text(encoding="utf-8")
    assert "raw_outputs.jsonl" not in {path.name for path in artifact_dir.iterdir()}


def test_phase5_committed_current_gate_audit_points_to_decision_validation() -> None:
    audit_dir = REPO_ROOT / "runs/needs_attention/phase_5_gate_audit_current"
    audit_path = audit_dir / "phase5_gate_audit.json"
    audit_markdown_path = audit_dir / "phase5_gate_audit.md"
    decision_request_path = (
        REPO_ROOT
        / "runs/needs_attention/phase_5_model_path_decision_request/phase5_model_path_decision_request.json"
    )

    assert audit_path.exists()
    assert audit_markdown_path.exists()

    report = json.loads(audit_path.read_text(encoding="utf-8"))
    markdown = audit_markdown_path.read_text(encoding="utf-8")
    assert report["status"] == "needs_attention"
    assert report["next_missing_gate"] == "model_path_decision_validation"
    assert report["gate_checks"]["model_path_decision_request"]["status"] == "passed"
    assert report["gate_checks"]["model_path_decision_validation"]["status"] == "missing"
    assert report["ready_for_real_smoke"] is False
    assert report["write_config"] is False
    assert report["exports_applied"] is False
    assert report["safety_flags"]["executed_real_model"] is False
    assert report["safety_flags"]["executed_real_benchmark"] is False
    assert report["safety_flags"]["submitted_remote_job"] is False
    assert report["safety_flags"]["raw_outputs_written"] is False
    source_artifact = report["source_artifacts"]["model_path_decision_request"]
    assert source_artifact["path"] == str(
        Path("runs/needs_attention/phase_5_model_path_decision_request/phase5_model_path_decision_request.json")
    )
    assert source_artifact["sha256"] == sha256_file(decision_request_path)

    packet = report["next_action_packet"]
    assert packet["gate"] == "model_path_decision_validation"
    assert packet["required_inputs"] == [
        "phase5_model_path_decision_request.json",
        "filled_human_decision_record.json",
        "phase5_model_path_decision_validation_output",
    ]
    assert packet["expected_artifacts"] == [
        "phase5_model_path_decision_validation.json",
    ]
    assert any(
        "phase5-validate-model-path-decision --request <phase5_model_path_decision_request.json>"
        in command
        for command in packet["safe_command_templates"]
    )
    assert "Do not treat unfilled template files as human approval." in packet["forbidden_actions"]
    assert "next_missing_gate: `model_path_decision_validation`" in markdown
    assert "## Source Artifacts" in markdown
    assert "- model_path_decision_request:" in markdown
    assert source_artifact["sha256"] in markdown
    assert "- gate: `model_path_decision_validation`" in markdown
    assert "phase5-validate-model-path-decision --request <phase5_model_path_decision_request.json>" in markdown
    assert "raw_outputs.jsonl" not in {path.name for path in audit_dir.iterdir()}


def test_phase5_verify_gate_audit_accepts_current_handoff(tmp_path: Path) -> None:
    audit_path = REPO_ROOT / "runs/needs_attention/phase_5_gate_audit_current/phase5_gate_audit.json"
    output_path = tmp_path / "phase5_gate_audit_verify.json"

    result = run_cli(
        "phase5-verify-gate-audit",
        "--audit",
        str(audit_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "phase5-verify-gate-audit"
    assert payload["status"] == "passed"
    assert payload["source_artifact_count"] == 1
    assert payload["ready_for_real_smoke"] is False
    assert payload["write_config"] is False
    assert payload["exports_applied"] is False
    assert payload["executed_real_model"] is False
    assert payload["executed_real_benchmark"] is False
    assert payload["submitted_remote_job"] is False
    assert payload["raw_outputs_written"] is False

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["audit_path"] == str(audit_path)
    assert report["source_artifact_count"] == 1
    assert report["checks"]["audit_identity"]["status"] == "passed"
    assert report["checks"]["non_executing_safety"]["status"] == "passed"
    assert report["checks"]["next_action_packet"]["status"] == "passed"
    assert report["checks"]["source_artifacts"]["status"] == "passed"
    assert report["checks"]["markdown_sidecar"]["status"] == "passed"
    assert report["markdown_sidecar"]["status"] == "passed"
    assert report["markdown_sidecar"]["path"] == str(audit_path.with_suffix(".md"))
    source_check = report["source_artifacts"]["model_path_decision_request"]
    decision_request_path = (
        REPO_ROOT
        / "runs/needs_attention/phase_5_model_path_decision_request/phase5_model_path_decision_request.json"
    )
    assert source_check["status"] == "passed"
    assert source_check["path"] == str(
        Path("runs/needs_attention/phase_5_model_path_decision_request/phase5_model_path_decision_request.json")
    )
    assert source_check["expected_sha256"] == sha256_file(decision_request_path)
    assert source_check["actual_sha256"] == sha256_file(decision_request_path)


def test_phase5_verify_gate_audit_rejects_stale_markdown_sidecar(tmp_path: Path) -> None:
    audit_path = REPO_ROOT / "runs/needs_attention/phase_5_gate_audit_current/phase5_gate_audit.json"
    markdown_path = audit_path.with_suffix(".md")
    copied_audit_path = tmp_path / "phase5_gate_audit.json"
    copied_markdown_path = tmp_path / "phase5_gate_audit.md"
    output_path = tmp_path / "phase5_gate_audit_verify.json"
    _write_json(copied_audit_path, json.loads(audit_path.read_text(encoding="utf-8")))
    copied_markdown_path.write_text(
        markdown_path.read_text(encoding="utf-8").replace(
            "next_missing_gate: `model_path_decision_validation`",
            "next_missing_gate: `phase5_readiness`",
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "phase5-verify-gate-audit",
        "--audit",
        str(copied_audit_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["command"] == "phase5-verify-gate-audit"
    assert payload["status"] == "failed"
    verification = json.loads(output_path.read_text(encoding="utf-8"))
    assert verification["status"] == "failed"
    assert verification["checks"]["markdown_sidecar"]["status"] == "failed"
    assert verification["markdown_sidecar"]["status"] == "failed"
    assert verification["markdown_sidecar"]["path"] == str(copied_markdown_path)
    assert "next_missing_gate" in verification["markdown_sidecar"]["summary"]
    assert verification["checks"]["source_artifacts"]["status"] == "passed"
    assert verification["ready_for_real_smoke"] is False
    assert verification["write_config"] is False
    assert verification["exports_applied"] is False


def test_phase5_verify_gate_audit_rejects_stale_markdown_command_template(tmp_path: Path) -> None:
    audit_path = REPO_ROOT / "runs/needs_attention/phase_5_gate_audit_current/phase5_gate_audit.json"
    markdown_path = audit_path.with_suffix(".md")
    copied_audit_path = tmp_path / "phase5_gate_audit.json"
    copied_markdown_path = tmp_path / "phase5_gate_audit.md"
    output_path = tmp_path / "phase5_gate_audit_verify.json"
    _write_json(copied_audit_path, json.loads(audit_path.read_text(encoding="utf-8")))
    copied_markdown_path.write_text(
        markdown_path.read_text(encoding="utf-8").replace(
            "phase5-validate-model-path-decision",
            "phase5-readiness",
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "phase5-verify-gate-audit",
        "--audit",
        str(copied_audit_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 1, result.stdout
    verification = json.loads(output_path.read_text(encoding="utf-8"))
    assert verification["status"] == "failed"
    assert verification["checks"]["markdown_sidecar"]["status"] == "failed"
    assert verification["markdown_sidecar"]["status"] == "failed"
    assert verification["markdown_sidecar"]["path"] == str(copied_markdown_path)
    assert "safe_command_templates" in verification["markdown_sidecar"]["summary"]
    assert verification["checks"]["source_artifacts"]["status"] == "passed"
    assert verification["ready_for_real_smoke"] is False
    assert verification["write_config"] is False
    assert verification["exports_applied"] is False


def test_phase5_verify_gate_audit_rejects_stale_source_hash(tmp_path: Path) -> None:
    audit_path = REPO_ROOT / "runs/needs_attention/phase_5_gate_audit_current/phase5_gate_audit.json"
    stale_audit_path = tmp_path / "phase5_gate_audit_stale.json"
    output_path = tmp_path / "phase5_gate_audit_verify.json"
    report = json.loads(audit_path.read_text(encoding="utf-8"))
    report["source_artifacts"]["model_path_decision_request"]["sha256"] = "0" * 64
    _write_json(stale_audit_path, report)

    result = run_cli(
        "phase5-verify-gate-audit",
        "--audit",
        str(stale_audit_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["command"] == "phase5-verify-gate-audit"
    assert payload["status"] == "failed"
    assert payload["source_artifact_count"] == 1
    assert payload["ready_for_real_smoke"] is False
    assert payload["write_config"] is False
    assert payload["exports_applied"] is False
    assert payload["executed_real_model"] is False
    assert payload["executed_real_benchmark"] is False
    assert payload["submitted_remote_job"] is False
    assert payload["raw_outputs_written"] is False

    verification = json.loads(output_path.read_text(encoding="utf-8"))
    assert verification["status"] == "failed"
    assert verification["checks"]["source_artifacts"]["status"] == "failed"
    source_check = verification["source_artifacts"]["model_path_decision_request"]
    decision_request_path = (
        REPO_ROOT
        / "runs/needs_attention/phase_5_model_path_decision_request/phase5_model_path_decision_request.json"
    )
    assert source_check["status"] == "failed"
    assert source_check["expected_sha256"] == "0" * 64
    assert source_check["actual_sha256"] == sha256_file(decision_request_path)
    assert "sha256 mismatch" in source_check["summary"]


def test_phase5_committed_decision_record_templates_are_unfilled_handoff_files() -> None:
    artifact_dir = REPO_ROOT / "runs/needs_attention/phase_5_model_path_decision_request"
    decision_request_path = artifact_dir / "phase5_model_path_decision_request.json"
    template_dir = artifact_dir / "decision_record_templates"
    request = json.loads(decision_request_path.read_text(encoding="utf-8"))
    request_templates = {
        template["decision"]: template
        for template in request["requested_decision"]["decision_record_templates"]
    }

    expected_paths = {
        "approve_variant_path": template_dir / "approve_variant_path.template.json",
        "reject_variant_path": template_dir / "reject_variant_path.template.json",
        "provide_base_model_root": template_dir / "provide_base_model_root.template.json",
    }
    assert set(request_templates) == set(expected_paths)
    for decision, path in expected_paths.items():
        assert path.exists()
        template = json.loads(path.read_text(encoding="utf-8"))
        assert template == request_templates[decision]
        assert template["approver"] is None
        assert template["rationale"] is None

    approve_template = json.loads(expected_paths["approve_variant_path"].read_text(encoding="utf-8"))
    assert approve_template["approved_model_path"] == request["target"]["model_path"]
    assert approve_template["approved_benchmark_root"] == request["target"]["benchmark_root"]


def test_phase5_unfilled_approval_template_does_not_validate(tmp_path: Path) -> None:
    artifact_dir = REPO_ROOT / "runs/needs_attention/phase_5_model_path_decision_request"
    decision_request_path = artifact_dir / "phase5_model_path_decision_request.json"
    approve_template_path = artifact_dir / "decision_record_templates/approve_variant_path.template.json"
    output_path = tmp_path / "phase5_model_path_decision_validation.json"

    report = phase5_module.validate_phase5_model_path_decision(
        request_path=decision_request_path,
        decision_record_path=approve_template_path,
        output=output_path,
    )

    assert report["status"] == "failed"
    assert report["approval_status"] == "invalid"
    assert report["checks"]["approver_present"]["status"] == "failed"
    assert report["checks"]["rationale_present"]["status"] == "failed"
    assert report["checks"]["approved_model_path_matches"]["status"] == "passed"
    assert report["checks"]["approved_benchmark_root_matches"]["status"] == "passed"
    assert report["safety_flags"]["write_config"] is False
    assert report["safety_flags"]["executed_real_model"] is False
    assert json.loads(output_path.read_text(encoding="utf-8"))["approval_status"] == "invalid"


def test_phase5_unfilled_base_root_template_does_not_validate(tmp_path: Path) -> None:
    artifact_dir = REPO_ROOT / "runs/needs_attention/phase_5_model_path_decision_request"
    decision_request_path = artifact_dir / "phase5_model_path_decision_request.json"
    base_root_template_path = artifact_dir / "decision_record_templates/provide_base_model_root.template.json"
    output_path = tmp_path / "phase5_model_path_decision_validation.json"

    report = phase5_module.validate_phase5_model_path_decision(
        request_path=decision_request_path,
        decision_record_path=base_root_template_path,
        output=output_path,
    )

    assert report["status"] == "failed"
    assert report["approval_status"] == "invalid"
    assert report["checks"]["approver_present"]["status"] == "failed"
    assert report["checks"]["rationale_present"]["status"] == "failed"
    assert report["checks"]["provided_model_root_present"]["status"] == "failed"
    assert report["safety_flags"]["write_config"] is False
    assert report["safety_flags"]["submitted_remote_job"] is False


def test_phase5_gate_audit_advances_to_approved_readiness_packet(tmp_path: Path) -> None:
    request_path = tmp_path / "phase5_model_path_decision_request.json"
    decision_validation_path = tmp_path / "phase5_model_path_decision_validation.json"
    output_path = tmp_path / "phase5_gate_audit.json"
    target = {"model_id": "qwen3_vl_2b_instruct", "benchmark_id": "pope"}
    safety_flags = {
        "executed_real_model": False,
        "executed_real_benchmark": False,
        "submitted_remote_job": False,
        "raw_outputs_written": False,
        "write_config": False,
    }
    request_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "model_path_decision_request",
                "status": "needs_attention",
                "approval_status": "pending",
                "target": {
                    **target,
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision_validation_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "model_path_decision_validation",
                "status": "passed",
                "approval_status": "approved",
                "target": {
                    **target,
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "decision": {
                    "decision": "approve_variant_path",
                    "approved_model_path": "/models/variant/Ours",
                    "approved_benchmark_root": "/benchmarks",
                },
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_cli(
        "phase5-gate-audit",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--decision-request",
        str(request_path),
        "--decision-validation",
        str(decision_validation_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "needs_attention"
    assert payload["next_missing_gate"] == "approved_decision_readiness"
    assert report["gate_checks"]["model_path_decision_request"]["status"] == "passed"
    assert report["gate_checks"]["model_path_decision_validation"]["status"] == "passed"
    assert report["gate_checks"]["approved_decision_readiness"]["status"] == "missing"
    packet = report["next_action_packet"]
    assert packet["gate"] == "approved_decision_readiness"
    assert packet["required_inputs"] == [
        "phase5_model_path_decision_validation.json",
        "approved_decision_readiness_output_dir",
    ]
    assert packet["expected_artifacts"] == [
        "phase5_approved_decision_readiness.json",
        "phase5_approved_decision_readiness.md",
    ]
    assert any(
        "phase5-approved-decision-readiness --decision-validation <phase5_model_path_decision_validation.json>"
        in command
        for command in packet["safe_command_templates"]
    )
    assert "Do not treat model-path approval as permission to run the real smoke." in packet["forbidden_actions"]
    assert report["ready_for_real_smoke"] is False
    assert report["safety_flags"]["submitted_remote_job"] is False


def test_phase5_gate_audit_advances_to_config_proposal_packet(tmp_path: Path) -> None:
    request_path = tmp_path / "phase5_model_path_decision_request.json"
    decision_validation_path = tmp_path / "phase5_model_path_decision_validation.json"
    approved_readiness_path = tmp_path / "phase5_approved_decision_readiness.json"
    output_path = tmp_path / "phase5_gate_audit.json"
    target = {"model_id": "qwen3_vl_2b_instruct", "benchmark_id": "pope"}
    approved_paths = {
        "model_path": "/models/variant/Ours",
        "benchmark_root": "/benchmarks",
    }
    safety_flags = {
        "executed_real_model": False,
        "executed_real_benchmark": False,
        "submitted_remote_job": False,
        "raw_outputs_written": False,
        "write_config": False,
    }
    request_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "model_path_decision_request",
                "status": "needs_attention",
                "approval_status": "pending",
                "target": {
                    **target,
                    **approved_paths,
                },
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision_validation_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "model_path_decision_validation",
                "status": "passed",
                "approval_status": "approved",
                "target": {
                    **target,
                    **approved_paths,
                },
                "decision": {
                    "decision": "approve_variant_path",
                    "approved_model_path": approved_paths["model_path"],
                    "approved_benchmark_root": approved_paths["benchmark_root"],
                },
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    approved_readiness_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "approved_model_path_readiness",
                "status": "needs_attention",
                "approval_status": "approved",
                "ready_for_real_smoke": False,
                "target": target,
                "approved_paths": approved_paths,
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_cli(
        "phase5-gate-audit",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--decision-request",
        str(request_path),
        "--decision-validation",
        str(decision_validation_path),
        "--approved-readiness",
        str(approved_readiness_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "needs_attention"
    assert payload["next_missing_gate"] == "config_representation_proposal"
    assert report["gate_checks"]["model_path_decision_request"]["status"] == "passed"
    assert report["gate_checks"]["model_path_decision_validation"]["status"] == "passed"
    assert report["gate_checks"]["approved_decision_readiness"]["status"] == "passed"
    assert report["gate_checks"]["config_representation_proposal"]["status"] == "missing"
    packet = report["next_action_packet"]
    assert packet["gate"] == "config_representation_proposal"
    assert packet["required_inputs"] == [
        "phase5_approved_decision_readiness.json",
        "config_representation_proposal_output_dir",
    ]
    assert packet["expected_artifacts"] == [
        "phase5_config_representation_proposal.json",
        "phase5_config_representation_proposal.md",
    ]
    assert any(
        "phase5-config-representation-proposal --approved-readiness <phase5_approved_decision_readiness.json>"
        in command
        for command in packet["safe_command_templates"]
    )
    assert "Do not apply approved paths to project_config or environment variables from this gate audit." in packet[
        "forbidden_actions"
    ]
    assert report["ready_for_real_smoke"] is False
    assert report["write_config"] is False
    assert report["exports_applied"] is False


def test_phase5_gate_audit_advances_to_config_decision_packet(tmp_path: Path) -> None:
    gate_paths = _write_passed_phase5_gate_chain(tmp_path)
    output_path = tmp_path / "phase5_gate_audit.json"

    result = run_cli(
        "phase5-gate-audit",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--decision-request",
        str(gate_paths["decision_request"]),
        "--decision-validation",
        str(gate_paths["decision_validation"]),
        "--approved-readiness",
        str(gate_paths["approved_readiness"]),
        "--config-proposal",
        str(gate_paths["config_proposal"]),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "needs_attention"
    assert payload["next_missing_gate"] == "config_representation_decision"
    assert report["gate_checks"]["config_representation_proposal"]["status"] == "passed"
    assert report["gate_checks"]["config_representation_decision"]["status"] == "missing"
    packet = report["next_action_packet"]
    assert packet["gate"] == "config_representation_decision"
    assert packet["required_inputs"] == [
        "phase5_config_representation_proposal.json",
        "filled_config_representation_decision_record.json",
        "phase5_config_representation_decision_validation_output",
    ]
    assert packet["expected_artifacts"] == [
        "phase5_config_representation_decision_validation.json",
    ]
    assert any(
        "phase5-validate-config-representation-decision --proposal <phase5_config_representation_proposal.json>"
        in command
        for command in packet["safe_command_templates"]
    )
    assert any("decision_record_templates" in command for command in packet["safe_command_templates"])
    assert "Do not apply approved paths to project_config or environment variables from this gate audit." in packet[
        "forbidden_actions"
    ]
    assert report["write_config"] is False
    assert report["exports_applied"] is False


def test_phase5_gate_audit_advances_to_readiness_packet(tmp_path: Path) -> None:
    gate_paths = _write_passed_phase5_gate_chain(tmp_path)
    output_path = tmp_path / "phase5_gate_audit.json"

    result = run_cli(
        "phase5-gate-audit",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--decision-request",
        str(gate_paths["decision_request"]),
        "--decision-validation",
        str(gate_paths["decision_validation"]),
        "--approved-readiness",
        str(gate_paths["approved_readiness"]),
        "--config-proposal",
        str(gate_paths["config_proposal"]),
        "--config-decision-validation",
        str(gate_paths["config_decision_validation"]),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "needs_attention"
    assert payload["next_missing_gate"] == "phase5_readiness"
    assert report["gate_checks"]["config_representation_decision"]["status"] == "passed"
    assert report["gate_checks"]["phase5_readiness"]["status"] == "missing"
    packet = report["next_action_packet"]
    assert packet["gate"] == "phase5_readiness"
    assert packet["required_inputs"] == [
        "reviewed_config_or_env_representation",
        "phase5_readiness_output_dir",
    ]
    assert packet["expected_artifacts"] == [
        "phase5_readiness.json",
        "phase5_readiness.md",
    ]
    assert any(
        "phase5-readiness --model qwen3_vl_2b_instruct --benchmark pope --limit 8 --instrumentation none"
        in command
        for command in packet["safe_command_templates"]
    )
    assert "Do not submit remote jobs or write raw_outputs.jsonl from this gate audit." in packet[
        "forbidden_actions"
    ]
    assert report["ready_for_real_smoke"] is False


def test_phase5_gate_audit_advances_to_real_smoke_result_packet(tmp_path: Path) -> None:
    gate_paths = _write_passed_phase5_gate_chain(tmp_path)
    readiness_path = tmp_path / "phase5_readiness.json"
    output_path = tmp_path / "phase5_gate_audit.json"
    safety_flags = {
        "executed_real_model": False,
        "executed_real_benchmark": False,
        "submitted_remote_job": False,
        "raw_outputs_written": False,
        "write_config": False,
    }
    readiness_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "status": "passed",
                "target": {
                    "model_id": "qwen3_vl_2b_instruct",
                    "benchmark_id": "pope",
                    "limit": 8,
                    "instrumentation_mode": "none",
                },
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_cli(
        "phase5-gate-audit",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--decision-request",
        str(gate_paths["decision_request"]),
        "--decision-validation",
        str(gate_paths["decision_validation"]),
        "--approved-readiness",
        str(gate_paths["approved_readiness"]),
        "--config-proposal",
        str(gate_paths["config_proposal"]),
        "--config-decision-validation",
        str(gate_paths["config_decision_validation"]),
        "--readiness",
        str(readiness_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "needs_attention"
    assert payload["next_missing_gate"] == "real_smoke_result"
    assert report["gate_checks"]["phase5_readiness"]["status"] == "passed"
    assert report["gate_checks"]["real_smoke_result"]["status"] == "missing"
    packet = report["next_action_packet"]
    assert packet["gate"] == "real_smoke_result"
    assert packet["required_inputs"] == [
        "controlled_worker_run_id",
        "runs_root",
        "validated_run_artifact_bundle",
    ]
    assert packet["expected_artifacts"] == [
        "run_manifest.json",
        "artifact_manifest.json",
        "raw_outputs.jsonl_or_failure_diagnostics",
    ]
    assert any("validate-run --run-id <controlled_worker_run_id>" in command for command in packet["safe_command_templates"])
    assert any("--smoke-run-id <controlled_worker_run_id>" in command for command in packet["safe_command_templates"])
    assert "Do not submit remote jobs or write raw_outputs.jsonl from this gate audit." in packet[
        "forbidden_actions"
    ]
    assert report["ready_for_real_smoke"] is False


def test_phase5_gate_audit_accepts_review_chain_but_stops_at_readiness(tmp_path: Path) -> None:
    request_path = tmp_path / "phase5_model_path_decision_request.json"
    decision_validation_path = tmp_path / "phase5_model_path_decision_validation.json"
    approved_readiness_path = tmp_path / "phase5_approved_decision_readiness.json"
    config_proposal_path = tmp_path / "phase5_config_representation_proposal.json"
    config_decision_path = tmp_path / "phase5_config_representation_decision_validation.json"
    readiness_path = tmp_path / "phase5_readiness.json"
    output_path = tmp_path / "phase5_gate_audit.json"
    target = {"model_id": "qwen3_vl_2b_instruct", "benchmark_id": "pope"}
    safety_flags = {
        "executed_real_model": False,
        "executed_real_benchmark": False,
        "submitted_remote_job": False,
        "raw_outputs_written": False,
        "write_config": False,
    }
    request_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "model_path_decision_request",
                "status": "needs_attention",
                "approval_status": "pending",
                "target": {
                    **target,
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision_validation_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "model_path_decision_validation",
                "status": "passed",
                "approval_status": "approved",
                "target": {
                    **target,
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "decision": {
                    "decision": "approve_variant_path",
                    "approved_model_path": "/models/variant/Ours",
                    "approved_benchmark_root": "/benchmarks",
                },
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    approved_readiness_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "approved_model_path_readiness",
                "status": "needs_attention",
                "approval_status": "approved",
                "ready_for_real_smoke": False,
                "target": target,
                "approved_paths": {
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config_proposal_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "config_representation_proposal",
                "status": "needs_attention",
                "ready_for_real_smoke": False,
                "write_config": False,
                "exports_applied": False,
                "target": target,
                "approved_paths": {
                    "model_path": "/models/variant/Ours",
                    "benchmark_root": "/benchmarks",
                },
                "representation_options": [
                    {
                        "name": "explicit_local_path_override",
                        "proposed_models_yaml": {"local_path": "/models/variant/Ours"},
                    }
                ],
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config_decision_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "mode": "config_representation_decision_validation",
                "status": "passed",
                "config_review_status": "approved",
                "ready_for_real_smoke": False,
                "write_config": False,
                "exports_applied": False,
                "target": target,
                "selected_option": {"name": "explicit_local_path_override"},
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    readiness_path.write_text(
        json.dumps(
            {
                "phase": "Phase 5",
                "status": "needs_attention",
                "target": {
                    **target,
                    "limit": 8,
                    "instrumentation_mode": "none",
                },
                "execution_authorization": {
                    "status": "needs_attention",
                    "gate_failures": [{"name": "runner_mode"}],
                },
                "safety_flags": safety_flags,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_cli(
        "phase5-gate-audit",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--decision-request",
        str(request_path),
        "--decision-validation",
        str(decision_validation_path),
        "--approved-readiness",
        str(approved_readiness_path),
        "--config-proposal",
        str(config_proposal_path),
        "--config-decision-validation",
        str(config_decision_path),
        "--readiness",
        str(readiness_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "needs_attention"
    assert payload["next_missing_gate"] == "phase5_readiness"
    assert payload["ready_for_real_smoke"] is False
    assert report["gate_checks"]["model_path_decision_request"]["status"] == "passed"
    assert report["gate_checks"]["model_path_decision_validation"]["status"] == "passed"
    assert report["gate_checks"]["approved_decision_readiness"]["status"] == "passed"
    assert report["gate_checks"]["config_representation_proposal"]["status"] == "passed"
    assert report["gate_checks"]["config_representation_decision"]["status"] == "passed"
    assert report["gate_checks"]["phase5_readiness"]["status"] == "needs_attention"
    assert report["do_not_continue_reason"] == "Phase 5 readiness has not passed."
    assert report["safety_flags"]["submitted_remote_job"] is False
    assert report["exports_applied"] is False


def test_phase5_gate_audit_accepts_reviewed_real_execution_failure_bundle(tmp_path: Path) -> None:
    gate_paths = _write_passed_phase5_gate_chain(tmp_path)
    runs_root = tmp_path / "runs"
    _write_landmark_failure_run(
        runs_root,
        "qwen_real_execution_failure",
        failure_type="landmark_worker_execution_failed",
    )
    output_path = tmp_path / "phase5_gate_audit.json"

    result = run_cli(
        "phase5-gate-audit",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--decision-request",
        str(gate_paths["decision_request"]),
        "--decision-validation",
        str(gate_paths["decision_validation"]),
        "--approved-readiness",
        str(gate_paths["approved_readiness"]),
        "--config-proposal",
        str(gate_paths["config_proposal"]),
        "--config-decision-validation",
        str(gate_paths["config_decision_validation"]),
        "--readiness",
        str(gate_paths["readiness"]),
        "--smoke-run-id",
        "qwen_real_execution_failure",
        "--runs-root",
        str(runs_root),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "needs_attention"
    assert payload["next_missing_gate"] == "none"
    assert payload["phase5_terminal_outcome"] == "reviewed_real_execution_failure"
    assert report["gate_checks"]["real_smoke_result"]["status"] == "passed"
    assert report["gate_checks"]["real_smoke_result"]["outcome"] == "reviewed_real_execution_failure"
    assert report["gate_checks"]["real_smoke_result"]["run_validation"]["status"] == "passed"
    assert report["do_not_continue_reason"] == (
        "Phase 5 has a reviewed real-execution failure bundle; the real smoke did not succeed."
    )
    assert not (runs_root / "qwen_real_execution_failure" / "raw_outputs.jsonl").exists()


def test_phase5_gate_audit_does_not_accept_validation_gate_failure_as_real_execution(tmp_path: Path) -> None:
    gate_paths = _write_passed_phase5_gate_chain(tmp_path)
    runs_root = tmp_path / "runs"
    _write_landmark_failure_run(
        runs_root,
        "qwen_validation_gate_failure",
        failure_type="landmark_worker_validation_gate_not_ready",
    )
    output_path = tmp_path / "phase5_gate_audit.json"

    result = run_cli(
        "phase5-gate-audit",
        "--model",
        "qwen3_vl_2b_instruct",
        "--benchmark",
        "pope",
        "--limit",
        "8",
        "--instrumentation",
        "none",
        "--decision-request",
        str(gate_paths["decision_request"]),
        "--decision-validation",
        str(gate_paths["decision_validation"]),
        "--approved-readiness",
        str(gate_paths["approved_readiness"]),
        "--config-proposal",
        str(gate_paths["config_proposal"]),
        "--config-decision-validation",
        str(gate_paths["config_decision_validation"]),
        "--readiness",
        str(gate_paths["readiness"]),
        "--smoke-run-id",
        "qwen_validation_gate_failure",
        "--runs-root",
        str(runs_root),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "needs_attention"
    assert payload["next_missing_gate"] == "real_smoke_result"
    assert payload["phase5_terminal_outcome"] == "none"
    assert report["gate_checks"]["real_smoke_result"]["status"] == "needs_attention"
    assert report["gate_checks"]["real_smoke_result"]["outcome"] == "pre_execution_gate_failure"
    assert "not a reviewed real-execution failure" in report["gate_checks"]["real_smoke_result"]["summary"]


def test_phase5_discover_model_candidates_finds_configured_root_candidate(tmp_path: Path) -> None:
    model_root = tmp_path / "candidate_models"
    model_path = model_root / "Qwen3-VL-2B-Instruct"
    model_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}\n", encoding="utf-8")
    (model_path / "model-00001-of-00002.safetensors").write_text("weight placeholder\n", encoding="utf-8")
    output_path = tmp_path / "model_candidates.json"
    env = os.environ.copy()
    env.pop("REMOTE_MODEL_ROOT", None)

    result = run_cli(
        "phase5-discover-model-candidates",
        "qwen3_vl_2b_instruct",
        "--search-root",
        str(tmp_path),
        "--output",
        str(output_path),
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["command"] == "phase5-discover-model-candidates"
    assert payload["status"] == "passed"
    assert written["status"] == "passed"
    assert written["write_config"] is False
    assert written["load_attempted"] is False
    candidate = written["candidates"][0]
    assert candidate["candidate_type"] == "configured_root"
    assert candidate["status"] == "passed"
    assert candidate["path"] == str(model_path)
    assert candidate["candidate_env"]["REMOTE_MODEL_ROOT"] == str(model_root)
    assert candidate["usable_with_current_config"] is True
    assert candidate["has_config"] is True
    assert candidate["has_weights"] is True


def test_phase5_discover_model_candidates_reports_incomplete_hf_cache(tmp_path: Path) -> None:
    hf_cache_base = tmp_path / "huggingface" / "hub" / "models--Qwen--Qwen3-VL-2B-Instruct"
    (hf_cache_base / "refs").mkdir(parents=True)
    (hf_cache_base / "refs" / "main").write_text("abc123\n", encoding="utf-8")
    output_path = tmp_path / "model_candidates.json"
    env = os.environ.copy()
    env.pop("REMOTE_MODEL_ROOT", None)

    result = run_cli(
        "phase5-discover-model-candidates",
        "qwen3_vl_2b_instruct",
        "--search-root",
        str(tmp_path),
        "--output",
        str(output_path),
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "needs_setup"
    assert written["status"] == "needs_setup"
    assert written["write_config"] is False
    assert written["load_attempted"] is False
    assert len(written["candidates"]) == 1
    candidate = written["candidates"][0]
    assert candidate["candidate_type"] == "hf_cache_base"
    assert candidate["status"] == "needs_setup"
    assert candidate["path"] == str(hf_cache_base)
    assert candidate["usable_with_current_config"] is False
    assert "missing snapshots" in candidate["reason"]


def test_phase5_discover_model_candidates_does_not_descend_into_output_dirs(tmp_path: Path) -> None:
    output_dir = tmp_path / "20260604_qwen3vl2b_smoke"
    output_dir.mkdir()
    (output_dir / "run_manifest.json").write_text("{}\n", encoding="utf-8")
    for index in range(20):
        (output_dir / f"artifact_shard_{index:02d}").mkdir()
    output_path = tmp_path / "model_candidates.json"

    result = run_cli(
        "phase5-discover-model-candidates",
        "qwen3_vl_2b_instruct",
        "--search-root",
        str(tmp_path),
        "--output",
        str(output_path),
        "--max-entries",
        "5",
    )

    assert result.returncode == 0, result.stderr
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["status"] == "needs_setup"
    assert written["searched_roots"][0]["truncated"] is False
    assert len(written["candidates"]) == 1
    candidate = written["candidates"][0]
    assert candidate["candidate_type"] == "run_output_dir"
    assert candidate["path"] == str(output_dir)


def test_phase5_discover_model_candidates_reports_model_like_variants(tmp_path: Path) -> None:
    variant_path = tmp_path / "output-model" / "Qwen3-VL-2B-3epoch" / "Ours"
    variant_path.mkdir(parents=True)
    (variant_path / "config.json").write_text("{}\n", encoding="utf-8")
    (variant_path / "model.safetensors").write_text("weight placeholder\n", encoding="utf-8")
    output_path = tmp_path / "model_candidates.json"

    result = run_cli(
        "phase5-discover-model-candidates",
        "qwen3_vl_2b_instruct",
        "--search-root",
        str(tmp_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["status"] == "needs_setup"
    assert len(written["candidates"]) == 1
    candidate = written["candidates"][0]
    assert candidate["candidate_type"] == "model_like_variant"
    assert candidate["status"] == "needs_review"
    assert candidate["path"] == str(variant_path)
    assert candidate["usable_with_current_config"] is False
    assert candidate["requires_config_path_override"] is True
    assert candidate["has_config"] is True
    assert candidate["has_weights"] is True


def test_export_schemas_cli_writes_json_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "schemas"
    result = run_cli("export-schemas", "--output", str(output_dir))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "export-schemas"
    assert "Idea" in payload["schemas"]
    assert (output_dir / "Idea.json").exists()
    assert json.loads((output_dir / "ValidationReport.json").read_text(encoding="utf-8"))["type"] == "object"
