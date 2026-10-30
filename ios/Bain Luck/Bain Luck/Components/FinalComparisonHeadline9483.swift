import SwiftUI

/// #9483 — A FINISHED NFL/NBA HEADLINE THAT COMPARES EACH TEAM'S EARLIER
/// EXPECTATION WITH ITS ACTUAL FINAL: the chance before the game, the score
/// forecast before the scheduled start, the final score, and the final's
/// distance from that forecast, in four aligned columns under the team's full
/// name and its result (design: `football-comparison-headline-20261023/
/// final-375.png`, `final-393.png`, `final-wide.png`).
///
/// Away first, then home. The final score is the one figure in the team's
/// colour at the larger size; the other three are the same high-contrast
/// figures at the comparison size. Where the four columns do not fit the width
/// the parent gives, or at an accessibility text size, each team gets two
/// labelled pairs (chance/forecast, final score/difference). Where even a
/// pair's two figures do not fit side by side, each value stands under its own
/// label, one below the other; where a figure's unit or qualifier ("pts
/// above") still does not fit beside it, the words move under the figure and
/// wrap. The view grows downward; numbers are never split, scaled down or
/// scrolled sideways.
///
/// PRESENTATION ONLY. Every value arrives already decided by its existing
/// owner and is drawn as given:
///
///   - RESULT          `NFLPairedHeadline9483.Side.figure` ("Won"/"Lost"),
///                     only from a decided final whose two verdicts are both
///                     present and opposite. Printed beside the name, never in
///                     a number column. No winner is read from the scores or a
///                     probability here.
///   - EARLIER CHANCE  `PrematchReading`, each side through `formatProbability`
///                     with the reading's own rendered percent, under the
///                     reading's own word ("Pre-match" or "Opened"). A missing
///                     reading is unavailable — never a terminal 0%/100%, and
///                     never `Side.pregame` parsed back into a number.
///   - FORECAST        `FinalForecastComparison11296.Qualified`'s raw halves,
///                     already qualified for this final and period, drawn with
///                     `NFLFinishCardView9483.points` (a half point stays), so
///                     the forecast and its difference agree. The rounded
///                     `Comparison` integers are the finished cards' display
///                     and are not read here. `comparison.label` is the spoken
///                     basis; the column's short header is "Before-start
///                     forecast". Nil is unavailable.
///   - FINAL SCORE     the host's scoreboard admission, independent of the
///                     pair: only `.score(final: true)` prints, a genuine 0
///                     prints 0, `.versus`, a nonfinal score or nil print
///                     "Unavailable". `paired.center` is never read.
///   - VS FORECAST     actual minus that team's raw forecast, only when both
///                     exist. The magnitude is `deltaPointsNumber`'s, with an
///                     explicit sign and the points unit. Exactly zero reads
///                     "At forecast"; a nonzero difference that magnitude
///                     prints as 0.0 reads "less than 0.1" above or below. No
///                     word or colour says the forecast was right or wrong.
///
/// No parser, rounding helper, formatter, clock, timer, retained copy, fetch,
/// navigation state or admission of its own. A finished NFL/NBA row with a
/// decided pair only (`resolve`); before play, live, draws and unresolved
/// finals and every other sport keep their existing renderers.
///
/// ACTION. The forecast and difference become a 44-point control for a team
/// only when that team has a qualified forecast AND an actual final AND the
/// host supplies `onForecastInspection`; it reports the side's `isHome`. One
/// VoiceOver stop per team names the team; the difference's duplicate target is
/// hidden from assistive tech so the same action is not read twice. No
/// callback: plain values with no arrow.
///
/// Mount (Native, later — not done here): in `EventDetailView`, in place of
/// `nflPairedHeadlineView` AND the `FinalForecastLine11296` under it while
/// `resolve` answers, with both kept as the fallback, so no forecast or
/// pre-match row is printed twice. Inputs map one to one, from one same-event
/// snapshot: `nflPairedHeadline(event, hasScore:)` → `paired`;
/// `PrematchReading.resolve(prematch:opening:)` → `baseline`; the scoreboard's
/// `hasScore` pair as `.score(away:home:final: true)` → `score`;
/// `EventDetailView.qualifiedFinalForecast11296(event)` → `forecast`;
/// `event.awayTeam` / `event.homeTeam` → names; `teamColors(event)` → colours;
/// the host's existing final/date words → `finalContext`.
struct FinalComparisonHeadline9483<Identity: View>: View {
    let sportKey: String?
    let status: String?
    let paired: NFLPairedHeadline9483?
    let baseline: PrematchReading?
    let score: NFLPairedHeadline9483.Center?
    let forecast: FinalForecastComparison11296.Qualified?
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    /// The host's own final/date words ("Final · Sep 28"); printed as given.
    let finalContext: String
    /// A team's existing logo or mark, by `isHome`. `EmptyView` is fine.
    let identity: (Bool) -> Identity
    /// The exact side's forecast comparison, by `isHome`.
    let onForecastInspection: ((Bool) -> Void)?

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved football reference: 22-point comparison figures and a
    /// 26-point final score, scaled with the reader's text size.
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 22
    @ScaledMetric(relativeTo: .title) private var finalSize: CGFloat = 26
    /// The unit after a difference, like the reference's small "%".
    @ScaledMetric(relativeTo: .footnote) private var suffixSize: CGFloat = 13
    /// The narrowest a four-column cell may be, so "Unavailable" and other
    /// wrapping words never decide the grid's width.
    @ScaledMetric(relativeTo: .title2) private var columnWidth: CGFloat = 58
    @ScaledMetric(relativeTo: .title) private var finalColumnWidth: CGFloat = 58

