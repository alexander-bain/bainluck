"""#5516 — an inning of a baseball game stops being BADGED a championship.

#6471 shipped the tier half of this and could not reach a reader. Measured on
production the night it released (2026-09-19, web `aa901f83`): `q=padres` went
10 of 10 inning cards from `market_tier 1` to `market_tier 5`, every assertion
green — and the card was unchanged, fresh rather than cached (the price moved
22% -> 23% and the stamp "8m ago" -> "9m ago" across the release). The chip is

    const categoryLabel = marketCategoryLabel(market.category);   // FuturesCard.tsx:141

and that component names neither `market_tier` nor `market_type_label`. The
badge is the `category` column and always was.

WHY THE COLUMN SAYS IT. `resolve_event_category` answers from the EVENT's
Polymarket tags and never reads the market's own name; every arm of it that
lands on a sport returns the single value `championship`. That column is really
"this is sport", spelled with a word that is false about most of its rows.

THE TWO DOORS ALREADY DISAGREED, WHICH IS THE CLEANEST EVIDENCE THAT `game_prop`
IS THE RIGHT ANSWER AND NOT A NEW OPINION. Of the 206 open "Inning Winner" /
"Map N Winner" / "Game N Winner" / "First 5 Innings" rows on 2026-09-19:

    category        rows   sport      written by
    championship     120   baseball   the PARENT writer (tags -> "championship")
    game_prop         86   esports    the decomposed-CHILD writer, which
                                      hardcodes `category="game_prop"`

Structurally identical rows, opposite badges, decided by which ingest door they
came through. Kalshi's door agrees with the child writer: all **1,025** open
Kalshi rows matching this predicate are `game_prop`, **none** `championship`.

BLAST RADIUS, MEASURED COMPREHENSIVELY RATHER THAN SAMPLED (production
2026-09-19, all 32,554 open Polymarket rows, the SQL model first calibrated
against this module's own predicate at 500/500 agreement on a random sample of
separator-bearing names):

    before_category  sport      movers
    championship     baseball      120   <- the specimen class
    championship     football       48   <- "… Season Series Winner", disclosed below
    championship     cricket        33
    ------------------------------------
    everything else                  0

Zero rows move out of `politics`, `award`, `other` or any other value, and zero
rows move INTO `championship`. 168 of the 201 were re-polled within six hours so
they repair on the next hourly poll; the 33 cricket rows have not been re-listed
in over a day and stay as they are until Polymarket lists them again.

THE 48 FOOTBALL ROWS ARE AN ACCEPTED IMPRECISION, NAMED RATHER THAN CARVED OUT.
"Pro Football: 49ers vs. Seahawks Season Series Winner" is not really one game's
prop. It is also not a championship, and #6471 already calls it tier 5. Excluding
it would mean a second vocabulary that `compute_market_tier` does not share —
which re-creates the exact divergence this fix exists to close. One predicate,
two columns.
"""

import inspect
import re

import pytest

from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket as poly
from app.utils.market_label_normalization import (
    compute_market_tier,
    game_prop_category,
)


# ── The specimens, as production stores them ─────────────────────────────
#
# (name, stored category, llm_sport_category). Every row below is a real open
# row read off production on 2026-09-19, not an invented string.

MISLABELLED = [
    ("Miami Marlins vs. San Diego Padres - 4th Inning Winner", "championship", "baseball"),
    ("Athletics vs. Cleveland Guardians - 1st Inning Winner", "championship", "baseball"),
    ("Chicago Cubs vs. Cincinnati Reds - 2nd Inning Winner", "championship", "baseball"),
    ("Washington Nationals vs. St. Louis Cardinals - First 5 Innings Winner",
     "championship", "baseball"),
    ("Pro Football: 49ers vs. Seahawks Season Series Winner", "championship", "football"),
    ("T20 Afghanistan vs India: Afghanistan vs India - Most Sixes", "championship", "cricket"),
]

# Already correct through the other door — these must not move, and they are the
# reason `game_prop` is the right target value rather than a guess.
ALREADY_GAME_PROP = [
    ("Counter-Strike: Just Players vs Leo Team - Map 2 Winner", "game_prop", "esports"),
    ("LoL: Karmine Corp vs Movistar KOI - Game 4 Winner", "game_prop", "esports"),
]

