---
name: Discover / Ranking Quality
about: A feed quality miss, ranking opportunity, or ground-truth gap
title: ''
labels: area:discover-ranking,type:quality
assignees: ''
---

## Agent start protocol

Before editing files, claim this issue:

```bash
python3 scripts/claim_issue.py ISSUE_NUMBER "In Progress" --owner "<thread/context>"
```

Check existing `In Progress` Discover/ranking issues before touching `feed.py`, ranking utilities, or admin quality surfaces.

## What did the feed do?

Describe the bad or missing feed behavior.

## What should it have done?

Describe the desired ranking/discover outcome.

## Evidence

Screenshots, URLs, market names, admin debug output, or ground-truth examples:

## Likely class

- [ ] stale/completed market surfaced
- [ ] boring or low-signal market surfaced
- [ ] duplicate/repetitive story
- [ ] timely/interesting market missed
- [ ] bad image/logo/context
- [ ] personalization/repetition issue
- [ ] ground-truth ingestion issue

## Acceptance criteria

- [ ] Ranking/debug output explains the fix
- [ ] Relevant audit or admin quality page is checked
- [ ] Backlog/docs are updated if this changes policy
