import SwiftUI

/// #10868 — THE GOLF TOURNAMENT SCREEN'S PRODUCTION ADAPTER, PART SIX: THE
/// ORIGINALS BEHIND THE FINISH AND CONTENDERS CARDS, AND THEIR DETAILS.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: golf finish and contender cards open the
/// exact original's Details — that market's own before-start reading, its own
/// recorded reading and its own contract result, each with its own clock and
/// source — and close back to the same reader.
///
/// It decides nothing the golf screen does not already decide:
///   - membership  the Winner market's outcomes in served order, then each finish
///                 market the host holds (Top 5, Top 10, Top 20, Make the Cut),
///                 each market once (`FieldEventOriginalsAdapter10868.held` — for
///                 membership only; that adapter's reading rule is not used here,
///                 so the golf screen keeps ONE currentness rule).
///   - identity    `(GolfFieldPageAdapter10868.sourceKey, market id, outcome id)`:
///                 the served ids, the same parts the finish card's selection ids
///                 (`GolfFieldFinishAdapter10868.selection`) and the chooser's refs
///                 (`GolfFieldChooserAdapter10868.ref`) are made of. A card's id is
///                 matched by EXACT EQUALITY against the keys built here — never
///                 parsed — and the match goes through
///                 `OriginalMarketDetails9483.original(in:selection:)`, which refuses
///                 a blank, withdrawn or duplicated identity.
///   - phase       the page's one phase, in the catalogue scope: a selection held
///                 from another phase resolves to nothing, and the Details draw
///                 their own unavailable view — never a neighbour.
///   - readings    the finish card's own authorities, per market, on the Winner
///                 market's phase, listed start and clock:
///                   before    `Field.before` alone, labelled "Before start";
///                   recorded  `Field.before` beside `Field.later` (the Details'
///                             own "Recorded chance");
///                   final     `Field.before` beside the market's own grade through
///                             `FuturesDetailRowValue.of` — Won / Lost, "Result
///                             unknown", or no grade (the Details' own "Result
///                             unavailable"; unknown is never a loss).
///                 Never the untimed opening, never a settled 0/1, never a reading
///                 moved across the listed start, never a substitute for a missing
///                 one.
///   - figures     `GolfFieldHistoryAdapter10868.figure` / `.provenance`: the printed
///                 value with its own clock ("Recorded …" / "Updated …") and source
///                 name. No Details rail: placement is nil for every golf original,
///                 so a tiny chance never sits invisibly on a fixed 0–100% scale
///                 (Design D1).
///   - source      `SourceLabels.attribution` for the served contributors, else
///                 `SourceLabels.label` — the chart notes' own two calls. A DataGolf
///                 body reads "Probabilities from the DataGolf model" (Design D2).
///                 No rule text is served: "Rules unavailable". The served market
///                 and outcome ids are About rows.
///
/// Finish Details (Design D3): offered when at least one CURRENT finish slot
/// resolves to exactly one original, so one absent finish never closes the
/// others. A tap resolves its id against the current slots of the same pass:
/// a slot with exactly one original opens it; a current slot whose original is
/// not held opens a named explanation in the slot's own finish name ("Top 5
/// original not supplied") with no identity, selection or market built for it;
/// an id naming no current slot opens the Details' unavailable view.
///
/// OWED, NOT PAID: all-props browsing (Design D4); history Details; the status
/// and movement producers; the production binding named in parts one and three.
///
/// Nothing here fetches, subscribes, schedules, ranks or holds state.
enum GolfFieldOriginalsAdapter10868 {
    typealias Details = OriginalMarketDetails9483
    typealias History = GolfFieldHistoryAdapter10868
    typealias Field = GolfFieldHistoryAdapter10868.Field
    typealias Host = GolfFieldPageAdapter10868.Host

    enum Words {
        static let rulesUnavailable = FieldEventOriginalsAdapter10868.Words.rulesUnavailable
        static let marketID = FieldEventOriginalsAdapter10868.Words.marketID
        static let outcomeID = FieldEventOriginalsAdapter10868.Words.outcomeID
        static let resultUnknown = GolfFieldFinishAdapter10868.Words.resultUnknown
        /// Under a named finish whose original is not held: the Details' own words.
        static let notSuppliedNote = LadderOriginalProbabilityDetails9483.unavailableNote

        /// "Top 5 original not supplied" — the slot's own finish name, verbatim.
        static func notSupplied(_ finish: String) -> String { "\(finish) original not supplied" }
    }

    /// The exact keys the page's cards hand back for one held original.
    struct Key: Equatable {
        let identity: Details.Identity
        /// The finish card's selection id for this original.
        let finishID: String
        /// The contenders card's ref; Winner originals only.
        let ref: FieldChooserOriginalRef10868?
    }

