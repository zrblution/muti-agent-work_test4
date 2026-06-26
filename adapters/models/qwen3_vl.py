from __future__ import annotations

from adapters.models._skeleton import ValidateOnlyModelAdapter


class Qwen3VLAdapter(ValidateOnlyModelAdapter):
    model_id = "qwen3_vl_2b_instruct"
    display_name = "Qwen3-VL-2B-Instruct"
