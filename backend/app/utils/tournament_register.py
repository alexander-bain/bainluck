"""Explicit, versioned tournament registers for player-field events (UX-P130).

A *register* answers one question, written down instead of guessed at request
time: **which market identity feeds this row?**  ``utils/grid_register.py``
established the pattern for championship grids, whose unit is a *team in a
stage*.  This module carries the same doctrine to tournaments whose unit is a
**player in a draw** — the US Open being the first, shipping for main-draw
Sunday 2026-08-30.

Why a second module rather than a wider ``grid_register``: the grid's cell is
``(stage, entity, source)`` and its entity identity comes from the ``teams``
table.  A tennis draw has no teams table to anchor to, its rows carry
draw/seed/draw-slot state a grid cell has no place for, and its daily slate is a
*pair* of registered players sharing one market.  Forking the shape while
**importing the vocabulary** (statuses, terminal results, finding
classification, evidence rules) keeps the two registers saying the same words
about the same situations, which is the part that must not drift.  Nothing here
is wired into the shipped grid path.

The 2026-08-24 US Open census is why every field below exists:

* ``llm_gender`` is ``NULL`` for **all 861,809** rows of ``futures_markets`` —
  the column is dead, so ``draw`` is register-owned and never read from it.
* ``llm_sport_category`` puts **every** US Open singles match market under
  ``table_tennis`` (298 rows for this tournament; 12,766 platform-wide, of which
  **zero** name table tennis), and puts 26 celebrity-attendance markets under
  ``tennis``.  Category is therefore never a membership test.
* Polymarket's men's and women's winner fields each carry an ``Other`` bucket
  pinned at ``probability = 1.000`` since 2026-05-12.  Sorted by probability it
  is the **first row of both boards**.  An aggregate bucket is not a player, so
  it gets no entry and cannot render — see ``INVALID_NON_PLAYER_ENTITY``.
* 15 Kalshi match markets for matches **played on 2026-08-19** are still
  ``status='open'`` with ``resolution_date`` inside US Open week (gotcha #33).
  Any date-window slate query pulls them in; a register keyed on matchups cannot.
* ``futures_outcomes.last_updated`` is not a freshness signal: the Polymarket
  men's field reads ``2026-07-21`` on every outcome while its snapshots ran to
  ``2026-08-10``.  Freshness is read from ``futures_odds_snapshots.captured_at``
  and stored as ``price_observed_at`` — see ``check_freshness``.

Identity only.  No probability, blend, weighting or ordering logic lives here.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from app.utils.grid_register import (
    AMBIGUOUS_FINDINGS as GRID_AMBIGUOUS_FINDINGS,
    REGISTER_STATUSES,
    TERMINAL_RESULTS,
    _HARD_INVALID_PREFIXES,
    is_iso8601,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "tournament-register/v1"

#: Only two sources carry US Open tennis.  Measured 2026-08-24: ``odds_api``
#: holds **zero** tennis futures of any kind, and DataGolf is golf-only, so the
#: blend on this page has exactly two contributors and no sportsbook column.
ALLOWED_SOURCES = ("kalshi", "polymarket")

#: The draws a tournament may have.  Register-owned because ``llm_gender`` is
#: dead (NULL on all 861,809 rows of ``futures_markets``).
#:
#: THE THREE DOUBLES DRAWS ARE HERE AND EMPTY (UX-P139, Alex's item 12):
#: "the measurement lane is cataloging what Polymarket carried for US Open
#: 2025 — build the section to accept those market classes when the catalog
#: lands."  Censused 2026-08-26: **zero** US Open doubles markets exist at
#: either source (3,581 markets platform-wide match "doubles"; none of them
#: this tournament), so nothing in the committed register uses them today.
#:
#: They are listed anyway rather than added later, because the alternative is
#: that the catalog lands and a doubles entry fails ``UNKNOWN_DRAW`` — a
#: population pass blocked on a one-line code change, which is exactly the
#: "deploy on the day" this whole register pattern exists to avoid.  ESPN
#: already carries all three draws' RESULTS under these exact slugs (63 men's,
#: 63 women's, 21 mixed competitions on 2026-08-26), so the results half is
#: live the moment anybody asks for it.
SINGLES_DRAWS = ("mens-singles", "womens-singles")
DOUBLES_DRAWS = ("mens-doubles", "womens-doubles", "mixed-doubles")
DRAWS = (*SINGLES_DRAWS, *DOUBLES_DRAWS)

#: Rounds, qualifying through the final.  ``qualifying`` is one bucket rather
#: than Q1/Q2/Q3 because the sources do not distinguish them by name.
ROUNDS = ("qualifying", "R128", "R64", "R32", "R16", "QF", "SF", "F")

#: **Contenders and participants are different sets** — the design consequence
#: the Day-1 census stated and this field enforces (UX-P132).
#:
#: v1 was seeded from the two outright winner fields: 80 *contenders*, exactly
#: right for the championship boards.  The daily slate's players are the
#: *qualifying draw*, and most of them will never appear in an outright field,
#: so every qualifying matchup failed ``MATCHUP_PLAYER_NOT_REGISTERED``.  The
#: fix is not to loosen that rule — it is the rule that keeps a stale Cincinnati
#: market off the slate — but to register the participants too.
#:
#: The role is what stops the second population pass from contaminating the
#: first.  A qualifier's only priceable identity is a *match* market, and a
#: match probability is P(wins this match), not P(wins the tournament).  Without
#: this split, populating the slate would have put "Diego Dedura-Palomero 54%"
#: on the men's championship board, above Alcaraz, sourced from a first-round
#: qualifying quote.  Boards read ``board_players``; participants are invisible
#: to them by construction rather than by a filter somebody has to remember.
PLAYER_ROLES = ("contender", "participant")

#: Absent ``role`` reads as ``contender``, so v1 registers stay valid and keep
#: rendering exactly as they did.
DEFAULT_PLAYER_ROLE = "contender"

#: What KIND of question a pinned identity answers.  ``outright`` is "wins the
#: tournament"; ``match`` is "wins this match"; ``reach`` is "gets as far as
#: round R".  The three must never be blended or ranked against each other —
#: they are different questions that happen to share a unit.
SOURCE_KINDS = ("outright", "match", "reach")
DEFAULT_SOURCE_KIND = "outright"

REQUIRED_REGISTER_FIELDS = frozenset(
    {"schema_version", "tournament", "season", "version", "generated_at",
     "draw_released", "players", "matchups"}
)

#: THE REACH CELL (UX-P139, Alex's amendment to ruling 3).
#:
#: "A blank cell, an improperly blended cell, or a cell populated from the WRONG
#: future is a linkage defect — no excuse, no interpolation. The derived-value
#: fallback is retired: a cell whose direct markets are not linked renders as an
#: ALARM STATE naming the missing linkage ... The register carries per-player
#: per-round market IDs from BOTH sources; the grid reads only the register."
#:
#: So the playoff grid's unit gets its own collection, keyed
#: ``(draw, entity_key, round)``, with one source block per source exactly like
#: a player entry.  Three consequences follow structurally rather than by
#: convention:
#:
#: 1. **The grid cannot read anything else.**  ``build_playoff_grid`` walks
#:    ``reaches`` and nothing else, so there is no path by which a match price,
#:    a chained product, or a curated prop could land in a reach cell.
#: 2. **Wrong-future placement is caught in the FILE**, not at render time.  A
#:    block restates the question it was pinned from — ``question_round``,
#:    ``question_draw``, ``question_subject`` — and validation asserts all three
#:    agree with the cell.  A reach-QF market wired into the SF cell is
#:    ``REACH_ROUND_MISMATCH``, a structural finding that refuses the register.
#: 3. **"No market" is a written-down census result, not an absence.**  A cell
#:    both sources were censused for and neither carries gets a ``missing``
#:    block per source with its own evidence timestamp.  That is materially
#:    different from a cell nobody looked at, which the grid renders as an
#:    alarm — see ``tournament_grid.CELL_UNREGISTERED``.
REQUIRED_REACH_FIELDS = frozenset({"draw", "entity_key", "round", "sources"})

#: A reach block must restate the question its identity was pinned from. These
#: are what make ruling-3's "wrong future" a validation failure instead of a
#: thing a reader might notice.
REQUIRED_REACH_QUESTION_FIELDS = ("question_round", "question_draw", "question_subject")

#: Curated props and futures (UX-P132, Alex's item 5): "beyond the two winner
#: markets and today's matches, surface a section of interesting tournament
#: props/futures — curated, not a dump."
#:
#: The curation lives HERE, in the committed file, for the same reason every
#: other row on this page does: a market not in the register does not render.
#: That makes "curated, not a dump" a structural property rather than a
#: promise — there is no code path that could surface an uncurated market,
#: because the page never asks the database what exists.
#:
#: Optional. A register with no ``props`` key is valid and renders an honest
#: empty section, which is the state until a population pass runs.
REQUIRED_PROP_FIELDS = frozenset({"key", "title", "source", "outcomes"})

#: Where to watch (UX-P132, Alex's item 4). A static per-tournament mapping is
#: explicitly acceptable for v1. It is register-owned rather than hardcoded in
#: the route so it travels with the tournament and can be corrected without a
#: deploy — the same reason every other fact on this page lives in the file.
REQUIRED_BROADCAST_FIELDS = frozenset({"region", "channels"})
REQUIRED_PLAYER_FIELDS = frozenset({"entity_key", "display_name", "draw", "sources"})
REQUIRED_MATCHUP_FIELDS = frozenset(
    {"matchup_key", "draw", "round", "scheduled_date", "players", "sources"}
)
REQUIRED_SOURCE_FIELDS = frozenset({"source", "status", "evidence"})

#: Where committed registers live: ``backend/data/tournament_registers/<t>-<season>.json``.
REGISTER_DIR = Path(__file__).resolve().parents[2] / "data" / "tournament_registers"

#: A live row whose price is older than this must not render as live.  The
#: census measured 34 days on the highest-liquidity market of the tournament, so
#: this bound is the difference between an honest empty board and a board of
#: month-old numbers presented as today's.
STALE_PRICE_HOURS = 6.0

#: Names that are aggregate buckets, not players.  Registering one would let a
#: 100%-pinned bucket lead a board (the measured Polymarket case).
NON_PLAYER_NAMES = frozenset({
    "other", "others", "any other", "field", "the field", "any other player",
    "no winner", "none of the above", "any other man", "any other woman",
})

#: Drift that means "a number would be shown that must not be" — same posture as
#: ``grid_register.RENDER_FINDINGS``: the register may be well-formed and the
#: release still blocked.
FRESHNESS_FINDINGS = frozenset({"LIVE_PRICE_STALE", "LIVE_PRICE_NEVER_OBSERVED"})

RENDER_FINDINGS = frozenset({
    "MISSING_RENDERED_AS_PROBABILITY",
    "SETTLED_RENDERED_AS_LIVE",
    "LIVE_RENDER_NOT_NUMERIC",
    "LIVE_PROBABILITY_OUT_OF_RANGE",
    "UNREGISTERED_RENDER_ROW",
    "POISON_RENDER_ROW",
    "RENDERED_WRONG_SHAPE",
}) | FRESHNESS_FINDINGS

UNAMBIGUOUS_FINDINGS = frozenset({
    "UNAMBIGUOUS_RENAME_DRIFT",
    "UNAMBIGUOUS_SETTLEMENT_DRIFT",
})

#: Ambiguity the grid register never had to name.  ``SETTLEMENT_WITHOUT_RESULT``
#: is gotcha #33's shape at the register boundary: the source says the market is
#: over but no winner is knowable, so neither "keep rendering it live" nor "grade
#: it" is safe.  Without this entry it fell through ``classify`` to ``clean`` —
#: the board would have kept printing a live probability for a finished match
#: and nobody would have been told.  A finding that is emitted but classified by
#: nothing is worse than no finding at all: it reads as green.
#: ``CANDIDATES_WRONG_SHAPE`` joins it for the same reason: the sentinel was
#: handed something it cannot compare against, so "no drift found" would be a
#: statement about the harness, not about the register.
AMBIGUOUS_FINDINGS = GRID_AMBIGUOUS_FINDINGS | {
    "SETTLEMENT_WITHOUT_RESULT",
    "CANDIDATES_WRONG_SHAPE",
}

#: Structural findings that ``_HARD_INVALID_PREFIXES`` does not spell.
#:
#: Prefix-matching is a naming convention doing a classifier's job: a finding is
#: severe because of what it means, and a name that happens not to start with
#: ``INVALID_`` silently becomes ``clean``.  Every entry below is emitted by a
#: validator, reaches ``classify``, and read as clean before this set existed —
#: a malformed matchup would have published.  Names are kept identical to
#: ``grid_register``'s on purpose so findings stay greppable across both
#: registers; the classification is made explicit here instead.
#:
#: The same hole is live in ``grid_register`` itself (#2198).
STRUCTURAL_FINDINGS = frozenset({
    "MAPPED_ENTRY_MISSING_IDENTITY",
    "MISSING_ENTRY_HAS_IDENTITY",
    "SETTLED_WITHOUT_RESULT",
    "MATCHUP_NOT_A_PAIR",
    "MATCHUP_PLAYER_NOT_REGISTERED",
    "MATCHUP_PLAYER_REPEATED",
    "MATCHUP_SIDES_MISMATCH",
    "MATCHUP_SIDE_MISSING_IDENTITY",
    # Both sides of a match reading the SAME outcome id renders one quote as
    # two players and makes the pair sum to 2x — the shape a normalizer would
    # then "fix" into a plausible 50/50. Structural, so it is rejected before
    # any display rule gets a chance to launder it.
    "MATCHUP_SIDES_SHARE_OUTCOME",
    # A matchup pointing at something that is not an events row id. Structural
    # because the consequence is a link to a 404, which reads as a broken page.
    "INVALID_MATCHUP_EVENT_ID",
    # One outcome feeding two different matchups: the same quote presented as
    # two separate matches. Registry-level, so validate_matchup cannot see it.
    "MATCHUP_IDENTITY_REUSED",
    # A curated prop whose outcomes cannot be priced, or whose two outcomes are
    # one quote read twice. Listed explicitly rather than relying on a name
    # prefix — which is the hole this whole set exists to close.
    "PROP_OUTCOME_MISSING_IDENTITY",
    "PROP_OUTCOME_REUSED",
    # Two outcomes both claiming to answer the question. The card prints one
    # number, so a second claimant means the register cannot say which — and
    # whichever the renderer picked would be arbitrary. Structural for the same
    # reason as the sides rules: it is an identity ambiguity, not a display
    # preference, and a display rule would launder it into a plausible answer.
    "PROP_MULTIPLE_ANSWERS",
    # "Where to watch:" with nothing after it. Small, and still a promise the
    # page cannot keep.
    "BROADCAST_NO_CHANNELS",
    # ── THE REACH CELL (UX-P139) ────────────────────────────────────────────
    # Alex: "wrong-future placement (a reach-QF market feeding the SF cell) is
    # a named eval failure, not a data quirk." Named here, structurally, so the
    # register is REFUSED rather than served with a plausible number in the
    # wrong column. All three mismatches are the same class — the identity
    # answers a different question than the cell asks — and the class is
    # exactly the one the grid register was built to kill (83% of golf cells
    # fed by the wrong tournament's market, 2026-08-01 baseline census).
    "REACH_ROUND_MISMATCH",
    "REACH_DRAW_MISMATCH",
    "REACH_SUBJECT_MISMATCH",
    # A cell naming a player the register does not carry, or two cells for one
    # (draw, player, round), or one outcome backing two cells. Same reasoning
    # as their matchup counterparts.
    "REACH_PLAYER_NOT_REGISTERED",
    "REACH_PLAYER_WRONG_DRAW",
    "DUPLICATE_REACH_CELL",
    "REACH_IDENTITY_REUSED",
    "DUPLICATE_SOURCE_FOR_REACH",
    # A reach block pinned as an outright or a match quote. P(wins the title)
    # rendered in the "reaches the semis" column is the ruling-3 defect with a
    # different label on it.
    "REACH_SOURCE_WRONG_KIND",
    # A reach cell with no source blocks at all is not a census result. The
    # honest "neither source carries this" is TWO `missing` blocks with
    # evidence; an empty list is a cell nobody looked at, and it must not be
    # mistaken for one that was cleared.
    "REACH_NO_SOURCES",
    "REACH_BLOCK_MISSING_QUESTION",
    # ── THE PLAYER IMAGE (UX-P142, Alex's ruling 8) ─────────────────────────
    # A face is an identity claim, and it is the one claim a reader checks
    # instantly and trusts absolutely. The bare-name Wikipedia lookup this repo
    # already uses for fighters returned a SERBIAN FOOTBALLER for the tennis
    # player Aleksandar Kovacevic (measured 2026-08-27), with a photo, at 200.
    # So an image is pinned like every other identity here — decided once,
    # offline, against evidence — and a block that cannot show its work is
    # refused rather than rendered.
    "PLAYER_IMAGE_WRONG_SHAPE",
    "PLAYER_IMAGE_NOT_VERIFIED",
    "PLAYER_IMAGE_BAD_URL",
})

#: Image URL prefixes a register may pin.  An allowlist rather than a scheme
#: check: the page renders these into an ``<img src>``, and "https" is not a
#: provenance claim.  Both hosts are already reached by the app elsewhere
#: (``lib/images.ts`` for Wikipedia thumbnails, ESPN's CDN for every team logo).
ALLOWED_IMAGE_PREFIXES = (
    "https://upload.wikimedia.org/",
    "https://a.espncdn.com/",
)

#: Findings from ``validate_transition`` only.  These never reach ``classify``:
#: they gate publication through its ``transition_ok`` argument, because they
#: describe the *move* from one version to the next, not the register itself.
TRANSITION_ONLY_FINDINGS = frozenset({
    "NON_MONOTONIC_VERSION",
    "MISSING_SUPERSEDES_LINK",
    "TRANSITION_CHANGED_SCOPE",
    "INVALID_DRAW_RELEASED_UNLATCH",
})


def normalize_player_name(name: Any) -> str:
    """Collapse a source's spelling to a comparison key.

    Spaces are dropped, not merely punctuation.  The census specimen: Kalshi
    writes ``Felix Auger-Aliassime`` and Polymarket writes ``Felix Auger
    Aliassime``.  Under a punctuation-only normalizer those are two keys, and
    the 11th-most-likely man in the men's draw renders as **two board rows**.
    Dropping spaces joins them; 19 of the men's field's 37 union rows then carry
    both sources instead of 18.
    """
    if not isinstance(name, str):
        return ""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def is_non_player(name: Any) -> bool:
    """Whether ``name`` is an aggregate bucket rather than a competitor."""
    if not isinstance(name, str):
        return False
    return name.strip().lower() in NON_PLAYER_NAMES


def player_role(player: Any) -> str:
    """A player's role, defaulting to ``contender`` when absent.

    Read through this helper everywhere rather than ``player["role"]``: v1
    registers have no ``role`` key at all, and a ``KeyError`` — or worse, a
    ``.get("role")`` returning ``None`` that then compares unequal to
    ``"contender"`` — would silently empty the championship boards.
    """
    if not isinstance(player, dict):
        return DEFAULT_PLAYER_ROLE
    role = player.get("role")
    return role if isinstance(role, str) and role else DEFAULT_PLAYER_ROLE


def source_kind(block: Any) -> str:
    """A source block's kind, defaulting to ``outright``.  Same reason as above."""
    if not isinstance(block, dict):
        return DEFAULT_SOURCE_KIND
    kind = block.get("kind")
    return kind if isinstance(kind, str) and kind else DEFAULT_SOURCE_KIND


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_source_entry(entry: Any, *, sources: set[str]) -> list[str]:
    """Validate one per-source identity block.  Returns finding codes."""
    if not isinstance(entry, dict):
        return ["REGISTER_SOURCE_WRONG_SHAPE"]
    if REQUIRED_SOURCE_FIELDS - entry.keys():
        return ["REGISTER_SOURCE_MISSING_FIELDS"]

    findings: list[str] = []
    if entry["source"] not in sources:
        findings.append("UNKNOWN_SOURCE")
    if entry["status"] not in REGISTER_STATUSES:
        findings.append("UNKNOWN_REGISTER_STATUS")
    if source_kind(entry) not in SOURCE_KINDS:
        findings.append("UNKNOWN_SOURCE_KIND")

    evidence = entry.get("evidence")
    if (
        not isinstance(evidence, dict)
        or not evidence.get("kind")
        or not is_iso8601(evidence.get("observed_at"))
    ):
        findings.append("INVALID_EVIDENCE")

    if entry["status"] == "missing":
        # A missing source must not keep a stale identity — that is how a
        # delisted market keeps rendering last week's number.
        if entry.get("market_id") is not None or entry.get("outcome_id") is not None:
            findings.append("MISSING_ENTRY_HAS_IDENTITY")
    elif entry.get("market_id") is None or entry.get("outcome_id") is None:
        findings.append("MAPPED_ENTRY_MISSING_IDENTITY")

    if entry["status"] == "settled" and entry.get("terminal_result") not in TERMINAL_RESULTS:
        findings.append("SETTLED_WITHOUT_RESULT")

    if entry.get("price_observed_at") is not None and not is_iso8601(entry["price_observed_at"]):
        findings.append("INVALID_PRICE_OBSERVED_AT")

    return findings


