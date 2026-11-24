import Foundation

/// Ruling 366: B — Version 1 Kit capability & fail-closed validation.
///
/// The phone announces `supportedKitVersion` (`kit_version=1`). Any kit payload whose
/// `kit_version`, `layout`, or nested `mark` kind is unknown (or whose body is empty)
/// fails closed to `nil` so callers fall back to today's standard grouped card with
/// real rows and real percents — never an empty card and never `0%`.
enum KitCardCapability366B {
    static let supportedKitVersion = 1
}

nonisolated enum KitLayoutId366B: String, Codable, CaseIterable, Equatable, Sendable {
    case stack
    case grid
    case calendar
    case axis
}

nonisolated enum KitMarkKind366B: String, Codable, CaseIterable, Equatable, Sendable {
    case bar
    case dot
    case tile
    case ring
    case line
    case number
    case word
    case picture
}

private enum KitJSONValue366B: Decodable, Equatable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case array([KitJSONValue366B])
    case object([String: KitJSONValue366B])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let b = try? container.decode(Bool.self) {
            self = .bool(b)
        } else if let n = try? container.decode(Double.self) {
            self = .number(n)
        } else if let s = try? container.decode(String.self) {
            self = .string(s)
        } else if let arr = try? container.decode([KitJSONValue366B].self) {
            self = .array(arr)
        } else if let obj = try? container.decode([String: KitJSONValue366B].self) {
            self = .object(obj)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unsupported JSON value in kit spec"
            )
        }
    }

    var isEffectivelyEmpty: Bool {
        switch self {
        case .null:
            return true
        case .string(let s):
            return s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .array(let arr):
            return arr.isEmpty
        case .object(let obj):
            return obj.isEmpty
        case .number, .bool:
            return false
        }
    }
}

/// Strict fail-closed envelope for `kit_card` / `kit_block` specs (`kit_version: 1`).
///
/// Until native kit renderers ship and pass blind grading (`363: A`), decoding succeeds
/// only for valid v1 shapes (and callers still render the standard grouped card rather
/// than an empty placeholder), while any unrecognized `kit_version`, `layout`, `mark`,
/// or empty body throws `DecodingError.dataCorrupted` and collapses cleanly to `nil`.
nonisolated struct KitCardEnvelope366B: Decodable, Equatable, Sendable {
    let kitVersion: Int
    let layout: KitLayoutId366B
    let variant: String?
    let id: String?

    private struct AnyKey: CodingKey {
        let stringValue: String
        let intValue: Int?
        init?(stringValue: String) {
            self.stringValue = stringValue
            self.intValue = nil
        }
        init?(intValue: Int) {
            self.stringValue = "\(intValue)"
            self.intValue = intValue
        }
    }

    init(kitVersion: Int = KitCardCapability366B.supportedKitVersion, layout: KitLayoutId366B, variant: String? = nil, id: String? = nil) {
        self.kitVersion = kitVersion
        self.layout = layout
        self.variant = variant
        self.id = id
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyKey.self)

        func decodeString(_ keys: [String]) -> String? {
            for k in keys {
                if let key = AnyKey(stringValue: k),
                   let value = try? c.decodeIfPresent(String.self, forKey: key) {
                    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !trimmed.isEmpty { return trimmed }
                }
            }
            return nil
        }

        func decodeInt(_ keys: [String]) -> Int? {
            for k in keys {
                if let key = AnyKey(stringValue: k),
                   let value = try? c.decodeIfPresent(Int.self, forKey: key) {
                    return value
                }
            }
            return nil
        }

        guard let version = decodeInt(["kit_version", "kitVersion"]),
              version == KitCardCapability366B.supportedKitVersion else {
            throw DecodingError.dataCorrupted(
                DecodingError.Context(
                    codingPath: decoder.codingPath,
                    debugDescription: "Unsupported or missing kit_version"
                )
            )
        }

        guard let rawLayout = decodeString(["layout", "layout_id", "layoutId"]),
              let resolvedLayout = KitLayoutId366B(rawValue: rawLayout) else {
            throw DecodingError.dataCorrupted(
                DecodingError.Context(
                    codingPath: decoder.codingPath,
                    debugDescription: "Unrecognized kit layout"
                )
            )
        }

        // Validate body non-emptiness and fail closed on any unknown mark kind anywhere inside the spec.
        var hasContentCollection = false
        for contentKeyName in ["body", "rows", "items", "days", "series", "sections", "cells", "marks"] {
            if let key = AnyKey(stringValue: contentKeyName),
               let val = try? c.decodeIfPresent(KitJSONValue366B.self, forKey: key),
               !val.isEffectivelyEmpty {
                try Self.validateMarks(in: val, insideMarksCollection: contentKeyName == "marks", codingPath: decoder.codingPath)
                if case .object(let obj) = val,
                   ["rows", "items", "days", "series", "sections", "cells", "marks"].contains(where: { obj[$0]?.isEffectivelyEmpty == false }) {
                    hasContentCollection = true
                } else if contentKeyName != "body" {
                    hasContentCollection = true
                } else if case .object(let obj) = val, !obj.isEmpty {
                    hasContentCollection = true
                }
            }
        }

        guard hasContentCollection else {
            throw DecodingError.dataCorrupted(
                DecodingError.Context(
                    codingPath: decoder.codingPath,
                    debugDescription: "Empty kit body cannot draw a blank card"
                )
            )
        }

        self.kitVersion = version
        self.layout = resolvedLayout
        self.variant = decodeString(["variant"])
        self.id = decodeString(["id"])
    }

    private static func validateMarks(
        in value: KitJSONValue366B,
        insideMarksCollection: Bool,
        codingPath: [CodingKey]
    ) throws {
        switch value {
        case .array(let elements):
            for el in elements {
                try validateMarks(in: el, insideMarksCollection: insideMarksCollection, codingPath: codingPath)
            }
        case .object(let dict):
            let markKeys = insideMarksCollection
                ? ["mark", "mark_kind", "markKind", "kind", "type"]
                : ["mark", "mark_kind", "markKind"]
            for mk in markKeys {
                if case .string(let rawMark)? = dict[mk] {
                    let trimmed = rawMark.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard KitMarkKind366B(rawValue: trimmed) != nil else {
                        throw DecodingError.dataCorrupted(
                            DecodingError.Context(
                                codingPath: codingPath,
                                debugDescription: "Unrecognized kit mark kind: \(trimmed)"
                            )
                        )
                    }
                }
            }
            for (k, child) in dict {
                let childIsMarks = (k == "marks")
                try validateMarks(in: child, insideMarksCollection: childIsMarks, codingPath: codingPath)
            }
        case .string, .number, .bool, .null:
            break
        }
    }
}
