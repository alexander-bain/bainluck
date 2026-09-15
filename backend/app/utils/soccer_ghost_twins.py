"""Which two soccer rows are one fixture, and which of the two is the ghost. #5896.

**SHIP: a La Liga match that finished yesterday stops being advertised as
tonight's kick-off.** (Pillar: MATCHING.)

This is the JUDGEMENT half of a sweep and it deliberately touches no database.
It answers one question and refuses everything else: *given these rows, which
one is a second copy of a fixture that has already been played, and which row is
the real one?*

It is the soccer sibling of :mod:`app.utils.tennis_twin_pairs` and it reuses that
module's vocabulary (``TWIN_FOUND`` / ``REFUSE_AMBIGUOUS`` / ``NOT_A_TWIN``) and
its discipline — a reversible label, no deleter, under-tagging as the intended
failure direction. It does NOT reuse its pairing, because the structure that
separates two tennis rows (a tournament sport key, a surname block) does not
exist in soccer, and the structure that separates two soccer rows (an authority
fixture id on one side and none on the other) is not what the tennis module
reads.

WHAT THE DEFECT LOOKS LIKE
══════════════════════════

Measured on production 2026-09-13, ten pairs, every one the same shape::

    ghost  15298125 Sevilla v Valencia  09-13 19:00Z  scheduled  no score  no anchor
    real   15298233 Sevilla v Valencia  09-11 19:00Z  completed  1-0       espn 401882878

The ghost is dated at a round placeholder hour on a later day, carries no score
and no authority id; the real row carries both. Both were written by the same
Odds API ingest 95 minutes apart on 2026-08-30 — the first pass published the
fixture before its kick-off was confirmed, the second published it again with
the real time, and ruling 048 correctly refused to absorb an id-less claim.
Nothing has ever drained the first row, so the site advertises a game that was
played two days ago.

The ESPN slate for 2026-09-13, read at the authority (notice 26/27), contains
none of the ten: four La Liga fixtures, five Argentine Primera, four Segunda,
two Brasileirão, and not one ghost among them.

WHAT "ANCHORED" MEANS HERE, AND WHY ``external_id`` IS NOT IT
══════════════════════════════════════════════════════════════

:func:`app.utils.tennis_twin_pairs.row_is_id_anchored` reads three columns —
``external_id``, ``espn_id``, ``statpal_fixture_id`` — and on the tennis
population all three move together. **On this population ``external_id`` is
worthless and reading it would refuse every pair.** Both halves of all ten pairs
carry one, because an Odds API row's ``external_id`` is a per-ingest surrogate
hash: the two passes minted two different hashes for one fixture, which is the
very reason there are two rows. A per-provider minted id re-encodes the claim
and anchors nothing.

So the anchor here is :func:`row_is_fixture_anchored` — ``espn_id`` or
``statpal_fixture_id``, an id assigned by an authority that knows the fixture
independently of us. Measured over the ten pairs: canonical anchored 10/10,
ghost anchored 0/10.

That asymmetry is also what puts this on the right side of ruling 048. The row
we decline to print is the id-less one and the row we keep is the id-anchored
one, which is the direction 048 argues for. Nothing is absorbed, deleted or
repointed; the ghost keeps its row, its markets and its id, and one predicate
reverts the label.

WHY THREE DAYS, AND WHAT IT COST TO CHOOSE IT
══════════════════════════════════════════════

Soccer, unlike tennis, gives a time window — the canonical's kick-off is a real
one. The window has to exclude a genuine rematch, and the question "do the same
two teams, in the same orientation, ever play twice within three days?" is
answerable. Measured on production over 365 days of soccer, both rows completed,
both carrying a final score, both fixture-anchored, identical
``lower(btrim(name))`` on BOTH sides::

    pairs within 3 days                                    1
    …of which the pair shares one statpal_fixture_id
      and one kick-off instant (i.e. is itself a twin)     1
    genuine rematches                                      0

Orientation is load-bearing in that count and is not a detail: a two-legged tie
swaps home and away, so it can never collide with this key. A replay is at the
same venue but weeks later.

:data:`MAX_GHOST_LAG` is therefore three days, and it is a measured bound rather
than a guess. Widening it is not a free parameter — it is a new measurement.

THE GHOST DOES NOT STOP BEING A GHOST AT ITS OWN FAKE KICK-OFF
═══════════════════════════════════════════════════════════════

This module's first cut required the ghost's advertised kick-off to be in the
FUTURE, reasoning that "a row nobody is being shown as upcoming is not this
defect". That premise is false, and it was refuted by our own screenshot before
it ever ran: on the league page a ``scheduled`` row with no score whose kick-off
has passed is not gone, it is PROMOTED — it leaves *Upcoming* and renders under
**Live & Paused** reading "No result reported", while the real result sits one
rail below (lane1/288's 17:02Z production shot for #5918, and on 2026-09-13 the
served La Liga payload carried three such rows: 15310513, 15308732, 15308726).

So the rule cost the ten measured ghosts of 2026-09-13 nothing at 18:00Z and
everything at 19:01Z, and it did it silently: they would have aged out of the
selector into a *worse* card and stayed on the page for the rest of the -5d
population window. What makes a row a ghost is that a scored, fixture-anchored
twin of it exists within :data:`MAX_GHOST_LAG` — a fact about two rows, not
about the hour. The clock now buys only :data:`GHOST_KICKOFF_GRACE`, which is
the one thing it was ever actually protecting.

None of the three gates that keep a real fixture visible moved: the ghost must
still carry no score and no authority fixture id, the canonical must still carry
both, the pair must still sit inside the measured three-day window, and a block
that cannot resolve to exactly one of each is still refused.

…AND THE STATUS GATE WAS THE SAME CLOCK, WEARING A DIFFERENT NAME
══════════════════════════════════════════════════════════════════

The section above removed the clock gate. The status gate then re-imposed the
identical boundary, and the sweep shipped INERT: enabled 2026-09-14, two healthy
passes, ``rows_read`` 1,184, ``written`` 0.

``scheduled`` is not a state a ghost stays in. ``espn_sync``'s promotion arm
selects on ``commence_time <= now``, so the invented kick-off passing moves the
row ``scheduled`` → ``live``; ``backfill_winners`` Phase 0 then writes
``suspended`` on anything still unreported two days past its own hour. **Nothing
in the state machine demotes ``suspended``** (the measurement is in
``tasks/polymarket.py``'s re-dating rail), so that is where the row stops. A
gate reading ``status == 'scheduled'`` is therefore a gate reading *before its
advertised kick-off* — the exact predicate the section above deleted for being
false, restated as a word instead of a comparison.

Measured on production 2026-09-14 over the sweep's own window (−5d/+5d) with
this module's own predicates, whole population, no sampling::

    pairs meeting every predicate EXCEPT status         11
      ├─ ghost status 'scheduled'  (what we admitted)    0
      └─ ghost status 'suspended'  (where they went)    11
    blocks resolving to exactly 1 ghost + 1 canonical  11 / 11

Headline specimen is this module's own: ghost ``15298125`` Sevilla v Valencia
against canonical ``15298233``, 09-11 19:00Z, 1-0, espn ``401882878`` — the pair
the docstring opens with, which the shipped predicate could not see.

WHY THIS IS NOT THE WIDENING IT LOOKS LIKE. ``suspended`` renders as "No result
reported", which is a statement that nothing was reported, not a statement that
a match is being played — and the page prints these rows on the same rail as the
real result, which is the duplicate this module exists to remove. The state that
does mean "in progress" is ``live``, and it stays out. Precision is unchanged
either way: what condemns a row is still a scored, fixture-anchored twin of it
inside :data:`MAX_GHOST_LAG`, and the measurement that bounds THAT — zero
genuine same-orientation rematches in 365 days — is what a wrongly-tagged
``suspended`` row would have to defeat.

``soccer_other`` IS NOT A COMPETITION, SO IT CANNOT SEPARATE TWO ROWS
══════════════════════════════════════════════════════════════════════

The block key holds a sport key so that a cup tie and a league fixture between
the same two clubs can never pair. That is right, and
``test_two_clubs_in_different_competitions_do_not_share_a_block`` keeps it.

But one soccer key names no competition. ``soccer_other`` is the ingest's
catch-all — 9,512 rows in the last 90 days against 245 for La Liga, only 28 of
them anchored — and ``sport_keys.py`` documents what is inside it: Greek Cup,
Copa do Brasil, the Colombian, Ecuadorian, Dominican and Venezuelan leagues, a
cup's qualifying rounds while its main draw sits under the real key. A row lands
there when the ingest could not say WHICH competition it belongs to, so reading
it as "a different competition from La Liga" reads an absence as a fact, and the
block key was doing exactly that.

The cost is a ghost the sweep cannot see at all. Measured on production
2026-09-14, this module's own predicates, its own −5d/+5d window, whole
population::

    block key                      blocks  decidable  ambiguous  ghosts tagged
    (sport_key, home, away)  today     14         14          0             14
    unclassified folded in             15         15          0             15

The one row is ``15307887`` — Daejeon Citizen v Pohang Steelers, advertised as a
13:00Z fixture under ``soccer_other`` three hours after ``15305024`` finished
2-2 under ``soccer_korea_kleague1``, statpal-anchored.

So an unclassified block joins the named block that shares its two clubs, and
**only when exactly one named competition does**. Two named competitions with
the same two clubs in the window is unresolvable — we cannot say which one an
unclassified row belongs to — and it is reported, never guessed.

WHY THIS IS SAFE IN THE DIRECTION THAT MATTERS. The risk the sport key guards is
that we stop printing a real fixture because a DIFFERENT real fixture between
the same clubs refutes it. Measured over 365 days of production soccer, both
rows played, both scored, both fixture-anchored, identical ``lower(btrim())``
names in the same orientation, inside :data:`MAX_GHOST_LAG`::

    pairs                                       1
      ├─ under the SAME sport key               1   (itself a twin — one
      │                                              statpal id, one instant)
      └─ under DIFFERENT sport keys             0

Zero. Not "rare": none, in a year, across every soccer key we carry. And folding
can only ever ADD rows to a block, so where it does go wrong the block stops
resolving to one ghost and one real row and is refused — under-tagging, which is
this module's intended failure direction throughout.

THE ONE THING A CROSS-KEY FOLD RISKS THAT A SAME-KEY FOLD NEVER DID. The ghost
usually holds the prices — here 8 markets on ``15307887`` against 0 on the
canonical — so the tag is only safe because ``_build_game_markets`` reads the
tagged row's markets onto the canonical (``folded_event_ids``). That reader has
a cross-sport safety net, ``sport_id == event.sport_id OR llm_sport_category ==
expected_category``, and until now both halves of every folded pair shared a
sport key, so the first clause always matched. An unclassified ghost's markets
carry the unclassified ``sport_id``, so they survive only on the second clause —
and that clause holds because ``expected_category`` is derived from the sport
key's PREFIX (``sport_key.split("_")[0]``), which is ``soccer`` for both halves.

That is a dependency, so it is measured rather than assumed. Every market on
every unclassified ghost candidate in the sweep's window, 2026-09-14, whole
population: 2,865 markets, 2,865 with ``llm_sport_category = 'soccer'``, 0 with
a null category and 0 with any other category. ``test_every_soccer_key_shares_
one_llm_category`` pins the prefix property that makes it true in general.

AND WHY THE NAME KEY DID NOT MOVE WITH IT. The obvious next step — fold
``Sligo Rovers FC`` onto ``Sligo Rovers`` too — was measured on the same
population and rejected on its own numbers. Stripping a trailing club suffix
(``fc``/``afc``/``cf``/``sc``/…) on top of the fold above gives 21 blocks, 17
decidable and **4 ambiguous**, and one of those four is this module's headline
pair: Sevilla v Valencia, decidable today, becomes two candidate ghosts and is
refused. It also does not buy the specimen that motivated it — ``Sligo Rovers FC
v Galway United FC`` carries FIVE unanchored rows against one canonical
(``15307330``, 1-3, statpal 9528953), so it is refused either way. A name fold
would lose a pair we tag today, keep the pair that prompted it, and widen a key
away from its measurement. Those five rows are one fixture minted five times by
ingest, which is a registry defect (#3813) and not something a judgement over
existing rows can repair.

THE NAME KEY IS DELIBERATELY THE NARROW ONE
════════════════════════════════════════════

The block key folds case and surrounding whitespace and nothing else. It does
NOT strip diacritics and does not normalise punctuation, even though
``app.utils.name_normalization`` is right there and the canonical spells its
clubs the same way the ghost does today.

That is on purpose. The precision evidence above — zero genuine rematches in a
year — was measured with ``lower(btrim())`` on both sides, and a looser key
matches rows that measurement never examined. The cost of the narrow key is a
ghost whose two halves are spelled differently and which we therefore miss; that
is under-tagging, which leaves a duplicate card visible and fixable. The cost of
the loose key is a real fixture we stop printing. The failure directions are not
symmetric, so the key stays where the measurement is.

…SO THE LOOSE KEY RUNS SECOND, OVER THE ROWS THE NARROW ONE LEFT
═════════════════════════════════════════════════════════════════

The paragraph above is still true and the key above has not moved. What it
leaves behind was measured by lane1 on production 2026-09-14 (comment
5670673213 on #3813): **18 ghosts holding 59 markets whose canonical serves
zero**, and the reader-visible failure is not a duplicate card at all — it is
``/events/15307330``, Sligo Rovers 1-3 Galway United, Final, chart, and then
**no market rail whatsoever**, because its six settled goal-total rungs sit on a
row the page never reads. Those pairs differ in BOTH block coordinates at once
(``soccer_other`` vs ``soccer_league_of_ireland``, ``Sabadell`` vs ``Sabadell
FC``), so :func:`block_key` puts them in different blocks and
:func:`classify_block` is never handed the pair. Not a lag miss, not a status
miss, not the ambiguous arm: structurally invisible at any window.

Widening :func:`block_key` itself was measured and is a net LOSS — stripping a
club suffix inside the one key gives 21 blocks, 17 decidable and **4 ambiguous**,
and one of the four is this module's own Sevilla v Valencia, decidable today and
refused after. That is the shape of the trap: a looser key merges two blocks that
each already resolved, and ambiguity is contagious.

So the loose key never touches the first pass. :func:`residual_pass` runs AFTER
it, over the rows it did not decide, and differs from it in exactly ONE
coordinate: club names come from :func:`loose_block_key`, trailing legal suffix
stripped. A ghost the first pass tagged is withheld, so no decision can be
revised and nothing the narrow key resolves today can be lost. A canonical is
NOT withheld: one played fixture can honestly have two id-less copies.

**THE SPORT KEY STAYS IN THE KEY, AND A PRODUCTION PAIR IS WHY.** The first cut
of this pass dropped it — the measured stranded pairs straddle two NAMED
competitions (``la_liga`` against ``segunda_division``), so dropping it is the
only thing that reaches them, and the 365-day rematch count over
played-AND-ANCHORED rows was zero, which read like permission. Widening the
denominator refuted it. Over 365 days of soccer, played and scored, **anchoring
not required** — 8,838 rows instead of 1,332 — the same-orientation loose-key
pairs within :data:`MAX_GHOST_LAG` are six, and one of them is::

    15293467  1. FC Köln v TSG Hoffenheim  08-28 16:30Z  1-0  soccer_germany_bundesliga_women
    14970278  1. FC Köln v TSG Hoffenheim  08-29 13:30Z  3-2  soccer_germany_bundesliga

Two real fixtures, twenty-one hours apart, different results, the same two club
names in the same orientation, separated by **nothing but the sport key**. The
other five are three same-key duplicates and the Lazio v AC Milan twin counted
in both directions (one statpal id 9545725, one instant). The earlier zero was
an artefact of its own anchoring filter, which excluded every one of these.

That pair also names the general shape: a key can be another key with a
qualifier appended (``_women``, ``_qualification``, ``_qualifiers_europe``) and
then the same two club NAMES are two different squads. Four such variants exist
in the 59 soccer keys we carry. A rule excluding just those would readmit the
cup-tie case that ``test_two_clubs_in_different_competitions_do_not_share_a_
block`` forbids on doctrine, and the argument for readmitting it would be an
absence of evidence in a year — while the failure it risks is a real upcoming
fixture silently vanishing, against a miss that merely leaves a visible gap. The
failure directions are not symmetric, so the sport key stays and the only fold
across keys remains :func:`fold_unclassified_blocks`.

RECALL, over the sweep's own −5d/+5d window, whole population, 1,248 rows: first
pass 12 tags (unchanged, by construction), residual pass **+1 tag moving 4
markets onto a canonical that held 1** — ghost ``15307681`` *Gwangju v FC Anyang*
(``soccer_other``) onto ``15306857`` *Gwangju FC v FC Anyang*
(``soccer_korea_kleague1``), which the shipped pass missed for the single
character ``FC`` — plus one refusal, Granada v Albacete, that was previously not
even examined.

WHAT REMAINS STRANDED, NAMED RATHER THAN ROUNDED AWAY. Of lane1's 18 ghosts /
59 markets (#3813, comment 5670673213), this pass takes one and the rest are
three classes, none of them this module's to decide:

* **two NAMED competitions** — Mallorca v Sabadell (7 markets) and Andorra v
  Real Sociedad B (4). Decidable only by crossing the key, which the Köln pair
  above says we may not do on names and a clock alone. What would settle them is
  knowing Sabadell is a Segunda club and the ghost's ``la_liga`` key is
  therefore impossible — a squad-to-competition authority, not a judgement over
  two rows. **That authority turned out to already be in the row** — see the
  section below, which takes both of these.
* **multi-mint** (#3813) — Sligo has FIVE id-less rows against one canonical,
  three at the canonical's own instant. The block cannot resolve to one ghost,
  and guessing which of five to stop printing is the call this module must not
  make. Its 14 markets need the registry fix, not a label.
* **pre-kick-off twins** — FC Sion v FC Zurich and Fiorentina v Pisa are two
  copies of a fixture nobody has played yet. Every judgement here rests on a
  scored, fixture-anchored row refuting an id-less one; with no result on either
  side there is no canonical, and inventing one from the anchor alone is a
  different rule with no measurement behind it.

THE SQUAD-TO-COMPETITION AUTHORITY WAS ALREADY IN THE ROW: ITS OWN TICKER
═════════════════════════════════════════════════════════════════════════

The bullet above asked for something that knows Sabadell is a Segunda club, and
called it a missing authority. It is not missing. The ghost holds
``KXLALIGA2GAME-26SEP13MALSAB``, and ``KXLALIGA2`` is Kalshi's own name for the
competition the fixture is in — ``sport_keys`` has mapped it to
``soccer_spain_segunda_division`` since #5982. **The row's ``la_liga`` key and
the row's own markets disagree, and the markets are the ones with an authority
behind them.** The key is wrong because the row was minted BEFORE #5982 landed,
by the eight-character ``kxlaliga`` prefix that swallowed every Spanish ticker.

So :func:`ticker_pass` runs THIRD, over what the first two did not decide, and
differs from the second in exactly one coordinate: a row that could be a ghost
is blocked under the competition its own Kalshi GAME tickers name, when they
unanimously name one. Ghost-capable rows only — a canonical is settled, scored
and fixture-anchored, so an authority already says what fixture it is and its
key is not in doubt. Unanimous only — a row whose tickers name two competitions
is telling us something we cannot act on, so it is left where it is.

WHY THIS IS NOT THE CROSS-KEY FOLD THE KÖLN PAIR FORBIDS. That pair is forbidden
because names and a clock cannot tell a women's fixture from a men's one twenty-
one hours later. This pass does not ask names and a clock to do it — it reads a
competition id off the venue's own series ticker. The distinction is measurable
rather than rhetorical, so it was measured. Over 365 days of production soccer,
both rows played and scored, loose-key names in the same orientation, inside
:data:`MAX_GHOST_LAG`, **straddling two different sport keys**::

    pairs                                                         1
      └─ 1. FC Köln v TSG Hoffenheim (women 08-28 / men 08-29)    1
           ├─ Kalshi game tickers on the women's row              0
           └─ Kalshi game tickers on the men's row                0
               (14 Polymarket markets, no Kalshi series at all)

The one pair in a year that this key could get wrong carries no ticker on either
side, so this pass is silent on exactly the population that motivated keeping the
sport key. It is also refused twice over before that matters: neither row is
fixture-anchored, so neither can be a canonical, and both carry a score, so
neither can be a ghost.

RECALL, over the sweep's own −5d/+5d window, whole population, 1,247 rows,
2026-09-15: first two passes 13 tags (unchanged, by construction), ticker pass
**+2 tags moving 11 markets onto two canonicals that served zero** — and they are
the two the bullet above named as stranded::

    15307878  Andorra v Real Sociedad B  (la_liga, 4 KXLALIGA2 markets)
        → 15305059  Andorra CF v Real Sociedad B  (segunda, 1-3, statpal 9545730)
    15308726  Mallorca v Sabadell        (la_liga, 1 KXLALIGA2 + 6 Polymarket)
        → 15306010  Mallorca v Sabadell FC        (segunda, 2-0, statpal 9545042)

Ten rows had their block key moved by their tickers; two produced a decision and
the other eight fell out of the same three gates as everything else. Granada v
Albacete is still refused, now with three candidate ghosts rather than two —
widening reaching a refusal and leaving it a refusal is the monotonicity the
second pass's docstring describes, observed rather than asserted.

The reader-visible half: ``/events/15306010`` was hero, chart, score
differential and then straight to "MORE SOCCER" with no market rail whatsoever,
while seven markets for that match sat on a hidden row filed under the wrong
league — which also put a played Segunda fixture on the La Liga page.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.utils.sport_keys import (
    get_sport_key_from_ticker,
    is_kalshi_game_level_ticker,
)

#: The two rows are one fixture and ``ghost_id`` is safe to stop printing.
#: Same vocabulary as :mod:`app.utils.tennis_twin_pairs`, on purpose — an
#: operator reading a refusal should not have to learn two words for one state.
TWIN_FOUND = "TWIN_FOUND"
#: The rows in this block cannot be resolved to exactly one ghost and one real
#: row. Reported, never acted on.
REFUSE_AMBIGUOUS = "REFUSE_AMBIGUOUS"
#: Nothing in this block pairs. The common answer.
NOT_A_TWIN = "NOT_A_TWIN"

#: The greatest gap between the real kick-off and the ghost's advertised time
#: that this module will call a twin. Measured, not chosen — see the module
#: docstring: zero genuine same-orientation rematches inside this window in 365
#: days of production soccer.
MAX_GHOST_LAG = timedelta(days=3)

#: How long after its own advertised kick-off a row is left alone before it may
#: be judged a ghost. A REAL fixture reads ``scheduled`` with no score for the
#: first minutes of its first half, until live ingest catches it, and there is
#: no urgency whatsoever to relabel anything in that window. It is deliberately
#: generous: the cost of waiting is half an hour of a card nobody has looked at
#: yet, and the cost of not waiting is a kicked-off match called a duplicate.
GHOST_KICKOFF_GRACE = timedelta(minutes=30)

#: A row in one of these states has been played and can be a canonical.
#: ``closed`` is StatPal's definitive completion and ``completed`` is everyone
#: else's; both mean the same thing to a reader.
SETTLED_STATUSES = ("completed", "closed")

#: The states a ghost may be in. ``scheduled`` is the row before its invented
#: kick-off and ``suspended`` is the same row afterwards — see the section on
#: the status gate above for why both are one population and why reading only
#: the first made this module inert.
#:
#: Still excluded, and for three different reasons: ``live`` because a match
#: genuinely in progress is indistinguishable from a ghost mid-promotion and
#: under-tagging is the intended failure direction; ``voided``/``merged``
#: because they are already unprintable; the settled pair because a row with a
#: result is not being advertised as a fixture.
GHOST_STATUSES = ("scheduled", "suspended")

#: The key the ingest writes when it could not say WHICH competition a fixture
#: belongs to. It is not a league — see the docstring section above for what is
#: measured inside it — so it cannot be read as evidence that two rows are two
#: different fixtures. Every other ``soccer_*`` key can.
UNCLASSIFIED_SPORT_KEY = "soccer_other"

#: Trailing tokens that are a club's legal form rather than part of its name, so
#: ``Sabadell FC`` and ``Sabadell`` are one club. Used ONLY by
#: :func:`loose_block_key`, i.e. only in the second pass — see the docstring
#: section on why the first pass's key did not move.
#:
#: Deliberately short and deliberately trailing-only: every difference in the
#: measured population is a trailing legal form (``Sligo Rovers FC``, ``Andorra
#: CF``, ``Sabadell FC``, ``Galway United FC``), and a LEADING token is a
#: different question — ``FC Zurich`` and ``Zurich`` are not known to be one club
#: here and nothing measured says they are. ``b`` is absent on purpose: ``Real
#: Sociedad B`` is a reserve side and a genuinely different team.
CLUB_LEGAL_SUFFIXES = (
    "fc",
    "afc",
    "cf",
    "sc",
    "cd",
    "ud",
    "ec",
    "sd",
    "fk",
    "if",
    "bk",
    "sk",
)

_CLUB_LEGAL_SUFFIX_RE = re.compile(
    r"\s+(?:" + "|".join(CLUB_LEGAL_SUFFIXES) + r")$", re.IGNORECASE
)


def row_is_fixture_anchored(*, espn_id: object, statpal_fixture_id: object) -> bool:
    """Does an authority that knows this fixture independently of us name it?

    A named function and not a lambda at the call site, because the reading a
    caller reaches for first is wrong in a way that silently refuses every pair:
    ``external_id`` looks like an anchor, is present on both halves of all ten
    measured pairs, and is a per-ingest surrogate that anchors nothing. The
    module docstring carries the measurement; this is the one line that must not
    drift from it.
    """
    return espn_id is not None or statpal_fixture_id is not None


def row_has_final_score(*, home_score: object, away_score: object) -> bool:
    """Has this row been played to a result?

    Both sides, because a soccer row can carry a lone ``home_score`` of 0 mid-
    ingest and 0 is falsy — ``if home_score`` is the bug this exists to prevent.
    """
    return home_score is not None and away_score is not None


def block_key(sport_key: object, home: object, away: object) -> tuple[str, str, str]:
    """The coarse key grouping rows that MIGHT be the same fixture.

    Ordered (home, away), so a two-legged tie's second leg lands in a different
    block and can never pair with its first. Case and surrounding whitespace are
    folded; nothing else is — see the module docstring for why the narrow key is
    the measured one.
    """
    return (
        str(sport_key or "").strip().lower(),
        str(home or "").strip().lower(),
        str(away or "").strip().lower(),
    )


def loose_block_key(home: object, away: object) -> tuple[str, str]:
    """The SECOND-pass club names: everything :func:`block_key` folds, plus one
    trailing :data:`CLUB_LEGAL_SUFFIXES` token per club.

    Names only. The sport key is NOT dropped — :func:`residual_pass` feeds these
    two strings back through :func:`block_key` with the row's own key, so the
    only fold across competitions remains the unclassified one. The production
    pair that decided this (Köln women against Köln men, 21 hours apart) is in
    the module docstring.

    Orientation is still load-bearing and still ordered, so a two-legged tie's
    second leg can no more pair here than it can in the narrow key.

    One suffix, not a loop: ``Real Madrid CF SC`` is not a spelling anyone
    produces, and each extra strip is another shape the precision measurement
    never examined.
    """
    return (
        _CLUB_LEGAL_SUFFIX_RE.sub("", str(home or "").strip().lower()),
        _CLUB_LEGAL_SUFFIX_RE.sub("", str(away or "").strip().lower()),
    )


def competition_from_tickers(external_ids: Iterable[object]) -> str | None:
    """The one competition this row's own Kalshi GAME tickers name, or ``None``.

    GAME tickers only, through :func:`is_kalshi_game_level_ticker` rather than a
    bare ``startswith``: a season or award ticker names the competition of a
    whole season and says nothing about which fixture a row is, and the two
    prefix maps overlap in both directions (see that predicate's docstring).

    ``None`` on disagreement, and that is the load-bearing half rather than a
    tidy edge case. A row whose markets name two competitions is telling us
    something real — that the link rail put markets from two series on one row —
    and the answer to it is not to pick one. ``None`` leaves the row exactly
    where its own sport key puts it, which is the under-tagging direction this
    module fails in everywhere else.
    """
    named = {
        get_sport_key_from_ticker(str(ext))
        for ext in external_ids
        if ext and is_kalshi_game_level_ticker(str(ext))
    }
    named.discard(None)
    return named.pop() if len(named) == 1 else None


@dataclass(frozen=True)
class SoccerRow:
    """One row's judgement inputs, copied to scalars.

    Frozen scalars rather than an ORM object: the sweep's writer commits per row,
    and an ORM object read across a commit boundary lazy-loads in a sync context
    (gotcha #6). A judgement that reads the database is also a judgement nobody
    can test.
    """

    event_id: int
    sport_key: str
    home_team_name: str
    away_team_name: str
    commence_time: datetime
    status: str
    has_final_score: bool
    is_fixture_anchored: bool
    #: What this row's own Kalshi game tickers say its competition is —
    #: :func:`competition_from_tickers` of its markets, or ``None`` when it holds
    #: none, holds only season markets, or holds markets from two competitions.
    #: Read ONLY by :func:`ticker_pass`; the first two passes never see it.
    ticker_sport_key: str | None = None


def block_sport_key(row: SoccerRow) -> str:
    """The competition :func:`ticker_pass` blocks ``row`` under.

    The row's own key, except for a row that could be a ghost and whose markets
    name a different competition — there, the markets win. Both halves of that
    exception are necessary:

    * **ghost-capable only.** A canonical is settled, scored AND fixture-
      anchored, so an authority that knows the fixture independently of us has
      already said what it is. Re-reading its competition off a market would let
      a mis-linked market move a REAL fixture's block, which is the direction
      that loses a card.
    * **a different competition only.** Agreement changes nothing, so saying so
      explicitly keeps the ordinary case out of the exception.
    """
    if (
        row.ticker_sport_key
        and row.ticker_sport_key != row.sport_key
        and row_could_be_a_ghost(row)
    ):
        return row.ticker_sport_key
    return row.sport_key


def row_could_be_a_ghost(row: SoccerRow) -> bool:
    """The three row-only halves of the ghost test, with the clock left out.

    :func:`classify_block` adds :data:`GHOST_KICKOFF_GRACE` to this; the fold in
    :func:`fold_unclassified_blocks` deliberately does not, because it is asking
    "could this block ever produce a decision?" and half an hour either side of
    a kick-off must not change which rows are considered together. One predicate
    so the two cannot drift.
    """
    return (
        row.status in GHOST_STATUSES
        and not row.has_final_score
        and not row.is_fixture_anchored
    )


def fold_unclassified_blocks(
    blocks: dict[tuple[str, str, str], list[SoccerRow]],
) -> tuple[dict[tuple[str, str, str], list[SoccerRow]], list[str]]:
    """Move :data:`UNCLASSIFIED_SPORT_KEY` rows into the named block they belong
    to, when exactly one named block shares their two clubs.

    Returns the rebuilt blocks and any refusals. Pure; the input is not mutated.

    Exactly one, and no guessing: two named competitions carrying the same two
    clubs inside the window is a question about which competition an
    unclassified row is in, and this module answers no such question. That
    refusal is only recorded when the unclassified block actually holds a row
    that could be a ghost, so the list stays readable.
    """
    named_by_clubs: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(
        list
    )
    for sport, home, away in blocks:
        if sport != UNCLASSIFIED_SPORT_KEY:
            named_by_clubs[(home, away)].append((sport, home, away))

    folded = {key: list(members) for key, members in blocks.items()}
    refusals: list[str] = []
    for key in list(blocks):
        sport, home, away = key
        if sport != UNCLASSIFIED_SPORT_KEY:
            continue
        targets = named_by_clubs.get((home, away), [])
        if len(targets) == 1:
            folded[targets[0]].extend(folded.pop(key))
        elif len(targets) > 1 and any(row_could_be_a_ghost(row) for row in blocks[key]):
            refusals.append(
                f"{home} v {away}: {len(targets)} named competitions carry these "
                f"clubs, so an unclassified row cannot be placed in one"
            )
    return folded, refusals


@dataclass(frozen=True)
class GhostTag:
    """One decision: ``ghost_id`` is a second copy of ``canonical_id``."""

    ghost_id: int
    canonical_id: int
    reason: str


@dataclass
class GhostPlan:
    """Everything one pass decided, including what it refused and why."""

    tags: list[GhostTag] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    blocks_examined: int = 0
    rows_considered: int = 0
    #: Blocks the SECOND pass looked at, and how many of ``tags`` it contributed.
    #: Reported separately rather than summed in, because the two passes fail
    #: differently: the first going quiet means the narrow key stopped reaching
    #: its rows, and the second going quiet means the loose one did. One total
    #: hides whichever half died.
    residual_blocks_examined: int = 0
    residual_tags: int = 0
    #: Blocks the THIRD pass looked at, and how many of ``tags`` it contributed.
    #: Its own pair for the same reason the second pass has one: this pass dies
    #: in a way neither of the others can — the ticker maps stop naming a
    #: competition, or the markets stop reaching the row — and a total would
    #: report that as a quiet ordinary day.
    ticker_blocks_examined: int = 0
    ticker_tags: int = 0


def classify_block(
    rows: list[SoccerRow],
    *,
    now: datetime,
    max_lag: timedelta = MAX_GHOST_LAG,
) -> tuple[str, GhostTag | None, str]:
    """Decide one block. Returns ``(outcome, tag_or_None, explanation)``. Pure.

    The two roles are read off the row, never off the clock alone:

    * a CANONICAL is settled, carries a final score AND is fixture-anchored;
    * a GHOST is in one of :data:`GHOST_STATUSES`, carries no score, is NOT
      fixture-anchored, and is not inside :data:`GHOST_KICKOFF_GRACE` of its own
      advertised kick-off.

    The clock decides ONE thing here and it is not whether the row is a ghost.
    A row that is refuted by a scored, fixture-anchored twin of its own within
    :data:`MAX_GHOST_LAG` is a ghost at every hour of the day; the grace exists
    only so that a real match which has just kicked off, and is briefly still
    ``scheduled`` with no score, is never the row we stop printing.

    Anything other than exactly one of each, among the rows that actually pair
    within ``max_lag``, is :data:`REFUSE_AMBIGUOUS`. Two ghosts and one
    canonical is a shape this module has never measured, and guessing which of
    two rows to stop printing is precisely the call it must not make.
    """
    canonicals = [
        r
        for r in rows
        if r.status in SETTLED_STATUSES and r.has_final_score and r.is_fixture_anchored
    ]
    ghosts = [
        r
        for r in rows
        if row_could_be_a_ghost(r)
        and not (now - GHOST_KICKOFF_GRACE < r.commence_time <= now)
    ]
    if not canonicals or not ghosts:
        return NOT_A_TWIN, None, "no ghost/canonical pair in this block"

    pairs = [
        (ghost, canonical)
        for ghost in ghosts
        for canonical in canonicals
        if timedelta(0) < ghost.commence_time - canonical.commence_time <= max_lag
    ]
    if not pairs:
        return (
            NOT_A_TWIN,
            None,
            f"no ghost sits within {max_lag.days}d after a played row",
        )

    paired_ghosts = {ghost.event_id for ghost, _ in pairs}
    paired_canonicals = {canonical.event_id for _, canonical in pairs}
    if len(paired_ghosts) != 1 or len(paired_canonicals) != 1:
        return (
            REFUSE_AMBIGUOUS,
            None,
            (
                f"{len(paired_ghosts)} candidate ghost(s) and "
                f"{len(paired_canonicals)} candidate real row(s) pair in this "
                f"block — which to stop printing is not decidable"
            ),
        )

    ghost, canonical = pairs[0]
    lag_hours = (ghost.commence_time - canonical.commence_time).total_seconds() / 3600
    return (
        TWIN_FOUND,
        GhostTag(
            ghost_id=ghost.event_id,
            canonical_id=canonical.event_id,
            reason=(
                f"{ghost.home_team_name} v {ghost.away_team_name}: advertised "
                f"{lag_hours:.0f}h after the played row, no score, no fixture id"
            ),
        ),
        "twin",
    )


def residual_pass(
    rows: list[SoccerRow],
    *,
    decided_ghost_ids: set[int],
    now: datetime,
    max_lag: timedelta = MAX_GHOST_LAG,
) -> tuple[list[GhostTag], list[str], int]:
    """Re-run the first pass over what it did not decide, with loose club names.

    Returns ``(tags, refusals, blocks_examined)``. Pure.

    It differs from the first pass in exactly ONE coordinate — the club names are
    :func:`loose_block_key`'d instead of :func:`block_key`'d. The sport key is
    still in the key and the only fold across keys is still
    :func:`fold_unclassified_blocks`, i.e. still unclassified-to-named and still
    only when exactly one named competition carries the clubs. Two NAMED
    competitions are as separate here as they are there; see the docstring
    section for the production pair that settles why.

    WHY THIS CANNOT UNDO THE FIRST PASS, stated as the two properties it rests on
    rather than as an intention:

    * a ghost already tagged is removed from this population, so no row can be
      re-decided against a different canonical, and the first pass's tag count is
      a floor on the plan's;
    * ambiguity is MONOTONE under adding rows — :func:`classify_block` refuses
      once two ghosts or two canonicals pair, and a larger block can only add
      pairs — so a block the first pass refused can never become decidable here.
      That is what makes re-blocking safe at all, and it is the property the
      rejected "widen :func:`block_key` itself" design broke in the other
      direction, by merging blocks that had each already resolved.

    A canonical is deliberately NOT withheld: it is settled, scored and anchored,
    so :func:`row_could_be_a_ghost` is false for it and it can only ever play the
    same role twice. One played fixture with two id-less copies is a real shape —
    the Andorra specimen in the module docstring is one.
    """
    return _reblock(
        rows,
        decided_ghost_ids=decided_ghost_ids,
        key_of=_loose_name_key,
        already_examined_key_of=lambda m: block_key(
            m.sport_key, m.home_team_name, m.away_team_name
        ),
        label="loose names",
        now=now,
        max_lag=max_lag,
    )


def _loose_name_key(row: SoccerRow) -> tuple[str, str, str]:
    """Second-pass key: the row's own competition, club names loosened."""
    return block_key(
        row.sport_key, *loose_block_key(row.home_team_name, row.away_team_name)
    )


def _ticker_competition_key(row: SoccerRow) -> tuple[str, str, str]:
    """Third-pass key: the second-pass key with the competition re-read from the
    row's own Kalshi game tickers (:func:`block_sport_key`)."""
    return block_key(
        block_sport_key(row), *loose_block_key(row.home_team_name, row.away_team_name)
    )


def _reblock(
    rows: list[SoccerRow],
    *,
    decided_ghost_ids: set[int],
    key_of: Callable[[SoccerRow], tuple[str, str, str]],
    already_examined_key_of: Callable[[SoccerRow], tuple[str, str, str]],
    label: str,
    now: datetime,
    max_lag: timedelta,
) -> tuple[list[GhostTag], list[str], int]:
    """Run one re-blocking pass over the rows an earlier pass did not decide.

    ONE implementation for the second and third passes, deliberately: they
    differ in a key function and nothing else, and two loops encoding one rule
    drift — the drift that matters being the one that DROPS a withholding or a
    dedupe and lets a later pass revise an earlier pass's decision.

    ``already_examined_key_of`` is how a pass declines to re-report what the
    previous one already saw: if every member of a block shares one key under
    the previous pass's own blocking, that pass examined this exact block and
    reached the same answer, so re-reading it would restate its refusal in
    different words and double-count it.
    """
    residual = [r for r in rows if r.event_id not in decided_ghost_ids]
    blocks: dict[tuple[str, str, str], list[SoccerRow]] = defaultdict(list)
    for r in residual:
        blocks[key_of(r)].append(r)
    blocks, refusals = fold_unclassified_blocks(blocks)

    tags: list[GhostTag] = []
    examined = 0
    for key, members in sorted(blocks.items()):
        if len(members) < 2:
            continue
        if len({already_examined_key_of(m) for m in members}) < 2:
            continue
        examined += 1
        outcome, tag, explanation = classify_block(members, now=now, max_lag=max_lag)
        if outcome == TWIN_FOUND and tag is not None:
            tags.append(tag)
        elif outcome == REFUSE_AMBIGUOUS:
            refusals.append(f"{key[1]} v {key[2]} ({label}): {explanation}")
    return tags, refusals, examined


def ticker_pass(
    rows: list[SoccerRow],
    *,
    decided_ghost_ids: set[int],
    now: datetime,
    max_lag: timedelta = MAX_GHOST_LAG,
) -> tuple[list[GhostTag], list[str], int]:
    """Re-run the pairing over what the first two passes left, with each
    ghost-capable row's competition read off its own Kalshi game tickers.

    Returns ``(tags, refusals, blocks_examined)``. Pure.

    This is the only place in this module where two NAMED competitions can share
    a block, and it is not the widening the second pass's docstring refuses: the
    key does not become looser, it becomes RIGHT. A row minted under
    ``soccer_spain_la_liga`` whose every market is a ``KXLALIGA2`` contract is a
    Segunda fixture wearing a key that predates #5982, and the ticker is the
    venue's own statement of which competition that is. The module docstring
    carries the measurement that separates this from the Köln pair: the one
    cross-key loose-name pair in 365 days of production soccer holds no Kalshi
    ticker on either side, so this pass cannot see it.

    It inherits both properties that make :func:`residual_pass` safe, through the
    same implementation rather than by restating them: a ghost already decided is
    withheld, so no decision can be revised; and ambiguity is monotone under
    adding rows, so a block an earlier pass refused can never become decidable
    here. Observed on the measured population — Granada v Albacete arrives here
    with three candidate ghosts instead of two and is refused again.
    """
    return _reblock(
        rows,
        decided_ghost_ids=decided_ghost_ids,
        key_of=_ticker_competition_key,
        already_examined_key_of=_loose_name_key,
        label="loose names, ticker competition",
        now=now,
        max_lag=max_lag,
    )


def plan_ghost_tags(
    rows: list[SoccerRow],
    *,
    now: datetime,
    max_lag: timedelta = MAX_GHOST_LAG,
) -> GhostPlan:
    """Every label this population supports, plus every refusal. Pure.

    Blocks with a single row — the overwhelming majority — cost one dictionary
    insert and are never classified, so the plan's ``blocks_examined`` counts the
    blocks that could conceivably hold a pair. That number, not the number of
    tags, is how this sweep proves it still reaches its population: soccer
    ghosts are episodic (ten on 2026-09-13, zero in the preceding thirty days),
    so a floor on the tag count would refuse the healthy quiet day. The tennis
    sibling can floor its plan because a Slam fortnight always has twins.

    :func:`fold_unclassified_blocks` runs between the grouping and the
    classification, so a row the ingest could not assign to a competition is
    judged alongside the named block for its two clubs rather than alone.

    :func:`residual_pass` then runs over whatever the narrow key did not decide,
    under the looser key, and can only ADD — see its docstring for the two
    properties that make that true. :func:`ticker_pass` runs last over what
    those two left, blocking each ghost-capable row under the competition its
    own Kalshi game tickers name, and adds under the same two properties.
    """
    blocks: dict[tuple[str, str, str], list[SoccerRow]] = defaultdict(list)
    for row in rows:
        blocks[block_key(row.sport_key, row.home_team_name, row.away_team_name)].append(
            row
        )
    blocks, fold_refusals = fold_unclassified_blocks(blocks)

    plan = GhostPlan(rows_considered=len(rows))
    plan.refusals.extend(fold_refusals)
    for key, members in sorted(blocks.items()):
        if len(members) < 2:
            continue
        plan.blocks_examined += 1
        outcome, tag, explanation = classify_block(members, now=now, max_lag=max_lag)
        if outcome == TWIN_FOUND and tag is not None:
            plan.tags.append(tag)
        elif outcome == REFUSE_AMBIGUOUS:
            plan.refusals.append(f"{key[0]} {key[1]} v {key[2]}: {explanation}")

    extra_tags, extra_refusals, examined = residual_pass(
        rows,
        decided_ghost_ids={t.ghost_id for t in plan.tags},
        now=now,
        max_lag=max_lag,
    )
    plan.tags.extend(extra_tags)
    plan.refusals.extend(extra_refusals)
    plan.residual_blocks_examined = examined
    plan.residual_tags = len(extra_tags)

    ticker_tags, ticker_refusals, ticker_examined = ticker_pass(
        rows,
        decided_ghost_ids={t.ghost_id for t in plan.tags},
        now=now,
        max_lag=max_lag,
    )
    plan.tags.extend(ticker_tags)
    plan.refusals.extend(ticker_refusals)
    plan.ticker_blocks_examined = ticker_examined
    plan.ticker_tags = len(ticker_tags)
    return plan
