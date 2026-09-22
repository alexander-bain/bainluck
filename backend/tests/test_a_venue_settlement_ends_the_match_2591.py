"""A MATCH THE VENUE HAS ALREADY PAID OUT ON STOPS SAYING IT IS LIVE — #2591/#7878.

═══ WHAT THIS SUITE IS FOR ═══

``EVENT-GRAPH-DOCTRINE`` §R wrote the state ladder on 2026-09-02 and closed with
one open item:

    authority state  >  venue settlement  >  scores  >  (never) price

    "Rung 2 (venue settlement) is DECLARED here and not yet wired into either
     net."

Nineteen days later it still was not, and the hole is the one a reader sees.
Rung 1 does not cover ATP/WTA challengers, Serie C, Ettan or CS2 — doctrine
rule 8 calls those venue-authority-of-last-resort — so for those matches nothing
above rung 4 ever speaks, and the only thing that can take the row off the live
board is a wall clock, which §R puts below every rung. Until that clock runs out
the row keeps its LIVE badge, and ``_extend_win_prob_history_to_live_edge``
(#920) keeps extending a synthetic flat line from the last real capture out to
*now*: the longer the match has been over, the more confident the chart looks
about it.

The arm writes the SAME word the staleness arm below it does — the entitlement
differs, the destination does not, and the reasoning (with the counts that
decided it) is on ``SUSPEND_ON_VENUE_SETTLEMENT_SQL``. What changes for a reader
is WHEN: hours earlier, and on rows a clock reaches late or not at all.

═══ THE SPECIMENS, BOTH MEASURED ON PRODUCTION 2026-09-21 ═══

**The ship**, photographed at 22:40Z. `/events/15316500` — Manzano v Pieri,
`tennis_atp`, stored kickoff 21:30Z — renders a ``LIVE`` badge with a **20-second
refresh countdown**, a hero reading **"No price"**, and a dead-flat 99% win-
probability line drawn from 2:30 PM to **3:38 PM**, the read minute. Kalshi
settled `KXATPCHALLENGERMATCH-26SEP21MARPIE` at **20:40:19Z**, two hours before
the shot. The row is 67 minutes past its stored kickoff against a 3.0h
unobserved tennis bound, so the staleness arm could not have touched it for
another two hours — and every one of those minutes lengthens the flat segment.

Its sibling `15316478` Goffin v Lajal, settled 17:50Z, had by then aged into
``suspended`` and reads **"Settled · Lajal wins"** — which is what this arm
delivers two hours sooner, and the reason it writes that word.

**The near-miss, and it is why this suite is not one assert.** `15315003`
Huskies eSport vs. BIG Academy, `esports`. Its settlements arrive in the order
a best-of-three does: ``Map 1`` **19:14:45Z**, ``Map 2`` 20:06Z, ``Total Maps``
20:44Z, and the match itself **20:49:37Z**. A rule that read "this event has a
resolved market" would have ended that match at 19:14 — **1h35m early, with
Map 2 still being played.** `15315004` is 1h49m,
`15314994` 36m. Three of the thirty live events on one evening's slate.

Same defect class as #5432/#5311 (a derivative published as the match result),
and the same one ``content_understanding``'s ``child_moneyline`` disagreement
catches at ingest. Here it is caught by
:func:`~app.utils.game_market_class.classify_game_market_class`, whose ordering
takes props, totals, spreads and ticker tells BEFORE the bare-matchup winner.

═══ RED-FIRST ═══

Verified by reverting ONLY ``event_completion.py`` and ``espn_sync.py`` and
re-running this file: every case in :class:`TestTheSettledMatchComesOffTheLiveBoard`
goes red, and the refusal cases in :class:`TestADerivativeIsNotTheMatch` and
:class:`TestTheHealthyDirectionIsUntouched` stay GREEN in both arms — they must,
because a refusal that only passes after the fix is just re-reporting that the
arm exists, not that it declines.
"""
import contextlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.utils.event_completion import (
    DRAWN_CONTEST_OUTCOMES,
    EVENT_SUSPENDED,
    FULL_CONTEST_WINNER_CLASS,
    venue_settlement_ends_the_match,
    winning_outcome_names_a_competitor,
)
from app.utils.game_market_class import classify_game_market_class
from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    DETERMINISTIC_SOURCES,
    GUESS_FAMILY_SOURCES,
    TERMINAL_SOURCES,
)

