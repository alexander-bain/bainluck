import Foundation

// MARK: - Weather Featured

nonisolated struct WeatherFeaturedItem: Decodable, Identifiable, Sendable {
    var id: String { q }
    let q: String
    let prob: Int
    let src: String
    let tag: String
    let closes: String
}

// MARK: - Weather City

nonisolated struct WeatherCity: Decodable, Identifiable, Sendable {
    var id: String { cityId }
    let cityId: String
    let name: String
    let region: String
    let srcs: [String]
    let high: WeatherDistribution?
    let low: WeatherDistribution?

    enum CodingKeys: String, CodingKey {
        case cityId = "id"
        case name, region, srcs, high, low
    }
}

nonisolated struct WeatherDistribution: Decodable, Sendable {
    let unit: String
    let mode: Double?
    let dist: [WeatherBracket]
}

nonisolated struct WeatherBracket: Decodable, Identifiable, Sendable {
    var id: String { label }
    let label: String
    let prob: Int
}

// MARK: - Economics

nonisolated struct EconomicsResponse: Decodable, Sendable {
    let totalMarkets: Int
    let updatedAt: String?
    let themes: EconomicsThemes
}

nonisolated struct EconomicsThemes: Decodable, Sendable {
    let fed: EconomicsFedTheme?
    let inflation: EconomicsInflationTheme?
    let jobs: EconomicsGenericTheme?
    let recession: EconomicsGenericTheme?
    let markets: EconomicsGenericTheme?
    let energy: EconomicsGenericTheme?
    let housing: EconomicsGenericTheme?
    let trade: EconomicsGenericTheme?
    let government: EconomicsGenericTheme?
}

nonisolated struct EconomicsFedTheme: Decodable, Sendable {
    let count: Int
    let fomcMeetings: [FOMCMeeting]?
    let sideMarkets: [EconomicsMarket]?
}

nonisolated struct FOMCMeeting: Decodable, Identifiable, Sendable {
    var id: String { date }
    let date: String
    let mo: String
    let dist: [[WeatherAnyCodable]]
    let resolved: Bool
    let marketId: Int?
    let sortKey: Int?
}

nonisolated struct EconomicsInflationTheme: Decodable, Sendable {
    let count: Int
    let cpiReleases: [CPIRelease]?
    let sideMarkets: [EconomicsMarket]?
}

nonisolated struct CPIRelease: Decodable, Identifiable, Sendable {
    var id: String { mo }
    let mo: String
    let brackets: [[WeatherAnyCodable]]?
    let upcoming: Bool?
    let peakIs: String?
    let marketId: Int?
}

nonisolated struct EconomicsGenericTheme: Decodable, Sendable {
    let count: Int
    let markets: [EconomicsMarket]?
}

nonisolated struct EconomicsMarket: Decodable, Identifiable, Sendable {
    var id: String { "\(marketId ?? 0)-\(q)" }
    let q: String
    let prob: Int
    let src: String
    let delta: Double?
    let marketId: Int?
}

nonisolated struct WeatherAnyCodable: Decodable, Sendable {
    let value: Any

    var doubleValue: Double? {
        if let d = value as? Double { return d }
        if let i = value as? Int { return Double(i) }
        return nil
    }

    var stringValue: String? {
        value as? String
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let d = try? container.decode(Double.self) { value = d }
        else if let s = try? container.decode(String.self) { value = s }
        else if let b = try? container.decode(Bool.self) { value = b }
        else if let i = try? container.decode(Int.self) { value = i }
        else { value = "" }
    }
}
