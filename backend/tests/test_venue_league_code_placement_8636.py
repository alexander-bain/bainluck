"""#8636 — a fixture's competition comes from the venue, not from its clubs.

THE DEFECT. Event 15317344, "1. FC Heidenheim @ VfB Stuttgart", led Discover as
a green BUNDESLIGA · LIVE card. It was a club friendly: Polymarket lists it as
`clf-vfb-fch-2026-09-25` under series `clf-games`, "Club Friendlies". The row
was minted on `soccer_other` and #5576's placer moved it into the Bundesliga
because both clubs play there.

WHAT THIS FILE PINS.
  1. The predicate against the production census it was written from: every
     Polymarket-created soccer row placed out of the catch-all in the 60 days
     to 2026-09-25, with the Gamma slug read for each. 11 of 44 contradict the
     venue and must be refused; the other 33 must still be placed.
  2. The create flow itself — the sport key `find_or_create_event` is handed
     for the specimen, its Bundesliga control, and a row with no slug (which
     must fail OPEN, because rows ingested before the stamp carry none).
  3. The ingest writes the slug on BOTH rows the create flow can read: the
     parent and the decomposed sub-market (the row an event is minted from).
"""

import ast
import inspect
from datetime import datetime, timezone

import pytest

import app.services.event_registry as event_registry
import app.tasks.prediction_market_matching as pmm
from app.tasks.polymarket import sub_market_metadata
from app.utils.venue_competition import (
    POLYMARKET_EVENT_SLUG_KEY as SLUG_FIELD,
    POLYMARKET_LEAGUE_CODES,
    polymarket_league_code,
    venue_refuses_placement,
)
from tests.lib_placement_predicate import PredicateSession, ScheduleRow


# (event id, Gamma slug of one of its Polymarket markets, league it was placed in)
# Read from production + Gamma on 2026-09-25.
PLACED_CENSUS = [
    (15318598, "argcopa-pla-elp-2026-10-01", "soccer_argentina_primera_division"),
    (15315592, "bel1-rch-cer-2026-09-19", "soccer_belgium_first_div"),
    (15318376, "bra-vit-cha-2026-10-07", "soccer_brazil_campeonato"),
    (15316293, "bra2-bot-vln-2026-10-03", "soccer_brazil_serie_b"),
    (15318378, "bra2-ava-lon-2026-10-07", "soccer_brazil_serie_b"),
    (15313687, "bra2-bot-pop-2026-09-29", "soccer_brazil_serie_b"),
    (15317980, "bra2-pop-juv-2026-10-06", "soccer_brazil_serie_b"),
    (15315613, "bra2-ava-csc-2026-10-02", "soccer_brazil_serie_b"),
    (
        15316760,
        "col1-inm-mif-2026-08-11-more-markets",
        "soccer_conmebol_copa_sudamericana",
    ),
    (15316072, "el1-wim-ste-2026-10-03", "soccer_england_league1"),
    (15317344, "clf-vfb-fch-2026-09-25", "soccer_germany_bundesliga"),
    (15313072, "bun-moe-mai-2026-09-19-player-props", "soccer_germany_bundesliga"),
    (15314794, "por-gil-csm-2026-09-19-total-corners", "soccer_portugal_primeira_liga"),
    (
        15314054,
        "lal-get-mala-2026-09-20-first-half-exact-score",
        "soccer_spain_la_liga",
    ),
    (15313991, "lal-val-rso-2026-09-20-first-half-exact-score", "soccer_spain_la_liga"),
    (15314029, "lal-vil-lev-2026-09-20-first-half-exact-score", "soccer_spain_la_liga"),
    (15317113, "es2-cor-cdt-2026-10-05", "soccer_spain_segunda_division"),
    (15316493, "es2-cas-ceu-2026-10-04", "soccer_spain_segunda_division"),
    (15315939, "es2-cad-leg-2026-10-03", "soccer_spain_segunda_division"),
    (15315940, "es2-alm-bur-2026-10-03", "soccer_spain_segunda_division"),
    (15315941, "es2-alb-eib-2026-10-03", "soccer_spain_segunda_division"),
    (15316491, "es2-rso-gra-2026-10-04", "soccer_spain_segunda_division"),
    (15316492, "es2-lpm-vld-2026-10-04", "soccer_spain_segunda_division"),
    (15313706, "uwcl-asr-fcb-2026-09-30", "soccer_uefa_champs_league"),
    (15315626, "u20wwc-ita-esp-2026-09-23", "soccer_uefa_nations_league"),
    (15313494, "unl-bul-est-2026-09-29", "soccer_uefa_nations_league"),
    (15314829, "vbeuro-ser2-bel2-2026-09-17", "soccer_uefa_nations_league"),
    (15314891, "unl-hun-geo-2026-10-02", "soccer_uefa_nations_league"),
    (15313495, "unl-lux-isl-2026-09-29", "soccer_uefa_nations_league"),
    (15314895, "unl-fra-ita-2026-10-02", "soccer_uefa_nations_league"),
    (15314898, "unl-lat-mon-2026-10-02", "soccer_uefa_nations_league"),
    (15314899, "unl-cyp-arm-2026-10-02", "soccer_uefa_nations_league"),
    (15313496, "unl-slv-mac-2026-09-29", "soccer_uefa_nations_league"),
    (15314061, "fif-lit-and-2026-09-30", "soccer_uefa_nations_league"),
    (15314505, "unl-mal-gib-2026-10-01", "soccer_uefa_nations_league"),
    (15314508, "unl-grc-nld-2026-10-01", "soccer_uefa_nations_league"),
    (15314509, "unl-ger-ser-2026-10-01", "soccer_uefa_nations_league"),
    (15314510, "unl-wal-nor-2026-10-01", "soccer_uefa_nations_league"),
    (15314511, "unl-den-prt-2026-10-01", "soccer_uefa_nations_league"),
    (15314512, "unl-isr-kvx-2026-10-01", "soccer_uefa_nations_league"),
    (15317150, "vbeuro-ger2-bul2-2026-09-19", "soccer_uefa_nations_league"),
    (15316005, "vbeuro-ita2-slo4-2026-09-17", "soccer_uefa_nations_league"),
    (15316006, "vbeuro-slo3-gre2-2026-09-17", "soccer_uefa_nations_league"),
    (15314830, "vbeuro-fin-gre2-2026-09-20", "soccer_uefa_nations_league"),
]

