import XCTest
@testable import Bain_Luck

/// #5914 — the app's About screen rendered the whole website inside itself.
///
/// `AboutView` is an `InAppWebView` of `/about`, deliberately (L2-144: "clean
/// webview of /about is acceptable v1", so the narrative never forks). It
/// loaded the full site shell with it, and the first photograph of the screen
/// (native/145, `artifacts-native-020/about-145b.png`) shows three things that
/// belong to a website and not to an app screen: a second header carrying the
/// WEBSITE's "Sign in" button, a second tab bar drawn over the real one and
/// disagreeing with it about which tab the reader is on, and a cookie consent
/// banner floating over the copy.
///
/// The fix is a pair. ux suppresses that chrome when `/about` is asked for with
/// `?embed=1`; native passes the parameter. This file guards the native half,
/// and it guards one thing more than the parameter, because the parameter alone
/// does not finish the ship: the About copy links to /calibration, /privacy,
/// /discover and mailto:bugs@bainluck.com, and a link followed IN PLACE turns a
/// screen whose navigation bar says "About" into a second copy of the website
/// one tap later — the same defect, arriving a moment afterwards.
///
/// What this file cannot see, stated so a later reader does not mistake its
/// green for the whole ship: `next/link` navigations inside the page are
/// client-side (`pushState`), which WKWebView never shows a navigation
/// delegate, so the rule below binds real navigations only. The parameter half
/// is verified on production against ux's release, not here.
final class AboutIsOneCoherentPage5914Tests: XCTestCase {

    /// The URL `AboutView` actually loads. Assembled from the same pieces the
    /// view uses so the cases below describe the shipping screen; the scan at
    /// the bottom is what pins that they stay the same pieces.
    private let embedded = URL(string: "https://www.bainluck.com/about?embed=1")!

    private func rendersInPlace(_ candidate: String) -> Bool {
        InAppWebViewNavigation.rendersInPlace(
            URL(string: candidate)!, embedding: embedded, under: .handOffToTheSystem)
    }

    // MARK: - The control: `false` has to be capable of being `true`

    /// Every "hands off" assertion below is an `XCTAssertFalse`. If the rule
    /// refused everything — the easy way to "confine" a web view, and one that
    /// would blank the About screen — all of them would pass while the screen
    /// showed nothing at all. This is the measurement proving it can still say
    /// yes, and the next test is it proving it can still say no.
    func testTheEmbeddedPageItselfStillLoads() {
        XCTAssertTrue(
            rendersInPlace("https://www.bainluck.com/about?embed=1"),
            "the About screen refuses to load About — the rule refuses everything")
    }

    /// And the other pole: with the policy set to follow links, the same URL
    /// that gets handed off below is allowed. Without this, a rule that ignored
    /// its `policy` argument entirely would pass the whole file.
    func testFollowingInPlaceIsStillAThingTheComponentCanDo() {
        XCTAssertTrue(
            InAppWebViewNavigation.rendersInPlace(
                URL(string: "https://www.bainluck.com/discover")!,
                embedding: embedded,
                under: .followInPlace),
            "`followInPlace` refuses a link — the policy argument is being ignored")
    }

    // MARK: - The screen must not eject itself

    /// 🔴 The highest-value case in this file, and the one the apex URL would
    /// have failed. `bainluck.com` 307s to `www.bainluck.com` (measured
    /// 2026-09-14, query preserved). A host comparison that did not know the
    /// two are one site would cancel the About screen's OWN redirect and launch
    /// Safari onto it — an app that opens a browser the instant you tap About.
    func testTheApexIsTheSameSiteAsWWW() {
        XCTAssertTrue(rendersInPlace("https://bainluck.com/about?embed=1"),
                      "the apex reads as a different site — About would eject itself to Safari")
        XCTAssertTrue(
            InAppWebViewNavigation.rendersInPlace(
                URL(string: "https://www.bainluck.com/about?embed=1")!,
                embedding: URL(string: "https://bainluck.com/about?embed=1")!,
                under: .handOffToTheSystem),
            "the rule is not symmetric between the apex and www")
    }

