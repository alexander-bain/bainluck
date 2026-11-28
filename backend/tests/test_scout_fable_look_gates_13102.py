"""Tests for Fable's Thu 1:15 AM scout look gates (#13102, rules a-d).

Verifies:
(a) Graded + public set loading, >=50% member / name overlap rejection, and newest grade carry.
(b) Kicker never cut mid-word (<=32 chars kept whole, >32 chars omitted as "").
(c) No blurb/name/kicker/footer refers to a market as a "question" / "questions".
(d) Sets mixing yes/no rows with ladder/score rows state each ladder row's answer or are not staged.
(e) Full before-and-after replay of Thu Nov 26's 10 staged sets (10/10 before -> 1/10 Snow Day Slopes after).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import llm_request
from app.services.llm_request import MemoryBudgetLedger
from app.utils.discover_fun_scout import (
    SCOUT_KICKER_MAX_CHARS,
    ScoutKnownSet,
    ScoutMarketRow,
    ScoutProposedSet,
    ScoutTaggedMarket,
    ScoutUncoveredFamily,
    build_fun_scout_set_producer,
    build_scout_rule_file_definition,
    check_scout_mixed_ladder_answers,
    check_scout_no_question_word,
    classify_scout_member_shape,
    find_scout_known_set_overlap,
    load_db_graded_scout_sets,
    load_graded_scout_sets,
    load_known_sets_for_scout,
    load_public_scout_sets,
    normalize_scout_kicker,
    normalize_scout_row_answers,
    run_nightly_fun_scout,
    validate_scout_proposed_set,
)
from app.utils.roundup_containers import RoundupMembers, RoundupProducer
from app.utils.scout_morning_deck import _sanitize_card_entry, build_scout_morning_deck

FROZEN_NOW = datetime(2026, 11, 26, 9, 0, tzinfo=timezone.utc)


def _mk(
    mid: int,
    title: str,
    *,
    source: str = "kalshi",
    category: str = "culture",
    volume: float = 50_000.0,
) -> ScoutMarketRow:
    return ScoutMarketRow(
        market_id=mid,
        source=source,
        title=title,
        status="open",
        category=category,
        resolution_date=FROZEN_NOW + timedelta(days=90),
        volume=volume,
    )


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._items))


class _FakeDB:
    def __init__(self, items):
        self._items = list(items)

    async def execute(self, _stmt):
        return _FakeResult(self._items)


class _FakeRedis:
    def __init__(self, initial=None):
        self.store: dict[str, str] = dict(initial or {})

    def get(self, key):
        return self.store.get(key)

    def set(self, key, val, ex=None):
        self.store[key] = val

    def mget(self, keys):
        return [self.store.get(k) for k in keys]

    def incrbyfloat(self, key, delta):
        nxt = float(self.store.get(key) or 0.0) + float(delta)
        self.store[key] = str(nxt)
        return nxt

    def expire(self, _key, _ttl):
        return True


def _nov_26_catalog_and_proposals() -> tuple[
    list[ScoutMarketRow],
    list[ScoutTaggedMarket],
    list[tuple[ScoutProposedSet, str]],
]:
    """Build exact 2026-11-26 scout markets plus raw pre-sliced LLM proposals."""
    rows = [
        _mk(108218, "Will Elon Musk visit Mars in his lifetime?", source="kalshi", category="elon musk", volume=126_757),
        _mk(52755879, "Elon Musk net worth on December 31, 2026", source="kalshi", category="elon musk", volume=99_226),
        _mk(109490, "Elon Musk out as Tesla CEO before 2027?", source="kalshi", category="elon musk", volume=93_222),
        _mk(113252, "Will Elon Musk announce Presidential run before 2027?", source="polymarket", category="elon musk", volume=28_426),
        _mk(68210398, "Elon Musk meets with Putin by...?", source="polymarket", category="elon musk", volume=15_549),
        _mk(109316, "Will Elon Musk buy a major sports team before 2027?", source="kalshi", category="elon musk", volume=11_417),
        _mk(113658, "Katy Perry and Justin Trudeau engaged by end of 2026?", source="polymarket", category="engagements", volume=65_824),
        _mk(109392, "Jaxson Dart and Madison Beer: Engaged before 2027?", source="kalshi", category="engagements", volume=21_116),
        _mk(129225, "Megan Thee Stallion and Klay Thompson engaged in 2026?", source="polymarket", category="engagements", volume=20_389),
        _mk(114493, "Kylie Jenner and Timothée Chalamet engaged in 2026?", source="polymarket", category="engagements", volume=14_657),
        _mk(56799671, "Kim Kardashian and Lewis Hamilton engaged in 2026?", source="polymarket", category="engagements", volume=10_372),
        _mk(109324, "Stranger Things: New episode this year?", source="kalshi", category="long-awaited", volume=2_526_794),
        _mk(59693617, "When will Drake release a new album?", source="kalshi", category="long-awaited", volume=127_647),
        _mk(113343, "Will Half-Life 3 be announced before 2027?", source="polymarket", category="long-awaited", volume=125_751),
        _mk(108494, "When will Elder Scrolls VI be released?", source="kalshi", category="long-awaited", volume=40_646),
        _mk(25924930, "When will Kendrick Lamar release a new album?", source="kalshi", category="long-awaited", volume=22_930),
        _mk(113426, 'Will George R. R. Martin announce "The Winds of Winter" in 2026?', source="polymarket", category="long-awaited", volume=17_979),
        _mk(63336234, '"GTA VI" Metacritic Score?', source="polymarket", category="long-awaited", volume=452_640),
        _mk(69851943, "GTA VI Online released by...?", source="polymarket", category="long-awaited", volume=162_377),
        _mk(67717832, "GTA VI on PC in what month?", source="polymarket", category="long-awaited", volume=97_145),
        _mk(66639375, "Another GTA VI trailer released by...?", source="polymarket", category="long-awaited", volume=47_561),
        _mk(9997262, "Satoshi's identity be proven by...?", source="polymarket", category="long shots", volume=2_005_321),
        _mk(113701, "10.0 or above earthquake before 2027?", source="polymarket", category="long shots", volume=844_121),
        _mk(113700, "9.0 or above earthquake before 2027?", source="polymarket", category="long shots", volume=337_326),
        _mk(34191685, "Is Earth flat?", source="polymarket", category="long shots", volume=110_700),
        _mk(108294, "8.0 magnitude earthquake in Japan before 2030?", source="kalshi", category="long shots", volume=45_851),
        _mk(65536494, "Hexed · Rotten Tomatoes score", source="kalshi", category="movies", volume=86_603),
        _mk(67804442, "The Angry Birds Movie 3 · Rotten Tomatoes score", source="kalshi", category="movies", volume=85_015),
        _mk(67804441, "Jumanji: Open World · Rotten Tomatoes score", source="kalshi", category="movies", volume=66_866),
        _mk(67804494, "Violent Night 2 · Rotten Tomatoes score", source="kalshi", category="movies", volume=15_029),
        _mk(109633, "Next Superman film: Will Elon Musk be cast?", source="kalshi", category="movies", volume=27_262),
        _mk(108239, "Next Pirates of the Caribbean film: Will Johnny Depp be cast?", source="kalshi", category="movies", volume=26_168),
        _mk(58858756, "Miles Morales live-action film actor?", source="polymarket", category="movies", volume=18_889),
        _mk(68313448, "Who will be in the 2027 Big Game halftime show?", source="polymarket", category="super bowl culture", volume=120_978),
        _mk(69851900, "What songs will be played at the 2027 Big Game halftime show?", source="polymarket", category="super bowl culture", volume=61_606),
        _mk(52755798, "Which brands will advertise during the Big Game?", source="kalshi", category="super bowl culture", volume=33_522),
        _mk(69851899, "First song at 2027 Big Game Halftime Show?", source="polymarket", category="super bowl culture", volume=31_373),
        _mk(69851897, "Last song at 2027 Big Game Halftime Show?", source="polymarket", category="super bowl culture", volume=30_988),
        _mk(65536401, "Total snowfall in Big Sky in December 2026?", source="kalshi", category="white christmas", volume=80_604),
        _mk(67804428, "Park City Mountain snowfall total by December 24th", source="kalshi", category="white christmas", volume=17_177),
        _mk(67804432, "Mammoth Mountain snowfall total by December 24th", source="kalshi", category="white christmas", volume=12_773),
        _mk(113987, "Top Spotify Artist 2026", source="polymarket", category="year-end", volume=1_889_600),
        _mk(70733200, "Top Spotify Song 2026", source="polymarket", category="year-end", volume=381_435),
        _mk(57574931, "#2 Spotify Song 2026", source="polymarket", category="year-end", volume=223_883),
        _mk(27988658, "Top Spotify Album 2026", source="polymarket", category="year-end", volume=85_632),
        _mk(35961535, "#2 Spotify Artist 2026", source="polymarket", category="year-end", volume=85_193),
        _mk(35961536, "#3 Spotify Artist 2026", source="polymarket", category="year-end", volume=52_928),
    ]
    proposals_with_before_kicker = [
        (
            ScoutProposedSet(
                slug="elon-everything-everywhere",
                name="Elon Everything Everywhere",
                kicker="ONE MAN, SIX WILDLY DIFFERENT FUTURES",
                category="elon musk",
                why_better_together=(
                    "Mars trips, Tesla's CEO seat, a sports team, a presidential run, "
                    "a Putin meeting and his net worth show how big Musk's odds can get."
                ),
                look="bars",
                member_ids=(108218, 52755879, 109490, 113252, 68210398, 109316),
            ),
            "ONE MAN, SIX WILDLY DIFFERENT FU",
        ),
        (
            ScoutProposedSet(
                slug="ring-watch-2026",
                name="Ring Watch 2026",
                kicker="WHICH CELEBRITY COUPLES GET ENGAGED",
                category="engagements",
                why_better_together=(
                    "Five buzzy celebrity pairings go head to head on who actually "
                    "makes it to an engagement by the end of 2026."
                ),
                look="bars",
                member_ids=(113658, 109392, 129225, 114493, 56799671),
            ),
            "WHICH CELEBRITY COUPLES GET ENGA",
        ),
        (
            ScoutProposedSet(
                slug="will-it-ever-come-out",
                name="Will It Ever Come Out?",
                kicker="THE LONG WAIT, RANKED BY HOPE",
                category="long-awaited",
                why_better_together=(
                    "Half-Life 3, Elder Scrolls VI, The Winds of Winter, Stranger Things, "
                    "Drake and Kendrick all test how long fans can wait."
                ),
                look="bars",
                member_ids=(109324, 59693617, 113343, 108494, 25924930, 113426),
            ),
            "THE LONG WAIT, RANKED BY HOPE",
        ),
        (
            ScoutProposedSet(
                slug="gta-vi-watch",
                name="GTA VI Watch",
                kicker="TRAILERS, PORTS AND REVIEW SCORES",
                category="long-awaited",
                why_better_together=(
                    "The Metacritic score, another trailer, the PC month and the "
                    "online release together capture the whole GTA VI rollout."
                ),
                look="bars",
                member_ids=(63336234, 69851943, 67717832, 66639375),
            ),
            "TRAILERS, PORTS AND REVIEW SCORE",
        ),
        (
            ScoutProposedSet(
                slug="wild-cards",
                name="Wild Cards",
                kicker="LONG SHOTS WORTH A GROUP CHAT",
                category="long shots",
                why_better_together=(
                    "Satoshi's identity, a flat Earth and monster earthquakes are the "
                    "kind of far-fetched questions friends love arguing about."
                ),
                look="bars",
                member_ids=(9997262, 113701, 113700, 34191685, 108294),
            ),
            "LONG SHOTS WORTH A GROUP CHAT",
        ),
        (
            ScoutProposedSet(
                slug="fresh-or-rotten",
                name="Fresh or Rotten?",
                kicker="FOUR UPCOMING MOVIES, FOUR SCORES",
                category="movies",
                why_better_together=(
                    "Hexed, The Angry Birds Movie 3, Jumanji: Open World and Violent "
                    "Night 2 all face critics on Rotten Tomatoes."
                ),
                look="bars",
                member_ids=(65536494, 67804442, 67804441, 67804494),
            ),
            "FOUR UPCOMING MOVIES, FOUR SCORE",
        ),
        (
            ScoutProposedSet(
                slug="who-gets-the-part",
                name="Who Gets the Part?",
                kicker="WILD CASTING RUMORS",
                category="movies",
                why_better_together=(
                    "Elon in Superman, Johnny Depp in Pirates of the Caribbean and "
                    "Miles Morales in live action are casting questions people love to debate."
                ),
                look="bars",
                member_ids=(109633, 108239, 58858756),
            ),
            "WILD CASTING RUMORS",
        ),
        (
            ScoutProposedSet(
                slug="halftime-and-ads",
                name="Halftime and Ads",
                kicker="THE BIG GAME WITHOUT THE FOOTBALL",
                category="super bowl culture",
                why_better_together=(
                    "Halftime performers, the first and last songs, the setlist and "
                    "the advertisers make up the whole Big Game spectacle."
                ),
                look="bars",
                member_ids=(68313448, 69851900, 52755798, 69851899, 69851897),
            ),
            "THE BIG GAME WITHOUT THE FOOTBAL",
        ),
        (
            ScoutProposedSet(
                slug="snow-day-slopes",
                name="Snow Day Slopes",
                kicker="WHO GETS BURIED BY CHRISTMAS?",
                category="white christmas",
                why_better_together=(
                    "Big Sky, Park City and Mammoth go head to head on how much "
                    "snow piles up for the holidays."
                ),
                look="map",
                member_ids=(65536401, 67804428, 67804432),
            ),
            "WHO GETS BURIED BY CHRISTMAS?",
        ),
        (
            ScoutProposedSet(
                slug="spotify-2026-showdown",
                name="Spotify 2026 Showdown",
                kicker="WHO OWNS YOUR HEADPHONES THIS YEAR",
                category="year-end",
                why_better_together=(
                    "The top artist, runners-up, biggest song and top album tell the "
                    "full story of what 2026 sounded like on Spotify."
                ),
                look="bars",
                member_ids=(113987, 70733200, 57574931, 27988658, 35961535, 35961536),
            ),
            "WHO OWNS YOUR HEADPHONES THIS YE",
        ),
    ]
    tagged = [
        ScoutTaggedMarket(
            market_id=r.market_id,
            fun_group=r.category or "culture",
            reason=f"Live fun signal for {r.category}",
            is_fun_single=False,
        )
        for r in rows
    ]
    return rows, tagged, proposals_with_before_kicker


class TestKnownGradedAndPublicOverlapGate:
    """Rule (a): read graded + public sets, block >=50% or name overlap, carry newest grade."""

    def test_load_graded_and_public_sets(self):
        graded = load_graded_scout_sets()
        assert len(graded) == 80
        graded_dates = [ks.graded_at or "" for ks in graded]
        assert graded_dates == sorted(graded_dates, reverse=True)
        assert any(ks.name == "Fresh or Rotten?" and ks.grade == "Keep" for ks in graded)
        assert any(ks.slug == "wrapped-2026" and ks.grade == "Fix" for ks in graded)

        public = load_public_scout_sets()
        elon_public = [ks for ks in public if ks.slug == "machinery-elon-musk-side-quests"]
        assert len(elon_public) == 1
        assert {108218, 109490, 109316}.issubset(set(elon_public[0].member_ids))
        assert all(ks.source == "public" for ks in public)

    @pytest.mark.asyncio
    async def test_load_db_graded_sets_reads_morning_deck_key_fallback_and_v2(self):
        deck_date = "2026-11-26"
        rc = _FakeRedis(
            {
                f"bainluck:fun_scout:deck_key:{deck_date}": json.dumps(
                    {
                        "entries": {
                            "s01": {
                                "slug": "novel-morning-set",
                                "name": "Novel Morning Set",
                                "member_ids": [901, 902, 903],
                            }
                        }
                    }
                )
            }
        )
        db_rows = [
            SimpleNamespace(
                id=101,
                surface="grade_scout_morning_deck",
                market_name="s01",
                label="Drop",
                notes="Repeated",
                created_at=datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc),
                label_metadata={
                    "grade": "Drop",
                    "item_id": "s01",
                    "deck_date": deck_date,
                    "timestamp": "2026-11-26T12:00:00Z",
                },
            ),
            SimpleNamespace(
                id=100,
                surface="grade_sets_v2_deck",
                market_name="g1",
                label="Fix",
                notes="Live override",
                created_at=datetime(2026, 11, 26, 11, 0, tzinfo=timezone.utc),
                label_metadata={
                    "grade": "Fix",
                    "item_id": "g1",
                    "timestamp": "2026-11-26T11:00:00Z",
                },
            ),
        ]
        loaded = await load_db_graded_scout_sets(_FakeDB(db_rows), redis_client=rc)
        top = loaded[0]
        assert top.slug == "novel-morning-set"
        assert top.grade == "Drop"
        assert top.member_ids == (901, 902, 903)
        assert top.deck_id == f"scout-morning-{deck_date}"

    def test_overlap_thresholds_and_priority_ranking(self):
        known = [
            ScoutKnownSet(
                source="graded",
                slug="older-set",
                name="Older Set",
                member_ids=(1, 2, 3, 4),
                grade="Keep",
                graded_at="2026-11-23T12:00:00Z",
            ),
            ScoutKnownSet(
                source="graded",
                slug="newer-fix-set",
                name="Newer Fix Set",
                member_ids=(1, 2, 3, 4),
                grade="Fix",
                graded_at="2026-11-26T12:00:00Z",
            ),
            ScoutKnownSet(
                source="graded",
                slug="same-day-less-overlap",
                name="Same Day Two",
                member_ids=(10, 11, 12),
                grade="Fix",
                graded_at="2026-11-25T09:00:00Z",
            ),
            ScoutKnownSet(
                source="graded",
                slug="same-day-more-overlap",
                name="Same Day Five",
                member_ids=(10, 11, 12, 13, 14),
                grade="Keep",
                graded_at="2026-11-25T08:00:00Z",
            ),
            ScoutKnownSet(
                source="public",
                slug="live-public-set",
                name="Live Public Set",
                member_ids=(50, 51, 52),
            ),
        ]
        # 2/5 (<50%) with distinct name passes overlap gate.
        below = [_mk(1, "A"), _mk(2, "B"), _mk(91, "C"), _mk(92, "D"), _mk(93, "E")]
        assert find_scout_known_set_overlap("Fresh Novel Board", "fresh-novel-board", below, known) is None

        # Newer day overrides older day for identical member set.
        exact_half = [_mk(1, "A"), _mk(2, "B"), _mk(91, "C"), _mk(92, "D")]
        ov_new = find_scout_known_set_overlap("Brand New Name", "brand-new-name", exact_half, known)
        assert ov_new is not None and ov_new.known_set.slug == "newer-fix-set"
        assert ov_new.known_set.grade == "Fix"

        # Same grading day picks greater member overlap (5/5 Keep beats 3/5 Fix).
        same_day_cands = [_mk(i, f"M{i}") for i in range(10, 15)]
        ov_same = find_scout_known_set_overlap("Fresh Name", "fresh-name", same_day_cands, known)
        assert ov_same is not None and ov_same.known_set.slug == "same-day-more-overlap"
        assert ov_same.known_set.grade == "Keep"

        # Name match rejects even with <50% members (1 of 3).
        name_only = [_mk(50, "P1"), _mk(98, "P2"), _mk(99, "P3")]
        ov_name = find_scout_known_set_overlap("Live Public Set", "different-slug", name_only, known)
        assert ov_name is not None and ov_name.matched_by_name is True

    def test_end_to_end_task_carries_grades_via_durable_known_sets(self, tmp_path, monkeypatch):
        import app.tasks.discover_fun_scout as scout_task

        rc = _FakeRedis()
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: rc)
        monkeypatch.setattr(llm_request, "_get_ledger", lambda: MemoryBudgetLedger())
        monkeypatch.setattr(scout_task, "_UNRECORDED_SPEND_MONTHS", set())
        monkeypatch.setattr(scout_task, "SCOUT_RETIRED_SETS_PATH", tmp_path / "retired.json")
        monkeypatch.setattr(scout_task, "SCOUT_LICENCE_STATE_PATH", tmp_path / "licence.json")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        class _SessionCtx:
            async def __aenter__(self):
                return _FakeDB([])

            async def __aexit__(self, *_exc):
                return False

        monkeypatch.setattr(scout_task, "async_session_maker", lambda: _SessionCtx())

        rows = [
            _mk(65536401, "Total snowfall in Big Sky in December 2026?", category="white christmas"),
            _mk(67804428, "Park City Mountain snowfall total by December 24th", category="white christmas"),
            _mk(67804432, "Mammoth Mountain snowfall total by December 24th", category="white christmas"),
            _mk(113987, "Top Spotify Artist 2026", source="polymarket", category="year-end"),
            _mk(70733200, "Top Spotify Song 2026", source="polymarket", category="year-end"),
            _mk(57574931, "#2 Spotify Song 2026", source="polymarket", category="year-end"),
            _mk(27988658, "Top Spotify Album 2026", source="polymarket", category="year-end"),
            _mk(35961535, "#2 Spotify Artist 2026", source="polymarket", category="year-end"),
            _mk(35961536, "#3 Spotify Artist 2026", source="polymarket", category="year-end"),
        ]
        monkeypatch.setattr(
            scout_task,
            "fetch_open_non_sports_markets_for_scout",
            AsyncMock(return_value=rows),
        )
        monkeypatch.setattr(
            scout_task,
            "fetch_reader_dismissed_sets_for_scout",
            AsyncMock(return_value={}),
        )

        class _OpenAI:
            class _Chat:
                class _Completions:
                    def create(self, **_kw):
                        body = json.dumps(
                            {
                                "tagged": [
                                    {
                                        "market_id": r.market_id,
                                        "fun_group": r.category,
                                        "is_fun_single": False,
                                        "set_hint": None,
                                        "reason": "fun theme",
                                    }
                                    for r in rows
                                ]
                            }
                        )
                        return SimpleNamespace(
                            choices=[SimpleNamespace(message=SimpleNamespace(content=body))],
                            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
                        )

                completions = _Completions()

            chat = _Chat()

        class _Anthropic:
            class _Messages:
                def create(self, **_kw):
                    body = json.dumps(
                        {
                            "sets": [
                                {
                                    "slug": "spotify-2026-showdown",
                                    "name": "Spotify 2026 Showdown",
                                    "kicker": "SPOTIFY CHARTS",
                                    "category": "year-end",
                                    "why_better_together": "Top artist, song and album side by side.",
                                    "look": "bars",
                                    "selector_kind": "fun_tag",
                                    "member_ids": [113987, 70733200, 57574931, 27988658, 35961535, 35961536],
                                },
                                {
                                    "slug": "snow-day-slopes",
                                    "name": "Snow Day Slopes",
                                    "kicker": "WHO GETS BURIED BY CHRISTMAS?",
                                    "category": "white christmas",
                                    "why_better_together": "Big Sky, Park City and Mammoth holiday snow totals.",
                                    "look": "map",
                                    "selector_kind": "fun_tag",
                                    "member_ids": [65536401, 67804428, 67804432],
                                },
                            ]
                        }
                    )
                    return SimpleNamespace(
                        content=[SimpleNamespace(text=body)],
                        usage=SimpleNamespace(input_tokens=100, output_tokens=50),
                    )

            messages = _Messages()

        monkeypatch.setattr(scout_task, "build_scout_openai_client", lambda: _OpenAI())
        monkeypatch.setattr(scout_task, "build_scout_anthropic_client", lambda: _Anthropic())

        out = asyncio.run(
            scout_task._run_discover_fun_scout(
                force=True,
                output_dir=tmp_path / "staged",
                now=FROZEN_NOW,
                publish_to_github=False,
            )
        )
        assert [s["slug"] for s in out["staged_sets"]] == ["snow-day-slopes"]
        latest = json.loads(rc.store["bainluck:fun_scout:latest"])
        assert len(latest["carried_grades"]) == 1
        carried = latest["carried_grades"][0]
        assert carried["proposed_slug"] == "spotify-2026-showdown"
        assert carried["grade"] == "Fix"
        assert carried["matched_slug"] == "wrapped-2026"
        md = scout_task.format_scout_nightly_comment_markdown(latest)
        assert "### Carried Grades (1)" in md
        assert "`Your Wrapped, Predicted`" in md
        assert "`Fix`" in md
        assert "wrapped-2026" in md


class TestKickerQuestionAndMixedLadderRules:
    """Rules (b), (c), and (d) across validator, rule def, task markdown, morning deck, and producer."""

    def test_rule_b_kicker_never_cut_mid_word_and_empty_preserved(self):
        assert normalize_scout_kicker("  who gets buried by christmas? ") == "WHO GETS BURIED BY CHRISTMAS?"
        assert len("A" * SCOUT_KICKER_MAX_CHARS) == 32
        assert normalize_scout_kicker("A" * 32) == "A" * 32
        assert normalize_scout_kicker("ONE MAN, SIX WILDLY DIFFERENT FUTURES") == ""

        cat = {
            1: _mk(1, "Big Sky total snowfall in December?"),
            2: _mk(2, "Park City total snowfall by Dec 24?"),
            3: _mk(3, "Mammoth total snowfall by Dec 24?"),
        }
        prop = ScoutProposedSet(
            slug="powder-check",
            name="Powder Check",
            kicker="WHICH WESTERN RESORT GETS THE MOST SNOW THIS WINTER",
            category="weather",
            why_better_together="Big Sky, Park City and Mammoth holiday totals compared.",
            look="map",
            member_ids=(1, 2, 3),
        )
        vset, err = validate_scout_proposed_set(prop, cat, known_sets=(), now=FROZEN_NOW)
        assert err is None and vset is not None
        assert vset.kicker == ""

        defn = build_scout_rule_file_definition(
            vset, model_used="claude-sonnet-5-5", created_at=FROZEN_NOW
        )
        assert defn["kicker"] == ""

        model_defn = RoundupProducer(
            slug="powder-check",
            name="Powder Check",
            kind="roundup",
            category="weather",
            section_title="Powder Check",
            footer="",
            produce=lambda _db: None,
            stage="preview",
            membership="computed-produced",
            relations=("same_subject",),
            level="related",
            rule={"look": "bars", "selector": {"fun_tag": "powder-check"}},
            kicker="",
        )
        assert model_defn.kicker == ""

        card = _sanitize_card_entry(
            title="Powder Check",
            kicker="",
            category="weather",
            summary="Three resorts.",
            look="map",
            members=[{"title": "Big Sky total snowfall in December?", "probability": 0.4}],
        )
        assert card["kicker"] == ""
        assert _sanitize_card_entry(
            title="Default Kicker",
            kicker=None,
            category="weather",
            summary="Three resorts.",
            look="bars",
            members=[{"title": "M1", "probability": 0.4}],
        )["kicker"] == "DISCOVER SET"

    def test_rule_c_question_word_banned_anywhere_in_copy(self):
        assert check_scout_no_question_word("Cast", "KICKER", "Good markets here.", "") is None
        assert check_scout_no_question_word("Big Question", "", "Blurb.", "") == "forbidden_word:question"
        assert (
            check_scout_no_question_word(
                "Wild Cards",
                "KICKER",
                "Far-fetched questions friends love debating.",
                "",
            )
            == "forbidden_word:questions"
        )

    @pytest.mark.asyncio
    async def test_rule_d_mixed_yes_no_and_ladder_requires_row_answers_end_to_end(
        self, monkeypatch
    ):
        import app.tasks.discover_fun_scout as scout_task

        m_yes = _mk(109324, "Stranger Things: New episode this year?")
        m_date = _mk(59693617, "When will Drake release a new album?")
        m_score = _mk(63336234, '"GTA VI" Metacritic Score?')
        m_snow1 = _mk(65536401, "Total snowfall in Big Sky in December 2026?")
        m_snow2 = _mk(67804428, "Park City Mountain snowfall total by December 24th")
        m_snow3 = _mk(67804432, "Mammoth Mountain snowfall total by December 24th")

        assert classify_scout_member_shape(m_yes) == "yes_no"
        assert classify_scout_member_shape(m_date) == "date_ladder"
        assert classify_scout_member_shape(m_score) == "score_ladder"
        assert classify_scout_member_shape(m_snow1) == "value_ladder"

        # Homogeneous yes/no or homogeneous value_ladder passes without row_answers.
        assert check_scout_mixed_ladder_answers([m_snow1, m_snow2, m_snow3]) is None

        cat = {m.market_id: m for m in (m_yes, m_date, m_score)}
        base_kw = dict(
            slug="stranger-drake-gta",
            name="Release Tracker",
            kicker="RELEASE CALENDAR WATCH",
            category="culture",
            why_better_together="Stranger Things, Drake's next album and GTA VI launch together.",
            look="bars",
            member_ids=(109324, 59693617, 63336234),
        )
        # Missing all ladder answers -> rejected.
        v_missing, err_missing = validate_scout_proposed_set(
            ScoutProposedSet(**base_kw), cat, known_sets=(), now=FROZEN_NOW
        )
        assert v_missing is None
        assert err_missing == "mixed_ladder_missing_row_answer:59693617,63336234"

        # Missing one ladder row answer -> still rejected naming that row.
        v_partial, err_partial = validate_scout_proposed_set(
            ScoutProposedSet(**base_kw, row_answers={59693617: "Q2 2026"}),
            cat,
            known_sets=(),
            now=FROZEN_NOW,
        )
        assert v_partial is None
        assert err_partial == "mixed_ladder_missing_row_answer:63336234"

        # All ladder rows stated -> accepted & flows through rule file, artifact, markdown, morning deck, and producer.
        complete_answers = normalize_scout_row_answers(
            {59693617: "Q2 2026", 63336234: "95+"}
        )
        v_ok, err_ok = validate_scout_proposed_set(
            ScoutProposedSet(**base_kw, row_answers=complete_answers),
            cat,
            known_sets=(),
            now=FROZEN_NOW,
        )
        assert err_ok is None and v_ok is not None
        defn = build_scout_rule_file_definition(
            v_ok, model_used="claude-sonnet-5-5", created_at=FROZEN_NOW
        )
        assert defn["scout"]["row_answers"] == {"59693617": "Q2 2026", "63336234": "95+"}

        # Rule (b) omitted kicker + Rule (d) row_answers in build_fun_scout_set_producer.
        import app.utils.discover_fun_tags as dft_mod

        orig_lookup = dft_mod.fun_market_ids_for_sub_tag
        monkeypatch.setattr(
            dft_mod,
            "fun_market_ids_for_sub_tag",
            lambda tag: (
                (109324, 59693617, 63336234) if tag == "stranger-drake-gta" else orig_lookup(tag)
            ),
        )
        empty_kicker_defn = dict(defn, kicker="")
        producer = build_fun_scout_set_producer(empty_kicker_defn)
        assert producer.kicker == ""

        fake_fm = [
            SimpleNamespace(
                id=m.market_id,
                name=m.title,
                question=m.title,
                category="culture",
                source="kalshi",
                volume=50_000,
                outcomes=[
                    SimpleNamespace(
                        name="Yes",
                        current_probability=0.55,
                        probability_change_24h=0.04,
                        rank=1,
                    )
                ],
            )
            for m in (m_yes, m_date, m_score)
        ]
        produced = await producer.produce(_FakeDB(fake_fm))

        assert isinstance(produced, RoundupMembers)
        assert produced.kicker == ""
        drake_card = next(c for c in produced.members if c["id"] == 59693617)
        assert drake_card["context_line"] == "Q2 2026"
        assert drake_card["row_answer"] == "Q2 2026"
        drake_row = next(r for r in produced.rows if r["destination_href"] == "/markets/59693617")
        assert drake_row["context_line"] == "Q2 2026"
        assert drake_row["row_answer"] == "Q2 2026"

        # Artifact -> comment markdown + morning deck hydration preserve row_answers & omitted kicker.
        v_omitted = validate_scout_proposed_set(
            ScoutProposedSet(
                **{**base_kw, "kicker": "THIS KICKER IS WAY TOO LONG TO FIT WITHOUT SLICING"},
                row_answers=complete_answers,
            ),
            cat,
            known_sets=(),
            now=FROZEN_NOW,
        )[0]
        assert v_omitted is not None and v_omitted.kicker == ""
        artifact = scout_task.build_scout_nightly_artifact(
            {
                "spend_line": "[discover-fun-scout] ok",
                "actual_total_cost_usd": 0.1,
                "set_model": "claude-sonnet-5-5",
                "tagged_count": 3,
                "validated_sets": [v_omitted],
                "verified_singles": [],
                "rejected_sets": [],
                "carried_grades": [],
                "licence_state": {"status": "awaiting_fable_look"},
            },
            run_now=FROZEN_NOW,
        )
        md = scout_task.format_scout_nightly_comment_markdown(artifact)
        assert "- **Kicker:** `(omitted)`" in md
        assert "answer: `Q2 2026`" in md

        deck = await build_scout_morning_deck(
            _FakeDB([]),
            deck_date="2026-11-26",
            redis_client=_FakeRedis(),
            staged_override=artifact["staged_sets"],
            public_override=[],
            now=FROZEN_NOW,
        )
        assert deck["status"] == "ready"
        deck_card = deck["items"][0]
        assert deck_card["kicker"] == ""
        drake_deck_row = next(r for r in deck_card["members"] if "Drake" in r["title"])
        assert drake_deck_row["row_answer"] == "Q2 2026"


class TestNov26BeforeAndAfterReplay:
    """Before-and-after replay of all 10 staged sets from Thu Nov 26 (#13102)."""

    def test_ten_sets_before_and_after_fable_look_gates(self, monkeypatch):
        monkeypatch.setattr(llm_request, "_get_ledger", lambda: MemoryBudgetLedger())
        rows, tagged, proposals_with_before_kicker = _nov_26_catalog_and_proposals()
        catalog_by_id = {r.market_id: r for r in rows}

        # Before: none of the 10 had known_sets overlap checks; 6 kickers sliced at 32 chars mid-word.
        before_sliced = [
            (p.slug, p.kicker[:32])
            for p, expected_slice in proposals_with_before_kicker
            if p.kicker[:32] == expected_slice and len(p.kicker) > 32
        ]
        assert [slug for slug, _ in before_sliced] == [
            "elon-everything-everywhere",
            "ring-watch-2026",
            "gta-vi-watch",
            "fresh-or-rotten",
            "halftime-and-ads",
            "spotify-2026-showdown",
        ]

        class _ReplayAnthropic:
            def __init__(self, proposals_seq):
                self._proposals_seq = proposals_seq

            @property
            def messages(self):
                outer = self

                class _Messages:
                    def create(self, **_kw):
                        payload = {
                            "sets": [
                                {
                                    "slug": p.slug,
                                    "name": p.name,
                                    "kicker": p.kicker,
                                    "category": p.category,
                                    "why_better_together": p.why_better_together,
                                    "look": p.look,
                                    "selector_kind": "fun_tag",
                                    "member_ids": list(p.member_ids),
                                }
                                for p, _ in outer._proposals_seq
                            ]
                        }
                        return SimpleNamespace(
                            content=[SimpleNamespace(text=json.dumps(payload))],
                            usage=SimpleNamespace(input_tokens=100, output_tokens=100),
                        )

                return _Messages()

        # After: full nightly scout run against loaded graded (Deck 1+2) and public sets.
        after_out = run_nightly_fun_scout(
            rows,
            [ScoutUncoveredFamily("white christmas", "Snowfall?", 3)],
            openai_client=object(),
            anthropic_client=_ReplayAnthropic(proposals_with_before_kicker),
            pretagged=(tagged, 0.01),
            known_sets=load_known_sets_for_scout(catalog_by_id=catalog_by_id),
            now=FROZEN_NOW,
        )

        # Only Snow Day Slopes survives; its 29-char kicker stays intact and unsliced.
        assert [v.slug for v in after_out["validated_sets"]] == ["snow-day-slopes"]
        assert after_out["validated_sets"][0].kicker == "WHO GETS BURIED BY CHRISTMAS?"

        rej_by_slug = {r["slug"]: r for r in after_out["rejected_sets"]}
        assert len(rej_by_slug) == 9
        assert rej_by_slug["elon-everything-everywhere"]["reason"] == (
            "public_set_overlap:machinery-elon-musk-side-quests"
        )
        assert rej_by_slug["spotify-2026-showdown"]["carried_grade"] == "Fix"
        assert rej_by_slug["spotify-2026-showdown"]["matched_slug"] == "wrapped-2026"
        for keep_slug in (
            "ring-watch-2026",
            "will-it-ever-come-out",
            "gta-vi-watch",
            "wild-cards",
            "fresh-or-rotten",
            "who-gets-the-part",
            "halftime-and-ads",
        ):
            assert rej_by_slug[keep_slug]["carried_grade"] == "Keep"

        assert len(after_out["carried_grades"]) == 8

        # Also isolate rules (b), (c), (d) with known_sets=() to confirm each gate fires cleanly.
        for p, expected_slice in proposals_with_before_kicker:
            norm_k = normalize_scout_kicker(p.kicker)
            if len(p.kicker) > 32:
                assert norm_k == ""
            else:
                assert norm_k == p.kicker

        assert (
            validate_scout_proposed_set(
                proposals_with_before_kicker[4][0], catalog_by_id, known_sets=(), now=FROZEN_NOW
            )[1]
            == "forbidden_word:questions"
        )
        assert (
            validate_scout_proposed_set(
                proposals_with_before_kicker[6][0], catalog_by_id, known_sets=(), now=FROZEN_NOW
            )[1]
            == "forbidden_word:questions"
        )
        assert (
            validate_scout_proposed_set(
                proposals_with_before_kicker[0][0], catalog_by_id, known_sets=(), now=FROZEN_NOW
            )[1]
            == "mixed_ladder_missing_row_answer:52755879,68210398"
        )
        assert (
            validate_scout_proposed_set(
                proposals_with_before_kicker[2][0], catalog_by_id, known_sets=(), now=FROZEN_NOW
            )[1]
            == "mixed_ladder_missing_row_answer:59693617,108494,25924930"
        )