NOW = datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc)

#: The Goffin v Lajal market, verbatim from production.
GOFFIN = ("Goffin vs Lajal", "KXATPCHALLENGERMATCH-26SEP21GOFLAJ", "tennis_atp")

#: The photographed specimen's market, verbatim. Kalshi settled it 20:40:19Z.
MANZANO = ("Martin Manzano vs Pieri", "KXATPCHALLENGERMATCH-26SEP21MARPIE",
           "tennis_atp")

#: How far past its stored kickoff the photographed row was when the LIVE badge
#: and the 20-second countdown were shot. Deliberately well INSIDE every bound
#: the staleness arm could apply (tennis unobserved 3.0h, sport maximum 6.0h, and
#: the arm's own +0.5h margin on top) — a specimen sitting near a boundary would
#: let a change to that constant make these cases pass for the wrong reason.
SETTLED_BUT_STILL_BADGED_LIVE = timedelta(minutes=67)

#: The Huskies ladder, verbatim, in settlement order. The last entry is the
#: match; the three before it are the ones that must not end it.
HUSKIES_LADDER = [
    ("Huskies eSport vs. BIG Academy: Map 1",
     "KXCS2MAP-26SEP211400HUSKBIGA-1", "19:14:45Z"),
    ("Huskies eSport vs. BIG Academy: Map 2",
     "KXCS2MAP-26SEP211400HUSKBIGA-2", "20:06Z"),
    ("Huskies eSport vs. BIG Academy: Total Maps",
     "KXCS2TOTALMAPS-26SEP211400HUSKBIGA", "20:44Z"),
]
HUSKIES_MATCH = ("Huskies eSport vs. BIG Academy",
                 "KXCS2GAME-26SEP211400HUSKBIGA", "20:49:37Z")


def _decides(
    name,
    ticker,
    sport="esports",
    status="resolved",
    winner_outcome="Huskies eSport",
    home="Huskies eSport",
    away="BIG Academy",
    # 🪤 THIS ARGUMENT STAYS LAST, and the reason is measured rather than
    # guessed. gitleaks' generic-api-key rule keys on the first three letters
    # of this value's name and then captures the next quoted value it finds —
    # ACROSS THE NEWLINE. So it is not "keep it on its own line"; it is "do not
    # let a quoted literal follow it". Here it is followed by the closing
    # paren, which is the arrangement that passes; the sibling helper below
    # passes because `None` follows it. Two CI reds were spent learning this.
    # Nothing is a credential — the value is a resolution_source enum used
    # across this repo — and nothing needs rotating.
    source="api_settlement",
):
    """Run the production trio — classifier, answer test, predicate — on one market.

    The outcome/team defaults name a competitor, so every case that predates
    conjunct 4 still exercises exactly the conjunct it was written for. The
    cases that exercise conjunct 4 itself pass ``winner_outcome`` explicitly.
    """
    return venue_settlement_ends_the_match(
        classify_game_market_class(name, ticker, sport),
        status,
        source,
        winning_outcome_names_a_competitor(winner_outcome, home, away),
    )


# ═══════════════════════════════════════════════════════════════════════════
# The predicate, on the rows that produced it
# ═══════════════════════════════════════════════════════════════════════════

class TestTheVenuesWordOnTheContest:
    def test_the_settled_tennis_match_is_over(self):
        assert _decides(GOFFIN[0], GOFFIN[1], GOFFIN[2]) is True

    def test_the_settled_esports_match_is_over(self):
        assert _decides(HUSKIES_MATCH[0], HUSKIES_MATCH[1]) is True

    @pytest.mark.parametrize("name,ticker", [
        ("Spezia vs Pesaro", "KXSERIECGAME-26SEP21SPEP98"),
        ("Vasalunds vs Assyriska", "KXETTANGAME-26SEP21VIFASS"),
        ("Samson vs Basiletti", "KXWTACHALLENGERMATCH-26SEP21SAMBAS"),
    ])
    def test_the_rest_of_the_measured_slate_reads_the_same(self, name, ticker):
        assert _decides(name, ticker, "soccer_other") is True

    def test_an_open_market_at_ninety_nine_percent_decides_nothing(self):
        """§R rung 4: a price is a price. It is also the state these rows are
        in for the two hours BEFORE the venue settles, so admitting `open`
        would end every blowout at its first lopsided quote."""
        assert _decides(GOFFIN[0], GOFFIN[1], GOFFIN[2], status="open") is False

    def test_an_ungraded_settlement_decides_nothing(self):
        """Five of the thirty measured events are here: the venue closed the
        market and no leg carries a winner. `15312683` (Nueva Chicago v
        Patronato) has fourteen such markets. The row IS finished, but nothing
        we can read says so, and this arm only ever speaks for the venue."""
        assert _decides(GOFFIN[0], GOFFIN[1], GOFFIN[2], source=None) is False


