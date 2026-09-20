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

THE FOURTH PASS ASKS A DIFFERENT QUESTION: WHOSE PAGE HOLDS THE PRICES
═══════════════════════════════════════════════════════════════════════

Everything above hunts ONE defect — a row still advertised as a fixture after
the fixture was played — and the direction rule in :func:`classify_block` is
that defect written down: ``0 < ghost.commence_time - canonical.commence_time``.
A phantom card is always dated LATER than the match it copies, because a row
dated earlier is not advertising anything.

What that leaves is the mirror image, and it is not a card defect at all. The
duplicate sits BEFORE the played row, nobody sees it, and it is holding the
prices. Measured on production 2026-09-15 over 365 days of soccer — same
competition, same NARROW key, same orientation, inside :data:`MAX_GHOST_LAG`,
one side settled/scored/fixture-anchored and serving ZERO markets, the other
unscored, unanchored and holding at least one::

    pairs                                                        19
      └─ inside the last 23 days                                 19
      └─ with the ghost dated AFTER the canonical                 0
      └─ needing any name widening to pair                        0
           (lags run 0.0h to −53.8h; every pair already
            shares the narrow key, so passes two and three
            reach none of them either)

Zero of nineteen. The direction rule refuses the whole population by
construction, and it is right to: it is the rule that makes the card ship
precise. So this pass does not touch it — it asks its own question alongside it.

The reader-visible half, and the specimen this pass is measured on: ``14959571``
is **AS Roma 4-0 Fiorentina**, Serie A, 2026-08-24, ESPN ``401874928`` — and it
has **zero linked markets**. ``14968103`` is the same two clubs in the same
competition 53 hours earlier, ``closed``, no score, no fixture id, holding
**28 Polymarket markets**. A marquee Serie A result whose prices are all on a
row nobody opens (notice 27).

🔴 **"SERVES NOTHING" IS MEASURED ON THE LINKED-MARKET COUNT, NOT ON THE SERVED
PAYLOAD, AND THAT IS NOT A SHORTCUT.** ``_build_game_markets`` assembles its
whole rail from ``FuturesMarket`` rows whose ``event_id`` is in
``folded_event_ids``, and returns the empty ``{"totals": [], "spreads": [],
"other": [], …}`` body the moment that set is empty. So a linked count of zero
IS the early return — it is the builder's own input, not a proxy for it.

Reading the payload instead would have been wrong, and was. On 2026-09-15 nine
of the eleven canonicals below served a full rail — 38 to 83 markets — while
holding zero linked rows. Two consecutive reads returned the identical
``created_at`` (the L1 in-process memo; the Redis entry is fresh for
``FRESH_TTL_FINAL`` = 3600 s on a final game), so the cache cannot be made to
rebuild from outside and "the page looks fine" is unfalsifiable from there.

What settles it is tracing one served market rather than arguing about the
cache. ``/api/events/14961230/game-markets`` serves ``_market_id 58728702``,
Atalanta vs Sassuolo: Total Goals, ``observed_at`` 2026-09-13T12:47Z — and that
row's ``event_id`` **is NULL**. The body is a photograph of an input set that no
longer exists; on a genuine rebuild the builder finds nothing and returns the
empty body. The two rows with a null ``lifecycle_watermark`` (``15296797``,
``15299944``) never held markets and serve that empty body already.

So the strand here has TWO halves and this pass repairs one of them: the
canonical's own Kalshi markets were orphaned to a null ``event_id``, and the
copy kept the Polymarket ones. Folding the copy gives the bare page a settled
rail; it does not re-link what was orphaned, and nothing here should be read as
claiming it does.

