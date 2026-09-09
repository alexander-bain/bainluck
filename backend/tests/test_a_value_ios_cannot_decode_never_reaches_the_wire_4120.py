"""lane1b/089 (#4120): the iOS event page could not decode 89 events, and a count
of sportsbooks was forcing "sources disagree" on every Discover card.

Two defects in three readers of `Event.win_probability_sources`, both traced from
Fable's 5:22pm note carrying Alex's sports-journey audit ("a count renders as a
source … `statpal_injuries` and other snake_case keys leak as source names").
Measuring it moved both the diagnosis and the fix off the filing, twice, and both
corrections are the point of this module.

## THE COLUMN

`Event.win_probability_sources` is a JSONB grab-bag. Alongside the sources it
carries writer metadata that shares the column because the column was convenient.
Census over the live column, 2026-09-08:

    betting_book_count        1,348 events   number
    statpal_injuries             89 events   ARRAY of injury dicts
    statpal_injuries_updated     89 events   ISO STRING
    final_result                311 events   number (a REAL source, weight 5.0)

## CORRECTION 1 — NO CLIENT WAS EVER SHOWN THESE AS SOURCES, AND ONE DEPENDS ON A COUNT

The filing says the keys "render as source names". They do not, on either client.
Web allowlists them out (`PROBABILITY_SOURCE_KEYS`, `lib/confidence.ts` #3914) and
iOS allowlists them out too (`WinProbSourceCatalog.realSourceKeys`) — the shipped
web page for the specimen reads "Bain Luck · 2 sources".

More than that: **iOS reads `betting_book_count` on purpose**, folding it into the
sportsbook row's label as "Sportsbooks (14)". So the obvious fix — filter the wire
down to the display registry — would have silently taken that count away from the
app. It is not shipped. **The gate is the value's SHAPE, not its key.**

## CORRECTION 2 — THE ARRAY IS NOT COSMETIC ON iOS, IT IS FATAL

The serialiser's `value` fell back to the RAW entry whenever `parse_source_entry`
returned None, which is exactly what the #1829 comment three lines above it
forbids. So `statpal_injuries` shipped an array where a probability belongs.

`WinProbValue` accepts Double or String and THROWS otherwise; `decodeIfPresent`
only swallows an ABSENT key, so a present-but-wrong-type value propagates out
through `[String: WinProbSource]` and fails the whole `EventDetail`. Reproduced
against the shipped model definitions (`swift`, 2026-09-08):

    AS SERVED TODAY : THE WHOLE EventDetail FAILED TO DECODE —
                      typeMismatch at winProbabilitySources.statpal_injuries.value
    AFTER THE FIX   : DECODED — 3 entries

**The iOS event page could not render those 89 events at all.** CI compiles no
Swift, so that proof lives in the cert body and the reproduction script; what this
module can guard is the wire that feeds it, which it does by asserting the SHAPE
of every served value.

## THE ARITHMETIC ONE, AND IT IS THE ONE NO CLIENT CAN COMPENSATE FOR

`routes/feed.py::_numeric_source_probs` walked `.values()` and took anything
numeric. `cross_source_agreement` is `max - min <= 0.10`, so a reading of 13.0
pins the spread above 12.9 and the verdict is **False every single time**. It
feeds `compute_confidence_score`, and it is computed on the SERVER — the clients'
own allowlists never see it. Replaying the shipped functions over the live
892-event population:

    sources_agree TRUE : 28 before -> 153 after
    verdicts changed   : 301
    became None        : 173   (the count was one of only two "readings", so
                                agreement is genuinely unmeasurable — the honest
                                answer, and the function's stated contract)

So a count of sportsbooks was applying a "sources disagree" penalty to the
Discover card of essentially every event with a sportsbook line.

## AND A FOURTH LEAK, FOUND BY THE REGISTRY GUARD RATHER THAN BY LOOKING

`final_result` is a real source — weight 5.0, the only one exempt from decay and
the share cap — with no entry in `WIN_PROB_SOURCES`, so the wire labelled it with
its own key on 311 events. Both clients allowlist the KEY, so they render it; the
web renders the served `display_name`. Given its entry, it now reads
"Final Result".
"""

from datetime import datetime, timezone

from app.config.win_prob_sources import WIN_PROB_SOURCES
from app.models import Event, Sport
from app.routes.events import _format_event
from app.routes.feed import _numeric_source_probs
from app.utils.aggregation import SOURCE_WEIGHTS
from app.utils.feed_market_quality import cross_source_agreement

#: The exact column read off production event 15296356 on 2026-09-08 19:45 PT.
#: Verbatim, so this is a specimen and not a convenient re-statement of the bug.
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

#: The two entries that break the iOS decoder — one array, one bare string.
UNDECODABLE_KEYS = ("statpal_injuries", "statpal_injuries_updated")


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
        win_probability_sources=(PRODUCTION_COLUMN if sources is None else sources),
        **kwargs,
    )


# ── the ship: the wire stops carrying a value iOS cannot decode ─────────────


