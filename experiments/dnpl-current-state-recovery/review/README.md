# Dated independent receipts, not current application certification

The receipts in the three subdirectories were written for separate frozen packets before this consolidation. Their file hashes and relative paths describe those packets. A relative `source/...` reference in a receipt must NOT be read as provenance for this checkout: the current ignored `source` alias resolves to b2b92fe86467d0accdb02f7b765ada020b594aec, whereas the earlier client/atomic packet used a43949050b966b8009bddd5dda1afd65ddf1f9f6. Producer receipts used two saved b2b92fe modules over the older dependency tree.

Pinned source trees:
- https://github.com/alexander-bain/bainluck/tree/a43949050b966b8009bddd5dda1afd65ddf1f9f6
- https://github.com/alexander-bain/bainluck/tree/b2b92fe86467d0accdb02f7b765ada020b594aec

Some original packet paths, logs and historical predecessor implementations are deliberately omitted. Unsafe old client variants are not copyable here. The paired numeric regression explicitly reads its sole old implementation from text-only negative-control evidence. Do not use historical `RUN` paths or build-permission statements as current status. Current commands are in the root RUN.md; fresh selected-suite results and repository gates are in GATES.md. Tests here are path-adapted where necessary, and PROVENANCE.json records differences from frozen inputs.
