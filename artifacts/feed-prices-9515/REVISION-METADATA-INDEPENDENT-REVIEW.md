# #9515 row-revision metadata corrective source review PASS

Reviewer: Codex deep_live_delivery_review. Two source/test files plus API contract delta over 9f864f7c69 inspected and bound by accompanying SHA-256 records. No gates or production checks duplicated; author reports 28 tests passing.

The additive outcome_revision_at / per-row price_revision_at names and outcome_clock_kind=row_revision identify the actual loaded last_updated values used for ordering. Existing in-flight outcome_observed_at and per-row price_observed_at remain byte-equivalent deprecated ordering aliases, so consumer ordering does not change underneath them. They do not claim a new price observation; rank/volume/settlement can advance the same row clock. Full off-top vector and microsecond/null behavior remain unchanged.

The route leaves the pre-existing card-level price_observed_at untouched. New guard preserves a seven-hour-old card quote-age stamp while row revision is now, preventing false just-updated age. Exact market/group identity, dispositions, result serialization, route bounds and rate limits are unchanged.

Source PASS only. This does not make a committed row revision evidence of a quote change, strict delivery timing or rendered freshness. Native/web consumers and documentation must retain that distinction; CI, Integrator composition/release and representative held-page proof remain separate gates.
