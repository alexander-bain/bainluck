"""#9387 — `representation=verified_title` on the NFL title detail and chart.

THE SHIP. The NFL title detail shows one supported current probability with
accurate contributors, while its chart labels authentic source history.

Everything here runs through the REAL route functions (`get_futures_market`,
`get_probability_timeline`) on a session that answers each statement by what
it selects, so the resolver's own reads are exercised, not stubbed. Only the
IO helpers the default route already owns (book provenance, withholding arms,
fleet clock, venue history) are pinned, exactly as their own suites do.

THE FIXTURE TRIO (test ids only — the resolver hardcodes none of them), from
Authority's 2026-10-02T16:20Z readback (#9387 comment 5956494541):

  86832   odds_api    americanfootball_nfl_super_bowl_winner, current event
                      270f600435a20d2046a59fc89fe8e9b8, commence 2027-02-14T23:35Z,
                      polled 2026-10-02T12:36:27.740Z, every outcome refreshed then
  40533   kalshi      KXSB-27, expected expiration 2027-02-14T23:30Z
                      (commence_time 2029-02-13 is the tail rule)
  129037  polymarket  event 202857, slug pro-football-2027-champion-…, no-winner
                      cutoff 2027-04-01T03:59Z (`Other`)
"""

from __future__ import annotations

import copy
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

import app.routes.futures as futures_routes
import app.utils.futures_market_snapshot as snapshot_utils
import app.utils.hook_staleness as hook_staleness
from app.models import FuturesMarket, FuturesOddsSnapshot, Team
from app.routes.futures import get_futures_market, get_probability_timeline
from app.utils import probability_to_american
from app.utils.futures_verified_title import (
    ANCHOR_MAX_AGE,
    CONTRIBUTOR_SOURCES,
    NFL_TITLE,
)

#: Authority's readback minute; every reader on the path is pinned to it.
NOW = datetime(2026, 10, 2, 16, 20, tzinfo=timezone.utc)
POLLED = datetime(2026, 10, 2, 12, 36, 27, 740202, tzinfo=timezone.utc)
KALSHI_AT = datetime(2026, 10, 2, 7, 54, 47, 255493, tzinfo=timezone.utc)
PM_AT = datetime(2026, 10, 2, 11, 50, 29, 207848, tzinfo=timezone.utc)
PM_OTHER_AT = datetime(2026, 5, 12, 16, 16, 38, 670166, tzinfo=timezone.utc)

ODDS_ID, KALSHI_ID, PM_ID = 86832, 40533, 129037
EIGHT_BOOKS = [
    "BetMGM", "BetRivers", "Caesars", "DraftKings",
    "FanDuel", "Fanatics", "bet365", "BetOnline.ag",
]

_CLOCK_READERS = (futures_routes, snapshot_utils, hook_staleness)


@contextmanager
def _at(instant: datetime = NOW):
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant if tz is None else instant.astimezone(tz)

    with ExitStack() as stack:
        for module in _CLOCK_READERS:
            stack.enter_context(patch_attr(module, "datetime", _Frozen))
        yield


@contextmanager
def patch_attr(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


# ── fixtures ─────────────────────────────────────────────────────────────────

ROSTER = [
    {"id": 1, "name": "Buffalo Bills", "abbreviation": "BUF", "location": "Buffalo",
     "alternate_names": []},
    {"id": 2, "name": "Los Angeles Rams", "abbreviation": "LAR", "location": "Los Angeles",
     "alternate_names": ["Los Angeles"]},
    {"id": 3, "name": "Los Angeles Chargers", "abbreviation": "LAC", "location": "Los Angeles",
     "alternate_names": ["Los Angeles"]},
    {"id": 4, "name": "Kansas City Chiefs", "abbreviation": "KC", "location": "Kansas City",
     "alternate_names": []},
    {"id": 5, "name": "San Francisco 49ers", "abbreviation": "SF", "location": "San Francisco",
     "alternate_names": []},
    {"id": 6, "name": "New York Giants", "abbreviation": "NYG", "location": "New York",
     "alternate_names": ["New York"]},
    {"id": 7, "name": "New York Jets", "abbreviation": "NYJ", "location": "New York",
     "alternate_names": ["New York"]},
]


def _outcome(oid, name, prob, at, *, external_id=None, opening=None, change=None):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=external_id or f"x-{oid}",
        current_probability=prob,
        current_american_odds=probability_to_american(prob) if prob else None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=change,
        opening_probability=opening,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=at,
        price_changed_at=at,
        team_id=None,
        team=None,
        current_yes_bid=None,
        current_yes_ask=None,
    )


def _market(mid, source, external_id, name, outcomes, *, metadata=None,
            resolution_date=None, commence_time=None, status="open", me=True,
            hook=None, **extra):
    return SimpleNamespace(
        **extra,
        id=mid,
        name=name,
        description=None,
        category="championship",
        source=source,
        external_id=external_id,
        status=status,
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=1,
        llm_sport_category="football",
        mutually_exclusive=me,
        commence_time=commence_time,
        resolution_date=resolution_date,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key="football::championship:2027",
        hook_description=hook,
        image_url=None,
        category_tags=["football"],
        market_metadata=metadata,
        outcomes=outcomes,
    )


def _anchor(**over):
    anchor = {
        "scope": "current_quotes_only",
        "event_id": "270f600435a20d2046a59fc89fe8e9b8",
        "polled_at": POLLED.isoformat(),
        "sport_key": "americanfootball_nfl_super_bowl_winner",
        "commence_time": "2027-02-14T23:35:00+00:00",
    }
    anchor.update(over)
    return anchor


ODDS_ROWS = [  # id, name, probability
    (1309486, "Buffalo Bills", 0.112913),
    (1309485, "Los Angeles Rams", 0.107361),
    (1309494, "San Francisco 49ers", 0.083701),
    (1309490, "Kansas City Chiefs", 0.080000),
    (1309499, "Los Angeles Chargers", 0.030000),
    (1309501, "New York Giants", 0.020000),
    (1309502, "New York Jets", 0.015000),
]
KALSHI_ROWS = [  # id, name, ticker, probability
    (643833, "Buffalo", "KXSB-27-BUF", 0.13),
    (643828, "Los Angeles R", "KXSB-27-LAR", 0.105),
    (643829, "San Francisco", "KXSB-27-SF", 0.11),
    (643836, "Kansas City", "KXSB-27-KC", 0.085),
    (643832, "Los Angeles C", "KXSB-27-LAC", 0.03),
    (643840, "New York G", "KXSB-27-NYG", 0.02),
    (643841, "New York J", "KXSB-27-NYJ", 0.015),
]
PM_ROWS = [  # id, name, probability
    (1709101, "Buffalo Bills", 0.135),
    (1709100, "Los Angeles Rams", 0.105),
    (1709109, "San Francisco 49ers", 0.0865),
    (1709102, "Kansas City Chiefs", 0.0865),
    (1709111, "Los Angeles Chargers", 0.03),
    (1709112, "New York Giants", 0.02),
    (1709113, "New York Jets", 0.015),
]
PM_OTHER_ID = 69775323


def odds_market(*, anchor="default", rows=ODDS_ROWS, at=POLLED, meta_extra=None, **kw):
    meta = {"odds_api_current_event": _anchor() if anchor == "default" else anchor}
    if anchor is None:
        meta = {}
    meta.update(meta_extra or {})
    return _market(
        ODDS_ID, "odds_api", "americanfootball_nfl_super_bowl_winner",
        "NFL Super Bowl Winner",
        [_outcome(i, n, p, at, opening=p / 2, change=0.01) for i, n, p in rows],
        metadata=meta, **kw,
    )


def kalshi_market(*, mid=KALSHI_ID, ticker="KXSB-27", rows=KALSHI_ROWS,
                  resolution_date=datetime(2027, 2, 14, 23, 30, tzinfo=timezone.utc), **kw):
    return _market(
        mid, "kalshi", ticker, "2027 Pro Football Champion",
        [_outcome(i, n, p, KALSHI_AT, external_id=t) for i, n, t, p in rows],
        metadata={"kalshi_event_ticker": ticker, "competition": "Pro Football"},
        resolution_date=resolution_date,
        commence_time=datetime(2029, 2, 13, 23, 30, tzinfo=timezone.utc),
        **kw,
    )


