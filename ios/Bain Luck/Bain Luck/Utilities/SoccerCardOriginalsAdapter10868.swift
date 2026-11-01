import Foundation

/// #10868 — THE SOCCER MATCH SCREEN'S PRODUCTION ADAPTER: A STORY CARD'S
/// DETAILS OPEN THAT ROW'S EXACT ORIGINAL.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: soccer story cards open their exact
/// original Details and return to the same card and chosen outcome — goal
/// milestones, both teams to score, first team to score, half by half and the
/// exact-score map each open the original market of the row they were tapped
/// on, in the page's existing Details.
///
/// It decides nothing the page does not already decide:
///   - which market   the owner's typed story admission
///                    (`SoccerPropReadingAdapter10868.Markets`, and its exact-score
///                    descriptor) — the same input that makes the card exist. A
///                    goal, both-teams or first-team origin names its admitted
///                    market; a half names the owner's half (market AND period
///                    identity); an exact-map original names the owner's scope
///                    (id, market AND period). Never a title, a position or a label.
///   - which row      `SoccerPropReadingAdapter10868.legs` of THAT market, kept by
///                    EXACT EQUALITY between the leg's id and the id the card
///                    handed back — the card's id is that same leg id, produced by
///                    the same rule. A half cell's id is compared with the id the
///                    real cell builder (`SoccerHalvesAdapter10868.cell`) gives that
///                    leg; no id is ever split or parsed. Exactly one leg, or none.
///   - which original the hockey originals adapter's own served rows
///                    (`HockeyJourneyOriginalsAdapter10868.sources`) whose catalogue
///                    row value is that leg's own row and whose identity side is the
///                    leg's id, through `identity(of:)` — called, never copied —
///                    accepted only as ONE served row that the page's own catalogue
///                    resolves by exact scope and identity
///                    (`OriginalMarketDetails9483.original(in:selection:)`, which
///                    refuses a blank, out-of-scope, withdrawn or duplicated one).
///                    Anything else opens the Details' own unavailable view — never
///                    a nearby original.
///   - what it holds  the typed ORIGIN (card, admitted market, period / scope
///                    identity, the card's own id) WITH the exact selection resolved
///                    when it was tapped (`Hold`). Every pass shows that original
///                    only while the origin is still offered — the mounted card
///                    draws its id exactly once, so an id that became ambiguous
///                    refuses — its admission still
///                    names the same market (and period / scope), the origin still
///                    resolves to that SAME selection and the catalogue accepts it.
///                    An old original can stay valid in All props after the owner
///                    moves the card to another market, and a served row naming
///                    several market ids keeps one catalogue identity across such a
///                    move — so the selection alone is never the test. A replacement
///                    is never adopted; the reader's story, outcome and scope choices
///                    are never touched.
///
/// Per-pass lookups (Design's performance correction): each `Pass` is built
/// ONCE per host pass, from that pass's own inputs, and holds the legs of every
/// admitted market, the served rows indexed by their identity side, and each
/// admitted half's legs with their builder cell ids. Deciding whether a card
/// offers Details, opening and revalidating all read those; none rebuilds the
/// market list or the served rows per candidate. Nothing is cached across
/// passes: a new pass rebuilds everything from its current inputs. Every
/// duplicate and ambiguous candidate stays in the lookups, so every refusal
/// still happens.
///
/// Readings, words and formatting are the originals adapter's own; nothing here
/// reads a price, a clock or a grade. Nothing fetches, subscribes or holds state;
/// building a callback, resolving and revalidating call nothing.
enum SoccerCardOriginalsAdapter10868 {
    typealias Details = OriginalMarketDetails9483
    typealias H4 = HockeyJourneyOriginalsAdapter10868
    typealias R = SoccerPropReadingAdapter10868
    typealias Card = SoccerEventPageCard10868

