"""Guard tests for automatic match-market linkage (Q426).

Anchored to what 2026-08-28 actually measured on production and on the
exchange, not to hypotheticals:

* The committed register carried **96 R128 fixtures with `status: "missing"`
  at both sources**, written once by the draw census at 2026-08-27T18:00Z and
  never revisited. `/api/tournaments/us-open` reported `slate.incoherent: 96`
  and `slate.price_state: "dark"`.
* Kalshi carried **47 KXATPMATCH + 49 KXWTAMATCH** open main-draw events at the
  same moment — including `KXATPMATCH-26AUG30YIBWAL`, the Wu vs Walton match
  Alex checked — and our database held **zero** of them.
* A Kalshi match outcome names its own player (`"Brandon Nakashima"`, ext
  `…-BORNAK-NAK`). Polymarket's decomposed sub-market is an unlabelled
  `Yes`/`No`, which is why only Kalshi is resolvable here.
* The same two players meet more than once a season: our tables hold
  `KXATPCHALLENGERMATCH-26JUN01WALTUN` ("Walton vs Wu") next to this week's
  `KXATPMATCH-26AUG30YIBWAL`. Kalshi settled markets stay `status='open'`
  (gotcha #33), so the date window is the only guard that separates them.

The ship test goes through `build_slate`, not just the resolver: a pure-library
guard stays green when the thing that renders stops printing the feature.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.utils.tournament_link_resolver import (
    AMBIGUOUS_CANDIDATES,
    AMBIGUOUS_SIDES,
    EVIDENCE_KIND,
    NO_CANDIDATE,
    STALE_REMATCH,
    apply_resolved_links,
    name_tokens,
    names_correspond,
    resolve_matchup_links,
)
from app.utils.tournament_register import (
    SCHEMA_VERSION,
    us_open_2026_contract,
    validate_register,
)
from app.utils.tournament_slate import build_slate

NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)
MATCH_DAY = datetime(2026, 8, 30, 4, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures shaped like the real thing
# ---------------------------------------------------------------------------

def _player(key, name, draw="mens-singles"):
    return {
        "entity_key": key, "display_name": name, "draw": draw,
        "role": "participant", "seed": None, "country": None,
        "draw_slot": None, "section": None, "sources": [],
        "evidence": {"kind": "draw-ceremony-espn",
                     "observed_at": "2026-08-27T18:00:00+00:00"},
    }


def _missing_block(source="kalshi"):
    """Exactly what `ingest_tournament_draw.py` wrote for all 96 R128 rows."""
    return {
        "source": source,
        "kind": "match",
        "market_id": None,
        "outcome_id": None,
        "status": "missing",
        "terminal_result": None,
        "evidence": {
            "kind": "draw-fixture-census-absent",
            "observed_at": "2026-08-27T18:00:00+00:00",
            "note": "fixture from the released draw; no match market pinned at "
                    "this source when the draw was ingested",
        },
    }


def _register(players=None, matchups=None):
    players = players or [
        _player("wu-yibing", "Wu Yibing"),
        _player("adam-walton", "Adam Walton"),
    ]
    matchups = matchups if matchups is not None else [{
        "matchup_key": "mens-singles:adam-walton-vs-wu-yibing:2026-08-30",
        "draw": "mens-singles",
        "round": "R128",
        "scheduled_date": MATCH_DAY.isoformat(),
        "players": ["wu-yibing", "adam-walton"],
        "sources": [_missing_block("kalshi"), _missing_block("polymarket")],
    }]
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open", "season": "2026", "version": 9,
        "generated_at": NOW.isoformat(), "draw_released": True,
        "players": players, "matchups": matchups,
    }


def _candidate(
    market_id=7001,
    ticker="KXATPMATCH-26AUG30YIBWAL",
    names=("Yibing Wu", "Adam Walton"),
    match_date=date(2026, 8, 30),
    source="kalshi",
):
    """A Kalshi match market in the shape `_load_candidates` produces."""
    return {
        "source": source, "market_id": market_id, "external_id": ticker,
        "name": "Wu vs Walton", "match_date": match_date,
        "outcomes": [
            {"outcome_id": market_id * 10 + i, "name": n,
             "external_id": f"{ticker}-{n[:3].upper()}"}
            for i, n in enumerate(names)
        ],
    }


# ---------------------------------------------------------------------------
# G1 — THE SHIP. A blank R128 card gets a probability, through the renderer.
# ---------------------------------------------------------------------------

def test_registered_fixture_with_no_pinned_market_becomes_a_priced_slate_row():
    """Alex's exact match: Wu vs Walton renders numbers instead of nothing.

    RED-FIRST: without the overlay the committed `missing` block is all there
    is, `build_slate` finds no `live` block, and both sides price to None. This
    asserts the whole chain — resolve, apply, render — not just the resolver.
    """
    register = _register()

    # Before: the state Alex saw.
    before = build_slate(register, prices={}, now=NOW)
    assert before["count"] == 1
    assert before["matches"][0]["priced"] is False
    assert [s["probability"] for s in before["matches"][0]["sides"]] == [None, None]

    resolved = resolve_matchup_links(register, [_candidate()], now=NOW)
    assert resolved["counters"]["resolved"] == 1

    linked_register, applied = apply_resolved_links(register, resolved["links"])
    assert applied == 1

    prices = {
        70010: {"probability": 0.485, "opening_probability": 0.50,
                "observed_at": NOW - timedelta(minutes=8)},
        70011: {"probability": 0.515, "opening_probability": 0.50,
                "observed_at": NOW - timedelta(minutes=8)},
    }
    after = build_slate(linked_register, prices=prices, now=NOW)
    row = after["matches"][0]

    assert row["priced"] is True
    assert row["coherent"] is True
    by_name = {s["display_name"]: s["probability"] for s in row["sides"]}
    # The side attribution is the half that can be silently backwards.
    assert by_name["Wu Yibing"] == pytest.approx(0.485, abs=1e-6)
    assert by_name["Adam Walton"] == pytest.approx(0.515, abs=1e-6)


def test_resolved_block_maps_each_player_to_their_own_outcome():
    """`Yibing Wu` is `wu-yibing`. An inverted card is worse than a blank one."""
    resolved = resolve_matchup_links(_register(), [_candidate()], now=NOW)
    block = resolved["links"]["mens-singles:adam-walton-vs-wu-yibing:2026-08-30|kalshi"]

    assert block["status"] == "live"
    assert block["market_id"] == 7001
    assert block["evidence"]["kind"] == EVIDENCE_KIND
    assert block["sides"]["wu-yibing"]["source_label"] == "Yibing Wu"
    assert block["sides"]["adam-walton"]["source_label"] == "Adam Walton"
    assert (
        block["sides"]["wu-yibing"]["outcome_id"]
        != block["sides"]["adam-walton"]["outcome_id"]
    )


def test_a_linked_register_still_validates():
    """An overlay must not produce a register the contract would reject."""
    register = _register()
    resolved = resolve_matchup_links(register, [_candidate()], now=NOW)
    linked, _ = apply_resolved_links(register, resolved["links"])
    findings = validate_register(linked, us_open_2026_contract())
    assert not [f for f in findings if f.startswith("MATCHUP_")], findings
    assert "MAPPED_ENTRY_MISSING_IDENTITY" not in findings
    assert "MISSING_ENTRY_HAS_IDENTITY" not in findings


# ---------------------------------------------------------------------------
# G2 — THE CONTROL. A curated pin is untouchable.
# ---------------------------------------------------------------------------

def test_a_pinned_identity_is_never_overwritten():
    """The register is the curation truth; this may only fill a blank.

    A control, and the one that matters most: if this ever goes green in the
    other direction, a task is silently re-pointing a reviewed, committed row.
    """
    pinned = {
        "source": "kalshi", "kind": "match",
        "market_id": 111, "outcome_id": 222, "status": "live",
        "terminal_result": None,
        "evidence": {"kind": "match-market-census",
                     "observed_at": "2026-08-27T00:15:00+00:00"},
        "sides": {
            "wu-yibing": {"outcome_id": 222, "source_label": "Wu Yibing"},
            "adam-walton": {"outcome_id": 223, "source_label": "Adam Walton"},
        },
    }
    register = _register(matchups=[{
        "matchup_key": "mens-singles:adam-walton-vs-wu-yibing:2026-08-30",
        "draw": "mens-singles", "round": "R128",
        "scheduled_date": MATCH_DAY.isoformat(),
        "players": ["wu-yibing", "adam-walton"],
        "sources": [pinned],
    }])

    resolved = resolve_matchup_links(register, [_candidate()], now=NOW)
    assert resolved["counters"]["needy"] == 0
    assert resolved["links"] == {}

    # Even handed a link for that key by force, apply refuses a non-missing block.
    forced = {"mens-singles:adam-walton-vs-wu-yibing:2026-08-30|kalshi":
              _candidate()}
    out, applied = apply_resolved_links(register, forced)
    assert applied == 0
    assert out["matchups"][0]["sources"][0]["market_id"] == 111


def test_apply_does_not_mutate_the_input_register():
    """The route holds a loaded register dict; an in-place edit would leak."""
    register = _register()
    original = register["matchups"][0]["sources"][0]["status"]
    resolved = resolve_matchup_links(register, [_candidate()], now=NOW)
    apply_resolved_links(register, resolved["links"])
    assert register["matchups"][0]["sources"][0]["status"] == original == "missing"


# ---------------------------------------------------------------------------
# G3 — REFUSALS. Ambiguity produces a blank card, never a guess.
# ---------------------------------------------------------------------------

def test_two_candidates_for_one_fixture_refuse():
    """The uniqueness backstop the initials rule's safety rests on."""
    twin = _candidate(market_id=7002, ticker="KXATPMATCH-26AUG30WALYIB")
    resolved = resolve_matchup_links(_register(), [_candidate(), twin], now=NOW)
    assert resolved["counters"]["resolved"] == 0
    assert resolved["counters"][AMBIGUOUS_CANDIDATES] == 1