class TestADerivativeIsNotTheMatch:
    """The 1h35m. Each of these settles while the match is still being played."""

    @pytest.mark.parametrize("name,ticker,settled", HUSKIES_LADDER)
    def test_no_rung_of_the_huskies_ladder_ends_the_match(
        self, name, ticker, settled
    ):
        assert _decides(name, ticker) is False, (
            f"{name!r} settled at {settled}; the match settled at "
            f"{HUSKIES_MATCH[2]}"
        )

    def test_the_match_itself_does_end_it(self):
        """The other half of the pair: a refusal test that never admits
        anything is satisfied by a predicate that returns False always."""
        assert _decides(*HUSKIES_MATCH[:2]) is True

    @pytest.mark.parametrize("name", [
        "Nueva Chicago vs. CA Patronato Parana: O/U 2.5",
        "Nueva Chicago vs. CA Patronato Parana: Both Teams to Score",
        "Nueva Chicago vs. CA Patronato Parana: 1st Half O/U 0.5",
        "Reveal vs. Pandaric eSports: Total Maps",
    ])
    def test_a_settled_side_market_never_ends_the_match(self, name):
        assert _decides(name, None, "soccer_other") is False

    def test_a_set_winner_does_not_end_a_tennis_match(self):
        """Polymarket settles a tennis ladder set by set (#2591's own comment
        measured Set 1 at 16:00Z against a moneyline at 17:39Z)."""
        assert _decides("Rinaldo Persson vs Pigato: Set 1 Winner",
                        "KXATPSETWINNER-26SEP16RINPIG", "tennis_atp") is False


#: The production specimen that bounced CERT-3264, read 2026-09-22 00:1xZ.
#: Kalshi market 1028088 is named exactly the matchup and settles NRFI, while
#: event 15316384 was in the Top of the 7th at 9-0 with an ESPN anchor.
NRFI_MARKET = ("Washington Nationals vs. Detroit Tigers", "1028088", "baseball_mlb")
NRFI_SIDES = ("Detroit Tigers", "Washington Nationals")


class TestADerivativeWearingTheMatchsOwnName:
    """#2591 conjunct 4. The derivative the NAME cannot betray.

    Conjunct 1 refuses everything that announces itself — ``: Map 1``,
    ``: Total Maps``, ``- Halftime Result``. This class is the shape it cannot
    reach, and it is not hypothetical: without conjunct 4 the arm suspended a
    live MLB game in review.
    """

    def test_the_nrfi_market_does_not_end_the_live_mlb_game(self):
        assert _decides(
            *NRFI_MARKET, winner_outcome="NRFI",
            home=NRFI_SIDES[0], away=NRFI_SIDES[1],
        ) is False

    def test_and_every_other_conjunct_had_said_yes(self):
        """The point of conjunct 4: 1, 2 and 3 all pass this row.

        If this ever goes red because the classifier learned to refuse the name,
        conjunct 4 is no longer what saves the game and this suite should say so
        rather than stay green on a different reason.
        """
        assert classify_game_market_class(*NRFI_MARKET) == FULL_CONTEST_WINNER_CLASS
        assert venue_settlement_ends_the_match(
            FULL_CONTEST_WINNER_CLASS, "resolved", "api_settlement",
            True,  # ← pretend the answer names a competitor
        ) is True

    def test_the_correctly_named_twin_is_refused_by_the_classifier(self):
        """The venue publishes the same question twice; only one is nameable."""
        assert classify_game_market_class(
            "Will there be a run scored in the first inning?: "
            "Washington Nationals vs. Detroit Tigers",
            "1028088", "baseball_mlb",
        ) != FULL_CONTEST_WINNER_CLASS

    @pytest.mark.parametrize("outcome", ["NRFI", "YRFI", "Over", "Yes", "2 - 1"])
    def test_an_answer_to_another_question_never_ends_a_match(self, outcome):
        assert winning_outcome_names_a_competitor(outcome, *NRFI_SIDES) is False


