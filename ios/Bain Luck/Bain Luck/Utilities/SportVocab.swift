import Foundation

// MARK: - Sport scoring vocabulary

/// What a sport's markets are quoted in, and whether its scoreboard counts the
/// same thing.
///
/// This is the Swift half of `frontend/lib/marketMapUtils.ts` (`sportVocab`),
/// ported verbatim in meaning — the phone was the surface that still had none.
/// Alex, on the live Pegula–Fernandez US Open match (2026-09-04, 10:26am PT):
/// the event page offered him "Proj. 13-13", a margin rail reading "Fernandez
/// by 18+ … Pegula by 18+", a "Projected total points" map over a 26.5 **game**
/// line, and an "Actual Score Diff" line that was the SET score (0, −1, 0)
/// drawn on the same ±6 axis as the books' GAME spread.
///
/// Every one of those is the same defect: a number printed in a unit the match
/// is not played in. The web fixed this class in ux/1034 B5 / #2441 and wrote
/// the rule down there — *a number in the wrong unit is worse than an absent
/// one, because it looks sourced.* This type is that rule, on iOS.
struct SportVocab: Equatable {
    /// Title of the margin/spread map, in the sport's own noun.
    let marginTitle: String
    /// Title of the total map.
    let totalTitle: String
    /// Plural unit the MARKET quotes: "games", "runs", "points". Empty for an
    /// undeclared sport, which prints the market's number and no unit.
    let unit: String
    /// Singular of ``unit``.
    let unitSingular: String
    /// The sport's own realistic spread of outcomes — not a round number. A
    /// tennis match is decided by ~6 games in the margin the market quotes; an
    /// NBA game by ~18 points.
    let marginRange: Int
    /// The span a whole match's TOTAL realistically lands in, in ``unit`` —
    /// `marginRange`'s counterpart for the totals maps, and nil where we have
    /// no honest answer.
    ///
    /// #3503: the totals rail had no such field, so `MarketMapView` fell back
    /// to the literals `180` and `230` whenever no market line parsed. Those
    /// are basketball points, and a live tennis match therefore drew a
    /// **"Games map"** whose rail read `170 · 205 · 240+` — 170 = 180−10,
    /// 240 = 230+10, 205 their midpoint — over a sport played in 20–40 games.
    /// The margin maps never had this bug because they had ``marginRange`` to
    /// read.
    ///
    /// **It is optional on purpose.** An undeclared sport has no span we can
    /// state, and the whole rule of this type is that a number in the wrong
    /// unit is worse than an absent one *because it looks sourced*. Encoding
    /// "we don't know" as a plausible-looking integer is the defect, not the
    /// fix — so it is `nil`, and the rail is built from whatever the market
    /// actually quoted instead (see `MarketMapRail.totalBounds`).
    ///
    /// Used ONLY as a fallback: a sport whose markets did quote lines keeps
    /// deriving its rail from those lines, exactly as before.
    let totalRange: ClosedRange<Int>?
    /// Whether the SCOREBOARD counts ``unit``.
    ///
    /// The default is `true`, deliberately: "the scoreboard counts what the
    /// market quotes" is true of very nearly every sport there is, and false
    /// only where play is scored in nested units and the market quotes the
    /// inner one (tennis: games inside sets). Defaulting false would silently
    /// delete a true, useful line from every sport nobody has declared yet.
    let scoreboardCountsTheUnit: Bool
    /// What the scoreboard counts INSTEAD, plural, when it does not count
    /// ``unit``. Empty where the question does not arise. It exists so a
    /// suppressed widget can say which two units it is refusing to mix — a
    /// widget that just goes quiet reads as broken.
    let scoreboardUnit: String
}

extension SportVocab {
    /// What a sport we have not declared gets.
    ///
    /// Deliberately NOT basketball's entry under another name: the titles avoid
    /// naming a unit at all and the rail is narrow, so an undeclared sport
    /// renders only what a market actually quoted, in the market's own words.
    static let unscoredInPoints = SportVocab(
        marginTitle: "Margin map",
        totalTitle: "Scoring map",
        unit: "",
        unitSingular: "",
        marginRange: 6,
        // Nil, not a guess. Cricket, rugby, MMA, AFL and esports all land here,
        // and they are not played on one scale — the old literals gave every
        // one of them basketball's. See the field's own note.
        totalRange: nil,
        scoreboardCountsTheUnit: true,
        scoreboardUnit: ""
    )

