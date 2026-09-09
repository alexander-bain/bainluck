"""#4151 — a Discover card never answers a question with a venue slug.

On production Discover, 2026-09-09 00:0x PT (`GET /api/feed?limit=60`), the "AI"
bundle served two rows, one directly above the other:

    Best AI at the end of 2026?   Claude leads at 60%                rows: Claude 60 · ChatGPT 28
    Top AI model in September?    claude-fable-5.1-max leads at 68%  rows: claude-fable-5.1-max 69

The same product named two ways one row apart, and the second is a string for a
request body. The slug travels in the served `reason`, so it is not a client-side
mapping miss — it is the outcome name we ingested being spoken in a sentence.

🔴 THE VENUE HAS NO HUMAN LABEL TO INGEST. Read against Kalshi's own API
(standing notice 26): `yes_sub_title`, `no_sub_title`, `custom_strike.Model` and
`rules_primary` all read `claude-fable-5.1-max`, because LMArena — Kalshi's
resolution source — names models that way. So there is no upstream field to
prefer and no mapping to repair; the display name has to be ours.

🔴 AND THE NAME HAS THREE COPIES IN THE SERVED PAYLOAD, NOT ONE. The issue
scopes this to "the point the reason sentence is composed". That is a third of
it:

    reason / headline / context_summary        humanize_binary_outcome_name
    data.top_outcomes[].name                   humanize_outcome_names_for_feed
    discover_card.distribution_outcomes[].label
    discover_card.threshold_points[].label     classify_discover_card_archetype

The first two are humanized SEPARATELY and both humanizers pass anything that is
not "Yes"/"No" straight through. The last two are built straight off the ORM row
and never saw a humanizer at all — and on production this card's
`suggested_format` is `threshold_heatmap`, so `threshold_points[].label` is the
copy a reader actually reads. **A fix at the two humanizers would have changed
nothing on the visible card** while every test that inspected `top_outcomes`
went green. Hence all three seams, and hence the guard below walks the whole
payload instead of the fields its author had in mind.

(The first draft of this file did exactly that: it checked the sentences and
`top_outcomes`, passed, and the card still showed the slug. That is CERT-2326's
lesson a second time — a guard aimed at the fields you just fixed is a guard
against the bug you already know about.)

The guards stand in four places:

* at the ROUTE, driving `_score_futures` for real and walking EVERY string in
  the served card, so a copy of the name nobody enumerated is still caught;
* RED-FIRST, neutralising all three seams and asserting that both the row copy
  and the label copy leak, so a seam cannot be deleted and still look covered;
* at the CONTROL, driving the same route with `blink-182` on its real live
  question, because the failure this design must never have is renaming a real
  entity whose lowercase spelling IS its identity;
* at BOTH ROUTE SITES structurally, because `_score_sports_mode_futures` is a
  hand-maintained near-copy of `_score_futures` and a near-copy is exactly where
  a fix applied once survives as a bug.
"""

import inspect
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Imported as MODULES, not as names: the red-first test monkeypatches attributes
# on them, and a module cannot be both `import`ed and `import from`ed without
# CodeQL's py/import-and-import-from.
import app.routes.feed as feed_route
import app.utils.discover_card_archetypes as archetypes
import app.utils.feed_reasons as fr
import app.utils.outcome_display_names as odn
from app.utils.personalization import PersonalizationContext

CANONICAL_KEY = "outcome-display-names-4151"

#: The AI-model question these markets actually carry, verbatim from production.
MODEL_QUESTION = "Top AI model in September?"

