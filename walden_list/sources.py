"""Resolve upstream source repositories and immutable provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Any


@dataclass(frozen=True)
class ResolvedSource:
    source_id: str
    root: Path
    commit: str
    committed_at: str
    config: dict[str, Any]


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True
    )
    return result.stdout.strip()


def _provenance(root: Path) -> tuple[str, str]:
    try:
        commit = _git("rev-parse", "HEAD", cwd=root)
        epoch = int(_git("show", "-s", "--format=%ct", "HEAD", cwd=root))
    except (subprocess.CalledProcessError, ValueError):
        return "local-unversioned", "1970-01-01T00:00:00Z"
    timestamp = datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")
    return commit, timestamp


class SourceResolver:
    def __init__(self, sources: dict[str, dict[str, Any]], overrides: dict[str, Path]):
        self.sources = sources
        self.overrides = overrides
        self._temporary = TemporaryDirectory(prefix="walden-list-sources-")
        self._resolved: dict[str, ResolvedSource] = {}

    def close(self) -> None:
        self._temporary.cleanup()

    def __enter__(self) -> SourceResolver:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def resolve(self, source_id: str) -> ResolvedSource:
        if source_id in self._resolved:
            return self._resolved[source_id]
        source = self.sources[source_id]
        if source_id in self.overrides:
            root = self.overrides[source_id].expanduser().resolve()
            if not root.is_dir():
                raise ValueError(f"source override is not a directory: {root}")
        else:
            root = Path(self._temporary.name) / source_id
            _git(
                "clone",
                "--depth",
                "1",
                "--branch",
                source["ref"],
                source["repository"],
                str(root),
            )
        commit, committed_at = _provenance(root)
        resolved = ResolvedSource(source_id, root, commit, committed_at, source)
        self._resolved[source_id] = resolved
        return resolved


def safe_source_path(root: Path, relative: str) -> Path:
    # On Mac: /var is a symlink to /private/var so need to resolve root before comparing
    root = root.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"source path escapes repository: {relative}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path