def validate_player(player: Any, *, draw_released: bool, sources: set[str]) -> list[str]:
    """Validate one player entry.  Returns finding codes (empty == clean)."""
    if not isinstance(player, dict):
        return ["REGISTER_PLAYER_WRONG_SHAPE"]
    if REQUIRED_PLAYER_FIELDS - player.keys():
        return ["REGISTER_PLAYER_MISSING_FIELDS"]

    findings: list[str] = []
    if player["draw"] not in DRAWS:
        findings.append("UNKNOWN_DRAW")
    if is_non_player(player.get("display_name")) or is_non_player(player.get("entity_key")):
        findings.append("INVALID_NON_PLAYER_ENTITY")

    role = player_role(player)
    if role not in PLAYER_ROLES:
        findings.append("INVALID_PLAYER_ROLE")

    seed = player.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool) or not 1 <= seed <= 32):
        findings.append("INVALID_SEED")

    slot = player.get("draw_slot")
    if slot is not None:
        # Before the ceremony there is no draw, so a slot is a guess wearing the
        # authority of a fact.  Empty-until-released is enforced, not documented.
        if not draw_released:
            findings.append("INVALID_DRAW_SLOT_BEFORE_RELEASE")
        elif not isinstance(slot, int) or isinstance(slot, bool) or not 1 <= slot <= 128:
            findings.append("INVALID_DRAW_SLOT")

    findings.extend(validate_player_image(player.get("image")))

    source_blocks = player.get("sources")
    if not isinstance(source_blocks, list):
        findings.append("REGISTER_PLAYER_NO_SOURCES")
        return findings

    if role == "participant":
        # A participant's only priceable identity is the matchup's `sides`. If
        # one carries a player-level source block it is a contender that was
        # labelled wrongly, and it would be invisible to the board it belongs
        # on — a silent omission, which is the failure mode a register exists
        # to make impossible.
        if source_blocks:
            findings.append("INVALID_PARTICIPANT_SOURCES")
    elif not source_blocks:
        findings.append("REGISTER_PLAYER_NO_SOURCES")
        return findings

    seen_sources: set[str] = set()
    for block in source_blocks:
        findings.extend(validate_source_entry(block, sources=sources))
        if isinstance(block, dict):
            name = block.get("source")
            if name in seen_sources:
                findings.append("DUPLICATE_SOURCE_FOR_PLAYER")
            seen_sources.add(name)
            if source_kind(block) != "outright":
                # A match quote on a contender's player entry would reach the
                # championship board through `build_boards` and be blended with
                # outright prices — P(wins this match) averaged into P(wins the
                # tournament). Different questions, one number, silently wrong.
                findings.append("INVALID_MATCH_SOURCE_ON_PLAYER")

    return findings


