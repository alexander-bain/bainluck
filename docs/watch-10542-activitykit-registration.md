# W3.2: signed-in registration substrate

PILLARS: TRUTH · FORMATTING.
SHIP: The explicitly selected game's Live Activity keeps receiving readings while
the iPhone is suspended. Alex approved sign-in for background updates; public
Watch/foreground behavior remains unchanged. This route does not acquire tokens,
send APNs, select Apple environments, or prove background receipt.

Existing `get_current_user` authenticates the bearer and existing account before
the request body is parsed. Analytics `x-session-id` grants no authority. The owner
is always the authenticated account; the client cannot supply a user ID.

PUT `/api/activitykit/registrations/{activity_id}` accepts `event_id`, hexadecimal
`push_token`, `expected_version` and UUID `mutation_id`. Version zero creates one
activity/event/owner binding; the server assigns version one. Replacement requires
the current server version and atomically increments it. Ownership and canonical
event are immutable. An existing event is required; table foreign keys enforce it.
GET the same URL returns only activity/event/version/active metadata to the owner.

DELETE accepts the same mutation fields except token. Version zero can create an
inactive tombstone BEFORE initial registration reaches the server. Later puts may
never reactivate that activity identity. Revocation clears both raw token and token
fingerprint. If concurrent creation/replacement wins, revocation receives 409: the
client MUST GET fresh metadata and retry revocation with that version/new mutation
ID until acknowledged; a conflict is never confirmation that delivery stopped.
A stopped client's queued registration must also be canceled locally. Tombstone
ownership persists until account/event deletion; their foreign keys cascade and
remove all credentials. Account deletion prevents session authentication through
the existing auth dependency; no auth code is changed here.

CAS is enforced by SQL owner/event/version/active predicates. Initial create uses
primary-key conflict-do-nothing, so competing creates never steal an activity.
Exact replay of the latest successful mutation returns its metadata without a
write. Reusing its mutation ID with changed action/token/version conflicts; old
replay after a newer operation conflicts. The client persists its mutation ID
until completion and never manufactures a newer server version.

Tokens are not responses, log fields, validation errors or exception messages.
Manual bounded-body validation prevents default error input echo. Unique-token
collisions are generic 409; DBAPI operational failures are generic 503 without
logging/chaining SQL bound parameters. A token fingerprint only enforces CURRENT
active uniqueness: historical tokens replaced/revoked are not a new installation
authentication system. Plaintext token storage is necessary for the eventual APNs
transport and uses the existing database trust boundary; no credentials/configuration
are introduced by this source preparation.

The separate model is exported by `app.models`, which Alembic imports for metadata.
Migration `activitykit_registration` follows `prob_publications`; it creates a new
small table and does not change existing data. No migration was executed. SQL route
tests use a real SQLite constraint/CAS engine, including intervening writes; they
are not PostgreSQL deployment evidence. Apple token acquisition, logout lifecycle,
transport, durable delivery state composition and #10543 physical receipt remain
separate work before the background ship can be claimed.

The PostgreSQL-specific gate is routed to the existing isolated CI leg through
`ci-postgres-groups.json`. Five cases use independent PostgreSQL sessions in a
random disposable schema under the explicitly configured `bl_searchtest` database:
replacement CAS, competing initial owners, unique active token collision,
create/revoke ordering and tombstones, and account-deletion cascade. No public
schema reset is used. Local collection found five cases; without the test URL
they skip, which is not PostgreSQL acceptance. The hosted step fails on any skip
or a count other than five passed. Hosted PostgreSQL execution remains pending.
