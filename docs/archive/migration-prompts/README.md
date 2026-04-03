# Canonical Identity Migration — Phased Prompts

## Overview

These prompts migrate Bain Luck from a fragmented team/event identity system
(where The Odds API is the accidental source of truth) to a canonical system
where StatPal provides authoritative schedules and a shared `TeamIdentityService`
resolves teams across all data sources.

## Execution Order

Run each phase as a **separate Claude Code CLI session**. Verify tests pass
and the commit is clean before proceeding to the next phase.

| Phase | File | Time Est. | Risk | What Changes |
|-------|------|-----------|------|-------------|
| 1 | `phase-1-sport-keys.md` | 30-60 min | Low | New `sport_keys.py`, import updates. No schema, no behavior change. |
| 2 | `phase-2-team-identity.md` | 1-2 hrs | Medium | New table + model columns + TeamIdentityService + backfill task. No consumer changes. |
| 3 | `phase-3-schedule-first.md` | 1.5-2.5 hrs | **High** | StatPal creates events, Odds API attaches. `external_id` becomes nullable. |
| 4 | `phase-4-consumer-migration.md` | 1.5-2 hrs | Medium | ESPN/StatPal/PM matching use TeamIdentityService. All fallbacks preserved. |

## Before Starting

1. **Clean your working tree.** Resolve any merge conflicts, commit or stash
   uncommitted changes. Run `git status` and ensure it's clean.

2. **Run the baseline test suite:**
   ```bash
   cd backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -10
   cd frontend && npx jest 2>&1 | tail -5
   ```
   Record the test counts. Every phase must maintain or increase these.

3. **Create a branch:**
   ```bash
   git checkout -b canonical-identity-migration
   ```

## Between Phases

After each phase:
- Run the FULL test suite (not just new tests)
- Review the diff: `git diff HEAD~1 --stat`
- Verify the commit is clean: `git status`
- If deploying incrementally, each phase is independently deployable

## Rollback

Each phase has a clean rollback path:
- **Phase 1:** Revert the commit (just import path changes)
- **Phase 2:** `alembic downgrade -1` drops the table/columns, revert code
- **Phase 3:** `alembic downgrade -1` restores NOT NULL on external_id, revert StatPal creation code
- **Phase 4:** Revert the commit (fallback paths mean old behavior is restored)

## Post-Migration

After all 4 phases are deployed:
1. Trigger backfill: `POST /api/admin/team-identity/backfill`
2. Check mapping coverage: `GET /api/admin/team-identity/status`
3. Monitor Celery dashboard for task health
4. Update CLAUDE.md with new architecture (instructions in Phase 4)
