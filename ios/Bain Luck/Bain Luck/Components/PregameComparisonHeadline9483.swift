import SwiftUI

/// #9483 — BEFORE AN NFL/NBA GAME, EACH TEAM'S WIN CHANCE AND PROJECTED FINAL
/// AS TWO ALIGNED FIGURES under the team's full name, with the host's start and
/// broadcast words above them (design: `football-comparison-headline-20261023/
/// pregame-375.png`).
///
/// Away first, then home. The win chance is the strongest figure, in the
/// team's colour at the larger size; the projected final is a high-contrast
/// figure at the comparison size. One grid holds both teams, so the figures
/// line up whatever the headers or the full names wrap to. Where the two
/// columns do not fit the width the parent gives, or at an accessibility text
/// size, each value stands under its own label, one below the other. The view
/// grows downward; numbers are never scaled down, cut or scrolled sideways.
///
/// PRESENTATION ONLY. Every value arrives already decided by its existing
/// owner and is drawn as given:
///
///   - WIN CHANCE      `NFLPairedHeadline9483.Side.figure`, the priced pair the
///                     host resolver admitted (its venue-settled refusal and
///                     #2085's both-or-neither percents included), printed only
///                     while the caller's `EventHeadlinePhase9483` says
///                     `.current`. `.lastRecorded` prints "No recent
///                     probability" and no number; a missing phase prints
///                     "Unavailable". `Side.pregame` is never read, and no
///                     chance is rounded, complemented or aged here.
///   - PROJECTED FINAL the host's printed integers, from its existing
///                     `projectionText` → `projectionFigure9483` →
///                     `projectedPair11285` chain. A supplied 0 prints 0; nil
///                     prints "Unavailable", never 0. Under the host's own
///                     caption (`forecastLabel`, "Projected final"), visible
///                     and spoken.
///   - CONTEXT         the host's pregame start/broadcast words
///                     (`adoptedPregameContext9483`), printed verbatim and
///                     wrapping. No date, clock or broadcast is formatted or
///                     looked up here.
///
/// The two absences are independent: a chance going missing never clears the
/// forecast, and the reverse. A missing pair declines the whole view, so the
/// host's existing renderer stays; the chance is never rebuilt from a baseline.
///
/// No parser, rounding helper, formatter, clock, timer, retained copy, fetch,
/// navigation state or admission of its own. An upcoming NFL/NBA row only
/// (`applies`): status scheduled or nil, not started on the host's clock, not
/// the opening line, with a priced pair and no score. Live, finished,
/// suspended, postponed and every other state or sport keep their existing
/// renderers.
///
/// ACTION. The projected final becomes a 44-point control for a team only when
/// there is a projection AND the host supplies `onForecastInspection`; it
/// reports the side's `isHome` and is named for that team. No callback: a plain
/// value with no arrow. The host owns the route and the return focus.
///
/// Mount (Native, later — not done here): in `EventDetailView`, in place of
/// `nflPairedHeadlineView` AND its pregame `adoptedPregameProjection11285` row
/// while `resolve` answers, with both kept as the fallback. Inputs map one to
/// one, from one same-event snapshot: `event.sport` / `event.status` →
/// `sportKey` / `status`; `EventState.hasStarted(commenceTime:now:)` on the
/// host's clock → `hasStarted`; `OpeningLineHero.resolve(...).isOpeningLine` →
/// `isOpeningLine`; `nflPairedHeadline(event, hasScore:)` → `paired`; the phase
/// the host's `headlinePhaseLabel` resolves → `chancePhase`;
/// `projectedPair11285(projectionFigure9483(projectionText(...)))` →
/// `projectedPair`; the host's "Projected final" caption → `forecastLabel`;
/// `event.awayTeam` / `event.homeTeam` → names; `teamColors(event)` → colours;
/// `adoptedPregameContext9483(event)` → `pregameContext`.
struct PregameComparisonHeadline9483<Identity: View>: View {
    let sportKey: String?
    let status: String?
    /// `EventState.hasStarted(commenceTime:now:)` on the host's clock; an
    /// undated game has started, so it declines.
    let hasStarted: Bool
    let isOpeningLine: Bool
    let paired: NFLPairedHeadline9483?
    let chancePhase: EventHeadlinePhase9483?
    let projectedPair: (away: Int, home: Int)?
    /// The host's caption for the projection ("Projected final").
    let forecastLabel: String
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    /// The host's start/broadcast words ("ESPN · Sep 28, 5:15 PM"); printed as
    /// given. Nil or empty prints nothing.
    let pregameContext: String?
    /// A team's existing logo or mark, by `isHome`. `EmptyView` is fine.
    let identity: (Bool) -> Identity
    /// The exact side's projection, by `isHome`.
    let onForecastInspection: ((Bool) -> Void)?

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved football reference: a 26-point chance and a 22-point
    /// projected final, scaled with the reader's text size.
    @ScaledMetric(relativeTo: .title) private var chanceSize: CGFloat = 26
    @ScaledMetric(relativeTo: .title2) private var forecastSize: CGFloat = 22
    /// The narrowest a column may be, so "Unavailable" and other wrapping words
    /// never decide the grid's width.
    @ScaledMetric(relativeTo: .title) private var chanceColumnWidth: CGFloat = 72
    @ScaledMetric(relativeTo: .title2) private var forecastColumnWidth: CGFloat = 58

