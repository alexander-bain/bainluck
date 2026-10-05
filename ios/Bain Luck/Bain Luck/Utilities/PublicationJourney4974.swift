import Foundation

/// #4974 — whether the iPhone chart may draw a finished game's recorded
/// checkpoints, and what a scrub over them may answer.
///
/// Pure. No view, no network, no clock. The integration (Native) decodes a
/// `PublicationCheckpointsResponse`, asks `adopt` once, and on `.success` uses
/// the returned `Journey` for three things only:
///
/// 1. **Scrub** — `Journey.hit` answers with a STORED vertex within
///    `hitRadius` points of the finger, or nothing. It never interpolates,
///    never holds the last value forward, and never answers with the cursor's
///    own time.
/// 2. **Window** — `Journey.window` is `min(t)...max(t)` over the vertices.
///    Not first/last `rev`: insert stamps are taken before commit, so commit
///    order and clock order can disagree.
/// 3. **Legacy segments** — the chart's existing (history) line must not draw
///    a connecting segment across the recorded window. `permitsLegacySegment`
///    refuses any segment whose closed time interval touches it; the legacy
///    points themselves are never moved, re-valued or supplemented.
///
/// ## What a vertex does NOT say
///
/// `rev` counts bag commits only. A status-only or blend-input-only commit can
/// move the published probability between two rows without moving `rev`, so
/// nothing proves two recorded checkpoints were adjacent. That is why there is
/// no connector, step, hold or expiry here, and why the gap between two
/// vertices answers a scrub with nothing at all.
///
/// Boundary: `4974-NATIVE-PURE-SOURCE-SUCCESSOR.md`.
nonisolated enum PublicationJourney4974 {
    /// The only body shape this reader understands.
    static let schemaVersion = 1
    /// The only meaning of `t` this reader understands.
    static let timeBasis = "recorded_at_insert_before_commit"
    /// One vertex is a dot, not a journey.
    static let minimumVertices = 2
    /// The server's cap (`MAX_VERTICES`); a body over it is not this contract.
    static let maximumVertices = 5000
    /// Scrub reach, in logical chart points (the units `ChartProxy.position(forX:)`
    /// returns). Fixed: no screen-scale adjustment.
    static let hitRadius: Double = 8

    /// Why a response is not drawn. The first failing check wins; the response
    /// is refused whole — a malformed row is never dropped so the rest can draw.
    nonisolated enum Refusal: Error, Equatable, Sendable {
        case wrongEvent(expected: Int, served: Int)
        case unfinished
        case schemaVersion(Int)
        case timeBasis(String)
        case truncated
        case vertexCount(Int)
        /// A negative revision.
        case invalidRevision(index: Int)
        /// A revision not strictly greater than the one before it (a duplicate
        /// included). Order is never synthesized.
        case nonIncreasingRevision(index: Int)
        /// Not a UTC ISO 8601 stamp the app parses.
        case malformedTimestamp(index: Int)
        /// Not finite, or outside 0...1.
        case invalidProbability(index: Int)
    }

    /// A served vertex, untouched, with the moment its own `t` names.
    nonisolated struct Checkpoint: Equatable, Sendable {
        let vertex: PublicationCheckpointVertex
        let date: Date
    }

    /// The vertex a scrub landed on, at its own x — never the cursor's.
    nonisolated struct Hit: Equatable, Sendable {
        let checkpoint: Checkpoint
        let x: Double
    }

    /// An adopted response: every vertex, in the server's order.
    nonisolated struct Journey: Equatable, Sendable {
        let eventId: Int
        let checkpoints: [Checkpoint]
        let window: ClosedRange<Date>

        /// Closed membership: both ends are inside.
        func contains(_ date: Date) -> Bool {
            window.contains(date)
        }

        /// Whether the legacy line may connect `from` to `to`.
        ///
        /// False when the segment's closed interval `[min, max]` shares any
        /// moment with the recorded window — crossing it, inside it, or
        /// touching either end. A legacy line at 20:15 and 20:16 around
        /// checkpoints at 20:15:10...20:15:50 breaks.
        func permitsLegacySegment(from: Date, to: Date) -> Bool {
            let start = min(from, to), end = max(from, to)
            return end < window.lowerBound || start > window.upperBound
        }

        /// The legacy series cut into the runs it may still be drawn as.
        ///
        /// Each run is a slice of `points` in their given order, elements
        /// returned as passed in: a cut drops only the connecting segment,
        /// never a point, and nothing is inserted at the window's edges.
        func legacyRuns<Point>(_ points: [Point], date: (Point) -> Date) -> [[Point]] {
            guard var previous = points.first else { return [] }
            var runs: [[Point]] = []
            var run: [Point] = [previous]
            for point in points.dropFirst() {
                if permitsLegacySegment(from: date(previous), to: date(point)) {
                    run.append(point)
                } else {
                    runs.append(run)
                    run = [point]
                }
                previous = point
            }
            runs.append(run)
            return runs
        }

        /// The stored vertex a scrub at `cursorX` lands on, or `nil`.
        ///
        /// `position` is the caller's chart x for a checkpoint, in logical
        /// points (`proxy.position(forX: checkpoint.date)`). Nearest wins; an
        /// equal distance goes to the greatest `rev`. Beyond `hitRadius` there
        /// is no answer — no fallback to the latest vertex before the cursor.
        /// A non-finite cursor, a missing or non-finite position, or a distance
        /// that overflows refuses the whole scrub rather than skipping a row.
        func hit(cursorX: Double, position: (Checkpoint) -> Double?) -> Hit? {
            guard cursorX.isFinite else { return nil }
            var best: Hit?
            var bestDistance = Double.infinity
            for checkpoint in checkpoints {
                guard let x = position(checkpoint), x.isFinite else { return nil }
                let distance = abs(x - cursorX)
                guard distance.isFinite else { return nil }
                if let current = best {
                    let closer = distance < bestDistance
                    let tieWins = distance == bestDistance
                        && checkpoint.vertex.rev > current.checkpoint.vertex.rev
                    guard closer || tieWins else { continue }
                }
                best = Hit(checkpoint: checkpoint, x: x)
                bestDistance = distance
            }
            guard let best, bestDistance <= PublicationJourney4974.hitRadius else { return nil }
            return best
        }
    }

    /// Adopt `response` for the chart of event `expectedEventID`, or say why not.
    ///
    /// `finished` is the page's own settled state; slice 1 draws finished games
    /// only. Checks run in a fixed order and the first failure is returned.
    static func adopt(
        _ response: PublicationCheckpointsResponse,
        expectedEventID: Int,
        finished: Bool
    ) -> Result<Journey, Refusal> {
        guard response.eventId == expectedEventID else {
            return .failure(.wrongEvent(expected: expectedEventID, served: response.eventId))
        }
        guard finished else { return .failure(.unfinished) }
        guard response.schemaVersion == schemaVersion else {
            return .failure(.schemaVersion(response.schemaVersion))
        }
        guard response.timeBasis == timeBasis else { return .failure(.timeBasis(response.timeBasis)) }
        guard !response.truncated else { return .failure(.truncated) }
        let count = response.vertices.count
        guard count >= minimumVertices, count <= maximumVertices else {
            return .failure(.vertexCount(count))
        }

        var checkpoints: [Checkpoint] = []
        checkpoints.reserveCapacity(count)
        var previousRev: Int64?
        for (index, vertex) in response.vertices.enumerated() {
            guard vertex.rev >= 0 else { return .failure(.invalidRevision(index: index)) }
            if let previousRev, vertex.rev <= previousRev {
                return .failure(.nonIncreasingRevision(index: index))
            }
            previousRev = vertex.rev
            guard let parsed = Self.date(ofStamp: vertex.t) else {
                return .failure(.malformedTimestamp(index: index))
            }
            guard vertex.p.isFinite, vertex.p >= 0, vertex.p <= 1 else {
                return .failure(.invalidProbability(index: index))
            }
            checkpoints.append(Checkpoint(vertex: vertex, date: parsed))
        }

        let dates = checkpoints.map(\.date)
        // count >= minimumVertices, so both exist.
        guard let earliest = dates.min(), let latest = dates.max() else {
            return .failure(.vertexCount(count))
        }
        return .success(Journey(eventId: response.eventId, checkpoints: checkpoints, window: earliest...latest))
    }

    /// The moment a served `t` names, parsed exactly as every other chart
    /// stamp on the page (`String.asDate`), with or without a fraction.
    /// The contract is UTC, so only a `Z` or `+00:00` suffix is accepted.
    static func date(ofStamp stamp: String) -> Date? {
        guard stamp.hasSuffix("Z") || stamp.hasSuffix("+00:00") else { return nil }
        return stamp.asDate
    }
}
