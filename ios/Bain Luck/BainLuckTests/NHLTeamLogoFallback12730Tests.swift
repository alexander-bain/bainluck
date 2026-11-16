import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #12730 — NHL fallback crests in `TeamLogoView` must hold ESPN's own team IDs,
/// never collide across distinct clubs in the same league, and request crisp 120 px assets.
@MainActor
final class NHLTeamLogoFallback12730Tests: XCTestCase {

    /// Explicit single-club aliases (relocation / rename / city shortening) that intentionally
    /// resolve to the same ESPN club ID. Any other duplicate ID within a league is a bug.
    private let singleClubAliases: [String: String] = [
        "oakland athletics": "athletics",
        "utah hockey club": "utah mammoth",
        "la clippers": "los angeles clippers",
    ]

    private nonisolated struct PinnedEspnFixture: Decodable {
        let teams: [String: [PinnedEspnTeam]]
    }

    private nonisolated struct PinnedEspnTeam: Decodable {
        let id: String
        let displayName: String
        let abbreviation: String?
        let shortDisplayName: String?
    }

    func testNoTwoDistinctClubsShareAnEspnIdWithinOneLeague() {
        var clubsByLeagueAndId: [String: Set<String>] = [:]
        for (rawKey, entry) in espnTeamIDs {
            let canonicalClub = singleClubAliases[rawKey] ?? rawKey
            let bucket = "\(entry.sport):\(entry.id)"
            clubsByLeagueAndId[bucket, default: []].insert(canonicalClub)
        }
        let collisions = clubsByLeagueAndId
            .filter { $0.value.count > 1 }
            .map { "\($0.key) shared by \($0.value.sorted().joined(separator: ", "))" }
            .sorted()
        XCTAssertEqual(collisions, [], "Distinct clubs must never share one ESPN logo ID within a league")
    }

    func testEveryEspnTeamIdMatchesPinnedAuthoritativeFixture() throws {
        let testFileURL = URL(fileURLWithPath: #filePath)
        let repoRoot = testFileURL
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let fixtureURL = repoRoot
            .appendingPathComponent("frontend")
            .appendingPathComponent("__tests__")
            .appendingPathComponent("fixtures")
            .appendingPathComponent("espn-team-ids.json")
        guard FileManager.default.fileExists(atPath: fixtureURL.path) else {
            return
        }
        let data = try Data(contentsOf: fixtureURL)
        let fixture = try JSONDecoder().decode(PinnedEspnFixture.self, from: data)

        let fixtureAliases: [String: String] = [
            "oakland athletics": "athletics",
            "utah hockey club": "utah mammoth",
            "los angeles clippers": "la clippers",
        ]

        var mismatches: [String] = []
        for (key, entry) in espnTeamIDs {
            guard let sportTeams = fixture.teams[entry.sport] else {
                mismatches.append("Missing sport \(entry.sport) in pinned fixture")
                continue
            }
            guard let matched = sportTeams.first(where: {
                $0.id == entry.id || $0.abbreviation?.lowercased() == entry.id
            }) else {
                mismatches.append("\(entry.sport)/\(key) -> id \(entry.id) does not exist in ESPN \(entry.sport)")
                continue
            }
            let expectedDisplay = fixtureAliases[key] ?? key
            let actualDisplay = normalizeEspnTeamLookupKey(matched.displayName)
            if expectedDisplay != actualDisplay {
                mismatches.append("\(entry.sport)/\(key) -> id \(entry.id) belongs to '\(matched.displayName)'")
            }
        }
        XCTAssertEqual(mismatches.sorted(), [])
    }

    func testNamedHockeyRegressionsAndCrisp120pxResolution() async throws {
        let predators = espnTeamLogoURL(for: "Nashville Predators")
        let sharks = espnTeamLogoURL(for: "San Jose Sharks")
        let knights = espnTeamLogoURL(for: "Vegas Golden Knights")
        let kraken = espnTeamLogoURL(for: "Seattle Kraken")
        let utahMammoth = espnTeamLogoURL(for: "Utah Mammoth")
        let utahLegacy = espnTeamLogoURL(for: "Utah Hockey Club")
        let leafs = espnTeamLogoURL(for: "Toronto Maple Leafs")
        let habsAccented = espnTeamLogoURL(for: "Montréal Canadiens")
        let habsAscii = espnTeamLogoURL(for: "Montreal Canadiens")

        XCTAssertNotEqual(predators, sharks)
        XCTAssertEqual(
            predators,
            "https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/27.png&w=120&h=120&transparent=true"
        )
        XCTAssertEqual(
            sharks,
            "https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/18.png&w=120&h=120&transparent=true"
        )
        XCTAssertEqual(
            knights,
            "https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/37.png&w=120&h=120&transparent=true"
        )
        XCTAssertEqual(
            kraken,
            "https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/sea.png&w=120&h=120&transparent=true"
        )
        XCTAssertEqual(
            utahMammoth,
            "https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/utah.png&w=120&h=120&transparent=true"
        )
        XCTAssertEqual(utahLegacy, utahMammoth)
        XCTAssertEqual(
            leafs,
            "https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/21.png&w=120&h=120&transparent=true"
        )
        XCTAssertEqual(
            habsAccented,
            "https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/10.png&w=120&h=120&transparent=true"
        )
        XCTAssertEqual(habsAccented, habsAscii)

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_12730_RENDERS_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

            let clubs: [String] = [
                "Nashville Predators",
                "San Jose Sharks",
                "Vegas Golden Knights",
                "Seattle Kraken",
                "Utah Mammoth",
                "Boston Bruins",
                "New Jersey Devils",
                "Toronto Maple Leafs",
                "Montréal Canadiens",
            ]

            for club in clubs {
                if let urlStr = espnTeamLogoURL(for: club), let u = URL(string: urlStr) {
                    _ = await ImageCache.shared.image(for: u)
                }
            }

            let sheet = VStack(alignment: .leading, spacing: 10) {
                Text("#12730 · NHL Fallback Crests (url: nil → ESPN 120 px)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                VStack(spacing: 8) {
                    ForEach(Array(clubs.enumerated()), id: \.offset) { _, club in
                        HStack(spacing: 12) {
                            TeamLogoView(
                                url: nil,
                                teamName: club,
                                color: DS.blueReadable,
                                size: 36,
                                sportKey: "icehockey_nhl"
                            )
                            Text(club)
                                .font(.subheadline.weight(.bold))
                                .foregroundStyle(.primary)
                            Spacer()
                            Text(espnTeamIDs[normalizeEspnTeamLookupKey(club)]?.id ?? "—")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                }
            }
            .padding(16)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))

            let host = hostForMeasurement(sheet.environment(\.colorScheme, .light), at: .large)
            let height = ceil(host.sizeThatFits(in: CGSize(width: 390, height: 2000)).height)
            host.overrideUserInterfaceStyle = .light
            host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: height))
            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
            window.overrideUserInterfaceStyle = .light
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            try await Task.sleep(nanoseconds: 500_000_000)
            let until = Date().addingTimeInterval(0.35)
            repeat {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.015))
            } while Date() < until
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
            if let png = img.pngData() {
                try png.write(to: dirURL.appendingPathComponent("nhl-12730-fallback-crests-390.png"))
            }
        }
    }
}
