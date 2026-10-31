import SwiftUI

// #10868 — the final period-winner card of a football game: for every
// regulation period, each outcome's own pregame chance as a hollow dot on its
// own 0–100% track, the period's own final points, and a separate check for
// the outcome that won by its own venue contract.
//
// Presentation only, from the approved design (`FinalQuarterOutlooks.tsx` +
// `finalQuarterEvidence.ts`, totals-final-forecast-binding-20261024; the
// earlier native reference and its fidelity contract,
// final-quarter-expectations-v73 `native/FinalQuarterOutlooks.swift` +
// `ADOPTION-BRIEF.md`). None of that reference's fixture keys, selectors or
// market ids is carried here: every period, outcome, original, chance, clock,
// score, result and word arrives resolved by the owner and is shown verbatim.
//
// The shared period primitives carry the data (`PeriodOutcomePeriod10868`,
// `PeriodOutcomeSeries10868`, `PeriodOutcomeCell10868` — the exact original
// identity, its admitted pregame observation or its own missing words, and its
// owner-resolved result — and `PeriodOutcomeActualContext10868` for a period's
// reported points), and their geometry places each dot
// (`PeriodOutcomeGeometry10868.fraction`, `PeriodOutcomeSymbolShape10868`).
//
// This layer never formats, rounds, normalizes, ranks or completes a chance:
// three independently timed chances in one period are drawn as they are, even
// when they add to more than 100%. A won dot stays at its pregame height; the
// result is its own mark. A missing result is never a loss, a period never
// lends another its score or chance, and a final quote is never a chance.
//
// Layout (the approved density): two panels across on a phone, four on a wide
// screen; at accessibility text sizes one across on a phone and two on a wide
// screen. Each panel is one large selection target; a separate row of 44-point
// outcome controls reaches every original without tapping a small dot. The
// selected outcome's side is held when the period changes. Selection, Details
// and the full card stay with the host; with no callback nothing is tappable.
// A held original the card no longer carries is not replaced by another: the
// readout says so (`selectionMissing`) until that exact original returns. The
// readout's Details appear only for an original the owner can route
// (`detailsOriginalIDs`); every other original keeps its dot and its control.

/// A panel: one period in the owner's order.
nonisolated struct FootballPeriodWinnersPanel10868: Equatable {
    let period: PeriodOutcomePeriod10868
    /// The period as VoiceOver says it.
    let spokenLabel: String
    /// The period's own rule words from its bound contracts, or none.
    let note: String?
}

/// One original with the outcome it belongs to.
nonisolated struct FootballPeriodWinnersOption10868: Equatable, Identifiable {
    let series: PeriodOutcomeSeries10868
    let cell: PeriodOutcomeCell10868
    var id: String { cell.id }
}

/// One original's reader caption, by exact original identity.
nonisolated struct FootballPeriodWinnersCaption10868: Equatable {
    let cellID: String
    let caption: String
}

/// The owner's words, chosen explicitly — never parsed from a label.
nonisolated struct FootballPeriodWinnersWords10868: Equatable {
    let eyebrow: String
    let title: String
    let summary: String?
    /// "Hollow dots · pregame chance"
    let legendPregame: String
    /// "Won the period"
    let legendWon: String
    /// Between the two scores in a panel.
    let scoreCaption: String
    let scaleTop: String
    let scaleBottom: String
    /// Beside a won outcome's check.
    let won: String
    let pregameTitle: String
    let resultTitle: String
    /// The readout's figure when the selected original has no pregame chance.
    let unavailable: String
    /// The outcome controls' group name.
    let sidesLabel: String
    let details: String
    let expand: String
    /// Shown when no single original is selected.
    let selectionMissing: String
    let notes: [String]
    /// Spoken name of a panel's selection button, from its spoken period.
    let selectPanel: String
}

