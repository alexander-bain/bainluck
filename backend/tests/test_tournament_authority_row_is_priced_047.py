"""THE AUTHORITY'S PAIRING CARRIES ITS OWN PRICE (lane1/047).

Measured on production at 2026-09-02T06:00Z, not hypothesised.

``GET /api/tournaments/us-open`` carried eleven slate rows.  Ten were ordinary
register rows.  The eleventh was ``espn:182703``, ``pairing_source:
"authority"`` — the Q505 substitution for a register fixture whose pairing the
ESPN scoreboard contradicts — and it read::

    Rafael Jodar        Bu Yunchaokete
    Nobody is quoting this match yet. It is in the draw with no probability
    against it.

At that moment ``futures_markets`` held, and had held for hours::

    60006342  KXATPMATCH-26SEP01JODYUN  "Jodar vs Bu"  kalshi  status=open
      223756711  "Rafael Jodar"     KXATPMATCH-26SEP01JODYUN-JOD  0.895
      223756712  "Yunchaokete Bu"   KXATPMATCH-26SEP01JODYUN-YUN  0.105

Both legs open, both named in full, summing to 1.000.  The sentence was false,
and false in the most expensive direction a probability product has: it told a
reader the market was silent while we quoted 90/10 one tab over.

WHY IT WAS BLANK, AND WHY NOTHING WAS RED.  ``authority_match_row`` took no
``prices`` argument at all.  The only identities this page reads a price
through are the ``(market_id, outcome_id)`` pairs the register pins, and the
register — by construction on this exact row — names the wrong people.  So the
blank was structural rather than a lookup that missed, and every existing guard
passed: they all assert the row is unpriced, which was the whole intended
behaviour of Q505.  Q505's own docstring named the missing piece — *"when the
match market for the real pairing is linked, the ordinary priced row takes
over"* — and nothing ever linked it.

WHAT THIS FILE PINS, and the second one is as load-bearing as the first:

1. An authority row whose two ESPN-named players resolve cleanly to a match
   market we hold renders that market's numbers.
2. Q503's refusal is untouched.  The number that was withheld is the one quoted
   for the pairing nobody is playing, and it still cannot reach this row —
   ``test_the_register_pinned_price_still_cannot_reach_the_authority_row``.
   Pricing this row from the register's pins would re-create the exact defect
   Q503 fixed, and it would look like a fix.

``resolve_authority_links`` and the new ``authority_match_row`` keywords are
imported INSIDE the tests that need them.  At module scope they make the whole
file uncollectable against the pre-fix tree — exit 2, an ImportError, a story
about the harness rather than a result (gotcha #124).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.utils.tournament_register import SCHEMA_VERSION
from app.utils.tournament_slate import build_slate

NOW = datetime(2026, 9, 2, 6, 0, tzinfo=timezone.utc)
START = "2026-09-02T17:00:00+00:00"
COMP = "182703"

JODAR = "espn:athlete:12657"
BU = "espn:athlete:11382"

# The two register outcome ids pinned for the pairing ESPN contradicts
# (Jodar vs Kokkinakis). They exist so the tests can prove they are NOT read.
REG_JODAR_OUTCOME = 900001
REG_KOKKINAKIS_OUTCOME = 900002
# The two Kalshi outcome ids that really price Jodar vs Bu.
KALSHI_JODAR_OUTCOME = 223756711
KALSHI_BU_OUTCOME = 223756712


def _register():
    """The US Open register as it stood: fixture 182703 pinned to the WRONG two.

    The pairing is a real production artefact — a post-ceremony census read it
    off a Kalshi market title — and it is what makes this an authority row.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 9,
        "generated_at": NOW.isoformat(),
        "draw_released": True,
        "players": [
            {"entity_key": "rafael-jodar", "display_name": "Rafael Jodar",
             "draw": "mens-singles", "sources": []},
            {"entity_key": "thanasi-kokkinakis", "display_name": "Thanasi Kokkinakis",
             "draw": "mens-singles", "sources": []},
        ],
        "matchups": [{
            "matchup_key": "mens-singles:rafael-jodar-vs-thanasi-kokkinakis:2026-08-30",
            "draw": "mens-singles",
            "round": "R128",
            "scheduled_date": START,
            "players": ["rafael-jodar", "thanasi-kokkinakis"],
            "evidence": {"espn_competition_id": COMP},
            "sources": [{
                "source": "kalshi", "kind": "match", "status": "live",
                "market_id": 59693730, "outcome_id": REG_JODAR_OUTCOME,
                "market_external_id": "KXATPMATCH-26AUG30JODKOK",
                "terminal_result": None,
                "evidence": {"kind": "draw-census", "espn_competition_id": COMP},
                "sides": {
                    "rafael-jodar": {"outcome_id": REG_JODAR_OUTCOME},
                    "thanasi-kokkinakis": {"outcome_id": REG_KOKKINAKIS_OUTCOME},
                },
            }],
        }],
    }