def pm_market(*, mid=PM_ID, event_id="202857",
              slug="pro-football-2027-champion-20260729185915366", rows=PM_ROWS,
              resolution_date=datetime(2027, 4, 1, 3, 59, tzinfo=timezone.utc), **kw):
    outcomes = [_outcome(i, n, p, PM_AT, external_id=f"0x{i:x}") for i, n, p in rows]
    outcomes.append(_outcome(PM_OTHER_ID, "Other", None, PM_OTHER_AT, external_id="0xother"))
    return _market(
        mid, "polymarket", event_id, "Pro Football: 2027 Champion", outcomes,
        metadata={
            "neg_risk": True,
            "polymarket_event_id": event_id,
            "polymarket_event_slug": slug,
        },
        resolution_date=resolution_date,
        **kw,
    )


def same_key_negatives():
    """Rows sharing `football::championship:2027` that ask OTHER questions.

    Each carries a Buffalo row priced far from the title, so wrongly admitting
    any one of them makes its venue ambiguous and visibly moves the answer.
    """
    return [
        _market(  # Kalshi MVP — person outcomes
            900001, "kalshi", "KXNFLMVP-27", "2027 Pro Football MVP",
            [_outcome(900011, "Josh Allen", 0.30, KALSHI_AT, external_id="KXNFLMVP-27-JALLEN")],
            metadata={"kalshi_event_ticker": "KXNFLMVP-27"},
            resolution_date=datetime(2027, 2, 10, tzinfo=timezone.utc),
        ),
        _market(  # Kalshi playoff qualifier — a Buffalo leg at 85%
            900002, "kalshi", "KXNFLPLAYOFF-27", "Pro Football Playoff Qualifiers",
            [_outcome(900012, "Buffalo", 0.85, KALSHI_AT, external_id="KXNFLPLAYOFF-27-BUF")],
            metadata={"kalshi_event_ticker": "KXNFLPLAYOFF-27"},
            resolution_date=datetime(2027, 1, 5, tzinfo=timezone.utc),
        ),
        _market(  # Polymarket coach of the year
            900003, "polymarket", "300001", "Pro Football: 2027 Coach of the Year",
            [_outcome(900013, "Sean McDermott", 0.2, PM_AT)],
            metadata={"polymarket_event_id": "300001",
                      "polymarket_event_slug": "pro-football-2027-coach-of-the-year-1"},
            resolution_date=datetime(2027, 2, 10, tzinfo=timezone.utc),
        ),
        _market(  # Polymarket playoff qualifier — a Buffalo leg at 85%
            900004, "polymarket", "300002", "Pro Football: 2027 Playoff Teams",
            [_outcome(900014, "Buffalo Bills", 0.85, PM_AT)],
            metadata={"polymarket_event_id": "300002",
                      "polymarket_event_slug": "pro-football-2027-champion-playoffs"},
            resolution_date=datetime(2027, 1, 5, tzinfo=timezone.utc),
        ),
    ]


# ── the session ──────────────────────────────────────────────────────────────


class _Result:
    def __init__(self, rows=(), one=None):
        self._rows = list(rows)
        self._one = one

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def unique(self):
        return self

    def scalar_one_or_none(self):
        return self._one


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def _loads(stmt) -> dict[str, str]:
    """Each eager load the statement asks for, as `outcomes.team -> selectin`."""
    out = {}
    for opt in getattr(stmt, "_with_options", ()):
        for element in getattr(opt, "context", ()):
            path = ".".join(prop.key for prop in element.path.path[1::2])
            out[path] = dict(element.strategy)["lazy"]
    return out


class _DB:
    """Answers each statement by WHAT IT SELECTS, never by call position.

    The candidate read returns every other market — a superset, as the real
    query is allowed to be — so membership is proved by the resolver's own
    rules, not by the fixture filtering for it.
    """

    def __init__(self, markets, roster=ROSTER, snapshots=()):
        self.markets = {m.id: m for m in markets}
        self.roster = roster
        self.snapshots = list(snapshots)
        self.kinds: list[str] = []
        #: (kind, postgres SQL, {relationship path: load strategy}) per statement.
        self.statements: list[tuple[str, str, dict[str, str]]] = []
        self.fail_on: str | None = None

    async def execute(self, stmt, *_a, **_k):
        descs = stmt.column_descriptions
        entities = {d.get("entity") for d in descs}
        params = stmt.compile().params
        if FuturesOddsSnapshot in entities:
            kind = "snapshots"
        elif Team in entities:
            kind = "roster"
        elif len(descs) == 1 and descs[0].get("name") == "FuturesMarket":
            kind = "members" if any(isinstance(v, (list, tuple)) for v in params.values()) else "market"
        elif FuturesMarket in entities:
            kind = "candidates"
        else:
            raise AssertionError(f"unexpected statement: {stmt}")
        self.kinds.append(kind)
        self.statements.append((kind, _sql(stmt), _loads(stmt)))
        if kind == self.fail_on:
            raise RuntimeError("database went away")
        if kind == "snapshots":
            return _Result(self.snapshots)
        if kind == "roster":
            return _Result([SimpleNamespace(**t) for t in self.roster])
        if kind == "market":
            (mid,) = [v for v in params.values() if isinstance(v, int)]
            return _Result(one=self.markets.get(mid))
        if kind == "members":
            (ids,) = [v for v in params.values() if isinstance(v, (list, tuple))]
            return _Result([self.markets[i] for i in ids if i in self.markets])
        excluded = [v for v in params.values() if isinstance(v, int)]
        return _Result([m for mid, m in self.markets.items() if mid not in excluded])


class _NoVenue:
    applicable = False
    thin_basis = None

    def in_window(self, *_a, **_k):
        return []


@pytest.fixture(autouse=True)
def _route_io(monkeypatch):
    async def _sources(_db, market_id, _ids):
        return (list(EIGHT_BOOKS), []) if market_id == ODDS_ID else ([], [])

    async def _nothing(*_a, **_k):
        return set()

    async def _none(*_a, **_k):
        return None

    async def _no_sides(*_a, **_k):
        return {}

    async def _venue(*_a, **_k):
        return _NoVenue()

    monkeypatch.setattr(futures_routes, "_load_market_sources", _sources)
    monkeypatch.setattr(futures_routes, "_withheld_price_outcome_ids", _nothing)
    monkeypatch.setattr(futures_routes, "_fleet_newest_observation", _none)
    monkeypatch.setattr(futures_routes, "_game_container_leg_sides", _no_sides)
    monkeypatch.setattr(futures_routes, "_game_container_lead_leg", _none)
    monkeypatch.setattr(futures_routes, "_game_container_of_event_id", _none)
    monkeypatch.setattr(futures_routes, "_load_generic_venue_history", _venue)
    monkeypatch.setattr(futures_routes, "_consider_generic_history_fill", _none)


def trio(*, odds=None, kalshi=None, pm=None, extra=()):
    return [
        odds if odds is not None else odds_market(),
        kalshi if kalshi is not None else kalshi_market(),
        pm if pm is not None else pm_market(),
        *same_key_negatives(),
        *extra,
    ]


def snapshots_for(market):
    snaps = []
    for k, hours in enumerate((5, 3, 1)):
        for o in market.outcomes:
            if o.current_probability is None:
                continue
            snaps.append(SimpleNamespace(
                outcome_id=o.id,
                probability=round(o.current_probability * (0.9 + 0.05 * k), 6),
                captured_at=NOW - timedelta(hours=hours),
                bookmaker="DraftKings",
            ))
    return snaps


async def detail(mid, markets, representation=None, **db_kw):
    db = _DB(markets, **db_kw)
    with _at():
        if representation is None:
            payload = await get_futures_market(mid, db=db)
        else:
            payload = await get_futures_market(mid, representation=representation, db=db)
    return payload, db


async def timeline(mid, markets, representation=None, top=10):
    requested = next(m for m in markets if m.id == mid)
    db = _DB(markets, snapshots=snapshots_for(requested))
    with _at():
        if representation is None:
            payload = await get_probability_timeline(market_id=mid, top=top, hours=168, db=db)
        else:
            payload = await get_probability_timeline(
                market_id=mid, top=top, hours=168, representation=representation, db=db
            )
    return payload, db


def by_name(payload, name, key="outcomes"):
    return next(o for o in payload[key] if o["name"] == name)


NEW_DETAIL_KEYS = {"representation", "question_identity", "contributing_sources"}
NEW_OUTCOME_KEYS = {"contributing_sources", "observed_at", "aggregation_rule"}
VERIFIED = "verified_title"


def _why(payload):
    return f"served {payload.get('representation')!r}, fallback {payload.get('representation_fallback')!r}"


