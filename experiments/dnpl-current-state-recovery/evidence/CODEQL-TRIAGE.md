# Standalone driver correction after hosted CodeQL review

Published parent: `4ea72a1cde247c6f5b914323b761bdefddafad4a`.
Hosted check: https://github.com/alexander-bain/bainluck/runs/119357777363

That head reports49 findings: one constructor error and48 notes. The constructor error is a real standalone fixture bug. Importing producer_driver directly can select the dependency checkout's unmodified PreviewRegistry, which does not accept wall_clock. Combined tests previously initialized the candidate first and hid this import-order dependency.

The correction explicitly calls current_source.load(candidate=True) before dependent fixture imports. A coherent (variant, modules) cache preserves same-variant identity and refuses mixing variants in one process. Two fresh-process regressions exercise direct startup without alias preload, quiet retries, final commit, stable original lease, and completion of an asynchronous callback. Network connections are forbidden by the fixtures.

Eleven small fixture/client notes are addressed by removing unused bindings/imports, using the coherent cache, and recording a disposable-instance cleanup warning. The preview clock state and timer updates remain. The callback's await remains and is explicitly tested; removing it would change behavior.

Thirty-five notes in byte-pinned reference source and one inherited candidate-registry note are preserved. No owner source, cancellation behavior, scan exclusion or alert dismissal is changed. Local tests cannot establish a new hosted CodeQL outcome.

The earlier uncommitted correction and its local logs were lost when the cloud workspace was replaced. This correction was reconstructed from the published parent and recorded review/test descriptions. Fresh exact-source review and targeted tests were repeated. After clarified permission, the new frontend build and mandatory post-build census passed; RESTORATION.json distinguishes those results from historical receipts. Hosted CodeQL clearance is still not inferred from local checks.