def _listed(competitors=None):
    """ESPN's ``order_of_play`` entry for competition 182703."""
    return {COMP: {
        "espn_competition_id": COMP,
        "draw": "mens-singles",
        "state": "upcoming",
        "start_at": START,
        "start_is_tbd": False,
        "status_detail": "Wed, September 2nd at 1:00 PM EDT",
        "espn_round": "R64",
        "players": ["Bu Yunchaokete", "Rafael Jodar"],
        "competitors": competitors if competitors is not None else [
            {"espn_athlete_id": 12657, "name": "Rafael Jodar", "determined": True,
             "country": "Spain", "flag_url": "esp.png", "order": 1},
            {"espn_athlete_id": 11382, "name": "Bu Yunchaokete", "determined": True,
             "country": "China", "flag_url": "chn.png", "order": 2},
        ],
    }}


def _candidate(
    market_id=60006342,
    ticker="KXATPMATCH-26SEP01JODYUN",
    names=("Rafael Jodar", "Yunchaokete Bu"),
    match_date=date(2026, 9, 1),
):
    """The Kalshi market, in the shape ``_load_candidates`` produces.

    Note the two spellings that must correspond: ESPN publishes the man as
    ``Bu Yunchaokete`` and Kalshi as ``Yunchaokete Bu``. Same player, reversed —
    which is exactly why the shared rule compares token SETS.
    """
    return {
        "source": "kalshi", "market_id": market_id, "external_id": ticker,
        "name": "Jodar vs Bu", "match_date": match_date,
        "outcomes": [
            {"outcome_id": KALSHI_JODAR_OUTCOME if i == 0 else KALSHI_BU_OUTCOME,
             "name": n, "external_id": f"{ticker}-{n[:3].upper()}"}
            for i, n in enumerate(names)
        ],
    }


def _prices():
    """Both books, at the values production was actually carrying."""
    observed = NOW - timedelta(minutes=20)
    return {
        # The Kalshi market for the pairing that is ON.
        KALSHI_JODAR_OUTCOME: {"probability": 0.895, "opening_probability": 0.880,
                               "observed_at": observed},
        KALSHI_BU_OUTCOME: {"probability": 0.105, "opening_probability": 0.120,
                            "observed_at": observed},
        # The register's pins, for the pairing NOBODY IS PLAYING. Deliberately
        # a wildly different split so that if it ever leaks onto the card the
        # assertion cannot pass by coincidence.
        REG_JODAR_OUTCOME: {"probability": 0.600, "opening_probability": 0.600,
                            "observed_at": observed},
        REG_KOKKINAKIS_OUTCOME: {"probability": 0.400, "opening_probability": 0.400,
                                 "observed_at": observed},
    }


def _links(now=NOW, competitions=None, candidates=None):
    """Run the real beat-side resolver — never a hand-written link.

    A hand-built fixture would let these tests keep passing while the resolver
    that has to produce it in production stopped resolving anything.
    """
    from app.utils.tournament_link_resolver import resolve_authority_links

    from app.tasks.tournament_matchup_linker import _authority_competitions

    return resolve_authority_links(
        competitions if competitions is not None
        else _authority_competitions(_listed()),
        candidates if candidates is not None else [_candidate()],
        now=now,
    )["links"]


