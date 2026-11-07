"""#10354 — the NFL division register: eight explicit Kalshi↔Polymarket pairs.

PILLARS: MATCHING · TRUTH. SHIP: the "NFL division front-runners" round-up
(#10357) can print one Bain Luck blend per division, because each division's
two venue markets are known, by name, to be the same market.

WHY A REGISTER AND NOT MATCHING. Alex, 2026-11-02: "build them as an explicit
eight-pair register listed in the PR, not fuzzy matching". The venues' own
structure is also not enough on its own. Polymarket's eight division events
carry the canonical key ``football:NFL:championship:2027`` (the classification
defect recorded in Fable's R4 on Oct 6), so a key join would pair them with the
Super Bowl. Kalshi names several clubs by a bare city ("Dallas"). So every
identity below is written down: the division, the season, each venue's own
event identifier, and, for each of the four clubs, the exact outcome name each
venue stores. Nothing is inferred from a title, a key, an alias table or the
calendar.

WHAT MAKES A DIVISION BLENDABLE (each failure is a ``Refusal`` with a reason
for the matching-defect report, never reader text):

* both venue rows are present, carry the registered identity, and are open;
* both are single-winner markets;
* SETTLEMENT: Kalshi's expected expiration falls at or before Polymarket's
  no-winner cutoff. Polymarket settles to ``Other`` if nobody wins by its
  cutoff; for the NAMED clubs the two markets are the same only while the
  division is decided inside that window. ``Other`` is never mapped to a club;
* each venue lists exactly the four registered clubs (Polymarket may add
  ``Other``), each with a price;
* ``futures_source_merge.blend_with_verdict``, unchanged, blends each club. If
  its divergence gate fires (the venues are 40+ points apart on one club), the
  pair is refused: two numbers that far apart are not two opinions on one
  market, and Alex's ruling is that such a division is a matching defect.

A blended club is as old as its oldest contributing price (R4, "When a number
is old").

Pure: plain values in, plain values out. Reads belong to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.utils.futures_source_merge import blend_with_verdict

__all__ = [
    "DivisionClub",
    "DivisionPair",
    "NFL_DIVISION_SEASON",
    "NFL_DIVISION_REGISTER",
    "VenueOutcome",
    "VenueBoard",
    "ClubBlend",
    "DivisionBlend",
    "Refusal",
    "register_identities",
    "compose_division",
    "compose_register",
    "board_from_row",
]

#: The season these pairs are for (decided in January 2027).
NFL_DIVISION_SEASON = "2026"


@dataclass(frozen=True)
class DivisionClub:
    #: The reader's name for the club ("Cowboys").
    club: str
    #: The outcome name Kalshi's market stores for it ("Dallas").
    kalshi_outcome: str
    #: The outcome name Polymarket's market stores for it ("Dallas Cowboys").
    polymarket_outcome: str


@dataclass(frozen=True)
class DivisionPair:
    division: str
    season: str
    #: Kalshi event ticker, which our row stores as ``external_id``.
    kalshi_event_ticker: str
    #: Polymarket provider event id, which our row stores as ``external_id``.
    polymarket_event_id: str
    clubs: tuple[DivisionClub, DivisionClub, DivisionClub, DivisionClub]


def _c(club: str, kalshi: str, polymarket: str) -> DivisionClub:
    return DivisionClub(club=club, kalshi_outcome=kalshi, polymarket_outcome=polymarket)


#: THE REGISTER. Eight pairs, 32 clubs. Read off production on 2026-11-02
#: (`GET /api/futures/{id}` for Kalshi rows 53671–53678 and Polymarket rows
#: 2248388/89/91/92/95 and 2279147/51/52) and Kalshi's own event listings.
#: A change to any line here is a matching change and is reviewed as one.
NFL_DIVISION_REGISTER: tuple[DivisionPair, ...] = (
    DivisionPair("AFC East", NFL_DIVISION_SEASON, "KXNFLAFCEAST-27", "232598", (
        _c("Bills", "Buffalo", "Buffalo Bills"),
        _c("Dolphins", "Miami", "Miami Dolphins"),
        _c("Patriots", "New England", "New England Patriots"),
        _c("Jets", "New York Jets", "New York Jets"),
    )),
    DivisionPair("AFC North", NFL_DIVISION_SEASON, "KXNFLAFCNORTH-27", "232603", (
        _c("Ravens", "Baltimore", "Baltimore Ravens"),
        _c("Bengals", "Cincinnati", "Cincinnati Bengals"),
        _c("Browns", "Cleveland", "Cleveland Browns"),
        _c("Steelers", "Pittsburgh", "Pittsburgh Steelers"),
    )),
    DivisionPair("AFC South", NFL_DIVISION_SEASON, "KXNFLAFCSOUTH-27", "232605", (
        _c("Texans", "Houston", "Houston Texans"),
        _c("Colts", "Indianapolis", "Indianapolis Colts"),
        _c("Jaguars", "Jacksonville", "Jacksonville Jaguars"),
        _c("Titans", "Tennessee", "Tennessee Titans"),
    )),
    DivisionPair("AFC West", NFL_DIVISION_SEASON, "KXNFLAFCWEST-27", "232614", (
        _c("Broncos", "Denver", "Denver Broncos"),
        _c("Chiefs", "Kansas City", "Kansas City Chiefs"),
        _c("Raiders", "Las Vegas", "Las Vegas Raiders"),
        _c("Chargers", "Los Angeles Chargers", "Los Angeles Chargers"),
    )),
    DivisionPair("NFC East", NFL_DIVISION_SEASON, "KXNFLNFCEAST-27", "232617", (
        _c("Cowboys", "Dallas", "Dallas Cowboys"),
        _c("Giants", "New York Giants", "New York Giants"),
        _c("Eagles", "Philadelphia", "Philadelphia Eagles"),
        _c("Commanders", "Washington", "Washington Commanders"),
    )),
    DivisionPair("NFC North", NFL_DIVISION_SEASON, "KXNFLNFCNORTH-27", "232622", (
        _c("Bears", "Chicago", "Chicago Bears"),
        _c("Lions", "Detroit", "Detroit Lions"),
        _c("Packers", "Green Bay", "Green Bay Packers"),
        _c("Vikings", "Minnesota", "Minnesota Vikings"),
    )),
    DivisionPair("NFC South", NFL_DIVISION_SEASON, "KXNFLNFCSOUTH-27", "232642", (
        _c("Falcons", "Atlanta", "Atlanta Falcons"),
        _c("Panthers", "Carolina", "Carolina Panthers"),
        _c("Saints", "New Orleans", "New Orleans Saints"),
        _c("Buccaneers", "Tampa Bay", "Tampa Bay Buccaneers"),
    )),
    DivisionPair("NFC West", NFL_DIVISION_SEASON, "KXNFLNFCWEST-27", "232647", (
        _c("Cardinals", "Arizona", "Arizona Cardinals"),
        _c("Rams", "Los Angeles Rams", "Los Angeles Rams"),
        _c("49ers", "San Francisco", "San Francisco 49ers"),
        _c("Seahawks", "Seattle", "Seattle Seahawks"),
    )),
)

#: Polymarket's no-winner outcome. Present on its boards; never a club.
_POLYMARKET_FIELD_OUTCOME = "Other"


def register_identities() -> list[tuple[str, str]]:
    """Every ``(source, external_id)`` the register names, for the caller's read."""
    out: list[tuple[str, str]] = []
    for pair in NFL_DIVISION_REGISTER:
        out.append(("kalshi", pair.kalshi_event_ticker))
        out.append(("polymarket", pair.polymarket_event_id))
    return out


