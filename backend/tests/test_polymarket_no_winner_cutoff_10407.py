"""#10407 A1 — Polymarket's stated no-winner cutoff, read from its own rule text.

PILLARS: MATCHING / TRUTH. SHIP: a playoff game page asks "who wins the
series" once, with one blended number; each venue keeps its own no-winner rules.

The two specimens are Gamma's own text for events 1120800 (Rays vs Yankees,
ALDS) and 1120859 (Brewers vs Padres, NLDS), retained by shopper at
`~/bainluck-dev/shopper/artifacts/shopper/10407-series-identity/
polymarket-gamma-event-11208{00,59}.json` (read 2026-10-04 15:12Z). The text is
copied verbatim below; Gamma's `endDate` for them is 10-12 / 10-11, which is
the date this parser must never return.

The ingest arm drives the REAL `_parse_event` and the REAL
`_process_event_batch` over a recording session (ruling 102 harness, as in
`test_polymarket_hindsight_opening_refused_2027.py`).
"""

from __future__ import annotations

import inspect
from collections import defaultdict

import pytest
from sqlalchemy import Insert
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket as poly
from app.utils import polymarket_no_winner_cutoff as cutoff_mod
from app.utils.market_label_normalization import compute_market_tier
from app.utils.odds_math import probability_to_american
from app.utils.polymarket_no_winner_cutoff import (
    CONFLICTING_INSTANTS,
    EVENT_MARKET_DISAGREE,
    MISSING_YEAR,
    NO_CLAUSE,
    NO_WINNER_CUTOFF_KEY,
    NOT_IN_FAMILY,
    NOT_ONE_MARKET,
    REFUSAL_REASONS,
    UNPARSEABLE_INSTANT,
    UNSUPPORTED_CLAUSE,
    parse_no_winner_cutoff,
)

NYY_TB_SLUG = "mlb-playoffs-who-will-win-series-rays-vs-yankees"
SD_MIL_SLUG = "mlb-playoffs-who-will-win-series-brewers-vs-padres"

NYY_TB_TEXT = (
    'This market will resolve to "Rays" if the Tampa Bay Rays win the 2026 MLB Playoffs American '
    "League Division Series between the Tampa Bay Rays and New York Yankees. This market will "
    'resolve to "Yankees" if the New York Yankees win the 2026 MLB Playoffs American League '
    "Division Series between the Tampa Bay Rays and New York Yankees.\n\n"
    "If a partial series is played and not completed by October 24, 2026, 11:59 PM ET, this "
    "market will resolve to 50-50.\n\n"
    "If the 2026 MLB Playoffs are cancelled, postponed after October 24, 2026, 11:59 PM ET, or "
    "there is otherwise no winner declared within that timeframe, this market will resolve to "
    "50-50.\n\n"
    "The resolution source for this market will be official information from MLB; however, a "
    "consensus of credible reporting may also be used."
)
SD_MIL_TEXT = (
    'This market will resolve to "Brewers" if the Milwaukee Brewers win the 2026 MLB Playoffs '
    "National League Division Series between the Milwaukee Brewers and San Diego Padres. This "
    'market will resolve to "Padres" if the San Diego Padres win the 2026 MLB Playoffs National '
    "League Division Series between the Milwaukee Brewers and San Diego Padres.\n\n"
    "If a partial series is played and not completed by October 23, 2026, 11:59 PM ET, this "
    "market will resolve to 50-50.\n\n"
    "If the 2026 MLB Playoffs are cancelled, postponed after October 23, 2026, 11:59 PM ET, or "
    "there is otherwise no winner declared within that timeframe, this market will resolve to "
    "50-50.\n\n"
    "The resolution source for this market will be official information from MLB; however, a "
    "consensus of credible reporting may also be used."
)
GAMMA_END_DATES = {"2026-10-12T03:59:00+00:00", "2026-10-11T03:59:00+00:00"}


def _parse(text, *, slug=NYY_TB_SLUG, event=None):
    return parse_no_winner_cutoff(slug=slug, market_descriptions=[text], event_description=event)


