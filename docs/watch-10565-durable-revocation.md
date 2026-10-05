# Durable owner-only Live Activity revocation

PILLARS: TRUTH · FORMATTING.
SHIP: An activity stopped while offline stays stopped, and its registration is
revoked when the same account returns even after it disappears from iOS.

Child #10565 of #10542, based on frozen client head
`44a5e69461b944ff35b713c461a4bdd3f87a6187`. Public foreground/Watch remains account-free.

Before asynchronous stop/logout work, persist the activity id, immutable owner and
known event id plus the DELETE CAS version and mutation UUID. Credentials are never
persisted in this record. A durable tuple also reconstructs the permanent stopped
identity after a crash between storage writes. A verified same-owner auth/activation
reconciles pending tuples independently of ActivityKit's current activities. Cold
account switches stop saved prior-owner identities without borrowing the new bearer.

Ambiguous DELETE retries reuse their mutation identity. A 409 requires an owner GET
and bounded CAS reconciliation. Only authoritative inactive metadata acknowledges
revocation. Acknowledgment clears pending work and saved ownership/event metadata;
the permanent stopped identity remains, so a late callback cannot register it again.
Offline/auth failure, active replies and exhausted conflicts retain pending work.
Legacy owner-only records resolve their event through owner-authorized GET; failed
resolution retains the record and never guesses an event id. No timer implies
successful revocation.

Server child #10564 separately bounds credential lifetime to eight hours after first
server registration. Its expired PUT returns 409; same-owner GET/DELETE expose the
existing inactive fields. Neither child deletes immutable server identity tombstones
or weakens event merge/prune protection.

Six additional native tests cover tuple/latch crash recovery, absent-activity owner
switch and return, stable ambiguous DELETE UUID, permanent stop after acknowledgment,
active replies versus inactive conflict reads, and legacy resolution/failure. Existing
lifecycle tests now expect stopped work to retry DELETE on real activation. Four
backend startup tests and diff checks passed. Native tests have not run locally;
exact-head hosted iPhone/Watch/archive/general gates remain required. No Apple account,
local Xcode/simulator, APNs, production migration, deployment or phone acceptance.