def player_image(player: Any) -> Optional[dict[str, Any]]:
    """The two URLs a surface may render for one player, or ``None``.

    Lives here rather than on either consumer because BOTH the board and the
    slate render a player and neither may import the other (the slate already
    imports the board).  It also keeps one answer to "what does a page get to
    see": the register's ``image`` block carries its evidence and its
    verification flag, and neither is shipped — a client handed the evidence is
    a client invited to re-decide whether the picture is of the right person,
    and that decision was made offline precisely so it is not made at render
    time.
    """
    if not isinstance(player, dict):
        return None
    image = player.get("image")
    if not isinstance(image, dict):
        return None
    url = image.get("url")
    flag_url = image.get("flag_url")
    if not url and not flag_url:
        return None
    return {"url": url or None, "flag_url": flag_url or None}


def validate_player_image(image: Any) -> list[str]:
    """Validate a player's pinned image block (UX-P142, Alex's ruling 8).

    Three things are checked, and the middle one is the reason this exists.

    1. **Shape.** A dict with a URL string, or nothing.
    2. **VERIFICATION.** ``verified_subject`` must be true.  The census that
       fills this field reads the source's own description of who the picture
       is OF and refuses anything that is not a tennis player — because a
       bare-name lookup that returns the wrong person returns it with a photo
       and a 200, which is indistinguishable from success at the render.  A
       block that does not carry the check is not a block that passed it.
    3. **Host.** ``ALLOWED_IMAGE_PREFIXES`` — see the note there.

    A flag is NOT held to (2): a country flag is a claim about a country, the
    country comes from the same ESPN record as the name, and there is no
    wrong-person failure mode to guard against.
    """
    if image is None:
        return []
    if not isinstance(image, dict):
        return ["PLAYER_IMAGE_WRONG_SHAPE"]

    findings: list[str] = []
    url = image.get("url")
    flag_url = image.get("flag_url")
    if url is None and flag_url is None:
        # An empty block is a census result — "we looked and found nothing" —
        # and it must carry its evidence like every other censused absence.
        if not isinstance(image.get("evidence"), dict):
            findings.append("PLAYER_IMAGE_WRONG_SHAPE")
        return findings

    for candidate in (url, flag_url):
        if candidate is None:
            continue
        if not isinstance(candidate, str) or not candidate.startswith(
            ALLOWED_IMAGE_PREFIXES
        ):
            findings.append("PLAYER_IMAGE_BAD_URL")

    if url is not None and image.get("verified_subject") is not True:
        findings.append("PLAYER_IMAGE_NOT_VERIFIED")
    if not isinstance(image.get("evidence"), dict):
        findings.append("PLAYER_IMAGE_WRONG_SHAPE")
    return findings


