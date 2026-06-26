from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, Sequence

SECRET_PATTERNS = [
    ("api_key_like", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("token_like", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{24,}")),
]

EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "models",
    ".cache",
    "wandb",
    "__pycache__",
    ".pytest_cache",
}

EXCLUDED_PARTS = {
    "raw_tensors",
    "attention_full",
    "hidden_states_full",
    "kv_cache_full",
    "browser_trace",
    "large_artifacts",
}

TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".conf",
    ".env",
    ".example",
    ".gitignore",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def _is_excluded(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & EXCLUDED_DIR_NAMES) or bool(parts & EXCLUDED_PARTS)


def _iter_files(paths: Iterable[Path]) -> Iterable[Path]:
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists() or _is_excluded(path):
            continue
        if path.is_file():
            if path.suffix in TEXT_SUFFIXES or path.name in {".env.example", ".gitignore", "AGENTS.md"}:
                yield path
            continue
        for child in path.rglob("*"):
            if child.is_file() and not _is_excluded(child):
                if child.suffix in TEXT_SUFFIXES or child.name in {".env.example", ".gitignore", "AGENTS.md"}:
                    yield child


def _redact(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def _scan_line(path: Path, line_number: int, line: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    if "<set-in-env>" in line or "<optional-set-in-env>" in line:
        return findings
    for pattern_type, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(line):
            findings.append(
                {
                    "path": str(path),
                    "line": line_number,
                    "pattern_type": pattern_type,
                    "redacted_preview": _redact(match.group(0)),
                    "action": "remove_and_rotate",
                }
            )
    return findings


def scan_paths(paths: Sequence[str | Path]) -> dict[str, object]:
    findings: list[dict[str, object]] = []
    for file_path in sorted(_iter_files(Path(p) for p in paths), key=lambda p: str(p)):
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            findings.extend(_scan_line(file_path, line_number, line))
    return {"status": "failed" if findings else "passed", "findings": findings}


def write_report(report: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan text files for key-like secrets.")
    parser.add_argument("--paths", nargs="+", required=True, help="Files or directories to scan.")
    parser.add_argument("--output", default=None, help="Optional JSON report path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = scan_paths([Path(path) for path in args.paths])
    if args.output:
        write_report(report, Path(args.output))
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
