# Fable feed-trial evidence preserved

PILLARS: DISCOVER / TRUTH. Ship supported: evaluate the existing #5105 feed proposal using retained prototype evidence, without treating a one-person prototype as production validation.

Alex supplied `15-FEED-TRIAL-AND-EVIDENCE.md`; preserved byte-for-byte as `17-FABLE-FEED-TRIAL-AND-EVIDENCE.md` to avoid the Root file 15 collision. The Mac original was renamed to the same 17 name; content is unchanged. Root's file 15 retains its name. Fable's claims remain attributed source material, not independent acceptance.

All 35 original feed manifest entries were checked for size/hash locally and hash again inside the archive. The complete 36-file bundle (including its original manifest) and renamed write-up are retained together in the existing unpublished draft evidence release 404954256. No product release was published.

- Asset `fable-feed-trial-evidence-20261006.tar.gz`, ID 616247834, 14,756,044 bytes.
- SHA256 `80c7975ba94ca057ca0f0e0527eb2ba5fa181474b4e90101b13fdc89322a2ac7`, matching GitHub uploaded digest.
- Companion `FEED-SHA256SUMS`, asset 616247836.
- Draft archive: https://github.com/alexander-bain/bainluck/releases/tag/untagged-98b4aa270ac2146ec6a8
- Local archive: /Users/bain/.codex-personal/artifact-archives/fable-feed-trial-20261006/fable-feed-trial-evidence-20261006.tar.gz

The manifest is also preserved in this PR. Full data/code/raw compressed observations are in the archive; relative evidence references in the write-up resolve after extracting it. The sole credential-pattern match was a public news-description link containing collapse-risk, not a credential. No scanner exclusion was added.

Recovery requires authenticated repository write access for draft assets:

```sh
gh api repos/alexander-bain/bainluck/releases/assets/616247834 -H 'Accept: application/octet-stream' > fable-feed-trial-evidence-20261006.tar.gz
gh api repos/alexander-bain/bainluck/releases/assets/616247836 -H 'Accept: application/octet-stream' > FEED-SHA256SUMS
shasum -a 256 -c FEED-SHA256SUMS
tar -tzf fable-feed-trial-evidence-20261006.tar.gz
```

Alex's separate #10626 addition is recorded in the issue body: once a day of records exists, report valid 20–28h same-composition pair coverage over all current published question/option identities. The exact provenance contract, selected scope, Discover owner, 4–7 day estimate and activation dependencies are unchanged. Coverage will inform a later decision; full-inventory capture is not authorized.
