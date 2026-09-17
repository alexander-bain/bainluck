"""#2602 follow-up — a venue-scoped card must fold across UTC midnight too.

═══ THE DEFECT ═══

`901056400` (merged `4093f86f5`, live v4697 2026-09-17 18:47Z) gave a venue card
an identity that is the PAIR — the promotion its title names plus the venue's own
fight date — so Polymarket's three real cards could form at all. The token it
mints carries the promotion as a suffix::

    venue_card_token(...)  ->  "26sep26ufcfightnight"

`_TOKEN_RE` is anchored (`^(\\d{2})([a-z]{3})(\\d{2})$`), so::

    token_date("26sep26ufcfightnight")  ->  None

and `fold_rollover_tokens` builds its candidate list as ``[... if token_date(t)
is not None ...]``. **Every scoped venue token is therefore filtered out of the
fold entirely.** A venue card that crosses UTC midnight splits into two cards and
can never fold back — the exact defect #1712 and CERT-3018 exist to prevent,
re-opened for the population `901056400` introduced, because the scoped token
retires `fold_rollover_tokens`'s founding invariant that *a token IS its date*.

Reproduced in the real backend by int416 on the merged tree (`92ba2599`), and
again here. Codex Brief15 raised it; the correction shape is codex's.

**It is latent, not live**: all 11 bouts of the 26 Sep card share one
`venue_game_start`, so they mint one token and there is nothing to split. It arms
the moment the venue publishes per-bout starts.

═══ THE RULE ═══

The fold asks its adjacency question of scoped tokens too, and only ever against
a token of the SAME scope. A scoped card never folds into another promotion's
night, and never into a bare date token — that join needs bout evidence, not a
date. Bare tokens keep scope `""`, so the legacy population is untouched.

═══ WHAT THIS IS NOT ═══

Not a container gate, not a promotion-membership rule, and not a cross-venue
join. Codex Brief17 rejected a broader exclusion rule; this is the bounded
correction only. Whether two bouts belong to one promotion stays #5603/#5602.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_combat import (
    card_span_by_token,
    fold_rollover_tokens,
    token_date,
    token_scope,
    venue_card_token,
)
from app.utils.event_ufc import UFCEventAdapter, list_ufc_card_concepts

_CFG = UFCEventAdapter().cfg


def _utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


#: Gotcha #44 — offset FIRST, then truncate, so no fixture can age into
#: `settled` between one run and the next.
def _next_utc_midnight() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(
        days=1
    )


_MONTH_ABBRS = (
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
)  # fmt: skip


def _token_for(d) -> str:
    return f"{d.year % 100:02d}{_MONTH_ABBRS[d.month - 1]}{d.day:02d}"


def _venue_row(mid, name, start, *, event_id=None, listing=None):
    """A COMBAT_PROJECTION row for a Polymarket bout.

    `commence_time` is Gamma's LISTING stamp and is deliberately wrong — every
    one of the 28 open MMA rows carrying both disagrees with `venue_game_start`.
    The card's date must come from the metadata, never from this column.
    """
    meta = {"venue_game_start": start.isoformat().replace("+00:00", "Z")}
    if event_id is not None:
        meta["polymarket_event_id"] = str(event_id)
    return (mid, None, name, listing or (start - timedelta(days=14)), meta)


def _bout(home, away, when, event_id):
    return SimpleNamespace(
        id=event_id, home_team_name=home, away_team_name=away, commence_time=when
    )


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    """The lister's two reads, told apart by name (see the sibling file)."""

    def __init__(self, events=(), outcomes=()):
        self._events = list(events)
        self._outcomes = list(outcomes)

    async def execute(self, statement, *_a, **_k):
        if "futures_outcomes" in str(statement):
            return _FakeResult(self._outcomes)
        return _FakeResult(self._events)


# ── arm 0: the primitive the whole fold is filtered on ─────────────────────