    /// One render pass: the values the page input and its originals were built
    /// from, that input and catalogue themselves, and the lookups built from
    /// them once. Immutable; the host builds a new one every pass.
    struct Pass {
        /// One served row as the hockey adapter reads it, with its identity.
        struct Served {
            let row: QuestionCatalog9483.Row
            let identity: Details.Identity
        }

        /// One leg of an admitted half, with the id the real cell builder gives it.
        struct HalfCell {
            let id: String
            let leg: R.Leg
        }

        let event: EventDetail
        /// `/game-markets`, already this event's own (the host's check).
        let markets: GameMarketsResponse?
        let admitted: R.Markets
        let host: R.Host
        /// The page input this pass mounts — which cards and ids are offered.
        let input: SoccerEventPageInput10868
        /// The page's own catalogue for this pass — the one its Details read.
        let catalogue: Details.Catalogue?

        // MARK: Built once, from the values above

        /// Which leaves this pass mounts (route-phase membership and explicit
        /// admissions already applied by the page input).
        let model: SoccerEventPageModel10868
        /// The owner's exact-score descriptor, only for this event.
        let descriptor: SoccerExactScoreAdapter10868.Descriptor?
        /// `R.legs` of every market the admission names (goals, both teams,
        /// first team, each half, each exact-score scope), one call per market.
        let legsByMarket: [Int: [R.Leg]]
        /// `H4.sources` of the body, one call per pass, each with
        /// `H4.identity(of:)`, indexed by the identity's opaque side. Every row is
        /// kept, duplicates included.
        let servedBySide: [String: [Served]]
        /// Parallel to `admitted.halves` (duplicates included): each half's legs
        /// with `SoccerHalvesAdapter10868.cell(...).id`.
        let halfCells: [[HalfCell]]

        init(event: EventDetail, markets: GameMarketsResponse?, admitted: R.Markets, host: R.Host,
             input: SoccerEventPageInput10868, catalogue: Details.Catalogue?) {
            self.event = event
            self.markets = markets
            self.admitted = admitted
            self.host = host
            self.input = input
            self.catalogue = catalogue
            model = SoccerEventPageModel10868(input)
            let descriptor = admitted.exactScore.flatMap { $0.admits(event) ? $0 : nil }
            self.descriptor = descriptor

            var marketIDs = Set(admitted.goals)
            if let both = admitted.both { marketIDs.insert(both) }
            if let first = admitted.first { marketIDs.insert(first) }
            marketIDs.formUnion(admitted.halves.map(\.marketID))
            marketIDs.formUnion(descriptor?.scopes.map(\.marketID) ?? [])
            var legsByMarket: [Int: [R.Leg]] = [:]
            for marketID in marketIDs { legsByMarket[marketID] = R.legs(marketID, in: markets) }
            self.legsByMarket = legsByMarket

            // No admitted market or no catalogue: nothing can resolve, so the
            // served rows are not read at all on this pass.
            var servedBySide: [String: [Served]] = [:]
            if let markets, catalogue != nil, !marketIDs.isEmpty {
                for source in H4.sources(markets) {
                    let identity = H4.identity(of: source)
                    servedBySide[identity.side, default: []].append(Served(row: source.row, identity: identity))
                }
            }
            self.servedBySide = servedBySide

            let phase = SoccerMatchPageAdapter10868.phase(event, now: host.now)
            halfCells = admitted.halves.map { half in
                (legsByMarket[half.marketID] ?? []).map { leg in
                    HalfCell(id: SoccerHalvesAdapter10868.cell(leg, half: half, event: event, phase: phase,
                                                               host: host).id,
                             leg: leg)
                }
            }
        }

        /// The legs of one admitted market; a market this pass does not admit has none.
        func legs(_ marketID: Int) -> [R.Leg] { legsByMarket[marketID] ?? [] }

        /// The identity of the ONE served row whose catalogue row value is the
        /// leg's own row and whose identity side is the leg's id; nil for none
        /// or more than one.
        func identity(of leg: R.Leg) -> Details.Identity? {
            let rows = (servedBySide[leg.id] ?? []).filter { $0.row == leg.row }
            return rows.count == 1 ? rows[0].identity : nil
        }

