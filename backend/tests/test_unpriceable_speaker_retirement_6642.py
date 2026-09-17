"""#6642 — a book whose OUTCOME NAMES can never price a side must retire its leg.

THE FIFTH SILENCE, and the first that is neither price- nor status-shaped, which
is why none of the four before it can see it. Polymarket links a soccer fixture
a container titled with the bare matchup whose only outcome is the draw:

    market 60986963  "DPR Korea vs. Japan"
       outcomes: [('Draw (DPR Korea vs. Japan)', 0.26)]

#6604 taught `find_moneyline_outcome` to refuse that name — "who draws" is a
different question from "who wins" — so the reading went to None and the writer
correctly stopped writing. Nothing retired the number already stored:
`count_admissible_speakers` counts 1, the book is not settled (0.26 is strictly
inside the band), and it was observed this hour. `/events/15312330` therefore
went on printing **26 % for DPR Korea** — the draw's price wearing Korea's name
— over a Win Probability chart drawn from it, indefinitely. #6604's commit says
"the next matching pass stores the right leg", and that is true only where a
right leg exists to store; on a market whose ONLY outcome is the draw there is
none, and those are exactly the fixtures the draw leg was the hero's sole input
for.

WHAT MAKES THIS SAFE TO RETIRE IS PERMANENCE, the same line #5548's file is
drawn around, and it is established by taking the PRICE out of the question.
Every resolution path in `find_moneyline_outcome` needs a price strictly inside
(0, 1) AND a name that clears one of its three name tests. So each admissible
speaker is asked again through the real resolver with every price held at 0.5 —
a value no price gate can refuse. If it STILL says nothing, only the names are
left deciding, and an outcome does not get renamed into a team. `_is_settled_book`
is the same argument from the other side: it holds the names and reads the
prices.

MEASURED, production 2026-09-17 00:5xZ, with the real code rather than by eye.
Over every scheduled/live event holding a stored Polymarket leg and a
bare-matchup-shaped linked market — 553 events — **45 are silent today and all
45 are this one cause** (0 price-only, 0 unparseable); the arm fires on exactly
those 45 and on none of the 508 that speak. 41 of the 45 store a draw leg's
price outright, 4 store its complement. THE KALSHI DELTA IS MEASURED, NOT
ASSERTED: over the same window's 312 events holding a stored Kalshi leg, none is
silent and the arm fires on none, so the rule is left source-agnostic rather
than carrying a special case no population exercises.

THE SURFACE IS STILL A SURFACE, and that is a test here rather than a hope
(`TestTheSurfaceSurvivesTheRetirement`). 41 of the 45 have Polymarket as their
ONLY source, so retiring empties the hero — and an empty hero passes every
refusal assertion ever written. The empty state was photographed on production
before this shipped (`artifacts-lane1-382/CONTROL-no-sources-15309171.png`,
Corinthians v Estudiantes): the hero reads a designed **"No price yet"** with
both crests, the kickoff line and every market section intact. That is the
house's ruling applied, not a new one invented — D102/notice 34, "if a number
cannot be shown honestly, leave the space empty".
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event
from app.tasks.prediction_market_matching import (
    _RETIREMENT_CAUSE_SENTENCES,
    _retire_unbacked_blend_source,
)
from app.utils.live_blend import (
    MarketOutcomes,
    admissible_speakers_are_all_settled,
    admissible_speakers_can_never_price_a_side,
    compute_source_home_probability,
    count_admissible_speakers,
)


NOW = datetime(2026, 9, 17, 0, 50, tzinfo=timezone.utc)

# The production specimen, by name and id, so a reader can find it at the venue.
EVENT_ID = 15312330
HOME = "DPR Korea"
AWAY = "Japan"
DRAW_LEG = "Draw (DPR Korea vs. Japan)"
STORED_WRONG = 0.26


# =============================================================================
# Fakes — only the attributes the gate and the writer actually read
# =============================================================================


class _Market:
    def __init__(self, mid, name, *, source="polymarket", external_id=None):
        self.id = mid
        self.name = name
        self.source = source
        self.external_id = external_id


class _Outcome:
    current_yes_bid = current_yes_ask = None

    def __init__(self, rank, name, probability):
        self.rank = rank
        self.name = name
        self.current_probability = probability


class _Result:
    def __init__(self, rows, scalar=None):
        self._rows = rows
        self._scalar = scalar

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    """Serves the SELECT the retirement issues and records its UPDATEs."""

    def __init__(self, wps):
        self.wps = wps
        self.updates = []
        self.commits = 0

    async def execute(self, stmt):
        text = str(stmt)
        if text.lstrip().upper().startswith("UPDATE"):
            self.updates.append(stmt)
            return _Result([])
        if "events" in text:
            return _Result([], scalar=self.wps)
        raise AssertionError(f"unexpected statement: {text[:160]}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):  # pragma: no cover — error path only
        pass

    def written_sources(self):
        for stmt in self.updates:
            values = dict(stmt._values)
            col = Event.__table__.c.win_probability_sources
            if col in values:
                return values[col].value
        return None

    def written_columns(self):
        """Every column any UPDATE touched — the blast-radius assertion."""
        touched = set()
        for stmt in self.updates:
            touched |= {col.name for col in dict(stmt._values)}
        return touched


def _entry(mid, name, outcomes=(), *, source="polymarket", external_id=None):
    return MarketOutcomes(
        market=_Market(mid, name, source=source, external_id=external_id),
        outcomes=[_Outcome(rank, oname, prob) for rank, oname, prob in outcomes],
        event_commence_time=NOW + timedelta(hours=15),
        event_has_result=False,
    )


def _ref(market_id, name, *, source="polymarket", external_id=None,
         home=HOME, away=AWAY):
    """The anchor the retirement reads its team names off.

    They are parameters and not constants because the arm asks the resolver
    whether THESE names can be priced: handing a Fiorentina board the Korea
    fixture's names makes any board unpriceable. A first draft of this file did
    exactly that and the healthy-board control failed — correctly.
    """
    from app.tasks.prediction_market_matching import _LinkedMarketRef

    return _LinkedMarketRef(
        market_id=market_id,
        source=source,
        external_id=external_id,
        name=name,
        event_id=EVENT_ID,
        event_commence_time=NOW + timedelta(hours=15),
        home_team_name=home,
        away_team_name=away,
    )


def _draw_only_container():
    """60986963, in the shape production served it at 00:50Z."""
    return _entry(60986963, "DPR Korea vs. Japan", [(1, DRAW_LEG, STORED_WRONG)])


def _wps(**sources):
    return {
        name: {"value": value, "display_name": name.title(), "type": "market"}
        for name, value in sources.items()
    }


# =============================================================================
# 1. The predicate — a NAME that can never price is permanent
# =============================================================================


class TestTheProductionSpecimen:
    def test_the_draw_only_container_is_admissible_and_mute(self):
        """The whole defect in two assertions: it may speak, and it cannot."""
        group = [_draw_only_container()]
        assert count_admissible_speakers(group) == 1, (
            "the container keeps its bare-matchup title, so the speaker count "
            "cannot see the problem — that is why a fifth arm is needed"
        )
        assert admissible_speakers_are_all_settled(group) is False, (
            "0.26 is strictly inside the band, so #5548's price arm abstains"
        )
        assert compute_source_home_probability(group, HOME, AWAY) is None, (
            "#6604 refuses the draw name, so no reading resolves"
        )
        assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is True

    def test_it_stays_true_at_any_price_the_draw_could_quote(self):
        """The permanence claim, exercised rather than asserted.

        The draw leg is repriced across the whole open band. The verdict may not
        move: nothing about a price decides this one, which is the difference
        between this arm and #5548's.
        """
        for price in (0.01, 0.12, 0.26, 0.5, 0.74, 0.99):
            group = [_entry(60986963, "DPR Korea vs. Japan", [(1, DRAW_LEG, price)])]
            assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is True, (
                f"the draw leg at {price} still cannot say who wins"
            )

    def test_the_complement_shape_is_the_same_cause(self):
        """15194389 (Portugal v Wales) stored 0.89 off a draw priced 0.11.

        4 of the 45 store the complement rather than the price — the orientation
        differs, the cause does not. Kills a fix written to the 41 alone.
        """
        group = [
            _entry(
                60000001,
                "Portugal vs. Wales",
                [(1, "Draw (Portugal vs. Wales)", 0.11)],
            )
        ]
        assert admissible_speakers_can_never_price_a_side(
            group, "Portugal", "Wales"
        ) is True

    def test_live_props_beside_it_do_not_rescue_the_winner(self):
        """15312330's real group: the container beside its six derivatives.

        The derivatives are not admissible, so their prices cannot bear on
        whether the SOURCE has an opinion about the winner. Kills the mutant
        that asks the question of every market instead of the admissible ones.
        """
        group = [
            _draw_only_container(),
            _entry(60986931, "DPR Korea vs. Japan - Exact Score",
                   [(1, "DPR Korea 1 - 0 Japan", 0.125)]),
            _entry(60986894, "DPR Korea vs. Japan - Total Corners",
                   [(1, "Japan Corners: O/U 4.5", 0.505)]),
            _entry(60986940, "DPR Korea vs. Japan - Halftime Result",
                   [(1, "Japan", 0.105)]),
        ]
        assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is True


class TestTheTransientCaseIsLeftAlone:
    """The twitch guard. Retiring a merely-unpriced winner would drop and re-add
    the leg as prices come and go — a whole source weight every fifteen minutes.
    """

    def test_an_unpriced_two_sided_winner_market_abstains(self):
        """THE test this guard is drawn around.

        Both team legs are present and NOT priced, so no reading resolves today
        — and the arm must still refuse, because a price is exactly what can
        come back. Kills any implementation that retires on "the reading is
        None".
        """
        group = [
            _entry("60986963", "DPR Korea vs. Japan",
                   [(1, HOME, None), (2, AWAY, None), (3, DRAW_LEG, 0.26)])
        ]
        assert compute_source_home_probability(group, HOME, AWAY) is None
        assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is False

    def test_a_winner_market_priced_at_the_boundary_abstains_to_the_settled_arm(self):
        """Terminal prices are #5548's case and must keep its counter.

        Both arms would happily retire this leg; the funnel has to say which
        silence it was, so the name arm declines a book the price arm owns.
        """
        group = [
            _entry(60986963, "DPR Korea vs. Japan",
                   [(1, HOME, 1.0), (2, AWAY, 0.0), (3, DRAW_LEG, 0.0)])
        ]
        assert admissible_speakers_are_all_settled(group) is True
        assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is False

    def test_a_book_we_have_not_fetched_abstains(self):
        """An empty outcome list is "no evidence", never "cannot price"."""
        group = [_entry(60986963, "DPR Korea vs. Japan", [])]
        assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is False

    def test_one_unfetched_speaker_abstains_for_the_whole_group(self):
        """A group is only mute if EVERY speaker is, and an unfetched book is
        not evidence of anything. Kills an `any()` where the rule needs `all()`.
        """
        group = [_draw_only_container(), _entry(60986964, "DPR Korea vs. Japan", [])]
        assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is False

    def test_a_group_with_no_admissible_speaker_abstains(self):
        """#5031's case, which keeps its own funnel counter."""
        group = [
            _entry(60986894, "DPR Korea vs. Japan - Total Corners",
                   [(1, "Total Corners: O/U 9.5", 0.5)])
        ]
        assert count_admissible_speakers(group) == 0
        assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is False

    def test_an_admissible_but_unparseable_title_abstains(self):
        """Mute for a reason that lives in the PARSER, not in the outcome names.

        Folding it in would retire a leg while hiding a parser defect behind a
        name-shaped counter. Measured 0 of 45 in the population, so this costs
        nothing today and keeps the causes separable tomorrow.

        THE SPECIMEN HAD TO BE HUNTED, and the first draft of this test was
        vacuous — a mutation pass caught it. `Set 1 Winner: …` looks like the
        obvious unparseable title and is refused one gate EARLIER, at admission,
        so the group reached the arm with zero speakers and passed for the wrong
        reason: deleting the clause under test left it green. A trailing
        qualifier is the shape that is admissible AND unparseable, so it is the
        one that exercises this line.
        """
        group = [_entry(60986963, "DPR Korea vs. Japan - Winner",
                        [(1, DRAW_LEG, 0.26)])]
        assert count_admissible_speakers(group) == 1, (
            "if this ever reads 0 the test is vacuous again — the clause it "
            "guards is only reachable for a market that may speak"
        )
        assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is False

    def test_a_segment_head_never_reaches_the_arm_at_all(self):
        """`Set 1 Winner: …` is refused at ADMISSION, one gate earlier.

        Kept as its own assertion because it was mistaken for the case above;
        naming the difference is what stops the next reader repeating it.
        """
        group = [_entry(60986963, "Set 1 Winner: DPR Korea vs. Japan",
                        [(1, DRAW_LEG, 0.26)])]
        assert count_admissible_speakers(group) == 0
        assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is False