class TestConjunctFourKeepsTheRowsTheShipIsFor:
    """The casualty half. A guard that only refuses is a guard that breaks the ship.

    These are the real 2026-09-22 00:3xZ rows: the venue answers with a FULL
    name where we store a surname.
    """

    @pytest.mark.parametrize("winner,home,away", [
        ("Juan Cruz Martin Manzano", "Martin Manzano", "Pieri"),
        ("Sebastian Gorzny", "Mayo", "Gorzny"),
        ("Timo Legout", "Legout", "Ostapenkov"),
        ("Erik Arutiunian", "Fenty", "Arutiunian"),
        ("EAC Extra", "ECSTATIC", "EAC Extra"),
        ("Dominica", "Dominica", "Anguilla"),
        ("Detroit", "Detroit Tigers", "Washington Nationals"),
    ])
    def test_a_settled_contest_still_ends(self, winner, home, away):
        assert winning_outcome_names_a_competitor(winner, home, away) is True

    @pytest.mark.parametrize("drawn", sorted(DRAWN_CONTEST_OUTCOMES) + ["Draw", "TIE"])
    def test_a_drawn_contest_is_still_a_finished_contest(self, drawn):
        assert winning_outcome_names_a_competitor(drawn, "Dominica", "Anguilla") is True

    def test_a_name_that_names_both_sides_names_neither(self):
        """resolve_team_side's fail-safe, kept rather than reinvented."""
        assert winning_outcome_names_a_competitor(
            "New York", "New York Yankees", "New York Mets"
        ) is False

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_an_absent_answer_fails_closed(self, empty):
        assert winning_outcome_names_a_competitor(empty, *NRFI_SIDES) is False

    def test_the_prefix_helper_would_have_lost_these_rows(self):
        """Why this arm does not call :func:`resolve_team_side`, pinned.

        Its containment is a prefix test and the venue's full names are
        suffixes. If someone later 'simplifies' conjunct 4 onto that helper,
        this goes red and names the four tennis rows it would cost. If the
        helper is ever widened so this passes, this test is the place that says
        the two rules have converged — read it, do not delete it.
        """
        from app.utils.team_side import resolve_team_side

        lost = [
            (w, h, a) for w, h, a in [
                ("Juan Cruz Martin Manzano", "Martin Manzano", "Pieri"),
                ("Sebastian Gorzny", "Mayo", "Gorzny"),
                ("Timo Legout", "Legout", "Ostapenkov"),
                ("Erik Arutiunian", "Fenty", "Arutiunian"),
            ]
            if resolve_team_side(w, h, a) is None
        ]
        assert len(lost) == 4, (
            "resolve_team_side now resolves these; conjunct 4 could be "
            f"reconsidered against it. Still lost: {lost}"
        )

    def test_the_two_draw_vocabularies_have_not_drifted(self):
        from app.utils.market_shape import _DRAW_TOKENS

        assert set(DRAWN_CONTEST_OUTCOMES) == set(_DRAW_TOKENS)


