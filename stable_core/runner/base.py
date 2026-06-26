from __future__ import annotations

from typing import Protocol, runtime_checkable

from stable_core.schemas.common import ValidationReport


@runtime_checkable
class ExperimentRunner(Protocol):
    def validate(self, experiment_spec: dict) -> ValidationReport:
        """Validate a structured experiment spec without executing arbitrary shell."""

    def submit(self, experiment_spec: dict) -> dict:
        """Submit a controlled job and return job_id/run_id metadata."""

    def poll(self, job_id: str) -> dict:
        """Return job status, heartbeat, and exit code when finished."""

    def resume(self, workflow_id: str) -> dict:
        """Resume from state.json and run manifests."""

    def cancel(self, job_id: str) -> dict:
        """Cancel a controlled job."""
