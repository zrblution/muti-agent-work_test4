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
    if value is None or value == "":
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


def _clean_list_item(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _required_files_from_yaml(path: Path, root_key: str) -> dict[str, list[str]]:
    discovered: dict[str, list[str]] = {}
    if not path.exists():
        return discovered
    current_id: str | None = None
    collecting_id: str | None = None
    list_indent = 0
    in_root = False
    root_indent = 0

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if stripped == f"{root_key}:":
            in_root = True
            root_indent = indent
            current_id = None
            collecting_id = None
            continue
        if not in_root:
            continue
        if indent <= root_indent and stripped.endswith(":"):
            in_root = stripped == f"{root_key}:"
            current_id = None
            collecting_id = None
            continue
        if collecting_id is not None and indent > list_indent and stripped.startswith("-"):
            discovered.setdefault(collecting_id, []).append(_clean_list_item(stripped[1:]))
            continue
        if collecting_id is not None:
            collecting_id = None
        if indent == root_indent + 2 and stripped.endswith(":"):
            current_id = stripped[:-1]
            continue
        if current_id is None or not stripped.startswith("required_files:"):
            continue
        _, _, raw_value = stripped.partition(":")
        if raw_value.strip():
            discovered[current_id] = _normalize_required_files(raw_value.strip())
            continue
        discovered.setdefault(current_id, [])
        collecting_id = current_id
        list_indent = indent
    return discovered


def _validate_required_file_config(section: str, entries: dict[str, Any], configured_files: dict[str, list[str]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for item_id in sorted(set(entries) | set(configured_files)):
        values = entries.get(item_id, {})
        if not isinstance(values, dict):
            values = {}
        required_files = configured_files.get(item_id, _normalize_required_files(values.get("required_files")))
        for unsafe in unsafe_required_files(required_files):
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
    model_required_files = _required_files_from_yaml(CONFIG_DIR / "models.yaml", "models")
    benchmark_required_files = _required_files_from_yaml(CONFIG_DIR / "benchmarks.yaml", "benchmarks")
    findings = [
        *_validate_required_file_config("models", _load_named_mapping(CONFIG_DIR / "models.yaml", "models"), model_required_files),
        *_validate_required_file_config("benchmarks", _load_named_mapping(CONFIG_DIR / "benchmarks.yaml", "benchmarks"), benchmark_required_files),
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
