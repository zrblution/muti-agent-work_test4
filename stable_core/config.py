from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adapters.inventory import unsafe_required_files
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


def _normalize_required_files(value: Any) -> list[str]:
    if value in {None, ""}:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        if text == "[]":
            return []
        if text.startswith("[") and text.endswith("]"):
            items = []
            for item in text[1:-1].split(","):
                cleaned = item.strip().strip('"').strip("'")
                if cleaned:
                    items.append(cleaned)
            return items
        return [text]
    return [str(value)]


def _validate_required_file_config(section: str, entries: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for item_id, values in entries.items():
        if not isinstance(values, dict):
            continue
        for unsafe in unsafe_required_files(_normalize_required_files(values.get("required_files"))):
            findings.append(
                {
                    "section": section,
                    "id": item_id,
                    "field": "required_files",
                    "value": unsafe,
                    "message": "required_files entries must be relative paths inside the configured root",
                }
            )
    return findings


def _validate_inventory_config() -> dict[str, Any]:
    findings = [
        *_validate_required_file_config("models", _load_named_mapping(CONFIG_DIR / "models.yaml", "models")),
        *_validate_required_file_config("benchmarks", _load_named_mapping(CONFIG_DIR / "benchmarks.yaml", "benchmarks")),
    ]
    return {"status": "failed" if findings else "passed", "findings": findings}


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
    inventory_report = _validate_inventory_config()
    findings = [name for name, exists in file_checks.items() if not exists]
    findings.extend(inventory_report["findings"])
    status = "passed" if not findings and provider_report["status"] == "passed" and inventory_report["status"] == "passed" else "failed"
    return {
        "status": status,
        "files": file_checks,
        "providers": provider_report,
        "inventory": inventory_report,
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
