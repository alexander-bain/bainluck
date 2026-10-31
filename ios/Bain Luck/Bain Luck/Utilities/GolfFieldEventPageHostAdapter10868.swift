import SwiftUI

/// #10868 — THE GOLF TOURNAMENT SCREEN'S HOST GLUE: what a golf tournament
/// destination would mount, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: a golf tournament opens on the named
/// chance-to-win history, the selected golfer's finish outlook and, before the
/// start date, who starts strongest; the full-size history, each story and the
/// golfer chooser open over it and close back to the same place, and choosing a
/// golfer anywhere updates the whole screen.
///
/// What it owns is only the screen's own reading state: which mode is shown, the
/// selected golfer, the selected finish and the chooser's disclosures. It builds
/// the page input from the values the page already holds (passed in — it reads
/// no view model, opens no network, subscribes to nothing, runs no timer and
/// ranks nothing).
///
/// The input is recomputed from those values on every body pass. No owner
/// supplies a revision that covers every value the adapters read (served prices
/// and stamps, history rows, grades, market status), and a partial memo would
/// hold a changed price on screen, so none is kept here (performance work,
/// routed).
///
/// Proposed mount (NOT applied — the golf tournament destination is Native's,
/// and no `ReleaseSurfaces` switch for it exists; adding one is Native's call):
/// ```swift
/// if GolfFieldEventPageHost10868.applies(winner) {
///     GolfFieldEventPageHost10868(
///         winner: winner,            // /api/futures/{evolution_market_id}
///         history: winnerHistory,    // /api/futures/{evolution_market_id}/history
///         legs: finishLegs,          // Top 5 / 10 / 20 / Make the Cut + the owner's join
///         tournament: presentation,  // GolfTournamentViewModel's loaded state
///         cohort: chartGolfers,      // the owner's chart golfers
///         initialSelection: nil,
///         now: now,
///         onInteraction: { /* the page's existing reader hold, if any */ })
/// }
/// ```
/// Owed before that line can be written: `GolfTournamentDetailResponse` does not
/// decode the served `evolution_market_id` or `markets` groups, nothing fetches
/// the Winner detail/history or the finish markets for this destination, and no
/// owner serves the per-golfer join across finish markets or a chart cohort.
///
/// Controls: Full chart opens the full-size history; Choose golfers opens the
/// chooser; a key entry chooses that golfer. Details is offered unavailable (no
/// destination), finish Details and original Details get no callback, and the
/// page has no About destination — so no control is drawn that does nothing.
/// Choosing never resumes or replaces a reading: there is no golf reading hold.
struct GolfFieldEventPageHost10868: View {
    let winner: FuturesMarketDetail
    let history: FuturesHistoryResponse?
    var legs: GolfFieldFinishAdapter10868.Legs = .init()
    var tournament: GolfTournamentPresentation? = nil
    /// The chart's golfers (Winner outcome ids), in the adopting owner's order.
    let cohort: [Int]
    /// The owner's selection before the reader chooses; nil elects none.
    var initialSelection: Int? = nil
    var now: Date = Date()
    /// The page's existing hold, requested BEFORE any reader mode opens.
    var onInteraction: (() -> Void)? = nil

    /// Golf futures markets only; which markets get this screen is the adopting owner's call.
    static func applies(_ winner: FuturesMarketDetail) -> Bool {
        (winner.llmSportCategory ?? "").lowercased() == "golf"
    }

    /// A non-page mode shown over the page.
    struct Presented: Identifiable, Equatable {
        let mode: GolfEventPageMode10868
        var id: String {
            switch mode {
            case .page: "page"
            case .reader(let card): "reader.\(card)"
            case .chooser: "chooser"
            }
        }
    }

    /// The screen's own reading state, as the builder takes it.
    struct Choice: Equatable {
        var selected: Int?
        var selectedFinish: String?
        var chooser: GolfFieldChooserAdapter10868.Disclosures

        init(selected: Int? = nil, selectedFinish: String? = nil,
             chooser: GolfFieldChooserAdapter10868.Disclosures = .init()) {
            self.selected = selected
            self.selectedFinish = selectedFinish
            self.chooser = chooser
        }
    }

    /// What one history action id asks the host to do.
    enum HistoryRoute: Equatable {
        case expand
        case chooser
        case choose(Int)
        /// Offered unavailable, or not this page's.
        case none
    }

