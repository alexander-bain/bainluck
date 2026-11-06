# Ranking eval harness (#12095, Decide 37-B)

Every ranking change is scored against the family's grades before it ships.

- `slates/` — captured Discover slates, one JSON file each, saved by
  `python3 tools/ranking/grades.py fetch` from `GET /api/admin/ranking/slates/{ref}`.
  A slate holds the served order and up to 500 candidates with the features the
  ranker had (`backend/app/utils/ranking_eval.py`). Its `slate_id` is the feed's
  `edition` token, which impression and swipe events carry too.
- `grades/` — one file per grader per slate: `<date PT>-<surface>-<slate id>-<grader>.json`.
  Make it with `python3 tools/ranking/grades.py sheet --slate slates/<file>.json --grader alex`
  (add `--kid` for a non-expert grader, whose id is a pseudonym such as `kid1` — never
  a child's name: this directory is public), then fill every `grade` with
  `shareable`, `interesting` or `neither`, plus an optional `note`. Check it with
  `python3 tools/ranking/grades.py check grades/<file>.json`.

```json
{
  "slate_id": "ae0bc760eb204e34",
  "surface": "discover",
  "grader": "alex",
  "expert": true,
  "items": [
    {"position": 1, "item_key": "futures:68948432", "title": "...", "probability": 0.4, "grade": "shareable", "note": ""}
  ]
}
```

`"expert"` must be `true` or `false`; `false` marks a kid's grades (pseudonymous
grader id). They get their own NDCG line and never mix into the founder number.

Score a slate (and replay another ranker over its candidates):

```
python3 tools/ranking/scorecard.py --slate evals/ranking/slates/<file>.json \
    --slates-dir evals/ranking/slates --replay movement
```

No grades means NDCG is UNKNOWN, never 0.
