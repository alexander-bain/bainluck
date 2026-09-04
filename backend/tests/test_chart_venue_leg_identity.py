"""live/060 (CERT-881) — a venue leg is fenced by WHICH question before WHOSE roster.

THE DEFECT THIS FILE HOLDS DOWN, as the cert window measured it on production
2026-09-04 over the exact set `eligible_market_ids()` nominates:

    Kalshi   34277822  US Open Men's Singles Winner          33 outcomes
    Polymarket 114159  2026 Men’s US Open Winner (Tennis)    23 outcomes  0.783
    Polymarket 57718620  Cincinnati Open: Winner             78 outcomes  0.879

`find_venue_legs()` ranked candidates by outcome-name overlap alone, so it chose
CINCINNATI — a different tournament, a fortnight earlier, on the same tour — and
`blend_venues()` averaged Cincinnati's prices into the US Open title chart. The
page got the density this queue shipped and lost the thing the density was for.

WHY OVERLAP CANNOT BE THE TEST. One tour draws from one pool of players. Two
tournaments a month apart share almost every name, and the SMALLER field is the
denominator, so a 78-name draw that swallows a 33-name field scores higher than
the real 23-name market that is missing five of them. The score is most
confident exactly where it is most wrong — which is why the fix is an identity
fence applied BEFORE the score, not a higher threshold on the score.

THE FIXTURES ARE THE PRODUCTION ROWS. All three fields below are the real
`futures_outcomes` name sets, and the first test in the file re-derives the
0.879-beats-0.783 arithmetic from them: if a future edit makes these rosters
agreeable, that control fails and says so, rather than letting every assertion
below pass on a fixture that no longer reproduces the defect.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import futures_chart_series_fill as fill
from app.utils.futures_chart_series import question_identity, same_question

NOW = datetime(2026, 9, 4, 6, 0, tzinfo=timezone.utc)

#: The field as production holds it, 33 outcomes, measured 2026-09-04.
KALSHI_US_OPEN_MEN = (
    "Alexander Bublik", "Alexander Zverev", "Alex de Minaur", "Andrey Rublev",
    "Arthur Fils", "Ben Shelton", "Cameron Norrie", "Carlos Alcaraz",
    "Casper Ruud", "Daniil Medvedev", "Dino Prizmic", "Felix Auger-Aliassime",
    "Flavio Cobolli", "Frances Tiafoe", "Francisco Cerundolo",
    "Gabriel Diallo", "Holger Rune", "Hubert Hurkacz", "Jack Draper",
    "Jakub Mensik", "Jan-Lennard Struff", "Jannik Sinner", "Joao Fonseca",
    "Karen Khachanov", "Learner Tien", "Lorenzo Musetti", "Novak Djokovic",
    "Rafael Jodar", "Sebastian Korda", "Stefanos Tsitsipas", "Taylor Fritz",
    "Tommy Paul", "Valentin Vacherot",
)

#: The field as production holds it, 23 outcomes, measured 2026-09-04.
POLYMARKET_US_OPEN_MEN = (
    "Alexander Bublik", "Alexander Zverev", "Andrey Rublev", "Arthur Fils",
    "Ben Shelton", "Carlos Alcaraz", "Daniil Medvedev",
    "Felix Auger Aliassime", "Flavio Cobolli", "Frances Tiafoe",
    "Grigor Dimitrov", "Holger Rune", "Hubert Hurkacz", "Jack Draper",
    "Jakub Mensik", "Jannik Sinner", "Jiri Lehecka", "Joao Fonseca",
    "Lorenzo Musetti", "Matteo Berrettini", "Novak Djokovic", "Other",
    "Taylor Fritz",
)

#: The field as production holds it, 78 outcomes, measured 2026-09-04.
POLYMARKET_CINCINNATI = (
    "Adolfo Daniel Vallejo", "Adrian Mannarino",
    "Alejandro Davidovich Fokina", "Alejandro Tabilo", "Aleksandar Kovacevic",
    "Alexander Blockx", "Alexander Bublik", "Alexander Zverev",
    "Alex de Minaur", "Alex Michelsen", "Andrey Rublev", "Arthur Fery",
    "Arthur Fils", "Arthur Rinderknech", "Ben Shelton",
    "Botic van de Zandschulp", "Brandon Nakashima", "Cameron Norrie",
    "Camilo Ugo Carabelli", "Carlos Alcaraz", "Casper Ruud",
    "Corentin Moutet", "Daniel Altmaier", "Daniil Medvedev",
    "Denis Shapovalov", "Ethan Quinn", "Fabian Marozsan",
    "Felix Auger-Aliassime", "Flavio Cobolli", "Frances Tiafoe",
    "Francisco Cerundolo", "Hamad Medjedovic", "Holger Rune",
    "Hubert Hurkacz", "Ignacio Buse", "Jakub Mensik", "James Duckworth",
    "Jan Choinski", "Jan-Lennard Struff", "Jannik Sinner", "Jaume Munar",
    "Jenson Brooksby", "Jesper de Jong", "Jiri Lehecka", "Joao Fonseca",
    "Juan Manuel Cerundolo", "Juncheng Shang", "Kamil Majchrzak",
    "Karen Khachanov", "Learner Tien", "Lorenzo Musetti", "Luciano Darderi",
    "Mariano Navone", "Martin Landaluce", "Matteo Arnaldi",
    "Matteo Berrettini", "Miomir Kecmanovic", "Novak Djokovic", "Nuno Borges",
    "Pablo Carreno Busta", "Rafael Jodar", "Raphael Collignon",
    "Roman Andres Burruchaga", "Sebastian Baez", "Sebastian Korda",
    "Tallon Griekspoor", "Taylor Fritz", "Terence Atmane",
    "Thiago Agustin Tirante", "Tomas Machac", "Tomas Martin Etcheverry",
    "Tommy Paul", "Ugo Humbert", "Valentin Vacherot", "Vit Kopriva",
    "Yannick Hanfmann", "Zachary Svajda", "Zizou Bergs",
)

# ---------------------------------------------------------------------------
# The three production rows, and a session that offers both Polymarket fields
# ---------------------------------------------------------------------------


class _Outcome:
    def __init__(self, oid, name, external_id, probability=0.01):
        self.id = oid
        self.name = name
        self.external_id = external_id
        self.current_probability = probability


class _Market:
    def __init__(self, mid, source, name, names, *, created_at=None):
        self.id = mid
        self.source = source
        self.name = name
        self.market_tier = 1
        self.llm_sport_category = "tennis"
        self.status = "open"
        self.created_at = created_at or (NOW - timedelta(days=87))
        self.outcomes = [
            _Outcome(mid * 100 + i, n, f"{source}:{mid}:{i}")
            for i, n in enumerate(names)
        ]


class _CandidateSession:
    """Returns the SAME candidate pool the production query returns.

    The pool is handed over whole rather than filtered by the select, because
    the subject here is the CHOICE among candidates: the SQL's own predicates
    (tier, category, other source, open) are already what put these two rows in
    front of the algorithm on production, and a fake that re-implemented them
    would only be testing itself.
    """

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _statement):
        rows = self._rows

        class _Result:
            def scalars(self):
                return self

            def all(self):
                return list(rows)

        return _Result()


def kalshi_us_open():
    return _Market(
        34277822, "kalshi", "US Open Men's Singles Winner", KALSHI_US_OPEN_MEN,
        created_at=NOW - timedelta(days=87),
    )


def polymarket_us_open():
    return _Market(
        114159, "polymarket", "2026 Men’s US Open Winner (Tennis)",
        POLYMARKET_US_OPEN_MEN, created_at=NOW - timedelta(days=197),
    )


def polymarket_cincinnati():
    return _Market(
        57718620, "polymarket", "Cincinnati Open: Winner",
        POLYMARKET_CINCINNATI, created_at=NOW - timedelta(days=35),
    )


def _overlap(left, right):
    """The score the old implementation ranked on, re-derived from the rosters."""
    a = {fill._norm(o.name) for o in left.outcomes}
    b = {fill._norm(o.name) for o in right.outcomes}
    return len(a & b) / float(min(len(a), len(b)))


# ---------------------------------------------------------------------------
# The control — this fixture really does reproduce the defect
# ---------------------------------------------------------------------------


class TestTheFixtureReproducesTheDefect:
    def test_cincinnati_outscores_the_real_us_open_on_roster_overlap(self):
        """🔴 Without this, every assertion below could pass on rosters that had
        stopped being the hard case."""
        kalshi = kalshi_us_open()
        right = _overlap(kalshi, polymarket_us_open())
        wrong = _overlap(kalshi, polymarket_cincinnati())

        assert wrong == pytest.approx(0.879, abs=0.002), wrong
        assert right == pytest.approx(0.783, abs=0.002), right
        assert wrong > right, (
            "the fixture no longer reproduces CERT-881 — overlap alone would "
            "now pick the right market and this file proves nothing"
        )
        assert right >= fill.MIN_ROSTER_OVERLAP, (
            "the correct market must clear the roster bar, or it is being "
            "selected by elimination rather than on its merits"
        )


# ---------------------------------------------------------------------------
# The fence
# ---------------------------------------------------------------------------


class TestTheIdentityFence:
    def test_the_two_us_open_names_ask_one_question(self):
        assert same_question(
            "US Open Men's Singles Winner",
            "2026 Men’s US Open Winner (Tennis)",
            category="tennis",
        )
        assert question_identity(
            "US Open Men's Singles Winner", category="tennis"
        ) == (frozenset({"us", "open"}), "men")

    def test_cincinnati_is_a_different_question(self):
        assert not same_question(
            "US Open Men's Singles Winner", "Cincinnati Open: Winner",
            category="tennis",
        )

    def test_the_two_draws_of_one_tournament_are_different_questions(self):
        """Same tokens, different draw. The rosters are disjoint so overlap
        would refuse this too — the fence refuses it for the right reason."""
        assert not same_question(
            "US Open Men's Singles Winner",
            "2026 Women’s US Open Winner (Tennis)",
            category="tennis",
        )

    def test_a_nameless_question_is_never_vouched_for(self):
        assert not same_question("Winner", "Winner", category="tennis")
        assert not same_question(None, "Cincinnati Open: Winner", category="tennis")


# ---------------------------------------------------------------------------
# The selection
# ---------------------------------------------------------------------------


class TestFindVenueLegsPicksTheRightTournament:
    async def test_the_us_open_leg_is_selected_and_cincinnati_is_rejected(self):
        kalshi = kalshi_us_open()
        session = _CandidateSession([polymarket_cincinnati(), polymarket_us_open()])
        stats = {}

        legs = await fill.find_venue_legs(session, kalshi, stats=stats)

        assert [m.id for m in legs] == [34277822, 114159]
        assert 57718620 not in {m.id for m in legs}, (
            "the Cincinnati Open is on the US Open's chart"
        )
        refused = {r["id"]: r for r in stats.get("identity_refused", [])}
        assert 57718620 in refused, (
            "the rejection must be RECORDED — a wrong leg that silently "
            "disappears is a wrong leg nobody can find the next time"
        )
        assert refused[57718620]["overlap"] > 0.6

    async def test_the_order_of_the_candidate_pool_does_not_decide(self):
        """The pool arrives in whatever order Postgres returns it."""
        kalshi = kalshi_us_open()
        session = _CandidateSession([polymarket_us_open(), polymarket_cincinnati()])

        legs = await fill.find_venue_legs(session, kalshi, stats={})

        assert [m.id for m in legs] == [34277822, 114159]

    async def test_cincinnati_alone_pairs_with_nothing(self):
        """🔴 The fence must not be a preference for the better candidate — with
        the real US Open absent, the US Open chart draws ONE venue rather than
        falling back to the closest tournament it can find."""
        kalshi = kalshi_us_open()
        session = _CandidateSession([polymarket_cincinnati()])

        legs = await fill.find_venue_legs(session, kalshi, stats={})

        assert [m.id for m in legs] == [34277822]

    async def test_cincinnatis_own_chart_still_finds_its_own_venue(self):
        """The fence refuses the wrong pair, not every pair."""
        cincinnati = polymarket_cincinnati()
        kalshi_cincinnati = _Market(
            99000001, "kalshi", "Cincinnati Open Winner", KALSHI_US_OPEN_MEN,
        )
        session = _CandidateSession([kalshi_cincinnati])

        legs = await fill.find_venue_legs(session, cincinnati, stats={})

        assert [m.id for m in legs] == [57718620, 99000001]


# ---------------------------------------------------------------------------
# End to end — what reaches the chart
# ---------------------------------------------------------------------------


class TestOnlyUsOpenLegsReachTheSeries:
    async def test_build_market_series_fetches_neither_cincinnatis_prices_nor_its_names(
        self, monkeypatch
    ):
        """The whole payload, built over the real candidate pool.

        Asserts three things at once, which is the only combination that closes
        the defect: the legs the payload NAMES, the legs the venue fetchers were
        actually HANDED, and the names that reached the drawn series. A fix that
        cleaned up the stats line while still fetching Cincinnati's tokens, or
        that fetched only the US Open but let a Cincinnati-only name into the
        field, fails one of the three.
        """
        kalshi = kalshi_us_open()
        session = _CandidateSession([polymarket_cincinnati(), polymarket_us_open()])
        fetched_from: list[int] = []

        async def _captures(_session, ids):
            assert 57718620 not in ids, "Cincinnati's captures were read"
            return {}

        async def _kalshi_series(_service, outcomes, **_kw):
            fetched_from.append(34277822)
            return {
                o.external_id: [
                    (NOW - timedelta(hours=h), 0.30 + h * 0.001) for h in (6, 3, 1)
                ]
                for o in outcomes
            }

        async def _polymarket_series(_service, leg, _outcome, **_kw):
            fetched_from.append(leg.id)
            return [(NOW - timedelta(hours=h), 0.32 + h * 0.001) for h in (5, 2)]

        monkeypatch.setattr(fill, "capture_series_by_name", _captures)
        monkeypatch.setattr(fill, "kalshi_field_series", _kalshi_series)
        monkeypatch.setattr(fill, "polymarket_outcome_series", _polymarket_series)

        payload = await fill.build_market_series(
            session, kalshi,
            kalshi_service=object(), polymarket_service=object(), now=NOW,
        )

        assert [leg["id"] for leg in payload["stats"]["legs"]] == [34277822, 114159]
        assert set(fetched_from) == {34277822, 114159}, (
            f"a venue fetch went to the wrong market: {sorted(set(fetched_from))}"
        )

        drawn = set(payload["outcomes"])
        assert drawn, "the series is empty — the assertions below cannot fail"
        cincinnati_only = {
            fill._norm(n) for n in POLYMARKET_CINCINNATI
        } - {fill._norm(n) for n in KALSHI_US_OPEN_MEN}
        assert cincinnati_only, "the two fields no longer differ"
        assert not (drawn & cincinnati_only), (
            f"Cincinnati-only names on the US Open chart: {drawn & cincinnati_only}"
        )


# ---------------------------------------------------------------------------
# The rest of the measured population
# ---------------------------------------------------------------------------


#: Every cross-source pair the OLD algorithm made over the eligible fill
#: population, read off production 2026-09-04 by reproducing its scoring in SQL:
#: `(category, evolution market name, chosen candidate name, is the pair right)`.
#:
#: Six of the fourteen were the wrong event. They are here because the US Open
#: is not a special case — the same "one tour, one pool of names" shape produced
#: a Spanish Grand Prix on the Italian Grand Prix's chart, a KING OF THE
#: MOUNTAINS jersey on the Vuelta's general-classification chart, and
#: Rhineland-Palatinate's parties on three other German states' charts. A fence
#: tuned to tennis would have left five of those standing.
MEASURED_PAIRS = [
    ("tennis", "US Open Men's Singles Winner",
     "2026 Men’s US Open Winner (Tennis)", True),
    ("tennis", "US Open Men's Singles Winner",
     "Cincinnati Open: Winner", False),
    ("tennis", "US Open Women's Singles Winner",
     "2026 Women’s US Open Winner (Tennis)", True),
    ("chess", "Titled Tuesday Winner: September 8",
     "FIDE Candidates Chess Tournament Winner", False),
    ("cycling", "Vuelta a Espana 2026: Winner",
     "Vuelta a Espana: Blue And White Polka Dot Jersey Winner", False),
    ("esports", "BLAST Open Porto Champion",
     "BLAST Open Porto 2026: Winner", True),
    ("lacrosse", "Premier League Lacrosse: 2026 Champion",
     "Premier Lacrosse League Championship Winner", True),
    ("motorsports", "Italian Grand Prix: Driver Winner",
     "Italian Grand Prix Winner", True),
    ("motorsports", "Italian Grand Prix Winner",
     "Spanish Grand Prix: Driver Winner", False),
    ("politics", "Berlin State Election Winner",
     "Rhineland-Palatinate state election winner?", False),
    ("politics", "Sachsen-Anhalt Parliamentary Election Winner",
     "Rhineland-Palatinate state election winner?", False),
    ("politics", "São Paulo Governor Election Winner",
     "São Paulo Governor winner?", True),
    ("politics", "Ceará Governor Election Winner",
     "Ceará gubernatorial election winner?", True),
    ("politics", "Calgary-Shaw Provincial By-Election Winner",
     "Calgary-Shaw provincial by-election winner?", True),
]


class TestTheFenceOverTheMeasuredPopulation:
    @pytest.mark.parametrize("category,left,right,expected", MEASURED_PAIRS)
    def test_each_measured_pair_is_judged_as_production_shows_it(
        self, category, left, right, expected
    ):
        assert same_question(left, right, category=category) is expected

    def test_the_fence_is_symmetric(self):
        """Which market a page happens to be built FROM cannot change whether
        two markets are the same question."""
        for category, left, right, _expected in MEASURED_PAIRS:
            assert same_question(left, right, category=category) is same_question(
                right, left, category=category
            ), f"{left!r} / {right!r}"

    def test_the_population_still_contains_the_defect_it_was_drawn_for(self):
        """The list is evidence, not decoration: it must hold both a pair the
        fence keeps and a pair it removes, or the parametrise above is vacuous."""
        verdicts = {expected for _c, _l, _r, expected in MEASURED_PAIRS}
        assert verdicts == {True, False}