def test_same_surname_same_initial_players_refuse_rather_than_pick():
    """`A. Smith` must not bind to a market naming Adam and Alex Smith.

    This is the collision that makes an initials rule dangerous in the
    abstract. The bijection check refuses it: one outcome corresponds to both
    registered players, so no unique assignment exists.
    """
    register = _register(
        players=[_player("a-smith", "A. Smith"), _player("alex-smith", "Alex Smith")],
        matchups=[{
            "matchup_key": "mens-singles:a-smith-vs-alex-smith:2026-08-30",
            "draw": "mens-singles", "round": "R128",
            "scheduled_date": MATCH_DAY.isoformat(),
            "players": ["a-smith", "alex-smith"],
            "sources": [_missing_block("kalshi")],
        }],
    )
    candidate = _candidate(names=("Adam Smith", "Alex Smith"))
    resolved = resolve_matchup_links(register, [candidate], now=NOW)
    assert resolved["counters"]["resolved"] == 0
    assert resolved["links"] == {}


def test_a_fixture_with_no_market_anywhere_stays_missing():
    resolved = resolve_matchup_links(_register(), [], now=NOW)
    assert resolved["counters"][NO_CANDIDATE] == 1
    assert resolved["links"] == {}


def test_a_market_naming_only_one_of_the_two_players_is_a_near_miss_not_an_absence():
    """A linkage defect must not read like "nobody quotes this match"."""
    candidate = _candidate(names=("Adam Walton", "Someone Else"))
    resolved = resolve_matchup_links(_register(), [candidate], now=NOW)
    assert resolved["counters"][AMBIGUOUS_SIDES] == 1
    assert resolved["counters"][NO_CANDIDATE] == 0


