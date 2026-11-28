import Foundation

#if os(iOS)
import UIKit
#endif

/// Reader-facing Home Screen icon choices (#13767, ruling 423: A).
/// Original artwork supplied by Alex.
nonisolated enum AppIconChoice423A: String, CaseIterable, Identifiable, Sendable {
    case original
    case winter
    case newYearsEve

    var id: String { rawValue }

    /// Reader-facing label shown in Settings and the icon picker list.
    var displayName: String {
        switch self {
        case .original: return "Original"
        case .winter: return "Winter"
        case .newYearsEve: return "New Year's Eve"
        }
    }

    /// Alternate app icon set name passed to `UIApplication.shared.setAlternateIconName(_:)`.
    /// Passing `nil` returns to the primary `AppIcon`.
    var alternateIconName: String? {
        switch self {
        case .original: return nil
        case .winter: return "AppIconWinter"
        case .newYearsEve: return "AppIconNewYearsEve"
        }
    }

    /// Preview `.imageset` name rendered beside each choice in Settings and the picker list.
    var previewAssetName: String {
        switch self {
        case .original: return "AppIconPreviewOriginal"
        case .winter: return "AppIconPreviewWinter"
        case .newYearsEve: return "AppIconPreviewNewYearsEve"
        }
    }

    /// Exact list of alternate icon set names declared in `ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES`.
    static let alternateIconNames: [String] = allCases.compactMap(\.alternateIconName)

    static func from(alternateIconName: String?) -> AppIconChoice423A {
        guard let alternateIconName else { return .original }
        return allCases.first { $0.alternateIconName == alternateIconName } ?? .original
    }
}

#if os(iOS)
/// Wraps `UIApplication.shared` alternate-icon APIs so tests can exercise switching
/// both ways without requiring SpringBoard.
@MainActor
struct AppIconSwitcher423A {
    let supportsAlternateIcons: () -> Bool
    let currentIconName: () -> String?
    let setIconName: @MainActor (String?) async throws -> Void

    static let live = AppIconSwitcher423A(
        supportsAlternateIcons: { UIApplication.shared.supportsAlternateIcons },
        currentIconName: { UIApplication.shared.alternateIconName },
        setIconName: { iconName in
            try await UIApplication.shared.setAlternateIconName(iconName)
        }
    )

    var activeChoice: AppIconChoice423A {
        AppIconChoice423A.from(alternateIconName: currentIconName())
    }

    /// Switches the Home Screen icon unless `choice` is already active.
    @discardableResult
    func select(_ choice: AppIconChoice423A) async throws -> AppIconChoice423A {
        guard supportsAlternateIcons() else { return activeChoice }
        if activeChoice == choice {
            return choice
        }
        try await setIconName(choice.alternateIconName)
        return activeChoice
    }
}
#endif
