"""#9173 — a withdrawn Kalshi leg never renames the live leg it duplicates.

## the ship, as the reader saw it

`bainluck.com/futures/25926800`, "Will mail-order mifepristone access be
restricted nationwide?", 2026-09-27 16:26Z: the hero read **12% · 27JAN**, the
chart legend read **27JAN**, the caption said "27JAN down 2.5 pts from opening",
and the /politics card printed `27JAN 12%`. `27JAN` is the tail of a ticker.

## what the venue said

`/events/KXMIFEPRISTONEMAIL-26?with_nested_markets=true`, read 16:25Z:

    KXMIFEPRISTONEMAIL-26-27      inactive  yes_sub_title 'Before 2027'  subtitle 'Before 2027'
    KXMIFEPRISTONEMAIL-26-27JAN   active    yes_sub_title 'Before 2027'  subtitle None

One outcome, listed twice, the first withdrawn: #4356's shape exactly (a
withdrawn `LARNONE` beside a live `NONE`). #4316's set-level namer saw two legs
called `Before 2027`, and its ticker rung "resolved" them as `27` / `27JAN`. That
is the distinction #4356 said "the venue explicitly denies".

## the arms

* the specimen, verbatim: the live leg keeps `Before 2027`;
* the #4316 control: two ACTIVE legs that collide are still told apart, so the
  change is scoped to withdrawn legs and does not switch the namer off;
* the gotcha-#21 control: a `finalized` / `closed` leg is still a sibling.
  Only `inactive` is a withdrawal (`_is_withdrawn_leg`), the same one-status
  rule #4356 measured (3,898 legs: `inactive` 1);
* a withdrawn leg is still NAMED (every ticker keeps a key), so no caller that
  indexes `names[m.ticker]` can KeyError on it.
"""

from app.tasks.kalshi import kalshi_outcome_names

EVENT = "Will mail-order mifepristone access be restricted nationwide?"
LEG_TITLE = (
    "Will it be reported by any of the Source Agencies that nationwide "
    "restrictions on mail-order mifepristone take effect before Jan 1, 2027?"
)


class _Market:
    """The fields the naming ladder and the withdrawal test read off a venue market."""

    def __init__(self, ticker, status, subtitle=None, yes_sub_title=None, title=LEG_TITLE):
        self.ticker = ticker
        self.title = title
        self.subtitle = subtitle
        self.yes_sub_title = yes_sub_title
        self.status = status


def _specimen(withdrawn_status="inactive"):
    return [
        _Market("KXMIFEPRISTONEMAIL-26-27", withdrawn_status, "Before 2027", "Before 2027"),
        _Market("KXMIFEPRISTONEMAIL-26-27JAN", "active", None, "Before 2027"),
    ]


def test_the_live_leg_keeps_the_venues_label():
    names = kalshi_outcome_names(EVENT, _specimen())

    assert names["KXMIFEPRISTONEMAIL-26-27JAN"] == "Before 2027", (
        "the live leg must read the venue's own label; a withdrawn duplicate is "
        f"not a sibling to be told apart from. got {names}"
    )
    assert "27JAN" not in names.values()


def test_every_leg_is_still_named():
    names = kalshi_outcome_names(EVENT, _specimen())

    assert set(names) == {"KXMIFEPRISTONEMAIL-26-27", "KXMIFEPRISTONEMAIL-26-27JAN"}


def test_two_active_legs_that_collide_are_still_told_apart():
    """#4316's invariant is untouched when neither leg is withdrawn."""
    names = kalshi_outcome_names(EVENT, _specimen(withdrawn_status="active"))

    assert names == {
        "KXMIFEPRISTONEMAIL-26-27": "27",
        "KXMIFEPRISTONEMAIL-26-27JAN": "27JAN",
    }, "the ticker rung still separates two ACTIVE legs sharing a label"


def test_a_finished_leg_is_still_a_sibling():
    """Only `inactive` withdraws. A finalized/closed leg's row is real data (gotcha #21)."""
    for status in ("finalized", "closed", "settled"):
        names = kalshi_outcome_names(EVENT, _specimen(withdrawn_status=status))
        assert names["KXMIFEPRISTONEMAIL-26-27JAN"] == "27JAN", (
            f"a {status!r} leg must still take part in #4316's collision group"
        )


def test_a_market_without_a_status_attribute_is_a_sibling():
    """The settled backfill and #4316's own fixtures pass objects with no `status`."""

    class _NoStatus:
        def __init__(self, ticker):
            self.ticker = ticker
            self.title = EVENT
            self.subtitle = None
            self.yes_sub_title = None

    names = kalshi_outcome_names(EVENT, [_NoStatus("KXAG-29-2"), _NoStatus("KXAG-29-3")])

    assert sorted(names.values()) == ["2", "3"]