        /// The indexes of the admitted halves naming exactly this market and period.
        func halves(market: Int, period: String) -> [Int] {
            admitted.halves.indices.filter {
                admitted.halves[$0].marketID == market && admitted.halves[$0].periodID == period
            }
        }

        /// The descriptor's scopes with this exact id.
        func scopes(_ id: String) -> [SoccerExactScoreAdapter10868.Descriptor.Scope] {
            descriptor?.scopes.filter { $0.id == id } ?? []
        }
    }

    /// The typed card-origin admission context of one Details tap.
    enum Origin: Equatable {
        /// A goal milestone: the admitted full-match total market and the card's id.
        case goal(market: Int, id: String)
        /// A both-teams outcome: the admitted market and the card's exact ref.
        case both(market: Int, ref: BothTeamsOutcomeRef10868)
        /// A first-team row: the admitted market and the card's id.
        case first(market: Int, id: String)
        /// A half cell: the owner's admitted half — market and period identity —
        /// and the card's cell id.
        case half(market: Int, period: String, id: String)
        /// An exact-map original: the owner's scope id, that scope's market and
        /// period identity, and the map's original id.
        case exact(scope: String, market: Int, period: String?, original: String)

        var card: Card {
            switch self {
            case .goal: .goals
            case .both: .both
            case .first: .first
            case .half: .halves
            case .exact: .exact
            }
        }
    }

    /// The origin together with the exact selection it resolved to when tapped.
    struct Hold: Equatable {
        let origin: Origin
        let selection: Details.Selection
    }

    /// What a card's Details tap opened.
    enum Opened: Equatable {
        /// One exact origin and its selection, revalidated on every pass.
        case held(Hold)
        /// No exact original: the Details' own unavailable view, for good — a
        /// later pass never fills it with whatever the tap would resolve to then.
        case unresolved(Card)
    }

    // MARK: - Opening (at the tap)

    static func open(goal id: String, in pass: Pass) -> Opened {
        opened(.goals, pass.admitted.goals.map { Origin.goal(market: $0, id: id) }, in: pass)
    }

    static func open(both ref: BothTeamsOutcomeRef10868, in pass: Pass) -> Opened {
        opened(.both, pass.admitted.both.map { [Origin.both(market: $0, ref: ref)] } ?? [], in: pass)
    }

    static func open(first id: String, in pass: Pass) -> Opened {
        opened(.first, pass.admitted.first.map { [Origin.first(market: $0, id: id)] } ?? [], in: pass)
    }

    static func open(half id: String, in pass: Pass) -> Opened {
        opened(.halves, pass.admitted.halves.map { Origin.half(market: $0.marketID, period: $0.periodID, id: id) },
               in: pass)
    }

    static func open(exactScope scope: String, original: String, in pass: Pass) -> Opened {
        opened(.exact, pass.scopes(scope).map {
            Origin.exact(scope: scope, market: $0.marketID, period: $0.periodID, original: original)
        }, in: pass)
    }

    /// Exactly one candidate origin, with its exact selection, or unresolved.
    /// An identical candidate named twice counts once; two different origins
    /// (two admitted markets both serving the id) are ambiguous.
    static func opened(_ card: Card, _ candidates: [Origin], in pass: Pass) -> Opened {
        var holds: [Hold] = []
        for origin in candidates {
            guard isOffered(origin, in: pass), isAdmitted(origin, in: pass),
                  let selection = resolve(origin, in: pass) else { continue }
            let hold = Hold(origin: origin, selection: selection)
            if !holds.contains(hold) { holds.append(hold) }
        }
        return holds.count == 1 ? .held(holds[0]) : .unresolved(card)
    }

    // MARK: - Revalidation (every pass)