    @State private var presented: Presented?
    @State private var chosen: Int?
    @State private var hasChosen = false
    @State private var selectedFinish: String?
    @State private var moreExpanded = false
    @State private var browseExpanded = false
    @State private var browseGroup: String?

    var body: some View {
        page(make(), mode: .page)
            .sheet(item: $presented) { shown in
                NavigationStack {
                    ScrollView {
                        page(make(), mode: shown.mode).padding(.horizontal, 16)
                    }
                    .toolbar {
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Done") { presented = nil }
                        }
                    }
                }
            }
    }

    private func page(_ input: GolfEventPageInput10868, mode: GolfEventPageMode10868) -> GolfEventPagePresentation10868 {
        GolfEventPagePresentation10868(
            input: input, mode: mode,
            onAbout: nil,
            onOpenCard: { card in open(.reader(card)) },
            onHistoryAction: { id in handle(Self.route(id)) },
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: nil,
            onSelectFinish: { selectedFinish = $0 },
            onFinishDetails: nil,
            onChoose: { ref in
                if let id = GolfFieldChooserAdapter10868.outcomeID(ref, market: winner) { choose(id) }
            },
            onChooserControl: { control in apply(control) },
            onOpenOriginal: nil)
    }

    /// The hold first, then the exact mode — never the reverse.
    private func open(_ mode: GolfEventPageMode10868) {
        onInteraction?()
        presented = Presented(mode: mode)
    }

    private func choose(_ id: Int) {
        chosen = id
        hasChosen = true
        selectedFinish = nil
    }

    private func handle(_ route: HistoryRoute) {
        switch route {
        case .expand: open(.reader(.history))
        case .chooser: open(.chooser)
        case .choose(let id): choose(id)
        case .none: break
        }
    }

    private func apply(_ control: FieldChooserControl10868) {
        switch control {
        case .toggleMore: moreExpanded.toggle()
        case .toggleBrowse: browseExpanded.toggle()
        case .chooseGroup(let id): browseGroup = id
        }
    }

    private func make() -> GolfEventPageInput10868 {
        Self.build(winner: winner, history: history, legs: legs, tournament: tournament, cohort: cohort,
                   choice: Choice(selected: hasChosen ? chosen : initialSelection, selectedFinish: selectedFinish,
                                  chooser: .init(moreExpanded: moreExpanded, browseExpanded: browseExpanded,
                                                 browseGroup: browseGroup)),
                   now: now)
    }

    /// The history action ids this page routes; every other id does nothing.
    static func route(_ id: String) -> HistoryRoute {
        if id == GolfFieldHistoryAdapter10868.expandActionID { return .expand }
        if id == GolfFieldHistoryAdapter10868.chooserActionID { return .chooser }
        let prefix = GolfFieldHistoryAdapter10868.choosePrefix
        if id.hasPrefix(prefix), let outcome = Int(id.dropFirst(prefix.count)) { return .choose(outcome) }
        return .none
    }

    /// The chart's golfers with the selected golfer kept in view: the owner's
    /// cohort, then the selection when it is not already drawn.
    static func chartGolfers(_ cohort: [Int], selected: Int?) -> [Int] {
        guard let selected, !cohort.contains(selected) else { return cohort }
        return cohort + [selected]
    }

    /// The page input from the passed values alone — pure, so every changed
    /// value reaches the screen on the next pass. A missing history response
    /// leaves only the chart slot unavailable.
    static func build(winner: FuturesMarketDetail, history: FuturesHistoryResponse?,
                      legs: GolfFieldFinishAdapter10868.Legs = .init(), tournament: GolfTournamentPresentation? = nil,
                      cohort: [Int], choice: Choice = Choice(), now: Date,
                      calendar: Calendar = .current, locale: Locale = .current) -> GolfEventPageInput10868 {
        let sources = GolfFieldPageInputAdapter10868.Sources(winner: winner, history: history, legs: legs,
                                                            tournament: tournament)
        let reading = GolfFieldPageInputAdapter10868.Reading(
            cohort: chartGolfers(cohort, selected: choice.selected), selected: choice.selected,
            selectedFinish: choice.selectedFinish, chooser: choice.chooser)
        return GolfFieldPageInputAdapter10868.input(
            sources, reading: reading,
            host: GolfFieldPageAdapter10868.Host(now: now, calendar: calendar, locale: locale))
    }
}
