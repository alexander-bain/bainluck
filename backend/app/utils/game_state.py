"""Display helpers for live game state labels."""

from __future__ import annotations

import re


# Pre-game status_detail strings like "Wed, March 25th at 10:00 PM EDT" should
# not be stored as period values. Lives here rather than in the ESPN task
# module (#5390): it is a pure statement about period strings, this module
# imports nothing but `re`, and its old home forced every caller in
# `utils/espn_helpers.py` into a function-local import to dodge a real cycle.
#
# ESPN writes the pre-game detail in TWO shapes and the pattern only knew the
# long one. The short numeric form ("5/23 - TBD") reached production and sat in
# `events.period`. The `\d{1,2}/\d{1,2}` branch requires a digit on BOTH sides
# of the slash, which is what keeps it off the real period vocabulary —
# "Final/10", "Final/2OT" and "Final/SO" all carry a letter before the slash.
# Measured against the whole `events` table, the branch newly matches 5 rows
# and every one of them is a date.
_PREGAME_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b"
    r"|\b\d{1,2}/\d{1,2}\b",
    re.IGNORECASE,
)


def _sanitize_period(status_detail: str | None) -> str | None:
    """Return status_detail if it looks like a game period, else None."""
    if not status_detail:
        return None
    if _PREGAME_DATE_RE.search(status_detail):
        return None
    return status_detail


_BASEBALL_HALF_ALIASES = {
    "top": "Top",
    "t": "Top",
    "bot": "Bottom",
    "bottom": "Bottom",
    "b": "Bottom",
    "mid": "Mid",
    "middle": "Mid",
    "end": "End",
}
_NON_BASEBALL_PERIODS = {"1h", "2h", "ht", "halftime", "1st half", "2nd half"}


def _ordinal_inning(value: str) -> str | None:
    try:
        inning = int(value)
    except (TypeError, ValueError):
        return None
    if inning <= 0:
        return None
    if 10 <= inning % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(inning % 10, "th")
    return f"{inning}{suffix}"


def _baseball_inning_label(value: str | None) -> str | None:
    if not value:
        return None

    text = str(value).strip()
    lowered = text.lower().strip()
    if lowered in _NON_BASEBALL_PERIODS:
        return None

    half_match = re.search(
        r"\b(top|t|bot|bottom|b|mid|middle|end)\b(?:\s+of)?\s+"
        r"(?:the\s+)?(\d+)(?:st|nd|rd|th)?(?:\s+inning)?\b",
        lowered,
    )
    if half_match:
        half = _BASEBALL_HALF_ALIASES[half_match.group(1)]
        inning = _ordinal_inning(half_match.group(2))
        return f"{half} {inning}" if inning else None

    inning_match = re.search(
        r"\b(?:inning\s+)?(\d+)(?:st|nd|rd|th)?(?:\s+inning)?\b",
        lowered,
    )
    if inning_match and ("inning" in lowered or lowered.isdigit()):
        return _ordinal_inning(inning_match.group(1))

    return None


def normalize_live_game_state(
    sport_key: str | None,
    period: str | None,
    game_clock: str | None,
) -> tuple[str | None, str | None]:
    """Return display-safe ``(period, game_clock)`` for API payloads."""
    if not sport_key or not sport_key.startswith("baseball"):
        return period, game_clock

    inning_label = _baseball_inning_label(period) or _baseball_inning_label(game_clock)
    return inning_label, None


