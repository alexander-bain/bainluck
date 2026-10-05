# #10542 signed-in iPhone ActivityKit registration

Pillar: TRUTH. Ship: a signed-in iPhone can register its explicitly started game
Live Activity for later background updates, and stop or logout ends its local
activity while attempting to revoke that registration.

This source adds optional token requests to explicit signed-in starts and observes
ActivityKit token rotation. Anonymous starts retain foreground-only updates and
are never silently upgraded after login. Persisted ownership contains only the
ActivityKit activity id and backend user id, plus stopped activity ids. Stop intent
is persisted synchronously before network or ActivityKit ending work, including
a cold/offline stop before auth restoration creates an in-memory entry. A relaunch
never registers a stopped identity; a remaining same-account activity is ended
locally and reconciled only through DELETE. Restored activities are adopted only
for the same verified account. Bearers and push tokens are never persisted by
this service or logged.

Registration uses the existing backend session bearer and the #10553
GET/PUT/DELETE versioned contract. A stop latches synchronously, cancels token
observation, and wins over an in-flight PUT. A 409 requires a metadata GET and a
new versioned DELETE; it never confirms revocation. Each reconciliation is
bounded to three conflicts and each production request has an eight-second
request timeout and twelve-second resource timeout. Local dismissal does not
await the network. Offline, unauthorized, absent endpoints and exhausted
conflicts leave remote revocation unconfirmed. Failed registration attempts retry
only on a real foreground activation or verified same-owner auth refresh, using
the unchanged token and stable mutation UUID. Refreshed same-owner credentials
apply to future attempts; stopped old-account work retains its old credential.
There is no retry timer. Failed revocations are not a
claim that the server stopped delivery; endpoint deployment and retry policy
remain integration gates.

No sender is connected by this change. Foreground wording remains accurate.
No APNs sends, credentials, signing, device acceptance or release is established.
The fifteen new deterministic native tests require the hosted iPhone gate.