    /// The declared sports. Substring match against the sport key, in order, so
    /// `basketball_nba` and `basketball_ncaab` share one entry — and so
    /// `tennis_wta_us_open` matches "tennis" without anyone listing the tour.
    private static let table: [(match: [String], vocab: SportVocab)] = [
        (["baseball", "mlb"], SportVocab(
            marginTitle: "Run margin map", totalTitle: "Runs map",
            unit: "runs", unitSingular: "run", marginRange: 5,
            totalRange: 4...14,
            scoreboardCountsTheUnit: true, scoreboardUnit: "")),
        (["hockey", "nhl"], SportVocab(
            marginTitle: "Goal margin map", totalTitle: "Goals map",
            unit: "goals", unitSingular: "goal", marginRange: 5,
            totalRange: 2...9,
            scoreboardCountsTheUnit: true, scoreboardUnit: "")),
        (["soccer", "mls", "epl", "uefa", "fifa"], SportVocab(
            marginTitle: "Goal margin map", totalTitle: "Goals map",
            unit: "goals", unitSingular: "goal", marginRange: 5,
            totalRange: 0...7,
            scoreboardCountsTheUnit: true, scoreboardUnit: "")),
        // A tennis match is scored in GAMES inside SETS; the market quotes a
        // game spread and a game total, and neither is a point. The scoreboard
        // reports sets, which is why this is the one row with
        // `scoreboardCountsTheUnit: false`.
        //
        // The total span has to cover BOTH formats the app carries: a
        // best-of-three is 12 games at the shortest and ~39 at the longest, a
        // best-of-five US Open men's match runs past 40 (its quoted totals sit
        // around 36.5–40.5). One span, wide enough to be honest about both.
        (["tennis"], SportVocab(
            marginTitle: "Game margin map", totalTitle: "Games map",
            unit: "games", unitSingular: "game", marginRange: 6,
            totalRange: 12...48,
            scoreboardCountsTheUnit: false, scoreboardUnit: "sets")),
        // 180...230 is the literal `MarketMapView` used to hardcode for every
        // sport on earth. It is kept verbatim HERE, where it is actually true,
        // so basketball's rail does not move on a fix aimed at everyone else.
        (["basketball", "nba", "wnba", "ncaab"], SportVocab(
            marginTitle: "Margin map", totalTitle: "Points map",
            unit: "points", unitSingular: "point", marginRange: 18,
            totalRange: 180...230,
            scoreboardCountsTheUnit: true, scoreboardUnit: "")),
        (["americanfootball", "nfl", "ncaaf"], SportVocab(
            marginTitle: "Margin map", totalTitle: "Points map",
            unit: "points", unitSingular: "point", marginRange: 18,
            totalRange: 28...62,
            scoreboardCountsTheUnit: true, scoreboardUnit: "")),
    ]

    /// The same span for a HALF.
    ///
    /// Derived rather than declared: a half is half a match by definition, and
    /// a second hand-maintained table is a second table to get wrong. Nil
    /// wherever ``totalRange`` is, for the same reason.
    var halfTotalRange: ClosedRange<Int>? {
        guard let full = totalRange else { return nil }
        let lower = full.lowerBound / 2
        return lower...Swift.max(lower + 1, full.upperBound / 2)
    }

    /// The vocabulary for a sport key (`tennis_wta_us_open`, `baseball_mlb`, …).
    static func forSport(_ sportKey: String?) -> SportVocab {
        let key = (sportKey ?? "").lowercased()
        guard !key.isEmpty else { return .unscoredInPoints }
        for entry in table where entry.match.contains(where: { key.contains($0) }) {
            return entry.vocab
        }
        return .unscoredInPoints
    }

    /// `"33 games"`, or just `"33"` for a sport whose unit we have not declared.
    func withUnit(_ value: String) -> String {
        unit.isEmpty ? value : "\(value) \(unit)"
    }

    /// The sentence a widget owes a reader when it has suppressed the half it
    /// cannot state. Nil whenever the question does not arise, so a caller can
    /// bind it straight to an optional view.
    ///
    /// A map that simply drops its Final tile reads as a map that failed to
    /// load; this says which two units it refuses to mix, in the sport's own
    /// words, so a second set-scored sport declared tomorrow gets it for free.
    /// #3465 — THE SENTENCE IS TENSED, so it has to be told whether the match
    /// is over. Written only for a match still being played, it told the reader
    /// of a FINAL US Open match that we "do not hold the games played YET" — a
    /// promise of a capture that will never arrive. Alex's standing ruling is
    /// that settled means settled, and it binds the copy a suppressed widget
    /// prints exactly as it binds a hero or a chart.
    ///
    /// `settled` defaults to false because the pre-match and live readings are
    /// the ones this sentence was written for; a caller that can be looking at
    /// a finished event has to say so.
    func unitMismatchNote(settled: Bool = false) -> String? {
        guard !scoreboardCountsTheUnit, !scoreboardUnit.isEmpty, !unit.isEmpty else { return nil }
        if settled {
            return "The scoreboard reported \(scoreboardUnit), this market quoted \(unit) — we did not hold the \(unit) played."
        }
        return "The scoreboard reports \(scoreboardUnit), this market quotes \(unit) — we do not hold the \(unit) played yet."
    }

    /// The differential chart's counterpart to `unitMismatchNote`, for the
    /// surface that suppresses a LINE rather than a tile.
    ///
    /// It lives here, beside the sentence it is a sibling of, for two reasons:
    /// the two must be tensed by one rule (#3465), and as a `private var` on a
    /// SwiftUI view the chart's wording could only be reached by rasterising
    /// the view — which cannot assert a tense.
    func projectedMarginNote(settled: Bool = false) -> String? {
        guard !scoreboardCountsTheUnit, !scoreboardUnit.isEmpty, !unit.isEmpty else { return nil }
        if settled {
            return "Played \(unit) were not captured — the scoreboard reported "
                + "\(scoreboardUnit). The line below was the books' projected "
                + "\(unitSingular) margin."
        }
        return "Played \(unit) are not captured yet — the scoreboard reports "
            + "\(scoreboardUnit). The line below is the books' projected "
            + "\(unitSingular) margin."
    }
}