# ─── #6056: WHERE A LIVE ROW IS IN ITS OWN GAME, SO TWO WRITERS CAN BE ORDERED ──
#
# `events.home_score` / `away_score` / `game_clock` / `period` have at least two
# unarbitrated writers on a live row — `espn_helpers.update_event_fields_from_espn`
# and `statpal_sync._sync_statpal_livescores` — and each one writes whatever it
# just fetched. Last write wins, so when the two feeds disagree the served state
# does not converge, it ALTERNATES. Measured on production in our own
# `score_snapshots` table for event 14637256 (Giants v Cowboys, 2026-09-14), the
# two writers are separable by their cadence offsets, `:37` and `:09`:
#
#     02:58:37  28–14   <- ESPN     03:11:37  28–20   <- ESPN
#     02:59:09  21–14   <- other    03:12:09  28–14   <- other
#     02:59:37  28–14   <- ESPN     03:12:37  28–20   <- ESPN
#     03:00:09  27–14   <- other    03:13:09  28–14   <- other
#     03:00:37  28–14   <- ESPN     03:13:39  28–20   <- ESPN
#
# A reader watching that page saw a point un-score itself, and later a
# touchdown leave the page for a minute and come back. ESPN's own snapshots over
# the same window are strictly monotonic, so neither feed is "corrupt" — the
# second one is simply BEHIND, and nothing stops a behind observation
# overwriting an ahead one.
#
# ── WHY THE PRIMARY DISCRIMINATOR IS GAME TIME AND NOT THE SCORE ──
#
# The obvious guard — "a score may not go down, ever" — is the wrong one and was
# rejected. A score going down is exactly what a legitimate correction looks
# like: a touchdown reversed on review, a point taken off after a penalty. An
# UNCONDITIONAL monotonic clamp would pin the first wrong number ever written
# and call it truth, which is a worse failure than the flicker because it never
# heals.
#
# So the discriminator is WHEN the observation was taken, in game time. An
# observation positioned strictly EARLIER in the game than the state already
# stored cannot be news, whatever it says; one positioned strictly AFTER it is
# accepted, whatever it says — including a lower score. That is the rule, and
# for every sport that carries a clock it is the whole rule.
#
# ── #6251: AT A POSITION TIE, AND ONLY THERE, THE SCORE BREAKS IT ──
#
# Game time is a discriminator only as fine as the label it is read from, and
# baseball's label has no clock in it. `live_progress_position` gives every
# observation inside one `Top 4th` the identical tuple `(inning*4 + state, 0.0)`,
# so the comparison above ties, the guard accepts, and a lagging feed overwrites
# an ahead one with nothing standing in its way. That is not a corner: MEASURED
# on production over the three days to 2026-09-15, MLB score reversions in
# `score_snapshots` split
#
#     221 pairs / 37 events   at the SAME inning-state   <- ties, accepted today
#       1 pair  /  1 event    at a different one         <- the rule above
#      70 pairs / 22 events   no period evidence either side
#
# and every one of the 221 sat on a plain `Top N` / `Bottom N` label that this
# module places perfectly well. The guard is not failing to parse them; it is
# parsing them, finding them equal, and having nothing else to say.
#
# The tie-break is the score, and the reason that is NOT the clamp rejected
# above is how narrowly it is scoped. Three fences, and the first is the one
# that matters:
#
#   * IT APPLIES ONLY WHERE THE LABEL NAMES A SPAN, never where it names an
#     instant — see `_position_names_a_span`. A clocked tie (`5:21 - 4th
#     Quarter` against itself) is two feeds agreeing on the second and
#     disagreeing on the score, which IS a correction and still lands at once; a
#     lagging clocked feed lags in its clock, so the rule above has it already.
#     An inning tie agrees on nothing finer than "somewhere in this half-inning".
#   * It refuses only while the position is UNCHANGED. The instant the game
#     moves to the next inning-state the incoming position is strictly later,
#     the first rule accepts it, and the lower score lands. So a genuine
#     correction is DEFERRED by at most one half-inning, never pinned. The
#     objection to the clamp was that it never heals; this heals on the clock
#     of the game itself, exactly as the positional refusal does.
#   * It is consulted only when all four scores are readable. A missing score
#     on either side is no evidence and leaves today's behaviour untouched. A
#     tie whose score RISES, or holds, still lands.
#
# What it buys: within one half-inning a run cannot un-score itself. What it
# costs: a downward correction taken mid-inning waits for the inning-state to
# turn. On a feed that publishes a corrected score every 30 seconds, that is a
# bounded wait for a right answer against an unbounded flicker of wrong ones.
#
# ── IT ONLY REFUSES WHAT IT CAN PROVE, AND IT CANNOT DEADLOCK ──
#
# Unparseable on EITHER side ⇒ no refusal. A position this function cannot
# locate is not evidence of staleness, and a guard that blocks writes it does
# not understand would freeze a live game — far worse than the flicker it is
# fixing. Equal positions with no score evidence are accepted too, so a
# same-moment correction lands.
#
# There is also no way for a refusal to become permanent. The bar is the STORED
# position, which the game itself moves past: if the ahead writer falls silent,
# the behind writer catches up to the frozen bar within a minute or two and is
# accepted again. The #6251 tie-break inherits that property rather than
# weakening it — its bar is the stored position too, and it stops applying the
# moment the game leaves it. Nothing needs a timeout, and no writer is declared
# the winner — the ordering is symmetric, so whichever feed is ahead at that
# instant wins that instant.

