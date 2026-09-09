"""lane1b/089 (#4120): three of the five "sources" on an event page were not sources.

Read off production on 2026-09-08 at 19:45 PT, `GET /api/events/15296356`
(Getafe v Celta Vigo), `win_probability_sources`:

    kalshi                   : display_name 'Kalshi'                   value 0.01
    betting                  : display_name 'Betting Odds'             value 0.2346
    statpal_injuries         : display_name 'statpal_injuries'         value [{"team": "Getafe",
                                 "type": "Injury", "player": "A. Abqar", "status": "Out"}, ...]
    betting_book_count       : display_name 'betting_book_count'       value 5.0
    statpal_injuries_updated : display_name 'statpal_injuries_updated' value "2026-09-07T18:20:01.048986+00:00"

Two of the five are real. One of the other three ships an entire array of injury
dictionaries as a source's probability.

`Event.win_probability_sources` is a JSONB grab-bag: writer metadata lives in it
alongside the sources because the column was convenient. The AGGREGATOR has always
known the difference — `_tier1_readings` skips any key outside `SOURCE_WEIGHTS`,
and `test_betting_consensus_book_count_1841` pins the count as metadata in so many
words. The three READERS did not.

Census over the live column, 2026-09-08: `betting_book_count` on **1,348** events,
`statpal_injuries` on **89**, `statpal_injuries_updated` on **89**.

## THE THIRD READER IS ARITHMETIC, NOT COSMETIC, AND IT IS THE WORST OF THE THREE

`routes/feed.py::_numeric_source_probs` walked `.values()` and took anything
numeric. `cross_source_agreement` is `max - min <= 0.10`. A reading of 13.0 in a
list of probabilities makes the spread at least 12.9, so the verdict is **False
every single time** — and it feeds `compute_confidence_score`, which sets the
confidence tier on Discover cards. Measured by replaying the shipped functions
over the live 892-event population:

    sources_agree TRUE : 28 before -> 153 after
    verdicts changed   : 301
    became None        : 173   (the count was one of only two "readings", so
                                agreement is genuinely unmeasurable — the honest
                                answer, and the function's stated contract)

So a count of sportsbooks was quietly applying a "sources disagree" penalty to
every event that had a sportsbook line.

## WHY AN ALLOWLIST AND NOT A DENYLIST OF THE THREE KEYS

A denylist of known-unknowns hands the claim to the first new metadata key anyone
adds, and this column has gained metadata keys three times already. `WIN_PROB_SOURCES`
is a positive statement that something is a source a reader may be shown, and it
carries the D91 display name so the wire needs no client-side mapping.

An allowlist has exactly one failure mode — dropping something real — and
`test_every_weighted_source_has_a_display_entry` closes it. That test found the
fourth leak while being written: **`final_result` is a real source** (weight 5.0,
the only one exempt from decay and the share cap) with no display entry, so it was
printing its own key as its name on 311 events. It is added to the registry in the
same commit rather than special-cased in the filter.
"""

from datetime import datetime, timezone

from app.config.win_prob_sources import WIN_PROB_SOURCES, is_displayable_source
from app.models import Event, Sport
from app.routes.events import _format_event
from app.routes.feed import _numeric_source_probs
from app.utils.aggregation import SOURCE_WEIGHTS
from app.utils.feed_market_quality import cross_source_agreement

#: The exact column read off production event 15296356 on 2026-09-08. Verbatim,
#: including the two real values, so this fixture is a specimen and not a
#: convenient re-statement of the bug.
PRODUCTION_COLUMN = {
    "kalshi": {"value": 0.01, "updated_at": "2026-09-07T16:52:03.117412+00:00"},
    "betting": {"value": 0.2346, "updated_at": "2026-09-07T16:58:00.221871+00:00"},
    "statpal_injuries": [
        {"team": "Getafe", "type": "Injury", "detail": None,
         "player": "A. Abqar", "status": "Out"},
        {"team": "Celta Vigo", "type": "Injury", "detail": None,
         "player": "C. Dominguez", "status": "Out"},
    ],
    "betting_book_count": 5,
    "statpal_injuries_updated": "2026-09-07T18:20:01.048986+00:00",
}

