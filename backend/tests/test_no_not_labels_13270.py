"""Regression guard for #13270: never synthesize 'Not <subject>' labels on Discover.

Builder C recorded all 17 live public Discover rows that received a server-made
'Not <subject>' label from `humanize_binary_outcome_name` (Strategy 1). In
negative/exit questions like 'Will Warsh be out as Fed Chair by June 30, 2027?',
'Not Warsh 93%' inverted the meaning of the 93% 'No' outcome.

Every binary yes-or-no market must serve the venue's canonical 'Yes' / 'No'
outcomes under the market's own title — never a manufactured 'Not ' label.
"""

import pytest

from app.utils.feed_reasons import (
    humanize_binary_outcome_name,
    humanize_outcome_names_for_feed,
)

# All 17 rows from Builder C's live scan on #13270 (comment 7055008840):
# (market_id, market_title, no_prob, yes_prob)
BUILDER_C_17_ROWS = [
    (
        56995847,
        "Will Warsh be out as Fed Chair by June 30, 2027?",
        0.93,
        0.07,
    ),
    (
        61380674,
        "Will Boston Bruins advance to the Second Round of the 2027 Stanley Cup Playoffs?",
        0.52,
        0.48,
    ),
    (
        61324475,
        "Will OpenAI IPO by June 30, 2027?",
        0.61,
        0.39,
    ),
    (
        22979758,
        "Will Anthropic's valuation hit (HIGH) $1.75T by December 31?",
        0.80,
        0.20,
    ),
    (
        71070985,
        "Will Salt Lake City get more snow than average this winter?",
        0.22,
        0.78,
    ),
    (
        61380669,
        "Will Nashville Predators advance to the Western Conference Finals of the 2027 Stanley Cup Playoffs?",
        0.88,
        0.12,
    ),
    (
        61380711,
        "Will Florida Panthers advance to the Eastern Conference Finals of the 2027 Stanley Cup Playoffs?",
        0.59,
        0.41,
    ),
    (
        69310392,
        "Will S&P 500 (SPY) hit (LOW) $690 in November?",
        0.27,
        0.73,
    ),
    (
        67637895,
        "Will Amazon.com, Inc. (AMZN) hit (LOW) $240 in November?",
        0.42,
        0.58,
    ),
    (
        67637906,
        "Will Meta Platforms, Inc. (META) hit (LOW) $540 in November?",
        0.45,
        0.55,
    ),
    (
        67647293,
        "Will Alphabet Inc. (GOOGL) hit (LOW) $270 in November?",
        0.10,
        0.90,
    ),
    (
        67666188,
        "Will Gold (XAUUSD) hit (LOW) $3,400 in November?",
        0.50,
        0.50,
    ),
    (
        67929513,
        "Will WTI Crude Oil (WTI) hit (LOW) $80 in November?",
        0.40,
        0.60,
    ),
    (
        68610461,
        "Will Robinhood Markets, Inc. (HOOD) hit (LOW) $60 in November?",
        0.35,
        0.65,
    ),
    (
        68702492,
        "Will Tesla, Inc. (TSLA) hit (LOW) $330 in November?",
        0.48,
        0.52,
    ),
    (
        69981670,
        "Will NVIDIA (NVDA) hit (LOW) $128 in November?",
        0.30,
        0.70,
    ),
    (
        69114046,
        "Will Apple (AAPL) hit (LOW) $336 in November?",
        0.45,
        0.55,
    ),
]

# Additional live Discover rows observed on Fri Nov 20 night (22:15 PT):
ADDITIONAL_LIVE_ROWS = [
    (
        70733137,
        "Will Unitree be removed from Chinese Military Companies list by June 30, 2027?",
        0.935,
        0.065,
    ),
    (
        62905394,
        'Will "Mo Bamba" by Sheck Wes be on the radio in GTA VI at launch?',
        0.6945,
        0.3055,
    ),
    (
        61327582,
        "Will S&P 500 (SPX) hit $6,000 (LOW) in December?",
        0.8015,
        0.1985,
    ),
]


class TestNoManufacturedNotLabels13270:
    def test_builder_c_fixture_has_all_17_rows(self):
        assert len(BUILDER_C_17_ROWS) == 17
        assert len({mid for mid, _, _, _ in BUILDER_C_17_ROWS}) == 17

    @pytest.mark.parametrize(
        "market_id,title,no_prob,yes_prob",
        BUILDER_C_17_ROWS + ADDITIONAL_LIVE_ROWS,
        ids=[f"m{mid}" for mid, _, _, _ in BUILDER_C_17_ROWS + ADDITIONAL_LIVE_ROWS],
    )
    def test_no_row_serves_not_prefix_label(self, market_id, title, no_prob, yes_prob):
        assert humanize_binary_outcome_name("No", title) == "No"
        assert humanize_binary_outcome_name("Yes", title) == "Yes"

        outcomes = sorted(
            [
                {"name": "No", "probability": no_prob},
                {"name": "Yes", "probability": yes_prob},
            ],
            key=lambda o: o["probability"],
            reverse=True,
        )
        rendered = humanize_outcome_names_for_feed(outcomes, title)
        names = [o["name"] for o in rendered]
        for name in names:
            assert not name.startswith("Not "), (
                f"market {market_id} ({title!r}) emitted manufactured label {name!r}"
            )
            assert not name.startswith("Not:"), (
                f"market {market_id} ({title!r}) emitted manufactured label {name!r}"
            )
        assert set(names) == {"Yes", "No"}

    def test_warsh_fed_chair_keeps_honest_no_93_and_yes_7(self):
        title = "Will Warsh be out as Fed Chair by June 30, 2027?"
        rendered = humanize_outcome_names_for_feed(
            [
                {"name": "No", "probability": 0.93},
                {"name": "Yes", "probability": 0.07},
            ],
            title,
        )
        assert rendered == [
            {"name": "No", "probability": 0.93},
            {"name": "Yes", "probability": 0.07},
        ]

    def test_named_multi_outcome_markets_unchanged(self):
        outcomes = [
            {"name": "No change", "probability": 0.56},
            {"name": "25 bps cut", "probability": 0.44},
        ]
        assert humanize_outcome_names_for_feed(outcomes, "Fed decision?") == outcomes
