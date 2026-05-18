import Foundation

// MARK: - Weather Featured

/// Featured weather market displayed on the weather page.
nonisolated struct WeatherFeaturedItem: Decodable, Identifiable, Sendable {
    var id: String { "\(marketId ?? 0)-\(q)" }
    let q: String
    let prob: Int
    let src: String
    let tag: String
    let closes: String
    let marketId: Int?
}

// MARK: - Weather City

/// City weather market summary with high and low distributions.
nonisolated struct WeatherCity: Decodable, Identifiable, Sendable {
    var id: String { cityId }
    let cityId: String
    let name: String
    let region: String
    let srcs: [String]
    let marketId: Int?
    let high: WeatherDistribution?
    let low: WeatherDistribution?

    enum CodingKeys: String, CodingKey {
        case cityId = "id"
        case name, region, srcs, marketId, high, low
    }
}

/// Probability distribution for a weather value such as high or low temperature.
nonisolated struct WeatherDistribution: Decodable, Sendable {
    let unit: String
    let mode: Double?
    let dist: [WeatherBracket]
}

/// Labeled probability bracket within a weather distribution.
nonisolated struct WeatherBracket: Decodable, Identifiable, Sendable {
    var id: String { label }
    let label: String
    let prob: Int
}

// MARK: - Economics

/// Economics dashboard response organized by market theme.
nonisolated struct EconomicsResponse: Decodable, Sendable {
    let totalMarkets: Int
    let updatedAt: String?
    let themes: EconomicsThemes
}

/// Theme buckets returned for the economics dashboard.
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

/// Fed-focused economics markets including FOMC meetings.
nonisolated struct EconomicsFedTheme: Decodable, Sendable {
    let count: Int
    let fomcMeetings: [FOMCMeeting]?
    let sideMarkets: [EconomicsMarket]?
}

/// Probability distribution for a specific FOMC meeting.
nonisolated struct FOMCMeeting: Decodable, Identifiable, Sendable {
    var id: String { date }
    let date: String
    let mo: String
    let dist: [[WeatherAnyCodable]]
    let resolved: Bool
    let marketId: Int?
    let sortKey: Int?
}

/// Inflation-focused economics markets including CPI releases.
nonisolated struct EconomicsInflationTheme: Decodable, Sendable {
    let count: Int
    let cpiReleases: [CPIRelease]?
    let sideMarkets: [EconomicsMarket]?
}

/// CPI release market distribution and display metadata.
nonisolated struct CPIRelease: Decodable, Identifiable, Sendable {
    var id: String { mo }
    let mo: String
    let brackets: [[WeatherAnyCodable]]?
    let upcoming: Bool?
    let peakIs: Int?
    let marketId: Int?
}

/// Generic economics theme containing primary and side markets.
nonisolated struct EconomicsGenericTheme: Decodable, Sendable {
    let count: Int
    let markets: [EconomicsMarket]?
    let sideMarkets: [EconomicsMarket]?
}

/// Single economics market row with probability and movement.
nonisolated struct EconomicsMarket: Decodable, Identifiable, Sendable {
    var id: String { "\(marketId ?? 0)-\(q)" }
    let q: String
    let prob: Double
    let src: String
    let delta: Double?
    let marketId: Int?
}

/// Flexible decoded value used by weather and economics matrix payloads.
nonisolated enum WeatherValue: Decodable, Sendable {
    case double(Double)
    case string(String)
    case bool(Bool)
    case int(Int)
    case empty

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let d = try? container.decode(Double.self) { self = .double(d) }
        else if let i = try? container.decode(Int.self) { self = .int(i) }
        else if let s = try? container.decode(String.self) { self = .string(s) }
        else if let b = try? container.decode(Bool.self) { self = .bool(b) }
        else { self = .empty }
    }
}

/// Type-erased decodable wrapper for mixed weather and economics values.
nonisolated struct WeatherAnyCodable: Decodable, Sendable {
    let value: WeatherValue

    var doubleValue: Double? {
        switch value {
        case .double(let d): return d
        case .int(let i): return Double(i)
        default: return nil
        }
    }

    var stringValue: String? {
        if case .string(let s) = value { return s }
        return nil
    }

    init(from decoder: Decoder) throws {
        value = try WeatherValue(from: decoder)
    }
}
