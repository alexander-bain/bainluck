"""#9935 slice P1 — pure guards for ``app.utils.theme_definitions``.

Case numbers are the producer contract's §8 table
(``docs/theme-collection-producer-contract-9935.md`` v3.1). Ids are the real
ones from #9925's evidence; every row here is an in-memory fixture. Nothing in
this file touches a database: the §4 gather arms are compiled to SQL text and
inspected, never executed (P1 builds them; P2 runs them).
"""

from __future__ import annotations

import ast
import inspect
import random
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.utils import theme_definitions as td
from app.utils.theme_definitions import (
    AI,
    FEED_KEY_MAP,
    OSCARS_2027,
    REGISTRY,
    CandidateContainer,
    ThemeDefinition,
    build_feed_key_map,
    build_registry,
    candidate_population,
    parse_theme_slug,
    resolve_collection_target,
)

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
PLACEHOLDER_2027 = datetime(2027, 12, 31, 15, 0, tzinfo=timezone.utc)
BACKEND = Path(__file__).resolve().parents[1]


def mk(
    id,
    name,
    *,
    source="polymarket",
    external_id=None,
    cat="entertainment",
    status="open",
    settled_at=None,
    resolution_date=None,
    metadata=None,
    outcomes=(),
):
    return SimpleNamespace(
        id=id,
        name=name,
        source=source,
        external_id=external_id or f"pm-{id}",
        llm_sport_category=cat,
        canonical_market_key=None,
        status=status,
        settled_at=settled_at,
        resolution_date=resolution_date,
        market_metadata=metadata,
        outcomes=list(outcomes),
        group_id=None,
    )


def kalshi(id, ticker, name, **kw):
    return mk(id, name, source="kalshi", external_id=ticker, **kw)


def oscars(m, now=NOW):
    return OSCARS_2027.decide(m, now=now)


def ai(m, now=NOW):
    return AI.decide(m, now=now)


def clause(decision, name):
    return next(c for c in decision.evidence["clauses"] if c["clause"] == name)


# ---------------------------------------------------------------------------
# Registry, slugs (case 10's parser half), static map guards (case 22).
# ---------------------------------------------------------------------------


