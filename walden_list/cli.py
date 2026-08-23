"""Command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .build import BuildError, build_lists, validate_distribution
from .config import load_config


def _source_overrides(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"source root must be SOURCE=PATH: {value}")
        source_id, raw_path = value.split("=", 1)
        if not source_id or not raw_path or source_id in result:
            raise ValueError(f"invalid or duplicate source root: {value}")
        result[source_id] = Path(raw_path)
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="walden-list", description="Build categorized domain lists for Walden"
    )
    result.add_argument(
        "--config", type=Path, default=Path("sources.json"), help="configuration file"
    )
    subcommands = result.add_subparsers(dest="command", required=True)

    build = subcommands.add_parser("build", help="build and validate all category files")
    build.add_argument("--output", type=Path, help="override the configured output directory")
    build.add_argument(
        "--source-root",
        action="append",
        default=[],
        metavar="SOURCE=PATH",
        help="use a local checkout instead of cloning a source; repeatable",
    )
    build.add_argument(
        "--allow-large-change",
        action="store_true",
        help="accept category count changes beyond the configured safety threshold",
    )

    validate = subcommands.add_parser("validate", help="validate an existing distribution")
    validate.add_argument("--output", type=Path, help="override the configured output directory")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config_path = args.config.resolve()
        config = load_config(config_path)
        output = (args.output or Path(config.get("output", "dist/v1"))).resolve()
        if args.command == "build":
            manifest = build_lists(
                config,
                config_path.parent,
                output,
                _source_overrides(args.source_root),
                args.allow_large_change,
            )
            print(f"Built {len(manifest['categories'])} categories in {output}")
            for category_id, category in manifest["categories"].items():
                print(f"  {category_id}: {category['domains']:,} domains")
        else:
            manifest = validate_distribution(output)
            print(f"Validated {len(manifest['categories'])} categories in {output}")
        return 0
    except (BuildError, FileNotFoundError, ValueError, OSError) as error:
        print(f"walden-list: {error}", file=sys.stderr)
        return 1

