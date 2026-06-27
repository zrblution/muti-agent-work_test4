import json
import os
import subprocess
import sys
from pathlib import Path

from stable_core import config as config_module
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
    assert report["probe"]["status"] == "passed"
    assert report["probe"]["requires_human_approval"] is True
    assert report["safety_flags"]["write_config"] is False
    assert report["safety_flags"]["executed_real_model"] is False
    assert "approval_status: `pending`" in markdown
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