#: `M:SS`, `MM:SS` or `MMM:SS`, with an optional tenths tail (ESPN serves
#: `0:04.2` inside the final minute of a period). Anchored: a clock is the whole
#: field or it is not a clock.
_GAME_CLOCK_RE = re.compile(r"^\s*(\d{1,3}):([0-5]\d)(?:\.\d+)?\s*$")

#: The countdown families, measured off `espn_snapshots.period` over two days of
#: production (2026-09-12/14): `'5:21 - 4th Quarter'` for football, and `Period`
#: for the hockey shape of the same string. Both count DOWN, which is what makes
#: a smaller remaining time LATER in the game.
#:
#: `Half` is deliberately absent. Soccer's clock counts UP and college
#: basketball's counts DOWN, so one `Half` label cannot be given a direction
#: from the string alone, and guessing it would invert the comparison for a
#: whole sport. Those rows fall through to "unparseable", i.e. today's
#: behaviour.
_COUNTDOWN_PERIOD_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)\s+(?:quarter|period)\b", re.IGNORECASE
)

#: `'End of 3rd Quarter'` — the same period at its last instant. Given remaining
#: `0`, which sorts it after every clocked observation in that period and before
#: the next one, with no special case anywhere else.
_END_OF_PERIOD_RE = re.compile(
    r"\bend\s+of\s+(\d{1,2})(?:st|nd|rd|th)\s+(?:quarter|period)\b", re.IGNORECASE
)

#: `'OT'`, `'2OT'`, `'Overtime'` — measured on NFL rows as `'10:00 - OT'`. Ranked
#: after regulation for every sport that uses the label (4 quarters, 3 hockey
#: periods, 4 basketball quarters all end below 5).
_OVERTIME_RE = re.compile(r"\b(\d)?\s*(?:ot|overtime)\b", re.IGNORECASE)
_REGULATION_PERIODS = 4

#: TERMINAL LABELS ARE REFUSED BEFORE ANYTHING ELSE IS TRIED, and this is not
#: belt-and-braces — the measured vocabulary contains `'Final/OT'` and
#: `'Final/4OT'`, which the overtime branch below would otherwise place as a
#: LIVE overtime position (and `'Final/4OT'` as the fourth one, ranked above
#: every real moment of the game). A finished row is not a position in a running
#: game; the guard has nothing to say about one and must not pretend otherwise.
#: Caught by `test_unplaceable_labels_are_none[Final/OT]`, not by reading.
_TERMINAL_LABEL_RE = re.compile(
    r"\bfinal\b|\bft\b|\bfull[- ]time\b|\bended\b|\bpostponed\b"
    r"|\bcancell?ed\b|\babandoned\b",
    re.IGNORECASE,
)

