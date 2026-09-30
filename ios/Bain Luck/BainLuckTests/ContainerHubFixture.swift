import Foundation
@testable import Bain_Luck

/// Byte-for-byte copies from server PR #9699 (3c9085c186) and producer PR #9721
/// (132ccbcdd2). The envelopes label these representative, NOT production.
enum ContainerHubFixture {
    static func responseData(_ name: String) throws -> Data {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("ContainerHubFixtures/\(name).json")
        let envelope = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        return try JSONSerialization.data(withJSONObject: envelope["response"]!)
    }

    static func decode(_ name: String = "representative_nfl_week", mutate: ((inout [String: Any]) -> Void)? = nil) throws -> ContainerHubResponse {
        var object = try JSONSerialization.jsonObject(with: responseData(name)) as! [String: Any]
        mutate?(&object)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(ContainerHubResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    static func collections(_ name: String) throws -> [ContainerHubCollection] {
        struct Response: Decodable { let collections: [ContainerHubCollection] }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Response.self, from: responseData(name)).collections
    }

    static func mutateMember(_ object: inout [String: Any], section: Int = 0, member: Int = 0, change: (inout [String: Any]) -> Void) {
        var sections = object["sections"] as! [[String: Any]]
        var members = sections[section]["members"] as! [[String: Any]]
        change(&members[member])
        sections[section]["members"] = members
        object["sections"] = sections
    }
}
