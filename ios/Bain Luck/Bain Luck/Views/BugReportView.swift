import Combine
import SwiftUI
import Network
import os
#if canImport(UIKit)
import UIKit
import PencilKit
#endif

struct BugReportView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var navCoordinator: NavigationCoordinator
    @EnvironmentObject var authManager: AuthManager

    let screenshot: PlatformImage?
    @State private var description = ""
    @State private var notifyOnFix = false
    @State private var submitting = false
    @State private var submitted = false
    @State private var submitError: String? = nil

    #if os(iOS)
    @State private var canvasView = PKCanvasView()
    #endif

    #if os(macOS)
    @State private var pastedScreenshot: NSImage? = nil
    #endif

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    // Screenshot with markup
                    if let screenshot {
                        // Compute explicit display size so the overlay canvas
                        // exactly matches the rendered image (no dead space).
                        // Without this, .frame(maxHeight:) inherits the parent
                        // width, making the canvas wider than the image and
                        // causing annotation coordinate offsets.
                        let imgAspect = screenshot.size.width / screenshot.size.height
                        let displayHeight: CGFloat = min(300, screenshot.size.height)
                        let displayWidth = displayHeight * imgAspect

                        Image(platformImage: screenshot)
                            .resizable()
                            .scaledToFit()
                            .frame(width: displayWidth, height: displayHeight)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .overlay {
                                #if os(iOS)
                                CanvasOverlay(canvasView: $canvasView)
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
                                #endif
                            }
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.secondary.opacity(0.3), lineWidth: 1)
                            )
                            .padding(.horizontal)

                        #if os(iOS)
                        Text("Draw on the screenshot to highlight the issue")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        #endif
                    } else {
                        #if os(macOS)
                        VStack(spacing: 8) {
                            Image(systemName: "photo.on.rectangle")
                                .font(.system(size: 32))
                                .foregroundStyle(.secondary)
                            Text("Cmd+Ctrl+Shift+4 to copy screenshot, then click here")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, minHeight: 120)
                        .background(Color.secondary.opacity(0.05))
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(style: StrokeStyle(lineWidth: 1, dash: [6])).foregroundStyle(.secondary.opacity(0.3)))
                        .padding(.horizontal)
                        .onTapGesture {
                            let pb = NSPasteboard.general
                            // Try PNG data first (Cmd+Shift+Ctrl+4 copies to clipboard)
                            if let data = pb.data(forType: .png), let img = NSImage(data: data) {
                                pastedScreenshot = img
                            // Try TIFF (some apps put TIFF on clipboard)
                            } else if let data = pb.data(forType: .tiff), let img = NSImage(data: data) {
                                pastedScreenshot = img
                            // Try file URL (Cmd+Shift+4 saves to desktop)
                            } else if let urlStr = pb.string(forType: .fileURL),
                                      let url = URL(string: urlStr),
                                      let img = NSImage(contentsOf: url) {
                                pastedScreenshot = img
                            // Fallback: NSImage(pasteboard:)
                            } else if let img = NSImage(pasteboard: pb) {
                                pastedScreenshot = img
                            }
                        }
                        #endif
                    }

                    #if os(macOS)
                    if let pasted = pastedScreenshot {
                        Image(nsImage: pasted)
                            .resizable()
                            .scaledToFit()
                            .frame(maxHeight: 300)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.green.opacity(0.5), lineWidth: 2))
                            .padding(.horizontal)
                    }
                    #endif

                    // Description field
                    VStack(alignment: .leading, spacing: 6) {
                        Text("What went wrong?")
                            .font(.subheadline.weight(.semibold))

                        TextField("Optional — the screenshot may be enough!", text: $description, axis: .vertical)
                            .lineLimit(3...6)
                            .textFieldStyle(.roundedBorder)
                    }
                    .padding(.horizontal)

                    if authManager.isAuthenticated {
                        Toggle(isOn: $notifyOnFix) {
                            Text("Email me when this is fixed")
                                .font(.subheadline)
                        }
                        .tint(.orange)
                        .padding(.horizontal)
                    } else {
                        HStack(spacing: 8) {
                            Image(systemName: "envelope")
                                .foregroundStyle(.secondary)
                            Text("Sign in to get notified when your bug is fixed")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.horizontal)
                    }

                    if submitted {
                        HStack(spacing: 8) {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                            Text("Bug report submitted! Thanks for helping improve Bain Luck.")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .padding()
                    }

                    if let error = submitError {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(.orange)
                            Text(error)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .padding()
                    }
                }
                .padding(.vertical)
            }
            .navigationTitle("Report a Bug")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .onAppear { AnalyticsService.trackScreen(name: "bug_report", type: "bug_report") }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Submit") { submitReport() }
                        .disabled(submitting || submitted)
                        .fontWeight(.semibold)
                }
            }
        }
    }

    private func submitReport() {
        submitting = true
        Task {
            do {
                let imageData = flattenedScreenshot()
                let base64 = imageData.map { $0.base64EncodedString() }

                let tabNames = ["Feed", "Discover", "Leagues", "Search", "My Stuff"]
                let tabName = navCoordinator.selectedTab.rawValue < tabNames.count
                    ? tabNames[navCoordinator.selectedTab.rawValue]
                    : "Tab \(navCoordinator.selectedTab.rawValue)"

                var currentPage = tabName
                if let route = navCoordinator.pendingRoute {
                    switch route {
                    case .eventDetail(let id): currentPage = "Event Detail (id: \(id))"
                    case .futuresDetail(let id): currentPage = "Futures Detail (id: \(id))"
                    case .leagueGrid(let slug): currentPage = "League Grid (\(slug))"
                    case .sportCategory(let key, _): currentPage = "Sport Category (\(key))"
                    case .teamDetail(let slug): currentPage = "Team Detail (\(slug))"
                    case .golfCategory: currentPage = "Golf"
                    case .golfLeaderboard: currentPage = "Golf Leaderboard"
                    case .golfTournament(_, let name): currentPage = "Golf: \(name)"
                    case .preferences: currentPage = "Preferences"
                    case .futuresList: currentPage = "Futures Browser"
                    case .predictionStats: currentPage = "Prediction Stats"
                    case .weather: currentPage = "Weather"
                    case .economics: currentPage = "Economics"
                    case .politics: currentPage = "Politics"
                    case .entertainment: currentPage = "Entertainment"
                    case .about: currentPage = "About"
                    }
                }

                let networkType = await currentNetworkType()
                let userName = authManager.user?.displayName ?? authManager.user.map { "User \($0.id)" } ?? "anonymous"

                var appState: [String: String] = [
                    "current_page": currentPage,
                    "current_tab": tabName,
                    "user_name": userName,
                    "user_id": authManager.user.map { "\($0.id)" } ?? "anonymous",
                    "network": networkType,
                    "platform": platformString(),
                    "device_model": deviceModel(),
                    "os_version": osVersion(),
                    "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?",
                    "live_game_count": "\(navCoordinator.liveGameCount)",
                    "screen_size": screenSize(),
                    "timestamp": ISO8601DateFormatter().string(from: Date()),
                ]
                appState.merge(NativeDiscoverDebugState.appStateFields()) { _, new in new }

                let submission = BugReportSubmission(
                    description: description,
                    screenshotBase64: base64,
                    appState: appState,
                    notifyOnFix: notifyOnFix
                )
                _ = try await APIClient.shared.submitBugReport(submission)
                submitError = nil
                submitted = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { dismiss() }
            } catch {
                submitError = "Couldn't submit — check your connection and try again."
            }
            submitting = false
        }
    }

    private func flattenedScreenshot() -> Data? {
        #if os(macOS)
        let img = pastedScreenshot ?? screenshot
        #else
        let img = screenshot
        #endif
        guard let screenshot = img else { return nil }

        #if os(iOS)
        let drawing = canvasView.drawing
        let canvasBounds = canvasView.bounds
        let renderer = UIGraphicsImageRenderer(size: screenshot.size)
        let flattened = renderer.image { ctx in
            screenshot.draw(at: .zero)
            // Map canvas points to image points. Use bounds.size (not
            // bounds, which includes contentOffset origin for scroll views).
            let scaleX = screenshot.size.width / canvasBounds.size.width
            let scaleY = screenshot.size.height / canvasBounds.size.height
            ctx.cgContext.scaleBy(x: scaleX, y: scaleY)
            // Render the drawing from a zero-origin rect sized to the
            // visible canvas area, at screen scale for crisp annotations.
            let drawRect = CGRect(origin: .zero, size: canvasBounds.size)
            drawing.image(from: drawRect, scale: UIScreen.main.scale).draw(at: .zero)
        }
        return flattened.jpegData(compressionQuality: 0.7)
        #else
        guard let tiff = screenshot.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff) else { return nil }
        return rep.representation(using: .jpeg, properties: [.compressionFactor: 0.7])
        #endif
    }

    private func platformString() -> String {
        #if os(iOS)
        return "ios"
        #else
        return "macos"
        #endif
    }

    private func deviceModel() -> String {
        #if os(iOS)
        var systemInfo = utsname()
        uname(&systemInfo)
        return withUnsafePointer(to: &systemInfo.machine) {
            $0.withMemoryRebound(to: CChar.self, capacity: 1) {
                String(cString: $0)
            }
        }
        #else
        return "Mac"
        #endif
    }

    private func osVersion() -> String {
        let os = ProcessInfo.processInfo.operatingSystemVersion
        return "\(os.majorVersion).\(os.minorVersion).\(os.patchVersion)"
    }

    private func screenSize() -> String {
        #if os(iOS)
        let s = UIScreen.main.bounds
        return "\(Int(s.width))x\(Int(s.height))"
        #else
        return "Mac"
        #endif
    }
}