# ---------------------------------------------------------------------------
# G4 — THE DATE WINDOW. gotcha #33: `status='open'` is not "not yet played".
# ---------------------------------------------------------------------------

def test_an_earlier_meeting_of_the_same_two_players_is_refused():
    """`KXATPCHALLENGERMATCH-26JUN01WALTUN` is Walton vs Wu, and is not this match."""
    june = _candidate(
        market_id=7009,
        ticker="KXATPMATCH-26JUN01WALTUN",
        match_date=date(2026, 6, 1),
    )
    resolved = resolve_matchup_links(_register(), [june], now=NOW)
    assert resolved["counters"]["resolved"] == 0
    assert resolved["counters"][STALE_REMATCH] == 1


def test_a_candidate_with_no_parseable_date_fails_closed():
    undated = _candidate(match_date=None)
    resolved = resolve_matchup_links(_register(), [undated], now=NOW)
    assert resolved["counters"]["resolved"] == 0


def test_the_window_absorbs_a_utc_day_boundary():
    """A night session in New York is the next day in UTC; that is still it."""
    next_day = _candidate(match_date=date(2026, 8, 31))
    resolved = resolve_matchup_links(_register(), [next_day], now=NOW)
    assert resolved["counters"]["resolved"] == 1


# ---------------------------------------------------------------------------
# G5 — SOURCE SCOPE. Polymarket's unlabelled Yes/No is never guessed at.
# ---------------------------------------------------------------------------

