import SwiftUI

/// #10868 — THE HOCKEY JOURNEY SCREEN'S HOST GLUE: what `EventDetailView` would
/// mount for an NHL game, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: an NHL event page opens on the paired
/// chances, the two-team history and the points and assists stories, and every
/// full-size card, the All props catalogue, an original's Details and About open
/// over it and close back to the same place.
///
/// What it owns is only the screen's own reading state: which mode is shown,
/// which story is held, which player and milestone each story is on, the held
/// original and the disclosures. It builds the page input from the values the
/// page already holds (passed in — it reads no view model, opens no network,
/// subscribes to nothing, runs no timer and ranks nothing) and rebuilds it only
/// when those values change, never on every body pass.
///
/// Proposed mount (NOT applied — `EventDetailView` is Native's):
/// ```swift
/// if ReleaseSurfaces.hockeyJourneyPageEnabled, HockeyJourneyEventPageHost10868.applies(event) {
///     HockeyJourneyEventPageHost10868(
///         event: vm.headline(event), history: vm.history, historyRevision: vm.historyGeneration,
///         markets: vm.gameMarkets, boxScore: vm.relatedFutures?.boxScore,
///         probabilityObservedAt: vm.displayedProbabilityObservedAt(event),
///         deliveryInterrupted: vm.liveUpdateStatus == .interrupted,
///         ladderHome: vm.history?.pmSpreadData?.projectedFinal?.homeScore,
///         ladderAway: vm.history?.pmSpreadData?.projectedFinal?.awayScore,
///         now: now,
///         onInteraction: { /* the page's existing reader hold */ })
/// }
/// ```
/// Backout is the same switch off (`ReleaseSurfaces`, the project's existing
/// per-surface gate); no data or route is touched by either state.
///
/// Until the first history payload arrives the slot shows the page's own
/// loading mark. The history owner has no words for a history that failed to
/// load, so none are invented here (routed, #10868 gap).
struct HockeyJourneyEventPageHost10868: View {
    let event: EventDetail
    let history: EventHistoryResponse?
    /// `vm.historyGeneration`: one step per adopted history payload.
    var historyRevision: Int = 0
    let markets: GameMarketsResponse?
    let boxScore: [String: [String: Double]]?
    let probabilityObservedAt: Date?
    var deliveryInterrupted: Bool = false
    var ladderHome: Double? = nil
    var ladderAway: Double? = nil
    var now: Date = Date()
    /// The page's existing hold, requested BEFORE any reader action the stream
    /// or a card starts. Appearance and reads call nothing.
    var onInteraction: (() -> Void)? = nil

    /// NHL games only; which NHL games get this screen is the adopting owner's call.
    static func applies(_ event: EventDetail) -> Bool {
        (event.sport ?? "").lowercased().hasPrefix("icehockey_nhl")
    }

    /// A non-page mode shown over the page.
    struct Presented: Identifiable, Equatable {
        let mode: HockeyJourneyPageMode10868
        var id: String {
            switch mode {
            case .page: "page"
            case .reader(let card): "reader.\(card.rawValue)"
            case .catalogue: "catalogue"
            case .original: "original"
            case .about: "about"
            }
        }
    }

    /// Everything a rebuild depends on: the event's served state, the history
    /// revision, the markets and box score by value, the reader's minute and
    /// the screen's own reading state.
    struct BuildKey: Equatable {
        let eventID: Int
        let status: String?
        let commenceTime: String?
        let homeScore: Int?
        let awayScore: Int?
        let scoreObservedAt: String?
        let period: String?
        let gameClock: String?
        let heroHome: Double?
        let heroAway: Double?
        let heroObservedAt: String?
        let probabilityObservedAt: Date?
        let interrupted: Bool
        let ladderHome: Double?
        let ladderAway: Double?
        let hasHistory: Bool
        let historyRevision: Int
        let markets: GameMarketsResponse?
        let boxScore: [String: [String: Double]]?
        let minute: Int
        let wide: Bool
        let pointsPlayer: String?
        let pointsMilestone: String?
        let assistsPlayer: String?
        let assistsMilestone: String?
        let story: HockeyJourneyPageCard10868?
        let readerOpen: Bool
        let selection: OriginalMarketDetails9483.Selection?
    }

    struct Built {
        let input: HockeyJourneyPageInput10868
        let originals: HockeyJourneyPageOriginals10868
    }

    @State private var built: Built?
    @State private var presented: Presented?
    @State private var story: HockeyJourneyPageCard10868?
    @State private var pointsPlayer: String?
    @State private var pointsMilestone: String?
    @State private var assistsPlayer: String?
    @State private var assistsMilestone: String?
    @State private var selection: OriginalMarketDetails9483.Selection?
    @State private var pointsChoices = false
    @State private var pointsTiming = false
    @State private var assistsChoices = false
    @State private var assistsTiming = false
    @Environment(\.horizontalSizeClass) private var sizeClass

