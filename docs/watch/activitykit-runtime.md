# Suspended-phone score and Probability updates (#10542)

Pillars: TRUTH / FORMATTING. Ship: the selected game's canonical score and
Probability continue updating, with authoritative end delivery, while the iPhone
is suspended.

The existing account-owned registration API is already included by `main.py`
and `routes/__init__.py`; this change does not mount a second router. The new
`app.tasks.deliver_activitykit_updates` beat runs every 30 seconds on realtime,
expires after 25 seconds if not started, and is a no-op by default. It has no
automatic Celery retries. A PostgreSQL transaction advisory lock serializes a
bounded page; a competing beat returns busy before reads or delivery. Cursor
state uses the existing `durable_state_snapshots` table, never Redis. A checksum
or read failure refuses dispatch. Completed and partially attempted pages bank
their continuation under that same lock; only an actual commit counts as saved.
A crash may revisit a page: existing per-registration leases and token/epoch
fences remain authoritative, and delivery is at-least-once, not exactly-once.

Each enabled page attempts at most 20 registrations, 100 expired-credential
cleanups, 30 seconds per item and 120 seconds for the page. Caller setup and
checkpoint have 15 seconds of additional budget; Celery soft/hard limits are
150/180 seconds. A game is captured once per page with the existing serialized
canonical reader. The original score/probability observation times are passed
through unchanged. Retries remain in the existing delivery state machine with
three finite delays of 30, 60 and 120 seconds. Partial/failing results fail the
Celery task with fixed text; no credential, registration ID or exception body is
returned in the task summary.

Activation requires all of these dedicated settings, configured explicitly for
the approved named candidate:

- `ACTIVITYKIT_RUNTIME_ENABLED=true` (every other value disables the task).
- `ACTIVITYKIT_APNS_BUNDLE_ID`: exact application bundle identity.
- `ACTIVITYKIT_APNS_ENVIRONMENT`: `sandbox` or `production`.
- `ACTIVITYKIT_APNS_TEAM_ID` and `ACTIVITYKIT_APNS_KEY_ID`: explicit Apple identities.
- `ACTIVITYKIT_APNS_PRIVATE_KEY`: approved P-256 private key as PEM.

No credentials are looked up at import time, discovered from files/keychain or
borrowed from Firebase. Enabled runs validate settings before opening the DB or
transport, sign ES256 provider JWTs, and close their owned resources. Disabling
stops new runs; an in-flight page can finish within its existing deadline. User
revocation uses the existing atomic registration/token fencing path.

This source does not configure any deployed environment or send a real push.
Local unit and disposable PostgreSQL gates are separate from hosted integration,
configured APNs acceptance and named-candidate device receipt (#10543). An APNs
HTTP 200 alone never proves that the Watch or phone displayed the update.
