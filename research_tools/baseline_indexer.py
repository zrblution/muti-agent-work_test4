from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stable_core.evidence.registry import EvidenceRecord, EvidenceRegistry

MATRIX_FIELDS = [
    "baseline_id",
    "paper_title",
    "has_code",
    "repo_url",
    "clone_commit",
    "model_loading_paths",
    "decoding_paths",
    "intervention_paths",
    "evaluation_paths",
    "analysis_paths",
    "script_paths",
    "reusable_patterns",
    "anti_patterns",
    "best_impl_base_for_new_ideas",
    "notes",
]


@dataclass
class BaselineManifestRow:
    baseline_id: str
    zotero_key: str
    read_status: str
    title: str
    repo: str
    repo_url: str | None
    clone_commit: str | None
    code_snapshot_status: str
    paper_file: str

    @property
    def has_code(self) -> bool:
        return bool(self.repo_url and self.repo != "NO_PUBLIC_CODE_REPO" and self.code_snapshot_status != "paper_only")

    @property
    def evidence_id(self) -> str:
        commit = self.clone_commit or "no_commit"
        return f"code:{self.baseline_id}:{commit}:MANIFEST.tsv"


def parse_manifest(manifest_path: str | Path) -> list[BaselineManifestRow]:
    path = Path(manifest_path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    parsed: list[BaselineManifestRow] = []
    for row in rows:
        parsed.append(
            BaselineManifestRow(
                baseline_id=row.get("folder", ""),
                zotero_key=row.get("zotero_key", ""),
                read_status=row.get("read_status", ""),
                title=row.get("title", ""),
                repo=row.get("repo", ""),
                repo_url=row.get("clone_remote_url", "") or None,
                clone_commit=row.get("clone_commit", "") or None,
                code_snapshot_status=row.get("code_snapshot_status", ""),
                paper_file=row.get("paper_file", ""),
            )
        )
    return parsed


def _pattern_for(row: BaselineManifestRow) -> str:
    name = row.baseline_id.lower()
    title = row.title.lower()
    if "deco" in name or "decoding" in title:
        return "decoding_wrapper"
    if "saliency" in name or "attention" in title:
        return "attention_hook"
    if "causal" in title or "intervention" in title:
        return "layerwise_recorder"
    return "unknown"


def _matrix_row(row: BaselineManifestRow) -> dict[str, str]:
    if row.has_code:
        notes = "Manifest-only index; full code structure survey is not completed in Phase 2."
    else:
        notes = "No public code snapshot in manifest; paper-only entry needs manual review."
    pattern = _pattern_for(row)
    return {
        "baseline_id": row.baseline_id,
        "paper_title": row.title,
        "has_code": str(row.has_code).lower(),
        "repo_url": row.repo_url or "",
        "clone_commit": row.clone_commit or "",
        "model_loading_paths": "needs_code_survey" if row.has_code else "",
        "decoding_paths": "needs_code_survey" if row.has_code else "",
        "intervention_paths": "needs_code_survey" if row.has_code else "",
        "evaluation_paths": "needs_code_survey" if row.has_code else "",
        "analysis_paths": "needs_code_survey" if row.has_code else "",
        "script_paths": "needs_code_survey" if row.has_code else "",
        "reusable_patterns": pattern,
        "anti_patterns": "metric_generation_coupling_risk",
        "best_impl_base_for_new_ideas": "unknown_until_code_survey",
        "notes": notes,
    }


def _evidence_for(row: BaselineManifestRow) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=row.evidence_id,
        source_type="baseline_code",
        source_name=row.baseline_id,
        locator={
            "path": "docs/research/source_snapshots/baseline_MANIFEST.tsv",
            "url": row.repo_url,
            "commit": row.clone_commit,
            "line_start": None,
            "line_end": None,
            "run_id": None,
            "artifact_id": None,
        },
        claim_supported=f"Manifest records baseline {row.baseline_id}: {row.title}; code_available={row.has_code}.",
        claim_scope="implementation_pattern",
        confidence=0.6 if row.has_code else 0.45,
        created_by="baseline_indexer",
    )