class TestAHealthyBoardIsNeverTouched:
    """The 508 that speak. An over-refusing arm strips real readings — CERT-2980's
    finding in this function's sibling — so the controls are the ship.
    """

    def test_a_three_way_board_with_both_team_legs_abstains(self):
        """15306079's real shape (Fiorentina v Napoli), and it is also the trap.

        Its draw is priced 0.285 and so is its home leg, so the issue's own
        population SQL — "stored value equals a Draw leg's price" — matched it as
        a defect. It is not one: the stored 0.285 is the HOME team's price, which
        the board prices perfectly well. A rule keyed on that coincidence would
        blank a healthy hero.
        """
        group = [
            _entry(60347030, "ACF Fiorentina vs. SSC Napoli",
                   [(1, "SSC Napoli", 0.425), (2, "ACF Fiorentina", 0.285),
                    (3, "Draw (ACF Fiorentina vs. SSC Napoli)", 0.285)])
        ]
        home, away = "ACF Fiorentina", "SSC Napoli"
        reading = compute_source_home_probability(group, home, away)
        assert reading is not None and reading.home_probability == pytest.approx(0.285)
        assert admissible_speakers_can_never_price_a_side(group, home, away) is False

    def test_a_two_sided_board_abstains(self):
        group = [
            _entry(59852299, "San Diego Padres vs. San Francisco Giants",
                   [(1, "San Diego Padres", 0.705), (2, "San Francisco Giants", 0.295)])
        ]
        assert admissible_speakers_can_never_price_a_side(
            group, "San Francisco Giants", "San Diego Padres"
        ) is False

    def test_a_full_matchup_outcome_still_prices_a_side(self):
        """Polymarket's UFC shape — the name IS the matchup, which #6604 keeps.

        The arm must not sweep up the fallback #6604 deliberately preserved.
        """
        group = [
            _entry(60000002, "Tai Tuivasa vs. Robelis Despaigne",
                   [(1, "Tai Tuivasa vs. Robelis Despaigne", 0.62)])
        ]
        assert admissible_speakers_can_never_price_a_side(
            group, "Tai Tuivasa", "Robelis Despaigne"
        ) is False

    def test_a_generic_yes_no_book_still_prices_a_side(self):
        group = [
            _entry(60000003, "DPR Korea vs. Japan",
                   [(1, "Yes", 0.31), (2, "No", 0.69)])
        ]
        assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is False

    def test_a_kalshi_group_is_not_retired_by_this_arm(self):
        """Measured 0 of 312 on production; asserted here so it stays 0.

        Kalshi's admission is venue-side, and its primary is exempt, so a Kalshi
        board that prices a side must stay untouched by a rule written for
        Polymarket's containers.
        """
        group = [
            _entry(70000001, "Will DPR Korea beat Japan?",
                   [(1, "Yes", 0.31), (2, "No", 0.69)],
                   source="kalshi", external_id="KXSOCCER-26SEP17DPRJPN-DPR")
        ]
        assert admissible_speakers_can_never_price_a_side(group, HOME, AWAY) is False


