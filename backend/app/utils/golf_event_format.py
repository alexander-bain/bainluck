"""Golf event FORMAT — which markets an event's format allows to exist at all.

#7985. `/golf`'s PGA Tour card led the **Presidents Cup** with "6.1% Jackson
Koivun, Leader" over a field of 132 golfers, for a **24-player team match-play
event with no cut and no individual winner**. Five stroke-play markets had been
minted for it — `datagolf:pga:500:{win,top_5,top_10,top_20,make_cut}` — and the
card ranked their outcomes exactly as it ranks a real tournament's, because
nothing in the mint or the serve path asks what KIND of event it is.

The correct market for that event was in the same payload the whole time: Kalshi's
Team USA 81.5% v Team World 14.5%, carried as an `h2h_matchups` entry.

── WHY NOT `is_tour_event` ─────────────────────────────────────────────────────
The filing proposed `is_tour_event`, which is served `False` for the Presidents Cup
and `True` for all three of its siblings, and looked like a ready-made
discriminator. It is not one. `routes/golf.py` computes it as *"this key is not in
`TOURNAMENT_ORDER`"*, and `TOURNAMENT_ORDER` is the hand-maintained list of named
events — the four men's majors, the women's majors, the Players, LIV, TGL and the
two cups. `golf.py` says so itself: *"Majors are NOT flagged `is_tour_event` (they
sit in TOURNAMENT_ORDER)"*.

So "Presidents Cup is the only `False` tournament" was a true reading of one
September week's payload and a false reading of the flag. A guard keyed on it
would have withheld the Winner market from **the Masters, the PGA Championship,
the U.S. Open and the Open Championship** — and no September measurement could
have caught that, because no major is in season in September.

The property is the event's FORMAT, and it is keyed the same way the rest of the
page keys tournaments.

── THE SET ─────────────────────────────────────────────────────────────────────
Team match play: two teams, every point won on the course head-to-head, **no cut
to miss and no individual champion**. `win` / `top_5` / `top_10` / `top_20` /
`make_cut` are not mispriced for such an event — they are questions the event
cannot answer, whatever field populates them.

TGL is deliberately NOT in this set although it is also team golf. It is not a
DataGolf tour, so nothing mints phantom stroke-play markets for it, and its card
is built from venue markets that are real. Adding it would be an untestable
widening of a guard whose whole job is to be narrow. If a phantom ever appears on
a TGL card, that is this constant plus a specimen, not a rewrite.
"""

import re
from typing import Final

# Tournament keys, as produced by `routes/golf.py`'s `_TOURNAMENT_PATTERNS`.
TEAM_MATCH_PLAY_KEYS: Final[frozenset[str]] = frozenset({
    "ryder_cup",
    "presidents_cup",
})

# For the MINT path, which has only the venue's event name — DataGolf's schedule
# carries `event_name`, `event_id`, `start_date`, `end_date`, `status` and no
# format field of any kind, so the name is the only signal available there.
#
# Anchored on the two cups rather than a general "cup" shape on purpose: golf is
# full of stroke-play events with "Cup" in the name (the FedEx Cup, the Zurich
# Classic's team stroke play, any number of sponsor cups), and a loose pattern
# here withholds real markets from real tournaments. The Junior Presidents Cup
# and the Junior Ryder Cup match, and should — they are the same format.
_TEAM_MATCH_PLAY_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"\bryder\s+cup\b|\bpresidents?\s+cup\b",
    re.I,
)

# The DataGolf market types that presuppose a cut and an individual champion.
# Kept as a set of the type codes `tasks/datagolf.py` mints, so the two stay
# legible side by side; a new stroke-play type added there is a one-line addition
# here and a guard test fails until it is made.
INDIVIDUAL_STROKE_PLAY_MARKET_TYPES: Final[frozenset[str]] = frozenset({
    "win",
    "top_5",
    "top_10",
    "top_20",
    "make_cut",
})


# ── THE PAIR THAT LEADS THE CARD ────────────────────────────────────────────
# Withholding the phantoms is only half the repair. `/golf`'s card component
# enters its cup renderer on `_isCupEvent(t) && t.golfers.length === 2` and reads
# its hero out of `golfers[0]` — it never looks at `h2h_matchups`
# (`frontend/components/TournamentCard.tsx:59,224`). So a team match-play card
# served with `golfers: []` and Team USA v Team World sitting in `h2h_matchups`
# renders as a bare title: the phantom is gone and nothing has replaced it.
# CERT-3289 blocked exactly that shape. The team pair has to be IN the contract
# the card reads.
#
# Which matchup is the team one is not a position — during a cup the same list
# carries the singles (Scheffler v Im), and `routes/golf.py` sorts h2h matchups
# by CLOSENESS, so a lopsided 81.5/14.5 team market sorts last behind every
# tight singles pairing. Taking `h2h_matchups[0]` would put a golfer back at the
# top of the card by a different road.
#
# So the sides are matched against a closed allowlist of team names. That is the
# safety property, and it is the mirror of `withhold_individual_market`'s: this
# predicate can only ever promote a pair whose BOTH sides name a team, so it can
# fail to find the team market and it can never promote a person.
_TEAM_SIDE_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^team\s+", re.I)