# ── 1. the trio ──────────────────────────────────────────────────────────────


class TestTheTrioServesOneVerifiedNumber:
    async def test_the_sportsbook_detail_serves_the_three_venue_answer(self):
        payload, _ = await detail(ODDS_ID, trio(), VERIFIED)
        assert payload["representation"] == VERIFIED, _why(payload)
        assert payload["question_identity"] == {
            "competition": "NFL",
            "edition": "2027",
            "question": "league_championship_winner",
        }
        assert payload["contributing_sources"] == ["odds_api", "kalshi", "polymarket"]
        buf = by_name(payload, "Buffalo Bills")
        # Three venues, equal weight under the existing blend: the middle one.
        assert buf["probability"] == pytest.approx(0.13 / 0.4715, abs=1e-8)
        assert buf["american_odds"] == probability_to_american(0.13)
        assert buf["contributing_sources"] == ["odds_api", "kalshi", "polymarket"]
        assert buf["aggregation_rule"] == "weighted_median"
        assert buf["observed_at"] == KALSHI_AT.isoformat(), "the OLDEST included observation"
        rams = by_name(payload, "Los Angeles Rams")
        assert rams["probability"] == pytest.approx(0.105 / 0.4715, abs=1e-8)

    async def test_every_venue_page_serves_the_same_answer_on_its_own_rows(self):
        odds, _ = await detail(ODDS_ID, trio(), VERIFIED)
        kalshi, _ = await detail(KALSHI_ID, trio(), VERIFIED)
        pm, _ = await detail(PM_ID, trio(), VERIFIED)
        for payload, buffalo in ((odds, 1309486), (kalshi, 643833), (pm, 1709101)):
            assert payload["representation"] == VERIFIED, _why(payload)
            row = next(o for o in payload["outcomes"] if o["id"] == buffalo)
            assert row["probability"] == pytest.approx(
                0.13 / 0.4715, abs=1e-8
            )  # #12530: one verified named-team field, before venue projection
            assert row["contributing_sources"] == ["odds_api", "kalshi", "polymarket"]
            assert payload["question_identity"]["edition"] == "2027"

    async def test_ids_names_order_and_provenance_are_the_requested_rows(self):
        default, _ = await detail(ODDS_ID, trio())
        verified, _ = await detail(ODDS_ID, trio(), VERIFIED)
        assert [(o["id"], o["name"]) for o in verified["outcomes"]] == [
            (o["id"], o["name"]) for o in default["outcomes"]
        ]
        assert verified["source"] == default["source"] == "odds_api"
        assert verified["bookmakers"] == default["bookmakers"] == EIGHT_BOOKS
        assert verified["id"] == ODDS_ID and verified["name"] == default["name"]

    async def test_eight_books_are_one_venue(self):
        payload, _ = await detail(ODDS_ID, trio(), VERIFIED)
        for o in payload["outcomes"]:
            assert o["contributing_sources"].count("odds_api") <= 1
        assert payload["contributing_sources"].count("odds_api") == 1

    async def test_a_blended_row_carries_no_movement_from_another_estimator(self):
        default, _ = await detail(ODDS_ID, trio())
        verified, _ = await detail(ODDS_ID, trio(), VERIFIED)
        assert by_name(default, "Buffalo Bills")["opening_probability"] is None  # normalized scale
        buf = by_name(verified, "Buffalo Bills")
        for key in ("opening_probability", "opening_american_odds",
                    "probability_change_24h", "price_changed_at"):
            assert buf[key] is None, key

    async def test_badges_follow_the_verified_value(self):
        # Both venues price the Jets at 20%: last on the sportsbook board, first
        # on the verified one. The badge must say so.
        kalshi = kalshi_market(rows=[r if r[2] != "KXSB-27-NYJ" else (*r[:3], 0.2)
                                     for r in KALSHI_ROWS])
        pm = pm_market(rows=[r if r[1] != "New York Jets" else (r[0], r[1], 0.2)
                             for r in PM_ROWS])
        default, _ = await detail(ODDS_ID, trio(kalshi=kalshi, pm=pm))
        payload, _ = await detail(ODDS_ID, trio(kalshi=kalshi, pm=pm), VERIFIED)
        assert by_name(default, "New York Jets")["rank"] == 7
        assert by_name(payload, "New York Jets")["probability"] == pytest.approx(0.2 / 0.6565, abs=1e-8)
        assert by_name(payload, "New York Jets")["rank"] == 1
        ranked = sorted(payload["outcomes"], key=lambda o: o["rank"])
        values = [o["probability"] or 0 for o in ranked]
        assert values == sorted(values, reverse=True)

    async def test_the_source_rows_hook_sentence_is_withheld_once_numbers_move(self):
        def markets():
            return trio(odds=odds_market(
                hook="Buffalo leads the field at 11%.",
                hook_generated_at=NOW - timedelta(hours=1),
                hook_leader_at_generation="Buffalo Bills",
                meta_extra={"hook_policy_version": 2,
                            "hook_probability_at_generation": 0.112913},
            ))
        default, _ = await detail(ODDS_ID, markets())
        assert default["hook_description"] == "Buffalo leads the field at 11%.", \
            "the source page serves this sentence, so withholding it below is ours"
        verified, _ = await detail(ODDS_ID, markets(), VERIFIED)
        assert verified["hook_description"] is None
        assert verified["hook_withheld"] is True


# ── 2. same-key negatives ────────────────────────────────────────────────────


class TestSameKeyQuestionsNeverJoin:
    @pytest.mark.parametrize("mid", [900001, 900002, 900003, 900004])
    async def test_an_mvp_coach_or_qualifier_page_stays_source(self, mid):
        payload, db = await detail(mid, trio(), VERIFIED)
        assert payload["representation"] == "source"
        assert payload["question_identity"] is None
        assert payload["representation_fallback"] == "not_a_title_question"
        assert "candidates" not in db.kinds, "no identity, no candidate read"

    async def test_they_are_never_contributors_to_the_title(self):
        payload, _ = await detail(ODDS_ID, trio(), VERIFIED)
        # Admitting either 85% Buffalo qualifier would make its venue ambiguous
        # and drop that venue, moving both the value and the contributors.
        buf = by_name(payload, "Buffalo Bills")
        assert buf["contributing_sources"] == ["odds_api", "kalshi", "polymarket"]
        assert buf["probability"] == pytest.approx(0.13 / 0.4715, abs=1e-8)

    def test_the_candidate_read_is_venue_identity_not_the_canonical_key(self):
        stmt = futures_routes._verified_title_candidates_stmt(NFL_TITLE, "2027", ODDS_ID)
        sql = str(stmt.compile(dialect=postgresql.dialect(),
                               compile_kwargs={"literal_binds": True}))
        assert "canonical_market_key" not in sql
        assert "'KXSB-27'" in sql
        assert "'americanfootball_nfl_super_bowl_winner'" in sql
        assert "LIKE 'pro-football-2027-champion%%'" in sql or \
            "LIKE 'pro-football-2027-champion%'" in sql
        assert "status = 'open'" in sql
        assert "polymarket_event_slug" in sql


# ── 3. the sportsbook anchor ─────────────────────────────────────────────────


