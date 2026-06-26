from __future__ import annotations

from pathlib import Path


BENCHMARK_METADATA_SUFFIXES = {".json", ".jsonl", ".tsv", ".csv", ".txt", ".yaml", ".yml"}


def missing_required_files(root: Path, required_files: list[str]) -> list[str]:
    return [name for name in required_files if not (root / name).is_file()]


def discover_benchmark_metadata(
    root: Path,
    *,
    max_files: int = 20,
    max_depth: int = 2,
    max_entries: int = 500,
) -> list[str]:
    matches: list[str] = []
    pending: list[tuple[Path, int]] = [(root, 0)]
    scanned_entries = 0
    while pending and len(matches) < max_files and scanned_entries < max_entries:
        directory, depth = pending.pop(0)
        try:
            children = sorted(directory.iterdir())
        except OSError:
            continue
        for path in children:
            scanned_entries += 1
            if scanned_entries > max_entries or len(matches) >= max_files:
                break
            if path.is_file() and path.suffix.lower() in BENCHMARK_METADATA_SUFFIXES:
                matches.append(str(path.relative_to(root)))
            elif path.is_dir() and depth < max_depth:
                pending.append((path, depth + 1))
    return matches
