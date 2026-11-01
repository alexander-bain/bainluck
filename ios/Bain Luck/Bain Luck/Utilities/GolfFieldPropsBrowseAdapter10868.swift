import SwiftUI

/// #10868 — THE GOLF TOURNAMENT SCREEN'S PRODUCTION ADAPTER: "EXPLORE PROPS",
/// THE SUPPLIED ORIGINALS IN COMPACT TYPED GROUPS.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: a fan explores the golf page's supplied
/// props in compact typed groups — Win, Top 5, Top 10, Top 20, Make cut, one
/// group at a time — opens any original's exact Details, and returns with the
/// golfer, the chart and every reader choice intact. This pays the all-props
/// browsing route item (Design D4, `GolfFieldOriginalsAdapter10868`'s OWED list).
///
/// It decides nothing the golf screen does not already decide:
///   - membership  the markets `GolfFieldOriginalsAdapter10868.fields` already
///                 holds — the Winner market, then each finish market the host
///                 holds, each market once — so a group is exactly one held
///                 market and every held original sits in exactly one group.
///   - role        TYPED, never read from a name: the page's Winner market is
///                 Win; any other market takes the first `Legs` slot (Top 5,
///                 Top 10, Top 20, Make cut) that holds that market id — the same
///                 order `fields` resolves it in. A market held under two slots is
///                 one group under its first role; the second role has no market
///                 of its own, so it gets no group and no original is lost or
///                 repeated. Never `market.name`, `external_id`, `category` or a
///                 ticker. The heading is `GolfFieldFinishAdapter10868.Kind.name`.
///   - originals   a slice of the ONE `Originals` value the host's render path
///                 built — the same value its Details resolve against — in the
///                 catalogue's own scope, by EXACT EQUALITY on the identity's own
///                 `source` and `market` components. Every supplied row stays:
///                 unpriced, zero, malformed, unattributed and duplicated rows
///                 alike. The existing exact-identity refusal
///                 (`OriginalMarketDetails9483.original(in:selection:)`) decides
///                 which cards open; nothing here filters, sorts, caps, ranks,
///                 searches, formats or grades.
///   - card label  the served outcome name, verbatim, for an identity carried by
///                 exactly one row; a duplicated identity gets no label, so both
///                 rows show the market's own title and stay unavailable — one
///                 golfer is never printed under another golfer's row.
///   - held group  `Key`: the catalogue scope, the market's exact source and id
///                 (the identity's own components) and the typed role. It
///                 resolves only to the one group carrying the same key. Another
///                 phase (scope), a market replaced under the same role, a
///                 changed source or a withdrawn market resolves to nothing — the
///                 host draws the Details' own unavailable view, never another
///                 group.
///
/// Readings are each original's own Details content, with its own dated
/// context: nothing here describes an inspected earlier moment (the as-of card /
/// Details contract stays parked).
///
/// COMPLETE vs SUPPLIED: within each held market, every served outcome of its
/// body is a card. Which markets exist is only what the host SUPPLIES — the
/// Winner market and the finish markets it holds; a market the host does not
/// hold is not listed, and no group claims to be every venue prop or the whole
/// field. Production supplies no finish markets yet (the host's OWED list).
///
/// Nothing here fetches, subscribes, schedules, ranks or holds state; building
/// a callback calls nothing.
enum GolfFieldPropsBrowseAdapter10868 {
    typealias Details = OriginalMarketDetails9483
    typealias Originals = GolfFieldOriginalsAdapter10868.Originals
    typealias Field = GolfFieldHistoryAdapter10868.Field
    typealias Kind = GolfFieldFinishAdapter10868.Kind
    typealias Legs = GolfFieldFinishAdapter10868.Legs

    enum Words {
        /// Above the group menu (Design).
        static let heading = "Prop groups"
        /// A group whose market serves no outcome, or a menu with no group.
        static let emptyWords = FieldEventOriginalsAdapter10868.Words.emptyWords
        /// A card whose original has no readable title or label of its own.
        static let unavailableChoice = FieldEventOriginalsAdapter10868.Words.unavailableChoice

        /// "3 original outcomes" — a count of the supplied rows, never a claim of completeness.
        static func count(_ count: Int) -> String { FieldEventOriginalsAdapter10868.Words.context(count) }
    }

