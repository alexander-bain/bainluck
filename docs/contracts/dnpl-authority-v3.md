# DNPL authority v3 — wire contract R2 (with D1–D3 clarification)

PILLAR: TRUTH / FORMATTING.
SHIP: held web and Native pages resume correctly ordered fast probabilities
after Redis has lost the old ordering history. This document freezes the new
reader envelope; it does not authorize activation or claim implementation.

Capability: `GET /api/events/{id}/stream?preview_protocol=authority-v3`.
Existing committed events keep their existing names and payloads. V3 adds two
SSE event names: `preview_open_v3` and `preview_v3`. Streams without this exact
capability receive no v3 open, blend or revoke. They continue committed delivery.
V3 streams never receive legacy `preview` events. Rollback to a legacy server
therefore means committed-only for a v3 visit; it cannot lower its authority.

## Exact envelope

Every v3 message has:

* `protocol`: JSON integer 3.
* `event_id`: the requested positive, safe-integer event ID.
* `authority`: object with `incarnation` and `namespace` only.
  `incarnation` is a canonical decimal string from `"1"` to
  `"9007199254740991"`; no leading zero, sign, whitespace, exponent or JSON number.
  `namespace` is a non-nil lowercase UUID string, exact hex 8-4-4-4-12 syntax;
  accept any version/variant bits, reject uppercase and whitespace. Compare incarnations by
  integer magnitude; a UUID supplies equality, never ordering.
* `stream_session`: non-nil lowercase UUID with that same exact syntax, generated for this stream opening.
  It is not a provider owner and is not allowed to reset authority by itself.

D1: Integer-valued JSON **number** fields use decoded numeric value, not lexical
spelling. Thus `3`, `3.0` and `3e0` all represent protocol 3; the same rule applies
to event/member IDs and existing inner integer fields. Their respective finite,
safe-integer, sign and range checks still apply. Strings are not numbers. This
does not relax `authority.incarnation`: that field remains a canonical decimal
**string**, so `"3.0"` and `"3e0"` remain invalid.

`preview_open_v3` additionally has `members`: 1–32 distinct positive safe-integer
event IDs in increasing numeric order, including `event_id`. It has no `frame`.
The server emits it only after verifying the ready PostgreSQL identity, current
Redis identity and fresh stream membership. Ordinary stream `open` may precede
it but does not enable v3 previews. A source code/HTTP version is not authority.
The open membership must equal the page's adopted detail membership, not just
include the page row. A mismatch activates no incoming session and changes no
fence; the existing detail-membership change path reopens the stream.

D3: An open received before any detail membership is adopted is refused, never
saved for later replay. The first valid membership adoption (unknown → known)
must reopen an already-running stream, just as a change to known membership
does. Close the prior handle, retire its held display/session, and require a new
current-connection `preview_open_v3`. A revision-only update with unchanged
membership advances committed floors without reopening. Obsolete callbacks from
the prior handle cannot enable the new stream.

`preview_v3` additionally has `frame`, the existing validated preview frame:
`frame.event_id` equals outer `event_id`, and `frame` has no committed `rev`.
There is no top-level `preview`, `epoch`, `seq`, `rev` or `members`. No decoder may
unwrap `frame` until this envelope passes its current-stream/domain checks.

For singleton membership, admit only the existing singleton shape (no folded
version or folded fields). `frame.preview` uses:
`kind`, `epoch`, `seq`, and either `base_rev`/`ttl_ms` (blend) or `through_seq`
(revoke). For membership of two or more rows, admit only folded_version 2 with
the existing folded-v2 payload shape:
`folded_version:2`, `fold_session`, `fold_seq`, `base_fold_revision`,
`origin_authority`, `kind`, `ttl_ms`. Here `fold_session` MUST equal the outer
`stream_session`. `folded_version:2` describes the INNER composition only; the
outer ordering authority is protocol 3 and travels only on the v3 event name.
Every base vector key must equal the open membership set. At most two elected
source origins may be pending; their authority remains per-origin, not scalar.
All existing probability/source/status/base/sequence checks still apply.

Reject unknown keys on the OUTER envelope and `authority`, malformed types,
incomplete structures and mismatched inner/outer event/session identity. Inner
`frame` and `frame.preview` retain their existing additive-key parsing rules;
their unknown keys alone are not a new rejection rule. Reject duplicate JSON
object keys at EVERY depth, including inner `frame`, before ordinary JSON
decoding. Compare decoded key strings, so escaped spelling does not evade this
rule. Foundation and JSON.parse choose different duplicate occurrences. The
16 KiB UTF-8 limit applies to the whole envelope, including open and revoke.
Probability is a finite JSON number in [0,1]; no stringification or NaN.
No absolute UTC timestamp is introduced into the user interface.

