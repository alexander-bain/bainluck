import SwiftUI
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
    @State private var submitting = false
    @State private var submitted = false

    #if os(iOS)
    @State private var canvasView = PKCanvasView()
    #endif

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    // Screenshot with markup
                    if let screenshot {
                        ZStack {
                            Image(platformImage: screenshot)
                                .resizable()
                                .scaledToFit()
                                .frame(maxHeight: 300)
                                .clipShape(RoundedRectangle(cornerRadius: 12))

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
                    }

                    // Description field
                    VStack(alignment: .leading, spacing: 6) {
                        Text("What went wrong?")
                            .font(.subheadline.weight(.semibold))

                        TextField("Describe the bug...", text: $description, axis: .vertical)
                            .lineLimit(3...6)
                            .textFieldStyle(.roundedBorder)
                    }
                    .padding(.horizontal)

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
                }
                .padding(.vertical)
            }
            .navigationTitle("Report a Bug")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Submit") { submitReport() }
                        .disabled(submitting || submitted || description.trimmingCharacters(in: .whitespaces).isEmpty)
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

                let appState: [String: String] = [
                    "current_tab": "\(navCoordinator.selectedTab.rawValue)",
                    "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?",
                    "platform": platformString(),
                    "device_model": deviceModel(),
                    "os_version": osVersion(),
                    "user_id": authManager.user.map { "\($0.id)" } ?? "anonymous",
                    "live_game_count": "\(navCoordinator.liveGameCount)",
                    "timestamp": ISO8601DateFormatter().string(from: Date()),
                ]

                let submission = BugReportSubmission(
                    description: description,
                    screenshotBase64: base64,
                    appState: appState
                )
                _ = try await APIClient.shared.submitBugReport(submission)
                submitted = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { dismiss() }
            } catch {
                submitted = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { dismiss() }
            }
            submitting = false
        }
    }

    private func flattenedScreenshot() -> Data? {
        guard let screenshot else { return nil }

        #if os(iOS)
        let drawing = canvasView.drawing
        let renderer = UIGraphicsImageRenderer(size: screenshot.size)
        let flattened = renderer.image { ctx in
            screenshot.draw(at: .zero)
            let scale = screenshot.size.width / canvasView.bounds.width
            ctx.cgContext.scaleBy(x: scale, y: scale)
            drawing.image(from: canvasView.bounds, scale: 1.0).draw(at: .zero)
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
        return canvasView
    }

    func updateUIView(_ uiView: PKCanvasView, context: Context) {}
}
#endif

// MARK: - Screenshot Capture

func captureScreenshot() -> PlatformImage? {
    #if os(iOS)
    let scenes = UIApplication.shared.connectedScenes
    print("[BugReport] Connected scenes: \(scenes.count)")
    guard let windowScene = scenes.compactMap({ $0 as? UIWindowScene }).first else {
        print("[BugReport] No UIWindowScene found")
        return nil
    }
    print("[BugReport] Windows: \(windowScene.windows.count), keyWindow: \(windowScene.keyWindow != nil)")
    guard let window = windowScene.keyWindow ?? windowScene.windows.first else {
        print("[BugReport] No window found")
        return nil
    }
    print("[BugReport] Window size: \(window.bounds.size)")

    let renderer = UIGraphicsImageRenderer(size: window.bounds.size)
    let image = renderer.image { ctx in
        window.drawHierarchy(in: window.bounds, afterScreenUpdates: false)
    }
    print("[BugReport] Screenshot captured: \(image.size)")
    return image
    #elseif os(macOS)
    guard let window = NSApplication.shared.keyWindow else { return nil }
    guard let cgImage = CGWindowListCreateImage(
        .null, .optionIncludingWindow,
        CGWindowID(window.windowNumber),
        [.boundsIgnoreFraming]
    ) else { return nil }
    return NSImage(cgImage: cgImage, size: window.frame.size)
    #else
    return nil
    #endif
}
