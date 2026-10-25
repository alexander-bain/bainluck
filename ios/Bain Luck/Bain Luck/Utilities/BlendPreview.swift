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
/// Per-origin authority; epochs from different event rows are never compared.
nonisolated struct FoldOriginAuthority: Decodable, Sendable, Equatable {
    enum State: String, Decodable, Sendable { case pending, revoked, expired, committed }
    let epoch: Int
    let seq: Int
    let state: State
    let ttlMs: Int?

    private enum CodingKeys: String, CodingKey { case epoch, seq, state, ttlMs }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        epoch = try c.decode(Int.self, forKey: .epoch)
        seq = try c.decode(Int.self, forKey: .seq)
        state = try c.decode(State.self, forKey: .state)
        ttlMs = try c.decodeIfPresent(Int.self, forKey: .ttlMs)
        guard (0...FoldRevision.maxSafeInteger).contains(epoch),
              (0...FoldRevision.maxSafeInteger).contains(seq),
              state == .pending
                ? (ttlMs.map { (0...FoldRevision.maxSafeInteger).contains($0) } ?? false)
                : !c.contains(.ttlMs) else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath,
                                                   debugDescription: "invalid origin authority"))
        }
    }
}

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
    var foldedVersion: Int? = nil
    var foldSession: String? = nil
    var foldSeq: Int? = nil
    var originAuthority: [String: FoldOriginAuthority]? = nil

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
        case kind, epoch, seq, baseRev, ttlMs, throughSeq, foldedVersion, originEventId, baseFoldRevision, foldSession, foldSeq, originAuthority
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
        foldedVersion = try preview.decodeIfPresent(Int.self, forKey: .foldedVersion)
        // v2 has independent origin authority; scalar order has no meaning.
        epoch = foldedVersion == 2 ? 0 : try preview.decode(Int.self, forKey: .epoch)
        seq = foldedVersion == 2 ? 0 : try preview.decode(Int.self, forKey: .seq)
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
            || preview.contains(.foldSession) || preview.contains(.foldSeq) || preview.contains(.originAuthority)
        if foldedVersion != 2 && (preview.contains(.foldSession) || preview.contains(.foldSeq)
                                  || preview.contains(.originAuthority)) {
            throw refuse("v2 authority cannot fall back to legacy ordering")
        }
        if foldedVersion == 2 {
            guard Self.safe(eventId), eventId > 0,
                  let vector = BlendPreview.validRevision(
                    try preview.decode([String: Int].self, forKey: .baseFoldRevision)),
                  vector.rows.count >= 2, vector.rows[String(eventId)] != nil,
                  Self.safe(ttlMs) else {
                throw refuse("invalid folded v2 base")
            }
            baseFoldRevision = vector
            pAway = try c.decodeIfPresent(Double.self, forKey: .pAway)
            sport = try c.decodeIfPresent(String.self, forKey: .sport)
            foldSession = try preview.decode(String.self, forKey: .foldSession)
            foldSeq = try preview.decode(Int.self, forKey: .foldSeq)
            originAuthority = try preview.decode([String: FoldOriginAuthority].self, forKey: .originAuthority)
            guard let session = foldSession, BlendPreview.validSession(session), Self.safe(foldSeq),
                  let authority = originAuthority, (1...2).contains(authority.count),
                  authority.keys.allSatisfy({ vector.rows[$0] != nil }),
                  pAway.map({ $0.isFinite && (0...1).contains($0) }) ?? true else {
                throw refuse("invalid folded v2 authority")
            }
            let active = authority.values.filter { $0.state == .pending }
            if kind == .blend {
                guard c.contains(.pAway), c.contains(.sport), !active.isEmpty,
                      let status, EventPriceStreaming.isEligible(status),
                      let p, p.isFinite, (0...1).contains(p),
                      let ttlMs, ttlMs > 0, active.allSatisfy({ ttlMs <= $0.ttlMs! }) else {
                    throw refuse("unprintable folded v2 blend")
                }
            } else {
                // A cold committed base can withdraw the whole display while
                // a sibling still owns pending authority. It supplies no price;
                // retain that sibling's original deadline for later composition.
                guard c.contains(.p), p == nil, let ttlMs,
                      active.isEmpty ? ttlMs == 0 : active.allSatisfy({ ttlMs <= $0.ttlMs! }) else {
                    throw refuse("invalid folded v2 withdrawal")
                }
            }
            return
        } else if folded {
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
    /// The fence floor: frames from a lower epoch are refused. -1 before any.
    var epoch: Int
    var floors: FoldRevision? = nil
    /// Retained across expiry, revoke and reconnect; a replay cannot renew TTL.
    /// Consumed by the first ACCEPTED v2 frame (`readerAfterV2`), which merges
    /// it into its origin's fence: after migration the fence is the record.
    var foldedSequence: FoldedSequence? = nil
    /// The legacy path's own order, per row (f211): the highest tuple each
    /// row's v1 frames reached here — accepted, or named by a revoke. A v1
    /// frame at or below its row's order is a replay (v1 never replays) and
    /// is refused; rows never order one another. `foldedSequence` stays the
    /// latest of them, for the v1→v2 bridge. Read by the v1 path only and
    /// dropped by the first accepted v2 frame, like `foldedSequence`.
    var legacyOrders: [String: FoldedSequence] = [:]
    /// A fold has a handful of rows. Past this many distinct legacy origins a
    /// new one is refused rather than any order forgotten (f211).
    static let maxOrigins = 32
    var enteredV2 = false
    var foldSession: String? = nil
    var foldSeq = -1
    var sessionOrigins: Set<String> = []
    var originFences: [String: OriginFence] = [:]
    var foldMembers: Set<String>? = nil
    /// The page's authoritative fold membership, from its adopted detail
    /// (`readerAfterMembership`). A change of it is a different fold.
    var authorityMembers: Set<String>? = nil
    /// Rows the page stopped folding, with the fence and commit floor they
    /// left behind, oldest first: a row that returns in a later membership — a
    /// cached detail flapping back, or a duplicate rejoining — gets its
    /// evidence back, so it cannot resurrect an identity, renew a lease or
    /// admit an uncovered base across the flap. NEVER evicted: safety evidence
    /// that is forgotten is safety that is gone (a returning row would read as
    /// unseen). Past `maxRetiredMembers` distinct rows the reader saturates
    /// instead (`evidenceSaturated`). There is no fixed count this list stays
    /// under: every row leaving in one transition is retired before the
    /// capacity check, so at saturation it holds at most `maxRetiredMembers`
    /// previously retired rows PLUS every row that left together in that
    /// transition — `maxRetiredMembers + 1` only when one row left — and then
    /// freezes. The rows that can leave at once are the distinct rows this
    /// visit recorded a fence or a commit floor for, which nothing here caps.
    var retiredMembers: [RetiredMember] = []
    /// How many distinct retired rows one visit follows before saturating. A
    /// page's fold is a few duplicate rows of one game; a visit that retires
    /// more than this many distinct rows is churn this reader does not follow.
    static let maxRetiredMembers = 8
    /// COVERAGE LIMIT, not continuity. Set when a membership change leaves
    /// more than `maxRetiredMembers` distinct retired rows: no evidence is
    /// dropped, and the reader admits no further preview — v1 or v2 — until
    /// navigation starts a new visit. The page shows committed truth
    /// meanwhile; DNPL coverage is lost for the rest of the visit. Reset,
    /// resync and later membership changes keep it, and move no evidence.
    var evidenceSaturated = false
    /// Whether this visit has folded: an authoritative membership of two or
    /// more rows, or folded authority accepted. After a fold, the page row's
    /// singleton frames are admitted only under its own recorded fence
    /// (`readerAfter`); a visit that never folded keeps the legacy singleton
    /// display rules exactly as they were.
    var hasFolded = false
    /// #11564 — the durable ordering domain this visit entered through a
    /// validated `preview_open_v3` (`PreviewAuthorityV3`), or nil before one.
    /// Only a newer incarnation replaces it; nothing ever lowers it.
    var v3Authority: PreviewAuthorityV3? = nil
    /// The active v3 `stream_session`. A transport open, close or reconnect
    /// ends it (`readerReset`); a frame is admitted only under it.
    var v3Session: String? = nil
    /// The membership the active v3 open named; equal to the page's adopted
    /// membership when it was accepted.
    var v3Members: Set<String>? = nil
    /// Every row identity a v3 open named this visit. A new incarnation never
    /// resets it; past `maxRowsV3` the visit saturates.
    var v3Rows: Set<String> = []
    static let maxRowsV3 = 32
    /// This connection's `preview_open_v3` was refused because the page had
    /// no adopted membership yet (`readerOpenedV3`). The open is never
    /// replayed: the first membership the page adopts reopens the stream
    /// instead (`membershipReopens`). The connection ending clears it.
    var v3OpenAwaitingMembership = false
    /// Whether the page row's singleton frames order against its recorded
    /// fence: after a fold, and always in the v3 domain, where a new session
    /// can neither revive an equal tuple nor renew its first-seen deadline.
    var fencesOwnRow: Bool { hasFolded || v3Authority != nil }

    struct OriginFence: Sendable, Equatable {
        let epoch: Int
        let seq: Int
        let retired: Bool
        let deadline: TimeInterval?
    }

    struct FoldedSequence: Sendable, Equatable {
        let epoch: Int
        let seq: Int
        let originEventId: Int
    }

    struct RetiredMember: Sendable, Equatable {
        let row: String
        let fence: OriginFence?
        let floor: Int?
        /// The row's v1 order once its carried lease was spent while it was
        /// away (`readerAfter`); it returns to `legacyOrders` with the row.
        var legacyOrder: FoldedSequence? = nil
    }

    static let empty = BlendPreviewReader(held: nil, epoch: -1)
}

