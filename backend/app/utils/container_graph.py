"""The closed vocabularies of the event graph: containers, edges, participants.

#2927 / ``ARTIFACT-LANE1B-CONTAINERS-SPEC.md``. This module is the single place
the string values live. It **imports nothing** from ``app`` and must stay that
way — ``app/models/models.py`` imports it, so any import back into the app
package creates a cycle at model-definition time (the same rule
``app/utils/sport_keys.py`` lives under, gotcha #3).

WHY ALLOWLISTS AND NOT DB ENUMS. Postgres ``ENUM`` types make adding a value a
migration, and this vocabulary is expected to grow (a ``card`` container for
fight nights, a ``draft``, whatever the Oscars turns out to need). The columns
are ``VARCHAR`` and the closed set is enforced here, in Python, by the writers.

WHY ALLOWLISTS AND NOT DENYLISTS. A denylist admits every state nobody thought
of. On ``events.status`` that mistake rejected the rare terminal value
(``completed``, 15,731 rows) and admitted the dominant one (``closed``,
212,289) — the check read as working for a year. Every set below is an
allowlist and every validator fails closed on an unknown value.

WHAT IS **NOT** HERE. No membership policy, no classification logic, no
scoring. Assembly decides what a member is; this module only says which words
it is allowed to write down.
"""

from typing import Final, FrozenSet

# --------------------------------------------------------------------------
# containers
# --------------------------------------------------------------------------

#: What a container *is*. A hub renders one of these.
CONTAINER_KINDS: Final[FrozenSet[str]] = frozenset(
    {
        "tournament",  # US Open 2026, and also "US Open 2026 — Men's Doubles"
        "award_show",  # the Oscars
        "card",  # a fight card
        "draft",  # the NFL draft
        "season",  # a league season
        "series",  # a playoff series
    }
)

#: A container's own state. **The authority decides this, never inference from
#: children** (D27 / spec §1): a container is ``final`` when its authority says
#: the tournament is over. Deriving it from "the last child we know about
#: finished" is what makes a hub go dark early on a fixture we missed.
CONTAINER_STATUSES: Final[FrozenSet[str]] = frozenset(
    {"scheduled", "live", "final", "cancelled"}
)

#: What kind of provider id an anchor holds. **Explicit, never inferred from
#: the shape of the string** (D55) — the digit-count inference is exactly how
#: the StatPal 6-digit/10-digit fixture ids collided under one column name.
ANCHOR_ID_KINDS: Final[FrozenSet[str]] = frozenset(
    {"tournament", "league", "series", "event_slug", "tag"}
)

#: Providers that can name a container.
ANCHOR_PROVIDERS: Final[FrozenSet[str]] = frozenset(
    {"espn", "statpal", "datagolf", "kalshi", "polymarket", "odds_api"}
)

# --------------------------------------------------------------------------
# event_edges
# --------------------------------------------------------------------------

#: What an edge endpoint points at. There is no FK behind these (the type
#: varies), so the nightly invariant check in the reconciliation rail is what
#: buys the integrity back — see ``EDGE_NODE_TABLES``.
EDGE_NODE_TYPES: Final[FrozenSet[str]] = frozenset({"container", "event", "market"})

#: The table each node type resolves to. The invariant check reads this rather
#: than a hand-written CASE, so a new node type cannot be added without the
#: check learning about it in the same commit.
EDGE_NODE_TABLES: Final[dict] = {
    "container": "containers",
    "event": "events",
    "market": "futures_markets",
}

#: ``contains`` — the membership relation, the one assembly writes.
#: ``same_as`` — cross-source identity. **The drain's ledger.** Ruling 048 is
#: unchanged by this table: an id-less claim still never absorbs, and a
#: ``same_as`` edge *records* a correspondence an anchored id already proved —
#: it does not create one. Assembly never writes this kind (spec §6.4); twins
#: stay lane1's under #2693 / D39.
#: ``derived_from`` — a prop from its match.
#: ``advances_to`` — bracket progression, R128 → R64.
EDGE_KINDS: Final[FrozenSet[str]] = frozenset(
    {"contains", "same_as", "derived_from", "advances_to"}
)

#: Kinds that assembly is permitted to write. Narrower than ``EDGE_KINDS`` on
#: purpose, and enforced at the writer rather than left as prose.
ASSEMBLY_WRITABLE_KINDS: Final[FrozenSet[str]] = frozenset({"contains"})

#: The section a member lands in, computed once at assembly from
#: ``market_shape`` + naming and **stored on the edge**, so the hub reads
#: sections instead of inferring them and ux never classifies (doctrine §C.4).
EDGE_CLASSES: Final[FrozenSet[str]] = frozenset(
    {
        "match_winner",  # one fixture's winner
        "advancement",  # "reaches R16" ladders
        "title",  # outright winner of a draw
        "prop",  # player/match props
        "side_question",  # "will Sinner actually play?"
        "doubles",  # doubles fixtures — authority-sourced only
        "unclassified",  # assembled but unnamed. NEVER dropped. See below.
    }
)

#: ``unclassified`` is a real class and is never dropped on the floor: a member
#: we could not classify is a member we would otherwise silently lose, which is
#: the failure this program exists to end. It gets a section last, or a count,
#: but it is never invisible. Named as a constant so a reader of the hub code
#: meets the rule rather than a bare string.
CLASS_UNCLASSIFIED: Final[str] = "unclassified"

