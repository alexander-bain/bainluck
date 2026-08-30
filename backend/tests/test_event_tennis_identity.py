"""UX-P066 / #1793 — the tennis adapter served the WRONG tournament.

`event:tennis:us-open-2026` — the concept key `majors_calendar.yaml` declares for
the US Open, marquee, starting 2026-08-24 — served **"Cincinnati Open: Winner"**
in production on 2026-08-12, with a real 78-player field and nothing to tell a
reader it was the wrong tournament. Serving the wrong tournament is worse than
serving nothing: absence is legible, a confident wrong answer is not.

Two independent defects produced one symptom, and they need different fixes:

1. **Identity was unrepresentable.** Resolution matched on `tournament_tokens`,
   which drops tokens shorter than 4 characters. `us` is two. So
   `tournament_tokens("US Open Men's Singles Winner") == {"open"}` — identical to
   Cincinnati Open, French Open and Australian Open. Matching is a SUBSET test, so
   a slug with fewer tokens matches MORE tournaments: degrading the slug widened
   the blast radius. `_rank` then picked the richest, and Cincinnati's draw was
   bigger than the US Open's.

2. **A novelty prop could be a tournament's field.** `is_winner_market` matches
   `to win`, so "Serena and Venus Williams to win Wimbledon Doubles this year"
   was eligible to BE Wimbledon's primary — and `/hub/tennis` linked "Serena
   Williams to Win a Tournament in 2026" as though it were a tournament.

The corpus in `tests/fixtures/tennis_production_corpus.json` is the real
production market set, measured the same day.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_tennis import (
    _MIN_FIELD_OUTCOMES,
    _TENNIS_STOPWORDS,
    _TOUR_TIER_TOKENS,
    TennisEventAdapter,
    canonical_slug_tokens,
    canonical_tokens,
    is_winner_field,
    is_winner_market,
    list_tennis_tournament_concepts,
    select_winner_field,
    tennis_gender,
    tennis_is_major,
    tournament_tokens,
)
from app.utils.name_normalization import clean_slug

_FIXTURE = (
    pathlib.Path(__file__).parent / "fixtures" / "tennis_production_corpus.json"
)
CORPUS = json.loads(_FIXTURE.read_text())["markets"]


def _markets(rows=None):
    return [
        SimpleNamespace(
            name=r["name"],
            id=r["id"],
            volume_24h=r["volume_24h"],
            _n=r["real_outcome_count"] or 0,
        )
        for r in (rows if rows is not None else CORPUS)
    ]


def _count(m):
    return m._n


def _resolve(slug, rows=None):
    w = select_winner_field(_markets(rows), slug, _count)
    return w.name if w else None


def _markets_with_outcomes(rows):
    """Corpus rows as market-shaped objects carrying real `outcomes`, so the hub
    rail's own `_real_count` (which reads `m.outcomes`) sees the measured count."""
    out = []
    for r in rows:
        n = r["real_outcome_count"] or 0
        out.append(
            SimpleNamespace(
                name=r["name"],
                id=r["id"],
                volume_24h=r["volume_24h"],
                status=r["status"],
                resolution_date=r.get("resolution_date"),
                outcomes=[SimpleNamespace(name=f"Player {i}") for i in range(n)],
            )
        )
    return out


class _Result:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    def __init__(self, items):
        self._items = items

    async def execute(self, *a, **k):
        return _Result(self._items)


