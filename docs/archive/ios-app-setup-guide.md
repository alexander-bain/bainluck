# Bain Luck iOS App — Native SwiftUI Setup Guide

## Phase 0: Apple Developer Setup

### 0.1 — Enroll in Apple Developer Program
1. Go to https://developer.apple.com/programs/enroll/
2. Sign in with your Apple ID (or create one)
3. Enroll as **Individual** ($99/year)
4. Wait for approval (usually 24-48 hours)

### 0.2 — Create App ID
1. Go to https://developer.apple.com/account/resources/identifiers/list
2. Click **+** → **App IDs** → **App**
3. Description: `Bain Luck`
4. Bundle ID: `com.bainluck.app` (Explicit)
5. Enable these capabilities:
   - **Sign In with Apple**
   - **Push Notifications** (for later)
   - **Associated Domains** (for universal links later)
6. Click **Continue** → **Register**

### 0.3 — Create Sign In with Apple Service ID (for web compatibility)
1. **Identifiers** → **+** → **Services IDs**
2. Identifier: `com.bainluck.auth`
3. Enable **Sign In with Apple** → Configure:
   - Primary App ID: `com.bainluck.app`
   - Domains: `bainluck.com`, `api.bainluck.com`
   - Return URLs: `https://api.bainluck.com/api/auth/apple/callback`
4. Register

### 0.4 — Create Sign In with Apple Key
1. **Keys** → **+**
2. Name: `Bain Luck Sign In`
3. Enable **Sign In with Apple** → Configure → Primary App ID: `com.bainluck.app`
4. Register → **Download** the `.p8` file (you only get one download)
5. Note the **Key ID** — you'll need it for Firebase

---

## Phase 1: Xcode Project Setup

### 1.1 — Create the project
1. Open Xcode → **File → New → Project**
2. **iOS → App**
3. Settings:
   - Product Name: `BainLuck`
   - Team: your Apple Developer team
   - Organization Identifier: `com.bainluck`
   - Bundle Identifier: `com.bainluck.app` (should auto-populate)
   - Interface: **SwiftUI**
   - Language: **Swift**
   - Storage: **None**
   - Uncheck "Include Tests" for now (add later)
4. Save to `/Users/bain/bainluck/ios/`

### 1.2 — Set deployment target
1. Select the project in the navigator → **General** tab
2. Minimum Deployments: **iOS 17.0** (enables modern SwiftUI features, Observable macro, etc.)
3. Device Orientation: Portrait only (for now)

### 1.3 — Add capabilities
1. Project → **Signing & Capabilities** tab
2. Click **+ Capability** and add:
   - **Sign In with Apple**
   - **Push Notifications**
   - **Background Modes** → check "Background fetch" and "Remote notifications"

### 1.4 — Project structure
Create this folder structure inside the Xcode project:

