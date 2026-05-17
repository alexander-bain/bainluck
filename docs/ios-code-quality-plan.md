# iOS Code Quality Plan

Honest audit of what a senior iOS engineer would say, and the fix plan.

## Grades

| Area | Grade | Key Issue |
|------|-------|-----------|
| Models | B+ | Solid. Consistent Decodable/Sendable, resilient decoding. |
| Comments/MARK usage | B- | Good section markers. Zero doc comments on types. |
| Naming | B- | Pervasive abbreviations: `vm`, `ct`, `ap`, `hp`, `gm`, `rf`, `tp` |
| SwiftUI | C+ | Force unwraps in URLs, Timers in @State, 250-line body properties |
| File organization | C+ | 2,259-line DiscoverView, ViewModels scattered in wrong dirs |
| Architecture | C | No consistent pattern, no DI, no testability |
| Code duplication | D | Clipboard, share URLs, guess cards, context menus all copy-pasted |
| Access control | D+ | Almost nothing is `private`, mutable state exposed everywhere |

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

### P2c. AuthManager thread safety
`restoreSession()` mutates `@Published` properties from a background `Task`. Add `@MainActor` to the class.
**File:** AuthManager.swift

## Priority 3: Code Duplication (biggest maintainability win)

### P3a. Extract shared utilities (1 hour)
Create `Utils/Clipboard.swift`:
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
Used in: DiscoverView (4 places), FeedView (4 places)

Create `Utils/ShareURLs.swift`:
```swift
func eventShareURL(_ id: Int) -> URL {
    URL(string: "https://bainluck.com/events/\(id)") ?? URL(string: "https://bainluck.com")!
}
func futuresShareURL(_ id: Int) -> URL {
    URL(string: "https://bainluck.com/futures/\(id)") ?? URL(string: "https://bainluck.com")!
}
```
Used in: DiscoverView, FeedView

### P3b. Unify NativeGuessCard and NativeEventGuessCard (2 hours)
90% identical — same layout, same `submitGuess()`, same `generateThreshold()`. Extract a single `GuessCardView` that takes a protocol or enum for the data source.
**File:** DiscoverView.swift (currently 2,259 lines → would drop ~400 lines)

### P3c. Shared context menu builder (30 min)
`FeedView.cardContextMenu()` and `DiscoverView.discoverCardMenu()` do the same thing. Extract to `Components/CardContextMenu.swift`.

## Priority 4: File Organization (2-3 hours)

### P4a. Split DiscoverView.swift
From 2,259 lines → 6-8 files:
- `DiscoverView.swift` — main view only (~200 lines)
- `DiscoverViewModel.swift` — ViewModel (~150 lines)
- `Components/GuessCardView.swift` — unified guess card (~300 lines)
- `Components/DailyChallengeCard.swift` — challenge UI (~150 lines)
- `Components/DiscoverFuturesCard.swift` — futures card (~150 lines)
- `Components/DiscoverEventCard.swift` — event card (~150 lines)
- `Components/ResolutionCard.swift` — resolution card (~50 lines)

### P4b. Create ViewModels/ directory
Move all ViewModels out of View files:
- `Views/EventDetailView.swift` → extract `ViewModels/EventDetailViewModel.swift`
- `Views/DiscoverView.swift` → extract `ViewModels/DiscoverViewModel.swift`
- Keep `PreferencesViewModel.swift` and `OnboardingViewModel.swift` but move to `ViewModels/`

### P4c. Split Extensions.swift
`Components/Extensions.swift` is a grab bag. Split into:
- `Utils/ColorExtensions.swift`
- `Utils/ProbabilityFormatting.swift`
- `Utils/SportDisplayNames.swift`
- `Components/FlowLayout.swift`

## Priority 5: Naming & Access Control (ongoing)

### P5a. Stop abbreviating
Replace throughout: `vm` → `viewModel`, `ct` → `commenceTime`, `ap`/`hp` → `awayProbability`/`homeProbability`, `gm` → `gameMarkets`, `rf` → `relatedFutures`

### P5b. Add `private` everywhere
- All `@Published` ViewModel properties → `private(set)`
- All helper methods in Views → `private`
- `PinManager.isAuthenticated` → `private(set)`
- `APIClient.authTokenProvider` → keep setter but document it

### P5c. Add doc comments to models
Every model struct gets a `///` comment explaining what it represents and where it comes from.

## Priority 6: Architecture (longer term)

- Add `@MainActor` to all ViewModel classes
- Replace `Timer.scheduledTimer` with `.task { for await _ in Timer.publish() }`
- Consider a simple DI container for `APIClient` (enables testing)
- Add unit tests for ViewModels (start with EventDetailViewModel)

## What NOT to fix

- **Don't adopt a full architecture framework** (TCA, MVVM-C, etc.) — the app ships and works
- **Don't add localization** — single market (US) for now
- **Don't refactor the navigation system** — it works across iPhone/iPad/Mac, touching it risks regressions
- **Don't add SwiftLint yet** — fix the patterns manually first, then add linting to enforce