#: Baseball has no clock, so its ordering is entirely in the label: FOUR states
#: per inning, in the order the game plays them — `Top` (visitors bat), `Middle`
#: (the break after the top half), `Bottom` (home bats), `End` (the break after
#: the bottom half, before the next inning's top).
#:
#: ── WHY `Middle`/`End` ARE RANKED NOW AND WERE NOT BEFORE (#6251) ──
#:
#: They were originally listed as deliberately unplaceable, on the stated ground
#: that they were an "unobserved family" (#5017) — the same conservatism that
#: still refuses `Half`. That premise is now refuted by measurement, and the two
#: cases are NOT alike:
#:
#: * OBSERVED. `espn_snapshots` holds `'End 8th'`, `'End 11th'`, `'End 2nd'`,
#:   `'End 3rd'`, `'Middle 7th'`, `'Middle 9th'` between 2026-03-15 and
#:   2026-08-26; and a direct read of `events.period` at 2026-09-15 00:25Z
#:   caught 2 of the 6 live MLB rows sitting on one (`'Middle 3rd'` on 15312194,
#:   `'End 7th'` on 15312187). They are the INNING-BREAK states, so they are
#:   short-lived — which is why a sparse snapshot table under-counts them and
#:   why the live table catches them a third of the time.
#: * UNAMBIGUOUS. `Half` is refused because the STRING cannot say which way its
#:   clock runs, so ranking it would invert a whole sport. Nothing is being
#:   guessed here: baseball's structure fixes top → middle → bottom → end, and
#:   the label names the state outright.
#:
#: Leaving them unplaceable is not neutral. Unplaceable means the guard stands
#: down ENTIRELY on that row — not "coarse", blind — so while a game sat in an
#: inning break, an observation from the 1st could overwrite the 9th. That
#: window is exactly when a run has just scored and the feeds most disagree.
#:
#: Ranking four states per inning rather than two also halves the tie window the
#: guard cannot see through. It does NOT close it: two observations inside one
#: `Top 4th` still tie, which is #6251's remaining half.
#:
#: ONLY the full-word spellings are ranked, on purpose. `_BASEBALL_HALF_ALIASES`
#: above canonicalises `middle` to `'Mid'`, which reads like a spelling this
#: guard should also accept — it is not, because that function is display-only
#: (`normalize_live_game_state`'s three callers are all serializers) and its
#: output is never written back to `events.period`. Checked rather than assumed:
#: `'Mid …'`, `'Bot …'`, `'T …'` and `'B …'` return 0 rows across both
#: `espn_snapshots.period` and `events.period`. Ranking an unstored spelling
#: would be the same unmeasured guess this block just finished refuting.
_INNING_STATE_RANK = {"top": 1, "middle": 2, "bottom": 3, "end": 4}
_INNING_STATES_PER_INNING = 4
#: The negative lookahead keeps this off the other sports' `End` family. Every
#: non-baseball `End` label measured across `espn_snapshots` is the
#: `'End of 3rd Quarter'` / `'End of 2nd Half'` / `'End of OT'` shape, which
#: carries an ` of ` and so cannot match `end <n><ord>` anyway; the lookahead is
#: for the unmeasured `'End 1st Period'` spelling, where stealing a hockey
#: period-end into the inning ladder would be silent and wrong. Fail-closed:
#: it can only make this branch decline, never widen it.
_INNING_STATE_RE = re.compile(
    r"\b(top|middle|bottom|end)\s+(\d{1,2})(?:st|nd|rd|th)\b"
    r"(?!\s+(?:quarter|period|half))",
    re.IGNORECASE,
)


def is_countdown_clock(value: str | None) -> bool:
    """Whether ``value`` is a game clock in the ``M:SS`` shape both writers store.

    #8322: StatPal's hockey board serves ``timer`` as the MINUTE OF THE PERIOD
    ELAPSED — a bare ``'13'``, counting UP — while ESPN's clock for the same
    game is ``'7:00'`` REMAINING, counting down. Measured side by side on
    Stars–Wild (15313798), 2026-09-24: ESPN ``19:33`` left ↔ StatPal ``1``;
    ESPN ``18:42`` left ↔ StatPal ``2``. Written into the same columns, the
    reader's badge read ``1 - 3rd Period`` and then ``19:03 - 3rd Period``
    forty-six seconds apart. A value that is not ``M:SS`` is not this kind of
    clock, whatever else it is.
    """
    return bool(value) and _GAME_CLOCK_RE.match(str(value)) is not None


