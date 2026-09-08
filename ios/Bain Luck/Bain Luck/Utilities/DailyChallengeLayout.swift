import CoreGraphics

/// #3865 — the numbers that stop `DailyChallengeView`'s question from being an
/// iPhone layout with its container widened.
///
/// MEASURED, against production, 2026-09-08 (`artifacts-native-064`):
///
/// | | iPhone 17 (402×874pt) | iPad Pro 11-inch (834×1210pt) |
/// |---|---|---|
/// | each answer button | 176pt | **392pt** |
/// | white below the buttons | 329pt (38% of the screen) | **781pt (65% of the page)** |
///
/// The issue's headline says "1,700pt of dead space under a 700pt-wide pair of
/// buttons". Both of those are the pixel counts wearing point labels (781×2 =
/// 1,562; 392×2 = 784) — the page is only 1,210pt tall, so 1,700pt of anything
/// cannot fit on it. The defect is real and the frames reproduce it; only the
/// two iPad magnitudes were wrong, and they are corrected here because this is
/// the file the next reader will size a change against.
enum DailyChallengeLayout {

    /// The widest the question column may draw.
    ///
    /// **Not the house 900.** `PoliticsView`, `EconomicsView`,
    /// `EntertainmentView` and `WeatherView` all cap regular-width content at
    /// 900pt, and copying that constant here would have shipped a no-op: the
    /// iPad this issue was filed against is **834pt wide**, so a 900pt cap
    /// never binds on it. Those four screens are dashboards — grids of cards
    /// that genuinely want the width. This screen is one question and a
    /// two-way answer, and at 834pt each button is 392pt: a tap target as wide
    /// as an entire iPhone, for a one-bit answer.
    ///
    /// ``DailyChallengeLayoutTests`` pins `maxContentWidth < 834` so that
    /// "just use the house constant" cannot silently un-fix this.
    static let maxContentWidth: CGFloat = 560

    /// The page's own inset. Was a bare `.padding()`; named so the button-width
    /// arithmetic below is the *same* number the view lays out with rather than
    /// a second copy of it that can drift.
    static let pagePadding: CGFloat = 16

    /// The gap between Higher and Lower.
    static let answerButtonSpacing: CGFloat = 16

    /// The width the question column draws at inside a viewport `width` wide.
    ///
    /// A cap, never a floor: on every iPhone this returns the viewport
    /// unchanged, so the fix cannot narrow the phone in the course of fixing
    /// the iPad.
    static func contentWidth(inViewportWidth width: CGFloat) -> CGFloat {
        min(width, maxContentWidth)
    }

    /// The width one answer button draws at inside a viewport `width` wide.
    ///
    /// Two buttons, one gap, both inside the page padding — this is what
    /// `frame(maxWidth: .infinity)` resolves to, and it is the number the
    /// issue is actually about.
    static func answerButtonWidth(inViewportWidth width: CGFloat) -> CGFloat {
        let column = contentWidth(inViewportWidth: width) - (pagePadding * 2)
        return max(0, (column - answerButtonSpacing) / 2)
    }
}
