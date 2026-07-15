import SwiftUI

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        var rgb: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&rgb)
        self.init(
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255
        )
    }

    /// Parse an "R, G, B" (0–255) decimal-triplet string, e.g. team colors from the
    /// feed ("85, 37, 130"). Falls back to blue when malformed. (Relocated from the
    /// retired ProgressionLadderView in L2-123 so the shared LadderCardView primitive
    /// can consume the same feed team colors.)
    init(rgb: String) {
        let components = rgb.split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .compactMap { Double($0) }
        if components.count >= 3 {
            self.init(
                red: components[0] / 255,
                green: components[1] / 255,
                blue: components[2] / 255
            )
        } else {
            self.init(.blue)
        }
    }

    /// Returns a lighter version for backgrounds.
    func lightened(_ amount: Double = 0.3) -> Color {
        let resolved = self.resolve(in: EnvironmentValues())
        let r = Double(resolved.red)
        let g = Double(resolved.green)
        let b = Double(resolved.blue)
        return Color(
            red: min(r + amount * (1 - r), 1),
            green: min(g + amount * (1 - g), 1),
            blue: min(b + amount * (1 - b), 1)
        )
    }

    #if os(iOS)
    static let cardBackground = Color(.secondarySystemGroupedBackground)
    static let cardBackgroundDark = Color(.tertiarySystemGroupedBackground)
    static let barTrack = Color(.separator)
    static let systemBackground = Color(.systemBackground)
    static let groupedBackground = Color(.systemGroupedBackground)
    static let pageBackground = Color(.systemGroupedBackground)
    static let systemGray5 = Color(.systemGray5)
    static let systemGray6 = Color(.systemGray6)
    #elseif os(macOS)
    static let cardBackground = Color(nsColor: .controlBackgroundColor)
    static let cardBackgroundDark = Color(nsColor: .windowBackgroundColor)
    static let barTrack = Color(nsColor: .separatorColor)
    static let systemBackground = Color(nsColor: .windowBackgroundColor)
    static let groupedBackground = Color(nsColor: .controlBackgroundColor)
    static let pageBackground = Color(nsColor: .controlBackgroundColor)
    static let systemGray5 = Color.gray.opacity(0.2)
    static let systemGray6 = Color.gray.opacity(0.15)
    #endif
    static let heroDarkBackground = Color(red: 0.035, green: 0.035, blue: 0.043)
}