    init(
        sportKey: String?, status: String?,
        paired: NFLPairedHeadline9483?, baseline: PrematchReading?,
        score: NFLPairedHeadline9483.Center?,
        forecast: FinalForecastComparison11296.Qualified?,
        awayName: String, homeName: String, awayColor: Color, homeColor: Color,
        finalContext: String,
        @ViewBuilder identity: @escaping (Bool) -> Identity,
        onForecastInspection: ((Bool) -> Void)? = nil
    ) {
        self.sportKey = sportKey
        self.status = status
        self.paired = paired
        self.baseline = baseline
        self.score = score
        self.forecast = forecast
        self.awayName = awayName
        self.homeName = homeName
        self.awayColor = awayColor
        self.homeColor = homeColor
        self.finalContext = finalContext
        self.identity = identity
        self.onForecastInspection = onForecastInspection
    }

    static var accessibilityIdentifier: String { "final-comparison-headline-9483" }

    // MARK: - What it prints

    /// One printed value, or the words that stand where it is absent.
    nonisolated struct Cell: Equatable {
        /// The column's visible label ("Pre-match chance", "Final score", …).
        let label: String
        /// What the cell shows.
        let text: String
        /// A smaller unit after the figure ("pts"), or nil.
        let suffix: String?
        /// The cell for VoiceOver: its full basis, then the value in words.
        let spoken: String
        /// False for an absence ("Unavailable").
        let isValue: Bool
    }

    /// One team's result and four values.
    nonisolated struct Row: Equatable, Identifiable {
        let isHome: Bool
        let name: String
        /// The supplied verdict word, "Won" or "Lost".
        let result: String
        let earlier: Cell
        let forecast: Cell
        let final: Cell
        let difference: Cell
        /// Whether the forecast and difference open this side's comparison.
        let inspects: Bool
        var id: Bool { isHome }

        var cells: [Cell] { [earlier, forecast, final, difference] }

        /// Team and result, then each value with its full basis.
        var spokenSummary: String {
            (["\(name), \(result)"] + cells.map(\.spoken)).joined(separator: ". ")
        }

        /// The control's spoken name, always with the team's.
        var actionLabel: String? {
            inspects ? "Compare final with forecast, \(name)" : nil
        }
    }

    nonisolated struct Resolved: Equatable {
        let finalContext: String
        let away: Row
        let home: Row
        /// The four column labels, in order.
        var headers: [String] { away.cells.map(\.label) }
        var rows: [Row] { [away, home] }
    }

    /// How the view arranges itself. Every arrangement ends in the stacked
    /// labelled values, which need only one figure's width.
    nonisolated enum Arrangement: Equatable {
        /// Four columns when they fit the parent's width, else labelled pairs
        /// when they fit, else stacked labelled values.
        case columnsWhenTheyFit
        /// Labelled pairs when they fit, else stacked labelled values; never
        /// the columns.
        case labelledPairs
    }

