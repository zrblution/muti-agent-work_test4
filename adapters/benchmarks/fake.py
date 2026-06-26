from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stable_core.schemas.common import GenerationOutput, GenerationRequest, ValidationReport


class FakeBenchmarkAdapter:
    benchmark_id = "fake_benchmark"
    task_type = "yes_no_vqa"
    normalizer_version = "fake_normalizer_v1"

    _samples: tuple[dict[str, Any], ...] = (
        {"sample_id": "fake_0001", "question": "Is there a red cube?", "reference_answer": "yes"},
        {"sample_id": "fake_0002", "question": "Is there a blue sphere?", "reference_answer": "no"},
        {"sample_id": "fake_0003", "question": "Is the object visible?", "reference_answer": "yes"},
        {"sample_id": "fake_0004", "question": "Is there a green triangle?", "reference_answer": "no"},
    )

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def validate_paths(self) -> ValidationReport:
        return ValidationReport(
            status="passed",
            checks=[
                {"name": "benchmark_id", "status": "passed", "value": self.benchmark_id},
                {"name": "external_dataset", "status": "skipped", "message": "Fake benchmark uses embedded samples."},
            ],
            summary="Fake benchmark is available without external files.",
        )

    def build_requests(self, split: str, limit: int | None) -> list[GenerationRequest]:
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        selected = list(self._samples if limit is None else self._samples[:limit])
        requests: list[GenerationRequest] = []
        for index, sample in enumerate(selected, start=1):
            sample_id = str(sample["sample_id"])
            requests.append(
                GenerationRequest(
                    request_id=f"fake_req_{index:04d}",
                    image_path=None,
                    prompt=str(sample["question"]),
                    benchmark_id=self.benchmark_id,
                    sample_id=sample_id,
                    metadata={
                        "subset": split,
                        "question": sample["question"],
                        "generation_prompt": sample["question"],
                        "reference_answer": sample["reference_answer"],
                        "task_type": self.task_type,
                    },
                )
            )
        return requests

    def normalize_prediction(self, raw_output: GenerationOutput) -> dict:
        text = raw_output.raw_text.strip().lower()
        prediction = "yes" if text.startswith("yes") else "no" if text.startswith("no") else "other"
        reference = str(raw_output.metadata.get("reference_answer", "")).lower()
        answer_length = len(raw_output.raw_text.split())
        return {
            "request_id": raw_output.request_id,
            "sample_id": raw_output.metadata.get("sample_id"),
            "benchmark_id": self.benchmark_id,
            "raw_text_ref": None,
            "normalized_prediction": prediction,
            "reference_answer": reference,
            "is_correct": prediction == reference,
            "hallucination_label": prediction != reference,
            "answer_length": answer_length,
            "normalizer_version": self.normalizer_version,
            "metadata": {"raw_text": raw_output.raw_text},
        }

    def compute_metrics(self, normalized_outputs_path: Path) -> dict:
        rows = _read_jsonl(normalized_outputs_path)
        sample_count = len(rows)
        correct = sum(1 for row in rows if row.get("is_correct"))
        yes_count = sum(1 for row in rows if row.get("normalized_prediction") == "yes")
        hallucinations = sum(1 for row in rows if row.get("hallucination_label"))
        answer_lengths = [float(row.get("answer_length", 0)) for row in rows]
        return {
            "sample_count": sample_count,
            "metrics": {
                "accuracy": correct / sample_count if sample_count else 0.0,
                "hallucination_rate": hallucinations / sample_count if sample_count else 0.0,
                "yes_rate": yes_count / sample_count if sample_count else 0.0,
                "answer_length_mean": sum(answer_lengths) / sample_count if sample_count else 0.0,
            },
        }

    def extract_failure_cases(self, normalized_outputs_path: Path) -> list[dict]:
        return [row for row in _read_jsonl(normalized_outputs_path) if not row.get("is_correct")]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