    private var key: BuildKey {
        BuildKey(eventID: event.id, status: event.status, commenceTime: event.commenceTime,
                 homeScore: event.homeScore, awayScore: event.awayScore, scoreObservedAt: event.scoreObservedAt,
                 period: event.espn?.period, gameClock: event.espn?.gameClock,
                 heroHome: event.heroProbability, heroAway: event.heroProbabilityAway,
                 heroObservedAt: event.heroProbabilityObservedAt, probabilityObservedAt: probabilityObservedAt,
                 interrupted: deliveryInterrupted, ladderHome: ladderHome, ladderAway: ladderAway,
                 hasHistory: history != nil, historyRevision: historyRevision,
                 markets: markets, boxScore: boxScore,
                 minute: Int(now.timeIntervalSince1970 / 60), wide: sizeClass == .regular,
                 pointsPlayer: pointsPlayer, pointsMilestone: pointsMilestone,
                 assistsPlayer: assistsPlayer, assistsMilestone: assistsMilestone,
                 story: story, readerOpen: presented != nil, selection: selection)
    }

    var body: some View {
        Group {
            if let built {
                page(built, mode: .page)
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 120)
            }
        }
        .onChange(of: key, initial: true) { _, _ in built = make() }
        .sheet(item: $presented) { shown in
            NavigationStack {
                ScrollView {
                    if let built { page(built, mode: shown.mode).padding(.horizontal, 16) }
                }
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { presented = nil }
                    }
                }
            }
        }
    }

    private func page(_ built: Built, mode: HockeyJourneyPageMode10868) -> HockeyJourneyEventPagePresentation10868 {
        HockeyJourneyEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
            onAbout: { open(.about) },
            onAllProps: { open(.catalogue) },
            onOriginalSelect: { chosen in
                selection = chosen
                open(.original)
            },
            onOriginalHistory: nil,
            onStoryIntent: { intent in handle(intent) },
            onOpenStory: { card in open(.reader(card)) },
            onHistoryAction: { id in
                if id == "history.expand" { open(.reader(.history)) }
            },
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: nil,
            onPointsSelect: { pointsMilestone = $0 },
            onPointsChoosePlayer: { pointsPlayer = $0; pointsMilestone = nil },
            onPointsDetails: nil,
            onAssistsSelect: { assistsMilestone = $0 },
            onAssistsChoosePlayer: { assistsPlayer = $0; assistsMilestone = nil },
            onAssistsDetails: nil,
            pointsChoicesExpanded: $pointsChoices,
            pointsTimingExpanded: $pointsTiming,
            assistsChoicesExpanded: $assistsChoices,
            assistsTimingExpanded: $assistsTiming)
    }

    /// The hold first, then the exact mode — never the reverse.
    private func open(_ mode: HockeyJourneyPageMode10868) {
        onInteraction?()
        presented = Presented(mode: mode)
    }

    private func handle(_ intent: StoryStreamPresentation10868.Intent) {
        switch intent {
        case .interaction:
            onInteraction?()
        case .browse(_, let target):
            story = HockeyJourneyPageCard10868(rawValue: target.id)
        case .open(let target):
            if let card = HockeyJourneyPageCard10868(rawValue: target.id) { open(.reader(card)) }
        case .pause, .resume, .applyUpdates:
            break // the manual stream offers none of these controls
        }
    }

    /// Nil until the first history payload: the history owner has no
    /// loading or failed-load state, and the page input requires one.
    private func make() -> Built? {
        guard let history else { return nil }
        let calendar = Calendar.current
        let locale = Locale.current
        let host = HockeyJourneyPageAdapter10868.Host(
            probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
            ladderHome: ladderHome, ladderAway: ladderAway, now: now, calendar: calendar, locale: locale)
        let phase = HockeyJourneyPageAdapter10868.phase(event, now: now)
        let historyInput = HockeyJourneyHistoryAdapter10868.history(
            history, event: event, phase: phase,
            host: HockeyJourneyHistoryAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        let people = HockeyJourneyContributionAdapter10868.Host(
            boxScore: boxScore, now: now, calendar: calendar, locale: locale)
        let points = HockeyJourneyContributionAdapter10868.points(
            event, markets: markets, host: people, selectedPlayerID: pointsPlayer, selectedMilestoneID: pointsMilestone)
        let assists = HockeyJourneyContributionAdapter10868.assists(
            event, markets: markets, host: people, selectedPlayerID: assistsPlayer, selectedMilestoneID: assistsMilestone)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let originals = HockeyJourneyOriginalsAdapter10868.originals(
            event, markets: markets,
            host: HockeyJourneyOriginalsAdapter10868.Host(now: now, calendar: calendar, locale: locale),
            tint: tints.home, selection: selection)
        let input = HockeyJourneyPageInputAdapter10868.input(
            event, history: historyInput, points: points, assists: assists,
            originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: story, readerOpen: presented != nil, wide: sizeClass == .regular),
            host: host)
        return Built(input: input, originals: originals)
    }
}
