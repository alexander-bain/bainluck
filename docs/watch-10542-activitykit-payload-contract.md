# W3.2 source slice: a suspended phone can receive the game's reading

PILLARS: TRUTH · FORMATTING.

SHIP: Keep the explicitly selected game's Live Activity updated while the phone
is suspended. This payload builder is the first delivery substrate for queued
issue #10542, under #4934. It is not mounted delivery and does not claim that the
background ship works yet.

## The contract built here

`backend/app/utils/activitykit_payload.py` builds bounded update/end bodies and
routine APNs headers, without credentials, tokens, network calls or implicit
`now()`. It consumes the already-projected `homeRenderedPercent` integer; it does
not independently round prices or infer a winner from scores.

The receiving contract is W3.1 `GameActivityAttributes.ContentState`, containing
only `snapshot`. The snapshot's camelCase fields match `GameActivitySnapshot`
from PR #10540 (first reviewed source `5223da093ec8043fce09e315a419e38d33ff2043`).
W3.1 has not been imported into this master-based backend branch.

Two time encodings are deliberately different:

- `content-state.snapshot.scoreObservedAt` and `probabilityObservedAt` are
  **seconds since 2001-01-01 UTC**, Swift `Date`'s default Codable representation.
  Missing fields are omitted, matching Swift optional-key encoding.
- APNs `aps.timestamp`, `stale-date`, and `dismissal-date` are **Unix seconds**.
  The caller explicitly provides `sent_at` for ordering; this never supplies a
  producer observation clock. Fractional producer observations remain fractional.

Apple specifies default JSON strategies for ActivityKit content state, and Unix
send timestamps in its current [ActivityKit push documentation](https://developer.apple.com/documentation/activitykit/starting-and-updating-live-activities-with-activitykit-push-notifications).
The focused backend tests pin independent golden Date/envelope numbers and the
entire nested ContentState shape. They do not execute a Swift decoder or prove
device receipt; a composed hosted Swift contract gate remains necessary.

Update freshness follows W3.1's 120-second observation-age policy. The oldest
clock belonging to a displayed score/probability controls `stale-date`. A missing
displayed clock makes the reading stale immediately; a later send never makes an
old observation fresh. Future clocks are rejected. Unknown/suspended lifecycle
is preserved and never promoted to final.

Only explicit `final`/`closed` authority permits a terminal end. An explicit
user-stop reason can end a nonterminal activity with immediate dismissal,
without changing its lifecycle to final. Terminal end retains the system's
default final-reading dismissal behavior. Scores do not manufacture a winner or
draw. Terminal/suspended/unknown snapshots cannot carry a forecast.

Bodies are UTF-8 JSON limited to 4096 bytes. Headers use `liveactivity`, priority
`5`, and expiration `0` (no APNs offline storage). There is no routine alert,
sound, or badge. APNs expiration is separate from on-device stale display: a
device missing an update must mark its last received reading stale on its already
received `stale-date`.

## Remaining delivery work and acceptance

This module alone does not satisfy #10542. Subsequent implementation must:

- Register/replace/revoke ActivityKit tokens through an authenticated contract,
  tied to the canonical event **and** activity; protect ownership and avoid tokens
  or credentials in logs. Generic FCM registration is insufficient.
- Project server authority into the shared snapshot and preserve the independently
  dated values. The frontend/Swift shared rounding decision must not be replaced
  by an unrelated backend source's rendered percentage.
- Serialize per-activity delivery timestamps, reject older/duplicate authority,
  and implement bounded retries, stop/final reconciliation and unavailable-device
  behavior. A pure builder cannot enforce ordering against prior sends.
- Supply approved APNs topic/environment/authentication configuration and a
  bounded transport. Nothing in this source slice changes Apple configuration.
- Enable ActivityKit token acquisition in the app: W3.1 currently requests
  `pushType: nil`, so its foreground activity cannot receive these pushes yet.
- Compose with the Swift candidate and prove decoded content, then capture real
  backgrounded iPhone/Watch receipts under #10543 before claiming delivery works.

No deployment, APNs send, token collection, Apple configuration, signing or
distribution action is included or authorized by this implementation.