def _slate(**kwargs):
    kwargs.setdefault("prices", _prices())
    kwargs.setdefault("now", NOW)
    kwargs.setdefault("order_of_play", _listed())
    return build_slate(_register(), **kwargs)


def _the_row(slate):
    rows = [r for r in slate["matches"] if r.get("pairing_source") == "authority"]
    assert len(rows) == 1, f"expected one authority row, got {slate['matches']}"
    return rows[0]


# ---------------------------------------------------------------------------
# G1 — THE SHIP. The sentence stops being false.
# ---------------------------------------------------------------------------

def test_the_authority_row_shows_the_price_of_the_match_that_is_on():
    """Jodar vs Bu renders 90/10 instead of "nobody is quoting this match".

    Through ``build_slate``, not the resolver alone: a pure-library guard stays
    green when the thing that renders stops printing the feature.
    """
    row = _the_row(_slate(authority_links=_links()))

    assert row["priced"] is True
    assert row["coherent"] is True
    assert row["price_state"] == "live"
    assert row["probability_is_live"] is True
    assert row["source_count"] == 1

    by_key = {s["entity_key"]: s for s in row["sides"]}
    assert round(by_key[JODAR]["probability"], 3) == 0.895
    assert round(by_key[BU]["probability"], 3) == 0.105
    assert by_key[JODAR]["display_name"] == "Rafael Jodar"
    assert by_key[BU]["display_name"] == "Bu Yunchaokete"
    assert row["favourite"] == JODAR


def test_the_row_is_still_the_authority_s_pairing_and_still_does_not_link():
    """Pricing it changes NOTHING else Q503 and Q505 decided.

    `matchup_key` stays the competition (two pairings must never share one id)
    and `event_id` stays null (the detail page still renders the register's
    fabricated pairing, so the card must remain unclickable).
    """
    row = _the_row(_slate(authority_links=_links()))
    assert row["matchup_key"] == f"espn:{COMP}"
    assert row["event_id"] is None
    assert row["pairing_source"] == "authority"
    assert {s["display_name"] for s in row["sides"]} == {
        "Rafael Jodar", "Bu Yunchaokete",
    }
    assert "Thanasi Kokkinakis" not in {s["display_name"] for s in row["sides"]}


def test_the_opening_price_and_the_move_come_through():
    """THE SCRIPT vs where it is now — the row prints the delta, not just the
    number, and normalises the opening pair on its OWN sum."""
    row = _the_row(_slate(authority_links=_links()))
    by_key = {s["entity_key"]: s for s in row["sides"]}
    assert round(by_key[JODAR]["opening_probability"], 3) == 0.880
    assert round(by_key[JODAR]["move"], 3) == 0.015
    assert round(by_key[BU]["move"], 3) == -0.015
    assert row["has_moved"] is True


def test_the_payload_counts_priced_authority_rows_separately():
    """`authority_pairings - authority_priced` is the live backlog: rows that
    still tell a reader nobody is quoting a match we may well hold."""
    unpriced = _slate()
    assert unpriced["authority_pairings"] == 1
    assert unpriced["authority_priced"] == 0

    priced = _slate(authority_links=_links())
    assert priced["authority_pairings"] == 1
    assert priced["authority_priced"] == 1


# ---------------------------------------------------------------------------
# G2 — Q503 IS UNTOUCHED. The withheld number still cannot reach this row.
# ---------------------------------------------------------------------------

def test_the_register_pinned_price_still_cannot_reach_the_authority_row():
    """═══ THE ONE THAT MATTERS ═══

    The register pins a live 60/40 for this fixture. That quote is for
    ``Jodar vs Kokkinakis``, a match nobody is playing, and Q503 withheld it for
    that reason. Now that the row CAN carry a number, the danger is no longer
    that the card is blank — it is that the blank gets filled from the nearest
    price to hand, which is the withheld one.

    ``prices`` contains it. No authority link is supplied. The row must stay
    exactly as Q505 wrote it.
    """
    row = _the_row(_slate())

    assert row["priced"] is False
    assert row["price_state"] == "unpriced"
    assert row["probability_is_live"] is False
    assert row["coherent"] is False
    assert row["favourite"] is None
    assert row["raw_sum"] is None
    assert row["source_count"] == 0
    for side in row["sides"]:
        assert side["probability"] is None
        assert side["opening_probability"] is None
        assert side["move"] is None
        assert side["raw_probability"] is None
        assert side["raw_opening_probability"] is None
        # `dark` means a reading we HAVE, gone stale. An unpriced side has no
        # reading to have gone stale, and collapsing the two would make "the
        # market stopped quoting this" and "no market is linked" one word.
        assert side["price_state"] == "unpriced"