class TestRegistryAndSlugs:
    def test_registry_holds_exactly_the_two_first_ship_subjects(self):
        assert set(REGISTRY) == {"oscars-2027", "ai"}
        assert REGISTRY["oscars-2027"] is OSCARS_2027 and REGISTRY["ai"] is AI
        assert (OSCARS_2027.scope, OSCARS_2027.edition) == ("finite", 2027)
        assert (AI.scope, AI.edition) == ("continuing", None)
        assert OSCARS_2027.container_kind == "award_show" and OSCARS_2027.category == "awards"
        assert AI.container_kind == "theme" and AI.category == "ai"
        assert OSCARS_2027.display_name == "Oscars 2027"
        assert OSCARS_2027.rule_version == "oscars-edition@1"
        # @2 (#9936): clause 3's unknown-time verdict no longer retires a standing member
        assert AI.rule_version == "ai-subject@2"

    @pytest.mark.parametrize("slug", sorted(REGISTRY))
    def test_every_registered_slug_round_trips(self, slug):
        parsed = parse_theme_slug(slug)
        assert parsed is not None
        defn = REGISTRY[slug]
        rebuilt = td.build_theme_slug(parsed["subject"], defn.scope, parsed.get("edition"))
        assert rebuilt == slug

    def test_parsed_shapes(self):
        assert parse_theme_slug("oscars-2027") == {
            "kind": "theme_edition", "subject": "oscars", "edition": 2027}
        assert parse_theme_slug("ai") == {"kind": "theme_continuing", "subject": "ai"}
        # A finite subject parses for any edition; whether a container exists is
        # the reader's question (404 `unavailable`), never a nearest guess here.
        assert parse_theme_slug("oscars-2031") == {
            "kind": "theme_edition", "subject": "oscars", "edition": 2031}

    @pytest.mark.parametrize(
        "slug",
        ["ai-2026", "nfl-2026-week-04", "oscars-27", "Oscars-2027", "oscars-2027 ",
         "oscars-02027", "oscars", "ai-", "grammys-2027", "", None, "oscars-2027-x"],
    )
    def test_non_round_tripping_slugs_return_none(self, slug):
        assert parse_theme_slug(slug) is None

    def test_slug_builder_refuses_shape_mismatch(self):
        with pytest.raises(ValueError):
            td.build_theme_slug("oscars", "finite", None)
        with pytest.raises(ValueError):
            td.build_theme_slug("ai", "continuing", 2026)

    def test_registry_refuses_duplicate_slug_and_split_scope(self):
        with pytest.raises(ValueError):
            build_registry([AI, AI])
        split = ThemeDefinition(
            subject="ai", scope="finite", edition=2026, rule_version="x@1",
            container_kind="theme", category="ai", display_name="AI 2026",
            decider=lambda *a, **k: None, population=lambda *a, **k: {})
        with pytest.raises(ValueError):
            build_registry([AI, split])

    # case 22 (static)
    def test_feed_key_map_names_registry_subjects_and_story_keys_only(self):
        subjects = {d.subject for d in REGISTRY.values()}
        assert FEED_KEY_MAP == {"story:ai": "ai"}
        for key, subject in FEED_KEY_MAP.items():
            assert key.startswith("story:")
            assert sum(1 for d in REGISTRY.values() if key in d.feed_keys) == 1
            assert subject in subjects
        assert td.SWINGS_FEED_KEY not in FEED_KEY_MAP
        assert not OSCARS_2027.feed_keys  # awards group_ids never get a map entry

    @pytest.mark.parametrize("bad_key", ["swings", "polymarket:12345", "group:oscars"])
    def test_feed_key_map_refuses_swings_and_group_ids(self, bad_key):
        defn = ThemeDefinition(
            subject="x", scope="continuing", rule_version="x@1", container_kind="theme",
            category="x", display_name="X", decider=lambda *a, **k: None,
            population=lambda *a, **k: {}, feed_keys=(bad_key,))
        with pytest.raises(ValueError):
            build_feed_key_map({"x": defn})

    def test_feed_key_map_refuses_a_key_claimed_by_two_subjects(self):
        twin = ThemeDefinition(
            subject="robots", scope="continuing", rule_version="r@1", container_kind="theme",
            category="ai", display_name="Robots", decider=lambda *a, **k: None,
            population=lambda *a, **k: {}, feed_keys=("story:ai",))
        with pytest.raises(ValueError):
            build_feed_key_map(build_registry([AI, twin]))

    def test_resolver_steps_never_read_publication_state(self):
        tree = ast.parse(textwrap.dedent(inspect.getsource(resolve_collection_target)))
        fn = tree.body[0]
        body = fn.body[1:]  # skip the docstring
        names = {
            n.attr if isinstance(n, ast.Attribute) else getattr(n, "id", None)
            for stmt in body for n in ast.walk(stmt)
            if isinstance(n, (ast.Attribute, ast.Name))
        }
        strings = {n.value for stmt in body for n in ast.walk(stmt)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        assert not any("publication" in (s or "") for s in names | strings)


# ---------------------------------------------------------------------------
# oscars-edition@1
# ---------------------------------------------------------------------------


class TestOscarsCeremonyClause:
    # case 3
    def test_oscar_named_people_never_enter_by_substring(self):
        collazo = kalshi(61082201, "KXBOXING-26SANCOL", "Sandoval vs Oscar Collazo", cat="boxing")
        brown = mk(63448382, "M15 Baku: Oscar Brown vs Ivan Petrov", cat="tennis")
        piastri = mk(990001, "Oscar Piastri to win the 2027 F1 title?", cat="f1")
        assert oscars(collazo).reason == td.NOT_THIS_CEREMONY
        assert oscars(brown).reason == td.NOT_THIS_CEREMONY
        # "Oscar Piastri" starts the title, so the category gate is what holds.
        assert oscars(piastri).reason == td.WRONG_CATEGORY
        for m in (collazo, brown, piastri):
            assert oscars(m).outcome == "excluded"

    def test_mid_title_oscar_substring_in_entertainment_is_not_the_ceremony(self):
        m = mk(990002, "Will an Oscar-winning director top the 2027 box office?")
        assert oscars(m).reason == td.NOT_THIS_CEREMONY

    def test_other_kalshi_ceremony_ticker_is_not_this_ceremony(self):
        m = kalshi(990003, "KXGRAMAOTY-69", "Grammy winner: Album of the Year")
        assert oscars(m).reason == td.NOT_THIS_CEREMONY

    def test_title_arms_are_the_polymarket_titles_only(self):
        # §3 clause 1: a non-KXOSCAR Kalshi row is the ticker arm's or nobody's,
        # whatever its name or stored event title says.
        title = {"event_title": "Oscars 2027: Best Picture Winner"}
        by_name = kalshi(990004, "KXFILMX-27", "Oscars 2027: Best Picture Winner")
        by_title = kalshi(990005, "KXFILMX-27B", "Will Oppenheimer win?", metadata=title)
        assert oscars(by_name).reason == td.NOT_THIS_CEREMONY
        assert oscars(by_title).reason == td.NOT_THIS_CEREMONY
        # Control: the same name / event title on a Polymarket row admits.
        assert oscars(mk(990006, "Oscars 2027: Best Picture Winner")).outcome == "admitted"
        assert oscars(mk(990008, "Will Oppenheimer win?", metadata=title)).outcome == "admitted"

    def test_structural_pattern_postgres_flavour_matches_python(self):
        assert td.OSCARS_STRUCTURAL_PG == td.OSCARS_STRUCTURAL_RE.pattern.replace(r"\b", r"\y")
        assert r"\b" not in td.OSCARS_STRUCTURAL_PG
        assert r"\b" not in td.AI_ENTITY_PG


class TestOscarsEdition:
    # case 4
    def test_prior_edition_tickers_are_other_edition_while_still_open(self):
        actor = kalshi(109566, "KXOSCARACTO-26", "Oscar for Best Actor?")
        guests = kalshi(109303, "KXOSCARGUESTS-26", "Who will attend the Oscars?")
        for m in (actor, guests):
            d = oscars(m)
            assert (d.outcome, d.reason) == ("excluded", td.OTHER_EDITION)
            assert m.status == "open"

    # case 5
    def test_best_picture_both_venues_admitted_and_not_folded(self):
        k = kalshi(6173044, "KXOSCARPIC-27", "Oscar for Best Picture?",
                   resolution_date=PLACEHOLDER_2027)
        p = mk(57313556, "Oscars 2027: Best Picture Winner",
               resolution_date=datetime(2027, 3, 15, tzinfo=timezone.utc))
        dk, dp = oscars(k), oscars(p)
        assert (dk.outcome, dk.reason, dk.edge_class) == ("admitted", td.ADMITTED_TICKER_EDITION, "title")
        assert (dp.outcome, dp.reason, dp.edge_class) == ("admitted", td.ADMITTED_TITLE_EDITION, "title")
        assert clause(dk, "edition")["input"] == {"year": 2027, "rule": "ticker_token"}
        # The placeholder neither decides nor disqualifies the edition.
        k_none = kalshi(6173044, "KXOSCARPIC-27", "Oscar for Best Picture?")
        assert oscars(k_none).reason == td.ADMITTED_TICKER_EDITION

    # case 6
    def test_nominations_are_members_in_their_own_class(self):
        k = kalshi(5165726, "KXOSCARNOMPIC-27", "Best Picture nominations?",
                   resolution_date=datetime(2027, 1, 22, tzinfo=timezone.utc))
        p = mk(27988771, "Oscars 2027: Best Picture Nominations",
               resolution_date=datetime(2027, 1, 22, tzinfo=timezone.utc))
        for m in (k, p):
            d = oscars(m)
            assert d.outcome == "admitted" and d.edge_class == "advancement"

    # case 7
    @pytest.mark.parametrize("market", [
        mk(115607, "Which film will get the most Oscar nominations at the 99th Academy Awards?"),
        kalshi(115607, "KXOSCARNOMMOST",
               "Which film will get the most Oscar nominations at the 99th Academy Awards?"),
    ])
    def test_ordinal_academy_awards_names_the_edition(self, market):
        d = oscars(market)
        assert (d.outcome, d.reason) == ("admitted", td.ADMITTED_TITLE_EDITION)
        assert clause(d, "edition")["input"] == {"year": 2027, "rule": "ordinal_academy_awards"}

    def test_ordinal_for_another_edition_is_other_edition(self):
        assert oscars(mk(990004, "Best Picture at the 98th Academy Awards?")).reason == td.OTHER_EDITION

    # case 8
    def test_resolution_date_alone_never_names_an_edition(self):
        m = mk(990005, "Oscars: Best Animated Feature Winner",
               resolution_date=datetime(2027, 3, 15, tzinfo=timezone.utc))
        d = oscars(m)
        assert (d.outcome, d.reason) == ("withheld", td.EDITION_UNKNOWN)

    def test_resolution_date_past_the_backstop_withholds_never_admits(self):
        m = mk(990006, "Oscars 2027: Best Director Winner",
               resolution_date=datetime(2028, 3, 1, tzinfo=timezone.utc))
        assert oscars(m).reason == td.EDITION_UNKNOWN

    # case 9
    def test_ticker_category_disagreeing_with_title_is_a_flag_not_an_exclusion(self):
        d = oscars(kalshi(59164593, "KXOSCARVIS-27", "Best Makeup and Hairstyling"))
        assert (d.outcome, d.edge_class) == ("admitted", "title")
        assert "venue_title_conflict" in d.evidence["flags"]
        agree = oscars(kalshi(6173044, "KXOSCARPIC-27", "Oscar for Best Picture?"))
        assert "venue_title_conflict" not in agree.evidence["flags"]
        assert clause(agree, "venue_title_conflict")["result"] == "agree"

    def test_a_nominations_row_is_never_recorded_as_agreeing(self):
        # Clause 5 checks a category row's title only; anything else is unchecked,
        # never a claimed agreement (Authority review 5964991446, item 3).
        d = oscars(kalshi(990009, "KXOSCARNOMPIC-27", "Best Actor nominations?"))
        assert d.edge_class == "advancement"
        assert clause(d, "venue_title_conflict") == {
            "clause": "venue_title_conflict", "input": "PIC", "result": "unchecked"}

    def test_novelty_is_a_side_question_member(self):
        d = oscars(kalshi(990007, "KXOSCARGUESTS-27", "Who will attend the Oscars?"))
        assert (d.outcome, d.edge_class) == ("admitted", "side_question")

    def test_evidence_carries_every_clause_and_the_inputs(self):
        d = oscars(mk(57313556, "Oscars 2027: Best Picture Winner"))
        assert [c["clause"] for c in d.evidence["clauses"]] == [
            "ceremony", "category_gate", "edition", "class"]
        assert d.evidence["inputs"]["id"] == 57313556
        assert set(d.evidence["inputs"]) >= {
            "external_id", "source", "llm_sport_category", "canonical_market_key",
            "resolution_date", "name"}
        assert d.reason in td.DECISION_REASONS and d.rule_version == "oscars-edition@1"


class TestOscarsFiniteHasNoRetention:
    # case 20 (decide half)
    def test_settled_long_ago_and_unknown_settle_time_are_admitted_on_every_pass(self):
        k = kalshi(990010, "KXOSCARNOMPIC-27", "Best Picture nominations?",
                   status="resolved", settled_at=NOW - timedelta(days=20))
        p = mk(990011, "Oscars 2027: Best Original Song Winner",
               status="resolved", settled_at=None)
        for now in (NOW, NOW + timedelta(days=30), NOW + timedelta(days=400)):
            for m in (k, p):
                d = oscars(m, now=now)
                assert d.outcome == "admitted", (m.id, now, d.reason)
                assert not any(c["clause"] == "retention" for c in d.evidence["clauses"])

    def test_finite_definition_can_never_emit_a_retention_reason(self):
        rows = [
            kalshi(1, "KXOSCARPIC-27", "Oscar for Best Picture?", status="resolved",
                   settled_at=NOW - timedelta(days=d))
            for d in (0, 13, 15, 365)
        ] + [kalshi(2, "KXOSCARPIC-27", "Oscar for Best Picture?", status="resolved")]
        for m in rows:
            assert oscars(m).reason not in td.CONTINUING_ONLY_REASONS


class TestVenueEventTitle:
    """case 23 (R-6): each Polymarket child decides on its own row."""

    TITLE = "Oscars 2027: Best Picture Winner"

    def rows(self):
        parent = mk(700, self.TITLE)
        kids = [mk(701 + i, f"Will {film} win Best Picture?", metadata={"event_title": self.TITLE})
                for i, film in enumerate(["Hamnet", "Wicked", "Marty Supreme"])]
        untitled = mk(704, "Will Sinners win Best Picture?")
        prior = mk(705, "Oscars 2026: Will Anora win Best Picture?",
                   metadata={"event_title": self.TITLE})
        return parent, kids, untitled, prior

    def test_children_decided_on_their_own_rows(self):
        parent, kids, untitled, prior = self.rows()
        assert oscars(parent).reason == td.ADMITTED_TITLE_EDITION
        for kid in kids:
            d = oscars(kid)
            assert (d.outcome, d.reason, d.edge_class) == (
                "admitted", td.ADMITTED_VENUE_EVENT_EDITION, "title")
            assert d.evidence["fields"] == {"ceremony": "event_title", "edition": "event_title"}
        assert oscars(untitled).reason == td.NOT_THIS_CEREMONY
        d = oscars(prior)
        assert d.reason == td.OTHER_EDITION
        assert "venue_title_conflict" in d.evidence["flags"]
        assert d.evidence["fields"]["edition"] == "name"

    def test_row_order_changes_no_outcome(self):
        parent, kids, untitled, prior = self.rows()
        rows = [parent, *kids, untitled, prior]
        base = {m.id: (oscars(m).outcome, oscars(m).reason) for m in rows}
        rng = random.Random(9935)
        for _ in range(5):
            rng.shuffle(rows)
            assert {m.id: (oscars(m).outcome, oscars(m).reason) for m in rows} == base

    def test_name_naming_another_ceremony_wins_over_the_event_title(self):
        m = mk(706, "Grammys 2027: Will Wicked win a Grammy?", metadata={"event_title": self.TITLE})
        d = oscars(m)
        assert d.reason == td.NOT_THIS_CEREMONY
        assert "venue_title_conflict" in d.evidence["flags"]

    def test_event_title_still_needs_its_own_category_gate(self):
        m = mk(707, "Will Hamnet win Best Picture?", cat="sports",
               metadata={"event_title": self.TITLE})
        assert oscars(m).reason == td.WRONG_CATEGORY

    def test_untitled_child_leaves_the_awards_bundle_without_a_ref(self):
        parent, kids, untitled, _ = self.rows()
        admitted = frozenset(m.id for m in (parent, *kids, untitled) if oscars(m).admitted)
        c = CandidateContainer(1, "oscars-2027", admitted, "published")
        target, reason = resolve_collection_target(
            "polymarket:700", [parent.id, kids[0].id, untitled.id], [c])
        assert target is None and reason == td.PREVIEW_SPANS_COLLECTIONS


# ---------------------------------------------------------------------------
# ai-subject@2
# ---------------------------------------------------------------------------


class TestAiEntity:
    # case 1 (pure half)
    def test_openai_ipo_is_an_ai_member(self):
        d = ai(mk(13791997, "OpenAI IPO before 2027?", cat="economics"))
        assert (d.outcome, d.reason, d.edge_class) == ("admitted", td.ADMITTED_ENTITY_SIGNAL, "side_question")

    # case 2
    def test_claude_monet_is_a_false_friend_and_claude_6_is_admitted(self):
        monet = ai(mk(990020, "Claude Monet's artwork break auction record?", cat="culture"))
        debussy = ai(mk(990021, "Claude Debussy streams top 1B?", cat="tech"))
        claude6 = ai(kalshi(61461524, "KXCLAUDE-CLAUDE6", "Claude 6 released before 2027?", cat="tech"))
        assert monet.reason == td.LEXICAL_FALSE_FRIEND and debussy.reason == td.LEXICAL_FALSE_FRIEND
        assert (claude6.outcome, claude6.reason) == ("admitted", td.ADMITTED_ENTITY_SIGNAL)

    def test_kalshi_entity_stem_is_the_second_signal_for_a_miscategorised_row(self):
        d = ai(kalshi(31835408, "KXOPUS48Y-27", "Claude Opus 4.8 released this year?", cat="crypto"))
        assert d.reason == td.ADMITTED_ENTITY_SIGNAL
        assert clause(d, "second_signal")["input"] == {"kalshi_entity_stem": "KXOPUS"}

    def test_entity_with_no_second_signal_is_wrong_category(self):
        assert ai(mk(990022, "Will Grok beat ChatGPT downloads?", cat="sports")).reason == td.WRONG_CATEGORY

    def test_model_names_with_suffixes_and_plurals_are_admitted_and_gathered(self):
        # A trailing word boundary after `gpt-?\d` / `ai model` dropped these rows
        # silently: no decision row, no evidence (Authority review 5964991446, item 1).
        gather = re.compile(td.AI_ENTITY_PG.replace(r"\y", r"\b"), re.IGNORECASE)
        for i, name in enumerate([
            "Will GPT-4o top LMArena?",
            "Top AI models by Oct 31",
            "GPT-4.5 released before 2027?",
            "Best AI model at the end of October?",
        ]):
            d = ai(mk(990040 + i, name, cat="tech"))
            assert (d.outcome, d.reason) == ("admitted", td.ADMITTED_ENTITY_SIGNAL), name
            assert gather.search(name), name

    def test_decide_and_gather_share_one_term_list(self):
        terms = td._AI_ENTITY_TERMS
        assert td.AI_ENTITY_PG == r"\y(" + "|".join(terms) + r")\y"
        decide_terms = td._AI_ENTITY_RE.pattern[len(r"\b("):-len(r")\b")].split("|")
        assert decide_terms == [t for t in terms if t != "gemini"]

    def test_a_row_with_no_entity_term_is_not_this_subject(self):
        assert ai(mk(990023, "Fed cuts rates in December?", cat="economics")).reason == td.NOT_THIS_SUBJECT

    # case 15
    def test_gemini_counts_only_with_adjacent_ai_context(self):
        xrp = ai(kalshi(990030, "KXGEMINI-XRP", "Will Gemini list XRP? (app)", cat="economics"))
        assert (xrp.outcome, xrp.reason) == ("excluded", td.LEXICAL_FALSE_FRIEND)
        for i, name in enumerate([
            "Google Gemini 3 released before 2027?",
            "Gemini Pro tops LMArena in October?",
            "Gemini 2.5 Flash price cut?",
        ]):
            d = ai(mk(990031 + i, name, cat="tech"))
            assert (d.outcome, d.reason) == ("admitted", td.ADMITTED_ENTITY_SIGNAL), name

    def test_gemini_context_elsewhere_in_the_name_does_not_count(self):
        d = ai(mk(990035, "Gemini exchange app adds pro tier for XRP?", cat="economics"))
        assert d.reason == td.LEXICAL_FALSE_FRIEND


class TestAiRetention:
    """case 14: the clock is settled_at; resolution_date never moves an outcome."""

    def rows(self):
        winner = SimpleNamespace(is_winner=True, resolution_source="kalshi")
        exclusive = {"shape": {"expected_winners": 1}}
        return [
            (mk(1, "OpenAI releases GPT-6 in 2026?", cat="tech", status="resolved",
                settled_at=NOW - timedelta(days=3)), "admitted", td.ADMITTED_ENTITY_SIGNAL),
            (mk(2, "Anthropic raises at $300B?", cat="tech", status="resolved",
                settled_at=NOW - timedelta(days=20)), "excluded", td.RESOLVED_BEYOND_RETENTION),
            (kalshi(3, "KXCLAUDE-SONNET5", "Claude Sonnet 5 before July?", cat="tech",
                    status="open", settled_at=None, metadata=exclusive, outcomes=[winner]),
             "excluded", td.RESOLVED_SETTLE_TIME_UNKNOWN),
            (mk(4, "DeepSeek R3 released?", cat="tech", status="resolved", settled_at=None),
             "excluded", td.RESOLVED_SETTLE_TIME_UNKNOWN),
        ]

    @pytest.mark.parametrize("resolution_date", [
        None, NOW - timedelta(days=400), NOW - timedelta(days=5), NOW + timedelta(days=1),
        NOW + timedelta(days=400), PLACEHOLDER_2027,
    ])
    def test_four_outcomes_and_resolution_date_changes_none(self, resolution_date):
        for m, outcome, reason in self.rows():
            m.resolution_date = resolution_date
            d = ai(m)
            assert (d.outcome, d.reason) == (outcome, reason), (m.id, resolution_date)

    def test_evidence_names_the_settled_arm(self):
        rows = self.rows()
        assert clause(ai(rows[0][0]), "retention")["input"]["settled_arm"] == "status_resolved"
        assert clause(ai(rows[2][0]), "retention")["input"]["settled_arm"] == "market_reads_settled"

    def test_open_unsettled_ai_row_is_admitted(self):
        d = ai(mk(5, "ChatGPT tops App Store on Friday?", cat="tech"))
        assert d.reason == td.ADMITTED_ENTITY_SIGNAL
        assert clause(d, "retention")["result"] == "open"

    def test_retention_boundary_is_fourteen_days_inclusive(self):
        edge = mk(6, "xAI raises again?", cat="tech", status="resolved",
                  settled_at=NOW - timedelta(days=14))
        past = mk(7, "xAI raises again?", cat="tech", status="resolved",
                  settled_at=NOW - timedelta(days=14, seconds=1))
        assert ai(edge).reason == td.ADMITTED_ENTITY_SIGNAL
        assert ai(past).reason == td.RESOLVED_BEYOND_RETENTION

    # case 21 (decide half): the prior-decision arm re-decides an aged-out member.
    def test_previously_admitted_member_retires_by_rule_as_the_clock_moves(self):
        m = mk(8, "OpenAI device ships in 2026?", cat="tech", status="resolved",
               settled_at=NOW - timedelta(days=6))
        assert ai(m).reason == td.ADMITTED_ENTITY_SIGNAL
        assert ai(m, now=NOW + timedelta(days=14)).reason == td.RESOLVED_BEYOND_RETENTION


# ---------------------------------------------------------------------------
# §4 gather arms — compiled, never executed (cases 20/21, population half).
# ---------------------------------------------------------------------------


def _sql(stmt):
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestCandidatePopulation:
    def test_finite_population_has_no_status_or_time_cutoff(self):
        arms = candidate_population(OSCARS_2027, container_id=11, now=NOW)
        assert set(arms) == {"kalshi_ticker_family", "polymarket_structural_title", "prior_decision"}
        for name in ("kalshi_ticker_family", "polymarket_structural_title"):
            sql = _sql(arms[name]).lower()
            for banned in ("settled_at", "status", "created_at", "resolution_date"):
                assert banned not in sql, (name, banned)
        # Left-anchored ticker family (literal binds render `%` as the
        # paramstyle-escaped `%%`).
        assert "external_id like 'kxoscar%" in _sql(arms["kalshi_ticker_family"]).lower()
        pm = _sql(arms["polymarket_structural_title"])
        assert "~*" in pm and "event_title" in pm and r"\y" in pm

    def test_finite_population_ignores_the_clock(self):
        a = candidate_population(OSCARS_2027, container_id=11, now=NOW)
        b = candidate_population(OSCARS_2027, container_id=11, now=NOW + timedelta(days=365))
        assert {k: _sql(v) for k, v in a.items()} == {k: _sql(v) for k, v in b.items()}

    def test_ai_population_retires_only_through_settled_at(self):
        arms = candidate_population(AI, container_id=12, now=NOW)
        assert set(arms) == {"open_entity", "resolved_within_retention", "prior_decision"}
        resolved = _sql(arms["resolved_within_retention"])
        assert "settled_at >=" in resolved
        assert "'2026-09-19 12:00:00+00:00'" in resolved  # NOW − 14 days
        assert "resolution_date" not in resolved
        assert "settled_at" not in _sql(arms["open_entity"])

    def test_prior_decision_arm_is_scoped_to_the_container_and_markets(self):
        for defn, cid in ((OSCARS_2027, 11), (AI, 12)):
            sql = _sql(candidate_population(defn, container_id=cid, now=NOW)["prior_decision"])
            assert "container_member_decisions" in sql
            assert f"container_id = {cid}" in sql and "child_type = 'market'" in sql

    def test_import_executes_nothing_and_loads_no_model_or_consumer(self):
        code = (
            "import sys; import app.utils.theme_definitions as t; "
            "bad = [m for m in ('app.models.models', 'app.utils.discover_bundles', "
            "'app.routes.feed', 'app.tasks', 'app.database') if m in sys.modules]; "
            "print(bad)"
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND,
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == "[]"


# ---------------------------------------------------------------------------
# §5 steps 0–3: resolve_collection_target (cases 17, 18; v3.2 swings step 0).
# ---------------------------------------------------------------------------


def _ipos_registry():
    ipos = ThemeDefinition(
        subject="ipos", scope="continuing", rule_version="ipos-test@1", container_kind="theme",
        category="economics", display_name="IPOs", decider=lambda *a, **k: None,
        population=lambda *a, **k: {})
    return {**REGISTRY, "ipos": ipos}


IPO_PACK = [13791997, 13791998]
IPO_MAP = {**FEED_KEY_MAP, "story:ipo_markets": "ipos"}


def cc(cid, slug, ids, state="published"):
    return CandidateContainer(cid, slug, frozenset(ids), state)


class TestResolveAwardsAndSwings:
    OSCAR_IDS = [6173044, 57313556, 5165726]

    # case 17
    def test_awards_bundle_all_oscars_resolves_by_the_no_map_arm(self):
        osc = cc(1, "oscars-2027", self.OSCAR_IDS)
        target, reason = resolve_collection_target("polymarket:42", self.OSCAR_IDS, [osc])
        assert (target, reason) == (osc, None)

    def test_awards_bundle_with_a_grammys_member_has_no_ref(self):
        osc = cc(1, "oscars-2027", self.OSCAR_IDS)
        target, reason = resolve_collection_target("polymarket:42", [*self.OSCAR_IDS, 444], [osc])
        assert target is None and reason == td.PREVIEW_SPANS_COLLECTIONS

    def test_mixed_swings_bundle_is_refused(self):
        # An extra, never the control: it fails at |C| != 1 with or without step 0.
        osc = cc(1, "oscars-2027", self.OSCAR_IDS)
        aic = cc(2, "ai", IPO_PACK)
        target, reason = resolve_collection_target("swings", [6173044, 13791997], [osc, aic])
        assert target is None and reason == td.SWINGS_NOT_A_COLLECTION

    # case 17's swings arm (v3.2) — the discriminating control. Root decision:
    # swings is refused even when every member is AI-only and
    # exactly one container (any state) admits them all.
    @pytest.mark.parametrize("state", ["published", "unpublished", "withdrawn"])
    def test_all_ai_swings_with_a_sole_candidate_is_refused(self, state):
        aic = cc(2, "ai", [*IPO_PACK, 61461524], state)
        target, reason = resolve_collection_target("swings", [61461524, 13791997], [aic])
        assert target is None and reason == td.SWINGS_NOT_A_COLLECTION

    def test_parity_control_same_all_ai_preview_resolves_when_not_swings(self):
        """Without the explicit refusal the sole-candidate arm WOULD target ai:
        the same preview and candidates under any other key give the ref."""
        aic = cc(2, "ai", [*IPO_PACK, 61461524])
        assert resolve_collection_target("story:unmapped_key", [61461524, 13791997], [aic]) == (aic, None)
        assert resolve_collection_target("story:ai", [61461524, 13791997], [aic]) == (aic, None)

    def test_empty_preview_never_resolves(self):
        aic = cc(2, "ai", IPO_PACK)
        assert resolve_collection_target("story:ai", [], [aic]) == (None, td.PREVIEW_EMPTY)


class TestResolveIpoPack:
    """case 18 = Discover R4a–R4e, with a test-only ipos definition and map."""

    def go(self, feed_key_map, candidates):
        return resolve_collection_target(
            "story:ipo_markets", IPO_PACK, candidates,
            registry=_ipos_registry(), feed_key_map=feed_key_map)

    def test_r4a_mapped_published_target(self):
        ipos, aic = cc(3, "ipos", IPO_PACK), cc(2, "ai", IPO_PACK)
        assert self.go(IPO_MAP, [aic, ipos]) == (ipos, None)

    def test_r4b_no_map_entry_two_candidates(self):
        ipos, aic = cc(3, "ipos", IPO_PACK), cc(2, "ai", IPO_PACK)
        assert self.go(FEED_KEY_MAP, [aic, ipos]) == (None, td.NO_MAP_ENTRY_AMBIGUOUS)

    def test_r4c_mapped_target_unpublished_never_redirects_to_ai(self):
        ipos = cc(3, "ipos", IPO_PACK, "unpublished")
        aic = cc(2, "ai", IPO_PACK, "published")
        for order in ([aic, ipos], [ipos, aic]):
            target, reason = self.go(IPO_MAP, order)
            # The intended target is ipos; step 4 (P2) removes it as
            # `target_unpublished`. It is never ai.
            assert target is ipos and reason is None
            assert target.publication_state == "unpublished"

    def test_r4d_mapped_target_absent_never_falls_back(self):
        aic = cc(2, "ai", IPO_PACK)
        ipos_partial = cc(3, "ipos", IPO_PACK[:1])
        assert self.go(IPO_MAP, [aic]) == (None, td.MAPPED_TARGET_ABSENT)
        assert self.go(IPO_MAP, [aic, ipos_partial]) == (None, td.MAPPED_TARGET_ABSENT)

    def test_r4e_no_map_single_candidate_any_state(self):
        for state in ("published", "unpublished"):
            aic = cc(2, "ai", IPO_PACK, state)
            assert self.go(FEED_KEY_MAP, [aic]) == (aic, None)

    def test_candidates_are_never_filtered_by_publication(self):
        """No map entry, ai UNPUBLISHED and ipos published both admit the pack:
        |C| = 2 → no ref. A publication filter on C would leave ipos as a sole
        survivor and redirect the link."""
        aic = cc(2, "ai", IPO_PACK, "unpublished")
        ipos = cc(3, "ipos", IPO_PACK, "published")
        assert self.go(FEED_KEY_MAP, [aic, ipos]) == (None, td.NO_MAP_ENTRY_AMBIGUOUS)

    def test_mapped_subject_held_by_two_containers_is_ambiguous(self):
        a = cc(5, "oscars-2027", IPO_PACK)
        b = cc(6, "oscars-2031", IPO_PACK)
        out = resolve_collection_target(
            "story:test_awards", IPO_PACK, [a, b],
            feed_key_map={"story:test_awards": "oscars"})
        assert out == (None, td.MAPPED_TARGET_AMBIGUOUS)

    def test_no_map_sole_candidate_with_a_non_theme_slug_fails_closed(self):
        odd = cc(7, "nfl-2026-week-04", IPO_PACK)
        assert resolve_collection_target("story:x", IPO_PACK, [odd]) == (None, td.TARGET_SLUG_NOT_THEME)


def test_9936_the_pass_only_reasons_are_pinned_and_never_decided():
    """Two reasons only the pass writes (#9936): ``decide()`` keeps its verdict
    on the row alone, so an unknown-time row is still excluded there."""
    assert td.ADMITTED_SETTLE_TIME_PENDING == "admitted_settle_time_pending"
    assert td.ADMITTED_SETTLE_TIME_PENDING in td.ADMITTED_REASONS
    assert td.MEMBER_ROW_ABSENT == "member_row_absent"
    assert td.MEMBER_ROW_ABSENT in td.EXCLUDED_REASONS
    assert td.MEMBER_ROW_ABSENT != "row_missing"  # the snapshot withhold, a different fact
    assert td.RETAIN_IF_MEMBER_REASONS == frozenset({td.RESOLVED_SETTLE_TIME_UNKNOWN})
    unknown = ai(mk(5, "DeepSeek R3 released?", cat="tech", status="resolved", settled_at=None))
    assert (unknown.outcome, unknown.reason, unknown.edge_class) == (
        "excluded", td.RESOLVED_SETTLE_TIME_UNKNOWN, None)
    assert unknown.rule_version == "ai-subject@2"


def test_reason_vocabulary_is_closed_and_disjoint():
    groups = [td.ADMITTED_REASONS, td.EXCLUDED_REASONS, td.WITHHELD_REASONS,
              td.HYDRATION_WITHHOLDS, td.RESOLVER_REASONS]
    seen: set[str] = set()
    for g in groups:
        assert not (seen & g)
        seen |= g
    assert td.CONTINUING_ONLY_REASONS <= td.EXCLUDED_REASONS


# ---------------------------------------------------------------------------
# §10.4 S0: the decision ledger declared once (no ORM model) + the vocabulary
# the P2 writer validates against. Pins only; nothing here touches a database.
# ---------------------------------------------------------------------------


def _ddl_columns():
    """``{name: sql_type}`` for every column line of ``CREATE_DECISIONS_SQL``."""
    body = td.CREATE_DECISIONS_SQL.split("(", 1)[1].rsplit(")", 1)[0]
    cols = {}
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.startswith("CONSTRAINT"):
            continue
        name, sql_type = line.split()[:2]
        cols[name] = sql_type
    return cols


def _varchar_len(sql_type):
    m = re.fullmatch(r"VARCHAR\((\d+)\)", sql_type)
    return int(m.group(1)) if m else None


class TestDecisionLedgerDDL:
    def test_the_core_clause_and_the_ddl_name_the_same_columns(self):
        assert td.DECISIONS_TABLE == "container_member_decisions"
        table = td.decisions_table()
        assert table.name == td.DECISIONS_TABLE
        assert set(table.c.keys()) == set(_ddl_columns())
        assert len(_ddl_columns()) == 12

    def test_every_varchar_bound_agrees_between_ddl_and_clause(self):
        table = td.decisions_table()
        bounded = {n: _varchar_len(t) for n, t in _ddl_columns().items() if _varchar_len(t)}
        assert bounded == {"child_type": 16, "outcome": 12, "reason": 40, "rule_version": 32}
        for name, length in bounded.items():
            assert table.c[name].type.length == length, name

    def test_evidence_is_jsonb_on_both_sides(self):
        from sqlalchemy.dialects.postgresql import JSONB

        assert _ddl_columns()["evidence"] == "JSONB"
        assert isinstance(td.decisions_table().c.evidence.type, JSONB)

    def test_outcomes_equal_the_check_constraint(self):
        m = re.search(r"CHECK \(outcome IN \(([^)]*)\)\)", td.CREATE_DECISIONS_SQL)
        assert m is not None
        assert {v.strip().strip("'") for v in m.group(1).split(",")} == td.OUTCOMES

    def test_every_written_value_fits_its_column(self):
        widths = {n: _varchar_len(t) for n, t in _ddl_columns().items()}
        assert all(len(r) <= widths["reason"] for r in td.DECISION_REASONS)
        assert all(len(o) <= widths["outcome"] for o in td.OUTCOMES)
        assert all(len(d.rule_version) <= widths["rule_version"] for d in REGISTRY.values())
        assert len("market") <= widths["child_type"]
        # The withdrawn exclusion is a decision-row reason (§10.4 semantics 4).
        assert td.CONTAINER_MEMBER_WITHDRAWN in td.DECISION_REASONS

    def test_the_one_member_key_is_unique(self):
        assert "CONSTRAINT uq_cmd_member UNIQUE (container_id, child_type, child_id)" in (
            td.CREATE_DECISIONS_SQL
        )

    def test_statements_are_idempotent_additive_and_never_concurrent(self):
        assert td.UPGRADE_STATEMENTS == (td.CREATE_DECISIONS_SQL, td.CREATE_DECISIONS_INDEX_SQL)
        for stmt in td.UPGRADE_STATEMENTS:
            assert "IF NOT EXISTS" in stmt
            assert "CONCURRENTLY" not in stmt.upper()  # gotcha #31
            assert "ALTER" not in stmt.upper() and "DROP" not in stmt.upper()
        assert td.DOWNGRADE_STATEMENTS == ("DROP TABLE IF EXISTS container_member_decisions",)

    def test_the_prior_decision_arm_reads_the_shared_clause(self, monkeypatch):
        from sqlalchemy import column, table

        monkeypatch.setattr(
            td, "decisions_table",
            lambda: table("shared_clause_probe", column("container_id"),
                          column("child_type"), column("child_id")),
        )
        sql = _sql(candidate_population(AI, container_id=12, now=NOW)["prior_decision"])
        assert "shared_clause_probe" in sql and "container_member_decisions" not in sql


MIGRATION = BACKEND / "alembic" / "versions" / "ce9935000002_theme_member_decisions.py"


def _load_migration():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ce9935000002_probe", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheC2Migration:
    """C2 (D45): the migration runs S0's statements, follows the head it was
    written on, and leaves exactly one head — the #9651 precedent."""

    def test_its_id_fits_and_it_follows_the_head_it_was_written_on(self):
        text = MIGRATION.read_text()
        revision = re.search(r'^revision = "([^"]+)"', text, re.M).group(1)
        down = re.search(r'^down_revision = "([^"]+)"', text, re.M).group(1)
        assert revision == "ce9935000002"
        assert len(revision) <= 32  # gotcha #1
        assert down == "serie_a_femminile_sport"

    def test_it_is_the_only_head(self):
        revisions, parents = set(), set()
        for path in (BACKEND / "alembic" / "versions").glob("*.py"):
            text = path.read_text()
            rev = re.search(r"^revision\s*(?::\s*str)?\s*=\s*['\"]([^'\"]+)", text, re.M)
            down = re.search(r"^down_revision[^=]*=\s*(.+)$", text, re.M)
            if rev:
                revisions.add(rev.group(1))
                parents.update(re.findall(r"['\"]([^'\"]+)['\"]", down.group(1) if down else ""))
        # ONE head, not THIS head: a successor migration must not read as a
        # branchpoint here. This revision being in the chain is asserted beside it.
        heads = revisions - parents
        assert len(heads) == 1, f"expected a single Alembic head, got {heads}"
        assert heads == {"ce9935000002"} or "ce9935000002" in parents

    def test_it_runs_the_helpers_statements_by_identity_not_a_copy(self):
        text = MIGRATION.read_text()
        for ddl in ("CREATE TABLE", "CREATE INDEX", "DROP TABLE", "container_member_decisions ("):
            assert ddl not in text
        module = _load_migration()
        assert module.UPGRADE_STATEMENTS is td.UPGRADE_STATEMENTS
        assert module.DOWNGRADE_STATEMENTS is td.DOWNGRADE_STATEMENTS

    def test_upgrade_and_downgrade_execute_exactly_those_statements_in_order(self, monkeypatch):
        module = _load_migration()
        executed: list[str] = []
        monkeypatch.setattr(module, "op", SimpleNamespace(execute=executed.append))
        module.upgrade()
        assert executed == list(td.UPGRADE_STATEMENTS)
        executed.clear()
        module.downgrade()
        assert executed == list(td.DOWNGRADE_STATEMENTS)


class TestWriterVocabulary:
    def test_every_registered_container_kind_is_writable(self):
        from app.utils.container_graph import validate_container_kind

        for defn in REGISTRY.values():
            assert validate_container_kind(defn.container_kind) == defn.container_kind
        assert validate_container_kind("theme") == "theme"

    def test_theme_rule_is_an_edge_source(self):
        from app.utils.container_graph import validate_edge_source

        assert validate_edge_source("theme_rule") == "theme_rule"

    @pytest.mark.parametrize("edge_class", ["title", "advancement", "side_question"])
    def test_every_class_decide_can_emit_is_a_contains_class(self, edge_class):
        from app.utils.container_graph import validate_edge_kind_and_class

        assert validate_edge_kind_and_class("contains", edge_class) == ("contains", edge_class)
