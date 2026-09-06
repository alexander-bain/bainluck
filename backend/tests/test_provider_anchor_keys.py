"""#1946 Item 8 — the anchor key must never let two different games share one key.

`event_provider_anchors`'s unique key is `(source, source_id, id_kind)` and only
`id_kind='game'` may anchor an absorption. So a defect in this module does not
show up as a bad row; it shows up as **two different games merged into one**,
which is the exact outcome ruling 048 exists to prevent.

These tests are fixture-only by design. Item 8's *backfill* is gated on a sink
census that is measurement-lane work under ruling 134; the *key logic* is not,
and pinning it now is what makes the backfill a small change when the census
clears.

The corpus is built from the two specimens that are already paid for:
the NCAA men's/women's bare-token collision behind Alex's 2026-08-21 Kalshi
ruling, and the 21 conflicting-StatPal-id duplicate groups measured in queue
411 — one of which is the pair that printed two different scores on Alex's own
home screen.
"""

import pytest

from app.utils.provider_anchor_keys import (
    AGREE,
    ANCHOR_KIND_CONTAINER,
    ANCHOR_KIND_GAME,
    ANCHOR_KIND_MARKET,
    CONFLICT,
    INCOMPARABLE,
    SOURCE_KALSHI,
    SOURCE_STATPAL,
    STATPAL_NS_LONG,
    STATPAL_NS_SHORT,
    compare_statpal_ids,
    espn_anchor_key,
    kalshi_anchor_key,
    odds_api_anchor_key,
    polymarket_anchor_key,
    statpal_anchor_key,
    statpal_namespace,
)

# The real pair from Alex's 2026-08-25 screenshot: one game, two rows, one
# StatPal id from each namespace. Queue 411 measured 21 groups of this shape.
SPECIMEN_SHORT = "354812"
SPECIMEN_LONG = "1329147155"

#: The sport those two rows are in. Both specimens are MLB — that is the point
#: of the pair, two StatPal endpoints numbering one league's fixtures
#: differently — so the sport qualifier D55 introduced does NOT separate them,
#: and `compare_statpal_ids` reading their two shapes is still the only thing
#: that can. The two functions answer different questions; see the module
#: docstring of `provider_anchor_keys`.
SPECIMEN_SPORT = "baseball_mlb"


# ---------------------------------------------------------------------------
# The namespace, and the three-valued comparison it makes possible
# ---------------------------------------------------------------------------


def test_the_two_measured_statpal_namespaces_are_distinguished():
    assert statpal_namespace(SPECIMEN_SHORT) == STATPAL_NS_SHORT
    assert statpal_namespace(SPECIMEN_LONG) == STATPAL_NS_LONG
    assert statpal_namespace("  354812  ") == STATPAL_NS_SHORT


def test_an_unrecognised_shape_is_none_not_a_guess():
    """A third namespace must arrive as `None`, not be forced into one of two.

    `None` costs a missed anchor. A guess costs a merged pair of games.
    """
    for junk in (None, "", "   ", "abc", "12345", "12345678901", "354-812", "35481a"):
        assert statpal_namespace(junk) is None


def test_cross_namespace_ids_are_incomparable_not_conflicting():
    """THE finding. Today's `a = b` returns false here and every caller reads
    false as 'different games'. They are the same game, written twice."""
    assert compare_statpal_ids(SPECIMEN_SHORT, SPECIMEN_LONG) == INCOMPARABLE
    assert compare_statpal_ids(SPECIMEN_LONG, SPECIMEN_SHORT) == INCOMPARABLE


def test_same_namespace_still_answers_definitely_in_both_directions():
    """Without this, 'INCOMPARABLE' could just mean the comparison went blind."""
    assert compare_statpal_ids(SPECIMEN_SHORT, SPECIMEN_SHORT) == AGREE
    assert compare_statpal_ids(SPECIMEN_SHORT, "355999") == CONFLICT
    assert compare_statpal_ids(SPECIMEN_LONG, SPECIMEN_LONG) == AGREE
    assert compare_statpal_ids(SPECIMEN_LONG, "1329100000") == CONFLICT