class TestAnAsciiVenueNameStillNamesAnAccentedCompetitor:
    """The venue writes `Frolunda HC`; we store `Frölunda HC`. #2591 rung 3.

    These four are the ENTIRE convertible residual of the 563 reader-reachable
    suspended rows, measured on production 2026-09-22 06:4xZ by replaying this
    predicate over all 1,336 graded winning legs: supported 160 → 164,
    **LOST 0**. None of the four has a completed twin carrying the score, so
    without the fold nothing in the system ever finishes them.

    The refusal half below is the load-bearing half. An accent fold is the only
    thing being bought: every other way of failing to match a name — an
    abbreviation, an acronym, a nickname, an unorientable ``Yes`` — must keep
    failing closed, because conjunct 4's whole job is to not end a match it
    cannot orient.
    """

    #: (venue's settled answer, our home, our away) — real production rows.
    ASCII_AGAINST_ACCENTED = [
        ("Frolunda HC", "Frölunda HC", "Växjö Lakers"),
        ("Malmo Redhawks", "HV71", "Malmö Redhawks"),
        ("Porin Assat", "Ässät", "Kiekko-Espoo"),
        ("Oulun Karpat", "Kärpät", "Sport"),
    ]

    @pytest.mark.parametrize("winner,home,away", ASCII_AGAINST_ACCENTED)
    def test_the_fold_lets_the_settlement_through(self, winner, home, away):
        assert winning_outcome_names_a_competitor(winner, home, away) is True

    @pytest.mark.parametrize("winner,home,away", ASCII_AGAINST_ACCENTED)
    def test_without_the_fold_every_one_of_them_is_stranded(
        self, winner, home, away, monkeypatch
    ):
        """The mutation, run in-suite rather than trusted.

        Sever the fold and each row must go back to being refused. A test that
        stays green with ``_fold_diacritics`` neutered is asserting something
        the normaliser already did, not the fix.
        """
        import app.utils.event_completion as ec

        monkeypatch.setattr(ec, "_fold_diacritics", lambda text: text)
        assert ec.winning_outcome_names_a_competitor(winner, home, away) is False

    @pytest.mark.parametrize("winner,home,away", [
        # An abbreviation is not an accent. (`15304466`, and that event already
        # has a completed twin `15306772` 30-20 — it is #7345/#2693's, not ours.)
        ("San Jose St.", "San Jose State Spartans", "Cal Poly Mustangs"),
        # Nor is an acronym. (`15312459`.)
        ("United Arab Emirates", "Malaysia", "UAE"),
        # Nor is a bare-matchup market answering `Yes` — nothing orients it, and
        # twelve of the residual look exactly like this. (`15313488`.)
        ("Yes", "Ässät", "Kiekko-Espoo"),
    ])
    def test_the_fold_buys_nothing_but_accents(self, winner, home, away):
        assert winning_outcome_names_a_competitor(winner, home, away) is False

    def test_the_fold_does_not_reopen_the_live_mlb_game(self):
        """Conjunct 4's own specimen, re-asserted through the new code path."""
        assert winning_outcome_names_a_competitor("NRFI", *NRFI_SIDES) is False

    def test_the_fold_does_not_break_the_both_sides_fail_safe(self):
        assert winning_outcome_names_a_competitor(
            "Växjö", "Växjö Lakers", "Vaxjo Lakers HC"
        ) is False

    def test_it_folds_accents_and_is_not_a_transliterator(self):
        """`ß` is deliberately left alone — NFKD does not decompose it, and
        mapping it to `ss` would be a policy call wearing a normaliser's coat.
        """
        from app.utils.event_completion import _fold_diacritics

        assert _fold_diacritics("Frölunda Ässät Kärpät") == "Frolunda Assat Karpat"
        assert _fold_diacritics("Weiß") == "Weiß"
        assert _fold_diacritics("") == ""

    def test_the_fold_is_not_in_the_shared_normaliser(self):
        """The architectural constraint, pinned so a later tidy-up cannot
        silently move it.

        ``normalize_team_text`` is reached by ``resolve_team_side``, whose
        readers include ``prediction_market_matching`` — the market→event
        LINKAGE path. Folding there would widen the matcher as a side effect of
        an event-completion fix. If someone moves the fold into the shared
        helper, this goes red and says why it was kept local.
        """
        from app.utils.team_side import normalize_team_text

        assert normalize_team_text("Frölunda HC") == "frölunda hc"


