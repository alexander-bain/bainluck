import Foundation

/// #10090 — a provisional blend shown before its event stamp commits
/// (`backend/app/utils/blend_preview.py`). The iPhone twin of web's
/// `frontend/lib/blendPreview.ts`; the rules are the same and so is the reason.
///
/// The server sends these only for its canary events, as a separate `preview`
/// SSE event. Without one, every function here returns its input and the page
/// renders exactly what it renders today.
///
/// A preview is never written into the page's committed `event`. It is an
/// overlay on the hero number alone, and it gives way to committed truth by rule:
///
/// - It carries no committed revision. Its `base_rev` is the revision it was
///   composed on; it shows only while the page holds no NEWER committed
///   revision of its one row. Any newer commit wins, whoever wrote it.
/// - `epoch` is the writing process's display claim, fenced at Redis: a
///   replacement worker's claim is a higher epoch. The reader keeps the highest
///   epoch it has seen and refuses anything older (`readerAfter`) — an earlier
///   epoch never regains the display, whatever order frames arrive in. A
///   higher epoch voids whatever the older one showed.
/// - Within an epoch, previews order by `seq`: a lower seq never replaces a
///   higher one, and a `revoke` withdraws every preview up to `through_seq`.
/// - Each origin row's ledger is its own `(epoch, seq)` domain. A folded frame
///   orders only against frames of its own origin (a singleton's origin is
///   the page's row): two rows' epochs are never compared.
/// - It expires `ttl_ms` after arrival — a backstop for a revoke lost with a
///   stopped worker; the server revokes on its own clock as well.
/// - A reconnect clears the held preview (previews are never replayed, so a
///   missed revoke cannot be ruled out across a reconnect); the epoch floor is
///   kept, because epochs only rise.
/// - It shows only for the same quote status the page holds, on a live blend
///   hero. A singleton orders against its one row; a folded preview must cover
///   the page's exact complete membership and match its sport.
///
/// The chart may end on the same provisional number, as a disposable
/// projection dated by `display_observed_at` (`chartFrames`); with no usable
/// observation clock, or one not newer than the drawn line, it keeps committed
/// history. The probability's clock follows the same admission
/// (`displayedObservedAt`).
nonisolated struct BlendPreviewFrame: Decodable, Sendable, Equatable {
    enum Kind: String, Sendable { case blend, revoke }

    /// This client's refusal bound, like `SourceSnapshot.maxFrameBytes`. The
    /// producer's frame is a few hundred bytes.
    static let maxFrameBytes = 16 * 1024

    let eventId: Int
    let p: Double?
    let status: String?
    let kind: Kind
    let epoch: Int
    let seq: Int
    /// Present on every `blend`; absent on a `revoke`.
    let baseRev: Int?
    let ttlMs: Int?
    /// Present on every `revoke`.
    let throughSeq: Int?
    /// When the contributing readings were observed (`display_observed_at`),
    /// or nil when unknown. Never the legacy `observed_at`: that is the
    /// producer's attempt time, which a persistence retry moves.
    let displayObservedAt: Date?
    /// Folded wire v1: the complete base and its one ledger origin.
    let baseFoldRevision: FoldRevision?
    let originEventId: Int?
    let pAway: Double?
    let sport: String?

    init(eventId: Int, p: Double?, status: String?, kind: Kind, epoch: Int, seq: Int,
         baseRev: Int? = nil, ttlMs: Int? = nil, throughSeq: Int? = nil, displayObservedAt: Date? = nil,
         baseFoldRevision: FoldRevision? = nil, originEventId: Int? = nil,
         pAway: Double? = nil, sport: String? = nil) {
        self.eventId = eventId
        self.p = p
        self.status = status
        self.kind = kind
        self.epoch = epoch
        self.seq = seq
        self.baseRev = baseRev
        self.ttlMs = ttlMs
        self.throughSeq = throughSeq
        self.displayObservedAt = displayObservedAt
        self.baseFoldRevision = baseFoldRevision
        self.originEventId = originEventId
        self.pAway = pAway
        self.sport = sport
    }

    private enum CodingKeys: String, CodingKey {
        case eventId, p, pAway, sport, status, rev, preview, displayObservedAt
    }

    private enum PreviewKeys: String, CodingKey {
        case kind, epoch, seq, baseRev, ttlMs, throughSeq, foldedVersion, originEventId, baseFoldRevision
    }

    /// Web's `safeInt`: a non-negative integer a JSON number carries exactly.
    /// `Int` decoding already refuses a fraction, a string and a bool.
    private static func safe(_ value: Int?) -> Bool {
        value.map { $0 >= 0 && $0 <= FoldRevision.maxSafeInteger } ?? false
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func refuse(_ why: String) -> DecodingError {
            .dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: why))
        }
        // A committed revision on a "preview" is a contradiction: refuse it.
        guard !c.contains(.rev) else { throw refuse("a preview carries no committed revision") }
        eventId = try c.decode(Int.self, forKey: .eventId)
        p = try c.decodeIfPresent(Double.self, forKey: .p)
        status = try c.decodeIfPresent(String.self, forKey: .status)
        let preview = try c.nestedContainer(keyedBy: PreviewKeys.self, forKey: .preview)
        guard let kind = Kind(rawValue: try preview.decode(String.self, forKey: .kind)) else {
            throw refuse("unknown preview kind")
        }
        self.kind = kind
        epoch = try preview.decode(Int.self, forKey: .epoch)
        seq = try preview.decode(Int.self, forKey: .seq)
        baseRev = try preview.decodeIfPresent(Int.self, forKey: .baseRev)
        ttlMs = try preview.decodeIfPresent(Int.self, forKey: .ttlMs)
        throughSeq = try preview.decodeIfPresent(Int.self, forKey: .throughSeq)
        // Additive: a missing, null or unreadable clock leaves the time
        // unknown and the frame itself still decodes, as on web.
        displayObservedAt = (try? c.decodeIfPresent(String.self, forKey: .displayObservedAt))?.asDate
        guard Self.safe(epoch), Self.safe(seq) else { throw refuse("unordered preview") }
        originEventId = try preview.decodeIfPresent(Int.self, forKey: .originEventId)
        if preview.contains(.originEventId) {
            guard let originEventId, Self.safe(originEventId), originEventId > 0 else {
                throw refuse("invalid preview origin")
            }
        }
        let folded = preview.contains(.foldedVersion) || preview.contains(.baseFoldRevision)
        if folded {
            guard kind == .blend, try preview.decode(Int.self, forKey: .foldedVersion) == 1,
                  let originEventId, Self.safe(eventId), eventId > 0,
                  let vector = BlendPreview.validRevision(
                    try preview.decode([String: Int].self, forKey: .baseFoldRevision)),
                  vector.rows.count >= 2, vector.rows[String(eventId)] != nil,
                  vector.rows[String(originEventId)] == baseRev,
                  c.contains(.pAway), c.contains(.sport) else {
                throw refuse("invalid folded preview authority")
            }
            baseFoldRevision = vector
            pAway = try c.decodeIfPresent(Double.self, forKey: .pAway)
            sport = try c.decodeIfPresent(String.self, forKey: .sport)
            if let pAway, !pAway.isFinite || !(0...1).contains(pAway) {
                throw refuse("unprintable folded away probability")
            }
        } else {
            // An origin-only revoke is the server's folded withdrawal shape.
            // An origin-only blend must never fall back to singleton admission.
            guard kind == .revoke || !preview.contains(.originEventId) else {
                throw refuse("folded blend without full authority")
            }
            baseFoldRevision = nil
            pAway = nil
            sport = nil
        }
        switch kind {
        case .revoke:
            guard Self.safe(throughSeq) else { throw refuse("revoke without through_seq") }
        case .blend:
            guard let p, p.isFinite, (0...1).contains(p), Self.safe(baseRev), Self.safe(ttlMs) else {
                throw refuse("unprintable preview")
            }
        }
    }

    /// The controller's raw `preview` data, or `nil` for anything that is not a
    /// well-formed provisional frame. Never throws: one bad frame is dropped.
    static func decode(_ raw: String) -> BlendPreviewFrame? {
        guard raw.utf8.count <= maxFrameBytes, let data = raw.data(using: .utf8) else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(BlendPreviewFrame.self, from: data)
    }
}