def validate_matchup(matchup: Any, *, entity_keys: set[str], sources: set[str]) -> list[str]:
    """Validate one daily-slate matchup entry."""
    if not isinstance(matchup, dict):
        return ["REGISTER_MATCHUP_WRONG_SHAPE"]
    if REQUIRED_MATCHUP_FIELDS - matchup.keys():
        return ["REGISTER_MATCHUP_MISSING_FIELDS"]

    findings: list[str] = []
    if matchup["draw"] not in DRAWS:
        findings.append("UNKNOWN_DRAW")
    if matchup["round"] not in ROUNDS:
        findings.append("UNKNOWN_ROUND")
    # OUR `events.id`, optional (UX-P139, Alex's item 7). Register-owned so the
    # click-through is pinned rather than name-matched at render time. Typed
    # here because a string id would render `/events/undefined`, which is a
    # 404 the reader reads as a broken page rather than as a missing link.
    event_id = matchup.get("event_id")
    if event_id is not None and (
        not isinstance(event_id, int) or isinstance(event_id, bool) or event_id <= 0
    ):
        findings.append("INVALID_MATCHUP_EVENT_ID")
    if not is_iso8601(matchup.get("scheduled_date")):
        findings.append("INVALID_SCHEDULED_DATE")

    players = matchup.get("players")
    if not isinstance(players, list) or len(players) != 2:
        findings.append("MATCHUP_NOT_A_PAIR")
    else:
        # A matchup may only name players the register already carries.  This is
        # what keeps a stale Cincinnati market from becoming a slate row: it has
        # no matchup entry, and it could not get one without both players.
        for key in players:
            if key not in entity_keys:
                findings.append("MATCHUP_PLAYER_NOT_REGISTERED")
        if players[0] == players[1]:
            findings.append("MATCHUP_PLAYER_REPEATED")

    source_blocks = matchup.get("sources")
    if not isinstance(source_blocks, list) or not source_blocks:
        findings.append("REGISTER_MATCHUP_NO_SOURCES")
        return findings

    for block in source_blocks:
        if not isinstance(block, dict):
            findings.append("REGISTER_SOURCE_WRONG_SHAPE")
            continue
        findings.extend(validate_source_entry(block, sources=sources))
        if block.get("status") == "missing":
            continue
        sides = block.get("sides")
        if not isinstance(sides, dict) or set(sides) != set(players if isinstance(players, list) else []):
            findings.append("MATCHUP_SIDES_MISMATCH")
            continue

        side_outcomes: list[Any] = []
        for side in sides.values():
            if not isinstance(side, dict) or side.get("outcome_id") is None:
                findings.append("MATCHUP_SIDE_MISSING_IDENTITY")
                continue
            side_outcomes.append(side["outcome_id"])
        if len(side_outcomes) == 2 and side_outcomes[0] == side_outcomes[1]:
            findings.append("MATCHUP_SIDES_SHARE_OUTCOME")

    return findings


def validate_prop(prop: Any, *, sources: set[str]) -> list[str]:
    """Validate one curated prop/futures entry."""
    if not isinstance(prop, dict):
        return ["REGISTER_PROP_WRONG_SHAPE"]
    if REQUIRED_PROP_FIELDS - prop.keys():
        return ["REGISTER_PROP_MISSING_FIELDS"]

    findings: list[str] = []
    if prop["source"] not in sources:
        findings.append("UNKNOWN_SOURCE")
    draw = prop.get("draw")
    if draw is not None and draw not in DRAWS:
        findings.append("UNKNOWN_DRAW")

    outcomes = prop.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        findings.append("REGISTER_PROP_NO_OUTCOMES")
        return findings

    seen: set[Any] = set()
    answers: list[Any] = []
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            findings.append("REGISTER_PROP_OUTCOME_WRONG_SHAPE")
            continue
        if not outcome.get("entity_key") or not outcome.get("display_name"):
            findings.append("PROP_OUTCOME_MISSING_IDENTITY")
        if outcome.get("is_answer") is True:
            answers.append(outcome.get("entity_key"))
        outcome_id = outcome.get("outcome_id")
        if outcome_id is None:
            findings.append("PROP_OUTCOME_MISSING_IDENTITY")
            continue
        if outcome_id in seen:
            # One quote rendered as two outcomes of the same question.
            findings.append("PROP_OUTCOME_REUSED")
        seen.add(outcome_id)

    # THE ANSWER RULE (UX-P134). A prop card prints one big number under a
    # question, so something has to decide WHICH outcome that number is. The
    # renderer used to take the highest-probability outcome, and the census
    # that populated this section proved how badly that fails: under "Can
    # Sinner complete the calendar slam?" the market's own outcomes are the
    # threshold ladder 1+/2+/3+, and the max is "1+ Grand Slam wins" at 99% —
    # so the card would have printed **99%** under a question whose true
    # answer, "All 4", is 1%. Not a rounding error; the opposite answer.
    #
    # So the answering outcome is NAMED in the register, offline, by the agent
    # who curated the question — the same doctrine as the matchup sides
    # mapping, and for the same reason: an identity decision made once against
    # the evidence beats a request-time heuristic that is admittedly wrong.
    # A field market where no single outcome answers the question marks none,
    # and the renderer shows a ranked list instead of a headline number.
    if len(answers) > 1:
        findings.append("PROP_MULTIPLE_ANSWERS")

    return findings


