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
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
    @EnvironmentObject private var authManager: AuthManager

    @State private var screenshot: PlatformImage?
    @State private var description = ""
    @State private var notifyOnFix = false
    @State private var submitting = false
    @State private var submitted = false
    @State private var submitError: String? = nil
    @State private var showErrorAlert = false
    @State private var savedLocally = false

    // MARK: Receipt state (#1847)

    /// The server acknowledgment for the report just submitted.
    @State private var lastReceipt: BugReportReceipt? = nil
    /// The newest receipt from BEFORE this sheet opened, so the user can see
    /// that their previous report landed without having to remember a toast.
    @State private var priorReceipt: BugReportReceipt? = nil
    /// Reports queued on this device and not yet delivered.
    @State private var pendingCount = 0
    /// Reports delivered by the outbox while this sheet was opening.
    @State private var recoveredCount = 0
    /// Whether the outbox is currently sending.
    @State private var flushing = false

    #if os(iOS)
    @State private var canvasView = PKCanvasView()
    #endif

    #if os(macOS)
    @State private var pastedScreenshot: NSImage? = nil
    #endif

    init(screenshot: PlatformImage?) {
        _screenshot = State(initialValue: screenshot)
    }

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
                        #else
                        // #1847: a shake whose screenshot capture failed now
                        // opens the form anyway. Say so, rather than rendering
                        // a form with an unexplained gap where an image goes.
                        HStack(spacing: 8) {
                            Image(systemName: "photo")
                                .foregroundStyle(.secondary)
                            Text("Couldn't capture a screenshot — describe the problem below and we'll still get it.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.horizontal)
                        .accessibilityIdentifier("bug-report-no-screenshot")
                        #endif
                    }

                    // Only offer removal when there is something to remove.
                    // A shake whose capture failed now opens this form with no
                    // image (#1847), and "Remove Screenshot" under an empty
                    // space reads as a bug.
                    if hasScreenshot {
                        Button(role: .destructive) {
                            screenshot = nil
                            #if os(macOS)
                            pastedScreenshot = nil
                            #endif
                        } label: {
                            Label("Remove Screenshot", systemImage: "xmark.circle")
                                .font(.caption)
                        }
                        .buttonStyle(.borderless)
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

                    // THE RECEIPT (#1847). Quotes the server-assigned id, which
                    // is the thing you can actually check later. The old
                    // version said only "Bug report submitted!" and vanished.
                    if submitted, let receipt = lastReceipt {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 8) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.green)
                                Text("Report #\(receipt.id) received")
                                    .font(.subheadline.weight(.semibold))
                            }
                            Text("Saved on this device so you can check it later. Thanks for helping improve Bain Luck.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .accessibilityIdentifier("bug-report-receipt")
                    }

                    // THE OUTBOX (#1847). `pendingCount` existed on the store
                    // from the beginning and had ZERO call sites, so a report
                    // sitting unsent on the device was invisible to its author.
                    if pendingCount > 0 && !submitted {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 8) {
                                Image(systemName: "tray.full.fill")
                                    .foregroundStyle(.orange)
                                Text(pendingCount == 1
                                     ? "1 report is waiting to send"
                                     : "\(pendingCount) reports are waiting to send")
                                    .font(.subheadline.weight(.semibold))
                            }
                            Text("They'll go automatically when the connection is back.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            if flushing {
                                ProgressView().controlSize(.small)
                            } else {
                                Button("Try Sending Now") {
                                    Task { await flushOutbox() }
                                }
                                .font(.caption.weight(.semibold))
                                .buttonStyle(.borderless)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .accessibilityIdentifier("bug-report-outbox")
                    }

                    // A report recovered by the outbox is announced, rather
                    // than silently disappearing from the queue.
                    if recoveredCount > 0 {
                        HStack(spacing: 8) {
                            Image(systemName: "paperplane.fill")
                                .foregroundStyle(.green)
                            Text(recoveredCount == 1
                                 ? "A report saved earlier has now been sent."
                                 : "\(recoveredCount) reports saved earlier have now been sent.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.horizontal)
                    }

                    if savedLocally {
                        HStack(spacing: 8) {
                            Image(systemName: "arrow.down.doc.fill")
                                .foregroundStyle(.blue)
                            Text("Saved on this device. We'll keep trying to send it in the background.")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .padding()
                    }

                    if let error = submitError, !savedLocally {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(.orange)
                            Text(error)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .padding()
                    }

                    // The last report that landed, shown BEFORE submitting so
                    // the question "did my last one go through?" is answerable
                    // on arrival rather than from memory.
                    if !submitted, let prior = priorReceipt {
                        Text("Last report sent: #\(prior.id) · \(prior.submittedAt.formatted(date: .abbreviated, time: .shortened))")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                            .padding(.horizontal)
                            .accessibilityIdentifier("bug-report-prior-receipt")
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
                    if submitting {
                        ProgressView()
                    } else {
                        // Only a LANDED report disables Submit. It used to be
                        // disabled by `savedLocally` too, which was a dead end:
                        // after a failed send the user could edit their
                        // description and have no way to send the edit.
                        // Re-submitting an unchanged report is harmless — the
                        // draft store de-duplicates on `draftKey`.
                        Button("Submit") { submitReport() }
                            .disabled(submitted)
                            .fontWeight(.semibold)
                    }
                }
            }
            // #1847 defect C: this alert used to offer a `Cancel` that ran
            // `{ }` — the report was destroyed with no save and no warning, on
            // the one path a frustrated user is most likely to take. The report
            // is now already on disk before this alert can appear, so there is
            // no longer a losing button to press.
            .alert("Couldn't Send Yet", isPresented: $showErrorAlert) {
                Button("Try Again") { submitReport() }
                Button("OK", role: .cancel) { savedLocally = true }
            } message: {
                Text((submitError ?? "Check your connection and try again.")
                     + "\n\nYour report is saved on this device and will send automatically.")
            }
            .task { await onOpen() }
        }
    }

    /// Maximum base64 screenshot size accepted by the backend (~1.5MB decoded).
    private static let maxScreenshotBase64Length = 2_000_000

    /// Whether there is an image attached, on either platform.
    private var hasScreenshot: Bool {
        #if os(macOS)
        return screenshot != nil || pastedScreenshot != nil
        #else
        return screenshot != nil
        #endif
    }

    private func submitReport() {
        submitting = true
        Task {
            // Built ONCE and reused on both paths. The old code rebuilt the
            // submission inside `saveReportLocally()`, so the draft that got
            // saved was a different object from the one that failed (fresh
            // `timestamp`, and any edit made in between).
            let submission = await buildSubmission()
            do {
                let response = try await submitWithRetry(submission, maxRetries: 2)

                // Record the receipt BEFORE anything can dismiss the view. The
                // response's `id` used to be discarded at the call site
                // (`_ = try await ...`), which is why a landed report left no
                // trace the user could check.
                lastReceipt = BugReportReceiptStore.record(
                    id: response.id,
                    description: submission.description,
                    page: submission.appState?["current_page"]
                )
                // If an earlier attempt queued this same report, it has now
                // been delivered — drop the duplicate.
                removeQueuedDraft(matching: submission)
                pendingCount = BugReportDraftStore.pendingCount

                submitError = nil
                savedLocally = false
                submitted = true
                // Long enough to read an id, not so long it feels stuck.
                DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) { dismiss() }
            } catch {
                // Persist FIRST, then tell the user. No ordering in which the
                // report can be lost.
                BugReportDraftStore.saveDraft(submission)
                pendingCount = BugReportDraftStore.pendingCount
                submitError = userFacingErrorMessage(for: error)
                showErrorAlert = true
            }
            submitting = false
        }
    }

    /// Refresh receipt/outbox state and deliver anything queued.
    private func onOpen() async {
        priorReceipt = BugReportReceiptStore.mostRecent
        pendingCount = BugReportDraftStore.pendingCount
        await flushOutbox()
    }

    /// Drain the outbox and reflect the result in the sheet.
    private func flushOutbox() async {
        guard BugReportDraftStore.hasPendingDrafts else {
            pendingCount = 0
            return
        }
        flushing = true
        let result = await BugReportOutbox.flush()
        flushing = false
        recoveredCount += result.sent
        pendingCount = result.remaining
        if result.sent > 0 {
            // A recovered report supplies a newer receipt than the one shown
            // on open.
            priorReceipt = BugReportReceiptStore.mostRecent
            savedLocally = false
        }
    }

    /// Remove a queued copy of `submission`, if one exists.
    private func removeQueuedDraft(matching submission: BugReportSubmission) {
        let key = submission.draftKey
        let drafts = BugReportDraftStore.loadDrafts()
        if let index = drafts.firstIndex(where: { $0.draftKey == key }) {
            BugReportDraftStore.removeDraft(at: index)
        }
    }

    /// Build the submission payload from the current view state.
    private func buildSubmission() async -> BugReportSubmission {
        let base64 = compressedScreenshotBase64()

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
            case .discoverLabeling: currentPage = "Discover Labeling"
            case .futuresList: currentPage = "Futures Browser"
            case .predictionStats: currentPage = "Prediction Stats"
            case .weather: currentPage = "Weather"
            case .economics: currentPage = "Economics"
            case .politics: currentPage = "Politics"
            case .entertainment: currentPage = "Entertainment"
            case .about: currentPage = "About"
            case .dailyChallenge: currentPage = "Daily Challenge"
            case .friendChallenge(let code): currentPage = "Challenge (\(code))"
            case .eventModels(let id): currentPage = "Event Models (\(id))"
            case .calibration: currentPage = "Calibration"
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

        return BugReportSubmission(
            description: description,
            screenshotBase64: base64,
            appState: appState,
            notifyOnFix: notifyOnFix
        )
    }

    /// Compress the screenshot to fit within the backend's 2MB base64 limit.
    /// Tries progressively lower JPEG quality, then scales down if needed.
    private func compressedScreenshotBase64() -> String? {
        guard let imageData = flattenedScreenshot() else { return nil }

        // Already small enough at default quality
        let base64 = imageData.base64EncodedString()
        if base64.count <= Self.maxScreenshotBase64Length {
            return base64
        }

        #if os(iOS)
        guard let uiImage = UIImage(data: imageData) else { return base64 }

        // Try lower JPEG quality levels
        for quality in [0.5, 0.3, 0.15] as [CGFloat] {
            if let compressed = uiImage.jpegData(compressionQuality: quality) {
                let b64 = compressed.base64EncodedString()
                if b64.count <= Self.maxScreenshotBase64Length {
                    return b64
                }
            }
        }

        // Scale down the image as a last resort (50% dimensions)
        let scaledSize = CGSize(width: uiImage.size.width * 0.5, height: uiImage.size.height * 0.5)
        let renderer = UIGraphicsImageRenderer(size: scaledSize)
        let scaled = renderer.image { _ in
            uiImage.draw(in: CGRect(origin: .zero, size: scaledSize))
        }
        if let compressed = scaled.jpegData(compressionQuality: 0.3) {
            let b64 = compressed.base64EncodedString()
            if b64.count <= Self.maxScreenshotBase64Length {
                return b64
            }
        }

        // Absolute fallback: drop the screenshot rather than fail submission
        return nil
        #else
        // macOS: try re-encoding at lower quality
        guard let nsImage = NSImage(data: imageData),
              let tiff = nsImage.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff) else {
            return base64
        }
        for quality in [0.5, 0.3, 0.15] as [Double] {
            if let compressed = rep.representation(using: .jpeg, properties: [.compressionFactor: quality]) {
                let b64 = compressed.base64EncodedString()
                if b64.count <= Self.maxScreenshotBase64Length {
                    return b64
                }
            }
        }
        return nil
        #endif
    }

    /// Submit a bug report with retry and exponential backoff.
    /// Retries only on network errors, not on HTTP 4xx/5xx.
    @discardableResult
    private func submitWithRetry(
        _ submission: BugReportSubmission, maxRetries: Int
    ) async throws -> BugReportResponse {
        var lastError: Error?

        for attempt in 0...maxRetries {
            do {
                // The response is the RECEIPT. Returned, not discarded (#1847).
                return try await BugReportOutbox.send(submission)
            } catch let error as APIError {
                switch error {
                case .networkError:
                    lastError = error
                    if attempt < maxRetries {
                        // Exponential backoff: 1s, 2s
                        let delay = UInt64(pow(2.0, Double(attempt))) * 1_000_000_000
                        try? await Task.sleep(nanoseconds: delay)
                    }
                default:
                    // HTTP errors or decoding errors: don't retry
                    throw error
                }
            } catch {
                lastError = error
                if attempt < maxRetries {
                    let delay = UInt64(pow(2.0, Double(attempt))) * 1_000_000_000
                    try? await Task.sleep(nanoseconds: delay)
                }
            }
        }

        // The loop either returned a response or recorded an error. Exhausting
        // it with neither is unreachable, but this function now yields a value
        // callers depend on, so it fails loudly rather than silently.
        throw lastError ?? APIError.networkError(
            underlying: NSError(
                domain: "BugReport", code: -1,
                userInfo: [NSLocalizedDescriptionKey: "Submission exhausted all retries"]
            )
        )
    }

    /// Map API errors to user-friendly messages.
    private func userFacingErrorMessage(for error: Error) -> String {
        if let apiError = error as? APIError {
            switch apiError {
            // These no longer say "you can save this report" — the report is
            // already saved by the time this text is read (#1847 defect C).
            // Copy that asks for an action already taken is its own small lie.
            case .networkError:
                return "No internet connection."
            case .httpError(let code, _) where code == 413:
                return "Screenshot is too large. Try removing the screenshot and submitting again."
            case .httpError(let code, _) where code == 422:
                return "Report content was too large. Try shortening your description."
            case .httpError(let code, _) where code >= 500:
                return "Our server is having trouble."
            case .httpError(let code, _):
                return "Submission failed (error \(code))."
            default:
                return "Something went wrong."
            }
        }
        return "Something went wrong."
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
    guard let windowScene = scenes.compactMap({ $0 as? UIWindowScene }).first(where: { $0.activationState == .foregroundActive }) ?? scenes.compactMap({ $0 as? UIWindowScene }).first else {
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
