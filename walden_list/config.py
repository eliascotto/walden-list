"""Configuration loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != 1:
        raise ValueError("configuration schema_version must be 1")
    sources = config.get("sources")
    categories = config.get("categories")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("configuration must define sources")
    if not isinstance(categories, list) or not categories:
        raise ValueError("configuration must define categories")

    for source_id, source in sources.items():
        if not ID_RE.fullmatch(source_id):
            raise ValueError(f"invalid source id: {source_id}")
        for required in ("repository", "ref", "homepage", "license"):
            if not source.get(required):
                raise ValueError(f"source {source_id} is missing {required}")

    seen: set[str] = set()
    families: dict[str, int] = {}
    for category in categories:
        category_id = category.get("id", "")
        if not ID_RE.fullmatch(category_id) or category_id in seen:
            raise ValueError(f"invalid or duplicate category id: {category_id}")
        seen.add(category_id)
        family = category.get("family", category_id)
        if not ID_RE.fullmatch(family):
            raise ValueError(f"invalid family for {category_id}: {family}")
        if category.get("default_variant"):
            families[family] = families.get(family, 0) + 1
        if category.get("strategy", "union") not in {"union", "intersection"}:
            raise ValueError(f"invalid strategy for {category_id}")
        if category.get("variant", "standard") not in {"standard", "extended"}:
            raise ValueError(f"invalid variant for {category_id}")
        inputs = category.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            raise ValueError(f"category {category_id} must have inputs")
        for item in [*inputs, *category.get("excludes", [])]:
            is_project_input = bool(item.get("project_path"))
            has_source = bool(item.get("source"))
            if is_project_input == has_source:
                raise ValueError(
                    f"input in {category_id} needs either source or project_path"
                )
            if is_project_input:
                if item.get("path") or item.get("path_from_json"):
                    raise ValueError(f"project input in {category_id} has extra selectors")
            else:
                if item.get("source") not in sources:
                    raise ValueError(f"unknown source in category {category_id}")
                selectors = [key for key in ("path", "path_from_json") if item.get(key)]
                if len(selectors) != 1:
                    raise ValueError(f"input in {category_id} needs exactly one path selector")
                if item.get("path_from_json") and not item.get("json_key"):
                    raise ValueError(f"dynamic input in {category_id} needs json_key")
            if item.get("format", "auto") not in {"auto", "hosts", "domains"}:
                raise ValueError(f"invalid input format in {category_id}")

    duplicated_defaults = [family for family, count in families.items() if count > 1]
    if duplicated_defaults:
        raise ValueError(f"families have multiple default variants: {duplicated_defaults}")