def validate_reach(
    reach: Any,
    *,
    players_by_key: dict[str, dict[str, Any]],
    sources: set[str],
) -> list[str]:
    """Validate one player x round reach cell (UX-P139).

    The three ``question_*`` assertions are the whole point of this function.
    Every other register entry is validated for *shape*; a reach block is
    validated for **agreement with its own subject matter**, because the defect
    Alex's amendment names — a reach-QF market feeding the SF cell — is
    perfectly well-shaped.  It renders a real price, from a real market, under
    the wrong question, and nothing downstream can tell.

    So the block carries the question it came from, in the source's own terms,
    and this function asserts the cell and the question describe the same
    (player, round, draw).  Restating is not redundancy: it is the only way the
    disagreement has somewhere to show up.
    """
    if not isinstance(reach, dict):
        return ["REGISTER_REACH_WRONG_SHAPE"]
    if REQUIRED_REACH_FIELDS - reach.keys():
        return ["REGISTER_REACH_MISSING_FIELDS"]

    findings: list[str] = []
    draw = reach["draw"]
    entity_key = reach["entity_key"]
    round_name = reach["round"]

    if draw not in DRAWS:
        findings.append("UNKNOWN_DRAW")
    if round_name not in ROUNDS:
        findings.append("UNKNOWN_ROUND")

    player = players_by_key.get(entity_key)
    if player is None:
        # Same rule as a matchup's: a cell may only name a player the register
        # already carries. It is what keeps a market for some other event's
        # "Alcaraz" from becoming a row on this grid.
        findings.append("REACH_PLAYER_NOT_REGISTERED")
    elif player.get("draw") != draw:
        findings.append("REACH_PLAYER_WRONG_DRAW")

    blocks = reach.get("sources")
    if not isinstance(blocks, list) or not blocks:
        findings.append("REACH_NO_SOURCES")
        return findings

    seen_sources: set[Any] = set()
    for block in blocks:
        if not isinstance(block, dict):
            findings.append("REGISTER_SOURCE_WRONG_SHAPE")
            continue
        findings.extend(validate_source_entry(block, sources=sources))

        name = block.get("source")
        if name in seen_sources:
            findings.append("DUPLICATE_SOURCE_FOR_REACH")
        seen_sources.add(name)

        if source_kind(block) != "reach":
            findings.append("REACH_SOURCE_WRONG_KIND")

        if block.get("status") == "missing":
            # A censused absence carries no question to agree with — there is
            # no market. Its `evidence.observed_at` (checked by
            # `validate_source_entry`) is what makes it a RESULT rather than a
            # gap, and that is all this cell can honestly claim.
            continue

        if any(block.get(field) in (None, "") for field in REQUIRED_REACH_QUESTION_FIELDS):
            findings.append("REACH_BLOCK_MISSING_QUESTION")
            continue

        # ── THE WRONG-FUTURE EVAL ──────────────────────────────────────────
        if block.get("question_round") != round_name:
            findings.append("REACH_ROUND_MISMATCH")
        if block.get("question_draw") != draw:
            findings.append("REACH_DRAW_MISMATCH")
        if player is not None:
            subject = normalize_player_name(block.get("question_subject"))
            if subject != normalize_player_name(player.get("display_name")):
                findings.append("REACH_SUBJECT_MISMATCH")

    return findings


def validate_broadcasts(broadcasts: Any) -> list[str]:
    """Validate the where-to-watch mapping.  Absent is valid."""
    if broadcasts is None:
        return []
    if not isinstance(broadcasts, list):
        return ["REGISTER_BROADCASTS_WRONG_SHAPE"]

    findings: list[str] = []
    for entry in broadcasts:
        if not isinstance(entry, dict) or REQUIRED_BROADCAST_FIELDS - entry.keys():
            findings.append("REGISTER_BROADCAST_MISSING_FIELDS")
            continue
        channels = entry.get("channels")
        if not isinstance(channels, list) or not channels:
            findings.append("BROADCAST_NO_CHANNELS")
        elif any(not isinstance(c, str) or not c.strip() for c in channels):
            findings.append("BROADCAST_NO_CHANNELS")
    return findings


def validate_register(register: Any, contract: dict[str, Any]) -> list[str]:
    """Validate a whole tournament register.  Returns sorted unique findings."""
    if not isinstance(register, dict):
        return ["REGISTER_WRONG_SHAPE"]
    if REQUIRED_REGISTER_FIELDS - register.keys():
        return ["REGISTER_MISSING_FIELDS"]

    spec = contract.get("tournament_contracts", {}).get(register.get("tournament"))
    if not spec:
        return ["UNKNOWN_TOURNAMENT"]

    findings: list[str] = []
    if register.get("schema_version") != contract.get("register_schema_version"):
        findings.append("REGISTER_SCHEMA_MISMATCH")
    if register.get("season") != spec.get("season"):
        findings.append("REGISTER_SEASON_MISMATCH")
    if not isinstance(register.get("version"), int) or register["version"] < 1:
        findings.append("INVALID_REGISTER_VERSION")
    if not is_iso8601(register.get("generated_at")):
        findings.append("INVALID_GENERATED_AT")
    if not isinstance(register.get("draw_released"), bool):
        findings.append("INVALID_DRAW_RELEASED")

    players = register.get("players")
    matchups = register.get("matchups")
    if not isinstance(players, list) or not isinstance(matchups, list):
        return sorted(set(findings + ["REGISTER_COLLECTIONS_WRONG_SHAPE"]))

    draw_released = register.get("draw_released") is True
    sources = set(contract.get("allowed_sources", ()))

    entity_keys: set[str] = set()
    slots: set[tuple] = set()
    name_keys: dict[tuple, str] = {}
    identities: dict[tuple, str] = {}

    for player in players:
        findings.extend(validate_player(player, draw_released=draw_released, sources=sources))
        if not isinstance(player, dict) or not REQUIRED_PLAYER_FIELDS <= player.keys():
            continue

        key = player["entity_key"]
        if key in entity_keys:
            findings.append("DUPLICATE_ENTITY_KEY")
        entity_keys.add(key)

        # Two entity_keys normalizing to one name is the two-rows-for-one-player
        # defect stated as a rule instead of hoped away.
        nkey = (player["draw"], normalize_player_name(player.get("display_name")))
        prior = name_keys.get(nkey)
        if prior is not None and prior != key:
            findings.append("DUPLICATE_PLAYER_ACROSS_KEYS")
        name_keys[nkey] = key

        slot = player.get("draw_slot")
        if slot is not None:
            cell = (player["draw"], slot)
            if cell in slots:
                findings.append("DUPLICATE_DRAW_SLOT")
            slots.add(cell)

        for block in player.get("sources") or []:
            if not isinstance(block, dict) or block.get("status") == "missing":
                continue
            identity = (block.get("source"), block.get("market_id"), block.get("outcome_id"))
            if None in identity:
                continue
            owner = identities.get(identity)
            if owner is not None and owner != key:
                findings.append("IDENTITY_REUSED_ACROSS_PLAYERS")
            identities[identity] = key

    matchup_keys: set[str] = set()
    matchup_identities: dict[tuple, str] = {}
    for matchup in matchups:
        findings.extend(validate_matchup(matchup, entity_keys=entity_keys, sources=sources))
        if not isinstance(matchup, dict) or "matchup_key" not in matchup:
            continue
        if matchup["matchup_key"] in matchup_keys:
            findings.append("DUPLICATE_MATCHUP_KEY")
        matchup_keys.add(matchup["matchup_key"])

        # One outcome id may back exactly one slate row. Two matchups sharing a
        # side is one quote rendered as two matches — visible to nobody, since
        # both rows look individually plausible.
        for block in matchup.get("sources") or []:
            if not isinstance(block, dict) or block.get("status") == "missing":
                continue
            for side in (block.get("sides") or {}).values():
                if not isinstance(side, dict) or side.get("outcome_id") is None:
                    continue
                identity = (block.get("source"), side["outcome_id"])
                owner = matchup_identities.get(identity)
                if owner is not None and owner != matchup["matchup_key"]:
                    findings.append("MATCHUP_IDENTITY_REUSED")
                matchup_identities[identity] = matchup["matchup_key"]

    # ── REACH CELLS (UX-P139) ───────────────────────────────────────────────
    # `players_by_key` is built from the loop above rather than re-scanned, so
    # a cell can only name a player that survived player validation.
    players_by_key = {
        p["entity_key"]: p
        for p in players
        if isinstance(p, dict) and isinstance(p.get("entity_key"), str)
    }
    reach_cells: set[tuple] = set()
    reach_identities: dict[tuple, tuple] = {}
    for reach in register.get("reaches") or []:
        findings.extend(
            validate_reach(reach, players_by_key=players_by_key, sources=sources)
        )
        if not isinstance(reach, dict) or REQUIRED_REACH_FIELDS - reach.keys():
            continue

        cell = (reach["draw"], reach["entity_key"], reach["round"])
        if cell in reach_cells:
            # Two rows for one cell means the generator could not decide which
            # market backs it — and whichever the grid read first would be
            # arbitrary. Exactly the ambiguity the register exists to remove.
            findings.append("DUPLICATE_REACH_CELL")
        reach_cells.add(cell)

        for block in reach.get("sources") or []:
            if not isinstance(block, dict) or block.get("status") == "missing":
                continue
            identity = (block.get("source"), block.get("market_id"), block.get("outcome_id"))
            if None in identity:
                continue
            owner = reach_identities.get(identity)
            if owner is not None and owner != cell:
                # One quote feeding two cells: the same number printed twice
                # under two different questions, both individually plausible.
                findings.append("REACH_IDENTITY_REUSED")
            reach_identities[identity] = cell

    prop_keys: set[str] = set()
    for prop in register.get("props") or []:
        findings.extend(validate_prop(prop, sources=sources))
        if isinstance(prop, dict) and prop.get("key"):
            if prop["key"] in prop_keys:
                findings.append("DUPLICATE_PROP_KEY")
            prop_keys.add(prop["key"])

    findings.extend(validate_broadcasts(register.get("broadcasts")))

    return sorted(set(findings))