#: The 11 rows whose venue code names another competition, and the code.
CONTRADICTED = {
    15318598: "argcopa",  # Copa Argentina            -> Argentina Primera
    15316760: "col1",  # Colombia Primera A        -> Copa Sudamericana
    15317344: "clf",  # Club Friendlies           -> Bundesliga (specimen)
    15313706: "uwcl",  # UEFA Women's Champions Lg -> UEFA Champions League
    15315626: "u20wwc",  # FIFA U-20 Women's WC      -> UEFA Nations League
    15314829: "vbeuro",  # Volleyball European Champ -> UEFA Nations League
    15314061: "fif",  # FIFA Friendlies           -> UEFA Nations League
    15317150: "vbeuro",
    15316005: "vbeuro",
    15316006: "vbeuro",
    15314830: "vbeuro",
}


class TestTheCensus:
    def test_the_census_is_the_one_measured(self):
        assert len(PLACED_CENSUS) == 44
        assert len(CONTRADICTED) == 11
        assert set(CONTRADICTED) <= {row[0] for row in PLACED_CENSUS}

    @pytest.mark.parametrize("event_id,slug,league", PLACED_CENSUS)
    def test_each_placed_row_is_refused_exactly_when_the_venue_disagrees(
        self, event_id, slug, league
    ):
        refused = venue_refuses_placement({SLUG_FIELD: slug}, league)
        assert refused == CONTRADICTED.get(event_id), (event_id, slug, league)


