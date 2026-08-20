# Admin access by identity

**Ruling: Alex, 2026-08-20 (Queue 386 Item 2).** A Google-authenticated session
belonging to an admin user unlocks the admin UI *without* the pasted admin
secret. Agent lanes keep using `ADMIN_TOKEN` on exactly the path they used
before.

---

## The two credentials

Both arrive in the same header — `Authorization: Bearer <x>` — and they are not
the same kind of thing.

| | ADMIN_TOKEN | Admin identity |
|---|---|---|
| What it is | one shared secret, in env | a per-user session JWT |
| Who holds it | every agent lane, CI, Alex | one signed-in person |
| Identifies | a **capability** | a **person** |
| Checked by | `_check_admin_secret` (constant-time compare) | `_resolve_admin_user` (verify JWT → look up `users` row) |
| Unlocks reads/writes | yes | yes |
| Unlocks **destructive** | yes, *with* `ADMIN_TOKEN_DESTRUCTIVE` | **never** |

The token arm is always tried **first**. It is an `hmac.compare_digest` against
an env var: no database, no JWT parse. A lane's request therefore never reaches
the identity arm, which is what "lanes keep tokens, zero change to their path"
means mechanically rather than as a promise. A failed JWT decode cannot change
the token arm's outcome — `_resolve_admin_user` returns `None` for every failure
mode and never raises.

Both failures produce the same 403 with the same body. Which arm declined is not
disclosed; that would be an oracle for probing who holds admin.

---

## Granting the role

`users.is_admin` is a `BOOLEAN NOT NULL DEFAULT false` column
(`alembic/versions/add_users_is_admin.py`, revision `add_users_is_admin`).

**No migration and no endpoint grants it.** Both were considered and both were
rejected:

- A migration that writes a grant is a privilege escalation shipped inside a
  diff that reviewers read as schema. It would also be wrong in the ordinary
  way: migrations run everywhere, so a hardcoded id grants admin to whichever
  row holds that id in a restored or seeded database.
- An endpoint behind `ADMIN_TOKEN` would let any of the dozen holders of that
  token grant *themselves* a durable, person-shaped privilege — collapsing the
  distinction in the table above, which is the whole point of the column.

Alex grants it with one statement (run it yourself with a `!` prefix — agent
sessions have no egress to port 5432):

```sql
UPDATE users SET is_admin = true WHERE lower(email) = lower('<his email>');
```

```bash
heroku pg:psql -a bainluck -c "UPDATE users SET is_admin = true WHERE lower(email) = lower('EMAIL_HERE');"
```

Audit and revoke:

```sql
SELECT id, email, is_admin FROM users WHERE is_admin;          -- who is admin right now
UPDATE users SET is_admin = false WHERE id = <id>;             -- revoke, effective next request
```

Revocation takes effect on the next request — there is no cache and no deploy.

### The legacy allowlists still work

`_user_is_admin` (`app/routes/admin_utils.py`) ORs three sources: the column,
then `ADMIN_USER_IDS` / `DEFAULT_ADMIN_USER_IDS = {364}`, then
`ADMIN_USER_EMAILS` / `DEFAULT_ADMIN_EMAILS`. The allowlists were deliberately
**kept**, not replaced: the column ships in a release and the grant is a manual
`UPDATE` afterwards, so removing them in the same change would open a window —
however short — in which the admin UI has no admin and the person locked out is
the one holding the SQL. Retire them in a later change, once
`SELECT ... WHERE is_admin` shows the intended set.

---

## The destructive invariant

**Identity alone NEVER unlocks a delete.** The mechanism is the first line of
`_check_admin_destructive`, not a rule anyone has to remember: it calls
`_check_admin_secret`, which is token-only. An identity-authenticated request
fails there and never reaches the `X-Admin-Destructive-Token` check at all — so
it is 403 *even when it presents a correct destructive token*.

Pinned by `backend/tests/test_admin_identity_auth_q386.py`.

---

## `GET /api/admin/whoami`

The probe the admin UI calls before rendering. **It does not 403.** "No" is the
answer here, not a refusal — a 403 would be indistinguishable from an expired
token, a CORS failure, or the API being down, which are three different fixes
behind one status code.

```json
{"is_admin": true, "via": "identity", "email": "…", "user_id": 364, "authenticated": true}
{"is_admin": true, "via": "token",    "email": null, "user_id": null, "authenticated": true}
{"is_admin": false, "via": null,      "email": null, "user_id": null, "authenticated": false}
```

`via` names the arm that accepted the credential the caller *sent*; it never
reveals whether some other credential would have worked.

---

## The admin UI

`components/admin/AdminAuthProvider.tsx` calls `whoami` with the Firebase /
backend-session bearer on mount:

- `is_admin: true` → no prompt. Context exposes `identityAdmin: true` and
  `authToken` = the session JWT.
- otherwise → the existing secret prompt, unchanged.

`secret` keeps its old meaning — **the pasted `ADMIN_TOKEN`, or `""`**. A session
JWT is never assigned to it. That is what keeps this change from touching the
other twenty admin call sites: pages that gate on `if (!secret)` keep their
current honest behaviour, and no page can accidentally put a JWT into a query
string (which is how `?secret=` leaked through history and `Referer` in the
first place — Queue #252 Item 3).

Pages opt in by reading `authToken` instead of `secret`. `/admin/labeling` is
migrated (Queue 386 Item 2's acceptance case). Under identity mode the provider
renders a slim bar offering token entry, so a token-only tool on another page
stays reachable without a reload.

---

## Gold-label attribution

A judgment written under a verified admin session records that identity twice,
for two different jobs:

- `ranking_judgments.reviewer` — the **operational** key. Reviewed-state dedup
  keys on it, so the read (`GET /candidates`) and the write (`POST ""`) must
  resolve it identically. They now share `GENERIC_REVIEWERS`; before Queue 386
  the web page asked with `reviewer="native"` (resolved to the email) and wrote
  back `reviewer="web"` (not resolved), so web labels never suppressed their own
  cards on the next batch.
- `label_metadata.reviewer_identity` — the **provenance** key, next to
  `reviewer_tier`. Written once, only from a verified session. `reviewer_tier`
  says which *pool* a row belongs to; this says which *person* put it there
  (#671).

A request authenticated by the shared `ADMIN_TOKEN` gets **no**
`reviewer_identity` key. A dozen lanes hold that token, so "written by the
token" identifies no one, and an unfalsifiable provenance claim in a ~24-row
gold corpus is worse than no claim.