    /// The selection the Details may show on this pass: the held one, only while
    /// its origin is still offered and admitted, still resolves to that SAME
    /// selection, and the catalogue accepts it. Otherwise nil — the Details' own
    /// unavailable view. Never a replacement.
    static func shown(_ opened: Opened, in pass: Pass) -> Details.Selection? {
        guard case .held(let hold) = opened,
              isOffered(hold.origin, in: pass), isAdmitted(hold.origin, in: pass),
              resolve(hold.origin, in: pass) == hold.selection,
              Details.original(in: pass.catalogue, selection: hold.selection) != nil
        else { return nil }
        return hold.selection
    }

    /// The page's originals with the card Details' selection in place of the
    /// All props one, every other field unchanged; no recorded history is
    /// carried over from another selection.
    static func originals(_ originals: SoccerEventPageOriginals10868,
                          showing selection: Details.Selection?) -> SoccerEventPageOriginals10868 {
        SoccerEventPageOriginals10868(
            catalogue: originals.catalogue, selection: selection, recorded: nil, labels: originals.labels,
            heading: originals.heading, context: originals.context, emptyWords: originals.emptyWords,
            unavailableChoice: originals.unavailableChoice, tint: originals.tint)
    }

    // MARK: - The three checks

    /// The card is mounted on this pass and draws the origin's own id EXACTLY
    /// ONCE — the same exact-id rule the leaves use for a selection. An id the
    /// card draws twice (two milestones, outcomes, rows, cells or scope
    /// originals with one id, or two scopes with one id) is an ambiguous
    /// action: it is offered for neither, every row stays drawn, and a held
    /// origin with that id refuses on this pass.
    static func isOffered(_ origin: Origin, in pass: Pass) -> Bool {
        let model = pass.model
        switch origin {
        case .goal(_, let id):
            return once(model.goals?.milestones ?? []) { $0.id == id }
        case .both(_, let ref):
            guard let both = model.both else { return false }
            return both.eventID == ref.eventID && both.marketID == ref.marketID
                && once(both.outcomes) { $0.id == ref.outcomeID }
        case .first(_, let id):
            return once(model.first?.overview ?? []) { $0.id == id }
        case .half(_, _, let id):
            return once((model.halves?.series ?? []).flatMap(\.cells)) { $0.id == id }
        case .exact(let scope, _, _, let original):
            let scopes = (model.exact?.scopes ?? []).filter { $0.id == scope }
            return scopes.count == 1 && once(scopes[0].originals) { $0.id == original }
        }
    }

    /// Exactly one element matches.
    static func once<Element>(_ elements: [Element], _ matches: (Element) -> Bool) -> Bool {
        elements.filter(matches).count == 1
    }

    /// The owner's admission on this pass still names the origin's market — and
    /// its period or scope — exactly.
    static func isAdmitted(_ origin: Origin, in pass: Pass) -> Bool {
        let admitted = pass.admitted
        switch origin {
        case .goal(let market, _):
            return admitted.goals.contains(market)
        case .both(let market, let ref):
            return admitted.both == market && ref.marketID == String(market) && ref.eventID == String(pass.event.id)
        case .first(let market, _):
            return admitted.first == market
        case .half(let market, let period, _):
            return pass.halves(market: market, period: period).count == 1
        case .exact(let scope, let market, let period, _):
            let scopes = pass.scopes(scope)
            return scopes.count == 1 && scopes[0].marketID == market && scopes[0].periodID == period
        }
    }

    /// The origin's exact selection on this pass: its market's ONE leg carrying
    /// the card's id, that leg's ONE served row's identity, accepted by the
    /// page's catalogue.
    static func resolve(_ origin: Origin, in pass: Pass) -> Details.Selection? {
        let legs: [R.Leg]
        switch origin {
        case .goal(let market, let id), .first(let market, let id):
            legs = pass.legs(market).filter { $0.id == id }
        case .both(let market, let ref):
            legs = pass.legs(market).filter { $0.id == ref.outcomeID }
        case .half(let market, let period, let id):
            let indexes = pass.halves(market: market, period: period)
            guard indexes.count == 1 else { return nil }
            legs = pass.halfCells[indexes[0]].filter { $0.id == id }.map(\.leg)
        case .exact(_, let market, _, let original):
            legs = pass.legs(market).filter { $0.id == original }
        }
        guard legs.count == 1, let catalogue = pass.catalogue, let identity = pass.identity(of: legs[0]) else {
            return nil
        }
        let selection = Details.Selection(scope: catalogue.scope, identity: identity)
        return Details.original(in: catalogue, selection: selection) == nil ? nil : selection
    }