#: Where an edge came from. ``register`` is the committed US Open JSON, which
#: this program demotes from "the truth" to *one edge source among several*.
EDGE_SOURCES: Final[FrozenSet[str]] = frozenset(
    {
        "venue_grouping",  # Kalshi series/event tickers, Polymarket slugs/tags
        "authority_tournament_id",  # ESPN / StatPal / DataGolf tournament ids
        "matcher",
        "human",
        "register",  # backend/data/tournament_registers/*.json
    }
)

# --------------------------------------------------------------------------
# event_participants
# --------------------------------------------------------------------------

#: Which side of the event. One shape covers a doubles match (two rows per
#: side), a golf field (many rows, ``field``), an award category (many
#: ``nominee`` rows) and a fight-card bout.
PARTICIPANT_SIDES: Final[FrozenSet[str]] = frozenset(
    {"home", "away", "field", "nominee", "a", "b"}
)

PARTICIPANT_ENTITY_TYPES: Final[FrozenSet[str]] = frozenset(
    {"team", "player", "person", "other"}
)

PARTICIPANT_ROLES: Final[FrozenSet[str]] = frozenset(
    {"competitor", "nominee", "partner"}
)


# --------------------------------------------------------------------------
# validators — every one fails closed
# --------------------------------------------------------------------------


class ContainerVocabularyError(ValueError):
    """An unknown value was offered for a closed vocabulary.

    Raised, never swallowed and never silently coerced to a default: a member
    written under a misspelled class is a member in the wrong section, which
    looks exactly like a right answer.
    """


def _require(value: str, allowed: FrozenSet[str], field: str) -> str:
    if value not in allowed:
        raise ContainerVocabularyError(
            f"{field}={value!r} is not one of {sorted(allowed)}"
        )
    return value


def validate_container_kind(value: str) -> str:
    return _require(value, CONTAINER_KINDS, "kind")


def validate_container_status(value: str) -> str:
    return _require(value, CONTAINER_STATUSES, "status")


def validate_anchor_id_kind(value: str) -> str:
    return _require(value, ANCHOR_ID_KINDS, "id_kind")


def validate_anchor_provider(value: str) -> str:
    return _require(value, ANCHOR_PROVIDERS, "provider")


def normalize_anchor_sport(value):
    """Fold ``sport`` to exactly one spelling per namespace. CERT-2006 follow-up.

    ``container_provider_anchors``' unique index is
    ``(provider, sport, id_kind, provider_id) NULLS NOT DISTINCT``. The
    ``NULLS NOT DISTINCT`` makes "no sport" a single namespace instead of one
    per row — but only if "no sport" is written exactly one way. Two spellings
    reopen the hole the index was widened to close:

    * ``''`` is not NULL, so an empty string is a THIRD namespace beside NULL
      and the real sports. Two anchors spelling it differently could then claim
      one provider id without colliding — the silent no-op D55 forbids, rebuilt
      out of whitespace.
    * ``'Tennis'`` and ``'tennis'`` are the same bug wearing different case.

    Returns ``None`` for anything blank, and a stripped, lower-cased string
    otherwise.

    WHY CANONICALISE HERE RATHER THAN REFUSE, when every other validator in
    this module fails closed. The two jobs are different. ``kind``, ``status``
    and ``id_kind`` are CLOSED vocabularies, where an unexpected value means an
    unexpected source and refusing is the informative answer. ``sport`` is an
    OPEN namespace key — new sports arrive without a code change — so refusing
    a variant spelling would just move the canonicalisation to every caller,
    and the first caller that forgot would write the duplicate namespace this
    exists to prevent. A non-string is still a type error and still raises.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContainerVocabularyError(
            f"sport must be a string or None, got {type(value).__name__}"
        )
    folded = value.strip().lower()
    return folded or None


def validate_node_type(value: str, field: str = "node_type") -> str:
    return _require(value, EDGE_NODE_TYPES, field)


def validate_edge_source(value: str) -> str:
    return _require(value, EDGE_SOURCES, "source")


def validate_participant_side(value: str) -> str:
    return _require(value, PARTICIPANT_SIDES, "side")


def validate_participant_entity_type(value: str) -> str:
    return _require(value, PARTICIPANT_ENTITY_TYPES, "entity_type")


def validate_edge_kind_and_class(kind: str, edge_class) -> tuple:
    """Validate an edge's ``kind``/``class`` pair together, because the rule
    that binds them is a pair rule.

    ``class`` is **required when kind='contains'** (spec §2) — a member with no
    section is a member the hub cannot render — and is **refused on every other
    kind**, because a class on a ``same_as`` edge would be a section assignment
    nobody will ever read, sitting in the one index the hub scans.

    The database carries the required-half of this as a CHECK constraint. The
    refused-half lives only here: a CHECK could express it too, but it would
    have to be rewritten by a migration every time a kind is added, and the
    value of catching it at the writer is the same.
    """
    _require(kind, EDGE_KINDS, "kind")
    if kind == "contains":
        if edge_class is None:
            raise ContainerVocabularyError(
                "kind='contains' requires a class; use "
                f"{CLASS_UNCLASSIFIED!r} when it could not be classified, "
                "never NULL — an unclassified member must stay visible"
            )
        _require(edge_class, EDGE_CLASSES, "class")
    elif edge_class is not None:
        raise ContainerVocabularyError(
            f"class={edge_class!r} is only meaningful on kind='contains', "
            f"not on kind={kind!r}"
        )
    return kind, edge_class


def validate_confidence(value) -> float:
    """``0.000..1.000`` inclusive. The DB carries this as a CHECK too; this
    catches it before the round-trip so the error names the field."""
    as_float = float(value)
    if not (0.0 <= as_float <= 1.0):
        raise ContainerVocabularyError(
            f"confidence={value!r} is outside 0.000..1.000"
        )
    return as_float