class TestTheSpecimensReadTheirStatedCutoff:
    def test_rays_yankees_is_october_24_1159_pm_et(self):
        value, reason = _parse(NYY_TB_TEXT, event=NYY_TB_TEXT)
        assert reason is None
        assert value == {
            "at": "2026-10-25T03:59:00+00:00",
            "source": "polymarket_rules_text",
            "family": "mlb_series_winner",
            "clauses": 2,
        }

    def test_brewers_padres_is_october_23_1159_pm_et(self):
        value, reason = _parse(SD_MIL_TEXT, slug=SD_MIL_SLUG, event=SD_MIL_TEXT)
        assert reason is None
        assert value["at"] == "2026-10-24T03:59:00+00:00"
        assert value["clauses"] == 2

    def test_gammas_end_date_is_never_the_result(self):
        for text, slug in ((NYY_TB_TEXT, NYY_TB_SLUG), (SD_MIL_TEXT, SD_MIL_SLUG)):
            value, _ = _parse(text, slug=slug)
            assert value["at"] not in GAMMA_END_DATES
        params = set(inspect.signature(parse_no_winner_cutoff).parameters)
        assert params == {"slug", "market_descriptions", "event_description"}

    def test_eastern_time_follows_the_calendar_not_a_fixed_offset(self):
        """After DST ends 11:59 PM ET is 04:59Z — a fixed -4h would be an hour early."""
        text = NYY_TB_TEXT.replace("October 24, 2026", "November 2, 2026")
        value, _ = _parse(text)
        assert value["at"] == "2026-11-03T04:59:00+00:00"

    def test_a_missing_event_text_reads_the_market_alone(self):
        assert _parse(NYY_TB_TEXT, event=None)[0]["at"] == "2026-10-25T03:59:00+00:00"
        assert _parse(NYY_TB_TEXT, event="")[0]["at"] == "2026-10-25T03:59:00+00:00"


class TestOutOfFamilyIsAbsent:
    @pytest.mark.parametrize("slug", [
        None, "", "mlb-playoffs-rays-vs-yankees-series-spread",
        "pro-baseball-2026-champion", "nba-playoffs-who-will-win-series-knicks-vs-celtics",
    ])
    def test_any_other_slug_reads_nothing(self, slug):
        assert _parse(NYY_TB_TEXT, slug=slug) == (None, NOT_IN_FAMILY)
        assert NOT_IN_FAMILY not in REFUSAL_REASONS


class TestEveryUnclearTextRefuses:
    def test_no_50_50_clause(self):
        text = NYY_TB_TEXT.split("\n\nIf a partial")[0]
        assert _parse(text) == (None, NO_CLAUSE)
        assert _parse(None) == (None, NO_CLAUSE)
        assert _parse("   ") == (None, NO_CLAUSE)

    def test_a_50_50_sentence_with_no_instant(self):
        text = NYY_TB_TEXT + "\n\nIf the series ends in a tie, this market will resolve to 50-50."
        assert _parse(text) == (None, UNSUPPORTED_CLAUSE)

    def test_a_date_with_no_year(self):
        text = NYY_TB_TEXT.replace("by October 24, 2026, 11:59 PM ET", "by October 24, 11:59 PM ET")
        assert _parse(text) == (None, MISSING_YEAR)

    def test_two_different_instants(self):
        text = NYY_TB_TEXT.replace("after October 24, 2026", "after October 25, 2026")
        assert _parse(text) == (None, CONFLICTING_INSTANTS)

    def test_a_50_slash_50_sentence_is_still_a_sentence_that_must_be_admitted(self):
        text = NYY_TB_TEXT + (
            "\n\nIf the series is suspended after October 30, 2026, 11:59 PM ET, this market "
            "will resolve 50/50."
        )
        assert _parse(text) == (None, UNSUPPORTED_CLAUSE)

    def test_the_unfinished_series_clause_must_agree_too(self):
        text = NYY_TB_TEXT.replace("by October 24, 2026", "by October 23, 2026")
        assert _parse(text) == (None, CONFLICTING_INSTANTS)

    @pytest.mark.parametrize("bad", ["11:59 PM PT", "11:59 AM ET", "11:59 PM", "13:59 PM ET"])
    def test_an_unread_time_or_zone(self, bad):
        text = NYY_TB_TEXT.replace("by October 24, 2026, 11:59 PM ET", f"by October 24, 2026, {bad}")
        assert _parse(text) == (None, UNPARSEABLE_INSTANT)

    def test_an_impossible_date(self):
        text = NYY_TB_TEXT.replace("October 24, 2026", "February 30, 2026")
        assert _parse(text) == (None, UNPARSEABLE_INSTANT)

    def test_event_and_market_disagree(self):
        assert _parse(NYY_TB_TEXT, event=SD_MIL_TEXT) == (None, EVENT_MARKET_DISAGREE)

    def test_an_event_text_that_says_nothing_is_not_agreement(self):
        assert _parse(NYY_TB_TEXT, event="Who will win the series?") == (None, EVENT_MARKET_DISAGREE)

    def test_the_family_is_one_market(self):
        two = parse_no_winner_cutoff(slug=NYY_TB_SLUG, market_descriptions=[NYY_TB_TEXT] * 2)
        none = parse_no_winner_cutoff(slug=NYY_TB_SLUG, market_descriptions=[])
        assert two == none == (None, NOT_ONE_MARKET)