#: Every distinct model slug on an AI-model question in production, 2026-09-09
#: (n=37; `futures_outcomes` joined to `futures_markets`). The expected reading
#: is written out rather than recomputed, so a change to the prettifier has to
#: face what a reader would see.
REAL_MODEL_SLUGS = {
    "claude-fable-5": "Claude Fable 5",
    "claude-fable-5.1-max": "Claude Fable 5.1 Max",
    "claude-opus-4-5-20251101": "Claude Opus 4-5-20251101",
    "claude-opus-4-5-20251101-thinking-32k": "Claude Opus 4-5-20251101 Thinking 32k",
    "claude-opus-4-6": "Claude Opus 4-6",
    "claude-opus-4-6-high": "Claude Opus 4-6 High",
    "claude-opus-4-6-thinking": "Claude Opus 4-6 Thinking",
    "claude-opus-4-7": "Claude Opus 4-7",
    "claude-opus-4-7-thinking": "Claude Opus 4-7 Thinking",
    "claude-opus-5-high": "Claude Opus 5 High",
    "claude-opus-5-max": "Claude Opus 5 Max",
    "dola-seed-2.0-preview": "Dola Seed 2.0 Preview",
    "ernie-5.0-0110": "Ernie 5.0-0110",
    "ernie-5.1-preview": "Ernie 5.1 Preview",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-3-flash": "Gemini 3 Flash",
    "gemini-3-pro": "Gemini 3 Pro",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
    "gemini-3.5-flash": "Gemini 3.5 Flash",
    "glm-4.6": "GLM 4.6",
    "glm-5.1": "GLM 5.1",
    "gpt-5.1-high": "GPT 5.1 High",
    "gpt-5.2": "GPT 5.2",
    "gpt-5.2-chat-latest-20260210": "GPT 5.2 Chat Latest 20260210",
    "gpt-5.4-high": "GPT 5.4 High",
    "gpt-5.5-high": "GPT 5.5 High",
    "grok-4.1-thinking": "Grok 4.1 Thinking",
    "grok-4.20-beta-0309-reasoning": "Grok 4.20 Beta 0309 Reasoning",
    "grok-4.20-beta1": "Grok 4.20 Beta1",
    "kimi-k2.5-thinking": "Kimi K2.5 Thinking",
    "mistral-large-3": "Mistral Large 3",
    "mistral-medium-2508": "Mistral Medium 2508",
    "muse-spark": "Muse Spark",
    "qwen3-max-preview": "Qwen3 Max Preview",
    "qwen3.5-max-preview": "Qwen3.5 Max Preview",
    "qwen3.7-max-preview": "Qwen3.7 Max Preview",
    "qwen3.8-max": "Qwen3.8 Max",
}

#: 🔴 THE NAMES THAT MUST SURVIVE UNTOUCHED, each with the real market it sits
#: on. These are the whole reason the predicate needs a second lock: they are
#: structurally indistinguishable from a model id (`estar_backs` vs
#: `muse-spark`), and their lowercase spelling is their identity. Measured: 17
#: outcome rows in production are slug-shaped on a non-model question, and these
#: are all four distinct names among them.
LOWERCASE_IS_THE_NAME = [
    ("blink-182", "Who will release a new album in 2026?"),
    ("estar_backs", "Amaru Gaming vs. estar_backs"),
    ("ex-1win", "ex-1win vs. Lazer Cats"),
    ("korekore_ch", "Who will be the Most Watched Kick Streamer in June?"),
]

#: Bucket labels on `quantity` markets — 920 of the first 1,000 hyphenated
#: outcome names in production. Re-typesetting any of these produces nonsense,
#: and they are tested ON the model question so that the SHAPE lock alone is
#: what has to stop them.
NOT_A_NAME_AT_ALL = [
    "120-139",
    "$250-$255",
    "17.5-18m",
    "350k-400k",
    "660-670b",
    "7th-9th",
    "9-1-1",
    "72%-74%",
    "<-150k",
]

#: A slug is lowercase, separator-joined, and has no spaces. Whole-value only.
#:
#: 🔴 A SUBSTRING SEARCH WITH THIS PATTERN CANNOT BE USED ON PROSE, and that is
#: not fussiness — it cannot tell a venue slug from an ordinary hyphenated
#: English word. It matches `front-runner`, which appears verbatim in this very
#: card's LLM `hook_description` on production ("the emergence of Claude-Fable
#: 5.1 Max as the front-runner…"). A guard that reds on English is a guard the
#: next person deletes, and deletes for a good reason.
#:
#: So the route guard checks prose against the EXACT raw names the fixture was
#: built from (`_slug_leaks` below), which has no false positives at all, and
#: this pattern is reserved for label fields, where a whole-value match is
#: exactly the right question.
LOOKS_LIKE_A_SLUG = re.compile(r"^[a-z][a-z0-9]*(?:[-_.][a-z0-9.]+)+$")

