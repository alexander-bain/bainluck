import Foundation

// #6667 / #6444 — a Discover fight card opens THAT card.
//
// The server half already exists: `GET /api/event/{key}` is what the web's
// `/event/<domain>/<slug>` page reads, and it answers JSON. Measured
// 2026-09-17 14:35Z against production for `event:ufc:26sep19` — 200, 3,995
// bytes, 12 fights each with two priced fighters. This file is the phone's
// decode of that response and the rules for turning it into rows.
//
// FOUNDATION ONLY, on purpose: no SwiftUI, no `APIClient`. Everything a test
// needs to pin — key handling, decode, ordering, the settled rule, where a
// bout leads — is here, so none of it has to be paraphrased by a test that
// cannot reach a `private func` on a `View`.

// MARK: - The key

/// An event-concept key: `event:<domain>:<slug>` (e.g. `event:ufc:26sep19`).
///
/// Mirrors `frontend/lib/eventKey.ts` `parseEventKey` / backend
/// `parse_event_key` — with ONE deliberate difference: web treats a bare slug as
/// golf (its slice-1 parity domain). The phone does not guess. A key this app
/// cannot read has no fight card to open, and the caller falls back to the
/// category rather than asking the server for something it invented.
nonisolated struct ConceptKey: Equatable, Hashable, Sendable {
    let domain: String
    let slug: String

    /// The canonical spelling the API keys on.
    var canonical: String { "event:\(domain):\(slug)" }

    init?(_ raw: String?) {
        let parts = (raw ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .split(separator: ":", omittingEmptySubsequences: false)
            .map(String.init)
        let domain: String
        let slug: String
        if parts.count >= 3, parts[0] == "event" {
            domain = parts[1]
            slug = parts[2...].joined(separator: ":")
        } else if parts.count == 2 {
            domain = parts[0]
            slug = parts[1]
        } else {
            return nil
        }
        guard !domain.isEmpty, !slug.isEmpty else { return nil }
        self.domain = domain.lowercased()
        self.slug = slug
    }

    /// From the web's colon-free path: `/event/ufc/26sep19`.
    init?(domain: String, slug: String) {
        self.init("event:\(domain):\(slug)")
    }

    /// The request path.
    ///
    /// The colons are percent-encoded, which is what web sends
    /// (`encodeURIComponent`). MEASURED 2026-09-17: the raw-colon and `%3A`
    /// spellings return byte-identical bodies (sha256 `b4393676…`), so this is
    /// a choice, not a requirement — made because a slug is server-authored
    /// text and the encoder is what stops a `/`, `?` or `#` in one from
    /// becoming a different URL.
    var apiPath: String {
        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~")
        let encoded = canonical.addingPercentEncoding(withAllowedCharacters: allowed) ?? canonical
        return "/api/event/\(encoded)"
    }
}

// MARK: - The response

/// `GET /api/event/{key}`, reduced to what a fight card draws.
///
/// Everything beyond `event.key` is optional. The envelope is shared by nine
/// adapters (golf, tennis, F1, awards, …) and is loosely typed on web for the
/// same reason; a field this screen does not need must never be the reason a
/// card that answered 200 renders as an error.
nonisolated struct EventConceptResponse: Decodable, Sendable {
    let event: EventConceptEvent
    let primary: EventConceptPrimary?
    let children: [EventConceptChild]

    private enum CodingKeys: String, CodingKey { case event, primary, children }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        event = try c.decode(EventConceptEvent.self, forKey: .event)
        primary = try? c.decodeIfPresent(EventConceptPrimary.self, forKey: .primary)
        // One malformed child must not blank eleven good ones (gotcha #42's
        // rule, on the client): decode each on its own and keep what decodes.
        let lossy = (try? c.decodeIfPresent([LossyChild].self, forKey: .children)) ?? []
        children = lossy.compactMap(\.value)
    }

    private struct LossyChild: Decodable {
        let value: EventConceptChild?
        init(from decoder: Decoder) throws {
            value = try? EventConceptChild(from: decoder)
        }
    }
}