def period_places_within(stored_period: str | None, label: str | None) -> bool:
    """Whether ``stored_period`` is a POSITION inside the period named ``label``.

    ``'18:42 - 3rd Period'`` and ``'End of 3rd Period'`` both place the game
    inside ``'3rd Period'``; the bare label ``'3rd Period'`` says only which
    period it is. A writer holding nothing finer than the label (#8322's
    StatPal hockey board) must not replace the finer stored value with it: the
    reader would lose the clock, and on the next ESPN pass get it back — a
    badge that blinks every minute. ``'13 - 2nd Period'`` (a bare minute
    stored before #8322) is NOT a position — it is exactly the value the label
    should replace — which is why this asks `live_progress_position` rather
    than comparing strings.
    """
    if not stored_period or not label:
        return False
    stored = str(stored_period).strip()
    wanted = str(label).strip()
    if not wanted or stored.casefold() == wanted.casefold():
        return False
    if not stored.casefold().endswith(wanted.casefold()):
        return False
    return live_progress_position(stored, None) is not None


def _clock_remaining_seconds(*candidates: str | None) -> float | None:
    """Seconds left in the period, from the first candidate that is a clock.

    Both live writers compose `period` as ``f"{clock} - {label}"`` (#5017 made
    StatPal byte-identical to ESPN on purpose), so the clock is usually readable
    off the period string itself; the separate ``game_clock`` column is the
    fallback for a writer that only fills one of them.
    """
    for candidate in candidates:
        if not candidate:
            continue
        match = _GAME_CLOCK_RE.match(str(candidate))
        if match:
            return int(match.group(1)) * 60 + int(match.group(2))
        # `'5:21 - 4th Quarter'`: take the clock off the front, if there is one.
        head = str(candidate).split(" - ", 1)[0]
        match = _GAME_CLOCK_RE.match(head)
        if match:
            return int(match.group(1)) * 60 + int(match.group(2))
    return None


def live_progress_position(
    period: str | None, game_clock: str | None
) -> tuple[float, float] | None:
    """Where this observation sits in its own game, or ``None`` if unreadable.

    Returns ``(period_rank, elapsed_key)``, comparable with ``<``: a LARGER
    tuple is LATER in the game. ``elapsed_key`` is the negated seconds remaining
    for countdown sports, so a smaller clock sorts later without the caller
    having to know which way the clock runs.

    ``None`` means "cannot locate this observation", which every caller must
    treat as "no evidence", never as "earliest". See the module note above.
    """
    if not period:
        return None
    text = str(period).strip()
    if not text:
        return None
    if _TERMINAL_LABEL_RE.search(text):
        return None

    end_of = _END_OF_PERIOD_RE.search(text)
    if end_of:
        return (float(end_of.group(1)), 0.0)

    inning_state = _INNING_STATE_RE.search(text)
    if inning_state:
        inning = int(inning_state.group(2))
        state = _INNING_STATE_RANK[inning_state.group(1).lower()]
        return (float(inning * _INNING_STATES_PER_INNING + state), 0.0)

    countdown = _COUNTDOWN_PERIOD_RE.search(text)
    if countdown:
        remaining = _clock_remaining_seconds(text, game_clock)
        if remaining is None:
            return None
        return (float(countdown.group(1)), -remaining)

    overtime = _OVERTIME_RE.search(text)
    if overtime:
        # `'OT'` is the first overtime; `'2OT'` the second.
        nth = int(overtime.group(1)) if overtime.group(1) else 1
        remaining = _clock_remaining_seconds(text, game_clock)
        if remaining is None:
            return None
        return (float(_REGULATION_PERIODS + nth), -remaining)

    return None


