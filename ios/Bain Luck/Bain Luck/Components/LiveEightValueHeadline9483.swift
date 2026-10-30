import SwiftUI

/// #9483 — A LIVE NFL/NBA HEADLINE THAT PRINTS ALL EIGHT VALUES: each team's
/// earlier chance, current chance, actual score and projected final, in four
/// aligned columns under the team's full name (design: selected study 3,
/// `eight-value-live-scoreboard-study-20261022/visual-refinement/
/// displayed-3-compact-momentum.png`, and the football reference
/// `football-comparison-headline-20261023/live-375.png` / `large-375.png`).
///
/// Away first, then home. The current chance is the one figure in the team's
/// colour at the larger size; the other six are the same high-contrast
/// figures at the comparison size. The projected final has a light outline.
/// Where the four columns do not fit the width the parent gives, or at an
/// accessibility text size, each team gets its own section with two labelled
/// pairs (earlier/current chance, score/projected final). Where even a pair's
/// two figures do not fit side by side, each value stands under its own label,
/// one below the other. The view grows downward; numbers are never scaled
/// down or scrolled sideways.
///
/// PRESENTATION ONLY. Every value arrives already decided by its existing
/// owner and is drawn as given:
///
///   - CURRENT CHANCE  `NFLPairedHeadline9483.Side.figure`, the hero's shared
///                     formatting, only for a priced side (`won == nil`) and
///                     only while the host's `EventHeadlinePhase9483` says
///                     `.current`. `.lastRecorded` prints "No recent
///                     probability"; no phase or no priced pair prints
///                     "Unavailable". `Side.pregame` is never read.
///   - EARLIER CHANCE  `PrematchReading`, each side through `formatProbability`
///                     with the reading's own rendered percent, under the
///                     reading's own word ("Pre-match" or "Opened"). A missing
///                     reading is unavailable, never the current number. A
///                     draw-priced sport's complement is withheld exactly as
///                     `DrawPricedWinner.printablePair` withholds it.
///   - SCORE           the host's scoreboard admission, independent of the
///                     pair: `.score(final: false)` prints, a genuine 0 prints
///                     0, `.versus`, a final score or nil print "Unavailable".
///                     `paired.center` is never read.
///   - PROJECTED FINAL `LivePregameComparison11296.Headline.current`'s printed
///                     integers under its own label. Nil is unavailable.
///
/// No parser, formatter, rounding, complement, clock, timer, retained copy,
/// fetch or admission of its own. A live NFL/NBA row only (`applies`); before
/// play, finals and every other sport keep their existing renderers.
///
/// ACTIONS. A current projected final becomes a 44-point "compare" control
/// only when the forecast carries its admitted baseline AND the host supplies
/// `onProjectionInspection`; it reports the side's `isHome`. An "Earlier"
/// control appears under an unavailable projected final only when the host
/// supplies that side's earlier callback, which it does only after admitting
/// earlier-only evidence for the same event, team, period, unit and cutoff.
/// The callbacks default to nil: `LivePregameComparison11296` qualifies a
/// baseline only beside a current pair, so no earlier-only evidence exists to
/// admit today, and this view never makes one from a held baseline.
///
/// Mount (Native, later — not done here): in `EventDetailView`'s adopted live
/// NFL/NBA headline, in place of `nflPairedHeadlineView` while `applies`, with
/// the existing view as the fallback. Inputs map one to one:
/// `nflPairedHeadline(event, hasScore:)` → `paired`; the phase the host already
/// resolves for `nflPairedPhase` → `chancePhase`;
/// `PrematchReading.resolve(prematch:opening:)` → `baseline`; the scoreboard's
/// `hasScore` pair as `.score(away:home:final: false)` → `score`;
/// `liveForecast11296(event, hasScore:)` → `forecast`; `event.awayTeam` /
/// `event.homeTeam` → names; `teamColors(event)` → colours;
/// `PeriodLabel.liveStatusText` → `gameState`.
struct LiveEightValueHeadline9483<Identity: View>: View {
    let sportKey: String?
    let status: String?
    let paired: NFLPairedHeadline9483?
    let chancePhase: EventHeadlinePhase9483?
    let baseline: PrematchReading?
    let score: NFLPairedHeadline9483.Center?
    let forecast: LivePregameComparison11296.Headline?
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    /// The host's own game-state words ("Q4 8:50"); printed as given.
    let gameState: String
    /// A team's existing logo or mark, by `isHome`. `EmptyView` is fine.
    let identity: (Bool) -> Identity
    /// The exact side's comparison, by `isHome`.
    let onProjectionInspection: ((Bool) -> Void)?
    /// Earlier-only forecast for one side. Nil unless the host independently
    /// admitted that side's earlier-only evidence; see the type comment.
    let onEarlierAwayInspection: (() -> Void)?
    let onEarlierHomeInspection: (() -> Void)?

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved football reference: 22-point comparison figures and a
    /// 26-point current chance, scaled with the reader's text size.
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 22
    @ScaledMetric(relativeTo: .title) private var currentSize: CGFloat = 26
    /// The narrowest a four-column cell may be, so "Unavailable" and other
    /// wrapping words never decide the grid's width.
    @ScaledMetric(relativeTo: .title2) private var columnWidth: CGFloat = 58
    @ScaledMetric(relativeTo: .title) private var currentColumnWidth: CGFloat = 70

