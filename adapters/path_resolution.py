from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


_ENV_TEMPLATE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class ResolvedPath:
    raw_value: str
    path: Path | None
    missing_env_var: str | None = None


def resolve_env_path(value: str | None) -> ResolvedPath:
    if value in {None, ""}:
        return ResolvedPath(raw_value="", path=None)
    raw_value = str(value)
    missing: str | None = None

    def replace(match: re.Match[str]) -> str:
        nonlocal missing
        env_name = match.group(1)
        env_value = os.environ.get(env_name)
        if env_value is None:
            missing = env_name
            return match.group(0)
        return env_value

    resolved = _ENV_TEMPLATE.sub(replace, raw_value)
    if missing is not None:
        return ResolvedPath(raw_value=raw_value, path=None, missing_env_var=missing)
    return ResolvedPath(raw_value=raw_value, path=Path(resolved))