#: 🔴 THE ONLY PLACES A LOWERCASE TOKEN IS ALLOWED, and they are machine fields,
#: not prose. Per notice 33's clarification the rule is about what a READER sees;
#: JSON keys and enum values a client branches on are out of scope. Each entry
#: names a served path whose value is an ENUM OR AN IDENTIFIER — never a string
#: any client prints verbatim:
#:
#:   canonical_market_key            our own grouping key
#:   discover_card.suggested_format  an enum the client switches on
#:   discover_card.qa_signals        admin/QA diagnostics, never rendered
#:   discover_card.reasons           admin/QA diagnostics, never rendered
#:   market_tags                     `market_status:open`-style filter tags
#:
#: This is a SKIP LIST, so it is the one part of the walk that can hide a real
#: defect. `test_the_machine_field_skips_are_all_still_machine_fields` asserts
#: every entry still resolves to a path the payload actually has, so an entry
#: cannot rot into a blanket exemption for a field that was renamed.
MACHINE_FIELDS = (
    "canonical_market_key",
    "discover_card.suggested_format",
    "discover_card.qa_signals",
    "discover_card.reasons",
    "market_tags",
)


def _is_machine_field(path: str) -> bool:
    return any(field in path for field in MACHINE_FIELDS)


def _slug_leaks(item: dict, raw_names) -> dict[str, str]:
    """Every reader-facing string in `item` that still carries a raw slug.

    Two tests, one per kind of field, because one pattern cannot do both:

    * PROSE — does the string CONTAIN one of the exact raw names the fixture was
      built from? Exact, so `front-runner` in an LLM hook cannot trip it.
    * LABELS — is the whole value slug-shaped? Catches a slug this test never
      named, which is what makes it a guard against the class rather than
      against the six strings in `LIVE_AI_OUTCOMES`.
    """
    leaks = {}
    for path, text in _every_served_string(item):
        if _is_machine_field(path):
            continue
        if any(raw in text for raw in raw_names):
            leaks[path] = text
        elif LOOKS_LIKE_A_SLUG.match(text):
            leaks[path] = text
    return leaks


# ── 1. THE PURE DECISION ────────────────────────────────────────────────────


@pytest.mark.parametrize("slug,expected", sorted(REAL_MODEL_SLUGS.items()))
def test_every_live_model_slug_reads_as_a_name(slug, expected):
    assert odn.display_outcome_name(slug, MODEL_QUESTION) == expected


@pytest.mark.parametrize("name,market", LOWERCASE_IS_THE_NAME)
def test_a_name_whose_lowercase_is_its_identity_is_never_retypeset(name, market):
    """`blink-182` is the band. `korekore_ch` is the streamer's handle."""
    assert odn.display_outcome_name(name, market) == name


@pytest.mark.parametrize("label", NOT_A_NAME_AT_ALL)
def test_a_bucket_label_is_never_retypeset_even_on_a_model_question(label):
    """The shape lock alone must stop these — they are passed the model question."""
    assert odn.display_outcome_name(label, MODEL_QUESTION) == label


@pytest.mark.parametrize(
    "name",
    ["Claude", "ChatGPT", "Los Angeles Dodgers", "Yes", "No", "Jean-Luc Picard"],
)
def test_an_already_human_name_is_never_touched(name):
    assert odn.display_outcome_name(name, MODEL_QUESTION) == name


def test_an_unrecognised_question_keeps_its_slug_rather_than_guessing():
    """The failure direction is one-way ON PURPOSE.

    A market phrased in a way `_MODEL_QUESTION_RE` does not know keeps the slug
    — status quo, no regression — rather than being re-typeset on a guess. This
    test exists so that widening the regex is a deliberate act with a test to
    change, not a silent drift into renaming other markets' answers.
    """
    assert (
        odn.display_outcome_name("claude-fable-5.1-max", "Who wins the Emmy?")
        == "claude-fable-5.1-max"
    )


def test_the_list_form_does_not_mutate_its_input():
    rows = [{"name": "gpt-5.2", "probability": 0.4}]
    out = odn.display_outcome_names(rows, MODEL_QUESTION)
    assert rows[0]["name"] == "gpt-5.2", "input was mutated"
    assert out[0]["name"] == "GPT 5.2"
    assert out[0]["probability"] == 0.4, "the rest of the row was dropped"


# ── 2. AT THE ROUTE: the sentence AND the row, on the real serve path ────────