def test_a_missing_id_is_never_a_conflict():
    """Absence of an id has never been evidence of anything. Reading
    `NULL != NULL` as disagreement is how a census miscounts its own successes."""
    for a, b in (
        (None, None),
        (None, SPECIMEN_SHORT),
        (SPECIMEN_SHORT, None),
        ("", SPECIMEN_SHORT),
    ):
        assert compare_statpal_ids(a, b) == INCOMPARABLE


def test_incomparable_never_authorizes_anything():
    """Ruling 048 is untouched: this module widens what we can SAY, never what
    we may DO. `INCOMPARABLE` is not a merge licence and not a split licence."""
    verdict = compare_statpal_ids(SPECIMEN_SHORT, SPECIMEN_LONG)
    assert verdict not in (AGREE, CONFLICT)


# ---------------------------------------------------------------------------
# StatPal anchor rows
# ---------------------------------------------------------------------------


def test_a_statpal_anchor_carries_its_namespace_in_the_source_id():
    """The unique key is `(source, source_id, id_kind)` with a BARE source_id.
    An unqualified `354812` from two id spaces is one key for two games.

    The qualifier is the SPORT since D55 (#2879) — see
    `test_statpal_anchor_sport_namespace_2879.py` for why counting digits could
    not survive a second sport. Here it is only the property that matters: a
    StatPal `source_id` is never bare.
    """
    short = statpal_anchor_key(SPECIMEN_SHORT, sport_key=SPECIMEN_SPORT)
    long = statpal_anchor_key(SPECIMEN_LONG, sport_key=SPECIMEN_SPORT)
    assert short.source == long.source == SOURCE_STATPAL
    assert short.source_id == f"{SPECIMEN_SPORT}:{SPECIMEN_SHORT}"
    assert long.source_id == f"{SPECIMEN_SPORT}:{SPECIMEN_LONG}"
    assert short.source_id != long.source_id
    assert short.id_kind == ANCHOR_KIND_GAME


def test_a_hypothetical_cross_sport_value_collision_cannot_share_a_key():
    """The property, stated directly rather than via the specimens.

    Two sports emitting the same literal fixture digits for two different games
    is the collision that actually threatens this table — NFL `contestid` and
    MLB `id` are both 6-digit — so construct it and assert the keys stay apart.
    """
    keys = {
        statpal_anchor_key(SPECIMEN_SHORT, sport_key=s).source_id
        for s in ("baseball_mlb", "americanfootball_nfl")
    }
    assert len(keys) == 2
    assert all(k.count(":") == 1 for k in keys)
    assert {k.split(":", 1)[0] for k in keys} == {
        "baseball_mlb",
        "americanfootball_nfl",
    }


def test_an_unusable_statpal_id_writes_no_anchor_at_all():
    """Refusing to write is the correct failure. A `game` anchor on an
    unqualified id is the one outcome that can merge two real games."""
    for junk in (None, "", "   "):
        assert statpal_anchor_key(junk, sport_key=SPECIMEN_SPORT) is None
    # And an id we cannot attribute to a sport, whatever its shape. Since D55
    # this is every unqualified call, not only the digit shapes the old rule
    # failed to recognise.
    for token in (SPECIMEN_SHORT, SPECIMEN_LONG, "abc", "12345"):
        assert statpal_anchor_key(token) is None


# ---------------------------------------------------------------------------
# Kalshi — Alex's 2026-08-21 ruling, implemented rather than paraphrased
# ---------------------------------------------------------------------------