def classify(findings: list[str], *, transition_ok: bool | None = None) -> dict[str, Any]:
    """Map finding codes to ``(classification, action, publish)``.

    Deliberately the same order and the same words as
    ``grid_register.classify``: structurally invalid is rejected outright,
    ambiguity is routed to a human before any render concern, a render or
    freshness breach blocks release even when the register itself is
    well-formed, and only then may unambiguous drift publish.
    """
    hard_invalid = any(
        f.startswith(_HARD_INVALID_PREFIXES) or f in STRUCTURAL_FINDINGS for f in findings
    )
    ambiguous = any(f in AMBIGUOUS_FINDINGS for f in findings)
    unambiguous = any(f in UNAMBIGUOUS_FINDINGS for f in findings)
    render_bad = any(f in RENDER_FINDINGS for f in findings)

    if hard_invalid:
        return {"classification": "invalid", "action": "reject_register", "publish": False}
    if ambiguous:
        return {"classification": "needs_ruling", "action": "file_p2_needs_triage", "publish": False}
    if render_bad:
        return {"classification": "render_contract_failure", "action": "block_release", "publish": False}
    if unambiguous:
        return {
            "classification": "unambiguous_drift",
            "action": "publish_new_version",
            "publish": bool(transition_ok),
        }
    return {"classification": "clean", "action": "no_change", "publish": False}


def validate_transition(register: dict[str, Any], proposed: Any, contract: dict[str, Any]) -> list[str]:
    """Validate a proposed next version: valid, one newer, same scope, linked back.

    One tennis-specific clause on top of the grid rules: ``draw_released`` is a
    **latch**.  It may go false->true when the ceremony happens; true->false
    would silently make every committed draw slot unvalidated again.
    """
    if proposed is None:
        return []
    findings = validate_register(proposed, contract)
    if not isinstance(proposed, dict):
        return sorted(set(findings))
    if proposed.get("version") != register.get("version", 0) + 1:
        findings.append("NON_MONOTONIC_VERSION")
    if (
        proposed.get("tournament") != register.get("tournament")
        or proposed.get("season") != register.get("season")
    ):
        findings.append("TRANSITION_CHANGED_SCOPE")
    if proposed.get("supersedes_version") != register.get("version"):
        findings.append("MISSING_SUPERSEDES_LINK")
    if register.get("draw_released") is True and proposed.get("draw_released") is not True:
        findings.append("INVALID_DRAW_RELEASED_UNLATCH")
    return sorted(set(findings))


# ---------------------------------------------------------------------------
# Drift detection (the daily sentinel's comparison core)
# ---------------------------------------------------------------------------

def priced_source_blocks(register: dict[str, Any]) -> list[dict[str, Any]]:
    """Every source block on the register that a page could print a number from.

    Players AND reach cells (UX-P139).  The two drift and freshness checks used
    to walk ``players`` alone, which was correct when the players' outright
    prices were the only thing rendered.  A grid of 336 reach prices that the
    sentinel does not look at is 336 numbers with no drift detection and no
    staleness gate — the exact hole the register pattern exists to close, and
    it would have opened silently the day the grid shipped.

    Matchup blocks are deliberately NOT here: their identities live under
    ``sides`` rather than on the block, so they need their own walk and the
    slate already has one.
    """
    blocks: list[dict[str, Any]] = []
    for player in register.get("players", []) or []:
        if isinstance(player, dict):
            blocks.extend(b for b in (player.get("sources") or []) if isinstance(b, dict))
    for reach in register.get("reaches", []) or []:
        if isinstance(reach, dict):
            blocks.extend(b for b in (reach.get("sources") or []) if isinstance(b, dict))
    return blocks


def _observed_index(candidates: list[dict[str, Any]]) -> dict[tuple, list[dict[str, Any]]]:
    index: dict[tuple, list[dict[str, Any]]] = {}
    for row in candidates:
        index.setdefault((row.get("source"), row.get("market_id"), row.get("outcome_id")), []).append(row)
    return index


def diff_against_inventory(register: dict[str, Any], candidates: Any) -> list[str]:
    """Compare registered identities against live source inventory.

    ``candidates`` is a list of observed rows, each ``{source, market_id,
    outcome_id, outcome_name, status, terminal_result, season}``.

    The asymmetry is inherited from the grid register on purpose: a **rename**
    or a **settlement** that keeps the pinned identity is unambiguous and may be
    auto-versioned; anything that changes *which market backs a row* is
    ambiguous and goes to a human.
    """
    if not isinstance(candidates, list):
        return ["CANDIDATES_WRONG_SHAPE"]
    if any(not isinstance(row, dict) for row in candidates):
        # One malformed row poisons publication for this tournament only, and it
        # is never silently dropped.
        return ["POISON_CANDIDATE"]

    findings: list[str] = []
    season = register.get("season")
    index = _observed_index(candidates)

    for block in priced_source_blocks(register):
        if block.get("status") == "missing":
            # Q426, so the next reader does not re-derive this: skipping
            # `missing` is right for THIS comparator and it is also the reason
            # nothing was red for a day of the US Open. The draw census wrote
            # `missing` against 96 R128 fixtures, markets appeared overnight,
            # and a check that only verifies pinned identities cannot notice a
            # row that has no pin — a guard blind to a population reports on it
            # exactly like a healthy one (gotcha #53).
            #
            # The fix is deliberately NOT here. Asking the database what it
            # thinks the tournament contains is the fuzzy discovery this whole
            # design refuses (see `build_candidates`). The inverse question is
            # asked by `tasks/tournament_matchup_linker`, which resolves what it
            # can against an id-anchored rule and reports `needy` against
            # `resolved` so an unfilled fixture is a number somebody can read.
            continue
        key = (block.get("source"), block.get("market_id"), block.get("outcome_id"))
        matches = index.get(key, [])
        if len(matches) > 1:
            findings.append("AMBIGUOUS_CANDIDATES")
            continue
        if not matches:
            findings.append("REGISTERED_IDENTITY_NOT_OBSERVED")
            continue

        row = matches[0]
        if row.get("status") == "settled" and block.get("status") == "live":
            if row.get("terminal_result") not in TERMINAL_RESULTS:
                findings.append("SETTLEMENT_WITHOUT_RESULT")
            else:
                findings.append("UNAMBIGUOUS_SETTLEMENT_DRIFT")
        elif (
            row.get("outcome_name") is not None
            and normalize_player_name(row.get("outcome_name"))
            != normalize_player_name(block.get("source_name"))
        ):
            findings.append("UNAMBIGUOUS_RENAME_DRIFT")

    if any(row.get("season") not in (None, season) for row in candidates):
        findings.append("NEXT_OR_OTHER_SEASON_CANDIDATE")

    return sorted(set(findings))


