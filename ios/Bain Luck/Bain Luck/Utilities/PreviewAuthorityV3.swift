import Foundation

/// #10090 / #11564 — the durable ordering domain of the v3 preview reader
/// (`docs/contracts/dnpl-authority-v3.md`, R2). Redis lost the history that ordered
/// v1/v2 epochs, so a v3 stream names the domain its previews belong to: a
/// durable `incarnation` and the `namespace` UUID it was committed with.
///
/// These are the wire-independent rules both clients share:
///
/// - An incarnation is a canonical decimal STRING from "1" through
///   "9007199254740991": no leading zero, sign, whitespace, fraction, exponent
///   or JSON number. Anything else is refused before it is compared.
/// - Incarnations compare by magnitude. The namespace is an equality guard,
///   never a clock: an equal incarnation with a different namespace is corrupt.
/// - A v3 incarnation is never compared with a legacy scalar epoch.
nonisolated struct PreviewAuthorityV3: Sendable, Equatable {
    let incarnation: Int
    let namespace: String

    /// The largest integer a JSON number carries exactly, as on web.
    static let maxIncarnation = 9_007_199_254_740_991

    init?(incarnation raw: String, namespace: String) {
        guard let value = Self.incarnation(raw), Self.isCanonicalUUID(namespace) else { return nil }
        incarnation = value
        self.namespace = namespace
    }

    /// The incarnation `raw` spells, or nil unless it is canonical and in range.
    static func incarnation(_ raw: String) -> Int? {
        let digits = Array(raw.utf8)
        // 16 digits is the widest in-range value; a longer one cannot be.
        guard (1...16).contains(digits.count), digits.first != UInt8(ascii: "0"),
              digits.allSatisfy({ (UInt8(ascii: "0")...UInt8(ascii: "9")).contains($0) }),
              let value = Int(raw), value <= maxIncarnation else { return nil }
        return value
    }

    /// Lowercase hexadecimal 8-4-4-4-12, any version or variant, never the nil
    /// UUID. `UUID(uuidString:)` also accepts uppercase, which the contract refuses.
    static func isCanonicalUUID(_ raw: String) -> Bool {
        let bytes = Array(raw.utf8)
        guard bytes.count == 36, raw != "00000000-0000-0000-0000-000000000000" else { return false }
        for (i, byte) in bytes.enumerated() {
            if [8, 13, 18, 23].contains(i) {
                guard byte == UInt8(ascii: "-") else { return false }
            } else {
                guard (UInt8(ascii: "0")...UInt8(ascii: "9")).contains(byte)
                        || (UInt8(ascii: "a")...UInt8(ascii: "f")).contains(byte) else { return false }
            }
        }
        return true
    }

    enum Order: Sendable, Equatable {
        /// The same domain: within it, the existing epoch/sequence rules order.
        case same
        /// A newer domain: it retires every preview identity of this one.
        case newer
        /// An older domain, or a contradiction of this one. Refused unchanged.
        case refused
    }

    /// How `other` stands against this, the reader's current domain.
    func order(_ other: PreviewAuthorityV3) -> Order {
        if other.incarnation > incarnation { return .newer }
        if other.incarnation == incarnation, other.namespace == namespace { return .same }
        return .refused
    }
}