def _as_score(value: object) -> int | None:
    """``value`` as a score, or ``None`` if it is not one.

    Deliberately total rather than trusting the caller: three writers feed this,
    two of them from duck-typed fixture objects that make no promise about the
    type of ``home_score``. An un-coercible value is NO EVIDENCE — the same
    verdict an absent score gets — never an exception and never a zero, because
    a zero here is a real baseball score and would read as a reversion from any
    lead (gotcha: absent and empty are different claims).
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _position_names_a_span(period: str | None) -> bool:
    """Does this label name a STRETCH of game time rather than an instant?

    This is the whole reason the #6251 tie-break is not a general rule, and the
    distinction is the one the existing behaviour already turns on:

    * `'5:21 - 4th Quarter'` locates an observation to the SECOND. Two feeds
      that tie there genuinely agree about the moment and disagree about the
      score, which is what a correction looks like — and a feed that were merely
      lagging would be lagging in its clock too, so the position rule has
      already caught it. Those ties must keep landing immediately
      (`test_schedule_sync_accepts_a_same_position_correction`).
    * `'Top 8th'` locates it to a half-inning, which is minutes wide. A tie
      there is not evidence of simultaneity; it is the absence of any evidence
      at all, and it is the window the lagging feed lives in.

    So only the inning ladder qualifies. `'End of 3rd Quarter'` is deliberately
    excluded even though it also carries a `0.0` elapsed: that is a real instant
    the game passes through once, not a span.

    Requiring BOTH sides to satisfy this also keeps the tie-break off a rank
    COLLISION rather than a real tie — `'Top 1st'` and `'End of 5th Period'`
    both place at `(5.0, 0.0)`, because the inning ladder and the period ladder
    share a number line they never share a row on.
    """
    if not period:
        return False
    return bool(_INNING_STATE_RE.search(str(period)))


def _score_would_regress(
    stored_home: object,
    stored_away: object,
    incoming_home: object,
    incoming_away: object,
) -> bool:
    """Does this observation take a run/point off a side, with all four readable?

    ``False`` unless every one of the four is a readable score: a comparison
    missing a side is no evidence, and this is only ever consulted as a
    tie-break, where "no evidence" must leave the tie accepted.

    EITHER side falling is enough. A pair where one side rises and the other
    falls is not a lagging feed and not a correction — it is two different
    games, or a feed mid-rewrite — and refusing it costs one beat.
    """
    sh = _as_score(stored_home)
    sa = _as_score(stored_away)
    ih = _as_score(incoming_home)
    ia = _as_score(incoming_away)
    if sh is None or sa is None or ih is None or ia is None:
        return False
    return ih < sh or ia < sa


def _authority_is_correcting_itself(incoming_is_authority: bool) -> bool:
    """At a span tie, is this the authority feed correcting its OWN reading?

    ── THE HOLE #6251's FIRST PASS LEFT, AND WHY IT IS THIS SHAPE ──

    The tie-break above rests on one premise: at a span tie, a LOWER score means
    a LAGGING feed is overwriting an AHEAD one. That premise is true of a
    secondary feed and false of the authority, because a feed cannot lag behind
    ITSELF. When ESPN publishes a run and then takes it back, the second reading
    is not an older observation arriving late — it is the authority's latest
    word, and it is the closest thing to ground truth we have.

    Refusing it does not protect the reader; it PINS THE ERROR. Measured on the
    specimen that failed #6251's after-check (event 15312655, Twins v Yankees,
    2026-09-16, read back out of the append-only `espn_snapshots`):

        02:00:25  Bottom 8th  home 2   <- ESPN publishes a phantom run
        02:01:25  Bottom 8th  home 2
        02:03:25  Bottom 8th  home 1   <- ESPN corrects itself, REFUSED here
        02:04:25  Bottom 8th  home 1      (still refused: same half-inning)
        02:14:25  Top 9th     home 1

    `score_snapshots` carries the 2 at `02:00:25.518390` — the same timestamp to
    the microsecond as the ESPN snapshot, i.e. the same transaction, which is
    how we know ESPN wrote the standing value it was then refused permission to
    correct. ESPN's own mistake lived three minutes. Ours lived nine, and the
    extra six were this guard's doing. That is the whole defect.

    ── WHY EXEMPTING THE AUTHORITY DOES NOT UNWIND THE FIX ──

    The fear is obvious: if the authority may always step down, does it not
    simply follow every flicker, re-opening the 19x collapse #6251 bought? It
    does not, and this is measured rather than argued. Over 2026-09-13 to
    2026-09-16, MLB rows in `espn_snapshots` (append-only, so this is a history
    of writes and not a snapshot of current values):

        262 consecutive pairs across 42 events   <- the probe is not dead
         58 of them at the SAME inning-state     <- the tie population
        152 upward steps                         <- it sees real movement
          1 downward step at a same-inning tie   <- the whole exposure
          0 of those bounced back up             <- it was a correction

    So ESPN does not flicker on MLB scores; it corrects, rarely, and when it
    corrected it was right. This exemption fires about once every three days,
    and on the only occasion it had to fire it would have been correct. The
    population #6251 actually collapsed — 221 same-inning reversions in three
    days — was never this: it was a clockless secondary feed overwriting the
    authority, and that path does not pass this flag and is untouched.

    ── SCOPE ──

    Baseball-only in effect, without a sport check anywhere: the caller reaches
    this line only at a tie on a position that `_position_names_a_span` accepts,
    and the inning ladder is the only such position. A clocked tie never gets
    here. The strictly-earlier rule is above this and is not exempted — an
    authority observation from a genuinely earlier inning is still refused,
    which is the one case where accepting it is provably wrong.

    THE SAMPLE IS THIN AND SAYING SO IS PART OF THE CLAIM. `espn_snapshots` is a
    win-probability capture table, roughly six observations per event, so 58
    same-inning pairs is what three days buys. The direction is unambiguous and
    the control pays, but this is not a 10,000-row result and must not be quoted
    as one.
    """
    return bool(incoming_is_authority)


def live_write_would_revert(
    stored_period: str | None,
    stored_clock: str | None,
    incoming_period: str | None,
    incoming_clock: str | None,
    *,
    stored_home_score: object = None,
    stored_away_score: object = None,
    incoming_home_score: object = None,
    incoming_away_score: object = None,
    incoming_is_authority: bool = False,
) -> bool:
    """Is this incoming live observation from EARLIER in the game than the row?

    ``True`` when both sides are locatable AND the incoming one is strictly
    earlier — the one case where accepting the write is guaranteed to move the
    served state backwards in front of a reader — or, at a tie on a position
    that names a SPAN of game time rather than an instant, when the four scores
    are all readable and the incoming one takes a run off a side (#6251; the
    module note says why a clockless label needs a second discriminator, and why
    scoping it this narrowly is not the monotonic clamp that was rejected).

    Every other case is ``False``: this function's job is to refuse proven
    reversions, not to gatekeep live updates. The four score arguments are
    keyword-only and default to absent, so a caller that does not write scores
    — and therefore cannot revert one — asks the same question it always did.

    ``incoming_is_authority`` exempts the SPAN TIE-BREAK ONLY — see
    `_authority_is_correcting_itself`. It never touches the strictly-earlier
    rule above it.
    """
    incoming = live_progress_position(incoming_period, incoming_clock)
    if incoming is None:
        return False
    stored = live_progress_position(stored_period, stored_clock)
    if stored is None:
        return False
    if incoming < stored:
        return True
    if (
        incoming == stored
        and _position_names_a_span(stored_period)
        and _position_names_a_span(incoming_period)
    ):
        if _authority_is_correcting_itself(incoming_is_authority):
            return False
        return _score_would_regress(
            stored_home_score,
            stored_away_score,
            incoming_home_score,
            incoming_away_score,
        )
    return False
