from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_TYPES = {
    "paper",
    "baseline_code",
    "external_framework",
    "experiment",
    "phenomenon",
    "pro_output",
    "agent_review",
    "codex_patch",
}


@dataclass
class EvidenceRecord:
    evidence_id: str
    source_type: str
    source_name: str
    locator: dict[str, Any]
    claim_supported: str
    claim_scope: str
    confidence: float
    created_by: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ValueError("evidence_id is required")
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {sorted(SOURCE_TYPES)}")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceRecord":
        return cls(**payload)


class EvidenceRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def list_records(self) -> list[EvidenceRecord]:
        if not self.path.exists():
            return []
        records: list[EvidenceRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(EvidenceRecord.from_dict(json.loads(line)))
        return records

    def add(self, record: EvidenceRecord) -> None:
        self.init()
        existing_ids = {item.evidence_id for item in self.list_records()}
        if record.evidence_id in existing_ids:
            raise ValueError(f"Duplicate evidence_id: {record.evidence_id}")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + chr(10))


def init_registry(path: str | Path) -> dict[str, Any]:
    registry = EvidenceRegistry(path)
    registry.init()
    return {"status": "passed", "registry": str(registry.path)}


def add_record_from_args(args: Any) -> dict[str, Any]:
    registry = EvidenceRegistry(args.registry)
    locator = {
        "path": args.path,
        "url": args.url,
        "commit": args.commit,
        "line_start": args.line_start,
        "line_end": args.line_end,
        "run_id": args.run_id,
        "artifact_id": args.artifact_id,
    }
    record = EvidenceRecord(
        evidence_id=args.evidence_id,
        source_type=args.source_type,
        source_name=args.source_name,
        locator=locator,
        claim_supported=args.claim_supported,
        claim_scope=args.claim_scope,
        confidence=float(args.confidence),
        created_by=args.created_by,
    )
    registry.add(record)
    return {"status": "passed", "record": record.to_dict()}


def list_registry(path: str | Path) -> dict[str, Any]:
    records = [record.to_dict() for record in EvidenceRegistry(path).list_records()]
    return {"status": "passed", "count": len(records), "records": records}
