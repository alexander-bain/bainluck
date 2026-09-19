import Foundation

/// When a Discover group card shows every one of its rows.
///
/// #7074. Alex, on build 15's UFC futures group: "it started out only showing
/// one and asked me to click to see more, where it then only revealed two more.
/// If the total number that would be shown is only three, then we should just
/// show them all." The same note on the Awards card two slots above it.
///
/// Lifted out of `NativeGroupCard`'s `@ViewBuilder` for the reason
/// `DiscoverMasonry` and `DailyChallengeLayout` were: a raster can show you that
/// a card has one row instead of three, and it cannot tell you which of the two
/// conditions in the body decided that. The body asked `expanded` to choose the
/// rows and `!expanded` to choose whether to draw the button — two conditions
/// that must always agree, which is a card with three rows and a "Show 2 more"
/// underneath as soon as someone edits one of them. One expression answers both
/// now, and it is a function so a test can call it.
enum DiscoverGroupRows {

    /// A group this size or smaller is drawn whole and offers no button.
    ///
    /// Three because three is what Alex met and what fits: the button earns its
    /// row when it is standing in for a list, not when it is standing in for two
    /// rows. Larger groups keep the expansion control — this raises the floor,
    /// it does not remove it.
    static let showsEveryRowUpTo = 3

    /// Whether every row of a group of `itemCount` is on screen: because the
    /// group is small enough to be drawn whole, or because the reader opened it.
    static func showsEveryRow(itemCount: Int, expanded: Bool) -> Bool {
        expanded || itemCount <= showsEveryRowUpTo
    }
}
