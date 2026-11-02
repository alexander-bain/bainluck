# Tier-B review updates

Pillar: TRUTH. Ship: a Tier-B merge waits for current-head approval from another person, including after a review is changed or dismissed.

The policy runs trusted default-branch code on PR metadata events, signed review dispatches and a five-minute reconciliation schedule. It aggregates every open PR sharing a source SHA before writing the required `Tier-B approval` check. An unlabeled sibling can never publish success over an unapproved Tier-B PR. Reviews are fetched again per candidate and heads/labels are rechecked before publishing.

GitHub review events have no `pull_request_target` trigger. A `pull_request_review` workflow would obtain its definition from the PR merge ref, so this implementation uses `POST /api/release-loop/tier-b-review`: the backend validates GitHub's `X-Hub-Signature-256` over the raw bounded body with `TIER_B_REVIEW_WEBHOOK_SECRET`, accepts only this repository's submitted/edited/dismissed reviews, and sends only the PR number in a `tier-b-review` repository dispatch using `RELEASE_DISPATCH_TOKEN`. The required workflow then executes its definition and policy from the default branch. Review text is never forwarded, and errors never expose tokens.

## Setup after the merge hold is lifted

1. Merge the reviewed receiver and policy when Alex has said `master is current`. Configure `TIER_B_REVIEW_WEBHOOK_SECRET` and `RELEASE_DISPATCH_TOKEN` on the backend through the shared release-loop setup; the dispatch token needs permission to dispatch this repository's workflows.
2. Preview `python3 tools/release/tier_b_webhook_setup.py`. It does not read or write repository settings.
3. Only after Alex says `branch protection on`, run `python3 tools/release/tier_b_webhook_setup.py --apply --confirmation 'branch protection on'` with the webhook secret in the environment. The tool verifies a signed ping against the deployed receiver before creating/updating a paginated, deduplicated subscription. It never prints a secret.
4. Verify an actual submitted/dismissed review dispatch updates the exact head check. Until the webhook is installed, polling remains fallback and is subject to GitHub scheduling delays. The shared fast-lane activation must not arm before the required subscriptions are verified.

No setup command ran in this offline session. Local verification covers self/stale/dismissed approval, the shared-SHA overwrite defect, unsigned/tampered review requests, all three review actions, repository rejection and safe dispatch shape. Hosted CI and live webhook receipt remain required before activation.