    static var unavailableText: String { "Unavailable" }
    static var earlierFallbackLabel: String { "Earlier chance" }
    /// The forecast column's short header; the full basis is spoken.
    static var forecastHeader: String { "Before-start forecast" }
    static var finalLabel: String { "Final score" }
    static var differenceLabel: String { "vs forecast" }
    static var differenceSpokenLabel: String { "Difference from forecast" }
    /// The visible unit after a difference, as the app's move captions say it.
    static var pointsSuffix: String { "pts" }

    /// A finished NFL or NBA row; anything else keeps its existing renderer.
    static func applies(sportKey: String?, status: String?) -> Bool {
        NFLRecognizablePage9483.applies(sportKey: sportKey) && EventState.isFinished(status)
    }

    /// Accessibility sizes always take the labelled pairs; every other size
    /// takes the columns when the measured figures fit.
    static func arrangement(typeSize: DynamicTypeSize) -> Arrangement {
        typeSize.isAccessibilitySize ? .labelledPairs : .columnsWhenTheyFit
    }

    /// The difference cell for one side: actual minus that side's qualified raw
    /// forecast, or unavailable when either is missing.
    static func differenceCell(actual: Int?, forecast: Double?, unit: String) -> Cell {
        guard let actual, let forecast else {
            return Cell(label: differenceLabel, text: unavailableText, suffix: nil,
                        spoken: "\(differenceSpokenLabel): \(unavailableText)", isValue: false)
        }
        let difference = Double(actual) - forecast
        let magnitude = deltaPointsNumber(difference)
        let direction = difference > 0 ? "above" : "below"
        if difference == 0 {
            return Cell(label: differenceLabel, text: "0", suffix: pointsSuffix,
                        spoken: "\(differenceSpokenLabel): At forecast", isValue: true)
        }
        // A real difference too small for the shared magnitude's one decimal is
        // never printed as ±0.0.
        if magnitude == deltaPointsNumber(0) {
            return Cell(label: differenceLabel, text: "<0.1", suffix: "\(pointsSuffix) \(direction)",
                        spoken: "\(differenceSpokenLabel): less than 0.1 \(unit) \(direction)", isValue: true)
        }
        let sign = difference > 0 ? "+" : "\u{2212}"
        return Cell(label: differenceLabel, text: "\(sign)\(magnitude)", suffix: pointsSuffix,
                    spoken: "\(differenceSpokenLabel): \(magnitude) \(unit) \(direction)", isValue: true)
    }

