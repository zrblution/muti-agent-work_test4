from pathlib import Path

import pytest

from adapters.benchmarks.base import BenchmarkAdapter
from adapters.models.base import ModelAdapter
from idea_plugins.base import IdeaPlugin
from instrumentation.base import Probe
from stable_core.runner.base import ExperimentRunner
from stable_core.schemas.common import (
    AgentReview,
    ArtifactManifest,
    ConvergenceDecision,
    EvidenceRef,
    ExperimentResult,
    ExperimentSpec,
    GenerationOutput,
    GenerationRequest,
    Idea,
    PhenomenonObservation,
    RunManifest,
    ValidationReport,
    export_schema_registry,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_core_schema_objects_are_stable_and_serializable() -> None:
    evidence = EvidenceRef(evidence_id="ev_001", source_type="spec", uri="docs/specs_pointer.md", summary="phase contract")
    idea = Idea(idea_id="idea_dummy", title="Dummy", hypothesis="No-op baseline", evidence_refs=[evidence])
    review = AgentReview(
        agent_id="NoveltyCritic",
        decision="revise",
        rationale="Needs stronger evidence",
        evidence_refs=[evidence],
    )
    spec = ExperimentSpec(
        experiment_id="exp_fake_001",
        model_id="fake_model",
        benchmark_id="fake_benchmark",
        limit=3,
        instrumentation_mode="none",
    )
    result = ExperimentResult(
        experiment_id="exp_fake_001",
        status="succeeded",
        metrics={"accuracy": 1.0},
        evidence_refs=[evidence],
    )
    observation = PhenomenonObservation(
        observation_id="obs_001",
        run_id="run_fake_001",
        summary="No hallucination in fake output",
        evidence_refs=[evidence],
    )
    decision = ConvergenceDecision(decision="experiment", rationale="Run controlled fake path", evidence_refs=[evidence])
    run_manifest = RunManifest(run_id="run_fake_001", run_type="preflight", status="succeeded")
    artifact_manifest = ArtifactManifest(run_id="run_fake_001", artifacts=[])

    payloads = [
        evidence,
        idea,
        review,
        spec,
        result,
        observation,
        decision,
        run_manifest,
        artifact_manifest,
    ]
    for payload in payloads:
        as_dict = payload.to_dict()
        assert isinstance(as_dict, dict)
        assert as_dict


def test_validation_report_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="status"):
        ValidationReport(status="unknown", checks=[], summary="bad")


def test_generation_request_and_output_preserve_raw_text() -> None:
    request = GenerationRequest(
        request_id="req_001",
        image_path=None,
        prompt="What is in the image?",
        benchmark_id="fake_benchmark",
        sample_id="sample_001",
    )
    output = GenerationOutput(request_id=request.request_id, raw_text="A red cube.")

    assert output.to_dict()["raw_text"] == "A red cube."
    assert request.to_dict()["metadata"] == {}


def test_protocols_expose_required_methods() -> None:
    expected = {
        ModelAdapter: ["validate_environment", "load", "generate", "unload", "supports_instrumentation"],
        BenchmarkAdapter: ["validate_paths", "build_requests", "normalize_prediction", "compute_metrics", "extract_failure_cases"],
        IdeaPlugin: ["validate_compatibility", "prepare", "modify_request", "wrap_generation", "collect_artifacts"],
        Probe: ["attach", "capture", "flush", "detach"],
        ExperimentRunner: ["validate", "submit", "poll", "resume", "cancel"],
    }

    for protocol, methods in expected.items():
        for method in methods:
            assert hasattr(protocol, method), f"{protocol.__name__}.{method} missing"


def test_schema_registry_contains_phase_one_contracts() -> None:
    registry = export_schema_registry()

    for name in [
        "Idea",
        "EvidenceRef",
        "AgentReview",
        "ExperimentSpec",
        "ExperimentResult",
        "PhenomenonObservation",
        "ConvergenceDecision",
        "RunManifest",
        "ArtifactManifest",
        "ValidationReport",
    ]:
        assert name in registry
        assert registry[name]["type"] == "object"


def test_stable_core_has_no_project_specific_absolute_paths() -> None:
    forbidden = ["/home/vepfs/data/work1/muti-agent-work_test4", "/Users/zrblution/Documents"]
    for file_path in (REPO_ROOT / "stable_core").rglob("*.py"):
        text = file_path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{file_path} contains hardcoded project path"


def test_adapters_do_not_cross_import_each_other() -> None:
    for file_path in (REPO_ROOT / "adapters" / "benchmarks").rglob("*.py"):
        text = file_path.read_text(encoding="utf-8")
        assert "adapters.models" not in text
    for file_path in (REPO_ROOT / "adapters" / "models").rglob("*.py"):
        text = file_path.read_text(encoding="utf-8")
        assert "adapters.benchmarks" not in text