class TestTheCode:
    @pytest.mark.parametrize(
        "slug,code",
        [
            ("clf-vfb-fch-2026-09-25", "clf"),
            ("clf-vfb-fch-2026-09-25-more-markets", "clf"),
            ("lal-get-mala-2026-09-20-first-half-exact-score", "lal"),
            ("vbeuro-ser2-bel2-2026-09-17", "vbeuro"),
            ("j2100-iwa-ven-2026-03-08", "j2100"),
            ("kor-dae1-gwa-2026-08-02-total-corners", "kor"),
            ("  BUN-MOE-MAI-2026-09-19  ", "bun"),
        ],
    )
    def test_a_game_slug_yields_its_league_code(self, slug, code):
        assert polymarket_league_code(slug) == code

    @pytest.mark.parametrize(
        "slug",
        [
            "bundesliga-2027-champion-202607081648403",
            "will-cristiano-ronaldo-announce-his-retirement",
            "liga-mx-2026-27-largest-goal-differential",
            "",
            None,
            12345,
        ],
    )
    def test_anything_that_is_not_a_game_slug_yields_nothing(self, slug):
        assert polymarket_league_code(slug) is None

    def test_a_code_is_a_whole_token_not_a_prefix(self):
        """`col` is the Conference League; `col1` is Colombia's league."""
        meta = {SLUG_FIELD: "col1-inm-mif-2026-08-11"}
        assert (
            venue_refuses_placement(meta, "soccer_uefa_europa_conference_league")
            == "col1"
        )
        meta = {SLUG_FIELD: "col-hjk-ael-2026-10-01"}
        assert (
            venue_refuses_placement(meta, "soccer_uefa_europa_conference_league")
            is None
        )


class TestItFailsOpenWithoutAnswers:
    @pytest.mark.parametrize(
        "meta",
        [
            None,
            {},
            {"polymarket_event_id": "1064052"},
            {SLUG_FIELD: "bundesliga-2027-champion"},
            "not a dict",
        ],
    )
    def test_no_code_refuses_nothing(self, meta):
        assert venue_refuses_placement(meta, "soccer_germany_bundesliga") is None

    @pytest.mark.parametrize(
        "league",
        [
            "baseball_npb",
            "icehockey_liiga",
            "basketball_euroleague",
            "",
            None,
        ],
    )
    def test_outside_soccer_the_venue_is_not_consulted(self, league):
        """62 non-soccer placements, 0 contradictions: nothing to buy there."""
        meta = {SLUG_FIELD: "clf-vfb-fch-2026-09-25"}
        assert venue_refuses_placement(meta, league) is None

    def test_an_unmapped_soccer_league_is_refused_when_the_venue_names_another(self):
        meta = {SLUG_FIELD: "clf-bay-fca-2026-09-25"}
        assert venue_refuses_placement(meta, "soccer_germany_liga3") == "clf"


class TestTheMap:
    def test_every_key_is_a_soccer_league(self):
        assert POLYMARKET_LEAGUE_CODES
        assert all(k.startswith("soccer_") for k in POLYMARKET_LEAGUE_CODES)
        assert not any(k.endswith("_other") for k in POLYMARKET_LEAGUE_CODES)

    def test_every_code_is_a_bare_lowercase_token(self):
        for codes in POLYMARKET_LEAGUE_CODES.values():
            assert codes
            for code in codes:
                assert code == code.lower() and code.isalnum(), code

    def test_no_code_names_two_leagues_except_qualifying_rounds(self):
        owners: dict[str, set[str]] = {}
        for league, codes in POLYMARKET_LEAGUE_CODES.items():
            for code in codes:
                owners.setdefault(code, set()).add(league)
        shared = {c: o for c, o in owners.items() if len(o) > 1}
        assert shared == {
            "ucl": {
                "soccer_uefa_champs_league",
                "soccer_uefa_champs_league_qualification",
            }
        }

    def test_friendlies_are_no_league(self):
        every_code = set().union(*POLYMARKET_LEAGUE_CODES.values())
        assert not {"clf", "fif"} & every_code


# ═══ The create flow, where the answer becomes the row's competition ═════════


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


BUNDESLIGA_FIXTURES = [
    _utc("2026-09-12 13:30:00"),
    _utc("2026-09-19 13:30:00"),
    _utc("2026-10-03 13:30:00"),
]
KICKOFF = _utc("2026-09-25 14:30:00")


class _Market:
    def __init__(self, metadata):
        self.source = "polymarket"
        self.external_id = "0x8636"
        self.name = "VfB Stuttgart vs. 1. FC Heidenheim"
        self.commence_time = KICKOFF
        self.llm_sport_category = None
        self.market_metadata = metadata
        self.event_id = None


class _Matchup:
    def __init__(self):
        self.team_a = "VfB Stuttgart"
        self.team_b = "1. FC Heidenheim"
        self.yes_team = self.team_a
        self.format_type = "vs"


class _Created:
    def __init__(self):
        self.identity = None

    async def __call__(self, session, identity, *args, **kwargs):
        self.identity = identity
        return type("E", (), {"id": 999, "sport_id": 1})(), True