class TestOnlyTheVenueMaySpeak:
    """Tier 3 and nothing else — ruling 038's invariant read from this side."""

    @pytest.mark.parametrize("source", sorted(AUTHORITATIVE_SOURCES))
    def test_every_tier_three_source_may_end_a_match(self, source):
        assert _decides(GOFFIN[0], GOFFIN[1], GOFFIN[2], source=source) is True

    @pytest.mark.parametrize("source", sorted(
        DETERMINISTIC_SOURCES | TERMINAL_SOURCES | GUESS_FAMILY_SOURCES
    ))
    def test_no_lower_tier_source_may(self, source):
        assert _decides(GOFFIN[0], GOFFIN[1], GOFFIN[2], source=source) is False

    def test_a_grade_computed_from_our_own_scores_may_not(self):
        """The one that would reopen CAL-P002 if it were admitted. `game_score`
        grades from `events.home_score`/`away_score` — the very columns on the
        row this arm is about to settle — so it would let a frozen mid-game
        score end the match it was frozen from (ruling 038)."""
        assert "game_score" in DETERMINISTIC_SOURCES
        assert _decides(GOFFIN[0], GOFFIN[1], GOFFIN[2],
                        source="game_score") is False

    def test_an_unclassified_source_fails_safe(self):
        """`authority_tier` answers -1 for a source nobody has classified, so a
        resolution_source added without being placed on the ladder cannot end a
        match by being new."""
        assert _decides(GOFFIN[0], GOFFIN[1], GOFFIN[2],
                        source="a_source_invented_next_tuesday") is False


class TestTheTwoModulesAgreeOnTheWord:
    def test_the_winner_class_string_has_not_drifted(self):
        """`event_completion` spells the class rather than importing it, to
        avoid pulling `app.services` into a pure module. That is only safe
        while this assert exists."""
        from app.utils.content_understanding import (
            FULL_CONTEST_WINNER_CLASS as THEIRS,
        )
        assert FULL_CONTEST_WINNER_CLASS == THEIRS

    def test_the_classifier_still_emits_that_word(self):
        assert classify_game_market_class(*GOFFIN) == FULL_CONTEST_WINNER_CLASS


# ═══════════════════════════════════════════════════════════════════════════
# End to end, through the real net
# ═══════════════════════════════════════════════════════════════════════════

class _Ev:
    def __init__(self, id, sport_key, commence_time, status="live",
                 home="Goffin", away="Lajal"):
        self.id = id
        self.status = status
        self.commence_time = commence_time
        self.completed_at = None
        self.home_score = None
        self.away_score = None
        self.period = None
        self.espn_id = None
        self.statpal_fixture_id = None
        self.win_probability_sources = {}
        self.home_team_name = home
        self.away_team_name = away
        self.sport = SimpleNamespace(key=sport_key)


def _candidate(ev, name, ticker, market_status="resolved",
               winner_source="api_settlement", winner_outcome_name=None):
    # The winning leg defaults to naming the home side, because that is what a
    # real settled contest answers with and it keeps every case written before
    # conjunct 4 testing the conjunct it was written for. A case that wants the
    # NRFI shape — an answer to a different question wearing the match's name —
    # passes ``winner_outcome_name`` explicitly.
    return SimpleNamespace(
        event_id=ev.id,
        home_team_name=ev.home_team_name,
        away_team_name=ev.away_team_name,
        sport_key=ev.sport.key,
        market_name=name,
        market_external_id=ticker,
        market_status=market_status,
        winner_outcome_name=(
            ev.home_team_name if winner_outcome_name is None else winner_outcome_name
        ),
        winner_source=winner_source,
    )


class _NetSession:
    """Same positional-select fake as the sibling suites, plus the rung-2 read.

    The UPDATE is applied back onto the rows, because the arm writes Core SQL
    and a fake that only records the statement cannot tell a CAS that matched
    from one that did not.
    """

    def __init__(self, live, candidates):
        # scheduled, live, suspended, bogus-completed, future-settled, #2772.
        self._selects = [[], live, [], [], [], []]
        self._live = live
        self._candidates = candidates
        self.updates = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "AS winner_source" in sql:
            return SimpleNamespace(all=lambda: list(self._candidates))
        if "GROUP BY x.event_id" in sql:
            return SimpleNamespace(all=lambda: [])
        if sql.strip().upper().startswith("UPDATE"):
            ids = set((params or {}).get("event_ids", []))
            matched = [e for e in self._live if e.id in ids and e.status == "live"]
            for ev in matched:
                ev.status = EVENT_SUSPENDED
            self.updates.append((sorted(ids), len(matched)))
            return SimpleNamespace(rowcount=len(matched))
        rows = self._selects.pop(0)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    async def commit(self):
        pass


