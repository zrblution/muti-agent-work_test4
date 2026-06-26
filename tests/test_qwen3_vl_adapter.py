import sys
import types
from pathlib import Path

import pytest

import adapters.models.qwen3_vl as qwen3_vl_module
from adapters.models.qwen3_vl import Qwen3VLAdapter
from stable_core.schemas.common import GenerationRequest


class _InputIds:
    shape = (1, 3)


class _ProcessorInputs(dict):
    def to(self, device: str) -> "_ProcessorInputs":
        self["moved_to"] = device
        return self


def _install_fake_qwen_runtime(monkeypatch: pytest.MonkeyPatch) -> dict:
    calls: dict = {"processor": [], "model": [], "messages": [], "decode": []}

    class FakeTorch:
        bfloat16 = "bf16-dtype"
        float16 = "fp16-dtype"
        float32 = "fp32-dtype"

    class FakeProcessor:
        @classmethod
        def from_pretrained(cls, model_path: str, **kwargs):
            calls["processor"].append({"model_path": model_path, "kwargs": kwargs})
            return cls()

        def apply_chat_template(self, messages, **kwargs):
            calls["messages"].append({"messages": messages, "kwargs": kwargs})
            return _ProcessorInputs({"input_ids": _InputIds()})

        def decode(self, token_ids, **kwargs):
            calls["decode"].append({"token_ids": token_ids, "kwargs": kwargs})
            return "Yes, there is a cat."

    class FakeModel:
        device = "cuda:0"

        def __init__(self) -> None:
            self.eval_called = False

        @classmethod
        def from_pretrained(cls, model_path: str, **kwargs):
            calls["model"].append({"model_path": model_path, "kwargs": kwargs})
            instance = cls()
            calls["model_instance"] = instance
            return instance

        def eval(self) -> None:
            self.eval_called = True

        def generate(self, **kwargs):
            calls["generate_kwargs"] = kwargs
            return [[101, 102, 103, 201, 202]]

    fake_transformers = types.SimpleNamespace(
        AutoProcessor=FakeProcessor,
        AutoModelForMultimodalLM=FakeModel,
    )
    monkeypatch.setitem(sys.modules, "torch", FakeTorch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    return calls


def test_qwen3_vl_validate_environment_checks_runtime_dependencies_without_loading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _install_fake_qwen_runtime(monkeypatch)
    model_path = tmp_path / "Qwen3-VL-2B-Instruct"
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")

    report = Qwen3VLAdapter({"path": str(model_path), "precision": "bf16"}).validate_environment()

    runtime_check = next(check for check in report.checks if check["name"] == "runtime_dependencies")
    assert report.status == "passed"
    assert runtime_check["status"] == "passed"
    assert runtime_check["processor_class"] == "FakeProcessor"
    assert runtime_check["model_class"] == "FakeModel"
    assert calls["processor"] == []
    assert calls["model"] == []


def test_qwen3_vl_validate_runtime_dependencies_does_not_require_model_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_fake_qwen_runtime(monkeypatch)

    report = Qwen3VLAdapter({"precision": "bf16"}).validate_runtime_dependencies()

    runtime_check = next(check for check in report.checks if check["name"] == "runtime_dependencies")
    assert report.status == "passed"
    assert runtime_check["status"] == "passed"
    assert runtime_check["processor_class"] == "FakeProcessor"
    assert runtime_check["model_class"] == "FakeModel"
    assert calls["processor"] == []
    assert calls["model"] == []


def test_qwen3_vl_validate_environment_reports_missing_transformers_dependency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model_path = tmp_path / "Qwen3-VL-2B-Instruct"
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")

    fake_torch = types.SimpleNamespace(bfloat16="bf16-dtype", float16="fp16-dtype", float32="fp32-dtype")

    def fake_import_module(name: str):
        if name == "transformers":
            raise ImportError("transformers is not installed")
        if name == "torch":
            return fake_torch
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(qwen3_vl_module, "import_module", fake_import_module)

    report = Qwen3VLAdapter({"path": str(model_path), "precision": "bf16"}).validate_environment()

    runtime_check = next(check for check in report.checks if check["name"] == "runtime_dependencies")
    assert report.status == "needs_setup"
    assert runtime_check["status"] == "needs_setup"
    assert runtime_check["missing_modules"] == ["transformers"]
    assert "no model was loaded" in report.summary


def test_qwen3_vl_load_uses_local_files_only_and_runtime_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _install_fake_qwen_runtime(monkeypatch)
    model_path = tmp_path / "Qwen3-VL-2B-Instruct"
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")

    adapter = Qwen3VLAdapter(
        {
            "path": str(model_path),
            "precision": "bf16",
            "device_map": "auto",
            "trust_remote_code": True,
            "max_new_tokens": 12,
        }
    )

    loaded = adapter.load()

    assert loaded is calls["model_instance"]
    assert calls["model_instance"].eval_called is True
    assert calls["processor"] == [
        {
            "model_path": str(model_path),
            "kwargs": {"trust_remote_code": True, "local_files_only": True},
        }
    ]
    assert calls["model"] == [
        {
            "model_path": str(model_path),
            "kwargs": {
                "trust_remote_code": True,
                "local_files_only": True,
                "torch_dtype": "bf16-dtype",
                "device_map": "auto",
            },
        }
    ]


def test_qwen3_vl_generate_builds_multimodal_chat_and_decodes_new_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _install_fake_qwen_runtime(monkeypatch)
    model_path = tmp_path / "Qwen3-VL-2B-Instruct"
    image_path = tmp_path / "image.jpg"
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    image_path.write_bytes(b"fake image bytes")
    adapter = Qwen3VLAdapter({"path": str(model_path), "precision": "bf16", "max_new_tokens": 7})
    adapter.load()

    output = adapter.generate(
        GenerationRequest(
            request_id="pope_req_0001",
            image_path=str(image_path),
            prompt="Is there a cat in the image?",
            benchmark_id="pope",
            sample_id="pope_0001",
            metadata={"reference_answer": "yes"},
        )
    )

    message = calls["messages"][0]["messages"][0]
    assert message["role"] == "user"
    assert message["content"][0]["type"] == "image"
    assert message["content"][0]["url"] == image_path.resolve().as_uri()
    assert message["content"][1] == {"type": "text", "text": "Is there a cat in the image?"}
    assert calls["messages"][0]["kwargs"]["tokenize"] is True
    assert calls["messages"][0]["kwargs"]["add_generation_prompt"] is True
    assert calls["generate_kwargs"]["max_new_tokens"] == 7
    assert calls["generate_kwargs"]["moved_to"] == "cuda:0"
    assert calls["decode"] == [
        {
            "token_ids": [201, 202],
            "kwargs": {"skip_special_tokens": True},
        }
    ]
    assert output.request_id == "pope_req_0001"
    assert output.raw_text == "Yes, there is a cat."
    assert output.metadata["model_id"] == "qwen3_vl_2b_instruct"
    assert output.metadata["benchmark_id"] == "pope"
    assert output.metadata["sample_id"] == "pope_0001"


def test_qwen3_vl_generate_requires_load() -> None:
    adapter = Qwen3VLAdapter()

    with pytest.raises(RuntimeError, match="load"):
        adapter.generate(
            GenerationRequest(
                request_id="req",
                image_path=None,
                prompt="Question?",
                benchmark_id="pope",
                sample_id="sample",
            )
        )