# ---------------------------------------------------------------------------
# 1. The identity token space
# ---------------------------------------------------------------------------
class TestCanonicalTokens:
    def test_us_survives_and_that_is_the_whole_bug(self):
        # The two-character token IS the identity of the US Open.
        assert canonical_tokens("US Open Men's Singles Winner") == {"us", "open"}
        assert canonical_slug_tokens("us-open-2026") == {"us", "open"}

    def test_us_open_is_now_distinguishable_from_every_other_open(self):
        us = canonical_tokens("US Open Men's Singles Winner")
        cincy = canonical_tokens("Cincinnati Open: Winner")
        assert us != cincy
        # and neither is a subset of the other, so neither can claim the other
        assert not us <= cincy
        assert not cincy <= us

    def test_the_old_token_space_could_not_tell_them_apart(self):
        # Kept as the regression's epitaph: this is what production did.
        assert tournament_tokens("US Open Men's Singles Winner") == {"open"}
        assert tournament_tokens("Cincinnati Open: Winner") == {"cincinnati", "open"}
        assert tournament_tokens("US Open Men's Singles Winner") <= tournament_tokens(
            "Cincinnati Open: Winner"
        )

    def test_stopwords_still_apply(self):
        assert "2026" not in canonical_tokens("2026 Women's US Open Winner (Tennis)")
        assert "winner" not in canonical_tokens("WTA Prague Winner")
        assert "wta" not in canonical_tokens("WTA Prague Winner")


class TestTournamentTokensIsNotWidened:
    """GUARDRAIL. `tournament_tokens` is the CHILD-association function. Widening
    it to fix a resolution bug would change which props fold into every tennis
    event — a blast radius this fix does not need and did not measure."""

    def test_child_association_token_space_still_drops_short_tokens(self):
        assert tournament_tokens("US Open Winner") == {"open"}
        assert "us" not in tournament_tokens("US Open Winner")

    def test_the_two_token_spaces_are_genuinely_different_functions(self):
        assert canonical_tokens("US Open Winner") != tournament_tokens("US Open Winner")


# ---------------------------------------------------------------------------
# 2. A winner FIELD is a field
# ---------------------------------------------------------------------------
class TestWinnerField:
    def test_one_outcome_is_a_prop_not_a_field(self):
        assert is_winner_market("Serena Williams to Win a Tournament in 2026") is True
        assert is_winner_field("Serena Williams to Win a Tournament in 2026", 1) is False

    def test_two_competitors_is_the_minimum_field(self):
        assert _MIN_FIELD_OUTCOMES == 2
        assert is_winner_field("WTA Prague Winner", 2) is True
        assert is_winner_field("WTA Prague Winner", 1) is False

    def test_the_threshold_clears_every_real_field_in_the_corpus(self):
        """Measured margin, not a guess: real fields run 4..89, props are 1."""
        real = [
            m["real_outcome_count"]
            for m in CORPUS
            if is_winner_market(m["name"]) and m["real_outcome_count"] > 1
        ]
        props = [
            m["real_outcome_count"]
            for m in CORPUS
            if is_winner_market(m["name"]) and m["real_outcome_count"] <= 1
        ]
        assert min(real) >= 4, "a real tournament field dropped below the floor"
        assert props and max(props) == 1
        assert _MIN_FIELD_OUTCOMES <= min(real)

    def test_a_matchup_is_still_never_a_field(self):
        assert is_winner_field("Gauff vs Sabalenka: Set 1 Winner", 2) is False


# ---------------------------------------------------------------------------
# 3. The named specimens from #1793
# ---------------------------------------------------------------------------
class TestSpecimens:
    @pytest.mark.parametrize("slug", ["us-open-2026", "us-open"])
    def test_us_open_never_serves_cincinnati(self, slug):
        got = _resolve(slug)
        assert got is not None, f"{slug} must resolve — the US Open's fields exist"
        assert "Cincinnati" not in got
        assert "US Open" in got

    @pytest.mark.parametrize("slug", ["wimbledon", "wimbledon-2026"])
    def test_wimbledon_never_serves_a_doubles_novelty(self, slug):
        got = _resolve(slug)
        # Wimbledon's real fields have aged out of the resolved window, so 404 is
        # the correct answer here. What is NOT acceptable is the novelty prop.
        assert got is None or "Doubles" not in got

    def test_a_slug_that_names_nothing_404s(self):
        assert _resolve("zzqqxx-does-not-exist-9999") is None
        # ...including one whose only surviving token was generic. This is the
        # probe that first exposed the class: "tournament" matched a Serena prop.
        assert _resolve("not-a-tournament-zzq") is None

    def test_cincinnati_still_serves_cincinnati(self):
        """Both directions (gotcha #43): the fix must not un-resolve the
        tournament that was wrongly winning."""
        assert _resolve("cincinnati-open") == "Cincinnati Open: Winner"