/// Proof attached only to the disposable folded chart endpoint. The chart
/// checks it against its own served history before removing a synthetic pin.
nonisolated struct BlendPreviewChartAuthority: Sendable, Equatable {
    let eventId: Int
    let base: FoldRevision
}

nonisolated enum BlendPreview {
    static func validSession(_ value: String) -> Bool {
        !value.isEmpty && value.utf8.count <= 128
    }

    /// Disconnect/navigation between connections withdraws display. Origin
    /// fences/deadlines survive, while a new open may establish a new session.
    static func readerReset(_ reader: BlendPreviewReader) -> BlendPreviewReader {
        var next = reader
        next.held = nil
        next.foldSession = nil
        next.foldSeq = -1
        next.sessionOrigins = []
        next.v3Session = nil
        next.v3OpenAwaitingMembership = false
        return next
    }

    static func readerOpened(_ reader: BlendPreviewReader, raw: String, eventId: Int) -> BlendPreviewReader {
        struct Packet: Decodable { let eventId: Int; let foldSession: String }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard reader.foldSession == nil, raw.utf8.count <= BlendPreviewFrame.maxFrameBytes,
              let data = raw.data(using: .utf8), let packet = try? decoder.decode(Packet.self, from: data),
              packet.eventId == eventId, validSession(packet.foldSession) else { return reader }
        var next = reader
        next.foldSession = packet.foldSession
        return next
    }

    /// Whether `members` changes the page's authoritative fold membership. The
    /// first membership a visit learns is not a change.
    static func membershipChanges(_ reader: BlendPreviewReader, members: Set<String>) -> Bool {
        reader.authorityMembers.map { $0 != members } ?? false
    }

    /// The reader after the page's authoritative detail folds `members`. The
    /// same membership records nothing new. A changed membership is a
    /// different fold, and the old fold's authority can neither hold it out
    /// nor get back in: the held preview is withdrawn and the session dropped
    /// (the owner reopens the stream, whose server-side composition is bound
    /// to the membership it opened with); members the page no longer folds
    /// lose their fences and commit floors — into retired evidence
    /// (`retiredMembers`) that a returning row gets back and that is never
    /// evicted — and a removed origin takes its legacy order AND the scalar
    /// epoch that was its domain with it, leaving that order behind as its
    /// fence; surviving members keep theirs — identity, retirement and
    /// first-seen deadline — so the new fold cannot renew or resurrect them.
    /// Snapshots of the old membership are refused (`foldMembers`). The page's
    /// own row carries its singleton authority, recorded at acceptance
    /// (`readerAfter`), into the fold; a fold-down to the page row alone hands
    /// the v1 order back to that row as its own fence, under which the
    /// singleton path resumes. Retiring more distinct rows than
    /// `maxRetiredMembers` saturates the reader (`evidenceSaturated`) rather
    /// than forgetting any of them. Ordinary disconnect and resync are not
    /// membership changes and go through `readerReset` as before.
    static func readerAfterMembership(_ reader: BlendPreviewReader, members: Set<String>) -> BlendPreviewReader {
        guard !members.isEmpty else { return reader }
        var next = reader
        next.authorityMembers = members
        next.v3OpenAwaitingMembership = false
        if members.count >= 2 { next.hasFolded = true }
        guard membershipChanges(reader, members: members) else { return next }
        next = readerReset(next)
        next.foldMembers = members
        // Saturated (coverage limit): nothing is admitted any more, so no
        // evidence moves; the old fold's display and session still go.
        guard !reader.evidenceSaturated else { return next }
        var fences = reader.originFences.filter { members.contains($0.key) }
        var floors = (reader.floors?.rows ?? [:]).filter { members.contains($0.key) }
        var leaving = reader.originFences
        if let order = reader.foldedSequence {
            // The v1 order is one origin's identity (the same ledger tuple
            // `readerAfterV2` seeds a fence from). A removed origin leaves it
            // behind as its fence, with the scalar epoch that was its domain;
            // folded down to the page row alone, it is that row's own fence.
            let origin = String(order.originEventId)
            let live = reader.held.map {
                $0.originEventId == order.originEventId && $0.epoch == order.epoch && $0.seq == order.seq
            } ?? false
            let fence = ownFence(reader.originFences[origin], epoch: order.epoch, seq: order.seq,
                                 retired: !live, deadline: live ? reader.held?.expiresAt : nil)
            if !members.contains(origin) {
                leaving[origin] = fence
                next.foldedSequence = nil
                next.epoch = -1
            } else if members.count == 1 {
                fences[origin] = fence
                next.foldedSequence = nil
            }
        } else if reader.epoch >= 0 {
            // With no v1 order, the scalar epoch was the page row's singleton
            // domain — recorded as its own fence at acceptance (`readerAfter`).
            // It orders nothing in the fold the page joins.
            next.epoch = -1
        }
        // Every row's legacy order crosses the boundary on the same rule as
        // the latest one above. A removed row leaves it as retired evidence;
        // folded down, or still on display, it becomes the row's fence (a
        // same tuple keeps its first-seen deadline); a surviving row whose
        // tuple is no longer shown keeps its order, so a replay of it stays
        // refused on the legacy path while the fence v2 reads is untouched.
        let shownRow = reader.held.flatMap { held in
            held.originEventId.map(String.init) ?? (held.baseFoldRevision == nil ? String(held.eventId) : nil)
        }
        var orders = reader.legacyOrders
        for (row, order) in reader.legacyOrders {
            let live = shownRow == row && reader.held?.epoch == order.epoch && reader.held?.seq == order.seq
            if !members.contains(row) {
                leaving[row] = ownFence(leaving[row], epoch: order.epoch, seq: order.seq,
                                        retired: !live, deadline: live ? reader.held?.expiresAt : nil)
                orders[row] = nil
            } else if members.count == 1 || live {
                fences[row] = ownFence(fences[row], epoch: order.epoch, seq: order.seq,
                                       retired: !live, deadline: live ? reader.held?.expiresAt : nil)
                orders[row] = nil
            }
        }
        next.legacyOrders = orders
        var retired = reader.retiredMembers.filter { !members.contains($0.row) }
        for row in Set(leaving.keys).union(reader.floors.map { Set($0.rows.keys) } ?? [])
        where !members.contains(row) {
            let prior = retired.first { $0.row == row }
            retired.removeAll { $0.row == row }
            let fence = leaving[row].map {
                ownFence(prior?.fence, epoch: $0.epoch, seq: $0.seq, retired: $0.retired, deadline: $0.deadline)
            } ?? prior?.fence
            let floor = [prior?.floor, reader.floors?.rows[row]].compactMap { $0 }.max()
            retired.append(.init(row: row, fence: fence, floor: floor, legacyOrder: prior?.legacyOrder))
        }
        if retired.count > BlendPreviewReader.maxRetiredMembers {
            // Never forget safety evidence. COVERAGE LIMIT: this visit admits
            // no further preview (`readerAfter`); committed truth shows. Every
            // row that left in this transition is already in `retired`, so
            // the list can hold more than `maxRetiredMembers + 1` entries here
            // (see `retiredMembers`); it does not grow again after this.
            next.evidenceSaturated = true
        }
        for entry in reader.retiredMembers where members.contains(entry.row) {
            if fences[entry.row] == nil, let fence = entry.fence { fences[entry.row] = fence }
            if let floor = entry.floor { floors[entry.row] = max(floors[entry.row] ?? 0, floor) }
            if let order = entry.legacyOrder { next.legacyOrders[entry.row] = newer(next.legacyOrders[entry.row], order) }
        }
        next.originFences = fences
        next.floors = FoldRevision(floors)
        next.retiredMembers = retired
        return next
    }

    /// `state` with its lifetime capped at `deadline`, when that is earlier.
    private static func capped(_ state: BlendPreviewState, at deadline: TimeInterval) -> BlendPreviewState {
        guard deadline < state.expiresAt else { return state }
        return BlendPreviewState(eventId: state.eventId, epoch: state.epoch, seq: state.seq, baseRev: state.baseRev,
                                 p: state.p, status: state.status, expiresAt: deadline,
                                 observedAt: state.observedAt, baseFoldRevision: state.baseFoldRevision,
                                 originEventId: state.originEventId, pAway: state.pAway, sport: state.sport)
    }

    /// A row's recorded fence merged with one more piece of legacy evidence —
    /// the page row's singleton frame, or an origin's v1 order at a membership
    /// boundary or the v1→v2 bridge: identity only moves forward, a same tuple
    /// keeps its first-seen deadline and its retirement, a newer tuple
    /// replaces it, and older evidence never overwrites a newer fence.
    private static func ownFence(_ old: BlendPreviewReader.OriginFence?, epoch: Int, seq: Int,
                                 retired: Bool, deadline: TimeInterval?) -> BlendPreviewReader.OriginFence {
        guard let old, epoch <= old.epoch else {
            return .init(epoch: epoch, seq: seq, retired: retired, deadline: deadline)
        }
        if epoch < old.epoch || seq < old.seq { return old }
        if seq == old.seq {
            return .init(epoch: epoch, seq: seq, retired: old.retired || retired,
                         deadline: [old.deadline, deadline].compactMap { $0 }.min())
        }
        return .init(epoch: epoch, seq: seq, retired: retired, deadline: deadline)
    }

    /// The v1 order a row's fence stands for while it holds a carried lease
    /// (pending, with a first-seen deadline), or nil.
    private static func lease(_ fence: BlendPreviewReader.OriginFence, row: String) -> BlendPreviewReader.FoldedSequence? {
        guard !fence.retired, fence.deadline != nil, let origin = Int(row) else { return nil }
        return .init(epoch: fence.epoch, seq: fence.seq, originEventId: origin)
    }

    /// The later of two v1 orders of one row.
    private static func newer(_ old: BlendPreviewReader.FoldedSequence?,
                              _ order: BlendPreviewReader.FoldedSequence) -> BlendPreviewReader.FoldedSequence {
        guard let old, old.epoch > order.epoch || (old.epoch == order.epoch && old.seq >= order.seq) else { return order }
        return old
    }

    /// All validation precedes fence mutation. A bad snapshot cannot poison
    /// future ordering or discard the sibling's admitted contribution.
    private static func readerAfterV2(_ reader: BlendPreviewReader, _ frame: BlendPreviewFrame,
                                     eventId: Int, now: TimeInterval) -> BlendPreviewReader {
        guard frame.eventId == eventId, let session = reader.foldSession,
              frame.foldSession == session, let sequence = frame.foldSeq, sequence > reader.foldSeq,
              let base = frame.baseFoldRevision, let authority = frame.originAuthority else { return reader }
        let members = Set(base.rows.keys)
        // Election authority is per session: every origin this session has
        // shown must be accounted for in each frame. Fences are per visit and
        // per row: a membership of three or more rows can elect a different
        // pair across sessions (the server disables a session whose owner set
        // changes and a fresh stream elects anew), so the dictionary is bounded
        // by the membership, not by the two elected origins — every row's fence
        // stays and keeps ordering that row.
        guard reader.foldMembers.map({ $0 == members }) ?? true,
              reader.floors.map({ base.covers($0) }) ?? true,
              reader.sessionOrigins.isSubset(of: Set(authority.keys)) else { return reader }
        var fences = reader.originFences
        // Upgrading this visit from v1 must not forget its origin's accepted
        // authority, even though v2 never uses the old global epoch ordering.
        // The v1 order is MERGED into the row's existing fence, never imported
        // only when none exists: the fence a returning origin gets back
        // (`readerAfterMembership`) can be older than the v1 order accepted
        // since, or than that order's revocation, and a snapshot validated
        // against the stale fence alone would admit an identity the v1 path
        // had already moved past. `ownFence` keeps the merge monotonic:
        // identity only moves forward, a same tuple keeps its first-seen
        // deadline and stays retired once retired, and a newer fence is never
        // overwritten by older evidence. The merge is the migration: the first
        // ACCEPTED v2 frame consumes the order (below), so it is read exactly
        // once, against the display as it stood before v2 — never again
        // against a v2 composite or a reset, which would be mistaken for the
        // legacy tuple having retired. Until a frame is accepted the order
        // stays, and every attempt reads the current display.
        if let prior = reader.foldedSequence {
            let origin = String(prior.originEventId)
            let held = reader.held.flatMap { value -> BlendPreviewState? in
                value.originEventId == prior.originEventId && value.epoch == prior.epoch
                    && value.seq == prior.seq ? value : nil
            }
            fences[origin] = ownFence(fences[origin], epoch: prior.epoch, seq: prior.seq,
                                      retired: held == nil, deadline: held?.expiresAt)
        }
        guard Set(fences.keys).isSubset(of: members) else { return reader }
        var deadline = now + Double(frame.ttlMs ?? 0) / 1000
        for (origin, value) in authority {
            let old = fences[origin]
            if let old, value.epoch < old.epoch || (value.epoch == old.epoch && value.seq < old.seq) {
                return reader
            }
            let same = old.map { $0.epoch == value.epoch && $0.seq == value.seq } ?? false
            var expires: TimeInterval? = nil
            if value.state == .pending {
                guard !(same && old?.retired == true), let ttl = value.ttlMs else { return reader }
                expires = now + Double(ttl) / 1000
                if same, let prior = old?.deadline { expires = min(expires!, prior) }
                // An expired tuple stays expired, including across reconnects.
                guard let expires, frame.kind == .revoke || expires > now else { return reader }
                deadline = min(deadline, expires)
            }
            fences[origin] = .init(epoch: value.epoch, seq: value.seq,
                                   retired: value.state != .pending, deadline: expires ?? (same ? old?.deadline : nil))
        }
        var next = reader
        next.enteredV2 = true
        next.hasFolded = true
        next.foldMembers = members
        next.foldSeq = sequence
        next.sessionOrigins.formUnion(authority.keys)
        next.originFences = fences
        // The legacy order is consumed by the migration (an accepted frame —
        // a refused blend below still returns `reader`, order intact): its
        // identity, deadline and retirement now live in its origin's fence,
        // which every later frame, reset, reconnect and membership boundary
        // reads instead.
        next.foldedSequence = nil
        next.legacyOrders = [:]
        if frame.kind == .revoke { next.held = nil; return next }
        guard let p = frame.p, let rev = base.rows[String(eventId)], deadline > now else { return reader }
        next.held = BlendPreviewState(eventId: eventId, epoch: 0, seq: sequence, baseRev: rev,
                                     p: p, status: frame.status, expiresAt: deadline,
                                     observedAt: frame.displayObservedAt, baseFoldRevision: base,
                                     pAway: frame.pAway, sport: frame.sport)
        return next
    }

    /// Canonical positive row identifiers and safe integer revisions only.
    static func validRevision(_ rows: [String: Int]) -> FoldRevision? {
        guard rows.keys.allSatisfy({ key in
            guard let id = Int(key), id > 0, id <= FoldRevision.maxSafeInteger else { return false }
            return String(id) == key
        }) else { return nil }
        return FoldRevision(rows)
    }

    /// Commit evidence withdraws an uncovered folded preview immediately; it
    /// never creates a probability, observation timestamp or renewed lifetime.
    static func readerAfterCommitFloor(_ reader: BlendPreviewReader, _ floor: FoldRevision?) -> BlendPreviewReader {
        var next = reader
        guard let floor else { next.held = nil; return next }
        var rows = reader.floors?.rows ?? [:]
        for (id, rev) in floor.rows {
            // A row the page no longer folds cannot withhold the current
            // fold; its floor is kept as that row's retired evidence, for
            // its return (`readerAfterMembership`).
            if let members = reader.authorityMembers, !members.contains(id) {
                guard !reader.evidenceSaturated else { continue }
                if let i = next.retiredMembers.firstIndex(where: { $0.row == id }) {
                    let entry = next.retiredMembers[i]
                    next.retiredMembers[i] = .init(row: id, fence: entry.fence, floor: max(entry.floor ?? 0, rev),
                                                   legacyOrder: entry.legacyOrder)
                } else {
                    next.retiredMembers.append(.init(row: id, fence: nil, floor: rev))
                    if next.retiredMembers.count > BlendPreviewReader.maxRetiredMembers { next.evidenceSaturated = true }
                }
                continue
            }
            rows[id] = max(rows[id] ?? 0, rev)
        }
        next.floors = FoldRevision(rows)
        if let base = reader.held?.baseFoldRevision, let floors = next.floors, !base.covers(floors) {
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
    /// row is fenced out; a higher one voids the preview that row's older epoch
    /// showed first. Rows never order one another: a folded frame orders
    /// against its origin's legacy order and fence; the scalar epoch is the
    /// page row's alone (f211).
    static func readerAfter(_ reader: BlendPreviewReader, _ frame: BlendPreviewFrame,
                            eventId: Int, now: TimeInterval) -> BlendPreviewReader {
        // COVERAGE LIMIT (`evidenceSaturated`): this visit admits nothing more.
        guard !reader.evidenceSaturated else { return reader }
        if frame.foldedVersion == 2 { return readerAfterV2(reader, frame, eventId: eventId, now: now) }
        let own = String(eventId)
        let singleton = frame.baseFoldRevision == nil && frame.originEventId == nil
        // The frame's row: its origin when folded, the page when singleton.
        let row = frame.originEventId.map { String($0) } ?? own
        guard frame.eventId == eventId, row != own || frame.epoch >= reader.epoch else { return reader }
        // After v2 authority, a legacy frame is a protocol downgrade — except
        // the page row's own singleton frames once the authoritative
        // membership is that row alone: the stream's composition is singleton
        // again, and they resume under the row's own fence (below).
        if reader.enteredV2 {
            guard singleton, reader.authorityMembers == Set([own]) else { return reader }
        }
        // A legacy frame speaks for one row's ledger: its origin when folded,
        // the page when singleton. An origin the page no longer folds has no
        // say — not even a bare revoke, which would otherwise move the scalar
        // fence into a removed row's domain.
        if let origin = frame.originEventId, let members = reader.authorityMembers,
           !members.contains(String(origin)) {
            return reader
        }
        // A folded frame for a membership the page no longer folds is refused
        // outright, as on the v2 path (`readerAfterMembership`).
        if let base = frame.baseFoldRevision, let members = reader.foldMembers, Set(base.rows.keys) != members {
            return reader
        }
        guard reader.legacyOrders[row] != nil || reader.legacyOrders.count < BlendPreviewReader.maxOrigins else {
            return reader
        }
        if !singleton || reader.fencesOwnRow, let order = reader.legacyOrders[row],
           frame.epoch < order.epoch || (frame.epoch == order.epoch && frame.seq <= order.seq) {
            return reader
        }
        if reader.foldedSequence != nil {
            // A folded withdrawal speaks only for a row this visit accepted.
            if frame.kind == .revoke, !singleton, reader.legacyOrders[row] == nil,
               reader.originFences[row] == nil { return reader }
            if frame.kind == .revoke, singleton { return reader }
            // Once this visit has seen folded authority, unmarked singleton
            // blends cannot re-enter its ordering domain after a reset.
            if frame.kind == .blend, frame.baseFoldRevision == nil { return reader }
        }
        // The row's recorded fence — its singleton authority, the order a
        // fold left it, or the identity it returned with — orders this blend:
        // identity only moves forward, a retired or expired tuple does not
        // come back, and a same tuple keeps its first-seen deadline. A visit
        // that never folded keeps the legacy singleton display rules unchanged.
        var cap: TimeInterval? = nil
        let fenced = frame.originEventId.map { String($0) } ?? (reader.fencesOwnRow ? own : nil)
        if frame.kind == .blend, let fenced, let fence = reader.originFences[fenced] {
            if frame.epoch < fence.epoch || (frame.epoch == fence.epoch && frame.seq < fence.seq) { return reader }
            if frame.epoch == fence.epoch, frame.seq == fence.seq {
                guard !fence.retired else { return reader }
                cap = fence.deadline
                if let cap, cap <= now { return reader }
            }
        }
        var next = reader
        if row == own { next.epoch = frame.epoch }
        // A higher epoch voids only the preview its own row's older epoch showed.
        let held = reader.held.flatMap { state in
            (state.originEventId.map { String($0) } ?? own) == row && frame.epoch > state.epoch ? nil : state
        }
        if let origin = frame.originEventId, frame.baseFoldRevision != nil || reader.foldedSequence != nil {
            next.foldedSequence = .init(epoch: frame.epoch, seq: frame.seq, originEventId: origin)
            next.hasFolded = true
        }
        if frame.kind == .revoke || frame.originEventId != nil {
            next.legacyOrders[row] = .init(epoch: frame.epoch, seq: max(frame.seq, frame.throughSeq ?? 0),
                                           originEventId: frame.originEventId ?? eventId)
        }
        // A carried lease — a tuple shown at a membership boundary, kept with
        // its first-seen deadline (`readerAfterMembership`) — only continues
        // the display that boundary interrupted. v1 shows one frame at a time,
        // so a later accepted blend of another row supersedes it: the lease is
        // spent into that row's v1 order — a member's in `legacyOrders`, an
        // away row's in its retired evidence, restored on its return — and a
        // replay of the tuple is refused on the legacy path (f211). The fence
        // v2 reads keeps the lease. After v2 authority the fences are v2's.
        if frame.kind == .blend, !reader.enteredV2 {
            for (other, fence) in reader.originFences where other != row {
                if let order = lease(fence, row: other) { next.legacyOrders[other] = newer(next.legacyOrders[other], order) }
            }
            next.retiredMembers = next.retiredMembers.map { entry in
                guard entry.row != row, let order = entry.fence.flatMap({ lease($0, row: entry.row) }) else { return entry }
                return .init(row: entry.row, fence: entry.fence, floor: entry.floor,
                             legacyOrder: newer(entry.legacyOrder, order))
            }
        }
        if let base = frame.baseFoldRevision, let floors = reader.floors, !base.covers(floors) {
            next.held = nil
        } else if singleton, frame.kind == .blend, reader.fencesOwnRow, let floor = reader.floors?.rows[own],
                  let baseRev = frame.baseRev, baseRev < floor {
            // A commit floor the fold taught withdraws a singleton composed
            // below it, as it withdraws an uncovered folded base.
            next.held = nil
        } else {
            next.held = previewAfter(held, frame, eventId: eventId, now: now)
            if let cap, let state = next.held, state.epoch == frame.epoch, state.seq == frame.seq {
                next.held = capped(state, at: cap)
            }
        }
        // The page's own row records its singleton authority at acceptance,
        // not off the display: a reset clears the display, and the identity,
        // first-seen deadline and retirement must survive it for the fold this
        // row may later join to compare against (`readerAfterV2`). The legacy
        // display rules above are unchanged by this record.
        if frame.baseFoldRevision == nil, frame.originEventId == nil {
            let own = String(eventId)
            switch frame.kind {
            case .blend:
                if let state = next.held, state.epoch == frame.epoch, state.seq == frame.seq {
                    next.originFences[own] = ownFence(reader.originFences[own], epoch: state.epoch, seq: state.seq,
                                                      retired: false, deadline: state.expiresAt)
                    next.legacyOrders[own] = .init(epoch: state.epoch, seq: state.seq, originEventId: eventId)
                }
            case .revoke:
                if let through = frame.throughSeq {
                    next.originFences[own] = ownFence(reader.originFences[own], epoch: frame.epoch, seq: through,
                                                      retired: true, deadline: nil)
                }
            }
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
            // Another row's withdrawal says nothing about this preview.
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
