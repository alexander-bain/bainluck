# Post-release order: thin-chart retry before NFL round-up

**Alex priority ruling — October 7: bounded thin-chart retry is first after the iPhone/Watch release handback. No dispatch.**

PILLARS: TRUTH / DISCOVER / FORMATTING. SHIP: a reader who opens a cold futures page sees the available fuller history appear without reloading after its background fill completes.

**Order:** current iPhone/Watch release correction, integration and release handback → bounded web history retry (#7547 under #883) → NFL division round-up (#4463 / #10354 / #10357). The release retains priority over both. #10626's existing capture scope, timing and provenance contract are unchanged. This does not add a release requirement.

**Scope:** the smallest page-level fix already reviewed: use the existing fresh-fetch and cancellation support to retry while history filling is pending. Preserve the current chart and existing gap labels. Stop on completion, refusal, failure, navigation/unmount or a bounded time limit; also avoid work on hidden pages and overlapping loops. No Discover prefill, broad history rewrite, provider-budget expansion or fabricated points. Build remains HELD until explicit release handback and normal file-ownership coordination; no implementation starts or agent dispatch occurs now.

**Required before this slice is called done:**
1. A page opened cold shows the fuller chart without reload once filling completes, demonstrated on desktop web and phone-width web.
2. Refused or failed fills end quietly with the existing gap labels; an empty chart is never presented as if it were data.
3. No retry continues after the reader leaves the page: cancel scheduled retries and in-flight work, and do not apply stale responses.
4. Fable rechecks the same 21 pages from the preserved October 6 audit, reporting first-visit versus after-fill points and terminal refusal/failure/no-gain cases honestly. That is acceptance of this named ship, not a new recurring audit or dispatch now. Preserve the distinction between first request and known cold state; no cache purge is authorized merely to manufacture cold evidence.

The implementation allowance remains **1–2 engineering days**. The round-up therefore starts one completed retry slice later: plan **1–2 additional engineering days**, plus any remaining integration or Fable acceptance wait. The round-up's own **6–9 day** allowance is unchanged. No calendar start is promised until the release handback; completion of code alone does not pay the four acceptance items.

Existing priorities, owners and release gates otherwise remain unchanged; no labels, assignees, milestones or issue states are changed.

<!-- alex-thin-chart-priority-20261007 -->

GitHub ruling records:

- [#7547](https://github.com/alexander-bain/bainluck/issues/7547#issuecomment-6038829365)
- [#883](https://github.com/alexander-bain/bainluck/issues/883#issuecomment-6038829867)

Mirrored into the current local YOUR-TURN.md, artifacts/discovery-containers-release-plan/CURRENT-YOUR-TURN.md and PLAN.md, preserving their other sections. Those local coordination files remain live working records; GitHub is authoritative for ordering. No release handback is claimed by this scheduling record.