class TestTheFieldFloorGuardsInferenceNotARequest:
    """The floor applies to a SUBSET match (the resolver inferring that a market
    represents the tournament a slug named) and NOT to an EXACT match (the caller
    naming that market directly).

    This is not a softening — it is what keeps the fix from creating the very
    thing it is meant to prevent. Search, typeahead and concept-links all emit
    `event:tennis:{clean_slug(name)}` for any winner market, and production really
    does return `event:tennis:serena-williams-to-win-a-tournament-in-2026` for the
    query "serena" (measured 2026-08-12). Refusing exact matches would convert a
    wrong page into a DEAD link, which is a broken shelf, not a repair.
    """

    def test_a_novelty_prop_still_serves_its_OWN_page(self):
        slug = "serena-williams-to-win-a-tournament-in-2026"
        assert _resolve(slug) == "Serena Williams to Win a Tournament in 2026"

    def test_but_it_can_never_stand_in_for_a_tournament(self):
        # Same market, reached by inference instead of by name.
        assert _resolve("wimbledon-2026") is None
        assert _resolve("not-a-tournament-zzq") is None

    def test_every_link_search_can_emit_still_resolves(self):
        """The emitters key on `is_winner_market` + `clean_slug`, so every winner
        market in the corpus is a link they can produce. None may 404."""
        dead = []
        for m in CORPUS:
            if not is_winner_market(m["name"]):
                continue
            slug = clean_slug(m["name"])
            if _resolve(slug) is None:
                dead.append(slug)
        assert not dead, f"slugs search/typeahead can emit that now 404: {dead}"


class TestAliasConvergenceSurvives:
    """L2-65 Item 2 is deliberate and must not be collateral damage: a bare or
    differently-named-per-source slug lands on the RICHEST field of the SAME
    tournament. Ambiguity across sources is a feature; ambiguity across
    tournaments is the bug."""

    @pytest.mark.parametrize(
        "slug,expected",
        [
            ("toronto", "WTA 1000 Toronto: Winner"),
            ("wta-toronto-winner", "WTA 1000 Toronto: Winner"),
            ("montreal", "ATP 1000 Montreal: Winner"),
            ("atp-montreal-winner", "ATP 1000 Montreal: Winner"),
        ],
    )
    def test_bare_and_alias_slugs_still_converge_on_the_richest_field(self, slug, expected):
        assert _resolve(slug) == expected

    def test_a_gendered_slug_still_never_crosses_genders(self):
        got = _resolve("us-open-men-s-singles-winner")
        assert got is not None
        assert tennis_gender(got) != "women"