class TestTheSportsbookAnchor:
    async def test_no_anchor_sends_the_sportsbook_page_to_source(self):
        payload, _ = await detail(ODDS_ID, trio(odds=odds_market(anchor=None)), VERIFIED)
        assert payload["representation"] == "source"
        assert payload["representation_fallback"] == "anchor_missing"

    async def test_without_its_anchor_the_sportsbook_never_contributes_elsewhere(self):
        payload, _ = await detail(KALSHI_ID, trio(odds=odds_market(anchor=None)), VERIFIED)
        assert payload["representation"] == VERIFIED, _why(payload)
        buf = next(o for o in payload["outcomes"] if o["id"] == 643833)
        assert buf["contributing_sources"] == ["kalshi", "polymarket"]
        assert buf["probability"] == pytest.approx(0.1325 / 0.4865, abs=1e-8)
        assert buf["aggregation_rule"] == "equal_weight_midpoint"
        assert payload["contributing_sources"] == ["kalshi", "polymarket"]

    async def test_a_stale_anchor_is_refused(self):
        old = NOW - ANCHOR_MAX_AGE - timedelta(minutes=1)
        markets = trio(odds=odds_market(anchor=_anchor(polled_at=old.isoformat()), at=old))
        payload, _ = await detail(ODDS_ID, markets, VERIFIED)
        assert payload["representation_fallback"] == "anchor_stale"

    @pytest.mark.parametrize("bad", [
        {"scope": "rolling"},
        {"event_id": ""},
        {"sport_key": "americanfootball_ncaaf_championship_winner"},
        {"commence_time": "2027-02-14T23:35:00"},  # naive
        {"polled_at": "yesterday"},
    ])
    async def test_a_malformed_stamp_is_refused(self, bad):
        payload, _ = await detail(ODDS_ID, trio(odds=odds_market(anchor=_anchor(**bad))), VERIFIED)
        assert payload["representation"] == "source"
        assert payload["representation_fallback"] == "anchor_malformed"

    async def test_a_leg_older_than_the_anchor_batch_does_not_inherit_its_edition(self):
        odds = odds_market()
        stale = next(o for o in odds.outcomes if o.name == "Kansas City Chiefs")
        stale.last_updated = POLLED - timedelta(hours=4)
        payload, _ = await detail(ODDS_ID, trio(odds=odds), VERIFIED)
        assert payload["representation"] == VERIFIED, _why(payload)
        kc = by_name(payload, "Kansas City Chiefs")
        assert kc["contributing_sources"] == ["kalshi", "polymarket"]
        assert kc["probability"] == pytest.approx(0.08575 / 0.47225, abs=1e-8)
        assert by_name(payload, "Buffalo Bills")["contributing_sources"][0] == "odds_api"


# ── 3b. the rows served are the rows proved ──────────────────────────────────


class _RollingDB(_DB):
    """A poll commits between the candidate read and the full member read.

    Candidate verdicts are taken on the old sportsbook row; ``roll`` rewrites
    that row the moment the first member read after them returns, so the board
    the resolver formats describes the NEW batch.
    """

    def __init__(self, markets, roll, **kw):
        super().__init__(markets, **kw)
        self._roll = roll
        self.rolled = False

    async def execute(self, stmt, *a, **kw):
        result = await super().execute(stmt, *a, **kw)
        if not self.rolled and self.kinds[-1] == "members" and "candidates" in self.kinds:
            self._roll(self.markets[ODDS_ID])
            self.rolled = True
        return result


def _roll_to(*, at, buffalo=None, **anchor):
    def roll(odds):
        odds.market_metadata["odds_api_current_event"] = _anchor(**anchor)
        for row in odds.outcomes:
            if at is not None:
                row.last_updated = at
            if buffalo is not None and row.name == "Buffalo Bills":
                row.current_probability = buffalo
    return roll


NEXT_POLL = NOW - timedelta(minutes=30)
#: Rolls the resolver must NOT credit: the sportsbook's loaded quotes are next
#: season's, or its loaded batch clock is newer than every loaded quote.
STALE_ROLLS = {
    "2027_to_2028_quote_rollover": _roll_to(
        at=NOW, event_id="new-2028-provider-event",
        commence_time="2028-02-13T23:35:00+00:00", polled_at=NOW.isoformat(),
    ),
    "same_edition_newer_poll": _roll_to(at=None, polled_at=NEXT_POLL.isoformat()),
    "same_edition_new_provider_event": _roll_to(
        at=None, event_id="0f0f-new-provider-event", polled_at=NEXT_POLL.isoformat(),
    ),
    "same_edition_new_instant": _roll_to(
        at=None, commence_time="2027-02-14T23:00:00+00:00",
        polled_at=NEXT_POLL.isoformat(),
    ),
}
KALSHI_BUFFALO = 643833


async def _rolled(mid, roll, route):
    markets = trio()
    requested = next(m for m in markets if m.id == mid)
    db = _RollingDB(markets, roll, snapshots=snapshots_for(requested))
    with _at():
        if route == "detail":
            payload = await get_futures_market(mid, representation=VERIFIED, db=db)
        else:
            payload = await get_probability_timeline(
                market_id=mid, top=10, hours=168, representation=VERIFIED, db=db
            )
    assert db.rolled, "the poll never landed between the two reads"
    return payload


class TestMembershipIsReprovedOnTheLoadedRows:
    @pytest.mark.parametrize("route", ["detail", "timeline"])
    @pytest.mark.parametrize("name", sorted(STALE_ROLLS))
    async def test_a_sportsbook_that_rolled_after_the_candidate_read_never_contributes(
        self, name, route
    ):
        payload = await _rolled(KALSHI_ID, STALE_ROLLS[name], route)
        assert payload["representation"] == VERIFIED, _why(payload)
        assert payload["question_identity"]["edition"] == "2027"
        assert payload["contributing_sources"] == ["kalshi", "polymarket"]
        prob_key = "probability" if route == "detail" else "current_probability"
        buf = next(o for o in payload["outcomes"] if o["id"] == KALSHI_BUFFALO)
        assert buf["contributing_sources"] == ["kalshi", "polymarket"]
        assert buf[prob_key] == pytest.approx(0.1325 / 0.4865, abs=1e-8)
        for o in payload["outcomes"]:
            assert "odds_api" not in o.get("contributing_sources", []), o["name"]

    @pytest.mark.parametrize("name", sorted(STALE_ROLLS))
    async def test_the_chart_keeps_its_history_through_the_roll(self, name):
        default, _ = await timeline(KALSHI_ID, trio())
        verified = await _rolled(KALSHI_ID, STALE_ROLLS[name], "timeline")
        assert default["timeline"], "the fixture draws history"
        for key in set(default) - {"outcomes"}:
            assert verified[key] == default[key], key
        assert [(m["id"], m["name"]) for m in verified["outcomes"]] == [
            (m["id"], m["name"]) for m in default["outcomes"]
        ]

    @pytest.mark.parametrize("route", ["detail", "timeline"])
    async def test_a_fresh_batch_on_the_loaded_row_contributes_its_loaded_quotes(self, route):
        # Same edition, newer poll, every quote refreshed WITH it: the loaded row
        # is a member on its own loaded clock, and its loaded price is the one
        # that moves the median (old 11.3% → 0.13; loaded 20% → 0.135).
        roll = _roll_to(at=NEXT_POLL, buffalo=0.20, polled_at=NEXT_POLL.isoformat())
        payload = await _rolled(KALSHI_ID, roll, route)
        assert payload["representation"] == VERIFIED, _why(payload)
        prob_key = "probability" if route == "detail" else "current_probability"
        buf = next(o for o in payload["outcomes"] if o["id"] == KALSHI_BUFFALO)
        assert buf["contributing_sources"] == ["odds_api", "kalshi", "polymarket"]
        assert buf[prob_key] == pytest.approx(0.135 / 0.4765, abs=1e-8)
        assert buf["observed_at"] == KALSHI_AT.isoformat(), "the OLDEST included observation"

    @pytest.mark.parametrize("route", ["detail", "timeline"])
    async def test_frozen_inputs_serve_the_same_payload(self, route):
        rolled = await _rolled(KALSHI_ID, lambda _odds: None, route)
        if route == "detail":
            frozen, _ = await detail(KALSHI_ID, trio(), VERIFIED)
        else:
            frozen, _ = await timeline(KALSHI_ID, trio(), VERIFIED)
        assert rolled == frozen


# ── 3c. a member's identity and quotes are one snapshot ──────────────────────
#
# The re-proof above is sound only if each loaded row's metadata and outcomes
# are one read: `selectinload(outcomes)` is a SECOND select, and a poll landing
# between the two pairs the old metadata (which re-proves) with refreshed quotes
# (which satisfy the old poll clock). A fake session cannot interleave inside a
# statement, so this pins the shape instead: on every opted-in member read, the
# market's identity columns and its outcomes' quote columns are columns of the
# SAME select.

ONE_SNAPSHOT_COLUMNS = (
    "futures_markets.market_metadata",
    "futures_markets.status",
    "futures_markets.resolution_date",
    "futures_outcomes_1.current_probability",
    "futures_outcomes_1.last_updated",
)


def _one_snapshot(sql: str) -> bool:
    return "LEFT OUTER JOIN futures_outcomes AS futures_outcomes_1" in sql and all(
        col in sql for col in ONE_SNAPSHOT_COLUMNS
    )


def _member_reads(db):
    return [(kind, sql, loads) for kind, sql, loads in db.statements
            if kind in ("market", "members")]