    /// The page is the page whatever it is carrying. A reload that drops the
    /// parameter, an in-page anchor, and the trailing-slash spelling are all
    /// the screen the reader is already on; ejecting any of them would be a
    /// worse defect than the one being fixed.
    func testTheSamePageInItsOtherSpellingsStaysPut() {
        XCTAssertTrue(rendersInPlace("https://www.bainluck.com/about"),
                      "a reload without the parameter leaves the screen")
        XCTAssertTrue(rendersInPlace("https://www.bainluck.com/about#calibration"),
                      "an in-page anchor leaves the screen")
        XCTAssertTrue(rendersInPlace("https://www.bainluck.com/about/"),
                      "the trailing-slash spelling reads as a different page")
    }

    /// The empty path is `/`, and `/` is not `/about`. Reading `""` and `"/"`
    /// as different strings would make the site root a fourth spelling of
    /// whatever page happened to be embedded.
    func testABareOriginIsTheRootPathNotTheEmptyString() {
        let origin = URL(string: "https://www.bainluck.com")!
        XCTAssertTrue(
            InAppWebViewNavigation.rendersInPlace(
                URL(string: "https://www.bainluck.com/")!,
                embedding: origin,
                under: .handOffToTheSystem),
            "a bare origin and its root path read as two different pages")
        XCTAssertFalse(rendersInPlace("https://www.bainluck.com"),
                       "the site root reads as the About page")
    }

    // MARK: - The four links the About copy actually carries

    /// Read out of `frontend/app/about/page.tsx` on 2026-09-14, not invented:
    /// a `<Link>` to /calibration, a `mailto:` to bugs@, a `<Link>` to /privacy
    /// and a `<Link>` to /discover. /discover is the one that matters most — the
    /// app HAS a Discover tab, and a second one inside a screen titled "About"
    /// is precisely the "second site navigation" this ship is named for.
    func testEveryLinkInTheAboutCopyLeavesTheAppScreen() {
        for link in [
            "https://www.bainluck.com/calibration",
            "https://www.bainluck.com/privacy",
            "https://www.bainluck.com/discover",
            "mailto:bugs@bainluck.com",
        ] {
            XCTAssertFalse(rendersInPlace(link),
                           "\(link) loads inside the About screen — About is a browser again")
        }
    }

    /// The `mailto:` deserves its own sentence, because it is not only a
    /// confinement case: WKWebView cancels a scheme it cannot handle and
    /// reports nothing, so before this change the "email us" link on the About
    /// page did nothing whatsoever when tapped inside the app. Handing it to
    /// the system is what makes it open Mail.
    func testTheEmailLinkIsHandedToTheSystemRatherThanSilentlyDropped() {
        XCTAssertFalse(rendersInPlace("mailto:bugs@bainluck.com"))
    }

    /// A non-web scheme that wears our own host. Without the scheme check,
    /// host-and-path alone would say "same page" and the navigation would be
    /// allowed into a web view that cannot load it — silently, which is the
    /// failure mode the `mailto:` already demonstrated.
    func testOurOwnDeepLinkSchemeIsNotTheWebPage() {
        XCTAssertFalse(rendersInPlace("bainluck://www.bainluck.com/about"))
    }

    /// Somewhere else entirely. A source we name in the copy, a venue, an
    /// unfurled link — none of them belong inside an app screen titled About.
    func testAnotherSiteLeavesTheAppScreen() {
        XCTAssertFalse(rendersInPlace("https://kalshi.com/markets"))
        XCTAssertFalse(rendersInPlace("https://polymarket.com/"))
    }

    // MARK: - The default, and the two lines in AboutView

    /// A future screen that reaches for `InAppWebView` gets the confined
    /// behaviour without having to know about #5914. The other default — a
    /// component that quietly becomes a browser — fails in a way nobody sees
    /// until a reviewer taps something.
    func testTheComponentDefaultsToHandingLinksOff() {
        XCTAssertEqual(
            InAppWebView(url: URL(string: "https://www.bainluck.com/about")!).linkPolicy,
            .handOffToTheSystem,
            "a new caller of InAppWebView gets a browser by default")
    }

