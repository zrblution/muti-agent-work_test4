import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stable_core.cli", *args],
        cwd=REPO_ROOT,
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


def test_list_model_benchmark_and_agent_clis_read_config() -> None:
    models = json.loads(run_cli("list-models").stdout)
    benchmarks = json.loads(run_cli("list-benchmarks").stdout)
    agents = json.loads(run_cli("list-agents").stdout)

    assert models["models"] == ["fake_model", "internvl3_5_4b", "qwen3_vl_2b_instruct"]
    assert benchmarks["benchmarks"] == ["amber", "chair", "fake_benchmark", "mme", "pope"]
    assert agents["providers"] == ["deepseek_v4_pro", "opus4_8_proxy"]


def test_export_schemas_cli_writes_json_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "schemas"
    result = run_cli("export-schemas", "--output", str(output_dir))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "export-schemas"
    assert "Idea" in payload["schemas"]
    assert (output_dir / "Idea.json").exists()
    assert json.loads((output_dir / "ValidationReport.json").read_text(encoding="utf-8"))["type"] == "object"