def test_a_kalshi_game_anchor_is_sport_key_colon_game_id_and_never_bare():
    key = kalshi_anchor_key("KXMLBGAME-26APR291840COLCIN")
    assert key.id_kind == ANCHOR_KIND_GAME
    assert key.source == SOURCE_KALSHI
    assert ":" in key.source_id
    sport_key, game_id = key.source_id.split(":", 1)
    assert game_id == "26APR291840COLCIN"
    assert sport_key and sport_key != game_id
    assert key.source_id != game_id, "the BARE token must never be the anchor"


def test_the_ncaa_specimen_that_the_ruling_was_written_for():
    """Men's and women's NCAA basketball share a bare game-id token. The
    sport_key qualifier is the entire reason they do not collide."""
    mens = kalshi_anchor_key("KXNCAAMBGAME-26FEB22IOWAWIS")
    womens = kalshi_anchor_key("KXNCAAWBGAME-26FEB22IOWAWIS")

    # Both ARE game anchors — asserted, not assumed, because a test that only
    # checks "the keys differ" passes trivially if the rule silently downgraded
    # both to `market` and stopped anchoring NCAA basketball at all.
    assert mens.id_kind == ANCHOR_KIND_GAME
    assert womens.id_kind == ANCHOR_KIND_GAME

    # The bare token is IDENTICAL. That is the collision, stated as data.
    assert mens.source_id.split(":", 1)[1] == womens.source_id.split(":", 1)[1]
    # The qualifier is the only thing keeping them apart.
    assert mens.source_id == "basketball_ncaab:26FEB22IOWAWIS"
    assert womens.source_id == "basketball_wncaab:26FEB22IOWAWIS"
    assert mens.source_id != womens.source_id, (
        "the men's and women's fixtures collapsed onto one anchor key — this "
        "is the collision Alex's 2026-08-21 ruling forbids"
    )


def test_tennis_stays_a_market_anchor():
    """Ruling, verbatim: tennis must be `id_kind='market'`. A market anchor
    asserts nothing about same-game, so it cannot absorb."""
    for ticker in ("KXATPMATCH-26MAR01ALCSIN", "KXWTAMATCH-26MAR01SWIGAU"):
        key = kalshi_anchor_key(ticker)
        assert key.id_kind == ANCHOR_KIND_MARKET, (
            f"{ticker} produced an anchor of kind {key.id_kind}; the ruling "
            "requires tennis to stay `market` so it can never absorb"
        )
        assert key.may_anchor_absorption is False
        # Recorded verbatim, not dropped — a market anchor is still how the
        # correspondence gets discovered later.
        assert key.source_id == ticker


def test_the_tennis_exclusion_is_the_reason_not_a_parser_accident():
    """Tennis must be excluded BY THE RULE, not because the parser happened to
    fail on it. Otherwise a parser improvement silently promotes tennis to
    `game` and nothing in the suite notices."""
    from app.utils.sport_keys import get_sport_key_from_ticker

    assert get_sport_key_from_ticker("KXATPMATCH-26MAR01ALCSIN") == "tennis_atp"
    assert get_sport_key_from_ticker("KXWTAMATCH-26MAR01SWIGAU") == "tennis_wta"


# ---------------------------------------------------------------------------
# CERT-409 [P1] — a futures series must never become a `game` anchor
# ---------------------------------------------------------------------------
#
# The defect: the helper asked `kalshi_game_id()` (a broad date-token
# extractor) and `get_sport_key_from_ticker()` (which resolves game AND futures
# prefixes on purpose), and inferred "game" from the pair. Neither question is
# "is this a game". A best-of-seven playoff series carries a date token and a
# sport key, so it answered yes — and a series that claims a single fixture's
# identity is an absorption, which is precisely what ruling 048 forbids.
#
# THE THREE TICKERS BELOW ARE A PERMANENT RED SET. They are named in the
# CERT-409 verdict; they do not get deleted when this test goes green.

