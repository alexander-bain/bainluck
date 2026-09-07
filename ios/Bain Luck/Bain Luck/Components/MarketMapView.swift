import SwiftUI

// MARK: - Marker Types

private enum MarkerType: String {
    case actual, pre, proj, final_

    var dotColor: Color {
        switch self {
        case .actual: return Color(hex: "#16a34a")
        case .final_: return Color(hex: "#0f172a")
        case .pre: return Color(hex: "#94a3b8")
        case .proj: return Color(hex: "#0f172a")
        }
    }
}

private struct MapMarker: Identifiable {
    let id: String
    let value: Double
    let type: MarkerType
    let label: String
    let displayValue: String
}

// MARK: - Main View

struct MarketMapView: View {
    let gameMarkets: GameMarketsResponse
    let eventStatus: String?
    let homeTeam: String
    let awayTeam: String
    let homeAbbr: String?
    let awayAbbr: String?
    let homeColor: Color
    let awayColor: Color
    let sportKey: String?
    var homeWinProb: Double?
    var awayWinProb: Double?
    var homeSpread: Double?
    var overUnder: Double?
    var homeScore: Int?
    var awayScore: Int?

    @Environment(\.horizontalSizeClass) private var sizeClass

    /// #3430 — both competitors of one matchup, so the pair rule decides.
    private var sides: (away: String, home: String) {
        TeamShortName.shortPair(
            away: awayTeam, home: homeTeam,
            awayServed: awayAbbr, homeServed: homeAbbr
        )
    }
    private var hAbbr: String { sides.home }
    private var aAbbr: String { sides.away }
    private var isDone: Bool { eventStatus == "completed" || eventStatus == "closed" }
    private var isLive: Bool { eventStatus == "live" }
    private var isPre: Bool { !isDone && !isLive }
    /// The sport's own words and rail width. Was a pair of local `switch`es
    /// that knew four sports and no tennis, so a US Open match got basketball's
    /// ±18 rail and "Projected total points" over a 26.5 GAME line.
    private var vocab: SportVocab { SportVocab.forSport(sportKey) }

    // MARK: - The full-game margin map's own rungs and unit (#3552 / #3533)

    /// The full-match spread legs, before anything is read out of them.
    private var fullGameSpreadLegs: [SpreadRungs.Leg] {
        (gameMarkets.spreads ?? [])
            .filter { isFullGameSpread($0.marketName) }
            .map(Self.leg)
    }

    /// What the full margin map may draw, and the unit it is drawn in.
    ///
    /// Read once and passed down, because three things have to agree about it —
    /// the card, the empty-chrome gate that decides whether the card exists,
    /// and the footnote that explains what the card withheld. That is #3503's
    /// rule, and computing it three times is how it gets broken.
    private var fullMarginData: SpreadRungs.Map {
        SpreadRungs.map(from: fullGameSpreadLegs, home: homeTeam, away: awayTeam, sportUnit: vocab.unit)
    }

    /// The unit the FULL totals map is drawn in, read from the markets on it
    /// rather than from the sport (#3509). See `SportVocab.totalsUnit`.
    private var fullTotalUnit: String {
        vocab.totalsUnit(quotedBy: fullGameTotals.map(\.marketName))
    }
    /// True where the scoreboard counts what THIS map's rungs are quoted in.
    ///
    /// `vocab.scoreboardCountsTheUnit` answers the same question about the
    /// SPORT's unit, and that is the question the margin maps need. A totals
    /// map whose rungs quote something else — soccer corners on a goals
    /// scoreboard — has to ask it about the rungs, or it draws the scoreboard's
    /// number on a rail that does not measure it.
    private func scoreboardCounts(_ mapUnit: String) -> Bool {
        vocab.scoreboardCountsTheUnit && mapUnit == vocab.unit
    }
    /// The EVENT-level over/under (`overUnder`) and spread (`homeSpread`) are
    /// quoted in the sport's unit, so they belong only on a map drawn in it.
    ///
    /// Weaker than ``scoreboardCounts(_:)`` on purpose: tennis's scoreboard
    /// does not count games, but the event's O/U IS a game line and does belong
    /// on the games map. Caught on the LOOK — the Braves–Phillies bases map
    /// printed `PROJECTION 8.3`, the game's RUNS line, over rungs of 2.5–5.5
    /// bases, and once #3509 handed the rail back to the market's own lines
    /// that stray marker took the axis with it (7 · 8 · 9+).
    private func sportUnitLineApplies(_ mapUnit: String) -> Bool {
        mapUnit == vocab.unit
    }
    /// The noun a subtitle prints. `totalsUnit` returns `""` where no unit is
    /// true of every rung, and `"Projected total \("")"` is a sentence with a
    /// trailing space — so the maps say "scoring" there, the same word
    /// `TotalPointsSpectrumView` uses for the same absence. Display only: the
    /// gates above compare the RAW value against `vocab.unit`.
    private func displayUnit(_ mapUnit: String) -> String {
        mapUnit.isEmpty ? "scoring" : mapUnit
    }

    /// The scoreboard's two numbers, ONLY where they count the thing this
    /// map's rail is drawn in (ux/1034 B5, ported from `MarketMapSection.tsx`).
    ///
    /// On a tennis match they are SETS (`1 — 1`) and the rail is GAMES, so
    /// every downstream use — the ACTUAL margin marker, the ACTUAL total
    /// marker, the live pace projection — was comparing sets against a game
    /// line and printing the answer as a fact. Nulled once here rather than at
    /// each use: there are several call sites across the maps on this page, and
    /// a gate per site is a gate somebody adds one more site beside.
    private var scoredHomeScore: Int? {
        vocab.scoreboardCountsTheUnit ? (gameMarkets.homeScore ?? homeScore) : nil
    }
    private var scoredAwayScore: Int? {
        vocab.scoreboardCountsTheUnit ? (gameMarkets.awayScore ?? awayScore) : nil
    }
    /// Pace is derived from the scoreboard, so it inherits the same gate.
    private var scoredPace: GameMarketPace? {
        vocab.scoreboardCountsTheUnit ? gameMarkets.pace : nil
    }