# ---------------------------------------------------------------------------
# 4. THE ORACLE — acceptance 4. Every slug the system can emit.
# ---------------------------------------------------------------------------
class TestOracleOverTheRealCorpus:
    """When the change is a repair, unchanged output on real payloads IS the
    acceptance. Every slug derivable from the real corpus is replayed; the ONLY
    permitted changes are the enumerated repairs."""

    # slug -> the tournament it must resolve to (None = must 404), for every
    # slug the corpus can produce. Derived from the measured before/after and
    # adjudicated one by one.
    REPAIRED = {
        # was Cincinnati Open — the wrong tournament entirely
        "us-open-2026": "2026 Women’s US Open Winner (Tennis)",
        "us-open": "2026 Women’s US Open Winner (Tennis)",
        "us-open-men-s-singles-winner": "US Open Men's Singles Winner",
        "us-open-women-s-singles-winner": "2026 Women’s US Open Winner (Tennis)",
        "2026-men-s-us-open-winner-tennis": "US Open Men's Singles Winner",
        "2026-women-s-us-open-winner-tennis": "2026 Women’s US Open Winner (Tennis)",
        # was a novelty prop standing in for a tournament
        "wimbledon-2026": None,
        "wimbledon": None,
        "not-a-tournament-zzq": None,
    }

    def _all_slugs(self):
        return sorted(
            {clean_slug(m["name"]) for m in CORPUS if is_winner_market(m["name"])}
            | set(self.REPAIRED)
        )

    def test_every_tournament_slug_resolves_to_its_own_tournament(self):
        """The heart of it: a slug built from a real field's own name must come
        back to that same tournament, for all 26 of them."""
        wrong = []
        for m in CORPUS:
            if not is_winner_field(m["name"], m["real_outcome_count"] or 0):
                continue
            slug = clean_slug(m["name"])
            got = _resolve(slug)
            if got is None:
                wrong.append((slug, m["name"], "404"))
                continue
            # It may converge on a RICHER field, but it must be the same
            # tournament — i.e. the winner's identity tokens must cover the
            # slug's.
            if not canonical_slug_tokens(slug) <= canonical_tokens(got):
                wrong.append((slug, m["name"], got))
        assert not wrong, f"slugs resolved to a different tournament: {wrong}"

    def test_no_slug_resolves_outside_its_own_identity(self):
        """The general statement of the bug: whatever a slug resolves to, the
        result must carry every identity token the slug asked for."""
        offenders = []
        for slug in self._all_slugs():
            got = _resolve(slug)
            if got is None:
                continue
            want = canonical_slug_tokens(slug)
            if want and not want <= canonical_tokens(got):
                offenders.append((slug, got))
        assert not offenders, f"resolved outside identity: {offenders}"

    def test_the_enumerated_repairs_all_hold(self):
        for slug, expected in self.REPAIRED.items():
            assert _resolve(slug) == expected, f"{slug} regressed"

    def test_nothing_else_changed(self):
        """Every slug NOT in the repair list must still resolve to something —
        the fix removed a wrong answer, it did not empty the domain."""
        for slug in self._all_slugs():
            if slug in self.REPAIRED:
                continue
            assert _resolve(slug) is not None, f"{slug} lost its page"


# ---------------------------------------------------------------------------
# 5. The hub must not LINK what the adapter will not SERVE
# ---------------------------------------------------------------------------
class TestHubRailNeverLinksABrokenShelf:
    """`/hub/tennis` groups winner markets and emits one concept per group. With
    the primary guard in `build_event` and no guard there, the rail would have
    gone on linking "Serena Williams to Win a Tournament in 2026" — measured live
    on 2026-08-12 — straight to a 404.

    These drive the REAL `list_tennis_tournament_concepts`, not a copy of its
    grouping. A test that re-implements the code under test certifies the
    agreement between two things that can be wrong together (cycle 64's lesson);
    the whole point here is that the rail and the adapter agree, so the rail has
    to be the real one.
    """

    async def _emitted(self):
        rows = [r for r in CORPUS if r["status"] == "open"]
        db = _FakeDB(_markets_with_outcomes(rows))
        concepts = await list_tennis_tournament_concepts(db, limit=50)
        return sorted(c["key"].split(":", 2)[2] for c in concepts)

    async def test_every_emitted_concept_resolves(self):
        unserved = [s for s in await self._emitted() if _resolve(s) is None]
        assert not unserved, f"hub links that 404: {unserved}"

    async def test_the_novelty_prop_is_no_longer_linked_as_a_tournament(self):
        assert "serena-williams-to-win-a-tournament-in-2026" not in await self._emitted()

    async def test_the_real_tournaments_are_still_linked(self):
        emitted = await self._emitted()
        for slug in ["cincinnati-open-winner", "wta-1000-toronto-winner",
                     "atp-1000-montreal-winner", "wta-hamburg-winner"]:
            assert slug in emitted, f"{slug} vanished from the hub rail"

    async def test_the_rail_is_not_silently_empty(self):
        """Guard the guard — an empty rail would pass the three above vacuously.

        The floor was 12 and is 11 because UX-P182 stopworded the ATP/WTA tour
        tiers: over this corpus "ATP 1000 Montreal: Winner"/"ATP Montreal Winner"
        and "WTA 1000 Toronto: Winner"/"WTA Toronto Winner" are each ONE
        tournament, and the rail used to emit both renderings of both. This
        number moves WITH that fix; it is not a threshold to relax when a future
        change makes the rail shorter. `TestTourTiersAreNotIdentity` below pins
        the merge itself, so a regression that re-splits them fails there loudly
        rather than here as an off-by-two.
        """
        assert len(await self._emitted()) >= 11


