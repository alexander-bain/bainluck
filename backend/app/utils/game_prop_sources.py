"""Typed NFL prop rows and held-pair selection for #12581.

The existing typed predicate reader owns player/stat/line parsing. Standard
NFL and protected contracts stay distinct. A cross-venue participation-rule
hold selects one book; it never averages the incompatible contracts.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from app.utils.event_props_matrix import STAT_TABLE, _team_forms, type_prop_row
from app.utils.source_mark import _probability, no_source_mark

# Verified against the actual KXNFL parents and Polymarket event 1356913.
# Kept local to this slice: the DURING matrix's closed stat table is unchanged.
NFL_STATS = {
    "passing yards": "passing_yards",
    "passing touchdowns": "passing_touchdowns",
    "receiving yards": "receiving_yards",
    "rushing yards": "rushing_yards",
    "touchdowns": "touchdowns",
}
NFL_LABELS = {
    "passing_yards": "Passing Yards",
    "passing_touchdowns": "Passing Touchdowns",
    "receiving_yards": "Receiving Yards",
    "rushing_yards": "Rushing Yards",
    "touchdowns": "Touchdowns",
}
_LABELS = {r[0]: r[1] for r in STAT_TABLE} | NFL_LABELS
_VERIFIED_PARTICIPATION_HOLDS = frozenset(
    {
        "passing_touchdowns",
        "receiving_yards",
        "rushing_yards",
        "touchdowns",
    }
)
_PROTECTED_SERIES = {
    "KXNFLPASSTDSPROT": "passing_touchdowns",
    "KXNFLRECYDSPROT": "receiving_yards",
    "KXNFLRSHYDSPROT": "rushing_yards",
    "KXNFLTDPROT": "touchdowns",
}


def select_standard_prop_rows(
    rows: list[dict], *, markets: Mapping[int, Any], sport_key: str | None
) -> tuple[list[dict], list[dict]]:
    """157-A: omit verified Protected contracts from every prop presentation.

    Select by the venue's series identity, not a name suffix or a successful
    player/stat parse. A Protected-only rung is also withheld; it never fills
    in for an absent standard contract. The caller runs this before copying
    DURING/AFTER inputs or folding prices. Separate diagnostics retain the
    original quote/grade evidence without adding a reader-facing prop row.
    """
    if sport_key != "americanfootball_nfl":
        return rows, []
    selected, withheld = [], []
    for row in rows:
        market = markets.get(row.get("_market_id"))
        ticker = getattr(market, "external_id", "") or ""
        if (
            getattr(market, "source", None) != "kalshi"
            or ticker.split("-", 1)[0] not in _PROTECTED_SERIES
        ):
            selected.append(row)
            continue
        withheld.append(
            {
                "reason": "protected_contract_not_standard",
                "contract_key": "kalshi_protected",
                "market_id": row.get("_market_id"),
                "external_id": ticker,
                "evidence": deepcopy(
                    {
                        key: row[key]
                        for key in (
                            "outcome_name",
                            "contributor_outcome_ids",
                            "observed_at",
                            "over_probability",
                            "source_mark",
                            "hit",
                            "actual",
                            "is_winner",
                            "resolution_source",
                            "player",
                            "stat",
                            "line",
                        )
                        if key in row
                    }
                ),
            }
        )
    return selected, withheld


def _typed(
    row: dict, market: Any, player_and_stat: Callable, team_forms: set
) -> tuple[dict, str | None]:
    ticker = getattr(market, "external_id", "") or ""
    protected = (
        _PROTECTED_SERIES.get(ticker.split("-", 1)[0])
        if getattr(market, "source", None) == "kalshi"
        else None
    )
    name = row.get("market_name") or ""
    # Only a verified protected series may shed the suffix for parsing.
    if protected and name.casefold().endswith(" (protected)"):
        name = name[: -len(" (protected)")]
    typed = type_prop_row(
        name,
        row.get("outcome_name"),
        player_and_stat,
        team_forms,
        additional_stats=NFL_STATS,
    )
    if protected and typed.get("stat_key") != protected:
        typed = {"refused": "protected_stat_mismatch"}
    return typed, protected


def annotate_prop_fields(
    rows: list[dict],
    *,
    markets: Mapping[int, Any],
    player_and_stat: Callable,
    home_team: str | None,
    away_team: str | None,
) -> None:
    """Name the predicate on the served over axis, or retain an explicit refusal.

    This reuses the closed typed-stat vocabulary. An ambiguous predicate is
    retained unchanged, with null typed parts; it is never guessed or dropped.
    Protected labels precede all grouping so they cannot be averaged with a
    standard contract, including on finished games.
    """
    forms = _team_forms(home_team, away_team)
    for row in rows:
        typed, protected = _typed(
            row, markets.get(row.get("_market_id")), player_and_stat, forms
        )
        if "refused" in typed:
            row.update(
                player=None,
                stat=None,
                line=None,
                side=None,
                period=None,
                typing_refusal=typed["refused"],
            )
            continue
        stat = typed["stat_key"]
        label = _LABELS[stat] + (" (Protected)" if protected else "")
        count = typed["count"] + (typed["kind"] == "count_at_most")
        row.update(
            player={"key": typed["subject_key"], "name": typed["subject_label"]},
            stat={"key": stat + ("_protected" if protected else ""), "label": label},
            line={"kind": "count_at_least", "value": count, "label": f"{count}+"},
            side="over",
            period="full_game",
        )
        if protected:
            row["market_name"] = f"{away_team} vs {home_team}: {label}"


def _book_width(row: dict, legs: Mapping[int, Any]) -> float:
    widths = []
    for oid in row.get("contributor_outcome_ids", []):
        leg = legs.get(oid)
        bid = _probability(getattr(leg, "current_yes_bid", None))
        ask = _probability(getattr(leg, "current_yes_ask", None))
        if bid is None or ask is None or ask == 0 or bid > ask:
            return float("inf")
        widths.append(ask - bid)
    return round(max(widths), 10) if widths else float("inf")


def _shape_entry(
    row: dict,
    typed: dict,
    protected: bool,
    entries: list[tuple[dict, dict, bool]],
    home_team: str | None,
    away_team: str | None,
) -> dict:
    """The same names and over-axis prices before and after settlement."""
    result = dict(row)
    stat = typed["stat_key"]
    count = typed["count"] + (typed["kind"] == "count_at_most")
    label = _LABELS[stat] + (" (Protected)" if protected else "")
    result.update(
        player={"key": typed["subject_key"], "name": typed["subject_label"]},
        stat={"key": stat + ("_protected" if protected else ""), "label": label},
        line={"kind": "count_at_least", "value": count, "label": f"{count}+"},
        side="over",
        period="full_game",
        contract_key="kalshi_protected" if protected else str(row.get("source")),
        market_name=f"{away_team} vs {home_team}: {label}",
        outcome_name=f"{typed['subject_label']}: {count}+",
        threshold=count,
        represented_outcome_ids=sorted(
            {
                oid
                for entry in entries
                for oid in entry[0].get("contributor_outcome_ids", [])
            }
        ),
        _inverted=False,
        all_sources=[row["source"]],
        source_count=1,
    )
    if typed["side"] == "under" and isinstance(result.get("movement"), (int, float)):
        result["movement"] = -result["movement"]
    # Installed SourceLabels shows no pill for this compatibility key. Actual
    # venue provenance stays in the mark, including for a finished card.
    if row.get("source") == "polymarket":
        result["source"] = "bainluck"
    return result


def shape_nfl_prop_rows(
    rows: list[dict],
    *,
    markets: Mapping[int, Any],
    legs: Mapping[int, Any],
    player_and_stat: Callable,
    home_team: str | None,
    away_team: str | None,
    sport_key: str | None,
    orient_under_verdict: Callable[[dict], dict],
) -> tuple[list[dict], list[dict]]:
    """One standard row per typed prop; protected remains a separate family.

    The hold records name every discarded contributor. A source-only prop
    remains present, including Polymarket rows older apps couldn't parse.
    Untyped rows are left intact. A graded pair uses the existing Kalshi-first
    preference, never a price or verdict average. Both verdicts stay in holds.
    A graded Polymarket book uses its Over leg (or reorients its lone Under),
    retaining both leg identities and the existing grade without re-grading.
    """
    if sport_key != "americanfootball_nfl":
        return rows, []
    team_forms = _team_forms(home_team, away_team)
    groups: dict[tuple, list[tuple[dict, dict, bool]]] = {}
    untouched = []
    for row in rows:
        market = markets.get(row.get("_market_id"))
        typed, protected_stat = _typed(row, market, player_and_stat, team_forms)
        if "refused" in typed or typed["stat_key"] not in _LABELS:
            untouched.append(row)
            continue
        if protected_stat is not None and protected_stat != typed["stat_key"]:
            untouched.append(row)
            continue
        # Installed readers group by the full market name. Name the family
        # before the grade/live split so one ladder cannot split in mid-game.
        label = _LABELS[typed["stat_key"]] + (" (Protected)" if protected_stat else "")
        row = {**row, "market_name": f"{away_team} vs {home_team}: {label}"}
        count = typed["count"] + (typed["kind"] == "count_at_most")
        key = (typed["subject_key"], typed["stat_key"], count, bool(protected_stat))
        entry = (row, typed, bool(protected_stat))
        groups.setdefault(key, []).append(entry)

    selected = []
    held = []
    for (player, stat, count, protected), entries in groups.items():
        # First choose one own-side leg per venue/market. A genuine over/yes
        # leg outranks the complemented under leg of that SAME book.
        books: dict[tuple, tuple[dict, dict, bool]] = {}
        book_entries: dict[tuple, list[tuple[dict, dict, bool]]] = {}
        for entry in entries:
            row, typed, _ = entry
            key = (row.get("source"), row.get("_market_id"))
            book_entries.setdefault(key, []).append(entry)
            previous = books.get(key)
            if previous is None or (
                typed["side"] == "over" and previous[1]["side"] != "over"
            ):
                books[key] = entry
        has_grade = any(
            e[0].get("resolution_source") is not None or e[0].get("hit") is not None
            for e in entries
        )
        shaped_books = {}
        for key, (row, typed, _) in books.items():
            own_entries = book_entries[key]
            result = _shape_entry(
                row, typed, protected, own_entries, home_team, away_team
            )
            if typed["side"] == "under" and any(
                e[0].get("resolution_source") is not None or e[0].get("hit") is not None
                for e in own_entries
            ):
                # Reorient this book's verdict once. The existing route gate
                # preserves void/retraction refusals; no result is inferred.
                result.update(orient_under_verdict(row))
                if row.get("hit") is not None:
                    result["hit"] = not row["hit"]
                elif row.get("source_mark", {}).get("state") == "settled":
                    won = result.get("is_winner")
                    result["source_mark"] = (
                        {
                            **row["source_mark"],
                            "settled": {
                                **row["source_mark"]["settled"],
                                "result": "Won" if won else "Lost",
                            },
                        }
                        if won is not None
                        else no_source_mark("settled_verdict_unproved")
                    )
            shaped_books[key] = result
        # No book width after settlement. Preserve the existing Kalshi-first
        # tie-break even if only one venue has graded, keeping one rung in
        # every state. The hold below retains each venue's own verdict.
        chosen = min(
            books.values(),
            key=lambda e: (
                0 if has_grade else _book_width(e[0], legs),
                e[0].get("source") != "kalshi",
                e[0].get("_market_id") or 0,
            ),
        )
        row, typed, _ = chosen
        result = dict(shaped_books[(row.get("source"), row.get("_market_id"))])
        result["represented_outcome_ids"] = sorted(
            {oid for e in entries for oid in e[0].get("contributor_outcome_ids", [])}
        )
        selected.append(result)

        venues = {entry[0].get("source") for entry in entries}
        if len(venues) > 1:
            width = _book_width(row, legs)
            known_widths = [
                _book_width(entry[0], legs)
                for entry in books.values()
                if _book_width(entry[0], legs) != float("inf")
            ]
            selection = "book_width_unknown"
            if has_grade:
                selection = "settled_source_preference"
            elif len(known_widths) == 1:
                selection = "only_known_book"
            elif known_widths:
                selection = (
                    "book_width_tie"
                    if known_widths.count(width) > 1
                    else "tighter_book"
                )
            held.append(
                {
                    "player": player,
                    "stat": stat,
                    "at_least": count,
                    "reason": (
                        "participation_rule_differs"
                        if stat in _VERIFIED_PARTICIPATION_HOLDS
                        else "contract_equivalence_unverified"
                    ),
                    "selected_source": row.get("source"),
                    "selection": selection,
                    "selected_outcome_ids": list(
                        row.get("contributor_outcome_ids", [])
                    ),
                    "candidate_outcome_ids": sorted(
                        {
                            oid
                            for e in entries
                            for oid in e[0].get("contributor_outcome_ids", [])
                        }
                    ),
                    "candidate_market_ids": sorted(
                        {e[0]["_market_id"] for e in entries}
                    ),
                    **(
                        {
                            "candidate_verdicts": [
                                {
                                    "source": source,
                                    "market_id": market_id,
                                    "represented_outcome_ids": candidate[
                                        "represented_outcome_ids"
                                    ],
                                    "hit": candidate.get("hit"),
                                    "is_winner": candidate.get("is_winner"),
                                    "resolution_source": candidate.get(
                                        "resolution_source"
                                    ),
                                    "settled": candidate.get("source_mark", {}).get(
                                        "settled"
                                    ),
                                }
                                for (source, market_id), candidate in sorted(
                                    shaped_books.items()
                                )
                            ]
                        }
                        if has_grade
                        else {}
                    ),
                }
            )
    return untouched + selected, held
