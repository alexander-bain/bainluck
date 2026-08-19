"""The CREATE plan's row derivation, in ONE place. Pure: no DB, no network, no clock.

Queue 369, building the attended CREATE consumer (#1796/#1902, ruling: *attended
event-CREATE from venue truth is APPROVED — provider anchors, plan artifact,
pre-cert, always attended*).

WHY THIS MODULE EXISTS AT ALL

The plan is a CONTENT ADDRESS. Alex approves a hash; the apply presents that hash;
the rail refuses anything else. That only works while every producer of the plan
derives the identical rows from the identical reviewed set — a second
implementation that orders clubs differently, or trims a label differently, or
picks the other MLB registry, mints a DIFFERENT address from the SAME approval,
and the operator is then holding a hash nothing will accept.

Before this module there were about to be exactly two such producers:
``scripts/derive_event_create_plan.py`` (the local dry run, which talks to
``/api/admin/db-query`` over HTTP) and the live rail in
``app/tasks/create_events_from_truth`` (which talks to a session). They differ in
how they READ, which is fine and unavoidable. They must not differ in what they
BUILD. So the reading stays in each shell and the building lives here, imported by
both — the same reasoning ``repair_event_team_binding`` gives for importing the
plan primitives instead of re-implementing them: *two copies of a gate is two
gates to keep honest, and the second one is always the one nobody re-reads.*

WHAT IS DELIBERATELY **NOT** HERE

Club name -> team id. That resolution is the poisoned path (``team_identity_mapping``
holds 158 rows whose ``source_name`` is another club's canonical name in the same
sport — #1918 — and ``resolve_team`` auto-registers its hits), so each shell
resolves it against ``teams`` directly and refuses anything that is not 1:1. This
module takes the ALREADY-RESOLVED anchors as an argument and will not look a club
up by any other route.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from app.utils.repair_apply_plan import PlannedCreate

#: The regular-season MLB sport row. 33178 is ``baseball_mlb_preseason`` and is NOT
#: interchangeable with it: every one of the 30 MLB clubs has TWO team rows carrying
#: the same ``espn_id``, one per registry, and both are in live use (#1798). A
#: derivation that took the club NAME alone would have had a coin-flip's chance of
#: binding 328 regular-season games to preseason club rows, with nothing downstream
#: complaining. This is also why ``sport_id`` is inside the create digest (queue 368).
MLB_SPORT_ID = 53232

#: Population 1 — the single Aug 5 MIN@KC game (#1902), the missing link target
#: behind market ``58609021``'s three-way identity error. A SUBSET of population 2.
POPULATION_1: tuple[str, ...] = ("401816407",)

#: Row #1 of population 2, asserted BY NAME so a re-derivation that quietly loses
#: Alex's own reported-missing game (#1925, Sox @ Pirates 2026-08-15) fails loudly
#: here instead of shipping 327 rows that look fine.
ROW_ONE = "401816534"

#: Path of the committed reviewed truth set, relative to ``backend/``. It is
#: committed rather than read out of ``.claude/handoff`` because handoff is
#: gitignored and therefore does not exist on the dyno — a rail that cannot read
#: its own reviewed population cannot be attended, it can only be re-derived, and
#: re-derivation at apply time is the entire defect this pattern exists to close.
TRUTH_SET_RELATIVE_PATH = "app/data/event_create_truth_set.json"

#: The Aug-19 population (#1947's population 2), added queue 369. It gets its OWN
#: file rather than being appended to the set above, and that is the whole point:
#: the q362 set's declared scope is *MLB 2026-03-25..2026-08-17* and its latest
#: reviewed game starts 2026-08-16T01:38Z, so these four are outside it. Adding
#: them would silently change an object Alex already reviewed — ruling 079's exact
#: shape (*not a widened constant, not "close enough"*). A new population is a new
#: reviewed object, a new address, and a new approval.
AUG19_TRUTH_SET_RELATIVE_PATH = "app/data/event_create_truth_set_aug19.json"

#: population token -> (committed reviewed file, id subset or None for "all of it").
#: The token selects WHICH APPROVAL an apply is bound to. It is deliberately not a
#: filter expression: a population an operator can describe is a population an
#: operator can widen, and the reviewed object must be a fixed list.
TRUTH_SET_REGISTRY: dict[str, tuple[str, tuple[str, ...] | None]] = {
    "1": (TRUTH_SET_RELATIVE_PATH, POPULATION_1),
    "2": (TRUTH_SET_RELATIVE_PATH, None),
    "3": (AUG19_TRUTH_SET_RELATIVE_PATH, None),
}

_LABEL_RE = re.compile(r"^(?P<away>.+?) @ (?P<home>.+?) (?P<date>\d{4}-\d{2}-\d{2})")


class DerivationRefused(Exception):
    """A derivation that cannot be completed EXACTLY as reviewed. Never a guess.

    Carries a machine-readable ``code`` as well as prose, because "the plan could
    not be built" and "the plan was built and refused" are different states to an
    operator and must not arrive as the same string.
    """

    def __init__(self, code: str, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def as_payload(self) -> dict[str, Any]:
        return {"refused": True, "reason_codes": [self.code], "note": self.message, **self.detail}


#: Refusal codes this module can raise. Named as verbs about what was refused.
REASON_TRUTH_SET_SHAPE = "TRUTH_SET_SHAPE_INVALID"
REASON_ROW_ONE_ABSENT = "TRUTH_SET_ROW_ONE_ABSENT"
REASON_ID_NOT_REVIEWED = "TRUTH_ID_NOT_IN_REVIEWED_SET"
REASON_LABEL_UNPARSEABLE = "TRUTH_LABEL_UNPARSEABLE"
REASON_ANCHOR_NOT_UNIQUE = "CLUB_ANCHOR_NOT_UNIQUE"


def parse_label(label: str) -> tuple[str, str]:
    """``"Away @ Home YYYY-MM-DD …"`` -> ``(away, home)``. Raises, never guesses."""
    match = _LABEL_RE.match(label or "")
    if not match:
        raise DerivationRefused(
            REASON_LABEL_UNPARSEABLE, f"unparseable venue label: {label!r}"
        )
    return match.group("away"), match.group("home")


def load_games(truth: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Index the reviewed set by provider id, asserting row #1 is still in it."""
    games_raw = truth.get("games")
    ids_raw = truth.get("truth_ids")
    if not isinstance(games_raw, list) or not isinstance(ids_raw, list):
        raise DerivationRefused(
            REASON_TRUTH_SET_SHAPE,
            "the reviewed truth set is missing its `games` / `truth_ids` arrays",
        )
    games: dict[str, Mapping[str, Any]] = {}
    for game in games_raw:
        if not isinstance(game, Mapping) or "espn_id" not in game:
            raise DerivationRefused(
                REASON_TRUTH_SET_SHAPE, "a reviewed game row has no `espn_id`"
            )
        games[str(game["espn_id"])] = game
    # Each reviewed set names its own sentinel row; the q362 file predates the key
    # and keeps ROW_ONE as its default. The assertion is what makes a derivation
    # that quietly lost a reviewed game fail HERE rather than ship n-1 rows that
    # each look fine.
    sentinel = str(truth.get("row_one") or ROW_ONE)
    if sentinel not in games:
        raise DerivationRefused(
            REASON_ROW_ONE_ABSENT,
            f"row #1 {sentinel} is absent from the reviewed set — this derivation "
            "is over a different population than the one that was reviewed",
        )
    return games