class TestTheTokenGrammarAdmitsAScopedToken:
    def test_a_scoped_token_has_a_date(self):
        """The one-line reproduction of the defect."""
        assert token_date("26sep26ufcfightnight") == datetime(2026, 9, 26).date()
        assert token_date("26sep18powerslap23") == datetime(2026, 9, 18).date()

    def test_a_scoped_token_reports_its_promotion(self):
        assert token_scope("26sep26ufcfightnight") == "ufcfightnight"
        assert token_scope("26sep18powerslap23") == "powerslap23"

    def test_a_bare_token_is_unscoped(self):
        """Keeps the legacy population on scope "" so nothing about it moves."""
        assert token_scope("26sep19") == ""
        assert token_date("26sep19") == datetime(2026, 9, 19).date()

    def test_the_minted_token_is_the_one_the_grammar_reads(self):
        """Pins the two halves together: a change to `venue_card_token`'s shape
        that this grammar could not parse would silently re-disable the fold."""
        minted = venue_card_token(
            _CFG,
            "UFC Fight Night: Elves Brener vs. Josiah Harrell (Lightweight)",
            {"venue_game_start": "2026-09-26T23:00:00Z"},
        )
        assert minted == "26sep26ufcfightnight"
        assert token_date(minted) == datetime(2026, 9, 26).date()
        assert token_scope(minted) == "ufcfightnight"

    def test_a_non_token_is_still_not_a_date(self):
        """The widening admits a promotion suffix, not arbitrary text."""
        for junk in (None, "", "26xxx19", "2026-09-19", "26sep99", "ufcfightnight"):
            assert token_date(junk) is None, junk
        assert token_scope("not-a-token") == ""


# ── arm 1: the fold itself ─────────────────────────────────────────────────


class TestAScopedCardFoldsAcrossMidnight:
    def test_the_two_halves_of_one_venue_night_become_one_card(self):
        survivor = fold_rollover_tokens(
            {
                "26sep26ufcfightnight": (
                    _utc(2026, 9, 26, 22, 0),
                    _utc(2026, 9, 26, 23, 30),
                ),
                "26sep27ufcfightnight": (
                    _utc(2026, 9, 27, 0, 15),
                    _utc(2026, 9, 27, 2, 0),
                ),
            }
        )
        assert survivor["26sep27ufcfightnight"] == "26sep26ufcfightnight"

    def test_a_real_gap_between_two_nights_still_does_not_fold(self):
        """Direction two (gotcha #43): the fold that stopped splitting did not
        start merging. Same promotion, adjacent days, 20 hours apart."""
        survivor = fold_rollover_tokens(
            {
                "26sep26ufcfightnight": (
                    _utc(2026, 9, 26, 2, 0),
                    _utc(2026, 9, 26, 3, 0),
                ),
                "26sep27ufcfightnight": (
                    _utc(2026, 9, 27, 23, 0),
                    _utc(2026, 9, 27, 23, 30),
                ),
            }
        )
        assert survivor["26sep27ufcfightnight"] == "26sep27ufcfightnight"


# ── arm 2: same date, different promotions ─────────────────────────────────