    init(
        sportKey: String?, status: String?,
        paired: NFLPairedHeadline9483?, chancePhase: EventHeadlinePhase9483?,
        baseline: PrematchReading?, score: NFLPairedHeadline9483.Center?,
        forecast: LivePregameComparison11296.Headline?,
        awayName: String, homeName: String, awayColor: Color, homeColor: Color,
        gameState: String,
        @ViewBuilder identity: @escaping (Bool) -> Identity,
        onProjectionInspection: ((Bool) -> Void)? = nil,
        onEarlierAwayInspection: (() -> Void)? = nil,
        onEarlierHomeInspection: (() -> Void)? = nil
    ) {
        self.sportKey = sportKey
        self.status = status
        self.paired = paired
        self.chancePhase = chancePhase
        self.baseline = baseline
        self.score = score
        self.forecast = forecast
        self.awayName = awayName
        self.homeName = homeName
        self.awayColor = awayColor
        self.homeColor = homeColor
        self.gameState = gameState
        self.identity = identity
        self.onProjectionInspection = onProjectionInspection
        self.onEarlierAwayInspection = onEarlierAwayInspection
        self.onEarlierHomeInspection = onEarlierHomeInspection
    }

    static var accessibilityIdentifier: String { "live-eight-value-headline-9483" }

    // MARK: - What it prints

    /// One printed value, or the words that stand where it is absent.
    nonisolated struct Cell: Equatable {
        /// The column's label ("Pre-match chance", "Score", …).
        let label: String
        /// What the cell shows.
        let text: String
        /// False for an absence ("Unavailable", "No recent probability").
        let isValue: Bool

        /// The cell for VoiceOver: its label, then the value or the absence.
        var spoken: String { "\(label): \(text)" }
    }

    /// What the projected-final cell may do.
    nonisolated enum ForecastAction: Equatable {
        /// A plain outlined value, or nothing under an absence.
        case plain
        /// Compare the two projected finals for this side.
        case compare
        /// Open this side's separately admitted earlier forecast.
        case earlier
    }

    /// One team's four values.
    nonisolated struct Row: Equatable, Identifiable {
        let isHome: Bool
        let name: String
        let earlier: Cell
        let current: Cell
        let score: Cell
        let projected: Cell
        let action: ForecastAction
        var id: Bool { isHome }

        var cells: [Cell] { [earlier, current, score, projected] }

        /// Team, earlier chance, current chance, score, projected final.
        var spokenSummary: String {
            ([name] + cells.map(\.spoken)).joined(separator: ". ")
        }

        /// The control's spoken name, always with the team's.
        var actionLabel: String? {
            switch action {
            case .plain: return nil
            case .compare: return "Compare projected finals, \(name)"
            case .earlier: return "Earlier forecast, \(name)"
            }
        }
    }

