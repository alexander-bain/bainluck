# iOS Code Quality Plan

Honest audit of what a senior iOS engineer would say, and the fix plan.

## Status (May 17, 2026)

Shipped:
- URL force unwraps in share links replaced with fallback URLs.
- `FeedItem.id` fallback is stable.
- `AuthManager` is main-actor isolated for published auth state.
- Shared clipboard and share URL helpers extracted.
- All native `ObservableObject` view models moved into `ViewModels/`.
- `Components/Extensions.swift` split into focused utilities.
- Native model and service doc comments added.
- View-model-owned published state is `private(set)` where views only read it.
- Futures browser entry point is hidden from production navigation until the native Futures browser is rebuilt; 🍀 sidebar branding and Calibration remain visible.
- CQ-10 shipped: daily challenge UI moved into `Components/DailyChallengeCard.swift`.
- iOS-7 hidden Futures browser rebuild is partial: grouped category rail, polished rows, reusable browse components, and loading/error/empty states are in place.

Still open:
- CQ-6: unify `NativeGuessCard` and `NativeEventGuessCard`.
- CQ-7: extract shared Discover/Feed context menu.
- CQ-9/CQ-11: move Discover card and resolution UI into component files.
- CQ-16: broad helper-method `private` cleanup.
- CQ-17: broad abbreviation cleanup.

## Grades

| Area | Grade | Key Issue |
|------|-------|-----------|
| Models | A- | Consistent Decodable/Sendable, resilient decoding, model doc comments added. |
| Comments/MARK usage | B+ | Model/service docs added; remaining view-level comments are pragmatic. |
| Naming | B- | Pervasive abbreviations: `vm`, `ct`, `ap`, `hp`, `gm`, `rf`, `tp` |
| SwiftUI | B- | URL crash risks fixed; large Discover UI components still need extraction. |
| File organization | B+ | ViewModels and utilities are now organized; DiscoverView remains oversized. |
| Architecture | C | No consistent pattern, no DI, no testability |
| Code duplication | C+ | Clipboard/share duplication fixed; guess cards and context menus remain duplicated. |
| Access control | B- | ViewModel published state tightened; broad view helper privacy still open. |

## Priority 1: Ship-Blocking (fix before App Store review)

None — Apple doesn't review code quality. These are all for maintainability.

## Priority 2: Crash Risks (fix soon)

### P2a. Force unwraps on URLs
`URL(string:)!` in EventDetailView, FeedView, DiscoverView will crash if a URL is malformed.
```swift
// Before (crashes):
URL(string: "https://bainluck.com/events/\(eventId)")!

// After (safe):
URL(string: "https://bainluck.com/events/\(eventId)") ?? URL(string: "https://bainluck.com")!
```
**Files:** EventDetailView.swift, FeedView.swift, DiscoverView.swift
**Status:** Shipped May 17. Share links use `bainLuckFallbackURL` through shared URL builders.

### P2b. Unstable FeedItem.id
`UUID().uuidString` fallback generates a new ID every access, causing SwiftUI list thrashing.
```swift
// Fix: use a stable fallback
var id: String {
    if let e = event { return "event-\(e.id)" }
    if let f = futures { return "futures-\(f.id)" }
    return "unknown-\(type)-\(score)"
}
```
**File:** FeedModels.swift line 79
**Status:** Shipped May 17.

### P2c. AuthManager thread safety
`restoreSession()` mutates `@Published` properties from a background `Task`. Add `@MainActor` to the class.
**File:** AuthManager.swift
**Status:** Shipped May 17.

## Priority 3: Code Duplication (biggest maintainability win)

### P3a. Extract shared utilities (1 hour)
Create `Utilities/Clipboard.swift`:
```swift
func copyToClipboard(_ string: String) {
    #if os(macOS)
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(string, forType: .string)
    #else
    UIPasteboard.general.string = string
    #endif
}
```
Used in: DiscoverView, FeedView, MyStuffView, and share/copy menus.

