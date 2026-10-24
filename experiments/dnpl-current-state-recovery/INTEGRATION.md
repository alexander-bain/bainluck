# Explicit unwired integration boundary

Do not copy the old EventPage from historical archives over current production. This handoff intentionally excludes that page and all route monkeypatch installers. The current base is b2b92fe86467d0accdb02f7b765ada020b594aec; older browser/hook work was based on a43949050b966b8009bddd5dda1afd65ddf1f9f6.

## Client alias contract for isolated tests

The tests use `source` as an ignored symlink to this checkout and `harness/node_modules` for the esbuild dependency. `@/*` resolves to `source/frontend/*`, except `@/lib/blendPreview` and `@/lib/liveStreamController` resolve to the selected `monotonic-candidate` modules. The hook's relative requestLease/currentPreviewProbe/acceptCurrentPreview imports remain together. `PendingHero` wraps the real current EventHeroProbabilityPair. No application config installs these aliases.

An owner integration must pass the hook a `committedAdoption` token only after the page has actually adopted an authoritative singleton revision, including fresh HTTP detail/history adoption. Raw frame receipt is not adoption. The token cancels the one-shot GET and may resolve pending only above the withdrawn preview base and at/above the reader's current known floor. The page must consume `previewRecoveryPending` so neither visible nor accessible probability attributes expose an old number while authority is unknown. This full current-page wiring is not supplied or tested here.

The hook expects a new no-store `/api/events/{id}/preview-current` response and SSE `preview_state` recovery envelope. Neither endpoint nor event is installed by this PR. The envelope needs current event/status coverage, epoch/sequence/revoke/commit floors, fixed chain identity and original expiry, and a freshly calculated remaining duration for this GET. A response must not reset primary EventSource health, reconnect/watchdog clocks, cursor or observation timestamps. Native retry remains 5000 in the prior source-default fixture, not a verified deployed override.

The client's local request start is captured immediately before fetch and cannot be supplied by JSON. Remaining budget is anchored to that start. Older GET generations, terminal/hidden/unmount callbacks, known newer revokes/commits and expired caps must not resurrect authority. Missing/ambiguous owner data is abstention, not an invented tombstone. See `monotonic-review/PROTOCOL.md` for the exact scope.

## Storage / producer composition boundary

The corrected singleton Lua operations are a proposed storage contract, not the existing batch publisher. `retention_input.py` prepares commands without sending them. Never replace the existing one ordered owner-fenced batch EVAL with a loop of singleton EVALs. Snapshot SQL coverage must be freshly ordered and may still race a later unseen DB commit/status transition; WPS revision is not a general status revision.

The producer metadata patch is additive on the saved current registry. Its publisher reference is unchanged. `lease_issued_at_ms` is the current attempt's budget timestamp, not original observation or chain start. A changed probability does not create a new lease. Metadata failure keeps the chain live-only rather than renewing it on retry. The monotonic-to-wall mapping remains a local assumption and does not establish distributed clock alignment.

The standalone `committed` Lua operation models only the preview committed-floor duty. It must not replace the existing committed last-frame retention/publication/recovery path. Producer identities of the form `pending:<counter>` are scoped by event plus the claimed writer epoch. Registry recreation under an unchanged epoch could reuse an identity and is not an allowed producer lifetime; owner integration must preserve that scope or use a stronger identity.
