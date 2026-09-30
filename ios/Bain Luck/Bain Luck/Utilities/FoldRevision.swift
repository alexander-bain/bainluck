import Foundation

/// #9051 — which of two served blends is NEWER, by the rows it was folded from.
///
/// The iPhone twin of web's `frontend/lib/foldRevision.ts`; the rules are the
/// same and so is the reason. A blend is dated by the newest PRICE it folded,
/// and a price clock cannot see a removal: after Kalshi is retired the fresh
/// Polymarket-only 40% is dated by Polymarket's last quote, which can be OLDER
/// than a 60% frame the page already holds that still folded Kalshi. Every
/// clock rule in `LiveEventPriceReconciliation` then kept the 60%.
///
/// So the producer serves a revision vector with every blend — `{"<row id>":
/// rev}` for each row the fold read, bumped by a database trigger on every
/// change to that row's sources. Each component is that row's commit order, so:
///
/// - `newer` — at least as high on every row, higher on one, same rows. Adopt
///   its value AND its clock, even an older clock, and keep its vector.
/// - `same` — the same snapshot; the price clocks decide as before.
/// - `older` — refuse.
/// - `incomparable` — different rows (a duplicate joined or left the fold) or
///   mixed directions. Keep what is held; only a fresh detail read settles it.
///
/// An absent or malformed vector makes NO claim. With none held, every
/// pre-contract rule applies unchanged. Against a held one it is not a newer
/// value in disguise: a value is never tagged with a revision borrowed from a
/// different value.
nonisolated struct FoldRevision: Sendable, Equatable {
    /// Largest integer a JSON number carries exactly in JavaScript. Web refuses
    /// anything past it, so the two clients read the same vectors as claims.
    static let maxSafeInteger = 9_007_199_254_740_991

    let rows: [String: Int]

    /// `nil` for an empty vector or any component that is negative or past the
    /// safe-integer bound — the same refusals as web's `parseFoldRevision`.
    init?(_ rows: [String: Int]) {
        guard !rows.isEmpty,
              rows.values.allSatisfy({ $0 >= 0 && $0 <= Self.maxSafeInteger }) else { return nil }
        self.rows = rows
    }
}

nonisolated enum FoldOrder: Sendable, Equatable {
    case newer, same, older, incomparable
}

/// A served revision as it arrived. NEVER THROWS, for the reason
/// `EvidenceContract.init(from:)` gives: it sits inside `EventDetail`,
/// `EventHistoryResponse` and every pushed frame, and a mistyped vector must
/// degrade to "no claim", never to "no page". `revision == nil` is that state.
nonisolated struct ServedFoldRevision: Decodable, Sendable, Equatable {
    let revision: FoldRevision?

    init(_ revision: FoldRevision?) {
        self.revision = revision
    }

    init(from decoder: Decoder) throws {
        // `[String: Int]` refuses a bool, a string and a fractional number, so
        // `{"1": true}` is malformed rather than revision 1.
        let rows = try? decoder.singleValueContainer().decode([String: Int].self)
        revision = rows.flatMap(FoldRevision.init)
    }
}

extension FoldRevision {
    /// How `incoming` orders against `held`.
    static func compare(_ incoming: FoldRevision, _ held: FoldRevision) -> FoldOrder {
        guard incoming.rows.count == held.rows.count,
              held.rows.keys.allSatisfy({ incoming.rows[$0] != nil }) else { return .incomparable }
        var higher = false
        var lower = false
        for (row, heldRev) in held.rows {
            let incomingRev = incoming.rows[row]!
            if incomingRev > heldRev { higher = true } else if incomingRev < heldRev { lower = true }
        }
        if higher && lower { return .incomparable }
        return higher ? .newer : lower ? .older : .same
    }

    /// A pushed frame speaks for ONE row's write. It orders against a held blend
    /// only when that blend was folded from that one row: a folded hero
    /// (canonical + duplicates) is a value the frame's raw-row `p` never
    /// computed, with or without a vector. A frame with no vector on a held one
    /// cannot be ordered either. `nil` (no claim) only when nothing is held.
    static func frameOrder(held: FoldRevision?, frame: FoldRevision?) -> FoldOrder? {
        guard let held else { return nil }
        guard held.rows.count == 1, let frame, frame.rows.count == 1 else { return .incomparable }
        return compare(frame, held)
    }
}
