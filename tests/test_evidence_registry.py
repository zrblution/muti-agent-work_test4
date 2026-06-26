import json
import subprocess
import sys
from pathlib import Path

import pytest

from stable_core.evidence.registry import EvidenceRecord, EvidenceRegistry


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stable_core.cli", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_evidence_registry_add_list_and_reject_duplicate(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "registry.jsonl")
    record = EvidenceRecord(
        evidence_id="code:test:abc:path.py:L1-L2",
        source_type="baseline_code",
        source_name="test_baseline",
        locator={"path": "path.py", "url": None, "commit": "abc", "line_start": 1, "line_end": 2},
        claim_supported="Test claim",
        claim_scope="implementation_pattern",
        confidence=0.8,
        created_by="codex",
    )

    registry.add(record)

    assert registry.list_records()[0].evidence_id == record.evidence_id
    with pytest.raises(ValueError, match="Duplicate evidence_id"):
        registry.add(record)


def test_evidence_record_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        EvidenceRecord(
            evidence_id="bad",
            source_type="baseline_code",
            source_name="x",
            locator={},
            claim_supported="bad",
            claim_scope="implementation_pattern",
            confidence=1.5,
            created_by="codex",
        )


def test_evidence_cli_init_add_list(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.jsonl"

    init_result = run_cli("evidence", "init", "--registry", str(registry_path))
    assert init_result.returncode == 0, init_result.stderr
    assert registry_path.exists()

    add_result = run_cli(
        "evidence",
        "add",
        "--registry",
        str(registry_path),
        "--evidence-id",
        "codex:test:commit:file.py",
        "--source-type",
        "codex_patch",
        "--source-name",
        "phase2_test",
        "--claim-supported",
        "Evidence CLI records a patch claim.",
        "--claim-scope",
        "implementation_pattern",
        "--confidence",
        "0.7",
        "--created-by",
        "codex",
    )
    assert add_result.returncode == 0, add_result.stderr

    list_result = run_cli("evidence", "list", "--registry", str(registry_path))
    assert list_result.returncode == 0, list_result.stderr
    payload = json.loads(list_result.stdout)
    assert payload["count"] == 1
    assert payload["records"][0]["evidence_id"] == "codex:test:commit:file.py"