@dataclass(frozen=True)
class VenueOutcome:
    name: str
    probability: Optional[float]
    observed_at: Optional[datetime]


@dataclass(frozen=True)
class VenueBoard:
    """One venue market's row and outcomes, copied off the DB as plain data."""

    market_id: int
    source: str
    external_id: str
    status: Optional[str]
    mutually_exclusive: Optional[bool]
    resolution_date: Optional[datetime]
    outcomes: Sequence[VenueOutcome] = field(default_factory=tuple)


@dataclass(frozen=True)
class ClubBlend:
    club: str
    probability: float
    #: The OLDEST of the two contributing prices; None if either is undated.
    observed_at: Optional[datetime]
    kalshi_probability: float
    polymarket_probability: float
    rule: str


@dataclass(frozen=True)
class DivisionBlend:
    division: str
    season: str
    kalshi_market_id: int
    polymarket_market_id: int
    clubs: tuple[ClubBlend, ...]

    @property
    def leader(self) -> ClubBlend:
        """Highest blended club; a tie keeps register order."""
        best = self.clubs[0]
        for c in self.clubs[1:]:
            if c.probability > best.probability:
                best = c
        return best

    @property
    def leaders(self) -> tuple[ClubBlend, ...]:
        """All clubs tied at the top within the whole-number percent the card prints (#11941)."""
        from app.utils.graded_card import rendered_percent

        lead = self.leader
        lead_pct = rendered_percent(lead.probability)
        if lead_pct is None:
            return (lead,)
        tied = tuple(
            c for c in self.clubs if rendered_percent(c.probability) == lead_pct
        )
        return tied or (lead,)


