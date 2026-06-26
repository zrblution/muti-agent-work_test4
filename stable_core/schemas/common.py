from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field, fields
from typing import Any, Literal, get_args, get_origin

ValidationStatus = Literal["passed", "failed", "needs_attention", "needs_setup", "skipped"]
JobStatus = Literal["pending", "running", "succeeded", "failed", "cancelled", "needs_attention", "skipped_due_to_cache", "blocked_by_gate"]
DecisionStatus = Literal["accept", "reject", "revise", "experiment", "handoff"]


class SerializableDataclass:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        properties: dict[str, dict[str, Any]] = {}
        required: list[str] = []
        for item in fields(cls):
            properties[item.name] = {"type": _json_type(item.type)}
            if item.default is MISSING and item.default_factory is MISSING:
                required.append(item.name)
        return {"title": cls.__name__, "type": "object", "properties": properties, "required": required}


def _json_type(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin is Literal:
        return "string"
    if origin in {list, tuple, set}:
        return "array"
    if origin is dict:
        return "object"
    if annotation is str:
        return "string"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is bool:
        return "boolean"
    return "object"


def _validate_literal(name: str, value: str, literal: Any) -> None:
    allowed = set(get_args(literal))
    if value not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}, got {value!r}")


@dataclass
class EvidenceRef(SerializableDataclass):
    evidence_id: str
    source_type: str
    uri: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Idea(SerializableDataclass):
    idea_id: str
    title: str
    hypothesis: str
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentReview(SerializableDataclass):
    agent_id: str
    decision: Literal["accept", "reject", "revise", "experiment", "handoff"]
    rationale: str
    evidence_refs: list[EvidenceRef]
    scores: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_literal("decision", self.decision, DecisionStatus)
        if self.decision == "accept" and not self.evidence_refs:
            raise ValueError("accept decisions require evidence_refs")


@dataclass
class ExperimentSpec(SerializableDataclass):
    experiment_id: str
    model_id: str
    benchmark_id: str
    limit: int | None
    instrumentation_mode: str
    idea_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentResult(SerializableDataclass):
    experiment_id: str
    status: JobStatus
    metrics: dict[str, Any]
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    run_id: str | None = None

    def __post_init__(self) -> None:
        _validate_literal("status", self.status, JobStatus)


@dataclass
class PhenomenonObservation(SerializableDataclass):
    observation_id: str
    run_id: str
    summary: str
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConvergenceDecision(SerializableDataclass):
    decision: DecisionStatus
    rationale: str
    evidence_refs: list[EvidenceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_literal("decision", self.decision, DecisionStatus)


@dataclass
class RunManifest(SerializableDataclass):
    run_id: str
    run_type: str
    status: JobStatus
    model_id: str | None = None
    benchmark_id: str | None = None
    idea_id: str | None = None
    outputs: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_literal("status", self.status, JobStatus)


@dataclass
class ArtifactManifest(SerializableDataclass):
    run_id: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ValidationReport(SerializableDataclass):
    status: ValidationStatus
    checks: list[dict[str, Any]]
    summary: str

    def __post_init__(self) -> None:
        _validate_literal("status", self.status, ValidationStatus)


@dataclass
class GenerationRequest(SerializableDataclass):
    request_id: str
    image_path: str | None
    prompt: str
    benchmark_id: str
    sample_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationOutput(SerializableDataclass):
    request_id: str
    raw_text: str
    tokens: list[int] | None = None
    logits_topk: list[dict[str, Any]] | None = None
    latency_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


_SCHEMA_CLASSES: tuple[type[SerializableDataclass], ...] = (
    Idea,
    EvidenceRef,
    AgentReview,
    ExperimentSpec,
    ExperimentResult,
    PhenomenonObservation,
    ConvergenceDecision,
    RunManifest,
    ArtifactManifest,
    ValidationReport,
    GenerationRequest,
    GenerationOutput,
)


def export_schema_registry() -> dict[str, dict[str, Any]]:
    return {schema_class.__name__: schema_class.json_schema() for schema_class in _SCHEMA_CLASSES}
