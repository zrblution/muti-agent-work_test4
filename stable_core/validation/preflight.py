from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from stable_core.security.secret_scan import scan_paths, write_report

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATHS_CONFIG = REPO_ROOT / "project_config" / "paths.yaml"
DEFAULT_PROVIDER_CONFIG = REPO_ROOT / "project_config" / "agents.yaml"


@dataclass(frozen=True)
class PreflightConfig:
    spec_root: Path
    local_agent_system_root: Path
    local_baseline_repo: Path
    server_framework_root: Path
    remote_execution_root: Path
    model_root: Path | None
    benchmark_root: Path | None
    artifact_root: Path
    provider_config: Path


def _clean_scalar(value: str) -> str | None:
    value = value.strip()
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def parse_simple_yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, data)]
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#") or raw_line.lstrip().startswith("-"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, _, raw_value = raw_line.strip().partition(":")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if raw_value.strip() == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _clean_scalar(raw_value)
    return data


def _path_from(value: Any) -> Path | None:
    if value in {None, ""}:
        return None
    return Path(str(value))


def _resolve_repo_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path if path.is_absolute() else REPO_ROOT / path


def load_preflight_config(paths_config: Path = DEFAULT_PATHS_CONFIG) -> PreflightConfig:
    data = parse_simple_yaml(paths_config)
    spec = data.get("spec", {})
    local = data.get("local", {})
    server = data.get("server", {})
    return PreflightConfig(
        spec_root=Path(spec.get("root", "")),
        local_agent_system_root=Path(local.get("agent_system_root", "")),
        local_baseline_repo=Path(local.get("baseline_repo", "")),
        server_framework_root=Path(server.get("framework_root", REPO_ROOT)),
        remote_execution_root=Path(server.get("remote_execution_root", server.get("framework_root", REPO_ROOT))),
        model_root=_path_from(server.get("model_root")),
        benchmark_root=_path_from(server.get("benchmark_root")),
        artifact_root=_resolve_repo_path(_path_from(server.get("artifact_root", "runs/artifacts"))) or REPO_ROOT / "runs/artifacts",
        provider_config=DEFAULT_PROVIDER_CONFIG,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run_git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False)


def _is_external_local_path(path: Path) -> bool:
    return platform.system() != "Darwin" and str(path).startswith("/Users/")


def _check_path(path: Path | None, *, allow_external_reference: bool = False) -> dict[str, Any]:
    if path is None:
        return {"status": "needs_setup", "path": None}
    if allow_external_reference and _is_external_local_path(path):
        return {"status": "configured_external", "path": str(path)}
    if path.exists():
        return {"status": "verified", "path": str(path), "is_dir": path.is_dir()}
    return {"status": "missing", "path": str(path)}


def collect_path_check(config: PreflightConfig) -> dict[str, Any]:
    return {
        "spec_root": _check_path(config.spec_root, allow_external_reference=True),
        "local_agent_system_root": _check_path(config.local_agent_system_root, allow_external_reference=True),
        "local_baseline_repo": _check_path(config.local_baseline_repo, allow_external_reference=True),
        "server_framework_root": _check_path(config.server_framework_root),
        "remote_execution_root": _check_path(config.remote_execution_root),
        "model_root": _check_path(config.model_root),
        "benchmark_root": _check_path(config.benchmark_root),
        "artifact_root": _check_path(config.artifact_root),
    }


def collect_git_check() -> dict[str, Any]:
    branch = _run_git(["branch", "--show-current"]).stdout.strip()
    status = _run_git(["status", "--porcelain"]).stdout.splitlines()
    remotes = _run_git(["remote", "-v"]).stdout.splitlines()
    env_tracked = _run_git(["ls-files", "--error-unmatch", ".env"]).returncode == 0
    env_ignored = _run_git(["check-ignore", "-q", ".env"]).returncode == 0
    inside_work_tree = _run_git(["rev-parse", "--is-inside-work-tree"]).stdout.strip() == "true"
    return {
        "status": "failed" if env_tracked else "passed",
        "inside_work_tree": inside_work_tree,
        "branch": branch,
        "remote_urls": remotes,
        "working_tree_clean": not status,
        "dirty_paths": status,
        "env_tracked": env_tracked,
        "env_ignored": env_ignored,
    }


def collect_env_check() -> dict[str, Any]:
    usage = shutil.disk_usage(REPO_ROOT)
    package_status = {
        name: importlib.util.find_spec(name) is not None
        for name in ["torch", "transformers", "accelerate", "vllm"]
    }
    return {
        "status": "passed",
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "executable": sys.executable,
        "cuda_visible_devices_set": "CUDA_VISIBLE_DEVICES" in os.environ,
        "packages": package_status,
        "disk_free_bytes": usage.free,
    }


def collect_gpu_check() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return {"status": "unavailable", "gpus": [], "message": "nvidia-smi unavailable"}
    if result.returncode != 0:
        return {"status": "unavailable", "gpus": [], "message": "nvidia-smi unavailable"}
    return {"status": "verified", "gpus": [line.strip() for line in result.stdout.splitlines() if line.strip()]}


def collect_model_check(config: PreflightConfig) -> dict[str, Any]:
    root_status = _check_path(config.model_root)
    return {
        "status": "verified" if root_status["status"] == "verified" else "needs_setup",
        "model_root": root_status,
        "models": {
            "qwen3_vl_2b_instruct": {"status": "not_checked", "reason": "Phase 0 records paths only"},
            "internvl3_5_4b": {"status": "not_checked", "reason": "Phase 0 records paths only"},
        },
    }