#: What a reader is entitled to see on that event, and nothing else.
REAL_SOURCES_ON_THE_SPECIMEN = {"kalshi", "betting"}

#: The three that are not sources. Named so a failure says WHICH one came back.
METADATA_KEYS = ("betting_book_count", "statpal_injuries", "statpal_injuries_updated")


def _event(sources=None, status="completed", **kwargs):
    sport = Sport(id=1, key="soccer_spain_la_liga", name="La Liga")
    return Event(
        id=15296356,
        sport_id=1,
        sport=sport,
        home_team_name="Getafe",
        away_team_name="Celta Vigo",
        commence_time=datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc),
        status=status,
        home_score=None,
        away_score=None,
        win_probability_sources=(
            PRODUCTION_COLUMN if sources is None else sources
        ),
        **kwargs,
    )


# ── the ship: what a reader is shown ────────────────────────────────────────


def test_the_specimen_serves_only_its_two_real_sources():
    """The defect, stated positively. This is `GET /api/events/15296356`."""
    served = _format_event(_event())["win_probability_sources"]
    leaked = sorted(set(served) - REAL_SOURCES_ON_THE_SPECIMEN)
    assert not leaked, (
        f"these are not sources and a reader was shown them as sources: {leaked}"
    )
    assert set(served) == REAL_SOURCES_ON_THE_SPECIMEN


def test_the_injuries_array_never_ships_as_a_probability():
    """`parse_source_entry` returns None for an array, and the serialiser's
    `value` then fell back to the RAW entry — so the whole injuries list shipped
    as a source's probability. Asserted on the SHAPE of every served value, not
    on the key, so a future array key is caught too."""
    served = _format_event(_event())["win_probability_sources"]
    for key, entry in served.items():
        assert isinstance(entry["value"], (int, float)), (
            f"{key} serves a {type(entry['value']).__name__} where a probability belongs: "
            f"{entry['value']!r}"
        )


def test_no_source_is_labelled_with_its_own_snake_case_key():
    """`display_name` falls back to `src_key`, which is how a reader came to see
    the words `betting_book_count` and `statpal_injuries` on a page. Asserted
    over the registry rather than over one payload, so it also fails for a source
    someone adds with a missing or copy-pasted name."""
    for key, meta in WIN_PROB_SOURCES.items():
        name = meta.get("display_name")
        assert name, f"{key} has no display_name, so the wire would print {key!r}"
        assert name != key, f"{key} is labelled with its own key"


def test_final_result_is_served_by_name_not_by_key():
    """The fourth leak, found by the subset guard below rather than by looking.
    A settled game's graded outcome carried no display entry on 311 events."""
    served = _format_event(
        _event(sources={"final_result": {"value": 1.0,
                                         "updated_at": "2026-09-07T19:00:00+00:00"}})
    )["win_probability_sources"]
    assert set(served) == {"final_result"}
    assert served["final_result"]["display_name"] == "Final Result"


# ── the iOS-typed map, which is the same defect one layer down ──────────────


def test_the_espn_map_drops_the_count_it_could_never_have_caught():
    """`espn.probability_sources` filtered on `_num is not None`, written to keep
    the ARRAYS out. A count is numeric, so it sailed through into a map iOS types
    as `[String: Double]` of probabilities — a count decoding cleanly as a
    probability is worse than a decode failure, because nothing complains."""
    espn = _format_event(_event()).get("espn") or {}
    served = espn.get("probability_sources") or {}
    assert set(served) == REAL_SOURCES_ON_THE_SPECIMEN
    assert served == {"kalshi": 0.01, "betting": 0.2346}


# ── the arithmetic one ──────────────────────────────────────────────────────