# ---------------------------------------------------------------------------
# 6. Tennis can say "major", and its one date is an END (UX-P178, #2167)
# ---------------------------------------------------------------------------
#
# Both tennis concept sites hardcoded `is_major: False` and the rail served the
# winner market's `resolution_date` under the key `start_date`. Measured live
# 2026-08-29 on /api/hub/tennis: 12 upcoming cards, **0** flagged major (and 0 of
# 48 across all five hubs — the "★ Marquee" chip had never rendered anywhere),
# while four cards printed a FUTURE date under a pulsing LIVE dot. The detail
# envelope for those same concepts served that identical timestamp as `end_date`
# with `start_date: None`.

#: The production census of tennis-categorized winner markets, verbatim
#: (db-query 2026-08-29, `truncated: False`, 14 rows). Three of them are FOOTBALL
#: — AFC Wimbledon — carrying `llm_sport_category = 'tennis'`. They are in this
#: table on purpose: they are what a bare `%Wimbledon%` substring test gets wrong.
_MAJOR_CENSUS: tuple[tuple[str, bool], ...] = (
    ("2026 Men's Australian Open Winner", True),
    ("2026 Men's French Open Winner", True),
    ("2026 Men’s Singles Roland Garros: Winner", True),
    ("2026 Men’s US Open Winner (Tennis)", True),
    ("2026 Men’s Wimbledon Winner", True),
    ("2026 Women's French Open Winner", True),
    ("2026 Women’s Singles Roland Garros: Winner", True),
    ("2026 Women’s US Open Winner (Tennis)", True),
    ("2026 Women's Wimbledon Winner", True),
    ("Huddersfield vs Wimbledon: First Half Winner", False),  # football
    ("US Open Men's Singles Winner", True),
    ("US Open Women's Singles Winner", True),
    ("Wimbledon vs Newport: First Half Winner", False),  # football
    ("Wimbledon vs Reading: First Half Winner", False),  # football
)


class TestTennisKnowsWhatAMajorIs:
    @pytest.mark.parametrize("name,expected", _MAJOR_CENSUS)
    def test_the_production_census(self, name, expected):
        assert tennis_is_major(name) is expected, name

    def test_the_football_wimbledons_are_rejected(self):
        """Called out separately from the table because it is the whole reason the
        predicate is anchored rather than a substring test. AFC Wimbledon is a
        football club and its markets are miscategorized as tennis upstream."""
        football = [n for n, _ in _MAJOR_CENSUS if " vs " in n]
        assert len(football) == 3, "the census lost its football rows"
        assert not [n for n in football if tennis_is_major(n)]

    @pytest.mark.parametrize(
        "name",
        [
            "Cincinnati Open: Winner",
            "WTA 1000 Toronto: Winner",
            "ATP 1000 Montreal: Winner",
            "WTA Washington Winner",
            "2026 WTA Athens Winner",
        ],
    )
    def test_ordinary_tournaments_are_not_majors(self, name):
        """The control, and it carries more weight than the positives: a predicate
        that returns True for everything satisfies every assertion above and makes
        the chip meaningless."""
        assert tennis_is_major(name) is False

    def test_both_names_for_the_french_open_are_recognized(self):
        """Roland Garros and the French Open are one tournament under two names and
        BOTH are live in the corpus, one winner market per source."""
        assert tennis_is_major("2026 Men's French Open Winner")
        assert tennis_is_major("2026 Men’s Singles Roland Garros: Winner")

    def test_the_census_is_not_vacuous(self):
        """Guard the guard: an all-False predicate passes every negative case."""
        assert sum(1 for n, _ in _MAJOR_CENSUS if tennis_is_major(n)) == 11