@dataclass(frozen=True)
class Refusal:
    division: str
    reason: str


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None or dt.tzinfo is None or dt.utcoffset() is None:
        return None
    return dt.astimezone(timezone.utc)


def _priced(board: VenueBoard) -> dict[str, VenueOutcome]:
    """Outcome name → outcome, refusing a board that names one outcome twice."""
    out: dict[str, VenueOutcome] = {}
    for o in board.outcomes:
        if o.name in out:
            raise ValueError(f"duplicate_outcome:{o.name}")
        out[o.name] = o
    return out


def compose_division(
    pair: DivisionPair,
    kalshi: Optional[VenueBoard],
    polymarket: Optional[VenueBoard],
) -> DivisionBlend | Refusal:
    """One division's blend from its two registered rows, or why not."""
    d = pair.division
    if kalshi is None:
        return Refusal(d, "kalshi_row_missing")
    if polymarket is None:
        return Refusal(d, "polymarket_row_missing")
    if (kalshi.source or "").lower() != "kalshi" or kalshi.external_id != pair.kalshi_event_ticker:
        return Refusal(d, "kalshi_identity_mismatch")
    if (polymarket.source or "").lower() != "polymarket" or polymarket.external_id != pair.polymarket_event_id:
        return Refusal(d, "polymarket_identity_mismatch")
    if kalshi.status != "open":
        return Refusal(d, "kalshi_not_open")
    if polymarket.status != "open":
        return Refusal(d, "polymarket_not_open")
    if kalshi.mutually_exclusive is False or polymarket.mutually_exclusive is False:
        return Refusal(d, "not_single_winner")
    if kalshi.mutually_exclusive is not True or polymarket.mutually_exclusive is not True:
        return Refusal(d, "single_winner_unknown")

    k_expiry = _aware(kalshi.resolution_date)
    p_cutoff = _aware(polymarket.resolution_date)
    if k_expiry is None or p_cutoff is None:
        return Refusal(d, "settlement_undated")
    if k_expiry > p_cutoff:
        return Refusal(d, "settles_after_polymarket_cutoff")

    try:
        k_out = _priced(kalshi)
        p_out = _priced(polymarket)
    except ValueError as err:
        return Refusal(d, str(err))

    k_expected = {c.kalshi_outcome for c in pair.clubs}
    p_expected = {c.polymarket_outcome for c in pair.clubs}
    if set(k_out) != k_expected:
        return Refusal(d, "kalshi_outcomes_differ_from_register")
    if set(p_out) - {_POLYMARKET_FIELD_OUTCOME} != p_expected:
        return Refusal(d, "polymarket_outcomes_differ_from_register")
    other = p_out.get(_POLYMARKET_FIELD_OUTCOME)
    if other is not None and other.probability is not None and other.probability >= 0.01:
        return Refusal(d, "polymarket_field_outcome_priced")

    clubs: list[ClubBlend] = []
    for c in pair.clubs:
        ko, po = k_out[c.kalshi_outcome], p_out[c.polymarket_outcome]
        if ko.probability is None or po.probability is None:
            return Refusal(d, f"unpriced:{c.club}")
        value, divergence, rule = blend_with_verdict([
            {"source": "kalshi", "probability": ko.probability},
            {"source": "polymarket", "probability": po.probability},
        ])
        if value is None or divergence is not None:
            return Refusal(d, f"venues_disagree:{c.club}")
        k_at, p_at = _aware(ko.observed_at), _aware(po.observed_at)
        clubs.append(ClubBlend(
            club=c.club,
            probability=float(value),
            observed_at=min(k_at, p_at) if k_at and p_at else None,
            kalshi_probability=float(ko.probability),
            polymarket_probability=float(po.probability),
            rule=rule,
        ))

    return DivisionBlend(
        division=d,
        season=pair.season,
        kalshi_market_id=kalshi.market_id,
        polymarket_market_id=polymarket.market_id,
        clubs=tuple(clubs),
    )