def test_polymarket_blocks_are_left_missing():
    """Two `missing` blocks, and only the one we can read is filled."""
    pm = _candidate(source="polymarket", market_id=8001)
    resolved = resolve_matchup_links(_register(), [_candidate(), pm], now=NOW)
    keys = set(resolved["links"])
    assert keys == {"mens-singles:adam-walton-vs-wu-yibing:2026-08-30|kalshi"}

    linked, _ = apply_resolved_links(_register(), resolved["links"])
    blocks = {b["source"]: b for b in linked["matchups"][0]["sources"]}
    assert blocks["polymarket"]["status"] == "missing"
    assert blocks["kalshi"]["status"] == "live"


# ---------------------------------------------------------------------------
# Name correspondence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a,b", [
    ("Wu Yibing", "Yibing Wu"),                       # word order
    ("Felix Auger-Aliassime", "Felix Auger Aliassime"),  # hyphen
    ("J.J. Wolf", "Jeffrey John Wolf"),               # initials
    ("Thiago Tirante", "Thiago Agustin Tirante"),     # dropped middle name
])
def test_names_that_are_the_same_player(a, b):
    assert names_correspond(name_tokens(a), name_tokens(b))


@pytest.mark.parametrize("a,b", [
    ("Wu Yibing", "Wu Jiaxin"),          # shared surname, different player
    ("J.J. Wolf", "Jeffrey John Fritz"), # initials match, surname does not
    ("Taylor Fritz", "Taylor Townsend"),
    ("Adam Walton", ""),
])
def test_names_that_are_different_players(a, b):
    assert not names_correspond(name_tokens(a), name_tokens(b))


def test_the_subset_rule_cannot_tell_a_suffix_from_a_middle_name():
    """A known and accepted limit, recorded rather than papered over.

    ``Adam Walton`` is a strict subset of ``Adam Walton Jr``, so the rule that
    forgives a dropped middle name also forgives a dropped generational suffix
    and calls them one player. Tightening it would need a suffix denylist,
    which is a new thing to be wrong about for a case tennis does not have.

    It is safe here because correspondence is never the whole test: a father
    and son in one draw would produce either two candidate markets for the
    fixture or one outcome matching two registered players, and both refuse.
    This test exists so the behaviour is a decision with a reason next to it,
    not a surprise the next reader has to re-derive.
    """
    assert names_correspond(name_tokens("Adam Walton"), name_tokens("Adam Walton Jr"))


def test_an_unnamed_outcome_corresponds_to_nobody():
    assert not names_correspond(name_tokens(None), name_tokens("Adam Walton"))
    assert name_tokens(None) == frozenset()


# ---------------------------------------------------------------------------
# G6 — INGESTION. The series that were unreachable are on the rescue net.
# ---------------------------------------------------------------------------

def test_tennis_match_and_nationality_series_are_on_the_kalshi_rescue_net():
    """The gap that made all of the above necessary.

    Golf got a guaranteed supplementary fetch in #163, combat sports in #173,
    and tennis never did — so US Open match markets and the men's/women's
    nationality props depended on a main scan whose own report reads
    `verdict: frozen`, `wrapped: false` on 24 of 24 recorded beats.
    """
    from app.services.kalshi_api import _SPORTS_SERIES_TICKERS

    for series in ("KXATPMATCH", "KXWTAMATCH", "KXATPNATSTAGE", "KXWTANATSTAGE"):
        assert series in _SPORTS_SERIES_TICKERS, f"{series} is not on the rescue net"


def test_daily_tennis_series_always_run_their_supplementary_fetch():
    """One stale event must not suppress the rescue for all of today's.

    The supplementary loop skips a series when the main scan already produced
    ANY event with its prefix. For a series that turns over daily that is
    self-sealing: our database held 8 open `KXATPMATCH` rows, every one created
    2026-08-19, which is precisely enough to satisfy the skip forever.
    """
    from app.services.kalshi_api import _ALWAYS_FETCH_SERIES

    for series in ("KXATPMATCH", "KXWTAMATCH", "KXATPNATSTAGE", "KXWTANATSTAGE"):
        assert series in _ALWAYS_FETCH_SERIES, (
            f"{series} may be skipped when partially present"
        )