WHAT THIS PASS DELIBERATELY DOES NOT REACH, MEASURED THE SAME DAY. ``15186733``
is Waterford FC 3-1 Bohemians with 63 markets stranded on ``15186691``, and this
pass refuses it — because ``15186733`` carries **no ``espn_id`` and no
``statpal_fixture_id``**. With no authority naming the fixture independently of
us, neither row can be the canonical, and choosing between two id-less rows is
the call ruling 048 forbids. It is a real defect and it belongs to the registry
(#3813), not to a judgement over existing rows.

WHAT REPLACES THE DIRECTION RULE, SINCE THE CLOCK CANNOT
─────────────────────────────────────────────────────────

The market asymmetry itself: the canonical must serve NOTHING and the twin must
hold something. That is strictly MORE evidence than the first three passes ask
for, not less — they require no market on either side — and it is what bounds
the blast radius. **This pass can only ever fire on a page that is currently
serving no markets at all**, so the worst a wrong tag can do is put the wrong
prices on a bare page; it can never replace a correct market rail with someone
else's. No other pass in this module has that property, and it is the only
reason a direction-agnostic pairing is safe to run.

The ambiguity refusal is unchanged in spirit and stricter in practice: the
canonical-shaped rows are counted over the WHOLE block, market count ignored,
so a block holding two played rows is refused before the zero-market one is
looked at.

YIELD, from the pure planner run over the sweep's own -45d/+5d population as it
stood on production 2026-09-15 — 6,721 rows, whole population, no sampling::

    stranded blocks examined                                   472
      ├─ tags                                                   11
      │    (139 markets moving onto pages with none: Serie A
      │     4, EPL 1, Bundesliga 1, Ligue 1 2, Brasileirão 1,
      │     Argentine Primera 1 — every canonical scored and
      │     fixture-anchored, every one of them serving zero)
      └─ refused ambiguous                                       5
           Bournemouth v Everton (4 copies), Real Sociedad v
           Espanyol (3), Levante v Real Betis (3), Liverpool v
           Nottingham Forest (2), Fiorentina v Frosinone (2)

The same run is the evidence for the window widening: first pass, residual and
ticker contributed **1 and 2 tags respectively and nothing new from the extra 40
days**, so the four passes do not overlap in practice either.

WHY ``GHOST_STATUSES`` IS NOT THE GATE HERE, AND THE ONE STATUS THAT IS
────────────────────────────────────────────────────────────────────────

:data:`GHOST_STATUSES` is ``scheduled``/``suspended`` because those are the
states a row can be *advertised* in, and the section above gives the reason for
each exclusion — all of them reasons about printing a card. A stranded market is
stranded at every status: four of the eleven decidable pairs (Roma v Fiorentina,
Bologna v Lazio, Torino v AC Milan, Atalanta v Sassuolo — 98 markets between
them) carry a ``closed`` twin, already unprintable and therefore invisible to
every rule above, and still holding the prices.

So this pass does not read the status gate. It reads one status, and excludes
it: ``live``. A match in progress is unscored and may be unanchored, and calling
it a duplicate of anything is the one mistake here that reaches a reader
mid-match. :data:`GHOST_KICKOFF_GRACE` is applied for the same reason and by the
same predicate as everywhere else.

THE FIFTH PASS STOPS GUESSING: THE VENUE ALREADY TOLD US THESE ARE ONE FIXTURE
═══════════════════════════════════════════════════════════════════════════════

Every pass above pairs rows on our own ``home_team_name`` and
``away_team_name``, loosened by a suffix rule and scoped by a competition, with
a clock or a market count standing in for proof. #6316 is the population where
none of that is needed, because **both rows carry the same Kalshi event
ticker**.

``/events/15310639`` is Liverpool FC v Fulham FC, ``scheduled``, kickoff stored
at ``2026-09-12 00:00:00+00``, running a live "Next update" countdown and
printing "No result reported" three days after the match. ``/events/15297677``
is the same fixture, ``completed``, 0-0, with a chart and a settled rail. The
first page is direct-link reachable only, so no listing rule can reach it. And
the two rows are not a guess::

    15297677  KXEPLGAME-26SEP12LFCFUL, KXEPLSPREAD-26SEP12LFCFUL, … (15 markets)
    15310639  KXEPLSCORE-26SEP12LFCFUL, KXEPL1HSCORE-26SEP12LFCFUL,
              KXEPLFTTS-26SEP12LFCFUL                               (3 markets)

``26SEP12LFCFUL`` is Kalshi's own event ticker for that fixture, and it is on
both rows. That is an **id-anchored correspondence** — a shared provider id on
the candidate — which is the first arm ruling 048 names, and it is the arm the
rest of this module does not have. Gotcha #32's "an id-less claim NEVER absorbs"
is the reason the other four passes need a clock or a market asymmetry to stand
in for evidence; this pass has the id, so it needs neither.

WHY THE FOUR PASSES ABOVE ALL MISS IT. The ghost is dated 14 hours BEFORE the
canonical, so the direction rule refuses it (passes 1-3). The canonical serves
15 markets, so the market-asymmetry rule refuses it (pass 4). And three of the
six specimens do not share even the LOOSE name key — ``RC Lens`` against
``Racing Club De Lens``, ``Brighton & Hove Albion`` against ``Brighton and Hove
Albion``, ``Deportivo`` against ``RC Deportivo De La Coruña`` — so no widening
short of a fuzzy matcher reaches them by name at all.

WHY THE TICKER MAPS DO NOT REACH IT EITHER, WHICH IS WHY THIS IS NOT
:func:`ticker_pass` AGAIN. That pass reads a COMPETITION off a ticker through
:func:`is_kalshi_game_level_ticker`, and every one of the ghost's three tickers
fails that predicate: ``KXEPLSCORE``, ``KXEPL1HSCORE`` and ``KXEPLFTTS`` are not
registered game-level prefixes, so :func:`competition_from_tickers` returns
``None`` for all six ghosts. This pass never asks which competition a ticker
names. It asks only whether two rows carry the SAME event ticker, which is a
question about string identity and needs no map to be complete.

PRECISION, MEASURED OVER THE WHOLE POPULATION RATHER THAN ARGUED. Production
2026-09-15, every soccer row in the sweep's own -45d/+5d window carrying a
Kalshi market whose ticker has an event suffix::

    rows carrying an event key                                 1,636
      └─ carrying exactly ONE, so this pass reads them         1,617
    distinct event keys over those rows                        1,522
      ├─ keys on one row only                                  1,446
      └─ keys shared by 2+ rows                                   76
           ├─ one played canonical + at least one ghost          13  ← acts
           ├─ two played canonicals                               1  ← refused
           └─ no canonical, or no ghost                          62  ← silent
    ghost rows tagged                                             16
      └─ blocks contributing two of them                          3

**Every shared-key block holding a canonical was read by name — 15 of them under
the grammar before the one-key rule was applied, 33 rows — and every one is
genuinely one fixture: zero collisions.** Sevilla v Atlético (2 copies),
Chelsea v Brighton (2), Man United v Ipswich, Napoli v Como, Sunderland v Fulham
(2), Sevilla v Valencia, Genoa v Frosinone, Grêmio v Vasco, Le Havre v Angers,
Liverpool v Fulham, Freiburg v M'gladbach, Sunderland v Arsenal, Coventry v
Brighton, Le Mans v Lens, Sassuolo v Juventus. A collision would need two soccer
fixtures on one date whose team codes concatenate identically in the same order;
the population says it does not happen, and the claim is falsifiable by re-running
that read rather than by taking this paragraph's word.

WHAT IT REFUSES, AND THE TWO REAL REPAIRS THAT REFUSAL COSTS. A row whose markets
name TWO event keys is left alone — the same None-on-disagreement rule
:func:`competition_from_tickers` applies, for the same reason: a row holding two
venues' fixtures is telling us the link rail is wrong, and the answer to that is
not to pick one. 19 rows are in that state and two of them are otherwise
decidable blocks (Sassuolo v Juventus, Grêmio v Vasco), so the strict rule costs
two repairs. Both canonicals carry two DATE spellings of their own single fixture
(``26SEP12SASJUV`` and ``26SEP13SASJUV``); three others are two ORIENTATIONS of
one fixture, and three more (``26APR11SDMIN`` with ``26AUG01MINSD``) are a
genuine home-and-away pair linked to one row. Separating those is a link-rail
question with its own evidence, not a judgement over two rows, so it is named
here and not guessed at.

WHAT THIS PASS DOES NOT REACH, SAID PLAINLY. Of #6316's six proven duplicates,
five share a ticker and this pass takes them. The sixth — Getafe v Deportivo,
``15310513`` against ``15311881`` — does not: the canonical carries **no Kalshi
markets at all**, so there is no shared id, and pairing it would be absorption on
names and a date alone. It is left refused. #6316's wider population is
477 rows across tennis, soccer and four other sports; this pass is soccer-only
and id-only, and the tennis two thirds of that population is explicitly out of
its reach.

WHY IT MAY TAG MORE THAN ONE GHOST PER BLOCK, WHERE EVERY OTHER PASS REFUSES.
:func:`classify_block` refuses a block with two candidate ghosts because with
names and a clock as the only evidence, "which of these is the copy" is
undecidable. Here it is decided by the anchor rather than by the count: the
canonical is the one row an authority names independently of us, and every other
row carrying that venue's event ticker is a copy of it. Three of the thirteen
blocks hold two ghosts each and all six are real. What stays ambiguous is the
other direction — TWO played, fixture-anchored rows sharing one event ticker —
and that is refused, because it means an authority has named one Kalshi fixture
twice and this module does not adjudicate between authorities.

THE FIFTH PASS IS NOT A SOCCER PASS, AND CONFINING IT TO SOCCER COST NINE ROWS
═══════════════════════════════════════════════════════════════════════════════

Everything above pairs rows on our own club names under a competition, so the
population read was ``WHERE s.key LIKE 'soccer%'`` and the fifth pass inherited
it. Nothing in that pass reads a sport: its key is a venue fixture id, its
canonical test is "does an authority name this row", and its refusal is "two
authorities named it twice". #6358 is the row that makes the inheritance
indefensible::

    14632820  Los Angeles Rams v San Francisco 49ers  americanfootball_nfl
              completed 7-27, espn 401872657, statpal 280446, 66 markets
    15305029  San Francisco v Los Angeles R           basketball_other
              scheduled 2026-09-10 00:00:00+00, 1 market

Both carry ``26SEP10SFLAR``. No name matcher can reach that pair: the sides are
reversed, the away club is truncated to ``Los Angeles R``, and the sport key is
wrong. No clock can: the ghost's kickoff is the ``00:00:00`` placeholder #6316
names. The venue's id can, and it is the only thing that can.

WHAT THE TAG DOES TO SEARCH, AND WHAT IT DOES NOT — MEASURED ON PRODUCTION
2026-09-15, BECAUSE THE DIFFERENCE IS THE WHOLE OF CERT-2910's FINDING. Tagging
``15305029`` withdraws it from every rail reading
:func:`app.utils.proven_duplicates.not_a_proven_duplicate`. That filter is
scope-only: it removes a duplicate, it never recalls the canonical in its place.
So the phantom stops being served, and the query that returned nothing but the
phantom returns nothing at all rather than the game::

    q=Los Angeles R      1 result   the ghost 15305029      → becomes 0 results
    q=Los Angeles Ram   19 results  includes played 14632820, ghost already
                                    absent  → unchanged by this pass

The played game is already reachable one character further in, and was before
this change. **Substituting a canonical for a suppressed duplicate inside search
is a separate ship and is NOT claimed here** — it is the unmet half of #6358,
which is why this pass does not close that issue.

WHAT CHANGED, IN TWO LINES. :func:`plan_ghost_tags` partitions rather than the
SQL filtering: the four name-based passes are handed ``soccer_rows`` via
:func:`row_is_soccer` — the identical population, so they cannot newly reach an
NFL name — and the fifth is handed all of them. And the fifth pass's ghost arm
becomes :func:`row_could_be_a_venue_ticker_ghost`, which drops the "unscored and
advertised" half of the strict test because the id already proved what that half
was inferring.

YIELD AND SAFETY, MEASURED WHOLE-POPULATION ON PRODUCTION 2026-09-15. Every row
in -45d/+5d carrying exactly one Kalshi event ticker — 5,653 rows, 4,785 distinct
keys — blocked by that ticker, in blocks holding exactly one played, fixture-
anchored canonical::

    ghost rows planned                                          25
      ├─ soccer                                                 16  ← unchanged
      ├─ american football                                       7
      ├─ NFL row keyed basketball_other                          1
      └─ tennis                                                  1

**All 16 soccer rows are the SAME 16 the shipped pass already tagged, compared by
id and not by count** — every soccer ghost in the population is
``scheduled``/``suspended``, so the wider arm admits none of them that the strict
arm refused, and the one two-canonical block stays refused. The widening's entire
effect is the nine rows in other sports, and each of the nine was read by name:
seven are the same fixture with the same final score on both rows (26AUG13ARILV
14-27, 26AUG13TENSF 13-19, 26AUG15DALSEA 7-17, 26SEP06LOUMISS 41-38,
26SEP06WSUWASH 24-10, 26SEP12UCDSMU 56-10, and 26SEP12MHUUNM whose copy is
unscored), one is the Rams row above, one is Sabalenka v Rybakina.

THE HALF THAT IS THE SHIP: THE FOLD, NOT THE SUPPRESSION. Six of the seven
football copies are ``completed`` and hold most of the fixture's prices.
``/events/15196980`` — Raiders 14-27 Cardinals, the fixture-anchored row (espn
``401873640``) — renders ONE unlabelled ``No 91% / Yes 9%`` gauge while its copy
``/events/15191796`` carries nineteen graded markets, a win-probability curve
and a score-differential chart. **Neither row is reachable from search** — both
are 2026-08-13 preseason, outside its recency window, measured 2026-09-15 — so
the canonical is not "the row search sends you to": it is the row every rail
keeps once the copy is withdrawn. Tagging the copy folds its markets onto the
canonical, the same reclamation :func:`stranded_market_pass` performs for
soccer, reached here by the venue's id rather than by a market-count asymmetry.
Across the eight pairs the canonical pages carry **101 markets today and 186
after the fold** (production 2026-09-15, counted per row).

HOW THE CROSS-SPORT MARKET REACHES THE PAGE, SINCE IT IS NOT THE CLAUSE THE
SOCCER SECTION ABOVE RELIES ON. ``15305029``'s single market is
``KXNFLFFPTS-26SEP10SFLAR`` — "San Francisco vs Los Angeles R: Fantasy Points",
an NFL market carrying ``llm_sport_category = 'basketball'``. On the Rams
canonical (``expected_category = 'football'``, via
:data:`SPORT_PREFIX_TO_LLM_CATEGORY`, not a bare prefix) it clears neither the
sport-id arm nor the category arm of :func:`linked_market_sport_filter`. It
reaches the page on the third arm, the one #6221 added: a market whose
``sport_id`` is the sport of any event in ``market_event_ids``. That arm exists
for exactly a fold across sport keys, and this is the first pair to exercise it.

WHAT IS STILL OUT OF REACH, SAID PLAINLY. 366 tennis and 126 baseball blocks hold
two or more rows on one event key with NO fixture-anchored canonical among them —
tennis rows carry neither an ``espn_id`` nor a ``statpal_fixture_id``, so
:func:`row_is_a_played_canonical` is false for every row in the block and the
pass is silent by construction. That population is real (one Bonzi v Hanfmann
match exists as six rows, five of them holding one Kalshi market each) and it
needs a canonical test that does not depend on an authority id. It is named here
and not guessed at, because "the row with the most markets wins" is exactly the
name-and-shape absorption gotcha #32 refuses.

THE SIXTH PASS EXTENDS A PROOF THAT ALREADY EXISTS, TO THE COPIES BESIDE IT
═══════════════════════════════════════════════════════════════════════════

#7549. Searching ``feyenoord`` on 2026-09-20 claimed **63 games** and led with a
card for a match that had finished **5-0** four hours earlier. Fifty-seven of
those rows are one fixture: Kalshi's Eredivisie legs each minted their own
``events`` row, because the Pass-2 auto-create guard read only half of its own
subtraction (the forward repair is in ``prediction_market_matching``). One row
of the fifty-seven — ``15316082``, which happens to hold 66 markets — already
carries ``provenance:duplicate-of:15306199``, written by the Polymarket
container rail off a shared provider event id. The other fifty-six carry no tag,
no score, no authority id, and in most cases **no markets at all**: the leg that
minted them was later re-linked, leaving an empty husk that a reader still
counts and search still pages through.

WHY NONE OF THE FIVE PASSES ABOVE REACHES THEM, EACH FOR ITS OWN REASON:

* the canonical spells its away club ``FC Utrecht`` and every copy spells it
  ``Utrecht``. That is a LEADING token, which :func:`loose_block_key`
  deliberately does not strip — ``FC Zurich`` and ``Zurich`` are not known to be
  one club — so passes one, two and three never put them in one block;
* :func:`ticker_pass` re-reads the COMPETITION off a ticker, and these rows are
  already in the right competition. It moves nothing;
* :func:`stranded_market_pass` requires the canonical to serve zero markets;
  ``15306199`` serves five. And it requires the copy to hold at least one, which
  ~50 of the husks do not;
* :func:`fixture_ticker_pass` needs both rows to name the same Kalshi EVENT
  ticker. The canonical holds five POLYMARKET markets and no Kalshi ticker at
  all, so the ticker block holds nothing but ghosts and it correctly refuses.

So the pass keys on the one piece of evidence that IS present: a sibling in the
same block that another rail has already proven, on an id-anchored
correspondence, to be a copy of ``15306199``. The canonical arrives by PRIMARY
KEY rather than by name, which is why no key in this module has to be widened to
reach the specimen — and the pass re-checks that the row that tag names is still
played, scored and fixture-anchored before extending it.

WHAT IT ADDS TO THE EXISTING PROOF, STATED AS ONE CLAIM. That two id-less,
unscored rows carrying the same clubs in the same competition inside
:data:`MAX_GHOST_LAG` of one played fixture are copies of the same thing. That
is the SAME claim every name-keyed pass here already makes, resting on the same
365-day measurement (zero genuine same-orientation rematches inside the window),
and it is made here with strictly more evidence than passes one to three have:
one member of the block is already proven.

YIELD AND PRECISION, whole population, production 2026-09-20, the sweep's own
-45d/+5d window read to exhaustion by id cursor (13,869 rows, 6,399 soccer)::

    blocks holding a proven duplicate beside an untagged copy       100
    tags planned                                                     82
      ├─ Feyenoord v Utrecht      → 15306199  (5-0, statpal 9551358) 56
      ├─ Ajax v Excelsior         → 15306197  (2-2, statpal 9551354) 19
      └─ Willem II v Sittard      → 15306198  (0-1, statpal 9551357)   7
    canonicals: completed, scored and statpal-anchored               3 / 3
    tags naming a canonical outside these three                      0

**All three canonicals were read by name and all three groups are exactly the
mint storm this pass exists for**: 56 + 1 already-tagged = the 57 rows the
duplicate-group query counts, 19 + 1 = 20, 7 + 1 = 8. Each group's already-proven
row is the evidence and the remainder is the drain, with nothing left over — the
shape a false positive could not produce.

WHAT IT DOES NOT REACH, AND THAT IS THE INTENDED DIRECTION. The same query finds
27 duplicate groups holding 179 rows in fourteen days; this pass takes 82 of
them. The rest — Pohang Steelers v Seoul (25), San Lorenzo v Olimpia (8),
Fortaleza v Junior (6), ADO Den Haag v Heerenveen (6) — hold **no proven sibling
at all**, so there is nothing to extend and the pass is silent by construction.
Under-tagging leaves a duplicate card visible and fixable; the alternative is
inventing the first proof from names alone, which is the call ruling 048 forbids
and which no measurement here supports.
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

#: The one status :func:`stranded_market_pass` excludes, where the passes above
#: instead name the statuses they allow. A stranded market is stranded whatever
#: state its row is in — see the fourth-pass section of the module docstring —
#: but a match actually in progress is unscored, may not be anchored yet, and is
#: the one row here whose mislabelling reaches a reader mid-match.
LIVE_STATUS = "live"

#: The key the ingest writes when it could not say WHICH competition a fixture
#: belongs to. It is not a league — see the docstring section above for what is
#: measured inside it — so it cannot be read as evidence that two rows are two
#: different fixtures. Every other ``soccer_*`` key can.
UNCLASSIFIED_SPORT_KEY = "soccer_other"

#: What makes a row one of the FIRST FOUR passes' rows. One spelling, shared by
#: :func:`row_is_soccer` and by the population SQL's ``LIKE 'soccer%'``, because
#: the sixth section of this docstring turns that SQL filter into an in-process
#: partition and two spellings of "is this soccer" is exactly how a widening
#: leaks into the passes it was measured not to touch.
SOCCER_KEY_PREFIX = "soccer"

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


#: A Kalshi EVENT ticker's second field: two-digit year, three-letter month,
#: two-digit day, then the concatenated team codes — ``26SEP12LFCFUL``.
#:
#: The month is an allowlist rather than ``[A-Z]{3}`` because the whole claim of
#: :func:`kalshi_event_key` is that this string names ONE fixture on ONE date,
#: and three arbitrary letters name nothing. The trailing run is ``[A-Z]+`` with
#: no length rule: team codes are 2 to 5 letters per club and vary by series, and
#: a length rule is a guess where the date prefix is already doing the work.
#:
#: Anchored both ends, so a market-level ticker with a third field
#: (``SERIES-EVENT-OUTCOME``) contributes its EVENT field and never its outcome —
#: the split takes field two, and this asserts field two is a date-shaped one.
_KALSHI_EVENT_TICKER_RE = re.compile(
    r"^[0-9]{2}(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[0-9]{2}[A-Z]+$"
)


def kalshi_event_key(external_ids: Iterable[object]) -> str | None:
    """The one Kalshi EVENT ticker this row's markets name, or ``None``.

    The venue's own identifier for a fixture, which is what makes
    :func:`fixture_ticker_pass` an id-anchored correspondence (ruling 048 arm A)
    rather than one more judgement over names — see that pass and the module
    docstring's fifth section.

    ``None`` on DISAGREEMENT and not a pick, exactly as
    :func:`competition_from_tickers` does and for the same reason: a row whose
    markets name two Kalshi events is telling us the link rail put two fixtures
    on one row, and choosing one of them would build a pairing on top of a known
    link defect. Measured at 19 rows on 2026-09-15 — some two date spellings of
    one fixture, some two orientations, some a genuine home-and-away pair — and
    the module docstring names the two decidable blocks that refusal costs.

    No sport-key or competition map is consulted anywhere here, which is the
    point: :func:`competition_from_tickers` returns ``None`` for every ghost in
    #6316's population because their series prefixes are unregistered, and this
    question does not need the prefix to mean anything.
    """
    named = {
        parts[1]
        for ext in external_ids
        if ext
        for parts in ((str(ext).split("-"),))
        if len(parts) > 1 and _KALSHI_EVENT_TICKER_RE.match(parts[1])
    }
    return named.pop() if len(named) == 1 else None


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
    #: How many markets of ANY source hang off this row. Read ONLY by
    #: :func:`stranded_market_pass`, which uses the asymmetry between the two
    #: halves of a pair as the evidence the other three passes take from the
    #: clock. Defaults to 0 so every existing construction of this row — and
    #: every test written before the fourth pass existed — keeps its meaning:
    #: a row claiming no markets can be neither half of a stranded pair, so an
    #: unset count can only ever withhold a tag.
    market_count: int = 0
    #: The Kalshi EVENT ticker this row's markets unanimously name —
    #: :func:`kalshi_event_key` of the same ``external_id`` list
    #: ``ticker_sport_key`` is read from, or ``None``. Read ONLY by
    #: :func:`fixture_ticker_pass`. Defaults to ``None`` so every row built
    #: before that pass existed keeps its meaning: a row naming no event can be
    #: neither half of a ticker-identity pair, so an unset key can only withhold.
    ticker_event_key: str | None = None
    #: The canonical this row is ALREADY proven to duplicate —
    #: :func:`app.utils.proven_duplicates.canonical_id_from_tags` of its own
    #: ``event_tags``, or ``None``. Read ONLY by :func:`proven_sibling_pass`,
    #: which uses an existing proof as the evidence the other passes take from a
    #: clock, a market count or a ticker. Defaults to ``None`` so every row built
    #: before that pass existed keeps its meaning: a row with no proof behind it
    #: can be neither the sibling that carries one nor a row this pass skips, and
    #: an unset value can only ever withhold a tag.
    duplicate_of: int | None = None


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


def row_is_soccer(row: SoccerRow) -> bool:
    """Is this row one the first four passes are allowed to judge?

    The population read used to answer this in SQL and hand the planner nothing
    else. It no longer does — :func:`fixture_ticker_pass` needs every sport — so
    the filter moved here, unchanged in meaning, and :func:`plan_ghost_tags`
    applies it before the four name-based passes see anything. A predicate rather
    than an inline ``startswith`` at three call sites, for the reason
    :func:`row_is_fixture_anchored` is one: the widening's whole safety argument
    is that passes 1-4 see EXACTLY the rows they were measured on, and that
    argument is only as good as there being one place to read it.

    ``sport_key`` is coerced because a row's key arrives from the database and a
    NULL there must read as "not soccer" rather than raise mid-plan.
    """
    return str(row.sport_key or "").startswith(SOCCER_KEY_PREFIX)


def row_could_be_a_venue_ticker_ghost(row: SoccerRow) -> bool:
    """The ghost arm of the FIFTH pass, which is wider than the other four's.

    :func:`row_could_be_a_ghost` asks three questions — advertised status, no
    score, no fixture id — because the passes that call it have no id and must
    infer from the row's own shape that it is a copy rather than a fixture. This
    pass has the venue's identifier, so only ONE of those three is still load-
    bearing: a row that no authority names, sharing a venue fixture id with a row
    that one does, is the copy. The other two are inferences the id makes
    redundant, and requiring them costs six of the seven measured American
    football repairs, whose copies are ``completed`` and carry the same final
    score as their canonical (26SEP06LOUMISS: 41-38 on both rows, 3 markets on
    the anchored one and 18 on the copy).

    ``live`` is still excluded, by the same reasoning and the same constant as
    :func:`row_could_strand_markets`: a match in progress is the one row here
    whose mislabelling reaches a reader mid-match, and no id-anchored evidence
    makes that cost acceptable. :data:`GHOST_KICKOFF_GRACE` is applied by the
    caller, as everywhere else.

    Measured on production 2026-09-15 over the whole -45d/+5d population: this
    predicate and the strict one plan the IDENTICAL 16 soccer ghosts — every
    soccer ghost in the population is ``scheduled``/``suspended`` anyway — so the
    widening's entire yield is the nine rows in other sports. The module
    docstring's sixth section carries the row-by-row read.
    """
    return not row.is_fixture_anchored and row.status != LIVE_STATUS


def row_is_a_played_canonical(row: SoccerRow) -> bool:
    """The canonical test, named once because two passes ask it.

    :func:`classify_block` used to spell this inline and
    :func:`classify_stranded_block` needs the identical question for its
    ambiguity count. Two spellings of one role is exactly the drift that would
    let the two passes disagree about which rows have been played — so there is
    one predicate and both call it.
    """
    return (
        row.status in SETTLED_STATUSES
        and row.has_final_score
        and row.is_fixture_anchored
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
    #: Blocks the FOURTH pass looked at, and how many of ``tags`` it contributed.
    #: Its own pair for the same reason the other two have one, and with the
    #: sharpest failure of the four: this pass is the only one whose evidence is
    #: the market counts, so it goes quiet the moment those stop being read —
    #: a join that returns no markets leaves every other number in this object
    #: exactly where it was.
    stranded_blocks_examined: int = 0
    stranded_tags: int = 0
    #: Blocks the FIFTH pass looked at, and how many of ``tags`` it contributed.
    #: Its own pair for the same reason as the other three, and it dies in a way
    #: none of them can: it is the only pass keyed on a VENUE identifier, so a
    #: Kalshi ticker-format change takes it to zero while every other number in
    #: this object is untouched. Tags can exceed blocks here — a block may hold
    #: two ghosts — which is true of no other pass and is why the two are
    #: reported rather than one ratio.
    fixture_blocks_examined: int = 0
    fixture_tags: int = 0
    #: Blocks the SIXTH pass looked at, and how many of ``tags`` it contributed.
    #: Its own pair for the same reason as the four above, and it dies in a way
    #: none of them can: its evidence is a tag ANOTHER rail writes, so a rail
    #: that stops writing ``provenance:duplicate-of:`` — or a reader that stops
    #: parsing it — takes this to zero while every other number here is
    #: untouched. Tags can exceed blocks, as in the fifth pass: one block held
    #: 56 copies of one fixture on 2026-09-20.
    proven_blocks_examined: int = 0
    proven_tags: int = 0
    #: How many of ``rows_considered`` the first four passes were handed, i.e.
    #: the soccer partition. Its own number and not a ratio: ``rows_considered``
    #: now counts every sport, so the floor that proves the name-based passes
    #: still reach their population has to be asked of THIS one — a soccer join
    #: that dies while the Kalshi-bearing rows keep arriving moves this to zero
    #: and leaves the total looking healthy.
    soccer_rows_considered: int = 0
    #: How many rows carried exactly one Kalshi event ticker, i.e. the only rows
    #: the fifth pass can ever block. Its own number for the mirror-image reason:
    #: a Kalshi ticker-format change, or a link rail that stops attaching markets,
    #: takes this to zero while the soccer count is untouched.
    ticker_rows_considered: int = 0


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
    canonicals = [r for r in rows if row_is_a_played_canonical(r)]
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


def row_could_strand_markets(row: SoccerRow) -> bool:
    """Could this row be the hidden half of a pair, holding prices nobody sees?

    Unscored and unanchored, exactly as :func:`row_could_be_a_ghost` requires —
    those two are what make a row a copy rather than a fixture. What differs is
    the status question, and the module docstring's fourth-pass section carries
    the measurement: ``GHOST_STATUSES`` describes the states a row can be
    *advertised* in, and four of the eleven measured pairs strand their markets
    on a ``closed`` row that is advertised nowhere. So the allowlist is replaced
    by one exclusion, :data:`LIVE_STATUS`.

    Holding at least one market is a REQUIREMENT and not a detail: a row with no
    markets strands nothing, so there is no defect to repair and no evidence to
    repair it on. The clock is not consulted here at all.
    """
    return (
        row.status != LIVE_STATUS
        and not row.has_final_score
        and not row.is_fixture_anchored
        and row.market_count > 0
    )


def classify_stranded_block(
    rows: list[SoccerRow],
    *,
    now: datetime,
    max_lag: timedelta = MAX_GHOST_LAG,
) -> tuple[str, GhostTag | None, str]:
    """Decide one block for the fourth pass. Returns the same triple as
    :func:`classify_block`, and is pure.

    Two differences from :func:`classify_block`, both stated in the module
    docstring with the measurement behind them:

    * **the pairing is direction-agnostic** — ``abs(...) <= max_lag`` rather than
      the strictly-after rule. Every one of the nineteen measured pairs is dated
      at or before its canonical, so the card rule refuses all of them, and no
      widening of the NAME key reaches any of them either;
    * **market asymmetry replaces what the clock was proving** — the canonical
      must serve nothing and the twin must hold something. That is more evidence
      than the other passes require, and it is what bounds the worst case: this
      can only fire on a page already serving no markets.

    🔴 **The ambiguity count ignores market counts on purpose.** The canonical
    role is counted over every played row in the block via
    :func:`row_is_a_played_canonical`, so a block holding two played fixtures is
    refused BEFORE anyone asks which of them serves zero. Counting only the
    zero-market ones would let a block with one stranded canonical and one
    healthy one look decidable, and "these two clubs played twice in three days"
    is the shape that must never resolve.
    """
    played = [r for r in rows if row_is_a_played_canonical(r)]
    strandable = [
        r
        for r in rows
        if row_could_strand_markets(r)
        and not (now - GHOST_KICKOFF_GRACE < r.commence_time <= now)
    ]
    if not played or not strandable:
        return NOT_A_TWIN, None, "no played row with a market-holding copy here"

    pairs = [
        (ghost, canonical)
        for ghost in strandable
        for canonical in played
        if abs(ghost.commence_time - canonical.commence_time) <= max_lag
    ]
    if not pairs:
        return (
            NOT_A_TWIN,
            None,
            f"no market-holding copy sits within {max_lag.days}d of a played row",
        )

    paired_ghosts = {ghost.event_id for ghost, _ in pairs}
    paired_canonicals = {canonical.event_id for _, canonical in pairs}
    if len(paired_ghosts) != 1 or len(paired_canonicals) != 1:
        return (
            REFUSE_AMBIGUOUS,
            None,
            (
                f"{len(paired_ghosts)} market-holding cop(ies) and "
                f"{len(paired_canonicals)} played row(s) pair in this block — "
                f"which row the prices belong to is not decidable"
            ),
        )

    ghost, canonical = pairs[0]
    if canonical.market_count:
        return (
            NOT_A_TWIN,
            None,
            (
                f"the played row already serves {canonical.market_count} market(s), "
                f"so nothing of its is stranded"
            ),
        )

    lag_hours = (ghost.commence_time - canonical.commence_time).total_seconds() / 3600
    return (
        TWIN_FOUND,
        GhostTag(
            ghost_id=ghost.event_id,
            canonical_id=canonical.event_id,
            reason=(
                f"{ghost.home_team_name} v {ghost.away_team_name}: holds "
                f"{ghost.market_count} market(s) {lag_hours:+.0f}h from a played "
                f"row that serves none, no score, no fixture id"
            ),
        ),
        "stranded",
    )


def stranded_market_pass(
    rows: list[SoccerRow],
    *,
    decided_ghost_ids: set[int],
    now: datetime,
    max_lag: timedelta = MAX_GHOST_LAG,
) -> tuple[list[GhostTag], list[str], int]:
    """Re-run the pairing over what the first three passes left, asking who holds
    the prices instead of who is being advertised.

    Returns ``(tags, refusals, blocks_examined)``. Pure.

    The NARROW key, deliberately and by measurement: all nineteen pairs already
    share it, so nothing here needs :func:`loose_block_key` and this pass does
    not inherit that key's ambiguity. It is therefore the only pass that reuses
    the first pass's own blocking, which is also why it cannot use
    :func:`_reblock` — that helper exists to stop a re-KEYED pass restating an
    earlier pass's refusal in different words, and the question here is
    different, so re-examining the same block is a new answer rather than an
    echo.

    It inherits the property that makes the second and third passes safe, by the
    same mechanism: a ghost already decided is withheld, so no earlier decision
    can be revised. It cannot collide with the earlier passes from the other
    side either — they can only tag a row that is unanchored and unscored, which
    :func:`row_is_a_played_canonical` is false for, so no row this pass calls a
    canonical can already be someone else's ghost.
    """
    residual = [r for r in rows if r.event_id not in decided_ghost_ids]
    blocks: dict[tuple[str, str, str], list[SoccerRow]] = defaultdict(list)
    for r in residual:
        blocks[block_key(r.sport_key, r.home_team_name, r.away_team_name)].append(r)
    blocks, refusals = fold_unclassified_blocks(blocks)

    tags: list[GhostTag] = []
    examined = 0
    for key, members in sorted(blocks.items()):
        if len(members) < 2:
            continue
        examined += 1
        outcome, tag, explanation = classify_stranded_block(
            members, now=now, max_lag=max_lag
        )
        if outcome == TWIN_FOUND and tag is not None:
            tags.append(tag)
        elif outcome == REFUSE_AMBIGUOUS:
            refusals.append(f"{key[1]} v {key[2]} (stranded markets): {explanation}")
    return tags, refusals, examined


def classify_fixture_ticker_block(
    rows: list[SoccerRow],
    *,
    now: datetime,
) -> tuple[str, list[GhostTag], str]:
    """Decide one block for the fifth pass. Pure.

    Returns ``(outcome, tags, explanation)`` — a LIST of tags, which is the one
    shape difference from :func:`classify_block` and
    :func:`classify_stranded_block`, both of which return at most one. The module
    docstring's fifth section carries why: every row in this block carries the
    venue's own ticker for one fixture, so "which of these is the copy" is not a
    question — the canonical is the row an authority names independently of us
    and every other one is a copy of it. Three of the thirteen measured blocks
    hold two ghosts.

    No clock arithmetic and no name comparison happens here at all. The block key
    IS the evidence, so re-deriving agreement from the rows would be a second,
    weaker matcher running underneath a stronger one. That is also why the ghost
    arm is :func:`row_could_be_a_venue_ticker_ghost` and not the strict
    :func:`row_could_be_a_ghost` the other passes use: with the venue's id in
    hand, "unscored and advertised" is a weaker restatement of what the id
    already proved, and requiring it refuses six of the seven measured American
    football repairs for having been played.

    :data:`GHOST_KICKOFF_GRACE` is still applied, by the same expression as
    everywhere else: a row inside half an hour of its own kick-off must not be
    relabelled while a reader may be watching it, and that reason does not depend
    on what proved the pairing.
    """
    played = [r for r in rows if row_is_a_played_canonical(r)]
    ghosts = [
        r
        for r in rows
        if row_could_be_a_venue_ticker_ghost(r)
        and not (now - GHOST_KICKOFF_GRACE < r.commence_time <= now)
    ]
    if not played or not ghosts:
        return NOT_A_TWIN, [], "no played row with an unanchored copy on this ticker"
    if len(played) > 1:
        return (
            REFUSE_AMBIGUOUS,
            [],
            (
                f"{len(played)} played, fixture-anchored rows carry this same "
                f"Kalshi event ticker — an authority has named one venue fixture "
                f"twice and which row is the fixture is not decidable here"
            ),
        )

    canonical = played[0]
    return (
        TWIN_FOUND,
        [
            GhostTag(
                ghost_id=ghost.event_id,
                canonical_id=canonical.event_id,
                reason=(
                    f"{ghost.home_team_name} v {ghost.away_team_name}: shares "
                    f"Kalshi event ticker {ghost.ticker_event_key} with a played, "
                    f"fixture-anchored row and is named by no authority itself"
                ),
            )
            for ghost in ghosts
        ],
        "fixture ticker",
    )


def fixture_ticker_pass(
    rows: list[SoccerRow],
    *,
    decided_ghost_ids: set[int],
    now: datetime,
) -> tuple[list[GhostTag], list[str], int]:
    """Re-run the pairing over what the first four passes left, blocking rows by
    the Kalshi EVENT ticker their own markets name.

    Returns ``(tags, refusals, blocks_examined)``. Pure.

    THE ONLY PASS HERE THAT IS NOT A JUDGEMENT ABOUT NAMES. Its key is a venue
    identifier, so it carries the id-anchored correspondence ruling 048 names as
    arm A and gotcha #32 requires before one row may stand in for another; the
    four passes above have no id and spend their docstrings earning the right to
    proceed without one. The module docstring's fifth section carries the
    specimen (``26SEP12LFCFUL`` on both halves of Liverpool v Fulham), the
    precision read (76 shared keys, 15 canonical-bearing blocks read by name,
    zero collisions), and why neither the direction rule, the market asymmetry,
    the loose name key nor :func:`ticker_pass`'s competition map reaches this
    population.

    It does not call :func:`_reblock`, and not only because the key is a single
    string: that helper exists to stop a re-KEYED pass restating an earlier
    pass's refusal in different words, and the ``already_examined_key_of``
    shortcut would be wrong here. A block every earlier pass saw and refused is
    a NEW answer under a venue id, not an echo of a refusal reached on names.

    It does not call :func:`fold_unclassified_blocks` either, and that is a
    property rather than an omission. The fold exists to move a
    :data:`UNCLASSIFIED_SPORT_KEY` row into the named block for its two clubs;
    this key contains no competition at all, so a ``soccer_other`` row and a
    ``soccer_brazil_campeonato`` row sharing one event ticker are already in one
    block. The measured population contains exactly that pair — ``15311681``
    against ``15299943``, Grêmio v Vasco — and it needs no fold to be seen.

    It inherits the property that makes passes two, three and four safe, by the
    same mechanism: a ghost already decided is withheld, so no earlier decision
    can be revised. It cannot collide from the other side either — every earlier
    pass can only tag an unanchored, unscored row, which
    :func:`row_is_a_played_canonical` is false for, so no row this pass calls a
    canonical is already someone else's ghost.
    """
    residual = [r for r in rows if r.event_id not in decided_ghost_ids]
    blocks: dict[str, list[SoccerRow]] = defaultdict(list)
    for r in residual:
        if r.ticker_event_key:
            blocks[r.ticker_event_key].append(r)

    tags: list[GhostTag] = []
    refusals: list[str] = []
    examined = 0
    for key, members in sorted(blocks.items()):
        if len(members) < 2:
            continue
        examined += 1
        outcome, block_tags, explanation = classify_fixture_ticker_block(
            members, now=now
        )
        if outcome == TWIN_FOUND:
            tags.extend(block_tags)
        elif outcome == REFUSE_AMBIGUOUS:
            refusals.append(f"{key} (fixture ticker): {explanation}")
    return tags, refusals, examined


def classify_proven_sibling_block(
    rows: list[SoccerRow],
    canonical_by_id: dict[int, SoccerRow],
    *,
    now: datetime,
    max_lag: timedelta = MAX_GHOST_LAG,
) -> tuple[str, list[GhostTag], str]:
    """Decide one block for the SIXTH pass. Pure.

    Returns ``(outcome, tags, explanation)`` — a LIST, like
    :func:`classify_fixture_ticker_block` and for the same reason: the question
    "which of these is the copy" is not asked here, so there is no count at which
    it becomes undecidable. Every id-less row in the block is a copy of the one
    fixture the block's existing proof names.

    The canonical is NOT taken from this block. It is looked up by id in
    ``canonical_by_id``, which is the whole point of the pass — the specimen's
    canonical spells its away club ``FC Utrecht`` where all 57 copies spell it
    ``Utrecht``, so it is in a different block under every key this module has.
    A canonical that is not in the window, or that does not meet
    :func:`row_is_a_played_canonical`, is refused rather than assumed: the tag
    being re-used as evidence was written by another rail, and this pass verifies
    the row it names still looks like a canonical before extending it.
    """
    named = {row.duplicate_of for row in rows if row.duplicate_of is not None}
    if not named:
        return NOT_A_TWIN, [], "no row in this block is a proven duplicate of anything"
    if len(named) > 1:
        return (
            REFUSE_AMBIGUOUS,
            [],
            (
                f"{len(named)} different canonicals are already named by proven "
                f"duplicates in this block — which fixture these rows copy is not "
                f"decidable here"
            ),
        )

    canonical_id = named.pop()
    canonical = canonical_by_id.get(canonical_id)
    if canonical is None:
        return (
            NOT_A_TWIN,
            [],
            f"the proven canonical {canonical_id} is not in this window",
        )
    if not row_is_a_played_canonical(canonical):
        return (
            NOT_A_TWIN,
            [],
            (
                f"the proven canonical {canonical_id} is not a played, "
                f"fixture-anchored row today"
            ),
        )

    rival = next(
        (
            row
            for row in rows
            if row.event_id != canonical_id and row_is_a_played_canonical(row)
        ),
        None,
    )
    if rival is not None:
        return (
            REFUSE_AMBIGUOUS,
            [],
            (
                f"row {rival.event_id} in this block is itself a played, "
                f"fixture-anchored fixture distinct from the proven canonical "
                f"{canonical_id} — two real fixtures share this key"
            ),
        )

    ghosts = [
        row
        for row in rows
        if row.duplicate_of is None
        and row_could_be_a_ghost(row)
        and not (now - GHOST_KICKOFF_GRACE < row.commence_time <= now)
        and abs(row.commence_time - canonical.commence_time) <= max_lag
    ]
    if not ghosts:
        return NOT_A_TWIN, [], "no untagged copy left in this block"

    return (
        TWIN_FOUND,
        [
            GhostTag(
                ghost_id=ghost.event_id,
                canonical_id=canonical_id,
                reason=(
                    f"{ghost.home_team_name} v {ghost.away_team_name}: an id-less "
                    f"copy sharing its competition, clubs and window with a row "
                    f"already proven to duplicate {canonical_id}"
                ),
            )
            for ghost in ghosts
        ],
        "proven sibling",
    )


def proven_sibling_pass(
    rows: list[SoccerRow],
    *,
    decided_ghost_ids: set[int],
    now: datetime,
    max_lag: timedelta = MAX_GHOST_LAG,
) -> tuple[list[GhostTag], list[str], int]:
    """Re-run the pairing over what the first five passes left, using a proof
    that ALREADY EXISTS on one row of the block as the evidence for its siblings.

    Returns ``(tags, refusals, blocks_examined)``. Pure. See the module
    docstring's seventh section for the specimen, the population and why the five
    passes above reach none of it.

    THE EVIDENCE IS NOT A NEW JUDGEMENT. Every other pass here decides, from
    scratch, that two rows are one fixture. This one decides nothing of the kind:
    it reads a ``provenance:duplicate-of:`` element that another rail — one with
    an id-anchored correspondence behind it (ruling 048 arm A or B) — has already
    written, verifies that the row it names still reads as a played,
    fixture-anchored canonical, and extends that finding to the rows the same
    mint produced beside it. What it adds to the existing proof is one claim:
    that two id-less rows carrying the same clubs, in the same competition,
    inside :data:`MAX_GHOST_LAG` of the same played fixture, are copies of the
    same thing. The module docstring's 365-day rematch measurement is what
    bounds that claim, and it is the same measurement every name-keyed pass here
    already rests on.

    IT IS THE ONLY PASS WHOSE CANONICAL NEED NOT BE IN THE BLOCK, which is why
    it reaches a population the other five cannot. ``Feyenoord v Utrecht`` and
    ``Feyenoord v FC Utrecht`` differ in a LEADING token, which
    :func:`loose_block_key` deliberately does not strip (``FC Zurich`` and
    ``Zurich`` are not known to be one club), so no key in this module puts the
    copies and their canonical together. The proven sibling bridges them without
    widening any key: the canonical arrives by primary key, not by name.

    It inherits the two properties that make passes two to five safe, by the same
    mechanism: a ghost already decided is withheld, so no earlier decision can be
    revised; and a row this pass calls a canonical is played, scored and
    fixture-anchored, which :func:`row_could_be_a_ghost` is false for, so it can
    never already be another pass's ghost.

    A row that already carries a tag is never re-tagged — it is this pass's
    EVIDENCE, not its subject — so running the sweep twice over an unchanged
    population plans the same tags the second time and writes none of them.
    """
    residual = [r for r in rows if r.event_id not in decided_ghost_ids]
    canonical_by_id = {r.event_id: r for r in rows}

    blocks: dict[tuple[str, str, str], list[SoccerRow]] = defaultdict(list)
    for r in residual:
        blocks[_loose_name_key(r)].append(r)
    blocks, refusals = fold_unclassified_blocks(blocks)

    tags: list[GhostTag] = []
    examined = 0
    for key, members in sorted(blocks.items()):
        if len(members) < 2:
            continue
        if not any(m.duplicate_of is not None for m in members):
            continue
        examined += 1
        outcome, block_tags, explanation = classify_proven_sibling_block(
            members, canonical_by_id, now=now, max_lag=max_lag
        )
        if outcome == TWIN_FOUND:
            tags.extend(block_tags)
        elif outcome == REFUSE_AMBIGUOUS:
            refusals.append(f"{key[1]} v {key[2]} (proven sibling): {explanation}")
    return tags, refusals, examined


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

    :func:`fixture_ticker_pass` runs FIFTH and last, over what the other four
    left, blocking rows by the Kalshi EVENT ticker their markets name rather than
    by any reading of our own club names. It is the only pass with an id-anchored
    correspondence behind it and the only one that can tag more than one ghost in
    a block; its own docstring and the module docstring's fifth section carry
    both. Running it last is what keeps it purely additive.

    🔴 **The five passes are handed DIFFERENT populations, and that line is the
    whole safety argument for the widening.** ``rows`` is now every sport; the
    four name-based passes are handed ``soccer_rows`` — the same partition their
    SQL filter used to make — and only the fifth sees the rest. Done here rather
    than in the caller so that a pure test can prove it: pass an NFL row into
    this function and passes 1-4 must behave exactly as if it were absent, which
    is not a property a SQL ``WHERE`` clause can be tested for. The module
    docstring's sixth section carries what the fifth pass gains by it.

    :func:`proven_sibling_pass` runs SIXTH and last, over what the five above
    left. It is the only pass that decides nothing on its own: it reads a
    ``provenance:duplicate-of:`` element another rail already wrote, verifies the
    row it names still reads as a played canonical, and extends it to the id-less
    copies in the same block. Running it last is what keeps it additive, and its
    canonical is fetched by id rather than found in the block — see the module
    docstring's seventh section for why that is the only thing that reaches its
    population.

    :func:`stranded_market_pass` runs FOURTH and is the only one asking a
    different question — not "which row is still being advertised" but "which
    row is holding the prices" — over the narrow key, direction-agnostic, and
    gated on a played row that serves no markets at all. Its own section of the
    module docstring carries why the three passes above cannot reach that
    population and why this one is safe to run beside them.
    """
    soccer_rows = [row for row in rows if row_is_soccer(row)]

    blocks: dict[tuple[str, str, str], list[SoccerRow]] = defaultdict(list)
    for row in soccer_rows:
        blocks[block_key(row.sport_key, row.home_team_name, row.away_team_name)].append(
            row
        )
    blocks, fold_refusals = fold_unclassified_blocks(blocks)

    plan = GhostPlan(
        rows_considered=len(rows),
        soccer_rows_considered=len(soccer_rows),
        ticker_rows_considered=sum(1 for row in rows if row.ticker_event_key),
    )
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
        soccer_rows,
        decided_ghost_ids={t.ghost_id for t in plan.tags},
        now=now,
        max_lag=max_lag,
    )
    plan.tags.extend(extra_tags)
    plan.refusals.extend(extra_refusals)
    plan.residual_blocks_examined = examined
    plan.residual_tags = len(extra_tags)

    ticker_tags, ticker_refusals, ticker_examined = ticker_pass(
        soccer_rows,
        decided_ghost_ids={t.ghost_id for t in plan.tags},
        now=now,
        max_lag=max_lag,
    )
    plan.tags.extend(ticker_tags)
    plan.refusals.extend(ticker_refusals)
    plan.ticker_blocks_examined = ticker_examined
    plan.ticker_tags = len(ticker_tags)

    stranded_tags, stranded_refusals, stranded_examined = stranded_market_pass(
        soccer_rows,
        decided_ghost_ids={t.ghost_id for t in plan.tags},
        now=now,
        max_lag=max_lag,
    )
    plan.tags.extend(stranded_tags)
    plan.refusals.extend(stranded_refusals)
    plan.stranded_blocks_examined = stranded_examined
    plan.stranded_tags = len(stranded_tags)

    fixture_tags, fixture_refusals, fixture_examined = fixture_ticker_pass(
        rows,
        decided_ghost_ids={t.ghost_id for t in plan.tags},
        now=now,
    )
    plan.tags.extend(fixture_tags)
    plan.refusals.extend(fixture_refusals)
    plan.fixture_blocks_examined = fixture_examined
    plan.fixture_tags = len(fixture_tags)

    proven_tags, proven_refusals, proven_examined = proven_sibling_pass(
        soccer_rows,
        decided_ghost_ids={t.ghost_id for t in plan.tags},
        now=now,
        max_lag=max_lag,
    )
    plan.tags.extend(proven_tags)
    plan.refusals.extend(proven_refusals)
    plan.proven_blocks_examined = proven_examined
    plan.proven_tags = len(proven_tags)
    return plan