    init(
        sportKey: String?, status: String?, hasStarted: Bool, isOpeningLine: Bool,
        paired: NFLPairedHeadline9483?, chancePhase: EventHeadlinePhase9483?,
        projectedPair: (away: Int, home: Int)?, forecastLabel: String,
        awayName: String, homeName: String, awayColor: Color, homeColor: Color,
        pregameContext: String?,
        @ViewBuilder identity: @escaping (Bool) -> Identity,
        onForecastInspection: ((Bool) -> Void)? = nil
    ) {
        self.sportKey = sportKey
        self.status = status
        self.hasStarted = hasStarted
        self.isOpeningLine = isOpeningLine
        self.paired = paired
        self.chancePhase = chancePhase
        self.projectedPair = projectedPair
        self.forecastLabel = forecastLabel
        self.awayName = awayName
        self.homeName = homeName
        self.awayColor = awayColor
        self.homeColor = homeColor
        self.pregameContext = pregameContext
        self.identity = identity
        self.onForecastInspection = onForecastInspection
    }

    static var accessibilityIdentifier: String { "pregame-comparison-headline-9483" }

    // MARK: - What it prints

    /// One printed value, or the words that stand where it is absent.
    nonisolated struct Cell: Equatable {
        /// The column's visible label ("Win chance", "Projected final").
        let label: String
        /// What the cell shows.
        let text: String
        /// The cell for VoiceOver: its label, then the value in words.
        let spoken: String
        /// False for an absence ("Unavailable", "No recent probability").
        let isValue: Bool
    }

    /// One team's two values.
    nonisolated struct Row: Equatable, Identifiable {
        let isHome: Bool
        let name: String
        let chance: Cell
        let forecast: Cell
        /// Whether the projected final opens this side's projection.
        let inspects: Bool
        var id: Bool { isHome }

        var cells: [Cell] { [chance, forecast] }

        /// The team, then each value with its label.
        var spokenSummary: String {
            ([name] + cells.map(\.spoken)).joined(separator: ". ")
        }

        /// The control's spoken name, always with the team's.
        var actionLabel: String? {
            inspects ? "\(forecast.label), \(name)" : nil
        }
    }

    nonisolated struct Resolved: Equatable {
        /// The host's words, verbatim; nil where it supplied none.
        let context: String?
        let away: Row
        let home: Row
        /// The two column labels, in order.
        var headers: [String] { away.cells.map(\.label) }
        var rows: [Row] { [away, home] }
        /// What VoiceOver reaches, top to bottom: the context, then each team.
        var spokenOrder: [String] {
            (context.map { [$0] } ?? []) + rows.map(\.spokenSummary)
        }
    }

    /// How the view arranges itself. Both end in the stacked labelled values,
    /// which need only one figure's width.
    nonisolated enum Arrangement: Equatable {
        /// Two columns when they fit the parent's width, else stacked values.
        case columnsWhenTheyFit
        /// Stacked labelled values; never the columns.
        case stackedValues
    }

    static var unavailableText: String { "Unavailable" }
    static var noRecentText: String { "No recent probability" }
    static var chanceLabel: String { "Win chance" }

