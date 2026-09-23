import Foundation

/// Launch-argument affordances for the headless LOOK rig (#3157), in the shape
/// #3141 established for the notification prompt.
///
/// The class of defect this exists to end is "the rig's arguments are silently
/// inert". `tools/native-g1-shoot.sh` passed `-temp_screenshot_tab` and
/// `-temp_screenshot_counts` for weeks; no Swift file on master has ever read
/// either. They live only in a scaffold that has to be copied in, hooked up,
/// built, shot, deleted and grepped for residue — so the rig looked like it was
/// driving the app and was doing nothing, and every unattended shot was of
/// Discover because Discover is the default tab.
///
/// Both affordances below are pure, injectable functions over `UserDefaults`,
/// so the contract the shoot scripts depend on is a test rather than a
/// convention. Neither can change what a reader who never passes them sees.
enum LaunchRig {

    // MARK: - Driving the app to a screen

    /// Launch-argument key carrying the screen to open, as a URL.
    ///
    /// `xcrun simctl launch <sim> <bundle> -launch_route "bainluck://search?q=US%20Open"`.
    static let routeKey = "launch_route"

    /// The screen the rig asked for, or `nil` when it asked for nothing.
    ///
    /// Deliberately a URL rather than a tab name: `NavigationCoordinator.handleURL`
    /// is already the app's one router, already tested, and already reaches every
    /// tab plus event detail, hubs, categories and a seeded search query. Parsing
    /// tab names here would be a second router to keep in sync with the first.
    ///
    /// Only Bain Luck's own links are accepted. That is not a security boundary —
    /// `handleURL` rejects foreign URLs anyway — it is what keeps this a screen
    /// selector rather than a general-purpose URL opener wired into a shipping
    /// build.
    static func route(defaults: UserDefaults = .standard) -> URL? {
        guard let raw = defaults.string(forKey: routeKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !raw.isEmpty,
            let url = URL(string: raw)
        else { return nil }

        if url.scheme == "bainluck" { return url }
        if url.host == "bainluck.com" || url.host == "www.bainluck.com" { return url }
        return nil
    }

    /// How long to wait before handing the route to the router.
    ///
    /// The first frame is not a mounted app: `ContentView`'s `TabView` builds
    /// only the selected tab, and Discover's own load is in flight. Routing into
    /// that window lands on a screen that is still deciding what it is. One beat
    /// is enough and is what native/019's hand-patched version used.
    static let routeDelay: TimeInterval = 2.5

    // MARK: - Photographing the count

    /// Launch-argument key that draws the served/drawn card counts over Discover.
    ///
    /// `xcrun simctl launch <sim> <bundle> -launch_debug_counts YES`.
    static let debugCountsKey = "launch_debug_counts"

    /// Whether Discover should draw its own card counter.
    ///
    /// SHOWABLE-1 G1's bar is a number — "Discover shows the feed the API sends
    /// (≥28 cards)" — and a photograph of a page that merely *looks* populated
    /// does not prove it. The counter makes the gate's own number visible to the
    /// camera. Off unless asked for, so no reader ever sees it.
    static func showsDebugCounts(defaults: UserDefaults = .standard) -> Bool {
        defaults.bool(forKey: debugCountsKey)
    }

    // MARK: - Photographing what is behind a disclosure

    /// Launch-argument key that starts collapsed disclosure sections OPEN.
    ///
    /// `xcrun simctl launch <sim> <bundle> -launch_expand_sections YES`.
    static let expandSectionsKey = "launch_expand_sections"

    /// Whether a collapsed section should start open for the camera.
    ///
    /// The event page's Sources list is behind a `@State` chevron that defaults
    /// closed, and the rig cannot tap — `-launch_scroll` moves a scroll view, it
    /// does not press a button. So no screenshot of that list had ever been
    /// taken, and #4107 (a hardcoded 118pt label column that never tracked
    /// Dynamic Type) sat unmeasured behind it: not because the defect was subtle
    /// but because the surface was unreachable.
    ///
    /// This is the same gap `-launch_scroll` was built to close, and the same
    /// argument applies — a defect nobody can photograph is a defect nobody can
    /// prove fixed. Off unless asked for, so the chevron a reader sees is
    /// unchanged and still starts closed.
    static func expandsCollapsedSections(defaults: UserDefaults = .standard) -> Bool {
        defaults.bool(forKey: expandSectionsKey)
    }

    // MARK: - Photographing a control the rig cannot tap

    /// Launch-argument key that starts the Evolution chart's `Sum` line ON.
    ///
    /// `xcrun simctl launch <sim> <bundle> -launch_chart_sum YES`.
    ///
    /// Same hole as `-launch_expand_sections`, one control along: the rig cannot
    /// tap, `Sum` is a `@State` checkbox that defaults off, and so the combined line
    /// had never been photographed at all. That is how a flat dashed line pinned to
    /// 100% across every point of a props market went unseen — not because it was
    /// subtle, but because no camera could reach it. Off unless asked for, so the
    /// checkbox a reader sees still starts clear.
    static let chartSumKey = "launch_chart_sum"

    /// Whether the chart's combined line should start drawn for the camera.
    ///
    /// Only ever ASKS for the line. Whether one is drawn is still
    /// `EvolutionCombinedLinePolicy`'s call, so this flag cannot photograph a chart
    /// no reader could get to — which is the property that makes it evidence.
    static func startsChartSumOn(defaults: UserDefaults = .standard) -> Bool {
        defaults.bool(forKey: chartSumKey)
    }

    // MARK: - Photographing what is BELOW the fold

    /// Launch-argument key carrying how far down the page to scroll, in POINTS,
    /// before the camera fires.
    ///
    /// `xcrun simctl launch <sim> <bundle> -launch_scroll 1600`.
    ///
    /// The rig has photographed one viewport since #3157, and an event page is
    /// several viewports tall — so the margin maps, the half maps and the
    /// probability ladders have never been photographed at all. #3533 had to be
    /// filed with "its rendering is unverified" written into the issue for
    /// exactly this reason, and native/029–036 each shot only the hero. A defect
    /// nobody can photograph is a defect nobody can prove fixed, which is how a
    /// LOOK-driven queue runs out of things it can honestly close.
    ///
    /// Points, not "pages", because a point is what both `UIScrollView` and the
    /// device geometry are already denominated in (iPhone 17 is 402×874 points),
    /// so a number here is checkable against a screenshot without a conversion
    /// nobody can remember.
    static let scrollKey = "launch_scroll"

    /// How far the rig asked to scroll, or `nil` when it asked for nothing.
    ///
    /// Refuses zero and negatives rather than clamping them to zero: a caller
    /// that passes `-launch_scroll 0` or `-launch_scroll -100` has made a
    /// mistake, and answering "the top of the page" would hand back a shot that
    /// looks exactly like a successful un-scrolled shot. Nil is the honest
    /// answer, and the shoot script can then say so.
    static func scrollOffset(defaults: UserDefaults = .standard) -> Double? {
        guard let raw = defaults.string(forKey: scrollKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !raw.isEmpty,
            let points = Double(raw),
            points > 0,
            points.isFinite
        else { return nil }
        return points
    }

    // MARK: - Keeping a robot's taps out of the personalization data

    /// Launch-argument key that stops the app POSTing Discover interactions.
    ///
    /// `xcrun simctl launch <sim> <bundle> -launch_no_interaction_upload YES`.
    static let suppressInteractionUploadKey = "launch_no_interaction_upload"

    /// Whether this process may report Discover interactions to the server.
    ///
    /// EVERY OTHER RIG AFFORDANCE HERE IS READ-ONLY WITH RESPECT TO PRODUCTION,
    /// AND THE TAP PATHS ARE NOT. A swipe, a card open and a share each POST a
    /// row to `/api/feed/interactions` under an anonymous `x-session-id`
    /// (`DiscoverView.recordInteraction`, `ShareInstrumentation`). For a reader
    /// that is the point — it is the downrank signal #1221 designed. For an
    /// unattended test that taps twenty cards a night it is a robot minting
    /// "what people are doing" rows, which is the exact failure standing notice
    /// 39 exists to prevent: our own robots are TAGGED, never minted.
    ///
    /// So a tap-driven rig passes this and the POST is not made. Off unless
    /// asked for, so a reader's swipe is unchanged and still counts.
    ///
    /// Deliberately NOT a "disable analytics" flag and not a network switch.
    /// Killing the transport would also kill the GETs the screen needs, and a
    /// test cannot tell a suppressed feed from a broken one. This is one
    /// endpoint, named, at the one choke point all four call sites already go
    /// through.
    static func suppressesInteractionUpload(defaults: UserDefaults = .standard) -> Bool {
        defaults.bool(forKey: suppressInteractionUploadKey)
    }

    // MARK: - Making a refresh's response genuinely, controllably DIFFERENT

    /// Launch-argument key that withholds the first N cards from every network
    /// publication AFTER the first one, so a pull's response differs from the
    /// published one by construction.
    ///
    /// `xcrun simctl launch <sim> <bundle> -launch_changed_refresh 5`.
    ///
    /// 🪤 **"AFTER THE FIRST PUBLICATION", NOT "AFTER THE FIRST PAINT" — AND THE
    /// DIFFERENCE IS THE WHOLE AFFORDANCE.** This said "after the first paint"
    /// until native/247, and the call site implemented that literally, as
    /// `!items.isEmpty`. **The last-good cache seed is a paint.** So in a WARM
    /// container the first *network* load was already withheld, the journey's
    /// BEFORE and AFTER were both staged, and it measured `SERVED 20 → 20` —
    /// reporting *the feed did not change* on a refresh that published correctly.
    /// Green in a cold container, red in the class run, same build: the shape of
    /// an instrument reading shared container state rather than the app.
    ///
    /// The payload the change is measured AGAINST must be one the server really
    /// sent, so the witness is a completed NETWORK publication
    /// (`DiscoverViewModel.hasPublishedNetworkFeed`) and nothing a cache can
    /// satisfy.
    ///
    /// 🔴 THE GAP THIS EXISTS FOR, IN #7074'S OWN WORDS. Alex, physical phone,
    /// build 15: *"Pull gesture briefly shows activity with no apparent change."*
    /// The issue ruled that INCONCLUSIVE and set the bar: *"Prove
    /// gesture→request→completion and useful stable position on a controlled
    /// changed-response test"*, and — one line later — *"Test actual gestures and
    /// read frames, not state-machine tests alone."*
    ///
    /// Those two sentences pull in opposite directions against the live API, and
    /// that is the whole difficulty. A journey with a finger cannot CONTROL what
    /// production serves, and the server may legitimately serve the same cards
    /// twice — so a live-API journey asserting "the cards changed" would red on a
    /// working app. native/243 resolved the contradiction by moving the controlled
    /// half onto the `DiscoverFeedProviding` seam, and said plainly what that
    /// costs: a seam test proves the publication rule and proves nothing about
    /// whether a finger ever produces it. Both halves were honest; neither was the
    /// arm.
    ///
    /// This closes it from the other side: keep the real network, the real
    /// gesture and the real screen, and make the *difference* the controlled
    /// variable.
    ///
    /// ⚠️ AND IT IS THE FIRST RIG AFFORDANCE THAT CHANGES WHAT THE READER IS
    /// SHOWN. Every other key here is read-only with respect to the feed — a
    /// counter drawn over it, a chevron opened, a scroll offset, one POST
    /// withheld. This one withholds CARDS, so a build that shipped with it live
    /// would quietly serve a shortened feed: the failure would look like a
    /// backend defect and nothing on the screen would say otherwise.
    ///
    /// So, unlike its siblings, **its one call site is `#if DEBUG`**
    /// (`DiscoverViewModel.load()`), and the shipping configuration is Release.
    /// Not a convention — a compile-time absence. The reader of a TestFlight
    /// build cannot reach this behaviour by passing the argument, because the
    /// code that honours it is not in their binary. The key is still read
    /// unconditionally, and still contract-tested beside its siblings, precisely
    /// so the thing under test is the same function the rig calls.
    /// 📎 ONE KNOWN SIDE EFFECT, WRITTEN DOWN RATHER THAN DISCOVERED. Withholding
    /// cards restamps the painted edition, and `loadMoreIfNeeded` discards a page
    /// whose token does not match the list it would splice into (#4110). So while
    /// this flag is set, infinite scroll stops yielding new pages — through the
    /// existing bounded duplicate-path, not a crash or a blank. That is correct
    /// behaviour for a list the server never sent, and it is fine for a journey
    /// that pulls at the top; it would quietly ruin a pagination journey, so do
    /// not combine the two.
    static let changedRefreshKey = "launch_changed_refresh"

    /// How many cards the rig asked a refresh to withhold, or `nil` for none.
    ///
    /// Refuses zero, negatives and non-numbers rather than clamping them, for
    /// ``scrollOffset``'s reason and a sharper one: every refused value here
    /// would produce an UNCHANGED response, which is exactly the state the
    /// journey exists to distinguish from a changed one. A clamp would hand the
    /// test a passing-looking run of the experiment it did not perform.
    /// 🪤 READ THROUGH `object(forKey:)`, NOT `string(forKey:)`. The argument
    /// domain type-coerces: `-launch_changed_refresh 12` can arrive as an
    /// `NSNumber` rather than the `"12"` the command line appears to pass. A
    /// string-only read then answers `nil`, the rig withholds nothing, and the
    /// journey downstream measures an unchanged refresh and reports **that the
    /// feed did not change** — the product verdict, produced by the instrument.
    /// Both forms are accepted here and both are asserted in the contract test.
    ///
    /// Refuses zero, negatives and non-integers rather than clamping them, for
    /// ``scrollOffset``'s reason and a sharper one: every refused value would
    /// produce an UNCHANGED response, which is exactly the state the journey
    /// exists to distinguish from a changed one. A clamp would hand the test a
    /// passing-looking run of the experiment it did not perform.
    static func changedRefreshDrop(defaults: UserDefaults = .standard) -> Int? {
        let text: String
        switch defaults.object(forKey: changedRefreshKey) {
        case let value as String: text = value
        case let value as NSNumber: text = value.stringValue
        default: return nil
        }
        guard let count = Int(text.trimmingCharacters(in: .whitespacesAndNewlines)), count > 0
        else { return nil }
        return count
    }

    /// How long to wait AFTER the route before scrolling.
    ///
    /// Longer than ``routeDelay`` and additional to it, because the two waits
    /// are for different things: routing waits for the app to mount, this waits
    /// for the destination screen's own network loads to land. Scrolling a page
    /// that is still three spinners tall lands on whatever happens to occupy
    /// that offset once the real content pushes it down — a shot of the wrong
    /// part of the page, which is worse than a shot of the top because it looks
    /// deliberate.
    static let scrollDelay: TimeInterval = 8.0

    /// The offset a scroll view can actually be put at, given the page it holds.
    ///
    /// Pure, and separated from the `UIScrollView` walk that uses it, because
    /// this is the half that can be wrong in a way a photograph cannot show.
    /// Asking for 4,000 points of a 1,200-point page and getting it would
    /// photograph past the end of the content: on iOS that is empty background,
    /// and empty background is indistinguishable in a PNG from "the card we were
    /// looking for is missing". The rig would then manufacture the exact finding
    /// it exists to test for.
    ///
    /// So the floor is the top and the ceiling is the last full viewport, and a
    /// caller that over-asks gets the BOTTOM of the page — a real part of it,
    /// which a reader can recognise.
    static func clampedScrollOffset(
        requested: Double,
        contentHeight: Double,
        viewportHeight: Double
    ) -> Double {
        let lastViewport = Swift.max(0, contentHeight - viewportHeight)
        return Swift.min(Swift.max(0, requested), lastViewport)
    }
}