/// The one preview an event's reader holds.
nonisolated struct BlendPreviewState: Sendable, Equatable {
    let eventId: Int
    let epoch: Int
    let seq: Int
    let baseRev: Int
    let p: Double
    let status: String?
    /// On the page's own `now()` clock: after this the preview is not shown.
    let expiresAt: TimeInterval
    /// The frame's `displayObservedAt`; nil when unknown.
    var observedAt: Date? = nil
    var baseFoldRevision: FoldRevision? = nil
    var originEventId: Int? = nil
    var pAway: Double? = nil
    var sport: String? = nil
}

/// What one event's reader holds: its preview, and the highest epoch it has seen.
nonisolated struct BlendPreviewReader: Sendable, Equatable {
    var held: BlendPreviewState?
    /// The fence floor of the page's own row: its frames from a lower epoch
    /// are refused. -1 before any. Another origin's epoch never moves it.
    var epoch: Int
    var floors: FoldRevision? = nil
    /// The newest `(epoch, seq)` accepted from each origin row, the page's own
    /// row included. Retained across expiry, revoke, reconnect AND membership
    /// change — a row that leaves the fold and returns keeps its fence — so a
    /// replay never renews TTL. Folded frames order strictly against it.
    var originFences: [Int: OriginSequence] = [:]
    /// Once this visit has seen folded authority, singleton frames also order
    /// strictly against their row's fence.
    var sawFolded = false
    /// The rows of the page's adopted fold revision (`readerAfterMembership`),
    /// or nil before any claim. A folded frame composed for other rows, and a
    /// singleton frame on a multi-row page, never apply.
    var members: Set<String>? = nil

    struct OriginSequence: Sendable, Equatable {
        let epoch: Int
        let seq: Int
    }

    /// A fold has a handful of rows. Past this many distinct origins a new one
    /// is refused rather than any fence forgotten.
    static let maxOrigins = 32

    static let empty = BlendPreviewReader(held: nil, epoch: -1)
}

