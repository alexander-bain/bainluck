# Post-deploy health and rollback

A successful master CI run and a five-minute schedule discover Heroku's current release. The observer executes trusted master code inside GitHub Actions. It checks anonymous `/api/health` and `/api/feed?limit=5` and uses the existing Speed worker and latency checks. A public probe must fail three attempts, separated by at least 30 seconds, before it can request rollback.

Vercel retains its existing Git auto-deployment. This PR's observer and rollback manage Heroku only. Release observation uses Heroku's existing log-session API with the Action's `HEROKU_API_KEY`. It adds no product route, production dispatch token, log drain or collector.

The log read is bounded to 1,500 retained worker-ws lines and 8 MiB. It must span the required 30-minute history floor and reach the current observation window. Missing, truncated or stale evidence stays UNKNOWN. The existing guard2 stop is two consecutive sampled minutes over 5,000 ms, excluding na_orientation. Guard3 retains its three-minute stop and 20-point deterioration rule. Startup/A10 must finish with a complete PASS.

Merge after the settings-freeze PR supplies `tools/speed/check.py`, `latency_guard2.py` and `latency_guard3.py`, after Midterms is live and after the independent review and CI gates. The release loop remains unarmed during integration.

Before any later, explicitly authorized arming operation, seed reviewed conclusive existing watcher evidence using `seed_baselines.py`. The exact current provider identity and source must agree with the proof. A failed-source veto refuses an older PASS under another release ID. The optional attended Heroku bootstrap requires a successful current-master CI attempt with all eight real backend shards and a seeded rollback target. It re-releases the same binary under the Heroku writer lock. None of these setup operations has been executed by this PR.

The arming preview is `python3 tools/release/arm.py`. Applying it requires a current-master proof, reviewed provider control evidence, a complete worker window, a valid current baseline and verified rollback. It publishes the fresh policy receipt before setting `RELEASE_LOOP_FAST_ENABLED`. Branch protection and collectors have separate explicit user holds.

Rollback persists a failed-source veto before waiting for `heroku-deploy`, validates a known-good PASS target against Heroku, checks that the failed release is still current, and verifies the target source after the write. Exit 1 means confirmed rollback, 0 means superseded and 2 means refusal or observer failure. An unknown baseline never authorizes rollback.

A verdict is one deduplicated line on NOW #11852. UNKNOWN before baseline seeding writes no NOW comment. Terminal receipts are replayable so an interrupted comment write can recover without repeating measurement. No verdict artifact is uploaded.

Local verification uses `python3 -m unittest discover -s tools/release/tests` and the backend startup and release-health guard. Live provider control, retained-window coverage and arming remain unperformed.
