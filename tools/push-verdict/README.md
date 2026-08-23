# `push-verdict` — is the iOS push rail alive? (#2109)

```bash
tools/push-verdict/run.sh                    # self-test (6 branches), then the live verdict
FLOOR=2026-08-25 tools/push-verdict/run.sh   # certify a session on a later day
tools/push-verdict/run.sh --selftest-only
tools/push-verdict/run.sh --verdict-only
```

**Today's answer** (2026-08-23, re-measured): `BROKEN — zero ios rows exist at all`.
`device_tokens` holds 2 rows, both `macos`/`apns`, newest `2026-06-04`. Unchanged from
#2109's 08-22 measurement.

## What this is for

Alex's post-drain labeling session puts a fresh build on a real iOS device. When he taps
through the notification prompt, this turns that into a one-line verdict in about a second,
instead of a judgement call about a table.

## The problem it exists to solve

#2109's difficulty is that **the "fixed" state and the "still broken" state are both zero
rows** — gotcha #53's empty-200, in table form. So a bare `COUNT(*) WHERE platform='ios'`
cannot answer the question it looks like it answers. Three consequences, each one a
property of the query rather than a note in a doc:

1. **It always returns exactly one row.** Every counter is an aggregate with a `FILTER`,
   never a `WHERE`. A predicate that can return zero rows cannot distinguish "nothing to
   report" from "the check never ran".
2. **`macos_control` is in the output on purpose.** It is `2` today. Its job is to make a
   zero legible: `ios=0` next to `macos=2` is a real absence; `ios=0` next to `macos=0`
   means the query is not seeing the table it thinks it is.
3. **There is a time floor.** Without one, the first `ios` row that ever lands certifies
   every later session forever.

## The self-test is the point

Production can only ever exercise the branch it is in, so a verdict that has only produced
one value is indistinguishable from a constant. `--selftest-only` runs the **same**
`verdict-core.sql` over a synthetic `VALUES` list (it never touches the table) and asserts
all six branches:

| scenario | expected | why it is in the fixture |
|---|---|---|
| `1_broken` | BROKEN | today's real shape — macOS rows only |
| `2_stale` | STALE | ios rows exist but predate the floor |
| `3_mislabeled` | MISLABELED | an `fcm` row holding a 64-char APNS hex token |
| `4_fixed` | FIXED | apns + fcm, both active, both after the floor |
| `5_partial_apns` | PARTIAL | APNS landed, Firebase did not |
| `6_partial_fcm` | PARTIAL | fcm with no apns twin — must not read as FIXED |

**`3_mislabeled` and `4_fixed` produce identical counters** (`rows=2 ios=2 since_floor=2
apns_new=1 fcm_new=1`). Only the token-shape regex separates them. That pair is the
argument for the regex: a count-based check calls a dead push rail fixed, and #1159's own
comment says the FCM token is "the only one the digest sender can actually deliver to".

Measured: `PASS 6/6`. The self-test always runs at the **pinned** floor, never at `$FLOOR`
— the fixture timestamps are chosen relative to it, so running them at a caller's floor
turns a correct ladder red (`FLOOR=2026-08-01` flips `2_stale` to FIXED, which is the
substitution working, not the ladder breaking).

## The traced upload path (read-only, this cycle)

Known-good rows `id=1` and `id=9`: `platform=macos`, `token_kind=apns`, `is_active=true`,
`user_id=364`, `session_id` a UUID, `device_token` **64 hex chars** (32-byte APNS token).

| leg | where |
|---|---|
| trigger | `Bain_LuckApp.swift:121` → `requestPermissionAfterDelay()` (5 s after launch) |
| prompt | `NotificationManager.requestPermission()` → `requestAuthorization` |
| APNS opt-in | `registerForRemoteNotifications()` — **only called from the `granted` branch**, line 302 |
| APNS token | AppDelegate `didRegisterForRemoteNotificationsWithDeviceToken` → `didRegisterForRemoteNotifications` |
| FCM token | that same callback sets `Messaging.messaging().apnsToken`, then `handleFCMToken` |
| upload | `registerAllTokens()` → `register(token:kind:)` → `APIClient.registerDeviceToken` |
| endpoint | `POST /api/notifications/register` |
| **auth** | **none** — no admin secret, no bearer required. `user_id` is optional, so an anonymous launch registers fine |
| payload | `{device_token, platform, session_id, token_kind, user_id?}` |
| write | upsert on `uq_device_tokens_token` (`routes/notifications.py:88-108`) |

`platform` is compiled in (`#if os(iOS)` → `"ios"`), so an `ios` row can only come from an
iOS build. `token_kind` falls back to `"apns"` server-side for unknown values, which is why
a mislabeled row is possible and worth checking for.

## db-query traps met while building this

`assert_read_only` (`app/utils/sql_read_guard.py:68-85`) is a substring check over the
**whole statement — string literals and comments included**. It refused this query three
times before it ran once:

| what | error |
|---|---|
| a `;` inside a verdict **string** | `Multi-statement queries not allowed` |
| a `;` inside a `--` **comment** | same |
| the English word **"grant"** in a verdict string | `Only SELECT queries are allowed` (`\bGRANT\b`) |

So: no semicolons anywhere, and none of
INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/CREATE/GRANT/REVOKE/COPY as prose either.
`render()` re-checks both before spending a request and exits 3 with the offending list, so
the next person gets a local failure instead of a 400.

## Files

| file | what |
|---|---|
| `verdict-core.sql` | the ONE copy of the CASE ladder, with `{{PREFIX_SELECT}}` / `{{SOURCE}}` / `{{GROUP}}` holes |
| `fixtures.sql` | synthetic rows, one scenario per branch |
| `run.sh` | renders both forms from the core, preflights, calls `db-query`, asserts |

The ladder is not duplicated between the self-test and the live run — both are rendered
from `verdict-core.sql`. A self-test asserting against its own copy of the rule proves
nothing about the rule that ships.