    /// The sentence a suppressed map owes the reader, once the match is under
    /// way and the missing tile would otherwise be conspicuous.
    private var unitMismatchNote: String? {
        // #3465: `isDone` is the same flag that decides the note is owed, so it
        // is also the flag that decides which tense it is owed in.
        guard isLive || isDone else { return nil }
        // #3509 — owed only where a map ON SCREEN actually withheld its
        // scoreboard tile. The gate used to be "the sport is tennis", which is
        // now too broad in a way that prints a falsehood: a doubles map whose
        // only rung is `"Total Sets O/U 2.5"` quotes SETS, the scoreboard
        // reports SETS, nothing is withheld — and the footnote underneath it
        // still said "this market quotes games". Each half of this reads the
        // same selector its own map builds its markers behind (#3503's rule:
        // a pointer and the thing it points at are gated together, or the next
        // person to change one orphans the other).
        //
        // #3533 — and each half now asks whether the sentence describes ITS
        // map, not whether the scoreboard counts the sport's unit. The two
        // questions are different the moment a map is drawn in something other
        // than `vocab.unit`: a tennis SET margin map withholds nothing (the
        // scoreboard reports sets) and the note under it would have said "this
        // market quotes games" about a card containing no game line at all. The
        // totals half had the same latent falsehood, reachable as soon as a
        // sets totals map draws; both are gated by one predicate now.
        let marginWithheld = showsAnyMarginMap && vocab.noteDescribesMap(quotedBy: fullMarginData.unit)
        let totalWithheld = !totalMapIsEmptyChrome && vocab.noteDescribesMap(quotedBy: fullTotalUnit)
        guard marginWithheld || totalWithheld else { return nil }
        return vocab.unitMismatchNote(settled: isDone)
    }

    private var hasSpreads: Bool { !(gameMarkets.spreads ?? []).isEmpty }
    // `hasTotals` used to gate the totals column. It asked whether rows EXIST,
    // which is a different question from whether any of them draw — the tennis
    // card in #3503 had a row and drew nothing from it. `showsAnyTotalMap` is
    // the question the layout actually needs, so the weaker one is gone rather
    // than left beside it for someone to reach for.
    private var useColumns: Bool {
        #if os(macOS)
        return true
        #else
        return sizeClass == .regular
        #endif
    }