    /// One pass's originals: the catalogue, and each original's keys in the same order.
    struct Originals: Equatable {
        let catalogue: Details.Catalogue
        let keys: [Key]
    }

    /// What a Details tap opens, decided when it is tapped.
    enum Destination: Equatable {
        /// The exact original, inside the catalogue scope it was chosen in.
        case original(Details.Selection)
        /// A current finish slot whose original the host does not hold: the slot's
        /// own finish name, the slot id it was tapped on and the scope it was
        /// current in. No identity, selection or market stands behind it.
        case notSupplied(finish: String, slot: String, scope: String)
        /// An id that names no current slot or held original.
        case unavailable
    }

    /// What the Details layer draws on one pass.
    enum Shown: Equatable {
        /// The held selection, handed to the Details unchanged: a selection from
        /// another phase, or a withdrawn original, draws their unavailable view.
        case original(Details.Selection)
        /// The named explanation's title.
        case notSupplied(String)
        /// The Details' own unavailable view.
        case unavailable
    }

    // MARK: - The catalogue

    /// One catalogue per Winner market and phase.
    static func scope(_ winner: Field) -> String {
        "golf:\(winner.market.id):\(winner.phase):originals"
    }

    /// Every held original once, in served order, with the keys the cards use.
    static func originals(_ winner: Field, legs: GolfFieldFinishAdapter10868.Legs, host: Host) -> Originals {
        var originals: [Details.Original] = []
        var keys: [Key] = []
        for field in fields(winner, legs: legs) {
            let isWinner = field.market.id == winner.market.id
            for outcome in field.market.outcomes {
                originals.append(original(outcome, field: field, host: host))
                keys.append(Key(
                    identity: identity(outcome, in: field.market),
                    finishID: GolfFieldFinishAdapter10868.selection(field.market, outcomeID: outcome.id),
                    ref: isWinner ? GolfFieldChooserAdapter10868.ref(outcome.id, field: field) : nil))
            }
        }
        return Originals(catalogue: Details.Catalogue(scope: scope(winner), originals: originals), keys: keys)
    }

    /// The Winner field, then each held finish market once, read as its own field
    /// on the Winner market's phase, listed start and clock — the finish card's
    /// own construction (`GolfFieldFinishAdapter10868.slot(_:leg:…)`).
    static func fields(_ winner: Field, legs: GolfFieldFinishAdapter10868.Legs) -> [Field] {
        let held = [legs.top5, legs.top10, legs.top20, legs.makeCut].compactMap { $0 }
        let members = FieldEventOriginalsAdapter10868.held(field: winner.market, markets: held.map(\.market))
        return members.compactMap { market -> Field? in
            if market.id == winner.market.id { return winner }
            guard let leg = held.first(where: { $0.market.id == market.id }) else { return nil }
            return Field(market: leg.market, history: leg.history, phase: winner.phase,
                         listedStart: winner.listedStart, now: winner.now)
        }
    }

    static func identity(_ outcome: FuturesOutcome, in market: FuturesMarketDetail) -> Details.Identity {
        Details.Identity(source: GolfFieldPageAdapter10868.sourceKey(market), market: String(market.id),
                         side: String(outcome.id))
    }

    // MARK: - One original

    static func original(_ outcome: FuturesOutcome, field: Field, host: Host) -> Details.Original {
        let market = field.market
        let mode: Details.Mode
        var later: Details.Reading?
        var grade: Details.Grade?
        switch field.phase {
        case .before:
            mode = .pregame
        case .recorded:
            mode = .comparison(.recorded)
            later = laterReading(field, outcomeID: outcome.id, host: host)
        case .final:
            mode = .result
            grade = self.grade(outcome, in: market)
        }
        return Details.Original(
            identity: identity(outcome, in: market), title: market.name, outcome: outcome.name,
            mode: mode, pregame: beforeReading(field, outcomeID: outcome.id, host: host),
            later: later, grade: grade, about: about(outcome, in: market),
            beforeLabel: History.Words.beforeLabel)
    }

    /// `Field.before`, or the finish card's own words for its absence.
    static func beforeReading(_ field: Field, outcomeID: Int, host: Host) -> Details.Reading {
        guard let reading = field.before(outcomeID) else {
            return .missing(field.listedStart == nil ? History.Words.noStartWords : History.Words.notBeforeStart)
        }
        return value(reading, market: field.market, host: host)
    }

    /// `Field.later` (recorded phase only), or the chooser's own words for its absence.
    static func laterReading(_ field: Field, outcomeID: Int, host: Host) -> Details.Reading {
        guard let reading = field.later(outcomeID) else {
            return .missing(field.listedStart == nil ? History.Words.notRecorded : History.Words.notSinceStart)
        }
        return value(reading, market: field.market, host: host)
    }