    /// The four cells per team, or nil where this view does not apply. Each
    /// value is decided on its own: one going missing never clears another.
    static func resolve(
        sportKey: String?, status: String?,
        paired: NFLPairedHeadline9483?,
        baseline: PrematchReading?,
        score: NFLPairedHeadline9483.Center?,
        forecast: FinalForecastComparison11296.Qualified?,
        awayName: String, homeName: String, finalContext: String,
        canInspect: Bool
    ) -> Resolved? {
        guard applies(sportKey: sportKey, status: status),
              let paired,
              let awayWon = paired.away.won, let homeWon = paired.home.won,
              awayWon != homeWon
        else { return nil }

        // Earlier chance: the reading's own pair, through the shared formatter.
        let earlierLabel = baseline.map { "\($0.captionWord) chance" } ?? earlierFallbackLabel
        func earlier(_ index: Int) -> Cell {
            guard let baseline else {
                return Cell(label: earlierLabel, text: unavailableText, suffix: nil,
                            spoken: "\(earlierLabel): \(unavailableText)", isValue: false)
            }
            let probability = index == 0 ? baseline.awayProbability : baseline.homeProbability
            let rendered = baseline.percents.indices.contains(index) ? baseline.percents[index] : nil
            let text = formatProbability(probability, renderedPercent: rendered)
            return Cell(label: earlierLabel, text: text, suffix: nil,
                        spoken: "\(earlierLabel): \(text)", isValue: true)
        }

        // Final score: the scoreboard's own final, never the pair's centre.
        var actual: (away: Int, home: Int)?
        if case let .score(away, home, final) = score, final { actual = (away, home) }
        func finalCell(_ value: Int?) -> Cell {
            guard let value else {
                return Cell(label: finalLabel, text: unavailableText, suffix: nil,
                            spoken: "\(finalLabel): \(unavailableText)", isValue: false)
            }
            return Cell(label: finalLabel, text: "\(value)", suffix: nil,
                        spoken: "\(finalLabel): \(value)", isValue: true)
        }

        // Forecast: the qualified raw half, printed as the finish card prints it.
        let unit = FinalForecastComparison11296.unit(forSport: sportKey) ?? "points"
        let basis = forecast?.comparison.label ?? forecastHeader
        func forecastCell(_ value: Double?) -> Cell {
            guard let value else {
                return Cell(label: forecastHeader, text: unavailableText, suffix: nil,
                            spoken: "\(basis): \(unavailableText)", isValue: false)
            }
            let text = NFLFinishCardView9483.points(value)
            return Cell(label: forecastHeader, text: text, suffix: nil,
                        spoken: "\(basis): \(text) \(unit)", isValue: true)
        }

        func row(isHome: Bool) -> Row {
            let side = isHome ? paired.home : paired.away
            let actualSide = actual.map { isHome ? $0.home : $0.away }
            let forecastSide = forecast.map { isHome ? $0.home : $0.away }
            return Row(
                isHome: isHome, name: isHome ? homeName : awayName, result: side.figure,
                earlier: earlier(isHome ? 1 : 0),
                forecast: forecastCell(forecastSide),
                final: finalCell(actualSide),
                difference: differenceCell(actual: actualSide, forecast: forecastSide, unit: unit),
                inspects: canInspect && actualSide != nil && forecastSide != nil)
        }

        return Resolved(finalContext: finalContext, away: row(isHome: false), home: row(isHome: true))
    }

    /// Calls the callback for exactly this side, and only where it inspects.
    static func perform(_ row: Row, inspect: ((Bool) -> Void)?) {
        guard row.inspects else { return }
        inspect?(row.isHome)
    }

    private var resolved: Resolved? {
        Self.resolve(
            sportKey: sportKey, status: status, paired: paired, baseline: baseline,
            score: score, forecast: forecast,
            awayName: awayName, homeName: homeName, finalContext: finalContext,
            canInspect: onForecastInspection != nil)
    }

    // MARK: - Body

