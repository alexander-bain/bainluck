"""#6941 — a search group header is a NAME, never the key that grouped it.

WHAT A READER SAW. Searching "UFC 331" on production (2026-09-18 12:2xZ) drew a
group of fight questions under the header `Ufc Event:331`. "BMW PGA Championship"
drew `Golf Tournament:Bmw Pga Championship`. Both are the machine key, colon
included. Searching "World Series" drew seven darts questions under
`NICHE LOW SIGNAL SPORTS` — our own ranking vocabulary, aimed at the reader whose
sport it is.

THE CAUSE was a FOURTH resolver. `_compose_futures_families` built its header by
string surgery on the key — `key.split(":", 1)[1].replace("_", " ").title()` —
while `discover_bundles` already resolved the same keys three correct ways
(authored map, per-tournament golf copy, per-event UFC name) for the same story
vocabulary. Search simply never called it. The fix is `story_family_label`, one
resolver both surfaces share.

WHY THE TWO CLIENTS DISAGREE ABOUT WHICH HALF IS VISIBLE, and why the fix is in
the payload rather than in either of them:

  * web uppercases the header (`SearchFamilyCard.tsx:158`), so `Us 2028 Election`
    renders `US 2028 ELECTION` and the casing defect is INVISIBLE there;
  * iOS sets `.textCase(nil)` (`SearchView.swift:852`), deliberately defeating
    SwiftUI's section-header uppercasing, so the phone prints the served string
    verbatim — "Ufc Events", "Ipo Markets", "Us 2028 Election".

A casing fix in the web client would have delivered nothing, and one in the phone
would have left the other client's vocabulary wrong. Both print `label` verbatim,
so one backend string serves both and neither client changes (notice 41).

NOT COVERED BY THIS FILE, and deliberately: 24 of the 27 literal story keys are
authored; three are not — `story:niche_low_signal_sports`,
`story:minor_soccer_leagues` and `story:daily_equity_direction` — so those still
derive to "Niche Low Signal Sports", "Minor Soccer Leagues", "Daily Equity
Direction". Authoring them requires an authored bundle QUESTION too
(`test_discover_bundle_shared_question_4066.py` enforces title ⊆ question) and
that sentence is a Discover product decision on Discover's surface. Routed, not
silently patched here, because a label invented in the search layer would fork
the very vocabulary this change exists to unify.
`test_the_unauthored_keys_are_the_known_remainder` below PINS that remainder, so
it cannot quietly grow.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import _compose_futures_families
from app.utils.discover_bundles import (
    AUTHORED_STORY_TITLES,
    story_family_label,
)
from app.utils.feed_market_quality import _story_key


def _mkt(mid, name, category=""):
    return SimpleNamespace(id=mid, name=name, llm_sport_category=category)


def _headers(markets, expanded):
    """The labels `/api/events/search` would ship for these markets."""
    ids = {m.id for m in markets}
    fams = _compose_futures_families(
        markets, expanded, lambda m: {"id": m.id, "name": m.name}, ids
    )
    return [f["label"] for f in fams]


# ── The two specimens that were photographed ─────────────────────────────────


class TestTheMachineKeyIsGone:
    def test_ufc_331_is_headed_by_the_event_not_the_key(self):
        """The reproduction. `Ufc Event:331` -> `UFC 331`."""
        markets = [
            _mkt(1, "UFC 331: Renato Moicano vs. Brian Ortega"),
            _mkt(2, "UFC 331: Will there be a first-round finish?"),
        ]

        assert _headers(markets, [("ufc", None)]) == ["UFC 331"]

    def test_the_golf_tournament_is_headed_by_its_name(self):
        markets = [
            _mkt(3, "BMW PGA Championship winner", "golf"),
            _mkt(4, "BMW PGA Championship top 5 finish", "golf"),
        ]

        assert _headers(markets, [("bmw", None)]) == ["BMW PGA Championship"]

    @pytest.mark.parametrize(
        "token,category,names",
        [
            (
                "ufc",
                "",
                [
                    "UFC 331: Renato Moicano vs. Brian Ortega",
                    "UFC 331: Will there be a first-round finish?",
                ],
            ),
            (
                "bmw",
                "golf",
                [
                    "BMW PGA Championship winner",
                    "BMW PGA Championship top 5 finish",
                ],
            ),
        ],
    )
    def test_no_header_carries_the_signature_of_a_key(self, token, category, names):
        """A colon or an underscore in a header is a machine key that escaped.

        Aimed at the CLASS rather than at the two photographed strings: any
        future prefixed key reaching this composer unresolved trips this.

        🪤 The first draft built its second member by appending " (alt)" to the
        first name. `_story_key` returns None for "BMW PGA Championship winner
        (alt)" — no recognised golf question — so the two members keyed
        differently, no family formed, and the loop below asserted over an EMPTY
        list: the golf half passed against the UNFIXED code. Hence real member
        names, and the `assert headers` that makes a silent empty a failure.
        """
        markets = [_mkt(9 + i, n, category) for i, n in enumerate(names)]

        headers = _headers(markets, [(token, None)])

        assert headers, "no family formed — this guard would assert nothing"
        for header in headers:
            assert ":" not in header, header
            assert "_" not in header, header


# ── The authored vocabulary, which search now speaks ─────────────────────────


class TestSearchSpeaksTheHouseVocabulary:
    @pytest.mark.parametrize(
        "story_key,expected",
        [
            ("story:ai", "AI"),
            ("story:ipo_markets", "IPOs"),
            ("story:ufc_events", "UFC"),
            ("story:us_2028_election", "2028 Election"),
            ("story:regional_us_elections", "US Local Elections"),
            ("story:fifa_world_cup", "World Cup"),
            ("story:macro_rates", "Fed & Rates"),
            ("story:russia_ukraine", "Russia–Ukraine"),
            ("story:drake_iceman", "Drake"),
            ("story:spacex_ipo", "SpaceX IPO"),
        ],
    )
    def test_the_authored_name_is_the_one_served(self, story_key, expected):
        assert story_family_label(story_key, []) == expected

    def test_every_authored_key_resolves_to_its_authored_name(self):
        """Not a sample — the WHOLE map.

        This is what makes a fork expensive: a search-local label table would
        have to reproduce all of `AUTHORED_STORY_TITLES` to pass, and would then
        drift the moment Discover edits one entry.
        """
        wrong = {
            key: story_family_label(key, [])
            for key, authored in AUTHORED_STORY_TITLES.items()
            if story_family_label(key, []) != authored
        }

        assert wrong == {}

    def test_a_derived_name_respects_acronyms(self):
        """The unauthored path is still not string surgery: `.title()` gave
        `Us State Races`, the shared resolver gives the acronym its case. On iOS
        this is the difference the reader sees; on web it is hidden by CSS."""
        assert story_family_label("story:us_state_races", []) == "State Races"
        assert "Us " not in story_family_label("story:us_government_stakes", [])


# ── The arms that must NOT move ──────────────────────────────────────────────


class TestTheEntityBranchIsUntouched:
    def test_an_entity_family_still_reads_as_the_query(self):
        markets = [
            _mkt(5, "Carlos Alcaraz to win the US Open"),
            _mkt(6, "Carlos Alcaraz year-end number one"),
        ]

        assert _headers(markets, [("alcaraz", None)]) == ["Alcaraz"]


class TestNoHonestHeadlineDropsTheFamilyRatherThanInventOne:
    def test_an_unnameable_family_is_not_headed_by_a_key(self):
        """A golf key whose members no longer state a tournament we can name.

        The bundler's rule is to fail closed, and search does the same. The
        markets are NOT lost: families are additive, so every member is still in
        the flat `futures` list the same response ships.
        """
        key = _story_key("Zzz Invitational winner", "golf")

        # Asserted, not assumed: an `if` here would let the whole guard go
        # silent the day this fixture stopped keying as a golf tournament.
        assert key == "story:golf_tournament:zzz_invitational"
        assert story_family_label(key, ["a question naming no tournament"]) is None

    def test_a_real_golf_family_is_headed_from_its_members(self, monkeypatch):
        """First, the case that actually occurs: the tournament is recoverable.

        🪤 I wrote the drop test below first and it FAILED — the composer headed
        this family "Zzz Invitational" instead of dropping it. That is correct,
        and it taught me the shape of the arm: a golf key is MINTED FROM a member
        name, and the composer passes exactly the members that minted it, so one
        of them can always give the tournament back. The fail-closed branch is
        DEFENSIVE, not naturally reachable — so the specimen below is
        manufactured rather than claimed.
        """
        markets = [
            _mkt(7, "Zzz Invitational winner", "golf"),
            _mkt(8, "Zzz Invitational top 5 finish", "golf"),
        ]

        assert _headers(markets, [("zzz", None)]) == ["Zzz Invitational"]

    def test_the_composer_drops_a_family_it_cannot_head(self, monkeypatch):
        """The `continue` arm, on a MANUFACTURED specimen.

        No live row reaches it (see above), so the resolver is forced to decline
        and the composer's response is measured. Without this, deleting the
        branch leaves every other test in this file green while search ships
        `label: None` to two clients that both print it verbatim.

        Patched at `discover_bundles`, not at `app.routes.events`: the composer
        imports the name INSIDE the function, so it is looked up on the source
        module at call time and a patch on the route module would no-op — and
        would do so silently, leaving a guard that proves nothing.
        """
        import app.utils.discover_bundles as bundles

        monkeypatch.setattr(bundles, "story_family_label", lambda *a, **k: None)
        markets = [
            _mkt(7, "Zzz Invitational winner", "golf"),
            _mkt(8, "Zzz Invitational top 5 finish", "golf"),
        ]

        assert _headers(markets, [("zzz", None)]) == []


# ── Anti-drift: one vocabulary, pinned in both directions ────────────────────


class TestTheVocabularyCannotSilentlyDrift:
    def test_the_resolver_covers_every_key_the_producer_can_mint(self):
        """Every literal `story:` key `_story_key` can return resolves to a name
        with no key signature in it. A new key added to the feed machinery
        without a label is caught HERE, by CI, rather than by a reader."""
        import ast
        import inspect

        import app.utils.feed_market_quality as fmq

        tree = ast.parse(inspect.getsource(fmq))
        keys = sorted(
            {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.startswith("story:")
                and not node.value.endswith(":")  # the two dynamic PREFIXES
            }
        )

        assert len(keys) >= 20, f"the scan found only {len(keys)} keys — it broke"
        offenders = {
            key: story_family_label(key, [])
            for key in keys
            if (story_family_label(key, []) or "").count(":")
        }

        assert offenders == {}

    def test_the_unauthored_keys_are_the_known_remainder(self):
        """#6941's stated scope, pinned so it cannot grow unnoticed.

        These derive rather than resolve, because authoring a title obliges an
        authored bundle question (Discover's contract). If a FOURTH key joins
        them, this reddens and the routing note needs rewriting — which is the
        point: the remainder is a decision, not a drift.

        🪤 It caught me on its first run. I wrote this assertion with the two
        keys I had SEEN on production and it failed on a third,
        `story:daily_equity_direction`, which my 23-query walk never turned up.
        24 of the 27 literal keys are authored; the remainder is three. A pin
        written from what a walk happened to surface is a sample, not a census —
        this one was cheap enough to take properly.
        """
        import ast
        import inspect

        import app.utils.feed_market_quality as fmq

        tree = ast.parse(inspect.getsource(fmq))
        keys = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("story:")
            and not node.value.endswith(":")
        }

        assert sorted(keys - set(AUTHORED_STORY_TITLES)) == [
            "story:daily_equity_direction",
            "story:minor_soccer_leagues",
            "story:niche_low_signal_sports",
        ]
