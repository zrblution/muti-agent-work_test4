import csv
import json
import subprocess
import sys
from pathlib import Path

from research_tools.baseline_indexer import parse_manifest, write_baseline_reports


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "docs" / "research" / "source_snapshots" / "baseline_MANIFEST.tsv"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stable_core.cli", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_parse_manifest_reads_baseline_rows() -> None:
    rows = parse_manifest(MANIFEST)

    assert len(rows) >= 10
    assert rows[0].baseline_id == "01_POPE"
    assert rows[0].has_code is True
    assert rows[0].repo_url.startswith("https://github.com/")


def test_write_baseline_reports_creates_matrix_and_evidence(tmp_path: Path) -> None:
    output_dir = tmp_path / "research"
    registry_path = tmp_path / "registry.jsonl"

    summary = write_baseline_reports(MANIFEST, output_dir, registry_path)

    assert summary["status"] == "passed"
    matrix_path = output_dir / "baseline_code_structure_matrix.tsv"
    assert matrix_path.exists()
    with matrix_path.open("r", encoding="utf-8", newline="") as handle:
        matrix_rows = list(csv.DictReader(handle, delimiter="	"))
    assert len(matrix_rows) == summary["baseline_count"]
    assert matrix_rows[0]["baseline_id"] == "01_POPE"
    assert registry_path.exists()
    evidence_lines = [json.loads(line) for line in registry_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(evidence_lines) >= 10
    assert evidence_lines[0]["source_type"] == "baseline_code"


def test_index_baselines_cli_generates_required_research_artifacts() -> None:
    result = run_cli("index-baselines", "--manifest", str(MANIFEST))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    for rel_path in [
        "docs/research/baseline_code_structure_matrix.tsv",
        "docs/research/reusable_patterns.md",
        "docs/research/anti_patterns.md",
        "docs/research/framework_reference_report.md",
        "docs/research/recent_paper_research.needs_attention.md",
        "docs/research/paper_to_framework_inspiration.md",
        "evidence/registry.jsonl",
    ]:
        assert (REPO_ROOT / rel_path).exists(), rel_path


def test_research_status_reports_needs_attention_for_unfinished_paper_research() -> None:
    result = run_cli("research-status")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] in {"needs_attention", "passed"}
    assert payload["checks"]["recent_paper_research"]["status"] == "needs_attention"