nonisolated struct EventConceptEvent: Decodable, Sendable {
    let key: String
    let domain: String?
    let name: String?
    /// `upcoming` | `live` | `settled` — ASSIGNED by the server off the card's
    /// authoritative start (`combat_status`), never inferred here.
    let status: String?
    let startDate: String?
    let isMajor: Bool?
}

nonisolated struct EventConceptPrimary: Decodable, Sendable {
    let kind: String?
    /// The main event's market id on a venue-listed card; `null` on an
    /// events-only card (no market exists yet).
    let evolutionMarketId: Int?
}

nonisolated struct EventConceptChild: Decodable, Sendable {
    /// ⚠️ TWO ID SPACES IN ONE FIELD. On a venue-listed card this is a
    /// `FuturesMarket` id. On an events-only card (`source == "events"`) the
    /// server puts the **Event PK** here "purely as a stable render key"
    /// (`event_combat._build_events_envelope`). Read it through
    /// `ConceptCardRouting.boutTarget`, never directly.
    let marketId: Int?
    let marketName: String?
    let source: String?
    /// `fight` | `prop` on combat cards.
    let kind: String?
    /// ⚠️ NOT "this bout was fought". The server ORs an ASSIGNED card state with
    /// a PRICE inference (`event_combat.fight_child_settled` →
    /// `settledness.price_converged`, ≥0.97 or ≤0.03), so an UPCOMING card's
    /// heavy favourite arrives `settled: true` days before the walkout.
    /// EXECUTED against the repo's own producer 2026-09-17:
    /// `fight_child_settled(0.98, card_settled=False) == True`.
    /// Good enough for "stop showing this as live" (what web does with it);
    /// never evidence that anyone won.
    let settled: Bool?
    let probability: Double?
    let outcomes: [EventConceptOutcome]?
    /// The graded winner's NAME, when the server has one. Declared by
    /// `frontend/lib/types.ts EventConceptChild.graded_winner` (#249 Item 4c)
    /// and emitted today by cycling/golf — NOT by the combat adapter, so it is
    /// `nil` on every fight card until that gap closes. Decoded now so closing
    /// it needs no client change.
    let gradedWinner: String?
}

nonisolated struct EventConceptOutcome: Decodable, Equatable, Sendable {
    let name: String
    let probability: Double?
    /// The AUTHORITATIVE grade — `FuturesOutcome.is_winner` (gotcha #21), the
    /// signal `settledness.market_assigned_settled` calls authoritative.
    /// Declared by `frontend/lib/types.ts` as `outcomes[].won` and emitted by
    /// the awards / cycling / election / f1 / soccer adapters; the combat
    /// adapter is the sole holdout (`event_combat._fight_outcomes` serialises
    /// `{name, probability}` and nothing else — verified against the production
    /// capture of `event:ufc:26sep19`). `nil` on fight cards today.
    let won: Bool?

    /// Spelled out (rather than left to the memberwise init) so that `won`
    /// carries a default: every existing caller that names an outcome by
    /// `{name, probability}` keeps compiling, and a caller that means "graded"
    /// has to say so.
    init(name: String, probability: Double?, won: Bool? = nil) {
        self.name = name
        self.probability = probability
        self.won = won
    }
}

// MARK: - What the screen draws

nonisolated struct ConceptBoutRow: Equatable, Identifiable, Sendable {
    /// Why a bout can be opened, or not. The id means different things on the
    /// two kinds of card, so the kind travels with it.
    enum Target: Equatable, Sendable {
        case market(id: Int)
        case event(id: Int)
        case none
    }

    let id: String
    let title: String
    /// Both fighters, favourite first. A missing price stays `nil` — it is
    /// drawn as the app's absent-price mark, never as 0% and never as 50%.
    let fighters: [EventConceptOutcome]
    let isSettled: Bool
    /// The fighter a settled bout names, or `nil` when the payload does not
    /// say. See `ConceptCardPresentation.settledWinner`.
    let winner: String?
    let isMainEvent: Bool
    let target: Target
}

