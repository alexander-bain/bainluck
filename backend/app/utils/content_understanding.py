"""CU-1 clause (2): what KIND of question is this market, written down.

#5273. Clause (4) taught `PolymarketMarket` to retain Gamma's own
``sportsMarketType``; it travels on the DTO and is persisted **nowhere**, so
nothing downstream of the poller can read it. This module is the persist half:
it turns "our classifier's reading of the question" plus "the venue's own label"
into one small blob that is stamped on the market row, and it names the single
rule by which a later reader turns that blob into an eligibility record's
``semantic_type``.

── WHY A BLOB AND NOT A COLUMN ──────────────────────────────────────────────

The amendment names two locations as alternatives — a ``semantic_market_type``
column, or ``market_metadata['content_understanding_v1']``. The subkey is taken
deliberately: a new column is an Alembic migration, and a migration-class sha is
attended-merge-only (D45 / standing notice 47(b)), where PR #3179 sat three days.
``market_metadata`` is never served wholesale — every consumer reads a *named*
subkey and frontend consumers of the column are zero — so this key is additive
and invisible to every client. Writes MUST go through Core ``update()`` or the
insert's own merge idiom, never ORM attribute assignment (gotcha #4).

🔴 **NEVER `futures_markets.market_type`.** That column is Queue #194's
presentation shape (``claim|quantity|duel|field|container_member|unshaped``) and
is read by `precompute_calibration`. This is a second, orthogonal question about
the same row, and writing it there would silently retype the calibration input.

── WHAT THIS DOES NOT DO ────────────────────────────────────────────────────

It does not gate. Nothing here refuses a market, changes an admission, or moves
a published number; `admissible_as_blend_speaker` behaves exactly as it did.
This clause writes down an understanding so that a quarantine consumer can be
built on a measured population rather than on a guess, and so a reader auditing
a blend number can see what kind of question produced it.
"""

from typing import Any, Optional

from app.services.polymarket_api import is_full_contest_winner_type
from app.utils.game_market_class import classify_game_market_class

#: The `market_metadata` subkey. Top level and versioned in its own name: the
#: census idiom for "does this row carry an understanding" is jsonb ``?``, which
#: does not see nested keys, and a v2 with a different shape must be able to sit
#: beside a v1 rather than silently reinterpret it.
CONTENT_UNDERSTANDING_KEY = "content_understanding_v1"

CONTENT_UNDERSTANDING_VERSION = 1

#: Named once so the writer and every test agree on the string.
CONTENT_UNDERSTANDING_RULE = "content_understanding@5273"

#: How our classifier and the venue's label stand to each other.
CORROBORATED = "corroborated"
CONTRADICTED = "contradicted"
UNCONFIRMED = "unconfirmed"

#: Our own classifier's value for "this market decides who wins the contest".
FULL_CONTEST_WINNER_CLASS = "moneyline"

#: Suffix marking a semantic type the venue's own label DISPUTES. It rides the
#: string rather than becoming a second field for the same reason
#: `ineligible_record` rides its reason in ``rule``: the reader's decision is
#: binary, and a parallel field nobody branches on is a field that drifts. Read
#: it with `record_semantic_type`/`is_disputed`, never by hand.
DISPUTED_SUFFIX = ":disputed"


