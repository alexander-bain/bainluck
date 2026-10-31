import SwiftUI

// #10868 — the lacrosse match screen (`lacrosse-match`): one native
// presentation composed from the accepted shared leaves, plus one small
// selectable actual-quarter leaf defined here. The two teams' independently
// traded chances lead at equal prominence, each with its own label and dated
// meaning. A fan sees, in this order: the match headline (the owner's eyebrow,
// title and About entry; each named team's readings for the phase — before
// play its pre-match chance, during play that chance beside a recorded chance,
// after the match that pre-match chance kept as a reminder beside the
// separately reported actual goals — and the owner's match state), the owner's
// status words, and the tall shared probability history with its source entry;
// then, during and after play, the actual quarters — paired goal bars for every
// admitted period on one owner goal scale, selectable, with the owner's
// cumulative actual score after the chosen period — labelled as actual facts
// and never as chances; then the original markets with the held original's
// Details and the "All props" entry. The history and the quarters open as
// full-size content made of the same Views; "All props", the held original's
// Details, the match About, the source details and the match report are
// further content modes.
//
// Presentation only, composed from the approved `LacrosseMatch.tsx`,
// `LacrosseQuarterCard.tsx`, `LacrosseHistoryPlot.tsx`,
// `LacrosseChanceComparison.tsx`, `MatchReadingContext.tsx`,
// `retainedMatchHeadlines.ts` and `lacrosseMatch.css`, with the native
// lacrosse adoption records as visual and semantic references only. The
// reference's fixture loader and evidence helper (`lacrosseMatchEvidence.ts`)
// — ticker and event allowlists, directional predicate checks, admission,
// scalar parsing, baseline election, score, header and scoreboard agreement,
// period election, cumulative sums, the finish title and caption, exact-minute
// lookup and segmentation — and `lacrosseHistoryIdentity.ts`,
// `matchHistoryInspection.ts`, the probability label, the archive clock, its
// phase picker, "Aa Larger", the card-focus reader, sheets, dialogs and focus
// restoration are NOT ported. The leaves are the actual accepted Views:
//
//   • `FieldPhaseHeadlinePresentation10868` — the two named teams;
//   • `RugbyMatchEventPageComparisonPresentation10868` (the accepted rugby
//     page's standalone comparison, read only) — every team's dated readouts
//     exactly as the history resolves them, at one equal scaled figure size,
//     each with its own label and date, above the history inline and full
//     size, from the same history copy the history leaf receives;
//   • `FieldProbabilityHistoryPresentation10868` — the anchor: the owner's
//     runs with their real gaps, readouts bound to their exact observations,
//     windows, inspection and previous/next;
//   • `LacrosseEventPagePeriodGoalsPresentation10868` (below) — the actual quarters,
//     on the accepted squash tile grid and bar geometry
//     (`SquashGameTileGrid10868`, `SquashGameScoresGeometry10868`), read only.
//     The complete squash games View has no period selection, so it is not
//     mounted, and no probability or threshold card is bent into goals;
//   • `OriginalMarketChooserView9483` — the original markets and the held
//     original's Details, on the page;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     "All props" and the held original's Details as content modes.
//
// The reference ranks no story stream (its full-size reader holds only the
// history and the quarter story), so no stream is mounted. Nothing else is
// drawn here beyond arrangement, card surfaces, the owner's notice, entry and
// text words and the compact reader heading.
//
// The page's phase is the owner's explicit `LacrosseEventPagePhase10868`,
// never read from a listed start, a market close, a settlement, a quote, a
// period count or a result. A leaf is mounted only when its own phase is the
// page's: a headline from another phase shows the owner's unavailable words,
// and the quarters are mounted during and after play only — never before, so
// no later period, cumulative score, caption or result reaches the page or its
// speech, whatever the owner supplies. The two teams' chances are independent
// markets: this layer never complements, normalizes or sums them, merges two
// originals that traded in the same minute, treats a missing value as zero,
// elects a baseline, forward-fills a gap, turns the result or a settlement
// into a closing point, reads a contract's grade from the match, or guesses a
// faceoff, a period end, a goal time or a link between a period and a
// probability. No projected final, live replay or scoring clock is drawn: no
// such channel exists here.
//
// The probability inspection and the actual quarters are separate inputs.
// Choosing a period hands back that period's exact id and nothing else — the
// history cursor, the held original and the headline are untouched — and
// inspecting a probability never chooses a period. Actual quarters stay
// mounted when the history is missing or explicitly absent.
//
// The host supplies each leaf's own immutable input, already admitted for the
// same snapshot; this layer groups them and never re-elects, copies, filters
// or formats an observation, a result, a window, a period or a word.
//
// The owner may pass an interaction hook, so it can hold its received frame
// before an action lands. On the page — the headline's open and About, the
// anchor history's actions, inspection choices and plot taps, the source
// entry, the quarters' expand, choice and report, an original choice and the
// All props entry — and in the catalogue and Details content — an original's
// selection and a Details history intent — the action calls that hook once and
// then the owner's exact callback with its exact value. Without a callback
// there is no control and no hook call; without a hook every callback is the
// owner's own. Building or reading the view calls nothing. Full-size history
// and quarters (with the headline above the quarters), and the About, source
// and report content, keep the exact callbacks: their host already holds the
// frame while they are open.
//
// The history leaf and the comparison read one presentation copy of the
// owner's history: every series, run, readout, inspection, mark, word and
// action exactly as supplied, with only the plot height, the expand control
// and the shared key's visibility set here. The comparison stands in for the
// shared key — the copy hides the key — only while no series carries a choose
// action or a visible key context; otherwise the owner's key stays. The
// owner's input is never changed, and the shared resolver stays the sole
// authority for every readout.
//
// The full-size history is that copy in its expanded layout, without its
// expand control, under the same comparison. Plot heights are geometry only:
// the owner's standard height while usable (finite and positive), else the
// history input's own usable height; at accessibility text sizes the owner's
// usable enlarged height, never shorter than that standard. With no usable
// height the history input's own value passes to the shared leaf unchanged.
// The full-size quarters are the same quarter input without the expand
// control, under the same headline input, so the pre-match chances stay
// clearly labelled beside the actual units.
//
// Phone stacks the headline above the history, then the quarters and the
// originals. A regular or unspecified size class (a Mac window) places the
// headline beside the history while both keep their minimum widths, otherwise
// it stacks too; accessibility sizes always stack.
//
// The host owns the scroll, pinning, reader paging, navigation, sheets,
// Back/Done, focus, routing to and from every content mode, the held original,
// the held inspection and window, the held period, the held/received frame,
// live subscriptions and every genuine update. This view keeps no state, runs
// no timer or animation, holds no subscription and presents no sheet or
// navigation of its own.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one match snapshot, the phase; the two teams' canonical original
// membership and their dated readings (a qualified pre-match chance only when
// one exists); the history's runs with their real gaps, the coordinate and
// axis words; the actual periods with each team's goals, the cumulative score
// words and the shared goal scale from an independent score record whose
// competition and team identities are bound exactly; the original catalogue
// with each original's own result and verbatim rules; the About, source and
// report words with any link; and maps every callback to its existing
// controls. No production lacrosse score channel exists in the app's models at
// this base.