class TestTheRailFlagsMajorsAndServesAnEndDate:
    """Drives the REAL `list_tennis_tournament_concepts` over the REAL production
    corpus — not a copy of its grouping (see section 5's note)."""

    async def _concepts(self):
        rows = [dict(r) for r in CORPUS if r["status"] == "open"]
        for r in rows:
            # The US Open winner markets carried this resolution date in production.
            if "US Open" in r["name"]:
                r["resolution_date"] = datetime(2026, 9, 13, tzinfo=timezone.utc)
        db = _FakeDB(_markets_with_outcomes(rows))
        return await list_tennis_tournament_concepts(db, limit=50)

    async def test_the_us_open_is_marquee(self):
        majors = [c["name"] for c in await self._concepts() if c["is_major"]]
        assert majors, "the rail flags no majors at all — the state UX-P178 fixed"
        assert all("US Open" in n for n in majors), majors

    async def test_the_ordinary_tournaments_are_not(self):
        """A rail that flags everything is as useless as one that flags nothing."""
        concepts = await self._concepts()
        plain = [c for c in concepts if not c["is_major"]]
        assert len(plain) >= 8, f"only {len(plain)} unflagged of {len(concepts)}"

    async def test_the_resolution_date_is_never_served_as_a_start(self):
        """The defect: /hub/tennis printed this END date as a start, under a LIVE
        pill. We have no tournament start date for tennis, and a date we do not
        have is absent — never guessed, never borrowed from another field."""
        for c in await self._concepts():
            assert c["start_date"] is None, c["name"]

    async def test_the_date_we_do_have_is_still_served(self):
        """The other half, and without it the fix is a regression: nulling
        `start_date` alone would turn every dated tennis card into "TBD"."""
        dated = [c for c in await self._concepts() if c["end_date"]]
        assert len(dated) == 2, [c["name"] for c in dated]
        assert all(c["end_date"].startswith("2026-09-13") for c in dated)


class TestTheRailAndTheDetailPageAgreeAboutOneTimestamp:
    """Redundancy is not coupling. Both layers read the SAME field
    (`winner.resolution_date`) and both were free to name it whatever they liked —
    which is exactly how they came to disagree, the rail calling it `start_date`
    and the envelope calling it `end_date`, one click apart.

    So this asserts the AGREEMENT, and it does it on ONE payload driven through
    BOTH real code paths rather than on two fixtures that can drift apart.
    """

    def _market(self, name="2026 Wimbledon Winner"):
        # Gotcha #44: offset FIRST, then truncate. A fixed calendar date here goes
        # stale — `tennis_status` settles anything already resolved and the rail
        # drops it, so the agreement would be asserted over two empty lists.
        resolves = (datetime.now(timezone.utc) + timedelta(days=4)).replace(
            microsecond=0
        )
        return SimpleNamespace(
            id=114157,
            name=name,
            status="open",
            llm_sport_category="tennis",
            source="polymarket",
            group_id="polymarket:139182",
            resolution_date=resolves,
            outcomes=[
                SimpleNamespace(name="Coco Gauff", current_probability=0.45, is_winner=False),
                SimpleNamespace(name="Aryna Sabalenka", current_probability=0.40, is_winner=False),
                SimpleNamespace(name="Karolína Muchová", current_probability=0.35, is_winner=False),
            ],
        )

    async def _both(self, name="2026 Wimbledon Winner"):
        from app.utils.name_normalization import clean_slug as _slug

        db = _FakeDB([self._market(name)])
        rail = await list_tennis_tournament_concepts(db, limit=50)
        envelope = await TennisEventAdapter().build_event(_slug(name), db)
        assert rail and envelope, "one of the two layers served nothing"
        return rail[0], envelope["event"]

    async def test_they_agree_on_the_end_date(self):
        rail, event = await self._both()
        assert rail["end_date"] == event["end_date"]
        assert rail["end_date"] is not None  # not agreeing on a shared None

    async def test_they_agree_that_there_is_no_start_date(self):
        rail, event = await self._both()
        assert rail["start_date"] is None and event["start_date"] is None

    async def test_they_agree_the_slam_is_major(self):
        rail, event = await self._both()
        assert rail["is_major"] is True and event["is_major"] is True

    async def test_they_agree_an_ordinary_tournament_is_not(self):
        rail, event = await self._both("Cincinnati Open: Winner")
        assert rail["is_major"] is False and event["is_major"] is False