# =============================================================================
# 2. The retirement — it fires, and it says WHICH silence
# =============================================================================


@pytest.mark.asyncio
class TestTheRetirementFires:
    async def test_the_specimens_wrong_leg_is_removed(self):
        session = _FakeSession(_wps(polymarket=STORED_WRONG))
        stats = {"funnel": {}}
        retired = await _retire_unbacked_blend_source(
            session, _ref(60986963, "DPR Korea vs. Japan"),
            [_draw_only_container()], stats,
        )
        assert retired is True
        assert session.written_sources() == {}
        assert session.commits == 1

    async def test_the_new_cause_is_counted_apart(self):
        """A new cause folded into an old counter reads as a spike in the old
        one, and the reach of each is measured separately.
        """
        session = _FakeSession(_wps(polymarket=STORED_WRONG))
        stats = {"funnel": {}}
        await _retire_unbacked_blend_source(
            session, _ref(60986963, "DPR Korea vs. Japan"),
            [_draw_only_container()], stats,
        )
        assert stats["funnel"] == {"blend_source_retired_no_name_can_price": 1}

    async def test_a_settled_book_still_counts_as_a_settled_book(self):
        """The branch this arm now shares with #5548 must not steal its counter."""
        session = _FakeSession(_wps(polymarket=0.069))
        stats = {"funnel": {}}
        await _retire_unbacked_blend_source(
            session, _ref(60258512, "San Diego Padres vs. San Francisco Giants",
                          home="San Francisco Giants", away="San Diego Padres"),
            [_entry(60258512, "San Diego Padres vs. San Francisco Giants",
                    [(1, "San Diego Padres", 1.0)])],
            stats,
        )
        assert stats["funnel"] == {"blend_source_retired_settled_book": 1}

    async def test_a_healthy_board_is_not_retired(self):
        """The whole point of the controls, at the call site."""
        session = _FakeSession(_wps(polymarket=0.285))
        stats = {"funnel": {}}
        retired = await _retire_unbacked_blend_source(
            session, _ref(60347030, "ACF Fiorentina vs. SSC Napoli",
                          home="ACF Fiorentina", away="SSC Napoli"),
            [_entry(60347030, "ACF Fiorentina vs. SSC Napoli",
                    [(1, "SSC Napoli", 0.425), (2, "ACF Fiorentina", 0.285),
                     (3, "Draw (ACF Fiorentina vs. SSC Napoli)", 0.285)])],
            stats,
        )
        assert retired is False
        assert session.updates == []
        assert stats["funnel"] == {}

    async def test_every_cause_the_function_can_set_has_a_sentence(self):
        """The log line is keyed off the funnel key, so a sixth cause added
        without its sentence would raise here rather than KeyError in
        production. Both directions, so a dead sentence is caught too.
        """
        import inspect

        from app.tasks import prediction_market_matching as pmm

        source = inspect.getsource(pmm._retire_unbacked_blend_source)
        keys_set = {
            line.split('"')[1]
            for line in source.splitlines()
            if "funnel_key = " in line and '"' in line
        }
        assert keys_set, "the scan found no funnel_key assignment — it has drifted"
        assert keys_set == set(_RETIREMENT_CAUSE_SENTENCES), (
            "every cause the function can set needs exactly one sentence"
        )