nonisolated struct FootballPeriodWinnersInput10868: Equatable {
    let panels: [FootballPeriodWinnersPanel10868]
    /// Every outcome, in the owner's order, each with its own originals.
    let series: [PeriodOutcomeSeries10868]
    /// The two outcomes whose points a panel prints, home first.
    let homeSeriesID: String
    let awaySeriesID: String
    /// Short side names printed beside the points ("JAX", "PHI").
    let homeScoreLabel: String
    let awayScoreLabel: String
    /// One actual context per period, naming its period exactly.
    let actuals: [PeriodOutcomeActualContext10868]
    let captions: [FootballPeriodWinnersCaption10868]
    /// The host's held original, exactly as held — never replaced by another
    /// when it is not on the card (the readout then says `selectionMissing`).
    let selectedID: String?
    let words: FootballPeriodWinnersWords10868
    /// Nil by default: the held exact original offers its Details. When
    /// supplied, only an original the owner names here offers Details; every
    /// other original still shows and stays selectable, with no Details
    /// control. An availability permission only (the shared period leaves'
    /// `detailsOriginalIDs`): it never adds an original, and an id the card
    /// does not show, or shows twice, still offers nothing.
    var detailsOriginalIDs: Set<String>? = nil

    // MARK: Pure reading

    static let axis = PeriodOutcomeAxis10868(lower: 0, upper: 1, ticks: [])

    var cells: [PeriodOutcomeCell10868] { series.flatMap(\.cells) }

    var hasOriginals: Bool { !cells.isEmpty }

    /// The series' original for the period, by exact period identity.
    func cell(_ one: PeriodOutcomeSeries10868, periodID: String) -> PeriodOutcomeCellLookup10868 {
        let matches = one.cells.filter { $0.periodID == periodID }
        switch matches.count {
        case 0: return .absent
        case 1: return Self.isExact(matches[0].id) && isUnique(matches[0].id) ? .cell(matches[0]) : .ambiguous
        default: return .ambiguous
        }
    }

    static func isExact(_ id: String) -> Bool {
        !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    func isUnique(_ id: String) -> Bool {
        cells.filter { $0.id == id }.count == 1
    }

    /// The held original and its outcome, when exactly one original carries the id.
    var selected: FootballPeriodWinnersOption10868? {
        guard let id = selectedID, Self.isExact(id), isUnique(id) else { return nil }
        for one in series {
            if let cell = one.cells.first(where: { $0.id == id }) {
                return FootballPeriodWinnersOption10868(series: one, cell: cell)
            }
        }
        return nil
    }

    /// The original a panel tap selects: the held outcome's in that period, so
    /// the side is kept; with nothing held, the first outcome offered there.
    func idForPanel(_ periodID: String) -> String? {
        if let held = selected {
            return cell(held.series, periodID: periodID).cell?.id
        }
        for one in series {
            if let found = cell(one, periodID: periodID).cell { return found.id }
        }
        return nil
    }

    /// The original whose Details the readout offers: the held original,
    /// exactly once on the card, and one the owner's availability names (nil
    /// availability: every exact original). No callback, nothing selected or
    /// an original the owner cannot route: nil, so no control is drawn that
    /// would open nothing.
    func detailsTarget(canOpenDetails: Bool) -> String? {
        guard canOpenDetails, let held = selected else { return nil }
        if let detailsOriginalIDs, !detailsOriginalIDs.contains(held.cell.id) { return nil }
        return held.cell.id
    }

    /// The selected period's originals, one per outcome offered there.
    var selectedPeriodCells: [FootballPeriodWinnersOption10868] {
        guard let held = selected else { return [] }
        return series.compactMap { one in
            cell(one, periodID: held.cell.periodID).cell.map { FootballPeriodWinnersOption10868(series: one, cell: $0) }
        }
    }

    /// A dot's height on the 0–100% track, from the pregame chance only. Nil
    /// draws no dot — never clamped, never a result's 0 or 1.
    func fraction(_ cell: PeriodOutcomeCell10868) -> Double? {
        cell.pregame.flatMap { PeriodOutcomeGeometry10868.fraction($0.probability, axis: Self.axis) }
    }

    func caption(_ cellID: String) -> String? {
        let matches = captions.filter { $0.cellID == cellID }
        return matches.count == 1 ? matches[0].caption : nil
    }

    /// A period's own reported points, home then away, with their provenance;
    /// or the owner's missing words. One missing side shows no half score.
    enum Score: Equatable {
        case reported(home: String, away: String, provenance: String)
        case missing(String)
    }

    func score(_ periodID: String, missing: String) -> Score {
        let contexts = actuals.filter { $0.periodID == periodID }
        guard contexts.count == 1, Self.isExact(contexts[0].id),
              actuals.filter({ $0.id == contexts[0].id }).count == 1 else { return .missing(missing) }
        switch contexts[0].state {
        case .unavailable(let text):
            return .missing(text)
        case .reported(let report):
            let home = report.scores.filter { $0.seriesID == homeSeriesID }
            let away = report.scores.filter { $0.seriesID == awaySeriesID }
            guard home.count == 1, away.count == 1 else { return .missing(missing) }
            return .reported(home: home[0].text, away: away[0].text, provenance: contexts[0].provenance)
        }
    }

    /// Panels across: two on a phone, four wide; at accessibility sizes one
    /// on a phone, two wide.
    static func columns(wide: Bool, accessibility: Bool) -> Int {
        wide ? (accessibility ? 2 : 4) : (accessibility ? 1 : 2)
    }

    /// The pregame chance with its own clock, then the result.
    func accessibilityValue(_ cell: PeriodOutcomeCell10868) -> String {
        let pregame = cell.pregame.map { "\(words.pregameTitle) \($0.text), \($0.accessibilityDetail)" }
            ?? "\(words.pregameTitle): \(cell.pregameMissing)"
        return "\(pregame). \(words.resultTitle): \(cell.result.text)"
    }
}

nonisolated enum FootballPeriodWinnersAccessibilityID10868 {
    static let card = "footballPeriodWinners10868.card"
    static func panel(_ periodID: String) -> String { "footballPeriodWinners10868.panel.\(periodID)" }
    static func side(_ cellID: String) -> String { "footballPeriodWinners10868.side.\(cellID)" }
    static let readout = "footballPeriodWinners10868.readout"
    static let details = "footballPeriodWinners10868.details"
}

struct FootballPeriodWinnersPresentation10868: View {
    let input: FootballPeriodWinnersInput10868
    /// The exact original id to hold. Nil: nothing is selectable.
    var onSelect: ((String) -> Void)? = nil
    /// The exact original's Details. Nil: no Details control. Offered for the
    /// held original only where `input.detailsTarget` names it.
    var onDetails: ((String) -> Void)? = nil
    /// The full card. Nil: no open control (the full card itself passes none).
    var onExpand: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 84

    private var accessibilitySize: Bool { typeSize.isAccessibilitySize }
    private var columnCount: Int {
        FootballPeriodWinnersInput10868.columns(wide: sizeClass == .regular, accessibility: accessibilitySize)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            heading
            legend
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10, alignment: .top),
                                     count: columnCount),
                      alignment: .leading, spacing: 10) {
                ForEach(input.panels, id: \.period.id) { panel in
                    panelButton(panel)
                }
            }
            sides
            Divider()
            readout
            ForEach(input.words.notes, id: \.self) { note in
                Text(note)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let onExpand {
                Button(action: onExpand) {
                    HStack {
                        Text(input.words.expand).font(.subheadline.weight(.semibold))
                        Spacer(minLength: 0)
                        Image(systemName: "chevron.right").accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                    .frame(minHeight: controlSize)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(FootballPeriodWinnersAccessibilityID10868.card)
    }

    private var heading: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.words.eyebrow)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
            Text(input.words.title)
                .font(.title3.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if let summary = input.words.summary {
                Text(summary)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
    }

    private var legend: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) {
                legendPregame
                Spacer(minLength: 0)
                legendWon
            }
            VStack(alignment: .leading, spacing: 4) {
                legendPregame
                legendWon
            }
        }
        .font(.caption)
        .foregroundStyle(DS.textSecondary)
    }

    private var legendPregame: some View {
        HStack(spacing: 6) {
            Circle().stroke(DS.textSecondary, lineWidth: 1.5).frame(width: 9, height: 9).accessibilityHidden(true)
            Text(input.words.legendPregame).fixedSize(horizontal: false, vertical: true)
        }
    }

    private var legendWon: some View {
        Label(input.words.legendWon, systemImage: "checkmark")
    }

    // MARK: Panels

    @ViewBuilder private func panelButton(_ panel: FootballPeriodWinnersPanel10868) -> some View {
        let target = input.idForPanel(panel.period.id)
        let isSelected = input.selected?.cell.periodID == panel.period.id
        if let onSelect, let target {
            Button { onSelect(target) } label: { panelBody(panel, isSelected: isSelected) }
                .buttonStyle(.plain)
                .accessibilityLabel("\(input.words.selectPanel) \(panel.spokenLabel)")
                .accessibilityAddTraits(isSelected ? .isSelected : [])
                .accessibilityIdentifier(FootballPeriodWinnersAccessibilityID10868.panel(panel.period.id))
        } else {
            panelBody(panel, isSelected: isSelected)
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(FootballPeriodWinnersAccessibilityID10868.panel(panel.period.id))
        }
    }

    private func panelBody(_ panel: FootballPeriodWinnersPanel10868, isSelected: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(panel.period.label).font(.headline).foregroundStyle(DS.textPrimary)
                Spacer(minLength: 4)
                if let note = panel.note {
                    Text(note)
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondary)
                        .multilineTextAlignment(.trailing)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            scoreRow(panel)
            Divider()
            HStack(alignment: .top, spacing: 2) {
                scale
                ForEach(input.series, id: \.id) { one in
                    column(one, periodID: panel.period.id)
                }
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
            .stroke(isSelected ? DS.blue : DS.border, lineWidth: isSelected ? 2 : 1))
        .contentShape(Rectangle())
    }

    @ViewBuilder private func scoreRow(_ panel: FootballPeriodWinnersPanel10868) -> some View {
        switch input.score(panel.period.id, missing: input.words.unavailable) {
        case .reported(let home, let away, let provenance):
            HStack(spacing: 4) {
                Text(input.homeScoreLabel).font(.caption2).foregroundStyle(DS.textSecondary)
                Text(home).font(.title3.weight(.bold)).foregroundStyle(DS.textPrimary)
                Spacer(minLength: 0)
                Text(input.words.scoreCaption)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                Text(away).font(.title3.weight(.bold)).foregroundStyle(DS.textPrimary)
                Text(input.awayScoreLabel).font(.caption2).foregroundStyle(DS.textSecondary)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(input.words.scoreCaption): \(input.homeScoreLabel) \(home), \(input.awayScoreLabel) \(away). \(provenance)")
        case .missing(let text):
            Text(text)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var scale: some View {
        VStack(alignment: .trailing) {
            Text(input.words.scaleTop)
            Spacer(minLength: 0)
            Text(input.words.scaleBottom)
        }
        .font(.caption2)
        .foregroundStyle(DS.textSecondary)
        .frame(height: trackHeight)
        .padding(.vertical, 6)
        .accessibilityHidden(true)
    }

    @ViewBuilder private func column(_ one: PeriodOutcomeSeries10868, periodID: String) -> some View {
        let lookup = input.cell(one, periodID: periodID)
        VStack(spacing: 4) {
            track(one, cell: lookup.cell)
                .frame(height: trackHeight)
                .padding(.vertical, 6)
            Text(one.label)
                .font(accessibilitySize ? .subheadline.weight(.semibold) : .caption2.weight(.semibold))
                .foregroundStyle(one.tint)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            if case .won? = lookup.cell?.result {
                HStack(spacing: 2) {
                    Image(systemName: "checkmark").accessibilityHidden(true)
                    Text(input.words.won)
                }
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize()
            } else {
                // An unconfirmed or lost result draws no check; unknown is never a loss.
                Text(" ").font(.caption2).accessibilityHidden(true)
            }
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(lookup.cell.flatMap { input.caption($0.id) } ?? one.label)
        .accessibilityValue(lookup.cell.map(input.accessibilityValue) ?? input.words.unavailable)
    }

    @ViewBuilder private func track(_ one: PeriodOutcomeSeries10868, cell: PeriodOutcomeCell10868?) -> some View {
        GeometryReader { geometry in
            let height = geometry.size.height
            ZStack(alignment: .bottom) {
                Rectangle().fill(DS.border).frame(height: 1)
                if let cell, let fraction = input.fraction(cell), let pregame = cell.pregame {
                    Rectangle()
                        .fill(one.tint.opacity(0.3))
                        .frame(width: 1, height: height * fraction)
                    VStack(spacing: 4) {
                        Text(pregame.text)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(one.tint)
                            .fixedSize()
                        PeriodOutcomeSymbolShape10868(symbol: one.symbol)
                            .fill(DS.cardBg)
                            .overlay(PeriodOutcomeSymbolShape10868(symbol: one.symbol).stroke(one.tint, lineWidth: 2))
                            .frame(width: PeriodOutcomeGeometry10868.markDiameter,
                                   height: PeriodOutcomeGeometry10868.markDiameter)
                    }
                    .offset(y: PeriodOutcomeGeometry10868.markDiameter / 2 - height * fraction)
                } else {
                    Text("–")
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .frame(maxHeight: .infinity)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
        }
    }

    // MARK: Outcome controls and the readout

    @ViewBuilder private var sides: some View {
        let options = input.selectedPeriodCells
        if !options.isEmpty {
            HStack(spacing: 8) {
                ForEach(options) { option in
                    sideButton(option.series, cell: option.cell)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(input.words.sidesLabel)
        }
    }

    @ViewBuilder private func sideButton(_ one: PeriodOutcomeSeries10868, cell: PeriodOutcomeCell10868) -> some View {
        let isSelected = cell.id == input.selectedID
        let label = Text(one.label)
            .font(.subheadline.weight(isSelected ? .semibold : .regular))
            .foregroundStyle(DS.textPrimary)
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            .frame(maxWidth: .infinity, minHeight: controlSize)
            .background(isSelected ? DS.border : Color.clear, in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous)
                .stroke(isSelected ? one.tint : DS.border, lineWidth: isSelected ? 2 : 1))
        if let onSelect {
            Button { onSelect(cell.id) } label: { label }
                .buttonStyle(.plain)
                .accessibilityAddTraits(isSelected ? .isSelected : [])
                .accessibilityIdentifier(FootballPeriodWinnersAccessibilityID10868.side(cell.id))
        } else {
            label
        }
    }

    @ViewBuilder private var readout: some View {
        if let held = input.selected {
            VStack(alignment: .leading, spacing: 8) {
                if let caption = input.caption(held.cell.id) {
                    Text(caption)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 12) { readoutFigures(held.cell) }
                    VStack(alignment: .leading, spacing: 8) { readoutFigures(held.cell) }
                }
                Text(held.cell.pregame?.accessibilityDetail ?? held.cell.pregameMissing)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let onDetails, let target = input.detailsTarget(canOpenDetails: true) {
                    Button { onDetails(target) } label: {
                        HStack {
                            Text(input.words.details).font(.subheadline.weight(.semibold))
                            Spacer(minLength: 0)
                            Image(systemName: "chevron.right").accessibilityHidden(true)
                        }
                        .foregroundStyle(DS.blue)
                        .frame(minHeight: controlSize)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier(FootballPeriodWinnersAccessibilityID10868.details)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(FootballPeriodWinnersAccessibilityID10868.readout)
        } else {
            Text(input.words.selectionMissing)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private func readoutFigures(_ cell: PeriodOutcomeCell10868) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(input.words.pregameTitle).font(.caption).foregroundStyle(DS.textSecondary)
            Text(cell.pregame?.text ?? input.words.unavailable)
                .font(.title2.weight(.bold))
                .foregroundStyle(DS.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        VStack(alignment: .leading, spacing: 3) {
            Text(input.words.resultTitle).font(.caption).foregroundStyle(DS.textSecondary)
            HStack(spacing: 4) {
                switch cell.result.mark {
                case .positive?: Image(systemName: "checkmark").accessibilityHidden(true)
                case .negative?: Image(systemName: "xmark").accessibilityHidden(true)
                case nil: EmptyView()
                }
                Text(cell.result.text)
            }
            .font(.title2.weight(.bold))
            .foregroundStyle(DS.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}