    // MARK: - Offering and callbacks

    /// A card offers Details only when at least one id it draws on this pass
    /// opens an exact original — no control that would only ever say
    /// "unavailable".
    static func offered(_ card: Card, in pass: Pass) -> Bool {
        let model = pass.model
        func resolves(_ opened: Opened) -> Bool {
            if case .held = opened { return true }
            return false
        }
        switch card {
        case .history:
            return false
        case .goals:
            return (model.goals?.milestones ?? []).contains { resolves(open(goal: $0.id, in: pass)) }
        case .both:
            guard let both = model.both else { return false }
            return both.outcomes.contains {
                resolves(open(both: BothTeamsOutcomeRef10868(eventID: both.eventID, marketID: both.marketID,
                                                              outcomeID: $0.id), in: pass))
            }
        case .first:
            return (model.first?.overview ?? []).contains { resolves(open(first: $0.id, in: pass)) }
        case .halves:
            return (model.halves?.series ?? []).contains { $0.cells.contains { resolves(open(half: $0.id, in: pass)) } }
        case .exact:
            return (model.exact?.scopes ?? []).contains { scope in
                scope.originals.contains { resolves(open(exactScope: scope.id, original: $0.id, in: pass)) }
            }
        }
    }

    /// One pass's Details callback for a card that takes one id: nil unless the
    /// card offers Details. A tap asks `hold` ONCE — nil in the compact stream,
    /// whose activation already asked — then hands the host what it opened.
    /// Building it calls nothing.
    static func details<ID>(_ card: Card, in pass: Pass, hold: (() -> Void)?,
                            open: @escaping (ID, Pass) -> Opened,
                            show: @escaping (Opened) -> Void) -> ((ID) -> Void)? {
        guard offered(card, in: pass) else { return nil }
        return { id in
            hold?()
            show(open(id, pass))
        }
    }

    static func goalDetails(in pass: Pass, hold: (() -> Void)?,
                            show: @escaping (Opened) -> Void) -> ((String) -> Void)? {
        details(.goals, in: pass, hold: hold, open: { Self.open(goal: $0, in: $1) }, show: show)
    }

    static func bothDetails(in pass: Pass, hold: (() -> Void)?,
                            show: @escaping (Opened) -> Void) -> ((BothTeamsOutcomeRef10868) -> Void)? {
        details(.both, in: pass, hold: hold, open: { Self.open(both: $0, in: $1) }, show: show)
    }

    static func firstDetails(in pass: Pass, hold: (() -> Void)?,
                             show: @escaping (Opened) -> Void) -> ((String) -> Void)? {
        details(.first, in: pass, hold: hold, open: { Self.open(first: $0, in: $1) }, show: show)
    }

    static func halfDetails(in pass: Pass, hold: (() -> Void)?,
                            show: @escaping (Opened) -> Void) -> ((String) -> Void)? {
        details(.halves, in: pass, hold: hold, open: { Self.open(half: $0, in: $1) }, show: show)
    }

    /// The same for the exact-score map's (scope id, original id).
    static func exactDetails(in pass: Pass, hold: (() -> Void)?,
                             show: @escaping (Opened) -> Void) -> ((String, String) -> Void)? {
        guard offered(.exact, in: pass) else { return nil }
        return { scope, original in
            hold?()
            show(Self.open(exactScope: scope, original: original, in: pass))
        }
    }
}