def test_the_agreement_signal_stops_reading_a_count_as_a_probability():
    """Two sources 23.5 points apart do not agree; two sources and a count of 5
    are not 500 points apart. The second reading is what shipped."""
    probs = _numeric_source_probs(PRODUCTION_COLUMN)
    assert sorted(probs) == [0.01, 0.2346]
    assert 5.0 not in probs, "the count is still being read as a probability"


def test_the_count_is_what_forced_every_verdict_to_disagree():
    """States the MECHANISM rather than re-implementing the old loop: any count
    admitted alongside real probabilities pins the spread above the threshold, so
    the verdict can only ever be False. Two arms of the shipped comparator."""
    probs = _numeric_source_probs(
        {"kalshi": {"value": 0.30}, "betting": {"value": 0.34},
         "betting_book_count": 13}
    )
    assert cross_source_agreement(probs) is True
    assert cross_source_agreement(list(probs) + [13.0]) is False


def test_agreement_is_none_rather_than_false_when_only_one_real_source_remains():
    """173 of the 892 live events land here. `None` means unmeasurable and the
    confidence signal drops it; a False manufactured from one source plus a count
    is a verdict the data does not support."""
    probs = _numeric_source_probs({"betting": {"value": 0.34}, "betting_book_count": 9})
    assert probs == [0.34]
    assert cross_source_agreement(probs) is None


# ── what makes an allowlist safe: it cannot drop a real source ──────────────


def test_every_weighted_source_has_a_display_entry():
    """THE GUARD THAT LETS THE OTHERS BE AN ALLOWLIST.

    An allowlist keyed on the display registry has exactly one failure mode:
    dropping something real. So every source the aggregator gives WEIGHT to must
    be in the display registry. Add a source to `SOURCE_WEIGHTS` without a
    display entry and this fails in CI rather than in production, where it would
    show as a source silently missing from the page — or, before this commit, as
    a source labelled with its own key.

    This is the test that found `final_result`.
    """
    missing = sorted(set(SOURCE_WEIGHTS) - set(WIN_PROB_SOURCES))
    assert not missing, (
        f"weighted but not displayable, so the page will drop them: {missing}"
    )


def test_a_real_source_survives_the_filter():
    """The control, and it is the arm that would catch an over-eager fix. Every
    weighted source at once, all served."""
    column = {
        key: {"value": 0.5, "updated_at": "2026-09-08T20:00:00+00:00"}
        for key in SOURCE_WEIGHTS
    }
    served = _format_event(_event(sources=column, status="scheduled"))[
        "win_probability_sources"
    ]
    assert set(served) == set(SOURCE_WEIGHTS)


# ── the predicate itself ────────────────────────────────────────────────────


def test_the_metadata_keys_are_refused_by_name():
    for key in METADATA_KEYS:
        assert is_displayable_source(key) is False


def test_the_predicate_survives_a_key_that_is_not_a_string():
    """JSONB keys are strings today; the predicate is a guard, not an assumption."""
    assert is_displayable_source(None) is False
    assert is_displayable_source(13) is False


def test_our_own_blend_is_displayable_but_never_counted_as_an_opinion():
    """SERVING and COUNTING are different questions, allowlisted separately.

    `bainluck_aggregate` is in the display registry (it is the blend line the
    chart draws and it carries a D91 name) and is deliberately NOT in
    `SOURCE_WEIGHTS`. Counting it in the agreement signal would ask whether our
    own output agrees with its own inputs. The frontend mirror
    (`PROBABILITY_SOURCE_KEYS`, `lib/confidence.ts` #3914) pins `SOURCE_WEIGHTS`
    for the same reason, and its test fails if the two sets part — so the feed
    path must allowlist on `SOURCE_WEIGHTS`, not on the display registry.
    """
    assert "bainluck_aggregate" in WIN_PROB_SOURCES
    assert "bainluck_aggregate" not in SOURCE_WEIGHTS
    assert _numeric_source_probs(
        {"betting": {"value": 0.4}, "kalshi": {"value": 0.42},
         "bainluck_aggregate": {"value": 0.41}}
    ) == [0.4, 0.42]