/// The owner's explicit phase for the whole screen.
nonisolated enum LacrosseEventPagePhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final
}

/// What the host's container is showing, chosen by the host.
nonisolated enum LacrosseEventPageMode10868: Equatable {
    /// The match screen body.
    case page
    /// The history's full-size content.
    case fullHistory
    /// The actual quarters' full-size content.
    case fullPeriods
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's match About.
    case about
    /// The owner's history and source details.
    case source
    /// The owner's match report.
    case report
}

nonisolated enum LacrosseEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Actual quarters

/// One team of the actual quarters, with a stable tint and a non-colour key.
nonisolated struct LacrosseEventPagePeriodTeam10868: Equatable {
    /// The owner's opaque, stable identity.
    let id: String
    /// The owner's name, shown whole and spoken.
    let name: String
    /// The same shape the history draws for this team.
    let shape: FieldHistoryShape10868
    let tint: Color
}

/// One team's actual goals in one period.
nonisolated enum LacrosseEventPagePeriodGoals10868: Equatable {
    /// The owner's figure, its spoken words with their unit, and the number
    /// that places the bar. A true zero is a reported figure.
    case reported(text: String, spoken: String, value: Double)
    /// Not reported — the owner's words, never zero and never a bar.
    case unknown(String)

    var figure: String? {
        if case .reported(let text, _, _) = self { return text }
        return nil
    }

    var value: Double? {
        if case .reported(_, _, let value) = self { return value }
        return nil
    }

    var unknownWords: String? {
        if case .unknown(let words) = self { return words }
        return nil
    }
}

/// The owner's cumulative actual score after one period: each team's own
/// figure and the whole readout in words. Never summed here.
nonisolated struct LacrosseEventPagePeriodReadout10868: Equatable {
    let first: String
    let second: String
    let spoken: String
}

/// One admitted period, in the owner's order.
nonisolated struct LacrosseEventPagePeriod10868: Equatable {
    /// The owner's opaque, stable identity; choosing hands it back. Empty is no
    /// identity.
    let id: String
    /// The owner's short label under the bars.
    let label: String
    /// The fuller spoken name; nil speaks `label`.
    let spokenLabel: String?
    /// The first team's goals in this period.
    let first: LacrosseEventPagePeriodGoals10868
    /// The second team's goals in this period.
    let second: LacrosseEventPagePeriodGoals10868
    /// The readout heading when this period is chosen.
    let readoutLabel: String
    /// The owner's cumulative score after this period; nil shows the input's
    /// unavailable words.
    let readout: LacrosseEventPagePeriodReadout10868?
}

/// The owner's one zero-based goal scale every period's bars share.
nonisolated struct LacrosseEventPagePeriodScale10868: Equatable {
    /// The top of every bar, in goals. Never a universal constant.
    let ceiling: Double
    /// The scale in words; nil draws none.
    let words: String?

    var isValid: Bool { ceiling.isFinite && ceiling > 0 }
}

/// The owner's held period.
nonisolated enum LacrosseEventPagePeriodSelection10868: Equatable {
    case none
    /// By exact id; its own words when that id names no single admitted
    /// period. Never a neighbour.
    case period(id: String, missingWords: String)
}