def test_tennis_match_series_fetch_with_nested_markets():
    """A match event is two one-line markets, so it must not be stripped.

    `_HEAVY_TOKENS` empties a series' nested markets and hands it to the
    per-event backfill, which reached 424 of 15,235 candidates on the beat
    measured 2026-08-28. A tennis series that landed in that queue would be no
    better off than it was before this fix.
    """
    from app.services.kalshi_api import _HEAVY_TOKENS

    for series in ("KXATPMATCH", "KXWTAMATCH", "KXATPNATSTAGE", "KXWTANATSTAGE"):
        assert not any(token in series for token in _HEAVY_TOKENS), (
            f"{series} would be fetched without nested markets"
        )


# ---------------------------------------------------------------------------
# G7 — THE TASK. It publishes, and it says so out loud when it publishes nothing.
# ---------------------------------------------------------------------------

async def test_task_publishes_links_and_reports_its_counters(monkeypatch):
    from app.tasks import tournament_matchup_linker as linker

    written: dict[str, object] = {}

    async def _fake_write(slug, payload):
        written[slug] = payload
        return True

    async def _fake_candidates(session, series, *, now=None):
        assert series == ("KXATPMATCH",)
        return [_candidate()]

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(linker, "load_register", lambda t, s: _register())
    monkeypatch.setattr(linker, "_load_candidates", _fake_candidates)
    monkeypatch.setattr(linker, "_write_links", _fake_write)
    monkeypatch.setattr(linker, "_now", lambda: NOW)
    monkeypatch.setattr("app.tasks.base.get_task_session", lambda: _Session())

    stats = await linker._link_tournament_matchups(
        watched=({"tournament": "us-open", "season": "2026",
                  "kalshi_series": ("KXATPMATCH",)},)
    )

    assert stats["resolved"] == 1
    assert stats["published"] == 1
    assert stats["written"] == 1
    payload = written["us-open"]
    assert payload["counters"]["resolved"] == 1
    assert list(payload["links"]) == [
        "mens-singles:adam-walton-vs-wu-yibing:2026-08-30|kalshi"
    ]


async def test_task_reports_needy_and_resolved_separately_when_it_resolves_nothing(
    monkeypatch
):
    """"It ran" is not "it worked" — the zero-yield case must be loud."""
    from app.tasks import tournament_matchup_linker as linker

    async def _none(session, series, *, now=None):
        return []

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(linker, "load_register", lambda t, s: _register())
    monkeypatch.setattr(linker, "_load_candidates", _none)
    monkeypatch.setattr(linker, "_write_links", lambda slug, payload: _ok())
    monkeypatch.setattr(linker, "_now", lambda: NOW)
    monkeypatch.setattr("app.tasks.base.get_task_session", lambda: _Session())

    async def _ok():
        return True

    stats = await linker._link_tournament_matchups(
        watched=({"tournament": "us-open", "season": "2026",
                  "kalshi_series": ("KXATPMATCH",)},)
    )
    assert stats["needy"] == 1
    assert stats["resolved"] == 0
    assert stats[NO_CANDIDATE] == 1


async def test_one_broken_tournament_does_not_starve_its_siblings(monkeypatch):
    from app.tasks import tournament_matchup_linker as linker

    def _load(tournament, season):
        if tournament == "broken":
            raise RuntimeError("poison")
        return _register()

    async def _cands(session, series, *, now=None):
        return [_candidate()]

    async def _write(slug, payload):
        return True

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(linker, "load_register", _load)
    monkeypatch.setattr(linker, "_load_candidates", _cands)
    monkeypatch.setattr(linker, "_write_links", _write)
    monkeypatch.setattr(linker, "_now", lambda: NOW)
    monkeypatch.setattr("app.tasks.base.get_task_session", lambda: _Session())

    stats = await linker._link_tournament_matchups(watched=(
        {"tournament": "broken", "season": "2026", "kalshi_series": ("KXATPMATCH",)},
        {"tournament": "us-open", "season": "2026", "kalshi_series": ("KXATPMATCH",)},
    ))
    assert stats["by_tournament"]["broken"]["error"] == "RuntimeError"
    assert stats["resolved"] == 1


def test_watched_tournaments_name_their_kalshi_series_explicitly():
    from app.tasks.tournament_matchup_linker import WATCHED

    assert WATCHED
    for entry in WATCHED:
        assert entry["tournament"] and entry["season"]
        assert entry["kalshi_series"], entry["tournament"]
