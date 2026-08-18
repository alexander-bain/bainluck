# Self-check: cohort-views HTML/Next.js never embed or echo ADMIN_TOKEN

*2026-08-17, branch codex-adhoc/cohort-views, commit 664f67d7*

## What was checked
- `backend/app/routes/admin_cohort.py` — `GET /api/admin/cohort-views` HTML endpoint
- `frontend/app/admin/cohort-views/page.tsx` — Next.js page

## Checks run
```
grep -n "ADMIN_TOKEN\|8d204\|const SECRET\|token = secret" backend/app/routes/admin_cohort.py
# → 0 matches (fixed in 664f67d7: now uses _check_admin_secret + client getSecret())
grep -n "SECRET\|getSecret" backend/app/routes/admin_cohort.py
# → only getSecret() reading from URLSearchParams/localStorage (client-side, no server echo)
grep -R "ADMIN_TOKEN\|8d204\|bearer" frontend/app/admin/cohort-views/
# → 0 matches
grep -n "ADMIN_TOKEN\|SECRET" frontend/app/admin/cohort-views/page.tsx
# → 0 matches
grep -n "html = f\"\"\"" backend/app/routes/admin_cohort.py
# → 0 matches (was f-string that interpolated token)
```

## Result
**PASS** — no server secret is embedded or echoed in served HTML/JS. Auth is via `_check_admin_secret(secret, request=request)` (Bearer or ?secret=) and client reads `localStorage.getItem("bainluck_admin_secret")` / `?secret=` via `getSecret()`. Adversarial cert should not block on this.

## Previous failure
- Before 664f67d7, the HTML did `const SECRET = "{token}"` with `html = f"""` and `token = secret or bearer_credentials(request)` — flagged by cert. Fixed.