    var body: some View {
        if !showsAnyMap { EmptyView() }
        else if useColumns {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .top, spacing: 12) {
                    if showsAnyMarginMap {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("MARGIN MAPS")
                                .font(.system(size: 11, weight: .heavy))
                                .foregroundStyle(.secondary)
                                .tracking(1)
                            fullMarginMap
                            halfMarginMaps
                        }
                        .frame(maxWidth: .infinity)
                    }
                    if showsAnyTotalMap {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("TOTAL MAPS")
                                .font(.system(size: 11, weight: .heavy))
                                .foregroundStyle(.secondary)
                                .tracking(1)
                            fullTotalMap
                            halfTotalMaps
                        }
                        .frame(maxWidth: .infinity)
                    }
                }
                unitMismatchFootnote
            }
        } else {
            VStack(spacing: 12) {
                if showsAnyMarginMap { fullMarginMap; halfMarginMaps }
                if showsAnyTotalMap { fullTotalMap; halfTotalMaps }
                unitMismatchFootnote
            }
        }
    }

    /// Whether ANY map is on screen — the one selector the footnote and the
    /// early-out both read.
    ///
    /// #3503, caught on the LOOK of the fix itself. Suppressing the tennis
    /// totals card left `unitMismatchFootnote` rendering alone under the hero:
    /// *"The scoreboard reports sets, this market quotes games — we do not hold
    /// the games played yet"*, with no map anywhere on the screen for "this
    /// market" to refer to. That sentence exists to explain a tile a map has
    /// suppressed; with no map it explains nothing and reads as a stray fault.
    /// A pointer and the thing it points at have to be gated by ONE condition,
    /// or the next person to suppress a card re-orphans it.
    private var showsAnyMap: Bool { showsAnyMarginMap || showsAnyTotalMap }

    /// Said once under the maps, not per card: the suppressed ACTUAL tiles are
    /// all one absence, and four copies of one sentence reads as four faults.
    @ViewBuilder
    private var unitMismatchFootnote: some View {
        if let note = unitMismatchNote {
            Text(note)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Full Game Margin Map

    /// True when the margin map would draw nothing a market said.
    ///
    /// `buildDensityFromSpreads([])` returns a FLAT rail — a uniform shape that
    /// looks like a distribution and is not one. On the live US Open match the
    /// two spread rows were Kalshi "No" legs, which name no player, so nothing
    /// parsed: the card was a title, a subtitle and a decorative rail. With the
    /// unit-mismatched ACTUAL tile now gone (see `scoredHomeScore`) there was
    /// literally nothing left in it, and empty chrome reads worse than an
    /// absent card.
    private var marginMapIsEmptyChrome: Bool {
        guard fullMarginData.rungs.isEmpty else { return false }
        // With no rungs there is no map unit either, so the event-level spread
        // is the sport's number on a rail nobody has drawn yet — it applies
        // exactly when the sport declares a unit for it to be in.
        let hasProjection = sportUnitLineApplies(fullMarginData.unit) && homeSpread != nil
        let hasScoreTile = scoredHomeScore != nil && scoredAwayScore != nil && (isLive || isDone)
        return !hasProjection && !hasScoreTile
    }

    @ViewBuilder
    private var fullMarginMap: some View {
        if marginMapIsEmptyChrome {
            EmptyView()
        } else {
            marginMapCard
        }
    }

    private var marginMapCard: some View {
        let data = fullMarginData
        let parsed = data.rungs
        let allMargins = parsed.map(\.margin)
        let bounds = MarketMapRail.marginBounds(
            margins: allMargins,
            declared: vocab.marginRange(quotedBy: data.unit),
            pad: 3
        )
        let rangeMin = bounds.min
        let rangeMax = bounds.max
        let density = buildDensityFromSpreads(parsed, rangeMin: rangeMin, rangeMax: rangeMax)

        // `Int(abs(margin))` truncated: a `-5.5` game line printed "+5", and on
        // the set maps this change introduces `-1.5` printed "+1" — a
        // two-set handicap relabelled as a one-set one, which is a different
        // market. `formatThreshold` is the same formatter the totals ladder
        // has always used.
        let ladder: [(label: String, prob: Double, color: Color)] =
            parsed.filter { !$0.isHome }.sorted { abs($0.margin) < abs($1.margin) }.prefix(3).map {
                ("\(aAbbr) +\(formatThreshold(abs($0.margin)))", $0.probability, awayColor)
            } +
            parsed.filter(\.isHome).sorted { $0.margin < $1.margin }.prefix(3).map {
                ("\(hAbbr) +\(formatThreshold($0.margin))", $0.probability, homeColor)
            }

        // Headline: favored team + win %
        let headline: String = {
            guard let homeProbability = homeWinProb, let awayProbability = awayWinProb else { return "" }
            let favored = homeProbability > 0.5
            return "\(favored ? hAbbr : aAbbr) \(Int(((favored ? homeProbability : awayProbability) * 100).rounded()))%"
        }()

        // Markers
        var markers: [MapMarker] = []
        // The event-level spread is quoted in the SPORT's unit, so it may only
        // be plotted on a rail drawn in that unit — the same gate `overUnder`
        // has carried on the totals side since #3509. Without it a tennis SET
        // margin map would print the books' GAME line as its projection.
        let sportSpread = sportUnitLineApplies(data.unit) ? homeSpread : nil
        let projValue = sportSpread != nil ? -(sportSpread!) : closestToEvenMargin(parsed)
        if isDone {
            if let homeScoreValue = scoredHomeScore,
               let awayScoreValue = scoredAwayScore {
                let margin = homeScoreValue - awayScoreValue
                markers.append(MapMarker(id: "final", value: Double(margin), type: .final_, label: "FINAL", displayValue: "\(margin > 0 ? hAbbr : aAbbr) +\(abs(margin))"))
            }
            if let pv = projValue {
                markers.append(MapMarker(id: "pre", value: pv, type: .pre, label: "PRE-GAME", displayValue: "\(pv > 0 ? hAbbr : aAbbr) +\(String(format: "%.1f", abs(pv)))"))
            }
        } else if isLive {
            if let homeScoreValue = scoredHomeScore,
               let awayScoreValue = scoredAwayScore {
                let margin = homeScoreValue - awayScoreValue
                markers.append(MapMarker(id: "actual", value: Double(margin), type: .actual, label: "ACTUAL", displayValue: "\(margin > 0 ? hAbbr : aAbbr) +\(abs(margin))"))
            }
            if let pv = projValue {
                markers.append(MapMarker(id: "proj", value: pv, type: .proj, label: "PROJECTION", displayValue: "\(pv > 0 ? hAbbr : aAbbr) +\(String(format: "%.1f", abs(pv)))"))
            }
        } else {
            if let pv = projValue {
                markers.append(MapMarker(id: "proj", value: pv, type: .proj, label: "PROJECTION", displayValue: "\(pv > 0 ? hAbbr : aAbbr) +\(String(format: "%.1f", abs(pv)))"))
            }
        }

        let zeroPos = posOnRail(0, min: rangeMin, max: rangeMax)
        let homeRgb = resolveRGB(homeColor)
        let awayRgb = resolveRGB(awayColor)

        // The axis ends name the rail's own outer bound. They used to name
        // `vocab.marginRange` regardless, which is the same number on every map
        // drawn in the sport's unit and a games number on one that is not.
        //
        // #3642 — EACH end names ITS OWN bound. One `formatThreshold(rangeMax)`
        // on both ends claims a symmetric rail, and `marginBounds`' declared
        // branch is asymmetric whenever the two teams are quoted to different
        // depths. See `MarketMapRail.marginAxisEnds`.
        let axisEnds = MarketMapRail.marginAxisEnds(bounds)

        // #3630 — ONE selector, both layouts. The column branch used to pin this
        // to the literal `"Full game margin map"`, so every unit-aware title the
        // phone had gained since #3509 was invisible on iPad and Mac: the iPad
        // headed Swiatek–Zheng's ±1.5 SET rungs "Full game margin map" while the
        // iPhone, on the same payload in the same minute, headed them "Set
        // margin map". In tennis that is not a synonym — a *game* is a real and
        // different unit quoted on the same page (`Game Spread ±5.5`), so the
        // column title named a market the card did not contain.
        //
        // The literal's only real job was to separate this card from the half
        // cards stacked under it in the column, and those already carry their
        // own `1st Half` / `2nd Half` labels beneath a `MARGIN MAPS` heading —
        // which is exactly how the phone has always read.
        return mapCard(
            title: vocab.marginTitle(quotedBy: data.unit),
            // #3763 — the card stops promising a distribution it has not got.
            // Asked of the density this card is about to draw, not of `parsed`,
            // so the sentence cannot disagree with the rail above it.
            subtitle: MarketMapRail.fullMarginSubtitle(
                isDone: isDone,
                hasDistribution: MarketMapRail.marginRailHasDistribution(density: density)
            ),
            headline: headline,
            density: density,
            rangeMin: rangeMin,
            rangeMax: rangeMax,
            zeroPosition: zeroPos,
            leftRgb: awayRgb,
            rightRgb: homeRgb,
            axisLeft: "\(aAbbr) by \(formatThreshold(axisEnds.left))+",
            axisMid: "Tie",
            axisRight: "\(hAbbr) by \(formatThreshold(axisEnds.right))+",
            markers: markers,
            ladder: ladder
        )
    }

    // MARK: - Full Game Total Map

    /// The full-match totals rows — the halves are the ones with a `":"`.
    private var fullGameTotals: [GameMarketOutcome] {
        (gameMarkets.totals ?? []).filter { !$0.outcomeName.contains(":") }
    }

    /// #3503 — the totals map's counterpart to `marginMapIsEmptyChrome`, which
    /// it never had. The rule itself lives in `MarketMapRail` so it can be
    /// asserted without rasterising this view.
    private var totalMapIsEmptyChrome: Bool {
        // #3509 — `scoreboardCounts` is the SAME gate `totalMapCard` builds its
        // scoreboard markers behind. It has to be, or the card is judged
        // non-empty on markers it then declines to draw and we are back to
        // #3503's empty chrome by another route.
        let mapUnit = fullTotalUnit
        let scoreboardIsComparable = scoreboardCounts(mapUnit)
        return MarketMapRail.totalMapDrawsNothing(
            hasThresholds: !extractTotalThresholds(fullGameTotals).isEmpty,
            overUnder: sportUnitLineApplies(mapUnit) ? overUnder : nil,
            isLive: isLive,
            isDone: isDone,
            hasScoreboardTotal: scoreboardIsComparable
                && scoredHomeScore != nil && scoredAwayScore != nil,
            hasProjectedTotal: scoreboardIsComparable && scoredPace?.projectedTotal != nil
        )
    }

    @ViewBuilder
    private var fullTotalMap: some View {
        if totalMapIsEmptyChrome {
            EmptyView()
        } else {
            totalMapCard
        }
    }

    private var totalMapCard: some View {
        let thresholds = extractTotalThresholds(fullGameTotals)
        let allThresh = thresholds.map(\.threshold)
        // #3509 — this map's own unit, and whether the scoreboard counts it.
        let mapUnit = fullTotalUnit
        let scoreboardIsComparable = scoreboardCounts(mapUnit)

        let ladder: [(label: String, prob: Double, color: Color)] = thresholds.prefix(6).map {
            ("Over \(formatThreshold($0.threshold))", $0.overProb, Color(hex: "#7c3aed"))
        }

        // Markers are built BEFORE the rail (#3503): with no line parsed they
        // are the only real numbers the card has, so the rail has to be able to
        // see them. Nothing in this block depends on the rail.
        var markers: [MapMarker] = []
        let sportLine = sportUnitLineApplies(mapUnit) ? overUnder : nil
        let ouLine = sportLine ?? thresholds.first(where: { abs($0.overProb - 0.5) < 0.1 })?.threshold
        if isDone {
            if scoreboardIsComparable,
               let homeScoreValue = scoredHomeScore,
               let awayScoreValue = scoredAwayScore {
                let totalScore = homeScoreValue + awayScoreValue
                markers.append(MapMarker(id: "final", value: Double(totalScore), type: .final_, label: "FINAL", displayValue: vocab.withUnit("\(totalScore)")))
            }
            if let ou = ouLine {
                markers.append(MapMarker(id: "pre", value: ou, type: .pre, label: "PRE-GAME", displayValue: formatThreshold(ou)))
            }
        } else if isLive {
            if scoreboardIsComparable,
               let homeScoreValue = scoredHomeScore,
               let awayScoreValue = scoredAwayScore,
               let pace = scoredPace, let proj = pace.projectedTotal {
                let totalScore = homeScoreValue + awayScoreValue
                markers.append(MapMarker(id: "actual", value: Double(totalScore), type: .actual, label: "ACTUAL", displayValue: "\(totalScore)"))
                markers.append(MapMarker(id: "proj", value: proj, type: .proj, label: "PROJECTED", displayValue: "\(Int(proj.rounded()))"))
            }
            if let ou = ouLine {
                markers.append(MapMarker(id: "pre", value: ou, type: .pre, label: "PRE-GAME", displayValue: formatThreshold(ou)))
            }
        } else {
            if let ou = ouLine {
                markers.append(MapMarker(id: "proj", value: ou, type: .proj, label: "PROJECTION", displayValue: formatThreshold(ou)))
            }
        }

        // A TOTAL cannot be negative, and the -10 padding put the rail's left
        // edge at "-7" on the live US Open match (a stray 2.5 threshold among
        // 21.5/22.5 game lines dragged the minimum down). Padding below zero is
        // never a real outcome, so the floor is zero on every sport.
        //
        // #3503 — the `?? 180` / `?? 230` that used to sit here were basketball
        // points wearing every sport's title. The sport's own span now comes
        // from `vocab.totalRange`, exactly as the margin maps have always read
        // `vocab.marginRange`.
        let bounds = MarketMapRail.totalBounds(
            thresholds: allThresh,
            markerValues: markers.map(\.value),
            declared: vocab.totalRange(quotedBy: fullGameTotals.map(\.marketName)),
            pad: 10
        )
        let rangeMin = bounds.min
        let rangeMax = bounds.max
        let density = buildDensityFromThresholds(thresholds, rangeMin: rangeMin, rangeMax: rangeMax, segments: 14)
        // #3576 — whether that density is data or a placeholder. The rule lives
        // in `MarketMapRail` so it can be asserted without rasterising a view.
        let hasDistribution = MarketMapRail.totalRailHasDistribution(thresholds: allThresh)

        let purpleRgb = (r: 124.0, g: 58.0, b: 237.0)

        // #3630 — the margin map's twin, and the more legible of the two: this
        // branch's SUBTITLE was already unit-aware (`Projected total \(unit)`
        // two lines down) while its title was pinned, so a bases map on iPad
        // read "Full game total map" over "Projected total bases". That split is
        // the precise failure `SportVocab.totalTitle` was written to close — a
        // title and its subtitle are one sentence to a reader, so they read one
        // selector.
        return mapCard(
            title: vocab.totalTitle(quotedBy: fullGameTotals.map(\.marketName)),
            subtitle: MarketMapRail.fullTotalSubtitle(
                isDone: isDone,
                hasDistribution: hasDistribution,
                unit: displayUnit(mapUnit)
            ),
            headline: "",
            density: density,
            drawsDistribution: hasDistribution,
            rangeMin: rangeMin,
            rangeMax: rangeMax,
            zeroPosition: nil,
            leftRgb: purpleRgb,
            rightRgb: purpleRgb,
            axisLeft: "\(Int(rangeMin))",
            axisMid: "\(Int((rangeMin + rangeMax) / 2))",
            axisRight: "\(Int(rangeMax))+",
            markers: markers,
            ladder: ladder
        )
    }

    // MARK: - Half Maps

    @ViewBuilder
    private var halfMarginMaps: some View {
        ForEach(halfMarginGroups) { group in
            halfMarginCard(outcomes: group.outcomes, label: group.id)
        }
    }

    /// The half-margin cards that will draw. Extracted from `halfMarginMaps` so
    /// `showsAnyMarginMap` can ask the question without rendering it; the
    /// membership rule is copied unchanged — #3503 does not move the margin
    /// side, it only needs to know whether the margin side is on screen.
    private var halfMarginGroups: [MapGroup] {
        // Try period_markets first, fall back to filtering spreads by name
        let periodMarkets = gameMarkets.periodMarkets ?? []
        let spreads = gameMarkets.spreads ?? []
        let halfSpreads = periodMarkets.filter { isSpreadMarket($0) } +
            spreads.filter { !isFullGameSpread($0.marketName) }

        return [
            MapGroup(id: "1st half margin",
                           outcomes: halfSpreads.filter { derivePeriod($0) == "1H" }),
            MapGroup(id: "2nd half margin",
                           outcomes: halfSpreads.filter { derivePeriod($0) == "2H" }),
        ].filter { !$0.outcomes.isEmpty }
    }

    /// Whether the MARGIN MAPS column has anything under its heading.
    private var showsAnyMarginMap: Bool {
        hasSpreads && (!marginMapIsEmptyChrome || !halfMarginGroups.isEmpty)
    }

    /// One half-map's worth of outcomes, labelled. Shared by the margin and
    /// totals halves so both can be counted without being rendered.
    private struct MapGroup: Identifiable {
        let id: String
        let outcomes: [GameMarketOutcome]
    }

    private var halfTotalGroups: [MapGroup] {
        let periodMarkets = gameMarkets.periodMarkets ?? []
        let totals = gameMarkets.totals ?? []
        let halfTotals = periodMarkets.filter { isTotalMarket($0) } +
            totals.filter { $0.outcomeName.contains(":") }

        return [
            MapGroup(id: "1st half total map",
                           outcomes: halfTotals.filter { derivePeriod($0) == "1H" }),
            MapGroup(id: "2nd half total map",
                           outcomes: halfTotals.filter { derivePeriod($0) == "2H" }),
        ].filter { !extractTotalThresholds($0.outcomes).isEmpty }
    }

    @ViewBuilder
    private var halfTotalMaps: some View {
        ForEach(halfTotalGroups) { group in
            halfTotalCard(outcomes: group.outcomes, label: group.id)
        }
    }

    /// Whether the TOTAL MAPS column has anything under its heading. Without
    /// this, suppressing an empty-chrome totals card (#3503) would leave the
    /// iPad/Mac layout printing a bare "TOTAL MAPS" header over nothing —
    /// trading one piece of empty chrome for another.
    private var showsAnyTotalMap: Bool {
        !totalMapIsEmptyChrome || !halfTotalGroups.isEmpty
    }

    private func halfMarginCard(outcomes: [GameMarketOutcome], label: String) -> some View {
        // A half reads its OWN rungs and its own unit, exactly as #3509 made
        // the half totals cards do.
        let data = SpreadRungs.map(
            from: outcomes.map(Self.leg), home: homeTeam, away: awayTeam, sportUnit: vocab.unit
        )
        let parsed = data.rungs
        let allMargins = parsed.map(\.margin)
        let bounds = MarketMapRail.marginBounds(
            margins: allMargins,
            declared: vocab.marginRange(quotedBy: data.unit),
            pad: 3
        )
        let rangeMin = bounds.min
        let rangeMax = bounds.max
        let density = buildDensityFromSpreads(parsed, rangeMin: rangeMin, rangeMax: rangeMax)
        let zeroPos = posOnRail(0, min: rangeMin, max: rangeMax)
        let projValue = closestToEvenMargin(parsed)

        var markers: [MapMarker] = []
        if let pv = projValue {
            markers.append(MapMarker(id: "pre", value: pv, type: .pre, label: "PRE-GAME", displayValue: "\(pv > 0 ? hAbbr : aAbbr) +\(String(format: "%.1f", abs(pv)))"))
        }

        // #3642 — each end names its own bound, as on the full-game card above.
        let axisEnds = MarketMapRail.marginAxisEnds(bounds)
        return mapCard(
            // #3763 — as on the full-game card above.
            title: label,
            subtitle: MarketMapRail.halfMarginSubtitle(
                hasDistribution: MarketMapRail.marginRailHasDistribution(density: density)
            ),
            headline: "",
            density: density, rangeMin: rangeMin, rangeMax: rangeMax,
            zeroPosition: zeroPos,
            leftRgb: resolveRGB(awayColor), rightRgb: resolveRGB(homeColor),
            axisLeft: "\(aAbbr) by \(formatThreshold(axisEnds.left))+",
            axisMid: "Tie",
            axisRight: "\(hAbbr) by \(formatThreshold(axisEnds.right))+",
            markers: markers, ladder: []
        )
    }

    private func halfTotalCard(outcomes: [GameMarketOutcome], label: String) -> some View {
        let thresholds = extractTotalThresholds(outcomes)
        let allThresh = thresholds.map(\.threshold)
        // #3509 — a half map reads ITS OWN rungs, not the full map's and not
        // the sport's.
        let mapUnit = vocab.totalsUnit(quotedBy: outcomes.map(\.marketName))

        var markers: [MapMarker] = []
        if let ou = thresholds.first(where: { abs($0.overProb - 0.5) < 0.1 })?.threshold {
            markers.append(MapMarker(id: "pre", value: ou, type: .pre, label: "PRE-GAME", displayValue: formatThreshold(ou)))
        }

        // #3503 — `?? 90` / `?? 120` here were basketball half-points, the same
        // defect as the full map's `?? 180` / `?? 230` at a smaller scale.
        let bounds = MarketMapRail.totalBounds(
            thresholds: allThresh,
            markerValues: markers.map(\.value),
            declared: vocab.totalRange(quotedBy: outcomes.map(\.marketName)) == nil
                ? nil
                : vocab.halfTotalRange,
            pad: 5
        )
        let rangeMin = bounds.min
        let rangeMax = bounds.max
        let density = buildDensityFromThresholds(thresholds, rangeMin: rangeMin, rangeMax: rangeMax, segments: 14)
        // #3576 — the full map's rule, on the half map's identical flat array.
        let hasDistribution = MarketMapRail.totalRailHasDistribution(thresholds: allThresh)
        let purpleRgb = (r: 124.0, g: 58.0, b: 237.0)

        return mapCard(
            title: label,
            subtitle: MarketMapRail.halfTotalSubtitle(
                hasDistribution: hasDistribution,
                unit: displayUnit(mapUnit)
            ),
            headline: "",
            density: density, drawsDistribution: hasDistribution,
            rangeMin: rangeMin, rangeMax: rangeMax,
            zeroPosition: nil,
            leftRgb: purpleRgb, rightRgb: purpleRgb,
            axisLeft: "\(Int(rangeMin))", axisMid: "\(Int((rangeMin + rangeMax) / 2))", axisRight: "\(Int(rangeMax))+",
            markers: markers, ladder: []
        )
    }

    // MARK: - Reusable Map Card

    /// - Parameter drawsDistribution: false when `density` is a placeholder
    ///   rather than data (#3576), in which case the rail is drawn as an empty
    ///   track. Defaults true so the margin cards, whose densities are always
    ///   built from real rungs, are untouched.
    private func mapCard(
        title: String, subtitle: String, headline: String,
        density: [Double], drawsDistribution: Bool = true,
        rangeMin: Double, rangeMax: Double,
        zeroPosition: Double?,
        leftRgb: (r: Double, g: Double, b: Double),
        rightRgb: (r: Double, g: Double, b: Double),
        axisLeft: String, axisMid: String, axisRight: String,
        markers: [MapMarker],
        ladder: [(label: String, prob: Double, color: Color)]
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(title)
                        .font(.system(size: 15, weight: .black))
                        .tracking(-0.5)
                    Text(subtitle)
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if !headline.isEmpty {
                    Text(headline)
                        .font(.system(size: 14, weight: .black))
                        .foregroundStyle(.primary)
                }
            }

            // Summary tiles
            if !markers.isEmpty {
                HStack(spacing: 8) {
                    ForEach(markers) { m in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(m.label)
                                .font(.system(size: 10, weight: .heavy))
                                .foregroundStyle(.secondary)
                                .tracking(0.5)
                            Text(m.displayValue)
                                .font(.system(size: 14, weight: .black))
                                .lineLimit(1)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.secondary.opacity(0.04))
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                        .overlay(alignment: .bottom) {
                            RoundedRectangle(cornerRadius: 2)
                                .fill(m.type.dotColor)
                                .frame(height: 3)
                                .padding(.horizontal, 4)
                        }
                    }
                }
            }

            // Density rail with marker dots
            densityRail(
                density: density, drawsDistribution: drawsDistribution,
                rangeMin: rangeMin, rangeMax: rangeMax,
                zeroPosition: zeroPosition,
                leftRgb: leftRgb, rightRgb: rightRgb,
                markers: markers
            )

            // Axis labels. #3566 — the ends are fixed, but the MIDDLE one is
            // only at the middle when the rail has no zero on it. On a margin
            // rail the mid label names zero ("Tie"), so it is drawn where zero
            // actually falls; `densityRail` no longer draws a second one.
            HStack {
                Text(axisLeft).foregroundStyle(.secondary)
                Spacer()
                Text(axisRight).foregroundStyle(.secondary)
            }
            .font(.system(size: 11, weight: .heavy))
            .overlay {
                GeometryReader { geo in
                    switch MarketMapRail.midAxisLabel(zeroPercent: zeroPosition) {
                    case .centred:
                        Text(axisMid)
                            .font(.system(size: 11, weight: .heavy))
                            .foregroundStyle(.secondary)
                            .position(x: geo.size.width / 2, y: geo.size.height / 2)
                    case .at(let percent):
                        Text(axisMid)
                            .font(.system(size: 11, weight: .heavy))
                            .foregroundStyle(.secondary)
                            .position(x: geo.size.width * percent / 100.0, y: geo.size.height / 2)
                    case .withheld:
                        EmptyView()
                    }
                }
            }

            // Probability ladder
            if !ladder.isEmpty {
                ladderView(entries: ladder)
            }
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 22))
        .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.barTrack.opacity(0.5), lineWidth: 1))
    }

    // MARK: - Density Rail with Marker Dots

    private func densityRail(
        density: [Double], drawsDistribution: Bool = true,
        rangeMin: Double, rangeMax: Double,
        zeroPosition: Double?,
        leftRgb: (r: Double, g: Double, b: Double),
        rightRgb: (r: Double, g: Double, b: Double),
        markers: [MapMarker]
    ) -> some View {
        let segmentCount = density.count
        let zeroFrac = zeroPosition.map { $0 / 100.0 }

        return ZStack(alignment: .leading) {
            GeometryReader { geo in
                // Background segments
                Group {
                    if drawsDistribution {
                        HStack(spacing: 0) {
                            ForEach(0..<segmentCount, id: \.self) { i in
                                let frac = Double(i) / Double(segmentCount)
                                let isLeft = zeroFrac.map { frac < $0 } ?? true
                                let rgb = isLeft ? leftRgb : rightRgb
                                let alpha = 0.15 + (density[i] / 100.0) * 0.75
                                Rectangle()
                                    .fill(Color(red: rgb.r / 255, green: rgb.g / 255, blue: rgb.b / 255).opacity(alpha))
                            }
                        }
                    } else {
                        // #3576 — no distribution, so no shading to read as one.
                        // `Color.secondary.opacity(0.08)` is this file's own
                        // empty-track fill (`ladderView`'s capsule), which is the
                        // point: the reader has already been taught it means
                        // "track, not data", and it is lighter than the 0.21 the
                        // placeholder density was rendering at.
                        Rectangle().fill(Color.secondary.opacity(0.08))
                    }
                }
                .clipShape(Capsule())
                .overlay(Capsule().stroke(Color.barTrack, lineWidth: 1))
                .overlay(
                    LinearGradient(
                        colors: [.white.opacity(0.30), .clear, .black.opacity(0.08)],
                        startPoint: .top, endPoint: .bottom
                    )
                    .clipShape(Capsule())
                )
                .shadow(color: .black.opacity(0.06), radius: 2, y: 1)

                // Zero line. #3566 — the `Text("0")` that used to sit here at
                // `y: 48` landed in the axis row below (this rail is
                // `height: 36`, the axis `HStack` follows at `spacing: 10`),
                // where it either crowded or overprinted the centred "Tie".
                // The axis row now carries one label for zero and this draws
                // only the rule itself.
                if let zeroPct = zeroPosition {
                    Rectangle()
                        .fill(Color.secondary.opacity(0.3))
                        .frame(width: 2)
                        .offset(x: geo.size.width * zeroPct / 100.0 - 1)
                        .frame(height: 40)
                        .offset(y: -5)
                }

                // Marker dots — scale radius relative to rail width
                ForEach(markers) { m in
                    let pct = posOnRail(m.value, min: rangeMin, max: rangeMax)
                    let xPos = geo.size.width * pct / 100.0
                    let isProj = m.type == .proj
                    let markerRadius: CGFloat = geo.size.width > 300 ? 13 : 11
                    let dotSize: CGFloat = isProj ? markerRadius * 2 : markerRadius * 2 - 4
                    Circle()
                        .fill(isProj ? Color.cardBackground : m.type.dotColor)
                        .frame(width: dotSize, height: dotSize)
                        .overlay(
                            Circle().stroke(isProj ? Color.primary : .white, lineWidth: 2)
                        )
                        .shadow(color: .black.opacity(0.2), radius: 3, y: 1)
                        .position(x: xPos, y: 15)
                }
            }
        }
        .frame(height: 36)
    }

    // MARK: - Probability Ladder

    private func ladderView(entries: [(label: String, prob: Double, color: Color)]) -> some View {
        VStack(spacing: 5) {
            ForEach(entries.indices, id: \.self) { i in
                let entry = entries[i]
                HStack(spacing: MarketMapLadderLayout.rowSpacing) {
                    // Label with team color dot for visual association.
                    MarketMapLadderLabel(text: entry.label, color: entry.color)
                        .frame(width: MarketMapLadderLayout.labelColumnWidth, alignment: .leading)
                    GeometryReader { geo in
                        Capsule()
                            .fill(Color.secondary.opacity(0.08))
                            .overlay(alignment: .leading) {
                                Capsule()
                                    .fill(entry.color.opacity(0.55))
                                    .frame(width: max(2, geo.size.width * min(entry.prob, 1.0)))
                            }
                    }
                    .frame(height: 16)
                    Text("\(Int((entry.prob * 100).rounded()))%")
                        .font(.system(size: 10, weight: .black, design: .monospaced))
                        .frame(width: MarketMapLadderLayout.valueColumnWidth, alignment: .trailing)
                }
            }
        }
    }

    // MARK: - Helpers

    private func posOnRail(_ value: Double, min: Double, max: Double) -> Double {
        Swift.max(0, Swift.min(100, ((value - min) / (max - min)) * 100))
    }

    private func resolveRGB(_ color: Color) -> (r: Double, g: Double, b: Double) {
        let resolved = color.resolve(in: EnvironmentValues())
        return (r: Double(resolved.red) * 255, g: Double(resolved.green) * 255, b: Double(resolved.blue) * 255)
    }

    private func formatThreshold(_ t: Double) -> String {
        t.truncatingRemainder(dividingBy: 1) == 0 ? "\(Int(t))" : String(format: "%.1f", t)
    }

    private func closestToEvenMargin(_ parsed: [SpreadRungs.Rung]) -> Double? {
        guard !parsed.isEmpty else { return nil }
        let closest = parsed.min(by: { abs($0.probability - 0.5) < abs($1.probability - 0.5) })!
        return closest.isHome ? closest.margin : closest.margin
    }

    /// Derive the period label for a market outcome.
    /// Uses backend-supplied ``period`` field (derived from ticker prefix);
    /// falls back to text-based detection in outcome/market names.
    private func derivePeriod(_ o: GameMarketOutcome) -> String? {
        if let p = o.period, !p.isEmpty { return p }
        if isFirstHalf(o.outcomeName) || isFirstHalf(o.marketName) { return "1H" }
        if isSecondHalf(o.outcomeName) || isSecondHalf(o.marketName) { return "2H" }
        return nil
    }

    private func isFirstHalf(_ s: String) -> Bool {
        let lower = s.lowercased()
        return lower.contains("1h") || lower.contains("1st half") || lower.contains("first half") || lower.contains("first 5")
    }

    private func isSecondHalf(_ s: String) -> Bool {
        let lower = s.lowercased()
        return lower.contains("2h") || lower.contains("2nd half") || lower.contains("second half")
    }

    private func isSpreadMarket(_ o: GameMarketOutcome) -> Bool {
        let mt = (o.marketType ?? "").lowercased()
        let mn = o.marketName.lowercased()
        return mt.contains("spread") || mn.contains("spread") || mn.contains("handicap")
    }

    private func isTotalMarket(_ o: GameMarketOutcome) -> Bool {
        let mt = (o.marketType ?? "").lowercased()
        let mn = o.marketName.lowercased()
        return mt.contains("total") || mn.contains("total")
    }

    private func isFullGameSpread(_ name: String) -> Bool {
        let lower = name.lowercased()
        return !lower.contains("1h") && !lower.contains("1st half") && !lower.contains("first half") &&
               !lower.contains("2h") && !lower.contains("2nd half") && !lower.contains("second half") &&
               !lower.contains("first 5")
    }

    // MARK: - Data Parsing

    /// `parseSprOutcome` used to live here. It read only `outcomeName`, matched
    /// team words as substrings and resolved an ambiguous hit to home; all
    /// three are now `SpreadRungs`, where they can be asserted without
    /// rasterising this view. #3552 / #3568.
    private static func leg(_ o: GameMarketOutcome) -> SpreadRungs.Leg {
        SpreadRungs.Leg(
            marketName: o.marketName,
            outcomeName: o.outcomeName,
            threshold: o.threshold,
            probability: o.probability
        )
    }

    private func extractTotalThresholds(_ outcomes: [GameMarketOutcome]) -> [(threshold: Double, overProb: Double)] {
        outcomes.compactMap { t in
            let name = t.outcomeName.lowercased()
            guard name.contains("over") else { return nil }
            let threshold = t.threshold ?? Self.extractNumber(from: t.outcomeName)
            guard let th = threshold else { return nil }
            return (th, t.overProbability ?? t.probability ?? 0.5)
        }
        .sorted(by: { $0.threshold < $1.threshold })
    }

    private static func extractNumber(from text: String) -> Double? {
        let pattern = try! NSRegularExpression(pattern: #"(\d+\.?\d*)"#)
        let range = NSRange(text.startIndex..., in: text)
        let matches = pattern.matches(in: text, range: range)
        guard let last = matches.last else { return nil }
        let matchRange = Range(last.range(at: 1), in: text)!
        return Double(text[matchRange])
    }

    // MARK: - Density Computation

    private func buildDensityFromSpreads(_ spreads: [SpreadRungs.Rung], rangeMin: Double, rangeMax: Double, segments: Int = 14) -> [Double] {
        if spreads.isEmpty { return Array(repeating: 5, count: segments) }
        var density = Array(repeating: 0.0, count: segments)
        let step = (rangeMax - rangeMin) / Double(segments)
        for s in spreads {
            let idx = Int((s.margin - rangeMin) / step)
            let clamped = max(0, min(segments - 1, idx))
            density[clamped] += s.probability
        }
        let peak = max(density.max() ?? 0.01, 0.01)
        return density.map { ($0 / peak) * 96 }
    }

    private func buildDensityFromThresholds(
        _ thresholds: [(threshold: Double, overProb: Double)],
        rangeMin: Double, rangeMax: Double, segments: Int = 14
    ) -> [Double] {
        if thresholds.count < 2 { return Array(repeating: 8, count: segments) }
        let sorted = thresholds.sorted(by: { $0.threshold < $1.threshold })
        var rawPdf: [(mid: Double, density: Double)] = []
        for i in 0..<(sorted.count - 1) {
            let dt = sorted[i + 1].threshold - sorted[i].threshold
            guard dt > 0 else { continue }
            let dp = sorted[i].overProb - sorted[i + 1].overProb
            rawPdf.append((mid: (sorted[i].threshold + sorted[i + 1].threshold) / 2, density: max(0, dp / dt)))
        }
        if rawPdf.isEmpty { return Array(repeating: 8, count: segments) }
        let step = (rangeMax - rangeMin) / Double(segments)
        var density = Array(repeating: 0.0, count: segments)
        for i in 0..<segments {
            let x = rangeMin + (Double(i) + 0.5) * step
            if rawPdf.count == 1 { density[i] = rawPdf[0].density }
            else if x <= rawPdf[0].mid { density[i] = rawPdf[0].density * max(0, 1 - (rawPdf[0].mid - x) / (step * 3)) }
            else if x >= rawPdf.last!.mid { density[i] = rawPdf.last!.density * max(0, 1 - (x - rawPdf.last!.mid) / (step * 3)) }
            else {
                for j in 0..<(rawPdf.count - 1) {
                    if x >= rawPdf[j].mid && x <= rawPdf[j + 1].mid {
                        let t = (x - rawPdf[j].mid) / (rawPdf[j + 1].mid - rawPdf[j].mid)
                        density[i] = rawPdf[j].density * (1 - t) + rawPdf[j + 1].density * t
                        break
                    }
                }
            }
        }
        let smoothed = density.enumerated().map { (i, _) in
            let prev = i > 0 ? density[i - 1] : density[i]
            let next = i < density.count - 1 ? density[i + 1] : density[i]
            return (prev + density[i] * 2 + next) / 4
        }
        let peak = max(smoothed.max() ?? 0.001, 0.001)
        return smoothed.map { ($0 / peak) * 96 }
    }
}
