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
from types import SimpleNamespace

import pytest

from app.utils.event_tennis import (
    _MIN_FIELD_OUTCOMES,
    canonical_slug_tokens,
    canonical_tokens,
    is_winner_field,
    is_winner_market,
    list_tennis_tournament_concepts,
    select_winner_field,
    tennis_gender,
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
                resolution_date=None,
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
        """Guard the guard — an empty rail would pass the three above vacuously."""
        assert len(await self._emitted()) >= 12