    var body: some View {
        if let resolved {
            VStack(alignment: .leading, spacing: 10) {
                if !resolved.finalContext.isEmpty {
                    Text(resolved.finalContext)
                        .font(.subheadline.weight(.semibold).monospacedDigit())
                        .foregroundStyle(Color.primary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                // Each grid's ideal width is its figures' alone (names and labels
                // take the width the figures give them; absences ask for a column's
                // width and wrap in it), so a header's unwrapped length never
                // pushes the view into a taller arrangement.
                switch Self.arrangement(typeSize: typeSize) {
                case .labelledPairs:
                    ViewThatFits(in: .horizontal) {
                        labelledPairs(resolved)
                        stackedValues(resolved)
                    }
                case .columnsWhenTheyFit:
                    ViewThatFits(in: .horizontal) {
                        columns(resolved)
                        labelledPairs(resolved)
                        stackedValues(resolved)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(Self.accessibilityIdentifier)
        }
    }

    // MARK: - Four columns

    private func columns(_ resolved: Resolved) -> some View {
        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 6) {
            GridRow(alignment: .bottom) {
                ForEach(Array(resolved.headers.enumerated()), id: \.offset) { _, header in
                    columnLabel(header)
                        .gridCellUnsizedAxes(.horizontal)
                }
            }
            ForEach(resolved.rows) { row in
                nameRow(row)
                    .gridCellUnsizedAxes(.horizontal)
                    .padding(.top, row.isHome ? 0 : 4)
                GridRow(alignment: .firstTextBaseline) {
                    figure(row.earlier, size: figureSize, color: .primary, width: columnWidth)
                    inspectable(row, row.forecast, primaryTarget: true, width: columnWidth)
                    figure(row.final, size: finalSize, color: color(row), weight: .heavy,
                           width: finalColumnWidth)
                    inspectable(row, row.difference, primaryTarget: false, width: columnWidth)
                }
                if !row.isHome {
                    Divider().gridCellUnsizedAxes(.horizontal)
                }
            }
        }
    }

    // MARK: - Labelled pairs

    /// Both teams in one grid, so their pairs share columns and the fit is
    /// decided for both at once. Labels and figures are separate rows, so a
    /// label that wraps never moves its figure off the other figure's baseline.
    /// Row spacing sits on the cells: a modifier on a GridRow would turn it
    /// into one spanning cell.
    private func labelledPairs(_ resolved: Resolved) -> some View {
        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 2) {
            ForEach(resolved.rows) { row in
                nameRow(row)
                    .gridCellUnsizedAxes(.horizontal)
                    .padding(.bottom, 6)
                GridRow(alignment: .bottom) {
                    pairLabel(row.earlier.label).gridCellUnsizedAxes(.horizontal)
                    pairLabel(row.forecast.label).gridCellUnsizedAxes(.horizontal)
                }
                GridRow(alignment: .firstTextBaseline) {
                    figure(row.earlier, size: figureSize, color: .primary, width: columnWidth)
                    inspectable(row, row.forecast, primaryTarget: true, width: columnWidth)
                }
                GridRow(alignment: .bottom) {
                    pairLabel(row.final.label, top: 8).gridCellUnsizedAxes(.horizontal)
                    pairLabel(row.difference.label, top: 8).gridCellUnsizedAxes(.horizontal)
                }
                GridRow(alignment: .firstTextBaseline) {
                    figure(row.final, size: finalSize, color: color(row), weight: .heavy,
                           width: finalColumnWidth)
                    inspectable(row, row.difference, primaryTarget: false, width: columnWidth)
                }
                if !row.isHome {
                    Divider()
                        .gridCellUnsizedAxes(.horizontal)
                        .padding(.vertical, 12)
                }
            }
        }
    }

    // MARK: - Stacked labelled values

    /// The last arrangement: each value under its own label, in reading order,
    /// so only the widest single figure has to fit.
    private func stackedValues(_ resolved: Resolved) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(resolved.rows) { row in
                VStack(alignment: .leading, spacing: 8) {
                    nameRow(row)
                    labelled(row.earlier.label) {
                        figure(row.earlier, size: figureSize, color: .primary, width: nil)
                    }
                    labelled(row.forecast.label) {
                        inspectable(row, row.forecast, primaryTarget: true, width: nil)
                    }
                    labelled(row.final.label) {
                        figure(row.final, size: finalSize, color: color(row), weight: .heavy, width: nil)
                    }
                    labelled(row.difference.label) {
                        inspectable(row, row.difference, primaryTarget: false, width: nil)
                    }
                }
                if !row.isHome { Divider() }
            }
        }
    }

    // MARK: - Pieces

    private func color(_ row: Row) -> Color { row.isHome ? homeColor : awayColor }

    /// The full name in the team's colour with its supplied result, on its own
    /// row, carrying the team's whole spoken summary. The figures under it are
    /// not separate stops.
    private func nameRow(_ row: Row) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            identity(row.isHome)
            Text(row.name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(color(row))
                .fixedSize(horizontal: false, vertical: true)
            Text(row.result)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(color(row))
                .fixedSize()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(row.spokenSummary)
    }

    private func columnLabel(_ text: String) -> some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityHidden(true)
    }