    /// An upcoming NFL or NBA row the host has not seen start; anything else
    /// keeps its existing renderer.
    static func applies(sportKey: String?, status: String?,
                        hasStarted: Bool, isOpeningLine: Bool) -> Bool {
        NFLRecognizablePage9483.applies(sportKey: sportKey)
            && (status == nil || status == "scheduled")
            && !hasStarted
            && !isOpeningLine
    }

    /// Accessibility sizes always stack; every other size takes the columns
    /// when the measured figures fit.
    static func arrangement(typeSize: DynamicTypeSize) -> Arrangement {
        typeSize.isAccessibilitySize ? .stackedValues : .columnsWhenTheyFit
    }

    /// The two cells per team, or nil where this view does not apply. Each
    /// value is decided on its own: one going missing never clears the other.
    static func resolve(
        sportKey: String?, status: String?, hasStarted: Bool, isOpeningLine: Bool,
        paired: NFLPairedHeadline9483?,
        chancePhase: EventHeadlinePhase9483?,
        projectedPair: (away: Int, home: Int)?,
        forecastLabel: String,
        awayName: String, homeName: String, pregameContext: String?,
        canInspect: Bool
    ) -> Resolved? {
        guard applies(sportKey: sportKey, status: status,
                      hasStarted: hasStarted, isOpeningLine: isOpeningLine),
              let paired,
              paired.away.won == nil, paired.home.won == nil,
              paired.center == .versus
        else { return nil }

        // Win chance: the pair's own figure, only while it is current.
        func chance(_ side: NFLPairedHeadline9483.Side) -> Cell {
            switch chancePhase {
            case .current?:
                return Cell(label: chanceLabel, text: side.figure,
                            spoken: "\(chanceLabel): \(side.figure)", isValue: true)
            case .lastRecorded?:
                return Cell(label: chanceLabel, text: noRecentText,
                            spoken: "\(chanceLabel): \(noRecentText)", isValue: false)
            case nil:
                return Cell(label: chanceLabel, text: unavailableText,
                            spoken: "\(chanceLabel): \(unavailableText)", isValue: false)
            }
        }

        // Projected final: the host's printed integer, as given.
        func forecast(_ value: Int?) -> Cell {
            guard let value else {
                return Cell(label: forecastLabel, text: unavailableText,
                            spoken: "\(forecastLabel): \(unavailableText)", isValue: false)
            }
            return Cell(label: forecastLabel, text: "\(value)",
                        spoken: "\(forecastLabel): \(value)", isValue: true)
        }

        func row(isHome: Bool) -> Row {
            Row(isHome: isHome, name: isHome ? homeName : awayName,
                chance: chance(isHome ? paired.home : paired.away),
                forecast: forecast(projectedPair.map { isHome ? $0.home : $0.away }),
                inspects: canInspect && projectedPair != nil)
        }

        let context = pregameContext.flatMap { $0.isEmpty ? nil : $0 }
        return Resolved(context: context, away: row(isHome: false), home: row(isHome: true))
    }

    /// Calls the callback for exactly this side, and only where it inspects.
    static func perform(_ row: Row, inspect: ((Bool) -> Void)?) {
        guard row.inspects else { return }
        inspect?(row.isHome)
    }

    private var resolved: Resolved? {
        Self.resolve(
            sportKey: sportKey, status: status, hasStarted: hasStarted,
            isOpeningLine: isOpeningLine, paired: paired, chancePhase: chancePhase,
            projectedPair: projectedPair, forecastLabel: forecastLabel,
            awayName: awayName, homeName: homeName, pregameContext: pregameContext,
            canInspect: onForecastInspection != nil)
    }

    // MARK: - Body