def compose_register(
    boards: Iterable[VenueBoard],
) -> tuple[list[DivisionBlend], list[Refusal]]:
    """Every registered division, blended or refused, in register order.

    A venue identity held by more than one row is refused for that division
    rather than resolved by picking one.
    """
    by_identity: dict[tuple[str, str], list[VenueBoard]] = {}
    for b in boards:
        by_identity.setdefault(((b.source or "").lower(), b.external_id), []).append(b)

    blends: list[DivisionBlend] = []
    refusals: list[Refusal] = []
    for pair in NFL_DIVISION_REGISTER:
        k_rows = by_identity.get(("kalshi", pair.kalshi_event_ticker), [])
        p_rows = by_identity.get(("polymarket", pair.polymarket_event_id), [])
        if len(k_rows) > 1:
            refusals.append(Refusal(pair.division, "kalshi_identity_ambiguous"))
            continue
        if len(p_rows) > 1:
            refusals.append(Refusal(pair.division, "polymarket_identity_ambiguous"))
            continue
        result = compose_division(pair, k_rows[0] if k_rows else None, p_rows[0] if p_rows else None)
        (refusals if isinstance(result, Refusal) else blends).append(result)  # type: ignore[arg-type]
    return blends, refusals


def board_from_row(row: Mapping[str, Any]) -> VenueBoard:
    """A ``VenueBoard`` from a plain mapping (the route's read, or a fixture)."""

    def _dt(v: Any) -> Optional[datetime]:
        if isinstance(v, datetime):
            return v
        if isinstance(v, str) and v.strip():
            try:
                return datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    return VenueBoard(
        market_id=int(row["market_id"]),
        source=str(row.get("source") or ""),
        external_id=str(row.get("external_id") or ""),
        status=row.get("status"),
        mutually_exclusive=row.get("mutually_exclusive"),
        resolution_date=_dt(row.get("resolution_date")),
        outcomes=tuple(
            VenueOutcome(
                name=str(o.get("name") or ""),
                probability=(float(o["probability"]) if o.get("probability") is not None else None),
                observed_at=_dt(o.get("last_updated") or o.get("observed_at")),
            )
            for o in (row.get("outcomes") or [])
        ),
    )
