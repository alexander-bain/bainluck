"""ESPN tennis results — the score behind a decided match (UX-P139, Alex's item 9).

    "Decided-match scores come from the ESPN API we already use for other
    scores — wire it; 'no data behind it' is not accepted."

UX-P138 built the seam and shipped it empty, and the report said so: nothing in
this codebase held the result of a tennis match, let alone its score.  That was
true of our own tables and it was the wrong place to have looked.  ESPN's
tennis scoreboard — the same ``site.api.espn.com`` host that already feeds
``sync_espn_live_events`` — carries the US Open in full, and it carries more
than we asked for.

MEASURED 2026-08-26, ``/sports/tennis/atp/scoreboard?dates=20260826``:

    event 189-2026 "US Open"
        grouping mens-singles    Men's Singles      239 competitions
        grouping womens-singles  Women's Singles    239
        grouping mens-doubles    Men's Doubles       63
        grouping womens-doubles  Women's Doubles     63
        grouping mixed-doubles   Mixed Doubles       21

Three things fall out of that shape, and each one answers a different item:

1. **The grouping slugs are the register's own ``draw`` vocabulary**, exactly —
   ``mens-singles`` / ``womens-singles``.  No mapping table, no gender
   inference, and nothing that touches ``llm_gender`` (dead) or
   ``llm_sport_category`` (which files every US Open match under table tennis).
2. **Per-set line scores with a winner flag**, plus ``round.displayName``
   ("Qualifying 1st Round"), so a decided match prints `6-3, 7-6` beside the
   name of whoever won it rather than a bare tick.
3. **Doubles and mixed doubles are already in the feed** (item 12).  No market
   exists for them yet on either source — censused 2026-08-26, zero US Open
   doubles markets platform-wide — but the RESULTS do, which is why
   ``DRAW_SLUGS`` lists all five and the parser does not filter.

THE JOIN, and the one rule it follows.  A result is matched to a register
matchup by the **unordered pair of normalized player names within a draw**, and
by nothing else.  Not by date (ESPN's competition date is the scheduled start
and a rain delay moves it), not by round (our register buckets all qualifying
into one ``qualifying`` while ESPN distinguishes three), and never by one name
alone.  Two players meet at most once in a knockout draw, so the pair is a key;
a single name is not, and a single-name join is how a first-round result lands
on a quarter-final card.

Read-only, and pure apart from the fetch: ``parse_results`` takes the decoded
payload so the whole join is testable without a network.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

ESPN_TENNIS_BASE = "https://site.api.espn.com/apis/site/v2/sports/tennis"

#: Both tours are fetched because the US Open appears under BOTH, carrying the
#: same event id and the same groupings.  Fetching one would be enough today
#: and would be a silent single point of failure the first time ESPN files a
#: women's draw only under `wta`.
TOURS = ("atp", "wta")

#: ESPN grouping slug -> register draw.  Identity for the two singles draws,
#: which is the point; the three doubles draws are carried so item 12's section
#: has real results the day a market for them appears.
DRAW_SLUGS: dict[str, str] = {
    "mens-singles": "mens-singles",
    "womens-singles": "womens-singles",
    "mens-doubles": "mens-doubles",
    "womens-doubles": "womens-doubles",
    "mixed-doubles": "mixed-doubles",
}

#: Only a FINAL competition yields a result.  An in-progress match has line
#: scores too, and printing them as a result would be the settled-means-settled
#: rule broken in the one direction that matters.
FINAL_STATES = ("post",)

#: The register's round vocabulary for a knockout draw, LARGEST FIRST.  Indexed
#: by draw size rather than hard-coded to a 128 field: a 64-slot doubles draw's
#: "Round 1" is `R64`, and reading it as `R128` would file every doubles fixture
#: one round too early for the rest of its life.
_KNOCKOUT_ROUNDS = ("R128", "R64", "R32", "R16", "QF", "SF", "F")

#: ESPN's own names for the rounds that are not "Round N".
_NAMED_ROUNDS: dict[str, str] = {
    "quarterfinal": "QF",
    "quarterfinals": "QF",
    "semifinal": "SF",
    "semifinals": "SF",
    "final": "F",
}

#: A competitor slot ESPN has filled with a placeholder rather than a person.
#: ``Bye`` is the core API's word and ``TBD`` the site API's for the same thing:
#: a main-draw slot reserved for a qualifier who has not qualified yet.  Both
#: also come back with a non-positive athlete id, which is the check that
#: actually runs — the names are here so the reason is legible.
PLACEHOLDER_NAMES = frozenset({"tbd", "bye", "qualifier", "lucky loser", ""})


def round_names_for_size(size: int) -> list[str]:
    """Register round keys for a knockout draw of ``size`` slots, largest first.

    ``256`` and anything not a power of two return ``[]`` rather than a
    best-effort guess: a draw whose size we cannot name is a draw whose rounds
    we cannot name, and filing a fixture under the wrong round is exactly the
    wrong-question defect the register exists to refuse.
    """
    if size < 2 or size & (size - 1):
        return []
    try:
        start = _KNOCKOUT_ROUNDS.index(f"R{size}")
    except ValueError:
        # 8, 4 and 2 are QF / SF / F, which have no `R` name.
        tail = {8: 4, 4: 5, 2: 6}.get(size)
        if tail is None:
            return []
        start = tail
    return list(_KNOCKOUT_ROUNDS[start:])


def espn_round_key(display_name: Any, *, draw_size: int) -> Optional[str]:
    """ESPN's ``round.displayName`` -> a register round key, or ``None``.

    Qualifying collapses to one bucket because the register has one: ESPN
    distinguishes three qualifying rounds and our draw does not, and inventing
    `Q1`/`Q2`/`Q3` keys to preserve a distinction nothing renders would be
    schema churn bought with nothing.
    """
    raw = str(display_name or "").strip().lower()
    if not raw:
        return None
    if raw.startswith("qual"):
        return "qualifying"
    if raw in _NAMED_ROUNDS:
        return _NAMED_ROUNDS[raw]
    if raw.startswith("round "):
        try:
            index = int(raw.split()[1]) - 1
        except (IndexError, ValueError):
            return None
        names = round_names_for_size(draw_size)
        if 0 <= index < len(names):
            return names[index]
    return None


def _competitor_view(competitor: dict[str, Any]) -> dict[str, Any]:
    """One side of an ESPN competition, as the draw ingest wants it.

    ``determined`` is the load-bearing field.  A main draw released before
    qualifying finishes carries real placeholder slots — measured 18 of 128 on
    the men's side and 16 on the women's, 2026-08-27 — and a placeholder is a
    FACT about the draw, not a gap in our read of it.  It is carried through
    rather than dropped so the fixture still says "somebody plays Jack Kennedy",
    which is true, instead of vanishing because half of it is unknown.
    """
    athlete = competitor.get("athlete") or {}
    name = str(athlete.get("displayName") or competitor.get("name") or "").strip()
    raw_id = str(competitor.get("id") or "")
    espn_id = int(raw_id) if raw_id.lstrip("-").isdigit() else None
    determined = (
        espn_id is not None
        and espn_id > 0
        and name.lower() not in PLACEHOLDER_NAMES
    )
    flag = athlete.get("flag") or {}
    return {
        "name": name,
        "espn_athlete_id": espn_id if determined else None,
        "flag_url": flag.get("href") if determined else None,
        "country": flag.get("alt") if determined else None,
        "determined": determined,
        "order": competitor.get("order"),
    }


def parse_draw(
    payloads: Iterable[dict[str, Any]],
    *,
    event_name: str,
    draws: Iterable[str] = ("mens-singles", "womens-singles"),
) -> dict[str, Any]:
    """Decoded ESPN scoreboards -> the tournament's real fixtures, by draw.

    THE DRAW IS A FIXTURE LIST, NOT A DRAW SHEET, and the distinction is the
    whole reason this function exists instead of a slot writer.

    ESPN publishes **who plays whom** — 64 first-round competitions a side,
    every one of them a fact about today's ceremony.  It does not publish the
    draw-sheet POSITION of those competitions, and the competition ids are
    ingest order, not bracket order (measured 2026-08-27: the men's list opens
    on an unseeded qualifier slot and Alcaraz is 37th, so it is demonstrably not
    the sheet).  Position is what says which first-round winner meets which, so
    writing ``draw_slot`` from this order would fabricate the second round while
    looking exactly like the first.

    So the ingest writes the pairings and leaves ``draw_slot`` null.  A pairing
    is checkable against any published draw; an invented position is not.
    """
    wanted = set(draws)
    by_draw: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    stats = {"events": 0, "competitions": 0, "fixtures": 0, "placeholder_slots": 0}

    for payload in payloads:
        for event in (payload or {}).get("events") or []:
            if event_name not in str(event.get("name") or ""):
                continue
            stats["events"] += 1
            for grouping in event.get("groupings") or []:
                slug = ((grouping.get("grouping") or {}).get("slug")) or ""
                draw = DRAW_SLUGS.get(slug)
                if draw is None or draw not in wanted:
                    continue
                competitions = grouping.get("competitions") or []
                # The draw's size, read off its own first round rather than
                # assumed. `Round 1` is `R128` only because there are 64 of it.
                first_round = [
                    c
                    for c in competitions
                    if str(((c.get("round") or {}).get("displayName")) or "").strip().lower()
                    == "round 1"
                ]
                draw_size = 2 * len(first_round)

                for competition in competitions:
                    comp_id = str(competition.get("id") or "")
                    # Both tours carry this event with the same competition ids.
                    if not comp_id or comp_id in seen:
                        continue
                    seen.add(comp_id)
                    stats["competitions"] += 1

                    round_key = espn_round_key(
                        (competition.get("round") or {}).get("displayName"),
                        draw_size=draw_size,
                    )
                    if round_key is None:
                        continue

                    competitors = sorted(
                        (competition.get("competitors") or []),
                        key=lambda c: c.get("order") or 0,
                    )
                    if len(competitors) != 2:
                        continue
                    sides = [_competitor_view(c) for c in competitors]
                    if not any(side["determined"] for side in sides):
                        # Both sides placeholders: a slot pair reserved for two
                        # qualifiers. Nothing to say and nobody to name.
                        continue
                    stats["placeholder_slots"] += sum(
                        1 for side in sides if not side["determined"]
                    )
                    stats["fixtures"] += 1
                    by_draw.setdefault(draw, []).append({
                        "espn_competition_id": comp_id,
                        "round": round_key,
                        "espn_round": (competition.get("round") or {}).get("displayName"),
                        "scheduled_at": competition.get("date"),
                        "state": ((competition.get("status") or {}).get("type") or {}).get("state"),
                        "draw_size": draw_size,
                        "players": sides,
                    })

    return {"draws": by_draw, "stats": stats}


def normalize_name(name: Any) -> str:
    """NFD-fold to a comparison key — the register's own rule, restated.

    Deliberately identical in behaviour to
    ``tournament_register.normalize_player_name`` composed with an NFD pass:
    spaces dropped, not just punctuation, because ESPN writes ``Felix
    Auger-Aliassime`` and Polymarket writes ``Felix Auger Aliassime``.
    """
    if not isinstance(name, str):
        return ""
    folded = unicodedata.normalize("NFD", name)
    return "".join(ch for ch in folded.lower() if ch.isalnum())


def pair_key(names: Iterable[str]) -> str:
    """The unordered normalized pair — the join key, and the only one."""
    return "|".join(sorted(normalize_name(name) for name in names if name))


def format_score(competitors: list[dict[str, Any]]) -> Optional[str]:
    """``6-3, 7-6`` — the winner's games first, set by set.

    Winner-first, always, so the score reads the same way the outcome does.  A
    card that says "Fearnley won" over "3-6, 6-7" is asking the reader to
    reverse it in their head, and half of them will not.

    ``None`` when the two competitors report different numbers of sets, which
    is a retirement or a mid-match read.  A partial score printed as a final one
    is the same class of defect as a stale price printed as live.
    """
    scored = [
        (c, [ls.get("value") for ls in (c.get("linescores") or [])])
        for c in competitors
    ]
    if len(scored) != 2:
        return None
    (a, a_sets), (b, b_sets) = scored
    if not a_sets or len(a_sets) != len(b_sets):
        return None
    if any(v is None for v in (*a_sets, *b_sets)):
        return None

    winner_first = scored if a.get("winner") else [scored[1], scored[0]]
    (_w, w_sets), (_l, l_sets) = winner_first
    return ", ".join(
        f"{int(w)}-{int(l)}" for w, l in zip(w_sets, l_sets)
    )


def parse_results(payloads: Iterable[dict[str, Any]], *, event_name: str) -> dict[str, Any]:
    """Decoded ESPN scoreboards -> ``{draw: {pair_key: result}}``.

    ``event_name`` selects the tournament out of a scoreboard that also carries
    whatever else is on that week ("Winston-Salem Open", "Abierto GNP
    Seguros").  An exact-substring test rather than a fuzzy one: this module is
    on the same page as the register and inherits its posture — a tournament is
    served because somebody named it, never because a scorer picked it.
    """
    by_draw: dict[str, dict[str, Any]] = {}
    seen_competitions: set[str] = set()
    stats = {"events": 0, "competitions": 0, "final": 0, "scored": 0, "unpaired": 0}

    for payload in payloads:
        for event in (payload or {}).get("events") or []:
            if event_name not in str(event.get("name") or ""):
                continue
            stats["events"] += 1
            for grouping in event.get("groupings") or []:
                slug = ((grouping.get("grouping") or {}).get("slug")) or ""
                draw = DRAW_SLUGS.get(slug)
                if draw is None:
                    continue
                for competition in grouping.get("competitions") or []:
                    # Both tours return the same competition ids for this
                    # event, so the second tour is a duplicate pass. Counted
                    # once.
                    comp_id = str(competition.get("id"))
                    if comp_id in seen_competitions:
                        continue
                    seen_competitions.add(comp_id)
                    stats["competitions"] += 1

                    status = ((competition.get("status") or {}).get("type") or {})
                    if status.get("state") not in FINAL_STATES:
                        continue
                    stats["final"] += 1

                    competitors = competition.get("competitors") or []
                    names = [
                        ((c.get("athlete") or {}).get("displayName") or "")
                        for c in competitors
                    ]
                    if len([n for n in names if n]) != 2:
                        # A doubles competition names a TEAM, not an athlete, in
                        # some ESPN payloads. Counted rather than dropped so the
                        # doubles section's coverage is a number and not a
                        # shrug.
                        stats["unpaired"] += 1
                        continue

                    winner = next(
                        (
                            (c.get("athlete") or {}).get("displayName")
                            for c in competitors
                            if c.get("winner")
                        ),
                        None,
                    )
                    by_draw.setdefault(draw, {})[pair_key(names)] = {
                        "score": format_score(competitors),
                        "winner_name": winner,
                        "winner_normalized": normalize_name(winner),
                        "players": names,
                        "espn_competition_id": comp_id,
                        "espn_round": (competition.get("round") or {}).get("displayName"),
                        "completed_at": competition.get("date"),
                        "status_detail": status.get("detail"),
                    }
                    if by_draw[draw][pair_key(names)]["score"]:
                        stats["scored"] += 1

    return {"draws": by_draw, "stats": stats}


async def fetch_tournament_results(
    event_name: str, *, dates: Optional[str] = None
) -> dict[str, Any]:
    """Fetch and parse both tours' scoreboards for one tournament.

    ``dates`` is ESPN's ``YYYYMMDD``; omitted, the scoreboard returns the
    current day, which is what a live tournament wants.  A tour that fails to
    fetch contributes nothing and is REPORTED — an empty result set from a
    timed-out request must never read as "no matches have finished" (gotcha
    #53).
    """
    import httpx

    payloads: list[dict[str, Any]] = []
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for tour in TOURS:
            url = f"{ESPN_TENNIS_BASE}/{tour}/scoreboard"
            try:
                response = await client.get(
                    url, params={"dates": dates} if dates else None
                )
                response.raise_for_status()
                payloads.append(response.json())
            except Exception as exc:  # noqa: BLE001 — reported, never silent
                errors.append(f"{tour}: {exc}")

    result = parse_results(payloads, event_name=event_name)
    result["errors"] = errors
    result["tours_fetched"] = len(payloads)
    return result


def fetch_scoreboards(dates: Optional[str] = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Both tours' scoreboards, synchronously — for the offline ingest scripts.

    ``fetch_tournament_results`` is the async path the Celery task uses.  The
    draw ingest is a one-shot command run by an agent on ceremony day, and an
    event loop bought nothing there but a way to get the error handling subtly
    different.  Returns ``(payloads, errors)`` so a caller can tell "no
    tournament today" from "both requests failed" — gotcha #53.
    """
    import httpx

    payloads: list[dict[str, Any]] = []
    errors: list[str] = []
    for tour in TOURS:
        url = f"{ESPN_TENNIS_BASE}/{tour}/scoreboard"
        try:
            response = httpx.get(
                url, params={"dates": dates} if dates else None, timeout=30.0
            )
            response.raise_for_status()
            payloads.append(response.json())
        except Exception as exc:  # noqa: BLE001 — reported, never silent
            errors.append(f"{tour}: {exc}")
    return payloads, errors