/// Whether a JSON message names any key twice in one object. Foundation's
/// `JSONDecoder` keeps the FIRST of two equal keys and web's `JSON.parse` the
/// LAST, so the same bytes would read differently on the two clients; the v3
/// contract refuses them instead. Keys compare after unescaping (`"a"` and
/// `"\u0061"` are one key). Malformed or over-deep input is refused too: the
/// decoder would refuse it anyway, and this never guesses.
nonisolated enum JSONDuplicateKeys {
    /// A preview message nests four objects deep. Deeper input is refused
    /// rather than recursed into.
    static let maxDepth = 16

    /// True only for well-formed JSON with no duplicate key in any object.
    static func isFree(_ data: Data) -> Bool {
        var scanner = Cursor(bytes: Array(data))
        guard scanner.value(depth: 0) else { return false }
        scanner.skipSpace()
        return scanner.index == scanner.bytes.count
    }

    private struct Cursor {
        let bytes: [UInt8]
        var index = 0

        init(bytes: [UInt8]) { self.bytes = bytes }

        mutating func skipSpace() {
            while index < bytes.count, [0x20, 0x09, 0x0A, 0x0D].contains(bytes[index]) { index += 1 }
        }

        mutating func take(_ byte: UInt8) -> Bool {
            skipSpace()
            guard index < bytes.count, bytes[index] == byte else { return false }
            index += 1
            return true
        }

        mutating func value(depth: Int) -> Bool {
            guard depth <= JSONDuplicateKeys.maxDepth else { return false }
            skipSpace()
            guard index < bytes.count else { return false }
            switch bytes[index] {
            case UInt8(ascii: "{"): return object(depth: depth)
            case UInt8(ascii: "["): return array(depth: depth)
            case UInt8(ascii: "\""): return string() != nil
            default: return scalar()
            }
        }

        mutating func object(depth: Int) -> Bool {
            index += 1
            var keys = Set<[UInt16]>()
            if take(UInt8(ascii: "}")) { return true }
            repeat {
                skipSpace()
                guard let key = string(), keys.insert(key).inserted,
                      take(UInt8(ascii: ":")), value(depth: depth + 1) else { return false }
            } while take(UInt8(ascii: ","))
            return take(UInt8(ascii: "}"))
        }

        mutating func array(depth: Int) -> Bool {
            index += 1
            if take(UInt8(ascii: "]")) { return true }
            repeat {
                guard value(depth: depth + 1) else { return false }
            } while take(UInt8(ascii: ","))
            return take(UInt8(ascii: "]"))
        }

        /// A literal or number. Its exact grammar is the decoder's to check;
        /// here it only has to end where a value ends.
        mutating func scalar() -> Bool {
            let start = index
            while index < bytes.count,
                  !",]} \t\n\r".utf8.contains(bytes[index]) { index += 1 }
            return index > start
        }

        /// The string at `index`, unescaped to UTF-16 code units, or nil.
        mutating func string() -> [UInt16]? {
            guard index < bytes.count, bytes[index] == UInt8(ascii: "\"") else { return nil }
            index += 1
            var units: [UInt16] = []
            var run = index
            func flush(_ end: Int) { units += String(decoding: bytes[run..<end], as: UTF8.self).utf16 }
            while index < bytes.count {
                let byte = bytes[index]
                if byte == UInt8(ascii: "\"") {
                    flush(index)
                    index += 1
                    return units
                }
                guard byte >= 0x20 else { return nil }
                guard byte == UInt8(ascii: "\\") else { index += 1; continue }
                flush(index)
                guard index + 1 < bytes.count else { return nil }
                let escape = bytes[index + 1]
                index += 2
                switch escape {
                case UInt8(ascii: "\""), UInt8(ascii: "\\"), UInt8(ascii: "/"): units.append(UInt16(escape))
                case UInt8(ascii: "b"): units.append(0x08)
                case UInt8(ascii: "f"): units.append(0x0C)
                case UInt8(ascii: "n"): units.append(0x0A)
                case UInt8(ascii: "r"): units.append(0x0D)
                case UInt8(ascii: "t"): units.append(0x09)
                case UInt8(ascii: "u"):
                    guard index + 4 <= bytes.count, bytes[index..<index + 4].allSatisfy({ $0.isHexDigit }),
                          let unit = UInt16(String(decoding: bytes[index..<index + 4], as: UTF8.self), radix: 16)
                    else { return nil }
                    units.append(unit)
                    index += 4
                default: return nil
                }
                run = index
            }
            return nil
        }
    }
}

private extension UInt8 {
    nonisolated var isHexDigit: Bool {
        (UInt8(ascii: "0")...UInt8(ascii: "9")).contains(self)
            || (UInt8(ascii: "a")...UInt8(ascii: "f")).contains(self)
            || (UInt8(ascii: "A")...UInt8(ascii: "F")).contains(self)
    }
}