# ---------------------------------------------------------------------------
# 8. A tour tier is a property, not an identity (UX-P182)
# ---------------------------------------------------------------------------
#
# Measured live on /api/hub/tennis 2026-08-29: the rail served **12 upcoming
# cards for 10 tournaments**. "ATP Montreal Winner" and "ATP 1000 Montreal:
# Winner" were two cards, as were "WTA Toronto Winner" and "WTA 1000 Toronto:
# Winner" — and all four keys, fetched from production, resolved to just TWO
# event pages. The rail keys its groups on the EXACT token set while
# `select_winner_field` matches by SUBSET, so the resolver had always treated
# each pair as one tournament and only the rail disagreed. The reader saw the
# disagreement as a duplicate that opened the page it had just come from.


class TestTourTiersAreNotIdentity:
    """The token-space half, the rail half, and the two controls that matter."""

    _PAIRS = (
        ("ATP 1000 Montreal: Winner", "ATP Montreal Winner", "montreal"),
        ("WTA 1000 Toronto: Winner", "WTA Toronto Winner", "toronto"),
    )

    def test_the_tier_token_is_gone_from_the_identity_space(self):
        for tiered, plain, city in self._PAIRS:
            assert canonical_tokens(tiered) == canonical_tokens(plain) == {city}

    def test_a_tier_in_the_slug_and_a_tier_in_the_name_agree(self):
        """Both spellings of the URL have to land in the same token set, or the
        rail merges while the resolver 404s the survivor's key."""
        assert canonical_slug_tokens("atp-1000-montreal-winner") == {"montreal"}
        assert canonical_slug_tokens("atp-montreal-winner") == {"montreal"}

    async def _emitted(self):
        rows = [r for r in CORPUS if r["status"] == "open"]
        db = _FakeDB(_markets_with_outcomes(rows))
        return await list_tennis_tournament_concepts(db, limit=50)

    async def test_the_rail_emits_one_card_per_tournament(self):
        """The ship. Drives the REAL lister over the REAL production corpus."""
        names = [c["name"] for c in await self._emitted()]
        for city in ("Montreal", "Toronto"):
            hits = [n for n in names if city.lower() in n.lower()]
            assert len(hits) == 1, f"{city} is listed {len(hits)}x: {hits}"

    async def test_the_surviving_card_is_the_fullest_draw(self):
        """Identity still comes from the richest field (L2-65), so the card and
        the page it opens finally print the same title."""
        names = {c["name"] for c in await self._emitted()}
        assert "ATP 1000 Montreal: Winner" in names
        assert "WTA 1000 Toronto: Winner" in names

    async def test_the_survivors_key_still_resolves(self):
        """A merge that produced a card pointing at nothing would be a broken
        shelf — the exact failure class section 5 exists for."""
        for c in await self._emitted():
            slug = c["key"].split(":", 2)[2]
            assert _resolve(slug) is not None, f"{slug} lost its page"

    async def test_both_old_urls_still_open_the_same_page(self):
        """Nobody's bookmark breaks: both spellings resolved to one market before
        the fix and must still resolve to that same one after it."""
        for tiered_slug, plain_slug, expected in (
            ("atp-1000-montreal-winner", "atp-montreal-winner",
             "ATP 1000 Montreal: Winner"),
            ("wta-1000-toronto-winner", "wta-toronto-winner",
             "WTA 1000 Toronto: Winner"),
        ):
            assert _resolve(tiered_slug) == expected
            assert _resolve(plain_slug) == expected

    # -- controls ----------------------------------------------------------

    def test_a_non_tier_number_is_still_identity(self):
        """`1000` is stripped because it is a TIER, not because it is a number.
        The corpus is full of numerics (`2` x199, `16` x87) and none of them may
        start collapsing tournaments together."""
        assert "16" in canonical_tokens("ATP 16 Springfield Winner")
        assert canonical_tokens("ATP 16 Springfield Winner") != canonical_tokens(
            "ATP Springfield Winner"
        )

    def test_the_1793_collision_is_still_impossible(self):
        """The whole reason this token space exists. Widening it is how
        `us-open-2026` came to serve Cincinnati."""
        us = canonical_tokens("US Open Men's Singles Winner")
        cincy = canonical_tokens("Cincinnati Open: Winner")
        assert not us <= cincy and not cincy <= us

    def test_the_tiers_are_the_closed_published_set(self):
        assert _TOUR_TIER_TOKENS == {"125", "250", "500", "1000"}
        assert _TOUR_TIER_TOKENS <= _TENNIS_STOPWORDS