# The load-bearing negatives. A predicate that swept these would put the World
# Series in the Game Props drawer, which is the same defect pointing the other way.
GENUINE_OUTRIGHTS = [
    ("MLB World Series Champion 2026", "championship", "baseball", 1),
    ("Super Bowl LXI Winner", "championship", "football", 1),
    ("UEFA Champions League 2026-27 Winner", "championship", "soccer", 1),
    ("AL Cy Young Winner", "championship", "baseball", 3),
    ("NL East Division Winner", "championship", "baseball", 4),
]

# Non-sport questions that happen to be written "A vs B". The exemption exists
# for these and they are the only thing holding it up.
NON_SPORT_VS = [
    ("OpenAI vs. Anthropic: First to another Millennium Prize?", "tech", "tech"),
    ("Trump vs. Newsom: Who leads the 2028 primary?", None, "politics"),
    ("Bitcoin vs. Ethereum: Bigger gain in Q4?", "crypto", "crypto"),
]


class TestThePredicateNamesTheDefect:
    @pytest.mark.parametrize("name,category,sport", MISLABELLED)
    def test_a_mislabelled_row_is_called_a_game_prop(self, name, category, sport):
        assert game_prop_category(name, category, sport) == "game_prop"

    @pytest.mark.parametrize("name,category,sport", ALREADY_GAME_PROP)
    def test_the_rows_the_other_door_already_got_right_agree(self, name, category, sport):
        """The child writer's hardcode and this predicate must answer the same."""
        assert game_prop_category(name, category, sport) == "game_prop"

    @pytest.mark.parametrize("name,category,sport,_tier", GENUINE_OUTRIGHTS)
    def test_a_real_outright_is_left_alone(self, name, category, sport, _tier):
        assert game_prop_category(name, category, sport) is None

    @pytest.mark.parametrize("name,category,sport", NON_SPORT_VS)
    def test_a_non_sport_question_is_exempt(self, name, category, sport):
        """"OpenAI vs. Anthropic: …" is an "A vs B: C" string and a top-level
        question. Deleting the exemption turns every one of these into a prop."""
        assert game_prop_category(name, category, sport) is None

    def test_the_exemption_reads_the_sport_first_then_the_category(self):
        """`sport_category or category` — the same precedence as the tier."""
        name = "Trump vs. Newsom: Who leads the 2028 primary?"
        assert game_prop_category(name, "championship", "politics") is None
        assert game_prop_category(name, "politics", None) is None

    def test_it_returns_the_value_not_a_boolean(self):
        """Callers write `category = game_prop_category(...) or category`; a bool
        would make every call site restate the target string."""
        result = game_prop_category(MISLABELLED[0][0], "championship", "baseball")
        assert result == "game_prop"
        assert result is not True

    def test_an_empty_or_missing_name_is_not_a_prop(self):
        assert game_prop_category("", "championship", "baseball") is None
        assert game_prop_category(None, "championship", "baseball") is None


class TestTierAndCategoryCannotDisagree:
    """The invariant the fix exists to create, not a restatement of the above.

    Two columns answering one question differently IS the defect; if a later
    edit can move one without the other, the defect is back.
    """

    @pytest.mark.parametrize(
        "name,category,sport",
        MISLABELLED + ALREADY_GAME_PROP + [(n, c, s) for n, c, s, _ in GENUINE_OUTRIGHTS]
        + NON_SPORT_VS,
    )
    def test_whenever_the_category_fires_the_tier_is_five(self, name, category, sport):
        if game_prop_category(name, category, sport) is not None:
            assert compute_market_tier(name, category, sport_category=sport) == 5

    def test_the_tier_function_actually_delegates_rather_than_restating(self):
        """A second copy of the condition inside `compute_market_tier` would pass
        every test above and still drift the day one of them is edited."""
        src = inspect.getsource(compute_market_tier)
        code = "\n".join(line.split("#")[0] for line in src.splitlines())
        assert "game_prop_category(" in code
        assert "is_game_prop(" not in code, (
            "compute_market_tier must ask through game_prop_category, so the two "
            "columns are one sentence evaluated once"
        )

    @pytest.mark.parametrize("name,category,sport,expected", GENUINE_OUTRIGHTS)
    def test_the_extraction_left_the_shipped_tiers_untouched(
        self, name, category, sport, expected
    ):
        """Regression guard on the refactor itself. #6471's behaviour is live and
        measured; lifting the condition out may not move any of it."""
        assert compute_market_tier(name, category, sport_category=sport) == expected

    @pytest.mark.parametrize("name,category,sport", NON_SPORT_VS)
    def test_non_sport_questions_keep_their_top_level_tier(self, name, category, sport):
        assert compute_market_tier(name, category, sport_category=sport) == 2