```
BainLuck/
├── App/
│   ├── BainLuckApp.swift          # @main entry point
│   └── AppState.swift             # Global app state (auth, preferences)
├── Models/
│   ├── Event.swift                # Matches backend Event response
│   ├── FuturesMarket.swift        # Matches backend FuturesMarket
│   ├── FeedItem.swift             # Union of event + futures feed items
│   ├── Sport.swift                # Sport metadata
│   ├── User.swift                 # User profile
│   ├── Preferences.swift          # User preferences + favorites
│   └── Pulse.swift                # Pulse score data
├── Services/
│   ├── APIClient.swift            # HTTP client for api.bainluck.com
│   ├── AuthService.swift          # Firebase Auth + Apple Sign-In
│   ├── AnalyticsService.swift     # GA4 via Firebase Analytics
│   └── PinStorage.swift           # Pinned events/futures (local + sync)
├── ViewModels/
│   ├── FeedViewModel.swift        # Homepage feed logic
│   ├── EventDetailViewModel.swift # Single event detail + chart data
│   ├── FuturesViewModel.swift     # Futures list
│   ├── FuturesDetailViewModel.swift
│   ├── SearchViewModel.swift      # Search + typeahead
│   ├── MyStuffViewModel.swift     # Team-filtered feed
│   ├── OnboardingViewModel.swift  # 5-step onboarding flow
│   └── PreferencesViewModel.swift # Settings
├── Views/
│   ├── MainTabView.swift          # Tab bar (Feed, Search, My Stuff, Preferences)
│   ├── Feed/
│   │   ├── FeedView.swift         # Scrollable feed
│   │   ├── EventCardView.swift    # Event card (live/upcoming/completed states)
│   │   ├── FuturesCardView.swift  # Futures market card
│   │   └── FeedSectionHeader.swift
│   ├── EventDetail/
│   │   ├── EventDetailView.swift  # Full event page
│   │   ├── OddsChartView.swift    # Multi-source probability chart
│   │   ├── ProbabilityBar.swift   # Team-colored probability bar
│   │   ├── RelatedFuturesView.swift
│   │   └── LineMovementView.swift
│   ├── Futures/
│   │   ├── FuturesListView.swift
│   │   └── FuturesDetailView.swift
│   ├── Search/
│   │   ├── SearchView.swift
│   │   └── TypeaheadRow.swift
│   ├── MyStuff/
│   │   └── MyStuffView.swift      # 3-state: sign-in, onboard, feed
│   ├── Onboarding/
│   │   ├── OnboardingView.swift   # 5-step stepper
│   │   ├── LocationStep.swift
│   │   ├── FollowStep.swift
│   │   ├── AlmaMaterStep.swift
│   │   ├── InterestsStep.swift
│   │   └── RivalsStep.swift
│   ├── Preferences/
│   │   └── PreferencesView.swift
│   ├── Shared/
│   │   ├── PulseBadge.swift       # Pulse score ring
│   │   ├── TeamLogo.swift         # AsyncImage with fallback
│   │   ├── ProbabilityText.swift  # "65%" styled text
│   │   └── SportBadge.swift
│   └── Auth/
│       └── SignInView.swift       # Apple + Google sign-in buttons
├── Theme/
│   ├── Colors.swift               # Match web design tokens
│   ├── Typography.swift           # Font styles
│   └── Spacing.swift              # Layout constants
├── Extensions/
│   ├── Date+Formatting.swift
│   ├── Double+Probability.swift
│   └── Color+Hex.swift
├── Resources/
│   ├── Assets.xcassets            # App icon, colors, images
│   ├── GoogleService-Info.plist   # Firebase config
│   └── Localizable.strings
└── Preview Content/
    └── SampleData.swift           # Mock data for SwiftUI previews
```

In Xcode: **File → New → Group** for each folder. Then **File → New → Swift File** for each `.swift` file.

---

## Phase 2: Dependencies (Swift Package Manager)

### 2.1 — Add Firebase SDK
1. **File → Add Package Dependencies**
2. URL: `https://github.com/firebase/firebase-ios-sdk`
3. Version: **Up to Next Major** from `11.0.0`
4. Add these libraries (check the boxes):
   - `FirebaseAuth`
   - `FirebaseAnalytics`
   - `FirebaseMessaging` (for push notifications later)

### 2.2 — Add Google Sign-In SDK
1. **File → Add Package Dependencies**
2. URL: `https://github.com/google/GoogleSignIn-iOS`
3. Version: **Up to Next Major** from `8.0.0`
4. Add: `GoogleSignIn`, `GoogleSignInSwift`

### 2.3 — Add Charts library
1. **File → Add Package Dependencies**
2. URL: `https://github.com/danielgindi/Charts`
3. Version: **Up to Next Major** from `5.0.0`
4. Add: `DGCharts`

(Alternatively, use Apple's native `Charts` framework if iOS 17+ is sufficient — it's built in and requires no dependency.)

### 2.4 — Add Kingfisher (image caching)
1. **File → Add Package Dependencies**
2. URL: `https://github.com/onevcat/Kingfisher`
3. Version: **Up to Next Major** from `8.0.0`

---

## Phase 3: Firebase Configuration