## Reader transitions

The transport attaches its current connection-generation identity to callbacks.
A callback from an obsolete connection is ignored before parsing or mutation.
These generation guards are separate from server `stream_session`.

1. Initial validated v3 open enters the v3 domain and retires any legacy held
   preview. Preserve committed revision floors and chart history. Never compare
   legacy scalar epochs numerically with a v3 incarnation or inner epoch.
2. A higher-incarnation open from the current connection replaces preview-domain
   identity and retires its held preview. Clear per-row preview origin fences,
   legacy orders, scalar epoch, fold sequence/session origins and the preview
   fences/orders of retired members. Keep committed revision floors INCLUDING
   retired members' floors, current membership, visit distinct-row count,
   saturation and chart continuity. Never use old-domain tuples to order the new
   domain. These rules also apply to initial entry from legacy preview mode.
3. Equal incarnation + different namespace rejects without mutation. Lower
   incarnation rejects. A frame alone cannot establish or advance a domain.
4. Same-incarnation/same-namespace reconnect opens a fresh session, retires the
   held preview and retains event ordering, retired evidence, first-seen deadlines
   and committed floors. A new session cannot revive a retired/equal tuple.
   Duplicate open for the exact active session is a no-op, not an expiry reset.
5. A frame requires exact active authority and stream session; then the existing
   singleton/folded checks decide admission. An older domain, session, origin
   epoch or sequence is refused. Equal tuple never extends its first deadline.
6. Committed frames always use the existing revision path. A new domain never
   makes an uncovered base acceptable. Old v1/v2 preview frames are rejected
   after entering v3, including revokes and callbacks from a previous transport.

Transport `open` (including reconnect on the same handle), `closed`, and
`reconnect` retire held display and END the active v3 stream_session; a new
`preview_open_v3` is required. `resync` retires held display but keeps the active
session and all ordering/first-seen evidence. The server's v3 authority validation
failure or overflow MUST issue `reconnect`, not merely `resync`. It may keep the
ordinary committed path available while the transport obtains a fresh session.
Retired tuples never revive on a same-domain resync/reopen.

D2: A transport `error` also immediately retires the held preview and ends its
active v3 session, including an error for which the same transport handle will
retry automatically. Preserve ordering, first-seen deadlines, committed floors,
chart history and saturation. Do not keep a preview visible until TTL after a
known transport loss. The transport's existing retry policy is unchanged; the
next successful open still requires a fresh `preview_open_v3` before previews.

Disconnect/recovery clears display authority, not the retained fences. Returning
committed truth is truthful fallback; neither an unknown domain nor a new open
may clear chart history or fabricate a committed revision.

## Deadlines and memory

Server receipt time is captured at Redis receive, before the authority-validation
queue. TTL at emission subtracts all queue/validation/mailbox time. At the client,
capture monotonic receipt before asynchronous work and subtract client processing
delay. First acceptance records a monotonic deadline. Repeated tuples use the
minimum of that deadline and the new remaining TTL. Expired output is not sent
or displayed. A frame never refreshes an old tuple merely by arriving later.

One current domain/session, 32 member rows, 32 distinct active row identities per
visit (never reset by a new incarnation), and an 8-retired-member threshold. Retire a whole leaving batch before
deciding saturation: at most 8 previous retired rows plus 32 leaving rows, then
freeze preview admission. Never discard a floor/fence to admit another row.
Saturation persists across reconnect and incarnation changes until navigation.
Source count remains at most two selected pending origins; these member bounds
are about duplicate event rows, not counting sportsbooks as preview sources.

## Shared examples and owner boundary

`dnpl-authority-v3.examples.json` contains complete open/blend/revoke examples
and transition cases. The timestamps are fixture data, not UI instructions.
Each transition names the expected admission action; existing inner-reader
checks may still refuse an envelope that passes the outer checks.

Speed owns backend/web; Native owns Swift decoder, transport, view model and
actual SwiftUI gates. R2 resolves Native's eight author-alignment questions.
The original R2 bytes earned independent contract acceptance. D1–D3 above are a
narrow author clarification prompted by the Native implementation review; their
delta review is separate. Contract acceptance is not runtime implementation
acceptance. The Redis rollback premise and latency remain implementation gates.
