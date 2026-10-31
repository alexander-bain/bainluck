import SwiftUI

/// #10868 — THE GOLF TOURNAMENT SCREEN'S HOST GLUE: what a golf tournament
/// destination would mount, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER / TRUTH. SHIP: a golf tournament opens on the
/// named chance-to-win history, the selected golfer's finish outlook and, before
/// the start date, who starts strongest; the full-size history, each story and
/// the golfer chooser open over it and close back to the same place, and
/// choosing a golfer anywhere updates the whole screen. Finish and contender
/// cards open the exact original's Details — its own readings, result and
/// clocks — and Done returns to the same reader.
///
/// What it owns is only the screen's own reading state (`Session`): which mode
/// is shown, the Details over it, the selected golfer, the selected finish, the
/// chart inspection, and the chooser's disclosures. It builds the page input and
/// the originals from the values the page already holds (passed in — it reads no
/// view model, opens no network, subscribes to nothing, runs no timer and ranks
/// nothing).
///
/// The input and the originals are recomputed from those values on every body
/// pass. No owner supplies a revision that covers every value the adapters read
/// (served prices and stamps, history rows, grades, market status), and a
/// partial memo would hold a changed price on screen, so none is kept here
/// (performance work, routed: the originals hold every outcome of every held
/// market).
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
/// chooser; a key entry chooses that golfer. History Details is offered
/// unavailable (no destination) and the page has no About destination. Finish
/// Details and the contenders card's Details are decided on every pass
/// (`finishDetails` / `openOriginal`) and open `GolfFieldOriginalsAdapter10868`'s
/// exact original — or, for a current finish whose original is not held, a named
/// explanation — so no control is drawn that does nothing. Each Details open
/// asks for the page's hold first. Done unwinds one layer (Details → the card it
/// was opened over, or the page); an interactive dismissal returns to the page
/// with the golfer and finish kept. Choosing never resumes or replaces a
/// reading: there is no golf reading hold.
///
/// Chart inspection (`GolfFieldHistoryInspectionAdapter10868`): "Inspect
/// history" or a plot tap starts one, after the page's hold, once; previous,
/// next and the moment choices move inside it with no further hold; "Done
/// inspecting" ends it. Each render path builds ONE inspection snapshot and uses
/// it for the applied input and for all three history callbacks
/// (`historyAction` / `inspectionChoice` / `plotPosition`). The inspection
/// survives the full-size reader, Done, swipe-down, golfer choice and the scale
/// while it still resolves; the first pass it no longer resolves on clears it
/// (`Session.expireInspection`), so it never comes back without a new
/// deliberate inspection. Nothing is held or resumed for incoming updates.
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
        /// Full scale on; false is the approved Auto scale.
        var fullScale: Bool
        /// The held chart inspection; nil when none is open.
        var inspection: GolfFieldHistoryInspectionAdapter10868.Held?

        init(selected: Int? = nil, selectedFinish: String? = nil,
             chooser: GolfFieldChooserAdapter10868.Disclosures = .init(), fullScale: Bool = false,
             inspection: GolfFieldHistoryInspectionAdapter10868.Held? = nil) {
            self.selected = selected
            self.selectedFinish = selectedFinish
            self.chooser = chooser
            self.fullScale = fullScale
            self.inspection = inspection
        }
    }

    /// What one history action id asks the host to do.
    enum HistoryRoute: Equatable {
        case expand
        case chooser
        case choose(Int)
        /// Auto ↔ Full scale.
        case scale
        /// Offered unavailable, or not this page's.
        case none
    }

    /// The host's open layers and held choices, with pure transitions. Return
    /// context is kept here, locally — no app routing is touched:
    ///   - a full-size card or the chooser opens over the page; Done returns to it;
    ///   - Details opened from a full-size card sits over that card; Done returns
    ///     to the SAME card with the same golfer and finish;
    ///   - Details opened from the page returns to the page;
    ///   - an interactive dismissal returns to the page, golfer and finish kept.
    struct Session: Equatable {
        /// The full-size card or the chooser open in the sheet; never `.page`.
        var mode: GolfEventPageMode10868? = nil
        /// Details, over `mode` when one is open, else over the page.
        var details: GolfFieldOriginalsAdapter10868.Destination? = nil
        var chosen: Int? = nil
        var hasChosen = false
        var selectedFinish: String? = nil
        /// The held chart inspection. Set only by a deliberate inspection action,
        /// cleared by Done or by the first pass it no longer resolves on, and never
        /// revived: a cleared inspection stays cleared whatever the data does next.
        var inspection: GolfFieldHistoryInspectionAdapter10868.Held? = nil

        /// The sheet's base layer: the open card or chooser, or the page under
        /// Details opened from it. Its id does not change while Details opens or
        /// closes over a card, so the card's sheet is never re-presented.
        var presented: Presented? {
            if let mode { return Presented(mode: mode) }
            return details == nil ? nil : Presented(mode: .page)
        }

        /// The reader's choice once made, else the owner's.
        func selected(initial: Int?) -> Int? { hasChosen ? chosen : initial }

        mutating func open(_ mode: GolfEventPageMode10868) {
            self.mode = mode == .page ? nil : mode
            details = nil
        }

        mutating func openDetails(_ destination: GolfFieldOriginalsAdapter10868.Destination) {
            details = destination
        }

        mutating func choose(_ id: Int) {
            chosen = id
            hasChosen = true
            selectedFinish = nil
        }

        mutating func selectFinish(_ id: String) {
            selectedFinish = id
        }

        /// Done: Details returns to the card it was opened over (or the page); a
        /// card or the chooser returns to the page.
        mutating func close() {
            if details != nil {
                details = nil
            } else {
                mode = nil
            }
        }

        /// The sheet was dismissed interactively: the page, choices kept.
        mutating func dismiss() {
            details = nil
            mode = nil
        }

        /// A deliberate inspection choice: start, step, moment choice or plot tap.
        mutating func inspect(_ held: GolfFieldHistoryInspectionAdapter10868.Held) {
            inspection = held
        }

        /// "Done inspecting".
        mutating func endInspection() {
            inspection = nil
        }

        /// Sticky withdrawal: an inspection that does not resolve on this pass is
        /// cleared, so evidence matching again later (A→B→A, a phase out and back)
        /// finds nothing to revive. Only the inspection is touched — the golfer,
        /// finish, open card and Details stay.
        mutating func expireInspection(in pass: GolfFieldHistoryInspectionAdapter10868.Pass) {
            guard let held = inspection, GolfFieldHistoryInspectionAdapter10868.resolve(held, in: pass) == nil else {
                return
            }
            inspection = nil
        }
    }

    @State private var session = Session()
    @State private var moreExpanded = false
    @State private var browseExpanded = false
    @State private var browseGroup: String?
    /// The reader's reversible Full-scale choice: one flag for the page and the
    /// full-size reader, kept across data refreshes.
    @State private var fullScale = false

    var body: some View {
        let snapshot = makeSnapshot()
        page(make(snapshot), mode: .page, originals: makeOriginals(), snapshot: snapshot)
            .sheet(item: Binding(get: { session.presented },
                                 set: { shown in if shown == nil { session.dismiss() } })) { _ in
                NavigationStack {
                    ScrollView {
                        sheetContent.padding(.horizontal, 16)
                    }
                    .toolbar {
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Done") { session.close() }
                        }
                    }
                }
            }
            .onChange(of: snapshot.pass) { _, pass in session.expireInspection(in: pass) }
    }

    /// Details over the open card or the page, else the open card or chooser —
    /// each over THIS pass's input and originals.
    @ViewBuilder private var sheetContent: some View {
        let snapshot = makeSnapshot()
        let input = make(snapshot)
        let originals = makeOriginals()
        if let details = session.details {
            detailsContent(details, input: input, originals: originals)
        } else if let mode = session.mode {
            page(input, mode: mode, originals: originals, snapshot: snapshot)
        }
    }

    @ViewBuilder private func detailsContent(_ destination: GolfFieldOriginalsAdapter10868.Destination,
                                             input: GolfEventPageInput10868,
                                             originals: GolfFieldOriginalsAdapter10868.Originals) -> some View {
        switch GolfFieldOriginalsAdapter10868.shown(destination, finish: GolfEventPageModel10868(input).finish,
                                                    originals: originals) {
        case .original(let selection):
            OriginalMarketDetailsView9483(catalogue: originals.catalogue, selection: selection, tint: DS.blue)
        case .notSupplied(let title):
            GolfFinishOriginalNotSupplied10868(title: title)
        case .unavailable:
            // The Details' own unavailable view: no selection is invented.
            OriginalMarketDetailsView9483(catalogue: originals.catalogue, selection: nil, tint: DS.blue)
        }
    }

    private func page(_ input: GolfEventPageInput10868, mode: GolfEventPageMode10868,
                      originals: GolfFieldOriginalsAdapter10868.Originals,
                      snapshot: GolfFieldHistoryInspectionAdapter10868.Snapshot) -> GolfEventPagePresentation10868 {
        GolfEventPagePresentation10868(
            input: input, mode: mode,
            onAbout: nil,
            onOpenCard: { card in open(.reader(card)) },
            onHistoryAction: Self.historyAction(snapshot, hold: onInteraction,
                                                inspect: { session.inspect($0) },
                                                end: { session.endInspection() },
                                                other: { id in handle(Self.route(id)) }),
            onHistoryInspectionChoice: Self.inspectionChoice(snapshot, inspect: { session.inspect($0) }),
            onHistoryPlotPosition: Self.plotPosition(snapshot, hold: onInteraction,
                                                     inspect: { session.inspect($0) }),
            onSelectFinish: { session.selectFinish($0) },
            onFinishDetails: Self.finishDetails(input, originals: originals, hold: onInteraction,
                                                open: { session.openDetails($0) }),
            onChoose: { ref in
                if let id = GolfFieldChooserAdapter10868.outcomeID(ref, market: winner) { session.choose(id) }
            },
            onChooserControl: { control in apply(control) },
            onOpenOriginal: Self.openOriginal(input, originals: originals, hold: onInteraction,
                                              open: { session.openDetails($0) }))
    }

    /// The hold first, then the exact mode — never the reverse.
    private func open(_ mode: GolfEventPageMode10868) {
        onInteraction?()
        session.open(mode)
    }

    private func handle(_ route: HistoryRoute) {
        switch route {
        case .expand: open(.reader(.history))
        case .chooser: open(.chooser)
        case .choose(let id): session.choose(id)
        case .scale: fullScale.toggle()
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

    private func make(_ snapshot: GolfFieldHistoryInspectionAdapter10868.Snapshot) -> GolfEventPageInput10868 {
        Self.build(winner: winner, history: history, legs: legs, tournament: tournament, cohort: cohort,
                   choice: Choice(selected: session.selected(initial: initialSelection),
                                  selectedFinish: session.selectedFinish,
                                  chooser: .init(moreExpanded: moreExpanded, browseExpanded: browseExpanded,
                                                 browseGroup: browseGroup),
                                  fullScale: fullScale,
                                  inspection: session.inspection),
                   snapshot: snapshot,
                   now: now)
    }

    /// This render path's one inspection snapshot.
    private func makeSnapshot() -> GolfFieldHistoryInspectionAdapter10868.Snapshot {
        Self.inspectionSnapshot(winner: winner, history: history, cohort: cohort,
                                selected: session.selected(initial: initialSelection),
                                held: session.inspection, now: now)
    }

    /// One pass's history action callback: the four inspection ids by exact
    /// equality, every other id to the existing `route`. A start asks for the
    /// page's hold once, first; a step, a choice or Done asks for none. An
    /// inspection control that names nothing on this snapshot does nothing — it
    /// is drawn unavailable or not drawn at all. Building it calls nothing.
    static func historyAction(_ snapshot: GolfFieldHistoryInspectionAdapter10868.Snapshot, hold: (() -> Void)?,
                              inspect: @escaping (GolfFieldHistoryInspectionAdapter10868.Held) -> Void,
                              end: @escaping () -> Void,
                              other: @escaping (String) -> Void) -> (String) -> Void {
        return { id in
            switch GolfFieldHistoryInspectionAdapter10868.intent(id, resolved: snapshot.resolved, in: snapshot.pass) {
            case .start(let held)?:
                hold?()
                inspect(held)
            case .select(let held)?:
                inspect(held)
            case .end?:
                end()
            case .unavailable?:
                break
            case nil:
                other(id)
            }
        }
    }

    /// One pass's moment-choice callback: offered only while an inspection
    /// resolves (the choices are drawn); a choice id resolves by exact equality
    /// against this snapshot's moments, or chooses nothing.
    static func inspectionChoice(_ snapshot: GolfFieldHistoryInspectionAdapter10868.Snapshot,
                                 inspect: @escaping (GolfFieldHistoryInspectionAdapter10868.Held) -> Void)
        -> ((String) -> Void)? {
        guard snapshot.resolved != nil else { return nil }
        let pass = snapshot.pass
        return { id in
            if let held = GolfFieldHistoryInspectionAdapter10868.choice(id, in: pass) { inspect(held) }
        }
    }

    /// One pass's plot-tap callback: offered only where inspection is (not at the
    /// final, not without drawn history). A tap that starts an inspection asks
    /// for the page's hold once, first; a tap inside one asks for none.
    static func plotPosition(_ snapshot: GolfFieldHistoryInspectionAdapter10868.Snapshot, hold: (() -> Void)?,
                             inspect: @escaping (GolfFieldHistoryInspectionAdapter10868.Held) -> Void)
        -> ((Double) -> Void)? {
        guard snapshot.pass.offered else { return nil }
        let pass = snapshot.pass
        let inspecting = snapshot.resolved != nil
        return { x in
            guard let held = GolfFieldHistoryInspectionAdapter10868.position(x, in: pass) else { return }
            if !inspecting { hold?() }
            inspect(held)
        }
    }

    private func makeOriginals() -> GolfFieldOriginalsAdapter10868.Originals {
        Self.originals(winner: winner, history: history, legs: legs, now: now)
    }

    /// One pass's finish Details callback (Design D3): offered only when at
    /// least one current finish slot resolves to exactly one original — one
    /// absent finish never closes the others. A tap asks for the page's hold
    /// once, then opens what the tapped id names among THIS pass's slots: the
    /// exact original, the slot's named explanation, or the unavailable view.
    /// Building it calls nothing.
    static func finishDetails(_ input: GolfEventPageInput10868, originals: GolfFieldOriginalsAdapter10868.Originals,
                              hold: (() -> Void)?,
                              open: @escaping (GolfFieldOriginalsAdapter10868.Destination) -> Void) -> ((String) -> Void)? {
        let finish = GolfEventPageModel10868(input).finish
        guard GolfFieldOriginalsAdapter10868.finishDetailsOffered(finish, originals: originals) else { return nil }
        return { id in
            hold?()
            open(GolfFieldOriginalsAdapter10868.destination(finishID: id, finish: finish, originals: originals))
        }
    }

    /// One pass's contenders Details callback: offered only when the card's
    /// selected original resolves to exactly one original (before the start
    /// only — the card is not mounted otherwise). A tap asks for the hold once,
    /// then opens that exact original, or the unavailable view for a ref that
    /// names none. Building it calls nothing.
    static func openOriginal(_ input: GolfEventPageInput10868, originals: GolfFieldOriginalsAdapter10868.Originals,
                             hold: (() -> Void)?,
                             open: @escaping (GolfFieldOriginalsAdapter10868.Destination) -> Void)
        -> ((FieldChooserOriginalRef10868) -> Void)? {
        guard GolfFieldOriginalsAdapter10868.contendersDetailsOffered(GolfEventPageModel10868(input).contenders,
                                                                       originals: originals) else { return nil }
        return { ref in
            hold?()
            open(GolfFieldOriginalsAdapter10868.destination(ref: ref, originals: originals))
        }
    }

    /// The history action ids this page routes; every other id does nothing.
    static func route(_ id: String) -> HistoryRoute {
        if id == GolfFieldHistoryAdapter10868.expandActionID { return .expand }
        if id == GolfFieldHistoryAdapter10868.chooserActionID { return .chooser }
        if id == GolfFieldHistoryAdapter10868.scaleActionID { return .scale }
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
    /// leaves only the chart slot unavailable. The held inspection
    /// (`choice.inspection`) is resolved against one snapshot built here.
    static func build(winner: FuturesMarketDetail, history: FuturesHistoryResponse?,
                      legs: GolfFieldFinishAdapter10868.Legs = .init(), tournament: GolfTournamentPresentation? = nil,
                      cohort: [Int], choice: Choice = Choice(), now: Date,
                      calendar: Calendar = .current, locale: Locale = .current) -> GolfEventPageInput10868 {
        let snapshot = inspectionSnapshot(winner: winner, history: history, cohort: cohort, selected: choice.selected,
                                          held: choice.inspection, now: now, calendar: calendar, locale: locale)
        return build(winner: winner, history: history, legs: legs, tournament: tournament, cohort: cohort,
                     choice: choice, snapshot: snapshot, now: now, calendar: calendar, locale: locale)
    }

    /// The same page input over a snapshot the caller already built for this
    /// render path, so the input and every callback read ONE pass. The snapshot
    /// must be built from the same values and `choice.inspection`.
    static func build(winner: FuturesMarketDetail, history: FuturesHistoryResponse?,
                      legs: GolfFieldFinishAdapter10868.Legs, tournament: GolfTournamentPresentation?,
                      cohort: [Int], choice: Choice, snapshot: GolfFieldHistoryInspectionAdapter10868.Snapshot,
                      now: Date, calendar: Calendar = .current, locale: Locale = .current) -> GolfEventPageInput10868 {
        let sources = GolfFieldPageInputAdapter10868.Sources(winner: winner, history: history, legs: legs,
                                                            tournament: tournament)
        let reading = GolfFieldPageInputAdapter10868.Reading(
            cohort: chartGolfers(cohort, selected: choice.selected), selected: choice.selected,
            selectedFinish: choice.selectedFinish, chooser: choice.chooser, fullScale: choice.fullScale)
        let base = GolfFieldPageInputAdapter10868.input(
            sources, reading: reading,
            host: GolfFieldPageAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        return GolfFieldHistoryInspectionAdapter10868.applied(base, snapshot: snapshot)
    }

    /// One render path's inspection snapshot: the chart's golfers and the same
    /// Winner field the page input reads, normalized once, with the held
    /// inspection resolved against it once.
    static func inspectionSnapshot(winner: FuturesMarketDetail, history: FuturesHistoryResponse?, cohort: [Int],
                                   selected: Int?, held: GolfFieldHistoryInspectionAdapter10868.Held?, now: Date,
                                   calendar: Calendar = .current,
                                   locale: Locale = .current) -> GolfFieldHistoryInspectionAdapter10868.Snapshot {
        let field = GolfFieldPageInputAdapter10868.field(
            GolfFieldPageInputAdapter10868.Sources(winner: winner, history: history), now: now)
        let pass = GolfFieldHistoryInspectionAdapter10868.pass(
            field, cohort: chartGolfers(cohort, selected: selected),
            host: GolfFieldPageAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        return GolfFieldHistoryInspectionAdapter10868.Snapshot(pass: pass, held: held)
    }

    /// The originals from the passed values alone, through the same Winner field
    /// the page input reads — so a golfer's Details and finish card read alike.
    static func originals(winner: FuturesMarketDetail, history: FuturesHistoryResponse?,
                          legs: GolfFieldFinishAdapter10868.Legs = .init(), now: Date,
                          calendar: Calendar = .current, locale: Locale = .current) -> GolfFieldOriginalsAdapter10868.Originals {
        let field = GolfFieldPageInputAdapter10868.field(
            GolfFieldPageInputAdapter10868.Sources(winner: winner, history: history, legs: legs), now: now)
        return GolfFieldOriginalsAdapter10868.originals(
            field, legs: legs, host: GolfFieldPageAdapter10868.Host(now: now, calendar: calendar, locale: locale))
    }
}

/// Design D3: a current finish whose original the page does not hold, named in
/// the slot's own finish name. No market, identity or neighbour stands behind
/// it; the sheet's Done closes it.
private struct GolfFinishOriginalNotSupplied10868: View {
    let title: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.headline)
            Text(GolfFieldOriginalsAdapter10868.Words.notSuppliedNote)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title). \(GolfFieldOriginalsAdapter10868.Words.notSuppliedNote)")
    }
}