### 3.1 — Add iOS app to Firebase project
1. Go to [Firebase Console](https://console.firebase.google.com/) → your project
2. **Project Settings** → **General** → **Add app** → **iOS**
3. Bundle ID: `com.bainluck.app`
4. App nickname: `Bain Luck iOS`
5. Download `GoogleService-Info.plist`
6. Drag it into your Xcode project root (check "Copy items if needed", add to BainLuck target)

### 3.2 — Configure Apple Sign-In in Firebase
1. Firebase Console → **Authentication** → **Sign-in method**
2. Enable **Apple** provider
3. Fill in:
   - Service ID: `com.bainluck.auth`
   - Apple Team ID: (from developer.apple.com → Membership)
   - Key ID: (from the `.p8` key you created in Phase 0)
   - Private Key: (paste contents of the `.p8` file)

### 3.3 — Configure Google Sign-In in Firebase
1. Firebase Console → **Authentication** → **Sign-in method** → **Google** (should already be enabled from web)
2. Note the **iOS client ID** from `GoogleService-Info.plist` (the `CLIENT_ID` field)
3. In Xcode → Project → **Info** tab → **URL Types** → Add:
   - URL Schemes: the **reversed** client ID from `GoogleService-Info.plist` (e.g., `com.googleusercontent.apps.123456-abcdef`)

### 3.4 — Link GA4 property
1. Firebase Console → **Project Settings** → **Integrations** → **Google Analytics**
2. Confirm it's linked to your `G-CY59Q6K975` property (you just did this)
3. Firebase Analytics events from the iOS app will now flow into the same GA4 property as the web app

---

## Phase 4: Core Implementation

### 4.1 — App entry point (`BainLuckApp.swift`)

```swift
import SwiftUI
import FirebaseCore
import FirebaseAuth
import GoogleSignIn

@main
struct BainLuckApp: App {
    @StateObject private var appState = AppState()

    init() {
        FirebaseApp.configure()
    }

    var body: some Scene {
        WindowGroup {
            MainTabView()
                .environmentObject(appState)
                .onOpenURL { url in
                    GIDSignIn.sharedInstance.handle(url)
                }
        }
    }
}
```

### 4.2 — App state (`AppState.swift`)

```swift
import SwiftUI
import FirebaseAuth

@MainActor
@Observable
class AppState: ObservableObject {
    var user: FirebaseAuth.User?
    var isAuthenticated: Bool { user != nil }
    var isLoading = true

    private var authListener: AuthStateDidChangeListenerHandle?

    init() {
        authListener = Auth.auth().addStateDidChangeListener { [weak self] _, user in
            self?.user = user
            self?.isLoading = false
        }
    }
}
```

### 4.3 — API client (`APIClient.swift`)

```swift
import Foundation
import FirebaseAuth

actor APIClient {
    static let shared = APIClient()
    private let baseURL = URL(string: "https://api.bainluck.com")!
    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    func fetch<T: Decodable>(_ path: String, query: [String: String] = []) async throws -> T {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }

        var request = URLRequest(url: components.url!)
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        // Attach auth token if available
        if let user = Auth.auth().currentUser {
            let token = try await user.getIDToken()
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0)
        }
        return try decoder.decode(T.self, from: data)
    }
}

enum APIError: Error {
    case httpError(Int)
    case decodingError(Error)
}
```

### 4.4 — Models (match your backend API responses)

```swift
// Event.swift
struct Event: Codable, Identifiable, Hashable {
    let id: Int
    let sportKey: String
    let homeTeamName: String
    let awayTeamName: String
    let commenceTime: Date?
    let status: String  // "scheduled", "live", "completed", "closed"
    let homeScore: Int?
    let awayScore: Int?
    let homeProbability: Double?
    let awayProbability: Double?
    let openingOddsHome: Double?
    let openingOddsAway: Double?
    let pulse: PulseData?
    let homeTeam: TeamInfo?
    let awayTeam: TeamInfo?
    let gameClock: String?
    let period: Int?
    let broadcastInfo: String?
}

struct PulseData: Codable, Hashable {
    let score: Int?
    let rawScore: Double?
    let status: String?
    let emoji: String?
    let label: String?
}

struct TeamInfo: Codable, Hashable {
    let id: Int?
    let primaryColor: String?
    let secondaryColor: String?
    let logoUrlSmall: String?
    let logoUrlLarge: String?
    let currentRecord: String?
}

// FeedItem.swift
struct FeedResponse: Codable {
    let items: [FeedItem]
}

struct FeedItem: Codable, Identifiable {
    let id: String  // "event-123" or "futures-456"
    let type: String  // "event" or "futures"
    let section: String  // "live", "just_happened", "upcoming", "top_markets"
    let event: Event?
    let market: FuturesMarket?
    let reason: String?
    let score: Double?
    let badges: [String]?
}

// FuturesMarket.swift
struct FuturesMarket: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let sportKey: String?
    let llmSportCategory: String?
    let marketTier: Int?
    let outcomes: [FuturesOutcome]?
}

struct FuturesOutcome: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let currentProbability: Double?
    let previousProbability: Double?
}
```

### 4.5 — Theme (`Colors.swift`)

Map your web design tokens to SwiftUI:

```swift
import SwiftUI

extension Color {
    // Surface colors (dark theme)
    static let surfaceDeep = Color(hex: "09090b")
    static let surfaceCard = Color(hex: "18181b")
    static let surfaceElevated = Color(hex: "27272a")
    static let surfaceBorder = Color(hex: "3f3f46")

    // Text colors
    static let textPrimary = Color(hex: "fafafa")
    static let textSecondary = Color(hex: "a1a1aa")
    static let textMuted = Color(hex: "71717a")

    // Accent
    static let accentBrand = Color(hex: "3b82f6")

    init(hex: String) {
        let scanner = Scanner(string: hex)
        var rgb: UInt64 = 0
        scanner.scanHexInt64(&rgb)
        self.init(
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255
        )
    }
}
```

---

## Phase 5: Authentication

### 5.1 — Auth service (`AuthService.swift`)

```swift
import AuthenticationServices
import FirebaseAuth
import GoogleSignIn
import GoogleSignInSwift

@MainActor
class AuthService {
    static let shared = AuthService()

    // MARK: - Apple Sign-In
    func signInWithApple(credential: ASAuthorizationAppleIDCredential) async throws {
        guard let tokenData = credential.identityToken,
              let token = String(data: tokenData, encoding: .utf8) else {
            throw AuthError.missingToken
        }

        let firebaseCredential = OAuthProvider.appleCredential(
            withIDToken: token,
            rawNonce: nil,  // Add nonce for production security
            fullName: credential.fullName
        )

        try await Auth.auth().signIn(with: firebaseCredential)
    }

    // MARK: - Google Sign-In
    func signInWithGoogle(presenting: UIViewController) async throws {
        guard let clientID = FirebaseApp.app()?.options.clientID else {
            throw AuthError.missingClientID
        }

        let config = GIDConfiguration(clientID: clientID)
        GIDSignIn.sharedInstance.configuration = config

        let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: presenting)
        guard let idToken = result.user.idToken?.tokenString else {
            throw AuthError.missingToken
        }

        let credential = GoogleAuthProvider.credential(
            withIDToken: idToken,
            accessToken: result.user.accessToken.tokenString
        )

        try await Auth.auth().signIn(with: credential)
    }

    // MARK: - Sign Out
    func signOut() throws {
        try Auth.auth().signOut()
        GIDSignIn.sharedInstance.signOut()
    }
}

enum AuthError: Error {
    case missingToken
    case missingClientID
}
```

### 5.2 — Sign-In view (`SignInView.swift`)

```swift
import SwiftUI
import AuthenticationServices
import GoogleSignInSwift

struct SignInView: View {
    @EnvironmentObject var appState: AppState
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 16) {
            Text("Sign in to sync your teams and preferences")
                .font(.subheadline)
                .foregroundStyle(.textSecondary)
                .multilineTextAlignment(.center)

            // Apple Sign-In (required by App Store)
            SignInWithAppleButton(.signIn) { request in
                request.requestedScopes = [.fullName, .email]
            } onCompletion: { result in
                Task {
                    switch result {
                    case .success(let auth):
                        if let credential = auth.credential as? ASAuthorizationAppleIDCredential {
                            try await AuthService.shared.signInWithApple(credential: credential)
                        }
                    case .failure(let error):
                        errorMessage = error.localizedDescription
                    }
                }
            }
            .signInWithAppleButtonStyle(.white)
            .frame(height: 50)

            // Google Sign-In
            GoogleSignInButton(style: .wide) {
                Task {
                    guard let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
                          let root = windowScene.windows.first?.rootViewController else { return }
                    try await AuthService.shared.signInWithGoogle(presenting: root)
                }
            }
            .frame(height: 50)

            if let error = errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
        .padding()
    }
}
```

---

## Phase 6: Core Views

### 6.1 — Tab bar (`MainTabView.swift`)

```swift
import SwiftUI

struct MainTabView: View {
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                FeedView()
            }
            .tabItem { Label("Feed", systemImage: "chart.line.uptrend.xyaxis") }
            .tag(0)

            NavigationStack {
                SearchView()
            }
            .tabItem { Label("Search", systemImage: "magnifyingglass") }
            .tag(1)

            NavigationStack {
                MyStuffView()
            }
            .tabItem { Label("My Stuff", systemImage: "heart.fill") }
            .tag(2)

            NavigationStack {
                PreferencesView()
            }
            .tabItem { Label("Settings", systemImage: "gearshape") }
            .tag(3)
        }
        .tint(.accentBrand)
        .preferredColorScheme(.dark)
    }
}
```

### 6.2 — Feed view (`FeedView.swift`)

```swift
import SwiftUI

struct FeedView: View {
    @StateObject private var vm = FeedViewModel()
    @EnvironmentObject var appState: AppState

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(vm.sections) { section in
                    if !section.items.isEmpty {
                        FeedSectionHeader(title: section.title)
                        ForEach(section.items) { item in
                            if item.type == "event", let event = item.event {
                                NavigationLink(value: event) {
                                    EventCardView(event: event, reason: item.reason)
                                }
                            } else if item.type == "futures", let market = item.market {
                                NavigationLink(value: market) {
                                    FuturesCardView(market: market)
                                }
                            }
                        }
                    }
                }
            }
            .padding(.horizontal)
        }
        .background(Color.surfaceDeep)
        .navigationTitle("Bain Luck")
        .navigationDestination(for: Event.self) { event in
            EventDetailView(eventId: event.id)
        }
        .navigationDestination(for: FuturesMarket.self) { market in
            FuturesDetailView(marketId: market.id)
        }
        .refreshable { await vm.refresh() }
        .task { await vm.load() }
    }
}
```

### 6.3 — Feed view model (`FeedViewModel.swift`)

```swift
import SwiftUI

struct FeedSection: Identifiable {
    let id: String
    let title: String
    let items: [FeedItem]
}

@MainActor
@Observable
class FeedViewModel: ObservableObject {
    var sections: [FeedSection] = []
    var isLoading = false
    var error: String?

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }

        do {
            let response: FeedResponse = try await APIClient.shared.fetch("/api/feed")
            let grouped = Dictionary(grouping: response.items, by: \.section)
            sections = [
                FeedSection(id: "live", title: "Live Now", items: grouped["live"] ?? []),
                FeedSection(id: "just_happened", title: "Just Happened", items: grouped["just_happened"] ?? []),
                FeedSection(id: "upcoming", title: "Upcoming", items: grouped["upcoming"] ?? []),
                FeedSection(id: "top_markets", title: "Top Markets", items: grouped["top_markets"] ?? []),
            ]
        } catch {
            self.error = error.localizedDescription
        }
    }

    func refresh() async {
        await load()
    }
}
```

### 6.4 — Event card (`EventCardView.swift`)

```swift
import SwiftUI

struct EventCardView: View {
    let event: Event
    let reason: String?

    var body: some View {
        VStack(spacing: 8) {
            // Teams row
            HStack {
                TeamRow(name: event.awayTeamName, logo: event.awayTeam?.logoUrlSmall,
                        color: event.awayTeam?.primaryColor, score: event.awayScore,
                        probability: event.awayProbability, isWinner: isAwayWinner)
                Spacer()
                TeamRow(name: event.homeTeamName, logo: event.homeTeam?.logoUrlSmall,
                        color: event.homeTeam?.primaryColor, score: event.homeScore,
                        probability: event.homeProbability, isWinner: isHomeWinner)
            }

            // Probability bar
            if let home = event.homeProbability, let away = event.awayProbability {
                ProbabilityBar(homePct: home, awayPct: away,
                             homeColor: Color(hex: event.homeTeam?.primaryColor ?? "3b82f6"),
                             awayColor: Color(hex: event.awayTeam?.primaryColor ?? "ef4444"))
            }

            // Reason text + Pulse badge
            HStack {
                if let reason, !reason.isEmpty {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.textMuted)
                }
                Spacer()
                if let pulse = event.pulse, let score = pulse.score {
                    PulseBadge(score: score)
                }
            }
        }
        .padding()
        .background(Color.surfaceCard)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.surfaceBorder, lineWidth: 1)
        )
    }

    private var isHomeWinner: Bool {
        event.status == "completed" && (event.homeScore ?? 0) > (event.awayScore ?? 0)
    }
    private var isAwayWinner: Bool {
        event.status == "completed" && (event.awayScore ?? 0) > (event.homeScore ?? 0)
    }
}
```

---

## Phase 7: Odds Chart (Swift Charts)

### 7.1 — Chart view using Apple's native Charts framework

```swift
import SwiftUI
import Charts

struct OddsChartView: View {
    let history: [OddsHistoryPoint]
    let sources: [WinProbSource]
    @State private var selectedRange: TimeRange = .all

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Time range picker
            Picker("Range", selection: $selectedRange) {
                ForEach(TimeRange.allCases, id: \.self) { range in
                    Text(range.label).tag(range)
                }
            }
            .pickerStyle(.segmented)

            // Chart
            Chart {
                // 50% reference line
                RuleMark(y: .value("Even", 0.5))
                    .foregroundStyle(.gray.opacity(0.3))
                    .lineStyle(StrokeStyle(dash: [4, 4]))

                // Odds consensus line
                ForEach(filteredHistory, id: \.timestamp) { point in
                    LineMark(
                        x: .value("Time", point.timestamp),
                        y: .value("Probability", point.homeProbability)
                    )
                    .foregroundStyle(Color.accentBrand)
                    .lineStyle(StrokeStyle(lineWidth: 2))
                }

                // Additional sources (ESPN, Kalshi, Polymarket, etc.)
                ForEach(sources) { source in
                    ForEach(source.points, id: \.timestamp) { point in
                        LineMark(
                            x: .value("Time", point.timestamp),
                            y: .value("Probability", point.value),
                            series: .value("Source", source.name)
                        )
                        .foregroundStyle(Color(hex: source.color))
                        .lineStyle(StrokeStyle(lineWidth: 1.5, dash: source.dashPattern))
                    }
                }
            }
            .chartYScale(domain: 0...1)
            .chartYAxis {
                AxisMarks(values: [0, 0.25, 0.5, 0.75, 1.0]) { value in
                    AxisValueLabel {
                        if let v = value.as(Double.self) {
                            Text("\(Int(v * 100))%")
                                .font(.caption2)
                                .foregroundStyle(.textMuted)
                        }
                    }
                }
            }
            .frame(height: 220)
        }
    }

    private var filteredHistory: [OddsHistoryPoint] {
        guard selectedRange != .all else { return history }
        let cutoff = Date().addingTimeInterval(-selectedRange.seconds)
        return history.filter { $0.timestamp >= cutoff }
    }
}

enum TimeRange: String, CaseIterable {
    case hour1 = "1H"
    case hours6 = "6H"
    case day1 = "1D"
    case all = "All"

    var label: String { rawValue }
    var seconds: TimeInterval {
        switch self {
        case .hour1: return 3600
        case .hours6: return 3600 * 6
        case .day1: return 86400
        case .all: return .infinity
        }
    }
}
```

---

## Phase 8: Analytics

### 8.1 — Analytics service (`AnalyticsService.swift`)

```swift
import FirebaseAnalytics

enum AnalyticsService {
    static func trackPageView(pageType: String, pageTitle: String, params: [String: Any] = [:]) {
        var eventParams: [String: Any] = [
            "page_type": pageType,
            "page_title": pageTitle,
            "platform": "ios"
        ]
        eventParams.merge(params) { _, new in new }
        Analytics.logEvent(AnalyticsEventScreenView, parameters: eventParams)
    }

    static func trackEvent(_ name: String, params: [String: Any] = [:]) {
        var eventParams = params
        eventParams["platform"] = "ios"
        Analytics.logEvent(name, parameters: eventParams)
    }

    static func trackCardClick(eventId: Int, sport: String, section: String, position: Int) {
        Analytics.logEvent("event_card_click", parameters: [
            "event_id": eventId,
            "sport": sport,
            "source_section": section,
            "position_index": position,
            "platform": "ios"
        ])
    }

    static func trackChartTimeRange(eventId: Int, range: String) {
        Analytics.logEvent("chart_time_range", parameters: [
            "event_id": eventId,
            "range": range,
            "platform": "ios"
        ])
    }
}
```

All events flow into the same GA4 property (`G-CY59Q6K975`) as your web events, with `platform: "ios"` to distinguish.

---

## Phase 9: App Store Preparation

### 9.1 — App icon
1. Create a 1024x1024 PNG (no transparency, no rounded corners — Apple applies the mask)
2. In Xcode → **Assets.xcassets** → **AppIcon** → drag your 1024px image in
3. Xcode auto-generates all required sizes

### 9.2 — Launch screen
1. In Xcode, edit **LaunchScreen** (or create a `LaunchScreen.storyboard`)
2. Set background to your `surfaceDeep` color (#09090b)
3. Add your logo centered

### 9.3 — Privacy manifest (`PrivacyInfo.xcprivacy`)
Required since spring 2024. Create this file:
1. **File → New → File → App Privacy** → name it `PrivacyInfo`
2. Declare:
   - **NSPrivacyTracking**: `NO` (you don't do ATT tracking)
   - **NSPrivacyCollectedDataTypes**: Analytics data (linked to user if signed in)
   - **NSPrivacyTrackingDomains**: empty
   - **NSPrivacyAccessedAPITypes**: `UserDefaults` (for pin storage)

### 9.4 — App Store Connect setup
1. Go to https://appstoreconnect.apple.com/
2. **My Apps** → **+** → **New App**
3. Fill in:
   - Platform: **iOS**
   - Name: **Bain Luck**
   - Primary Language: English (U.S.)
   - Bundle ID: `com.bainluck.app`
   - SKU: `bainluck-ios`
4. Fill in:
   - Subtitle: "Win probabilities, not betting lines"
   - Category: **Sports**
   - Secondary Category: **News**
   - Privacy Policy URL: `https://bainluck.com/privacy` (you'll need to create this page)
   - Age Rating: 17+ (due to gambling references — odds display may trigger this)

### 9.5 — Screenshots
You need screenshots for:
- 6.7" (iPhone 15 Pro Max): 1290 x 2796
- 6.5" (iPhone 11 Pro Max): 1242 x 2688 (optional but recommended)
- iPad Pro 12.9": 2048 x 2732 (if supporting iPad)

Use Xcode Simulator to capture, or design marketing screenshots in Figma.

### 9.6 — Build and upload
1. In Xcode: **Product → Archive**
2. When the archive completes, click **Distribute App** → **App Store Connect** → **Upload**
3. Wait for processing (~15 min)
4. In App Store Connect, select the build for your version → **Submit for Review**

---

## Phase 10: App Review Checklist

Things Apple will check (and reject you for if missing):

1. **Privacy policy page** — must exist at a public URL before submission
2. **Apple Sign-In working** — they'll test it
3. **No web view wrapping** — if they detect you're just wrapping a website, they'll reject. The app must feel native (SwiftUI navigation, native tab bar, native gestures)
4. **Gambling disclaimer** — since you display odds, you may need to clarify in the review notes that the app displays publicly available odds for informational purposes only and does not facilitate gambling
5. **No placeholder content** — every screen must work
6. **Data deletion** — if users can create accounts, you must provide account deletion (add to Preferences)

**Review notes to include with your submission:**

> "This app displays publicly available sports odds converted to win probabilities for informational and entertainment purposes. It does not facilitate, enable, or link to any form of gambling or wagering. Users cannot place bets through this app. Data is sourced from publicly available APIs (The Odds API, Kalshi, Polymarket) and displayed as probability percentages."

---

## Recommended Build Order

Do these in order, testing each phase before moving on:

1. **Phase 0-1**: Apple Developer + Xcode project → verify it builds and runs on simulator
2. **Phase 2-3**: Dependencies + Firebase → verify Firebase initializes (check Xcode console for "Firebase configured")
3. **Phase 4**: API client + models → verify you can fetch and print feed data from `api.bainluck.com`
4. **Phase 6**: Feed view + event cards → verify scrollable feed renders with real data
5. **Phase 5**: Auth → verify Apple + Google sign-in work
6. **Phase 7**: Odds chart → verify chart renders with history data
7. **Phase 8**: Analytics → verify events appear in GA4 Realtime
8. **Remaining views**: Search, My Stuff, Onboarding, Preferences, Futures
9. **Phase 9-10**: App Store submission

The code samples above are starting points — you'll iterate on styling and edge cases as you build each view. The models will need adjustment as you discover differences between the actual API responses and these type definitions. Test against `api.bainluck.com/docs` for the exact response shapes.