class TestIdentityAndQuotesAreOneStatement:
    @pytest.mark.parametrize("route", ["detail", "timeline"])
    @pytest.mark.parametrize("mid", [ODDS_ID, KALSHI_ID, PM_ID])
    async def test_every_opted_in_member_read_joins_its_outcomes(self, route, mid):
        if route == "detail":
            payload, db = await detail(mid, trio(), VERIFIED)
        else:
            payload, db = await timeline(mid, trio(), VERIFIED)
        assert payload["representation"] == VERIFIED, _why(payload)
        reads = _member_reads(db)
        # Requested AND siblings, or the guard would pass on one statement.
        assert [kind for kind, _, _ in reads] == ["market", "members"]
        for kind, sql, loads in reads:
            assert _one_snapshot(sql), f"{route} {kind} read splits identity from quotes"
            assert loads["outcomes"] == "joined", (route, kind)
            assert loads["sport"] == "selectin", (route, kind)

    async def test_the_opted_in_chart_keeps_its_team_enrichment(self):
        _, db = await timeline(ODDS_ID, trio(), VERIFIED)
        (requested,) = [loads for kind, _, loads in db.statements if kind == "market"]
        # The team read carries no edition and no quote, so it may stay separate.
        assert requested["outcomes.team"] == "selectin"

    @pytest.mark.parametrize("representation", [None, "source"])
    async def test_the_default_detail_read_is_the_original_statement(self, representation):
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        _, db = await detail(ODDS_ID, trio(), representation)
        original = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.sport))
            .options(selectinload(FuturesMarket.outcomes))
            .where(FuturesMarket.id == ODDS_ID)
        )
        assert db.statements == [("market", _sql(original), _loads(original))]
        assert "futures_outcomes" not in db.statements[0][1]

    @pytest.mark.parametrize("representation", [None, "source"])
    async def test_the_default_timeline_read_is_the_original_statement(self, representation):
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.models import FuturesOutcome

        _, db = await timeline(ODDS_ID, trio(), representation)
        original = (
            select(FuturesMarket)
            .options(
                selectinload(FuturesMarket.outcomes).selectinload(FuturesOutcome.team),
                selectinload(FuturesMarket.sport),
            )
            .where(FuturesMarket.id == ODDS_ID)
        )
        assert db.statements[0] == ("market", _sql(original), _loads(original))
        assert [kind for kind, _, _ in _member_reads(db)] == ["market"]
        assert "candidates" not in db.kinds


# ── 4. wrong edition ─────────────────────────────────────────────────────────


class TestWrongEdition:
    async def test_next_seasons_venues_are_not_this_seasons_contributors(self):
        extra = [
            kalshi_market(mid=900101, ticker="KXSB-28",
                          resolution_date=datetime(2028, 2, 13, 23, 30, tzinfo=timezone.utc),
                          rows=[(900111, "Buffalo", "KXSB-28-BUF", 0.5)]),
            pm_market(mid=900102, event_id="400001",
                      slug="pro-football-2028-champion-1",
                      resolution_date=datetime(2028, 4, 1, 3, 59, tzinfo=timezone.utc),
                      rows=[(900112, "Buffalo Bills", 0.5)]),
        ]
        payload, _ = await detail(ODDS_ID, trio(extra=extra), VERIFIED)
        buf = by_name(payload, "Buffalo Bills")
        assert buf["probability"] == pytest.approx(0.13 / 0.4715, abs=1e-8)
        assert buf["contributing_sources"] == ["odds_api", "kalshi", "polymarket"]

    async def test_a_sportsbook_anchored_to_another_edition_finds_no_partner(self):
        odds = odds_market(anchor=_anchor(commence_time="2028-02-13T23:30:00+00:00"))
        payload, _ = await detail(ODDS_ID, trio(odds=odds), VERIFIED)
        assert payload["representation"] == "source"
        assert payload["representation_fallback"] == "no_corroborating_venue"

    async def test_a_kalshi_row_dated_outside_its_ticker_year_is_refused(self):
        kalshi = kalshi_market(resolution_date=datetime(2028, 2, 13, tzinfo=timezone.utc))
        payload, _ = await detail(KALSHI_ID, trio(kalshi=kalshi), VERIFIED)
        assert payload["representation_fallback"] == "edition_mismatch"

    async def test_venues_that_date_the_game_apart_are_refused(self):
        kalshi = kalshi_market(resolution_date=datetime(2027, 2, 7, 23, 30, tzinfo=timezone.utc))
        payload, _ = await detail(ODDS_ID, trio(kalshi=kalshi), VERIFIED)
        assert payload["representation_fallback"] == "edition_instant_conflict"


# ── 5. team correspondence ───────────────────────────────────────────────────


class TestExactTeamCorrespondence:
    async def test_an_ambiguous_city_name_never_corresponds(self):
        rows = [r if r[1] != "New York Giants" else (r[0], "New York", r[2]) for r in ODDS_ROWS]
        payload, _ = await detail(ODDS_ID, trio(odds=odds_market(rows=rows)), VERIFIED)
        assert payload["representation"] == VERIFIED, _why(payload)
        ny = by_name(payload, "New York")
        assert ny["contributing_sources"] == ["odds_api"]
        assert ny["aggregation_rule"] == "single_source"
        assert ny["probability"] == 0.02
        assert ny["opening_probability"] == 0.01
        # An unresolved canonical row cannot certify a full common field.
        # Its own value/reference remain source-only; neither is borrowed
        # from the Giants or from the normalized named-team set.

    async def test_kalshi_corresponds_by_its_ticker_not_its_city_string(self):
        # Kalshi's display strings are bare cities and truncations; every one of
        # them still lands on its club because the ticker names it.
        payload, _ = await detail(ODDS_ID, trio(), VERIFIED)
        for name in ("Los Angeles Rams", "Los Angeles Chargers", "New York Giants", "New York Jets"):
            assert "kalshi" in by_name(payload, name)["contributing_sources"], name

    async def test_a_kalshi_name_that_names_another_club_vetoes_its_ticker(self):
        rows = [r if r[2] != "KXSB-27-KC" else (r[0], "Buffalo Bills", r[2], r[3])
                for r in KALSHI_ROWS]
        payload, _ = await detail(ODDS_ID, trio(kalshi=kalshi_market(rows=rows)), VERIFIED)
        assert by_name(payload, "Kansas City Chiefs")["contributing_sources"] == [
            "odds_api", "polymarket"]

    async def test_a_city_alias_alone_never_resolves(self):
        # `location` is not an alias here: a Polymarket leg named only "Buffalo"
        # (no ticker to rescue it) contributes nothing.
        rows = [r if r[1] != "Buffalo Bills" else (r[0], "Buffalo", r[2]) for r in PM_ROWS]
        payload, _ = await detail(ODDS_ID, trio(pm=pm_market(rows=rows)), VERIFIED)
        assert by_name(payload, "Buffalo Bills")["contributing_sources"] == ["odds_api", "kalshi"]

    async def test_two_legs_for_one_club_in_one_venue_both_stand_down(self):
        rows = PM_ROWS + [(1709199, "Buffalo Bills", 0.5)]
        payload, _ = await detail(ODDS_ID, trio(pm=pm_market(rows=rows)), VERIFIED)
        assert by_name(payload, "Buffalo Bills")["contributing_sources"] == ["odds_api", "kalshi"]
        assert by_name(payload, "Los Angeles Rams")["contributing_sources"] == [
            "odds_api", "kalshi", "polymarket"]


# ── 6. duplicate venues ──────────────────────────────────────────────────────


class TestDuplicateVenues:
    def _second_pm(self):
        return pm_market(mid=900201, event_id="500001",
                         slug="pro-football-2027-champion-20260901000000000")

    async def test_two_title_rows_at_one_venue_drop_that_venue(self):
        payload, _ = await detail(ODDS_ID, trio(extra=[self._second_pm()]), VERIFIED)
        assert payload["representation"] == VERIFIED, _why(payload)
        assert payload["contributing_sources"] == ["odds_api", "kalshi"]

    async def test_the_requested_rows_own_venue_duplicated_is_source(self):
        payload, _ = await detail(PM_ID, trio(extra=[self._second_pm()]), VERIFIED)
        assert payload["representation_fallback"] == "ambiguous_requested_venue"


# ── 7. settlement ────────────────────────────────────────────────────────────