async def _run_net(live, candidates, now=NOW):
    session = _NetSession(live, candidates)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.espn_sync as mod

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch("app.tasks.base.get_task_session", _fake_session), \
            patch.object(mod, "datetime", _FrozenNow):
        stats = await mod._transition_event_statuses_impl()
    return session, stats


def _manzano():
    """The photographed specimen: 67 minutes past its stored kickoff, badged
    LIVE with a 20s countdown, two hours after Kalshi paid out on it."""
    return _Ev(15316500, "tennis_atp", NOW - SETTLED_BUT_STILL_BADGED_LIVE,
               home="Manzano", away="Pieri")


class TestTheSettledMatchComesOffTheLiveBoard:
    @pytest.mark.asyncio
    async def test_it_comes_off_the_live_board(self):
        ev = _manzano()
        _, stats = await _run_net([ev], [_candidate(ev, MANZANO[0], MANZANO[1])])
        assert ev.status == EVENT_SUSPENDED
        assert stats["suspended_by_venue_settlement"] == 1

    @pytest.mark.asyncio
    async def test_it_is_stamped_with_no_completion_time(self):
        """The venue settles a MARKET. On 20 of the 25 measured rows its
        settlement instant lands BEFORE our stored `commence_time` (gotcha #14),
        so spending it as a game-end time would invert `completed_at >=
        commence_time` (gotcha #46) on most of the population and file a
        matching-layer P1 for what is really a clock-provenance bug.

        The status assert is not decoration: without it this case passes on
        pre-fix source, where the row is inside its bound and NOTHING writes a
        completion time. It has to prove the arm fired and still wrote none."""
        ev = _manzano()
        await _run_net([ev], [_candidate(ev, MANZANO[0], MANZANO[1])])
        assert ev.status == EVENT_SUSPENDED
        assert ev.completed_at is None

    @pytest.mark.asyncio
    async def test_no_score_is_invented_for_it(self):
        ev = _manzano()
        await _run_net([ev], [_candidate(ev, MANZANO[0], MANZANO[1])])
        assert ev.status == EVENT_SUSPENDED
        assert ev.home_score is None and ev.away_score is None

    @pytest.mark.asyncio
    async def test_the_cas_reports_what_it_actually_wrote(self):
        """A row something else settled between the SELECT and the UPDATE is a
        no-op, not a demotion of that verdict, and the counter says so."""
        ev = _manzano()
        ev.status = "completed"
        _, stats = await _run_net([ev], [_candidate(ev, MANZANO[0], MANZANO[1])])
        assert ev.status == "completed"
        assert stats["suspended_by_venue_settlement"] == 0

    @pytest.mark.asyncio
    async def test_it_is_not_then_suspended_by_the_next_arm(self):
        """Both arms select live rows and the settlement runs first. A row it
        took off the board must not be picked up as a stale live row four
        lines later and counted a second time — it lands in the same state, so
        the corruption is not the status but the ATTRIBUTION: `live_to_suspended`
        is the number that says how often we are reasoning from a clock."""
        ev = _Ev(15316478, "tennis_atp", NOW - timedelta(hours=7),
                 home="Goffin", away="Lajal")
        _, stats = await _run_net([ev], [_candidate(ev, MANZANO[0], MANZANO[1])])
        assert ev.status == EVENT_SUSPENDED
        assert stats["live_to_suspended"] == 0


