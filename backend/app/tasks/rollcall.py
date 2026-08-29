"""The daily ground-truth roll call (C-ROLLCALL-BUILD-1) — the beat.

Once a day this asks the outside world what fixtures exist, then asserts the
axiom Alex issued on 2026-08-26: for MLB, NBA, NHL, NFL, WNBA and the PGA/LPGA
tour, **every published fixture is in our product exactly once, with every
source we carry attached to it.** Not 95%. Not "up from last week". A gap is a
defect and it gets named, the same day it appears.

It exists because three separate incident classes were each found by a human who
happened to look: #1779/#1798/#1811 (games we never created), #2213 (41
duplicate MLB groups, one game rendering as forty-one cards), and the ingestion
outage `C-ROLLCALL-PREP-1` measured at ``0/15`` Kalshi game linkage on a full
MLB slate. Each was invisible for weeks and each was obvious in one table.

What it does NOT do, deliberately: it does not repair anything. Read-only
against events and markets; the only rows it writes are its own scorecard and
the GitHub issue the shared filing rail files for it. Applying a repair from a
detector is how a wrong detection becomes data loss (gotcha #21).

Truth sources — ESPN scoreboard for the team leagues, Datagolf for golf (Alex's
golf ruling: ESPN has no tour-event truth we can use). A truth read that FAILS
is a third state, never folded into "no fixtures": the league is reported
``truth_unavailable``, it does not count as graded, and the run's terminal falls
to ``partial`` so ``ENFORCED_TASKS`` sees it. Gotcha #53 in the detector.
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import date as _date, datetime, timedelta, timezone
from typing import Any

from app.utils.rollcall import (
    AXIOM_LEAGUES,
    FINGERPRINT_MARKER,
    MEASURED_DOMAINS,
    REDIS_KEY_TEMPLATE,
    REDIS_TTL_SECONDS,
    SCORECARD_SCHEMA,
    AxiomLeague,
    FixtureRow,
    axiom_is_red,
    axiom_offenders,
    baseline_verdict,
    build_rollcall_issue_body,
    build_rollcall_issue_title,
    coverage_percent,
    fixture_matches,
    rollcall_fingerprint,
    rollcall_terminal,
    score_fixtures,
)

logger = logging.getLogger(__name__)

#: Per-run wall-clock bound, comfortably inside the task's soft limit. A
#: sentinel that can run long is one that gets SIGKILLed mid-write.
DEADLINE_SECONDS = 480.0

#: Half-width of the window in which one of our events may satisfy a fixture.
#: 18h matches ``schedule_coverage``'s window so the two detectors cannot
#: disagree about what "today" means.
WINDOW_HOURS = 18

ESPN_TRUTH_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates={date}"
DATAGOLF_TRUTH_URL = "https://feeds.datagolf.com/get-schedule?tour={tour}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Truth reads
# ---------------------------------------------------------------------------


async def _espn_fixtures(league: AxiomLeague, day: str) -> list[dict[str, Any]]:
    """Today's published fixtures for an ESPN-truth league.

    Raises on a failed read — the caller turns that into ``truth_unavailable``
    rather than an empty slate.
    """
    from app.services.espn_api import ESPNAPIService

    service = ESPNAPIService()
    try:
        events = await service.get_scoreboard(
            league.truth_key, date=day.replace("-", "")
        )
    finally:
        close = getattr(service, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass
    out = []
    for ev in events:
        home = getattr(ev.home_team, "display_name", None) or getattr(
            ev.home_team, "name", ""
        ) if ev.home_team else ""
        away = getattr(ev.away_team, "display_name", None) or getattr(
            ev.away_team, "name", ""
        ) if ev.away_team else ""
        out.append({
            "espn_id": str(ev.espn_id),
            "home": home,
            "away": away,
            "kickoff": ev.date.isoformat() if getattr(ev, "date", None) else None,
            "label": f"{away} @ {home}".strip(),
        })
    return out


async def _datagolf_fixtures(league: AxiomLeague, day: str) -> list[dict[str, Any]]:
    """Tour events whose window contains ``day``.

    A golf "fixture" is a tournament, not a game: the event is live from its
    start date through its computed end date, so the day's slate is every tour
    event whose window covers today. An empty tour week is an off-day and is
    silent, exactly like an ESPN off-day.
    """
    from app.services.datagolf_api import DataGolfAPIService

    service = DataGolfAPIService()
    try:
        schedule = await service.get_schedule(tour=league.truth_key)
    finally:
        close = getattr(service, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass

    today = _date.fromisoformat(day)
    out = []
    for t in schedule:
        if not t.start_date:
            continue
        try:
            start = _date.fromisoformat(t.start_date)
            end = _date.fromisoformat(t.end_date) if t.end_date else start
        except ValueError:
            continue
        if start <= today <= end:
            out.append({
                "espn_id": None,
                "datagolf_event_id": t.event_id,
                "home": t.event_name or "",
                "away": "",
                "kickoff": t.start_date,
                "label": t.event_name or f"datagolf:{t.event_id}",
            })
    return out


# ---------------------------------------------------------------------------
# Our side
# ---------------------------------------------------------------------------


async def _our_events(session, sport_keys: tuple[str, ...], day: str) -> list[dict]:
    """Every event of these sports in the day's ±18h window, with linkage.

    One query per league, and the source columns are computed in SQL so the
    fixture loop never issues a query per fixture — a sentinel that scales with
    the slate is one that starts timing out in October.
    """
    from sqlalchemy import text

    day_noon = datetime.strptime(day, "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
    rows = (await session.execute(
        text("""
            SELECT e.id,
                   e.espn_id,
                   e.home_team_name,
                   e.away_team_name,
                   e.commence_time,
                   (e.espn_id IS NOT NULL
                    OR jsonb_typeof(e.win_probability_sources->'espn') = 'number')
                       AS has_espn,
                   (jsonb_typeof(e.win_probability_sources->'betting') = 'number')
                       AS has_odds_api,
                   EXISTS (SELECT 1 FROM futures_markets fm
                           WHERE fm.event_id = e.id AND fm.source = 'kalshi')
                       AS has_kalshi,
                   EXISTS (SELECT 1 FROM futures_markets fm
                           WHERE fm.event_id = e.id AND fm.source = 'polymarket')
                       AS has_polymarket
            FROM events e
            JOIN sports s ON s.id = e.sport_id
            WHERE s.key = ANY(:sport_keys)
              AND e.commence_time BETWEEN :lo AND :hi
        """),
        {
            "sport_keys": list(sport_keys),
            "lo": day_noon - timedelta(hours=WINDOW_HOURS),
            "hi": day_noon + timedelta(hours=WINDOW_HOURS),
        },
    )).mappings().all()
    return [dict(r) for r in rows]


def _attach(fixtures: list[dict], events: list[dict]) -> list[FixtureRow]:
    """Bind each truth fixture to the DB events that claim it.

    Two passes, and the rule between them is the whole correctness argument:

    * **An event carrying an ``espn_id`` is claimed by that id and by nothing
      else.** Its identity is already settled by an id-anchored correspondence,
      so the name pass must not be able to take it. Without this, two stamped
      rows for two different games — identical team names, a doubleheader or a
      series — both fall to whichever fixture the name loop reaches first, and
      the second fixture reads ``missing`` while the first reads ``dupes=2``.
      Two fabricated defects out of a healthy pair.
    * **An event with no id is claimed by name.** That is deliberate and it is
      the thing being hunted: an id-less duplicate must be VISIBLE (ruling 048 —
      a duplicate is visible and reversible, a wrong absorption is neither).

    A stamped row whose id is not on today's board is therefore claimed by
    nobody. That is honest: either it is an adjacent-day game inside the ±18h
    window, or its stamp is wrong — and a wrong stamp showing up as an
    unclaimed row beats it silently satisfying the wrong fixture.
    """
    by_espn: dict[str, list[dict]] = {}
    for ev in events:
        if ev.get("espn_id"):
            by_espn.setdefault(str(ev["espn_id"]), []).append(ev)
    nameable = [ev for ev in events if not ev.get("espn_id")]

    rows: list[FixtureRow] = []
    for fx in fixtures:
        claimed: list[dict] = []
        seen_ids: set[int] = set()
        if fx.get("espn_id"):
            for ev in by_espn.get(str(fx["espn_id"]), []):
                claimed.append(ev)
                seen_ids.add(ev["id"])
        for ev in nameable:
            if ev["id"] in seen_ids:
                continue
            if fixture_matches(
                ev.get("home_team_name") or "", ev.get("away_team_name") or "",
                fx.get("home") or "", fx.get("away") or "",
            ):
                claimed.append(ev)
                seen_ids.add(ev["id"])

        sources: dict[str, bool] = {}
        if len(claimed) == 1:
            ev = claimed[0]
            sources = {
                "kalshi": bool(ev.get("has_kalshi")),
                "polymarket": bool(ev.get("has_polymarket")),
                "espn": bool(ev.get("has_espn")),
                "odds_api": bool(ev.get("has_odds_api")),
            }
        rows.append(FixtureRow(
            label=fx.get("label") or "",
            kickoff=fx.get("kickoff"),
            event_ids=[e["id"] for e in claimed],
            sources=sources,
            truth_ref=fx.get("espn_id") or fx.get("datagolf_event_id"),
        ))
    return rows


# ---------------------------------------------------------------------------
# Durability
# ---------------------------------------------------------------------------


def _write_redis(day: str, payload: dict) -> bool:
    from app.tasks.redis_state import get_redis_client

    try:
        client = get_redis_client()
        if client is None:
            return False
        client.setex(
            REDIS_KEY_TEMPLATE.format(date=day), REDIS_TTL_SECONDS, json.dumps(payload)
        )
        return True
    except Exception as exc:
        logger.warning("rollcall: redis write failed for %s: %s", day, exc)
        return False


def read_redis_history(days: int = 30, before: str | None = None) -> list[dict]:
    """The trailing scorecards a measured domain's baseline is cut from.

    Reads whole days, newest first, skipping the day being graded. A missing day
    is simply absent — an off-day or a run that did not happen is not a zero.
    """
    from app.tasks.redis_state import get_redis_client

    out: list[dict] = []
    try:
        client = get_redis_client()
        if client is None:
            return out
        anchor = _date.fromisoformat(before) if before else _utc_now().date()
        for back in range(1, days + 1):
            key = REDIS_KEY_TEMPLATE.format(date=(anchor - timedelta(days=back)).isoformat())
            raw = client.get(key)
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except (TypeError, ValueError):
                continue
    except Exception as exc:
        logger.warning("rollcall: redis history read failed: %s", exc)
    return out


async def _write_scores(session, day: str, cards: list[dict]) -> int:
    """Upsert one row per ``(date, league)``. Idempotent by design.

    Written through Core SQL rather than ORM attribute assignment because the
    payload columns are JSONB (gotcha #4), and per-league so one malformed card
    cannot lose the whole day's record.
    """
    from sqlalchemy import text

    written = 0
    for card in cards:
        try:
            await session.execute(
                text("""
                    INSERT INTO rollcall_scores (
                        score_date, league, axiom, events_external, matched_1,
                        dupes, missing, clean, per_source, verdict, offenders,
                        justification, generated_at
                    ) VALUES (
                        :d, :league, :axiom, :ext, :m1, :dupes, :missing, :clean,
                        CAST(:per_source AS jsonb), :verdict, CAST(:offenders AS jsonb),
                        :justification, now()
                    )
                    ON CONFLICT (score_date, league) DO UPDATE SET
                        axiom = EXCLUDED.axiom,
                        events_external = EXCLUDED.events_external,
                        matched_1 = EXCLUDED.matched_1,
                        dupes = EXCLUDED.dupes,
                        missing = EXCLUDED.missing,
                        clean = EXCLUDED.clean,
                        per_source = EXCLUDED.per_source,
                        verdict = EXCLUDED.verdict,
                        offenders = EXCLUDED.offenders,
                        justification = EXCLUDED.justification,
                        generated_at = now()
                """),
                {
                    "d": day,
                    "league": card["league"],
                    "axiom": bool(card.get("axiom", True)),
                    "ext": int(card.get("events_external", 0) or 0),
                    "m1": int(card.get("matched_1", 0) or 0),
                    "dupes": int(card.get("dupes", 0) or 0),
                    "missing": int(card.get("missing", 0) or 0),
                    "clean": int(card.get("clean", 0) or 0),
                    "per_source": json.dumps(card.get("per_source") or {}),
                    "verdict": card.get("verdict", "unmeasurable"),
                    "offenders": json.dumps(card.get("offenders") or []),
                    "justification": card.get("justification"),
                },
            )
            await session.commit()
            written += 1
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "rollcall: score row failed for %s/%s: %s", day, card.get("league"), exc
            )
    return written


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


async def _grade_axiom_league(session, league: AxiomLeague, day: str) -> dict:
    """One league, isolated. A poison league never starves its siblings."""
    if league.truth == "datagolf":
        fixtures = await _datagolf_fixtures(league, day)
        truth_url = DATAGOLF_TRUTH_URL.format(tour=league.truth_key)
    else:
        from app.utils.sport_keys import SPORT_LEAGUE_MAP

        fixtures = await _espn_fixtures(league, day)
        path = SPORT_LEAGUE_MAP.get(league.truth_key, ("", ""))
        truth_url = ESPN_TRUTH_URL.format(
            sport=path[0], league=path[1], date=day.replace("-", "")
        )

    events = await _our_events(session, league.sport_keys, day)
    rows = _attach(fixtures, events)
    card = score_fixtures(rows, league.axiom_sources)
    offenders = axiom_offenders(rows, league.axiom_sources)
    red = axiom_is_red(card, league.axiom_sources)

    card.update({
        "league": league.key,
        "axiom": True,
        "axiom_sources": list(league.axiom_sources),
        "verdict": "off_day" if card["events_external"] == 0 else ("red" if red else "pass"),
        "offenders": offenders,
        "justification": "; ".join(league.exclusions) or None,
        "truth_url": truth_url,
        "truth": league.truth,
    })
    return card


async def _grade_measured_domain(session, domain, day: str, history: list[dict]) -> dict:
    """A partial domain, graded against its own trailing linkage rate.

    There is no external fixture list here (that is precisely why the domain is
    partial), so the measured quantity is our own linked-share: of the events we
    hold in the window, how many carry a prediction-market link. A 2σ drop from
    the trailing mean is the alarm.
    """
    events = await _our_events(session, domain.sport_keys, day)
    total = len(events)
    linked = sum(
        1 for e in events if e.get("has_kalshi") or e.get("has_polymarket")
    )
    today_rate = (linked / total) if total else None

    prior: list[float] = []
    for snap in history:
        for card in (snap.get("measured") or []):
            if card.get("league") == domain.key and card.get("rate") is not None:
                prior.append(float(card["rate"]))
    verdict, evidence = baseline_verdict(prior, today_rate)

    return {
        "league": domain.key,
        "axiom": False,
        "events_external": total,
        "matched_1": total,
        "dupes": 0,
        "missing": 0,
        "clean": linked,
        "per_source": {},
        "rate": today_rate,
        "verdict": "pass" if verdict == "pass" else ("red" if verdict == "drop" else "unmeasurable"),
        "baseline": evidence,
        "offenders": [],
        "justification": domain.justification,
    }


async def run_rollcall(
    date: str | None = None, file_issues: bool = True, now: datetime | None = None
) -> dict:
    """Grade the day's slate and publish the scorecard.

    Returns the payload written to Redis, plus a ``terminal`` the Celery wrapper
    hands to ``task_verdict``.
    """
    from app.tasks.base import get_task_session

    started = _time.monotonic()
    moment = now or _utc_now()
    day = date or moment.strftime("%Y-%m-%d")

    axiom_cards: list[dict] = []
    measured_cards: list[dict] = []
    truth_failures: list[dict] = []
    history = read_redis_history(before=day)

    async with get_task_session() as session:
        for league in AXIOM_LEAGUES:
            if _time.monotonic() - started > DEADLINE_SECONDS:
                truth_failures.append({"league": league.key, "error": "run deadline reached"})
                continue
            try:
                axiom_cards.append(await _grade_axiom_league(session, league, day))
            except Exception as exc:
                logger.warning("rollcall: %s truth read failed: %s", league.key, exc)
                truth_failures.append({"league": league.key, "error": str(exc)[:200]})
                axiom_cards.append({
                    "league": league.key, "axiom": True, "events_external": 0,
                    "matched_1": 0, "dupes": 0, "missing": 0, "clean": 0,
                    "per_source": {}, "verdict": "truth_unavailable",
                    "offenders": [], "justification": f"truth read failed: {str(exc)[:120]}",
                })

        for domain in MEASURED_DOMAINS:
            try:
                measured_cards.append(
                    await _grade_measured_domain(session, domain, day, history)
                )
            except Exception as exc:
                logger.warning("rollcall: %s baseline failed: %s", domain.key, exc)
                measured_cards.append({
                    "league": domain.key, "axiom": False, "events_external": 0,
                    "matched_1": 0, "dupes": 0, "missing": 0, "clean": 0,
                    "per_source": {}, "verdict": "unmeasurable", "offenders": [],
                    "justification": domain.justification,
                })

        graded = [c for c in axiom_cards if c["verdict"] != "truth_unavailable"]
        payload = {
            "schema": SCORECARD_SCHEMA,
            "date": day,
            "generated_at": moment.isoformat(),
            "axiom": axiom_cards,
            "measured": measured_cards,
            "truth_failures": truth_failures,
            "coverage_pct": coverage_percent(graded),
            "leagues_red": [c["league"] for c in axiom_cards + measured_cards
                            if c["verdict"] == "red"],
        }

        redis_ok = _write_redis(day, payload)
        rows_written = await _write_scores(session, day, axiom_cards + measured_cards)

    filings = []
    if file_issues:
        filings = _reconcile(day, axiom_cards)

    payload["redis_written"] = redis_ok
    payload["rows_written"] = rows_written
    payload["filings"] = filings
    payload["duration_s"] = round(_time.monotonic() - started, 2)
    payload["terminal"] = rollcall_terminal(
        leagues_graded=len(graded),
        leagues_expected=len(AXIOM_LEAGUES),
        truth_failures=len(truth_failures),
        mirror_written=rows_written == len(axiom_cards) + len(measured_cards),
    )
    logger.info(
        "rollcall %s: coverage=%s red=%s terminal=%s",
        day, payload["coverage_pct"], payload["leagues_red"], payload["terminal"],
    )
    return payload


def _reconcile(day: str, axiom_cards: list[dict]) -> list[dict]:
    """File or resolve ONE issue per league through the shared rail.

    ``truth_unavailable`` leagues are skipped in BOTH directions: a league we
    could not observe must not file (we have no evidence) and must not close an
    open issue (we have no evidence of recovery either).
    """
    from app.tasks.sentinel_filing import fetch_open_alert_issues, reconcile_issue

    open_issues = fetch_open_alert_issues()
    out = []
    for card in axiom_cards:
        if card["verdict"] == "truth_unavailable":
            out.append({"league": card["league"], "action": "skipped_truth_unavailable"})
            continue
        league = card["league"]
        offenders = card.get("offenders") or []
        red = card["verdict"] == "red"
        fp = rollcall_fingerprint(league, offenders)
        try:
            result = reconcile_issue(
                red=red,
                fingerprint=fp,
                marker_key=FINGERPRINT_MARKER,
                title=build_rollcall_issue_title(league, card),
                title_prefix=f"[rollcall] {league.upper()}:",
                body=build_rollcall_issue_body(
                    league, day, card, offenders, card.get("truth_url", ""),
                    card.get("axiom_sources") or [],
                    [card["justification"]] if card.get("justification") else [],
                ),
                red_body=build_rollcall_issue_body(
                    league, day, card, offenders, card.get("truth_url", ""),
                    card.get("axiom_sources") or [],
                    [card["justification"]] if card.get("justification") else [],
                ),
                green_comment=(
                    f"Roll call {day}: {league.upper()} is clean — "
                    f"{card.get('clean')}/{card.get('events_external')} fixtures with "
                    f"exactly one event and every axiom source linked."
                ),
                open_issues=open_issues,
            )
        except Exception as exc:  # one league's filing never sinks the run
            logger.warning("rollcall: filing failed for %s: %s", league, exc)
            result = {"action": "error", "error": str(exc)[:200]}
        result["league"] = league
        out.append(result)
    return out


async def _run_rollcall(date: str | None = None, file_issues: bool = True) -> dict:
    """Celery entry point. Kept thin so the logic above stays testable."""
    return await run_rollcall(date=date, file_issues=file_issues)
