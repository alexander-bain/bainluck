# CLI Prompts for Architecture Improvement

## Quick Start

1. Read `../architecture-improvement-plan.md` for the full reasoning and risk assessment
2. Do the manual steps below
3. Open 2 terminal windows and run Prompts 1 + 2 in parallel
4. After both complete, run Prompts 3 + 4 (can parallel)
5. After all complete, run Prompt 5

## Manual Steps (Do These First)

```bash
# In your frontend/ directory:
npx shadcn-ui@latest init
# When prompted: TypeScript=yes, style=New York, base color=Slate, CSS variables=yes

npm install framer-motion

npx shadcn-ui@latest add card badge button tooltip
```

## Execution Order

```
WEEK 1 (parallel):
  Terminal 1: 01-backend-cleanup.md    (~3-4 hours)
  Terminal 2: 02-frontend-design-system.md  (~2-3 hours)

WEEK 2 (after Week 1, can parallel):
  Terminal 3: 03-win-prob-charts.md    (~4-6 hours)
  Terminal 4: 04-futures-grouping.md   (~4-5 hours)

WEEK 2-3 (after all above):
  Terminal 5: 05-component-migration.md  (~3-4 hours)
```

## After Each Prompt

1. Review the changes (don't auto-commit)
2. Run the full test suite yourself
3. Check for any conflicts with other terminals
4. Commit with a descriptive message
5. Push to master (auto-deploys to Heroku + Vercel)

## If Something Breaks

- Prompt 1 Step 3 (name matching) is the highest risk — if tests fail, revert that step and proceed with the others
- Prompt 1 Step 1 (fangraphs rename) requires the Alembic migration to run on Heroku — if it fails, check the migration revision ID length (must be ≤32 chars)
- Frontend changes (Prompts 2, 5) are lowest risk — they don't affect the API
