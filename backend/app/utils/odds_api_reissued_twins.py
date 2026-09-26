"""Which of two Odds API rows is a fixture the provider re-issued. #8422.

**SHIP: /search?q=arsenal lists Fleetwood Town v Arsenal once, at the real
kick-off — not twice, 19 hours apart.** (Pillar: MATCHING.)

This is the JUDGEMENT half of a sweep and it touches no database and no
network. :mod:`app.tasks.odds_api_reissued_twin_sweep` reads the rows and the
provider's schedule, and writes the label.

WHAT THE DEFECT LOOKS LIKE
══════════════════════════

The Odds API sometimes re-issues a fixture under a NEW event id — typically
when a cup draw's placeholder date is replaced by the real kick-off. The old id
simply stops being listed. Our registry cannot know that at claim time: the new
id is a different id from the same provider, so ruling 048 correctly CREATES a
second row, and the old row sits ``scheduled`` at the placeholder time forever.

Production, 2026-09-25 01:45Z::

    15313977  Fleetwood Town v Arsenal  2026-10-28 15:00Z  odds_api:95b553f7…  first seen 09-17
    15314731  Fleetwood Town v Arsenal  2026-10-27 20:00Z  odds_api:29d04f0d…  first seen 09-18

``GET /v4/sports/soccer_england_efl_cup/events`` lists ``29d04f0d…`` and NOT
``95b553f7…``. The same read over every same-pair Odds API block in the next
45 days found nine such rows (three EFL Cup, four DFB-Pokal, one Greek Super
League) — and four blocks where BOTH ids are still listed.

WHY THIS IS ID-ANCHORED, NOT NAME-AND-TIME (ruling 048)
═══════════════════════════════════════════════════════

The pairing below uses names only to form a CANDIDATE block. What decides is
the provider's own schedule, keyed on the provider's own ids: the ghost's id no
longer dereferences in the schedule that issued it, and a sibling id for the
same pair does. That is gotcha #32's second arm — "the claim's id dereferencing
via its own provider's schedule" — read in the negative. The four blocks where
both ids are listed are REFUSED, not guessed at: two games between one pair
inside a few days is a real thing (a WNBA back-to-back, a two-legged tie), and
names and times cannot tell it from a re-issue.

WHY THE GHOST MUST BE THE OLDER ID
═════════════════════════════════

A re-issue replaces an old id with a new one. So, on the schedule alone, the
unlisted row must carry the EARLIER-first-seen id: a NEWER id the provider
dropped could be a game it added and withdrew, and "duplicate of" would then be
a false statement.

UNLESS ITS PRICES MOVED — #8755. The newer-id refusal was written for WNBA Lynx
v Liberty, ``15318133`` (Sep 26 00:30Z, unlisted) beside ``15318132`` (Sep 27
18:00Z, listed, ESPN 401918014), and it was wrong about that very block. The
ghost's one price — FanDuel ``-300/+235 · -7.5 · 173.5`` at 09-24 02:19Z — is on
the listed row, byte for byte, from 02:24Z on. The provider did not withdraw a
game; it split one sportsbook's listing onto a second id for eighteen minutes
and folded it back. Nobody retired the split row, so it went ``live`` at a
start that was never a start and served a two-day-old line as a live number.

So a newer-id ghost is labelled when :func:`lines_moved` holds: it held at
least one FULLY priced line (moneyline both sides, spread and total), and
every such line is on the listed sibling from the same sportsbook. One book
quoting the identical four numbers for two different games of one pair is not
a coincidence the label needs to survive; a partial (moneyline-only) capture is
too weak to count either way and is ignored. With no lines read, or one line
the sibling never held, the newer-id refusal stands exactly as before.

The label is ``provenance:duplicate-of:<canonical>``, whose read side
(:func:`app.utils.proven_duplicates.not_a_proven_duplicate`) already sits on
search, the league and team rails and the feed. Under-tagging is the intended
failure direction: every rule here refuses rather than guesses.

Refs #8422, #8755, #2693.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

#: Statuses a re-issued ghost can sit in. A retired row renders nothing; a live
#: or settled one is past the point where the provider's schedule is evidence.
OPEN_STATUSES = ("scheduled", "suspended")

#: The widest kick-off gap a re-issue has been measured to move a fixture. The
#: nine live specimens moved 19h–48h (a placeholder date replaced by the real
#: one); three days is the lag the soccer ghost judgement already uses.
MAX_REISSUE_GAP = timedelta(days=3)

#: Neither row may start sooner than this. ``/events`` drops a game once it is
#: over, so near kick-off "not listed" stops meaning "re-issued".
MIN_LEAD = timedelta(hours=1)


@dataclass(frozen=True)
class ReissueRow:
    """One Odds API-anchored event, as the planner needs it."""

    event_id: int
    sport_key: str
    home: str
    away: str
    commence_time: datetime
    status: str
    #: Every ``odds_api`` game anchor on the row — usually one. A row counts as
    #: LISTED when any of them is listed, so a row that holds both the old and
    #: the new id can never be read as its own ghost.
    odds_api_ids: frozenset[str]
    #: When the row's first ``odds_api`` game anchor was written — its age.
    first_seen_at: datetime
    #: Any game anchor from ANOTHER provider (espn_id, statpal_fixture_id, or a
    #: non-odds_api `game` row in `event_provider_anchors`). An independent
    #: authority vouching for the row outranks one provider dropping its id.
    other_anchor: bool
    already_tagged: bool


#: One sportsbook's FULLY priced line, as ``odds_snapshots`` stores it:
#: ``(bookmaker, home_ml, away_ml, home_spread, over_under)``, the two decimals as
#: the text Postgres renders them so both rows go through one spelling. #8755.
BookLine = tuple[str, int, int, str, str]


def lines_moved(ghost_lines: frozenset, canonical_lines: frozenset) -> bool:
    """Did every fully priced line the ghost held reappear on the sibling? #8755.

    Empty ghost lines answer False: no evidence is not evidence the prices
    moved, and the newer-id refusal must then stand.
    """
    return bool(ghost_lines) and ghost_lines <= canonical_lines


@dataclass(frozen=True)
class ReissueTag:
    duplicate_id: int
    canonical_id: int
    sport_key: str
    ghost_odds_api_ids: str  # comma-joined, sorted — the bank's column
    canonical_odds_api_ids: str


@dataclass
class ReissuePlan:
    tags: list[ReissueTag] = field(default_factory=list)
    refusals: list[dict] = field(default_factory=list)
    blocks_examined: int = 0


def pair_key(row: ReissueRow) -> tuple[str, str, str]:
    """The CANDIDATE block: one provider, one sport, one ordered pair of names.

    Exact names after case-folding, because both rows came from the same
    provider, which spells a team the same way every time. A fuzzy key would
    only widen the candidate set, and nothing downstream needs it wider.
    """
    return (row.sport_key, row.home.strip().casefold(), row.away.strip().casefold())


def candidate_blocks(rows: list[ReissueRow], *, now: datetime) -> list[list[ReissueRow]]:
    """Same-pair blocks of two or more open, future rows inside the gap.

    This is the set whose sports need a schedule read, so it is computed before
    any network call: a quiet pass reads nothing from the provider.
    """
    blocks: dict[tuple[str, str, str], list[ReissueRow]] = {}
    for row in rows:
        if row.status not in OPEN_STATUSES or row.commence_time < now + MIN_LEAD:
            continue
        blocks.setdefault(pair_key(row), []).append(row)
    out = []
    for members in blocks.values():
        if len(members) < 2:
            continue
        times = [m.commence_time for m in members]
        if max(times) - min(times) <= MAX_REISSUE_GAP:
            out.append(sorted(members, key=lambda m: m.event_id))
    return out


def plan_reissue_tags(
    blocks: list[list[ReissueRow]],
    schedules: dict[str, set[str]],
    book_lines: dict[int, frozenset] | None = None,
) -> ReissuePlan:
    """Decide each block against the provider's schedule for its sport.

    ``schedules`` maps a sport key to the ids ``/events`` listed on THIS pass.
    A sport absent from it was not read (or the read failed) and every block in
    it is refused — an unread schedule is not an empty one.

    ``book_lines`` maps a block member to its fully priced lines (#8755). It is
    consulted only for a ghost holding the NEWER id; a row absent from it has
    no lines, so the newer-id refusal stands.
    """
    book_lines = book_lines or {}
    plan = ReissuePlan()
    for block in blocks:
        plan.blocks_examined += 1
        sport = block[0].sport_key
        ids = [m.event_id for m in block]

        def refuse(reason: str) -> None:
            plan.refusals.append({"event_ids": ids, "sport_key": sport, "reason": reason})

        listed_ids = schedules.get(sport)
        if listed_ids is None:
            refuse("schedule_not_read")
            continue

        listed = [m for m in block if m.odds_api_ids & listed_ids]
        unlisted = [m for m in block if not m.odds_api_ids & listed_ids]
        if not unlisted:
            refuse("all_listed")  # two real games, or a provider twin: undecidable
            continue
        if len(listed) != 1:
            # Zero listed: the whole pair left the schedule, nothing to fold
            # onto. Two or more: which one did the ghost become?
            refuse("no_listed_canonical" if not listed else "several_listed")
            continue

        canonical = listed[0]
        if canonical.already_tagged:
            refuse("canonical_is_a_duplicate")
            continue
        for ghost in unlisted:
            if ghost.already_tagged:
                continue
            if ghost.other_anchor:
                refuse(f"ghost_{ghost.event_id}_has_another_authority")
                continue
            if ghost.first_seen_at >= canonical.first_seen_at and not lines_moved(
                book_lines.get(ghost.event_id, frozenset()),
                book_lines.get(canonical.event_id, frozenset()),
            ):
                refuse(f"ghost_{ghost.event_id}_is_the_newer_id")
                continue
            plan.tags.append(
                ReissueTag(
                    duplicate_id=ghost.event_id,
                    canonical_id=canonical.event_id,
                    sport_key=sport,
                    ghost_odds_api_ids=",".join(sorted(ghost.odds_api_ids)),
                    canonical_odds_api_ids=",".join(sorted(canonical.odds_api_ids)),
                )
            )
    return plan


def relisted_banked_ids(
    banked: dict[int, tuple[str, frozenset[str]]],
    schedules: dict[str, set[str]],
) -> list[int]:
    """Rows this sweep labelled whose own id the provider lists AGAIN.

    ``banked`` maps a labelled row to ``(sport_key, its odds_api ids)``. The
    label rested on one fact — the id had left the schedule — so when the id
    comes back, the fact is gone and the label is lifted. Without this a
    provider that briefly drops an id would hide a real game for good.
    Only a sport actually read this pass can lift anything.
    """
    return sorted(
        event_id
        for event_id, (sport, odds_ids) in banked.items()
        if sport in schedules and odds_ids & schedules[sport]
    )
