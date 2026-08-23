"""Deterministic category builder and output validator."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .normalize import ParsedDomains, parse_domain_file, validate_output_domains
from .sources import ResolvedSource, SourceResolver, safe_source_path


class BuildError(RuntimeError):
    pass


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_value(document: Any, dotted_key: str) -> Any:
    value = document
    for component in dotted_key.split("."):
        if not isinstance(value, dict) or component not in value:
            raise BuildError(f"JSON key not found: {dotted_key}")
        value = value[component]
    return value


def _item_path(source: ResolvedSource, item: dict[str, Any]) -> tuple[Path, str]:
    if "path" in item:
        relative = item["path"]
    else:
        metadata_path = safe_source_path(source.root, item["path_from_json"])
        with metadata_path.open("r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        relative = _json_value(metadata, item["json_key"])
        if not isinstance(relative, str):
            raise BuildError(f"dynamic path is not a string: {item['json_key']}")
    return safe_source_path(source.root, relative), relative


def _safe_project_path(config_root: Path, relative: str) -> Path:
    root = config_root.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise BuildError(f"project path escapes project: {relative}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _parse_item(
    resolver: SourceResolver, item: dict[str, Any], config_root: Path
) -> tuple[ParsedDomains, dict[str, Any]]:
    if "project_path" in item:
        relative = item["project_path"]
        path = _safe_project_path(config_root, relative)
        parsed = parse_domain_file(path, item.get("format", "auto"))
        details = {
            "source": "local-project",
            "path": relative,
            "format": item.get("format", "auto"),
            "sha256": sha256_bytes(path.read_bytes()),
            **asdict(parsed.stats),
        }
        if parsed.rejected_samples:
            details["rejected_samples"] = list(parsed.rejected_samples)
        return parsed, details

    source = resolver.resolve(item["source"])
    path, relative = _item_path(source, item)
    parsed = parse_domain_file(path, item.get("format", "auto"))
    details = {
        "source": source.source_id,
        "path": relative,
        "format": item.get("format", "auto"),
        "sha256": sha256_bytes(path.read_bytes()),
        **asdict(parsed.stats),
    }
    if parsed.rejected_samples:
        details["rejected_samples"] = list(parsed.rejected_samples)
    return parsed, details


def _parse_curation(config_root: Path, relative: str | None) -> ParsedDomains | None:
    if not relative:
        return None
    path = _safe_project_path(config_root, relative)
    return parse_domain_file(path, "domains")


def _domain_content(domains: set[str]) -> bytes:
    return ("\n".join(sorted(domains)) + "\n").encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_previous_counts(manifest_path: Path) -> dict[str, int]:
    if not manifest_path.is_file():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            category_id: int(category["domains"])
            for category_id, category in manifest.get("categories", {}).items()
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {}


def _check_size_changes(
    previous: dict[str, int], current: dict[str, int], threshold: float
) -> None:
    surprising: list[str] = []
    for category_id, current_count in current.items():
        old_count = previous.get(category_id)
        if not old_count:
            continue
        percent = abs(current_count - old_count) / old_count * 100
        if percent > threshold:
            surprising.append(
                f"{category_id}: {old_count:,} -> {current_count:,} ({percent:.1f}%)"
            )
    if surprising:
        joined = "; ".join(surprising)
        raise BuildError(
            f"category size change exceeds {threshold:g}%: {joined}. "
            "Review the upstream change and rebuild with --allow-large-change."
        )


def build_lists(
    config: dict[str, Any],
    config_root: Path,
    output_root: Path,
    source_overrides: dict[str, Path],
    allow_large_change: bool = False,
) -> dict[str, Any]:
    settings = config.get("settings", {})
    manifest_path = output_root / "manifest.json"
    previous_counts = _read_previous_counts(manifest_path)
    rendered: dict[str, bytes] = {}
    category_manifest: dict[str, Any] = {}
    used_sources: dict[str, ResolvedSource] = {}

    with SourceResolver(config["sources"], source_overrides) as resolver:
        for category in config["categories"]:
            parsed_inputs: list[ParsedDomains] = []
            input_details: list[dict[str, Any]] = []
            for item in category["inputs"]:
                parsed, details = _parse_item(resolver, item, config_root)
                parsed_inputs.append(parsed)
                input_details.append(details)
                if "source" in item:
                    source = resolver.resolve(item["source"])
                    used_sources[source.source_id] = source

            if category.get("strategy", "union") == "intersection":
                domains = set(parsed_inputs[0].domains)
                for parsed in parsed_inputs[1:]:
                    domains.intersection_update(parsed.domains)
            else:
                domains = set().union(*(parsed.domains for parsed in parsed_inputs))

            exclude_details: list[dict[str, Any]] = []
            for item in category.get("excludes", []):
                parsed, details = _parse_item(resolver, item, config_root)
                domains.difference_update(parsed.domains)
                exclude_details.append(details)
                if "source" in item:
                    source = resolver.resolve(item["source"])
                    used_sources[source.source_id] = source

            curation = category.get("curation", {})
            additions = _parse_curation(config_root, curation.get("additions"))
            allowlist = _parse_curation(config_root, curation.get("allowlist"))
            if additions:
                domains.update(additions.domains)
            if allowlist:
                domains.difference_update(allowlist.domains)
            if not domains:
                raise BuildError(f"category produced no domains: {category['id']}")

            content = _domain_content(domains)
            filename = f"categories/{category['id']}.txt"
            rendered[filename] = content
            entry = {
                "name": category["name"],
                "description": category["description"],
                "family": category.get("family", category["id"]),
                "variant": category.get("variant", "standard"),
                "default_variant": bool(category.get("default_variant", False)),
                "included_by_default": False,
                "recommended": bool(category.get("recommended", False)),
                "confidence": category.get("confidence", "medium"),
                "license": category.get("license", "LicenseRef-Multiple"),
                "path": filename,
                "format": "domains-v1",
                "domains": len(domains),
                "bytes": len(content),
                "sha256": sha256_bytes(content),
                "strategy": category.get("strategy", "union"),
                "inputs": input_details,
                "excludes": exclude_details,
            }
            if category.get("warning"):
                entry["warning"] = category["warning"]
            if additions or allowlist:
                entry["curation"] = {
                    "additions": len(additions.domains) if additions else 0,
                    "allowlist": len(allowlist.domains) if allowlist else 0,
                }
            category_manifest[category["id"]] = entry

        source_manifest = {
            source_id: {
                "homepage": source.config["homepage"],
                "repository": source.config["repository"],
                "ref": source.config["ref"],
                "commit": source.commit,
                "committed_at": source.committed_at,
                "license": source.config["license"],
            }
            for source_id, source in sorted(used_sources.items())
        }

    counts = {
        category_id: entry["domains"] for category_id, entry in category_manifest.items()
    }
    if not allow_large_change:
        _check_size_changes(
            previous_counts,
            counts,
            float(settings.get("max_category_change_percent", 35)),
        )

    timestamps = [source["committed_at"] for source in source_manifest.values()]
    generated_at = (
        max(
            timestamps,
            key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
        )
        if timestamps
        else "1970-01-01T00:00:00Z"
    )
    manifest = {
        "schema_version": 1,
        "format": "walden-domain-registry-v1",
        "generated_at": generated_at,
        "reproducible": True,
        "categories_are_opt_in": True,
        "categories": dict(sorted(category_manifest.items())),
        "sources": source_manifest,
    }

    for relative, content in sorted(rendered.items()):
        _atomic_write(output_root / relative, content)

    checksums = "".join(
        f"{sha256_bytes(content)}  {relative}\n"
        for relative, content in sorted(rendered.items())
    ).encode("utf-8")
    _atomic_write(output_root / "checksums.txt", checksums)
    manifest_content = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_write(manifest_path, manifest_content)
    validate_distribution(output_root)
    return manifest


def validate_distribution(output_root: Path) -> dict[str, Any]:
    manifest_path = output_root / "manifest.json"
    if not manifest_path.is_file():
        raise BuildError(f"missing manifest: {manifest_path}")
    manifest_bytes = manifest_path.read_bytes()
    if not manifest_bytes.endswith(b"\n"):
        raise BuildError("manifest must end with a newline")
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema_version") != 1:
        raise BuildError("unsupported manifest schema")

    expected_checksums: dict[str, str] = {}
    for category_id, category in sorted(manifest["categories"].items()):
        relative = category["path"]
        if relative != f"categories/{category_id}.txt":
            raise BuildError(f"unexpected category path: {relative}")
        path = output_root / relative
        content = path.read_bytes()
        if not content.endswith(b"\n"):
            raise BuildError(f"category does not end with a newline: {category_id}")
        with path.open("r", encoding="utf-8") as handle:
            domains = validate_output_domains(handle)
        digest = sha256_bytes(content)
        if len(domains) != category["domains"]:
            raise BuildError(f"domain count mismatch: {category_id}")
        if len(content) != category["bytes"]:
            raise BuildError(f"byte count mismatch: {category_id}")
        if digest != category["sha256"]:
            raise BuildError(f"checksum mismatch: {category_id}")
        expected_checksums[relative] = f"{digest}  {relative}\n"

    actual_checksums = (output_root / "checksums.txt").read_text(encoding="utf-8")
    expected_checksum_content = "".join(
        expected_checksums[relative] for relative in sorted(expected_checksums)
    )
    if actual_checksums != expected_checksum_content:
        raise BuildError("checksums.txt does not match the manifest")
    return manifest
