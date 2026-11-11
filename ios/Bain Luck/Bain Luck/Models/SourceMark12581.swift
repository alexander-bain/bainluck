import Foundation

/// #12581 / 137-A — where a served probability came from, as the server says it.
///
/// The SERVER owns every part of this: which sources contributed, their order,
/// their prices and when each was observed. The app draws it and never works a
/// source out, orders one or fills one in (137-A: "don't infer a source in the
/// app"). The shape is #12581's:
///
/// ```
/// "source_mark": {
///   "state": "blend" | "settled" | "none",
///   "sources": [{"key", "name", "probability", "observed_at", "count"?}],
///   "settled": {"source", "result", "at"}
/// }
/// ```
///
/// Every field decodes leniently (gotcha #42): one unreadable source drops that
/// source, never the prop row it rides on, and an unknown `state` reads as
/// ``State/unknown``, which draws no mark.
nonisolated struct SourceMark: Decodable, Equatable, Sendable {
    enum State: Equatable, Sendable { case blend, settled, none, unknown }

    nonisolated struct Source: Decodable, Equatable, Sendable {
        let key: String
        let name: String
        let probability: Double?
        /// When THIS source's price was observed (#12581), not when the row was polled.
        let observedAt: String?
        /// Sportsbooks only: how many books the line stands for.
        var count: Int? = nil
    }

    nonisolated struct Settled: Decodable, Equatable, Sendable {
        let source: String?
        let result: String?
        let at: String?
    }

    let state: State
    let sources: [Source]
    let settled: Settled?
    /// Why a `none` mark names no source, as the server says it (#12597):
    /// `monotonic_conflict`, `source_evidence_incomplete`, `opening_only`, …
    var reason: String? = nil

    init(state: State, sources: [Source], settled: Settled? = nil, reason: String? = nil) {
        self.state = state
        self.sources = sources
        self.settled = settled
        self.reason = reason
    }

    private enum CodingKeys: String, CodingKey { case state, sources, settled, reason }

    /// Decodes `[Source]` element by element so one bad entry drops alone.
    private struct Lenient<T: Decodable>: Decodable {
        let value: T?
        init(from decoder: Decoder) throws { value = try? T(from: decoder) }
    }

    init(from decoder: Decoder) throws {
        // Not an object at all: no mark, and the row it rides on still decodes.
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else {
            state = .unknown; sources = []; settled = nil
            return
        }
        switch (try? c.decodeIfPresent(String.self, forKey: .state)) ?? nil {
        case "blend": state = .blend
        case "settled": state = .settled
        case "none": state = .none
        default: state = .unknown
        }
        sources = ((try? c.decodeIfPresent([Lenient<Source>].self, forKey: .sources)) ?? nil)?
            .compactMap(\.value) ?? []
        settled = (try? c.decodeIfPresent(Settled.self, forKey: .settled)) ?? nil
        reason = (try? c.decodeIfPresent(String.self, forKey: .reason)) ?? nil
    }

    /// Does this mark draw an ⓘ? Only where the sheet has a source to name: a
    /// `blend` with at least one source. Alex's second look (Nov 11): a settled
    /// result ("Won") and a capped line draw none — a tap that answers nothing,
    /// or explains our ladder housekeeping, isn't offered. Unknown states and an
    /// empty blend draw nothing either.
    var draws: Bool {
        state == .blend && !sources.isEmpty
    }
}