class TestOnlyTheNoWinnerClausesAdmit:
    """Root review 2026-10-04: a date and "50-50" in one sentence are not a
    no-winner rule. Both of root's controls, verbatim, plus the reviewer's."""

    def test_root_control_1_negated_resolution_refuses(self):
        negated = NYY_TB_TEXT.replace("will resolve to 50-50", "will not resolve to 50-50")
        assert negated.count("will not resolve to 50-50") == 2
        assert _parse(negated, event=negated) == (None, UNSUPPORTED_CLAUSE)

    def test_root_control_2_a_winner_condition_refuses(self):
        text = ("If the Yankees win by October 24, 2026, 11:59 PM ET, this market will "
                "resolve to 50-50.")
        assert _parse(text, event=text) == (None, UNSUPPORTED_CLAUSE)

    @pytest.mark.parametrize("old,new", [
        ("this market will resolve to 50-50.\n\nIf the 2026",
         "this market will NOT resolve to 50-50.\n\nIf the 2026"),
        ("If a partial series is played and not completed by",
         "If the Rays WIN the series by"),
    ])
    def test_the_reviewers_variants_refuse(self, old, new):
        assert NYY_TB_TEXT.count(old) == 1
        assert _parse(NYY_TB_TEXT.replace(old, new)) == (None, UNSUPPORTED_CLAUSE)

    def test_an_amended_wording_refuses(self):
        text = NYY_TB_TEXT.replace(
            "11:59 PM ET, this market will resolve to 50-50.\n\nIf the 2026",
            "11:59 PM ET, this market will resolve to 50-50 unless MLB rules otherwise.\n\nIf the 2026",
        )
        assert _parse(text) == (None, UNSUPPORTED_CLAUSE)

    def test_the_playoffs_year_must_be_the_instants(self):
        text = NYY_TB_TEXT.replace("If the 2026 MLB Playoffs", "If the 2025 MLB Playoffs")
        assert _parse(text) == (None, UNSUPPORTED_CLAUSE)

    def test_both_retained_positives_still_admit(self):
        assert _parse(NYY_TB_TEXT, event=NYY_TB_TEXT)[0]["at"] == "2026-10-25T03:59:00+00:00"
        assert _parse(SD_MIL_TEXT, slug=SD_MIL_SLUG, event=SD_MIL_TEXT)[0]["at"] == (
            "2026-10-24T03:59:00+00:00")


def test_the_module_never_reads_end_date_resolution_date_or_neg_risk():
    source = inspect.getsource(cutoff_mod)
    code = "\n".join(line.split("#")[0] for line in source.split('"""', 2)[2].splitlines())
    for forbidden in ("end_date", "endDate", "resolution_date", "neg_risk", "negRisk", "now("):
        assert forbidden not in code, forbidden


# ── the ingest writer ───────────────────────────────────────────────────────


def _venue_event(*, slug=NYY_TB_SLUG, text=NYY_TB_TEXT, event_text=None):
    """Gamma event 1120800's shape: one market, two named outcomes."""
    return {
        "id": "1120800",
        "title": "MLB Playoffs: Who Will Win Series? - Rays vs. Yankees",
        "slug": slug,
        "description": text if event_text is None else event_text,
        "active": True,
        "closed": False,
        "archived": False,
        "endDate": "2026-10-12T03:59:00Z",
        "startDate": "2026-10-02T19:58:00Z",
        "negRisk": False,
        "tags": [{"slug": "mlb-playoffs"}, {"slug": "series-winner"}, {"slug": "mlb"}],
        "markets": [{
            "id": "5215308",
            "conditionId": "0x5c0bc358",
            "question": "MLB Playoffs: Who Will Win Series? - Rays vs. Yankees",
            "slug": slug,
            "description": text,
            "outcomes": '["Rays", "Yankees"]',
            "outcomePrices": '["0.645", "0.355"]',
            "clobTokenIds": '["111", "222"]',
            "bestBid": 0.64,
            "bestAsk": 0.65,
            "lastTradePrice": 0.645,
            "endDate": "2026-10-12T03:59:00Z",
            "closed": False,
        }],
    }