    private func labelled<Value: View>(_ label: String, @ViewBuilder value: () -> Value) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            pairLabel(label)
            value()
        }
    }

    private func pairLabel(_ text: String, top: CGFloat = 0) -> some View {
        Text(text)
            .font(.subheadline)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, top)
            .accessibilityHidden(true)
    }

    /// The figure itself, whole and on one line, with its smaller unit (and,
    /// for a control, its arrow) after it on the same baseline where they fit
    /// the width offered. Where they do not, the unit and arrow move under the
    /// figure as one run of words that wraps there, so a qualifier such as
    /// "pts above" never forces the figure's line wider than the parent. The
    /// figure itself is never wrapped, split or scaled; its first baseline stays
    /// the cell's in both arrangements.
    private func figureText(_ cell: Cell, size: CGFloat, color: Color,
                            weight: Font.Weight, arrow: Bool = false) -> some View {
        let number = Text(cell.text)
            .font(.system(size: size, weight: weight, design: .rounded).monospacedDigit())
            .foregroundStyle(color)
            .lineLimit(1)
            .fixedSize()
        let unit = cell.suffix.map { suffixText($0) }
        return ViewThatFits(in: .horizontal) {
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 2) {
                    number
                    if let unit { unit.lineLimit(1).fixedSize() }
                }
                if arrow { arrowText.fixedSize() }
            }
            VStack(alignment: .leading, spacing: 2) {
                number
                if let trailing = trailingText(unit, arrow: arrow) {
                    trailing.fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func suffixText(_ suffix: String) -> Text {
        Text(suffix)
            .font(.system(size: suffixSize, weight: .semibold, design: .rounded))
            .foregroundStyle(Color.primary)
    }

    private var arrowText: Text {
        Text(Image(systemName: "arrow.up.right"))
            .font(.caption.weight(.semibold))
            .foregroundStyle(.secondary)
    }

    /// The unit and arrow as one wrapping run, for under the figure.
    private func trailingText(_ unit: Text?, arrow: Bool) -> Text? {
        guard arrow else { return unit }
        guard let unit else { return arrowText }
        return unit + Text(" ") + arrowText
    }

    /// A figure at its size, or the absence words at reading size. In a grid,
    /// a figure claims at least `width`; an absence asks for exactly `width`
    /// and wraps inside whatever the column becomes.
    @ViewBuilder
    private func figure(_ cell: Cell, size: CGFloat, color: Color,
                        weight: Font.Weight = .bold, width: CGFloat?) -> some View {
        if cell.isValue {
            figureText(cell, size: size, color: color, weight: weight)
                .frame(minWidth: width, maxWidth: .infinity, alignment: .leading)
                .accessibilityHidden(true)
        } else {
            absence(cell.text, width: width)
                .accessibilityHidden(true)
        }
    }

    private func absence(_ text: String, width: CGFloat?) -> some View {
        Text(text)
            .font(.footnote.weight(.semibold))
            .foregroundStyle(Color.primary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(minWidth: 0, idealWidth: width, maxWidth: .infinity, alignment: .leading)
    }

    /// The forecast or the difference: a 44-point control with an arrow only
    /// where `row.inspects`, otherwise the plain figure. The forecast is the
    /// team's one VoiceOver stop for the action; the difference's target does
    /// the same thing and is hidden from assistive tech so it is not read twice.
    @ViewBuilder
    private func inspectable(_ row: Row, _ cell: Cell, primaryTarget: Bool, width: CGFloat?) -> some View {
        if cell.isValue && row.inspects {
            Button {
                Self.perform(row, inspect: onForecastInspection)
            } label: {
                // The arrow travels with the unit, so it never pins a full-width
                // run beside the figure either.
                figureText(cell, size: figureSize, color: .primary, weight: .bold, arrow: true)
                    .frame(minWidth: 44, minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .frame(minWidth: width, maxWidth: .infinity, alignment: .leading)
            .accessibilityLabel(row.actionLabel ?? "")
            .accessibilityValue("\(row.forecast.spoken). \(row.difference.spoken)")
            .accessibilityHidden(!primaryTarget)
        } else {
            figure(cell, size: figureSize, color: .primary, width: width)
        }
    }
}

extension FinalComparisonHeadline9483 where Identity == EmptyView {
    /// No team marks (tests and previews).
    init(
        sportKey: String?, status: String?,
        paired: NFLPairedHeadline9483?, baseline: PrematchReading?,
        score: NFLPairedHeadline9483.Center?,
        forecast: FinalForecastComparison11296.Qualified?,
        awayName: String, homeName: String, awayColor: Color, homeColor: Color,
        finalContext: String,
        onForecastInspection: ((Bool) -> Void)? = nil
    ) {
        self.init(
            sportKey: sportKey, status: status, paired: paired, baseline: baseline,
            score: score, forecast: forecast,
            awayName: awayName, homeName: homeName, awayColor: awayColor, homeColor: homeColor,
            finalContext: finalContext, identity: { _ in EmptyView() },
            onForecastInspection: onForecastInspection)
    }
}