def test_a_link_for_a_different_competition_cannot_price_this_row():
    """The lookup is keyed on the row's own competition id. A resolved link for
    the court next door must not leak onto it — that is the same class of
    error as the fabricated pairing, arriving through the new door."""
    other = {"espn:999999|kalshi": v for v in _links().values()}
    row = _the_row(_slate(authority_links=other))
    assert row["priced"] is False
    assert all(s["probability"] is None for s in row["sides"])


def test_one_priced_side_is_not_half_a_match():
    """A pair normalised against a missing partner is a fabricated split.

    Only Jodar's outcome has a price loaded. The honest row is the unpriced
    one, not Jodar at 100%.
    """
    prices = _prices()
    del prices[KALSHI_BU_OUTCOME]
    row = _the_row(_slate(prices=prices, authority_links=_links()))
    assert row["priced"] is False
    assert all(s["probability"] is None for s in row["sides"])


def test_an_incoherent_pair_shows_no_split():
    """Two stale readings summing to 1.5 are not one question (gotcha #23).
    The row keeps its price_state but refuses the number."""
    prices = _prices()
    prices[KALSHI_BU_OUTCOME] = {
        **prices[KALSHI_BU_OUTCOME], "probability": 0.605,
    }
    row = _the_row(_slate(prices=prices, authority_links=_links()))
    assert row["priced"] is True
    assert row["coherent"] is False
    assert row["probability_is_live"] is False
    assert all(s["probability"] is None for s in row["sides"])


# ---------------------------------------------------------------------------
# G3 — THE RESOLVER REFUSES RATHER THAN GUESSES.
# ---------------------------------------------------------------------------

def test_the_reversed_name_order_is_the_same_player():
    """ESPN's ``Bu Yunchaokete`` and Kalshi's ``Yunchaokete Bu``. A collapsed
    string makes them two people; the token SET makes word order irrelevant.
    This is the correspondence the whole ship rests on."""
    links = _links()
    sides = links[f"espn:{COMP}|kalshi"]["sides"]
    assert sides[JODAR]["outcome_id"] == KALSHI_JODAR_OUTCOME
    assert sides[BU]["outcome_id"] == KALSHI_BU_OUTCOME
    assert sides[BU]["source_label"] == "Yunchaokete Bu"


def test_an_earlier_meeting_of_the_same_two_players_is_refused():
    """Two players meet more than once a season, and Kalshi settled markets
    stay ``status='open'`` here (gotcha #33), so "still open" is not evidence a
    match has not been played. The date window is the only real bound."""
    from app.utils.tournament_link_resolver import (
        STALE_REMATCH,
        resolve_authority_links,
    )

    from app.tasks.tournament_matchup_linker import _authority_competitions

    june = _candidate(
        market_id=70001,
        ticker="KXATPCHALLENGERMATCH-26JUN01JODYUN",
        match_date=date(2026, 6, 1),
    )
    out = resolve_authority_links(
        _authority_competitions(_listed()), [june], now=NOW
    )
    assert out["links"] == {}
    assert out["counters"][STALE_REMATCH] == 1


def test_two_markets_naming_the_same_pair_refuse_rather_than_pick():
    from app.utils.tournament_link_resolver import (
        AMBIGUOUS_CANDIDATES,
        resolve_authority_links,
    )

    from app.tasks.tournament_matchup_linker import _authority_competitions

    out = resolve_authority_links(
        _authority_competitions(_listed()),
        [_candidate(), _candidate(market_id=70002, ticker="KXATPMATCH-26SEP02JODYUN")],
        now=NOW,
    )
    assert out["links"] == {}
    assert out["counters"][AMBIGUOUS_CANDIDATES] == 1