class _Result:
    def __init__(self, fake):
        self._fake = fake

    def scalar_one(self):
        self._fake.next_id += 1
        return self._fake.next_id

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None

    @property
    def rowcount(self):
        return 0


class _Savepoint:
    is_active = True

    async def commit(self):
        self.is_active = False

    async def rollback(self):
        self.is_active = False


class _Session:
    def __init__(self):
        self.statements, self.next_id = [], 1000

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _Result(self)

    async def commit(self):
        pass

    async def begin_nested(self):
        return _Savepoint()


async def _ingest(monkeypatch, raw):
    event = PolymarketAPIService()._parse_event(raw)
    assert event is not None and len(event.markets) == 1, "the parser refused Gamma's shape"
    assert event.description and event.markets[0].description, "rule text never reached the DTO"
    fake = _Session()
    monkeypatch.setattr(poly, "get_task_session", lambda: fake)
    stats = defaultdict(int, {"by_category": {}, "errors": []})
    await poly._process_event_batch(
        [event], stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
        pg_insert, probability_to_american, compute_market_tier,
    )
    assert not stats.get("errors"), stats.get("errors")
    parents = [
        s for s in fake.statements
        if isinstance(s, Insert) and s.table.name == "futures_markets"
    ]
    assert len(parents) == 1, "the writer produced no market row"
    compiled = parents[0].compile(dialect=postgresql.dialect())
    return compiled.params, str(compiled), stats


class TestTheWriterStoresIt:
    async def test_the_specimen_row_carries_the_cutoff_beside_its_slug(self, monkeypatch):
        params, sql, stats = await _ingest(monkeypatch, _venue_event())
        meta = params["market_metadata"]
        assert meta["polymarket_event_slug"] == NYY_TB_SLUG
        assert meta[NO_WINNER_CUTOFF_KEY] == {
            "at": "2026-10-25T03:59:00+00:00",
            "source": "polymarket_rules_text",
            "family": "mlb_series_winner",
            "clauses": 2,
        }
        assert stats["no_winner_cutoff_stored"] == 1
        # Existing rows acquire it on the next ordinary poll: the conflict arm
        # SETs the freshly built dict (#2222 merges only its own stamp back).
        update = sql.split("DO UPDATE SET", 1)[1]
        assert "market_metadata = " in update
        rewrites = [k for k, v in params.items()
                    if k != "market_metadata" and NO_WINNER_CUTOFF_KEY in str(v)]
        assert rewrites and all(f"%({k})s" in update for k in rewrites)

    async def test_resolution_date_stays_gammas_end_date(self, monkeypatch):
        """The cutoff is its OWN field; the stored schedule is not overwritten."""
        params, _, _ = await _ingest(monkeypatch, _venue_event())
        assert params["resolution_date"].isoformat() == "2026-10-12T03:59:00+00:00"
        assert NO_WINNER_CUTOFF_KEY in params["market_metadata"]

    async def test_an_out_of_family_event_has_no_key_and_counts_nothing(self, monkeypatch):
        params, _, stats = await _ingest(
            monkeypatch, _venue_event(slug="mlb-playoffs-rays-vs-yankees-series-spread")
        )
        meta = params["market_metadata"]
        assert NO_WINNER_CUTOFF_KEY not in meta
        assert "no_winner_cutoff_refused" not in stats
        assert stats.get("no_winner_cutoff_stored", 0) == 0

    async def test_a_negated_rule_is_never_stored(self, monkeypatch):
        negated = NYY_TB_TEXT.replace("will resolve to 50-50", "will not resolve to 50-50")
        params, _, stats = await _ingest(monkeypatch, _venue_event(text=negated))
        assert NO_WINNER_CUTOFF_KEY not in params["market_metadata"]
        assert stats["no_winner_cutoff_refused"] == {UNSUPPORTED_CLAUSE: 1}

    async def test_a_refusal_leaves_the_key_absent_and_is_counted(self, monkeypatch):
        params, _, stats = await _ingest(monkeypatch, _venue_event(event_text=SD_MIL_TEXT))
        meta = params["market_metadata"]
        assert NO_WINNER_CUTOFF_KEY not in meta
        assert stats["no_winner_cutoff_refused"] == {EVENT_MARKET_DISAGREE: 1}
        assert stats.get("no_winner_cutoff_stored", 0) == 0
