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
///   "state": "blend" | "single" | "settled" | "none",
///   "sources": [{"key", "name", "probability", "observed_at", "count"?}],
///   "settled": {"source", "result", "at"},
///   "method"?: "<short calculation name>"
/// }
/// ```
///
/// Every field decodes leniently (gotcha #42): one unreadable source drops that
/// source, never the prop row it rides on, and an unknown `state` reads as
/// ``State/unknown``, which draws no mark.
nonisolated struct SourceMark: Decodable, Equatable, Sendable {
    enum State: Equatable, Sendable { case blend, single, settled, none, unknown }

    nonisolated struct Source: Decodable, Equatable, Sendable {
        let key: String
        let name: String
        let probability: Double?
        /// When THIS source's price was observed (#12581), not when the row was polled.
        let observedAt: String?
        /// Sportsbooks only: how many books the line stands for.
        var count: Int? = nil

        init(key: String, name: String, probability: Double?, observedAt: String?, count: Int? = nil) {
            self.key = key
            self.name = name
            self.probability = probability
            self.observedAt = observedAt
            self.count = count
        }

        private nonisolated struct DynamicKey: CodingKey {
            var stringValue: String
            var intValue: Int? { nil }
            init(_ string: String) { self.stringValue = string }
            init?(stringValue: String) { self.stringValue = stringValue }
            init?(intValue: Int) { return nil }
        }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: DynamicKey.self)
            self.key = try c.decode(String.self, forKey: DynamicKey("key"))
            self.name = try c.decode(String.self, forKey: DynamicKey("name"))
            self.probability = try c.decodeIfPresent(Double.self, forKey: DynamicKey("probability"))
            self.observedAt = (try? c.decodeIfPresent(String.self, forKey: DynamicKey("observedAt")))
                ?? (try? c.decodeIfPresent(String.self, forKey: DynamicKey("observed_at")))
            self.count = try c.decodeIfPresent(Int.self, forKey: DynamicKey("count"))
        }
    }

    nonisolated struct Settled: Decodable, Equatable, Sendable {
        let source: String?
        let result: String?
        let at: String?
    }

    /// Optional dev-only metadata (`#11920` rev 2, Dev Signal C): omitted on public payloads,
    /// decoded leniently when present so the owner-only dev overlay can inspect breadth and weights.
    nonisolated struct Dev: Decodable, Equatable, Sendable {
        let of: Int?
        let missing: [String]?
        let weights: [String: Double]?

        init(of: Int? = nil, missing: [String]? = nil, weights: [String: Double]? = nil) {
            self.of = of
            self.missing = missing
            self.weights = weights
        }
    }

    let state: State
    let sources: [Source]
    let settled: Settled?
    let method: String?
    var dev: Dev? = nil

    init(
        state: State,
        sources: [Source],
        settled: Settled? = nil,
        method: String? = nil,
        dev: Dev? = nil
    ) {
        self.state = state
        self.sources = sources
        self.settled = settled
        self.method = method
        self.dev = dev
    }

    private enum CodingKeys: String, CodingKey { case state, sources, settled, method, dev }

    /// Decodes `[Source]` element by element so one bad entry drops alone.
    private nonisolated struct Lenient<T: Decodable>: Decodable {
        let value: T?
        init(from decoder: Decoder) throws { value = try? T(from: decoder) }
    }

    init(from decoder: Decoder) throws {
        // Not an object at all: no mark, and the row it rides on still decodes.
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else {
            state = .unknown; sources = []; settled = nil; method = nil; dev = nil
            return
        }
        switch (try? c.decodeIfPresent(String.self, forKey: .state)) ?? nil {
        case "blend": state = .blend
        case "single": state = .single
        case "settled": state = .settled
        case "none": state = .none
        default: state = .unknown
        }
        sources = ((try? c.decodeIfPresent([Lenient<Source>].self, forKey: .sources)) ?? nil)?
            .compactMap(\.value) ?? []
        settled = (try? c.decodeIfPresent(Settled.self, forKey: .settled)) ?? nil
        method = (try? c.decodeIfPresent(String.self, forKey: .method)) ?? nil
        dev = (try? c.decodeIfPresent(Dev.self, forKey: .dev)) ?? nil
    }

    /// Does this mark draw at all? Only when the sheet would have something to
    /// say: a blend or single-venue mark with at least one source, or a settled
    /// result. "none", an unknown state and an empty mark draw nothing — never
    /// an empty sheet.
    var draws: Bool {
        switch state {
        case .blend, .single: return !sources.isEmpty
        case .settled: return settled != nil || !sources.isEmpty
        case .none, .unknown: return false
        }
    }
}