def test_a_market_naming_only_one_of_the_two_is_a_near_miss_not_an_absence():
    """A linkage defect and an ordinary absence need different people."""
    from app.utils.tournament_link_resolver import (
        AMBIGUOUS_SIDES,
        NO_CANDIDATE,
        resolve_authority_links,
    )

    from app.tasks.tournament_matchup_linker import _authority_competitions

    out = resolve_authority_links(
        _authority_competitions(_listed()),
        [_candidate(names=("Rafael Jodar", "Thanasi Kokkinakis"))],
        now=NOW,
    )
    assert out["links"] == {}
    assert out["counters"][AMBIGUOUS_SIDES] == 1
    assert out["counters"][NO_CANDIDATE] == 0


def test_no_market_at_all_is_reported_as_an_absence():
    from app.utils.tournament_link_resolver import (
        NO_CANDIDATE,
        resolve_authority_links,
    )

    from app.tasks.tournament_matchup_linker import _authority_competitions

    out = resolve_authority_links(
        _authority_competitions(_listed()), [], now=NOW
    )
    assert out["links"] == {}
    assert out["counters"][NO_CANDIDATE] == 1
    # "It ran" is not "it worked" (gotcha #53) — the zero-yield case is loud.
    assert out["counters"]["needy"] == 1
    assert out["counters"]["resolved"] == 0


def test_a_doubles_competition_names_no_athlete_and_is_never_resolved():
    """A doubles competition names a TEAM and no athlete; a qualifier slot
    names "TBD" with a non-positive id. ``determined`` is the same gate
    ``authority_match_row`` uses to decide it may draw the row at all."""
    from app.tasks.tournament_matchup_linker import _authority_competitions

    doubles = _listed(competitors=[
        {"espn_athlete_id": None, "name": None, "determined": False,
         "country": None, "flag_url": None, "order": 1},
        {"espn_athlete_id": None, "name": None, "determined": False,
         "country": None, "flag_url": None, "order": 2},
    ])
    assert _authority_competitions(doubles) == []

    half = _listed(competitors=[
        {"espn_athlete_id": 12657, "name": "Rafael Jodar", "determined": True,
         "country": "Spain", "flag_url": "esp.png", "order": 1},
        {"espn_athlete_id": None, "name": "TBD", "determined": False,
         "country": None, "flag_url": None, "order": 2},
    ])
    assert _authority_competitions(half) == []


# ---------------------------------------------------------------------------
# G4 — ONE RULE, TWO CALLERS.
# ---------------------------------------------------------------------------

def test_both_paths_bind_the_same_pair_to_the_same_outcomes():
    """The register path and the authority path differ only in WHO NAMED the
    two people. A second copy of the correspondence rule would be free to rot
    away from the first while both kept passing their own tests, so this pins
    that one pair, one candidate and one date resolve identically through both.
    """
    from app.utils.tournament_link_resolver import (
        resolve_authority_links,
        resolve_matchup_links,
    )

    from app.tasks.tournament_matchup_linker import _authority_competitions

    register = {
        "players": [
            {"entity_key": "rafael-jodar", "display_name": "Rafael Jodar"},
            {"entity_key": "bu-yunchaokete", "display_name": "Bu Yunchaokete"},
        ],
        "matchups": [{
            "matchup_key": "m1",
            "scheduled_date": START,
            "players": ["rafael-jodar", "bu-yunchaokete"],
            "sources": [{"source": "kalshi", "status": "missing"}],
        }],
    }
    via_register = resolve_matchup_links(
        register, [_candidate()], now=NOW
    )["links"]["m1|kalshi"]
    via_authority = resolve_authority_links(
        _authority_competitions(_listed()), [_candidate()], now=NOW
    )["links"][f"espn:{COMP}|kalshi"]

    assert via_register["market_id"] == via_authority["market_id"]
    assert (
        {s["outcome_id"] for s in via_register["sides"].values()}
        == {s["outcome_id"] for s in via_authority["sides"].values()}
    )
    # Jodar lands on Jodar's leg under both, so the bijection is the same one
    # and not merely the same SET of ids.
    assert via_register["sides"]["rafael-jodar"]["outcome_id"] == KALSHI_JODAR_OUTCOME
    assert via_authority["sides"][JODAR]["outcome_id"] == KALSHI_JODAR_OUTCOME