def build_content_understanding(
    *,
    name: Optional[str],
    external_id: Optional[str] = None,
    sport: Optional[str] = None,
    sports_market_type: Optional[str] = None,
) -> Optional[dict]:
    """Our reading of the question, and how the venue's own label stands to it.

    Returns ``None`` when there is nothing to say — an unnamed market. The
    caller stamps this straight into ``market_metadata``, and an empty object
    there would overwrite a populated key on re-ingest (`sub_market_metadata`'s
    own rule, and the reason it returns ``None`` rather than ``{}``).

    ── THE VENUE'S LABEL CORROBORATES; IT NEVER GATES ───────────────────────

    Standing notice 40: a title match alone is only a CANDIDATE, and it enters
    the container when a *second, independent* signal agrees. Gamma's
    ``sportsMarketType`` is that signal — a venue-authored classification, not a
    re-reading of the same title we already read.

    🔴 It is **absent on 21%** of markets (measured, 100 markets 2026-09-12; see
    `PolymarketMarket`). So absence is `UNCONFIRMED` and is NOT evidence against
    the market. `is_full_contest_winner_type` returns False for a missing label,
    and reading that False as "the venue says no" would fail closed on a fifth
    of the population — which is why the absent case is branched on FIRST here
    and never reaches the comparison.

    The comparison is asked on the one question CU-1 exists to answer — *is this
    the full-contest winner?* — rather than by mapping Gamma's 13-value open set
    onto our six-value taxonomy. Those vocabularies do not correspond (Gamma
    splits `soccer_exact_score` from `totals`; we split `player_prop` from
    `team_prop`), so a value-by-value map would invent disagreements that mean
    nothing. Agreement on the winner question is the claim we actually make.

    🔴 The disagreement that matters is `child_moneyline`: winner-SHAPED, and a
    Map/period winner rather than the contest's. Our title recognizer reads
    `… - Map 1 Winner` as a winner (it carries the word), Gamma says
    `child_moneyline`, `is_full_contest_winner_type` is exact-match False, and
    the pair lands `CONTRADICTED` — which is precisely the #5432/#5311 defect
    class (a derivative published as the match result) being caught at ingest.
    """
    if not name:
        return None

    semantic_type = classify_game_market_class(name, external_id, sport)

    understanding: dict[str, Any] = {
        "v": CONTENT_UNDERSTANDING_VERSION,
        "semantic_type": semantic_type,
        "rule": CONTENT_UNDERSTANDING_RULE,
    }

    if sports_market_type is None:
        # Absent (or null — the venue serves both as None and neither can
        # corroborate, so they are owed the same answer). No `venue_type` key:
        # storing a null would be a claim that the venue said something.
        understanding["agreement"] = UNCONFIRMED
        return understanding

    understanding["venue_type"] = sports_market_type
    ours_says_winner = semantic_type == FULL_CONTEST_WINNER_CLASS
    venue_says_winner = is_full_contest_winner_type(sports_market_type)
    understanding["agreement"] = (
        CORROBORATED if ours_says_winner == venue_says_winner else CONTRADICTED
    )
    return understanding


def understanding_from_metadata(market_metadata: Any) -> Optional[dict]:
    """Read the understanding out of a row's ``market_metadata``, or ``None``.

    NEVER RAISES, and for the same load-bearing reason `from_entry` never does:
    this runs on the request path over a JSONB column that provably holds
    several shapes at once, and a malformed subkey must degrade to "no
    understanding" rather than take down a page.

    A record from a FUTURE version reads as absent: this reader cannot interpret
    what it does not know, and a rolling deploy routinely puts an old reader in
    front of a new writer.
    """
    if not isinstance(market_metadata, dict):
        return None
    understanding = market_metadata.get(CONTENT_UNDERSTANDING_KEY)
    if not isinstance(understanding, dict):
        return None

    version = understanding.get("v")
    if not isinstance(version, int) or isinstance(version, bool):
        return None
    if version > CONTENT_UNDERSTANDING_VERSION:
        return None

    semantic_type = understanding.get("semantic_type")
    if not isinstance(semantic_type, str) or not semantic_type:
        return None
    return understanding


def record_semantic_type(understanding: Optional[dict]) -> Optional[str]:
    """THE rule turning a stored understanding into a record's ``semantic_type``.

    Written once here so a caller cannot half-remember it — the same reason
    `contributing_market_ids` exists next door.

    A `CONTRADICTED` understanding is reported as ``"<class>:disputed"`` rather
    than as a clean class. The record substantiates a served number, so a type
    the venue's own label disputes must not read on it as settled fact; a reader
    auditing "is this the match winner?" would otherwise see a bare
    ``moneyline`` on exactly the rows where the two signals disagree, and a
    second query is not a defence a request path gets to make.

    `UNCONFIRMED` is NOT disputed — absence is not disagreement (21% of the
    population) — so it reports the plain class.
    """
    if not understanding:
        return None
    semantic_type = understanding.get("semantic_type")
    if not isinstance(semantic_type, str) or not semantic_type:
        return None
    if understanding.get("agreement") == CONTRADICTED:
        return f"{semantic_type}{DISPUTED_SUFFIX}"
    return semantic_type


def is_disputed(semantic_type: Optional[str]) -> bool:
    """Does this record ``semantic_type`` carry the venue's disagreement?

    The read side of `record_semantic_type`'s encoding, so no caller writes the
    suffix test by hand and drifts from the writer.
    """
    return bool(semantic_type) and semantic_type.endswith(DISPUTED_SUFFIX)


def semantic_type_for_market(market: Any) -> Optional[str]:
    """A market row's record ``semantic_type``, straight off its metadata.

    The one call a mint site makes. ``None`` whenever the row carries no
    readable understanding, which is every row until the poller has re-served it
    — so the field stays absent rather than becoming a fabricated default, and
    `to_entry` drops it exactly as it does today.
    """
    return record_semantic_type(
        understanding_from_metadata(getattr(market, "market_metadata", None))
    )
