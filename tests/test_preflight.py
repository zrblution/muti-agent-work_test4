import json
import subprocess
import sys
from pathlib import Path

from stable_core.validation.preflight import (
    PreflightConfig,
    run_preflight,
    validate_provider_config,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_env_example_has_only_placeholders() -> None:
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "DEEPSEEK_API_KEY=<set-in-env>" in env_example
    assert "OPUS_PROXY_API_KEY=<set-in-env>" in env_example
    assert "HF_TOKEN=<optional-set-in-env>" in env_example
    assert "sk-" not in env_example
    for line in env_example.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        assert not key.endswith(("API_KEY", "TOKEN")) or value.startswith("<")


def test_gitignore_blocks_env_and_large_artifacts() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    required_patterns = [
        ".env",
        "*.key",
        "*.pem",
        "*.pt",
        "*.pth",
        "*.safetensors",
        "models/",
        "runs/**/browser_trace/",
        "runs/**/large_artifacts/",
    ]
    for pattern in required_patterns:
        assert pattern in gitignore


def test_provider_config_uses_env_names_only(tmp_path: Path) -> None:
    provider_config = tmp_path / "agents.yaml"
    provider_config.write_text(
        "providers:\n"
        "  deepseek_v4_pro:\n"
        "    provider_type: openai_compatible\n"
        "    model: deepseek-v4-pro\n"
        "    api_key_env: DEEPSEEK_API_KEY\n"
        "    base_url_env: null\n",
        encoding="utf-8",
    )

    report = validate_provider_config(provider_config)

    assert report["status"] == "passed"
    assert report["providers"]["deepseek_v4_pro"]["api_key_env"] == "DEEPSEEK_API_KEY"


def test_provider_config_rejects_inline_key_values(tmp_path: Path) -> None:
    provider_config = tmp_path / "agents.yaml"
    provider_config.write_text(
        "providers:\n"
        "  unsafe:\n"
        "    provider_type: openai_compatible\n"
        "    model: unsafe-model\n"
        "    api_key: " + "sk-" + "C" * 48 + "\n",
        encoding="utf-8",
    )

    report = validate_provider_config(provider_config)

    assert report["status"] == "failed"
    assert report["findings"][0]["field"] == "api_key"


def test_preflight_reports_missing_paths_without_crashing(tmp_path: Path) -> None:
    existing_spec_root = tmp_path / "specs"
    existing_spec_root.mkdir()
    existing_local_root = tmp_path / "local_agent"
    existing_local_root.mkdir()
    output_dir = tmp_path / "preflight"
    config = PreflightConfig(
        spec_root=existing_spec_root,
        local_agent_system_root=existing_local_root,
        local_baseline_repo=tmp_path / "missing_baselines",
        server_framework_root=Path("/definitely/missing/server/framework"),
        remote_execution_root=Path("/definitely/missing/server/framework"),
        model_root=None,
        benchmark_root=None,
        artifact_root=tmp_path / "artifacts",
        provider_config=tmp_path / "missing_agents.yaml",
    )

    report = run_preflight(config=config, output_dir=output_dir, dry_run=True, scan_paths=[existing_spec_root])

    assert report["status"] == "needs_setup"
    assert report["path_check"]["spec_root"]["status"] == "verified"
    assert report["path_check"]["local_baseline_repo"]["status"] == "missing"
    assert (output_dir / "path_check.json").exists()
    assert (output_dir / "git_check.json").exists()
    assert (output_dir / "secret_scan_report.json").exists()
    assert (output_dir / "preflight_summary.md").exists()


def test_cli_preflight_dry_run_generates_required_artifacts() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "stable_core.cli", "preflight", "--dry-run"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode in {0, 2}
    summary = REPO_ROOT / "runs" / "preflight" / "preflight_summary.md"
    secret_report = REPO_ROOT / "runs" / "preflight" / "secret_scan_report.json"
    assert summary.exists()
    assert json.loads(secret_report.read_text(encoding="utf-8"))["status"] in {"passed", "failed"}


def test_cli_doctor_prints_json_status() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "stable_core.cli", "doctor"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode in {0, 2}
    payload = json.loads(result.stdout)
    assert payload["command"] == "doctor"
    assert payload["preflight_status"] in {"passed", "needs_setup", "failed"}