async def _none():
    return None


async def _value(value):
    return value


async def _drive(monkeypatch, metadata):
    """The real create flow; only the club resolver and coverage are faked."""
    created = _Created()
    monkeypatch.setattr(
        pmm,
        "_polymarket_container_sibling_event_id",
        lambda session, market: _none(),
    )
    monkeypatch.setattr(
        pmm,
        "covered_league_for_matchup",
        lambda session, a, b: _none(),
    )
    monkeypatch.setattr(
        pmm,
        "placeable_league_for_matchup",
        lambda session, a, b, sport_key: _value("soccer_germany_bundesliga"),
    )
    monkeypatch.setattr(
        pmm, "auto_create_sport_key_from_category", lambda category: "soccer_other"
    )
    monkeypatch.setattr(event_registry, "find_or_create_event", created)
    session = PredicateSession(
        [
            ScheduleRow("soccer_germany_bundesliga", when, "odds_api")
            for when in BUNDESLIGA_FIXTURES
        ]
    )
    await pmm._create_event_from_prediction_market(
        session, _Matchup(), _Market(metadata), KICKOFF
    )
    assert (
        created.identity is not None
    ), "the create flow returned before the registry — this measured nothing"
    return created.identity.sport_key


class TestTheCreateFlow:
    @pytest.mark.asyncio
    async def test_the_club_friendly_stays_on_the_catch_all(self, monkeypatch):
        key = await _drive(
            monkeypatch, {SLUG_FIELD: "clf-vfb-fch-2026-09-25"}
        )
        assert key == "soccer_other"

    @pytest.mark.asyncio
    async def test_a_bundesliga_game_is_still_placed(self, monkeypatch):
        """The control: the same clubs, the venue's Bundesliga code."""
        key = await _drive(
            monkeypatch, {SLUG_FIELD: "bun-vfb-fch-2026-09-25"}
        )
        assert key == "soccer_germany_bundesliga"

    @pytest.mark.asyncio
    async def test_a_row_without_a_slug_is_placed_as_before(self, monkeypatch):
        key = await _drive(monkeypatch, {})
        assert key == "soccer_germany_bundesliga"


# ═══ The ingest: both rows the create flow can read carry the slug ═══════════


class TestTheIngestStamp:
    def test_the_sub_market_row_carries_the_slug(self):
        meta = sub_market_metadata(
            event_id="1064052",
            matchup_title=None,
            event_slug="clf-vfb-fch-2026-09-25-more-markets",
        )
        assert meta[SLUG_FIELD] == "clf-vfb-fch-2026-09-25-more-markets"
        assert venue_refuses_placement(meta, "soccer_germany_bundesliga") == "clf"

    @pytest.mark.parametrize("absent", [None, ""])
    def test_no_slug_stamps_nothing(self, absent):
        meta = sub_market_metadata(
            event_id="1064052",
            matchup_title=None,
            event_slug=absent,
        )
        assert SLUG_FIELD not in meta

    def test_the_ingest_loop_passes_the_event_slug_to_every_sub_market(self):
        from app.tasks import polymarket as poly_mod

        tree = ast.parse(inspect.getsource(poly_mod))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "sub_market_metadata"
        ]
        assert calls, "no call to sub_market_metadata — this guard reads nothing"
        for call in calls:
            kwargs = {k.arg: k.value for k in call.keywords if k.arg}
            value = kwargs.get("event_slug")
            assert (
                isinstance(value, ast.Attribute) and value.attr == "slug"
            ), "the sub-market ingest does not stamp the venue slug (#8636)"

    def test_the_parent_row_stamps_the_slug(self):
        """`poly_metadata[POLYMARKET_EVENT_SLUG_KEY] = event.slug` exists."""
        from app.tasks import polymarket as poly_mod

        tree = ast.parse(inspect.getsource(poly_mod))
        writes = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Subscript)
            and isinstance(n.targets[0].value, ast.Name)
            and n.targets[0].value.id == "poly_metadata"
            and isinstance(n.targets[0].slice, ast.Name)
            and n.targets[0].slice.id == "POLYMARKET_EVENT_SLUG_KEY"
        ]
        assert len(writes) == 1
        value = writes[0].value
        assert isinstance(value, ast.Attribute) and value.attr == "slug"