class TestSettlementRule:
    async def test_a_cutoff_before_the_game_refuses_polymarket(self):
        pm = pm_market(resolution_date=datetime(2027, 2, 1, tzinfo=timezone.utc))
        payload, _ = await detail(ODDS_ID, trio(pm=pm), VERIFIED)
        assert payload["contributing_sources"] == ["odds_api", "kalshi"]
        own, _ = await detail(PM_ID, trio(pm=pm), VERIFIED)
        assert own["representation_fallback"] == "settlement_rule_refused"

    async def test_no_cutoff_is_no_membership(self):
        pm = pm_market(resolution_date=None)
        own, _ = await detail(PM_ID, trio(pm=pm), VERIFIED)
        assert own["representation_fallback"] == "settlement_deadline_missing"

    async def test_other_is_never_a_team(self):
        payload, _ = await detail(PM_ID, trio(), VERIFIED)
        other = next(o for o in payload["outcomes"] if o["id"] == PM_OTHER_ID)
        assert other["probability"] is None
        assert other["contributing_sources"] == []

    async def test_a_priced_other_stays_polymarkets_own_number(self):
        pm = pm_market()
        next(o for o in pm.outcomes if o.id == PM_OTHER_ID).current_probability = 0.004
        next(o for o in pm.outcomes if o.id == PM_OTHER_ID).last_updated = PM_AT
        payload, _ = await detail(PM_ID, trio(pm=pm), VERIFIED)
        other = next(o for o in payload["outcomes"] if o["id"] == PM_OTHER_ID)
        assert other["contributing_sources"] == ["polymarket"]
        assert other["aggregation_rule"] == "single_source"
        odds, _ = await detail(ODDS_ID, trio(pm=pm), VERIFIED)
        assert by_name(odds, "Buffalo Bills")["probability"] == pytest.approx(0.13 / 0.4715, abs=1e-8)


# ── 8. everything else falls back ────────────────────────────────────────────


class TestIneligibleRequestsFallBack:
    async def test_unrelated_market(self):
        nba = _market(900301, "odds_api", "basketball_nba_championship_winner",
                      "NBA Championship Winner",
                      [_outcome(900311, "Boston Celtics", 0.2, POLLED)],
                      metadata={"odds_api_current_event": _anchor(
                          sport_key="basketball_nba_championship_winner")})
        payload, _ = await detail(900301, trio(extra=[nba]), VERIFIED)
        assert payload["representation_fallback"] == "not_a_title_question"

    async def test_independent_binaries(self):
        payload, _ = await detail(ODDS_ID, trio(odds=odds_market(me=False)), VERIFIED)
        assert payload["representation_fallback"] == "not_single_winner"

    async def test_draw_market(self):
        game = _market(900302, "kalshi", "KXNFLGAME-27FEB14BUFLAR", "Buffalo vs Los Angeles R",
                       [_outcome(900312, "Buffalo", 0.5, KALSHI_AT, external_id="KXNFLGAME-27FEB14BUFLAR-BUF"),
                        _outcome(900313, "Tie", 0.01, KALSHI_AT, external_id="KXNFLGAME-27FEB14BUFLAR-TIE")])
        payload, _ = await detail(900302, trio(extra=[game]), VERIFIED)
        assert payload["representation_fallback"] == "not_a_title_question"

    async def test_venues_that_share_no_team_are_not_a_composition(self):
        # Kalshi is a member but none of its tickers names a known club, and
        # Polymarket's cutoff refuses it: nothing is answered twice.
        kalshi = kalshi_market(rows=[(i, n, f"KXSB-27-Z{k}", p)
                                     for k, (i, n, _t, p) in enumerate(KALSHI_ROWS)])
        pm = pm_market(resolution_date=datetime(2027, 2, 1, tzinfo=timezone.utc))
        payload, _ = await detail(ODDS_ID, trio(kalshi=kalshi, pm=pm), VERIFIED)
        assert payload["representation"] == "source"
        assert payload["representation_fallback"] == "no_multi_source_outcome"

    async def test_settled_market(self):
        payload, _ = await detail(ODDS_ID, trio(odds=odds_market(status="resolved")), VERIFIED)
        assert payload["representation_fallback"] == "not_open"

    async def test_a_resolver_failure_is_source_mode_not_an_error_page(self):
        db = _DB(trio())
        db.fail_on = "candidates"
        with _at():
            payload = await get_futures_market(ODDS_ID, representation=VERIFIED, db=db)
        assert payload["representation"] == "source"
        assert payload["representation_fallback"] == "resolver_error"
        assert payload["outcomes"], "the source page still serves"


# ── 9. default and source are unchanged ──────────────────────────────────────


class TestDefaultIsUnchanged:
    async def test_default_and_explicit_source_are_identical_and_carry_no_new_keys(self):
        default, db_default = await detail(ODDS_ID, trio())
        explicit, db_explicit = await detail(ODDS_ID, trio(), "source")
        assert default == explicit
        assert not (NEW_DETAIL_KEYS | {"representation_fallback"}) & set(default)
        for o in default["outcomes"]:
            assert not NEW_OUTCOME_KEYS & set(o)
        assert db_default.kinds == db_explicit.kinds == ["market"], "no resolver reads"

    async def test_an_opted_in_fallback_is_the_default_plus_three_labels(self):
        default, _ = await detail(ODDS_ID, trio(odds=odds_market(anchor=None)))
        fallback, _ = await detail(ODDS_ID, trio(odds=odds_market(anchor=None)), VERIFIED)
        extra = set(fallback) - set(default)
        assert extra == {"representation", "question_identity", "representation_fallback"}
        assert {k: fallback[k] for k in default} == default

    async def test_default_timeline_is_unchanged(self):
        default, db_default = await timeline(ODDS_ID, trio())
        explicit, _ = await timeline(ODDS_ID, trio(), "source")
        assert default == explicit
        assert "history_basis" not in default and "representation" not in default
        assert "candidates" not in db_default.kinds


# ── 10–12. the chart ─────────────────────────────────────────────────────────


class TestTheChartAgreesAndKeepsItsHistory:
    async def test_detail_and_chart_current_values_are_one_computation(self):
        markets = trio()
        hero, _ = await detail(ODDS_ID, markets, VERIFIED)
        chart, _ = await timeline(ODDS_ID, copy.deepcopy(markets), VERIFIED)
        assert chart["representation"] == hero["representation"] == VERIFIED
        assert chart["question_identity"] == hero["question_identity"]
        hero_rows = {o["id"]: o for o in hero["outcomes"]}
        assert chart["outcomes"]
        for meta in chart["outcomes"]:
            row = hero_rows[meta["id"]]
            assert meta["current_probability"] == row["probability"], meta["name"]
            for key in NEW_OUTCOME_KEYS:
                assert meta[key] == row[key], (meta["name"], key)

    async def test_history_points_gaps_and_coverage_are_the_sources_own(self):
        default, _ = await timeline(ODDS_ID, trio())
        verified, _ = await timeline(ODDS_ID, trio(), VERIFIED)
        assert verified["timeline"] == default["timeline"]
        assert default["timeline"], "the fixture draws history"
        for key in set(default) - {"outcomes"}:
            assert verified[key] == default[key], key
        assert verified["history_basis"] == {
            "kind": "single_source", "source": "odds_api", "market_id": ODDS_ID,
        }

    async def test_metadata_ids_order_names_and_top_are_the_sources_own(self):
        default, _ = await timeline(ODDS_ID, trio(), top=3)
        verified, _ = await timeline(ODDS_ID, trio(), VERIFIED, top=3)
        assert [(m["id"], m["name"]) for m in verified["outcomes"]] == [
            (m["id"], m["name"]) for m in default["outcomes"]
        ]
        history_keys = {k for entry in verified["timeline"] for k in entry["outcomes"]}
        for meta in verified["outcomes"]:
            assert meta["name"] in history_keys, f"{meta['name']!r} has no history line"

    async def test_field_current_is_the_rest_of_the_verified_column(self):
        verified, _ = await timeline(ODDS_ID, trio(), VERIFIED, top=3)
        hero, _ = await detail(ODDS_ID, trio(), VERIFIED)
        top_ids = {m["id"] for m in verified["outcomes"] if m["id"] is not None}
        field = by_name(verified, "Field")
        expected = round(sum(o["probability"] or 0 for o in hero["outcomes"]
                             if o["id"] not in top_ids), 8)
        assert field["current_probability"] == expected
        assert field["contributing_sources"] == ["odds_api", "kalshi", "polymarket"]

    async def test_a_fallback_chart_still_names_its_history(self):
        chart, _ = await timeline(ODDS_ID, trio(odds=odds_market(anchor=None)), VERIFIED)
        assert chart["representation"] == "source"
        assert chart["history_basis"]["source"] == "odds_api"
        for meta in chart["outcomes"]:
            assert not NEW_OUTCOME_KEYS & set(meta)


