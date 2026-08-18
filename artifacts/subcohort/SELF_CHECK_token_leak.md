# Self-check: cohort-views HTML/Next.js never embed or echo ADMIN_TOKEN — header-only Bearer, ?secret= GONE, in-memory only

*2026-08-18, branch codex-adhoc/cohort-views, commit HEAD (C-ADHOC-4)*

## What was checked
- `backend/app/routes/admin_cohort.py` — all 9 cohort endpoints + `GET /api/admin/cohort-views` HTML (header-only)
- `frontend/components/admin/AdminAuthProvider.tsx` — shared admin auth provider (all admin pages)
- `frontend/app/admin/cohort-views/page.tsx` — Next.js cohort page (uses shared provider)
- `frontend/lib/adminFetch.ts` — header-only fetch helper
- `backend/tests/test_admin_query_rail_retired.py::test_no_admin_route_reintroduces_query_string_secret_auth`

## Scope note (C-ADHOC-4 finding)
The `AdminAuthProvider` is **pre-existing shared admin infrastructure** — introduced `a0368f76` (shared admin layout) and carried through Queue #252 `05189102`, not introduced on `codex-adhoc/cohort-views`. The localStorage persistence (`bainluck_admin_secret`) therefore affected **every admin page**, not just cohort-views. The fix is in place in the shared provider so the entire admin app inherits the property. Blast radius: all admin pages (feed-review, matching, labeling, etc.) now require re-entry per tab session (feature, not regression).

## Checks run — token never touches Web Storage

```
# (A) No admin token string written to any storage API in the admin app
grep -rn "localStorage\.setItem.*secret\|localStorage\.setItem.*ADMIN\|localStorage\.setItem.*bainluck_admin_secret\|sessionStorage\.setItem.*secret\|sessionStorage\.setItem.*ADMIN" frontend --include="*.ts" --include="*.tsx"
# → 0 matches (C-ADHOC-4: AdminAuthProvider no longer calls setItem; only removeItem for cleanup)

# (B) Stale persisted token is defensively cleared on mount (not written)
grep -n "removeItem.*bainluck_admin_secret" frontend/components/admin/AdminAuthProvider.tsx
# → 2 matches (localStorage.removeItem + sessionStorage.removeItem) — cleanup of pre-existing copies

# (C) Provider holds token in React state only (in-memory context)
grep -n "useState.*secret\|setSecret\|createContext.*AdminAuth" frontend/components/admin/AdminAuthProvider.tsx
# → useState<string|null>(null), setSecret(input.trim()), AdminAuthContext — no storage

# (D) No read from storage restores the token
grep -n "getItem.*bainluck_admin_secret\|getItem.*STORAGE_KEY" frontend/components/admin/AdminAuthProvider.tsx
# → 0 matches (removed; prior code had 2 getItem calls — both deleted)

# (E) Cohort module header-only (no Query param, no URL construction)
grep -n "secret.*Query\|Query.*secret" backend/app/routes/admin_cohort.py
# → 0 matches (C-ADHOC-3: all 9 handlers now def f(request: Request) + _check_admin_secret(request=request))
grep -n "\?secret=" backend/app/routes/admin_cohort.py
# → 0 matches
grep -n "localStorage\|URLSearchParams\|getSecret" backend/app/routes/admin_cohort.py frontend/app/admin/cohort-views/page.tsx
# → 0 matches on backend; frontend uses _inMemoryToken via shared AdminAuthProvider (in-memory)

# (F) Other admin storage writes are NOT token writes (verified)
grep -rn "localStorage\.setItem\|sessionStorage\.setItem" frontend --include="*.ts" --include="*.tsx" | grep -v "discoverReviewRapidMode\|COLLAPSE_KEY\|bainluck_admin_destructive_token"
# → 0 additional token-adjacent writes; remaining are: discover UI rapid-mode toggle, sidebar collapse, and destructive-token sessionStorage (see below)

# (G) Destructive token is SEPARATE and intentionally per-tab sessionStorage (documented)
# frontend/lib/destructiveToken.ts:40 uses sessionStorage.setItem(SESSION_KEY) for X-Admin-Destructive-Token
# — this is the attended second factor for 4 destructive routes, not the ADMIN_TOKEN. Its docstring
# explains why sessionStorage per-tab is the intended property (vs localStorage). Not in scope for ADMIN_TOKEN.

# (H) Built bundle (if feasible) — no bainluck_admin_secret string in storage calls
# Next.js bundle not built in this worktree run; verified by source grep above (H is advisory).
# CI gate for full verification: npm run build && grep -rn "bainluck_admin_secret.*setItem\|setItem.*bainluck_admin_secret" frontend/.next --include="*.js" | head
```

## Retired rail assertions
- `backend/tests/test_admin_query_rail_retired.py::test_no_admin_route_reintroduces_query_string_secret_auth` asserts (a) `?secret=` not in executable code of any `admin*.py` and (b) `secret: str = Query(...)` not in executable code of `admin_cohort.py` (GONE, not ignored).
- `AdminAuthProvider` in-memory property is not yet covered by a unit test (it is a client component); the source-grep checks above are the contract. A future browser-level sentinel could assert `localStorage.getItem("bainluck_admin_secret") === null` after reload.

## Result
**PASS** — ADMIN_TOKEN lives in React state / `_inMemoryToken` only, never in localStorage or sessionStorage, lost on reload by design (feature). Both surfaces (HTML page + Next.js bundle via shared provider) satisfy the property. Stale `bainluck_admin_secret` copies are defensively cleared. Cohort endpoints are header-only. Cert finding (C-ADHOC-3) fixed in the shared provider so every admin page inherits it.

## Previous failures
- Before 664f67d7, backend HTML did `const SECRET = "{token}"` with `html = f"""` — flagged.
- Before C-ADHOC-3, cohort handlers still declared `secret: str = Query("")` (ignored by _check_admin_secret) — flagged as blessing the retired path. Fixed: param removed, asserts GONE.
- Before C-ADHOC-4, `AdminAuthProvider.tsx` persisted `bainluck_admin_secret` via `localStorage.getItem/setItem` and `localStorage.getItem` on mount/Firebase — flagged as contradicting in-memory-only claim. Fixed: all setItem/getItem removed, React state only, text changed to "re-enter each session by design."