class TestTwoPromotionsNeverFoldIntoEachOther:
    def test_a_neighbouring_promotion_does_not_capture_the_spillover(self):
        """The `by_date` collision int416 went looking for.

        Power Slap runs the 26th; UFC Fight Night runs the 26th into the 27th.
        Keyed on date alone, ONE of the two same-date tokens survives into the
        lookup and the 27th folds into whichever it was — possibly the wrong
        promotion. Scoped, each asks its own night's question.
        """
        survivor = fold_rollover_tokens(
            {
                "26sep26powerslap23": (
                    _utc(2026, 9, 26, 22, 30),
                    _utc(2026, 9, 26, 23, 0),
                ),
                "26sep26ufcfightnight": (
                    _utc(2026, 9, 26, 22, 0),
                    _utc(2026, 9, 26, 23, 30),
                ),
                "26sep27ufcfightnight": (
                    _utc(2026, 9, 27, 0, 15),
                    _utc(2026, 9, 27, 2, 0),
                ),
            }
        )
        assert survivor["26sep27ufcfightnight"] == "26sep26ufcfightnight"
        assert survivor["26sep26powerslap23"] == "26sep26powerslap23"
        assert survivor["26sep26ufcfightnight"] == "26sep26ufcfightnight"

    def test_a_scoped_card_never_folds_into_a_bare_token(self):
        """A bare token is a Kalshi-ticker card. Joining it to a venue card is a
        cross-source identity claim and needs bout evidence, not an adjacent
        date — contiguity here would be a silent cross-source merge.
        """
        survivor = fold_rollover_tokens(
            {
                "26sep26": (_utc(2026, 9, 26, 22, 0), _utc(2026, 9, 26, 23, 30)),
                "26sep27ufcfightnight": (
                    _utc(2026, 9, 27, 0, 15),
                    _utc(2026, 9, 27, 2, 0),
                ),
            }
        )
        assert survivor["26sep27ufcfightnight"] == "26sep27ufcfightnight"

    def test_a_bare_card_never_folds_into_a_scoped_token(self):
        """The same refusal in the other direction."""
        survivor = fold_rollover_tokens(
            {
                "26sep26ufcfightnight": (
                    _utc(2026, 9, 26, 22, 0),
                    _utc(2026, 9, 26, 23, 30),
                ),
                "26sep27": (_utc(2026, 9, 27, 0, 15), _utc(2026, 9, 27, 2, 0)),
            }
        )
        assert survivor["26sep27"] == "26sep27"


# ── arm 3: legacy bare tokens are untouched ────────────────────────────────


class TestTheLegacyPopulationDoesNotMove:
    def test_the_ufc_331_pair_still_folds_exactly_as_before(self):
        """The measured specimen from the sibling file, unchanged."""
        survivor = fold_rollover_tokens(
            card_span_by_token(
                {"26sep19": [_utc(2026, 9, 15, 1, 53), _utc(2026, 9, 20, 7, 20)]},
                {
                    "26sep19": [_utc(2026, 9, 19, 0, 0), _utc(2026, 9, 19, 22, 45)],
                    "26sep20": [_utc(2026, 9, 20, 0, 15), _utc(2026, 9, 20, 7, 20)],
                },
            )
        )
        assert survivor["26sep20"] == "26sep19"

    def test_two_separate_bare_nights_still_do_not_fold(self):
        survivor = fold_rollover_tokens(
            {
                "26sep19": (_utc(2026, 9, 19, 2, 0), _utc(2026, 9, 19, 3, 0)),
                "26sep20": (_utc(2026, 9, 20, 23, 0), _utc(2026, 9, 20, 23, 30)),
            }
        )
        assert survivor["26sep20"] == "26sep20"


# ── arm 4: the lister, where the reader meets it ───────────────────────────