def _write_matrix(rows: list[BaselineManifestRow], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "baseline_code_structure_matrix.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATRIX_FIELDS, delimiter="\t", lineterminator=chr(10))
        writer.writeheader()
        for row in rows:
            writer.writerow(_matrix_row(row))


def _write_research_docs(rows: list[BaselineManifestRow], output_dir: Path, manifest_sha256: str) -> None:
    code_count = sum(1 for row in rows if row.has_code)
    output_dir.mkdir(parents=True, exist_ok=True)
    reusable = f"""# Reusable Patterns (Manifest-Level)

This file is generated from MANIFEST.tsv only. It identifies candidate pattern classes, not audited implementation details.

- Baselines indexed: {len(rows)}
- Baselines with code snapshots: {code_count}
- Candidate patterns: decoding_wrapper, attention_hook, layerwise_recorder, unknown
- Next required step: inspect code paths before accepting any pattern as reusable.
"""
    anti = """# Anti-Patterns (Preliminary)

Phase 2 does not claim confirmed anti-patterns from code inspection.

## Anti-pattern: metric-generation coupling risk

- anti_pattern_id: anti_metric_generation_coupling_risk_001
- evidence_id: manifest-level entries in `evidence/registry.jsonl`
- why_bad: benchmark metric logic must remain inside BenchmarkAdapter and must not be mixed into model generation or idea plugins.
- status: risk_to_check_in_code_survey
"""
    framework = """# Framework Reference Report

Status: needs_attention. External framework research has not been completed in this phase.

Tracked targets: lmms-eval, VLMEvalKit, lm-evaluation-harness, OpenCompass, HELM-like harnesses.

No external framework findings are claimed here.
"""
    recent = """# Recent Paper Research Needs Attention

Status: needs_attention. No 2024-2026 recent-paper search was executed in Phase 2.

This file exists to prevent downstream agents from treating paper research as complete.
"""
    inspiration = f"""# Paper to Framework Inspiration

Status: preliminary. Derived only from the baseline manifest, not from full paper or code reading.

Source manifest SHA-256: `{manifest_sha256}`
"""
    (output_dir / "reusable_patterns.md").write_text(reusable, encoding="utf-8")
    (output_dir / "anti_patterns.md").write_text(anti, encoding="utf-8")
    (output_dir / "framework_reference_report.md").write_text(framework, encoding="utf-8")
    (output_dir / "recent_paper_research.needs_attention.md").write_text(recent, encoding="utf-8")
    (output_dir / "paper_to_framework_inspiration.md").write_text(inspiration, encoding="utf-8")


def write_baseline_reports(manifest_path: str | Path, output_dir: str | Path, registry_path: str | Path) -> dict[str, Any]:
    manifest = Path(manifest_path)
    output = Path(output_dir)
    registry = EvidenceRegistry(registry_path)
    registry.init()
    rows = parse_manifest(manifest)
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    _write_matrix(rows, output)
    _write_research_docs(rows, output, manifest_sha256)
    existing = {item.evidence_id for item in registry.list_records()}
    for row in rows:
        record = _evidence_for(row)
        if record.evidence_id not in existing:
            registry.add(record)
            existing.add(record.evidence_id)
    return {
        "status": "passed",
        "baseline_count": len(rows),
        "code_baseline_count": sum(1 for row in rows if row.has_code),
        "manifest_sha256": manifest_sha256,
        "registry": str(registry.path),
    }


def research_status(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root)
    checks = {
        "baseline_matrix": {"status": "passed" if (root / "docs/research/baseline_code_structure_matrix.tsv").exists() else "missing"},
        "evidence_registry": {"status": "passed" if (root / "evidence/registry.jsonl").exists() else "missing"},
        "recent_paper_research": {"status": "needs_attention" if (root / "docs/research/recent_paper_research.needs_attention.md").exists() else "missing"},
        "framework_reference": {"status": "needs_attention" if (root / "docs/research/framework_reference_report.md").exists() else "missing"},
    }
    statuses = {value["status"] for value in checks.values()}
    overall = "needs_attention" if "needs_attention" in statuses or "missing" in statuses else "passed"
    return {"status": overall, "checks": checks}