nonisolated struct LacrosseEventPagePeriodInput10868: Equatable {
    /// The owner's explicit phase. Before play nothing is drawn or spoken.
    let phase: LacrosseEventPagePhase10868
    /// The owner's eyebrow; nil draws none.
    let eyebrow: String?
    /// The owner's heading, never computed here.
    let title: String
    /// The owner's unit words for the bars.
    let keyLabel: String
    let first: LacrosseEventPagePeriodTeam10868
    let second: LacrosseEventPagePeriodTeam10868
    /// Every period the owner admitted for the phase, in its order — never
    /// sorted, filtered, capped or completed here.
    let periods: [LacrosseEventPagePeriod10868]
    let scale: LacrosseEventPagePeriodScale10868
    let selection: LacrosseEventPagePeriodSelection10868
    /// The owner's words when a reported figure cannot be placed on the scale.
    let notDrawn: String
    /// Shown when no period is admitted.
    let empty: String
    /// Shown in the readout when no period is held.
    let readoutPrompt: String
    /// Shown in the readout when the held period carries no cumulative score.
    let readoutUnavailable: String
    /// The owner's hint on a choosable period; nil adds none.
    let chooseHint: String?
    /// The owner's story caption; nil draws none.
    let caption: String?
    /// Verbatim lines.
    let notes: [String]
    /// The owner's report words; drawn only with the host's callback.
    let reportLabel: String?
    /// The expand control's spoken name; drawn only with the host's callback.
    let expandLabel: String

    // MARK: Phase gating

    var isShown: Bool { phase != .before }

    var visiblePeriods: [LacrosseEventPagePeriod10868] { isShown ? periods : [] }

    var visibleCaption: String? { isShown ? LacrosseEventPageModel10868.readable(caption) : nil }

    var visibleNotes: [String] { isShown ? notes.filter { LacrosseEventPageModel10868.readable($0) != nil } : [] }

    var visibleScaleWords: String? { isShown ? LacrosseEventPageModel10868.readable(scale.words) : nil }

    // MARK: Identity and choice

    /// A nonempty id naming exactly one admitted period.
    func isUnique(_ id: String) -> Bool {
        LacrosseEventPageModel10868.readable(id) != nil && visiblePeriods.filter { $0.id == id }.count == 1
    }

    /// The exact id a period hands back: nonempty, unique and with a callback.
    func chooseID(at index: Int, canChoose: Bool) -> String? {
        guard canChoose, visiblePeriods.indices.contains(index) else { return nil }
        let id = visiblePeriods[index].id
        return isUnique(id) ? id : nil
    }

    /// The held period's position: the one admitted period its id names.
    var selectedIndex: Int? {
        guard case .period(let id, _) = selection, isUnique(id) else { return nil }
        return visiblePeriods.firstIndex { $0.id == id }
    }

    var selectedPeriod: LacrosseEventPagePeriod10868? { selectedIndex.map { visiblePeriods[$0] } }

    func isSelected(at index: Int) -> Bool { selectedIndex == index }

    /// The owner's words for a held period that names no single admitted
    /// period — omitted, withdrawn, repeated or empty. Never a neighbour.
    var selectionWords: String? {
        guard isShown, case .period(_, let words) = selection, selectedIndex == nil else { return nil }
        return LacrosseEventPageModel10868.readable(words) ?? readoutUnavailable
    }

    /// The readout's heading, or the owner's words when nothing is held.
    var readoutHeading: String? {
        guard isShown else { return nil }
        if let period = selectedPeriod { return period.readoutLabel }
        return selectionWords ?? readoutPrompt
    }

    /// The held period's cumulative score, exactly as the owner wrote it.
    var shownReadout: LacrosseEventPagePeriodReadout10868? { selectedPeriod?.readout }

    /// A held period without a cumulative score keeps the owner's words.
    var readoutWords: String? {
        guard selectedPeriod != nil, shownReadout == nil else { return nil }
        return readoutUnavailable
    }

    // MARK: Geometry

    /// A reported figure's bar height as a fraction of the shared scale. Nil
    /// for unknown goals, an invalid scale, or a value that is negative,
    /// non-finite or beyond the ceiling — never clamped.
    func barFraction(_ goals: LacrosseEventPagePeriodGoals10868) -> Double? {
        guard isShown, scale.isValid, let value = goals.value, value.isFinite, value >= 0, value <= scale.ceiling else {
            return nil
        }
        return value / scale.ceiling
    }

    /// A reported figure that cannot be placed keeps its figure and says so.
    func showsNotDrawn(_ goals: LacrosseEventPagePeriodGoals10868) -> Bool {
        guard isShown, goals.value != nil else { return false }
        return barFraction(goals) == nil
    }

    func periodShowsNotDrawn(_ period: LacrosseEventPagePeriod10868) -> Bool {
        showsNotDrawn(period.first) || showsNotDrawn(period.second)
    }

    /// A unique period keeps its id-based identifier; an empty or repeated id
    /// adds its position so two tiles never share one.
    func accessibilityID(at index: Int) -> String? {
        guard visiblePeriods.indices.contains(index) else { return nil }
        let id = visiblePeriods[index].id
        let base = LacrosseEventPagePeriodAccessibilityID10868.period(id)
        return isUnique(id) ? base : "\(base).\(index)"
    }

    // MARK: VoiceOver

    var accessibilityHeader: String? {
        guard isShown else { return nil }
        return Self.joined([eyebrow ?? "", title])
    }

    /// The key: the unit words and both teams' names.
    var accessibilityKey: String? {
        guard isShown else { return nil }
        return Self.joined([keyLabel, first.name, second.name])
    }

    /// One period in reading order: each team's goals or words, then a figure
    /// that could not be placed. Empty before play.
    func accessibilityPeriod(_ period: LacrosseEventPagePeriod10868) -> String {
        guard isShown else { return "" }
        var parts = [Self.spoken(period.first, team: first), Self.spoken(period.second, team: second)]
        if periodShowsNotDrawn(period) { parts.append(notDrawn) }
        return Self.joined(parts)
    }

    /// The readout in words: the held period's own words, or the heading.
    var accessibilityReadout: String? {
        guard isShown else { return nil }
        if let readout = shownReadout {
            return LacrosseEventPageModel10868.readable(readout.spoken)
                ?? Self.joined([readoutHeading ?? "", first.name, readout.first, second.name, readout.second])
        }
        return Self.joined([readoutHeading ?? "", readoutWords ?? ""])
    }

    private static func spoken(_ goals: LacrosseEventPagePeriodGoals10868, team: LacrosseEventPagePeriodTeam10868) -> String {
        switch goals {
        case .reported(let text, let spoken, _):
            "\(team.name) \(LacrosseEventPageModel10868.readable(spoken) ?? text)"
        case .unknown(let words):
            "\(team.name): \(words)"
        }
    }

    /// Owner words joined in order; an empty line adds no pause.
    static func joined(_ parts: [String]) -> String {
        parts.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }.joined(separator: ". ")
    }
}

/// Stable ids for the host's focus return and UI tests.
nonisolated enum LacrosseEventPagePeriodAccessibilityID10868 {
    static let header = "lacrosseEventPagePeriods10868.header"
    static let expand = "lacrosseEventPagePeriods10868.expand"
    static let key = "lacrosseEventPagePeriods10868.key"
    static let empty = "lacrosseEventPagePeriods10868.empty"
    static let readout = "lacrosseEventPagePeriods10868.readout"
    static let caption = "lacrosseEventPagePeriods10868.caption"
    static let notes = "lacrosseEventPagePeriods10868.notes"
    static let report = "lacrosseEventPagePeriods10868.report"
    static func period(_ id: String) -> String { "lacrosseEventPagePeriods10868.period.\(id)" }
}

