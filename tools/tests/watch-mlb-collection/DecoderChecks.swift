import Foundation

/// Tests decode real producer envelopes plus explicitly synthetic mutations.
/// They exercise production decoder behavior, not source strings or a clone.
@MainActor enum DecoderChecks {
    static func check(_ value: Bool, _ message: String) { precondition(value, message) }
    static func bytes(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value) }
    static func response(_ name: String, _ directory: URL) throws -> [String: Any] {
        let root = try JSONSerialization.jsonObject(with: Data(contentsOf: directory.appendingPathComponent(name))) as! [String: Any]
        check((root["_representative"] as! String).contains("NOT production"), "retain producer disclaimer")
        return root["response"] as! [String: Any]
    }
    static func reject(_ message: String, _ operation: () throws -> Void) {
        do { try operation() } catch { return }
        preconditionFailure(message)
    }
    static func mutateFirstGame(_ hub: [String: Any], _ mutate: (inout [String: Any]) -> Void) -> [String: Any] {
        var result = hub
        var sections = result["sections"] as! [[String: Any]]
        var members = sections[0]["members"] as! [[String: Any]]
        mutate(&members[0])
        sections[0]["members"] = members
        result["sections"] = sections
        return result
    }
    static func run(_ directory: URL) throws {
        let originalIndex = try response("discovery.json", directory)
        let hub = try response("postseason.json", directory)
        let original = try WatchMLBCollectionDecoder.collections(bytes(originalIndex), season: 2026)
        check(original.count == 1 && original[0].id == 81, "real published MLB Browse result")
        reject("separate producer fixture rows must never be silently joined") {
            _ = try WatchMLBCollectionDecoder.membership(bytes(hub), collection: original[0])
        }
        var aligned = originalIndex
        var rows = aligned["collections"] as! [[String: Any]]
        rows[0]["id"] = 80 // Synthetic identity alignment for behavioral scenarios only.
        aligned["collections"] = rows
        let collection = try WatchMLBCollectionDecoder.collections(bytes(aligned), season: 2026)[0]
        func decode(_ value: [String: Any]) throws -> WatchMLBMembership {
            try WatchMLBCollectionDecoder.membership(bytes(value), collection: collection)
        }
        let real = try decode(hub)
        check(real.games.map(\.id) == [801, 802], "own real games preserve producer order")
        check(real.games[0].home == "New York Yankees" && real.games[0].away == "Boston Red Sox", "full sides unchanged")
        check(real.games[0].stateText == "Final" && real.games[0].scheduledStart == nil, "final is supplied; no inferred result or start")
        check(real.games[1].stateText == "Scheduled" && real.games[1].scheduledStart != nil, "explicit known start retained")
        check(real.questions.map(\.id) == [9201, 9202], "exact own-root market questions preserve producer order")
        check(real.questions.map(\.name) == ["Padres at Dodgers: winner", "2026 World Series champion"],
              "full question titles retained without promoting card prices or results")
        check(!real.hasOtherEntries && real.children.isEmpty, "all supported root entries shown")
        func mutateFirstQuestion(_ mutate: (inout [String: Any]) -> Void) -> [String: Any] {
            var body = hub
            var sections = body["sections"] as! [[String: Any]]
            var members = sections[0]["members"] as! [[String: Any]]
            mutate(&members[2]); sections[0]["members"] = members; body["sections"] = sections
            return body
        }
        let badQuestions: [(inout [String: Any]) -> Void] = [
            { $0["id"] = 999 },
            { $0["container_id"] = 999 },
            { $0["destination"] = ["kind": "market", "id": 9201, "api": "/api/futures/999"] },
            { $0["destination"] = ["kind": "event", "id": 9201, "api": "/api/events/9201"] },
            { $0["card"] = ["id": 999, "name": "Wrong identity"] },
            { $0["card"] = ["id": 9201, "name": " "] },
            { $0["card"] = ["id": 9201, "name": 42] }
        ]
        for corrupt in badQuestions {
            let result = try decode(mutateFirstQuestion(corrupt))
            check(result.questions.map(\.id) == [9202] && result.games.map(\.id) == [801, 802]
                  && result.hasOtherEntries, "invalid question cannot erase healthy questions or games")
        }
        for malformed in [false, true] {
            var body = hub
            var sections = body["sections"] as! [[String: Any]]
            var members = sections[0]["members"] as! [[String: Any]]
            var duplicate = members[2]
            if malformed { duplicate["card"] = ["id": 9201, "name": 42] }
            members.append(duplicate); sections[0]["members"] = members; body["sections"] = sections
            let result = try decode(body)
            check(result.questions.map(\.id) == [9202] && result.hasOtherEntries,
                  "readable duplicate market identity is refused even with malformed payload")
        }

        for change in [
            ["state": "withdrawn"], ["state": "unpublished"], ["state": "unknown"],
            ["slug": "mlb-2026-postseason/evil"], ["revision": 0],
            ["edition": ["kind": "mlb_series", "league": "mlb", "season": 2026]],
            ["destination": ["kind": "container", "slug": "mlb-2026-postseason", "api": "/api/containers/other"]],
        ] as [[String: Any]] {
            var bad = rows[0]
            bad.merge(change) { _, new in new }
            let result = try WatchMLBCollectionDecoder.collections(bytes(["collections": [bad]]), season: 2026)
            check(result.isEmpty, "unsupported publication/edition/route cannot open")
        }
        check(try WatchMLBCollectionDecoder.collections(bytes(aligned), season: 2025).isEmpty, "different season refused")
        check(try WatchMLBCollectionDecoder.collections(bytes(["collections": [rows[0], "malformed", rows[0]]]), season: 2026).count == 1,
              "malformed siblings and duplicate root do not duplicate Browse")

        for state in ["withdrawn", "unpublished", "unknown"] {
            var body = hub; body["state"] = state
            let result = try decode(body)
            check(result.availability == .unavailable && result.games.isEmpty && result.children.isEmpty && result.questions.isEmpty,
                  "nonpublished hub never exposes stale rows")
        }
        var empty = hub; empty["state"] = "empty"
        let emptyResult = try decode(empty)
        check(emptyResult.availability == .empty && emptyResult.games.isEmpty && emptyResult.questions.isEmpty, "empty distinguished from unavailable; stale members ignored")
        var noGames = hub; noGames["sections"] = []
        check(try decode(noGames).published && decode(noGames).games.isEmpty, "published empty visible list is supported")
        for change in [
            ["slug": "mlb-2025-postseason"], ["revision": 1], ["revision": NSNull()],
            ["container": ["id": 81, "slug": "mlb-2026-postseason"]],
            ["edition": ["kind": "mlb_postseason", "league": "mlb", "season": 2025]],
            ["withheld_count": -1],
        ] as [[String: Any]] {
            var bad = hub; bad.merge(change) { _, new in new }
            reject("invalid exact hub identity/revision must fail") { _ = try decode(bad) }
        }
        let corruptions: [(inout [String: Any]) -> Void] = [
            { $0["id"] = 999 },
            { $0["container_id"] = 999 },
            { $0["destination"] = ["kind": "event", "id": 801, "api": "/api/events/999"] },
            { member in var card = member["card"] as! [String: Any]; card["sport"] = "americanfootball_nfl"; member["card"] = card },
            { member in var card = member["card"] as! [String: Any]; card["home_team"] = " "; member["card"] = card },
            { member in var card = member["card"] as! [String: Any]; card["id"] = 999; member["card"] = card },
        ]
        for corrupt in corruptions {
            let result = try decode(mutateFirstGame(hub, corrupt))
            check(result.games.map(\.id) == [802] && result.hasOtherEntries, "invalid member withheld without erasing valid sibling")
        }
        var duplicated = hub
        var sections = duplicated["sections"] as! [[String: Any]]
        var members = sections[0]["members"] as! [[String: Any]]
        members.append(members[0]); sections[0]["members"] = members; duplicated["sections"] = sections
        check(try decode(duplicated).games.map(\.id) == [801, 802], "duplicate member cannot duplicate selection")
        let tbd = mutateFirstGame(hub) { member in
            var card = member["card"] as! [String: Any]
            card["status"] = "scheduled"; card["started_without_result"] = false; card["start_is_tbd"] = true
            member["card"] = card
        }
        check(try decode(tbd).games[0].startContext == "Start to be determined" && decode(tbd).games[0].scheduledStart == nil,
              "TBD cannot borrow a midnight placeholder")

        // Synthetic child objects exercise the documented serializer shape.
        // There is no retained valid MLB nested-edition fixture or inferred route.
        func child(_ id: Int, _ name: String, _ slug: String, _ state: String = "published") -> [String: Any] {
            ["id": id, "name": name, "slug": slug, "publication_state": state,
             "edition": NSNull(), "destination": ["kind": "container", "slug": slug, "api": "/api/containers/\(slug)"]]
        }
        var nested = hub
        nested["children"] = [child(90, "Producer stage B", "mlb-2026-stage-b"),
                              child(91, "Producer stage A", "mlb-2026-stage-a"),
                              child(92, "Withdrawn", "removed", "withdrawn"),
                              child(93, "Unpublished", "draft", "unpublished"),
                              child(90, "Duplicate", "duplicate"),
                              child(94, "Cycle", "mlb-2026-postseason"),
                              ["id": "malformed"]]
        let kids = try decode(nested)
        check(kids.children.map(\.id) == [90, 91] && kids.children.map(\.name) == ["Producer stage B", "Producer stage A"],
              "published labels retain supplied order; withdrawn, malformed, duplicate and cyclic labels excluded")
        check(kids.hasOtherEntries, "unsupported children make partial coverage explicit")
        nested["state"] = "withdrawn"
        check(try decode(nested).children.isEmpty, "parent withdrawal also removes child labels")
        let january = ISO8601DateFormatter().date(from: "2026-01-01T00:00:00Z")!
        check(WatchMLBCollectionDecoder.season(asOf: january) == 2026, "MLB uses calendar year, never NFL rollover")
    }
}