# ── types and vocabulary ─────────────────────────────────────────────────────


class TestWireTypes:
    async def test_new_fields_have_the_specified_types(self):
        payload, _ = await detail(ODDS_ID, trio(), VERIFIED)
        assert isinstance(payload["representation"], str)
        assert all(isinstance(v, str) for v in payload["question_identity"].values())
        assert set(payload["question_identity"]) == {"competition", "edition", "question"}
        for o in payload["outcomes"]:
            assert isinstance(o["contributing_sources"], list)
            assert set(o["contributing_sources"]) <= set(CONTRIBUTOR_SOURCES)
            assert isinstance(o["aggregation_rule"], str)
            if o["observed_at"] is not None:
                assert datetime.fromisoformat(o["observed_at"]).tzinfo is not None


class TestDivergenceGate:
    async def test_a_gated_pair_credits_only_the_venue_whose_number_prints(self):
        rows = [r if r[1] != "Buffalo Bills" else (r[0], r[1], 0.60) for r in PM_ROWS]
        payload, _ = await detail(KALSHI_ID, trio(odds=odds_market(anchor=None),
                                                   pm=pm_market(rows=rows)), VERIFIED)
        buf = next(o for o in payload["outcomes"] if o["id"] == 643833)
        assert buf["aggregation_rule"] == "divergence_gate"
        assert len(buf["contributing_sources"]) == 1


class TestTheRosterIndex:
    def test_a_city_is_not_an_alias(self):
        from app.utils.futures_verified_title import title_team_index

        index = title_team_index(ROSTER)
        assert index.alias_team("Buffalo Bills") == 1
        assert index.alias_team("Buffalo") is None
        assert index.abbrev_team("BUF") == 1
        assert index.is_ambiguous("New York"), "a shared alternate name is refused"


# #12530: the November 10 field that exposed per-venue normalization.
_SNAPSHOT_12530 = [
    ('Buffalo Bills', 0.145),
    ('San Francisco 49ers', 0.1435),
    ('Jacksonville Jaguars', 0.10828),
    ('Chicago Bears', 0.1095),
    ('Kansas City Chiefs', 0.075),
    ('Los Angeles Rams', 0.060789),
    ('Cincinnati Bengals', 0.060396),
    ('Denver Broncos', 0.0505),
    ('Detroit Lions', 0.045),
    ('Seattle Seahawks', 0.045),
    ('Green Bay Packers', 0.035),
    ('Minnesota Vikings', 0.0275),
    ('Houston Texans', 0.0235),
    ('Pittsburgh Steelers', 0.021),
    ('New England Patriots', 0.025),
    ('New York Giants', 0.0145),
    ('Dallas Cowboys', 0.013583),
    ('Baltimore Ravens', 0.006),
    ('Tampa Bay Buccaneers', 0.01),
    ('Carolina Panthers', 0.007911),
    ('Atlanta Falcons', 0.007341),
    ('New Orleans Saints', 0.004702),
    ('Cleveland Browns', 0.003844),
    ('Washington Commanders', 0.003812),
    ('Las Vegas Raiders', 0.005094),
    ('Arizona Cardinals', 0.000849),
    ('Miami Dolphins', 0.000643),
    ('Indianapolis Colts', 0.000764),
    ('Los Angeles Chargers', 0.000764),
    ('New York Jets', 0.000721),
    ('Philadelphia Eagles', 0.000849),
    ('Tennessee Titans', 0.000678),
]


class TestOneTitleField12530:
    def markets(self, *, missing_last=False):
        values = list(_SNAPSHOT_12530)
        if missing_last:
            values[-1] = (values[-1][0], None)
        odds = odds_market(rows=[(100 + i, name, p if p is not None else 0) for i, (name, p) in enumerate(values)])
        if missing_last:
            odds.outcomes[-1].current_probability = None
        pm = pm_market(rows=[(1000 + i, name, p) for i, (name, p) in enumerate(values)])
        roster = [
            {"id": i + 1, "name": name, "abbreviation": f"team{i}", "alternate_names": []}
            for i, (name, _p) in enumerate(values)
        ]
        return [odds, pm], roster

    async def test_all_32_teams_share_the_number_and_other_is_retained_unpriced(self):
        markets, roster = self.markets()
        odds, _ = await detail(ODDS_ID, markets, VERIFIED, roster=roster)
        pm, _ = await detail(PM_ID, markets, VERIFIED, roster=roster)
        assert len(odds["outcomes"]) == 32
        assert len(pm["outcomes"]) == 33
        for name, raw in _SNAPSHOT_12530:
            expected = round(raw / 1.04702, 8)
            assert by_name(odds, name)["probability"] == expected
            assert by_name(pm, name)["probability"] == expected
        other = by_name(pm, "Other")
        assert other["id"] == PM_OTHER_ID
        assert other["probability"] is None
        assert other["contributing_sources"] == []
        assert by_name(pm, "Buffalo Bills")["probability"] == 0.13848828

    async def test_a_missing_named_team_stops_normalization_under_both_aliases(self):
        markets, roster = self.markets(missing_last=True)
        for mid in (ODDS_ID, PM_ID):
            payload, _ = await detail(mid, markets, VERIFIED, roster=roster)
            assert by_name(payload, "Buffalo Bills")["probability"] == 0.145
            assert by_name(payload, _SNAPSHOT_12530[-1][0])["probability"] is None

    async def test_each_alias_has_one_destination_and_the_same_top_five(self):
        from app.routes.events import _format_futures_for_search, _dedup_verified_title_markets

        markets, roster = self.markets()
        cards, verdicts = [], {}
        for market in markets:
            with _at():
                verdict = await futures_routes._compose_verified_title(_DB(markets, roster=roster), market)
                cards.append(_format_futures_for_search(market, set(), verified=verdict))
            verdicts[market.id] = verdict
        for key in ("id", "name", "source", "sport", "sport_name", "resolution_date",
                    "outcome_count", "prices_updated_at"):
            assert cards[0][key] == cards[1][key], key
        assert cards[0]["id"] == ODDS_ID
        assert cards[0]["outcome_count"] == 32
        named = [[(o["name"], o["probability"]) for o in c["top_outcomes"]] for c in cards]
        assert named[0] == named[1]
        assert [n for n, _p in named[0]] == [
            "Buffalo Bills", "San Francisco 49ers", "Chicago Bears",
            "Jacksonville Jaguars", "Kansas City Chiefs",
        ]
        assert len(_dedup_verified_title_markets(markets, verdicts)) == 1
        assert len(_dedup_verified_title_markets(markets, {})) == 2

    async def test_aliases_reuse_one_snapshot_without_another_database_read(self, monkeypatch):
        from app.routes.events import _format_futures_for_search

        markets, roster = self.markets()
        db = _DB(markets, roster=roster)
        monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "60")
        monkeypatch.setattr(futures_routes, "_VERIFIED_TITLE_CACHE_MAX", 3)
        futures_routes._VERIFIED_TITLE_CACHE.clear()
        futures_routes._VERIFIED_TITLE_CACHE.update({
            777: (float("inf"), None), 888: (float("inf"), None),
        })
        try:
            with _at():
                first = await futures_routes._resolve_verified_title(db, markets[0])
                reads = list(db.kinds)
                # A later poll must not make the other alias recompose within
                # the already-accepted snapshot's short cache life.
                markets[1].outcomes[0].current_probability = 0.9
                second = await futures_routes._resolve_verified_title(db, markets[1])
                a = _format_futures_for_search(markets[0], set(), verified=first)
                b = _format_futures_for_search(markets[1], set(), verified=second)
            assert db.kinds == reads
            assert set(futures_routes._VERIFIED_TITLE_CACHE) == {ODDS_ID, PM_ID}
            assert len({entry[0] for entry in futures_routes._VERIFIED_TITLE_CACHE.values()}) == 1
            assert [(r["name"], r["probability"]) for r in a["top_outcomes"]] == [
                (r["name"], r["probability"]) for r in b["top_outcomes"]
            ]
            assert second.peer_verdicts == {}, "cached projections must not form cycles"
        finally:
            futures_routes._VERIFIED_TITLE_CACHE.clear()

    @pytest.mark.parametrize("mid", [ODDS_ID, KALSHI_ID, PM_ID])
    async def test_each_chart_current_column_still_matches_its_detail(self, mid):
        board, _ = await detail(mid, trio(), VERIFIED)
        chart, _ = await timeline(mid, trio(), VERIFIED)
        detail_values = {o["id"]: o["probability"] for o in board["outcomes"]}
        for row in chart["outcomes"]:
            if row.get("id") is not None:
                assert row["current_probability"] == detail_values[row["id"]]


