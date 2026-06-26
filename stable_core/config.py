from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stable_core.schemas.common import export_schema_registry
from stable_core.validation.preflight import REPO_ROOT, parse_simple_yaml, validate_provider_config

CONFIG_DIR = REPO_ROOT / "project_config"


def _load_named_mapping(path: Path, key: str) -> dict[str, Any]:
    data = parse_simple_yaml(path)
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def list_models() -> list[str]:
    return sorted(_load_named_mapping(CONFIG_DIR / "models.yaml", "models"))


def list_benchmarks() -> list[str]:
    return sorted(_load_named_mapping(CONFIG_DIR / "benchmarks.yaml", "benchmarks"))


def list_agents() -> list[str]:
    return sorted(_load_named_mapping(CONFIG_DIR / "agents.yaml", "providers"))


def validate_config() -> dict[str, Any]:
    required_files = [
        "paths.yaml",
        "models.yaml",
        "benchmarks.yaml",
        "agents.yaml",
        "security.yaml",
        "server.yaml",
        "experiment_budget.yaml",
        "instrumentation.yaml",
        "git_policy.yaml",
    ]
    file_checks = {name: (CONFIG_DIR / name).exists() for name in required_files}
    provider_report = validate_provider_config(CONFIG_DIR / "agents.yaml")
    findings = [name for name, exists in file_checks.items() if not exists]
    status = "passed" if not findings and provider_report["status"] == "passed" else "failed"
    return {
        "status": status,
        "files": file_checks,
        "providers": provider_report,
        "models": list_models(),
        "benchmarks": list_benchmarks(),
        "agents": list_agents(),
        "findings": findings,
    }


def export_schemas(output_dir: Path) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    registry = export_schema_registry()
    for name, schema in registry.items():
        (output_dir / f"{name}.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
    return sorted(registry)
