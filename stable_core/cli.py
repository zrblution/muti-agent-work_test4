from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from stable_core.validation.preflight import run_preflight


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stable_core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Run Phase 0 preflight checks.")
    preflight.add_argument("--dry-run", action="store_true", help="Record missing setup without running remote jobs.")
    preflight.add_argument("--output-dir", default="runs/preflight", help="Directory for preflight artifacts.")

    subparsers.add_parser("doctor", help="Print machine-readable preflight status.")
    return parser


def _exit_code(status: str) -> int:
    return 1 if status == "failed" else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "preflight":
        report = run_preflight(output_dir=Path(args.output_dir), dry_run=args.dry_run)
        print(json.dumps({"command": "preflight", "status": report["status"]}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    if args.command == "doctor":
        report = run_preflight(output_dir=Path("runs/preflight"), dry_run=True)
        print(json.dumps({"command": "doctor", "preflight_status": report["status"]}, ensure_ascii=False))
        return _exit_code(str(report["status"]))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
