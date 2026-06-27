from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adapters.benchmarks._skeleton import ValidateOnlyBenchmarkAdapter
from adapters.inventory import discover_benchmark_metadata, unsafe_required_files
from adapters.path_resolution import resolve_env_path
from stable_core.schemas.common import GenerationOutput, GenerationRequest


PREFERRED_SAMPLE_FILES = (
    "output/coco/coco_pope_random.json",
    "output/coco/coco_pope_popular.json",
    "output/coco/coco_pope_adversarial.json",
    "POPEv2/dataset/annotations.json",
)


class POPEAdapter(ValidateOnlyBenchmarkAdapter):
    benchmark_id = "pope"
    display_name = "POPE"
    task_type = "yes_no_vqa"
    normalizer_version = "pope_normalizer_v1"

    def build_requests(self, split: str, limit: int | None) -> list[GenerationRequest]:
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        benchmark_path = self._benchmark_path()
        rows = self._load_sample_rows(benchmark_path)
        selected = rows if limit is None else rows[:limit]
        requests: list[GenerationRequest] = []
        for index, row in enumerate(selected, start=1):
            sample = _canonical_sample(row, benchmark_path, split=split, index=index)
            requests.append(
                GenerationRequest(
                    request_id=f"pope_req_{index:04d}",
                    image_path=sample["image_path"],
                    prompt=sample["generation_prompt"],
                    benchmark_id=self.benchmark_id,
                    sample_id=sample["sample_id"],
                    metadata={
                        "subset": sample["subset"],
                        "question": sample["question"],
                        "caption_prompt": sample["caption_prompt"],
                        "reference_answer": sample["reference_answer"],
                        "task_type": self.task_type,
                        "generation_prompt": sample["generation_prompt"],
                        "source_file": sample["source_file"],
                    },
                )
            )
        return requests

    def normalize_prediction(self, raw_output: GenerationOutput) -> dict:
        prediction = _normalize_yes_no(raw_output.raw_text)
        reference = _normalize_yes_no(str(raw_output.metadata.get("reference_answer", "")))
        is_correct = prediction == reference if reference in {"yes", "no"} else False
        answer_length = len(raw_output.raw_text.split())
        return {
            "request_id": raw_output.request_id,
            "sample_id": raw_output.metadata.get("sample_id"),
            "benchmark_id": self.benchmark_id,
            "raw_text_ref": raw_output.metadata.get("raw_text_ref"),
            "normalized_prediction": prediction,
            "reference_answer": reference,
            "is_correct": is_correct,
            "hallucination_label": not is_correct,
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

    def _benchmark_path(self) -> Path:
        path_value = self.config.get("path")
        if not path_value:
            raise RuntimeError("POPE benchmark path is not configured.")
        resolved = resolve_env_path(str(path_value))
        if resolved.missing_env_var is not None:
            raise RuntimeError(f"POPE benchmark path requires environment variable {resolved.missing_env_var}.")
        benchmark_path = resolved.path or Path(str(path_value))
        if not benchmark_path.is_dir():
            raise RuntimeError(f"POPE benchmark path is not a directory: {benchmark_path}")
        return benchmark_path

    def _sample_files(self, benchmark_path: Path) -> list[Path]:
        configured_files = [str(name) for name in self.config.get("required_files") or []]
        unsafe_files = unsafe_required_files(configured_files)
        if unsafe_files:
            raise RuntimeError(f"POPE benchmark required_files contains unsafe required file paths: {unsafe_files}")
        candidate_names = configured_files or _preferred_sample_names(benchmark_path) or discover_benchmark_metadata(benchmark_path)
        sample_files = [
            benchmark_path / name
            for name in candidate_names
            if Path(name).suffix.lower() in {".json", ".jsonl"} and (benchmark_path / name).is_file()
        ]
        if not sample_files:
            raise RuntimeError("No parseable POPE JSON or JSONL sample files are configured or discovered.")
        return sample_files

    def _load_sample_rows(self, benchmark_path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for sample_file in self._sample_files(benchmark_path):
            for row in _read_samples(sample_file):
                row = dict(row)
                row["_source_file"] = str(sample_file.relative_to(benchmark_path))
                rows.append(row)
        if not rows:
            raise RuntimeError("POPE sample files did not contain any JSON object samples.")
        return rows


def _preferred_sample_names(benchmark_path: Path) -> list[str]:
    return [name for name in PREFERRED_SAMPLE_FILES if (benchmark_path / name).is_file()]


def _read_samples(path: Path) -> list[dict[str, Any]]:
    payloads = _read_json_values(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        rows.extend(_sample_rows_from_payload(payload))
    return rows


def _read_json_values(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        value, index = decoder.raw_decode(text, index)
        values.append(value)
    return values


def _sample_rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("samples", "data", "annotations", "questions"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _canonical_sample(row: dict[str, Any], root: Path, *, split: str, index: int) -> dict[str, Any]:
    sample_id = str(row.get("sample_id") or row.get("question_id") or row.get("id") or f"pope_{index:06d}")
    subset = row.get("subset") or row.get("category") or row.get("type") or split
    question = str(row.get("question") or row.get("text") or row.get("query") or row.get("prompt") or "")
    reference = _normalize_yes_no(
        str(row.get("reference_answer") or row.get("answer") or row.get("label") or row.get("gt_answer") or "")
    )
    image_value = row.get("image_path") or row.get("image") or row.get("image_id")
    return {
        "sample_id": sample_id,
        "subset": str(subset) if subset is not None else None,
        "image_path": _resolve_image_path(root, image_value),
        "question": question,
        "caption_prompt": None,
        "reference_answer": reference,
        "generation_prompt": question,
        "source_file": row.get("_source_file"),
    }


def _resolve_image_path(root: Path, image_value: Any) -> str | None:
    if image_value in {None, ""}:
        return None
    image_path = Path(str(image_value))
    candidates = _image_path_candidates(root, image_path)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return str(candidates[0])


def _image_path_candidates(root: Path, image_path: Path) -> list[Path]:
    if image_path.is_absolute():
        relative = Path(str(image_path).lstrip("/"))
    else:
        relative = image_path
    candidates = [root / relative]
    name = relative.name
    stem = relative.stem
    if name.startswith("COCO_val2014_"):
        candidates.append(root / "images" / "coco_official_val2014" / name)
    elif stem.isdigit():
        candidates.append(root / "images" / "coco_official_val2014" / f"COCO_val2014_{int(stem):012d}.jpg")
    return candidates


def _normalize_yes_no(text: str) -> str:
    stripped = text.strip().lower()
    if stripped.startswith("yes"):
        return "yes"
    if stripped.startswith("no"):
        return "no"
    return "other"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