class _Outcome:
    def __init__(self, id, name, probability):
        self.id = id
        self.name = name
        self.external_id = None
        self.current_probability = probability
        self.probability_change_24h = 0.0
        self.opening_probability = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        self.current_yes_bid = None
        self.current_yes_ask = None


class _Market:
    """A real object so `__dict__.get(...)` reads work, as in #250's harness."""

    def __init__(self, id, name, *, outcomes, category="politics"):
        now = datetime.now(timezone.utc)
        self.id = id
        self.name = name
        self.source = "kalshi"
        self.external_id = f"kalshi-{id}"
        self.sport_id = None
        self.sport = None
        self.category = category
        self.llm_sport_category = category
        self.market_tier = 1
        self.canonical_market_key = CANONICAL_KEY
        self.group_id = None
        self.group_type = None
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250000
        self.updated_at = now
        self.commence_time = now - timedelta(days=1)
        self.resolution_date = now + timedelta(days=30)
        self.status = "open"
        self.created_at = now - timedelta(days=10)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.outcomes = outcomes


def _mock_db(markets):
    db = AsyncMock()

    def make_result(*a, **k):
        r = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]
        unique = MagicMock()
        unique.all.return_value = markets
        scalars.unique.return_value = unique
        r.scalars.return_value = scalars
        r.all.return_value = []
        return r

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _serve(markets, *, source_count: int = 2):
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={CANONICAL_KEY: source_count}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        return await feed_route._score_futures(
            _mock_db(markets),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )


def _served_sentences(item: dict) -> dict[str, str]:
    return {
        slot: item.get(slot) or "" for slot in ("headline", "reason", "context_summary")
    }


def _served_row_names(item: dict) -> list[str]:
    return [
        o.get("name") or ""
        for o in ((item.get("data") or {}).get("top_outcomes") or [])
    ]


def _every_served_string(node, path="") -> list[tuple[str, str]]:
    """Every string anywhere in the served payload, with the path it sits at.

    🔴 THE GUARD WALKS THE WHOLE CARD, and it has to. The first version of this
    file inspected `headline`/`reason`/`context_summary` and
    `top_outcomes[].name` — the places the fix had just touched — and passed
    while the served card still carried the raw slug in TWO more:
    `discover_card.distribution_outcomes[].label` (six of them, more than
    `top_outcomes` holds) and `discover_card.threshold_points[].label`. On
    production this card's `suggested_format` is `threshold_heatmap`, so the
    labels a reader actually reads are the SECOND of those — the copy the guard
    was not looking at, on the path the fix had not reached.

    That is CERT-2326's lesson a second time: a guard that checks the fields the
    author was thinking about is a guard against the bug the author already
    fixed. Enumerating nothing and walking everything is what makes it a guard
    against the CLASS.
    """
    found: list[tuple[str, str]] = []
    if isinstance(node, str):
        found.append((path, node))
    elif isinstance(node, dict):
        for key, value in node.items():
            found += _every_served_string(value, f"{path}.{key}" if path else key)
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            found += _every_served_string(value, f"{path}[{index}]")
    return found


#: The live `Top AI model in September?` market, all six outcomes at the prices
#: production served on 2026-09-09. SIX, not the three `top_outcomes` carries:
#: the archetype builder is handed EVERY outcome, so the label lists it emits
#: are longer than the row list and a three-outcome fixture would not reproduce
#: them. Verified against production: with these six the fixture classifies
#: `threshold_heatmap` / `['threshold_values']`, byte-identical to the live
#: card, so the guards below run on the archetype a reader is actually served.
#: With three it classifies `binary_probability` and tests nothing real.
LIVE_AI_OUTCOMES = [
    ("claude-fable-5.1-max", 0.685),
    ("claude-opus-5-max", 0.075),
    ("claude-opus-5-high", 0.060),
    ("claude-opus-4-6-thinking", 0.035),
    ("claude-fable-5", 0.010),
    ("claude-opus-4-7", 0.010),
]


def _live_ai_market(market_id=1, outcomes=None) -> _Market:
    """The live `Top AI model in September?` card, at its production prices."""
    rows = outcomes or LIVE_AI_OUTCOMES
    return _Market(
        market_id,
        MODEL_QUESTION,
        outcomes=[_Outcome(101 + i, n, p) for i, (n, p) in enumerate(rows)],
    )