    var body: some View {
        if let resolved {
            VStack(alignment: .leading, spacing: 10) {
                if let context = resolved.context {
                    Text(context)
                        .font(.subheadline)
                        .foregroundStyle(Color.primary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                // The grid's ideal width is its figures' alone (names and labels
                // take the width the figures give them; absences ask for a
                // column's width and wrap in it), so a header's or a name's
                // unwrapped length never pushes the view into the stacked values.
                switch Self.arrangement(typeSize: typeSize) {
                case .stackedValues:
                    stackedValues(resolved)
                case .columnsWhenTheyFit:
                    ViewThatFits(in: .horizontal) {
                        columns(resolved)
                        stackedValues(resolved)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(Self.accessibilityIdentifier)
        }
    }

    // MARK: - Two columns

    /// Both teams in one grid: the headers once, then each team's full name
    /// across both columns and its two figures on one baseline under it.
    private func columns(_ resolved: Resolved) -> some View {
        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 6) {
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
                    chanceFigure(row, width: chanceColumnWidth)
                    forecastFigure(row, width: forecastColumnWidth)
                }
                if !row.isHome {
                    Divider().gridCellUnsizedAxes(.horizontal)
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
                    labelled(row.chance.label) { chanceFigure(row, width: nil) }
                    labelled(row.forecast.label) { forecastFigure(row, width: nil) }
                }
                if !row.isHome { Divider() }
            }
        }
    }

    // MARK: - Pieces

    private func color(_ row: Row) -> Color { row.isHome ? homeColor : awayColor }

    /// The full name in the team's colour on its own row, carrying the team's
    /// whole spoken summary. The figures under it are not separate stops.
    private func nameRow(_ row: Row) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
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
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityHidden(true)
            value()
        }
    }

    /// A figure, whole and on one line: never wrapped, split or scaled.
    private func number(_ text: String, size: CGFloat, color: Color, weight: Font.Weight) -> some View {
        Text(text)
            .font(.system(size: size, weight: weight, design: .rounded).monospacedDigit())
            .foregroundStyle(color)
            .lineLimit(1)
            .fixedSize()
    }

    /// The chance in the team's colour at the strongest size, or the absence
    /// words at reading size.
    @ViewBuilder
    private func chanceFigure(_ row: Row, width: CGFloat?) -> some View {
        if row.chance.isValue {
            number(row.chance.text, size: chanceSize, color: color(row), weight: .heavy)
                .frame(minWidth: width, maxWidth: .infinity, alignment: .leading)
                .accessibilityHidden(true)
        } else {
            absence(row.chance.text, width: width)
                .accessibilityHidden(true)
        }
    }

    /// The projected final: a 44-point control with an arrow only where
    /// `row.inspects`, otherwise the plain figure or its absence words.
    @ViewBuilder
    private func forecastFigure(_ row: Row, width: CGFloat?) -> some View {
        if row.forecast.isValue && row.inspects {
            Button {
                Self.perform(row, inspect: onForecastInspection)
            } label: {
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    number(row.forecast.text, size: forecastSize, color: .primary, weight: .bold)
                    Image(systemName: "arrow.up.right")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
                .frame(minWidth: 44, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .frame(minWidth: width, maxWidth: .infinity, alignment: .leading)
            .accessibilityLabel(row.actionLabel ?? "")
            .accessibilityValue(row.forecast.text)
        } else if row.forecast.isValue {
            number(row.forecast.text, size: forecastSize, color: .primary, weight: .bold)
                .frame(minWidth: width, maxWidth: .infinity, alignment: .leading)
                .accessibilityHidden(true)
        } else {
            absence(row.forecast.text, width: width)
                .accessibilityHidden(true)
        }
    }

    /// Absence words: readable, wrapping inside whatever the column becomes.
    private func absence(_ text: String, width: CGFloat?) -> some View {
        Text(text)
            .font(.footnote.weight(.semibold))
            .foregroundStyle(Color.primary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(minWidth: 0, idealWidth: width, maxWidth: .infinity, alignment: .leading)
    }
}

extension PregameComparisonHeadline9483 where Identity == EmptyView {
    /// No team marks (tests and previews).
    init(
        sportKey: String?, status: String?, hasStarted: Bool, isOpeningLine: Bool,
        paired: NFLPairedHeadline9483?, chancePhase: EventHeadlinePhase9483?,
        projectedPair: (away: Int, home: Int)?, forecastLabel: String,
        awayName: String, homeName: String, awayColor: Color, homeColor: Color,
        pregameContext: String?,
        onForecastInspection: ((Bool) -> Void)? = nil
    ) {
        self.init(
            sportKey: sportKey, status: status, hasStarted: hasStarted,
            isOpeningLine: isOpeningLine, paired: paired, chancePhase: chancePhase,
            projectedPair: projectedPair, forecastLabel: forecastLabel,
            awayName: awayName, homeName: homeName, awayColor: awayColor, homeColor: homeColor,
            pregameContext: pregameContext, identity: { _ in EmptyView() },
            onForecastInspection: onForecastInspection)
    }
}