    nonisolated struct Resolved: Equatable {
        let gameState: String
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
    static var noRecentProbabilityText: String { "No recent probability" }
    static var currentLabel: String { "Current chance" }
    static var scoreLabel: String { "Score" }
    static var earlierFallbackLabel: String { "Earlier chance" }
    static var earlierActionTitle: String { "Earlier" }

    /// A live NFL or NBA row; anything else keeps its existing renderer.
    static func applies(sportKey: String?, status: String?) -> Bool {
        NFLRecognizablePage9483.applies(sportKey: sportKey) && status == "live"
    }

    /// Accessibility sizes always take the labelled pairs; every other size
    /// takes the columns when the measured figures fit.
    static func arrangement(typeSize: DynamicTypeSize) -> Arrangement {
        typeSize.isAccessibilitySize ? .labelledPairs : .columnsWhenTheyFit
    }

    /// The eight cells, or nil where this view does not apply. Each value is
    /// decided on its own: one going missing never clears another.
    static func resolve(
        sportKey: String?, status: String?,
        paired: NFLPairedHeadline9483?,
        chancePhase: EventHeadlinePhase9483?,
        baseline: PrematchReading?,
        score: NFLPairedHeadline9483.Center?,
        forecast: LivePregameComparison11296.Headline?,
        awayName: String, homeName: String, gameState: String,
        canCompare: Bool, earlierAway: Bool, earlierHome: Bool
    ) -> Resolved? {
        guard applies(sportKey: sportKey, status: status) else { return nil }

        // Earlier chance: the reading's own pair, through the shared formatter.
        let earlierLabel = baseline.map { "\($0.captionWord) chance" } ?? earlierFallbackLabel
        let printable = baseline.flatMap {
            DrawPricedWinner.printablePair(away: $0.awayProbability, home: $0.homeProbability, sport: sportKey)
        }
        func earlier(_ index: Int) -> Cell {
            guard let baseline, let printable,
                  let probability = index == 0 ? printable.away : printable.home
            else { return Cell(label: earlierLabel, text: unavailableText, isValue: false) }
            let rendered = baseline.percents.indices.contains(index) ? baseline.percents[index] : nil
            return Cell(label: earlierLabel,
                        text: formatProbability(probability, renderedPercent: rendered), isValue: true)
        }

        // Current chance: a priced side, while the host says it is current.
        func current(_ side: NFLPairedHeadline9483.Side?) -> Cell {
            guard let side, side.won == nil, let chancePhase else {
                return Cell(label: currentLabel, text: unavailableText, isValue: false)
            }
            switch chancePhase {
            case .current: return Cell(label: currentLabel, text: side.figure, isValue: true)
            case .lastRecorded: return Cell(label: currentLabel, text: noRecentProbabilityText, isValue: false)
            }
        }

        // Score: the scoreboard's own, never the pair's centre.
        var actual: (away: Int, home: Int)?
        if case let .score(away, home, final) = score, !final { actual = (away, home) }
        func scoreCell(_ value: Int?) -> Cell {
            guard let value else { return Cell(label: scoreLabel, text: unavailableText, isValue: false) }
            return Cell(label: scoreLabel, text: "\(value)", isValue: true)
        }

        // Projected final: the admitted current pair's printed integers.
        let projectedLabel = forecast?.current.label
            ?? LiveProjectedFinalAdmission2920.format(forSport: sportKey)?.label
            ?? "Projected final"
        func projected(_ value: Int?) -> Cell {
            guard let value else { return Cell(label: projectedLabel, text: unavailableText, isValue: false) }
            return Cell(label: projectedLabel, text: "\(value)", isValue: true)
        }
        func action(earlierCapability: Bool) -> ForecastAction {
            if let forecast { return forecast.baseline != nil && canCompare ? .compare : .plain }
            return earlierCapability ? .earlier : .plain
        }

        return Resolved(
            gameState: gameState,
            away: Row(isHome: false, name: awayName,
                      earlier: earlier(0), current: current(paired?.away),
                      score: scoreCell(actual?.away), projected: projected(forecast?.current.away),
                      action: action(earlierCapability: earlierAway)),
            home: Row(isHome: true, name: homeName,
                      earlier: earlier(1), current: current(paired?.home),
                      score: scoreCell(actual?.home), projected: projected(forecast?.current.home),
                      action: action(earlierCapability: earlierHome)))
    }

    /// Calls the callback for exactly this side's action, and nothing else.
    static func perform(
        _ action: ForecastAction, isHome: Bool,
        compare: ((Bool) -> Void)?, earlierAway: (() -> Void)?, earlierHome: (() -> Void)?
    ) {
        switch action {
        case .plain: return
        case .compare: compare?(isHome)
        case .earlier: (isHome ? earlierHome : earlierAway)?()
        }
    }

    private var resolved: Resolved? {
        Self.resolve(
            sportKey: sportKey, status: status, paired: paired, chancePhase: chancePhase,
            baseline: baseline, score: score, forecast: forecast,
            awayName: awayName, homeName: homeName, gameState: gameState,
            canCompare: onProjectionInspection != nil,
            earlierAway: onEarlierAwayInspection != nil, earlierHome: onEarlierHomeInspection != nil)
    }

    // MARK: - Body

    var body: some View {
        if let resolved {
            VStack(alignment: .leading, spacing: 10) {
                if !resolved.gameState.isEmpty {
                    Text(resolved.gameState)
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
                    figure(row.current, size: currentSize, color: color(row), weight: .heavy,
                           width: currentColumnWidth)
                    figure(row.score, size: figureSize, color: .primary, width: columnWidth)
                    projectedCell(row, width: columnWidth)
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
                    pairLabel(row.current.label).gridCellUnsizedAxes(.horizontal)
                }
                GridRow(alignment: .firstTextBaseline) {
                    figure(row.earlier, size: figureSize, color: .primary, width: columnWidth)
                    figure(row.current, size: currentSize, color: color(row), weight: .heavy,
                           width: currentColumnWidth)
                }
                GridRow(alignment: .bottom) {
                    pairLabel(row.score.label, top: 8).gridCellUnsizedAxes(.horizontal)
                    pairLabel(row.projected.label, top: 8).gridCellUnsizedAxes(.horizontal)
                }
                GridRow(alignment: .firstTextBaseline) {
                    figure(row.score, size: figureSize, color: .primary, width: columnWidth)
                    projectedCell(row, width: columnWidth)
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
                    labelled(row.current.label) {
                        figure(row.current, size: currentSize, color: color(row), weight: .heavy, width: nil)
                    }
                    labelled(row.score.label) {
                        figure(row.score, size: figureSize, color: .primary, width: nil)
                    }
                    labelled(row.projected.label) {
                        projectedCell(row, width: nil)
                    }
                }
                if !row.isHome { Divider() }
            }
        }
    }

    // MARK: - Pieces

    private func color(_ row: Row) -> Color { row.isHome ? homeColor : awayColor }

    /// The full name in the team's colour, on its own row, carrying the team's
    /// whole spoken summary. The figures under it are not separate stops.
    private func nameRow(_ row: Row) -> some View {
        HStack(spacing: 8) {
            identity(row.isHome)
            Text(row.name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(color(row))
                .fixedSize(horizontal: false, vertical: true)
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

    /// A figure at its size, or the absence words at reading size. In a grid,
    /// a figure claims at least `width`; an absence asks for exactly `width`
    /// and wraps inside whatever the column becomes.
    @ViewBuilder
    private func figure(_ cell: Cell, size: CGFloat, color: Color,
                        weight: Font.Weight = .bold, width: CGFloat?) -> some View {
        if cell.isValue {
            Text(cell.text)
                .font(.system(size: size, weight: weight, design: .rounded).monospacedDigit())
                .foregroundStyle(color)
                .lineLimit(1)
                .fixedSize()
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

    /// The projected final: outlined; a 44-point control only where `row.action`
    /// says so. An unavailable forecast is never filled from an earlier one.
    @ViewBuilder
    private func projectedCell(_ row: Row, width: CGFloat?) -> some View {
        let cell = row.projected
        if cell.isValue {
            let value = Text(cell.text)
                .font(.system(size: figureSize, weight: .bold, design: .rounded).monospacedDigit())
                .foregroundStyle(Color.primary)
                .lineLimit(1)
                .fixedSize()
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
                .overlay {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .strokeBorder(Color.secondary.opacity(0.45), lineWidth: 1)
                }
            Group {
                if row.action == .compare {
                    Button {
                        perform(row)
                    } label: {
                        value
                            .frame(minWidth: 44, minHeight: 44, alignment: .leading)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(row.actionLabel ?? "")
                    .accessibilityValue(cell.spoken)
                } else {
                    value.accessibilityHidden(true)
                }
            }
            .frame(minWidth: width, maxWidth: .infinity, alignment: .leading)
        } else {
            VStack(alignment: .leading, spacing: 0) {
                absence(cell.text, width: width)
                    .accessibilityHidden(true)
                if row.action == .earlier {
                    Button {
                        perform(row)
                    } label: {
                        Text(Self.earlierActionTitle)
                            .font(.footnote.weight(.semibold))
                            .frame(minWidth: 44, minHeight: 44, alignment: .leading)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel(row.actionLabel ?? "")
                }
            }
            .frame(minWidth: 0, idealWidth: width, maxWidth: .infinity, alignment: .leading)
        }
    }

    private func perform(_ row: Row) {
        Self.perform(row.action, isHome: row.isHome, compare: onProjectionInspection,
                     earlierAway: onEarlierAwayInspection, earlierHome: onEarlierHomeInspection)
    }
}

extension LiveEightValueHeadline9483 where Identity == EmptyView {
    /// No team marks (tests and previews).
    init(
        sportKey: String?, status: String?,
        paired: NFLPairedHeadline9483?, chancePhase: EventHeadlinePhase9483?,
        baseline: PrematchReading?, score: NFLPairedHeadline9483.Center?,
        forecast: LivePregameComparison11296.Headline?,
        awayName: String, homeName: String, awayColor: Color, homeColor: Color,
        gameState: String,
        onProjectionInspection: ((Bool) -> Void)? = nil,
        onEarlierAwayInspection: (() -> Void)? = nil,
        onEarlierHomeInspection: (() -> Void)? = nil
    ) {
        self.init(
            sportKey: sportKey, status: status, paired: paired, chancePhase: chancePhase,
            baseline: baseline, score: score, forecast: forecast,
            awayName: awayName, homeName: homeName, awayColor: awayColor, homeColor: homeColor,
            gameState: gameState, identity: { _ in EmptyView() },
            onProjectionInspection: onProjectionInspection,
            onEarlierAwayInspection: onEarlierAwayInspection,
            onEarlierHomeInspection: onEarlierHomeInspection)
    }
}
