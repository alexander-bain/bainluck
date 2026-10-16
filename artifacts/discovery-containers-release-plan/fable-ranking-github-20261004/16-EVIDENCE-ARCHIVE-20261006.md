# Complete Fable evidence archive

The supplied errata plus complete `fable-evidence-20261006/` directory are retained as an unpublished draft GitHub release asset, separate from application releases. Do not publish this archive as a product release.

- Draft archive: https://github.com/alexander-bain/bainluck/releases/tag/untagged-98b4aa270ac2146ec6a8
- Release ID: `404954256`; intended archive tag: `evidence-fable-comparisons-20261006`.
- Asset: `fable-comparison-evidence-20261006.tar.gz`, ID `616103555`, 29,085,438 bytes.
- SHA-256: `9c1a30f648afd6b5e7fc2c38cfeec8880d7323617090bc2f32d8f7ff8c9cd9ba`.
- Companion `SHA256SUMS`: asset ID `616103538`.
- Local archive: `/Users/bain/.codex-personal/artifact-archives/fable-comparisons-20261006/fable-comparison-evidence-20261006.tar.gz` (checksum file alongside).

The archive's local hash matches GitHub's uploaded asset digest and byte count. All 38 original manifest entries were checked against the supplied files and again inside the tarball. The original manifest is preserved unchanged in Git. Its four `.gz` entries are intentionally stored only in the complete archive; remaining entries are in this PR.

Draft assets require repository write access and authenticated GitHub access. To recover by stable asset ID (even if the draft URL changes):

```sh
gh api repos/alexander-bain/bainluck/releases/assets/616103555   -H 'Accept: application/octet-stream' > fable-comparison-evidence-20261006.tar.gz
gh api repos/alexander-bain/bainluck/releases/assets/616103538   -H 'Accept: application/octet-stream' > SHA256SUMS
shasum -a 256 -c SHA256SUMS
tar -tzf fable-comparison-evidence-20261006.tar.gz
```

The supplied originals remain in Alex's checkout. No originals were moved or deleted. A credential-pattern skim's `sk-` matches in the compressed Polymarket text were inspected: public slug/prose fragments (Musk, MetaMask, risk and team symbols), not credentials. No broad secret-scanner exclusion was added.