/// One v3 message's outer envelope (`preview_open_v3` or `preview_v3`),
/// validated before anything inside `frame` is read. The keys are exact: an
/// unknown outer or `authority` key refuses the message, while the inner frame
/// keeps its own additive rules. The whole message is at most 16 KiB and names
/// no key twice at any depth.
nonisolated struct PreviewEnvelopeV3: Sendable, Equatable {
    enum Kind: Sendable { case open, preview }

    let authority: PreviewAuthorityV3
    let session: String
    /// The open's membership (1–32 rows, the page row among them); nil on a
    /// preview.
    let members: Set<String>?
    /// The message itself, for the second pass that reads `frame`.
    private let data: Data

    static func decode(_ raw: String, kind: Kind, eventId: Int) -> PreviewEnvelopeV3? {
        guard raw.utf8.count <= BlendPreviewFrame.maxFrameBytes else { return nil }
        let data = Data(raw.utf8)
        guard JSONDuplicateKeys.isFree(data), let outer = try? JSONDecoder().decode(Outer.self, from: data),
              outer.keys == (kind == .open ? Outer.openKeys : Outer.previewKeys),
              outer.version == 3, outer.eventId == eventId, eventId > 0, eventId <= FoldRevision.maxSafeInteger,
              let authority = PreviewAuthorityV3(incarnation: outer.incarnation, namespace: outer.namespace),
              PreviewAuthorityV3.isCanonicalUUID(outer.session) else { return nil }
        var members: Set<String>? = nil
        if kind == .open {
            // Increasing order makes the rows distinct.
            guard let rows = outer.members, (1...BlendPreviewReader.maxRowsV3).contains(rows.count),
                  rows.contains(eventId), zip(rows, rows.dropFirst()).allSatisfy({ $0 < $1 }),
                  rows.allSatisfy({ $0 > 0 && $0 <= FoldRevision.maxSafeInteger }) else { return nil }
            members = Set(rows.map(String.init))
        }
        return PreviewEnvelopeV3(authority: authority, session: outer.session, members: members, data: data)
    }

    /// The inner preview frame, under the existing frame rules. Read only after
    /// the reader has matched this envelope to its active domain and session.
    func frame() -> BlendPreviewFrame? {
        struct Wrapped: Decodable { let frame: BlendPreviewFrame }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return (try? decoder.decode(Wrapped.self, from: data))?.frame
    }

    private struct Key: CodingKey {
        let stringValue: String
        init(_ value: String) { stringValue = value }
        init?(stringValue: String) { self.init(stringValue) }
        var intValue: Int? { nil }
        init?(intValue: Int) { nil }
    }

    private struct Outer: Decodable {
        static let openKeys: Set<String> = ["protocol", "event_id", "authority", "stream_session", "members"]
        static let previewKeys: Set<String> = ["protocol", "event_id", "authority", "stream_session", "frame"]
        let keys: Set<String>
        let version: Int
        let eventId: Int
        let incarnation: String
        let namespace: String
        let session: String
        let members: [Int]?

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Key.self)
            keys = Set(c.allKeys.map(\.stringValue))
            version = try c.decode(Int.self, forKey: Key("protocol"))
            eventId = try c.decode(Int.self, forKey: Key("event_id"))
            let authority = try c.nestedContainer(keyedBy: Key.self, forKey: Key("authority"))
            guard Set(authority.allKeys.map(\.stringValue)) == ["incarnation", "namespace"] else {
                throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath,
                                                       debugDescription: "unknown authority key"))
            }
            incarnation = try authority.decode(String.self, forKey: Key("incarnation"))
            namespace = try authority.decode(String.self, forKey: Key("namespace"))
            session = try c.decode(String.self, forKey: Key("stream_session"))
            members = try c.decodeIfPresent([Int].self, forKey: Key("members"))
        }
    }
}