class TestTheTitleThePredicateSeesIsTheVenues:
    """Non-vacuity: the writer passes `event.title`, so if the parser did not put
    the market's name there, every assertion above would be about a string that
    never reaches production."""

    @staticmethod
    def _parse(title: str):
        svc = PolymarketAPIService()
        return svc._parse_event(
            {
                "id": "61422581",
                "title": title,
                "slug": "marlins-padres-4th-inning",
                "active": True,
                "closed": False,
                "endDate": "2026-09-19T23:00:00Z",
                "markets": [
                    {
                        "id": "614225",
                        "conditionId": "0x4d61726c696e73",
                        "question": title,
                        "slug": "marlins-padres-4th-inning",
                        "outcomes": '["San Diego Padres", "Miami Marlins"]',
                        "outcomePrices": '["0.23", "0.20"]',
                        "clobTokenIds": '["111", "222"]',
                        "closed": False,
                    }
                ],
            }
        )

    def test_the_specimens_name_survives_the_real_parser(self):
        name = MISLABELLED[0][0]
        event = self._parse(name)
        assert event is not None, "the parser refused a venue-shaped payload"
        assert event.title == name

    def test_and_the_predicate_fires_on_what_the_parser_produced(self):
        event = self._parse(MISLABELLED[0][0])
        assert game_prop_category(event.title, "championship", "baseball") == "game_prop"


class TestTheWriterActuallyAsksIt:
    """Structural, because this path needs a live async session to execute — the
    same idiom and the same reason as `test_polymarket_under_leg_book.py` and
    `test_polymarket_pair_price_coherence_6793.py`.

    Comments are stripped first: this fix ships a long explanatory comment that
    names every symbol below, and a blunt substring test over source text cannot
    tell code from prose.
    """

    @staticmethod
    def _code() -> str:
        src = inspect.getsource(poly._process_event_batch)
        return "\n".join(line.split("#")[0] for line in src.splitlines())

    def test_the_writer_asks_the_shared_predicate(self):
        code = self._code()
        assert "game_prop_category(" in code

    def test_it_asks_about_the_events_own_title(self):
        """Asking about anything else — the tag, the slug — is the bug it fixes."""
        assert re.search(
            r"game_prop_category\(\s*event\.title", self._code()
        ), "the predicate must be given the name the reader sees"

    def test_the_override_is_actually_assigned_to_the_column(self):
        """Mutation M5, which survived the first pass and is the reason this test
        exists: replacing the guard with `if False:` left every other assertion in
        this class green — the predicate is still called, the flag is still set,
        `update_set["category"]` is still written — while the value written is the
        OLD `championship` and the fix does nothing whatsoever.

        Computing an answer is not applying it.
        """
        assert re.search(
            r"if _category_corrected:\s*\n\s*category = _game_prop_category\b",
            self._code(),
        ), "the corrected value must be assigned to `category`, not merely computed"

    def test_the_correction_reaches_rows_that_already_exist(self):
        """`category` is otherwise INSERT-only on this upsert, which is exactly
        why 120 rows kept the wrong badge after #6471 corrected their tier.
        An insert-only fix leaves every already-open row lying until it closes."""
        code = self._code()
        assert 'update_set["category"] = category' in code

    def test_but_never_unconditionally(self):
        """An unconditional `"category": category` in the update set would hand
        every hourly re-poll authority over a column that two repair tasks and an
        LLM also write — reverting them on 32,554 open rows, forever."""
        code = self._code()
        assert '"category": category' not in code
        assert re.search(
            r"if _category_corrected:\s*\n\s*update_set\[\"category\"\] = category",
            code,
        ), "the write must be gated on the override having actually fired"

    def test_the_flag_is_only_set_when_the_value_would_change(self):
        code = self._code()
        assert "category != _game_prop_category" in code

    def test_the_writer_does_not_carry_its_own_copy_of_the_rule(self):
        """A regex over market names growing here is how this rail drifts from
        the poller — the warning `repair_kalshi_nhl_prop_category` is built on."""
        code = self._code()
        assert "is_game_prop(" not in code
        assert "Inning" not in code

    def test_the_correction_happens_before_the_tier_is_computed(self):
        """So `compute_market_tier` and the stored `category` are read off the
        same value, rather than the tier seeing a category the row will not have."""
        code = self._code()
        override = code.index("_game_prop_category = game_prop_category(")
        tier = code.index("market_tier = compute_market_tier(")
        assert override < tier