class TestVenueTeamCodes12530:
    """The Nov 10 JAC/WAS identities, with deliberately different fixture quotes."""

    def test_all_32_real_tickers_resolve_distinct_real_roster_clubs(self):
        import json
        from pathlib import Path
        from app.utils.futures_verified_title import _row_team_id, title_team_index

        # Captured by bounded READ ONLY SQL on Nov 11. No invented aliases or
        # stored outcome team IDs participate in the resolution under test.
        specimen = json.loads(
            (Path(__file__).parent / "fixtures/nfl_title_teams_12530.json").read_text()
        )
        index = title_team_index(specimen["roster"])
        resolved = {
            row["external_id"]: _row_team_id(
                "kalshi", row["external_id"], row["name"], index,
                kalshi_event_ticker=specimen["market_external_id"],
            )
            for row in specimen["outcomes"]
        }
        assert len(resolved) == 32
        assert len(set(resolved.values())) == 32
        assert set(resolved.values()) == {team["id"] for team in specimen["roster"]}
        assert resolved["KXSB-27-JAC"] == 564
        assert resolved["KXSB-27-WAS"] == 542

    def markets(self):
        roster = copy.deepcopy(ROSTER) + [
            {"id": 564, "name": "Jacksonville Jaguars", "abbreviation": "JAX",
             "alternate_names": ["jags", "Jaguars"]},
            {"id": 542, "name": "Washington Commanders", "abbreviation": "WSH",
             "alternate_names": ["Commanders"]},
        ]
        markets = [
            odds_market(rows=ODDS_ROWS + [
                (1309497, "Jacksonville Jaguars", 0.11),
                (1309504, "Washington Commanders", 0.003),
            ]),
            kalshi_market(rows=KALSHI_ROWS + [
                (643835, "Jacksonville", "KXSB-27-JAC", 0.105),
                (643851, "Washington", "KXSB-27-WAS", 0.01),
            ]),
            pm_market(rows=PM_ROWS + [
                (1709110, "Jacksonville Jaguars", 0.10),
                (1709121, "Washington Commanders", 0.004),
            ]),
        ]
        # Stored outcome team IDs remain deliberately untrusted.
        for row in markets[1].outcomes:
            row.team_id = 10740
        return markets, roster

    async def test_venue_codes_share_values_and_clocks_on_all_three_pages(self):
        markets, roster = self.markets()
        expected = {"Jacksonville": round(0.105 / 0.5805, 8),
                    "Washington": round(0.004 / 0.5805, 8)}
        for mid in (ODDS_ID, KALSHI_ID, PM_ID):
            payload, _ = await detail(mid, markets, VERIFIED, roster=roster)
            for city, nickname in (("Jacksonville", "Jaguars"), ("Washington", "Commanders")):
                row = by_name(payload, city if mid == KALSHI_ID else f"{city} {nickname}")
                assert row["probability"] == pytest.approx(expected[city], abs=1e-8)
                assert row["contributing_sources"] == ["odds_api", "kalshi", "polymarket"]
                assert row["aggregation_rule"] == "weighted_median"
                assert row["observed_at"] == KALSHI_AT.isoformat()

    @pytest.mark.parametrize("mid", [ODDS_ID, KALSHI_ID, PM_ID])
    async def test_chart_current_and_search_cards_use_the_same_venue_code_answer(self, mid):
        from app.routes.events import _format_futures_for_search

        markets, roster = self.markets()
        market = next(m for m in markets if m.id == mid)
        payload, _ = await detail(mid, markets, VERIFIED, roster=roster)
        db = _DB(markets, roster=roster, snapshots=snapshots_for(market))
        with _at():
            chart = await get_probability_timeline(mid, top=10, hours=168,
                                                  representation=VERIFIED, db=db)
            cards = []
            for member in markets:
                verdict = await futures_routes._compose_verified_title(_DB(markets, roster=roster), member)
                cards.append(_format_futures_for_search(member, set(), verified=verdict))
        detail_rows = {r["id"]: r for r in payload["outcomes"]}
        for row in chart["outcomes"]:
            if row.get("id") in detail_rows:
                assert row["current_probability"] == detail_rows[row["id"]]["probability"]
                for key in NEW_OUTCOME_KEYS:
                    assert row[key] == detail_rows[row["id"]][key]
        assert [c["id"] for c in cards] == [ODDS_ID] * 3
        visible = [[(r["name"], r["probability"]) for r in c["top_outcomes"]] for c in cards]
        assert visible[0] == visible[1] == visible[2]
        assert any(name == "Jacksonville Jaguars" for name, _p in visible[0])

    @pytest.mark.parametrize("query,expected", [
        ("jaguars", "Jacksonville Jaguars"),
        ("jacksonville", "Jacksonville Jaguars"),
        ("commanders", "Washington Commanders"),
        ("washington", "Washington Commanders"),
    ])
    @pytest.mark.parametrize("lean", [False, True])
    async def test_canonical_labels_keep_team_query_pinning_and_source_names(self, query, expected, lean):
        from app.routes.events import _build_search_top_outcomes

        markets, roster = self.markets()
        original_names = [[o.name for o in market.outcomes] for market in markets]
        previews = []
        with _at():
            for market in markets:
                verdict = await futures_routes._compose_verified_title(_DB(markets, roster=roster), market)
                rows = _build_search_top_outcomes(
                    market, limit=3, lean=lean, query_terms=[(query, None)], verified=verdict,
                )
                assert rows[0]["name"] == expected
                if not lean:
                    assert rows[0]["query_match"] is True
                previews.append([(r["name"], r["probability"]) for r in rows])
        assert previews[0] == previews[1] == previews[2]
        assert [[o.name for o in market.outcomes] for market in markets] == original_names
        source, _ = await detail(KALSHI_ID, markets, "source", roster=roster)
        assert by_name(source, "Jacksonville")["id"] == 643835
        assert by_name(source, "Washington")["id"] == 643851

    @pytest.mark.parametrize("ticker,name", [
        ("KXSB-26-BUF", "Jacksonville"),
        ("KXNFLPLAYOFF-27-BUF", "Jacksonville"),
        ("KXSB-27-JAC-WAS", "Jacksonville"),
        ("KXSB-27-JAC-BUF", "Jacksonville"),
        ("KXNBA-27-WAS", "Jacksonville"),
        ("KXSB-27-ZZZ", "Jacksonville"),
        ("KXSB-27-JAC", "Buffalo Bills"),
    ])
    async def test_wrong_parent_matchups_unknown_codes_and_conflicting_names_refuse(self, ticker, name):
        markets, roster = self.markets()
        row = next(r for r in markets[1].outcomes if r.id == 643835)
        row.external_id, row.name = ticker, name
        odds, _ = await detail(ODDS_ID, markets, VERIFIED, roster=roster)
        assert by_name(odds, "Jacksonville Jaguars")["contributing_sources"] == ["odds_api", "polymarket"]
        assert by_name(odds, "Buffalo Bills")["contributing_sources"] == ["odds_api", "kalshi", "polymarket"]
        own, _ = await detail(KALSHI_ID, markets, VERIFIED, roster=roster)
        refused = next(r for r in own["outcomes"] if r["id"] == 643835)
        assert refused["contributing_sources"] == ["kalshi"]
        assert refused["probability"] == 0.105

    @pytest.mark.parametrize("extra", [
        [{"id": 901, "name": "Another club", "abbreviation": "JAC", "alternate_names": []}],
        [{"id": 901, "name": "Another club", "abbreviation": "XXX", "alternate_names": ["Jaguars"]}],
        [{"id": 901, "name": "Another club", "abbreviation": "JAC", "alternate_names": []},
         {"id": 902, "name": "A third club", "abbreviation": "JAC", "alternate_names": []}],
    ])
    async def test_the_venue_alias_cannot_override_conflicting_or_ambiguous_roster_claims(self, extra):
        markets, roster = self.markets()
        odds, _ = await detail(ODDS_ID, markets, VERIFIED, roster=roster + extra)
        assert by_name(odds, "Jacksonville Jaguars")["contributing_sources"] == ["odds_api", "polymarket"]
        own, _ = await detail(KALSHI_ID, markets, VERIFIED, roster=roster + extra)
        assert by_name(own, "Jacksonville")["contributing_sources"] == ["kalshi"]