def test_an_authority_link_says_which_rule_minted_it():
    """An authority link prices a fixture whose register pairing was withheld
    as contradicted. A reader auditing one must be able to tell at a glance
    which of the two questions was asked."""
    from app.utils.tournament_link_resolver import (
        AUTHORITY_EVIDENCE_KIND,
        AUTHORITY_RULE,
        EVIDENCE_KIND,
    )

    block = _links()[f"espn:{COMP}|kalshi"]
    assert block["evidence"]["kind"] == AUTHORITY_EVIDENCE_KIND
    assert block["evidence"]["kind"] != EVIDENCE_KIND
    assert block["evidence"]["rule"] == AUTHORITY_RULE
    assert block["evidence"]["espn_competition_id"] == COMP
    assert block["market_external_id"] == "KXATPMATCH-26SEP01JODYUN"


# ---------------------------------------------------------------------------
# G5 — THE BEAT PUBLISHES IT.
# ---------------------------------------------------------------------------

async def test_the_task_publishes_authority_links_and_counts_them(monkeypatch):
    """The overlay the route reads has to actually contain this, and the two
    halves have to stay apart: ``apply_resolved_links`` may only ever replace a
    register block, and an authority link belongs to no register matchup."""
    from app.tasks import tournament_matchup_linker as linker

    written: dict[str, object] = {}

    async def _fake_write(slug, payload):
        written[slug] = payload
        return True

    async def _fake_candidates(session, series, *, now=None):
        return [_candidate()]

    async def _fake_order_of_play(slug):
        return _listed()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(linker, "load_register", lambda t, s: _register())
    monkeypatch.setattr(linker, "_load_candidates", _fake_candidates)
    monkeypatch.setattr(linker, "_read_order_of_play", _fake_order_of_play)
    monkeypatch.setattr(linker, "_write_links", _fake_write)
    monkeypatch.setattr(linker, "_now", lambda: NOW)
    monkeypatch.setattr("app.tasks.base.get_task_session", lambda: _Session())

    stats = await linker._link_tournament_matchups(
        watched=({"tournament": "us-open", "season": "2026",
                  "kalshi_series": ("KXATPMATCH",)},)
    )

    assert stats["authority_competitions"] == 1
    assert stats["authority_resolved"] == 1
    assert stats["authority_published"] == 1

    payload = written["us-open"]
    assert list(payload["authority_links"]) == [f"espn:{COMP}|kalshi"]
    # Kept out of `links`, which only ever means "a register block to fill".
    assert f"espn:{COMP}|kalshi" not in payload["links"]
    assert payload["authority_counters"]["resolved"] == 1


async def test_a_cold_order_of_play_cache_costs_only_the_numbers(monkeypatch):
    """The overlay is an optimisation over the committed truth and must never
    be a gate: no scoreboard in the cache means no authority links, which
    returns the card to the unpriced row — the honest state, not a stale one.
    """
    from app.tasks import tournament_matchup_linker as linker

    written: dict[str, object] = {}

    async def _fake_write(slug, payload):
        written[slug] = payload
        return True

    async def _fake_candidates(session, series, *, now=None):
        return [_candidate()]

    async def _cold(slug):
        return {}

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(linker, "load_register", lambda t, s: _register())
    monkeypatch.setattr(linker, "_load_candidates", _fake_candidates)
    monkeypatch.setattr(linker, "_read_order_of_play", _cold)
    monkeypatch.setattr(linker, "_write_links", _fake_write)
    monkeypatch.setattr(linker, "_now", lambda: NOW)
    monkeypatch.setattr("app.tasks.base.get_task_session", lambda: _Session())

    stats = await linker._link_tournament_matchups(
        watched=({"tournament": "us-open", "season": "2026",
                  "kalshi_series": ("KXATPMATCH",)},)
    )

    assert stats["authority_competitions"] == 0
    assert stats["authority_published"] == 0
    assert written["us-open"]["authority_links"] == {}
    # And the register half is unaffected by the authority half going dark.
    assert stats["written"] == 1