def check_freshness(register: dict[str, Any], now: datetime, *, max_age_hours: float = STALE_PRICE_HOURS) -> list[str]:
    """Verify every ``live`` identity has a recently observed price.

    Read from ``price_observed_at``, which the writer fills from
    ``futures_odds_snapshots.captured_at`` — **not** from
    ``futures_outcomes.last_updated``, which the census proved unreliable (the
    Polymarket men's field read 2026-07-21 on all 23 outcomes while its
    snapshots ran to 2026-08-10).  A board is only allowed to be rich; it is not
    allowed to be confident about a number nobody has seen since July.
    """
    findings: list[str] = []
    cutoff = now - timedelta(hours=max_age_hours)
    for block in priced_source_blocks(register):
        if block.get("status") != "live":
            continue
        observed = block.get("price_observed_at")
        if not is_iso8601(observed):
            findings.append("LIVE_PRICE_NEVER_OBSERVED")
            continue
        if datetime.fromisoformat(str(observed).replace("Z", "+00:00")) < cutoff:
            findings.append("LIVE_PRICE_STALE")
    return sorted(set(findings))


def check_rendered_rows(register: dict[str, Any], rendered: Any) -> list[str]:
    """Verify rendered rows honour their registered status.

    "Settled means settled" enforced at the render boundary, and the membership
    rule enforced in the one direction that matters: a row the register does not
    carry is ``UNREGISTERED_RENDER_ROW`` — *a market not in the register does
    not render*.
    """
    if not isinstance(rendered, list):
        return ["RENDERED_WRONG_SHAPE"]

    findings: list[str] = []
    by_row: dict[tuple, dict[str, Any]] = {}
    for player in register.get("players", []):
        if not isinstance(player, dict):
            continue
        for block in player.get("sources") or []:
            if isinstance(block, dict):
                by_row[(player.get("entity_key"), block.get("source"))] = block

    for row in rendered:
        if not isinstance(row, dict):
            findings.append("POISON_RENDER_ROW")
            continue
        block = by_row.get((row.get("entity_key"), row.get("source")))
        if block is None:
            findings.append("UNREGISTERED_RENDER_ROW")
            continue

        status = block.get("status")
        state = row.get("state")
        probability = row.get("probability")
        if status == "missing":
            if state != "missing" or probability is not None:
                findings.append("MISSING_RENDERED_AS_PROBABILITY")
        elif status == "settled":
            if state != block.get("terminal_result") or probability is not None:
                findings.append("SETTLED_RENDERED_AS_LIVE")
        elif status == "live":
            if state != "live" or not isinstance(probability, (int, float)):
                findings.append("LIVE_RENDER_NOT_NUMERIC")
            elif not 0 <= float(probability) <= 1:
                findings.append("LIVE_PROBABILITY_OUT_OF_RANGE")

    return sorted(set(findings))


# ---------------------------------------------------------------------------
# Loading + lookup (the serving path)
# ---------------------------------------------------------------------------

def register_filename(tournament: str, season: str) -> str:
    return f"{tournament}-{season}.json"


def load_register(
    tournament: str,
    season: str,
    *,
    directory: Path | None = None,
) -> dict[str, Any] | None:
    """Load a committed register, or ``None`` when there is no readable file.

    ``None`` is meaningful and safe: no register means the page has no rows to
    render, which is an honest empty state.  A file that exists but is
    unreadable also returns ``None``, logged loudly — a broken register degrades
    to nothing, never to a wrong number.
    """
    path = (directory or REGISTER_DIR) / register_filename(tournament, season)
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        logger.error("Tournament register %s unreadable — rendering nothing: %s", path, exc)
        return None


def registered_market_ids(*, directory: Path | None = None) -> set[int]:
    """Every ``futures_markets.id`` any committed register renders.

    THE PRICE RAIL NEEDS THIS AND NOTHING ELSE DOES YET (#2199 follow-up).
    ``futures_price_refresh`` selects by *tier and traded volume*, which is the
    right bound for a platform-wide sweep and the wrong one for a curated page:
    a market earns its place on ``/tournaments/us-open`` because an agent chose
    it, not because it cleared $10K. Measured 2026-08-27, all three markets
    behind the "More predictions" section were tier 5 — two at 837h stale, one
    at 215h — so the only rail that can reach them structurally excluded every
    one, permanently. Curation IS the value floor for these rows.

    Walks the whole document rather than reading ``props``/``players`` by name.
    The register grows sections (props, players, matchups, and whatever the next
    surface needs) and a collector that enumerates today's keys silently stops
    covering tomorrow's — the failure would be a *new* section going price-dark
    with every existing test green.

    Best-effort by construction: an unreadable or malformed register yields
    nothing from that file and never raises. The sweep degrades to its volume
    class, which is strictly better than not running (same posture as
    :func:`load_register`, which returns ``None`` rather than propagating).
    Files whose name starts with ``_`` are fixtures, not committed registers.
    """
    found: set[int] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            market_id = node.get("market_id")
            # `bool` is an `int` subclass; `True` would collect as market 1.
            if isinstance(market_id, int) and not isinstance(market_id, bool):
                found.add(market_id)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    root = directory or REGISTER_DIR
    try:
        paths = sorted(root.glob("*.json"))
    except OSError as exc:
        logger.error("Tournament register dir %s unreadable: %s", root, exc)
        return found

    for path in paths:
        if path.name.startswith("_"):
            continue
        try:
            walk(json.loads(path.read_text()))
        except (OSError, ValueError) as exc:
            logger.error(
                "Tournament register %s unreadable — its markets will not be "
                "price-refreshed as registered: %s",
                path,
                exc,
            )
    return found