/// Proof attached only to the disposable folded chart endpoint. The chart
/// checks it against its own served history before removing a synthetic pin.
nonisolated struct BlendPreviewChartAuthority: Sendable, Equatable {
    let eventId: Int
    let base: FoldRevision
}

nonisolated enum BlendPreview {
    /// Canonical positive row identifiers and safe integer revisions only.
    static func validRevision(_ rows: [String: Int]) -> FoldRevision? {
        guard rows.keys.allSatisfy({ key in
            guard let id = Int(key), id > 0, id <= FoldRevision.maxSafeInteger else { return false }
            return String(id) == key
        }) else { return nil }
        return FoldRevision(rows)
    }

    /// #10090 — whether the page's adopted fold revision names different rows
    /// than the membership the reader is bound to. The first claim and an
    /// absent one are not a change.
    static func membershipChanges(_ reader: BlendPreviewReader, _ revision: FoldRevision?) -> Bool {
        guard let members = reader.members, let revision else { return false }
        return Set(revision.rows.keys) != members
    }

    /// The reader once the page adopts `revision` as its authoritative fold.
    /// A changed membership withdraws the held preview and binds the new rows;
    /// every origin fence, commit floor and epoch is kept, so nothing the
    /// visit already accepted or saw committed can be replayed with a new
    /// lifetime — not even by a row that left and returned.
    static func readerAfterMembership(_ reader: BlendPreviewReader, _ revision: FoldRevision?) -> BlendPreviewReader {
        guard let revision else { return reader }
        var next = reader
        if membershipChanges(reader, revision) { next.held = nil }
        next.members = Set(revision.rows.keys)
        return next
    }

    /// The commit floors that apply to the bound membership. A floor of a row
    /// that is not a member is kept for its return but cannot withhold a fold
    /// that no longer contains it.
    private static func memberFloors(_ reader: BlendPreviewReader) -> FoldRevision? {
        guard let floors = reader.floors, let members = reader.members else { return reader.floors }
        return FoldRevision(floors.rows.filter { members.contains($0.key) })
    }

    /// Commit evidence withdraws an uncovered folded preview immediately; it
    /// never creates a probability, observation timestamp or renewed lifetime.
    static func readerAfterCommitFloor(_ reader: BlendPreviewReader, _ floor: FoldRevision?) -> BlendPreviewReader {
        var next = reader
        guard let floor else { next.held = nil; return next }
        var rows = reader.floors?.rows ?? [:]
        for (id, rev) in floor.rows { rows[id] = max(rows[id] ?? 0, rev) }
        next.floors = FoldRevision(rows)
        if let base = reader.held?.baseFoldRevision, let floors = memberFloors(next), !base.covers(floors) {
            next.held = nil
        }
        return next
    }

    /// Wrong-page controls are ignored; malformed controls for this stream
    /// conservatively withdraw without forgetting any accumulated fences.
    static func readerAfterCommitFloor(_ reader: BlendPreviewReader, raw: String, eventId: Int) -> BlendPreviewReader {
        struct Packet: Decodable { let eventId: Int; let floor: [String: Int]? }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard raw.utf8.count <= BlendPreviewFrame.maxFrameBytes,
              let data = raw.data(using: .utf8), let packet = try? decoder.decode(Packet.self, from: data) else {
            return readerAfterCommitFloor(reader, nil)
        }
        guard packet.eventId == eventId else { return reader }
        return readerAfterCommitFloor(reader, packet.floor.flatMap(validRevision))
    }

    /// The reader after `frame` arrives at `now`. A lower epoch of the frame's
    /// origin is fenced out; a higher one raises that origin's floor and voids
    /// the preview its older epoch showed first.
    static func readerAfter(_ reader: BlendPreviewReader, _ frame: BlendPreviewFrame,
                            eventId: Int, now: TimeInterval) -> BlendPreviewReader {
        guard frame.eventId == eventId else { return reader }
        if let members = reader.members {
            if let base = frame.baseFoldRevision {
                guard Set(base.rows.keys) == members else { return reader }
            } else if frame.kind == .blend, members != [String(eventId)] {
                return reader
            }
        }
        let origin = frame.originEventId ?? eventId
        let fence = reader.originFences[origin]
        guard frame.epoch >= (origin == eventId ? reader.epoch : -1),
              frame.epoch >= fence?.epoch ?? -1 else { return reader }
        if frame.originEventId != nil || reader.sawFolded, let fence,
           frame.epoch == fence.epoch, frame.seq <= fence.seq { return reader }
        // A folded withdrawal speaks only for an origin this visit accepted.
        if frame.kind == .revoke, frame.originEventId != nil, fence == nil { return reader }
        guard fence != nil || reader.originFences.count < BlendPreviewReader.maxOrigins else { return reader }
        var next = reader
        if origin == eventId { next.epoch = frame.epoch }
        let seq = max(frame.seq, frame.throughSeq ?? 0)
        if fence.map({ frame.epoch > $0.epoch || seq > $0.seq }) ?? true {
            next.originFences[origin] = .init(epoch: frame.epoch, seq: seq)
        }
        if frame.baseFoldRevision != nil { next.sawFolded = true }
        let held = reader.held.flatMap { state in
            (state.originEventId ?? eventId) == origin && frame.epoch > state.epoch ? nil : state
        }
        if let base = frame.baseFoldRevision, let floors = memberFloors(reader), !base.covers(floors) {
            next.held = nil
        } else {
            next.held = previewAfter(held, frame, eventId: eventId, now: now)
        }
        return next
    }

    /// Within one epoch: the preview to hold after `frame` arrives at `now`.
    static func previewAfter(_ state: BlendPreviewState?, _ frame: BlendPreviewFrame,
                             eventId: Int, now: TimeInterval) -> BlendPreviewState? {
        guard frame.eventId == eventId else { return state }
        let sameOrigin = state.map { ($0.originEventId ?? eventId) == (frame.originEventId ?? eventId) } ?? false
        let sameEpoch = sameOrigin && state?.epoch == frame.epoch
        switch frame.kind {
        case .revoke:
            // Another origin's withdrawal says nothing about this preview.
            if let state, !sameOrigin { return state }
            guard let state, sameEpoch, let through = frame.throughSeq else {
                // A new epoch spoke; the old one's preview cannot be trusted.
                return nil
            }
            return state.seq <= through ? nil : state
        case .blend:
            if let state, sameEpoch, frame.seq <= state.seq { return state }
            guard let p = frame.p, let baseRev = frame.baseRev, let ttlMs = frame.ttlMs else { return state }
            return BlendPreviewState(eventId: eventId, epoch: frame.epoch, seq: frame.seq, baseRev: baseRev,
                                     p: p, status: frame.status, expiresAt: now + Double(ttlMs) / 1000,
                                     observedAt: frame.displayObservedAt,
                                     baseFoldRevision: frame.baseFoldRevision,
                                     originEventId: frame.originEventId, pAway: frame.pAway, sport: frame.sport)
        }
    }

    /// The provisional hero probability to show, or `nil` for committed truth.
    static func displayed(_ state: BlendPreviewState?, held: EventDetail?, now: TimeInterval) -> Double? {
        guard let state, let held, now < state.expiresAt, held.id == state.eventId,
              let status = held.status, EventPriceStreaming.isEligible(status), status == state.status,
              let committed = LiveEventPriceReconciliation.pairedFoldRevision(in: held) else { return nil }
        if let base = state.baseFoldRevision {
            guard held.sport == state.sport, base.rows.count == committed.rows.count,
                  base.covers(committed) else { return nil }
            return state.p
        }
        // A singleton frame cannot stand in for a folded page during transition.
        guard committed.rows.count == 1, let rev = committed.rows[String(state.eventId)] else { return nil }
        return rev > state.baseRev ? nil : state.p
    }

    /// The observation clock of the probability actually displayed (web's
    /// `displayedProbabilityObservedAt`): `committed` whenever the headline
    /// shows committed truth; the preview's own observation time while it
    /// shows one — nil when that is unknown, never the committed clock.
    static func displayedObservedAt(_ state: BlendPreviewState?, held: EventDetail?, now: TimeInterval,
                                    committed: Date?) -> Date? {
        guard displayed(state, held: held, now: now) != nil else { return committed }
        return state?.observedAt
    }

    /// The pushed frames the chart draws, plus the displayed preview at its
    /// observation time (web's `overlayBlendPreviewLine`). A render projection
    /// only: `frames` and the history are never written. The same admission as
    /// the headline; a preview with no observation time, or one not strictly
    /// newer than every committed blend point, leaves the line committed. The
    /// point carries no venue reading, so a page with no served blend line
    /// (`extendingServedSourceSeries`) never draws it.
    static func chartFrames(_ frames: [LiveBlendPoint], history: EventHistoryResponse?,
                            state: BlendPreviewState?, held: EventDetail?, now: TimeInterval) -> [LiveBlendPoint] {
        guard let p = displayed(state, held: held, now: now), let at = state?.observedAt else { return frames }
        let authority = state.flatMap { state in
            state.baseFoldRevision.map { BlendPreviewChartAuthority(eventId: state.eventId, base: $0) }
        }
        if let authority, let history, !chartCoversAuthority(history, authority: authority) { return frames }
        let line = history?.aggregateLine ?? []
        let replacing = history.flatMap { history in
            authority.flatMap { syntheticEdgeToReplace(history, authority: $0, at: at) }
        } != nil
        for stamp in replacing ? Array(line.dropLast()) : line {
            guard let committedAt = stamp.timestamp.asDate, committedAt < at else { return frames }
        }
        if let last = frames.last, last.date >= at { return frames }
        return frames + [LiveBlendPoint(date: at, homeProbability: p, previewAuthority: authority)]
    }

    /// Revision authority wins even if a newer committed pin has an OLDER
    /// observation timestamp. Apply before extension as well as replacement.
    static func chartCoversAuthority(_ history: EventHistoryResponse,
                                     authority: BlendPreviewChartAuthority) -> Bool {
        guard history.eventId == authority.eventId else { return false }
        if let floor = history.historyFoldRevision {
            guard let revision = floor.revision, revision.rows.count == authority.base.rows.count,
                  authority.base.covers(revision) else { return false }
        }
        if history.blendEdgePinned == true {
            guard let revision = history.blendEdgeFoldRevision?.revision,
                  revision.rows.count == authority.base.rows.count,
                  authority.base.covers(revision) else { return false }
        }
        return true
    }

    /// A history read can pin an older observed value at its later read time.
    /// Remove only that proven presentation point, from a render copy; every
    /// real historical point and every venue series remains untouched.
    static func syntheticEdgeToReplace(_ history: EventHistoryResponse,
                                       authority: BlendPreviewChartAuthority, at: Date) -> AggregateLinePoint? {
        guard chartCoversAuthority(history, authority: authority), history.blendEdgePinned == true,
              let observed = history.blendEdgeObservedAt?.asDate, observed < at,
              let revision = history.blendEdgeFoldRevision?.revision,
              revision.rows.count == authority.base.rows.count, authority.base.covers(revision),
              let edge = history.aggregateLine?.last, let edgeAt = edge.timestamp.asDate,
              edgeAt >= at else { return nil }
        for point in (history.aggregateLine ?? []).dropLast() {
            guard let date = point.timestamp.asDate, date < at else { return nil }
        }
        return edge
    }

    /// `event` with the provisional hero overlaid, or `event` itself when no
    /// preview applies — so a page without previews renders unchanged. The
    /// committed clock and revision stay: a preview has neither.
    static func overlay(_ event: EventDetail, _ state: BlendPreviewState?, now: TimeInterval) -> EventDetail {
        guard let p = displayed(state, held: event, now: now), var odds = event.currentOdds else { return event }
        var shown = event
        odds.homeProbability = p
        // Folded authority supplies its own away value, including null. The
        // singleton path retains its existing withheld-away behavior.
        odds.awayProbability = state?.baseFoldRevision != nil
            ? state?.pAway : (odds.awayProbability == nil ? nil : 1 - p)
        // The served whole percents describe the committed pair, not this one;
        // both nil means every reader rounds this pair WHOLE (`duelPercents`).
        odds.homeRenderedPercent = nil
        odds.awayRenderedPercent = nil
        shown.currentOdds = odds
        shown.heroProbability = p
        shown.heroProbabilityAway = state?.baseFoldRevision != nil
            ? state?.pAway : (event.heroProbabilityAway == nil ? nil : 1 - p)
        return shown
    }
}