def truth_set_path_for(population: str) -> str:
    """The committed file a population is bound to. Refuses an unknown token."""
    entry = TRUTH_SET_REGISTRY.get(str(population))
    if entry is None:
        raise DerivationRefused(
            "UNKNOWN_POPULATION",
            f"population must be one of {sorted(TRUTH_SET_REGISTRY)}, got {population!r}",
        )
    return entry[0]


def select_population(truth: Mapping[str, Any], population: str) -> list[str]:
    """The reviewed id list for a population token, in reviewed order."""
    games = load_games(truth)
    entry = TRUTH_SET_REGISTRY.get(str(population))
    if entry is None:
        raise DerivationRefused(
            "UNKNOWN_POPULATION",
            f"population must be one of {sorted(TRUTH_SET_REGISTRY)}, got {population!r}",
        )
    subset = entry[1]
    wanted = list(subset) if subset is not None else [str(i) for i in truth["truth_ids"]]
    unreviewed = [tid for tid in wanted if tid not in games]
    if unreviewed:
        raise DerivationRefused(
            REASON_ID_NOT_REVIEWED,
            f"{len(unreviewed)} id(s) are not in the reviewed truth set",
            not_reviewed=unreviewed,
        )
    return wanted


def required_club_names(wanted: Sequence[str], games: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Every club name the plan will need an anchor for, sorted and deduped."""
    names: set[str] = set()
    for tid in wanted:
        away, home = parse_label(str(games[tid].get("label", "")))
        names.update((away, home))
    return sorted(names)


def build_rows(
    wanted: Sequence[str],
    games: Mapping[str, Mapping[str, Any]],
    anchors: Mapping[str, int],
    *,
    sport_id: int = MLB_SPORT_ID,
) -> list[PlannedCreate]:
    """The reviewed ids, as plan rows. The ONLY place a ``PlannedCreate`` is built.

    ``anchors`` is ``club name -> team id``, already proven 1:1 in ``sport_id`` by
    the caller. A name absent from it is a refusal, never a lookup by another route.
    """
    missing = sorted({n for tid in wanted for n in parse_label(str(games[tid]["label"]))} - set(anchors))
    if missing:
        raise DerivationRefused(
            REASON_ANCHOR_NOT_UNIQUE,
            f"{len(missing)} club(s) have no 1:1 anchor in sport_id={sport_id}",
            unanchored=missing,
        )
    rows: list[PlannedCreate] = []
    for tid in wanted:
        game = games[tid]
        away, home = parse_label(str(game["label"]))
        rows.append(
            PlannedCreate(
                truth_id=tid,
                provider="espn",
                home_team_id=int(anchors[home]),
                away_team_id=int(anchors[away]),
                home_name=home,
                away_name=away,
                commence_time=str(game["commence"]),
                sport_id=int(sport_id),
                label=str(game["label"]),
            )
        )
    return rows


def anchors_from_rows(rows: Iterable[Sequence[Any]]) -> dict[str, int]:
    """``[(name, team_id), …]`` -> ``{name: team_id}``, refusing anything not 1:1.

    Shared by both shells because the refusal is the load-bearing half: a club that
    resolves to two rows in one sport is exactly the #1798 registry split, and
    picking either one is picking a copy of the club nobody approved.
    """
    by_name: dict[str, list[int]] = {}
    for row in rows:
        name, team_id = str(row[0]), int(row[1])
        by_name.setdefault(name, []).append(team_id)
    ambiguous = {n: ids for n, ids in by_name.items() if len(ids) != 1}
    if ambiguous:
        raise DerivationRefused(
            REASON_ANCHOR_NOT_UNIQUE,
            f"{len(ambiguous)} club name(s) do not resolve 1:1",
            ambiguous={n: ids for n, ids in sorted(ambiguous.items())},
        )
    return {n: ids[0] for n, ids in by_name.items()}