@pytest.mark.asyncio
class TestTheSurfaceSurvivesTheRetirement:
    """41 of the 45 have Polymarket as their only source, so this arm empties
    their hero — and an empty surface passes every refusal assertion, which is
    why the removal is bounded here rather than merely observed.
    """

    async def test_only_the_probability_column_is_touched(self):
        """The blast radius. Teams, kickoff, scores, links and every market row
        are untouched, so the card is still a card — the page renders the
        designed "No price yet" hero (photographed on production, see the module
        docstring), not a broken one.
        """
        session = _FakeSession(_wps(polymarket=STORED_WRONG))
        await _retire_unbacked_blend_source(
            session, _ref(60986963, "DPR Korea vs. Japan"),
            [_draw_only_container()], {"funnel": {}},
        )
        assert session.written_columns() == {"win_probability_sources"}

    async def test_the_other_sources_of_a_blended_hero_survive(self):
        """The other 4 of the 45 carry three sources, and they must keep two.

        Retiring the wrong Polymarket leg there does not empty the hero — it
        makes it more accurate. Kills an implementation that clears the column.
        """
        session = _FakeSession(_wps(polymarket=STORED_WRONG, kalshi=0.71, espn=0.68))
        await _retire_unbacked_blend_source(
            session, _ref(60986963, "DPR Korea vs. Japan"),
            [_draw_only_container()], {"funnel": {}},
        )
        written = session.written_sources()
        assert set(written) == {"kalshi", "espn"}
        assert written["kalshi"]["value"] == 0.71
