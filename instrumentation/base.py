from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Probe(Protocol):
    probe_id: str
    signal_type: str

    def attach(self, model_handle: Any, config: dict) -> None:
        """Attach hooks while respecting instrumentation budget."""

    def capture(self, request_id: str, context: dict) -> dict:
        """Capture lightweight signal or summary."""

    def flush(self, run_dir: Path) -> list[dict]:
        """Persist artifacts and return manifest-compatible refs."""

    def detach(self) -> None:
        """Remove hooks to avoid memory leaks."""