TEAM_SIDE_NAMES: Final[frozenset[str]] = frozenset({
    # Presidents Cup — Kalshi writes "Team USA" / "Team World"; DataGolf and the
    # tour's own materials say "International".
    "usa", "us", "united states", "america",
    "world", "international", "rest of the world",
    # Ryder Cup (and the Solheim Cup, whose sides are the same two).
    "europe",
    # Walker Cup. Not reachable from `TEAM_MATCH_PLAY_KEYS` today, and listed
    # because the frontend's `_isCupEvent` already names walker/solheim: the day
    # a key is added there, the promotion works rather than silently serving a
    # titles-only card. A name in this set does nothing on its own — it is only
    # ever consulted for a tournament that is already team match play.
    "great britain and ireland", "gb and i",
})


def is_team_match_play_key(tournament_key: str | None) -> bool:
    """True when a `routes/golf.py` tournament key names a team match-play event."""
    if not tournament_key:
        return False
    return tournament_key.strip().lower() in TEAM_MATCH_PLAY_KEYS


def normalize_team_side_name(name: str | None) -> str:
    """Fold a served outcome name to the form `TEAM_SIDE_NAMES` is keyed in.

    Drops the optional "Team " prefix, periods (`U.S.A.` → `usa`) and spells `&`
    so one spelling of each side is stored. Returns `""` for an absent name,
    which is not in the set, so an empty name can never match a team.
    """
    if not name:
        return ""
    folded = name.strip().lower().replace(".", "").replace("&", " and ")
    folded = _TEAM_SIDE_PREFIX_RE.sub("", folded)
    return re.sub(r"\s+", " ", folded).strip()


def is_team_side_name(name: str | None) -> bool:
    """True when a served outcome name names one of a cup's two SIDES, not a player."""
    return normalize_team_side_name(name) in TEAM_SIDE_NAMES


def select_team_side_matchup(matchups: list[dict] | None) -> dict | None:
    """The h2h matchup that is the cup itself, or `None`.

    Both sides must name a team and they must name DIFFERENT teams — a pair that
    folds to one side ("USA" v "Team USA") is a data defect, and leading the card
    with a 50/50 of one team against itself would be a worse reading than the
    phantom it replaced.

    Order within the list is not consulted: see the module note above for why
    position is the wrong key.
    """
    for matchup in matchups or []:
        if not isinstance(matchup, dict):
            continue
        side_a = (matchup.get("golfer_a") or {}).get("name")
        side_b = (matchup.get("golfer_b") or {}).get("name")
        if not (is_team_side_name(side_a) and is_team_side_name(side_b)):
            continue
        if normalize_team_side_name(side_a) == normalize_team_side_name(side_b):
            continue
        return matchup
    return None


def is_team_match_play_name(event_name: str | None) -> bool:
    """True when a venue's own event name names a team match-play event.

    Used by the mint path, which has no tournament key.
    """
    if not event_name:
        return False
    return bool(_TEAM_MATCH_PLAY_NAME_RE.search(event_name))


def datagolf_market_type(external_id: str | None) -> str | None:
    """The trailing type code of a `datagolf:{tour}:{event_id}:{market_type}` id.

    `None` for anything that is not that shape, so a caller can never read a
    truncated or foreign id as a market type.
    """
    if not external_id:
        return None
    parts = external_id.split(":")
    if len(parts) != 4 or parts[0] != "datagolf":
        return None
    return parts[3] or None


def withhold_individual_market(
    tournament_key: str | None,
    source: str | None,
    external_id: str | None,
) -> bool:
    """True for an individual stroke-play market minted onto a team match-play event.

    The `source == "datagolf"` clause is the safety property, not a detail: this
    predicate can only ever withhold a market **we minted ourselves**. A venue's
    own market on the same card — Kalshi's Team USA v Team World, its
    "Golfers to compete in the Presidents Cup" field — is out of reach of this
    guard by construction, so a wrong answer here can hide our phantom and can
    never hide a real market.
    """
    if not is_team_match_play_key(tournament_key):
        return False
    if (source or "").strip().lower() != "datagolf":
        return False
    return datagolf_market_type(external_id) in INDIVIDUAL_STROKE_PLAY_MARKET_TYPES