nonisolated struct ConceptCardPresentation: Equatable, Sendable {
    let key: String
    let name: String?
    let domain: String?
    let status: String?
    let startDate: String?
    let isMajor: Bool
    /// Main event first.
    let bouts: [ConceptBoutRow]

    init(response: EventConceptResponse) {
        let e = response.event
        key = e.key
        name = e.name?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
        domain = e.domain
        status = e.status
        startDate = e.startDate
        isMajor = e.isMajor == true

        let mainId = response.primary?.evolutionMarketId

        // FIGHTS ONLY in this cut. Props ride the same `children` array
        // (`kind == "prop"`), and the one on the measured card was a
        // no-trade 50/50 — not a number worth a row. Untagged children are
        // kept: `kind` is a combat-adapter nicety and its absence must not
        // empty a card.
        let fights = response.children.filter { ($0.kind ?? "fight") == "fight" }

        // The server sends bouts ASCENDING by bout order with the main event
        // LAST (`fights[-1]` / `main_bout_of`). A phone list reads top-down, so
        // the card's headline fight goes first. Reversal keeps the server's
        // total order rather than re-sorting on a time that ties across a card.
        bouts = fights.reversed().enumerated().map { index, child in
            let fighters = (child.outcomes ?? []).sorted {
                ($0.probability ?? -1) > ($1.probability ?? -1)
            }
            let settled = Self.boutIsDecided(childSettled: child.settled, cardStatus: e.status)
            let isMain: Bool
            if let mainId, let id = child.marketId {
                isMain = id == mainId
            } else {
                // Events-only card: no market id names the main event, and the
                // server's order does — it is last on the wire, first here.
                isMain = mainId == nil && index == 0
            }
            return ConceptBoutRow(
                id: child.marketId.map(String.init) ?? "bout-\(index)",
                title: child.marketName ?? fighters.map(\.name).joined(separator: " vs "),
                fighters: Array(fighters.prefix(2)),
                isSettled: settled,
                winner: Self.settledWinner(child, fighters),
                isMainEvent: isMain,
                target: ConceptCardRouting.boutTarget(for: child)
            )
        }
    }

    /// Whether a bout may be DRAWN as decided — "Final", no price.
    ///
    /// This is the same defect as `settledWinner` one level up, and it survived
    /// that repair. Removing the winner floor stopped the phone naming a fighter
    /// off a price; it did NOT stop the phone declaring the FIGHT OVER off a
    /// price, because the row's whole settled/live branch keys on `child.settled`
    /// — and `child.settled` is `price_converged(lead) OR card_settled`
    /// (`backend/app/utils/event_combat.py:1086`, read 2026-09-17; its own
    /// docstring: "a card in play has `card_settled` False and the price test
    /// decides exactly as it always did").
    ///
    /// So an UPCOMING card whose favourite is quoted 0.98 arrived `settled: true`,
    /// and `ConceptCardView` drew **"Final"** over two bare names with **no
    /// prices at all** — since no grade exists on a fight card, not even a "Won".
    /// A bout nobody had walked out to, reported as over, with its live market
    /// erased. That is a worse reading than the winner floor gave.
    ///
    /// The tell was sitting in this ship's own test suite: the adversarial case
    /// asserts `bout.fighters.first?.probability == 0.98` with the reason *"and
    /// the price is still shown"*. It passed — on the MODEL. The view reads
    /// `isSettled` and showed nothing. Neither upstream author compiled Swift, so
    /// no one had run the screen that sentence describes.
    ///
    /// The rule: the price term may only decide a bout on a card whose ASSIGNED
    /// status says the card is not still in the future. `event.status` is the
    /// authoritative term — the server sets it off `combat_status`, the card's
    /// real commence time, never off a price — so on `upcoming` the assigned half
    /// of that OR is false by construction and a `true` here can only be the
    /// price. No fight on a card that has not started has been fought.
    ///
    /// Deliberately narrow: `live` and `settled` keep today's behaviour, so an
    /// early bout that genuinely finishes while the card is in play still reads
    /// Final, and an unknown status stays permissive rather than silently
    /// un-settling a real result.
    static func boutIsDecided(childSettled: Bool?, cardStatus: String?) -> Bool {
        guard childSettled == true else { return false }
        return cardStatus?.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased() != "upcoming"
    }

    /// Who a settled bout names — or nobody.
    ///
    /// **A PRICE IS NOT A RESULT.** The previous revision of this function named
    /// the favourite whenever `child.settled` was true and the lead price was
    /// ≥ 0.97. Both halves of that gate fail:
    ///
    /// 1. `child.settled` does not mean the bout happened. It is
    ///    `assigned card state OR price_converged(lead)` — EXECUTED against the
    ///    repo's own producer 2026-09-17:
    ///    `fight_child_settled(0.98, card_settled=False) == True`. So a −3000
    ///    favourite on a card three days out satisfied both halves and the row
    ///    printed "Final · Won" for a fight nobody had walked out to.
    /// 2. On a card that HAS happened, the price still is not the result. The
    ///    producer's own docstring measures it: `event:ufc:26aug08`, card status
    ///    `settled`, rendered "Johns vs Rosas" at 0.54/0.44 — these are the last
    ///    prices seen, not a grade. A favourite who is upset keeps their 0.97 and
    ///    would have been crowned by the old rule on exactly the bouts a reader
    ///    most wants the truth about.
    ///
    /// So the phone reads only signals the SERVER has graded — `graded_winner`,
    /// or an outcome flagged `won` (`FuturesOutcome.is_winner`, gotcha #21; the
    /// authoritative term in `settledness.market_assigned_settled`). This is the
    /// web's own order of preference for a decided child
    /// (`frontend/lib/eventConceptDisplay.ts`, L2-175 Item 2b).
    ///
    /// The combat adapter emits NEITHER field today, so on every fight card this
    /// returns `nil` and no winner is claimed — which is the correct answer until
    /// #6667-GAP-A lands. It is not dead code: five sibling adapters already emit
    /// `won`, and when combat joins them this lights up with no client change.
    ///
    /// Deliberately NOT ported: the server's display-only price crown
    /// (`_WON_PRICE_THRESHOLD = 0.97` in awards/cycling/election/f1/soccer). That
    /// crown is gated on the ASSIGNED `event_status == "settled"`, it lives on the
    /// server where one rule serves every client, and re-deriving it here from a
    /// price-contaminated per-child flag is how defect 1 above happened.
    static func settledWinner(
        _ child: EventConceptChild,
        _ fightersFavouriteFirst: [EventConceptOutcome]
    ) -> String? {
        if let graded = child.gradedWinner?
            .trimmingCharacters(in: .whitespacesAndNewlines), !graded.isEmpty {
            return graded
        }
        return (child.outcomes ?? fightersFavouriteFirst).first { $0.won == true }?.name
    }
}