def collect_benchmark_check(config: PreflightConfig) -> dict[str, Any]:
    root_status = _check_path(config.benchmark_root)
    return {
        "status": "verified" if root_status["status"] == "verified" else "needs_setup",
        "benchmark_root": root_status,
        "benchmarks": {
            name: {"status": "not_checked", "reason": "Phase 0 records paths only"}
            for name in ["pope", "chair", "amber", "mme"]
        },
    }


def validate_provider_config(provider_config: Path) -> dict[str, Any]:
    if not provider_config.exists():
        return {"status": "needs_setup", "providers": {}, "findings": [{"field": "providers", "message": "provider config missing"}]}
    data = parse_simple_yaml(provider_config)
    providers = data.get("providers", {})
    findings: list[dict[str, Any]] = []
    normalized: dict[str, dict[str, Any]] = {}
    if not isinstance(providers, dict):
        return {"status": "failed", "providers": {}, "findings": [{"field": "providers", "message": "providers must be a mapping"}]}
    for name, values in providers.items():
        if not isinstance(values, dict):
            findings.append({"provider": name, "field": "provider", "message": "provider must be a mapping"})
            continue
        normalized[name] = values
        for field, value in values.items():
            if field in {"api_key", "secret", "token", "password"}:
                findings.append({"provider": name, "field": field, "message": "inline secret fields are forbidden"})
            if isinstance(value, str) and "sk-" in value:
                findings.append({"provider": name, "field": field, "message": "key-like value is forbidden"})
        if "api_key_env" not in values:
            findings.append({"provider": name, "field": "api_key_env", "message": "provider must reference an environment variable name"})
    return {"status": "failed" if findings else "passed", "providers": normalized, "findings": findings}


def _summary_lines(report: dict[str, Any]) -> list[str]:
    lines = ["# Phase 0 Preflight Summary", "", f"Status: `{report['status']}`", ""]
    for section in ["path_check", "git_check", "env_check", "gpu_check", "model_check", "benchmark_check", "provider_check", "secret_scan_report"]:
        lines.append(f"## {section}")
        payload = report.get(section, {})
        if isinstance(payload, dict) and "status" in payload:
            lines.append(f"- status: `{payload['status']}`")
        elif isinstance(payload, dict):
            statuses = sorted({str(value.get("status")) for value in payload.values() if isinstance(value, dict) and "status" in value})
            lines.append(f"- statuses: {', '.join(statuses) if statuses else 'recorded'}")
        else:
            lines.append("- recorded")
        lines.append("")
    lines.append("Phase 0 does not download models or run real benchmarks.")
    return lines


def _overall_status(*sections: dict[str, Any]) -> str:
    statuses: list[str] = []
    for section in sections:
        if "status" in section:
            statuses.append(str(section["status"]))
        for value in section.values():
            if isinstance(value, dict) and "status" in value:
                statuses.append(str(value["status"]))
    if "failed" in statuses:
        return "failed"
    if any(status in {"missing", "needs_setup", "unavailable"} for status in statuses):
        return "needs_setup"
    return "passed"


def run_preflight(
    *,
    config: PreflightConfig | None = None,
    output_dir: Path | None = None,
    dry_run: bool = False,
    scan_paths: Sequence[Path] | None = None,
) -> dict[str, Any]:
    del dry_run
    config = config or load_preflight_config()
    output_dir = output_dir or REPO_ROOT / "runs" / "preflight"
    output_dir.mkdir(parents=True, exist_ok=True)

    path_check = collect_path_check(config)
    git_check = collect_git_check()
    env_check = collect_env_check()
    gpu_check = collect_gpu_check()
    model_check = collect_model_check(config)
    benchmark_check = collect_benchmark_check(config)
    provider_check = validate_provider_config(config.provider_config)
    default_scan_paths = [
        REPO_ROOT / "adapters",
        REPO_ROOT / "docs",
        REPO_ROOT / "experiments",
        REPO_ROOT / "idea_plugins",
        REPO_ROOT / "instrumentation",
        REPO_ROOT / "project_config",
        REPO_ROOT / "research_tools",
        REPO_ROOT / "stable_core",
        REPO_ROOT / "tests",
        REPO_ROOT / "scripts",
        REPO_ROOT / "runs",
        REPO_ROOT / ".env.example",
        REPO_ROOT / ".gitignore",
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "README.md",
    ]
    secret_report = scan_paths and globals()["scan_paths"](scan_paths) or globals()["scan_paths"](default_scan_paths)

    _write_json(output_dir / "path_check.json", path_check)
    _write_json(output_dir / "git_check.json", git_check)
    _write_json(output_dir / "env_check.json", env_check)
    _write_json(output_dir / "gpu_check.json", gpu_check)
    _write_json(output_dir / "model_check.json", model_check)
    _write_json(output_dir / "benchmark_check.json", benchmark_check)
    _write_json(output_dir / "provider_check.json", provider_check)
    write_report(secret_report, output_dir / "secret_scan_report.json")

    status = _overall_status(path_check, git_check, env_check, gpu_check, model_check, benchmark_check, provider_check, secret_report)
    report = {
        "status": status,
        "path_check": path_check,
        "git_check": git_check,
        "env_check": env_check,
        "gpu_check": gpu_check,
        "model_check": model_check,
        "benchmark_check": benchmark_check,
        "provider_check": provider_check,
        "secret_scan_report": secret_report,
    }
    (output_dir / "preflight_summary.md").write_text("\n".join(_summary_lines(report)) + "\n", encoding="utf-8")
    return report