def test_every_served_value_is_a_number():
    """THE GUARD FOR THE iOS DECODE FAILURE, asserted on SHAPE so it also covers
    the next non-probability key someone puts in this column. A dict, a list or a
    string here is a `typeMismatch` that fails the whole `EventDetail`."""
    served = _format_event(_event())["win_probability_sources"]
    for key, entry in served.items():
        assert isinstance(entry["value"], (int, float)) and not isinstance(
            entry["value"], bool
        ), (
            f"{key} serves a {type(entry['value']).__name__} where a probability "
            f"belongs; iOS throws on this and loses the whole event: {entry['value']!r}"
        )


def test_the_two_undecodable_entries_are_gone_and_named():
    served = _format_event(_event())["win_probability_sources"]
    for key in UNDECODABLE_KEYS:
        assert key not in served, f"{key} is still on the wire and iOS cannot decode it"


def test_the_count_stays_on_the_wire_because_the_app_reads_it():
    """THE CONTROL, AND IT IS THE ARM AN OBVIOUS FIX WOULD HAVE BROKEN.

    `betting_book_count` is not a source, and the tempting fix is to filter the
    wire down to the display registry. iOS consumes this key deliberately —
    `WinProbSourceCatalog` folds it into the sportsbook row as "Sportsbooks (14)"
    — and both clients already keep it out of their source LISTS with their own
    allowlists. Filtering it here would take the count away from the app while
    looking like tidying up.
    """
    served = _format_event(_event())["win_probability_sources"]
    assert served["betting_book_count"]["value"] == 5


def test_the_two_real_sources_are_untouched():
    served = _format_event(_event())["win_probability_sources"]
    assert served["kalshi"]["value"] == 0.01
    assert served["kalshi"]["display_name"] == "Kalshi"
    assert served["betting"]["value"] == 0.2346


def test_a_leading_underscore_key_is_still_skipped():
    """The one filter that was already there, kept. Its own regression arm."""
    served = _format_event(
        _event(sources={"kalshi": {"value": 0.4}, "_internal": 0.9})
    )["win_probability_sources"]
    assert set(served) == {"kalshi"}


# ── the fourth leak, and the registry guard that found it ───────────────────


def test_final_result_is_served_by_name_not_by_key():
    served = _format_event(
        _event(sources={"final_result": {"value": 1.0,
                                         "updated_at": "2026-09-07T19:00:00+00:00"}})
    )["win_probability_sources"]
    assert served["final_result"]["display_name"] == "Final Result"


def test_every_weighted_source_has_a_display_entry():
    """THE REGISTRY GUARD. A source the aggregator gives WEIGHT to is a source a
    reader may be shown, so it must carry a name. Without an entry the wire falls
    back to `display_name = src_key` and prints snake_case at a reader — which is
    what `final_result` was doing on 311 events, and this test is how that was
    found rather than by looking."""
    missing = sorted(set(SOURCE_WEIGHTS) - set(WIN_PROB_SOURCES))
    assert not missing, (
        f"weighted sources with no display entry, so the wire prints their keys: {missing}"
    )


def test_no_source_is_labelled_with_its_own_key():
    for key, meta in WIN_PROB_SOURCES.items():
        name = meta.get("display_name")
        assert name, f"{key} has no display_name, so the wire would print {key!r}"
        assert name != key, f"{key} is labelled with its own key"


# ── the arithmetic one ──────────────────────────────────────────────────────


def test_the_agreement_signal_stops_reading_a_count_as_a_probability():
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


def test_our_own_blend_is_displayable_but_never_counted_as_an_opinion():
    """SERVING and COUNTING are different questions, allowlisted differently, and
    this is the pair that shows why.

    The feed's counting path allowlists on `SOURCE_WEIGHTS` — what the blend
    treats as an independent opinion, and exactly what the shipped frontend mirror
    pins (`PROBABILITY_SOURCE_KEYS`, whose test reads `SOURCE_WEIGHTS` out of this
    Python and fails the moment the two part). `bainluck_aggregate` is in the
    display registry and deliberately not in `SOURCE_WEIGHTS`: counting it would
    ask whether our own output agrees with its own inputs.
    """
    assert "bainluck_aggregate" in WIN_PROB_SOURCES
    assert "bainluck_aggregate" not in SOURCE_WEIGHTS
    assert _numeric_source_probs(
        {"betting": {"value": 0.4}, "kalshi": {"value": 0.42},
         "bainluck_aggregate": {"value": 0.41}}
    ) == [0.4, 0.42]


def test_the_feed_ignores_the_undecodable_entries_too():
    """It always did — they are not numeric — but the arm is here so a future
    'simplification' of the filter has to keep both properties."""
    assert _numeric_source_probs(
        {"statpal_injuries": [{"player": "A. Abqar"}],
         "statpal_injuries_updated": "2026-09-07T18:20:01+00:00",
         "kalshi": {"value": 0.4}}
    ) == [0.4]