class TestTheDerivativeLadderThroughTheNet:
    @pytest.mark.asyncio
    async def test_a_match_with_only_a_settled_map_stays_live(self):
        """19:14:45Z on the Huskies ladder. Map 2 is still being played.

        Status only, no counter: this case must be GREEN against pre-fix source
        too, and a `stats[...]` read on a key the old net does not emit raises
        rather than asserts. A control that goes red is not telling you the
        healthy direction survived — it is re-reporting that the arm is
        missing, which the behavioural cases already say."""
        ev = _Ev(15315003, "esports", NOW - timedelta(hours=1),
                 home="Huskies eSport", away="BIG Academy")
        name, ticker, _ = HUSKIES_LADDER[0]
        await _run_net([ev], [_candidate(ev, name, ticker)])
        assert ev.status == "live"

    @pytest.mark.asyncio
    async def test_the_refusal_is_counted_not_inferred(self):
        """"We looked and declined" must be distinguishable from "we never
        looked" (gotcha #53) — otherwise a selector that silently stops
        returning candidates reads exactly like a clean night."""
        ev = _Ev(15315003, "esports", NOW - timedelta(hours=1))
        name, ticker, _ = HUSKIES_LADDER[0]
        _, declined = await _run_net([ev], [_candidate(ev, name, ticker)])
        _, looked_at_nothing = await _run_net([ev], [])
        assert declined["held_derivative_settlement_only"] == 1
        assert looked_at_nothing["held_derivative_settlement_only"] == 0

    @pytest.mark.asyncio
    async def test_the_full_ladder_closes_it_once_the_match_settles(self):
        """The same event, four settled markets, one of them the contest."""
        ev = _Ev(15315003, "esports", NOW - timedelta(hours=1))
        rows = [_candidate(ev, n, t) for n, t, _ in HUSKIES_LADDER]
        rows.append(_candidate(ev, HUSKIES_MATCH[0], HUSKIES_MATCH[1]))
        _, stats = await _run_net([ev], rows)
        assert ev.status == EVENT_SUSPENDED
        assert stats["suspended_by_venue_settlement"] == 1
        assert stats["held_derivative_settlement_only"] == 0


class TestTheLiveMlbGameStaysOnTheBoard:
    """#2591 conjunct 4, through the real net. The regression CERT-3264 caught.

    Event 15316384 on 2026-09-22 00:1xZ: Tigers/Nationals, Top of the 7th, 9-0,
    ESPN-anchored, one resolved market named exactly the matchup and settling
    NRFI. Every conjunct but the fourth says end it.
    """

    @pytest.mark.asyncio
    async def test_a_game_in_the_seventh_is_not_suspended_by_an_nrfi_leg(self):
        ev = _Ev(15316384, "baseball_mlb", NOW - timedelta(hours=1),
                 home="Detroit Tigers", away="Washington Nationals")
        ev.espn_id = "401817028"
        ev.period = "Top 7th"
        ev.home_score, ev.away_score = 9, 0
        _, stats = await _run_net(
            [ev],
            [_candidate(ev, *NRFI_MARKET[:2], winner_outcome_name="NRFI")],
        )
        assert ev.status == "live"
        assert stats["suspended_by_venue_settlement"] == 0
        assert stats["held_derivative_settlement_only"] == 1

    @pytest.mark.asyncio
    async def test_the_same_game_does_end_when_the_real_winner_settles(self):
        """The refusal above is not a predicate that says no to everything."""
        ev = _Ev(15316384, "baseball_mlb", NOW - timedelta(hours=1),
                 home="Detroit Tigers", away="Washington Nationals")
        _, stats = await _run_net(
            [ev],
            [_candidate(ev, *NRFI_MARKET[:2], winner_outcome_name="Detroit Tigers")],
        )
        assert ev.status == EVENT_SUSPENDED
        assert stats["suspended_by_venue_settlement"] == 1


class TestTheHealthyDirectionIsUntouched:
    """Green against pre-fix source too. These pin what must NOT change."""

    @pytest.mark.asyncio
    async def test_a_live_match_nobody_has_settled_is_left_alone(self):
        ev = _manzano()
        await _run_net([ev], [])
        assert ev.status == "live"
        assert ev.completed_at is None

    @pytest.mark.asyncio
    async def test_the_wall_clock_could_not_have_moved_the_specimen(self):
        """The control that makes `test_it_comes_off_the_live_board` mean
        anything. At
        three hours the tennis bound (6.0h) has not elapsed, so with the rung-2
        evidence withheld the SAME row on the SAME clock stays live — the
        transition is the settlement's doing and nothing else's."""
        ev = _manzano()
        await _run_net([ev], [])
        assert ev.status == "live"

    @pytest.mark.asyncio
    async def test_a_row_past_its_sport_bound_still_suspends(self):
        """The staleness arm keeps its population. Seven hours of tennis with
        nothing reporting on it is still `suspended`, and it is counted as
        `live_to_suspended` — the clock's verdict, not the venue's."""
        ev = _Ev(15295047, "tennis_atp", NOW - timedelta(hours=7))
        _, stats = await _run_net([ev], [])
        assert ev.status == "suspended"
        assert stats["live_to_suspended"] == 1
