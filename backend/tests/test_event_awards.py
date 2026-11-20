"""L2-87 (B6): awards adapter pure helpers — proves the "config drop" grammar over
the real KX award ticker/name shapes (verified live 2026-07-12). The adapter's
build_event is exercised via the route test (test_route_event_concept.py)."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_awards import (
    CEREMONIES,
    AwardsEventAdapter,
    ceremony_end_date,
    classify_market,
    clean_category_label,
    derive_awards_concept,
    edition_year,
    parse_awards_slug,
)


class TestParseAwardsSlug:
    def test_bare_ceremony(self):
        cfg, yr = parse_awards_slug("oscars")
        assert cfg is not None and cfg.slug == "oscars"
        assert yr is None

    def test_four_digit_year(self):
        cfg, yr = parse_awards_slug("oscars-2027")
        assert cfg.slug == "oscars"
        assert yr == 27

    def test_two_digit_year(self):
        cfg, yr = parse_awards_slug("emmys-26")
        assert cfg.slug == "emmys"
        assert yr == 26

    def test_aliases_resolve(self):
        assert parse_awards_slug("academy-awards-2027")[0].slug == "oscars"
        assert parse_awards_slug("tony-awards")[0].slug == "tonys"
        assert parse_awards_slug("grammy")[0].slug == "grammys"

    def test_unknown_ceremony_is_none(self):
        cfg, yr = parse_awards_slug("golden-globes")
        assert cfg is None

    def test_empty(self):
        assert parse_awards_slug("") == (None, None)


class TestEditionYear:
    def test_ticker_year_token(self):
        assert edition_year("KXOSCARPIC-27") == 27
        assert edition_year("kalshi:KXOSCARPIC-26") == 26

    def test_emmy_date_token(self):
        # KXEMMYDSERIES-26SEP14 -> first -NN is the edition year, not the day.
        assert edition_year("KXEMMYDSERIES-26SEP14") == 26
        assert edition_year("KXEMMYNOMS-26-DS") == 26

    def test_tony_embedded(self):
        assert edition_year("KXTONYAWARDS-26BM") == 26

    def test_falls_back_to_resolution_date(self):
        # Grammy tickers carry no year token.
        rd = datetime(2027, 11, 1, tzinfo=timezone.utc)
        assert edition_year("KXGRAMAOTY", rd) == 27
        assert edition_year("KXGRAMAOTY", None) is None

    def test_implausible_ticker_token_is_not_a_year(self):
        # KXGRAMAOTY-69 ends in a Kalshi series id (69), NOT a 2069 edition — must
        # fall back to the resolution date (2027), never yield "The Grammys 2069".
        rd = datetime(2027, 12, 31, tzinfo=timezone.utc)
        assert edition_year("KXGRAMAOTY-69", rd) == 27
        assert edition_year("KXGRAMMYNOMAOTY-69", rd) == 27


class TestCeremonyEndDate:
    """A resolution date is a deadline; only sometimes is it a schedule. The four
    instants below are the ones production actually served on 2026-09-01."""

    def test_year_end_backstop_is_not_published(self):
        # Oscars 2027, Grammys 2027 and Tonys 2026 all carried this SAME instant —
        # a default, not three ceremonies that happen to fall on New Year's Eve.
        for year in (2026, 2027):
            rd = datetime(year, 12, 31, 15, 0, tzinfo=timezone.utc)
            assert ceremony_end_date(rd) is None

    def test_a_real_ceremony_date_survives(self):
        # THE CONTROL. The Emmys publish a genuine date and it must still reach the
        # page — without this arm the suppression above passes on a function that
        # returns None for everything.
        rd = datetime(2027, 9, 14, 14, 0, tzinfo=timezone.utc)
        assert ceremony_end_date(rd) == rd.isoformat()

    def test_missing_and_malformed_dates_are_absent_not_fatal(self):
        assert ceremony_end_date(None) is None
        assert ceremony_end_date("2027-12-31") is None

    async def test_the_backstop_is_not_a_ceremony_completion_signal(self):
        # #5349 replaces the obsolete deadline-derived status assumption with
        # the actual build_event negative, preserving date suppression coverage.
        past = datetime(2020, 12, 31, 15, 0, tzinfo=timezone.utc)
        assert ceremony_end_date(past) is None
        category = _category(
            1, "Oscar winner: Best Picture", "KXOSCARPIC-20", deadline=past
        )
        body = await _build([category], "oscars-2020")
        assert body["event"]["status"] == "unknown"
        assert body["event"]["end_date"] is None
        assert body["children"][0]["settled"] is False


class TestClassifyMarket:
    def test_winner_categories(self):
        assert classify_market("KXOSCARPIC-27", "Oscar winner: Best Picture") == "category"
        assert classify_market("KXOSCARPIC-26", "Oscar for Best Picture?") == "category"
        assert classify_market("KXEMMYDSERIES-26SEP14", "Emmy Award for Drama Series") == "category"
        assert classify_market("KXTONYAWARDS-26BM", "Tony Award for Best Musical?") == "category"
        assert classify_market("KXGRAMAOTY", "Grammy winner: Album of the Year") == "category"

    def test_nominations(self):
        assert classify_market("KXOSCARNOMPIC-27", "Oscar nominations for Best Picture?") == "nominations"
        assert classify_market("KXEMMYNOMS-26-DS", "Emmy Nominations: Outstanding Drama Series") == "nominations"
        assert classify_market("KXGRAMMYNOMAOTY", "2026 Grammy nominations for Album of the Year") == "nominations"

    def test_nominated_question_is_a_nomination_not_its_best_category(self):
        # #11336: "nominated" names no "nomination"/"nominee", and "Best" made this a
        # winner category.
        q = "Will Julianne Moore be nominated for Best Actress at the 99th Academy Awards?"
        assert classify_market("pm-1", q) == "nominations"
        assert classify_market(None, "Who will get nominated for Best Director?") == "nominations"
        assert classify_market(None, "Will Dune: Part Three be nominated?") == "nominations"
        assert classify_market(None, "Nominated for Best Picture: Wicked?") == "nominations"
        assert classify_market(None, "Will Wicked be Oscar-nominated for Best Picture?") == "nominations"

    def test_adjectival_nominated_in_a_winner_question_stays_a_category(self):
        assert classify_market(None, "Will a nominated film win Best Picture?") == "category"
        assert classify_market(None, "Will the most-nominated film win Best Picture?") == "category"
        assert classify_market(None, "Best dollar-denominated box office?") == "category"
        assert classify_market(None, "Will the most nominated film sweep?") == "novelty"
        # Post-noun "nominated for" describes the film; the question is still who wins.
        assert classify_market(
            None, "Will a film nominated for Best Picture win Best Director?") == "category"
        # A "that/which" relative clause also describes the film (#11336 root control).
        assert classify_market(
            None, "Will a film that is nominated for 10+ Oscars win Best Picture?") == "category"
        assert classify_market(
            None, "Will the film which got nominated for Best Picture win?") == "category"
        # A real nomination question beside a relative clause is still a nomination.
        assert classify_market(
            None, "Will the film that won Cannes be nominated for Best Picture?") == "nominations"

    def test_novelty(self):
        assert classify_market("KXOSCARGUESTS-26", "Who will attend the Oscars?") == "novelty"
        assert classify_market("KXMOSTWINSOSCARS", "Most Oscar wins?") == "novelty"


class TestCleanCategoryLabel:
    def test_strips_ceremony_boilerplate(self):
        assert clean_category_label("Oscar winner: Best Picture") == "Best Picture"
        assert clean_category_label("Oscar for Best Director?") == "Best Director"
        assert clean_category_label("Emmy Award for Drama Series") == "Drama Series"
        assert clean_category_label("Tony Award for Best Play?") == "Best Play"
        assert clean_category_label("Grammy winner: Album of the Year") == "Album of the Year"

    def test_strips_leading_year(self):
        assert clean_category_label("2026 Oscar for Best Music (Original Score)?") == "Best Music (Original Score)"

    def test_empty_falls_back(self):
        assert clean_category_label("") == ""


class TestDeriveAwardsConcept:
    """L2-88: the discovery-entry helper for search/typeahead + futures breadcrumb.
    Maps a matched awards MARKET to its bare ceremony concept key."""

    def test_ticker_stem_wins(self):
        assert derive_awards_concept("KXOSCARPIC-27", "anything")["key"] == "event:awards:oscars"
        assert derive_awards_concept("KXEMMYDSERIES-26SEP14", "x")["key"] == "event:awards:emmys"
        assert derive_awards_concept("KXTONYAWARDS-26BM", "x")["key"] == "event:awards:tonys"
        assert derive_awards_concept("KXGRAMAOTY-69", "x")["key"] == "event:awards:grammys"

    def test_bare_key_no_edition(self):
        # Bare slug → the adapter resolves to the latest rich edition (never a dead link).
        c = derive_awards_concept("kalshi:KXOSCARDIR-26", "Oscar for Best Director?")
        assert c["key"] == "event:awards:oscars"
        assert c["domain"] == "awards"
        assert c["name"] == "The Oscars"

    def test_name_fallback_when_no_ticker(self):
        assert derive_awards_concept(None, "Oscar winner: Best Picture")["key"] == "event:awards:oscars"
        assert derive_awards_concept("", "Emmy Award for Drama Series")["key"] == "event:awards:emmys"
        assert derive_awards_concept(None, "Tony Award for Best Play?")["key"] == "event:awards:tonys"

    def test_non_awards_is_none(self):
        assert derive_awards_concept("KXPGATOUR-GESO26", "Genesis Scottish Open Winner") is None
        assert derive_awards_concept(None, "2026 Men's Wimbledon Winner") is None
        assert derive_awards_concept(None, None) is None

    def test_sports_emmy_ticker_excluded(self):
        # KXEMMY is not a substring of KXSPORTSEMMY → the ticker path never
        # miscategorizes the Sports Emmys as the (TV) Emmys.
        assert derive_awards_concept("KXSPORTSEMMY-26", "Sports Broadcasting Award") is None


class TestCeremoniesConfig:
    def test_all_ceremonies_have_marquee(self):
        for cfg in CEREMONIES.values():
            assert cfg.marquee_re is not None
            assert cfg.ticker.startswith("KX")

    def test_emmy_ticker_excludes_sports_emmy(self):
        # KXEMMY is not a substring of KXSPORTSEMMY, so the Sports Emmys are excluded.
        assert "KXEMMY" not in "KXSPORTSEMMY"


# #5349: source-only replay of independent category announcements. Synthetic
# specimens are not ceremony-roster, calendar, provider or production acceptance.
def _category(id_, name, ticker, *, status="open", outcomes=None, deadline=None):
    return SimpleNamespace(
        id=id_,
        name=name,
        external_id=ticker,
        status=status,
        source="kalshi",
        resolution_date=deadline,
        outcomes=[
            SimpleNamespace(
                name=name,
                current_probability=probability,
                is_winner=won,
                # #5349: a winner in these specimens is the venue's own settlement,
                # as on the 2026 Emmys (`api_settlement`). A grade from any other
                # source is covered in test_awards_result_authority_5349.py.
                resolution_source="api_settlement" if won else None,
                last_updated=None,
            )
            for name, probability, won in (
                outcomes or [("Favorite", 0.55, False), ("Other nominee", 0.45, False)]
            )
        ],
    )


class _AwardsResult:
    def __init__(self, markets):
        self.markets = markets

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self.markets


class _AwardsDB:
    def __init__(self, markets):
        self.markets = markets
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        return _AwardsResult(self.markets)


async def _build(markets, slug="oscars-2027"):
    return await AwardsEventAdapter().build_event(slug, _AwardsDB(markets))


@pytest.mark.parametrize(
    "slug,tickers,names",
    [
        (
            "oscars-2027",
            ("KXOSCARPIC-27", "KXOSCARDIR-27"),
            ("Oscar winner: Best Picture", "Oscar winner: Best Director"),
        ),
        (
            "emmys-2028",
            ("KXEMMYDSERIES-28", "KXEMMYCOMEDY-28"),
            ("Emmy Award for Drama Series", "Emmy Award for Comedy Series"),
        ),
        # Held-out edition: same source/config, no calendar or edition declaration.
        (
            "oscars-2038",
            ("KXOSCARPIC-38", "KXOSCARDIR-38"),
            ("Oscar winner: Best Picture", "Oscar winner: Best Director"),
        ),
    ],
)
async def test_announced_marquee_never_settles_an_unannounced_category(
    slug, tickers, names
):
    marquee = _category(
        1,
        names[0],
        tickers[0],
        outcomes=[("Actual winner", 0.51, True), ("Runner up", 0.49, False)],
    )
    sibling = _category(2, names[1], tickers[1])
    body = await _build([marquee, sibling], slug)
    children = {c["market_id"]: c for c in body["children"]}
    assert children[1]["settled"] is True
    assert children[1]["graded_winner"] == "Actual winner"
    assert children[2]["settled"] is False
    assert children[2]["graded_winner"] is None
    assert body["event"]["status"] == "unknown"
    assert [c["name"] for c in body["primary"]["competitors"] if c["won"]] == [
        "Actual winner"
    ]


async def test_independent_non_marquee_result_does_not_settle_marquee():
    marquee = _category(1, "Oscar winner: Best Picture", "KXOSCARPIC-27")
    sibling = _category(
        2,
        "Oscar winner: Best Director",
        "KXOSCARDIR-27",
        outcomes=[("Director", None, True), ("Other director", 0.5, False)],
    )
    body = await _build([marquee, sibling])
    children = {c["market_id"]: c for c in body["children"]}
    assert children[1]["settled"] is False
    assert children[2]["settled"] is True and children[2]["graded_winner"] == "Director"
    assert body["event"]["status"] == "unknown"


async def test_nomination_grade_preserves_roster_but_does_not_announce_category_winner():
    categories = [
        _category(1, "Oscar winner: Best Picture", "KXOSCARPIC-27"),
        _category(2, "Oscar winner: Best Director", "KXOSCARDIR-27"),
    ]
    nominations = _category(
        3,
        "Oscar nominations for Best Picture?",
        "KXOSCARNOMPIC-27",
        outcomes=[("Nominee", 0.99, True), ("Other nominee", 0.7, True)],
    )
    novelty = _category(4, "Who will attend the Oscars?", "KXOSCARGUESTS-27")
    wrong_edition = _category(
        5,
        "Oscar winner: Best Actor",
        "KXOSCARACTOR-26",
        outcomes=[("Prior winner", 1.0, True), ("Prior runner", 0.0, False)],
    )
    body = await _build(categories + [nominations, novelty, wrong_edition])
    children = {c["market_id"]: c for c in body["children"]}
    assert set(children) == {1, 2, 3, 4}
    assert children[1]["settled"] is False and children[2]["settled"] is False
    assert children[3]["settled"] is True and children[3]["prop_type"] == "nominations"
    assert (
        children[3]["graded_winner"] is None
    )  # Multiple nomination results are not one award winner.
    assert all(o["won"] for o in children[3]["outcomes"])
    assert children[4]["prop_type"] == "occurrence" and children[4]["settled"] is False
    assert body["sections"] == [
        {"type": "categories", "label": "Categories", "market_ids": [1, 2]},
        {"type": "props", "label": "Nominations & props", "market_ids": [3, 4]},
    ]
    assert body["event"]["status"] == "unknown"


async def test_price_extreme_and_past_placeholder_never_complete_or_crown():
    category = _category(
        1,
        "Oscar winner: Best Picture",
        "KXOSCARPIC-20",
        deadline=datetime(2020, 12, 31, tzinfo=timezone.utc),
        outcomes=[("Favorite", 0.99, False), ("Long shot", 0.01, False)],
    )
    body = await _build([category], "oscars-2020")
    assert body["event"]["status"] == "unknown" and body["event"]["end_date"] is None
    assert (
        body["children"][0]["settled"] is False
        and body["children"][0]["graded_winner"] is None
    )
    assert not any(c["won"] for c in body["primary"]["competitors"])


@pytest.mark.parametrize("status", ["closed", "resolved", "settled"])
async def test_own_assigned_category_without_grade_stays_resolved_result_unknown(
    status,
):
    category = _category(
        1,
        "Oscar winner: Best Picture",
        "KXOSCARPIC-27",
        status=status,
        outcomes=[("Favorite", 0.99, False), ("Long shot", 0.01, False)],
    )
    sibling = _category(2, "Oscar winner: Best Director", "KXOSCARDIR-27")
    body = await _build([category, sibling])
    children = {c["market_id"]: c for c in body["children"]}
    assert children[1]["settled"] is True and children[1]["graded_winner"] is None
    assert not any(c["won"] for c in children[1]["outcomes"])
    assert children[2]["settled"] is False and body["event"]["status"] == "unknown"
    assert not any(c["won"] for c in body["primary"]["competitors"])


@pytest.mark.parametrize("winner_name", ["Actual low-priced winner", "Other"])
async def test_authoritative_winner_outside_preview_survives_child_and_marquee(
    winner_name,
):
    nominees = [(f"Unannounced nominee {i}", 0.8 - i / 100, False) for i in range(45)]
    category = _category(
        1,
        "Oscar winner: Best Picture",
        "KXOSCARPIC-27",
        outcomes=nominees + [(winner_name, None, True)],
    )
    body = await _build([category])
    child = body["children"][0]
    assert child["settled"] is True and child["graded_winner"] == winner_name
    assert [o["name"] for o in child["outcomes"] if o["won"]] == [winner_name]
    assert [o["name"] for o in body["primary"]["competitors"] if o["won"]] == [
        winner_name
    ]
    assert child["outcomes"][-1]["probability"] is None
    assert body["event"]["status"] == "unknown"


async def test_every_known_category_resolved_is_not_a_full_ceremony_signal():
    body = await _build(
        [
            _category(
                1, "Oscar winner: Best Picture", "KXOSCARPIC-27", status="resolved"
            ),
            _category(
                2, "Oscar winner: Best Director", "KXOSCARDIR-27", status="closed"
            ),
        ]
    )
    assert all(c["settled"] for c in body["children"])
    assert all(c["graded_winner"] is None for c in body["children"])
    assert body["event"]["status"] == "unknown"


async def test_wrong_edition_remains_absent_and_ceremony_identity_independent():
    markets = [
        _category(1, "Oscar winner: Best Picture", "KXOSCARPIC-27"),
        _category(
            2,
            "Oscar winner: Best Picture",
            "KXOSCARPIC-26",
            outcomes=[("Previous winner", 1.0, True), ("Previous runner", 0.0, False)],
        ),
    ]
    current = await _build(markets)
    previous = await _build(markets, "oscars-2026")
    assert current["event"]["key"] != previous["event"]["key"]
    assert [c["market_id"] for c in current["children"]] == [1]
    assert [c["market_id"] for c in previous["children"]] == [2]
    assert current["children"][0]["settled"] is False
    assert await _build(markets, "oscars-2025") is None
    assert await _build(markets, "golden-globes") is None
