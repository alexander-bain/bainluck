# Self-check: cohort-views HTML/Next.js never embed or echo ADMIN_TOKEN — header-only Bearer, ?secret= GONE

*2026-08-17, branch codex-adhoc/cohort-views, commit HEAD (C-ADHOC-3 refreeze)*

## What was checked
- `backend/app/routes/admin_cohort.py` — all 9 cohort endpoints + `GET /api/admin/cohort-views` HTML
- `frontend/app/admin/cohort-views/page.tsx` — Next.js page
- `backend/tests/test_admin_query_rail_retired.py::test_no_admin_route_reintroduces_query_string_secret_auth`

## Checks run
```
# Cohort module must be header-only: no ?secret= Query param at all (GONE, not ignored)
grep -n "secret.*Query\|Query.*secret" backend/app/routes/admin_cohort.py
# → 0 matches (removed in C-ADHOC-3: all handlers now `def f(request: Request)` + _check_admin_secret(request=request))
# No URL construction with ?secret=
grep -n "\?secret=" backend/app/routes/admin_cohort.py
# → 0 matches
# _check_admin_secret is header-only (Authorization: Bearer)
grep -n "_check_admin_secret" backend/app/routes/admin_cohort.py
# → _check_admin_secret(request=request) on every handler
# HTML uses in-memory _inMemoryToken, never localStorage/URLSearchParams
grep -n "localStorage\|URLSearchParams\|getSecret" backend/app/routes/admin_cohort.py frontend/app/admin/cohort-views/page.tsx
# → 0 matches on backend; frontend uses _inMemoryToken only
# Frontend never embeds ADMIN_TOKEN
grep -n "ADMIN_TOKEN\|SECRET" frontend/app/admin/cohort-views/page.tsx
# → 0 matches (auth via adminFetch Bearer header)
```

## Retired rail assertion (C-ADHOC-3)
`backend/tests/test_admin_query_rail_retired.py::test_no_admin_route_reintroduces_query_string_secret_auth` now asserts **GONE**:
- (a) `?secret=` not in executable code of any `admin*.py`
- (b) `secret: str = Query(...)` not in executable code of `admin_cohort.py` at all — the param does not exist, it is not merely ignored. Other admin modules still declare it for call-site compat (ignored by `_check_admin_secret`), but the cohort lane re-proves GONE.

Cohort module is clean: `grep -n "secret" backend/app/routes/admin_cohort.py` shows only `_check_admin_secret(request=request)` and client-side `secret` local var in JS (`const secret = _inMemoryToken`), plus comment `Header-only auth (no ?secret)`.

## Result
**PASS** — cohort-views is header-only Bearer. `?secret=` query-param auth is GONE from `admin_cohort.py` (no Query param, no URL construction, no localStorage). Cert finding (3) fixed.

## Previous failure
- Before 664f67d7, HTML did `const SECRET = "{token}"` with `html = f"""` — flagged.
- Before C-ADHOC-3, handlers still declared `secret: str = Query("")` and `_check_admin_secret(secret, request=request)` ignored it — cert flagged as blessing the retired path (safe but still present). Fixed: param removed, asserts GONE.