class TestMergingNeverSubtractsTheDate:
    """The regression the merge would have shipped if it had stopped at grouping.

    `winner` is the fullest DRAW, and the fullest draw is not the row that knows
    the most. Measured 2026-08-29: "ATP 1000 Montreal: Winner" has 69 outcomes
    and `resolution_date = NULL`; "ATP Montreal Winner" has 46 and knows the
    tournament ends 2026-09-13. Reading the date off `winner` alone turns one
    duplicated-but-dated card into one deduplicated UNDATED card, downgraded from
    `live` to `upcoming` — a silent subtraction traded for a visible duplicate.
    """

    def _pair(self):
        # Gotcha #44: offset FIRST, then truncate — a fixed date settles and the
        # rail drops the row, asserting everything over an empty list.
        ends = (datetime.now(timezone.utc) + timedelta(days=5)).replace(microsecond=0)
        rich = SimpleNamespace(
            id=57718610,
            name="ATP 1000 Montreal: Winner",
            status="open",
            resolution_date=None,  # the fullest draw, and it has no date
            volume_24h=3294,
            outcomes=[SimpleNamespace(name=f"Player {i}") for i in range(69)],
        )
        dated = SimpleNamespace(
            id=58728642,
            name="ATP Montreal Winner",
            status="open",
            resolution_date=ends,  # the smaller draw, and it does
            volume_24h=67053,
            outcomes=[SimpleNamespace(name=f"Player {i}") for i in range(46)],
        )
        return rich, dated, ends

    async def _rail(self, markets):
        return await list_tennis_tournament_concepts(_FakeDB(markets), limit=50)

    async def test_the_two_renderings_become_one_card(self):
        rich, dated, _ = self._pair()
        assert len(await self._rail([rich, dated])) == 1

    async def test_the_survivor_keeps_the_date_its_sibling_knew(self):
        rich, dated, ends = self._pair()
        (card,) = await self._rail([rich, dated])
        assert card["name"] == "ATP 1000 Montreal: Winner"  # identity from the draw
        assert card["end_date"] == ends.isoformat()  # date from the group

    async def test_the_survivor_keeps_its_live_status(self):
        rich, dated, _ = self._pair()
        (card,) = await self._rail([rich, dated])
        assert card["status"] == "live"

    async def test_alone_the_undated_rendering_still_admits_no_date(self):
        """The control. A date is borrowed from a SIBLING, never invented — with
        no sibling to read, the rail still says it does not know."""
        rich, _, _ = self._pair()
        (card,) = await self._rail([rich])
        assert card["end_date"] is None and card["status"] == "upcoming"

    async def test_the_winners_own_date_wins_when_it_has_one(self):
        """Identity's row is still preferred; the sibling is a fallback, not an
        override."""
        rich, dated, ends = self._pair()
        rich.resolution_date = ends + timedelta(days=2)
        (card,) = await self._rail([rich, dated])
        assert card["end_date"] == (ends + timedelta(days=2)).isoformat()