@pytest.mark.asyncio
class TestTheListerServesOneVenueCard:
    async def test_a_venue_card_crossing_midnight_lists_once(self):
        midnight = _next_utc_midnight()
        card_day = (midnight - timedelta(days=1)).date()
        starts = [
            midnight - timedelta(hours=2),
            midnight - timedelta(hours=1),
            midnight + timedelta(minutes=30),
            midnight + timedelta(hours=1, minutes=30),
        ]
        names = [
            "UFC Fight Night: Elves Brener vs. Josiah Harrell (Lightweight)",
            "UFC Fight Night: Brady Hiestand vs. Rinya Nakamura (Bantamweight)",
            "UFC Fight Night: Robert Bryczek vs. Rodolfo Vieira (Middleweight)",
            "UFC Fight Night: Raoni Barcelos vs. Raul Rosas Jr. (Bantamweight)",
        ]
        rows = [
            _venue_row(700 + i, n, s, event_id=900 + i)
            for i, (n, s) in enumerate(zip(names, starts))
        ]

        concepts = await list_ufc_card_concepts(
            _FakeDB(), statuses=("upcoming", "live"), rows=rows
        )

        assert [c["key"] for c in concepts] == [
            f"event:ufc:{_token_for(card_day)}ufcfightnight"
        ]
        assert concepts[0]["fight_count"] == len(names)

    async def test_two_promotions_on_the_same_night_still_list_twice(self):
        """The ship #2602 delivered — two promotions are two cards — survives
        the fold being taught to read their tokens."""
        midnight = _next_utc_midnight()
        card_day = (midnight - timedelta(days=1)).date()
        rows = [
            _venue_row(
                801,
                "UFC Fight Night: Elves Brener vs. Josiah Harrell (Lightweight)",
                midnight - timedelta(hours=2),
                event_id=901,
            ),
            _venue_row(
                802,
                "Power Slap 23: Brandon Wilson vs. Brian Ellis (Fight 1)",
                midnight - timedelta(hours=1),
                event_id=902,
            ),
        ]
        concepts = await list_ufc_card_concepts(
            _FakeDB(), statuses=("upcoming", "live"), rows=rows
        )
        assert {c["key"] for c in concepts} == {
            f"event:ufc:{_token_for(card_day)}ufcfightnight",
            f"event:ufc:{_token_for(card_day)}powerslap23",
        }


# ── arm 5: the page must agree with the feed ───────────────────────────────


class TestThePageAgreesWithTheFeedOnAVenueCard:
    """A card the feed serves once must not open a page holding half of it."""

    def _markets(self):
        return [
            SimpleNamespace(
                external_id=None,
                name="UFC Fight Night: Elves Brener vs. Josiah Harrell (Lightweight)",
                commence_time=_utc(2026, 9, 12, 22, 0),  # the LISTING stamp
                market_metadata={"venue_game_start": "2026-09-26T22:00:00Z"},
                outcomes=[object(), object()],
            ),
            SimpleNamespace(
                external_id=None,
                name="UFC Fight Night: Raoni Barcelos vs. Raul Rosas Jr. (Bantamweight)",
                commence_time=_utc(2026, 9, 12, 22, 0),
                market_metadata={"venue_game_start": "2026-09-27T00:15:00Z"},
                # Most venue bouts are NOT two-sided moneylines; the page's span
                # read must not filter them the way the ticker path does.
                outcomes=[],
            ),
        ]

    def test_both_halves_of_a_venue_card_resolve_to_the_whole_card(self):
        adapter = UFCEventAdapter()
        for slug in ("26sep26ufcfightnight", "26sep27ufcfightnight"):
            assert adapter._folded_card_tokens(slug, self._markets(), {}) == {
                "26sep26ufcfightnight",
                "26sep27ufcfightnight",
            }, slug

    def test_an_unrelated_promotion_is_not_swept_into_the_page(self):
        adapter = UFCEventAdapter()
        markets = self._markets() + [
            SimpleNamespace(
                external_id=None,
                name="Power Slap 23: Brandon Wilson vs. Brian Ellis (Fight 1)",
                commence_time=_utc(2026, 9, 12, 22, 0),
                market_metadata={"venue_game_start": "2026-09-26T22:30:00Z"},
                outcomes=[object(), object()],
            )
        ]
        assert "26sep26powerslap23" not in adapter._folded_card_tokens(
            "26sep26ufcfightnight", markets, {}
        )


def test_both_callers_still_build_their_span_the_same_way():
    """Named pin, inherited from the sibling file: the feed card and the page
    behind it fold independently, so a rule applied to one and not the other is
    a card that lists once and opens half-empty."""
    from app.utils import event_combat

    for source in (
        inspect.getsource(event_combat.list_card_concepts),
        inspect.getsource(event_combat.CombatEventAdapter._folded_card_tokens),
    ):
        assert "card_span_by_token(" in source