SERIES_RED_SET = (
    "KXMLBSERIES-26OCT15NYYATL",
    "KXNBASERIES-26MAY10BOSPHI",
    "KXNHLSERIES-26MAY10FLORNG",
)


@pytest.mark.parametrize("ticker", SERIES_RED_SET)
def test_a_playoff_series_is_never_a_game_anchor(ticker):
    """CERT-409 [P1], stated as the three tickers the cert named."""
    key = kalshi_anchor_key(ticker)
    assert key.id_kind == ANCHOR_KIND_MARKET, (
        f"{ticker} produced an anchor of kind {key.id_kind}. A best-of-seven "
        "series is not a fixture; anchoring it as `game` lets the series "
        "absorb one of its own games (ruling 048, gotcha #32)."
    )
    assert key.may_anchor_absorption is False
    assert key.source_id == ticker


@pytest.mark.parametrize("ticker", SERIES_RED_SET)
def test_the_series_refusal_is_the_rule_not_a_parser_accident(ticker):
    """The same discipline the tennis exclusion already gets.

    Both inputs the old code trusted still say "yes" for these tickers — a date
    token IS extractable and a sport key IS resolvable. If the refusal were an
    accident of parsing, a parser improvement would silently re-promote them.
    It is not: the refusal comes from a positive game-level classification.
    """
    from app.utils.prediction_market_matching import kalshi_game_id
    from app.utils.sport_keys import get_sport_key_from_ticker, is_kalshi_game_level_ticker

    assert kalshi_game_id(ticker), "premise: a date token is still extractable"
    assert get_sport_key_from_ticker(ticker), "premise: a sport key still resolves"
    assert is_kalshi_game_level_ticker(ticker) is False, (
        "premise: the canonical game-ticker predicate already refuses this — "
        "the anchor helper's bug was never asking it"
    )


def test_no_futures_prefix_can_produce_a_game_anchor():
    """The structural negative control, over the whole futures map.

    The three named tickers are the specimens; this is the class. Every futures
    prefix in `sport_keys.py` gets a date-shaped token appended — the exact
    shape that fooled the old code — and none of them may come back `game`.

    This also covers a case the cert counted but did not name: 8 futures
    prefixes are LONGER than a game prefix they happen to start with
    (`kxmlbhrderby` extends the game prefix `kxmlbhr`), so the bare
    `startswith` predicate this repo used to carry would still have promoted
    them. Q440 (#2231) deleted that predicate; this control outlives it.
    """
    from app.utils.sport_keys import KALSHI_FUTURES_TICKER_TO_SPORT_KEY

    promoted = [
        prefix
        for prefix in KALSHI_FUTURES_TICKER_TO_SPORT_KEY
        if kalshi_anchor_key(f"{prefix.upper()}-26MAY10BOSPHI").id_kind
        == ANCHOR_KIND_GAME
    ]
    assert promoted == [], (
        f"{len(promoted)} futures prefixes produced `game` anchors: "
        f"{sorted(promoted)[:10]}"
    )


def test_every_game_prefix_still_anchors_as_a_game():
    """The other direction, asserted so the fix cannot be a blanket refusal.

    A rule that refused everything would pass the test above and silently stop
    anchoring all 229 game prefixes — the anchor channel would go quiet and
    look correct. Tennis is the one deliberate exclusion.
    """
    from app.utils.provider_anchor_keys import _KALSHI_TENNIS_SPORT_KEYS
    from app.utils.sport_keys import (
        KALSHI_GAME_TICKER_PREFIXES,
        get_sport_key_from_ticker,
    )

    refused = []
    for prefix in KALSHI_GAME_TICKER_PREFIXES:
        ticker = f"{prefix.upper()}-26MAY10BOSPHI"
        if get_sport_key_from_ticker(ticker) in _KALSHI_TENNIS_SPORT_KEYS:
            continue  # the ruling's deliberate exclusion
        if kalshi_anchor_key(ticker).id_kind != ANCHOR_KIND_GAME:
            refused.append(prefix)
    assert refused == [], (
        f"{len(refused)} real game prefixes lost their `game` anchor: "
        f"{sorted(refused)[:10]}"
    )


