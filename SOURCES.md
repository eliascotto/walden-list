# Sources and provenance

Every build records exact upstream Git commit IDs, input paths, input hashes,
accepted counts, and output hashes in `dist/v1/manifest.json`.

## StevenBlack/hosts

- Project: https://github.com/StevenBlack/hosts
- Role: advertising/malware base list and the dedicated fake-news, gambling,
  social-media, and pornography category lists.
- Repository license: MIT. The base aggregation contains upstream sources with
  additional licenses and attribution requirements; see the project's source
  table before redistributing `ads-malware.txt`.

Only the `*-only` category variants are used. This prevents advertising and
malware domains from being silently included in content categories.

## Bon-Appetit/porn-domains

- Project: https://github.com/Bon-Appetit/porn-domains
- Role: second adult-content aggregation and adult-domain allowlist.
- License: CC BY-SA 4.0.

Required attribution: [Bon-Appetit/porn-domains](https://github.com/Bon-Appetit/porn-domains)
is licensed under [CC BY-SA 4.0](https://github.com/Bon-Appetit/porn-domains/blob/main/LICENSE).

The standard pornography output is an intersection of the two aggregations.
The extended output is their union. Both subtract the Bon-Appetit allowlist and
the corresponding local curation allowlist.