private func currentNetworkType() async -> String {
    await withCheckedContinuation { continuation in
        let monitor = NWPathMonitor()
        let queue = DispatchQueue(label: "com.bainluck.network-check")
        monitor.pathUpdateHandler = { path in
            monitor.cancel()
            if path.usesInterfaceType(.wifi) { continuation.resume(returning: "wifi") }
            else if path.usesInterfaceType(.cellular) { continuation.resume(returning: "cellular") }
            else if path.usesInterfaceType(.wiredEthernet) { continuation.resume(returning: "ethernet") }
            else if path.status == .satisfied { continuation.resume(returning: "connected") }
            else { continuation.resume(returning: "offline") }
        }
        monitor.start(queue: queue)
    }
}

// MARK: - PencilKit Canvas Overlay (iOS only)

#if os(iOS)
struct CanvasOverlay: UIViewRepresentable {
    @Binding var canvasView: PKCanvasView

    func makeUIView(context: Context) -> PKCanvasView {
        canvasView.drawingPolicy = .anyInput
        canvasView.backgroundColor = .clear
        canvasView.isOpaque = false
        canvasView.tool = PKInkingTool(.marker, color: .systemRed, width: 8)
        // Prevent scroll/zoom from shifting the drawing coordinate space
        canvasView.isScrollEnabled = false
        canvasView.minimumZoomScale = 1.0
        canvasView.maximumZoomScale = 1.0
        canvasView.contentInsetAdjustmentBehavior = .never
        canvasView.showsVerticalScrollIndicator = false
        canvasView.showsHorizontalScrollIndicator = false
        return canvasView
    }