def test_an_unparseable_ticker_is_recorded_but_cannot_absorb():
    """Recording it is how the anchor is discovered later. `market` is what
    stops the recording from becoming an assertion."""
    key = kalshi_anchor_key("SOMETHING-WITH-NO-GAME-TOKEN")
    assert key is not None
    assert key.id_kind == ANCHOR_KIND_MARKET
    assert key.may_anchor_absorption is False


def test_no_ticker_writes_nothing():
    assert kalshi_anchor_key(None) is None
    assert kalshi_anchor_key("") is None
    assert kalshi_anchor_key("   ") is None


# ---------------------------------------------------------------------------
# Polymarket, ESPN, Odds API
# ---------------------------------------------------------------------------


def test_polymarket_is_never_a_game_anchor():
    """A Polymarket 'event' groups sub-markets that may span several real
    fixtures — that is what `group_id` exists for. Anchoring a game on one
    would absorb ACROSS fixtures."""
    cond = polymarket_anchor_key(condition_id="0xabc123")
    evt = polymarket_anchor_key(event_id="90210")
    assert cond.id_kind == ANCHOR_KIND_MARKET
    assert evt.id_kind == ANCHOR_KIND_CONTAINER
    assert cond.may_anchor_absorption is False
    assert evt.may_anchor_absorption is False
    assert polymarket_anchor_key() is None


def test_the_condition_id_wins_when_both_are_supplied():
    key = polymarket_anchor_key(condition_id="0xabc123", event_id="90210")
    assert key.source_id == "0xabc123"
    assert key.id_kind == ANCHOR_KIND_MARKET


def test_espn_and_odds_api_ids_are_game_anchors():
    assert espn_anchor_key("401816587").id_kind == ANCHOR_KIND_GAME
    assert odds_api_anchor_key("abc-def-123").id_kind == ANCHOR_KIND_GAME
    for f in (espn_anchor_key, odds_api_anchor_key):
        assert f(None) is None
        assert f("") is None
        assert f("   ") is None


# ---------------------------------------------------------------------------
# The invariant that outranks every case above
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        statpal_anchor_key(SPECIMEN_SHORT, sport_key=SPECIMEN_SPORT),
        statpal_anchor_key(SPECIMEN_LONG, sport_key=SPECIMEN_SPORT),
        kalshi_anchor_key("KXMLBGAME-26APR291840COLCIN"),
        kalshi_anchor_key("SOMETHING-WITH-NO-GAME-TOKEN"),
        polymarket_anchor_key(condition_id="0xabc"),
        polymarket_anchor_key(event_id="90210"),
        espn_anchor_key("401816587"),
        odds_api_anchor_key("abc-def-123"),
    ],
)
def test_every_emitted_key_is_wellformed_and_fits_the_column(key):
    assert key is not None
    assert key.id_kind in (
        ANCHOR_KIND_GAME,
        ANCHOR_KIND_MARKET,
        ANCHOR_KIND_CONTAINER,
    )
    assert key.source and len(key.source) <= 32
    assert key.source_id and len(key.source_id) <= 200
    assert key.source_id == key.source_id.strip()
    assert key.may_anchor_absorption == (key.id_kind == ANCHOR_KIND_GAME)


def test_an_anchor_key_cannot_be_mutated_after_its_kind_was_checked():
    """`frozen=True` is the point: a key whose `id_kind` can change after the
    absorption check is a key whose check means nothing."""
    key = statpal_anchor_key(SPECIMEN_SHORT, sport_key=SPECIMEN_SPORT)
    assert key.may_anchor_absorption is True
    with pytest.raises(Exception):
        key.id_kind = ANCHOR_KIND_MARKET  # type: ignore[misc]