Create `Utilities/ShareURLs.swift`:
```swift
func eventShareURL(_ id: Int) -> URL {
    URL(string: "https://bainluck.com/events/\(id)") ?? URL(string: "https://bainluck.com")!
}
func futuresShareURL(_ id: Int) -> URL {
    URL(string: "https://bainluck.com/futures/\(id)") ?? URL(string: "https://bainluck.com")!
}
```
Used in: DiscoverView, FeedView
**Status:** Shipped May 17. `Utilities/Clipboard.swift` and `Utilities/ShareURLs.swift` are live. Bug-report screenshot pasteboard reads remain intentionally separate.

### P3b. Unify NativeGuessCard and NativeEventGuessCard (2 hours)
90% identical — same layout, same `submitGuess()`, same `generateThreshold()`. Extract a single `GuessCardView` that takes a protocol or enum for the data source.
**File:** DiscoverView.swift (currently ~2,200 lines → would drop ~400 lines)
**Status:** Open.

### P3c. Shared context menu builder (30 min)
`FeedView.cardContextMenu()` and `DiscoverView.discoverCardMenu()` do the same thing. Extract to `Components/CardContextMenu.swift`.
**Status:** Open.

## Priority 4: File Organization (2-3 hours)

### P4a. Split DiscoverView.swift
From ~2,200 lines → 6-8 files:
- `DiscoverView.swift` — main view only (~200 lines)
- `DiscoverViewModel.swift` — ViewModel (~150 lines) — shipped
- `Components/GuessCardView.swift` — unified guess card (~300 lines)
- `Components/DailyChallengeCard.swift` — challenge UI (~150 lines)
- `Components/DiscoverFuturesCard.swift` — futures card (~150 lines)
- `Components/DiscoverEventCard.swift` — event card (~150 lines)
- `Components/ResolutionCard.swift` — resolution card (~50 lines)
**Status:** Partially shipped. ViewModel extracted; UI component extraction remains open.

### P4b. Create ViewModels/ directory
Move all ViewModels out of View files:
- `Views/EventDetailView.swift` → extract `ViewModels/EventDetailViewModel.swift`
- `Views/DiscoverView.swift` → extract `ViewModels/DiscoverViewModel.swift`
- Keep `PreferencesViewModel.swift` and `OnboardingViewModel.swift` but move to `ViewModels/`
**Status:** Shipped May 17 for all native view models, not just these examples.

### P4c. Split Extensions.swift
`Components/Extensions.swift` is a grab bag. Split into:
- `Utilities/ColorExtensions.swift`
- `Utilities/FormattingUtilities.swift`
- `Utilities/SportDisplayNames.swift`
- `Utilities/FlagUtilities.swift`
- `Utilities/FlowLayout.swift`
**Status:** Shipped May 17.

## Priority 5: Naming & Access Control (ongoing)

### P5a. Stop abbreviating
Replace throughout: `vm` → `viewModel`, `ct` → `commenceTime`, `ap`/`hp` → `awayProbability`/`homeProbability`, `gm` → `gameMarkets`, `rf` → `relatedFutures`
**Status:** Open. Broad mechanical rename with high conflict risk.

### P5b. Add `private` everywhere
- All `@Published` ViewModel properties → `private(set)`
- All helper methods in Views → `private`
- `PinManager.isAuthenticated` → `private(set)`
- `APIClient.authTokenProvider` → keep setter but document it
**Status:** Partially shipped. ViewModel-owned published state and `PinManager.isAuthenticated` are done; view helper privacy remains open. Bound/view-assigned fields intentionally remain mutable.

### P5c. Add doc comments to models
Every model struct gets a `///` comment explaining what it represents and where it comes from.
**Status:** Shipped May 17 across native model files.

## Priority 6: Architecture (longer term)

- Prefer `@MainActor` on async mutating methods, not blanket class isolation, unless a class specifically requires class-wide main actor behavior.
- Replace `Timer.scheduledTimer` with `.task { for await _ in Timer.publish() }`
- Consider a simple DI container for `APIClient` (enables testing)
- Add unit tests for ViewModels (start with EventDetailViewModel)

## What NOT to fix

- **Don't adopt a full architecture framework** (TCA, MVVM-C, etc.) — the app ships and works
- **Don't add localization** — single market (US) for now
- **Don't refactor the navigation system** — it works across iPhone/iPad/Mac, touching it risks regressions
- **Don't add SwiftLint yet** — fix the patterns manually first, then add linting to enforce