class TournamentRegister:
    """Read-only lookup view over a validated register.

    Built once per request.  Every method is a dict lookup; there is no
    matching, normalization or scoring on the serving path by design.
    """

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.tournament: str = data.get("tournament", "")
        self.season: str = data.get("season", "")
        self.version: int = data.get("version", 0)
        self.generated_at: str = data.get("generated_at", "")
        self.draw_released: bool = data.get("draw_released") is True

        self.players: list[dict[str, Any]] = [
            p for p in data.get("players", []) if isinstance(p, dict)
        ]
        self.matchups: list[dict[str, Any]] = [
            m for m in data.get("matchups", []) if isinstance(m, dict)
        ]

        # (source, market_id, outcome_id) -> (entity_key, source block).  The
        # serving path walks the outcomes it loaded and asks "is this identity
        # registered?"; anything absent never enters the board.
        self.by_identity: dict[tuple, tuple[str, dict[str, Any]]] = {}
        for player in self.players:
            for block in player.get("sources") or []:
                if not isinstance(block, dict) or block.get("status") == "missing":
                    continue
                identity = (block.get("source"), block.get("market_id"), block.get("outcome_id"))
                if None in identity:
                    continue
                self.by_identity[identity] = (player.get("entity_key", ""), block)

        self.by_entity: dict[str, dict[str, Any]] = {
            p.get("entity_key", ""): p for p in self.players
        }

    def draw_players(self, draw: str) -> list[dict[str, Any]]:
        return [p for p in self.players if p.get("draw") == draw]

    def board_players(self, draw: str) -> list[dict[str, Any]]:
        """Contenders only — the championship board's population.

        Separate from ``draw_players`` on purpose. After the second population
        pass the register carries ~4x more participants than contenders, and a
        board built from ``draw_players`` would rank a qualifier's
        P(wins-this-match) alongside Alcaraz's P(wins-the-title). The filter
        lives here, once, rather than at each call site.
        """
        return [
            p for p in self.players
            if p.get("draw") == draw and player_role(p) == "contender"
        ]

    def image_for(self, entity_key: str) -> Optional[dict[str, Any]]:
        """The pinned image a surface may render for one player, or ``None``.

        Returns the two URLs and nothing else — the evidence and the
        verification flag are the *register's* business, checked at load, and
        shipping them to a browser would invite a client to re-decide something
        that was already decided offline.
        """
        player = self.by_entity.get(entity_key)
        image = (player or {}).get("image")
        if not isinstance(image, dict):
            return None
        url = image.get("url")
        flag_url = image.get("flag_url")
        if url is None and flag_url is None:
            return None
        return {"url": url, "flag_url": flag_url, "country": image.get("country")}

    def image_coverage(self, draw: str) -> dict[str, int]:
        """Per-draw image counts — Alex's ruling 8 gate, as a number.

        "Enable ONLY if coverage is ~complete per draw — half-covered looks
        worse than none."  The gate is a measurement, so it is measurable from
        the register itself rather than from a report somebody wrote once.
        """
        players = self.draw_players(draw)
        faces = 0
        flags = 0
        for player in players:
            image = player.get("image")
            if not isinstance(image, dict):
                continue
            if image.get("url"):
                faces += 1
            if image.get("flag_url"):
                flags += 1
        return {
            "players": len(players),
            "faces": faces,
            "flags": flags,
            "any": sum(
                1
                for p in players
                if isinstance(p.get("image"), dict)
                and (p["image"].get("url") or p["image"].get("flag_url"))
            ),
        }

    def market_ids(self, source: str | None = None) -> list[int]:
        """Distinct market ids the register pins, for a bounded targeted load."""
        ids = set()
        for player in self.players:
            for block in player.get("sources") or []:
                if not isinstance(block, dict):
                    continue
                if source is not None and block.get("source") != source:
                    continue
                if isinstance(block.get("market_id"), int):
                    ids.add(block["market_id"])
        for holder in (*self.matchups, *self.reaches):
            for block in holder.get("sources") or []:
                if not isinstance(block, dict):
                    continue
                if source is not None and block.get("source") != source:
                    continue
                if isinstance(block.get("market_id"), int):
                    ids.add(block["market_id"])
        return sorted(ids)

    def entry_for_identity(self, source: str, market_id: Any, outcome_id: Any):
        return self.by_identity.get((source, market_id, outcome_id))

    def matchups_on(self, date_iso: str) -> list[dict[str, Any]]:
        return [m for m in self.matchups if str(m.get("scheduled_date", "")).startswith(date_iso)]

    def source_coverage(self) -> dict[str, int]:
        """How many players carry 1 source vs 2 — the blend-richness number."""
        counts: Counter = Counter()
        for player in self.players:
            live = [
                b for b in (player.get("sources") or [])
                if isinstance(b, dict) and b.get("status") != "missing"
            ]
            counts[f"{len(live)}_source"] += 1
        return dict(sorted(counts.items()))

    @property
    def reaches(self) -> list[dict[str, Any]]:
        """Every player x round cell the register carries (UX-P139)."""
        return [r for r in (self.data.get("reaches") or []) if isinstance(r, dict)]

    def reach_cells(self, draw: str) -> dict[tuple[str, str], dict[str, Any]]:
        """``(entity_key, round) -> cell`` for one draw.

        A dict, because the grid's only question of this collection is "what
        backs THIS cell" and the answer has to be a lookup.  The moment it
        became a scan-and-match the register would have stopped being the
        register.
        """
        return {
            (str(r.get("entity_key")), str(r.get("round"))): r
            for r in self.reaches
            if r.get("draw") == draw
        }

    def reach_rounds(self, draw: str) -> list[str]:
        """The rounds this draw has cells for, in draw order — the grid's columns.

        Read off the register rather than from a constant so a tournament whose
        sources publish a different ladder gets a different grid with no code
        change.  Ordered by ``ROUNDS`` so a register listing them out of order
        still renders left-to-right in the order they are played.
        """
        present = {str(r.get("round")) for r in self.reaches if r.get("draw") == draw}
        return [name for name in ROUNDS if name in present]

    def reach_outcome_ids(self) -> list[int]:
        """Every outcome id a reach cell would price — the bounded grid load."""
        ids: set[int] = set()
        for reach in self.reaches:
            for block in reach.get("sources") or []:
                if isinstance(block, dict) and isinstance(block.get("outcome_id"), int):
                    ids.add(block["outcome_id"])
        return sorted(ids)

    @property
    def props(self) -> list[dict[str, Any]]:
        return [p for p in (self.data.get("props") or []) if isinstance(p, dict)]

    @property
    def broadcasts(self) -> list[dict[str, Any]]:
        return [b for b in (self.data.get("broadcasts") or []) if isinstance(b, dict)]

    def prop_outcome_ids(self) -> list[int]:
        """Every outcome id a curated prop would price — bounded, like the rest."""
        ids: set[int] = set()
        for prop in self.props:
            for outcome in prop.get("outcomes") or []:
                if isinstance(outcome, dict) and isinstance(outcome.get("outcome_id"), int):
                    ids.add(outcome["outcome_id"])
        return sorted(ids)

    def matchup_outcome_ids(self) -> list[int]:
        """Every outcome id a slate row would price — the bounded slate load."""
        ids: set[int] = set()
        for matchup in self.matchups:
            for block in matchup.get("sources") or []:
                if not isinstance(block, dict) or block.get("status") == "missing":
                    continue
                for side in (block.get("sides") or {}).values():
                    if isinstance(side, dict) and isinstance(side.get("outcome_id"), int):
                        ids.add(side["outcome_id"])
        return sorted(ids)

    def counters(self) -> dict[str, int]:
        counts: Counter = Counter()
        for player in self.players:
            counts[f"players_{player.get('draw', 'unknown')}"] += 1
            counts[f"role_{player_role(player)}"] += 1
            for block in player.get("sources") or []:
                if isinstance(block, dict):
                    counts[f"source_{block.get('status', 'invalid')}"] += 1
        counts["matchups"] = len(self.matchups)
        counts["reach_cells"] = len(self.reaches)
        for reach in self.reaches:
            for block in reach.get("sources") or []:
                if isinstance(block, dict):
                    counts[f"reach_{block.get('status', 'invalid')}"] += 1
        counts["seeded"] = sum(1 for p in self.players if p.get("seed") is not None)
        counts["draw_slotted"] = sum(1 for p in self.players if p.get("draw_slot") is not None)
        return dict(sorted(counts.items()))


def build_contract(tournament_specs: dict[str, Any]) -> dict[str, Any]:
    """Assemble a validation contract from tournament specs."""
    return {
        "register_schema_version": SCHEMA_VERSION,
        "allowed_sources": list(ALLOWED_SOURCES),
        "draws": list(DRAWS),
        "rounds": list(ROUNDS),
        "tournament_contracts": tournament_specs,
    }


def us_open_2026_contract() -> dict[str, Any]:
    """The contract this program ships against."""
    return build_contract({"us-open": {"season": "2026", "entity_kind": "player"}})


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