extension BlendPreview {
    /// The reader after a validated `preview_open_v3`. The open must name the
    /// page's adopted membership exactly; a mismatch activates no session and
    /// moves no fence (the page's membership change reopens the stream). An
    /// open that arrives before the page has adopted any membership is refused
    /// the same way and recorded (`v3OpenAwaitingMembership`), because the
    /// first adoption is not a change: it reopens the stream instead
    /// (`membershipReopens`).
    ///
    /// - First entry, or a NEWER incarnation: every preview identity of the old
    ///   domain is retired (`clearingPreviewIdentity`); committed floors —
    ///   retired members' included — membership, the visit's row count and
    ///   saturation stay. Old-domain tuples never order the new one.
    /// - The same domain under a new session: the display is withdrawn and the
    ///   fences, orders and first-seen deadlines stay, so a new session cannot
    ///   revive or renew a tuple.
    /// - The exact active session again: nothing changes.
    /// - An older incarnation, or the same one under another namespace: refused.
    static func readerOpenedV3(_ reader: BlendPreviewReader, _ open: PreviewEnvelopeV3) -> BlendPreviewReader {
        guard let members = open.members, !reader.evidenceSaturated else { return reader }
        guard reader.authorityMembers != nil else {
            var next = reader
            next.v3OpenAwaitingMembership = true
            return next
        }
        guard reader.authorityMembers == members else { return reader }
        var next: BlendPreviewReader
        switch reader.v3Authority.map({ $0.order(open.authority) }) ?? .newer {
        case .refused:
            return reader
        case .same:
            guard reader.v3Session != open.session else { return reader }
            next = readerReset(reader)
        case .newer:
            next = clearingPreviewIdentity(reader)
        }
        next.v3Authority = open.authority
        next.v3Session = open.session
        next.v3Members = members
        // The folded composition's `fold_session` is this stream's session.
        next.foldSession = open.session
        next.foldMembers = members
        next.v3Rows.formUnion(members)
        if next.v3Rows.count > BlendPreviewReader.maxRowsV3 {
            // COVERAGE LIMIT, as `evidenceSaturated`: committed truth shows.
            next.held = nil
            next.evidenceSaturated = true
        }
        return next
    }

    /// Whether adopting `members` closes the stream so the page reopens it: a
    /// changed membership (`membershipChanges`), or the first membership after
    /// this connection's open was refused for want of one — that refused open
    /// is never replayed, and without a reopen the connection would carry no
    /// preview until it ends.
    static func membershipReopens(_ reader: BlendPreviewReader, members: Set<String>) -> Bool {
        guard !members.isEmpty else { return false }
        return membershipChanges(reader, members: members) || reader.v3OpenAwaitingMembership
    }

    /// `reader` with every preview identity retired and every committed floor kept.
    private static func clearingPreviewIdentity(_ reader: BlendPreviewReader) -> BlendPreviewReader {
        var next = readerReset(reader)
        next.epoch = -1
        next.originFences = [:]
        next.legacyOrders = [:]
        next.foldedSequence = nil
        next.enteredV2 = false
        next.retiredMembers = reader.retiredMembers.map { .init(row: $0.row, fence: nil, floor: $0.floor) }
        return next
    }

    /// The reader after a `preview_v3` arrives at `now`. The envelope must carry
    /// the active domain and session before its frame is read; then the shape
    /// must match the open's membership — the singleton shape for one row,
    /// folded v2 for two or more, on this session and this exact membership —
    /// and the existing singleton/folded rules decide (`readerAfter`).
    static func readerAfterV3(_ reader: BlendPreviewReader, _ envelope: PreviewEnvelopeV3,
                              eventId: Int, now: TimeInterval) -> BlendPreviewReader {
        guard envelope.members == nil, !reader.evidenceSaturated,
              let authority = reader.v3Authority, authority == envelope.authority,
              let session = reader.v3Session, session == envelope.session,
              let members = reader.v3Members, let frame = envelope.frame(), frame.eventId == eventId else {
            return reader
        }
        if members.count == 1 {
            guard frame.foldedVersion == nil, frame.baseFoldRevision == nil, frame.originEventId == nil else {
                return reader
            }
        } else {
            guard frame.foldedVersion == 2, frame.foldSession == session,
                  frame.baseFoldRevision.map({ Set($0.rows.keys) == members }) ?? false else { return reader }
        }
        return readerAfter(reader, frame, eventId: eventId, now: now)
    }
}
