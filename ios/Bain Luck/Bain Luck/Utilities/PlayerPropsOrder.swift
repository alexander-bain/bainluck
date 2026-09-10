import Foundation

/// The order the Player Props card deals its cards and its stat groups.
///
/// #4857 — A LIST THAT RESHUFFLED ON EVERY LAUNCH. Photographed three times on
/// `bainluck://events/15305028` within five minutes — twice on the SAME binary —
/// and the five players came back in three different orders, with identical
/// data and identical percentages.
///
/// The cause is one shape repeated at two levels. `PlayerPropsCardView` groups
/// props into a Swift `Dictionary` and maps over it, and **dictionary iteration
/// order is seeded per process**, so it differs on every app launch. Each level
/// then sorted on a single count:
///
///     .sorted { $0.statGroups.map(\.rungs.count).reduce(0, +) > $1… }   // cards
///     .sorted { $0.rungs.count > $1.rungs.count }                       // stat groups
///
/// Neither key is unique. On the photographed specimen every player had exactly
/// one rung, so all five compared equal, `sorted` is not guaranteed stable, and
/// the random dictionary order survived the sort untouched and reached the
/// screen. A game where every player has one prop is ordered *entirely* at random.
///
/// 🔴 A COUNT IS NOT AN ORDER. The fix is not "sort harder", it is to end every
/// comparison on a key that cannot tie. Both functions below finish on a
/// dictionary KEY — the player's name, the stat type — which is unique by
/// construction, so the result is a total order and the same payload always
/// draws the same list.
///
/// The middle term is the only product choice here, and it is small: among
/// players tied on rung count, the one whose most likely prop is likeliest comes
/// first. That is what the card's bars already imply a reader should look at, and
/// it beats alphabetical, which would open every NFL card on the same surname.
enum PlayerPropsOrder {

    /// One player card's sort key: how many rungs it carries in total, its
    /// likeliest rung, and its player name.
    struct CardKey {
        let rungs: Int
        let topProbability: Double
        let name: String

        init(rungs: Int, topProbability: Double, name: String) {
            self.rungs = rungs
            self.topProbability = topProbability
            self.name = name
        }
    }

    /// Most rungs first, then the likeliest prop, then the name.
    ///
    /// `name` is the dictionary key the cards were grouped under, so it is unique
    /// across the list and this can never fall through to a tie.
    static func cardPrecedes(_ lhs: CardKey, _ rhs: CardKey) -> Bool {
        if lhs.rungs != rhs.rungs { return lhs.rungs > rhs.rungs }
        if lhs.topProbability != rhs.topProbability {
            return lhs.topProbability > rhs.topProbability
        }
        return lhs.name < rhs.name
    }

    /// One stat group's sort key within a single player's card.
    struct StatGroupKey {
        let rungs: Int
        let type: String

        init(rungs: Int, type: String) {
            self.rungs = rungs
            self.type = type
        }
    }

    /// The fullest ladder first, then the stat name.
    ///
    /// `type` is this level's dictionary key and is likewise unique within one
    /// player, so this is a total order too. Missing it is why a player with
    /// "Hits" and "RBIs" could swap them between launches.
    static func statGroupPrecedes(_ lhs: StatGroupKey, _ rhs: StatGroupKey) -> Bool {
        if lhs.rungs != rhs.rungs { return lhs.rungs > rhs.rungs }
        return lhs.type < rhs.type
    }
}