    private func aboutViewCode() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Views")
            .appendingPathComponent("AboutView.swift")
        // 🔴 COMMENTS STRIPPED. The docstring on `aboutURL` explains the embed
        // contract and therefore contains the string `embed=1`, twice. A scan
        // that read the whole file would pass on the prose alone — it would
        // still be green the day someone deleted the parameter and left the
        // paragraph describing it.
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { Self.codeBeforeAComment(on: String($0)) }
            .joined(separator: "\n")
    }

    /// The stripper the sibling guards use — `line.range(of: "//")` — cuts this
    /// file in the wrong place, and the anti-vacuity test above is what caught
    /// it: the very line under scan is `URL(string: "https://www.bainluck.com/
    /// about?embed=1")`, whose FIRST `//` is inside the scheme. That stripper
    /// left `URL(string: "https:` and the scan then truthfully reported that
    /// AboutView contains no `/about` — a guard that would have failed forever
    /// for a reason unrelated to the rule it states.
    ///
    /// So this one tracks whether it is inside a string literal, and only a
    /// `//` outside one begins a comment.
    private static func codeBeforeAComment(on line: String) -> String {
        var code = ""
        var insideStringLiteral = false
        var escaped = false
        var previousWasSlash = false

        for character in line {
            if insideStringLiteral {
                if escaped { escaped = false }
                else if character == "\\" { escaped = true }
                else if character == "\"" { insideStringLiteral = false }
                code.append(character)
                previousWasSlash = false
                continue
            }
            if character == "\"" {
                insideStringLiteral = true
                code.append(character)
                previousWasSlash = false
                continue
            }
            if character == "/" {
                if previousWasSlash { return String(code.dropLast()) }
                previousWasSlash = true
            } else {
                previousWasSlash = false
            }
            code.append(character)
        }
        return code
    }

    /// The stripper is now big enough to be wrong on its own, so it is
    /// measured rather than trusted: it must keep a URL whole and it must still
    /// remove a comment, including one sitting after code on the same line.
    /// Only the first of these three would have passed before.
    func testTheStripperKeepsURLsAndStillRemovesComments() {
        XCTAssertEqual(
            Self.codeBeforeAComment(on: #"let u = "https://www.bainluck.com/about?embed=1""#),
            #"let u = "https://www.bainluck.com/about?embed=1""#,
            "the stripper cut the URL at its scheme — every scan below is reading a stump")
        XCTAssertEqual(Self.codeBeforeAComment(on: "    /// embed=1 in prose"), "    ")
        XCTAssertEqual(
            Self.codeBeforeAComment(on: #"let u = "x"  // embed=1 in a trailing comment"#),
            #"let u = "x"  "#,
            "a trailing comment survives the stripper — prose could satisfy the scan")
    }

    /// Anti-vacuity: if this fails, every claim below is about the wrong file,
    /// or about a file the comment-stripper has eaten.
    func testTheScanCanSeeTheFileItIsAbout() throws {
        let code = try aboutViewCode()
        XCTAssertTrue(code.contains("struct AboutView"), "the scan did not find the view")
        XCTAssertTrue(code.contains("InAppWebView("), "the scan did not find the web view it is about")
        XCTAssertTrue(code.contains("/about"), "the scan did not find the URL it is about")
    }

    /// The native half of the contract, in code rather than in a comment.
    func testAboutAsksForTheEmbeddedRenderingOfThePage() throws {
        let code = try aboutViewCode()
        XCTAssertTrue(code.contains("embed=1"),
                      "AboutView no longer passes the embed signal — the site shell, "
                      + "its Sign in button and the consent banner are back on the screen")
    }

    /// And it never asks for the browser.
    func testAboutNeverFollowsLinksInPlace() throws {
        let code = try aboutViewCode()
        XCTAssertFalse(code.contains("followInPlace"),
                       "AboutView follows links in place — one tap and it is the website again")
    }
}
