from __future__ import annotations

from adapters.models._skeleton import ValidateOnlyModelAdapter


class InternVLAdapter(ValidateOnlyModelAdapter):
    model_id = "internvl3_5_4b"
    display_name = "InternVL3.5-4B"