    /// The printed figure with its own clock and source; no rail mark (Design D1).
    static func value(_ reading: History.Reading, market: FuturesMarketDetail, host: Host) -> Details.Reading {
        .value(History.figure(reading), placement: nil,
               provenance: History.provenance(reading, market: market, host: host))
    }

    /// The Market Details rule's grade for this row; nil when it grades nothing
    /// (the Details then print "Result unavailable", never "Lost").
    static func grade(_ outcome: FuturesOutcome, in market: FuturesMarketDetail) -> Details.Grade? {
        switch FuturesDetailRowValue.of(outcome, marketStatus: market.status, marketSource: market.source) {
        case .verdict(let verdict): return Details.Grade(words: verdict.label, provenance: nil)
        case .resultUnknown: return Details.Grade(words: Words.resultUnknown, provenance: nil)
        case .price, .none: return nil
        }
    }

    static func about(_ outcome: FuturesOutcome, in market: FuturesMarketDetail) -> Details.About {
        Details.About(
            source: source(market),
            rules: .unavailable(Words.rulesUnavailable),
            provenance: [Details.Row(label: Words.marketID, value: String(market.id)),
                         Details.Row(label: Words.outcomeID, value: String(outcome.id))],
            historicalQuote: nil)
    }

    /// The chart notes' own two calls (`GolfFieldHistoryAdapter10868.notes`).
    static func source(_ market: FuturesMarketDetail) -> String? {
        SourceLabels.attribution(for: market.bookmakers ?? []) ?? GolfFieldPageAdapter10868.sourceName(market)
    }

    // MARK: - Resolution (exact equality, never parsed)

    /// The selection a finish card id names: exactly one held original carries
    /// that id, and the Details resolve it.
    static func selection(finishID id: String, in originals: Originals) -> Details.Selection? {
        selection(originals, matching: originals.keys.filter { $0.finishID == id })
    }

    /// The selection a contenders ref names: exactly one Winner original carries
    /// that exact ref, scope included, and the Details resolve it.
    static func selection(for ref: FieldChooserOriginalRef10868, in originals: Originals) -> Details.Selection? {
        selection(originals, matching: originals.keys.filter { $0.ref == ref })
    }

    private static func selection(_ originals: Originals, matching keys: [Key]) -> Details.Selection? {
        guard keys.count == 1 else { return nil }
        let selection = Details.Selection(scope: originals.catalogue.scope, identity: keys[0].identity)
        return Details.original(in: originals.catalogue, selection: selection) == nil ? nil : selection
    }

    // MARK: - Routing

    /// Design D3: at least one current finish slot resolves to exactly one original.
    static func finishDetailsOffered(_ finish: GolfFinishExpectationInput10868?, originals: Originals) -> Bool {
        (finish?.slots ?? []).contains { selection(finishID: $0.selection, in: originals) != nil }
    }

    /// The contenders card's selected original resolves to exactly one original.
    static func contendersDetailsOffered(_ contenders: FieldOutlookInput10868?, originals: Originals) -> Bool {
        guard let contenders, let ref = FieldOutlookModel10868(contenders).detailsRef(canOpen: true) else {
            return false
        }
        return selection(for: ref, in: originals) != nil
    }

    /// Design D3: a tapped finish id against the current finish slots of the same
    /// pass, by exact equality.
    static func destination(finishID id: String, finish: GolfFinishExpectationInput10868?,
                            originals: Originals) -> Destination {
        let slots = (finish?.slots ?? []).filter { $0.selection == id }
        guard slots.count == 1 else { return .unavailable }
        if let selection = selection(finishID: id, in: originals) { return .original(selection) }
        return .notSupplied(finish: slots[0].name, slot: id, scope: originals.catalogue.scope)
    }

    /// A tapped contenders ref: its exact original, or the unavailable view.
    static func destination(ref: FieldChooserOriginalRef10868, originals: Originals) -> Destination {
        guard let selection = selection(for: ref, in: originals) else { return .unavailable }
        return .original(selection)
    }

    /// What a held destination draws on this pass. A named explanation stands
    /// only while its slot is still current and still not held, in the same
    /// phase; otherwise it is withdrawn to the unavailable view — never upgraded
    /// to an original and never moved to a neighbour.
    static func shown(_ destination: Destination, finish: GolfFinishExpectationInput10868?,
                      originals: Originals) -> Shown {
        switch destination {
        case .original(let selection):
            return .original(selection)
        case .notSupplied(_, let slot, let scope):
            guard scope == originals.catalogue.scope,
                  case .notSupplied(let name, _, _) = self.destination(finishID: slot, finish: finish,
                                                                       originals: originals) else {
                return .unavailable
            }
            return .notSupplied(Words.notSupplied(name))
        case .unavailable:
            return .unavailable
        }
    }
}
