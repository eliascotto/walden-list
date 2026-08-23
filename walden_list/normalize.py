"""Strict extraction and normalization of hostname blocklist entries."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from pathlib import Path
import re
from typing import Iterable


LABEL_RE = re.compile(r"^[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?$")
SPECIAL_NAMES = {
    "broadcasthost",
    "ip6-allhosts",
    "ip6-allnodes",
    "ip6-allrouters",
    "ip6-localhost",
    "ip6-loopback",
    "ip6-mcastprefix",
    "ip6-localnet",
    "local",
    "localhost",
    "localhost.localdomain",
}


@dataclass(frozen=True)
class ParseStats:
    lines: int
    candidates: int
    accepted: int
    rejected: int


@dataclass(frozen=True)
class ParsedDomains:
    domains: frozenset[str]
    stats: ParseStats
    rejected_samples: tuple[str, ...]


def normalize_domain(value: str) -> str | None:
    """Return a canonical ASCII hostname, or None for an invalid value."""
    value = value.strip().lstrip("\ufeff").lower().rstrip(".")
    if not value or value in SPECIAL_NAMES:
        return None
    if "://" in value or "/" in value or "@" in value or ":" in value:
        return None
    try:
        ipaddress.ip_address(value)
        return None
    except ValueError:
        pass

    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        return None

    if len(value) > 253 or "." not in value:
        return None
    labels = value.split(".")
    if any(not label or len(label) > 63 or not LABEL_RE.fullmatch(label) for label in labels):
        return None
    return value


def _candidate_tokens(line: str, input_format: str) -> list[str]:
    line = line.strip().lstrip("\ufeff")
    if not line or line.startswith(("#", "!")):
        return []
    line = line.split("#", 1)[0].strip()
    if not line:
        return []
    fields = line.split()

    if input_format == "domains":
        return [fields[0]]
    if input_format not in {"hosts", "auto"}:
        raise ValueError(f"unsupported input format: {input_format}")

    first_is_ip = False
    try:
        ipaddress.ip_address(fields[0].split("%", 1)[0])
        first_is_ip = True
    except ValueError:
        pass

    if input_format == "hosts":
        return fields[1:] if first_is_ip else []
    return fields[1:] if first_is_ip else [fields[0]]


def parse_domain_lines(lines: Iterable[str], input_format: str = "auto") -> ParsedDomains:
    domains: set[str] = set()
    line_count = candidate_count = rejected = 0
    rejected_samples: list[str] = []

    for raw_line in lines:
        line_count += 1
        for candidate in _candidate_tokens(raw_line, input_format):
            candidate_count += 1
            normalized = normalize_domain(candidate)
            if normalized is None:
                rejected += 1
                if len(rejected_samples) < 10:
                    rejected_samples.append(candidate)
                continue
            domains.add(normalized)

    return ParsedDomains(
        domains=frozenset(domains),
        stats=ParseStats(
            lines=line_count,
            candidates=candidate_count,
            accepted=len(domains),
            rejected=rejected,
        ),
        rejected_samples=tuple(rejected_samples),
    )


def parse_domain_file(path: Path, input_format: str = "auto") -> ParsedDomains:
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        return parse_domain_lines(handle, input_format)


def validate_output_domains(lines: Iterable[str]) -> list[str]:
    """Validate a generated domain-only file and return its domains."""
    raw = [line.rstrip("\n") for line in lines]
    if any(not line or line != line.strip() for line in raw):
        raise ValueError("output contains an empty or whitespace-padded line")
    normalized = [normalize_domain(line) for line in raw]
    if any(value is None for value in normalized):
        raise ValueError("output contains an invalid domain")
    domains = [value for value in normalized if value is not None]
    if domains != sorted(set(domains)):
        raise ValueError("output is not sorted and unique")
    return domains