    func updateUIView(_ uiView: PKCanvasView, context: Context) {}
}
#endif

// MARK: - Screenshot Capture

private let bugReportLogger = Logger(subsystem: "com.bainluck", category: "BugReport")

func captureScreenshot() -> PlatformImage? {
    #if os(iOS)
    let scenes = UIApplication.shared.connectedScenes
    bugReportLogger.debug("Connected scenes: \(scenes.count)")
    guard let windowScene = scenes.compactMap({ $0 as? UIWindowScene }).first else {
        bugReportLogger.warning("No UIWindowScene found")
        return nil
    }
    bugReportLogger.debug("Windows: \(windowScene.windows.count), keyWindow: \(windowScene.keyWindow != nil)")
    guard let window = windowScene.keyWindow ?? windowScene.windows.first else {
        bugReportLogger.warning("No window found")
        return nil
    }
    bugReportLogger.debug("Window size: \(window.bounds.size.width)x\(window.bounds.size.height)")

    let renderer = UIGraphicsImageRenderer(size: window.bounds.size)
    let image = renderer.image { ctx in
        window.drawHierarchy(in: window.bounds, afterScreenUpdates: false)
    }
    bugReportLogger.debug("Screenshot captured: \(image.size.width)x\(image.size.height)")
    return image
    #elseif os(macOS)
    // SwiftUI's Metal rendering can't be captured via AppKit APIs.
    // Return nil — BugReportView will show a paste prompt instead.
    return nil
    #else
    return nil
    #endif
}