/// The actual quarters: paired goal bars for every admitted period on the
/// owner's one scale, each period a control that hands back its exact id, and
/// the owner's cumulative score after the held period. Actual facts only —
/// never a chance, a winner or a total computed here. Keeps no state.
struct LacrosseEventPagePeriodGoalsPresentation10868: View {
    let input: LacrosseEventPagePeriodInput10868
    /// A period's exact id, for the host to hold; nil draws every period as
    /// readable but static.
    var onChoose: ((String) -> Void)? = nil
    /// Opens the host's full-size quarters; nil draws no control.
    var onExpand: (() -> Void)? = nil
    /// Opens the host's match report; nil draws no control.
    var onReport: (() -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved reference's bar scale, growing with text size.
    @ScaledMetric(relativeTo: .caption) private var barMaxHeight: CGFloat = 108
    @ScaledMetric(relativeTo: .caption) private var barWidth: CGFloat = 20
    @ScaledMetric(relativeTo: .title) private var readoutSize: CGFloat = 32
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    /// The report control's words, only with readable words and a callback.
    var reportLabel: String? {
        guard onReport != nil else { return nil }
        return LacrosseEventPageModel10868.readable(input.reportLabel)
    }

    /// The period control's action: the exact id when it is choosable.
    func choose(at index: Int) {
        guard let id = input.chooseID(at: index, canChoose: onChoose != nil), let onChoose else { return }
        onChoose(id)
    }

    var body: some View {
        if input.isShown {
            VStack(alignment: .leading, spacing: 16) {
                header
                key
                if input.visiblePeriods.isEmpty {
                    Text(input.empty)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier(LacrosseEventPagePeriodAccessibilityID10868.empty)
                } else {
                    SquashGameTileGrid10868(spacing: 6, accessibilitySize: typeSize.isAccessibilitySize) {
                        ForEach(Array(input.visiblePeriods.enumerated()), id: \.offset) { index, period in
                            tile(period, index: index)
                        }
                    }
                }
                if let words = input.visibleScaleWords {
                    Text(words)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                readout
                if let caption = input.visibleCaption {
                    Text(caption)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier(LacrosseEventPagePeriodAccessibilityID10868.caption)
                }
                notes
                reportButton
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: Header and key

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                if let eyebrow = LacrosseEventPageModel10868.readable(input.eyebrow) {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                }
                Text(input.title)
                    .font(.title2.bold())
                    .foregroundStyle(DS.textPrimary)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityHeader ?? "")
            .accessibilityAddTraits(.isHeader)
            .accessibilityIdentifier(LacrosseEventPagePeriodAccessibilityID10868.header)
            if let onExpand {
                Button(action: onExpand) {
                    Image(systemName: "arrow.up.right")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(input.expandLabel)
                .accessibilityIdentifier(LacrosseEventPagePeriodAccessibilityID10868.expand)
            }
        }
    }

    private var key: some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 6))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 12))
        return layout {
            Text(input.keyLabel)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
            teamKey(input.first)
            teamKey(input.second)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityKey ?? "")
        .accessibilityIdentifier(LacrosseEventPagePeriodAccessibilityID10868.key)
    }

    /// The team's shape in its tint beside the whole name in primary text.
    private func teamKey(_ team: LacrosseEventPagePeriodTeam10868) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: SquashGameScoresGeometry10868.symbol(team.shape))
                .font(.caption2)
                .foregroundStyle(team.tint)
            Text(team.name)
                .font(.subheadline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Periods

    /// One period: a control when its id is choosable, otherwise the same
    /// readable tile without an action. One element, spoken in full.
    @ViewBuilder private func tile(_ period: LacrosseEventPagePeriod10868, index: Int) -> some View {
        let selected = input.isSelected(at: index)
        if input.chooseID(at: index, canChoose: onChoose != nil) != nil {
            Button {
                choose(at: index)
            } label: {
                tileBody(period, selected: selected)
            }
            .buttonStyle(.plain)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(period.spokenLabel ?? period.label)
            .accessibilityValue(input.accessibilityPeriod(period))
            .accessibilityHint(input.chooseHint ?? "")
            .accessibilityAddTraits(selected ? [.isSelected] : [])
            .accessibilityIdentifier(input.accessibilityID(at: index) ?? "")
        } else {
            tileBody(period, selected: selected)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(period.spokenLabel ?? period.label)
                .accessibilityValue(input.accessibilityPeriod(period))
                .accessibilityAddTraits(selected ? [.isSelected] : [])
                .accessibilityIdentifier(input.accessibilityID(at: index) ?? "")
        }
    }

    /// Both teams' figures over their bars, the period label, any absence or
    /// not-drawn words; the held period is outlined.
    private func tileBody(_ period: LacrosseEventPagePeriod10868, selected: Bool) -> some View {
        VStack(spacing: 6) {
            HStack(alignment: .bottom, spacing: 4) {
                bar(period.first, team: input.first)
                bar(period.second, team: input.second)
            }
            .frame(maxWidth: .infinity, minHeight: barMaxHeight, alignment: .bottom)
            Rectangle()
                .fill(DS.border)
                .frame(height: 1)
            Text(period.label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(Array([period.first.unknownWords, period.second.unknownWords].compactMap { $0 }.enumerated()),
                    id: \.offset) { _, words in
                Text(words)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if input.periodShowsNotDrawn(period) {
                Text(input.notDrawn)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 4)
        .padding(.top, 4)
        .padding(.bottom, 8)
        .frame(maxWidth: .infinity, minHeight: controlSize)
        .background(selected ? DS.cardBg : Color.clear, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(selected ? input.first.tint : Color.clear, lineWidth: 1.5)
        )
        .contentShape(Rectangle())
    }

    /// One team's figure over its bar on the shared scale; a figure that
    /// cannot be placed keeps its words and draws no bar; unknown goals draw
    /// neither. Decorative: the tile speaks.
    private func bar(_ goals: LacrosseEventPagePeriodGoals10868, team: LacrosseEventPagePeriodTeam10868) -> some View {
        VStack(spacing: 4) {
            if let figure = goals.figure {
                Text(figure)
                    .font(.caption.bold())
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            }
            if let fraction = input.barFraction(goals),
               let height = SquashGameScoresGeometry10868.barHeight(fraction, maxHeight: barMaxHeight) {
                UnevenRoundedRectangle(topLeadingRadius: 4, bottomLeadingRadius: 0, bottomTrailingRadius: 0,
                                       topTrailingRadius: 4, style: .continuous)
                    .fill(team.tint)
                    .frame(width: barWidth, height: height)
            } else {
                Color.clear.frame(width: barWidth, height: 0)
            }
        }
        .frame(maxWidth: .infinity)
        .accessibilityHidden(true)
    }

    // MARK: Readout, notes and report

    /// The held period's heading and the owner's cumulative score, each team's
    /// figure in its tint above its name; otherwise the owner's words.
    private var readout: some View {
        VStack(spacing: 6) {
            if let heading = input.readoutHeading {
                Text(heading)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let score = input.shownReadout {
                let layout = typeSize.isAccessibilitySize
                    ? AnyLayout(VStackLayout(alignment: .center, spacing: 8))
                    : AnyLayout(HStackLayout(alignment: .top, spacing: 16))
                layout {
                    readoutTeam(score.first, team: input.first)
                    Text("–")
                        .font(.title3)
                        .foregroundStyle(DS.textSecondary)
                        .accessibilityHidden(true)
                    readoutTeam(score.second, team: input.second)
                }
            } else if let words = input.readoutWords {
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textPrimary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityReadout ?? "")
        .accessibilityIdentifier(LacrosseEventPagePeriodAccessibilityID10868.readout)
    }

    private func readoutTeam(_ figure: String, team: LacrosseEventPagePeriodTeam10868) -> some View {
        VStack(spacing: 2) {
            Text(figure)
                .font(.system(size: readoutSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(team.tint)
                .fixedSize(horizontal: false, vertical: true)
            Text(team.name)
                .font(.caption)
                .foregroundStyle(DS.textPrimary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private var notes: some View {
        if !input.visibleNotes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(input.visibleNotes.enumerated()), id: \.offset) { _, note in
                    Text(note)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(LacrosseEventPagePeriodAccessibilityID10868.notes)
        }
    }

    @ViewBuilder private var reportButton: some View {
        if let label = reportLabel, let onReport {
            Button(action: onReport) {
                HStack(spacing: 8) {
                    Text(label)
                        .font(.body.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Image(systemName: "chevron.right")
                        .font(.body.weight(.semibold))
                        .accessibilityHidden(true)
                }
                .foregroundStyle(DS.blue)
                .frame(minHeight: controlSize)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(LacrosseEventPagePeriodAccessibilityID10868.report)
        }
    }
}

// MARK: - Page input

/// The owner's one-line match words above full-size content.
nonisolated struct LacrosseEventPageReaderHeader10868: Equatable {
    /// The owner's teams and phase words.
    let title: String
    /// The owner's event words; nil draws none.
    let state: String?
}

/// One titled section of owner text, verbatim.
nonisolated struct LacrosseEventPageSection10868: Equatable {
    let title: String?
    let paragraphs: [String]
}

/// An owner link inside a text mode: its id is handed back unchanged.
nonisolated struct LacrosseEventPageLink10868: Equatable {
    let id: String
    let label: String
}

/// The owner's About, source details or match report, verbatim.
nonisolated struct LacrosseEventPageText10868: Equatable {
    let title: String
    let sections: [LacrosseEventPageSection10868]
    /// Drawn only with readable words, a nonempty id and the host's callback.
    var link: LacrosseEventPageLink10868? = nil
}

/// The owner's plot heights: standard, and enlarged at accessibility sizes.
/// A nil, non-finite, zero or negative value is unusable and never drawn.
nonisolated struct LacrosseEventPageHistoryHeights10868: Equatable {
    let standard: CGFloat?
    let enlarged: CGFloat?
}

nonisolated struct LacrosseEventPageCopy10868: Equatable {
    /// Shown in place of a headline whose phase is not the page's.
    let headlineUnavailable: String
    /// The comparison's spoken name.
    let comparisonLabel: String
    /// The source entry's words; nil draws no entry.
    var sourceLabel: String? = nil
    /// The All props entry's words; nil draws no entry.
    var allPropsLabel: String? = nil
    /// Shown during and after play when this phase admits no quarters; nil
    /// draws none.
    var periodsUnavailable: String? = nil
}

nonisolated struct LacrosseEventPageInput10868: Equatable {
    let phase: LacrosseEventPagePhase10868
    let reader: LacrosseEventPageReaderHeader10868
    let headline: FieldHeadlineInput10868
    /// The owner's status words under the headline; nil draws none.
    var notice: String? = nil
    /// The probability history with the owner's own inspection — separate
    /// from the actual quarters.
    let history: FieldHistoryInput10868
    /// The owner's plot heights; nil keeps the history input's own height.
    var historyHeights: LacrosseEventPageHistoryHeights10868? = nil
    /// The actual quarters, during and after play only.
    var periods: LacrosseEventPagePeriodInput10868? = nil
    /// Opened by the headline's About control; nil: no control.
    var about: LacrosseEventPageText10868? = nil
    /// Opened by the source entry; nil: no entry.
    var source: LacrosseEventPageText10868? = nil
    /// Opened by the quarters' report control; nil: no control.
    var report: LacrosseEventPageText10868? = nil
    let copy: LacrosseEventPageCopy10868
}

/// The owner's originals behind the chooser, "All props" and the Details
/// mode — an arbitrary catalogue. Every field reaches the existing leaves
/// unchanged.
struct LacrosseEventPageOriginals10868 {
    /// The latest admitted originals for one scope; nil shows `emptyWords`.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The owner's held selection; nil holds none.
    let selection: OriginalMarketDetails9483.Selection?
    /// The held original's admitted recorded history, for the Details mode
    /// only; nil keeps its summary-only Details.
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    /// The owner's choice label for an exact identity; otherwise its title.
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    let heading: String
    /// Nil draws none.
    var context: String? = nil
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum LacrosseEventPageAccessibilityID10868 {
    static let page = "lacrosseEventPage10868.page"
    static let hero = "lacrosseEventPage10868.hero"
    static let headlineUnavailable = "lacrosseEventPage10868.headline.unavailable"
    static let notice = "lacrosseEventPage10868.notice"
    static let anchor = "lacrosseEventPage10868.anchor"
    static let sourceEntry = "lacrosseEventPage10868.sourceEntry"
    static let periods = "lacrosseEventPage10868.periods"
    static let periodsUnavailable = "lacrosseEventPage10868.periods.unavailable"
    static let originals = "lacrosseEventPage10868.originals"
    static let allProps = "lacrosseEventPage10868.allProps"
    static let readerHeader = "lacrosseEventPage10868.readerHeader"
    static let readerAbout = "lacrosseEventPage10868.readerHeader.about"
    static let fullHistory = "lacrosseEventPage10868.fullHistory"
    static let fullPeriods = "lacrosseEventPage10868.fullPeriods"
    static let catalogue = "lacrosseEventPage10868.catalogue"
    static let original = "lacrosseEventPage10868.original"
    static let about = "lacrosseEventPage10868.about"
    static let source = "lacrosseEventPage10868.source"
    static let report = "lacrosseEventPage10868.report"
    static let link = "lacrosseEventPage10868.link"
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
nonisolated struct LacrosseEventPageModel10868: Equatable {
    let input: LacrosseEventPageInput10868

    init(_ input: LacrosseEventPageInput10868) {
        self.input = input
    }

    /// The headline's own name for the page's phase.
    static func headlinePhase(_ phase: LacrosseEventPagePhase10868) -> FieldOutlookPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == Self.headlinePhase(input.phase) ? input.headline : nil
    }

    /// The actual quarters at the page's own phase, during and after play
    /// only. Never read from the history.
    var periods: LacrosseEventPagePeriodInput10868? {
        guard let periods = input.periods, periods.phase == input.phase, periods.isShown else { return nil }
        return periods
    }

    /// The owner's words for a phase that shows quarters but admits none.
    var periodsUnavailable: String? {
        guard input.phase != .before, periods == nil else { return nil }
        return Self.readable(input.copy.periodsUnavailable)
    }

    var notice: String? { Self.readable(input.notice) }

    /// Full-size content exists for the history always, and for the quarters
    /// when this phase shows them.
    func readerShows(_ mode: LacrosseEventPageMode10868) -> Bool {
        switch mode {
        case .fullHistory: true
        case .fullPeriods: periods != nil
        default: false
        }
    }

    /// A height that can be drawn: finite and positive. Otherwise none.
    static func usableHeight(_ height: CGFloat?) -> CGFloat? {
        guard let height, height.isFinite, height > 0 else { return nil }
        return height
    }

    /// The standard plot height: the owner's while usable, else the history
    /// input's own while usable. Nil when neither is.
    var standardPlotHeight: CGFloat? {
        Self.usableHeight(input.historyHeights?.standard) ?? Self.usableHeight(input.history.plotHeight)
    }

    /// The plot height for the text size. Geometry only: the standard height;
    /// at accessibility sizes the owner's usable enlarged height, never shorter
    /// than the standard. With no usable height, the history input's own value
    /// unchanged — the shared leaf keeps its own rule for it.
    func plotHeight(enlarged: Bool) -> CGFloat {
        guard let standard = standardPlotHeight else { return input.history.plotHeight }
        guard enlarged, let larger = Self.usableHeight(input.historyHeights?.enlarged) else { return standard }
        return max(standard, larger)
    }

    /// Whether the comparison stands in for the shared key: only while the key
    /// would show nothing but the readouts the comparison shows — no series
    /// with a choose action and none with a visible key context. Otherwise the
    /// owner's key stays.
    var hidesSharedKey: Bool {
        input.history.series.allSatisfy { $0.choose == nil && FieldHistoryGeometry10868.keyContext($0) == nil }
    }

    /// The key's visibility in both presentation copies.
    var presentedKey: Bool { hidesSharedKey ? false : input.history.showsKey }

    /// The anchor: a presentation copy of the owner's history at the plot
    /// height for the text size, with the duplicate key hidden. Every other
    /// field is the owner's; the owner's input is never changed.
    func history(enlarged: Bool) -> FieldHistoryInput10868 {
        Self.history(input.history, plotHeight: plotHeight(enlarged: enlarged),
                     layout: input.history.layout, expand: input.history.expand, showsKey: presentedKey)
    }

    /// The anchor's full-size content: the same copy in its expanded layout,
    /// without an expand control inside the reader, at the same plot height
    /// and key rules. Every other field is the owner's.
    func readerHistory(enlarged: Bool) -> FieldHistoryInput10868 {
        Self.history(input.history, plotHeight: plotHeight(enlarged: enlarged), layout: .expanded, expand: nil,
                     showsKey: presentedKey)
    }

    /// A presentation copy: every series, run, readout, inspection, mark, word,
    /// window and action exactly as supplied, with only the given height,
    /// layout, expand control and key visibility.
    static func history(_ history: FieldHistoryInput10868, plotHeight: CGFloat, layout: FieldHistoryLayout10868,
                        expand: FieldHistoryAction10868?, showsKey: Bool) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: plotHeight,
            unboundReadingWords: history.unboundReadingWords, plotUnavailableWords: history.plotUnavailableWords,
            windows: history.windows, scale: history.scale, moreOriginals: history.moreOriginals,
            details: history.details, expand: expand, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: history.inspection,
            layout: layout,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: showsKey
        )
    }

    // MARK: Text modes and entries

    static func hasWords(_ section: LacrosseEventPageSection10868) -> Bool {
        readable(section.title) != nil || section.paragraphs.contains { readable($0) != nil }
    }

    /// Owner text, when it carries readable words.
    static func readableText(_ text: LacrosseEventPageText10868?) -> LacrosseEventPageText10868? {
        guard let text, readable(text.title) != nil || text.sections.contains(where: hasWords) else { return nil }
        return text
    }

    var about: LacrosseEventPageText10868? { Self.readableText(input.about) }

    var source: LacrosseEventPageText10868? { Self.readableText(input.source) }

    var report: LacrosseEventPageText10868? { Self.readableText(input.report) }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil
    }

    /// The source entry: readable details, the owner's entry words and a callback.
    func sourceAvailable(canOpen: Bool) -> Bool {
        canOpen && source != nil && Self.readable(input.copy.sourceLabel) != nil
    }

    /// The quarters' report control: a readable report and a callback; the
    /// quarter leaf adds its own label rule.
    func reportAvailable(canOpen: Bool) -> Bool {
        canOpen && report != nil
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && Self.readable(input.copy.allPropsLabel) != nil
    }

    /// Whether `mode`'s compact heading shows the About entry: full-size
    /// history only — the page and the full-size quarters carry the
    /// headline's own control.
    func aboutEntry(mode: LacrosseEventPageMode10868, canOpen: Bool) -> Bool {
        guard mode == .fullHistory, Self.readable(input.headline.copy.aboutLabel) != nil else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    /// A text mode's link: a nonempty id and readable words with a callback.
    static func link(_ text: LacrosseEventPageText10868, canOpen: Bool) -> LacrosseEventPageLink10868? {
        guard canOpen, let link = text.link, readable(link.id) != nil, readable(link.label) != nil else { return nil }
        return link
    }

    static func readable(_ words: String?) -> String? {
        guard let words, !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return words
    }

    /// The arrangements to try, in order. Accessibility sizes and a compact
    /// width stack; a regular or unspecified width (a Mac window has no size
    /// class) tries the headline beside the history, then stacks — their
    /// minimum widths decide which fits.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [LacrosseEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

// MARK: - Text content

/// The owner's About, source details or match report in its own words, with
/// its link only when the host can open it. Acts on nothing else.
struct LacrosseEventPageTextContent10868: View {
    let text: LacrosseEventPageText10868
    /// Hands back the link's exact id.
    var onLink: ((String) -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var link: LacrosseEventPageLink10868? { LacrosseEventPageModel10868.link(text, canOpen: onLink != nil) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let title = LacrosseEventPageModel10868.readable(text.title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(text.sections.enumerated()), id: \.offset) { _, section in
                if LacrosseEventPageModel10868.hasWords(section) {
                    VStack(alignment: .leading, spacing: 6) {
                        if let title = LacrosseEventPageModel10868.readable(section.title) {
                            Text(title)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                        }
                        ForEach(Array(section.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            if let words = LacrosseEventPageModel10868.readable(paragraph) {
                                Text(words)
                                    .font(.body)
                                    .foregroundStyle(DS.textPrimary)
                            }
                        }
                    }
                }
            }
            if let link, let onLink {
                Button {
                    onLink(link.id)
                } label: {
                    HStack(spacing: 8) {
                        Text(link.label)
                            .font(.body.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Image(systemName: "arrow.up.right")
                            .font(.body.weight(.semibold))
                            .accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                    .frame(minHeight: controlSize)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.link)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Page view

struct LacrosseEventPagePresentation10868: View {
    let input: LacrosseEventPageInput10868
    var mode: LacrosseEventPageMode10868 = .page
    /// The page's chooser and the catalogue and Details modes' content; nil:
    /// none of them has any.
    var originals: LacrosseEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's About.
    var onAbout: (() -> Void)? = nil
    /// Opens the host's container on the owner's source details.
    var onSource: (() -> Void)? = nil
    /// Opens the host's container on the owner's match report.
    var onReport: (() -> Void)? = nil
    /// A text mode's link id, for the host to open.
    var onLink: ((String) -> Void)? = nil
    /// Opens the host's existing catalogue.
    var onAllProps: (() -> Void)? = nil
    /// A chooser or catalogue original's exact selection, for the host to hold
    /// and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// A headline team's exact open, for the host's history.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    /// The history's owner action ids (expand, windows, inspect, previous, next).
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Opens the quarters' full-size content.
    var onPeriodsExpand: (() -> Void)? = nil
    /// A period's exact id, for the host to hold. Never touches the history.
    var onPeriodChoose: ((String) -> Void)? = nil
    /// Called once just before a page, catalogue or Details action reaches its
    /// owner callback, so the owner can hold its frame. Never called by
    /// building the view or by full-size or text content.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var headlineMinWidth: CGFloat = 300
    @ScaledMetric(relativeTo: .body) private var headlineMaxWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var model: LacrosseEventPageModel10868 { LacrosseEventPageModel10868(input) }

    // MARK: Holds

    /// A page, catalogue or Details action, after the owner's interaction
    /// hook. No host callback: no action and no hook call. No hook: the exact
    /// callback.
    static func held<Value>(_ action: ((Value) -> Void)?, by interaction: (() -> Void)?) -> ((Value) -> Void)? {
        guard let action else { return nil }
        guard let interaction else { return action }
        return { value in
            interaction()
            action(value)
        }
    }

    /// The same for an action without a value.
    static func heldAction(_ action: (() -> Void)?, by interaction: (() -> Void)?) -> (() -> Void)? {
        guard let action else { return nil }
        guard let interaction else { return action }
        return {
            interaction()
            action()
        }
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .fullHistory: fullHistoryMode
            case .fullPeriods: fullPeriodsMode
            case .catalogue: catalogueMode
            case .original: originalMode
            case .about: textMode(aboutContent(), id: LacrosseEventPageAccessibilityID10868.about)
            case .source: textMode(sourceContent(), id: LacrosseEventPageAccessibilityID10868.source)
            case .report: textMode(reportContent(), id: LacrosseEventPageAccessibilityID10868.report)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    /// The host's About opener; nil without readable About text or without a
    /// callback, so no About control is drawn.
    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    /// The host's report opener; nil without a readable report or a callback.
    func reportOpener() -> (() -> Void)? {
        guard model.reportAvailable(canOpen: onReport != nil), let onReport else { return nil }
        return onReport
    }

    /// The match headline, at the page's phase only. On the page its open and
    /// About pass the interaction hook first; above the full-size quarters they
    /// keep the exact callbacks.
    func headlineContent(reader: Bool = false) -> FieldPhaseHeadlinePresentation10868? {
        let interaction = reader ? nil : onInteraction
        return model.headline.map {
            FieldPhaseHeadlinePresentation10868(input: $0, onAbout: Self.heldAction(aboutOpener(), by: interaction),
                                                onOpen: Self.held(onHeadlineOpen, by: interaction))
        }
    }

    /// The equal-size dated comparison: the accepted standalone View, read
    /// from the very history copy the history leaf shows beside it — the same
    /// resolved slots inline and full size. It acts on nothing.
    func comparisonContent(reader: Bool, enlarged: Bool = false) -> RugbyMatchEventPageComparisonPresentation10868 {
        RugbyMatchEventPageComparisonPresentation10868(
            history: reader ? model.readerHistory(enlarged: enlarged) : model.history(enlarged: enlarged),
            label: input.copy.comparisonLabel)
    }

    /// The anchor passes the interaction hook first; the full-size history
    /// keeps the exact callbacks. `enlarged` picks the owner's enlarged plot
    /// height; the view passes its own accessibility size.
    func historyContent(reader: Bool, enlarged: Bool = false) -> FieldProbabilityHistoryPresentation10868 {
        let interaction = reader ? nil : onInteraction
        return FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory(enlarged: enlarged) : model.history(enlarged: enlarged),
            onAction: Self.held(onHistoryAction, by: interaction),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: interaction),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: interaction)
        )
    }

    /// The actual quarters, during and after play. On the page the expand,
    /// choice and report controls pass the hook first; full size there is no
    /// expand and the choice and report keep their exact callbacks. Never
    /// reads the inspection.
    func periodsContent(reader: Bool) -> LacrosseEventPagePeriodGoalsPresentation10868? {
        let interaction = reader ? nil : onInteraction
        return model.periods.map {
            LacrosseEventPagePeriodGoalsPresentation10868(
                input: $0,
                onChoose: Self.held(onPeriodChoose, by: interaction),
                onExpand: reader ? nil : Self.heldAction(onPeriodsExpand, by: interaction),
                onReport: Self.heldAction(reportOpener(), by: interaction)
            )
        }
    }

    /// The existing chooser and held Details on the page, with the owner's
    /// originals exactly as admitted, its select callback after the hook.
    func chooserContent() -> OriginalMarketChooserView9483? {
        originals.map {
            OriginalMarketChooserView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: Self.held(onOriginalSelect, by: onInteraction)
            )
        }
    }

    /// The existing catalogue with the owner's originals, exactly as admitted,
    /// and its select callback after the interaction hook.
    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: Self.held(onOriginalSelect, by: onInteraction)
            )
        }
    }

    /// The existing Details for the owner's held selection, with its optional
    /// recorded history and its history callback after the interaction hook.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: Self.held(onOriginalHistory, by: onInteraction)
            )
        }
    }

    /// The owner's About — content the host already holds, so no hook.
    func aboutContent() -> LacrosseEventPageTextContent10868? {
        model.about.map { LacrosseEventPageTextContent10868(text: $0, onLink: onLink) }
    }

    func sourceContent() -> LacrosseEventPageTextContent10868? {
        model.source.map { LacrosseEventPageTextContent10868(text: $0, onLink: onLink) }
    }

    func reportContent() -> LacrosseEventPageTextContent10868? {
        model.report.map { LacrosseEventPageTextContent10868(text: $0, onLink: onLink) }
    }

    /// Full-size content's About: the exact callback, no hook.
    func openReaderAbout() {
        aboutOpener()?()
    }

    /// The page's source entry, after the interaction hook.
    func openSource() {
        guard model.sourceAvailable(canOpen: onSource != nil) else { return }
        Self.heldAction(onSource, by: onInteraction)?()
    }

    /// The page's All props entry, after the interaction hook.
    func openAllProps() {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return }
        Self.heldAction(onAllProps, by: onInteraction)?()
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            hero
            if let periods = periodsContent(reader: false) {
                periods
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(LacrosseEventPageCardSurface10868())
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.periods)
            } else if let words = model.periodsUnavailable {
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(LacrosseEventPageCardSurface10868())
                    .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.periodsUnavailable)
            }
            originalsPanel
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.page)
    }

    /// The headline and the history in one panel: side by side where both fit
    /// at their minimum widths, otherwise the headline above the history.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            let arrangements = LacrosseEventPageModel10868.arrangements(
                sizeClass: sizeClass,
                accessibilitySize: typeSize.isAccessibilitySize
            )
            if arrangements == [.stacked] {
                heroStacked
            } else {
                ViewThatFits(in: .horizontal) {
                    heroSideBySide
                    heroStacked
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(LacrosseEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.hero)
    }

    private var heroStacked: some View {
        VStack(alignment: .leading, spacing: 24) {
            headlineSection
            anchor
        }
    }

    private var heroSideBySide: some View {
        HStack(alignment: .top, spacing: 32) {
            headlineSection
                .frame(minWidth: headlineMinWidth, maxWidth: headlineMaxWidth, alignment: .topLeading)
            anchor
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
        }
    }

    /// The headline, or the owner's words when its phase is not the page's,
    /// then the owner's status words.
    private var headlineSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            headlineOrWords(reader: false)
            if let notice = model.notice {
                Text(notice)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.notice)
            }
        }
    }

    @ViewBuilder private func headlineOrWords(reader: Bool) -> some View {
        if let headline = headlineContent(reader: reader) {
            headline
        } else {
            Text(input.copy.headlineUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.headlineUnavailable)
        }
    }

    /// The equal-size dated comparison above the history, then the source
    /// entry when the owner names one.
    private var anchor: some View {
        VStack(alignment: .leading, spacing: 12) {
            comparisonContent(reader: false, enlarged: typeSize.isAccessibilitySize)
            historyContent(reader: false, enlarged: typeSize.isAccessibilitySize)
            if model.sourceAvailable(canOpen: onSource != nil), let label = input.copy.sourceLabel {
                entry(label, action: openSource, id: LacrosseEventPageAccessibilityID10868.sourceEntry)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.anchor)
    }

    /// The originals with the held original's Details, then the All props
    /// entry when the owner names one.
    @ViewBuilder private var originalsPanel: some View {
        let allProps = model.allPropsAvailable(canOpen: onAllProps != nil)
        if chooserContent() != nil || allProps {
            VStack(alignment: .leading, spacing: 16) {
                if let chooser = chooserContent() {
                    chooser
                }
                if allProps, let label = input.copy.allPropsLabel {
                    entry(label, action: openAllProps, id: LacrosseEventPageAccessibilityID10868.allProps)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(LacrosseEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.originals)
        }
    }

    private func entry(_ label: String, action: @escaping () -> Void, id: String) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Text(label)
                    .font(.body.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right")
                    .font(.body.weight(.semibold))
                    .accessibilityHidden(true)
            }
            .foregroundStyle(DS.blue)
            .frame(minHeight: controlSize)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }

    // MARK: Full-size content

    /// The same comparison and history copy, full size, under the compact
    /// match words.
    private var fullHistoryMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            compactHeader
            comparisonContent(reader: true, enlarged: typeSize.isAccessibilitySize)
            historyContent(reader: true, enlarged: typeSize.isAccessibilitySize)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.fullHistory)
    }

    /// The same headline and quarter inputs, full size, under the compact
    /// match words: the pre-match chances stay labelled above the actual
    /// goals. None when this phase shows no quarters.
    @ViewBuilder private var fullPeriodsMode: some View {
        if let periods = periodsContent(reader: true) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                headlineOrWords(reader: true)
                periods
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.fullPeriods)
        }
    }

    /// The owner's one-line match words and, in the full-size history, the
    /// About entry.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = LacrosseEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutEntry(mode: mode, canOpen: onAbout != nil) {
                Button(action: openReaderAbout) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(input.headline.copy.aboutLabel)
                .accessibilityHint(input.headline.copy.aboutHint ?? "")
                .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.readerHeader)
    }

    // MARK: All props, Details and text

    /// The owner's admitted originals under the compact match words.
    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.catalogue)
        }
    }

    /// The held original's existing Details, for the host's container.
    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(LacrosseEventPageAccessibilityID10868.original)
        }
    }

    /// The owner's text under the compact match words; none without readable text.
    @ViewBuilder private func textMode(_ content: LacrosseEventPageTextContent10868?, id: String) -> some View {
        if let content {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(id)
        }
    }
}

/// The reference's white card on the page surface.
private struct LacrosseEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
