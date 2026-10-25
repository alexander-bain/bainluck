import Foundation

/// #10090 / #11564 — the durable ordering domain of the v3 preview reader
/// (`docs/contracts/dnpl-authority-v3.md`). Redis lost the history that ordered
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

    /// Lowercase hexadecimal 8-4-4-4-12. `UUID(uuidString:)` also accepts
    /// uppercase, which the contract refuses.
    static func isCanonicalUUID(_ raw: String) -> Bool {
        let bytes = Array(raw.utf8)
        guard bytes.count == 36 else { return false }
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