// MARK: - Where things lead

nonisolated enum ConceptCardRouting {
    /// Domains whose concept opens the native fight-card screen.
    ///
    /// ONE, deliberately. The envelope is generic but this screen is not: it
    /// draws two-fighter bouts. Boxing is the same adapter and very likely a
    /// one-word addition — after someone has looked at a real boxing card on
    /// it. Every other domain keeps today's destination.
    static let fightCardDomains: Set<String> = ["ufc"]

    /// Where a Discover concept card leads.
    ///
    /// The key is the FEED's own (`data.key`), never derived on the client —
    /// the feed lister is gated against rumoured cards (#4485) and a key the
    /// feed did not serve is a key nobody vouched for (#6733).
    static func destination(key: String, name: String, domain: String?) -> Route? {
        if let parsed = ConceptKey(key), fightCardDomains.contains(parsed.domain) {
            return .conceptCard(key: parsed.canonical, name: name)
        }
        // Unchanged from before #6667: the closest existing surface.
        guard let domain = domain?.lowercased(), !domain.isEmpty else { return nil }
        if domain == "golf" { return .golfCategory }
        return .sportCategory(key: domain, name: properTitleCase(domain))
    }

    /// The provenance string the events-only envelope stamps on its children
    /// (`event_combat._build_events_envelope`), where `market_id` carries an
    /// **Event PK**, not a futures id.
    static let eventsOnlySource = "events"

    /// Sources whose `market_id` is a `FuturesMarket` id.
    ///
    /// A CLOSED SET, and that is the correction. `FuturesMarket.source` is
    /// `nullable=False` (`models.py`), so on the venue path this field is always
    /// one of these strings; the events-only path always says `events`. Those two
    /// producers are the only ones in the combat adapter (verified: the only
    /// `"market_id"` emitters in `event_combat.py` are lines 1317 and 1474).
    /// Between them they are exhaustive — so ANY other value, including `nil`, is
    /// a shape neither producer emits, i.e. a third writer this client has never
    /// seen. Opening it as a futures id would be guessing at an id space.
    static let futuresSources: Set<String> = [
        "kalshi", "polymarket", "odds_api", "datagolf",
    ]

    /// Where one bout leads — or nowhere.
    ///
    /// ⚠️ `market_id` holds TWO id spaces and `source` is the only discriminator.
    /// The rule is an allowlist in BOTH directions and refuses on anything else,
    /// because the failure being avoided is not a dead tap — it is opening the
    /// WRONG OBJECT. Event PK 60306288 and FuturesMarket 60306288 can both exist;
    /// nothing about the number says which one you are holding.
    ///
    /// The previous revision defaulted every non-`"events"` source — and `nil` —
    /// to `.market(id:)`. That is the shape of a gate keyed on a provenance
    /// string: it is correct for today's two writers and goes silently wrong the
    /// day a third is added, which is the one day nobody re-reads this function.
    /// Refusing costs a bout row its tap; guessing costs a reader a stranger's
    /// page (#6667's own defect, one level down).
    static func boutTarget(for child: EventConceptChild) -> ConceptBoutRow.Target {
        guard let id = child.marketId, let source = child.source else { return .none }
        if source == eventsOnlySource { return .event(id: id) }
        if futuresSources.contains(source) { return .market(id: id) }
        return .none
    }

    static func route(for target: ConceptBoutRow.Target) -> Route? {
        switch target {
        case .market(let id): return .futuresDetail(id: id)
        case .event(let id): return .eventDetail(id: id)
        case .none: return nil
        }
    }
}

// MARK: - What a failed load means

/// The three things a failed load can mean for this screen. Pure, so the split
/// is executed by a test rather than described by one.
nonisolated enum ConceptCardFailure: Equatable, Sendable {
    /// HTTP 404 — the server refuses this key. Not retryable, and it replaces
    /// even a loaded screen: prices for a card the server no longer stands
    /// behind are what #6733 removed from the web.
    case gone
    /// A refresh failed over a good screen. Keep the screen.
    case keepShowing
    /// Nothing on screen and a failure that might not repeat. Offer Retry.
    case retryable

    static func classify(httpStatus: Int?, hasLoadedScreen: Bool) -> ConceptCardFailure {
        if httpStatus == 404 { return .gone }
        return hasLoadedScreen ? .keepShowing : .retryable
    }
}

private extension String {
    nonisolated var nilIfEmpty: String? { isEmpty ? nil : self }
}