    /// What a held group is bound to.
    struct Key: Equatable {
        /// The catalogue scope (market and phase) the group was chosen in.
        let scope: String
        /// The market's exact source key and id — `Details.Identity.source` / `.market`.
        let source: String
        let market: String
        let role: Kind
    }

    /// One held market's originals, ready for `OriginalMarketCatalogueView9483`.
    struct Group {
        let key: Key
        let originals: FieldEventPageOriginals10868

        /// The supplied rows in this group.
        var count: Int { originals.catalogue?.originals.count ?? 0 }
    }

    /// The browse sheet's layer: the group menu, or one held group.
    enum Layer: Equatable {
        case menu
        case group(Key)
    }

    // MARK: - The groups

    /// One group per held market, in `fields`' order, from THIS pass's originals.
    static func groups(_ winner: Field, legs: Legs, originals: Originals, tint: Color) -> [Group] {
        let catalogue = originals.catalogue
        return GolfFieldOriginalsAdapter10868.fields(winner, legs: legs).compactMap { field -> Group? in
            let market = field.market
            guard let kind = Self.role(market, winner: winner.market, legs: legs) else { return nil }
            let key = Key(scope: catalogue.scope, source: GolfFieldPageAdapter10868.sourceKey(market),
                          market: String(market.id), role: kind)
            let members = catalogue.originals.filter {
                $0.identity.source == key.source && $0.identity.market == key.market
            }
            return Group(key: key, originals: FieldEventPageOriginals10868(
                catalogue: members.isEmpty ? nil : Details.Catalogue(scope: catalogue.scope, originals: members),
                selection: nil,
                labels: Self.labels(members),
                heading: kind.name,
                context: members.isEmpty ? nil : Words.count(members.count),
                emptyWords: Words.emptyWords,
                unavailableChoice: Words.unavailableChoice,
                tint: tint))
        }
    }

    /// The market's typed role: Win for the page's Winner market, else the first
    /// `Legs` slot holding that market id (`fields`' own order); nil for none.
    static func role(_ market: FuturesMarketDetail, winner: FuturesMarketDetail, legs: Legs) -> Kind? {
        if market.id == winner.id { return .win }
        let slots: [(Kind, GolfFieldFinishAdapter10868.Leg?)] = [
            (.top5, legs.top5), (.top10, legs.top10), (.top20, legs.top20), (.makeCut, legs.makeCut),
        ]
        return slots.first { $0.1?.market.id == market.id }?.0
    }

    /// The served outcome name for each identity carried by exactly one row.
    static func labels(_ originals: [Details.Original]) -> [Details.Identity: String] {
        var counts: [Details.Identity: Int] = [:]
        for original in originals { counts[original.identity, default: 0] += 1 }
        var labels: [Details.Identity: String] = [:]
        for original in originals where counts[original.identity] == 1 {
            labels[original.identity] = original.outcome
        }
        return labels
    }

    // MARK: - Resolution and actions

    /// The held group on this pass: exactly one group carrying the same key, or nil.
    static func group(_ key: Key, in groups: [Group]) -> Group? {
        let matches = groups.filter { $0.key == key }
        return matches.count == 1 ? matches[0] : nil
    }

    /// Explore props acts only when some group holds a supplied row.
    static func offered(_ groups: [Group]) -> Bool {
        groups.contains { $0.count > 0 }
    }

    /// One pass's Explore props callback: nil when nothing would be shown. A tap
    /// asks for the page's hold ONCE, then opens the group menu. Building it
    /// calls nothing.
    static func entry(_ groups: [Group], hold: (() -> Void)?, open: @escaping () -> Void) -> (() -> Void)? {
        guard offered(groups) else { return nil }
        return {
            hold?()
            open()
        }
    }

    /// One pass's card callback: a tap asks for the page's hold ONCE, then opens
    /// that card's exact selection in the shared Details — unchanged, never
    /// re-scoped. Building it calls nothing.
    static func select(hold: (() -> Void)?,
                       open: @escaping (GolfFieldOriginalsAdapter10868.Destination) -> Void) -> (Details.Selection) -> Void {
        return { selection in
            hold?()
            open(.original(selection))
        }
    }

    /// "Top 5, 3 original outcomes".
    static func spoken(_ group: Group) -> String {
        "\(group.key.role.name), \(Words.count(group.count))"
    }
}