@pytest.mark.asyncio
async def test_no_served_sentence_or_row_answers_with_a_venue_slug():
    """The live defect, at the route, on the real card.

    Checks the sentence and the row TOGETHER: the invariant is that a reader
    never sees a slug, and it is not satisfied by fixing whichever half the test
    happened to look at.
    """
    items = await _serve([_live_ai_market()])
    futures = [i for i in items if i["type"] == "futures"]

    # Eligible denominator, both halves: the card was admitted AND it printed
    # rows. Without these a dropped fixture passes having proved nothing
    # (#4169's lesson).
    assert len(futures) == 1, f"the fixture card was not served: {items}"
    rows = _served_row_names(futures[0])
    assert rows, f"the card served no outcome rows at all: {futures[0]}"

    # The denominator's third half: the walk below is only meaningful if it is
    # actually reaching the label lists. Naming them here means that if the
    # payload shape changes and they vanish, this reds instead of passing
    # vacuously.
    paths = {path for path, _ in _every_served_string(futures[0])}
    for required in (
        "data.top_outcomes[0].name",
        "data.discover_card.distribution_outcomes[0].label",
    ):
        assert required in paths, (
            f"{required} is missing from the served card, so the walk below "
            f"cannot see it: {sorted(paths)}"
        )

    offenders = _slug_leaks(futures[0], [n for n, _ in LIVE_AI_OUTCOMES])
    assert not offenders, f"a venue slug reached the reader: {offenders}"

    # And the positive half — it says the right thing, not merely "not a slug".
    assert rows[0] == "Claude Fable 5.1 Max", rows
    assert "Claude Fable 5.1 Max" in futures[0]["headline"], futures[0]["headline"]


@pytest.mark.asyncio
async def test_the_sentence_and_the_row_never_disagree_about_the_name():
    """#4146's invariant, applied to the NAME instead of the percent.

    A fix that resolved the display name on only one of the two humanization
    paths would pass the test above's sentence half and still put a card on the
    page whose caption names something its own rows do not.
    """
    items = await _serve([_live_ai_market()])
    futures = [i for i in items if i["type"] == "futures"]
    assert len(futures) == 1, f"the fixture card was not served: {items}"

    rows = _served_row_names(futures[0])
    leader = rows[0]
    assert leader, "no leader row to compare against"
    for slot, text in _served_sentences(futures[0]).items():
        if leader.split()[0].lower() in text.lower():
            assert leader in text, (
                f"{slot} names the leader but not the way the row prints it: "
                f"row={leader!r} sentence={text!r}"
            )


@pytest.mark.asyncio
async def test_the_route_guard_can_fail(monkeypatch):
    """The guard above is only worth its runtime if a regression reds it.

    Re-creates the defect exactly as it was: the humanizers pass anything that
    is not Yes/No straight through. Note WHICH knob is turned — neutralising the
    display-name resolution, not the prettifier — because after the fix the
    served path resolves the name in `feed_reasons`, and a broken prettifier
    alone would still not put the raw slug back on the page.

    🔴 ALL THREE SEAMS ARE NEUTRALISED, one per copy of the name. Turning off
    only the two in `feed_reasons` leaves the archetype builder resolving
    `distribution_outcomes`, and a red-first proof that reds for the wrong
    reason is not a proof.
    """
    monkeypatch.setattr(fr, "display_outcome_name", lambda name, market: name)
    monkeypatch.setattr(fr, "display_outcome_names", lambda rows, market: rows)
    monkeypatch.setattr(archetypes, "display_outcome_names", lambda rows, market: rows)

    items = await _serve([_live_ai_market()])
    futures = [i for i in items if i["type"] == "futures"]
    assert len(futures) == 1, f"the fixture card was not served: {items}"

    leaked = _slug_leaks(futures[0], [n for n, _ in LIVE_AI_OUTCOMES])
    assert leaked, (
        "the guard cannot fail: with the display-name resolution neutralised "
        "the route still served no slug, so the passing test above proves nothing"
    )
    # Each copy of the name has to be reachable by the neutralised path, or a
    # seam could be removed entirely and this test would still pass on the
    # other two.
    leaked_paths = " ".join(leaked)
    for copy in ("top_outcomes", "distribution_outcomes"):
        assert copy in leaked_paths, (
            f"{copy} did not leak a slug when resolution was neutralised, so "
            f"this test is not covering that copy of the name: {sorted(leaked)}"
        )


