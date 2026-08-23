# Walden List

Reproducible, categorized domain lists for Walden.

This project does not invent the blocklists. It formats and aggregates upstream
community lists into a stable `domains-v1` format and a manifest Walden can
consume. Upstream repos are fetched at build time and are not vendored.

All categories are opt-in. A `default_variant` is only the normal choice within
a category—it does not mean Walden should enable that category automatically.

## Sources

The domain content comes from these projects. Full provenance, licenses, and
per-build commit IDs are in `SOURCES.md`, `LICENSE-DATA.md`, and the generated
manifest.

| Source | Role |
|---|---|
| [StevenBlack/hosts](https://github.com/StevenBlack/hosts) | Base advertising/malware aggregation and dedicated fake-news, gambling, social-media, and pornography category lists (MIT; the base list also carries upstream source licenses) |
| [Bon-Appetit/porn-domains](https://github.com/Bon-Appetit/porn-domains) | Second adult-content aggregation and allowlist ([CC BY-SA 4.0](https://github.com/Bon-Appetit/porn-domains/blob/main/LICENSE)) |

Only StevenBlack’s `*-only` category variants are used, so advertising and
malware domains are not silently mixed into content categories. Standard
pornography is the intersection of StevenBlack and Bon-Appetit; `porn-extended`
is their union. Both subtract Bon-Appetit’s allowlist and local curation.

## Published contract

Walden needs only one stable URL:

```text
https://raw.githubusercontent.com/OWNER/walden-list/main/dist/v1/manifest.json
```

Paths in the manifest are relative to the manifest, so the generator does not
need to know the final GitHub owner. A client downloads the manifest, selects
category files, verifies their SHA-256 hashes and byte counts, validates the
domains, and caches the verified result.

Generated category files use `domains-v1`:

```text
example.com
media.example.net
xn--bcher-kva.example
```

They contain lowercase ASCII hostnames only, sorted and deduplicated, with one
final newline. There are no comments, IP prefixes, URLs, or metadata lines.

## Categories

| Category | Variant | Selection policy |
|---|---|---|
| `ads-malware` | standard | Broad StevenBlack base aggregation; not advertising-only |
| `fake-news` | standard | Opt-in and cautioned because classification is subjective |
| `gambling` | standard | Dedicated category aggregation |
| `social-media` | standard | Dedicated category aggregation |
| `porn` | standard | Intersection of StevenBlack and Bon-Appetit for higher confidence |
| `porn-extended` | extended | Aggressive union; never the default variant |

The standard pornography list deliberately favors certainty over coverage.
The extended variant is available for users who explicitly want broader
coverage and accept greater false-positive and performance risk.

## Build and update locally

Python 3.10 or newer and Git are the only requirements. Rebuild whenever you
want fresher upstream domains:

```sh
python3 -m walden_list build
python3 -m walden_list validate
```

To build from existing checkouts without network access:

```sh
python3 -m walden_list build \
  --source-root stevenblack=/path/to/StevenBlack-hosts \
  --source-root bon-appetit=/path/to/porn-domains
```

The builder refuses an update when an existing category changes by more than
35 percent. After reviewing a legitimate upstream change, override that guard:

```sh
python3 -m walden_list build --allow-large-change
```

Build timestamps come from upstream Git commits rather than the wall clock.
Given identical source commits and curation files, outputs are byte-for-byte
reproducible. Commit the updated `dist/` files when you publish a new snapshot.

## Add a source or category

Sources and categories are declared in `sources.json`. The generator supports:

- hosts-file, domain-only, and automatically detected input formats;
- multiple inputs combined by `union` or `intersection`;
- dynamically named input files selected through an upstream JSON metadata
  file;
- local project files for fully custom categories;
- upstream exclusion lists;
- local additions and allowlists;
- standard and extended variants grouped into one category family.

For example, a future proxy category can be added without Python changes:

```json
{
  "id": "proxies",
  "family": "proxies",
  "name": "Proxy services",
  "description": "Known public proxy-service domains.",
  "variant": "standard",
  "default_variant": true,
  "recommended": true,
  "confidence": "high",
  "license": "MIT",
  "strategy": "intersection",
  "inputs": [
    {"project_path": "custom/proxies-a.txt", "format": "domains"},
    {"source": "proxy-source-b", "path": "hosts", "format": "hosts"}
  ],
  "curation": {
    "additions": "curation/additions/proxies.txt",
    "allowlist": "curation/allowlists/proxies.txt"
  }
}
```

Add each referenced external source to the top-level `sources` object, create
any `project_path` files, and add the two curation files. Use an intersection
when certainty is more important than coverage, or a union for an explicitly
extended variant.
