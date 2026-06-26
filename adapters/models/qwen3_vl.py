from __future__ import annotations

from importlib import import_module
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from adapters.models._skeleton import ValidateOnlyModelAdapter
from adapters.path_resolution import resolve_env_path
from stable_core.schemas.common import GenerationOutput, GenerationRequest


class Qwen3VLAdapter(ValidateOnlyModelAdapter):
    model_id = "qwen3_vl_2b_instruct"
    display_name = "Qwen3-VL-2B-Instruct"
    default_max_new_tokens = 16

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._model: Any | None = None
        self._processor: Any | None = None

    def load(self) -> object:
        validation = self.validate_environment()
        if validation.status != "passed":
            raise RuntimeError(f"{self.display_name} validation did not pass before load: {validation.summary}")

        model_path = self._model_path()
        transformers = import_module("transformers")
        processor_class = getattr(transformers, "AutoProcessor")
        model_class = _select_qwen_model_class(transformers)
        trust_remote_code = bool(self.config.get("trust_remote_code", True))
        load_kwargs: dict[str, Any] = {
            "trust_remote_code": trust_remote_code,
            "local_files_only": True,
        }
        torch_dtype = _torch_dtype(self.config.get("precision", "bf16"))
        if torch_dtype is not None:
            load_kwargs["torch_dtype"] = torch_dtype
        device_map = self.config.get("device_map", "auto")
        if device_map is not None:
            load_kwargs["device_map"] = device_map

        self._processor = processor_class.from_pretrained(
            str(model_path),
            trust_remote_code=trust_remote_code,
            local_files_only=True,
        )
        self._model = model_class.from_pretrained(str(model_path), **load_kwargs)
        if hasattr(self._model, "eval"):
            self._model.eval()
        self._loaded = True
        return self._model

    def generate(self, request: GenerationRequest) -> GenerationOutput:
        if not self._loaded or self._model is None or self._processor is None:
            raise RuntimeError(f"{self.display_name} load() must be called before generate().")

        messages = [_user_message(request)]
        inputs = self._processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        device = getattr(self._model, "device", None)
        if device is not None and hasattr(inputs, "to"):
            inputs = inputs.to(device)

        prompt_length = _prompt_length(inputs)
        max_new_tokens = int(self.config.get("max_new_tokens", self.default_max_new_tokens))
        generation_kwargs = dict(inputs)
        generation_kwargs["max_new_tokens"] = max_new_tokens

        started = perf_counter()
        generated_ids = self._model.generate(**generation_kwargs)
        latency_ms = (perf_counter() - started) * 1000
        new_token_ids = _new_token_ids(generated_ids, prompt_length)
        raw_text = self._processor.decode(new_token_ids, skip_special_tokens=True).strip()
        return GenerationOutput(
            request_id=request.request_id,
            raw_text=raw_text,
            tokens=_token_list(new_token_ids),
            latency_ms=latency_ms,
            metadata={
                **request.metadata,
                "model_id": self.model_id,
                "benchmark_id": request.benchmark_id,
                "sample_id": request.sample_id,
                "generation_config": {"max_new_tokens": max_new_tokens},
            },
        )

    def unload(self) -> None:
        self._model = None
        self._processor = None
        self._loaded = False

    def _model_path(self) -> Path:
        path_value = self.config.get("path") or self.config.get("local_path")
        if not path_value:
            raise RuntimeError("Qwen3-VL model path is not configured.")
        resolved = resolve_env_path(str(path_value))
        if resolved.missing_env_var is not None:
            raise RuntimeError(f"Qwen3-VL model path requires environment variable {resolved.missing_env_var}.")
        model_path = resolved.path or Path(str(path_value))
        if not model_path.is_dir():
            raise RuntimeError(f"Qwen3-VL model path is not a directory: {model_path}")
        return model_path


def _select_qwen_model_class(transformers_module: Any) -> Any:
    for class_name in (
        "Qwen3VLForConditionalGeneration",
        "AutoModelForMultimodalLM",
        "AutoModelForImageTextToText",
        "AutoModelForVision2Seq",
    ):
        model_class = getattr(transformers_module, class_name, None)
        if model_class is not None:
            return model_class
    raise RuntimeError(
        "transformers does not expose a supported Qwen3-VL model class. "
        "Expected Qwen3VLForConditionalGeneration or a compatible AutoModel class."
    )


def _torch_dtype(precision: Any) -> Any | None:
    normalized = str(precision or "").strip().lower()
    if not normalized:
        return None
    if normalized == "auto":
        return "auto"
    torch = import_module("torch")
    if normalized in {"bf16", "bfloat16"}:
        return getattr(torch, "bfloat16")
    if normalized in {"fp16", "float16"}:
        return getattr(torch, "float16")
    if normalized in {"fp32", "float32"}:
        return getattr(torch, "float32")
    raise ValueError(f"Unsupported Qwen3-VL precision: {precision!r}")


def _user_message(request: GenerationRequest) -> dict[str, Any]:
    content: list[dict[str, str]] = []
    if request.image_path:
        image_path = Path(request.image_path)
        if not image_path.is_file():
            raise FileNotFoundError(f"Qwen3-VL input image does not exist: {image_path}")
        content.append({"type": "image", "url": image_path.resolve().as_uri()})
    content.append({"type": "text", "text": request.prompt})
    return {"role": "user", "content": content}


def _prompt_length(inputs: Mapping[str, Any]) -> int:
    input_ids = inputs.get("input_ids")
    if input_ids is None:
        return 0
    shape = getattr(input_ids, "shape", None)
    if shape:
        return int(shape[-1])
    try:
        return len(input_ids[0])
    except (TypeError, IndexError):
        return 0


def _new_token_ids(generated_ids: Any, prompt_length: int) -> Any:
    first_sequence = generated_ids[0]
    return first_sequence[prompt_length:]


def _token_list(token_ids: Any) -> list[int] | None:
    if hasattr(token_ids, "tolist"):
        token_ids = token_ids.tolist()
    if isinstance(token_ids, list):
        return [int(token_id) for token_id in token_ids]
    return None