@pytest.mark.asyncio
async def test_a_real_entity_named_in_lowercase_is_served_unchanged():
    """🔴 THE CONTROL, on the real route.

    `blink-182` is live right now on 'Who will release a new album in 2026?'.
    The failure this design must never have is renaming it, so the control runs
    the whole serve path rather than the predicate alone — a future widening of
    `_MODEL_QUESTION_RE` reds HERE, which is where it should.
    """
    market = _Market(
        3,
        "Who will release a new album in 2026?",
        outcomes=[
            _Outcome(301, "blink-182", 0.62),
            _Outcome(302, "Rihanna", 0.21),
            _Outcome(303, "Adele", 0.17),
        ],
    )
    items = await _serve([market])
    futures = [i for i in items if i["type"] == "futures"]
    assert len(futures) == 1, f"the control card was not served: {items}"

    rows = _served_row_names(futures[0])
    assert rows, "the control card served no rows"
    assert "blink-182" in rows, f"the band was renamed: {rows}"

    # Across the WHOLE payload, for the same reason the main guard walks it:
    # the band could survive in `top_outcomes` and still be renamed in the
    # distribution the card actually draws.
    renamed = {
        path: text
        for path, text in _every_served_string(futures[0])
        if "Blink 182" in text
    }
    assert not renamed, f"the band was renamed: {renamed}"


@pytest.mark.asyncio
async def test_the_machine_field_skips_are_all_still_machine_fields():
    """The skip list is the one place this file can hide a real defect.

    A renamed or removed field would leave a substring in `MACHINE_FIELDS` that
    matches nothing — harmless today, but the next field to be given that name
    inherits a silent exemption. So every entry must still resolve to a path the
    served payload actually has.
    """
    items = await _serve([_live_ai_market()])
    futures = [i for i in items if i["type"] == "futures"]
    assert len(futures) == 1, f"the fixture card was not served: {items}"

    paths = [path for path, _ in _every_served_string(futures[0])]
    unmatched = [f for f in MACHINE_FIELDS if not any(f in p for p in paths)]
    assert not unmatched, (
        f"these skips no longer name a served field, so they are exempting "
        f"nothing and may exempt something else later: {unmatched}"
    )


# ── 3. BOTH ROUTE SITES ──────────────────────────────────────────────────────


@pytest.mark.parametrize("scorer", ["_score_futures", "_score_sports_mode_futures"])
def test_both_scoring_sites_humanize_the_names_they_serve(scorer):
    """`_score_sports_mode_futures` is a hand-maintained near-copy.

    The route fixtures above can only reach `_score_futures` (sports mode needs
    a real `Sport` and a `sport_id`), so the /sports rail is held structurally
    instead: both scorers must route their names through the two seams where the
    display name is resolved. Scoped to the FUNCTION's source, not the file's,
    so a call somewhere else in `feed.py` cannot satisfy it.
    """
    source = inspect.getsource(getattr(feed_route, scorer))
    assert "humanize_binary_outcome_name(leader_name" in source, (
        f"{scorer} composes its sentence from a name that never passes through "
        "the display-name seam"
    )
    assert "humanize_outcome_names_for_feed(" in source, (
        f"{scorer} builds its outcome rows without passing them through the "
        "display-name seam"
    )


def test_the_seam_is_where_the_guard_above_thinks_it_is():
    """Proves the slice the structural test asserts on is load-bearing.

    If the display-name resolution ever moves out of the three seams, the test
    above keeps passing while checking nothing. This pins the coupling.

    There are THREE, one per copy of the name in the served payload — the
    sentence, the `top_outcomes` row, and the archetype builder's two label
    lists. The third is the one the first draft of this file did not know about.
    """
    assert "display_outcome_name(" in inspect.getsource(
        fr.humanize_binary_outcome_name
    ), "the sentence seam no longer resolves display names"
    assert "display_outcome_names(" in inspect.getsource(
        fr.humanize_outcome_names_for_feed
    ), "the row seam no longer resolves display names"
    assert "display_outcome_names(" in inspect.getsource(
        archetypes.classify_discover_card_archetype
    ), "the archetype seam no longer resolves display names"
