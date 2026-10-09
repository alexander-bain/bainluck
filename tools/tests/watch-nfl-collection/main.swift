import Foundation

// Authored semantic tests. Run only after Native takes ownership of this proposal.
@main struct NFLCollectionChecks {
    static func data(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    }
    static func changed(_ object: [String: Any], _ path: [String], _ value: Any?) -> [String: Any] {
        var copy = object
        let key = path[0]
        if path.count == 1 { copy[key] = value }
        else { copy[key] = changed(copy[key] as! [String: Any], Array(path.dropFirst()), value) }
        return copy
    }
    static func check(_ condition: Bool, _ message: String = "check failed") {
        precondition(condition, message)
    }
    static func main() throws {
        let fixtures = URL(fileURLWithPath: CommandLine.arguments[1])
        func fixture(_ name: String) throws -> [String: Any] {
            let envelope = try JSONSerialization.jsonObject(with: Data(contentsOf: fixtures.appendingPathComponent(name))) as! [String: Any]
            check((envelope["_representative"] as! String).contains("NOT production"))
            return envelope["response"] as! [String: Any]
        }
        let index = try fixture("discovery.json")
        let hub = try fixture("week.json")
        let row = (index["collections"] as! [[String: Any]])[0]
        func weeks(_ rows: [Any], season: Int = 2026) throws -> [WatchNFLWeek] {
            try WatchNFLCollectionDecoder.weeks(data(["collections": rows]), season: season)
        }
        let week = try weeks([row])[0]
        check(week.id == 70 && week.revision == 4)
        check(try weeks([row, row]).count == 1)
        check(try weeks([row], season: 2025).isEmpty)
        let invalidWeeks: [([String], Any?)] = [
            (["type"], "event"), (["state"], "draft"), (["id"], 0),
            (["revision"], nil), (["revision"], 0), (["revision"], "4"),
            (["name"], "  "), (["slug"], "../events/502"),
            (["edition", "kind"], "mlb_series"), (["edition", "league"], "mlb"),
            (["edition", "season"], 2025), (["edition", "stage"], "Unknown"),
            (["edition", "week"], 0), (["edition", "week"], 100),
            (["destination", "kind"], "event"), (["destination", "slug"], "wrong"),
            (["destination", "api"], "https://example.com/api/containers/nfl-2026-week-5"),
            (["game_count"], -1), (["question_count"], -1)
        ]
        for (path, value) in invalidWeeks {
            let bad = changed(row, path, value)
            check(try weeks([bad]).isEmpty, "invalid index accepted: \(path)")
            check(try weeks([bad, row]).map(\.id) == [70], "valid sibling lost")
        }
        check(try weeks([changed(changed(row, ["game_count"], 0), ["question_count"], 0)]).isEmpty)
        // Positive counts cannot overflow when both are large.
        check(try weeks([changed(changed(row, ["game_count"], Int.max), ["question_count"], Int.max)]).count == 1)
        for (stage, prefix) in [("Pre Season", "preseason-"), ("Post Season", "postseason-")] {
            let slug = "nfl-2026-\(prefix)week-5"
            var variant = changed(row, ["edition", "stage"], stage)
            variant = changed(variant, ["slug"], slug)
            variant = changed(variant, ["destination", "slug"], slug)
            variant = changed(variant, ["destination", "api"], "/api/containers/\(slug)")
            check(try weeks([variant]).count == 1)
        }
        func membership(_ object: [String: Any]) throws -> WatchNFLMembership {
            try WatchNFLCollectionDecoder.membership(data(object), week: week)
        }
        func rejected(_ object: [String: Any]) {
            do { _ = try membership(object); preconditionFailure("invalid hub accepted") }
            catch { }
        }
        let result = try membership(hub)
        check(result.published && result.revision == 4 && result.hasOtherEntries)
        check(result.games.map(\.id) == [502, 501])
        check(result.games[0].scheduledStart == nil)
        check(result.games[1].scheduledStart == "2026-10-06T22:00:00+00:00")
        for state in ["withdrawn", "draft", "unpublished"] {
            let hidden = try membership(changed(hub, ["state"], state))
            check(!hidden.published && hidden.games.isEmpty)
        }
        let invalidHubs: [([String], Any?)] = [
            (["slug"], "wrong"), (["revision"], nil), (["revision"], 3),
            (["container", "id"], 71), (["container", "slug"], "wrong"),
            (["edition", "season"], 2025), (["edition", "week"], 6),
            (["withheld_count"], -1)
        ]
        for (path, value) in invalidHubs { rejected(changed(hub, path, value)) }
        let sections = hub["sections"] as! [[String: Any]]
        let members = sections[0]["members"] as! [[String: Any]]
        func withMembers(_ rows: [Any]) -> [String: Any] {
            var copy = hub
            var first = sections[0]
            first["members"] = rows
            copy["sections"] = [first]
            copy["withheld_count"] = 0
            return copy
        }
        let empty = try membership(withMembers([]))
        check(empty.published && empty.games.isEmpty && !empty.hasOtherEntries)
        let invalidMembers: [([String], Any?)] = [
            (["id"], 0), (["container_id"], 71), (["card", "id"], 501),
            (["card", "sport"], "baseball_mlb"), (["card", "home_team"], " \n"),
            (["card", "away_team"], nil), (["destination", "id"], 501),
            (["destination", "kind"], "market"), (["destination", "api"], "/api/events/501")
        ]
        for (path, value) in invalidMembers {
            let partial = try membership(withMembers([changed(members[0], path, value), members[1]]))
            check(partial.games.map(\.id) == [501] && partial.hasOtherEntries)
        }
        let partial = try membership(withMembers([NSNull(), "bad", members[0], members[0], members[1], members[2]]))
        check(partial.games.map(\.id) == [502, 501] && partial.hasOtherEntries)
        let tbd = try membership(withMembers([changed(members[1], ["card", "start_is_tbd"], true)]))
        check(tbd.games[0].scheduledStart == nil)
        let unknownStart = try membership(withMembers([changed(members[1], ["card", "start_is_tbd"], nil)]))
        check(unknownStart.games[0].scheduledStart == nil)
        for (raw, expected) in [("2026-01-01T00:00:00Z", 2025), ("2026-02-28T23:59:59Z", 2025), ("2026-03-01T00:00:00Z", 2026)] {
            check(WatchNFLCollectionDecoder.season(asOf: ISO8601DateFormatter().date(from: raw)!) == expected)
        }
        print("NFL model fixture and refusal checks PASS")
    }
}
