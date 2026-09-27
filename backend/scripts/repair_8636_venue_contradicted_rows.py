"""#8636 — the rows the venue contradicts: volleyball matches leave the site, and six soccer games read their real competition.

THE SHIP. ``/search?q=italy`` at 390px on 2026-09-27 lists **UEFA NATIONS LEAGUE ·
Italy v Slovenia · No result reported · Sep 17** — a Volleyball European
Championship match. ``/events/15313706`` (Roma v Barcelona, Sep 30) is the
**women's** Champions League, and its page prints the MEN's Champions League
grid and Roma/Barcelona men's title odds under "Bigger Picture". The Copa
Argentina tie Platense v Estudiantes (Oct 1) is filed as an Argentina Primera
game, Lithuania v Andorra (a FIFA friendly, Sep 30) as the Nations League, and
Medellín v Millonarios (Colombia's Primera A) as the Copa Sudamericana. After
this runs, the volleyball rows are retired (``voided``, the status no surface
shows) and the six soccer rows sit where the venue lists them.

WHY THE ROWS ARE THERE. A Polymarket game market carries no ticker, so it is
minted on a family catch-all and #5576's placer relabels it with the league both
sides play in. Nothing read the venue's own word for the competition (the slug)
until #8636's forward fix (PR #8641), which refuses such a placement for NEW
rows. It said, in its own PR: "the 11 rows above are still mislabeled —
relabeling them is a production write and is a follow-up". This is that
follow-up, plus the volleyball class it exposed: Polymarket's ``Volleyball``
tag was unread, so a volleyball match was minted as whatever sport its names
suggested. The tag fix ships in the same PR (``_TAG_TO_CATEGORY``).

THE POPULATION, measured on production + Gamma 2026-09-27 ~11:40Z.

* Soccer: every Polymarket-born soccer row placed out of ``soccer_other`` in the
  last 60 days and not retired — 127 — read against the venue's league code
  (the stamped slug, else the linked group's Gamma slug): 116 agree, 11
  contradict. Exactly #8641's 11; none new since the fix went live. Five of the
  11 are volleyball and are handled below; the other SIX are pinned here.
* Volleyball: every Gamma event under ``tag_slug=volleyball`` (198, open and
  closed, back to 2025-11) joined to our markets by ``group_id``: 55 events of
  ours; 41 already ``voided``; the remaining 14 are pinned here.

Every pinned row is RE-QUALIFIED at apply time — still on the league it was
measured on, not retired, still linked to the measured venue event, and no
linked market's stamped slug names a different competition. Anything that no
longer qualifies is skipped and named, so the population can only shrink.

THE WRITES, one row at a time, each guarded on the value it was read with, the
pre-image banked first (first pre-image wins):

* volleyball: ``events.status`` -> ``voided``. Not deleted (``events`` has FK
  children); its markets stay linked — there is no real fixture of ours for
  them to move to, and a resolved market is not re-matched.
* soccer: ``events.sport_id`` -> the ONE league the venue's code names
  (``_league_for_polymarket_code``, the #5576 placer's reverse map: ``uwcl`` is
  the women's Champions League), else ``soccer_other`` — the row the create path
  would have kept since #8641. ``events.llm_league`` is rewritten from the new
  key by the enrichment's own ``classify_league``, so the stored league word
  stops naming the old competition.

``--restore`` puts back only rows still where this put them.

Runs only on ``bainluck-heavy`` (notice 47(c): runtime DDL, attended invocation):

    python3 scripts/repair_8636_venue_contradicted_rows.py            # dry run
    python3 scripts/repair_8636_venue_contradicted_rows.py --apply    # bank, write
    python3 scripts/repair_8636_venue_contradicted_rows.py --restore  # undo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCER_APP = "bainluck-heavy"
CATCH_ALL = "soccer_other"
BACKUP = "backup_8636_venue_contradicted"
RETIRED = "voided"
RETIRED_STATUSES = ("voided", "merged")
VOLLEYBALL = "Volleyball"

#: (event id, the league it was measured on, the Gamma event id it is linked
#: through, that event's slug, the venue's sport tag), 2026-09-27 ~11:40Z.
PINS: tuple[tuple[int, str, str, str, str], ...] = (
    # ── soccer, the competition the venue names (6)
    (15313706, "soccer_uefa_champs_league", "1034901", "uwcl-asr-fcb-2026-09-30", "Soccer"),
    (15314061, "soccer_uefa_nations_league", "1038099", "fif-lit-and-2026-09-30", "Soccer"),
    (15315626, "soccer_uefa_nations_league", "1049364", "u20wwc-ita-esp-2026-09-23", "Soccer"),
    (15316760, "soccer_conmebol_copa_sudamericana", "1058510",
     "col1-inm-mif-2026-08-11-more-markets", "Soccer"),
    (15317344, "soccer_germany_bundesliga", "1063975", "clf-vfb-fch-2026-09-25", "Soccer"),
    (15318598, "soccer_argentina_primera_division", "1078281",
     "argcopa-pla-elp-2026-10-01", "Soccer"),
    # ── volleyball, retired (14)
    (15179607, "baseball_other", "739849", "vbvnl-ita-usa-2026-07-30", VOLLEYBALL),
    (15179608, "baseball_other", "739852", "vbvnl-bra2-ita2-2026-07-25", VOLLEYBALL),
    (15179609, "baseball_other", "739846", "vbvnl-slo-tur-2026-07-29", VOLLEYBALL),
    (15185473, "baseball_other", "773372", "vbvnl-slo-pol2-2026-08-01", VOLLEYBALL),
    (15185724, "baseball_other", "773375", "vbvnl-jap2-usa-2026-08-01", VOLLEYBALL),
    (15291762, "soccer_other", "895375", "vbeuro-spa-aze-2026-08-23", VOLLEYBALL),
    (15291764, "soccer_other", "889576", "vbeuro-ita-mon-2026-08-22", VOLLEYBALL),
    (15291842, "soccer_other", "885437", "vbeuro-ger-slo-2026-08-22", VOLLEYBALL),
    (15314829, "soccer_uefa_nations_league", "1037990", "vbeuro-ser2-bel2-2026-09-17", VOLLEYBALL),
    (15314830, "soccer_uefa_nations_league", "1042636", "vbeuro-fin-gre2-2026-09-20", VOLLEYBALL),
    (15316005, "soccer_uefa_nations_league", "1037992", "vbeuro-ita2-slo4-2026-09-17", VOLLEYBALL),
    (15316006, "soccer_uefa_nations_league", "1037989", "vbeuro-slo3-gre2-2026-09-17", VOLLEYBALL),
    (15317150, "soccer_uefa_nations_league", "1037993", "vbeuro-ger2-bul2-2026-09-19", VOLLEYBALL),
    (15318806, "soccer_other", "1080303", "vb2bundesliga-tub-fc-2026-09-26", VOLLEYBALL),
)


def wrong_app_refusal() -> str | None:
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    return (
        f"refusing to run on HEROKU_APP_NAME={app!r}: this repair writes "
        f"production rows and runs only on {PRODUCER_APP!r}"
    )


def target_for(slug: str, venue_sport: str) -> tuple[str, str]:
    """What the venue's listing says to do with a pinned row: (action, value).

    ``("retire", "voided")`` for a sport we run no fixtures for; otherwise
    ``("relabel", <league key>)`` — the one league the venue's code names, else
    the catch-all. Pure, so the whole manifest is checked by the unit file.
    """
    from app.utils.venue_competition import (
        _league_for_polymarket_code,
        polymarket_league_code,
    )

    if venue_sport == VOLLEYBALL:
        return "retire", RETIRED
    code = polymarket_league_code(slug)
    if code is None:
        raise ValueError(f"{slug!r} is not a Polymarket game slug")
    return "relabel", _league_for_polymarket_code(code) or CATCH_ALL


def refusal(pin: tuple, event: dict | None, groups: set[str], stamped: set[str]) -> str | None:
    """Why this pinned row must NOT be written now, or None to write it.

    ``groups`` are the linked markets' ``group_id``s; ``stamped`` the league
    codes of their stamped slugs. Pure, so it is driven directly.
    """
    from app.utils.venue_competition import polymarket_league_code

    _event_id, measured_on, gamma_id, slug, _sport = pin
    if event is None:
        return "gone"
    if event["status"] in RETIRED_STATUSES:
        return f"already {event['status']!r}"
    if event["sport_key"] != measured_on:
        return f"now on {event['sport_key']!r}, not {measured_on!r}"
    if f"polymarket:{gamma_id}" not in groups:
        return f"no longer linked to Polymarket event {gamma_id}"
    code = polymarket_league_code(slug)
    if stamped - {code}:
        return f"a linked market's slug now names {sorted(stamped - {code})!r}"
    return None


async def _read_events(session) -> dict[int, dict]:
    res = await session.execute(
        text(
            "SELECT e.id, e.sport_id, s.key AS sport_key, e.status, e.llm_league, "
            "e.home_team_name, e.away_team_name "
            "FROM events e JOIN sports s ON s.id = e.sport_id WHERE e.id = ANY(:ids)"
        ),
        {"ids": [pin[0] for pin in PINS]},
    )
    return {r.id: dict(r._mapping) for r in res}


async def _links(session) -> tuple[dict[int, set[str]], dict[int, set[str]]]:
    from app.utils.venue_competition import POLYMARKET_EVENT_SLUG_KEY, polymarket_league_code

    res = await session.execute(
        text(
            "SELECT event_id, group_id, market_metadata FROM futures_markets "
            "WHERE event_id = ANY(:ids) AND source = 'polymarket'"
        ),
        {"ids": [pin[0] for pin in PINS]},
    )
    groups: dict[int, set[str]] = {}
    stamped: dict[int, set[str]] = {}
    for r in res:
        if r.group_id:
            groups.setdefault(r.event_id, set()).add(r.group_id)
        meta = r.market_metadata
        if isinstance(meta, str):
            meta = json.loads(meta)
        if isinstance(meta, dict):
            code = polymarket_league_code(meta.get(POLYMARKET_EVENT_SLUG_KEY))
            if code:
                stamped.setdefault(r.event_id, set()).add(code)
    return groups, stamped


async def _sport_ids(session) -> dict[str, int]:
    keys = sorted({target_for(p[3], p[4])[1] for p in PINS} - {RETIRED})
    res = await session.execute(
        text("SELECT id, key FROM sports WHERE key = ANY(:keys)"), {"keys": keys}
    )
    return {r.key: r.id for r in res}


async def plan(session) -> tuple[list[tuple[int, str, str]], list[str]]:
    """The pins that still qualify as (event id, action, value), and a line per skip."""
    events = await _read_events(session)
    groups, stamped = await _links(session)
    write: list[tuple[int, str, str]] = []
    skipped: list[str] = []
    for pin in PINS:
        event_id = pin[0]
        why = refusal(pin, events.get(event_id), groups.get(event_id, set()),
                      stamped.get(event_id, set()))
        if why:
            skipped.append(f"  skip {event_id}: {why}")
        else:
            write.append((event_id, *target_for(pin[3], pin[4])))
    return write, skipped


async def _apply(session, write, events, sport_ids) -> list[str]:
    from app.services.llm import classify_league

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP} (event_id bigint PRIMARY KEY, "
            "from_status text NOT NULL, to_status text NOT NULL, "
            "from_sport_id bigint NOT NULL, to_sport_id bigint NOT NULL, "
            "from_llm_league text, to_llm_league text, "
            "banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    out = []
    for event_id, action, value in write:
        ev = events[event_id]
        to_status, to_sport_id, to_league = ev["status"], ev["sport_id"], ev["llm_league"]
        if action == "retire":
            to_status = RETIRED
        else:
            to_sport_id = sport_ids[value]
            to_league = classify_league(
                f"{ev['away_team_name']} at {ev['home_team_name']}", value
            )
        # First pre-image wins: a re-run never overwrites what was banked.
        await session.execute(
            text(
                f"INSERT INTO {BACKUP} (event_id, from_status, to_status, from_sport_id, "
                "to_sport_id, from_llm_league, to_llm_league) VALUES (:id, :fs, :ts, "
                ":fsp, :tsp, :fl, :tl) ON CONFLICT (event_id) DO NOTHING"
            ),
            {"id": event_id, "fs": ev["status"], "ts": to_status, "fsp": ev["sport_id"],
             "tsp": to_sport_id, "fl": ev["llm_league"], "tl": to_league},
        )
        res = await session.execute(
            text(
                "UPDATE events SET status = :ts, sport_id = :tsp, llm_league = :tl "
                "WHERE id = :id AND status = :fs AND sport_id = :fsp "
                "AND llm_league IS NOT DISTINCT FROM :fl"
            ),
            {"id": event_id, "ts": to_status, "tsp": to_sport_id, "tl": to_league,
             "fs": ev["status"], "fsp": ev["sport_id"], "fl": ev["llm_league"]},
        )
        if res.rowcount != 1:
            raise RuntimeError(f"event {event_id} touched {res.rowcount} rows")
        what = RETIRED if action == "retire" else f"{value} ({to_league})"
        out.append(
            f"  {action}d {event_id} {ev['home_team_name']} v {ev['away_team_name']} "
            f"({ev['sport_key']}, {ev['status']}) -> {what}"
        )
    return out


async def _backup_exists(session) -> bool:
    res = await session.execute(text("SELECT to_regclass(:t)"), {"t": BACKUP})
    return res.scalar_one() is not None


async def _restore(session) -> int:
    if not await _backup_exists(session):
        return 0
    # Only rows still exactly where the repair put them: a row somebody has
    # since moved or re-statused is theirs.
    res = await session.execute(
        text(
            f"UPDATE events e SET status = b.from_status, sport_id = b.from_sport_id, "
            f"llm_league = b.from_llm_league FROM {BACKUP} b WHERE e.id = b.event_id "
            "AND e.status = b.to_status AND e.sport_id = b.to_sport_id "
            "AND e.llm_league IS NOT DISTINCT FROM b.to_llm_league"
        )
    )
    return res.rowcount


async def repair(session, mode: str) -> tuple[int, list[str]]:
    """``mode`` is ``dry``, ``apply`` or ``restore``. Returns (exit code, lines).

    Commits only on a clean apply or restore; every refusal writes nothing.
    """
    out: list[str] = []
    if mode == "restore":
        restored = await _restore(session)
        await session.commit()
        out.append(f"  restored {restored} event(s)")
        return 0, out

    sport_ids = await _sport_ids(session)
    needed = {target_for(p[3], p[4])[1] for p in PINS} - {RETIRED}
    missing = sorted(needed - set(sport_ids))
    if missing:
        out.append(f"REFUSED: no sports row for {missing!r}")
        return 2, out
    write, skipped = await plan(session)
    out.extend(skipped)
    for event_id, action, value in write:
        out.append(f"  {action} {event_id} -> {value}")
    if not write:
        out.append(f"\nnothing to write ({len(skipped)} skipped).")
        return 0, out
    retire = sum(1 for _, action, _ in write if action == "retire")
    if mode != "apply":
        out.append(
            f"\ndry run — nothing written. Would retire {retire}, relabel "
            f"{len(write) - retire}, skip {len(skipped)}."
        )
        return 0, out

    events = await _read_events(session)
    try:
        out.extend(await _apply(session, write, events, sport_ids))
    except Exception as exc:  # one transaction: any failure undoes all of it
        await session.rollback()
        out.append(f"ROLLED BACK: {exc}")
        return 1, out
    await session.commit()
    out.append(
        f"\n  applied: {retire} retired, {len(write) - retire} relabelled, "
        f"{len(skipped)} skipped (banked in {BACKUP})"
    )
    out.append("undo: python3 scripts/repair_8636_venue_contradicted_rows.py --restore")
    return 0, out


async def run(mode: str) -> int:
    refused = wrong_app_refusal()
    if refused:
        print(f"REFUSED: {refused}")
        return 2
    from app.tasks.base import get_task_session

    print(f"#8636 venue-contradicted rows — {mode.upper()}")
    async with get_task_session() as session:
        code, lines = await repair(session, mode)
    for line in lines:
        print(line)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="bank, write (default: dry run)")
    group.add_argument("--restore", action="store_true", help="undo from the banked rows")
    args = parser.parse_args()
    mode = "restore" if args.restore else ("apply" if args.apply else "dry")
    return asyncio.run(run(mode))


if __name__ == "__main__":
    raise SystemExit(main())
