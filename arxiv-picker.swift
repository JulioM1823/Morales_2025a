#!/usr/bin/env swift
import AppKit
import WebKit
import PDFKit
import Foundation
import CryptoKit
import QuartzCore
import ImageIO
import CoreImage
import CoreImage.CIFilterBuiltins
import Metal
import CoreVideo
import CoreText
import os
#if canImport(XCTest)
import XCTest
#endif

/*
WHAT CHANGED (window root background refactor)
- Removed the window-level liquid-glass/vibrancy background layer (the full-window glass view).
- The window now renders a user-provided background image behind all UI using `WINDOW_BACKGROUND_IMAGE_PATH`.
- Introduced a single base glass-style source (`baseGlassStyleTintColor()`) so components that previously referenced
  “window glass tint” (search bar tint/outline, palettes, etc.) now reference the primary remaining glass layer.
*/

// =====================
// USER CONFIG (optional)
// =====================
let APP_DISPLAY_NAME: String = "AstroStack"
let APP_LOG_SUBSYSTEM: String = "com.juliomorales.AstroStack"

let HEADER_IMAGE_CENTER_PATH: String = "/Users/juliomorales/Documents/Gifs/arxiv-logo.png"
let HEADER_IMAGE_LEFT_PATH: String = "/Users/juliomorales/Documents/Gifs/image-from-rawpixel-id-16003417-png.png"
let HEADER_IMAGE_RIGHT_PATH: String = "/Users/juliomorales/Documents/Gifs/pngtree-highly-magnetized-rotating-neutron-stars-emittin-png-image_13150087.png"
// Left glass-card background image underlay (supports GIF; leave empty to disable).
let BACKGROUND_IMAGE_PATH: String = ""
let LEFT_CARD_BACKGROUND_IMAGE_ALPHA: CGFloat = 0.7
// Right glass-card background image underlay (supports GIF; leave empty to disable).
let RIGHT_CARD_BACKGROUND_IMAGE_PATH: String = ""
let RIGHT_CARD_BACKGROUND_IMAGE_ALPHA: CGFloat = 0.0
// Window background image underlay (supports GIF; leave empty to disable).
let WINDOW_BACKGROUND_IMAGE_PATH: String = ""//"/Users/juliomorales/Downloads/54960149350_2d46fe0a36_o.jpg"
let WINDOW_BACKGROUND_IMAGE_ALPHA: CGFloat = 1.0
// Solid window background used when `WINDOW_BACKGROUND_IMAGE_PATH` is empty/invalid.
let WINDOW_BACKGROUND_SOLID_COLOR: NSColor = .white
// Background image performance guard:
// If enabled, large non-animated images are downsampled at load time to avoid huge RAM spikes and slow startup.
// Set HARD max higher to “force” higher-res decoding (at the cost of memory), or set enabled=falseTha to disable.
let BACKGROUND_IMAGE_DOWNSCALE_ENABLED: Bool = true
let BACKGROUND_IMAGE_HARD_MAX_PIXEL_DIM: Int = 8192
let DEBUG_ROOT_GLASS_TINT: Bool = false

let HEADER_IMAGE_MAX_HEIGHT: CGFloat = 120
let HEADER_IMAGE_SCALE: CGFloat = 0.25
let HEADER_IMAGE_SIDE_SCALE: CGFloat = 1.2

let RIGHT_LINK_COLOR_HEX: String = "#2f81f7"
let GLASS_TRANSPARENCY_MULTIPLIER: CGFloat = 0.7
let LIQUID_GLASS_TINT_HEX: String = "#4a2c24"
let WINDOW_GLASS_TINT_ALPHA: CGFloat = 0.2
let WINDOW_GLASS_TINT_SATURATION: CGFloat = 2.0
let PANEL_GLASS_GRAY_TINT_WHITE: CGFloat = 0.07
let PANEL_GLASS_GRAY_TINT_ALPHA: CGFloat = 0.5
// Panels only: higher transparency (alpha scaled down). 0.2 == “80% more transparent”.
let PANEL_GLASS_ALPHA_MULTIPLIER: CGFloat = 0.2
// Panels: “90% translucent” ≈ 10% tint overlay (neutral, no hue).
let PANEL_CLEAR_GLASS_TINT_ALPHA: CGFloat = 0.10
// Dropdown glass (now the base glass effect): stronger diffusion to fully wash out background behind menus.
let DROPDOWN_GLASS_TRANSMISSION: CGFloat = 0.60
let DROPDOWN_GLASS_DIFFUSION_AMOUNT: CGFloat = 0.80
// Toolbar glass: clearer and brighter in Light Mode, with preserved depth in Dark Mode.
let TOOLBAR_GLASS_TRANSMISSION_LIGHT: CGFloat = 0.95
let TOOLBAR_GLASS_TRANSMISSION_DARK: CGFloat = 0.90
let TOOLBAR_GLASS_DIFFUSION_LIGHT: CGFloat = 0.08
let TOOLBAR_GLASS_DIFFUSION_DARK: CGFloat = 0.16
let TOOLBAR_GLASS_REFRACTION_STRENGTH_LIGHT: CGFloat = 0.95
let TOOLBAR_GLASS_REFRACTION_STRENGTH_DARK: CGFloat = 0.90
let TOOLBAR_GLASS_FRESNEL_STRENGTH_LIGHT: CGFloat = 0.44
let TOOLBAR_GLASS_FRESNEL_STRENGTH_DARK: CGFloat = 0.38
let TOOLBAR_GLASS_SPECULAR_LIGHT: CGFloat = 1.12
let TOOLBAR_GLASS_SPECULAR_DARK: CGFloat = 1.0
let TOOLBAR_GLASS_SHADOW_BOTTOM_LIGHT: CGFloat = 0.05
let TOOLBAR_GLASS_SHADOW_BOTTOM_DARK: CGFloat = 0.10
let TOOLBAR_GLASS_RIM_OPACITY_LIGHT_SCALE: Float = 0.85
// Visual separation between the left/right glass cards (implemented via split-view divider thickness).
let PANEL_INTER_CARD_GAP: CGFloat = 14
let SEARCH_BAR_TINT_BRIGHTNESS_ADJUST: CGFloat = -0.1
let LEFT_TABLE_UNDERLAY_TINT_WHITE: CGFloat = 0.06
let LEFT_TABLE_UNDERLAY_TINT_ALPHA: CGFloat = 0.55
let LIQUID_GLASS_TINT_SATURATION_MULTIPLIER: CGFloat = 1.35
let LIQUID_GLASS_TINT_SATURATION_BIAS: CGFloat = 0.02
let LIQUID_GLASS_TINT_BRIGHTNESS_MULTIPLIER: CGFloat = 0.68
let LIQUID_GLASS_TINT_BRIGHTNESS_BIAS: CGFloat = 0.02
let LIQUID_GLASS_TINT_BRIGHTNESS_GAMMA: CGFloat = 1.05
let LIQUID_GLASS_TINT_HUE_SHIFT: CGFloat = 0.0

// Layout + animation constants
let SPOTLIGHT_SEARCH_OUTLINE_WIDTH: CGFloat = 2.0
let SPOTLIGHT_SEARCH_TEXT_COLOR_HEX: String = "#f2ede9"
let SPOTLIGHT_SEARCH_PLACEHOLDER_ALPHA: CGFloat = 0.62
let SPOTLIGHT_SEARCH_GLASS_ALPHA_MULTIPLIER: CGFloat = 1.5
let SPOTLIGHT_SEARCH_OUTLINE_LIGHT_ALPHA: CGFloat = 0.28
let SPOTLIGHT_SEARCH_OUTLINE_DARK_ALPHA: CGFloat = 0.22
let SPOTLIGHT_SEARCH_HIGHLIGHT_TOP_ALPHA: CGFloat = 0.5
let SPOTLIGHT_SEARCH_HIGHLIGHT_MID_ALPHA: CGFloat = 0.2
let SPOTLIGHT_SEARCH_FALLOFF_ALPHA: CGFloat = 0.3
let SPOTLIGHT_SEARCH_FOCUS_SCALE_BOOST: CGFloat = 0.014
let SPOTLIGHT_SEARCH_HOVER_SCALE_BOOST: CGFloat = 0.01

let ROW_TEXT_HOVER_SCALE: CGFloat = 1.03
let ROW_TEXT_HOVER_LIFT: CGFloat = -0.6
let ROW_TEXT_HOVER_BOUNCE_DURATION: CFTimeInterval = 0.14

let WINDOW_BEZEL_INSET: CGFloat = 16 * 2.0
let PANEL_CORNER_RADIUS: CGFloat = 18
let PANEL_INSET: CGFloat = 10
let PANEL_BORDER_WIDTH: CGFloat = 1

let INITIAL_SIDEBAR_WIDTH_FRACTION_OF_MAX: CGFloat = 0.33

let PDF_CACHE_DIR_NAME: String = "appCache/pdfs"
let PDF_CACHE_MAX_CONCURRENT_DOWNLOADS: Int = 8
let PDF_CACHE_PREFETCH_LOG_EVERY: Int = 5

let PDF_FIND_TEXT_COLOR_HEX: String = "#000000"

let PDF_FIND_APPEAR_DURATION: CFTimeInterval = 0.36
let PDF_FIND_DISMISS_DURATION: CFTimeInterval = 0.28
let PDF_FIND_APPEAR_START_SCALE_X: CGFloat = 0.9
let PDF_FIND_APPEAR_START_SCALE_Y: CGFloat = 0.97
let PDF_FIND_APPEAR_START_Y_OFFSET: CGFloat = -12
let PDF_FIND_APPEAR_OVERSHOOT_SCALE_X: CGFloat = 1.03
let PDF_FIND_APPEAR_OVERSHOOT_SCALE_Y: CGFloat = 1.01
let PDF_FIND_APPEAR_OVERSHOOT_Y_OFFSET: CGFloat = 2
let PDF_FIND_APPEAR_OVERSHOOT_TIME: CGFloat = 0.62
let PDF_FIND_OPACITY_RAMP_TIME: CGFloat = 0.22
let PDF_FIND_DISMISS_TENSION_SCALE_X: CGFloat = 1.02
let PDF_FIND_DISMISS_TENSION_SCALE_Y: CGFloat = 1.005
let PDF_FIND_DISMISS_TENSION_Y_OFFSET: CGFloat = 2
let PDF_FIND_DISMISS_TENSION_TIME: CGFloat = 0.18
let PDF_FIND_DISMISS_OVERSHOOT_SCALE_X: CGFloat = 0.9
let PDF_FIND_DISMISS_OVERSHOOT_SCALE_Y: CGFloat = 0.96
let PDF_FIND_DISMISS_OVERSHOOT_Y_OFFSET: CGFloat = -16
let PDF_FIND_DISMISS_OVERSHOOT_TIME: CGFloat = 0.72
let PDF_FIND_DISMISS_END_SCALE_X: CGFloat = 0.9
let PDF_FIND_DISMISS_END_SCALE_Y: CGFloat = 0.96
let PDF_FIND_DISMISS_END_Y_OFFSET: CGFloat = -12

// MARK: - Appearance

private enum SystemAppearanceMode {
    case light
    case dark
}

private struct AppearanceSnapshot {
    let mode: SystemAppearanceMode
    let nsAppearanceName: NSAppearance.Name
    let revision: UInt64
    let monotonicTimestampNs: UInt64

    var isDark: Bool { mode == .dark }
}

private struct AppearanceBudgets {
    var appearanceSwitchLatencyMs: Double = 80
    var mainThreadBlockingMs: Double = 24
    var viewInvalidationsPerSwitch: Int = 2
    var redundantLayoutPasses: Int = 6
    var droppedFramesDuringSwitch: Int = 8
}

private struct Metrics {
    var lastSwitchLatencyMs: Double = 0
    var lastMainThreadBlockingMs: Double = 0
    var lastRootViewInvalidations: Int = 0
    var lastLayoutPasses: Int = 0
    var lastDroppedFrames: Int = 0
    var switchCount: Int = 0
}

private extension Notification.Name {
    static let arxivAppearanceDidChange = Notification.Name("arxiv.appearance.didChange")
}

private final class AppearanceManager {
    static let shared = AppearanceManager()

    private let lock = NSLock()
    private let log = OSLog(subsystem: APP_LOG_SUBSYSTEM, category: "appearance")
    private let signpostLog = OSLog(subsystem: APP_LOG_SUBSYSTEM, category: "appearance.signpost")

    private var started = false
    private var scheduled = false
    private var pendingReason: String = "startup"

    private var budgets = AppearanceBudgets()
    private var metrics = Metrics()
    private var currentSnapshot = AppearanceSnapshot(
        mode: .light,
        nsAppearanceName: .aqua,
        revision: 0,
        monotonicTimestampNs: DispatchTime.now().uptimeNanoseconds
    )


    private var observers: [Any] = []
    private var distributedObservers: [Any] = []

    private init() {}

    func startIfNeeded() {
        lock.lock()
        let needsStart = !started
        if needsStart { started = true }
        lock.unlock()
        guard needsStart else { return }

        // Initialize snapshot from system once.
        refreshFromSystem(reason: "startup", forceNotify: true)

        // Observe system appearance changes directly (authoritative).
        // NOTE: On newer SDKs the typed Swift constant is not available; use the Objective-C
        // notification name string to remain source-compatible.
        observers.append(NotificationCenter.default.addObserver(
            forName: Notification.Name("NSApplicationDidChangeEffectiveAppearanceNotification"),
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.scheduleRefresh(reason: "system_appearance")
        })

        // Observe accent/tint changes.
        observers.append(NotificationCenter.default.addObserver(
            forName: NSColor.systemColorsDidChangeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.scheduleRefresh(reason: "system_colors")
        })

        // Extra robustness: distributed theme-changed notification.
        distributedObservers.append(DistributedNotificationCenter.default().addObserver(
            forName: Notification.Name("AppleInterfaceThemeChangedNotification"),
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.scheduleRefresh(reason: "distributed_theme")
        })
    }

    func snapshot() -> AppearanceSnapshot {
        lock.lock(); defer { lock.unlock() }
        return currentSnapshot
    }

    func isDark() -> Bool {
        snapshot().isDark
    }

    func resolvedSystemColor(_ color: NSColor) -> NSColor {
        let appearanceName = snapshot().nsAppearanceName
        let appearance = NSAppearance(named: appearanceName)
            ?? NSAppearance.current
            ?? NSAppearance(named: .aqua)
            ?? NSAppearance(named: .darkAqua)

        // If this is ever nil, something is seriously wrong with AppKit; fail loudly in debug.
        assert(appearance != nil)

        guard let appearance else { return color }
        var resolved = color
        appearance.performAsCurrentDrawingAppearance {
            resolved = color.usingColorSpace(.deviceRGB) ?? color
        }
        return resolved
    }

    func metricsSnapshot() -> Metrics {
        lock.lock(); defer { lock.unlock() }
        return metrics
    }

    private func scheduleRefresh(reason: String) {
        lock.lock()
        pendingReason = reason
        let shouldSchedule = !scheduled
        if shouldSchedule { scheduled = true }
        lock.unlock()

        guard shouldSchedule else { return }

        // Coalesce to next runloop tick; guarantees atomic propagation even under rapid toggling.
        DispatchQueue.main.async { [weak self] in
            self?.applyPendingRefresh()
        }
    }

    private func applyPendingRefresh() {
        let reason: String
        lock.lock()
        reason = pendingReason
        scheduled = false
        lock.unlock()
        refreshFromSystem(reason: reason, forceNotify: false)
    }

    private func refreshFromSystem(reason: String, forceNotify: Bool) {
        // NOTE: This is the *only* place where we query system appearance.
        let sys = NSApplication.shared.effectiveAppearance
        let best = sys.bestMatch(from: [.darkAqua, .aqua]) ?? .aqua
        let mode: SystemAppearanceMode = (best == .darkAqua) ? .dark : .light

        let startNs = DispatchTime.now().uptimeNanoseconds
        let signpostID = OSSignpostID(log: signpostLog)
        os_signpost(.begin, log: signpostLog, name: "AppearanceSwitch", signpostID: signpostID,
                    "reason=%{public}@", reason)

        // Main-thread blocking timer measures only the synchronous work here.
        let blockingStart = DispatchTime.now().uptimeNanoseconds

        var newSnapshot: AppearanceSnapshot?
        var oldSnapshot: AppearanceSnapshot?

        lock.lock()
        oldSnapshot = currentSnapshot
        let nextRevision = currentSnapshot.revision &+ 1
        let shouldNotify = forceNotify || currentSnapshot.mode != mode || currentSnapshot.nsAppearanceName != best
        if shouldNotify {
            currentSnapshot = AppearanceSnapshot(mode: mode,
                                                nsAppearanceName: best,
                                                revision: nextRevision,
                                                monotonicTimestampNs: startNs)
            newSnapshot = currentSnapshot
        }
        lock.unlock()

        guard let snapshot = newSnapshot else {
            os_signpost(.end, log: signpostLog, name: "AppearanceSwitch", signpostID: signpostID,
                        "noop=1")
            return
        }

        // Atomic propagation: freeze screen updates across all windows until flush.
        let windows = NSApp.windows
        for w in windows {
            w.disableScreenUpdatesUntilFlush()
        }

        // Notify subscribers once, with a single snapshot.
        NotificationCenter.default.post(name: .arxivAppearanceDidChange, object: self, userInfo: ["snapshot": snapshot, "reason": reason])

        // One root invalidation per window (budgeted).
        var rootInvalidations = 0
        for w in windows {
            if let root = w.contentView {
                root.needsDisplay = true
                rootInvalidations += 1
            }
        }

        let blockingEnd = DispatchTime.now().uptimeNanoseconds
        let blockingMs = Double(blockingEnd - blockingStart) / 1_000_000.0

        CATransaction.begin()
        CATransaction.setCompletionBlock { [weak self] in
            guard let self else { return }
            let endNs = DispatchTime.now().uptimeNanoseconds
            let latencyMs = Double(endNs - startNs) / 1_000_000.0
            os_signpost(.end, log: self.signpostLog, name: "AppearanceSwitch", signpostID: signpostID,
                        "latency_ms=%.3f", latencyMs)

            self.lock.lock()
            self.metrics.lastSwitchLatencyMs = latencyMs
            self.metrics.lastMainThreadBlockingMs = blockingMs
            self.metrics.lastRootViewInvalidations = rootInvalidations
            self.metrics.switchCount += 1
            self.lock.unlock()

            self.enforceBudgets(snapshot: snapshot)
        }
        CATransaction.commit()
    }

    private func enforceBudgets(snapshot: AppearanceSnapshot) {
        let m = metricsSnapshot()

        // Hard failure thresholds are enforced via asserts in debug; also logged for Instruments.
        if m.lastSwitchLatencyMs > budgets.appearanceSwitchLatencyMs {
            os_log("[APPEARANCE_BUDGET] latency_ms=%.3f exceeded (rev=%llu)", log: log, type: .fault, m.lastSwitchLatencyMs, snapshot.revision)
            assert(m.lastSwitchLatencyMs <= budgets.appearanceSwitchLatencyMs)
        }
        if m.lastMainThreadBlockingMs > budgets.mainThreadBlockingMs {
            os_log("[APPEARANCE_BUDGET] main_block_ms=%.3f exceeded (rev=%llu)", log: log, type: .fault, m.lastMainThreadBlockingMs, snapshot.revision)
            assert(m.lastMainThreadBlockingMs <= budgets.mainThreadBlockingMs)
        }
        if m.lastRootViewInvalidations > budgets.viewInvalidationsPerSwitch * max(1, NSApp.windows.count) {
            os_log("[APPEARANCE_BUDGET] root_invalidations=%d exceeded (rev=%llu)", log: log, type: .fault, m.lastRootViewInvalidations, snapshot.revision)
            assert(m.lastRootViewInvalidations <= budgets.viewInvalidationsPerSwitch * max(1, NSApp.windows.count))
        }
        if m.lastLayoutPasses > budgets.redundantLayoutPasses {
            os_log("[APPEARANCE_BUDGET] layout_passes=%d exceeded (rev=%llu)", log: log, type: .fault, m.lastLayoutPasses, snapshot.revision)
            assert(m.lastLayoutPasses <= budgets.redundantLayoutPasses)
        }
        if m.lastDroppedFrames > budgets.droppedFramesDuringSwitch {
            os_log("[APPEARANCE_BUDGET] dropped_frames=%d exceeded (rev=%llu)", log: log, type: .fault, m.lastDroppedFrames, snapshot.revision)
            assert(m.lastDroppedFrames <= budgets.droppedFramesDuringSwitch)
        }
    }
}

private func activeAppearance() -> NSAppearance {
    let name = AppearanceManager.shared.snapshot().nsAppearanceName
    return NSAppearance(named: name)
        ?? NSAppearance.current
        ?? NSAppearance(named: .aqua)
        ?? NSAppearance(named: .darkAqua)
        ?? NSAppearance()
}

private func glassAlpha(_ alpha: CGFloat) -> CGFloat {
    max(0.0, min(1.0, alpha * GLASS_TRANSPARENCY_MULTIPLIER))
}

private func applyGlassTransparency(_ color: NSColor) -> NSColor {
    color.withAlphaComponent(glassAlpha(color.alphaComponent))
}

private func resolvedSystemColor(_ color: NSColor) -> NSColor {
    AppearanceManager.shared.resolvedSystemColor(color)
}

private func inkyBlackColor() -> NSColor {
    if let color = colorFromHex(PDF_FIND_TEXT_COLOR_HEX) {
        return color.usingColorSpace(.deviceRGB) ?? color
    }
    return NSColor(srgbRed: 0.05, green: 0.05, blue: 0.06, alpha: 1.0)
}

private func tintedImage(_ image: NSImage, color: NSColor) -> NSImage {
    let size = image.size
    let out = NSImage(size: size)
    out.lockFocus()
    let rect = NSRect(origin: .zero, size: size)
    image.draw(in: rect, from: .zero, operation: .sourceOver, fraction: 1.0)
    color.set()
    rect.fill(using: .sourceAtop)
    out.unlockFocus()
    out.isTemplate = false
    return out
}

private func horizontallyMirroredImage(_ image: NSImage) -> NSImage {
    let size = image.size
    let out = NSImage(size: size)
    out.lockFocus()
    defer { out.unlockFocus() }

    let transform = NSAffineTransform()
    transform.translateX(by: size.width, yBy: 0)
    transform.scaleX(by: -1, yBy: 1)
    transform.concat()

    image.draw(in: NSRect(origin: .zero, size: size), from: .zero, operation: .sourceOver, fraction: 1.0)
    out.isTemplate = image.isTemplate
    return out
}

private func mainSearchForegroundColor() -> NSColor {
    // Match the sidebar/menu button tint (uses `NSColor.labelColor`) so the search icon+text read the same black.
    resolvedSystemColor(.labelColor)
}

// Pass-through view so background layers never intercept events.
private final class PassthroughView: NSView {
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
}

private final class PassthroughVisualEffectView: NSVisualEffectView {
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
}

private final class MenuDismissView: NSView {
    var onDismiss: (() -> Void)?
    override func hitTest(_ point: NSPoint) -> NSView? {
        guard !isHidden,
              alphaValue > 0.01,
              window != nil,
              bounds.contains(point) else { return nil }
        return self
    }
    override func mouseDown(with event: NSEvent) {
        guard !isHidden else { return }
        onDismiss?()
    }
}

/// Allows clicks that land on empty header chrome to fall through to views below.
private final class HeaderHitTestContainer: NSView {
    override func hitTest(_ point: NSPoint) -> NSView? {
        guard let hit = super.hitTest(point) else { return nil }
        return hit === self ? nil : hit
    }
}

private final class SearchFocusContainer: NSView {
    weak var focusTarget: NSView?
    var onAppearanceChanged: (() -> Void)?

    private var appearanceObserver: Any?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        appearanceObserver = NotificationCenter.default.addObserver(
            forName: .arxivAppearanceDidChange,
            object: AppearanceManager.shared,
            queue: .main
        ) { [weak self] _ in
            self?.onAppearanceChanged?()
        }
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        appearanceObserver = NotificationCenter.default.addObserver(
            forName: .arxivAppearanceDidChange,
            object: AppearanceManager.shared,
            queue: .main
        ) { [weak self] _ in
            self?.onAppearanceChanged?()
        }
    }

    deinit {
        if let appearanceObserver {
            NotificationCenter.default.removeObserver(appearanceObserver)
        }
    }

    override func mouseDown(with event: NSEvent) {
        if let target = focusTarget {
            window?.makeFirstResponder(target)
            target.mouseDown(with: event)
            return
        }
        super.mouseDown(with: event)
    }
}

private final class RightPanelContentHostView: NSView {
}

private let launchDebugEnabled = ProcessInfo.processInfo.environment["DEBUG_LAUNCH"] == "1"
private let launchCheckEnabled = ProcessInfo.processInfo.environment["ARXIV_LAUNCH_CHECK"] == "1"
private let debugLayoutEnabled = ProcessInfo.processInfo.environment["DEBUG_LAYOUT"] == "1"

private let chatLatencyDebugEnabled = ProcessInfo.processInfo.environment["ARXIV_CHAT_LATENCY"] == "1"

private func monotonicNowNs() -> UInt64 {
    DispatchTime.now().uptimeNanoseconds
}

private final class ChatLatencyProbe {
    static let shared = ChatLatencyProbe()

    private let log = OSLog(subsystem: APP_LOG_SUBSYSTEM, category: "chat.latency")
    private let signpostLog = OSLog(subsystem: APP_LOG_SUBSYSTEM, category: "chat.latency.signpost")
    private let lock = NSLock()

    private var token: UInt64 = 0
    private var actionNs: UInt64 = 0
    private var animationCommitNs: UInt64 = 0
    private var firstVsyncNs: UInt64 = 0
    private var opening: Bool = false
    private var signpostID: OSSignpostID = .invalid

    private var displayLink: CVDisplayLink?
    private var displayLinkActive = false

    private init() {}

    private func stdoutLog(_ message: String) {
        // `os_log`/signposts are visible in Console/Instruments but not reliably in stdout.
        // For latency proof in terminal, mirror the key events to NSLog when enabled.
        NSLog("[CHAT_LATENCY] \(message)")
    }

    func markButtonAction(opening: Bool) {
        guard chatLatencyDebugEnabled else { return }
        lock.lock()
        token &+= 1
        self.opening = opening
        actionNs = monotonicNowNs()
        animationCommitNs = 0
        firstVsyncNs = 0
        signpostID = OSSignpostID(log: signpostLog)
        let currentToken = token
        lock.unlock()

        os_signpost(.begin, log: signpostLog, name: "right_aux_toggle", signpostID: signpostID, "%{public}@ token=%llu", opening ? "open" : "close", currentToken)
        os_log("button_action %{public}@ token=%llu", log: log, type: .info, opening ? "open" : "close", currentToken)
        stdoutLog("button_action \(opening ? "open" : "close") token=\(currentToken)")
        startDisplayLinkIfNeeded()
    }

    func markAnimationCommitted() {
        guard chatLatencyDebugEnabled else { return }
        let now = monotonicNowNs()
        lock.lock()
        if animationCommitNs == 0 {
            animationCommitNs = now
        }
        let currentToken = token
        let opening = self.opening
        let deltaMs = Double(now &- actionNs) / 1_000_000.0
        lock.unlock()

        os_signpost(.event, log: signpostLog, name: "anim_commit", signpostID: signpostID, "dt_ms=%.3f token=%llu", deltaMs, currentToken)
        os_log("anim_commit %{public}@ dt_ms=%.3f token=%llu", log: log, type: .info, opening ? "open" : "close", deltaMs, currentToken)
        stdoutLog(String(format: "anim_commit %@ dt_ms=%.3f token=%llu", opening ? "open" : "close", deltaMs, currentToken))
    }

    private func markFirstVsyncCallback(vsyncNs: UInt64) {
        guard chatLatencyDebugEnabled else { return }
        lock.lock()
        guard firstVsyncNs == 0 else { lock.unlock(); return }
        firstVsyncNs = vsyncNs
        let currentToken = token
        let opening = self.opening
        let actionDeltaMs = Double(vsyncNs &- actionNs) / 1_000_000.0
        let commitDeltaMs: Double
        if animationCommitNs > 0, vsyncNs >= animationCommitNs {
            commitDeltaMs = Double(vsyncNs &- animationCommitNs) / 1_000_000.0
        } else {
            commitDeltaMs = -1
        }
        lock.unlock()

        os_signpost(.event, log: signpostLog, name: "first_vsync", signpostID: signpostID, "action_ms=%.3f commit_ms=%.3f token=%llu", actionDeltaMs, commitDeltaMs, currentToken)
        os_log("first_vsync %{public}@ action_ms=%.3f commit_ms=%.3f token=%llu", log: log, type: .info, opening ? "open" : "close", actionDeltaMs, commitDeltaMs, currentToken)
        stdoutLog(String(format: "first_vsync %@ action_ms=%.3f commit_ms=%.3f token=%llu", opening ? "open" : "close", actionDeltaMs, commitDeltaMs, currentToken))
        os_signpost(.end, log: signpostLog, name: "right_aux_toggle", signpostID: signpostID, "token=%llu", currentToken)
        stopDisplayLinkIfNeeded()
    }

    private func startDisplayLinkIfNeeded() {
        guard chatLatencyDebugEnabled else { return }
        lock.lock()
        let needsStart = !displayLinkActive
        lock.unlock()
        guard needsStart else { return }

        var link: CVDisplayLink?
        let result = CVDisplayLinkCreateWithActiveCGDisplays(&link)
        guard result == kCVReturnSuccess, let created = link else {
            os_log("CVDisplayLinkCreate failed=%d", log: log, type: .error, result)
            return
        }

        let callback: CVDisplayLinkOutputCallback = { _, _, _, _, _, context in
            guard let context else { return kCVReturnSuccess }
            let probe = Unmanaged<ChatLatencyProbe>.fromOpaque(context).takeUnretainedValue()
            let vsyncNs = monotonicNowNs()
            DispatchQueue.main.async {
                probe.markFirstVsyncCallback(vsyncNs: vsyncNs)
            }
            return kCVReturnSuccess
        }

        CVDisplayLinkSetOutputCallback(created, callback, Unmanaged.passUnretained(self).toOpaque())
        CVDisplayLinkStart(created)

        lock.lock()
        displayLink = created
        displayLinkActive = true
        lock.unlock()
    }

    private func stopDisplayLinkIfNeeded() {
        lock.lock()
        guard displayLinkActive, let link = displayLink else { lock.unlock(); return }
        displayLinkActive = false
        displayLink = nil
        lock.unlock()
        CVDisplayLinkStop(link)
    }
}

private func launchLog(_ message: String) {
    guard launchDebugEnabled else { return }
    NSLog("[LAUNCH] \(message)")
}

private func layoutLog(_ message: String) {
    guard debugLayoutEnabled else { return }
    NSLog("[LayoutDebug] \(message)")
}

private final class GapSplitView: NSSplitView {
    var gap: CGFloat = PANEL_INTER_CARD_GAP
    override var dividerThickness: CGFloat { max(1, gap) }

    override func drawDivider(in rect: NSRect) {
        // Intentionally no-op: keep the divider hit area without drawing the line.
    }

    override func resetCursorRects() {
        super.resetCursorRects()
        guard subviews.count >= 2 else { return }
        for i in 0..<(subviews.count - 1) {
            let rect = dividerRect(at: i)
            guard rect.width > 0, rect.height > 0 else { continue }
            addCursorRect(rect, cursor: .resizeLeftRight)
        }
    }

    func dividerRect(at index: Int) -> NSRect {
        // Important: do NOT derive the divider hitbox width from the transient gap between subviews.
        // During AppKit layout churn that gap can become very large, which makes hit-testing/drags
        // feel “stuck” or trigger in the wrong place. Always return a deterministic divider rect.
        guard index >= 0, index < (subviews.count - 1) else { return .zero }
        let first = subviews[index].frame
        let thickness = dividerThickness
        if isVertical {
            return NSRect(x: first.maxX, y: 0, width: thickness, height: bounds.height)
        } else {
            return NSRect(x: 0, y: first.maxY, width: bounds.width, height: thickness)
        }
    }
}

private final class SplitDividerHandleView: NSView {
    private let lineLayer = CALayer()
    private var trackingArea: NSTrackingArea?
    private var dragStartX: CGFloat = 0
    private var dragStartPosition: CGFloat = 0
    private var isHovering = false
    private var isDragging = false
    private var didBeginDragCallback = false
    private let lineWidth: CGFloat = max(1, PANEL_BORDER_WIDTH)
    private var lastDragLogTime: TimeInterval = 0

    var paletteProvider: (() -> (fill: NSColor, glow: NSColor, glowOpacity: Float))?
    var positionProvider: (() -> CGFloat)?
    var clampPosition: ((CGFloat) -> CGFloat)?
    var applyPosition: ((CGFloat) -> Void)?
    var onDragBegin: (() -> Void)?
    var onDragEnd: (() -> Void)?
    var debugName: String = "divider_handle"

    private var appearanceObserver: Any?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
        lineLayer.backgroundColor = NSColor.clear.cgColor
        lineLayer.shadowOpacity = 0
        lineLayer.shadowRadius = 0
        lineLayer.shadowOffset = .zero
        lineLayer.masksToBounds = false
        lineLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
        layer?.addSublayer(lineLayer)
        updateLineStyle()

        appearanceObserver = NotificationCenter.default.addObserver(
            forName: .arxivAppearanceDidChange,
            object: AppearanceManager.shared,
            queue: .main
        ) { [weak self] _ in
            self?.updateLineStyle()
        }
    }

    required init?(coder: NSCoder) { fatalError() }

    deinit {
        if let appearanceObserver {
            NotificationCenter.default.removeObserver(appearanceObserver)
        }
    }

    override var isOpaque: Bool { false }

    override func layout() {
        super.layout()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        let verticalInset = max(4, min(12, PANEL_CORNER_RADIUS * 0.4))
        let height = max(0, bounds.height - (2 * verticalInset))
        let x = (bounds.width - lineWidth) / 2
        lineLayer.frame = NSRect(x: x, y: verticalInset, width: lineWidth, height: height)
        lineLayer.cornerRadius = lineWidth / 2
        lineLayer.shadowPath = CGPath(roundedRect: lineLayer.bounds,
                                      cornerWidth: lineLayer.cornerRadius,
                                      cornerHeight: lineLayer.cornerRadius,
                                      transform: nil)
        CATransaction.commit()
    }

    override func viewDidChangeBackingProperties() {
        super.viewDidChangeBackingProperties()
        lineLayer.contentsScale = window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0
    }

    override func updateTrackingAreas() {
        if let trackingArea {
            removeTrackingArea(trackingArea)
        }
        let area = NSTrackingArea(rect: bounds,
                                  options: [.mouseEnteredAndExited, .activeInKeyWindow, .inVisibleRect],
                                  owner: self,
                                  userInfo: nil)
        addTrackingArea(area)
        trackingArea = area
        super.updateTrackingAreas()
    }

    override func mouseEntered(with event: NSEvent) {
        isHovering = true
        updateLineStyle()
        super.mouseEntered(with: event)
    }

    override func mouseExited(with event: NSEvent) {
        isHovering = false
        updateLineStyle()
        super.mouseExited(with: event)
    }

    override func resetCursorRects() {
        super.resetCursorRects()
        addCursorRect(bounds, cursor: .resizeLeftRight)
    }

    override func mouseDown(with event: NSEvent) {
        dragStartX = event.locationInWindow.x
        dragStartPosition = positionProvider?() ?? 0
        isDragging = true
        didBeginDragCallback = false
        updateLineStyle()
        layoutLog("\(debugName) mouse_down x=\(String(format: "%.1f", event.locationInWindow.x)) start=\(Int(dragStartPosition)) frame=\(Int(frame.origin.x)),\(Int(frame.origin.y)) \(Int(frame.width))x\(Int(frame.height))")
    }

    override func mouseDragged(with event: NSEvent) {
        guard isDragging else { return }
        let delta = event.locationInWindow.x - dragStartX
        // Prevent immediate state flips on a mere click; only treat as a drag
        // once the pointer has moved a couple of pixels.
        if !didBeginDragCallback, abs(delta) >= 2 {
            didBeginDragCallback = true
            onDragBegin?()
            if debugLayoutEnabled {
                layoutLog("\(debugName) drag_begin_threshold delta=\(Int(delta))")
            }
        }
        guard didBeginDragCallback else { return }
        let proposed = dragStartPosition + delta
        let clamped = clampPosition?(proposed) ?? proposed
        if debugLayoutEnabled {
            let t = event.timestamp
            if t - lastDragLogTime > 0.05 {
                lastDragLogTime = t
                layoutLog("\(debugName) mouse_drag delta=\(Int(delta)) proposed=\(Int(proposed)) clamped=\(Int(clamped))")
            }
        }
        applyPosition?(clamped)
    }

    override func mouseUp(with event: NSEvent) {
        guard isDragging else { return }
        isDragging = false
        updateLineStyle()
        layoutLog("\(debugName) mouse_up x=\(String(format: "%.1f", event.locationInWindow.x))")
        if didBeginDragCallback {
            onDragEnd?()
        } else if debugLayoutEnabled {
            layoutLog("\(debugName) click_without_drag")
        }
        didBeginDragCallback = false
    }

    func refreshStyle() {
        updateLineStyle()
    }

    private func updateLineStyle() {
        let palette = paletteProvider?() ?? (
            fill: resolvedSystemColor(.separatorColor).withAlphaComponent(0.2),
            glow: NSColor.white.withAlphaComponent(0.2),
            glowOpacity: 0.2
        )
        let boost: CGFloat = (isHovering || isDragging) ? 0.12 : 0.0
        let fill = boostedAlpha(palette.fill, by: boost)
        let glow = boostedAlpha(palette.glow, by: boost * 0.6)
        let glowOpacity = min(1.0, palette.glowOpacity + Float(boost * 1.2))

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        lineLayer.backgroundColor = fill.cgColor
        lineLayer.shadowColor = glow.cgColor
        lineLayer.shadowOpacity = glowOpacity
        lineLayer.shadowRadius = (isHovering || isDragging) ? 6 : 3
        lineLayer.shadowOffset = .zero
        CATransaction.commit()
    }

    private func boostedAlpha(_ color: NSColor, by boost: CGFloat) -> NSColor {
        let c = color.usingColorSpace(.deviceRGB) ?? color
        return c.withAlphaComponent(min(1, c.alphaComponent + boost))
    }
}

private final class DebugHitTestOverlayView: NSView {
    private let outlineLayer = CAShapeLayer()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
        outlineLayer.fillColor = NSColor.clear.cgColor
        outlineLayer.strokeColor = NSColor.systemRed.cgColor
        outlineLayer.lineWidth = 1.5
        outlineLayer.lineDashPattern = [6, 4]
        outlineLayer.isHidden = true
        if let layer = layer {
            layer.addSublayer(outlineLayer)
        }
    }

    required init?(coder: NSCoder) { fatalError() }

    override var isOpaque: Bool { false }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    func update(rect: NSRect) {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        outlineLayer.frame = bounds
        outlineLayer.path = CGPath(rect: rect, transform: nil)
        outlineLayer.isHidden = false
        CATransaction.commit()
    }

    func hide() {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        outlineLayer.isHidden = true
        CATransaction.commit()
    }
}

private final class DebugLayoutOverlayView: NSView {
    struct Item {
        let name: String
        let rect: NSRect
        let color: NSColor
        let label: String
    }

    private var itemLayers: [String: (shape: CAShapeLayer, text: CATextLayer)] = [:]

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
    }

    required init?(coder: NSCoder) { fatalError() }

    override var isOpaque: Bool { false }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    func update(items: [Item]) {
        guard let rootLayer = layer else { return }
        let scale = window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0

        CATransaction.begin()
        CATransaction.setDisableActions(true)

        var seen = Set<String>()
        for item in items {
            seen.insert(item.name)
            let pair: (CAShapeLayer, CATextLayer)
            if let existing = itemLayers[item.name] {
                pair = existing
            } else {
                let shape = CAShapeLayer()
                shape.fillColor = NSColor.clear.cgColor
                shape.lineWidth = 2
                shape.lineDashPattern = [5, 3]

                let text = CATextLayer()
                text.contentsScale = scale
                text.alignmentMode = .left
                text.font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
                text.fontSize = 11

                rootLayer.addSublayer(shape)
                rootLayer.addSublayer(text)
                itemLayers[item.name] = (shape, text)
                pair = (shape, text)
            }

            pair.0.strokeColor = item.color.cgColor
            pair.0.path = CGPath(rect: item.rect, transform: nil)
            pair.0.isHidden = item.rect.width <= 0 || item.rect.height <= 0

            pair.1.foregroundColor = item.color.cgColor
            pair.1.string = item.label
            let labelX = max(0, item.rect.minX + 4)
            let labelY = min(bounds.height - 16, max(0, item.rect.maxY - 16))
            pair.1.frame = NSRect(x: labelX, y: labelY, width: min(bounds.width - labelX, 520), height: 14)
            pair.1.isHidden = pair.0.isHidden
        }

        for (name, pair) in itemLayers where !seen.contains(name) {
            pair.shape.isHidden = true
            pair.text.isHidden = true
        }

        CATransaction.commit()
    }
}

// Apple Music–grade liquid glass renderer (Core Image + Metal when available).
private final class LiquidGlassRenderer {
    struct Parameters: Equatable {
        // Diffusion model (points; multiplied by backing scale for pixels).
        // CALIBRATION (clarity leap): aggressively reduce diffusion, increase refraction + rim energy.
        //
        // Numerical diff (frost → clear pass):
        // - diffusionBlurRadius: 0.65 → 0.25
        // - centerBlurMix: 0.10 → 0.04
        // - edgeBlurMix: 0.40 → 0.18
        // - refractionScale: 22.0 → 30.0
        // - refractionAmplitude: 0.28 → 0.34
        // - centerRefractionMix: 0.08 → 0.13
        // - rimMaskWidth: 15.0 → 12.0
        // - rimMaskSoftness: 7.0 → 5.0
        // - tintAlpha: [0.0006, 0.014] → [0.0002, 0.006]
        // - fresnel: intensity 0.30 → 0.38, exponent 2.35 → 2.80
        // The pipeline now uses a single diffusion blur pass; softness comes from refraction.
        var diffusionBlurRadius: CGFloat = 0.25
        // How much of the blurred sample to mix into transmission (0 = fully clear, 1 = fully blurred).
        // Kept very low so the material reads as clear liquid acrylic rather than etched glass.
        var centerBlurMix: CGFloat = 0.04
        var edgeBlurMix: CGFloat = 0.18
        // Refraction.
        var refractionScale: CGFloat = 30.0
        var refractionAmplitude: CGFloat = 0.34
        // Apply a small amount of refraction across the whole surface so the center reads “liquid”
        // (still weaker than the rim, which is mask-boosted).
        var centerRefractionMix: CGFloat = 0.13
        // Rim/edge falloff controls (points).
        var rimMaskWidth: CGFloat = 12.0
        var rimMaskSoftness: CGFloat = 5.0
        // Fresnel (edge reflectance): increases reflectivity at edges without reducing center transmission.
        var fresnelIntensity: CGFloat = 0.38
        var fresnelExponent: CGFloat = 2.80
        var fresnelCornerBoost: CGFloat = 0.25
        // Color behavior.
        var saturation: CGFloat = 1.05
        var contrast: CGFloat = 1.06
        // Milkiness overlay bounds (auto-tuned via background luminance).
        var tintAlphaMin: CGFloat = 0.0002
        var tintAlphaMax: CGFloat = 0.006
        struct TintOverride: Equatable {
            var r: CGFloat
            var g: CGFloat
            var b: CGFloat
        }
        var tintOverride: TintOverride? = nil
        // Micro noise: disabled by default (noise should modulate refraction, not act like opacity).
        var noiseOpacity: CGFloat = 0.0

        var enableRefraction: Bool = true
        var enableNoise: Bool = true

        func scaled(by s: CGFloat) -> Parameters {
            var p = self
            p.diffusionBlurRadius *= s
            p.refractionScale *= s
            p.rimMaskWidth *= s
            p.rimMaskSoftness *= s
            return p
        }
    }

    enum DebugView: String {
        case none
        case rimMask
        case aoMask
        case refractionField
        case baseBlur
        case edgeBlur
        case final
    }

    static let shared = LiquidGlassRenderer()

    private let context: CIContext
    private let queue = DispatchQueue(label: "LiquidGlassRenderer.queue", qos: .userInitiated)
    private let deviceRGB = CGColorSpaceCreateDeviceRGB()

    private init() {
        if let device = MTLCreateSystemDefaultDevice() {
            context = CIContext(mtlDevice: device, options: [
                CIContextOption.workingColorSpace: deviceRGB,
                CIContextOption.outputColorSpace: deviceRGB
            ])
        } else {
            context = CIContext(options: [
                CIContextOption.workingColorSpace: deviceRGB,
                CIContextOption.outputColorSpace: deviceRGB
            ])
        }
    }

    func renderAsync(background: CGImage,
                     sizePx: CGSize,
                     cornerRadiusPx: CGFloat,
                     isDark: Bool,
                     parameters: Parameters,
                     debug: DebugView,
                     completion: @escaping (CGImage?) -> Void) {
        queue.async { [weak self] in
	            guard let self else { return }
            let out = self.render(background: background,
                                  sizePx: sizePx,
                                  cornerRadiusPx: cornerRadiusPx,
                                  isDark: isDark,
                                  parameters: parameters,
                                  debug: debug)
            DispatchQueue.main.async { completion(out) }
        }
    }

    private func render(background: CGImage,
                        sizePx: CGSize,
                        cornerRadiusPx: CGFloat,
                        isDark: Bool,
                        parameters: Parameters,
                        debug: DebugView) -> CGImage? {
        let extent = CGRect(origin: .zero, size: sizePx.integralSize)
        guard extent.width >= 2, extent.height >= 2 else { return nil }

        var input = CIImage(cgImage: background)
        // Ensure the sampled background matches the requested render size (avoid 1px seams from rounding differences).
        if abs(input.extent.width - extent.width) > 0.5 || abs(input.extent.height - extent.height) > 0.5 {
            let sx = extent.width / max(1.0, input.extent.width)
            let sy = extent.height / max(1.0, input.extent.height)
            input = input.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
        }
        input = input.cropped(to: extent)
        let clamped = input.clampedToExtent()

        let rimMask = makeRimMask(extent: extent,
                                  cornerRadius: cornerRadiusPx,
                                  width: parameters.rimMaskWidth,
                                  softness: parameters.rimMaskSoftness)
        let aoMask = makeAOMask(from: rimMask, extent: extent)

        // Transmission: single-pass diffusion blur (center clearer, rim slightly more diffused).
        // Key point: blend blurred transmission over the *original* sample so we keep fine background detail.
        let diffusionBlur = gaussianBlur(clamped, radius: parameters.diffusionBlurRadius).cropped(to: extent)

        if debug == .rimMask {
            return context.createCGImage(rimMask, from: extent)
        }
        if debug == .aoMask {
            return context.createCGImage(aoMask, from: extent)
        }

        if debug == .baseBlur || debug == .edgeBlur {
            return context.createCGImage(diffusionBlur, from: extent)
        }

        let diffusionMask = mixMask(rimMask,
                                    base: parameters.centerBlurMix,
                                    edge: parameters.edgeBlurMix,
                                    extent: extent)
        var glass = blendWithMask(foreground: diffusionBlur, background: clamped, mask: diffusionMask) ?? clamped

        // Refraction: apply distortion to the *less blurred* background so we bend light instead of erasing detail.
        if parameters.enableRefraction,
           let refractedRaw = glassDistortion(image: clamped,
                                              extent: extent,
                                              isDark: isDark,
                                              scale: parameters.refractionScale,
                                              amplitude: parameters.refractionAmplitude) {
            if debug == .refractionField {
                return context.createCGImage(refractionTexture(extent: extent,
                                                               isDark: isDark,
                                                               amplitude: parameters.refractionAmplitude),
                                             from: extent)
            }
            // Keep refraction *sharp*: minimal blur to suppress aliasing only.
            let refr = gaussianBlur(refractedRaw.clampedToExtent(),
                                    radius: max(0.12, parameters.diffusionBlurRadius * 0.18)).cropped(to: extent)

            // Keep center highly transmissive: refraction is strongest near the rim (mask-weighted).
            var refrMask = powMask(rimMask, exponent: 2.10, extent: extent)
            let baseMix = max(0.0, min(0.25, parameters.centerRefractionMix))
            if baseMix > 0.0001 {
                refrMask = mixMask(refrMask, base: baseMix, edge: 1.0, extent: extent)
            }
            glass = blendWithMask(foreground: refr, background: glass, mask: refrMask) ?? glass
        }

        // Tint / internal light pooling:
        // Use *screen* blending of a very low-alpha, background-tinted swatch so we lift perceived brightness
        // without adding a milky source-over veil (better match to Apple’s “clear wet glass” samples).
        let avg = areaAverageRGB(input: input, extent: extent)
        let luma = (0.2126 * avg.r + 0.7152 * avg.g + 0.0722 * avg.b)
        let t = max(0.0, min(1.0, (luma - 0.15) / 0.70))
        let tintAlpha = lerp(parameters.tintAlphaMin, parameters.tintAlphaMax, t: t) * (isDark ? 1.05 : 0.90)
        let tintMix: CGFloat = isDark ? 0.66 : 0.70
        let tintBase: (r: CGFloat, g: CGFloat, b: CGFloat)
        if let override = parameters.tintOverride {
            tintBase = (override.r, override.g, override.b)
        } else {
            tintBase = (avg.r, avg.g, avg.b)
        }
        let tintR = lerp(tintBase.r, 1.0, t: tintMix)
        let tintG = lerp(tintBase.g, 1.0, t: tintMix)
        let tintB = lerp(tintBase.b, 1.0, t: tintMix)
        let tint = CIImage(color: CIColor(red: tintR, green: tintG, blue: tintB, alpha: tintAlpha)).cropped(to: extent)
        glass = screenBlend(foreground: tint, background: glass) ?? tint.composited(over: glass)

        // Subtle contrast/saturation lift to keep micro-contrast (avoid “chalky” blur).
        glass = colorControls(input: glass,
                              saturation: parameters.saturation,
                              contrast: parameters.contrast,
                              brightness: isDark ? 0.003 : 0.0) ?? glass

        // Ambient occlusion: faint darkening near the contact edge (inside the glass), masked to the rim zone.
        let aoStrength: CGFloat = isDark ? 0.042 : 0.030
        let aoTint = CIImage(color: CIColor(red: 0, green: 0, blue: 0, alpha: aoStrength)).cropped(to: extent)
        if let aoApplied = blendWithMask(foreground: aoTint, background: glass, mask: aoMask) {
            glass = aoApplied
        }

        // Fresnel edge reflectance (dedicated term): brighter/wetter rim while the center stays highly transmissive.
        if parameters.fresnelIntensity > 0.0001 {
            let fresnelMask = makeFresnelMask(rimMask: rimMask,
                                              extent: extent,
                                              exponent: parameters.fresnelExponent,
                                              cornerBoost: parameters.fresnelCornerBoost)
            let fresnelWhite = CIImage(color: CIColor(red: 1, green: 1, blue: 1, alpha: parameters.fresnelIntensity)).cropped(to: extent)
            if let fresnelApplied = blendWithMask(foreground: fresnelWhite, background: glass, mask: fresnelMask) {
                glass = fresnelApplied
            }
        }

        if parameters.enableNoise, parameters.noiseOpacity > 0.0001 {
            glass = addMicroNoise(to: glass, extent: extent, opacity: parameters.noiseOpacity) ?? glass
        }

        return context.createCGImage(glass.cropped(to: extent), from: extent)
    }

    private func gaussianBlur(_ image: CIImage, radius: CGFloat) -> CIImage {
        guard radius > 0.001 else { return image }
        let f = CIFilter.gaussianBlur()
        f.inputImage = image
        f.radius = Float(radius)
        return f.outputImage ?? image
    }

    private func colorControls(input: CIImage, saturation: CGFloat, contrast: CGFloat, brightness: CGFloat) -> CIImage? {
        let f = CIFilter.colorControls()
        f.inputImage = input
        f.saturation = Float(saturation)
        f.contrast = Float(contrast)
        f.brightness = Float(brightness)
        return f.outputImage
    }

    private func blendWithMask(foreground: CIImage, background: CIImage, mask: CIImage) -> CIImage? {
        let f = CIFilter.blendWithMask()
        f.inputImage = foreground
        f.backgroundImage = background
        f.maskImage = mask
        return f.outputImage
    }

    private func screenBlend(foreground: CIImage, background: CIImage) -> CIImage? {
        let f = CIFilter.screenBlendMode()
        f.inputImage = foreground
        f.backgroundImage = background
        return f.outputImage
    }

    private func mixMask(_ mask: CIImage, base: CGFloat, edge: CGFloat, extent: CGRect) -> CIImage {
        let b = max(0.0, min(1.0, base))
        let e = max(0.0, min(1.0, edge))
        let scale = max(0.0, e - b)
        let scaled = mask.applyingFilter("CIColorMatrix", parameters: [
            "inputRVector": CIVector(x: scale, y: 0, z: 0, w: 0),
            "inputGVector": CIVector(x: scale, y: 0, z: 0, w: 0),
            "inputBVector": CIVector(x: scale, y: 0, z: 0, w: 0),
            "inputBiasVector": CIVector(x: b, y: b, z: b, w: 0)
        ]).cropped(to: extent)
        let clamp = CIFilter.colorClamp()
        clamp.inputImage = scaled
        clamp.minComponents = CIVector(x: 0, y: 0, z: 0, w: 0)
        clamp.maxComponents = CIVector(x: 1, y: 1, z: 1, w: 1)
        return (clamp.outputImage ?? scaled).cropped(to: extent)
    }

    private func powMask(_ mask: CIImage, exponent: CGFloat, extent: CGRect) -> CIImage {
        let p = max(0.25, min(4.0, exponent))
        let g = CIFilter.gammaAdjust()
        g.inputImage = mask
        g.power = Float(p)
        return (g.outputImage ?? mask).cropped(to: extent)
    }

    private func makeFresnelMask(rimMask: CIImage,
                                 extent: CGRect,
                                 exponent: CGFloat,
                                 cornerBoost: CGFloat) -> CIImage {
        // Fresnel response ramps smoothly with the rim mask and gets a small extra lift at corners (higher curvature).
        var mask = powMask(rimMask, exponent: exponent, extent: extent)

        let cb = max(0.0, min(0.4, cornerBoost))
        if cb > 0.0001, let corners = makeCornerBoostMask(extent: extent) {
            let scaled = corners.applyingFilter("CIColorMatrix", parameters: [
                "inputRVector": CIVector(x: cb, y: 0, z: 0, w: 0),
                "inputGVector": CIVector(x: cb, y: 0, z: 0, w: 0),
                "inputBVector": CIVector(x: cb, y: 0, z: 0, w: 0),
                "inputBiasVector": CIVector(x: 0, y: 0, z: 0, w: 0)
            ]).cropped(to: extent)
            let add = CIFilter.additionCompositing()
            add.inputImage = scaled
            add.backgroundImage = mask
            mask = (add.outputImage ?? mask).cropped(to: extent)
        }

        // Clamp to [0,1] to avoid hard clipping artifacts.
        let clamp = CIFilter.colorClamp()
        clamp.inputImage = mask
        clamp.minComponents = CIVector(x: 0, y: 0, z: 0, w: 0)
        clamp.maxComponents = CIVector(x: 1, y: 1, z: 1, w: 1)
        return (clamp.outputImage ?? mask).cropped(to: extent)
    }

    private func makeCornerBoostMask(extent: CGRect) -> CIImage? {
        // Corner-only mask (1 at corners, 0 on flats): sum of four radial gradients, clamped.
        let r = max(24.0, min(extent.width, extent.height) * 0.35)
        func radial(at p: CGPoint) -> CIImage? {
            guard let f = CIFilter(name: "CIRadialGradient") else { return nil }
            f.setValue(CIVector(x: p.x, y: p.y), forKey: "inputCenter")
            f.setValue(0.0, forKey: "inputRadius0")
            f.setValue(r, forKey: "inputRadius1")
            f.setValue(CIColor(red: 1, green: 1, blue: 1, alpha: 1), forKey: "inputColor0")
            f.setValue(CIColor(red: 0, green: 0, blue: 0, alpha: 1), forKey: "inputColor1")
            return (f.outputImage?.cropped(to: extent))
        }

        guard let tl = radial(at: CGPoint(x: extent.minX, y: extent.maxY)),
              let tr = radial(at: CGPoint(x: extent.maxX, y: extent.maxY)),
              let bl = radial(at: CGPoint(x: extent.minX, y: extent.minY)),
              let br = radial(at: CGPoint(x: extent.maxX, y: extent.minY)) else { return nil }

        let add1 = CIFilter.additionCompositing()
        add1.inputImage = tl
        add1.backgroundImage = tr
        let sum1 = (add1.outputImage ?? tl).cropped(to: extent)

        let add2 = CIFilter.additionCompositing()
        add2.inputImage = bl
        add2.backgroundImage = br
        let sum2 = (add2.outputImage ?? bl).cropped(to: extent)

        let add3 = CIFilter.additionCompositing()
        add3.inputImage = sum1
        add3.backgroundImage = sum2
        let sum = (add3.outputImage ?? sum1).cropped(to: extent)

        let clamp = CIFilter.colorClamp()
        clamp.inputImage = sum
        clamp.minComponents = CIVector(x: 0, y: 0, z: 0, w: 0)
        clamp.maxComponents = CIVector(x: 1, y: 1, z: 1, w: 1)
        return (clamp.outputImage ?? sum).cropped(to: extent)
    }

    private func makeRimMask(extent: CGRect, cornerRadius: CGFloat, width: CGFloat, softness: CGFloat) -> CIImage {
        // 0 in the center, 1 near the rim (rounded-rect stroke blurred outward).
        let size = extent.size.integralSize
        let w = max(2, Int(size.width))
        let h = max(2, Int(size.height))
        let cs = CGColorSpaceCreateDeviceGray()
        guard let ctx = CGContext(data: nil,
                                  width: w,
                                  height: h,
                                  bitsPerComponent: 8,
                                  bytesPerRow: w,
                                  space: cs,
                                  bitmapInfo: CGImageAlphaInfo.none.rawValue) else {
            return CIImage(color: CIColor(red: 0, green: 0, blue: 0, alpha: 1)).cropped(to: extent)
        }
        ctx.setFillColor(gray: 0.0, alpha: 1.0)
        ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))

        let stroke = max(1.0, width)
        ctx.setStrokeColor(gray: 1.0, alpha: 1.0)
        ctx.setLineWidth(stroke)
        ctx.setLineJoin(.round)

        let inset = stroke / 2
        let rect = CGRect(x: inset, y: inset, width: CGFloat(w) - stroke, height: CGFloat(h) - stroke)
        let r = max(0, cornerRadius)
        ctx.addPath(CGPath(roundedRect: rect, cornerWidth: r, cornerHeight: r, transform: nil))
        ctx.strokePath()

        guard let cg = ctx.makeImage() else {
            return CIImage(color: CIColor(red: 0, green: 0, blue: 0, alpha: 1)).cropped(to: extent)
        }
        var mask = CIImage(cgImage: cg).cropped(to: extent)
        if softness > 0.5 {
            let blurred = gaussianBlur(mask.clampedToExtent(), radius: softness).cropped(to: extent)
            mask = blurred
        }
        // Clamp to [0,1] and keep as grayscale mask.
        let normalize = CIFilter.colorControls()
        normalize.inputImage = mask
        normalize.saturation = 0
        normalize.contrast = 1.2
        normalize.brightness = 0
        return (normalize.outputImage ?? mask).cropped(to: extent)
    }

    private func makeAOMask(from rimMask: CIImage, extent: CGRect) -> CIImage {
        // Slightly wider and softer than rimMask so AO sits under the highlight instead of looking like a hard outline.
        let blur = max(6.0, min(18.0, min(extent.width, extent.height) * 0.020))
        let widened = gaussianBlur(rimMask.clampedToExtent(), radius: blur).cropped(to: extent)
        let f = CIFilter.colorControls()
        f.inputImage = widened
        f.saturation = 0
        f.contrast = 1.0
        f.brightness = -0.02
        return (f.outputImage ?? widened).cropped(to: extent)
    }

    private func refractionTexture(extent: CGRect, isDark: Bool, amplitude: CGFloat) -> CIImage {
        // Refraction field (centered around 0.5 so distortion bends light instead of drifting/erasing it).
        // Replace “frost” with refraction by using a smooth, liquid normal-field:
        // - low-frequency component for broad lensing
        // - small high-frequency component for subtle waviness (NOT opacity grain)
        let blurLow = max(8.0, min(18.0, min(extent.width, extent.height) * 0.020))
        let blurHigh = max(2.2, min(5.0, blurLow * 0.24))

        guard let noise = CIFilter.randomGenerator().outputImage?
            .cropped(to: extent)
            .applyingFilter("CIColorControls", parameters: [kCIInputSaturationKey: 0.0, kCIInputContrastKey: 0.9])
            .cropped(to: extent) else {
            return CIImage(color: CIColor(red: 0.5, green: 0.5, blue: 0.5, alpha: 1)).cropped(to: extent)
        }

        let low = gaussianBlur(noise.clampedToExtent(), radius: blurLow).cropped(to: extent)
        let high = gaussianBlur(noise.clampedToExtent(), radius: blurHigh).cropped(to: extent)

        // Weighted sum: 0.90*low + 0.10*high.
        let lowScaled = low.applyingFilter("CIColorMatrix", parameters: [
            "inputRVector": CIVector(x: 0.90, y: 0, z: 0, w: 0),
            "inputGVector": CIVector(x: 0.90, y: 0, z: 0, w: 0),
            "inputBVector": CIVector(x: 0.90, y: 0, z: 0, w: 0),
            "inputBiasVector": CIVector(x: 0, y: 0, z: 0, w: 0)
        ]).cropped(to: extent)
        let highScaled = high.applyingFilter("CIColorMatrix", parameters: [
            "inputRVector": CIVector(x: 0.10, y: 0, z: 0, w: 0),
            "inputGVector": CIVector(x: 0.10, y: 0, z: 0, w: 0),
            "inputBVector": CIVector(x: 0.10, y: 0, z: 0, w: 0),
            "inputBiasVector": CIVector(x: 0, y: 0, z: 0, w: 0)
        ]).cropped(to: extent)

        let add = CIFilter.additionCompositing()
        add.inputImage = highScaled
        add.backgroundImage = lowScaled
        let raw = (add.outputImage ?? lowScaled).cropped(to: extent)

        // Center around 0.5 with small amplitude.
        let a = max(0.12, min(0.45, amplitude))
        let amp: CGFloat = isDark ? a * 0.90 : a
        let bias: CGFloat = 0.5 * (1.0 - amp)
        let centered = raw.applyingFilter("CIColorMatrix", parameters: [
            "inputRVector": CIVector(x: amp, y: 0, z: 0, w: 0),
            "inputGVector": CIVector(x: amp, y: 0, z: 0, w: 0),
            "inputBVector": CIVector(x: amp, y: 0, z: 0, w: 0),
            "inputBiasVector": CIVector(x: bias, y: bias, z: bias, w: 0)
        ]).cropped(to: extent)
        return centered
    }

    private func glassDistortion(image: CIImage,
                                 extent: CGRect,
                                 isDark: Bool,
                                 scale: CGFloat,
                                 amplitude: CGFloat) -> CIImage? {
        guard scale > 0.001 else { return nil }
        guard let f = CIFilter(name: "CIGlassDistortion") else { return nil }
        f.setValue(image, forKey: kCIInputImageKey)
        // Core Image uses the key name "inputTexture" for CIGlassDistortion's texture map on older SDKs.
        f.setValue(refractionTexture(extent: extent, isDark: isDark, amplitude: amplitude), forKey: "inputTexture")
        f.setValue(scale, forKey: kCIInputScaleKey)
        return (f.outputImage?.cropped(to: extent))
    }

    private func addMicroNoise(to image: CIImage, extent: CGRect, opacity: CGFloat) -> CIImage? {
        guard let noise = CIFilter.randomGenerator().outputImage?.cropped(to: extent) else { return nil }
        // Convert to subtle monochrome noise centered near 0.5, then source-over at very low alpha.
        let n = noise
            .applyingFilter("CIColorControls", parameters: [kCIInputSaturationKey: 0.0, kCIInputContrastKey: 0.6])
            .cropped(to: extent)

        let noiseAlpha = max(0.0, min(0.08, opacity))
        let tint = CIImage(color: CIColor(red: 1, green: 1, blue: 1, alpha: noiseAlpha)).cropped(to: extent)
        let clear = CIImage(color: CIColor(red: 0, green: 0, blue: 0, alpha: 0)).cropped(to: extent)
        let n2 = blendWithMask(foreground: tint, background: clear, mask: n) ?? tint
        return n2.composited(over: image)
    }

    private func areaAverageRGB(input: CIImage, extent: CGRect) -> (r: CGFloat, g: CGFloat, b: CGFloat) {
        let f = CIFilter.areaAverage()
        f.inputImage = input
        f.extent = extent
        guard let out = f.outputImage else { return (0, 0, 0) }
        var px = [UInt8](repeating: 0, count: 4)
        context.render(out,
                       toBitmap: &px,
                       rowBytes: 4,
                       bounds: CGRect(x: 0, y: 0, width: 1, height: 1),
                       format: .RGBA8,
                       colorSpace: deviceRGB)
        return (CGFloat(px[0]) / 255.0, CGFloat(px[1]) / 255.0, CGFloat(px[2]) / 255.0)
    }

    private func lerp(_ a: CGFloat, _ b: CGFloat, t: CGFloat) -> CGFloat {
        a + (b - a) * max(0.0, min(1.0, t))
    }
}

private extension CGSize {
    var integralSize: CGSize { CGSize(width: ceil(width), height: ceil(height)) }
}

// Glass card material kit: condensed config + factory for reusable liquid-glass cards.
private enum GlassCardKit {
    enum State: String {
        case normal
        case hover
        case pressed
        case selected
        case disabled
    }

    struct ShadowStyle: Equatable {
        var rimOpacity: Float
        var rimRadius: CGFloat
        var rimOffset: CGSize
        var bottomAlpha: CGFloat

        static let subtle = ShadowStyle(rimOpacity: 0.30,
                                        rimRadius: 7.5,
                                        rimOffset: CGSize(width: 0, height: -0.9),
                                        bottomAlpha: 0.10)
    }

    struct BorderStyle: Equatable {
        var rimWidth: CGFloat
        var outerWidth: CGFloat
        var innerWidth: CGFloat
        var rimLightAlpha: CGFloat
        var rimDarkAlpha: CGFloat
        var outerAlpha: CGFloat
        var innerAlpha: CGFloat
        var dispersionAlpha: CGFloat

        static let clearRim = BorderStyle(rimWidth: 2.1,
                          outerWidth: 1.1,
                          innerWidth: 0.9,
                          rimLightAlpha: 0.04,   // 80% more transparent
                          rimDarkAlpha: 0.036,  // 80% more transparent
                          outerAlpha: 0.028,    // 80% more transparent
                          innerAlpha: 0.020,    // 80% more transparent
                          dispersionAlpha: 0.0056) // 80% more transparent
    }

    struct GlassCardConfig: Equatable {
        var cornerRadius: CGFloat = PANEL_CORNER_RADIUS
        var thickness: CGFloat = 1.0
        var transmission: CGFloat = 0.93
        var refractionStrength: CGFloat = 0.90
        var refractionScale: CGFloat = 30.0
        var fresnelStrength: CGFloat = 0.38
        var specularIntensity: CGFloat = 1.0
        var tint: NSColor? = nil
        var diffusionAmount: CGFloat = 0.08
        var shadowStyle: ShadowStyle = .subtle
        var borderStyle: BorderStyle = .clearRim
        var state: State = .normal

        static func == (lhs: GlassCardConfig, rhs: GlassCardConfig) -> Bool {
            return lhs.cornerRadius == rhs.cornerRadius &&
                lhs.thickness == rhs.thickness &&
                lhs.transmission == rhs.transmission &&
                lhs.refractionStrength == rhs.refractionStrength &&
                lhs.refractionScale == rhs.refractionScale &&
                lhs.fresnelStrength == rhs.fresnelStrength &&
                lhs.specularIntensity == rhs.specularIntensity &&
                lhs.diffusionAmount == rhs.diffusionAmount &&
                lhs.shadowStyle == rhs.shadowStyle &&
                lhs.borderStyle == rhs.borderStyle &&
                lhs.state == rhs.state &&
                tintSignature(lhs.tint) == tintSignature(rhs.tint)
        }

        private static func tintSignature(_ color: NSColor?) -> (Int, Int, Int, Int) {
            guard let color else { return (-1, -1, -1, -1) }
            let c = color.usingColorSpace(.deviceRGB) ?? color
            return (
                Int(max(0, min(255, round(c.redComponent * 255)))),
                Int(max(0, min(255, round(c.greenComponent * 255)))),
                Int(max(0, min(255, round(c.blueComponent * 255)))),
                Int(max(0, min(255, round(c.alphaComponent * 255))))
            )
        }
    }

    static func makeGlassCard(config: GlassCardConfig,
                              backgroundProvider: ((CGRect, CGFloat) -> CGImage?)? = nil) -> GlassCardView {
        let card = GlassCardView(frame: .zero, config: config)
        card.backgroundProvider = backgroundProvider
        return card
    }
}

// Glass card view: renders refraction + diffusion into a cached bitmap, then layers Apple-like rims on top.
private final class GlassCardView: NSView {
    private let backgroundImageLayer = CALayer()
    private let fillLayer = CALayer()
    private let highlightLayer = CAGradientLayer()
    private let shadowLayer = CAGradientLayer()
    // "Bubbly" rim: layered strokes + soft glow/shadow for a rounded glass edge.
    private let rimLightLayer = CAShapeLayer()
    private let rimDarkLayer = CAShapeLayer()
    private let strokeLayer = CAShapeLayer()
    private let innerStrokeLayer = CAShapeLayer()
    private let dispersionLayer = CAGradientLayer()
    private let dispersionMask = CAShapeLayer()
    private let symmetryGuideLayer = CAShapeLayer()

    var config: GlassCardKit.GlassCardConfig {
        didSet { applyConfig(from: oldValue) }
    }

    // Background sampling provider (rect in window coordinates, scale) -> CGImage.
    var backgroundProvider: ((CGRect, CGFloat) -> CGImage?)?

    private var renderWorkItem: DispatchWorkItem?
    private var lastRenderKey: String = ""
    private var frozenBackground: CGImage?
    private static var didLogLiquidGlassParams: Bool = false

    private var glassParams: LiquidGlassRenderer.Parameters {
        var p = makeRendererParameters()
        if ProcessInfo.processInfo.environment["ARXIV_GLASS_DISABLE_REFRACTION"] == "1" { p.enableRefraction = false }
        if ProcessInfo.processInfo.environment["ARXIV_GLASS_DISABLE_NOISE"] == "1" { p.enableNoise = false }
        return p
    }

    private var glassDebugView: LiquidGlassRenderer.DebugView {
        let raw = (ProcessInfo.processInfo.environment["ARXIV_GLASS_DEBUG"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return LiquidGlassRenderer.DebugView(rawValue: raw) ?? .none
    }

    private var freezeBackgroundSampling: Bool {
        ProcessInfo.processInfo.environment["ARXIV_GLASS_FREEZE_BG"] == "1"
    }

    var cornerRadius: CGFloat {
        get { config.cornerRadius }
        set {
            var next = config
            next.cornerRadius = newValue
            config = next
        }
    }

    init(frame frameRect: NSRect, config: GlassCardKit.GlassCardConfig) {
        self.config = config
        super.init(frame: frameRect)
        commonInit()
    }

    override init(frame frameRect: NSRect) {
        self.config = GlassCardKit.GlassCardConfig()
        super.init(frame: frameRect)
        commonInit()
    }

    required init?(coder: NSCoder) { fatalError() }

    private func commonInit() {
        wantsLayer = true
        layer?.masksToBounds = true
        if #available(macOS 10.13, *) { layer?.cornerCurve = .continuous }

        backgroundImageLayer.contentsGravity = .resize
        backgroundImageLayer.masksToBounds = true
        layer?.addSublayer(backgroundImageLayer)

        fillLayer.backgroundColor = NSColor.clear.cgColor
        layer?.addSublayer(fillLayer)

        highlightLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
        highlightLayer.endPoint = CGPoint(x: 0.5, y: 0.0)
        layer?.addSublayer(highlightLayer)

        shadowLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
        shadowLayer.endPoint = CGPoint(x: 0.5, y: 0.0)
        layer?.addSublayer(shadowLayer)

        rimDarkLayer.fillColor = NSColor.clear.cgColor
        rimDarkLayer.lineJoin = .round
        rimDarkLayer.lineCap = .round
        layer?.addSublayer(rimDarkLayer)

        rimLightLayer.fillColor = NSColor.clear.cgColor
        rimLightLayer.lineJoin = .round
        rimLightLayer.lineCap = .round
        layer?.addSublayer(rimLightLayer)

        // Rim-only chroma split (tasteful dispersion) - masked to the rim path.
        dispersionLayer.startPoint = CGPoint(x: 0.0, y: 0.5)
        dispersionLayer.endPoint = CGPoint(x: 1.0, y: 0.5)
        dispersionLayer.mask = dispersionMask
        layer?.addSublayer(dispersionLayer)

        strokeLayer.fillColor = NSColor.clear.cgColor
        strokeLayer.lineJoin = .round
        strokeLayer.lineCap = .round
        layer?.addSublayer(strokeLayer)

        innerStrokeLayer.fillColor = NSColor.clear.cgColor
        innerStrokeLayer.lineJoin = .round
        innerStrokeLayer.lineCap = .round
        layer?.addSublayer(innerStrokeLayer)
    }

    func updateConfig(_ newConfig: GlassCardKit.GlassCardConfig) {
        config = newConfig
    }

    func updateState(_ newState: GlassCardKit.State) {
        guard config.state != newState else { return }
        var next = config
        next.state = newState
        config = next
    }

    private func applyConfig(from oldValue: GlassCardKit.GlassCardConfig) {
        if oldValue.cornerRadius != config.cornerRadius {
            needsLayout = true
        }
        updateStyle()
        if needsRenderUpdate(from: oldValue, to: config) {
            invalidateGlass(reason: "config")
        }
    }

    private func needsRenderUpdate(from oldValue: GlassCardKit.GlassCardConfig,
                                   to newValue: GlassCardKit.GlassCardConfig) -> Bool {
        if oldValue.cornerRadius != newValue.cornerRadius { return true }
        if oldValue.transmission != newValue.transmission { return true }
        if oldValue.refractionStrength != newValue.refractionStrength { return true }
        if oldValue.refractionScale != newValue.refractionScale { return true }
        if oldValue.fresnelStrength != newValue.fresnelStrength { return true }
        if oldValue.diffusionAmount != newValue.diffusionAmount { return true }
        if oldValue.thickness != newValue.thickness { return true }
        if tintSignature(oldValue.tint) != tintSignature(newValue.tint) { return true }
        return false
    }

    private func tintSignature(_ color: NSColor?) -> (Int, Int, Int, Int) {
        guard let color else { return (-1, -1, -1, -1) }
        let c = color.usingColorSpace(.deviceRGB) ?? color
        return (
            Int(max(0, min(255, round(c.redComponent * 255)))),
            Int(max(0, min(255, round(c.greenComponent * 255)))),
            Int(max(0, min(255, round(c.blueComponent * 255)))),
            Int(max(0, min(255, round(c.alphaComponent * 255))))
        )
    }

    private func clampUnit(_ value: CGFloat) -> CGFloat {
        max(0.0, min(1.0, value))
    }

    private func stateMultipliers(for state: GlassCardKit.State) -> (specular: CGFloat, fill: CGFloat, shadow: CGFloat) {
        switch state {
        case .normal:
            return (1.0, 1.0, 1.0)
        case .hover:
            return (1.06, 1.05, 1.05)
        case .pressed:
            return (0.92, 1.08, 0.90)
        case .selected:
            return (1.10, 1.06, 1.10)
        case .disabled:
            return (0.75, 0.85, 0.60)
        }
    }

    private func makeRendererParameters() -> LiquidGlassRenderer.Parameters {
        var p = LiquidGlassRenderer.Parameters()
        let transmission = clampUnit(config.transmission)
        let diffusion = clampUnit(config.diffusionAmount)
        let refractionStrength = clampUnit(config.refractionStrength)
        let thickness = max(0.6, config.thickness)

        p.diffusionBlurRadius = 0.18 + diffusion * 0.75
        p.centerBlurMix = (1.0 - transmission) * 0.55
        let rimBoost = 0.03 + diffusion * 0.95
        p.edgeBlurMix = min(0.32, max(p.centerBlurMix, p.centerBlurMix + rimBoost))

        p.refractionScale = max(2.0, config.refractionScale)
        p.refractionAmplitude = 0.22 + 0.14 * refractionStrength
        p.centerRefractionMix = 0.04 + 0.11 * refractionStrength

        p.rimMaskWidth = 12.0 * thickness
        p.rimMaskSoftness = 5.0 * thickness

        p.fresnelIntensity = clampUnit(config.fresnelStrength)
        p.fresnelExponent = 2.80
        p.fresnelCornerBoost = min(0.35, 0.22 + 0.05 * thickness)

        if let tint = config.tint {
            let c = tint.usingColorSpace(.deviceRGB) ?? tint
            p.tintOverride = .init(r: c.redComponent, g: c.greenComponent, b: c.blueComponent)
            let a = clampUnit(c.alphaComponent)
            p.tintAlphaMin *= a
            p.tintAlphaMax *= a
        }

        return p
    }

    private var appearanceObserver: Any?

    private func installAppearanceObserverIfNeeded() {
        guard appearanceObserver == nil else { return }
        appearanceObserver = NotificationCenter.default.addObserver(
            forName: .arxivAppearanceDidChange,
            object: AppearanceManager.shared,
            queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            self.updateStyle()
            self.scheduleRender(reason: "appearance")
        }
    }

    deinit {
        if let appearanceObserver {
            NotificationCenter.default.removeObserver(appearanceObserver)
        }
    }

    override func layout() {
        super.layout()
        installAppearanceObserverIfNeeded()
        layer?.cornerRadius = cornerRadius
        if #available(macOS 10.13, *) { layer?.cornerCurve = .continuous }

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        backgroundImageLayer.frame = bounds
        backgroundImageLayer.cornerRadius = cornerRadius
        if #available(macOS 10.13, *) { backgroundImageLayer.cornerCurve = .continuous }
        fillLayer.frame = bounds
        highlightLayer.frame = bounds
        shadowLayer.frame = bounds

        let outerInset = max(0.5, strokeLayer.lineWidth / 2)
        let innerInset = max(0.5, innerStrokeLayer.lineWidth / 2) + 1.0
        let outerRect = bounds.insetBy(dx: outerInset, dy: outerInset)
        let innerRect = bounds.insetBy(dx: innerInset, dy: innerInset)
        let outerPath = CGPath(roundedRect: outerRect,
                               cornerWidth: cornerRadius,
                               cornerHeight: cornerRadius,
                               transform: nil)
        let innerPath = CGPath(roundedRect: innerRect,
                               cornerWidth: max(0, cornerRadius - 1.0),
                               cornerHeight: max(0, cornerRadius - 1.0),
                               transform: nil)
        rimDarkLayer.frame = bounds
        rimDarkLayer.path = outerPath
        rimDarkLayer.shadowPath = outerPath
        rimLightLayer.frame = bounds
        rimLightLayer.path = outerPath
        rimLightLayer.shadowPath = outerPath
        dispersionLayer.frame = bounds
        dispersionMask.frame = bounds
        dispersionMask.path = outerPath
        strokeLayer.frame = bounds
        strokeLayer.path = outerPath
        innerStrokeLayer.frame = bounds
        innerStrokeLayer.path = innerPath
        CATransaction.commit()

        updateStyle()
        scheduleRender(reason: "layout")
    }

    private func updateStyle() {
        let dark = AppearanceManager.shared.isDark()
        let stateScale = stateMultipliers(for: config.state)
        let thickness = max(0.7, config.thickness)
        let specular = max(0.2, min(1.6, config.specularIntensity)) * stateScale.specular
        let border = config.borderStyle
        let shadowStyle = config.shadowStyle

        // Clarity leap: keep the fill nearly invisible; let refraction + rims define the glass.
        // Optional debug instrumentation: colorize layers to isolate what is darkening the card.
        let fillBase: CGFloat = dark ? 0.010 : 0.014
        let clarity = clampUnit(config.transmission)
        let fillAlpha = max(0.0, fillBase * (1.05 - (0.80 * clarity)) * stateScale.fill)
        let fillColor = (config.tint ?? NSColor.white).usingColorSpace(.deviceRGB) ?? (config.tint ?? NSColor.white)
        let fillAlphaAdjusted = fillAlpha * clampUnit(fillColor.alphaComponent)

        let highlightTop: CGFloat = (dark ? 0.32 : 0.24) * specular
        let highlightMid: CGFloat = (dark ? 0.12 : 0.08) * specular
        let shadowBottom: CGFloat = (dark ? shadowStyle.bottomAlpha * 1.25 : shadowStyle.bottomAlpha) * stateScale.shadow

        CATransaction.begin()
        CATransaction.setDisableActions(true)

        let layerDebug = ProcessInfo.processInfo.environment["ARXIV_GLASS_LAYER_DEBUG"] == "1"
        if layerDebug {
            // Layer stack visualization:
            // - fillLayer: red
            // - highlightLayer: green
            // - shadowLayer: blue
            fillLayer.backgroundColor = NSColor.systemRed.withAlphaComponent(max(0.02, fillAlphaAdjusted * 20)).cgColor
        } else {
            fillLayer.backgroundColor = fillColor.withAlphaComponent(fillAlphaAdjusted).cgColor
        }

        if layerDebug {
            highlightLayer.colors = [
                NSColor.systemGreen.withAlphaComponent(0.50).cgColor,
                NSColor.systemGreen.withAlphaComponent(0.22).cgColor,
                NSColor.clear.cgColor
            ]
        } else {
            highlightLayer.colors = [
                NSColor.white.withAlphaComponent(highlightTop).cgColor,
                NSColor.white.withAlphaComponent(highlightMid).cgColor,
                NSColor.clear.cgColor
            ]
        }
        highlightLayer.locations = [0.0, 0.15, 1.0]

        if layerDebug {
            shadowLayer.colors = [
                NSColor.clear.cgColor,
                NSColor.systemBlue.withAlphaComponent(0.55).cgColor
            ]
        } else {
            shadowLayer.colors = [
                NSColor.clear.cgColor,
                NSColor.black.withAlphaComponent(shadowBottom).cgColor
            ]
        }
        shadowLayer.locations = [0.80, 1.0]

        // Crisp rim shadows (rounded bubble edge).
        let rimWidth = border.rimWidth * thickness
        let rimDarkAlpha = border.rimDarkAlpha * (dark ? 1.20 : 1.0) * specular
        let rimLightAlpha = border.rimLightAlpha * (dark ? 1.15 : 1.0) * specular

        rimDarkLayer.lineWidth = rimWidth
        rimDarkLayer.strokeColor = NSColor.black.withAlphaComponent(rimDarkAlpha).cgColor
        rimDarkLayer.shadowColor = NSColor.black.cgColor
        rimDarkLayer.shadowOpacity = shadowStyle.rimOpacity * (dark ? 1.35 : 1.0) * Float(stateScale.shadow)
        rimDarkLayer.shadowRadius = shadowStyle.rimRadius * thickness
        rimDarkLayer.shadowOffset = CGSize(width: shadowStyle.rimOffset.width,
                                           height: -abs(shadowStyle.rimOffset.height))

        rimLightLayer.lineWidth = rimWidth + (0.2 * thickness)
        rimLightLayer.strokeColor = NSColor.white.withAlphaComponent(rimLightAlpha).cgColor
        rimLightLayer.shadowColor = NSColor.white.cgColor
        rimLightLayer.shadowOpacity = shadowStyle.rimOpacity * (dark ? 1.15 : 0.95) * Float(stateScale.shadow)
        rimLightLayer.shadowRadius = shadowStyle.rimRadius * 0.85 * thickness
        rimLightLayer.shadowOffset = CGSize(width: shadowStyle.rimOffset.width,
                                            height: abs(shadowStyle.rimOffset.height))

        // Rim dispersion (warm/cool split) - subtle and rim-only.
        let dispersionAlpha = border.dispersionAlpha * (dark ? 1.20 : 1.0) * specular
        let warm = NSColor(calibratedRed: 1.0, green: 0.86, blue: 0.72, alpha: dispersionAlpha * 1.10)
        let cool = NSColor(calibratedRed: 0.72, green: 0.88, blue: 1.0, alpha: dispersionAlpha)
        dispersionLayer.colors = [warm.cgColor, NSColor.clear.cgColor, cool.cgColor]
        dispersionLayer.locations = [0.0, 0.5, 1.0]

        // Crisp outer + inner strokes to define the edge without a hard border.
        strokeLayer.lineWidth = border.outerWidth * thickness
        strokeLayer.strokeColor = NSColor.white.withAlphaComponent(border.outerAlpha * (dark ? 1.10 : 1.0)).cgColor
        innerStrokeLayer.lineWidth = border.innerWidth * thickness
        innerStrokeLayer.strokeColor = NSColor.white.withAlphaComponent(border.innerAlpha * (dark ? 1.05 : 1.0)).cgColor

        CATransaction.commit()
    }

    func invalidateGlass(reason: String = "invalidate") {
        _ = reason
        lastRenderKey = ""
        if !freezeBackgroundSampling { frozenBackground = nil }
        scheduleRender(reason: reason)
    }

    private func scheduleRender(reason: String) {
        _ = reason
        renderWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in
            self?.renderGlassIfPossible()
        }
        renderWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.06, execute: work)
    }

    private func renderGlassIfPossible() {
        guard bounds.width >= 8, bounds.height >= 8 else { return }
        guard let window else { return }
        // Avoid doing any work before the window is visible (AppKit can crash when caching display too early).
        guard window.isVisible else { return }

        let scale = max(1.0, window.backingScaleFactor)
        let sizePx = CGSize(width: bounds.width * scale, height: bounds.height * scale)
        let cornerRadiusPx = cornerRadius * scale
        let dark = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua

        let rectInWindow = convert(bounds, to: nil)
        let key = "\(Int(sizePx.width))x\(Int(sizePx.height))@\(Int(scale * 100))_dark=\(dark)_dbg=\(glassDebugView.rawValue)"
        if key == lastRenderKey, backgroundImageLayer.contents != nil { return }
        lastRenderKey = key

        let paramsPx = glassParams.scaled(by: scale)
        maybeLogLiquidGlassParamsOnce(paramsPx: paramsPx, dark: dark, scale: scale)

        let bg: CGImage
        if freezeBackgroundSampling, let frozen = frozenBackground {
            bg = frozen
        } else if let image = backgroundProvider?(rectInWindow, scale) {
            bg = image
            if freezeBackgroundSampling { frozenBackground = image }
        } else {
            bg = solidFallbackBackground(sizePx: sizePx, dark: dark)
        }

        LiquidGlassRenderer.shared.renderAsync(
            background: bg,
            sizePx: sizePx,
            cornerRadiusPx: cornerRadiusPx,
            isDark: dark,
            parameters: paramsPx,
            debug: glassDebugView
        ) { [weak self] cg in
            guard let self else { return }
            guard let cg else { return }
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            self.backgroundImageLayer.contents = cg
            self.backgroundImageLayer.contentsScale = scale
            CATransaction.commit()
        }
    }

    private func solidFallbackBackground(sizePx: CGSize, dark: Bool) -> CGImage {
        let w = max(2, Int(sizePx.width.rounded()))
        let h = max(2, Int(sizePx.height.rounded()))
        let cs = CGColorSpaceCreateDeviceRGB()
        let bitmapInfo = CGImageAlphaInfo.premultipliedLast.rawValue
        let base = dark ? NSColor.black : NSColor.white
        let c = base.usingColorSpace(.deviceRGB) ?? base
        guard let ctx = CGContext(data: nil,
                                  width: w,
                                  height: h,
                                  bitsPerComponent: 8,
                                  bytesPerRow: w * 4,
                                  space: cs,
                                  bitmapInfo: bitmapInfo) else {
            // As a last resort, return a 2x2 black image.
            return CGImage(width: 2, height: 2, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: 8, space: cs, bitmapInfo: CGBitmapInfo(rawValue: bitmapInfo), provider: CGDataProvider(data: Data(repeating: 0, count: 16) as CFData)!, decode: nil, shouldInterpolate: false, intent: .defaultIntent)!
        }
        ctx.setFillColor(red: c.redComponent, green: c.greenComponent, blue: c.blueComponent, alpha: 1.0)
        ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
        return ctx.makeImage()!
    }

    private func maybeLogLiquidGlassParamsOnce(paramsPx: LiquidGlassRenderer.Parameters, dark: Bool, scale: CGFloat) {
        guard ProcessInfo.processInfo.environment["ARXIV_GLASS_LOG_PARAMS"] == "1" else { return }
        guard !Self.didLogLiquidGlassParams else { return }
        Self.didLogLiquidGlassParams = true
        NSLog("[LiquidGlass] scale=%.2f dark=%@ diffuse(blur=%.2fpx mix(center=%.2f edge=%.2f)) refr(scale=%.2fpx amp=%.2f baseMix=%.2f enabled=%@) tint=[%.4f,%.4f] fresnel(int=%.3f exp=%.2f corner=%.2f) sat=%.2f con=%.2f noise(op=%.4f enabled=%@)",
              scale,
              dark ? "true" : "false",
              paramsPx.diffusionBlurRadius,
              paramsPx.centerBlurMix,
              paramsPx.edgeBlurMix,
              paramsPx.refractionScale,
              paramsPx.refractionAmplitude,
              paramsPx.centerRefractionMix,
              paramsPx.enableRefraction ? "true" : "false",
              paramsPx.tintAlphaMin,
              paramsPx.tintAlphaMax,
              paramsPx.fresnelIntensity,
              paramsPx.fresnelExponent,
              paramsPx.fresnelCornerBoost,
              paramsPx.saturation,
              paramsPx.contrast,
              paramsPx.noiseOpacity,
              paramsPx.enableNoise ? "true" : "false")
    }
}

private class NoScrollTableView: NSTableView {
    override func scrollWheel(with event: NSEvent) {
        // Disable gesture-driven scrolling/panning for the publications list.
    }
}

private final class MenuTableView: NoScrollTableView {
    override func mouseDown(with event: NSEvent) {
        super.mouseDown(with: event)
        guard event.type == .leftMouseDown,
              event.clickCount == 1,
              clickedRow >= 0,
              let action = action else {
            return
        }
        NSApp.sendAction(action, to: target, from: self)
    }
}

private final class NoScrollScrollView: NSScrollView {
    override func scrollWheel(with event: NSEvent) {
        // Swallow scroll-wheel events so trackpad gestures cannot pan this scroll view.
    }
}

private protocol HitTestControlling: AnyObject {
    var allowsHitTesting: Bool { get set }
}

private final class HorizontalLockedWKWebView: WKWebView, HitTestControlling {
    var allowsHitTesting: Bool = true

    override func hitTest(_ point: NSPoint) -> NSView? {
        guard allowsHitTesting, !isHidden else { return nil }
        return super.hitTest(point)
    }

    var lockedX: CGFloat = 0

    override func scrollWheel(with event: NSEvent) {
        super.scrollWheel(with: event)
        clampHorizontalOffset()
    }

    override func layout() {
        super.layout()
        clampHorizontalOffset()
    }

    private func clampHorizontalOffset() {
        guard let scrollView = firstDescendantScrollView() else { return }
        let clip = scrollView.contentView
        var origin = clip.bounds.origin
        guard abs(origin.x - lockedX) > 0.01 else { return }
        origin.x = lockedX
        clip.setBoundsOrigin(origin)
        scrollView.reflectScrolledClipView(clip)
    }

    private func firstDescendantScrollView() -> NSScrollView? {
        func walk(_ view: NSView) -> NSScrollView? {
            if let sv = view as? NSScrollView { return sv }
            for sub in view.subviews {
                if let found = walk(sub) { return found }
            }
            return nil
        }
        return walk(self)
    }
}

private final class ZoomablePDFView: PDFView, HitTestControlling {
    var allowsHitTesting: Bool = true
    var onMagnify: ((NSEvent) -> Bool)?
    var suppressMagnifyEvents: Bool = false
    var onAnnotateRequest: ((NSPoint, PDFPage) -> Void)?

    private var lastContextMenuLocationInView: NSPoint?
    private weak var lastContextMenuPage: PDFPage?

    override var acceptsFirstResponder: Bool { true }

    private func primaryScrollView() -> NSScrollView? {
        var found: [NSScrollView] = []
        func walk(_ v: NSView) {
            if let sv = v as? NSScrollView { found.append(sv) }
            for sub in v.subviews { walk(sub) }
        }
        walk(self)
        return found.first(where: { $0.documentView != nil }) ?? found.first
    }

    private func scrollPrimary(by deltaY: CGFloat) -> Bool {
        guard let scrollView = primaryScrollView() else { return false }
        let clip = scrollView.contentView
        var origin = clip.bounds.origin
        origin.y += deltaY
        origin = clip.constrainBoundsRect(NSRect(origin: origin, size: clip.bounds.size)).origin
        clip.setBoundsOrigin(origin)
        scrollView.reflectScrolledClipView(clip)
        return true
    }

    private func scrollPrimaryToEdge(top: Bool) -> Bool {
        guard let scrollView = primaryScrollView(),
              let doc = scrollView.documentView else { return false }
        let clip = scrollView.contentView
        var origin = clip.bounds.origin
        if top {
            origin.y = doc.bounds.minY
        } else {
            origin.y = doc.bounds.maxY - clip.bounds.height
        }
        origin = clip.constrainBoundsRect(NSRect(origin: origin, size: clip.bounds.size)).origin
        clip.setBoundsOrigin(origin)
        scrollView.reflectScrolledClipView(clip)
        return true
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        guard allowsHitTesting, !isHidden else { return nil }
        return super.hitTest(point)
    }

    override func menu(for event: NSEvent) -> NSMenu? {
        let locationInView = convert(event.locationInWindow, from: nil)
        guard let page = page(for: locationInView, nearest: true) else {
            return super.menu(for: event)
        }

        let pagePoint = convert(locationInView, to: page)
        let bounds = page.bounds(for: displayBox)
        guard bounds.contains(pagePoint) else {
            return super.menu(for: event)
        }

        lastContextMenuLocationInView = locationInView
        lastContextMenuPage = page

        let menu = super.menu(for: event) ?? NSMenu()
        let annotate = NSMenuItem(title: "Annotate…", action: #selector(handleAnnotateMenuItem(_:)), keyEquivalent: "")
        annotate.target = self
        menu.insertItem(annotate, at: 0)
        return menu
    }

    override func mouseDown(with event: NSEvent) {
        // Ensure key events (e.g. Shift+Arrow selection extension) reach PDFKit.
        window?.makeFirstResponder(self)
        super.mouseDown(with: event)
    }

    @objc private func handleAnnotateMenuItem(_ sender: NSMenuItem) {
        guard let location = lastContextMenuLocationInView, let page = lastContextMenuPage else { return }
        onAnnotateRequest?(location, page)
        lastContextMenuLocationInView = nil
        lastContextMenuPage = nil
    }

    override func scrollWheel(with event: NSEvent) {
        // If PDFKit's internal scroll view didn't win hit-testing for some reason, forward wheel
        // events so the document remains scrollable.
        if let sv = primaryScrollView() {
            sv.scrollWheel(with: event)
            return
        }
        super.scrollWheel(with: event)
    }

    override func keyDown(with event: NSEvent) {
        // Provide deterministic keyboard scrolling (arrow keys / page up/down / space).
        // This avoids relying on PDFKit's responder chain, which can be inconsistent across macOS.
        // But PDFKit uses Shift+Arrow for text selection extension; let it handle that.
        if event.modifierFlags.contains(.shift) {
            switch event.keyCode {
            case 123, 124, 125, 126: // left, right, down, up
                super.keyDown(with: event)
                return
            default:
                break
            }
        }
        guard let scrollView = primaryScrollView() else {
            super.keyDown(with: event)
            return
        }

        let shift = event.modifierFlags.contains(.shift)
        let line = max(8, scrollView.verticalLineScroll)
        let page = max(40, scrollView.verticalPageScroll)

        switch event.keyCode {
        case 126: // up
            if scrollPrimary(by: line) { return }
        case 125: // down
            if scrollPrimary(by: -line) { return }
        case 116: // page up
            if scrollPrimary(by: page) { return }
        case 121: // page down
            if scrollPrimary(by: -page) { return }
        case 49: // space
            if scrollPrimary(by: (shift ? page : -page)) { return }
        case 115: // home
            if scrollPrimaryToEdge(top: true) { return }
        case 119: // end
            if scrollPrimaryToEdge(top: false) { return }
        default:
            break
        }

        super.keyDown(with: event)
    }

    override func magnify(with event: NSEvent) {
        if suppressMagnifyEvents {
            return
        }
        if onMagnify?(event) == true {
            return
        }
        super.magnify(with: event)
    }

    func routeScrollWheel(_ event: NSEvent) -> Bool {
        if let sv = primaryScrollView() {
            sv.scrollWheel(with: event)
            return true
        }
        return false
    }
}

private final class HorizontalLockClipView: NSClipView {
    var lockedX: CGFloat = 0
    var locksHorizontal: Bool = true
    var clampsVertical: Bool = false
    private let preservesFlipped: Bool

    init(frame frameRect: NSRect, flipped: Bool) {
        self.preservesFlipped = flipped
        super.init(frame: frameRect)
    }

    required init?(coder: NSCoder) { fatalError() }

    override var isFlipped: Bool { preservesFlipped }

    override func constrainBoundsRect(_ proposedBounds: NSRect) -> NSRect {
        var rect = super.constrainBoundsRect(proposedBounds)
        if locksHorizontal {
            rect.origin.x = lockedX
        }
        if clampsVertical, let doc = documentView {
            let docFrame = doc.frame
            let minY = docFrame.minY
            let maxY = max(minY, docFrame.maxY - rect.height)
            rect.origin.y = max(minY, min(maxY, rect.origin.y))
        }
        return rect
    }

    override func scroll(to newOrigin: NSPoint) {
        let proposedX = locksHorizontal ? lockedX : newOrigin.x
        let proposed = NSRect(origin: NSPoint(x: proposedX, y: newOrigin.y), size: bounds.size)
        let constrained = constrainBoundsRect(proposed)
        super.scroll(to: constrained.origin)
    }
}

private struct AnnotationContext {
    let viewPointInView: NSPoint
    let viewPointInHost: NSPoint
    let page: PDFPage
    let pagePoint: NSPoint
    let selection: PDFSelection?
    let existingAnnotation: PDFAnnotation?
}

private final class AnnotationTextView: NSTextView {
    var onSubmit: (() -> Void)?
    var onCancel: (() -> Void)?

    override func keyDown(with event: NSEvent) {
        let isReturn = (event.keyCode == 36 || event.keyCode == 76)
        if isReturn && !event.modifierFlags.contains(.shift) {
            onSubmit?()
            return
        }
        if event.keyCode == 53 { // esc
            onCancel?()
            return
        }
        super.keyDown(with: event)
    }
}

private final class AnnotationComposerViewController: NSViewController {
    var onSubmit: ((String, NSColor) -> Void)?
    var onCancel: (() -> Void)?
    var initialText: String = ""
    var initialColor: NSColor = .systemYellow
    var dropdownGlassFactory: (() -> GlassCardView)?

    private let textView = AnnotationTextView()
    private var colorButtons: [NSButton] = []
    private var selectedColor: NSColor = .systemYellow

    private func paletteColors() -> [NSColor] {
        // Use the app accent as the palette seed to avoid reaching into the picker controller here.
        let base = NSColor.controlAccentColor.usingColorSpace(.deviceRGB) ?? NSColor.controlAccentColor
        func mix(_ other: NSColor, t: CGFloat) -> NSColor {
            let a = base
            let b = other.usingColorSpace(.deviceRGB) ?? other
            let r = a.redComponent + (b.redComponent - a.redComponent) * t
            let g = a.greenComponent + (b.greenComponent - a.greenComponent) * t
            let b2 = a.blueComponent + (b.blueComponent - a.blueComponent) * t
            return NSColor(calibratedRed: r, green: g, blue: b2, alpha: a.alphaComponent)
        }
        let lighter = mix(.white, t: 0.35)
        let darker = mix(.black, t: 0.2)
        let muted = mix(NSColor.systemGray, t: 0.25)
        let warm = mix(NSColor.systemOrange, t: 0.3)
        return [base, lighter, darker, muted, warm]
    }

    override func loadView() {
        let glass = dropdownGlassFactory?() ?? AnnotationComposerViewController.makeFallbackDropdownGlass()
        glass.translatesAutoresizingMaskIntoConstraints = false
        glass.wantsLayer = true
        glass.layer?.masksToBounds = true
        if #available(macOS 10.13, *) {
            glass.layer?.cornerCurve = .continuous
        }

        let content = NSView()
        content.translatesAutoresizingMaskIntoConstraints = false
        glass.addSubview(content)
        content.leadingAnchor.constraint(equalTo: glass.leadingAnchor, constant: 12).isActive = true
        content.trailingAnchor.constraint(equalTo: glass.trailingAnchor, constant: -12).isActive = true
        content.topAnchor.constraint(equalTo: glass.topAnchor, constant: 12).isActive = true
        content.bottomAnchor.constraint(equalTo: glass.bottomAnchor, constant: -12).isActive = true

        let colorStack = NSStackView()
        colorStack.orientation = .horizontal
        colorStack.alignment = .centerY
        colorStack.spacing = 8
        colorStack.translatesAutoresizingMaskIntoConstraints = false

        for color in paletteColors() {
            let button = NSButton()
            button.bezelStyle = .shadowlessSquare
            button.isBordered = false
            button.wantsLayer = true
            button.title = ""
            button.layer?.cornerRadius = 9
            button.layer?.borderWidth = 0
            button.layer?.borderColor = nil
            button.layer?.backgroundColor = color.cgColor
            button.layer?.shadowColor = color.withAlphaComponent(0.7).cgColor
            button.layer?.shadowOpacity = 0.2
            button.layer?.shadowRadius = 4
            button.setButtonType(.momentaryChange)
            button.target = self
            button.action = #selector(onSelectColor(_:))
            button.widthAnchor.constraint(equalToConstant: 30).isActive = true
            button.heightAnchor.constraint(equalToConstant: 18).isActive = true
            colorStack.addArrangedSubview(button)
            colorButtons.append(button)
        }

        let scroll = NSScrollView()
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.borderType = .noBorder
        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = false
        scroll.drawsBackground = false

        textView.translatesAutoresizingMaskIntoConstraints = false
        textView.isEditable = true
        textView.isRichText = false
        textView.font = NSFont.systemFont(ofSize: 13)
        textView.textColor = .labelColor
        textView.backgroundColor = .clear
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.textContainerInset = NSSize(width: 4, height: 4)
        textView.textContainer?.widthTracksTextView = true
        textView.onSubmit = { [weak self] in self?.submit() }
        textView.onCancel = { [weak self] in self?.cancel() }

        scroll.documentView = textView
        scroll.contentView.postsBoundsChangedNotifications = true

        // Keep the text view fully visible and match the scroll width so typing is shown.
        NSLayoutConstraint.activate([
            textView.leadingAnchor.constraint(equalTo: scroll.contentView.leadingAnchor),
            textView.trailingAnchor.constraint(equalTo: scroll.contentView.trailingAnchor),
            textView.topAnchor.constraint(equalTo: scroll.contentView.topAnchor),
            textView.bottomAnchor.constraint(equalTo: scroll.contentView.bottomAnchor),
            textView.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor)
        ])

        content.addSubview(colorStack)
        content.addSubview(scroll)

        colorStack.centerXAnchor.constraint(equalTo: content.centerXAnchor).isActive = true
        colorStack.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -12).isActive = true

        scroll.leadingAnchor.constraint(equalTo: content.leadingAnchor).isActive = true
        scroll.trailingAnchor.constraint(equalTo: content.trailingAnchor).isActive = true
        scroll.topAnchor.constraint(equalTo: content.topAnchor).isActive = true
        scroll.bottomAnchor.constraint(equalTo: colorStack.topAnchor, constant: -12).isActive = true
        scroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 120).isActive = true

        view = glass
        preferredContentSize = NSSize(width: 400, height: 250)
    }

    static func makeFallbackDropdownGlass() -> GlassCardView {
        var config = GlassCardKit.GlassCardConfig()
        config.transmission = DROPDOWN_GLASS_TRANSMISSION
        config.diffusionAmount = DROPDOWN_GLASS_DIFFUSION_AMOUNT
        config.cornerRadius = 12
        config.tint = NSColor(white: 1.0, alpha: max(0.0, min(1.0, PANEL_CLEAR_GLASS_TINT_ALPHA)))
        let card = GlassCardKit.makeGlassCard(config: config) { _, _ in nil }
        card.translatesAutoresizingMaskIntoConstraints = true
        card.wantsLayer = true
        if #available(macOS 10.13, *) {
            card.layer?.cornerCurve = .continuous
        }
        return card
    }

    override func viewDidAppear() {
        super.viewDidAppear()
        selectedColor = initialColor
        textView.string = initialText
        updateColorSelection()
        view.window?.makeFirstResponder(textView)
    }

    @objc private func onSelectColor(_ sender: NSButton) {
        let palette = paletteColors()
        guard let idx = colorButtons.firstIndex(of: sender), idx < palette.count else { return }
        selectedColor = palette[idx]
        updateColorSelection()
    }

    private func updateColorSelection() {
        let palette = paletteColors()
        for (idx, button) in colorButtons.enumerated() where idx < palette.count {
            let base = palette[idx].usingColorSpace(.deviceRGB)
            let target = selectedColor.usingColorSpace(.deviceRGB)
            let isSelected = {
                guard let base, let target else { return false }
                return abs(base.redComponent - target.redComponent) < 0.001 &&
                       abs(base.greenComponent - target.greenComponent) < 0.001 &&
                       abs(base.blueComponent - target.blueComponent) < 0.001 &&
                       abs(base.alphaComponent - target.alphaComponent) < 0.001
            }()
            if let layer = button.layer {
                layer.cornerRadius = layer.bounds.height / 2
                layer.shadowOpacity = isSelected ? 0.32 : 0.12
                layer.shadowRadius = isSelected ? 5 : 3
            }
        }
    }

    private func submit() {
        onSubmit?(textView.string, selectedColor)
    }

    private func cancel() {
        onCancel?()
    }
}

private final class AnnotationIconOverlayView: NSView {
    struct Icon {
        let annotation: PDFAnnotation
        let frame: CGRect
        let color: NSColor
    }

    var icons: [Icon] = [] {
        didSet { needsDisplay = true }
    }

    var onIconTapped: ((PDFAnnotation) -> Void)?

    override var isOpaque: Bool { false }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
    }

    required init?(coder: NSCoder) { fatalError() }

    override func hitTest(_ point: NSPoint) -> NSView? {
        if icons.contains(where: { $0.frame.contains(point) }) {
            return self
        }
        return nil
    }

    override func mouseUp(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        guard let icon = icons.first(where: { $0.frame.contains(p) }) else { return }
        onIconTapped?(icon.annotation)
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }
        for icon in icons {
            let rect = icon.frame
            let path = NSBezierPath(ovalIn: rect)
            icon.color.setFill()
            path.fill()
            ctx.setLineWidth(1)
            NSColor.black.withAlphaComponent(0.25).setStroke()
            path.stroke()
        }
    }
}

private final class PDFAnnotationCoordinator: NSObject, NSPopoverDelegate {
    private weak var pdfView: PDFView?
    private weak var hostView: NSView?
    private let overlay = AnnotationIconOverlayView(frame: .zero)
    private var overlayConstraints: [NSLayoutConstraint] = []
    private var composerPopover: NSPopover?
    private var readOnlyPopover: NSPopover?
    private var readOnlyPopoverAnnotation: PDFAnnotation?
    private var observers: [NSObjectProtocol] = []
    private var scrollObserver: NSObjectProtocol?
    private var currentContext: AnnotationContext?
    private let dropdownGlassFactory: () -> GlassCardView

    private let noteGroupKey = PDFAnnotationKey(rawValue: "NoteGroupID")

    private let noteSize = CGSize(width: 24, height: 24)

    init(pdfView: PDFView, hostView: NSView, dropdownGlassFactory: @escaping () -> GlassCardView) {
        self.pdfView = pdfView
        self.hostView = hostView
        self.dropdownGlassFactory = dropdownGlassFactory
        super.init()
        attachOverlay()
        installObservers()
        refreshIcons()
    }

    deinit {
        removeObservers()
    }

    func beginAnnotation(at viewPoint: NSPoint, page: PDFPage) {
        guard let pdfView, let host = hostView else { return }
        let pagePoint = pdfView.convert(viewPoint, to: page)
        let crop = page.bounds(for: pdfView.displayBox)
        guard crop.contains(pagePoint) else { return }

        // Always prefer the user's current selection, even if the click is slightly outside.
        let selection = selectionForAnnotation(in: pdfView, page: page, pagePoint: pagePoint)
        let context = AnnotationContext(
            viewPointInView: viewPoint,
            viewPointInHost: pdfView.convert(viewPoint, to: host),
            page: page,
            pagePoint: pagePoint,
            selection: selection,
            existingAnnotation: nil
        )
        currentContext = context
        presentComposer(context: context)
    }

    func refreshIcons() {
        guard let pdfView, let host = hostView else { return }
        pdfView.layoutSubtreeIfNeeded()
        host.layoutSubtreeIfNeeded()
        guard let doc = pdfView.document else {
            overlay.icons = []
            return
        }

        var icons: [AnnotationIconOverlayView.Icon] = []
        for pageIndex in 0..<doc.pageCount {
            guard let page = doc.page(at: pageIndex) else { continue }
            for ann in page.annotations where ann.type == PDFAnnotationSubtype.text.rawValue {
                let rectInView = pdfView.convert(ann.bounds, from: page)
                let rectInOverlay = overlay.convert(rectInView, from: pdfView)
                let color = ann.color ?? NSColor.systemYellow
                icons.append(.init(annotation: ann, frame: rectInOverlay, color: color))
            }
        }
        overlay.icons = icons
    }

    private func attachOverlay() {
        guard let pdfView, let host = hostView else { return }
        overlay.translatesAutoresizingMaskIntoConstraints = false
        overlay.onIconTapped = { [weak self] ann in
            self?.presentComposer(for: ann)
        }
        host.addSubview(overlay)
        overlayConstraints = [
            overlay.leadingAnchor.constraint(equalTo: pdfView.leadingAnchor),
            overlay.trailingAnchor.constraint(equalTo: pdfView.trailingAnchor),
            overlay.topAnchor.constraint(equalTo: pdfView.topAnchor),
            overlay.bottomAnchor.constraint(equalTo: pdfView.bottomAnchor)
        ]
        NSLayoutConstraint.activate(overlayConstraints)
    }

    private func installObservers() {
        guard let pdfView else { return }
        let center = NotificationCenter.default
        observers.append(center.addObserver(forName: .PDFViewScaleChanged, object: pdfView, queue: .main) { [weak self] _ in
            self?.refreshIcons()
        })
        observers.append(center.addObserver(forName: .PDFViewPageChanged, object: pdfView, queue: .main) { [weak self] _ in
            self?.refreshIcons()
        })
        observers.append(center.addObserver(forName: .PDFViewDocumentChanged, object: pdfView, queue: .main) { [weak self] _ in
            self?.refreshIcons()
        })

        if let scrollView = primaryScrollView(in: pdfView) {
            scrollView.contentView.postsBoundsChangedNotifications = true
            scrollObserver = center.addObserver(forName: NSView.boundsDidChangeNotification,
                                                object: scrollView.contentView,
                                                queue: .main) { [weak self] _ in
                self?.refreshIcons()
            }
        }
    }

    private func removeObservers() {
        let center = NotificationCenter.default
        for obs in observers { center.removeObserver(obs) }
        if let scrollObserver { center.removeObserver(scrollObserver) }
        observers.removeAll()
        scrollObserver = nil
    }

    private func noteGroupID(for annotation: PDFAnnotation) -> String? {
        annotation.value(forAnnotationKey: noteGroupKey) as? String
    }

    private func assignGroupID(_ id: String, to annotation: PDFAnnotation) {
        annotation.setValue(id, forAnnotationKey: noteGroupKey)
    }

    private func highlightColor(for tagColor: NSColor) -> NSColor {
        // Slightly higher alpha so highlights remain visible after submitting the composer.
        tagColor.withAlphaComponent(0.45)
    }

    private func existingGroupID(for selection: PDFSelection, on page: PDFPage) -> String? {
        let selBounds = selection.bounds(for: page)

        // Prefer highlights that already overlap the selection and carry a group id.
        for ann in page.annotations where ann.type == PDFAnnotationSubtype.highlight.rawValue {
            let overlap = ann.bounds.intersection(selBounds)
            guard overlap.width > 0, overlap.height > 0 else { continue }
            if let gid = noteGroupID(for: ann) { return gid }
        }

        // Fall back to nearby text notes that likely belong to this selection.
        for ann in page.annotations where ann.type == PDFAnnotationSubtype.text.rawValue {
            guard let gid = noteGroupID(for: ann) else { continue }
            let expanded = selBounds.insetBy(dx: -80, dy: -32)
            if expanded.intersects(ann.bounds) { return gid }
        }

        return nil
    }

    private func noteForGroup(_ groupID: String, on page: PDFPage) -> PDFAnnotation? {
        for ann in page.annotations where ann.type == PDFAnnotationSubtype.text.rawValue {
            if noteGroupID(for: ann) == groupID { return ann }
        }
        return nil
    }

    private func noteNearSelection(_ selection: PDFSelection, on page: PDFPage) -> PDFAnnotation? {
        let selBounds = selection.bounds(for: page)
        let expanded = selBounds.insetBy(dx: -80, dy: -32)
        for ann in page.annotations where ann.type == PDFAnnotationSubtype.text.rawValue {
            if expanded.intersects(ann.bounds) { return ann }
        }
        return nil
    }

    private func highlightsMatching(selection: PDFSelection?, page: PDFPage, groupID: String?) -> [PDFAnnotation] {
        let selBounds = selection.map { $0.bounds(for: page) }
        return page.annotations.compactMap { ann in
            guard ann.type == PDFAnnotationSubtype.highlight.rawValue else { return nil }
            if let gid = groupID, let annGid = noteGroupID(for: ann), annGid == gid {
                return ann
            }
            if let selBounds {
                let overlap = ann.bounds.intersection(selBounds)
                let overlapArea = overlap.width * overlap.height
                let selArea = selBounds.width * selBounds.height
                if overlap.width > 0, overlap.height > 0, selArea > 0, overlapArea / selArea >= 0.2 {
                    return ann
                }
            }
            return nil
        }
    }

    private func recolorHighlights(groupID: String, page: PDFPage, color: NSColor, selection: PDFSelection?) {
        let matches = highlightsMatching(selection: selection, page: page, groupID: groupID)
        for highlight in matches {
            assignGroupID(groupID, to: highlight)
            highlight.color = highlightColor(for: color)
        }
    }

    private func primaryScrollView(in view: NSView) -> NSScrollView? {
        var out: NSScrollView?
        func walk(_ v: NSView) {
            if let sv = v as? NSScrollView { out = sv; return }
            for sub in v.subviews where out == nil { walk(sub) }
        }
        walk(view)
        return out
    }

    private func presentComposer(context: AnnotationContext) {
        guard composerPopover == nil else { return }
        let vc = AnnotationComposerViewController()
        vc.initialText = context.existingAnnotation?.contents ?? ""
        if let existingColor = context.existingAnnotation?.color { vc.initialColor = existingColor }
        vc.dropdownGlassFactory = dropdownGlassFactory
        let pop = NSPopover()
        pop.contentViewController = vc
        pop.behavior = .transient
        pop.animates = true
        pop.delegate = self
        composerPopover = pop

        vc.onSubmit = { [weak self] text, color in
            self?.composerPopover?.close()
            self?.composerPopover = nil
            self?.commitAnnotation(text: text, color: color, context: context)
        }

        vc.onCancel = { [weak self] in
            self?.composerPopover?.close()
            self?.composerPopover = nil
        }

        if let host = hostView, let pdfView {
            func clamped(_ rect: NSRect, in bounds: NSRect, inset: CGFloat = 8) -> NSRect {
                let ib = bounds.insetBy(dx: inset, dy: inset)
                var r = rect
                r.origin.x = min(max(ib.minX, r.origin.x), ib.maxX - max(1, r.width))
                r.origin.y = min(max(ib.minY, r.origin.y), ib.maxY - max(1, r.height))
                return r
            }

            let anchorRect: NSRect
            if let selection = context.selection {
                var selectionRect = selection.bounds(for: context.page)
                if selectionRect.height < 2 { selectionRect.size.height = 12 }
                let inView = pdfView.convert(selectionRect, from: context.page)
                let inHost = pdfView.convert(inView, to: host)
                anchorRect = clamped(inHost, in: host.bounds)
            } else {
                let pointRect = NSRect(origin: context.viewPointInHost, size: NSSize(width: 1, height: 1))
                anchorRect = clamped(pointRect, in: host.bounds)
            }

            pop.show(relativeTo: anchorRect, of: host, preferredEdge: .maxY)
        }
    }

    func popoverDidClose(_ notification: Notification) {
        composerPopover = nil
    }

    private func selectionForAnnotation(in pdfView: PDFView, page: PDFPage, pagePoint: NSPoint) -> PDFSelection? {
        guard let sel = pdfView.currentSelection else { return nil }
        let trimmed = sel.string?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !trimmed.isEmpty else { return nil }
        let pages = sel.pages ?? []
        guard pages.contains(page) else { return nil }

        // If the click is near the selection, use it; otherwise still honor the current selection to avoid losing the highlight on submit.
        let bounds = sel.bounds(for: page)
        let padded = bounds.insetBy(dx: -12, dy: -12)
        if padded.contains(pagePoint) {
            return sel
        }

        return sel
    }

    private func commitAnnotation(text: String, color: NSColor, context: AnnotationContext) {
        guard let pdfView, let doc = pdfView.document else { return }
        let page = context.page
        if let selection = context.selection {
            let groupID = existingGroupID(for: selection, on: page)
                ?? context.existingAnnotation.flatMap { noteGroupID(for: $0) }
                ?? UUID().uuidString

            let pieces = selection.selectionsByLine() ?? [selection]
            let existingHighlights = highlightsMatching(selection: selection, page: page, groupID: groupID)
            if existingHighlights.isEmpty {
                for piece in pieces {
                    guard (piece.pages ?? []).contains(page) else { continue }
                    let bounds = piece.bounds(for: page)
                    guard bounds.width > 0, bounds.height > 0 else { continue }
                    let highlight = PDFAnnotation(bounds: bounds, forType: .highlight, withProperties: nil)
                    highlight.color = highlightColor(for: color)
                    assignGroupID(groupID, to: highlight)
                    page.addAnnotation(highlight)
                }
            } else {
                for highlight in existingHighlights {
                    assignGroupID(groupID, to: highlight)
                    highlight.color = highlightColor(for: color)
                }
            }

            let selBounds = selection.bounds(for: page)
            let note = noteForGroup(groupID, on: page)
                ?? noteNearSelection(selection, on: page)
                ?? {
                    let rect = noteRect(for: page, anchor: NSPoint(x: selBounds.minX, y: selBounds.midY), selectionBounds: selBounds)
                    let created = PDFAnnotation(bounds: rect, forType: .text, withProperties: nil)
                    page.addAnnotation(created)
                    return created
                }()
            assignGroupID(groupID, to: note)
            note.contents = text
            note.color = color
            note.userName = NSFullUserName()
        } else if let existing = context.existingAnnotation {
            let groupID = noteGroupID(for: existing) ?? UUID().uuidString
            assignGroupID(groupID, to: existing)
            existing.contents = text
            existing.color = color
            recolorHighlights(groupID: groupID, page: page, color: color, selection: context.selection)
        } else {
            let groupID = UUID().uuidString
            let noteRect = noteRect(for: page, anchor: context.pagePoint, selectionBounds: nil)
            let note = PDFAnnotation(bounds: noteRect, forType: .text, withProperties: nil)
            assignGroupID(groupID, to: note)
            note.contents = text
            note.color = color
            note.userName = NSFullUserName()
            page.addAnnotation(note)
        }

        persistAndReload(document: doc, focusPage: page)
        refreshIcons()
    }

    private func noteRect(for page: PDFPage, anchor: NSPoint, selectionBounds: CGRect?) -> CGRect {
        let crop = page.bounds(for: .cropBox)
        var size = noteSize
        size.width = max(size.width, 18)
        size.height = max(size.height, 18)

        var origin = anchor
        if let selectionBounds {
            // Place to the left of the selection start, vertically centered on the selection.
            origin = NSPoint(x: selectionBounds.minX - size.width - 4, y: selectionBounds.midY - (size.height / 2))
        } else {
            origin.y -= size.height / 2
        }

        origin.x = min(max(crop.minX, origin.x), crop.maxX - size.width)
        origin.y = min(max(crop.minY, origin.y), crop.maxY - size.height)
        return CGRect(origin: origin, size: size)
    }

    private func persistAndReload(document: PDFDocument, focusPage: PDFPage) {
        guard let pdfView else { return }
        let currentScale = pdfView.scaleFactor
        let focusIndex = document.index(for: focusPage)
        let targetURL = writableURL(for: document)

        guard let targetURL else { return }
        let tmp = targetURL.deletingLastPathComponent().appendingPathComponent(".tmp-\(UUID().uuidString)-\(targetURL.lastPathComponent)")

        if document.write(to: tmp) {
            do {
                if FileManager.default.fileExists(atPath: targetURL.path) {
                    _ = try FileManager.default.replaceItemAt(targetURL, withItemAt: tmp)
                } else {
                    try FileManager.default.moveItem(at: tmp, to: targetURL)
                }
            } catch {
                try? FileManager.default.removeItem(at: tmp)
            }
        } else {
            try? FileManager.default.removeItem(at: tmp)
        }

        guard let reloaded = PDFDocument(url: targetURL) else {
            refreshIcons()
            return
        }

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        pdfView.document = reloaded
        CATransaction.commit()
        if focusIndex != NSNotFound, focusIndex >= 0, let page = reloaded.page(at: focusIndex) {
            pdfView.go(to: page)
        }
        pdfView.scaleFactor = currentScale
        refreshIcons()
    }

    private func writableURL(for document: PDFDocument) -> URL? {
        if let url = document.documentURL, url.isFileURL, FileManager.default.isWritableFile(atPath: url.path) {
            return url
        }
        let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        let targetName = document.documentURL?.lastPathComponent ?? "annotated.pdf"
        if let caches {
            try? FileManager.default.createDirectory(at: caches, withIntermediateDirectories: true)
            return caches.appendingPathComponent("annotated_" + targetName)
        }
        return nil
    }

    private func presentComposer(for annotation: PDFAnnotation) {
        guard let page = annotation.page, let pdfView, let host = hostView else { return }
        let pointInView = pdfView.convert(annotation.bounds.origin, from: page)
        let context = AnnotationContext(
            viewPointInView: pointInView,
            viewPointInHost: pdfView.convert(pointInView, to: host),
            page: page,
            pagePoint: annotation.bounds.origin,
            selection: nil,
            existingAnnotation: annotation
        )
        presentComposer(context: context)
    }

    private func showAnnotationPopover(for annotation: PDFAnnotation) {
        presentComposer(for: annotation)
    }

    @objc private func handleEditButton(_ sender: NSButton) {
        guard let ann = readOnlyPopoverAnnotation,
              let page = ann.page,
              let pdfView,
              let host = hostView else { return }
        readOnlyPopover?.close()
        readOnlyPopover = nil
        readOnlyPopoverAnnotation = nil
        let pointInView = pdfView.convert(ann.bounds.origin, from: page)
        let context = AnnotationContext(
            viewPointInView: pointInView,
            viewPointInHost: pdfView.convert(pointInView, to: host),
            page: page,
            pagePoint: ann.bounds.origin,
            selection: nil,
            existingAnnotation: ann
        )
        presentComposer(context: context)
    }

    @objc private func handleDeleteButton(_ sender: NSButton) {
        guard let ann = readOnlyPopoverAnnotation,
              let page = ann.page,
              let doc = page.document else { return }
        readOnlyPopover?.close()
        readOnlyPopover = nil
        readOnlyPopoverAnnotation = nil
        page.removeAnnotation(ann)
        persistAndReload(document: doc, focusPage: page)
        refreshIcons()
    }
}

private final class HorizontalScrollLock {
    private weak var scrollView: NSScrollView?
    private var observer: NSObjectProtocol?
    private weak var observedContentView: NSView?
    private var isAdjusting: Bool = false
    private var lockedX: CGFloat
    private var clampVertical: Bool
    private var swapClipView: Bool

            init(scrollView: NSScrollView, lockedX: CGFloat, clampVertical: Bool = false, swapClipView: Bool = true) {
		        self.scrollView = scrollView
		        self.lockedX = lockedX
		        self.clampVertical = clampVertical
                self.swapClipView = swapClipView

                applyScrollViewPolicy(scrollView)
                if swapClipView {
                    installLockingClipViewIfPossible(on: scrollView)
                }
		        ensureObserver(on: scrollView.contentView)

	        clampIfNeeded()
	    }

	    deinit {
	        if let observer { NotificationCenter.default.removeObserver(observer) }
	    }

	    func updateLockedX(_ x: CGFloat, clamp: Bool = true) {
	        lockedX = x
	        if let clip = scrollView?.contentView as? HorizontalLockClipView {
	            clip.lockedX = x
	        }
	        if clamp { clampIfNeeded() }
	    }

        func setLocksHorizontal(_ enabled: Bool) {
            if let clip = scrollView?.contentView as? HorizontalLockClipView {
                clip.locksHorizontal = enabled
            }
        }

		    private func installLockingClipViewIfPossible(on scrollView: NSScrollView) {
		        let oldClip = scrollView.contentView
		        if let existing = oldClip as? HorizontalLockClipView {
		            existing.lockedX = lockedX
		            existing.clampsVertical = clampVertical
		            return
		        }

		        let doc = scrollView.documentView

	        // Root cause: WebKit/PDFKit often use custom clip-view subclasses; locking must live on the
	        // clip surface itself to prevent horizontal panning during gestures (no visible snapping).
	        // Preserve the original flipped coordinate system when swapping clip views.
		        let newClip = HorizontalLockClipView(frame: oldClip.frame, flipped: oldClip.isFlipped)
		        newClip.lockedX = lockedX
		        newClip.clampsVertical = clampVertical
		        newClip.postsBoundsChangedNotifications = true
		        newClip.drawsBackground = oldClip.drawsBackground
		        newClip.backgroundColor = oldClip.backgroundColor

	        scrollView.contentView = newClip
	        if let doc { scrollView.documentView = doc }
	        scrollView.reflectScrolledClipView(newClip)
	    }

		    private func applyScrollViewPolicy(_ scrollView: NSScrollView) {
		        scrollView.hasHorizontalScroller = false
		        scrollView.horizontalScrollElasticity = .none
                // Important: when X is hard-locked via the clip view, enabling predominant-axis
                // scrolling can cause AppKit to choose horizontal-only for a gesture. Since X is
                // clamped, that results in *no movement* and makes vertical scrolling feel broken.
                scrollView.usesPredominantAxisScrolling = false
		    }

	    private func ensureObserver(on contentView: NSClipView) {
	        guard observedContentView !== contentView else { return }
	        if let observer { NotificationCenter.default.removeObserver(observer) }
	        observedContentView = contentView
	        contentView.postsBoundsChangedNotifications = true
	        observer = NotificationCenter.default.addObserver(
	            forName: NSView.boundsDidChangeNotification,
	            object: contentView,
	            queue: .main
	        ) { [weak self] _ in
	            self?.clampIfNeeded()
	        }
	    }

        // Scroll clamp notes:
        // Root cause: we were calling constrainBoundsRect() on every bounds change even when
        // clampVertical == false. PDFKit already clamps vertical bounds during momentum, so
        // double-clamping caused a feedback loop and visible top-of-scroll jitter.
        // Change: only correct X unless vertical clamping is explicitly requested.
        // Why this prevents oscillation: the native scroll view remains the single source of
        // truth for vertical bounds, so momentum can settle without competing corrections.
        //
        // Regression test plan:
        // - fast trackpad upward fling to top (repeat)
        // - slow scroll to top
        // - zoomed PDF scroll to top
        // - resize panels while at top
        // - switch PDFs and repeat
		    func clampIfNeeded() {
		        guard let scrollView else { return }
		        guard isAdjusting == false else { return }
		        applyScrollViewPolicy(scrollView)
                if swapClipView {
                    installLockingClipViewIfPossible(on: scrollView)
                }
		        ensureObserver(on: scrollView.contentView)

		        let clip = scrollView.contentView
		        let origin = clip.bounds.origin
                var target = origin
                    if let lockClip = clip as? HorizontalLockClipView {
                        if lockClip.locksHorizontal {
                            target.x = lockedX
                        }
                    } else {
                        target.x = lockedX
                    }
                if clampVertical {
                    let constrained = clip.constrainBoundsRect(NSRect(origin: origin, size: clip.bounds.size)).origin
                    target.y = constrained.y
                }
		        guard abs(target.x - origin.x) > 0.01 || abs(target.y - origin.y) > 0.01 else { return }

		        isAdjusting = true
		        clip.setBoundsOrigin(target)
		        scrollView.reflectScrolledClipView(clip)
		        isAdjusting = false
                PDFScrollDebugState.shared.noteClamp(scrollView: scrollView, origin: origin, target: target)
	    }
}

private final class PDFScrollDebugState {
    static let shared = PDFScrollDebugState()
    let enabled: Bool
    let logEnabled: Bool
    weak var targetScrollView: NSScrollView?

    var lastWheelDeltaY: CGFloat = 0
    var lastWheelPrecise: Bool = false
    var lastWheelPhase: NSEvent.Phase = []
    var lastMomentumPhase: NSEvent.Phase = []
    var lastWheelTimestamp: CFTimeInterval = 0
    var lastScrollTimestamp: CFTimeInterval = 0
    var lastClampTimestamp: CFTimeInterval = 0
    var lastClampOrigin: NSPoint = .zero
    var lastClampTarget: NSPoint = .zero
    var clampCount: Int = 0

    private var eventCounter: Int = 0
    private let maxEvents = 10
    private(set) var eventLog: [String] = []

    private init() {
        let env = ProcessInfo.processInfo.environment
        enabled = env["ARXIV_PDF_SCROLL_DEBUG"] == "1"
        logEnabled = env["ARXIV_PDF_SCROLL_DEBUG_LOG"] == "1"
    }

    func bind(scrollView: NSScrollView) {
        targetScrollView = scrollView
    }

    func noteWheel(_ event: NSEvent) {
        guard enabled else { return }
        lastWheelDeltaY = event.scrollingDeltaY
        lastWheelPrecise = event.hasPreciseScrollingDeltas
        lastWheelPhase = event.phase
        lastMomentumPhase = event.momentumPhase
        lastWheelTimestamp = CACurrentMediaTime()
        noteEvent("wheel")
        if logEnabled {
            NSLog("[PDFScrollDebug] wheel deltaY=%.2f precise=%@ phase=%@ momentum=%@",
                  lastWheelDeltaY,
                  lastWheelPrecise ? "true" : "false",
                  phaseLabel(lastWheelPhase),
                  phaseLabel(lastMomentumPhase))
        }
    }

    func noteScroll() {
        guard enabled else { return }
        lastScrollTimestamp = CACurrentMediaTime()
        noteEvent("scroll")
    }

    func noteClamp(scrollView: NSScrollView, origin: NSPoint, target: NSPoint) {
        guard enabled else { return }
        guard scrollView === targetScrollView else { return }
        lastClampTimestamp = CACurrentMediaTime()
        lastClampOrigin = origin
        lastClampTarget = target
        clampCount += 1
        noteEvent("clamp")
        if logEnabled {
            NSLog("[PDFScrollDebug] clamp origin=(%.2f,%.2f) target=(%.2f,%.2f)",
                  origin.x, origin.y, target.x, target.y)
        }
    }

    func noteFrame() {
        guard enabled else { return }
        noteEvent("frame")
    }

    private func noteEvent(_ label: String) {
        eventCounter += 1
        eventLog.append("\(eventCounter):\(label)")
        if eventLog.count > maxEvents {
            eventLog.removeFirst(eventLog.count - maxEvents)
        }
    }

    private func phaseLabel(_ phase: NSEvent.Phase) -> String {
        if phase.isEmpty { return "none" }
        var parts: [String] = []
        if phase.contains(.began) { parts.append("began") }
        if phase.contains(.changed) { parts.append("changed") }
        if phase.contains(.ended) { parts.append("ended") }
        if phase.contains(.cancelled) { parts.append("cancelled") }
        if phase.contains(.mayBegin) { parts.append("mayBegin") }
        if phase.contains(.stationary) { parts.append("stationary") }
        return parts.joined(separator: "|")
    }
}

private final class PDFScrollDebugOverlay {
    private let state = PDFScrollDebugState.shared
    private weak var scrollView: NSScrollView?
    private weak var hostView: NSView?
    private let container = PassthroughView(frame: .zero)
    private let label = NSTextField(labelWithString: "")
    private var timer: Timer?
    private var wheelMonitor: Any?
    private var scrollObserver: NSObjectProtocol?
    private var lastClampCount: Int = 0

    init(hostView: NSView, scrollView: NSScrollView) {
        self.hostView = hostView
        self.scrollView = scrollView
        state.bind(scrollView: scrollView)

        container.wantsLayer = true
        container.layer?.masksToBounds = true

        label.font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        label.textColor = .white
        label.backgroundColor = NSColor.black.withAlphaComponent(0.65)
        label.isEditable = false
        label.isSelectable = false
        label.isBezeled = false
        label.drawsBackground = true
        label.usesSingleLineMode = false
        label.lineBreakMode = .byWordWrapping
        label.maximumNumberOfLines = 0
        label.alignment = .left
        label.wantsLayer = true
        label.layer?.cornerRadius = 6
        label.layer?.masksToBounds = true

        container.addSubview(label)
        hostView.addSubview(container)
        installMonitors()
    }

    deinit {
        if let wheelMonitor { NSEvent.removeMonitor(wheelMonitor) }
        if let scrollObserver { NotificationCenter.default.removeObserver(scrollObserver) }
        timer?.invalidate()
    }

    func matches(scrollView: NSScrollView) -> Bool {
        return self.scrollView === scrollView
    }

    func setHidden(_ hidden: Bool) {
        container.isHidden = hidden
    }

    func layout(in bounds: NSRect) {
        let width: CGFloat = 340
        let height: CGFloat = 120
        let x: CGFloat = 12
        let y: CGFloat = max(12, bounds.height - height - 12)
        container.frame = NSRect(x: x, y: y, width: width, height: height)
        label.frame = container.bounds
    }

    private func installMonitors() {
        guard state.enabled else { return }
        if let clip = scrollView?.contentView {
            scrollObserver = NotificationCenter.default.addObserver(
                forName: NSView.boundsDidChangeNotification,
                object: clip,
                queue: .main
            ) { [weak self] _ in
                self?.state.noteScroll()
            }
        }

        wheelMonitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { [weak self] event in
            guard let self,
                  let hostView = self.hostView,
                  event.window == hostView.window else {
                return event
            }
            let point = hostView.convert(event.locationInWindow, from: nil)
            if hostView.bounds.contains(point) {
                self.state.noteWheel(event)
            }
            return event
        }

        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            self?.tick()
        }
        timer?.tolerance = 0.01
    }

    private func tick() {
        guard state.enabled, let scrollView else { return }
        let clip = scrollView.contentView
        let doc = scrollView.documentView
        let origin = clip.bounds.origin
        let minY = doc?.bounds.minY ?? 0
        let scrollY = origin.y - minY
        let docHeight = doc?.bounds.height ?? 0
        let clipHeight = clip.bounds.height
        let maxScroll = max(0, docHeight - clipHeight)

        let now = CACurrentMediaTime()
        let lastActivity = max(state.lastWheelTimestamp,
                               max(state.lastScrollTimestamp, state.lastClampTimestamp))
        if now - lastActivity < 0.25 {
            state.noteFrame()
        }

        let clampHappened = state.clampCount != lastClampCount
        lastClampCount = state.clampCount
        let clampDeltaY = state.lastClampTarget.y - state.lastClampOrigin.y

        let deltaMode = state.lastWheelPrecise ? "px" : "line"
        let phase = phaseLabel(state.lastWheelPhase)
        let momentum = phaseLabel(state.lastMomentumPhase)
        let clampFlag = clampHappened ? "1" : "0"
        let events = state.eventLog.joined(separator: " ")

        label.stringValue = String(
            format: "scrollY=%.1f max=%.1f docH=%.1f clipH=%.1f\n" +
                    "deltaY=%.1f mode=%@ phase=%@ momentum=%@ clamp=%@\n" +
                    "clampY=%.2f originY=%.2f targetY=%.2f\n" +
                    "events: %@",
            scrollY, maxScroll, docHeight, clipHeight,
            state.lastWheelDeltaY, deltaMode, phase, momentum, clampFlag,
            clampDeltaY, state.lastClampOrigin.y, state.lastClampTarget.y,
            events
        )
    }

    private func phaseLabel(_ phase: NSEvent.Phase) -> String {
        if phase.isEmpty { return "none" }
        var parts: [String] = []
        if phase.contains(.began) { parts.append("began") }
        if phase.contains(.changed) { parts.append("changed") }
        if phase.contains(.ended) { parts.append("ended") }
        if phase.contains(.cancelled) { parts.append("cancelled") }
        if phase.contains(.mayBegin) { parts.append("mayBegin") }
        if phase.contains(.stationary) { parts.append("stationary") }
        return parts.joined(separator: "|")
    }
}

// Pass-through effect view so background glass never intercepts events.
@available(macOS 26.0, *)
private final class PassthroughGlassEffectView: NSGlassEffectView {
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
}

private final class StaticBackgroundImageView: NSView {
    private let fillImageView = NSImageView(frame: .zero)
    private let fitImageView = NSImageView(frame: .zero)
    private let overlayCropThreshold: CGFloat = 0.18
    private let fillAlphaWhenOverlay: CGFloat = 0.35
    private let snapshotColorSpace = CGColorSpaceCreateDeviceRGB()

    var baseColor: NSColor = .black {
        didSet {
            layer?.backgroundColor = baseColor.cgColor
            needsDisplay = true
        }
    }

    var image: NSImage? {
        didSet {
            fillImageView.image = image
            fitImageView.image = image
            needsLayout = true
        }
    }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = baseColor.cgColor
        layer?.masksToBounds = true
        fillImageView.animates = true
        fillImageView.imageScaling = .scaleNone
        fillImageView.imageAlignment = .alignCenter
        fillImageView.wantsLayer = true
        addSubview(fillImageView)

        fitImageView.animates = true
        fitImageView.imageScaling = .scaleNone
        fitImageView.imageAlignment = .alignCenter
        fitImageView.wantsLayer = true
        addSubview(fitImageView)
    }

    required init?(coder: NSCoder) { fatalError() }

    func updateBackingScale(_ scale: CGFloat) {
        layer?.contentsScale = scale
        fillImageView.layer?.contentsScale = scale
        fitImageView.layer?.contentsScale = scale
        needsLayout = true
    }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func layout() {
        super.layout()
        updateImageFrame()
    }

    private func updateImageFrame() {
        guard let image = fillImageView.image else {
            fillImageView.frame = bounds
            fitImageView.frame = bounds
            return
        }

        let imageSize = image.size
        let viewSize = bounds.size
        guard imageSize.width > 0,
              imageSize.height > 0,
              viewSize.width > 0,
              viewSize.height > 0 else {
            fillImageView.frame = bounds
            fitImageView.frame = bounds
            return
        }

        let fillScale = max(viewSize.width / imageSize.width, viewSize.height / imageSize.height)
        let fillSize = NSSize(width: imageSize.width * fillScale, height: imageSize.height * fillScale)
        let fillX = bounds.midX - (fillSize.width / 2)
        let fillY = bounds.midY - (fillSize.height / 2)
        fillImageView.frame = NSRect(x: fillX, y: fillY, width: fillSize.width, height: fillSize.height)

        let fitScale = min(viewSize.width / imageSize.width, viewSize.height / imageSize.height)
        let fitSize = NSSize(width: imageSize.width * fitScale, height: imageSize.height * fitScale)
        let fitX = bounds.midX - (fitSize.width / 2)
        let fitY = bounds.midY - (fitSize.height / 2)
        fitImageView.frame = NSRect(x: fitX, y: fitY, width: fitSize.width, height: fitSize.height)

        let viewArea = max(viewSize.width * viewSize.height, CGFloat(1))
        let fillArea = max(fillSize.width * fillSize.height, CGFloat(1))
        let cropRatio = max(CGFloat(0), min(CGFloat(1), CGFloat(1.0) - (viewArea / fillArea)))
        let showOverlay = cropRatio >= overlayCropThreshold

        fitImageView.isHidden = !showOverlay
        if showOverlay {
            fillImageView.alphaValue = fillAlphaWhenOverlay
            fitImageView.alphaValue = 1.0
        } else {
            fillImageView.alphaValue = 1.0
            fitImageView.alphaValue = 1.0
        }
    }

    func snapshotCGImage(in rectInSelf: CGRect, scale: CGFloat) -> CGImage? {
        // Safe region snapshot without AppKit `cacheDisplay` (which can throw exceptions early in startup).
        // We reproduce the current composite of fill+fit image views into a bitmap.
        let rect = rectInSelf.intersection(bounds)
        guard rect.width > 2, rect.height > 2 else { return nil }

        let s = max(1.0, scale)
        let pxW = max(2, Int(round(rect.width * s)))
        let pxH = max(2, Int(round(rect.height * s)))

        let bitmapInfo = CGImageAlphaInfo.premultipliedLast.rawValue
        guard let ctx = CGContext(data: nil,
                                  width: pxW,
                                  height: pxH,
                                  bitsPerComponent: 8,
                                  bytesPerRow: pxW * 4,
                                  space: snapshotColorSpace,
                                  bitmapInfo: bitmapInfo) else {
            return nil
        }
        ctx.interpolationQuality = .high

        // Map view points -> pixel space.
        ctx.scaleBy(x: s, y: s)
        ctx.translateBy(x: -rect.minX, y: -rect.minY)

        func drawImageView(_ iv: NSImageView) {
            guard let img = iv.image,
                  let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return }
            let a = max(0.0, min(1.0, iv.alphaValue))
            if a <= 0.001 { return }
            ctx.saveGState()
            ctx.setAlpha(a)
            ctx.draw(cg, in: iv.frame)
            ctx.restoreGState()
        }

        // Base fill (matches the view’s configured base background).
        let bc = (baseColor.usingColorSpace(.deviceRGB) ?? baseColor)
        ctx.setFillColor(red: bc.redComponent, green: bc.greenComponent, blue: bc.blueComponent, alpha: 1)
        ctx.fill(bounds)

        drawImageView(fillImageView)
        if !fitImageView.isHidden {
            drawImageView(fitImageView)
        }

        return ctx.makeImage()
    }
}

private final class CardEdgeGlowView: NSView {
    private let glowLayer = CAShapeLayer()
    var cornerRadius: CGFloat = PANEL_CORNER_RADIUS { didSet { needsLayout = true } }
    var glowColor: NSColor = NSColor.white { didSet { updateGlowStyle() } }
    var strokeAlpha: CGFloat = 0.32 { didSet { updateGlowStyle() } }
    var glowOpacity: Float = 0.5 { didSet { updateGlowStyle() } }
    var glowRadius: CGFloat = 18 { didSet { updateGlowStyle() } }
    var glowOffset: CGSize = .zero { didSet { updateGlowStyle() } }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.masksToBounds = false
        layer?.backgroundColor = NSColor.clear.cgColor
        glowLayer.fillColor = NSColor.clear.cgColor
        glowLayer.lineWidth = 1
        glowLayer.lineJoin = .round
        glowLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
        layer?.addSublayer(glowLayer)
        updateGlowStyle()
    }

    required init?(coder: NSCoder) { fatalError() }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func layout() {
        super.layout()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        glowLayer.frame = bounds
        let inset = max(0.5, glowLayer.lineWidth / 2)
        let rect = bounds.insetBy(dx: inset, dy: inset)
        let path = CGPath(roundedRect: rect, cornerWidth: cornerRadius, cornerHeight: cornerRadius, transform: nil)
        glowLayer.path = path
        glowLayer.shadowPath = path
        CATransaction.commit()
    }

    private func updateGlowStyle() {
        let stroke = glowColor.withAlphaComponent(strokeAlpha)
        glowLayer.strokeColor = stroke.cgColor
        glowLayer.shadowColor = glowColor.cgColor
        glowLayer.shadowOpacity = glowOpacity
        glowLayer.shadowRadius = glowRadius
        glowLayer.shadowOffset = glowOffset
    }
}

private final class CenteredSearchFieldCell: NSSearchFieldCell {
    override func searchTextRect(forBounds rect: NSRect) -> NSRect {
        var textRect = super.searchTextRect(forBounds: rect)
        let font = self.font ?? NSFont.systemFont(ofSize: NSFont.systemFontSize)
        let lineHeight = font.ascender - font.descender + font.leading
        let centeredY = rect.minY + (rect.height - lineHeight) / 2
        textRect.origin.y = centeredY
        textRect.size.height = lineHeight
        return textRect
    }

    override func titleRect(forBounds rect: NSRect) -> NSRect {
        searchTextRect(forBounds: rect)
    }

    override func drawingRect(forBounds rect: NSRect) -> NSRect {
        searchTextRect(forBounds: rect)
    }

    override func edit(withFrame rect: NSRect,
                       in controlView: NSView,
                       editor: NSText,
                       delegate: Any?,
                       event: NSEvent?) {
        let textRect = searchTextRect(forBounds: rect)
        super.edit(withFrame: textRect, in: controlView, editor: editor, delegate: delegate, event: event)
    }

    override func select(withFrame rect: NSRect,
                         in controlView: NSView,
                         editor: NSText,
                         delegate: Any?,
                         start: Int,
                         length: Int) {
        let textRect = searchTextRect(forBounds: rect)
        super.select(withFrame: textRect, in: controlView, editor: editor, delegate: delegate, start: start, length: length)
    }

    override func searchButtonRect(forBounds rect: NSRect) -> NSRect {
        var buttonRect = super.searchButtonRect(forBounds: rect)
        buttonRect.origin.y = rect.minY + (rect.height - buttonRect.height) / 2
        return buttonRect
    }

    override func cancelButtonRect(forBounds rect: NSRect) -> NSRect {
        var buttonRect = super.cancelButtonRect(forBounds: rect)
        buttonRect.origin.y = rect.minY + (rect.height - buttonRect.height) / 2
        return buttonRect
    }
}

private final class GlassSeparatorView: NSView {
    private let fillLayer = CALayer()
    private var fillColor: NSColor = NSColor.white.withAlphaComponent(0.12) {
        didSet { fillLayer.backgroundColor = fillColor.cgColor }
    }
    private var glowColor: NSColor = NSColor.white.withAlphaComponent(0.35) {
        didSet { fillLayer.shadowColor = glowColor.cgColor }
    }
    private var glowOpacity: Float = 0.35 {
        didSet { fillLayer.shadowOpacity = glowOpacity }
    }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.masksToBounds = false
        fillLayer.backgroundColor = fillColor.cgColor
        fillLayer.shadowColor = glowColor.cgColor
        fillLayer.shadowOpacity = glowOpacity
        fillLayer.shadowRadius = 3
        fillLayer.shadowOffset = .zero
        layer?.addSublayer(fillLayer)
    }

    required init?(coder: NSCoder) { fatalError() }

    override func layout() {
        super.layout()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        fillLayer.frame = bounds
        let radius = min(bounds.width, bounds.height) / 2
        fillLayer.cornerRadius = radius
        fillLayer.shadowPath = CGPath(roundedRect: bounds,
                                      cornerWidth: radius,
                                      cornerHeight: radius,
                                      transform: nil)
        CATransaction.commit()
    }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    func apply(fill: NSColor, glow: NSColor, glowOpacity: Float) {
        fillColor = fill
        glowColor = glow
        self.glowOpacity = glowOpacity
    }
}

private class GlassToolbarButton: NSButton {
    private var tracking: NSTrackingArea?
    private let hoverLayer = CALayer()
    private let haloLayer = CAShapeLayer()
    private var isHovering = false
    private var glassBackground: GlassCardView?
    var restingGlowColor: NSColor? { didSet { updateHoverState(animated: false) } }
    var restingTintColor: NSColor? { didSet { updateTint() } }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.masksToBounds = false
        layer?.backgroundColor = NSColor.clear.cgColor

        haloLayer.fillColor = NSColor.clear.cgColor
        haloLayer.strokeColor = NSColor.white.withAlphaComponent(0.30).cgColor
        haloLayer.lineWidth = 1.2
        haloLayer.opacity = 0
        haloLayer.shadowOffset = .zero
        haloLayer.shadowRadius = 14
        haloLayer.shadowOpacity = 0
        layer?.addSublayer(haloLayer)

        hoverLayer.backgroundColor = NSColor.white.withAlphaComponent(0.12).cgColor
        hoverLayer.opacity = 0
        layer?.addSublayer(hoverLayer)
        isBordered = false
        imagePosition = .imageOnly
        focusRingType = .none
        updateTint()
        updateHoverState(animated: false)
    }

    required init?(coder: NSCoder) { fatalError() }

    override func layout() {
        super.layout()
        CATransaction.begin()
        CATransaction.setDisableActions(true)

        haloLayer.frame = bounds
        let haloRadius = (layer?.cornerRadius ?? 0)
        let inset: CGFloat = 0.6
        let haloRect = haloLayer.bounds.insetBy(dx: inset, dy: inset)
        let haloCorner = max(0, haloRadius - inset)
        let haloPath = CGPath(roundedRect: haloRect,
                              cornerWidth: haloCorner,
                              cornerHeight: haloCorner,
                              transform: nil)
        haloLayer.path = haloPath
        haloLayer.shadowPath = haloPath

        hoverLayer.frame = bounds
        hoverLayer.cornerRadius = layer?.cornerRadius ?? 0
        if let radius = layer?.cornerRadius {
            layer?.shadowPath = CGPath(roundedRect: bounds,
                                       cornerWidth: radius,
                                       cornerHeight: radius,
                                       transform: nil)
        }
        if let glass = glassBackground,
           let superview = superview,
           glass.superview === superview {
            let targetFrame = frame
            let needsInvalidate = glass.frame != targetFrame
            if needsInvalidate {
                glass.frame = targetFrame
            }
            if let radius = layer?.cornerRadius, glass.cornerRadius != radius {
                glass.cornerRadius = radius
            }
            if needsInvalidate {
                glass.invalidateGlass(reason: "button_frame")
            }
	        }
	        CATransaction.commit()
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let tracking { removeTrackingArea(tracking) }
        let opts: NSTrackingArea.Options = [.mouseEnteredAndExited, .activeAlways, .inVisibleRect]
        let area = NSTrackingArea(rect: bounds, options: opts, owner: self, userInfo: nil)
        addTrackingArea(area)
        tracking = area
    }

    override func mouseEntered(with event: NSEvent) {
        isHovering = true
        updateHoverState(animated: true)
    }

    override func mouseExited(with event: NSEvent) {
        isHovering = false
        updateHoverState(animated: true)
    }

    override var isHighlighted: Bool {
        didSet { updateHoverState(animated: true) }
    }

    override var isEnabled: Bool {
        didSet {
            updateTint()
            updateHoverState(animated: false)
        }
    }

    override var alphaValue: CGFloat {
        didSet { glassBackground?.alphaValue = alphaValue }
    }

    override var isHidden: Bool {
        didSet { glassBackground?.isHidden = isHidden }
    }

    func updateTint() {
        let tint = restingTintColor ?? resolvedSystemColor(.labelColor)
        contentTintColor = isEnabled ? tint : resolvedSystemColor(.tertiaryLabelColor)
    }

    func attachLiquidGlassBackground(_ background: GlassCardView) {
        glassBackground = background
        background.alphaValue = alphaValue
        background.isHidden = isHidden
        updateGlassState()
        needsLayout = true
    }

    func invalidateLiquidGlass(reason: String = "button_state") {
        glassBackground?.invalidateGlass(reason: reason)
    }

    func setCornerRadius(_ radius: CGFloat, maskedCorners: CACornerMask? = nil) {
        layer?.cornerRadius = radius
        if let maskedCorners {
            layer?.maskedCorners = maskedCorners
        }
        glassBackground?.cornerRadius = radius
    }

    private func updateHoverState(animated: Bool) {
        let reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion || !animated
        let isActive = isEnabled && (isHovering || isHighlighted)
        let hoverTarget: Float = isHighlighted ? 0.22 : ((isHovering && isEnabled) ? 0.12 : 0.0)
        let glowColor = (restingGlowColor ?? NSColor.white).usingColorSpace(.deviceRGB) ?? NSColor.white

        let haloTargetOpacity: Float = (isHovering && isEnabled && !isHighlighted) ? 1.0 : 0.0
        let haloTargetShadowOpacity: Float = (isHovering && isEnabled && !isHighlighted) ? 0.55 : 0.0
        let haloTargetShadowRadius: CGFloat = (isHovering && isEnabled && !isHighlighted) ? 18 : 14

        let baseGlowOpacity: Float = (restingGlowColor == nil || !isEnabled) ? 0.0 : 0.28
        let targetShadowOpacity: Float = isActive ? (isHighlighted ? 0.32 : 0.22) : baseGlowOpacity
        let targetShadowRadius: CGFloat = isActive ? 6 : (restingGlowColor == nil ? 0 : 4)
        let targetShadowOffset = CGSize(width: 0, height: isActive ? -1.0 : (restingGlowColor == nil ? 0 : -0.4))
        let hoverOnly = (isHovering && isEnabled && !isHighlighted)
        let scale: CGFloat = hoverOnly ? 1.085 : (isActive ? 1.03 : 1.0)
        let lift: CGFloat = hoverOnly ? -1.6 : (isActive ? -0.8 : 0.0)
        var transform = CATransform3DIdentity
        transform = CATransform3DTranslate(transform, 0, lift, 0)
        transform = CATransform3DScale(transform, scale, scale, 1.0)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer?.shadowColor = glowColor.cgColor
        haloLayer.shadowColor = glowColor.cgColor
        haloLayer.strokeColor = glowColor.withAlphaComponent(0.35).cgColor
        CATransaction.commit()

        if reduceMotion {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            hoverLayer.opacity = hoverTarget
            layer?.transform = transform
            layer?.shadowOpacity = targetShadowOpacity
            layer?.shadowRadius = targetShadowRadius
            layer?.shadowOffset = targetShadowOffset
            haloLayer.opacity = haloTargetOpacity
            haloLayer.shadowOpacity = haloTargetShadowOpacity
            haloLayer.shadowRadius = haloTargetShadowRadius
            CATransaction.commit()
        } else {
            let preset: SpringPreset = hoverOnly ? .hoverBounce : .microBounce
            animateLayer(hoverLayer, keyPath: "opacity", to: hoverTarget, preset: preset, reduceMotion: false, basicDuration: 0.12)
            animateLayer(layer, keyPath: "transform", to: transform, preset: preset, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowOpacity", to: targetShadowOpacity, preset: preset, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowRadius", to: targetShadowRadius, preset: preset, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowOffset", to: targetShadowOffset, preset: preset, reduceMotion: false, basicDuration: 0.14)

            animateLayer(haloLayer, keyPath: "opacity", to: haloTargetOpacity, preset: preset, reduceMotion: false, basicDuration: 0.14)
            animateLayer(haloLayer, keyPath: "shadowOpacity", to: haloTargetShadowOpacity, preset: preset, reduceMotion: false, basicDuration: 0.14)
            animateLayer(haloLayer, keyPath: "shadowRadius", to: haloTargetShadowRadius, preset: preset, reduceMotion: false, basicDuration: 0.14)
        }

        updateGlassState()
    }

    private func updateGlassState() {
        guard let glass = glassBackground else { return }
        let state: GlassCardKit.State
        if !isEnabled {
            state = .disabled
        } else if isHighlighted {
            state = .pressed
        } else if isHovering {
            state = .hover
        } else {
            state = .normal
        }
        glass.updateState(state)
    }
}

// Reusable “Share button” glass border ornament stack:
// - highlight gradient
// - falloff gradient
// - inner + outer strokes
// The host decides geometry (mask/outer/inner paths) and any animation.
private final class ShareStyleOrnamentStack {
    let maskLayer = CAShapeLayer()
    let outlineLayer = CAShapeLayer()
    let innerOutlineLayer = CAShapeLayer()
    let highlightLayer = CAGradientLayer()
    let falloffLayer = CAGradientLayer()

    init() {
        maskLayer.fillColor = NSColor.black.cgColor

        outlineLayer.fillColor = NSColor.clear.cgColor
        innerOutlineLayer.fillColor = NSColor.clear.cgColor
        outlineLayer.lineJoin = .round
        outlineLayer.lineCap = .round
        innerOutlineLayer.lineJoin = .round
        innerOutlineLayer.lineCap = .round

        highlightLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
        highlightLayer.endPoint = CGPoint(x: 0.5, y: 0.0)
        falloffLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
        falloffLayer.endPoint = CGPoint(x: 0.5, y: 0.0)
    }

    func attach(to hostLayer: CALayer) {
        hostLayer.mask = maskLayer
        hostLayer.addSublayer(highlightLayer)
        hostLayer.addSublayer(falloffLayer)
        hostLayer.addSublayer(innerOutlineLayer)
        hostLayer.addSublayer(outlineLayer)
    }

    func setContentsScale(_ scale: CGFloat) {
        maskLayer.contentsScale = scale
        outlineLayer.contentsScale = scale
        innerOutlineLayer.contentsScale = scale
        highlightLayer.contentsScale = scale
        falloffLayer.contentsScale = scale
    }

    func setFrames(bounds: CGRect) {
        maskLayer.frame = bounds
        outlineLayer.frame = bounds
        innerOutlineLayer.frame = bounds
        highlightLayer.frame = bounds
        falloffLayer.frame = bounds
    }

    func applyShareStyle(enabled: Bool) {
        let borderAlpha: CGFloat = enabled ? 0.78 : 0.28
        let innerBorderAlpha: CGFloat = enabled ? 0.34 : 0.14
        let highlightTopAlpha: CGFloat = enabled ? 0.18 : 0.08
        let highlightMidAlpha: CGFloat = enabled ? 0.06 : 0.03
        let falloffAlpha: CGFloat = enabled ? 0.18 : 0.06

        outlineLayer.lineWidth = 1
        innerOutlineLayer.lineWidth = 1
        outlineLayer.strokeColor = NSColor.black.withAlphaComponent(borderAlpha).cgColor
        innerOutlineLayer.strokeColor = NSColor.black.withAlphaComponent(innerBorderAlpha).cgColor
        highlightLayer.colors = [
            NSColor.white.withAlphaComponent(highlightTopAlpha).cgColor,
            NSColor.white.withAlphaComponent(highlightMidAlpha).cgColor,
            NSColor.clear.cgColor
        ]
        falloffLayer.colors = [
            NSColor.clear.cgColor,
            NSColor.black.withAlphaComponent(falloffAlpha).cgColor
        ]
    }
}

private final class ShareStyleCapsuleOrnamentOverlayView: NSView {
    private let ornaments = ShareStyleOrnamentStack()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.masksToBounds = false
        if let host = layer {
            ornaments.attach(to: host)
        }
    }

    required init?(coder: NSCoder) { fatalError() }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        needsLayout = true
    }

    override func layout() {
        super.layout()
        updateOrnaments()
    }

    private func updateOrnaments() {
        let b = bounds
        guard b.width > 4, b.height > 4 else { return }

        let scale = max(1.0, window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0)
        let radius = b.height / 2

        let maskRect = b
        let outerRect = b.insetBy(dx: 0.5, dy: 0.5)
        let innerRect = b.insetBy(dx: 1.5, dy: 1.5)

        let maskPath = CGPath(roundedRect: maskRect,
                              cornerWidth: radius,
                              cornerHeight: radius,
                              transform: nil)
        let outerPath = CGPath(roundedRect: outerRect,
                               cornerWidth: max(0, radius - 0.5),
                               cornerHeight: max(0, radius - 0.5),
                               transform: nil)
        let innerPath = CGPath(roundedRect: innerRect,
                               cornerWidth: max(0, radius - 1.5),
                               cornerHeight: max(0, radius - 1.5),
                               transform: nil)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        ornaments.setContentsScale(scale)
        ornaments.setFrames(bounds: b)
        ornaments.applyShareStyle(enabled: true)
        ornaments.maskLayer.path = maskPath
        ornaments.outlineLayer.path = outerPath
        ornaments.innerOutlineLayer.path = innerPath
        CATransaction.commit()
    }
}

private final class ShareStyleRoundedRectOrnamentOverlayView: NSView {
    private let ornaments = ShareStyleOrnamentStack()
    var cornerRadius: CGFloat { didSet { needsLayout = true } }

    init(frame frameRect: NSRect, cornerRadius: CGFloat) {
        self.cornerRadius = cornerRadius
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.masksToBounds = false
        if let host = layer {
            ornaments.attach(to: host)
        }
    }

    convenience init(cornerRadius: CGFloat) {
        self.init(frame: .zero, cornerRadius: cornerRadius)
    }

    required init?(coder: NSCoder) { fatalError() }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        needsLayout = true
    }

    override func layout() {
        super.layout()
        updateOrnaments()
    }

    private func updateOrnaments() {
        let b = bounds
        guard b.width > 4, b.height > 4 else { return }

        let scale = max(1.0, window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0)
        let clampedRadius = max(0, min(cornerRadius, min(b.width, b.height) / 2))

        let maskRect = b
        let outerRect = b.insetBy(dx: 0.5, dy: 0.5)
        let innerRect = b.insetBy(dx: 1.5, dy: 1.5)

        let maskPath = CGPath(roundedRect: maskRect,
                              cornerWidth: clampedRadius,
                              cornerHeight: clampedRadius,
                              transform: nil)
        let outerPath = CGPath(roundedRect: outerRect,
                               cornerWidth: max(0, clampedRadius - 0.5),
                               cornerHeight: max(0, clampedRadius - 0.5),
                               transform: nil)
        let innerPath = CGPath(roundedRect: innerRect,
                               cornerWidth: max(0, clampedRadius - 1.5),
                               cornerHeight: max(0, clampedRadius - 1.5),
                               transform: nil)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        ornaments.setContentsScale(scale)
        ornaments.setFrames(bounds: b)
        ornaments.applyShareStyle(enabled: true)
        ornaments.maskLayer.path = maskPath
        ornaments.outlineLayer.path = outerPath
        ornaments.innerOutlineLayer.path = innerPath
        CATransaction.commit()
    }
}

private final class ShareToolbarButton: GlassToolbarButton {
    // Secondary action is discoverable via right-click context menu.
    var shareMenuProvider: (() -> NSMenu?)?

    private let outlineLayer = CAShapeLayer()
    private let innerOutlineLayer = CAShapeLayer()
    private let highlightLayer = CAGradientLayer()
    private let falloffLayer = CAGradientLayer()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)

        // Clip our glass highlight/falloff to the circular shape.
        layer?.masksToBounds = true

        outlineLayer.fillColor = NSColor.clear.cgColor
        innerOutlineLayer.fillColor = NSColor.clear.cgColor
        outlineLayer.lineJoin = .round
        outlineLayer.lineCap = .round
        innerOutlineLayer.lineJoin = .round
        innerOutlineLayer.lineCap = .round

        outlineLayer.lineWidth = 1
        innerOutlineLayer.lineWidth = 1

        highlightLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
        highlightLayer.endPoint = CGPoint(x: 0.5, y: 0.0)
        falloffLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
        falloffLayer.endPoint = CGPoint(x: 0.5, y: 0.0)

        let scale = max(1.0, window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0)
        outlineLayer.contentsScale = scale
        innerOutlineLayer.contentsScale = scale
        highlightLayer.contentsScale = scale
        falloffLayer.contentsScale = scale

        // Keep border on top of the hover sheen.
        layer?.addSublayer(highlightLayer)
        layer?.addSublayer(falloffLayer)
        layer?.addSublayer(innerOutlineLayer)
        layer?.addSublayer(outlineLayer)
    }

    required init?(coder: NSCoder) { fatalError() }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        needsLayout = true
    }

    override func layout() {
        // Establish the circular corner radius *before* the superclass computes
        // hover/halo/shadow geometry from `layer.cornerRadius`.
        let side = min(bounds.width, bounds.height)
        if side > 0 {
            setCornerRadius(side / 2)
        }
        super.layout()
        updateCircularGlassyOutline()
    }

    private func updateCircularGlassyOutline() {
        let bounds = self.bounds
        let side = min(bounds.width, bounds.height)
        guard side > 0 else { return }

        // Ensure circular shape even if layout ever drifts from a perfect square.
        let radius = side / 2
        setCornerRadius(radius)

        let circleBounds = NSRect(
            x: bounds.midX - side / 2,
            y: bounds.midY - side / 2,
            width: side,
            height: side
        )

        // Keep the outer rim decisively black while preserving a subtle glass highlight.
        let borderAlpha: CGFloat = isEnabled ? 0.78 : 0.28
        let innerBorderAlpha: CGFloat = isEnabled ? 0.34 : 0.14
        let highlightTopAlpha: CGFloat = isEnabled ? 0.18 : 0.08
        let highlightMidAlpha: CGFloat = isEnabled ? 0.06 : 0.03
        let falloffAlpha: CGFloat = isEnabled ? 0.18 : 0.06

        let outerRect = circleBounds.insetBy(dx: 0.5, dy: 0.5)
        let innerRect = circleBounds.insetBy(dx: 1.5, dy: 1.5)
        let outerPath = CGPath(ellipseIn: outerRect, transform: nil)
        let innerPath = CGPath(ellipseIn: innerRect, transform: nil)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        outlineLayer.frame = bounds
        innerOutlineLayer.frame = bounds
        highlightLayer.frame = circleBounds
        falloffLayer.frame = circleBounds

        outlineLayer.path = outerPath
        innerOutlineLayer.path = innerPath

        outlineLayer.strokeColor = NSColor.black.withAlphaComponent(borderAlpha).cgColor
        innerOutlineLayer.strokeColor = NSColor.black.withAlphaComponent(innerBorderAlpha).cgColor
        highlightLayer.colors = [
            NSColor.white.withAlphaComponent(highlightTopAlpha).cgColor,
            NSColor.white.withAlphaComponent(highlightMidAlpha).cgColor,
            NSColor.clear.cgColor
        ]
        falloffLayer.colors = [
            NSColor.clear.cgColor,
            NSColor.black.withAlphaComponent(falloffAlpha).cgColor
        ]
        CATransaction.commit()
    }

    override func rightMouseDown(with event: NSEvent) {
        if let menu = shareMenuProvider?() {
            NSMenu.popUpContextMenu(menu, with: event, for: self)
            return
        }
        super.rightMouseDown(with: event)
    }
}

private final class GlassToolbarMenuButton: NSButton {
    private var tracking: NSTrackingArea?
    private let hoverLayer = CALayer()
    private var isHovering = false
    var restingGlowColor: NSColor? { didSet { updateHoverState(animated: false) } }
    var restingTintColor: NSColor? { didSet { updateTint() } }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.masksToBounds = false
        layer?.backgroundColor = NSColor.clear.cgColor
        hoverLayer.backgroundColor = NSColor.white.withAlphaComponent(0.12).cgColor
        hoverLayer.opacity = 0
        layer?.addSublayer(hoverLayer)
        isBordered = false
        focusRingType = .none
        imagePosition = .imageTrailing
        alignment = .center
        updateTint()
        updateHoverState(animated: false)
    }

    required init?(coder: NSCoder) { fatalError() }

    override func layout() {
        super.layout()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        hoverLayer.frame = bounds
        hoverLayer.cornerRadius = layer?.cornerRadius ?? 0
        if let radius = layer?.cornerRadius {
            layer?.shadowPath = CGPath(roundedRect: bounds,
                                       cornerWidth: radius,
                                       cornerHeight: radius,
                                       transform: nil)
	        }
	        CATransaction.commit()
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let tracking { removeTrackingArea(tracking) }
        let opts: NSTrackingArea.Options = [.mouseEnteredAndExited, .activeAlways, .inVisibleRect]
        let area = NSTrackingArea(rect: bounds, options: opts, owner: self, userInfo: nil)
        addTrackingArea(area)
        tracking = area
    }

    override func mouseEntered(with event: NSEvent) {
        isHovering = true
        updateHoverState(animated: true)
    }

    override func mouseExited(with event: NSEvent) {
        isHovering = false
        updateHoverState(animated: true)
    }

    override var isHighlighted: Bool {
        didSet { updateHoverState(animated: true) }
    }

    override var isEnabled: Bool {
        didSet {
            updateTint()
            updateHoverState(animated: false)
        }
    }

    func updateTint() {
        let tint = isEnabled ? (restingTintColor ?? resolvedSystemColor(.labelColor)) : resolvedSystemColor(.tertiaryLabelColor)
        contentTintColor = tint
        let attr = NSMutableAttributedString(attributedString: attributedTitle)
        attr.addAttributes([.foregroundColor: tint], range: NSRange(location: 0, length: attr.length))
        attributedTitle = attr
    }

    func setCornerRadius(_ radius: CGFloat, maskedCorners: CACornerMask? = nil) {
        layer?.cornerRadius = radius
        if let maskedCorners {
            layer?.maskedCorners = maskedCorners
        }
    }

    private func updateHoverState(animated: Bool) {
        let reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion || !animated
        let isActive = isEnabled && (isHovering || isHighlighted)
        let hoverTarget: Float = isHighlighted ? 0.22 : ((isHovering && isEnabled) ? 0.12 : 0.0)
        let glowColor = (restingGlowColor ?? NSColor.white).usingColorSpace(.deviceRGB) ?? NSColor.white

        let baseGlowOpacity: Float = (restingGlowColor == nil || !isEnabled) ? 0.0 : 0.24
        let targetShadowOpacity: Float = isActive ? (isHighlighted ? 0.30 : 0.20) : baseGlowOpacity
        let targetShadowRadius: CGFloat = isActive ? 6 : (restingGlowColor == nil ? 0 : 4)
        let targetShadowOffset = CGSize(width: 0, height: isActive ? -1.0 : (restingGlowColor == nil ? 0 : -0.4))
        let scale: CGFloat = isActive ? 1.02 : 1.0
        let lift: CGFloat = isActive ? -0.7 : 0.0
        var transform = CATransform3DIdentity
        transform = CATransform3DTranslate(transform, 0, lift, 0)
        transform = CATransform3DScale(transform, scale, scale, 1.0)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer?.shadowColor = glowColor.cgColor
        CATransaction.commit()

        if reduceMotion {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            hoverLayer.opacity = hoverTarget
            layer?.transform = transform
            layer?.shadowOpacity = targetShadowOpacity
            layer?.shadowRadius = targetShadowRadius
            layer?.shadowOffset = targetShadowOffset
            CATransaction.commit()
        } else {
            animateLayer(hoverLayer, keyPath: "opacity", to: hoverTarget, preset: .microBounce, reduceMotion: false, basicDuration: 0.12)
            animateLayer(layer, keyPath: "transform", to: transform, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowOpacity", to: targetShadowOpacity, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowRadius", to: targetShadowRadius, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowOffset", to: targetShadowOffset, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
        }
    }
}

private final class MorphingGlassPillControl: NSView {
    private final class OrnamentOverlayView: NSView {
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
    }

    private let backgroundView: NSView
    private let ornamentOverlayView = OrnamentOverlayView(frame: .zero)
    private let shareOrnaments = ShareStyleOrnamentStack()

    private let shapeMaskLayer = CAShapeLayer()
    private let hoverLayer = CAShapeLayer()
    private let strokeGroupLayer = CALayer()
    private let seamSmudgeMaskLayer = CAGradientLayer()
    private let rimDarkLayer = CAShapeLayer()
    private let rimLightLayer = CAShapeLayer()
    private let strokeLayer = CAShapeLayer()
    private let innerStrokeLayer = CAShapeLayer()
    private let dispersionLayer = CAGradientLayer()
    private let dispersionMask = CAShapeLayer()
    private var tracking: NSTrackingArea?

    // Robust hover detection: AppKit can miss `mouseEntered` on fast passes or during layout churn.
    // We poll mouse position in screen coordinates and detect segment-rect crossings.
    private var hoverPollTimer: Timer?
    private var hoverReconcileWorkItem: DispatchWorkItem?
    private var lastMouseScreenPoint: NSPoint?
    private var lastCrossingTriggerTime: TimeInterval = 0

    private var isHovering = false
    private var isPressed = false
    private var isExpanded = false

    // Content (collapsed state): single compositional unit (icon+text inline).
    private let pillLabel = NSTextField(labelWithString: "")

    // Expanded state hit targets + icons.
    private var circleButtons: [NSButton] = []
    private var circleIconViews: [NSImageView] = []

    var mirroredHorizontally = false {
        didSet {
            updateStyle()
            updatePaths(animated: false)
            layoutContent(animated: false)
        }
    }
    var pathAnimationPreset: SpringPreset = .soft
    var pathAnimationDuration: CFTimeInterval = 0.28

    var reduceMotionProvider: (() -> Bool)?
    var backgroundProvider: ((CGRect, CGFloat) -> CGImage?)? {
        didSet {
            if let card = backgroundView as? GlassCardView {
                card.backgroundProvider = backgroundProvider
            }
        }
    }

    // Allows the host to theme the pill background using the same pipeline as the embedded search bar.
    // Must not mutate geometry/animation; only appearance (tint/material).
    var backgroundThemeApplier: ((NSView) -> Void)? {
        didSet {
            backgroundThemeApplier?(backgroundView)
        }
    }
    var onActivate: (() -> Void)?
    var onExpansionStateChanged: ((Bool) -> Void)?
    private var symmetryDebugEnabled: Bool {
        ProcessInfo.processInfo.environment["ARXIV_PILL_SYMMETRY_DEBUG"] == "1"
    }
    private let expandedCircleCount: Int = 4

    private var baseConfig = GlassCardKit.GlassCardConfig()
    private let rimStyle = GlassCardKit.BorderStyle.clearRim
    private static let suppressedBorderStyle = GlassCardKit.BorderStyle(rimWidth: 0,
                                                                        outerWidth: 0,
                                                                        innerWidth: 0,
                                                                        rimLightAlpha: 0,
                                                                        rimDarkAlpha: 0,
                                                                        outerAlpha: 0,
                                                                        innerAlpha: 0,
                                                                        dispersionAlpha: 0)

    override init(frame frameRect: NSRect) {
        var config = GlassCardKit.GlassCardConfig()
        baseConfig = config
        config.borderStyle = Self.suppressedBorderStyle

        // Match the search bar's rendering pipeline: use an effect view background.
        // The pill's animations are driven by masks/strokes on this view's layer, so only the
        // underlying background implementation changes.
        if #available(macOS 26.0, *) {
            let v = PassthroughGlassEffectView(frame: .zero)
            v.style = .regular
            v.translatesAutoresizingMaskIntoConstraints = true
            backgroundView = v
        } else {
            let v = PassthroughVisualEffectView(frame: .zero)
            v.material = .hudWindow
            v.blendingMode = .withinWindow
            v.state = .active
            v.isEmphasized = true
            v.translatesAutoresizingMaskIntoConstraints = true
            v.wantsLayer = true
            v.layer?.masksToBounds = true
            if #available(macOS 10.13, *) {
                v.layer?.cornerCurve = .continuous
            }
            backgroundView = v
        }
        super.init(frame: frameRect)

        wantsLayer = true
        layer?.masksToBounds = false

        backgroundView.translatesAutoresizingMaskIntoConstraints = true
        backgroundView.wantsLayer = true
        addSubview(backgroundView)

        ornamentOverlayView.translatesAutoresizingMaskIntoConstraints = true
        ornamentOverlayView.wantsLayer = true
        ornamentOverlayView.layer?.masksToBounds = false
        addSubview(ornamentOverlayView)

        pillLabel.translatesAutoresizingMaskIntoConstraints = true
        pillLabel.wantsLayer = true
        pillLabel.isEditable = false
        pillLabel.isSelectable = false
        pillLabel.isBezeled = false
        pillLabel.isBordered = false
        pillLabel.drawsBackground = false
        pillLabel.lineBreakMode = .byTruncatingTail
        addSubview(pillLabel)

        shapeMaskLayer.fillColor = NSColor.black.cgColor

        hoverLayer.fillColor = NSColor.white.withAlphaComponent(0.12).cgColor
        hoverLayer.opacity = 0

        // Share-style ornaments: gradients clipped to shape + 2 strokes.
        if let ornamentLayer = ornamentOverlayView.layer {
            shareOrnaments.attach(to: ornamentLayer)
        }

        // Smudge/erase the stitched-midline seam on stroked layers without changing geometry.
        // Implemented as a narrow, soft transparent band at x=0.5 in mask coordinates.
        seamSmudgeMaskLayer.startPoint = CGPoint(x: 0.0, y: 0.5)
        seamSmudgeMaskLayer.endPoint = CGPoint(x: 1.0, y: 0.5)
        seamSmudgeMaskLayer.colors = [
            NSColor.white.cgColor,
            NSColor.white.cgColor,
            NSColor.clear.cgColor,
            NSColor.white.cgColor,
            NSColor.white.cgColor,
        ]
        seamSmudgeMaskLayer.locations = [0.0, 0.48, 0.5, 0.52, 1.0]
        seamSmudgeMaskLayer.opacity = 1.0
        strokeGroupLayer.mask = seamSmudgeMaskLayer

        rimDarkLayer.fillColor = NSColor.clear.cgColor
        rimDarkLayer.lineJoin = .round
        rimDarkLayer.lineCap = .round

        rimLightLayer.fillColor = NSColor.clear.cgColor
        rimLightLayer.lineJoin = .round
        rimLightLayer.lineCap = .round

        strokeLayer.fillColor = NSColor.clear.cgColor
        strokeLayer.lineJoin = .round
        strokeLayer.lineCap = .round

        innerStrokeLayer.fillColor = NSColor.clear.cgColor
        innerStrokeLayer.lineJoin = .round
        innerStrokeLayer.lineCap = .round

        dispersionLayer.startPoint = CGPoint(x: 0.0, y: 0.5)
        dispersionLayer.endPoint = CGPoint(x: 1.0, y: 0.5)
        dispersionLayer.mask = dispersionMask

        if let glassLayer = backgroundView.layer {
            glassLayer.mask = shapeMaskLayer

            glassLayer.addSublayer(strokeGroupLayer)
            strokeGroupLayer.addSublayer(rimDarkLayer)
            strokeGroupLayer.addSublayer(rimLightLayer)
            glassLayer.addSublayer(dispersionLayer)
            strokeGroupLayer.addSublayer(strokeLayer)
            strokeGroupLayer.addSublayer(innerStrokeLayer)
            glassLayer.addSublayer(hoverLayer)
        }

        updateStyle()
        updateForEffectiveAppearance()
        updatePaths(animated: false)
        layoutContent(animated: false)
        updateContentVisibility(animated: false)
        updateInteraction(animated: false)
    }

    private func pixelAlignedRect(_ rect: NSRect) -> NSRect {
        let scale = max(1.0, window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0)
        let minX = round(rect.minX * scale) / scale
        let minY = round(rect.minY * scale) / scale
        let maxX = round(rect.maxX * scale) / scale
        let maxY = round(rect.maxY * scale) / scale
        return NSRect(x: minX, y: minY, width: max(0, maxX - minX), height: max(0, maxY - minY))
    }

    required init?(coder: NSCoder) { fatalError() }

    deinit {
        stopRobustHoverDetection()
    }

    func applyConfig(_ config: GlassCardKit.GlassCardConfig) {
        baseConfig = config
        applyConfigForState()
    }

    func updateTint(_ tint: NSColor?) {
        baseConfig.tint = tint
        applyConfigForState()
    }

    private func currentState() -> GlassCardKit.State {
        if isPressed { return .pressed }
        if isHovering { return .hover }
        return .normal
    }

    private func applyConfigForState() {
        var config = baseConfig
        config.cornerRadius = max(6, bounds.height / 2)
        config.state = currentState()
        config.borderStyle = Self.suppressedBorderStyle
        if let card = backgroundView as? GlassCardView {
            card.updateConfig(config)
        } else {
            // The effect view background is themed by the host (embedded search bar theme).
            // Keep this path geometry-only: corner radius and masks remain stable.
            backgroundThemeApplier?(backgroundView)
        }
        updateStyle()
    }

    override func layout() {
        super.layout()
        backgroundView.frame = bounds
        ornamentOverlayView.frame = bounds
        shapeMaskLayer.frame = bounds
        updatePaths(animated: false)
        layoutContent(animated: false)
        applyConfigForState()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        // Ensure subview-backed layers have their correct initial visibility once attached.
        updateContentVisibility(animated: false)

        if window == nil {
            stopRobustHoverDetection()
            lastMouseScreenPoint = nil
        } else {
            startRobustHoverDetectionIfNeeded()
            syncHoverFromCurrentMouseLocation(animated: false)
        }
    }

    private func startRobustHoverDetectionIfNeeded() {
        guard hoverPollTimer == nil else { return }
        // 60Hz is enough for responsiveness while keeping CPU reasonable.
        let timer = Timer(timeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            self?.pollMouseAndDetectCrossing()
        }
        timer.tolerance = 0.01
        hoverPollTimer = timer
        RunLoop.main.add(timer, forMode: .common)

        // Prime last point immediately to avoid a giant first segment after pauses.
        lastMouseScreenPoint = NSEvent.mouseLocation
    }

    private func stopRobustHoverDetection() {
        hoverReconcileWorkItem?.cancel()
        hoverReconcileWorkItem = nil
        hoverPollTimer?.invalidate()
        hoverPollTimer = nil
    }

    private func pollMouseAndDetectCrossing() {
        guard window != nil else { return }
        let p = NSEvent.mouseLocation
        detectCrossing(usingScreenPoint: p)
        lastMouseScreenPoint = p
    }

    private func pillScreenRect() -> NSRect? {
        guard let w = window, !isHidden, alphaValue > 0.01 else { return nil }
        // Bounds -> window coords -> screen coords.
        let rectInWindow = convert(bounds, to: nil)
        return w.convertToScreen(rectInWindow)
    }

    private func detectCrossing(usingScreenPoint point: NSPoint) {
        guard let rect = pillScreenRect() else { return }

        // If we are already hovering/pressed/expanded, tracking areas should keep us correct.
        // Still record the last point to keep segment math stable.
        let now = ProcessInfo.processInfo.systemUptime
        let last = lastMouseScreenPoint

        // Direct hit.
        if rect.contains(point) {
            triggerHoverFromCrossing(animated: true, now: now)
            return
        }

        // Segment crossing hit (fast pass between samples).
        if let last, segmentIntersectsRect(a: last, b: point, rect: rect) {
            triggerHoverFromCrossing(animated: true, now: now)
        }
    }

    private func triggerHoverFromCrossing(animated: Bool, now: TimeInterval) {
        // Throttle: avoid retriggering continuously while the cursor jitter-crosses the boundary.
        if now - lastCrossingTriggerTime < 0.10 {
            return
        }
        lastCrossingTriggerTime = now

        // Always trigger the expand animation on a crossing event, even if the cursor is no longer inside.
        if !isHovering {
            isHovering = true
            setExpanded(true, animated: animated)
            updateInteraction(animated: animated)
        } else if !isExpanded {
            setExpanded(true, animated: animated)
            updateInteraction(animated: animated)
        }

        // After a short hold (enough for the animation to be visible), reconcile to the true hover state.
        hoverReconcileWorkItem?.cancel()
        let hold = max(0.12, min(0.35, pathAnimationDuration))
        let work = DispatchWorkItem { [weak self] in
            self?.syncHoverFromCurrentMouseLocation(animated: true)
        }
        hoverReconcileWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + hold, execute: work)
    }

    private func segmentIntersectsRect(a: NSPoint, b: NSPoint, rect: NSRect) -> Bool {
        if rect.contains(a) || rect.contains(b) { return true }

        // Fast reject using bounding boxes.
        let minX = min(a.x, b.x)
        let maxX = max(a.x, b.x)
        let minY = min(a.y, b.y)
        let maxY = max(a.y, b.y)
        if maxX < rect.minX || minX > rect.maxX || maxY < rect.minY || minY > rect.maxY {
            return false
        }

        let r1 = NSPoint(x: rect.minX, y: rect.minY)
        let r2 = NSPoint(x: rect.maxX, y: rect.minY)
        let r3 = NSPoint(x: rect.maxX, y: rect.maxY)
        let r4 = NSPoint(x: rect.minX, y: rect.maxY)

        return segmentsIntersect(a1: a, a2: b, b1: r1, b2: r2)
            || segmentsIntersect(a1: a, a2: b, b1: r2, b2: r3)
            || segmentsIntersect(a1: a, a2: b, b1: r3, b2: r4)
            || segmentsIntersect(a1: a, a2: b, b1: r4, b2: r1)
    }

    private func segmentsIntersect(a1: NSPoint, a2: NSPoint, b1: NSPoint, b2: NSPoint) -> Bool {
        func orientation(_ p: NSPoint, _ q: NSPoint, _ r: NSPoint) -> Int {
            let val = (q.y - p.y) * (r.x - q.x) - (q.x - p.x) * (r.y - q.y)
            if abs(val) < 1e-9 { return 0 }
            return (val > 0) ? 1 : 2
        }
        func onSegment(_ p: NSPoint, _ q: NSPoint, _ r: NSPoint) -> Bool {
            q.x <= max(p.x, r.x) + 1e-9 && q.x + 1e-9 >= min(p.x, r.x)
                && q.y <= max(p.y, r.y) + 1e-9 && q.y + 1e-9 >= min(p.y, r.y)
        }

        let o1 = orientation(a1, a2, b1)
        let o2 = orientation(a1, a2, b2)
        let o3 = orientation(b1, b2, a1)
        let o4 = orientation(b1, b2, a2)

        if o1 != o2 && o3 != o4 { return true }
        if o1 == 0 && onSegment(a1, b1, a2) { return true }
        if o2 == 0 && onSegment(a1, b2, a2) { return true }
        if o3 == 0 && onSegment(b1, a1, b2) { return true }
        if o4 == 0 && onSegment(b1, a2, b2) { return true }
        return false
    }

    fileprivate func syncHoverFromCurrentMouseLocation(animated: Bool) {
        guard let w = window else { return }
        let locInWindow = w.mouseLocationOutsideOfEventStream
        let p = convert(locInWindow, from: nil)
        let inside = pointIsInsideVisibleShape(p)

        if inside {
            if !isHovering {
                isHovering = true
                setExpanded(true, animated: animated)
                updateInteraction(animated: animated)
            }
        } else {
            if isHovering || isPressed {
                isHovering = false
                isPressed = false
                setExpanded(false, animated: animated)
                updateInteraction(animated: animated)
            }
        }
    }

    private func pointIsInsideVisibleShape(_ point: NSPoint) -> Bool {
        guard !isHidden, alphaValue > 0.01 else { return false }
        guard bounds.contains(point) else { return false }
        guard let path = shapeMaskLayer.presentation()?.path ?? shapeMaskLayer.path else {
            return bounds.contains(point)
        }
        return path.contains(point)
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        updateStyle()
        updateForEffectiveAppearance()
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        // Critical: don't intercept clicks in the rectangular bounds when the visible
        // shape is smaller (capsule corners or gaps between circles).
        guard pointIsInsideVisibleShape(point) else { return nil }

        if isExpanded {
            for b in circleButtons {
                if b.frame.contains(point) { return b }
            }
        }
        return self
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let tracking { removeTrackingArea(tracking) }
        let opts: NSTrackingArea.Options = [.mouseEnteredAndExited, .activeAlways, .inVisibleRect]
        let area = NSTrackingArea(rect: bounds, options: opts, owner: self, userInfo: nil)
        addTrackingArea(area)
        tracking = area
    }

    override func mouseEntered(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        guard pointIsInsideVisibleShape(p) else { return }
        isHovering = true
        setExpanded(true, animated: true)
        updateInteraction(animated: true)
    }

    override func mouseExited(with event: NSEvent) {
        isHovering = false
        isPressed = false
        setExpanded(false, animated: true)
        updateInteraction(animated: true)
    }

    override func mouseDown(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        guard pointIsInsideVisibleShape(p) else { return }
        isPressed = true
        updateInteraction(animated: true)
    }

    override func mouseUp(with event: NSEvent) {
        let wasPressed = isPressed
        isPressed = false
        updateInteraction(animated: true)
        guard wasPressed else { return }
        let point = convert(event.locationInWindow, from: nil)
        if pointIsInsideVisibleShape(point) {
            // Collapsed pill acts as a single control.
            if !isExpanded {
                onActivate?()
            }
        }
    }

    fileprivate func setExpanded(_ expanded: Bool, animated: Bool) {
        guard expanded != isExpanded else { return }
        isExpanded = expanded
        updatePaths(animated: animated)
        updateContentVisibility(animated: animated)
        // Ensure layout stays in sync with the geometry end state.
        layoutContent(animated: false)

        // Host layout can depend on the pill's visual state (e.g. after animations).
        // Re-center deterministically on every expand/collapse to avoid accumulating drift.
        onExpansionStateChanged?(expanded)
    }

    private func updateInteraction(animated: Bool) {
        applyConfigForState()
        let reduceMotion = (reduceMotionProvider?() ?? false)
            || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
            || !animated
        let isActive = isHovering || isPressed
        let hoverTarget: Float = isPressed ? 0.22 : (isHovering ? 0.12 : 0.0)
        let targetShadowOpacity: Float = isActive ? (isPressed ? 0.32 : 0.22) : 0.0
        let targetShadowRadius: CGFloat = isActive ? 6 : 0
        let targetShadowOffset = CGSize(width: 0, height: isActive ? -1.0 : 0.0)
        let scale: CGFloat = isActive ? 1.03 : 1.0
        let lift: CGFloat = isActive ? -0.8 : 0.0
        // Visually compress just this pill control uniformly (X and Y) so the capsule,
        // circular buttons, and label/icon scale together.
        let basePillScale: CGFloat = 0.8
        let combinedScale = scale * basePillScale
        var transform = CATransform3DIdentity
        // Preserve the existing “translate then scale” feel for lift.
        transform = CATransform3DTranslate(transform, 0, lift, 0)
        transform = CATransform3DScale(transform, combinedScale, combinedScale, 1.0)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer?.shadowColor = NSColor.white.cgColor
        CATransaction.commit()

        if reduceMotion {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            hoverLayer.opacity = hoverTarget
            layer?.transform = transform
            layer?.shadowOpacity = targetShadowOpacity
            layer?.shadowRadius = targetShadowRadius
            layer?.shadowOffset = targetShadowOffset
            CATransaction.commit()
        } else {
            animateLayer(hoverLayer, keyPath: "opacity", to: hoverTarget, preset: .microBounce, reduceMotion: false, basicDuration: 0.12)
            animateLayer(layer, keyPath: "transform", to: transform, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowOpacity", to: targetShadowOpacity, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowRadius", to: targetShadowRadius, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowOffset", to: targetShadowOffset, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
        }
    }

    private func updateForEffectiveAppearance() {
        // Collapsed label: SF system typography + dynamic label color.
        let pointSize: CGFloat = 13.5
        let font = NSFont.systemFont(ofSize: pointSize, weight: .regular)
        let color = mainSearchForegroundColor()

        let iconPoint: CGFloat = 14
        let iconConfig = NSImage.SymbolConfiguration(pointSize: iconPoint, weight: .regular)
        let iconName = "sparkles" // Apple Intelligence-style visual language in SF Symbols.
        let baseIcon = NSImage(systemSymbolName: iconName, accessibilityDescription: nil) ?? NSImage()
        let icon = baseIcon.withSymbolConfiguration(iconConfig) ?? baseIcon

        let tintedIcon = tintedImage(icon, color: color)
        let mirroredTintedIcon = horizontallyMirroredImage(tintedIcon)

        // Inline attachment ensures baseline-aligned icon+text behave as one unit.
        let attachment = NSTextAttachment()
        attachment.image = tintedIcon
        // Optic baseline adjustment: slight drop reads like SF Symbols baseline alignment.
        attachment.bounds = CGRect(x: 0, y: -2, width: iconPoint, height: iconPoint)

        let s = NSMutableAttributedString(attachment: attachment)
        s.append(NSAttributedString(string: " "))
        let text = NSAttributedString(
            string: "Ask a Question with AI",
            attributes: [
                .font: font,
                .foregroundColor: color
            ]
        )
        s.append(text)

        s.append(NSAttributedString(string: " "))
        let rightAttachment = NSTextAttachment()
        rightAttachment.image = mirroredTintedIcon
        rightAttachment.bounds = CGRect(x: 0, y: -2, width: iconPoint, height: iconPoint)
        s.append(NSAttributedString(attachment: rightAttachment))
        pillLabel.attributedStringValue = s

        if let l = pillLabel.layer {
            l.contentsScale = window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0
        }

        // Expanded iconography uses Apple "Writing Tools" SF Symbol.
        for iv in circleIconViews {
            let base = NSImage(systemSymbolName: "writingtools", accessibilityDescription: nil)
                ?? NSImage(systemSymbolName: "pencil.and.scribble", accessibilityDescription: nil)
                ?? NSImage(systemSymbolName: "pencil", accessibilityDescription: nil)
            if let base {
                iv.image = tintedImage(base.withSymbolConfiguration(NSImage.SymbolConfiguration(pointSize: 13, weight: .regular)) ?? base,
                                       color: color)
            }
            iv.contentTintColor = color
        }
    }

    private func ensureCircleButtonsIfNeeded() {
        guard circleButtons.isEmpty else { return }
        for _ in 0..<expandedCircleCount {
            let b = NSButton(frame: .zero)
            b.title = ""
            b.isBordered = false
            b.bezelStyle = .regularSquare
            b.wantsLayer = true
            b.layer?.backgroundColor = NSColor.clear.cgColor
            b.layer?.cornerRadius = 0
            b.target = self
            b.action = #selector(circleButtonPressed(_:))

            let iv = NSImageView(frame: .zero)
            iv.imageAlignment = .alignCenter
            iv.imageScaling = .scaleProportionallyDown
            iv.wantsLayer = true
            iv.layer?.anchorPoint = CGPoint(x: 0.5, y: 0.5)
            iv.layer?.contentsScale = window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0

            // Fix launch flash: ensure icon layers start hidden when collapsed.
            if let il = iv.layer {
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                il.opacity = 0.0
                il.transform = CATransform3DTranslate(CATransform3DIdentity, 0, 2.0, 0)
                CATransaction.commit()
            }
            b.addSubview(iv)

            addSubview(b)
            circleButtons.append(b)
            circleIconViews.append(iv)
        }
        for b in circleButtons { b.isEnabled = false }
        updateForEffectiveAppearance()
    }

    @objc private func circleButtonPressed(_ sender: Any?) {
        onActivate?()
    }

    private func updatePaths(animated: Bool) {
        let b = bounds
        guard b.width > 4, b.height > 4 else { return }

        updateStyle()
        ensureCircleButtonsIfNeeded()

        // Keep the seam-smudge band roughly constant in physical pixels.
        let scale = max(1.0, window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0)
        let halfWidthPx: CGFloat = 1.25 * scale
        let halfWidth = max(0.5, halfWidthPx / max(1.0, b.width))
        let leftStop = max(0.0, 0.5 - halfWidth)
        let rightStop = min(1.0, 0.5 + halfWidth)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        seamSmudgeMaskLayer.locations = [0.0, NSNumber(value: Double(leftStop)), 0.5, NSNumber(value: Double(rightStop)), 1.0]
        CATransaction.commit()

        let outerInset = max(0.5, rimLightLayer.lineWidth / 2)
        let innerInset = max(0.5, innerStrokeLayer.lineWidth / 2) + 1.0
        // Match Share: let the glass fill reach the visible edge; border ornaments are inset.
        let maskInset: CGFloat = 0.0

        let outerPath = morphPath(in: b, inset: outerInset)
        let innerPath = morphPath(in: b, inset: innerInset)
        let maskPath = morphPath(in: b, inset: maskInset)

        // Share-style ornament geometry: inset by 0.5/1.5 points.
        let ornamentMaskPath = morphPath(in: b, inset: 0.0)
        let ornamentOuterPath = morphPath(in: b, inset: 0.5)
        let ornamentInnerPath = morphPath(in: b, inset: 1.5)

        if let glassLayer = backgroundView.layer {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            shapeMaskLayer.frame = glassLayer.bounds
            hoverLayer.frame = glassLayer.bounds
            strokeGroupLayer.frame = glassLayer.bounds
            seamSmudgeMaskLayer.frame = glassLayer.bounds
            rimDarkLayer.frame = glassLayer.bounds
            rimLightLayer.frame = glassLayer.bounds
            dispersionLayer.frame = glassLayer.bounds
            dispersionMask.frame = glassLayer.bounds
            strokeLayer.frame = glassLayer.bounds
            innerStrokeLayer.frame = glassLayer.bounds
            CATransaction.commit()
        }

        if let ornamentLayer = ornamentOverlayView.layer {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            shareOrnaments.setFrames(bounds: ornamentLayer.bounds)
            CATransaction.commit()
        }

        let reduceMotion = (reduceMotionProvider?() ?? false)
            || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
            || !animated

        applyPath(shapeMaskLayer, path: maskPath, reduceMotion: reduceMotion)
        applyPath(hoverLayer, path: maskPath, reduceMotion: reduceMotion)
        applyPath(rimDarkLayer, path: outerPath, reduceMotion: reduceMotion)
        applyPath(rimLightLayer, path: outerPath, reduceMotion: reduceMotion)
        applyPath(strokeLayer, path: outerPath, reduceMotion: reduceMotion)
        applyPath(innerStrokeLayer, path: innerPath, reduceMotion: reduceMotion)
        applyPath(dispersionMask, path: outerPath, reduceMotion: reduceMotion)

        applyPath(shareOrnaments.maskLayer, path: ornamentMaskPath, reduceMotion: reduceMotion)
        applyPath(shareOrnaments.outlineLayer, path: ornamentOuterPath, reduceMotion: reduceMotion)
        applyPath(shareOrnaments.innerOutlineLayer, path: ornamentInnerPath, reduceMotion: reduceMotion)

        // Fade the seam-smudge mask out when expanded.
        let smudgeOpacity: Float = isExpanded ? 0.0 : 1.0
        if reduceMotion {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            seamSmudgeMaskLayer.opacity = smudgeOpacity
            CATransaction.commit()
        } else {
            animateLayer(seamSmudgeMaskLayer, keyPath: "opacity", to: smudgeOpacity, preset: pathAnimationPreset, reduceMotion: false, basicDuration: pathAnimationDuration)
        }

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer?.shadowPath = ornamentMaskPath
        CATransaction.commit()

        if symmetryDebugEnabled {
            let debugRect = b.insetBy(dx: outerInset, dy: outerInset)
            let layout = expandedCircleLayout(in: debugRect, circleCount: expandedCircleCount)
            logSymmetryPairs(leftCenters: layout.left, rightCenters: layout.right, centerX: debugRect.midX)
        }
    }

    private func applyPath(_ layer: CAShapeLayer, path: CGPath, reduceMotion: Bool) {
        let fromPath = layer.presentation()?.path ?? layer.path
        layer.removeAnimation(forKey: "basic_path")

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.path = path
        CATransaction.commit()

        guard !reduceMotion else { return }
        let basic = CABasicAnimation(keyPath: "path")
        basic.fromValue = fromPath
        basic.toValue = path
        basic.duration = pathAnimationDuration
        basic.timingFunction = CAMediaTimingFunction(controlPoints: 0.25, 0.8, 0.25, 1)
        layer.add(basic, forKey: "basic_path")
    }

    private func layoutContent(animated: Bool) {
        let b = bounds
        guard b.width > 4, b.height > 4 else { return }
        ensureCircleButtonsIfNeeded()

        // Label centered within the *collapsed* capsule, not the full bounds.
        // This keeps the capsule visually tight around the text without affecting the expanded geometry.
        let contentInset = max(0.5, strokeLayer.lineWidth / 2)
        let capsuleRect = collapsedCapsuleRect(in: b, inset: contentInset)
        let labelSize = pillLabel.fittingSize
        let labelX = capsuleRect.midX - (labelSize.width / 2)
        let labelY = capsuleRect.midY - (labelSize.height / 2)
        pillLabel.frame = pixelAlignedRect(NSRect(x: labelX, y: labelY, width: labelSize.width, height: labelSize.height))

        // Button frames always reflect the expanded geometry, but the buttons are only enabled
        // (and hit-testable) in the expanded state.
        let outerInset = max(0.5, rimLightLayer.lineWidth / 2)
        let layoutRect = b.insetBy(dx: outerInset, dy: outerInset)
        let layout = expandedCircleLayout(in: layoutRect, circleCount: expandedCircleCount)
        let centers: [CGFloat] = {
            let merged = layout.left + (layout.center.map { [$0] } ?? []) + layout.right
            return merged.sorted()
        }()

        for i in 0..<min(circleButtons.count, centers.count) {
            let cx = centers[i]
            let frame = NSRect(x: cx - (layout.diameter / 2), y: layout.y, width: layout.diameter, height: layout.diameter)
            circleButtons[i].frame = pixelAlignedRect(frame)
            circleButtons[i].layer?.cornerRadius = circleButtons[i].bounds.height / 2
            circleIconViews[i].frame = circleButtons[i].bounds.insetBy(dx: max(2, circleButtons[i].bounds.width * 0.22),
                                                                       dy: max(2, circleButtons[i].bounds.height * 0.22))
        }

        if circleButtons.count > centers.count {
            for j in centers.count..<circleButtons.count {
                circleButtons[j].frame = .zero
                circleIconViews[j].frame = .zero
            }
        }
    }

    private func updateContentVisibility(animated: Bool) {
        let reduceMotion = (reduceMotionProvider?() ?? false)
            || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
            || !animated

        let labelVisible = !isExpanded
        let labelOpacity: Float = labelVisible ? 1.0 : 0.0
        let labelSlide: CGFloat = labelVisible ? 0.0 : -2.0

        if let l = pillLabel.layer {
            let target = CATransform3DTranslate(CATransform3DIdentity, 0, labelSlide, 0)
            if reduceMotion {
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                l.opacity = labelOpacity
                l.transform = target
                CATransaction.commit()
            } else {
                animateLayer(l, keyPath: "opacity", to: labelOpacity, preset: pathAnimationPreset, reduceMotion: false, basicDuration: pathAnimationDuration)
                animateLayer(l, keyPath: "transform", to: target, preset: pathAnimationPreset, reduceMotion: false, basicDuration: pathAnimationDuration)
            }
        }

        let iconOpacity: Float = isExpanded ? 1.0 : 0.0
        let iconSlide: CGFloat = isExpanded ? 0.0 : 2.0
        for i in 0..<min(circleButtons.count, circleIconViews.count) {
            circleButtons[i].isEnabled = isExpanded
            guard let il = circleIconViews[i].layer else { continue }
            let target = CATransform3DTranslate(CATransform3DIdentity, 0, iconSlide, 0)
            if reduceMotion {
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                il.opacity = iconOpacity
                il.transform = target
                CATransaction.commit()
            } else {
                animateLayer(il, keyPath: "opacity", to: iconOpacity, preset: pathAnimationPreset, reduceMotion: false, basicDuration: pathAnimationDuration)
                animateLayer(il, keyPath: "transform", to: target, preset: pathAnimationPreset, reduceMotion: false, basicDuration: pathAnimationDuration)
            }
        }
    }

    private func mirroredCompositePath(fromRightHalf right: CGPath, centerX: CGFloat) -> CGPath {
        var t = CGAffineTransform(a: -1, b: 0, c: 0, d: 1, tx: 2 * centerX, ty: 0)
        let left = right.copy(using: &t) ?? right
        let out = CGMutablePath()
        out.addPath(left)
        out.addPath(right)
        return out
    }

    // `applyPath` removed: the morph is now entirely driven by a single `progress` value.

    private func symmetryDebugScale() -> CGFloat {
        max(1.0, window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0)
    }

    private func symmetryDebugEpsilon() -> CGFloat {
        0.5 / symmetryDebugScale()
    }

    private func logSymmetryPairs(leftCenters: [CGFloat], rightCenters: [CGFloat], centerX: CGFloat) {
        guard symmetryDebugEnabled, !leftCenters.isEmpty, leftCenters.count == rightCenters.count else { return }
        let epsilon = symmetryDebugEpsilon()
        for pairIndex in 0..<leftCenters.count {
            let leftX = leftCenters[pairIndex]
            let rightX = rightCenters[pairIndex]
            let dxLeft = leftX - centerX
            let dxRight = rightX - centerX
            let sum = dxLeft + dxRight
            let message = String(format: "pair=%d dx_left=%.3f dx_right=%.3f sum=%.3f eps=%.3f",
                                 pairIndex, dxLeft, dxRight, sum, epsilon)
            NSLog("[PillSymmetry] \(message)")
            assert(abs(sum) < epsilon, "Pill symmetry failed: \(message)")
        }
    }

    private func mirroredCenterPairs(centerX: CGFloat,
                                     count: Int,
                                     step: CGFloat) -> (center: CGFloat?, left: [CGFloat], right: [CGFloat]) {
        guard count > 0 else { return (nil, [], []) }
        let hasCenter = (count % 2) == 1
        let pairCount = count / 2
        let offsetBase: CGFloat = hasCenter ? 1.0 : 0.5

        // Source of truth: compute RIGHT side first.
        var rightCenters: [CGFloat] = []
        rightCenters.reserveCapacity(pairCount)
        for pairIndex in 0..<pairCount {
            let dx = (CGFloat(pairIndex) + offsetBase) * step
            rightCenters.append(centerX + dx)
        }

        // Strict geometric mirror across the vertical bisector.
        // x_left = centerX - (x_right - centerX) == 2*centerX - x_right
        let leftCenters = rightCenters.map { xRight in centerX - (xRight - centerX) }
        return (hasCenter ? centerX : nil, leftCenters, rightCenters)
    }

    private func expandedCircleLayout(in rect: CGRect,
                                      circleCount: Int) -> (center: CGFloat?, left: [CGFloat], right: [CGFloat], diameter: CGFloat, y: CGFloat) {
        guard circleCount > 0 else { return (nil, [], [], 0, rect.midY) }
        let spacingRatio: CGFloat = 0.28
        let count = CGFloat(circleCount)
        let diameterFromWidth = rect.width / (count + ((count - 1) * spacingRatio))
        let diameter = max(2, min(rect.height, diameterFromWidth))
        let spacing = max(0, (rect.width - (count * diameter)) / max(1, (count - 1)))
        let step = diameter + spacing
        let pairs = mirroredCenterPairs(centerX: rect.midX, count: circleCount, step: step)
        let y = rect.midY - (diameter / 2)
        return (pairs.center, pairs.left, pairs.right, diameter, y)
    }

    private func morphPath(in bounds: CGRect, inset: CGFloat) -> CGPath {
        let rect = bounds.insetBy(dx: inset, dy: inset)
        guard rect.width > 1, rect.height > 1 else { return CGPath(rect: rect, transform: nil) }

        if !isExpanded {
            let capsule = collapsedCapsuleRect(in: bounds, inset: inset)
            return CGPath(roundedRect: capsule,
                          cornerWidth: rect.height / 2,
                          cornerHeight: rect.height / 2,
                          transform: nil)
        }

        // Expanded geometry: distinct circles.
        let layout = expandedCircleLayout(in: rect, circleCount: expandedCircleCount)
        let centers: [CGFloat] = {
            let merged = layout.left + (layout.center.map { [$0] } ?? []) + layout.right
            return merged.sorted()
        }()

        let out = CGMutablePath()
        for cx in centers {
            let x = cx - (layout.diameter / 2)
            out.addEllipse(in: CGRect(x: x, y: layout.y, width: layout.diameter, height: layout.diameter))
        }
        return out
    }

    private func collapsedCapsuleRect(in bounds: CGRect, inset: CGFloat) -> CGRect {
        let rect = bounds.insetBy(dx: inset, dy: inset)
        guard rect.width > 1, rect.height > 1 else { return rect }

        // Apple-like end padding: tight, but not cramped.
        // Keep padding stable across minor font rendering differences.
        let labelWidth = max(0, pillLabel.fittingSize.width)
        let minEndPadding: CGFloat = max(14, rect.height * 0.55)
        let desiredWidth = labelWidth + (2 * minEndPadding)

        // Clamp to available space and to a reasonable minimum so the pill never looks “pinched”.
        let minWidth = max(rect.height * 2.6, 140)
        let width = min(rect.width, max(minWidth, desiredWidth))
        let x = rect.midX - (width / 2)
        return CGRect(x: x, y: rect.minY, width: width, height: rect.height)
    }

    // MARK: - Test hooks
    fileprivate func _test_isExpanded() -> Bool { isExpanded }
    fileprivate func _test_labelOpacity() -> Float { pillLabel.layer?.opacity ?? -1 }
    fileprivate func _test_hasMorphAnimation() -> Bool {
        if shapeMaskLayer.animation(forKey: "basic_path") != nil { return true }
        if shapeMaskLayer.animation(forKey: "spring_path") != nil { return true }
        if let keys = shapeMaskLayer.animationKeys(), !keys.isEmpty { return true }
        return false
    }


    private func stateMultipliers(for state: GlassCardKit.State) -> (specular: CGFloat, fill: CGFloat, shadow: CGFloat) {
        switch state {
        case .normal:
            return (1.0, 1.0, 1.0)
        case .hover:
            return (1.06, 1.05, 1.05)
        case .pressed:
            return (0.92, 1.08, 0.90)
        case .selected:
            return (1.10, 1.06, 1.10)
        case .disabled:
            return (0.75, 0.85, 0.60)
        }
    }

    private func updateStyle() {
        let dark = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let stateScale = stateMultipliers(for: currentState())
        let thickness = max(0.7, baseConfig.thickness)
        let specular = max(0.2, min(1.6, baseConfig.specularIntensity)) * stateScale.specular
        let shadowStyle = baseConfig.shadowStyle

        // The pill border should match `ShareToolbarButton` exactly. Suppress the previous
        // glass-rim layers and rely on Share's ornament stack.
        let scale = max(1.0, window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0)

        CATransaction.begin()
        CATransaction.setDisableActions(true)

        rimDarkLayer.opacity = 0
        rimLightLayer.opacity = 0
        strokeLayer.opacity = 0
        innerStrokeLayer.opacity = 0
        dispersionLayer.opacity = 0

        rimDarkLayer.lineWidth = 0
        rimLightLayer.lineWidth = 0
        strokeLayer.lineWidth = 0
        innerStrokeLayer.lineWidth = 0

        // Share-style ornaments.
        shareOrnaments.setContentsScale(scale)
        shareOrnaments.applyShareStyle(enabled: true)

        // Preserve the pill's own shadow behavior.
        _ = dark
        _ = thickness
        _ = specular
        _ = shadowStyle

        CATransaction.commit()
    }
}

// MARK: - Pill Animation Stability Tests

#if canImport(XCTest)
private final class PillAnimationStabilityTests: XCTestCase {
    private func makeHostWindow() -> NSWindow {
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 800, height: 600),
                         styleMask: [.borderless],
                         backing: .buffered,
                         defer: false)
        w.isReleasedWhenClosed = false
        w.contentView = NSView(frame: w.contentRect(forFrameRect: w.frame))
        return w
    }

    private func makeControl(in window: NSWindow) -> MorphingGlassPillControl {
        let c = MorphingGlassPillControl(frame: NSRect(x: 100, y: 100, width: 320, height: 34))
        window.contentView?.addSubview(c)
        c.layoutSubtreeIfNeeded()
        return c
    }

    func testStateIntegrityCollapsedAndExpanded() {
        let _ = NSApplication.shared
        let w = makeHostWindow()
        let c = makeControl(in: w)

        c.setExpanded(false, animated: false)
        c.layoutSubtreeIfNeeded()
        XCTAssertEqual(c._test_isExpanded(), false)
        XCTAssertEqual(c._test_labelOpacity(), 1.0, accuracy: 1e-6)

        c.setExpanded(true, animated: false)
        c.layoutSubtreeIfNeeded()
        XCTAssertEqual(c._test_isExpanded(), true)
        XCTAssertEqual(c._test_labelOpacity(), 0.0, accuracy: 1e-6)
    }

    func testRapidToggleStressNoCrashAndFinalState() {
        let _ = NSApplication.shared
        let w = makeHostWindow()
        let c = makeControl(in: w)
        for i in 0..<10 {
            c.setExpanded((i % 2 == 0), animated: true)
        }
        c.setExpanded(true, animated: false)
        XCTAssertEqual(c._test_isExpanded(), true)
    }

    func testRepeatabilityNoLayoutDriftOver50Cycles() {
        let _ = NSApplication.shared
        let w = makeHostWindow()
        let c = makeControl(in: w)
        c.setExpanded(true, animated: false)
        c.layoutSubtreeIfNeeded()
        let baselineFrames = c.subviews.filter { $0 is NSButton }.map { $0.frame }

        for _ in 0..<50 {
            c.setExpanded(false, animated: false)
            c.setExpanded(true, animated: false)
            c.layoutSubtreeIfNeeded()
        }

        let afterFrames = c.subviews.filter { $0 is NSButton }.map { $0.frame }
        XCTAssertEqual(baselineFrames.count, afterFrames.count)
        for i in 0..<min(baselineFrames.count, afterFrames.count) {
            XCTAssertEqual(baselineFrames[i].origin.x, afterFrames[i].origin.x, accuracy: 1e-6)
            XCTAssertEqual(baselineFrames[i].origin.y, afterFrames[i].origin.y, accuracy: 1e-6)
            XCTAssertEqual(baselineFrames[i].size.width, afterFrames[i].size.width, accuracy: 1e-6)
            XCTAssertEqual(baselineFrames[i].size.height, afterFrames[i].size.height, accuracy: 1e-6)
        }
    }
}

private final class SettingsNonRegressionTests: XCTestCase {
    private func spinRunLoop(seconds: TimeInterval) {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            RunLoop.main.run(mode: .default, before: deadline)
        }
    }

    private func snapshotPNGHash(of view: NSView) -> String {
        view.layoutSubtreeIfNeeded()
        let bounds = view.bounds
        guard let rep = view.bitmapImageRepForCachingDisplay(in: bounds) else { return "" }
        view.cacheDisplay(in: bounds, to: rep)
        guard let data = rep.representation(using: .png, properties: [:]) else { return "" }
        let digest = SHA256.hash(data: data)
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    private func clearKnownDefaults() {
        let defaults = UserDefaults.standard
        defaults.removeObject(forKey: "astroStack.settings.v1")
        [
            "astroStack.sidebarWidth",
            "astroStack.sidebarVisible",
            "arxivPicker.sidebarWidth",
            "arxivPicker.sidebarVisible"
        ].forEach { defaults.removeObject(forKey: $0) }
    }

    override func setUp() {
        super.setUp()
        clearKnownDefaults()
    }

    func testDefaultSettingsRoundTrip() throws {
        let s = AppSettings()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(s)
        let decoded = try JSONDecoder().decode(AppSettings.self, from: data)
        XCTAssertEqual(s, decoded)
        XCTAssertEqual(decoded.schemaVersion, AppSettings.currentSchemaVersion)
    }

    func testOpenCloseSettingsDoesNotChangeMainWindowSnapshot() {
        let _ = NSApplication.shared

        let controller = PickerWindowController(payloadPathToWatch: nil)
        controller.showWindow(nil)
        controller.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        spinRunLoop(seconds: 0.35)

        guard let mainWindow = controller.window, let root = mainWindow.contentView else {
            XCTFail("missing_main_window")
            return
        }

        // Establish baseline while the main window is key.
        mainWindow.makeKeyAndOrderFront(nil)
        spinRunLoop(seconds: 0.15)
        let baselineHash = snapshotPNGHash(of: root)
        XCTAssertFalse(baselineHash.isEmpty)

        // Open settings, then close; main window should restore focus and render identically.
        SettingsWindowController.shared.openSettings(nil)
        spinRunLoop(seconds: 0.20)
        SettingsWindowController.shared.window?.performClose(nil)
        spinRunLoop(seconds: 0.25)

        mainWindow.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        spinRunLoop(seconds: 0.20)
        let afterHash = snapshotPNGHash(of: root)

        XCTAssertEqual(baselineHash, afterHash)
    }
}

#else

private struct PillAnimationDeterministicTests {
    private struct TestRunner {
        private(set) var failures: Int = 0
        mutating func assertTrue(_ condition: Bool, _ message: String) {
            if !condition {
                failures += 1
                NSLog("[PILL_TESTS] FAIL: \(message)")
            }
        }
        mutating func assertApprox(_ a: Double, _ b: Double, eps: Double = 1e-6, _ message: String) {
            if abs(a - b) > eps {
                failures += 1
                NSLog("[PILL_TESTS] FAIL: \(message) (\(a) vs \(b))")
            }
        }
    }

    private static func makeHostWindow() -> NSWindow {
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 800, height: 600),
                         styleMask: [.borderless],
                         backing: .buffered,
                         defer: false)
        w.isReleasedWhenClosed = false
        w.contentView = NSView(frame: w.contentRect(forFrameRect: w.frame))
        return w
    }

    private static func makeControl(in window: NSWindow) -> MorphingGlassPillControl {
        let c = MorphingGlassPillControl(frame: NSRect(x: 100, y: 100, width: 320, height: 34))
        window.contentView?.addSubview(c)
        c.layoutSubtreeIfNeeded()
        return c
    }

    static func run() -> Int {
        let _ = NSApplication.shared
        var t = TestRunner()

        do {
            let c = MorphingGlassPillControl(frame: NSRect(x: 0, y: 0, width: 320, height: 34))
            c.setExpanded(false, animated: false)
            t.assertTrue(c._test_isExpanded() == false, "collapsed_state")
            t.assertApprox(Double(c._test_labelOpacity()), 1.0, "collapsed_label_opacity")

            c.setExpanded(true, animated: false)
            t.assertTrue(c._test_isExpanded() == true, "expanded_state")
            t.assertApprox(Double(c._test_labelOpacity()), 0.0, "expanded_label_opacity")
        }

        do {
            let c = MorphingGlassPillControl(frame: NSRect(x: 0, y: 0, width: 320, height: 34))
            for i in 0..<10 {
                c.setExpanded((i % 2 == 0), animated: true)
            }
            c.setExpanded(true, animated: false)
            t.assertTrue(c._test_isExpanded() == true, "rapid_toggle_final_state")
        }

        do {
            let c = MorphingGlassPillControl(frame: NSRect(x: 0, y: 0, width: 360, height: 34))
            c.setExpanded(true, animated: false)
            c.layoutSubtreeIfNeeded()
            let baseline = c.subviews.compactMap { $0 as? NSButton }.map { $0.frame }

            for _ in 0..<50 {
                c.setExpanded(false, animated: false)
                c.setExpanded(true, animated: false)
                c.layoutSubtreeIfNeeded()
            }

            let after = c.subviews.compactMap { $0 as? NSButton }.map { $0.frame }
            t.assertTrue(baseline.count == after.count, "repeatability_button_count")
            for i in 0..<min(baseline.count, after.count) {
                t.assertApprox(Double(baseline[i].origin.x), Double(after[i].origin.x), "repeatability_x_\(i)")
                t.assertApprox(Double(baseline[i].origin.y), Double(after[i].origin.y), "repeatability_y_\(i)")
                t.assertApprox(Double(baseline[i].size.width), Double(after[i].size.width), "repeatability_w_\(i)")
                t.assertApprox(Double(baseline[i].size.height), Double(after[i].size.height), "repeatability_h_\(i)")
            }
        }

        // Basic animation presence check: path should animate when requested.
        do {
            let w = makeHostWindow()
            let c = makeControl(in: w)
            c.setExpanded(true, animated: true)
            CATransaction.flush()
            let reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
            t.assertTrue(reduceMotion || c._test_hasMorphAnimation(), "morph_path_animates")
        }

        if t.failures == 0 {
            NSLog("[PILL_TESTS] OK")
        }
        return t.failures
    }
}

private struct SettingsNonRegressionDeterministicTests {
    private struct TestRunner {
        private(set) var failures: Int = 0
        mutating func assertTrue(_ condition: Bool, _ message: String) {
            if !condition {
                failures += 1
                NSLog("[SETTINGS_TESTS] FAIL: \(message)")
            }
        }
        mutating func assertEqual(_ a: String, _ b: String, _ message: String) {
            if a != b {
                failures += 1
                NSLog("[SETTINGS_TESTS] FAIL: \(message) (\(a.prefix(12))… vs \(b.prefix(12))…)")
            }
        }
    }

    private static func spinRunLoop(seconds: TimeInterval) {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            RunLoop.main.run(mode: .default, before: deadline)
        }
    }

    private static func snapshotPNGHash(of view: NSView) -> String {
        view.layoutSubtreeIfNeeded()
        let bounds = view.bounds
        guard let rep = view.bitmapImageRepForCachingDisplay(in: bounds) else { return "" }
        view.cacheDisplay(in: bounds, to: rep)
        guard let data = rep.representation(using: .png, properties: [:]) else { return "" }
        let digest = SHA256.hash(data: data)
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    private static func clearKnownDefaults() {
        let defaults = UserDefaults.standard
        defaults.removeObject(forKey: "astroStack.settings.v1")
        [
            "astroStack.sidebarWidth",
            "astroStack.sidebarVisible",
            "arxivPicker.sidebarWidth",
            "arxivPicker.sidebarVisible"
        ].forEach { defaults.removeObject(forKey: $0) }
    }

    static func run() -> Int {
        let _ = NSApplication.shared
        clearKnownDefaults()
        var t = TestRunner()

        // Codable round-trip stability.
        do {
            let s = AppSettings()
            let encoder = JSONEncoder()
            if #available(macOS 10.13, *) {
                encoder.outputFormatting = [.sortedKeys]
            }
            let data = (try? encoder.encode(s)) ?? Data()
            let decoded = (try? JSONDecoder().decode(AppSettings.self, from: data))
            t.assertTrue(decoded == s, "default_round_trip")
            t.assertTrue(decoded?.schemaVersion == AppSettings.currentSchemaVersion, "schema_version")
        }

        // Open/close settings must not alter main window render once focus is restored.
        let controller = PickerWindowController(payloadPathToWatch: nil)
        controller.showWindow(nil)
        controller.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        spinRunLoop(seconds: 0.35)

        guard let mainWindow = controller.window, let root = mainWindow.contentView else {
            t.assertTrue(false, "missing_main_window")
            return t.failures
        }

        mainWindow.makeKeyAndOrderFront(nil)
        spinRunLoop(seconds: 0.15)
        let baselineHash = snapshotPNGHash(of: root)
        t.assertTrue(!baselineHash.isEmpty, "baseline_hash")

        SettingsWindowController.shared.openSettings(nil)
        spinRunLoop(seconds: 0.20)
        SettingsWindowController.shared.window?.performClose(nil)
        spinRunLoop(seconds: 0.25)

        mainWindow.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        spinRunLoop(seconds: 0.20)
        let afterHash = snapshotPNGHash(of: root)
        t.assertEqual(baselineHash, afterHash, "main_window_snapshot_unchanged")

        if t.failures == 0 {
            NSLog("[SETTINGS_TESTS] OK")
        }
        return t.failures
    }
}

#endif

private struct SpringSpec {
    let mass: CGFloat
    let stiffness: CGFloat
    let damping: CGFloat
    let initialVelocity: CGFloat
    let settleCap: CFTimeInterval
}

private enum SpringPreset {
    case microBounce
    case hoverBounce
    case crisp
    case soft
    case panelTransition
    case panelTransitionFast
    case gesture(initialVelocity: CGFloat)
}

private func springSpec(for preset: SpringPreset) -> SpringSpec {
    switch preset {
    case .microBounce:
        return SpringSpec(mass: 1.0, stiffness: 700, damping: 70, initialVelocity: 0.0, settleCap: 0.40)
    case .hoverBounce:
        // More dramatic “bouncy” hover: lower damping for overshoot + slightly longer settle.
        return SpringSpec(mass: 1.0, stiffness: 680, damping: 42, initialVelocity: 0.35, settleCap: 0.55)
    case .crisp:
        return SpringSpec(mass: 1.0, stiffness: 1100, damping: 120, initialVelocity: 0.0, settleCap: 0.28)
    case .soft:
        return SpringSpec(mass: 1.1, stiffness: 500, damping: 45, initialVelocity: 0.2, settleCap: 0.55)
    case .panelTransition:
        // Near-critically damped: subtle “settle” with no wobble/overshoot.
        // Damping ratio ζ ≈ 1.05 for a calm macOS-native feel.
        return SpringSpec(mass: 1.0, stiffness: 900, damping: 63, initialVelocity: 0.0, settleCap: 0.28)
    case .panelTransitionFast:
        // Faster variant used during rapid toggles; keep the same damping character.
        return SpringSpec(mass: 1.0, stiffness: 1200, damping: 73, initialVelocity: 0.0, settleCap: 0.22)
    case .gesture(let v):
        let clamped = min(max(v, 0.0), 3.0)
        return SpringSpec(mass: 1.0, stiffness: 900, damping: 80, initialVelocity: clamped, settleCap: 0.45)
    }
}

private func boxedAnimationValue(_ value: Any?) -> Any? {
    if let t = value as? CATransform3D { return NSValue(caTransform3D: t) }
    if let size = value as? CGSize { return NSValue(size: size) }
    if let rect = value as? CGRect { return NSValue(rect: rect) }
    if let point = value as? CGPoint { return NSValue(point: point) }
    return value
}

private func animateLayer(_ layer: CALayer?,
                          keyPath: String,
                          to value: Any,
                          preset: SpringPreset,
                          reduceMotion: Bool,
                          basicDuration: CFTimeInterval? = nil) {
    guard let layer else { return }

    let fromValue = layer.presentation()?.value(forKeyPath: keyPath) ?? layer.value(forKeyPath: keyPath)
    let boxedFrom = boxedAnimationValue(fromValue)
    let boxedTo = boxedAnimationValue(value)

    CATransaction.begin()
    CATransaction.setDisableActions(true)
    switch keyPath {
    case "transform":
        if let t = value as? CATransform3D { layer.transform = t }
        else if let v = value as? NSValue { layer.transform = v.caTransform3DValue }
    case "shadowOpacity":
        if let v = value as? CGFloat { layer.shadowOpacity = Float(v) }
        else if let v = value as? Float { layer.shadowOpacity = v }
        else if let v = value as? NSNumber { layer.shadowOpacity = v.floatValue }
    case "shadowRadius":
        if let v = value as? CGFloat { layer.shadowRadius = v }
        else if let v = value as? NSNumber { layer.shadowRadius = CGFloat(truncating: v) }
    case "shadowOffset":
        if let v = value as? CGSize { layer.shadowOffset = v }
        else if let v = value as? NSValue { layer.shadowOffset = v.sizeValue }
    case "opacity":
        if let v = value as? CGFloat { layer.opacity = Float(v) }
        else if let v = value as? Float { layer.opacity = v }
        else if let v = value as? NSNumber { layer.opacity = v.floatValue }
    default:
        layer.setValue(value, forKeyPath: keyPath)
    }
    CATransaction.commit()

    if reduceMotion {
        let basic = CABasicAnimation(keyPath: keyPath)
        basic.fromValue = boxedFrom
        basic.toValue = boxedTo
        basic.duration = (basicDuration ?? 0.18) * 0.75
        basic.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        layer.add(basic, forKey: "basic_\(keyPath)")
        return
    }

    let spec = springSpec(for: preset)
    let spring = CASpringAnimation(keyPath: keyPath)
    spring.mass = spec.mass
    spring.stiffness = spec.stiffness
    spring.damping = spec.damping
    spring.initialVelocity = spec.initialVelocity
    spring.fromValue = boxedFrom
    spring.toValue = boxedTo
    spring.duration = min(spring.settlingDuration, spec.settleCap)
    layer.add(spring, forKey: "spring_\(keyPath)")
}

// MARK: - SidebarAnimator (left sidebar slide)

private final class SidebarAnimator {
    private weak var owner: PickerWindowController?
    private var preparedLeftTargetWidth: CGFloat?
    private var preparedLeftOpeningFromCollapsed: Bool?

    init(owner: PickerWindowController) {
        self.owner = owner
    }

    func prepare(leftTargetWidth: CGFloat?, leftOpeningFromCollapsed: Bool?) {
        if let w = leftTargetWidth { preparedLeftTargetWidth = w }
        if let o = leftOpeningFromCollapsed { preparedLeftOpeningFromCollapsed = o }
    }

    func animateLeft(show: Bool, animated: Bool, completion: @escaping () -> Void) {
        guard let owner else { completion(); return }

        let reduceMotion = owner.shouldReduceMotion || !animated
        let targetWidth = preparedLeftTargetWidth ?? owner.leftContainer.frame.width
        let openingFromCollapsed = preparedLeftOpeningFromCollapsed ?? (show && owner.leftContainer.frame.width < 2)
        preparedLeftTargetWidth = nil
        preparedLeftOpeningFromCollapsed = nil

        owner.cancelSplitDividerSpringAnimation()

        // Views that must move in lock-step: glass card, background underlay, edge glow, search bar.
        var leftViews: [NSView] = [owner.leftContainer, owner.searchContainer]
        if let bg = owner.leftCardBackgroundImageView { leftViews.append(bg) }
        if let glow = owner.leftCardGlowView { leftViews.append(glow) }
        leftViews.forEach { $0.wantsLayer = true }

        let distance = max(CGFloat(0), show ? targetWidth : owner.leftContainer.frame.width)
        let offscreen = CATransform3DMakeTranslation(-distance, 0, 0)
        let identity = CATransform3DIdentity
        let toTransform: CATransform3D = show ? identity : offscreen

        let hidePreset: SpringPreset = .panelTransition   // near-critical, no overshoot
        let showPreset: SpringPreset = .hoverBounce       // gentle, slightly lively
        let transformPreset = show ? showPreset : hidePreset
        let spec = springSpec(for: transformPreset)
        let settle = spec.settleCap

        func applyTransform(_ t: CATransform3D) {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            leftViews.forEach { $0.layer?.transform = t }
            CATransaction.commit()
        }

        if openingFromCollapsed {
            applyTransform(offscreen)
        }

        if reduceMotion {
            owner.splitView.setPosition(targetWidth, ofDividerAt: 0)
            owner.splitView.adjustSubviews()
            owner.updateSplitDividerHandleFrame()
            applyTransform(toTransform)
            completion()
            return
        }

        leftViews.forEach { view in
            guard let layer = view.layer else { return }
            layer.shouldRasterize = true
            layer.rasterizationScale = view.window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0
        }
        // Divider handling: use the same spring preset as the panel so divider + viewer stay in sync.
        owner.animateSplitViewDivider(to: targetWidth, preset: transformPreset) {
            if !show { owner.splitView.adjustSubviews() }
            completion()
        }

        for (idx, view) in leftViews.enumerated() {
            guard let layer = view.layer else { continue }
            let from: CATransform3D = {
                if openingFromCollapsed { return offscreen }
                return layer.presentation()?.transform ?? layer.transform
            }()
            let key = "sidebar_slide_transform_\(idx)"
            animateTransform(layer,
                             from: from,
                             to: toTransform,
                             preset: transformPreset,
                             reduceMotion: false,
                             key: key)
        }

        let clearTime = settle + 0.02
        DispatchQueue.main.asyncAfter(deadline: .now() + clearTime) {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            if !show {
                owner.splitView.setPosition(targetWidth, ofDividerAt: 0)
                owner.splitView.adjustSubviews()
                owner.updateSplitDividerHandleFrame()
                applyTransform(identity)
            }
            CATransaction.commit()

            leftViews.forEach { view in
                view.layer?.shouldRasterize = false
            }
        }
    }

    private func animateTransform(_ layer: CALayer?,
                                  from: CATransform3D,
                                  to: CATransform3D,
                                  preset: SpringPreset,
                                  reduceMotion: Bool,
                                  key: String) {
        guard let layer else { return }

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.transform = to
        CATransaction.commit()

        layer.removeAnimation(forKey: key)

        if reduceMotion {
            let basic = CABasicAnimation(keyPath: "transform")
            basic.fromValue = NSValue(caTransform3D: from)
            basic.toValue = NSValue(caTransform3D: to)
            basic.duration = 0.16
            basic.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            layer.add(basic, forKey: key)
            return
        }

        let spec = springSpec(for: preset)
        let spring = CASpringAnimation(keyPath: "transform")
        spring.mass = spec.mass
        spring.stiffness = spec.stiffness
        spring.damping = spec.damping
        spring.initialVelocity = spec.initialVelocity
        spring.fromValue = NSValue(caTransform3D: from)
        spring.toValue = NSValue(caTransform3D: to)
        spring.duration = min(spring.settlingDuration, spec.settleCap)
        layer.add(spring, forKey: key)
    }
}

private func applyHoverBounce(to view: NSView?,
                              hovered: Bool,
                              animated: Bool,
                              reduceMotion: Bool) {
    guard let view else { return }
    view.wantsLayer = true
    guard let layer = view.layer else { return }

    let targetScale: CGFloat = hovered ? ROW_TEXT_HOVER_SCALE : 1.0
    let targetLift: CGFloat = hovered ? ROW_TEXT_HOVER_LIFT : 0.0
    var transform = CATransform3DIdentity
    transform = CATransform3DTranslate(transform, 0, targetLift, 0)
    transform = CATransform3DScale(transform, targetScale, targetScale, 1.0)

    guard animated else {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.transform = transform
        CATransaction.commit()
        return
    }

    animateLayer(layer,
                 keyPath: "transform",
                 to: transform,
                 preset: .microBounce,
                 reduceMotion: reduceMotion,
                 basicDuration: ROW_TEXT_HOVER_BOUNCE_DURATION)
}

// MARK: - Model

struct Paper: Equatable {
    let index: Int
    let title: String
    let authors: String
    let categories: String
    let dateLine: String
    let url: String
    let comments: String
    let abstractText: String
}

// MARK: - Share URL normalization (canonical arXiv /abs/)

private enum ArxivShareDebug {
    static let enabled: Bool = (ProcessInfo.processInfo.environment["ARXIV_SHARE_DEBUG"] == "1")
    static func log(_ message: String) {
        guard enabled else { return }
        NSLog("[Share] \(message)")
    }
}

private enum ArxivShareURL {
    // Accept both new-style and older arXiv identifiers.
    private static let newStylePattern = #"\b\d{4}\.\d{4,5}(v\d+)?\b"#
    private static let oldStylePattern = #"\b[a-z-]+(\.[A-Z]{2})?/\d{7}(v\d+)?\b"#

    static func canonicalAbsURL(from maybeURL: URL?) -> URL? {
        guard let url = maybeURL else { return nil }
        if url.isFileURL { return nil }
        if let canonical = canonicalAbsURL(fromArxivHostURL: url) { return canonical }
        if let id = extractArxivIdentifier(from: url.absoluteString) {
            return URL(string: "https://arxiv.org/abs/\(id)")
        }
        return nil
    }

    static func canonicalAbsURL(from maybeString: String?) -> URL? {
        guard let raw = maybeString?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return nil }
        if let url = URL(string: raw), let canonical = canonicalAbsURL(from: url) {
            return canonical
        }
        if let id = extractArxivIdentifier(from: raw) {
            return URL(string: "https://arxiv.org/abs/\(id)")
        }
        return nil
    }

    private static func canonicalAbsURL(fromArxivHostURL url: URL) -> URL? {
        guard let comps = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let host = comps.host?.lowercased(), host.hasSuffix("arxiv.org") else {
            return nil
        }

        let path = comps.path
        if path.lowercased().hasPrefix("/abs/") {
            let id = String(path.dropFirst("/abs/".count)).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            guard !id.isEmpty else { return nil }
            guard let canonical = URL(string: "https://arxiv.org/abs/\(id)") else { return nil }
            return canonical
        }
        if path.lowercased().hasPrefix("/pdf/") {
            var rest = String(path.dropFirst("/pdf/".count))
            rest = rest.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            if rest.lowercased().hasSuffix(".pdf") {
                rest = String(rest.dropLast(4))
            }
            rest = rest.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !rest.isEmpty else { return nil }
            guard isValidArxivIdentifier(rest) else { return nil }
            return URL(string: "https://arxiv.org/abs/\(rest)")
        }

        // Some arxiv.org variants embed the id elsewhere; fallback to regex extraction.
        if let id = extractArxivIdentifier(from: url.absoluteString) {
            return URL(string: "https://arxiv.org/abs/\(id)")
        }
        return nil
    }

    static func extractArxivIdentifier(from text: String) -> String? {
        let candidates = [newStylePattern, oldStylePattern]
        for pattern in candidates {
            if let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) {
                let range = NSRange(text.startIndex..<text.endIndex, in: text)
                if let match = re.firstMatch(in: text, options: [], range: range),
                   let r = Range(match.range, in: text) {
                    let id = String(text[r])
                    if isValidArxivIdentifier(id) { return id }
                }
            }
        }
        return nil
    }

    private static func isValidArxivIdentifier(_ id: String) -> Bool {
        // New-style: yymm.nnnn(n) with optional vN. Validate month range.
        if let re = try? NSRegularExpression(pattern: #"^(\d{4})\.(\d{4,5})(v\d+)?$"#, options: []) {
            let s = id.trimmingCharacters(in: .whitespacesAndNewlines)
            let range = NSRange(s.startIndex..<s.endIndex, in: s)
            if let m = re.firstMatch(in: s, options: [], range: range), m.numberOfRanges >= 3,
               let yymmRange = Range(m.range(at: 1), in: s) {
                let yymm = String(s[yymmRange])
                if yymm.count == 4 {
                    let mmStr = String(yymm.suffix(2))
                    if let mm = Int(mmStr), (1...12).contains(mm) {
                        return true
                    }
                }
            }
        }

        // Old-style: archive[.SUB]/yymmnnn with optional vN.
        if let re = try? NSRegularExpression(pattern: #"^[a-z-]+(\.[A-Z]{2})?/\d{7}(v\d+)?$"#, options: [.caseInsensitive]) {
            let s = id.trimmingCharacters(in: .whitespacesAndNewlines)
            let range = NSRange(s.startIndex..<s.endIndex, in: s)
            return (re.firstMatch(in: s, options: [], range: range) != nil)
        }
        return false
    }
}

private func buildMailtoURL(subject: String, body: String) -> URL? {
    var comps = URLComponents()
    comps.scheme = "mailto"
    comps.path = ""
    comps.queryItems = [
        URLQueryItem(name: "subject", value: subject),
        URLQueryItem(name: "body", value: body)
    ]
    return comps.url
}

private enum MailShareDiagnostics {
    static let forceAppleScript: Bool = (ProcessInfo.processInfo.environment["ARXIV_SHARE_FORCE_APPLESCRIPT"] == "1")

    static func log(_ message: String) {
        ArxivShareDebug.log(message)
    }
}

private func mailAppRunning() -> NSRunningApplication? {
    NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.mail").first
}

@available(macOS 10.15, *)
private func ensureMailLaunchedForShare(activates: Bool, completion: (() -> Void)? = nil) {
    let bundleID = "com.apple.mail"
    if mailAppRunning() != nil {
        completion?()
        return
    }
    guard let mailURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleID) else {
        completion?()
        return
    }
    let config = NSWorkspace.OpenConfiguration()
    config.activates = activates
    NSWorkspace.shared.openApplication(at: mailURL, configuration: config) { _, _ in
        completion?()
    }
}

private func activateMailAppForShare() {
    let bundleID = "com.apple.mail"
    if let running = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).first {
        // Avoid `.activateAllWindows` which can un-minimize the viewer and cause visible flicker.
        // We prefer an explicit one-shot AppleScript activation+minimize sequence after composing.
        running.activate(options: [])
        return
    }

    guard let mailURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleID) else {
        return
    }

    if #available(macOS 10.15, *) {
        let config = NSWorkspace.OpenConfiguration()
        config.activates = true
        NSWorkspace.shared.openApplication(at: mailURL, configuration: config) { app, _ in
            app?.activate(options: [])
        }
    } else {
        // Best-effort fallback for older systems.
        NSWorkspace.shared.open(mailURL)
    }
}

private func mailActivateAndMinimizeViewerOnceAppleScript(subject: String) -> String {
    // One-shot stabilization script:
    // - activates Mail (to guarantee the compose window is visible)
    // - waits a beat so the compose window exists
    // - minimizes all Mail windows except the compose window ("New Message" / subject)
    let subj = appleScriptStringLiteral(subject)
    return """
    tell application \"Mail\"
        if it is not running then
            launch
        end if
        activate
        delay 0.08

        set composeWin to missing value
        try
            set composeWin to first window whose name contains \"New Message\"
        end try
        if composeWin is missing value then
            try
                set composeWin to first window whose name contains \(subj)
            end try
        end if

        repeat with w in windows
            if composeWin is not missing value and w is not composeWin then
                try
                    if miniaturized of w is false then set miniaturized of w to true
                end try
            end if
        end repeat

        if composeWin is not missing value then
            try
                set miniaturized of composeWin to false
                set index of composeWin to 1
            end try
        end if
    end tell
    """
}

private func mailShareBody(recipientName: String?, arxivAbsURL: String) -> String {
    let trimmed = (recipientName ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let name = trimmed.isEmpty ? "there" : trimmed
    // Requirement: exactly
    // Hey [recipient],
    // [arxiv link]
    // (with two line breaks)
    return "Hey \(name),\n\n\(arxivAbsURL)"
}

private func appleScriptStringLiteral(_ s: String) -> String {
    // AppleScript string escaping: backslash, quote, and newlines.
    var out = s
    out = out.replacingOccurrences(of: "\\", with: "\\\\")
    out = out.replacingOccurrences(of: "\"", with: "\\\"")
    out = out.replacingOccurrences(of: "\r\n", with: "\n")
    out = out.replacingOccurrences(of: "\r", with: "\n")
    out = out.replacingOccurrences(of: "\n", with: "\\n")
    return "\"\(out)\""
}

private func runAppleScriptAsync(_ source: String, label: String) {
    DispatchQueue.global(qos: .userInitiated).async {
        let start = monotonicNow()
        var errorDict: NSDictionary?
        let script = NSAppleScript(source: source)
        let result = script?.executeAndReturnError(&errorDict)
        let elapsedMs = Int(((monotonicNow() - start) * 1000.0).rounded())
        if let errorDict {
            MailShareDiagnostics.log("AppleScript(\(label)) error ms=\(elapsedMs) err=\(errorDict)")
        } else {
            _ = result
            MailShareDiagnostics.log("AppleScript(\(label)) ok ms=\(elapsedMs)")
        }
    }
}

private func mailComposeAppleScript(subject: String, body: String, toAddress: String?) -> String {
    let subj = appleScriptStringLiteral(subject)
    let content = appleScriptStringLiteral(body + "\n")
    let toAddr = appleScriptStringLiteral((toAddress ?? "").trimmingCharacters(in: .whitespacesAndNewlines))
    return """
    tell application \"Mail\"
        if it is not running then
            launch
        end if
        activate
        set newMessage to make new outgoing message with properties {subject:\(subj), content:\(content), visible:true}
        if \(toAddr) is not \"\" then
            try
                make new to recipient at end of to recipients of newMessage with properties {address:\(toAddr)}
            end try
        end if
        open newMessage
        delay 0.05
        -- IMPORTANT: Mail may keep a viewer window frontmost even after creating a new message.
        -- Heuristic: identify the compose window by title ("New Message" or subject substring).
        set composeWin to missing value
        try
            set composeWin to first window whose name contains "New Message"
        end try
        if composeWin is missing value then
            try
                set composeWin to first window whose name contains \(subj)
            end try
        end if
        if composeWin is missing value then
            try
                set composeWin to front window
            end try
        end if
        repeat with w in windows
            if w is not composeWin then
                try
                    set miniaturized of w to true
                end try
            end if
        end repeat
        try
            set miniaturized of composeWin to false
            set index of composeWin to 1
        end try
    end tell
    """
}

private func mailMinimizeNonFrontWindowsAppleScript() -> String {
    return """
    tell application \"Mail\"
        if it is not running then return
        try
            -- Prefer keeping a compose window visible if one exists.
            set keepWin to missing value
            try
                set keepWin to first window whose name contains \"New Message\"
            end try
            if keepWin is missing value then set keepWin to front window
            repeat with w in windows
                if w is not keepWin then
                    try
                        set miniaturized of w to true
                    end try
                end if
            end repeat
            try
                set miniaturized of keepWin to false
                set index of keepWin to 1
            end try
        end try
    end tell
    """
}

private func runShareSelfTestIfEnabled() {
    guard ProcessInfo.processInfo.environment["ARXIV_SHARE_SELF_TEST"] == "1" else { return }

    // This self-test must not open Mail or invoke sharing; it only validates string generation and script syntax.
    let recipientName = ProcessInfo.processInfo.environment["ARXIV_SHARE_TEST_RECIPIENT_NAME"]
    let url = ProcessInfo.processInfo.environment["ARXIV_SHARE_TEST_URL"] ?? "https://arxiv.org/abs/1234.56789"
    let expectedRecipient = (recipientName ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "there" : recipientName!.trimmingCharacters(in: .whitespacesAndNewlines)
    let expectedBody = "Hey \(expectedRecipient),\n\n\(url)"
    let actualBody = mailShareBody(recipientName: recipientName, arxivAbsURL: url)

    var failures = 0
    if actualBody != expectedBody {
        failures += 1
        MailShareDiagnostics.log("self_test_body_mismatch expected=\(expectedBody.debugDescription) actual=\(actualBody.debugDescription)")
    } else {
        MailShareDiagnostics.log("self_test_body_ok")
    }

    let hasComposeService = (NSSharingService(named: .composeEmail) != nil)
    MailShareDiagnostics.log("self_test_sharing_service_available=\(hasComposeService)")

    // Compile (do not execute) the AppleScript fallback to catch syntax errors early.
    let scriptSource = mailComposeAppleScript(subject: "arXiv paper", body: actualBody, toAddress: nil)
    let script = NSAppleScript(source: scriptSource)
    var compileError: NSDictionary?
    let compiledOk = (script?.compileAndReturnError(&compileError) ?? false)
    if !compiledOk {
        failures += 1
        MailShareDiagnostics.log("self_test_applescript_compile_error err=\(compileError ?? [:])")
    } else {
        MailShareDiagnostics.log("self_test_applescript_compile_ok")
    }

    MailShareDiagnostics.log("self_test_done failures=\(failures)")
    // Exit deterministically so this can be used as a launch-check style harness.
    Darwin.exit(failures == 0 ? 0 : 2)
}

struct Payload {
    let papers: [Paper]
    let keywords: [String]
    let recipientName: String?
    let recipientEmail: String?
}

private struct PaperKey: Hashable {
    let index: Int
    let url: String
}

private extension Paper {
    var key: PaperKey { PaperKey(index: index, url: url) }
}

private final class PublicationStore {
    private(set) var all: [Paper] = []
    private(set) var filtered: [Paper] = []

    func setAll(_ papers: [Paper]) {
        all = papers
        filtered = papers
    }

    func setFiltered(_ papers: [Paper]) {
        filtered = papers
    }
}

// Maps filtered-list indices to visible “pages”.
//
// Pagination mapping contract:
// - Pages are computed greedily to fit within the available height for the left list.
// - Page boundaries are stable for a given available height + wrap width because they depend only on measured row heights.
// - Table rows (header + page slice) always map back to exactly one filtered index via `globalIndex(forTableRow:)`.
private struct Paginator {
    private(set) var pageRanges: [Range<Int>] = []

    var pageCount: Int { pageRanges.count }

    func range(forPage pageIndex: Int) -> Range<Int> {
        guard !pageRanges.isEmpty else { return 0..<0 }
        let p = max(0, min(pageRanges.count - 1, pageIndex))
        return pageRanges[p]
    }

    func pageIndex(containingGlobalFilteredIndex index: Int) -> Int? {
        guard index >= 0 else { return nil }
        for (i, r) in pageRanges.enumerated() where r.contains(index) { return i }
        return nil
    }

    mutating func recompute(itemCount: Int,
                            availableHeight: CGFloat,
                            minTopBottomInset: CGFloat,
                            headerRowHeight: CGFloat,
                            rowHeightForFilteredIndex: (Int) -> CGFloat) {
        pageRanges.removeAll(keepingCapacity: true)
        guard itemCount > 0 else { return }

        // Account for symmetric padding inside the scroll view so we never overflow the visible card.
        let contentMax = max(0, availableHeight - (2 * minTopBottomInset))
        guard contentMax > 1 else {
            pageRanges = [0..<min(1, itemCount)]
            return
        }

        var start = 0
        while start < itemCount {
            var used = headerRowHeight
            var end = start

            while end < itemCount {
                let rh = max(1, rowHeightForFilteredIndex(end))
                if end == start {
                    used += rh
                    end += 1
                    if used > contentMax {
                        // Always include at least one row per page, even if it is taller than the viewport.
                        break
                    }
                } else {
                    if used + rh <= contentMax {
                        used += rh
                        end += 1
                    } else {
                        break
                    }
                }
            }

            if end <= start { end = min(itemCount, start + 1) }
            pageRanges.append(start..<end)
            start = end
        }
    }
}

private struct SearchSuggestion: Equatable {
    let paperKey: PaperKey
    let allIndex: Int
    let title: String
    let subtitle: String
    let score: Double
}

private enum MenuItemKind: Equatable {
    case summary
    case separator
    case page
    case action
}

private struct MenuItem: Equatable {
    let kind: MenuItemKind
    let title: String
    let isEnabled: Bool
    let isChecked: Bool
    let actionIndex: Int?

    var isSelectable: Bool {
        isEnabled && kind != .summary && kind != .separator
    }
}

private final class SearchIndex {
    private struct Doc {
        let key: PaperKey
        let allIndex: Int
        let title: String
        let subtitle: String
        let haystack: String
    }

    private var docs: [Doc] = []

    func rebuild(from all: [Paper]) {
        docs = all.enumerated().map { (i, p) in
            let title = decodeTeXAccents(p.title).replacingOccurrences(of: "\n", with: " ")
            let authorYear = decodeTeXAccents(leftAuthorYearText(paper: p)).replacingOccurrences(of: "\n", with: " ")
            let cats = decodeTeXAccents(stripLeadingLabel(p.categories, label: "Categories")).replacingOccurrences(of: "\n", with: " ")
            let subtitle = authorYear.isEmpty ? cats : authorYear
            let abs = decodeTeXAccents(p.abstractText).replacingOccurrences(of: "\n", with: " ")
            let hay = "\(title) \(authorYear) \(cats) \(abs)".lowercased()
            return Doc(key: p.key, allIndex: i, title: title, subtitle: subtitle, haystack: hay)
        }
    }

    func suggest(query raw: String, maxResults: Int) -> [SearchSuggestion] {
        let q = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return [] }

        // Simple Safari-like scoring:
        // - Prefer title prefix, then title contains, then other-field contains.
        // - Earlier matches rank higher; shorter titles get a small boost.
        var matches: [SearchSuggestion] = []
        matches.reserveCapacity(min(maxResults, 12))

        for d in docs {
            guard let range = d.haystack.range(of: q) else { continue }
            let pos = d.haystack.distance(from: d.haystack.startIndex, to: range.lowerBound)

            let titleLower = d.title.lowercased()
            let titlePos = titleLower.range(of: q).map { titleLower.distance(from: titleLower.startIndex, to: $0.lowerBound) }
            let titlePrefixBoost: Double = titleLower.hasPrefix(q) ? 1000 : 0
            let titleContainsBoost: Double = titlePos != nil ? 250 : 0
            let positionPenalty: Double = Double(min(600, pos))
            let lengthBoost: Double = Double(max(0, 90 - min(90, d.title.count))) * 0.15

            let score = titlePrefixBoost + titleContainsBoost + lengthBoost - positionPenalty
            matches.append(SearchSuggestion(paperKey: d.key,
                                           allIndex: d.allIndex,
                                           title: d.title,
                                           subtitle: d.subtitle,
                                           score: score))
        }

        matches.sort { a, b in
            if a.score != b.score { return a.score > b.score }
            if a.title.count != b.title.count { return a.title.count < b.title.count }
            return a.allIndex < b.allIndex
        }

        if matches.count > maxResults { matches.removeLast(matches.count - maxResults) }
        return matches
    }
}


// MARK: - Utilities

private func monotonicNow() -> CFTimeInterval {
    CACurrentMediaTime()
}

private func perfLog(_ message: String) {
    NSLog("[Perf] \(message)")
}

private func sha256Hex(_ string: String) -> String {
    let data = Data(string.utf8)
    let digest = SHA256.hash(data: data)
    return digest.map { String(format: "%02x", $0) }.joined()
}

private func pdfMimeTypeLooksValid(_ mimeType: String?) -> Bool {
    guard let raw = mimeType?.lowercased(), !raw.isEmpty else { return false }
    if raw.contains("pdf") { return true }
    return raw == "application/octet-stream"
}

private func dataHasPDFHeader(_ data: Data) -> Bool {
    let prefix = data.prefix(5)
    return prefix == Data("%PDF-".utf8)
}

private func fileHasPDFHeader(_ url: URL) -> Bool {
    guard let handle = try? FileHandle(forReadingFrom: url) else { return false }
    defer { try? handle.close() }
    let data = handle.readData(ofLength: 5)
    return dataHasPDFHeader(data)
}

private func stripLeadingLabel(_ value: String, label: String) -> String {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    let lower = trimmed.lowercased()
    let prefix = (label.lowercased() + ":")
    if lower.hasPrefix(prefix) {
        return trimmed.dropFirst(prefix.count).trimmingCharacters(in: .whitespacesAndNewlines)
    }
    return trimmed
}

private func regexReplace(_ s: String,
                          _ pattern: String,
                          _ repl: String,
                          options: NSRegularExpression.Options = []) -> String {
    guard let re = try? NSRegularExpression(pattern: pattern, options: options) else { return s }
    let range = NSRange(location: 0, length: (s as NSString).length)
    return re.stringByReplacingMatches(in: s, options: [], range: range, withTemplate: repl)
}

private func htmlEscape(_ s: String) -> String {
    var out = s
    out = out.replacingOccurrences(of: "&", with: "&amp;")
    out = out.replacingOccurrences(of: "<", with: "&lt;")
    out = out.replacingOccurrences(of: ">", with: "&gt;")
    out = out.replacingOccurrences(of: "\"", with: "&quot;")
    return out
}

private func jsStringEscape(_ s: String) -> String {
    var out = s
    out = out.replacingOccurrences(of: "\\", with: "\\\\")
    out = out.replacingOccurrences(of: "\"", with: "\\\"")
    out = out.replacingOccurrences(of: "\n", with: "\\n")
    out = out.replacingOccurrences(of: "\r", with: "")
    out = out.replacingOccurrences(of: "\u{2028}", with: "\\u2028")
    out = out.replacingOccurrences(of: "\u{2029}", with: "\\u2029")
    return out
}

private func cssRGBA(_ color: NSColor) -> String {
    let c = (color.usingColorSpace(.deviceRGB) ?? color)
    return String(format: "rgba(%.0f,%.0f,%.0f,%.3f)",
                  (c.redComponent * 255.0),
                  (c.greenComponent * 255.0),
                  (c.blueComponent * 255.0),
                  c.alphaComponent)
}

private func colorFromHex(_ hex: String) -> NSColor? {
    let trimmed = hex.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.hasPrefix("#") else { return nil }
    let hexBody = String(trimmed.dropFirst())
    guard hexBody.count == 6 || hexBody.count == 8 else { return nil }

    var value: UInt64 = 0
    guard Scanner(string: hexBody).scanHexInt64(&value) else { return nil }

    let r: CGFloat
    let g: CGFloat
    let b: CGFloat
    let a: CGFloat

    if hexBody.count == 6 {
        r = CGFloat((value >> 16) & 0xFF) / 255.0
        g = CGFloat((value >> 8) & 0xFF) / 255.0
        b = CGFloat(value & 0xFF) / 255.0
        a = 1.0
    } else {
        r = CGFloat((value >> 24) & 0xFF) / 255.0
        g = CGFloat((value >> 16) & 0xFF) / 255.0
        b = CGFloat((value >> 8) & 0xFF) / 255.0
        a = CGFloat(value & 0xFF) / 255.0
    }

    return NSColor(srgbRed: r, green: g, blue: b, alpha: a)
}

private func relativeLuminance(_ color: NSColor) -> CGFloat {
    let c = (color.usingColorSpace(.deviceRGB) ?? color)
    func channel(_ v: CGFloat) -> CGFloat {
        if v <= 0.03928 { return v / 12.92 }
        return CGFloat(pow(Double((v + 0.055) / 1.055), 2.4))
    }
    let r = channel(c.redComponent)
    let g = channel(c.greenComponent)
    let b = channel(c.blueComponent)
    return (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
}

private func contrastRatio(_ a: NSColor, _ b: NSColor) -> CGFloat {
    let l1 = relativeLuminance(a) + 0.05
    let l2 = relativeLuminance(b) + 0.05
    return max(l1, l2) / min(l1, l2)
}

private func blend(_ a: NSColor, _ b: NSColor, t: CGFloat) -> NSColor {
    let ca = (a.usingColorSpace(.deviceRGB) ?? a)
    let cb = (b.usingColorSpace(.deviceRGB) ?? b)
    let tt = max(0.0, min(1.0, t))
    let r = ca.redComponent + (cb.redComponent - ca.redComponent) * tt
    let g = ca.greenComponent + (cb.greenComponent - ca.greenComponent) * tt
    let b = ca.blueComponent + (cb.blueComponent - ca.blueComponent) * tt
    let aComp = ca.alphaComponent + (cb.alphaComponent - ca.alphaComponent) * tt
    return NSColor(srgbRed: r, green: g, blue: b, alpha: aComp)
}

private func adjustedForContrast(_ color: NSColor, background: NSColor, target: CGFloat) -> NSColor {
    var candidate = color
    var ratio = contrastRatio(candidate, background)
    guard ratio < target else { return candidate }

    let toward = relativeLuminance(background) > 0.5 ? NSColor.black : NSColor.white
    var t: CGFloat = 0.0
    while ratio < target && t < 0.85 {
        t += 0.08
        candidate = blend(color, toward, t: t)
        ratio = contrastRatio(candidate, background)
    }
    return candidate
}

private func srgbToLinear(_ v: CGFloat) -> CGFloat {
    let x = max(0.0, min(1.0, v))
    if x <= 0.04045 { return x / 12.92 }
    return CGFloat(pow(Double((x + 0.055) / 1.055), 2.4))
}

private func linearToSrgb(_ v: CGFloat) -> CGFloat {
    let x = max(0.0, min(1.0, v))
    if x <= 0.0031308 { return x * 12.92 }
    return CGFloat(1.055 * pow(Double(x), 1.0 / 2.4) - 0.055)
}

private func compositeRGBLinear(sourceRGB: (CGFloat, CGFloat, CGFloat),
                               sourceAlpha: CGFloat,
                               destRGB: (CGFloat, CGFloat, CGFloat)) -> (CGFloat, CGFloat, CGFloat) {
    let a = max(0.0, min(1.0, sourceAlpha))
    let r = a * sourceRGB.0 + (1.0 - a) * destRGB.0
    let g = a * sourceRGB.1 + (1.0 - a) * destRGB.1
    let b = a * sourceRGB.2 + (1.0 - a) * destRGB.2
    return (r, g, b)
}

private func inverseCompositeRGBLinear(targetRGB: (CGFloat, CGFloat, CGFloat),
                                      underRGB: (CGFloat, CGFloat, CGFloat),
                                      sourceAlpha: CGFloat) -> (CGFloat, CGFloat, CGFloat) {
    // Solve C_tint_needed = (C_target - (1 - a) * C_under) / a per channel.
    let a = max(0.0001, min(1.0, sourceAlpha))
    let r = (targetRGB.0 - (1.0 - a) * underRGB.0) / a
    let g = (targetRGB.1 - (1.0 - a) * underRGB.1) / a
    let b = (targetRGB.2 - (1.0 - a) * underRGB.2) / a
    return (max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b)))
}

private func averageColor(from image: NSImage, sampleSize: Int = 16) -> NSColor? {
    guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }
    let width = max(1, sampleSize)
    let height = max(1, sampleSize)
    let bytesPerPixel = 4
    let bytesPerRow = width * bytesPerPixel
    var data = [UInt8](repeating: 0, count: width * height * bytesPerPixel)
    let space = CGColorSpaceCreateDeviceRGB()
    guard let ctx = CGContext(data: &data,
                              width: width,
                              height: height,
                              bitsPerComponent: 8,
                              bytesPerRow: bytesPerRow,
                              space: space,
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        return nil
    }
    ctx.interpolationQuality = .medium
    ctx.draw(cgImage, in: CGRect(x: 0, y: 0, width: width, height: height))

    var r: CGFloat = 0
    var g: CGFloat = 0
    var b: CGFloat = 0
    var aSum: CGFloat = 0

    for i in stride(from: 0, to: data.count, by: 4) {
        let a = CGFloat(data[i + 3]) / 255.0
        if a <= 0 { continue }
        r += (CGFloat(data[i]) / 255.0) * a
        g += (CGFloat(data[i + 1]) / 255.0) * a
        b += (CGFloat(data[i + 2]) / 255.0) * a
        aSum += a
    }

    guard aSum > 0 else { return nil }
    return NSColor(srgbRed: r / aSum, green: g / aSum, blue: b / aSum, alpha: 1.0)
}

private func rgbToHSV(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat) -> (h: CGFloat, s: CGFloat, v: CGFloat) {
    let maxV = max(r, max(g, b))
    let minV = min(r, min(g, b))
    let delta = maxV - minV
    let v = maxV
    let s: CGFloat = (maxV <= 0.00001) ? 0.0 : (delta / maxV)
    var h: CGFloat = 0.0
    if delta > 0.00001 {
        if maxV == r {
            h = (g - b) / delta
        } else if maxV == g {
            h = 2.0 + (b - r) / delta
        } else {
            h = 4.0 + (r - g) / delta
        }
        h /= 6.0
        if h < 0 { h += 1.0 }
        if h >= 1.0 { h -= 1.0 }
    }
    return (h, s, v)
}

private func dominantHueColor(from image: NSImage, sampleSize: Int = 72, hueBins: Int = 36) -> NSColor? {
    // Dominant-hue estimate (for titlebar tinting): downsample, hue-histogram (weighted), then average RGB of the winning bin.
    guard hueBins > 0 else { return nil }
    guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }

    let width = max(1, sampleSize)
    let height = max(1, sampleSize)
    let bytesPerPixel = 4
    let bytesPerRow = width * bytesPerPixel
    var data = [UInt8](repeating: 0, count: width * height * bytesPerPixel)
    let space = CGColorSpaceCreateDeviceRGB()
    guard let ctx = CGContext(data: &data,
                              width: width,
                              height: height,
                              bitsPerComponent: 8,
                              bytesPerRow: bytesPerRow,
                              space: space,
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        return nil
    }
    ctx.interpolationQuality = .medium
    ctx.draw(cgImage, in: CGRect(x: 0, y: 0, width: width, height: height))

    var binWeights = [Double](repeating: 0.0, count: hueBins)
    var rSums = [Double](repeating: 0.0, count: hueBins)
    var gSums = [Double](repeating: 0.0, count: hueBins)
    var bSums = [Double](repeating: 0.0, count: hueBins)

    for i in stride(from: 0, to: data.count, by: 4) {
        let a = CGFloat(data[i + 3]) / 255.0
        if a < 0.05 { continue }

        let r = CGFloat(data[i]) / 255.0
        let g = CGFloat(data[i + 1]) / 255.0
        let b = CGFloat(data[i + 2]) / 255.0
        let hsv = rgbToHSV(r, g, b)

        // Ignore near-grayscale pixels where hue is unstable.
        if hsv.s < 0.08 || hsv.v < 0.05 { continue }

        let hue = max(0.0, min(0.999999, hsv.h))
        let bin = max(0, min(hueBins - 1, Int(hue * CGFloat(hueBins))))
        let weight = Double(a * hsv.s * (0.25 + 0.75 * hsv.v))

        binWeights[bin] += weight
        rSums[bin] += Double(r) * weight
        gSums[bin] += Double(g) * weight
        bSums[bin] += Double(b) * weight
    }

    guard let maxIndex = binWeights.enumerated().max(by: { $0.element < $1.element })?.offset else { return nil }
    let w = binWeights[maxIndex]
    if w <= 0.00001 {
        // Fall back to average color when there isn't a meaningful dominant hue (e.g., grayscale wallpaper).
        return averageColor(from: image, sampleSize: max(12, sampleSize / 6))
    }
    let rr = CGFloat(rSums[maxIndex] / w)
    let gg = CGFloat(gSums[maxIndex] / w)
    let bb = CGFloat(bSums[maxIndex] / w)
    return NSColor(srgbRed: rr, green: gg, blue: bb, alpha: 1.0)
}

private struct TextPalette {
    let primary: NSColor
    let secondary: NSColor
    let muted: NSColor
    let link: NSColor
    let rule: NSColor
    let codeText: NSColor
    let codeBackground: NSColor
}

private func adaptiveTextPalette(baseColor: NSColor, linkHex: String) -> TextPalette {
    let base = baseColor.usingColorSpace(.deviceRGB) ?? baseColor
    let isLight = relativeLuminance(base) > 0.55

    let primarySeed = isLight
        ? NSColor(srgbRed: 0.10, green: 0.11, blue: 0.12, alpha: 1.0)
        : NSColor(srgbRed: 0.94, green: 0.94, blue: 0.95, alpha: 1.0)
    let secondarySeed = isLight
        ? NSColor(srgbRed: 0.26, green: 0.28, blue: 0.30, alpha: 1.0)
        : NSColor(srgbRed: 0.82, green: 0.83, blue: 0.84, alpha: 1.0)
    let mutedSeed = isLight
        ? NSColor(srgbRed: 0.39, green: 0.40, blue: 0.42, alpha: 1.0)
        : NSColor(srgbRed: 0.70, green: 0.71, blue: 0.72, alpha: 1.0)
    let linkSeed = colorFromHex(linkHex)
        ?? (isLight
            ? NSColor(srgbRed: 0.17, green: 0.43, blue: 0.86, alpha: 1.0)
            : NSColor(srgbRed: 0.36, green: 0.62, blue: 0.96, alpha: 1.0))
    let ruleSeed = (isLight ? NSColor.black : NSColor.white).withAlphaComponent(isLight ? 0.14 : 0.18)
    let codeBackground = (isLight ? NSColor.black : NSColor.white).withAlphaComponent(isLight ? 0.06 : 0.10)
    let codeTextSeed = isLight
        ? NSColor(srgbRed: 0.16, green: 0.18, blue: 0.20, alpha: 1.0)
        : NSColor(srgbRed: 0.88, green: 0.89, blue: 0.90, alpha: 1.0)

    return TextPalette(
        primary: adjustedForContrast(primarySeed, background: base, target: 4.5),
        secondary: adjustedForContrast(secondarySeed, background: base, target: 3.0),
        muted: adjustedForContrast(mutedSeed, background: base, target: 2.5),
        link: adjustedForContrast(linkSeed, background: base, target: 4.5),
        rule: ruleSeed,
        codeText: adjustedForContrast(codeTextSeed, background: base, target: 4.5),
        codeBackground: codeBackground
    )
}

private func loadBackgroundImage(from path: String) -> NSImage? {
    let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    var isDir: ObjCBool = false
    guard FileManager.default.fileExists(atPath: trimmed, isDirectory: &isDir), !isDir.boolValue else {
        NSLog("[Background] Image file not found: \(trimmed)")
        return nil
    }
    // Load via ImageIO so we can optionally downsample large still images to keep startup smooth.
    return loadBackgroundImage(from: trimmed, maxPixelDim: nil, preserveAnimated: true)
}

private func loadBackgroundImage(from trimmedPath: String,
                                 maxPixelDim: Int?,
                                 preserveAnimated: Bool) -> NSImage? {
    let url = URL(fileURLWithPath: trimmedPath)
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else {
        // Fallback to NSImage for any unsupported formats.
        return NSImage(contentsOfFile: trimmedPath)
    }

    let frameCount = CGImageSourceGetCount(src)
    if preserveAnimated, frameCount > 1 {
        // Preserve animation (GIF/APNG): NSImage keeps frames; downsampling animated images robustly is non-trivial.
        return NSImage(contentsOfFile: trimmedPath)
    }

    var pixelW = 0
    var pixelH = 0
    if let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any] {
        pixelW = (props[kCGImagePropertyPixelWidth] as? Int) ?? 0
        pixelH = (props[kCGImagePropertyPixelHeight] as? Int) ?? 0
    }

    let maxDim = max(pixelW, pixelH)
    let requestedCap = maxPixelDim ?? maxDim
    let hardCap = max(0, BACKGROUND_IMAGE_HARD_MAX_PIXEL_DIM)
    let effectiveCap = (BACKGROUND_IMAGE_DOWNSCALE_ENABLED && hardCap > 0) ? min(requestedCap, hardCap) : maxDim

    // If the image is already within bounds (or we can't read pixel size), use the simple path.
    if maxDim <= 0 || effectiveCap <= 0 || maxDim <= effectiveCap {
        let image = NSImage(contentsOfFile: trimmedPath)
        if image == nil { NSLog("[Background] Failed to load image: \(trimmedPath)") }
        return image
    }

    let options: [CFString: Any] = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceShouldCacheImmediately: true,
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: effectiveCap
    ]

    guard let thumb = CGImageSourceCreateThumbnailAtIndex(src, 0, options as CFDictionary) else {
        return NSImage(contentsOfFile: trimmedPath)
    }

    let out = NSImage(cgImage: thumb, size: NSSize(width: thumb.width, height: thumb.height))
    if out.size.width <= 0 || out.size.height <= 0 {
        NSLog("[Background] Image has invalid size after downsample: \(trimmedPath)")
        return nil
    }
    NSLog("[Background] Downsampled \(url.lastPathComponent) maxDim=\(maxDim) -> \(effectiveCap)")
    return out
}

private func recommendedBackgroundMaxPixelDim(for window: NSWindow?) -> Int? {
    // Enough pixels for crisp rendering at current backing scale, plus a small headroom for resizing.
    guard let window else { return nil }
    let scale = window.screen?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0
    let size = window.contentView?.bounds.size ?? window.frame.size
    let px = Int(ceil(max(size.width, size.height) * scale * 1.15))
    return max(512, px)
}

private func arxivID(fromAbsURL url: String) -> String? {
    let u = stripLeadingLabel(url, label: "URL")
        .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !u.isEmpty else { return nil }

    if let re = try? NSRegularExpression(pattern: #"arxiv\.org/abs/([^?#\s]+)"#, options: [.caseInsensitive]) {
        let ns = u as NSString
        let range = NSRange(location: 0, length: ns.length)
        if let m = re.firstMatch(in: u, range: range), m.numberOfRanges >= 2 {
            let id = ns.substring(with: m.range(at: 1))
            return id.trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }
    return nil
}

private func arxivPDFFromAbs(url: String) -> String? {
    guard let id = arxivID(fromAbsURL: url), !id.isEmpty else { return nil }
    return "https://arxiv.org/pdf/\(id).pdf"
}

// TeX accent decoding
private let texAccentMap: [String: String] = [
    "\\'A":"Á","\\'a":"á","\\'E":"É","\\'e":"é","\\'I":"Í","\\'i":"í","\\'O":"Ó","\\'o":"ó","\\'U":"Ú","\\'u":"ú","\\'Y":"Ý","\\'y":"ý",
    "\\`A":"À","\\`a":"à","\\`E":"È","\\`e":"è","\\`I":"Ì","\\`i":"ì","\\`O":"Ò","\\`o":"ò","\\`U":"Ù","\\`u":"ù",
    "\\^A":"Â","\\^a":"â","\\^E":"Ê","\\^e":"ê","\\^I":"Î","\\^i":"î","\\^O":"Ô","\\^o":"ô","\\^U":"Û","\\^u":"û",
    "\\\"A":"Ä","\\\"a":"ä","\\\"E":"Ë","\\\"e":"ë","\\\"I":"Ï","\\\"i":"ï","\\\"O":"Ö","\\\"o":"ö","\\\"U":"Ü","\\\"u":"ü","\\\"Y":"Ÿ","\\\"y":"ÿ",
    "\\~A":"Ã","\\~a":"ã","\\~N":"Ñ","\\~n":"ñ","\\~O":"Õ","\\~o":"õ",
    "\\cC":"Ç","\\cc":"ç"
]

private func decodeTeXAccents(_ s: String) -> String {
    var out = s
    for (k, v) in texAccentMap { out = out.replacingOccurrences(of: k, with: v) }
    out = out.replacingOccurrences(of: "\\\\'", with: "")
    out = out.replacingOccurrences(of: "\\'", with: "")
    return out
}

// Lightweight LaTeX → readable Unicode conversion for abstracts (no external deps)
private let latexSymbolMap: [String: String] = [
    "\\alpha":"α","\\beta":"β","\\gamma":"γ","\\delta":"δ","\\epsilon":"ε","\\varepsilon":"ε","\\zeta":"ζ","\\eta":"η","\\theta":"θ","\\vartheta":"ϑ","\\iota":"ι","\\kappa":"κ","\\lambda":"λ","\\mu":"μ","\\nu":"ν","\\xi":"ξ","\\pi":"π","\\varpi":"ϖ","\\rho":"ρ","\\varrho":"ϱ","\\sigma":"σ","\\varsigma":"ς","\\tau":"τ","\\upsilon":"υ","\\phi":"φ","\\varphi":"ϕ","\\chi":"χ","\\psi":"ψ","\\omega":"ω",
    "\\Gamma":"Γ","\\Delta":"Δ","\\Theta":"Θ","\\Lambda":"Λ","\\Xi":"Ξ","\\Pi":"Π","\\Sigma":"Σ","\\Upsilon":"Υ","\\Phi":"Φ","\\Psi":"Ψ","\\Omega":"Ω",
    "\\mathbb{R}":"ℝ","\\mathbb{Z}":"ℤ","\\mathbb{Q}":"ℚ","\\mathbb{N}":"ℕ","\\mathbb{C}":"ℂ",
    "\\leq":"≤","\\geq":"≥","\\neq":"≠","\\pm":"±","\\mp":"∓","\\times":"×","\\cdot":"·","\\infty":"∞","\\approx":"≈","\\propto":"∝","\\sim":"∼","\\to":"→","\\rightarrow":"→","\\leftarrow":"←","\\Rightarrow":"⇒","\\Leftarrow":"⇐","\\leftrightarrow":"↔","\\mapsto":"↦","\\partial":"∂","\\nabla":"∇","\\int":"∫","\\sum":"∑","\\prod":"∏","\\exists":"∃","\\forall":"∀","\\in":"∈","\\notin":"∉","\\cup":"∪","\\cap":"∩","\\subset":"⊂","\\subseteq":"⊆","\\supset":"⊃","\\supseteq":"⊇","\\setminus":"∖","\\oplus":"⊕","\\otimes":"⊗","\\perp":"⊥","\\angle":"∠","\\deg":"°"
]

private let superscriptMap: [Character: Character] = [
    "0":"⁰","1":"¹","2":"²","3":"³","4":"⁴","5":"⁵","6":"⁶","7":"⁷","8":"⁸","9":"⁹",
    "+":"⁺","-":"⁻","=":"⁼","(":"⁽",")":"⁾","n":"ⁿ","i":"ⁱ","j":"ʲ","k":"ᵏ","l":"ˡ","m":"ᵐ","x":"ˣ","y":"ʸ","z":"ᶻ","a":"ᵃ","b":"ᵇ","c":"ᶜ","d":"ᵈ","e":"ᵉ","f":"ᶠ","g":"ᵍ","h":"ʰ","o":"ᵒ","p":"ᵖ","r":"ʳ","s":"ˢ","t":"ᵗ","u":"ᵘ","v":"ᵛ","w":"ʷ","q":"ᑫ"
]

private let subscriptMap: [Character: Character] = [
    "0":"₀","1":"₁","2":"₂","3":"₃","4":"₄","5":"₅","6":"₆","7":"₇","8":"₈","9":"₉",
    "+":"₊","-":"₋","=":"₌","(":"₍",")":"₎","i":"ᵢ","j":"ⱼ","k":"ₖ","l":"ₗ","m":"ₘ","n":"ₙ","p":"ₚ","r":"ᵣ","s":"ₛ","t":"ₜ","u":"ᵤ","v":"ᵥ","x":"ₓ","a":"ₐ","e":"ₑ","o":"ₒ","h":"ₕ","q":"ᵩ"
]

private func mapScript(_ s: String, table: [Character: Character]) -> String {
    return String(s.map { table[$0] ?? $0 })
}

private func replaceRegex(_ pattern: String, in text: String, options: NSRegularExpression.Options = [], transform: (NSTextCheckingResult, NSString) -> String) -> String {
    guard let re = try? NSRegularExpression(pattern: pattern, options: options) else { return text }
    let ns = text as NSString
    var out = ""
    var last = 0
    for m in re.matches(in: text, options: [], range: NSRange(location: 0, length: ns.length)) {
        if m.range.location > last {
            out += ns.substring(with: NSRange(location: last, length: m.range.location - last))
        }
        out += transform(m, ns)
        last = m.range.location + m.range.length
    }
    if last < ns.length {
        out += ns.substring(from: last)
    }
    return out
}

private func renderLatexReadable(_ s: String) -> String {
    var out = s

    // Remove common math delimiters while keeping content.
    out = replaceRegex(#"(?s)\$\$(.+?)\$\$"#, in: out, options: [.dotMatchesLineSeparators]) { m, ns in
        ns.substring(with: m.range(at: 1))
    }
    out = replaceRegex(#"(?s)\\\[(.+?)\\\]"#, in: out, options: [.dotMatchesLineSeparators]) { m, ns in
        ns.substring(with: m.range(at: 1))
    }
    out = replaceRegex(#"(?s)\\\((.+?)\\\)"#, in: out, options: [.dotMatchesLineSeparators]) { m, ns in
        ns.substring(with: m.range(at: 1))
    }
    out = replaceRegex(#"(?s)\$(.+?)\$"#, in: out, options: [.dotMatchesLineSeparators]) { m, ns in
        ns.substring(with: m.range(at: 1))
    }

    // Convert superscripts/subscripts.
    out = replaceRegex(#"\^\{([^}]+)\}"#, in: out) { m, ns in mapScript(ns.substring(with: m.range(at: 1)), table: superscriptMap) }
    out = replaceRegex(#"\^([A-Za-z0-9\+\-\=\(\)]+)"#, in: out) { m, ns in mapScript(ns.substring(with: m.range(at: 1)), table: superscriptMap) }
    out = replaceRegex(#"_\{([^}]+)\}"#, in: out) { m, ns in mapScript(ns.substring(with: m.range(at: 1)), table: subscriptMap) }
    out = replaceRegex(#"_([A-Za-z0-9\+\-\=\(\)]+)"#, in: out) { m, ns in mapScript(ns.substring(with: m.range(at: 1)), table: subscriptMap) }

    // Replace simple symbol macros.
    for (k, v) in latexSymbolMap {
        out = out.replacingOccurrences(of: k, with: v)
    }

    // Strip simple formatting wrappers.
    out = replaceRegex(#"\\text\{([^}]*)\}"#, in: out) { m, ns in ns.substring(with: m.range(at: 1)) }
    out = replaceRegex(#"\\mathrm\{([^}]*)\}"#, in: out) { m, ns in ns.substring(with: m.range(at: 1)) }
    out = replaceRegex(#"\\mathbf\{([^}]*)\}"#, in: out) { m, ns in ns.substring(with: m.range(at: 1)) }

    return out
}


// MARK: - Abstract cleanup

private func cleanAbstract(_ raw: String) -> String {
    var s = raw
        .replacingOccurrences(of: "\r\n", with: "\n")
        .replacingOccurrences(of: "\r", with: "\n")

    s = regexReplace(
        s,
        #"\n\s*\\\\\s*\(\s*https?://arxiv\.org/abs/[^)]*\)\s*\n\s*[-–—]{5,}\s*\n\s*\\\\\s*(?:\n|$)"#,
        "\n",
        options: [.caseInsensitive]
    )

    s = regexReplace(s, #"(?m)^([ \t]*)\\\\([ \t]*)$"#, " ", options: [])
    s = s.replacingOccurrences(of: "\t", with: "    ")
    s = regexReplace(s, #"[ ]{16,}"#, "    ")

    return s.trimmingCharacters(in: .whitespacesAndNewlines)
}

private func extractYear(from dateLine: String) -> String {
    let s = stripLeadingLabel(dateLine, label: "Date")
    if let re = try? NSRegularExpression(pattern: #"\b(19|20)\d{2}\b"#) {
        let range = NSRange(location: 0, length: (s as NSString).length)
        if let m = re.firstMatch(in: s, range: range) {
            return (s as NSString).substring(with: m.range)
        }
    }
    return ""
}

private func dateOnlyDisplayString(from dateLine: String) -> String {
    // Date header should show only the date portion (no time-of-day / timezone).
    var s = decodeTeXAccents(stripLeadingLabel(dateLine, label: "Date"))
        .replacingOccurrences(of: "\n", with: " ")
        .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !s.isEmpty else { return "" }

    if let pipe = s.firstIndex(of: "|") {
        s = String(s[..<pipe]).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    if let re = try? NSRegularExpression(pattern: #"\b\d{1,2}:\d{2}(?::\d{2})?\b"#) {
        let ns = s as NSString
        let r = NSRange(location: 0, length: ns.length)
        if let m = re.firstMatch(in: s, range: r) {
            let prefix = ns.substring(to: m.range.location)
            let trimmed = prefix.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { return trimmed }
        }
    }

    return s
}


// MARK: - Author formatting

private func parseAuthorList(from authorsField: String) -> [String] {
    let s = decodeTeXAccents(stripLeadingLabel(authorsField, label: "Authors"))
        .replacingOccurrences(of: "\n", with: " ")
        .trimmingCharacters(in: .whitespacesAndNewlines)

    guard !s.isEmpty else { return [] }

    var parts = s.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
    if parts.count == 1, s.lowercased().contains(" and ") {
        parts = s.components(separatedBy: " and ").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
    }
    return parts.filter { !$0.isEmpty }
}

private func formatAuthorInitialsLast(_ full: String) -> String {
    let cleaned = decodeTeXAccents(full)
        .replacingOccurrences(of: "  ", with: " ")
        .trimmingCharacters(in: .whitespacesAndNewlines)
    if cleaned.isEmpty { return cleaned }

    let tokens = cleaned.split(separator: " ").map { String($0) }.filter { !$0.isEmpty }
    guard tokens.count >= 1 else { return cleaned }

    let last = tokens.last!

    func initial(from token: String) -> String? {
        let t = token.trimmingCharacters(in: .punctuationCharacters)
        guard let ch = t.first else { return nil }
        if t.count == 2, t.last == "." { return t }
        return "\(ch)."
    }

    let firstInit = initial(from: tokens[0]) ?? ""
    var middleInit = ""
    if tokens.count >= 3 {
        let mid = tokens[1]
        let low = mid.lowercased()
        if low != "de" && low != "van" && low != "von" {
            if let mi = initial(from: mid) { middleInit = mi }
        }
    }

    let initials = [firstInit, middleInit].filter { !$0.isEmpty }.joined(separator: " ")
    if initials.isEmpty { return last }
    return "\(initials) \(last)"
}

private func leftAuthorYearText(paper: Paper) -> String {
    let authors = parseAuthorList(from: paper.authors).map(formatAuthorInitialsLast)
    let year = extractYear(from: paper.dateLine)

    if authors.isEmpty {
        return year.isEmpty ? "Unknown authors" : "Unknown authors \(year)"
    }
    if authors.count == 1 {
        return year.isEmpty ? authors[0] : "\(authors[0]) \(year)"
    }

    let a1 = authors[0]
    let a2 = authors[1]
    let etal = (authors.count >= 3) ? " et al." : ""
    let yr = year.isEmpty ? "" : " \(year)"
    return "\(a1) & \(a2)\(etal)\(yr)"
}


// MARK: - Keyword presence

private func paperSearchCorpus(_ p: Paper) -> String {
    let absClean = cleanAbstract(p.abstractText)
    let corpus = [
        p.title, p.authors, p.categories, p.dateLine, p.url, p.comments, absClean
    ].joined(separator: "\n")
    return decodeTeXAccents(corpus).lowercased()
}

private func keywordsPresent(in paper: Paper, keywords: [String]) -> [String] {
    let corpus = paperSearchCorpus(paper)
    var seen = Set<String>()
    var out: [String] = []

    for kw in keywords {
        let k = kw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !k.isEmpty else { continue }
        let kl = k.lowercased()
        if corpus.contains(kl), !seen.contains(kl) {
            seen.insert(kl)
            out.append(k)
        }
    }

    out.sort { $0.localizedCaseInsensitiveCompare($1) == .orderedAscending }
    return out
}

private func dedupePluralKeywordsForDisplay(_ keywords: [String]) -> [String] {
    guard keywords.count > 1 else { return keywords }
    let normalized = keywords.map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
    let normalizedSet = Set(normalized)

    func hasSingularVariant(_ lower: String) -> Bool {
        // Drop plural forms when a singular keyword is also present.
        if lower.hasSuffix("ies"), lower.count > 3 {
            let candidate = String(lower.dropLast(3)) + "y"
            if normalizedSet.contains(candidate) { return true }
        }
        if lower.hasSuffix("es"), lower.count > 2 {
            let candidate = String(lower.dropLast(2))
            if normalizedSet.contains(candidate) { return true }
        }
        if lower.hasSuffix("s"), lower.count > 1 {
            let candidate = String(lower.dropLast(1))
            if normalizedSet.contains(candidate) { return true }
        }
        return false
    }

    var out: [String] = []
    for (idx, kw) in keywords.enumerated() {
        let lower = normalized[idx]
        if hasSingularVariant(lower) { continue }
        out.append(kw)
    }
    return out
}


// MARK: - HTML rendering (details)

	private func buildDetailsHTML(paper: Paper,
	                              keywordsForHighlight: [String],
	                              highlightCSS: String,
	                              textPalette: TextPalette,
	                              paperIndex: Int,
	                              paperTotal: Int) -> String {
	    let title = paper.title
	    let authors = stripLeadingLabel(paper.authors, label: "Authors")
	    let authorHeader = decodeTeXAccents(authors)
	        .replacingOccurrences(of: "\n", with: " ")
	        .components(separatedBy: .whitespacesAndNewlines)
	        .filter { !$0.isEmpty }
	        .joined(separator: " ")
	    let categories = stripLeadingLabel(paper.categories, label: "Categories")
	    let dateHeader = dateOnlyDisplayString(from: paper.dateLine)
	    let url = stripLeadingLabel(paper.url, label: "URL")
	    let comments = stripLeadingLabel(paper.comments, label: "Comments")
	    let abstract = renderLatexReadable(decodeTeXAccents(cleanAbstract(paper.abstractText)))

    func imgTag(_ path: String, isSide: Bool) -> String {
        let p = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !p.isEmpty else { return "" }
        let u = URL(fileURLWithPath: p)
        let klass = isSide ? "header-img header-img-side" : "header-img header-img-center"
        return #"<img class="\#(klass)" src="\#(htmlEscape(u.absoluteString))" alt="header"/>"#
    }

    // arXiv logo removed; keep only the side images flanking the title.
    let headerHTML = ""

    let kwJSArray = "[" + keywordsForHighlight.map { "\"\(jsStringEscape($0))\"" }.joined(separator: ",") + "]"
    let detailsLightBG = NSColor.white
    let detailsDarkBG = NSColor(srgbRed: 0.11, green: 0.11, blue: 0.12, alpha: 1.0)
    let lightPalette = adaptiveTextPalette(baseColor: detailsLightBG, linkHex: RIGHT_LINK_COLOR_HEX)
    let darkPalette = adaptiveTextPalette(baseColor: detailsDarkBG, linkHex: RIGHT_LINK_COLOR_HEX)
    let clampedTotal = max(0, paperTotal)
    let clampedIndex = clampedTotal == 0 ? 0 : max(1, min(clampedTotal, paperIndex))

    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    :root {
      --bg: \(cssRGBA(detailsLightBG));
      --text-primary: \(cssRGBA(lightPalette.primary));
      --text-secondary: \(cssRGBA(lightPalette.secondary));
      --text-muted: \(cssRGBA(lightPalette.muted));
      --text-link: \(cssRGBA(lightPalette.link));
      --rule: \(cssRGBA(lightPalette.rule));
      --code-fg: \(cssRGBA(lightPalette.codeText));
      --code-bg: \(cssRGBA(lightPalette.codeBackground));
      --kwbg: \(highlightCSS);
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --bg: \(cssRGBA(detailsDarkBG));
        --text-primary: \(cssRGBA(darkPalette.primary));
        --text-secondary: \(cssRGBA(darkPalette.secondary));
        --text-muted: \(cssRGBA(darkPalette.muted));
        --text-link: \(cssRGBA(darkPalette.link));
        --rule: \(cssRGBA(darkPalette.rule));
        --code-fg: \(cssRGBA(darkPalette.codeText));
        --code-bg: \(cssRGBA(darkPalette.codeBackground));
      }
    }

    html, body { height: 100%; background: transparent; overflow-x: hidden; overscroll-behavior: none; overscroll-behavior-y: none; }
    body {
      margin: 0;
      color: var(--text-primary);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
      line-height: 1.35;
    }

    .page-shell {
      min-height: 100vh;
      background: var(--bg);
      border-radius: \(PANEL_CORNER_RADIUS)px;
      overflow: hidden;
      position: relative;
      padding: 18px 18px 28px 18px;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
    }

    .content {
      flex: 1 1 auto;
    }

    * { overflow-wrap: anywhere; word-break: break-word; }

		    /* Static page header: stays at the top of the document and scrolls away (not fixed/sticky). */
		    .page-header {
		      display: grid;
		      grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) minmax(0, 1fr);
		      align-items: start;
		      column-gap: 12px;
		      margin: 0 0 12px 0;
		    }

		    .chrome-left,
		    .chrome-center,
		    .chrome-right {
		      font-size: 11px;
		      font-weight: 500;
		      letter-spacing: 0.1px;
		      color: var(--text-muted);
		      opacity: 0.95;
		      user-select: none;
		      pointer-events: none;
		      font-variant-numeric: tabular-nums;
		      min-width: 0;
		    }

		    .chrome-left {
		      text-align: left;
		      white-space: nowrap;
		      overflow: hidden;
		      text-overflow: ellipsis;
		    }

		    .chrome-center {
		      text-align: center;
		      white-space: normal;
		      overflow-wrap: anywhere;
		      word-break: break-word;
		      line-height: 1.25;
		    }

		    .chrome-right {
		      text-align: right;
		      white-space: nowrap;
		      overflow: hidden;
		      text-overflow: ellipsis;
		    }

	    .title-row {
	      display: flex;
	      align-items: center;
	      justify-content: center;
	      gap: 12px;
	      margin: 0 0 6px 0;
	    }

	    .title-link {
	      color: inherit !important;
	      text-decoration: none !important;
	    }
	    .title-link:hover {
	      color: var(--text-link) !important;
	      text-decoration: underline !important;
	    }

	    .header-img {
	      max-height: \(HEADER_IMAGE_MAX_HEIGHT)px;
	      height: auto; width: auto;
	      transform-origin: center;
	      display: block;
    }
    .header-img-center { transform: scale(\(HEADER_IMAGE_SCALE)); }
    .header-img-side   { transform: scale(\(HEADER_IMAGE_SIDE_SCALE)); }

	    h1 { font-size: 20px; margin: 0; font-weight: 700; text-align: center; color: var(--text-primary); }
	    .rule { height: 1px; background: var(--rule); margin: 10px 0 16px 0; }
	    .row { margin: 0 0 10px 0; color: var(--text-primary); }
	    .label { font-weight: 700; margin-right: 6px; color: var(--text-muted); }

    a { color: var(--text-link); text-decoration: underline; }

    .abstract-label { font-weight: 700; margin-top: 10px; text-align: center; color: var(--text-secondary); }
    .abstract {
      font-family: Georgia, "Times New Roman", Times, serif;
      font-size: 14px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
      text-align: center;
      color: var(--text-primary);
    }

	    .abstract-end {
	      /* Intentionally unused (footer has the only divider). */
	      display: none;
	    }

	    .footer {
	      display: flex;
	      align-items: flex-start;
	      justify-content: space-between;
	      gap: 14px;
	      margin: 14px 0 0 0;
	      padding: 10px 0 0 0;
	      border-top: 1px solid var(--rule);
	      color: var(--text-muted);
	      font-size: 11px;
	      font-weight: 500;
	      letter-spacing: 0.1px;
	    }
	    .footer-left { flex: 1; text-align: left; }
	    .footer-right { flex: 1; text-align: right; }

	    .header-divider {
	      border-top: 1px solid var(--rule);
	      margin: 12px 0 0 0;
	    }

    code, pre {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      color: var(--code-fg);
      background: var(--code-bg);
      border-radius: 6px;
    }
    code { padding: 0 4px; }
    pre { padding: 10px; }

    .kw {
      background-color: var(--kwbg);
      color: inherit;
      padding: 0 2px;
      border-radius: 4px;
      box-decoration-break: clone;
      -webkit-box-decoration-break: clone;
    }
	  </style>

	  <script>
		    function escapeRegExp(s) { return s.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'); }

    function highlightKeywords(container, keywords) {
      if (!container || !keywords || !keywords.length) return;
      const uniq = Array.from(new Set(keywords.map(k => (k || '').trim()).filter(Boolean)));
      if (!uniq.length) return;
      uniq.sort((a,b) => b.length - a.length);
      const pattern = uniq.map(k => escapeRegExp(k)).join('|');
      const re = new RegExp(pattern, 'gi');

      const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);

      for (const node of nodes) {
        const text = node.nodeValue;
        if (!text || !re.test(text)) continue;
        re.lastIndex = 0;

        const frag = document.createDocumentFragment();
        let last = 0, m;

        while ((m = re.exec(text)) !== null) {
          const start = m.index;
          const end = start + m[0].length;

          if (start > last) frag.appendChild(document.createTextNode(text.slice(last, start)));

          const span = document.createElement('span');
          span.className = 'kw';
          span.textContent = text.slice(start, end);
          frag.appendChild(span);

          last = end;
        }

        if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
        node.parentNode.replaceChild(frag, node);
      }
    }

    const PAPER_KEYWORDS = \(kwJSArray);
  </script>
	</head>
		<body>
			  <div class="page-shell">
				  <div class="page-header">
				    <div class="chrome-left">\(htmlEscape(dateHeader))</div>
				    <div class="chrome-center">\(htmlEscape(authorHeader))</div>
				    <div class="chrome-right">Paper \(clampedIndex)/\(clampedTotal)</div>
					  </div>
				  <div class="title-row">
				    \(imgTag(HEADER_IMAGE_LEFT_PATH, isSide: true))
				    <h1 id="titleText"><a class="title-link" href="\(htmlEscape(url))">\(htmlEscape(title))</a></h1>
				    \(imgTag(HEADER_IMAGE_RIGHT_PATH, isSide: true))
				  </div>
				  \(headerHTML)
				  <div class="header-divider"></div>

		  <div class="content">
		    <div class="abstract-label"><span class="label">Abstract</span></div>
		    <div id="abstractText" class="abstract">\(htmlEscape(abstract))</div>
		  </div>

		  <div class="footer">
		    <div class="footer-left"><span class="label">Comments:</span><span>\(htmlEscape(comments))</span></div>
		    <div class="footer-right"><span class="label">Categories:</span><span>\(htmlEscape(categories))</span></div>
		  </div>

				  <script>
				    try { highlightKeywords(document.getElementById('titleText'), PAPER_KEYWORDS); } catch(e) {}
				    try { highlightKeywords(document.getElementById('abstractText'), PAPER_KEYWORDS); } catch(e) {}
				  </script>
		  </div>
		</body>
		</html>
"""

}

// MARK: - PDF Cache
private final class PDFCacheManager {
    enum CacheError: Error {
        case badStatus(Int)
        case invalidContentType(String?)
        case invalidPDF
        case missingTempFile
        case fileMoveFailed
        case timeout
        case notEnqueued
    }

    enum LifecycleStage: String {
        case urlKnown = "url-known"
        case prefetchQueued = "prefetch-queued"
        case downloading = "downloading"
        case downloaded = "downloaded"
        case validated = "validated"
        case renderQueued = "render-queued"
        case rendered = "rendered"
        case failed = "failed"
    }

    struct Metadata {
        let url: URL
        let paperIndex: Int?
        let stableID: String?
    }

    struct PrefetchRequest {
        let url: URL
        let metadata: Metadata?
    }

    private struct LifecycleRecord {
        var stage: LifecycleStage
        var timestamp: CFTimeInterval
    }

    struct PreparedPDF {
        let fileURL: URL
        let byteCount: Int64
        let lastModified: Date?
    }

    private struct PendingItem {
        let url: URL
        var priority: Int
        let order: Int
        var callbacks: [(Result<PreparedPDF, Error>) -> Void]
        let attempt: Int
        let resumeData: Data?
        let earliestStart: CFTimeInterval
        let reason: String
    }

    private struct ActiveItem {
        let url: URL
        let priority: Int
        let attempt: Int
        var callbacks: [(Result<PreparedPDF, Error>) -> Void]
        let task: URLSessionDownloadTask
        let startedAt: CFTimeInterval
        let reason: String
        var timeoutWorkItem: DispatchWorkItem?
    }

    private let stateQueue = DispatchQueue(label: "arxiv.pdfcache.state", qos: .utility)
    private let ioQueue = DispatchQueue(label: "arxiv.pdfcache.io", qos: .utility)
    private let ioQueueKey = DispatchSpecificKey<UInt8>()
    private let stateQueueKey = DispatchSpecificKey<UInt8>()
    private let session: URLSession
    private let parentDir: URL
    private let cacheDir: URL
    private let maxConcurrent: Int
    private let maxRetryCount: Int = 3
    private let downloadTimeoutSeconds: TimeInterval = 16.0
    private let debugForceRetryCount: Int
    private var metadataByKey: [String: Metadata] = [:]
    private var lifecycleRecords: [String: LifecycleRecord] = [:]
    private var stageCounters: [LifecycleStage: Int] = [:]

    private var pending: [String: PendingItem] = [:]
    private var active: [String: ActiveItem] = [:]
    private var ready: [String: PreparedPDF] = [:]
    private var failures: [String: Error] = [:]
    private var orderCounter: Int = 0
    private var deferredDrainWorkItem: DispatchWorkItem?

    private var prefetchStartTime: CFTimeInterval?
    private var prefetchSuccessCount: Int = 0
    private var prefetchFailureCount: Int = 0
    private var prefetchBytes: Int64 = 0
    private var prefetchLastLoggedCount: Int = 0
    private var lastSummaryLogTime: CFTimeInterval?
    private var lastFailureMessage: String?

    init() {
        self.maxConcurrent = max(1, PDF_CACHE_MAX_CONCURRENT_DOWNLOADS)
        self.parentDir = FileManager.default.temporaryDirectory
            .appendingPathComponent(PDF_CACHE_DIR_NAME, isDirectory: true)
        let sessionID = "session-\(UUID().uuidString)"
        self.cacheDir = parentDir.appendingPathComponent(sessionID, isDirectory: true)
        let rawForceRetry = (ProcessInfo.processInfo.environment["ARXIV_DEBUG_FORCE_RETRY_COUNT"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        self.debugForceRetryCount = max(0, Int(rawForceRetry) ?? 0)
        if debugForceRetryCount > 0 {
            NSLog("[PDFEager] debug_force_retry_count=\(debugForceRetryCount)")
        }

        let config = URLSessionConfiguration.default
        config.httpMaximumConnectionsPerHost = maxConcurrent
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.urlCache = nil
        self.session = URLSession(configuration: config)

        ioQueue.setSpecific(key: ioQueueKey, value: 1)
        stateQueue.setSpecific(key: stateQueueKey, value: 1)

        createCacheDirectories()
        purgeOrphanedSessions()

        NSLog("[PDFEager] cache_dir=\(cacheDir.path) concurrent=\(maxConcurrent)")
    }

    deinit {
        session.invalidateAndCancel()
    }

    var sessionDirectory: URL { cacheDir }

    func cacheKey(for url: URL) -> String {
        sha256Hex(url.absoluteString)
    }

    func prefetch(_ requests: [PrefetchRequest], priority: Int, reason: String) {
        enqueue(requests: requests, priority: priority, reason: reason, completion: nil)
    }

    func preparedPDFIfReady(for url: URL) -> PreparedPDF? {
        let key = cacheKey(for: url)
        return stateQueue.sync { ready[key] }
    }

    func whenPreparedPDF(for url: URL, completion: @escaping (Result<PreparedPDF, Error>) -> Void) {
        let key = cacheKey(for: url)
        stateQueue.async { [weak self] in
            guard let self else { return }
            if let prepared = self.ready[key] {
                DispatchQueue.main.async { completion(.success(prepared)) }
                return
            }
            if var activeItem = self.active[key] {
                activeItem.callbacks.append(completion)
                self.active[key] = activeItem
                return
            }
            if var pendingItem = self.pending[key] {
                pendingItem.callbacks.append(completion)
                self.pending[key] = pendingItem
                return
            }
            if let err = self.failures[key] {
                DispatchQueue.main.async { completion(.failure(err)) }
                return
            }
            DispatchQueue.main.async { completion(.failure(CacheError.notEnqueued)) }
        }
    }

    func debugStateDescription(for url: URL) -> String {
        let key = cacheKey(for: url)
        return stateQueue.sync {
            if ready[key] != nil { return "ready" }
            if active[key] != nil { return "downloading" }
            if pending[key] != nil { return "pending" }
            if failures[key] != nil { return "failed" }
            return "unknown"
        }
    }

    func cleanupOnExit() {
        session.invalidateAndCancel()
        stateQueue.sync {
            pending.removeAll()
            active.removeAll()
            ready.removeAll()
            failures.removeAll()
        }

        let fm = FileManager.default
        let cacheDirPath = cacheDir.path
        let existedBefore = fm.fileExists(atPath: cacheDirPath)
        let removeCacheDir = { [cacheDir] in
            try? FileManager.default.removeItem(at: cacheDir)
        }
        if DispatchQueue.getSpecific(key: ioQueueKey) == 1 {
            removeCacheDir()
        } else {
            ioQueue.sync(execute: removeCacheDir)
        }
        let existsAfter = fm.fileExists(atPath: cacheDirPath)
        NSLog("[PDFEager] cleanup dir=\(cacheDirPath) existed_before=\(existedBefore) exists_after=\(existsAfter)")
    }

    func registerMetadata(_ metadata: Metadata, for url: URL) {
        let key = cacheKey(for: url)
        stateQueue.async {
            self.metadataByKey[key] = metadata
            self.logLifecycleTransition(
                key: key,
                stage: .urlKnown,
                url: url,
                message: "metadata-registered"
            )
        }
    }

    func trackLifecycleStage(_ stage: LifecycleStage,
                             for url: URL,
                             fileURL: URL? = nil,
                             fileSize: Int64? = nil,
                             lastModified: Date? = nil,
                             message: String? = nil) {
        let key = cacheKey(for: url)
        stateQueue.async {
            self.logLifecycleTransition(
                key: key,
                stage: stage,
                url: url,
                fileURL: fileURL,
                fileSize: fileSize,
                lastModified: lastModified,
                message: message
            )
        }
    }

    private func createCacheDirectories() {
        do {
            try FileManager.default.createDirectory(at: parentDir, withIntermediateDirectories: true, attributes: nil)
        } catch {
            NSLog("[PDFEager] cache_dir_create_failed parent=\(parentDir.path) error=\(error)")
        }
        do {
            try FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true, attributes: nil)
        } catch {
            NSLog("[PDFEager] cache_dir_create_failed cache=\(cacheDir.path) error=\(error)")
        }
    }

    private func purgeOrphanedSessions() {
        ioQueue.async { [parentDir, cacheDir] in
            let fm = FileManager.default
            let urls = (try? fm.contentsOfDirectory(
                at: parentDir,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles]
            )) ?? []
            for url in urls {
                guard url != cacheDir else { continue }
                let values = try? url.resourceValues(forKeys: [.isDirectoryKey])
                guard values?.isDirectory == true else { continue }
                try? fm.removeItem(at: url)
            }
        }
    }

    private func cachedFileURL(forKey key: String) -> URL {
        cacheDir.appendingPathComponent(key).appendingPathExtension("pdf")
    }

    private func partialFileURL(forKey key: String) -> URL {
        cacheDir.appendingPathComponent(key).appendingPathExtension("partial")
    }

    private func enqueue(requests: [PrefetchRequest],
                         priority: Int,
                         reason: String,
                         completion: ((Result<PreparedPDF, Error>) -> Void)?) {
        guard !requests.isEmpty else { return }
        stateQueue.async { [weak self] in
            guard let self else { return }

            if self.prefetchStartTime == nil {
                self.prefetchStartTime = monotonicNow()
                NSLog("[PDFEager] metadata_loaded -> eager_download_start count=\(requests.count)")
            }

            for request in requests {
                let url = request.url
                let key = self.cacheKey(for: url)
                if let metadata = request.metadata {
                    self.metadataByKey[key] = metadata
                }
                self.logLifecycleTransition(
                    key: key,
                    stage: .urlKnown,
                    url: url,
                    message: "prefetch-request reason=\(reason)"
                )

                if let prepared = self.ready[key] {
                    if let completion {
                        DispatchQueue.main.async { completion(.success(prepared)) }
                    }
                    continue
                }

                if var activeItem = self.active[key] {
                    if let completion { activeItem.callbacks.append(completion) }
                    self.active[key] = activeItem
                    continue
                }

                if var pendingItem = self.pending[key] {
                    if priority < pendingItem.priority { pendingItem.priority = priority }
                    if let completion { pendingItem.callbacks.append(completion) }
                    self.pending[key] = pendingItem
                    continue
                }

                self.failures.removeValue(forKey: key)
                self.orderCounter += 1
                var callbacks: [(Result<PreparedPDF, Error>) -> Void] = []
                if let completion { callbacks.append(completion) }
                let item = PendingItem(
                    url: url,
                    priority: priority,
                    order: self.orderCounter,
                    callbacks: callbacks,
                    attempt: 0,
                    resumeData: nil,
                    earliestStart: 0,
                    reason: reason
                )
                self.pending[key] = item
                self.logLifecycleTransition(
                    key: key,
                    stage: .prefetchQueued,
                    url: url,
                    message: "queued reason=\(reason)"
                )
            }
            self.drainQueueLocked()
        }
    }

    private func drainQueueLocked() {
        deferredDrainWorkItem?.cancel()
        deferredDrainWorkItem = nil

        guard active.count < maxConcurrent else { return }

        let now = monotonicNow()
        var soonestEarliestStart: CFTimeInterval?

        let sortedKeys = pending.keys.sorted { lhs, rhs in
            guard let a = pending[lhs], let b = pending[rhs] else { return false }
            if a.priority != b.priority { return a.priority < b.priority }
            return a.order < b.order
        }

        for key in sortedKeys {
            guard active.count < maxConcurrent else { break }
            guard let item = pending[key] else { continue }
            if item.earliestStart > now {
                soonestEarliestStart = min(soonestEarliestStart ?? item.earliestStart, item.earliestStart)
                continue
            }
            _ = pending.removeValue(forKey: key)
            startDownloadLocked(key: key, item: item)
        }

        if active.count < maxConcurrent, let t = soonestEarliestStart {
            scheduleDeferredDrainLocked(earliestStart: t)
        }
    }

    private func scheduleDeferredDrainLocked(earliestStart: CFTimeInterval) {
        let delay = max(0.02, earliestStart - monotonicNow())
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.drainQueueLocked()
        }
        deferredDrainWorkItem = work
        stateQueue.asyncAfter(deadline: .now() + delay, execute: work)
    }

    private func startDownloadLocked(key: String, item: PendingItem) {
        let startedAt = monotonicNow()
        NSLog("[PDFEager] download_start key=\(key.prefix(8)) attempt=\(item.attempt) priority=\(item.priority) reason=\(item.reason)")
        logLifecycleTransition(
            key: key,
            stage: .downloading,
            url: item.url,
            message: "attempt=\(item.attempt) priority=\(item.priority)"
        )

        let completion: (URL?, URLResponse?, Error?) -> Void = { [weak self] location, response, error in
            self?.handleDownloadCompletion(
                key: key,
                url: item.url,
                priority: item.priority,
                attempt: item.attempt,
                startedAt: startedAt,
                location: location,
                response: response,
                error: error,
                callbacks: item.callbacks,
                reason: item.reason
            )
        }

        let task: URLSessionDownloadTask
        if let resumeData = item.resumeData {
            task = session.downloadTask(withResumeData: resumeData, completionHandler: completion)
        } else {
            task = session.downloadTask(with: item.url, completionHandler: completion)
        }

        var activeItem = ActiveItem(
            url: item.url,
            priority: item.priority,
            attempt: item.attempt,
            callbacks: item.callbacks,
            task: task,
            startedAt: startedAt,
            reason: item.reason,
            timeoutWorkItem: nil
        )
        let timeoutWork = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.handleDownloadTimeout(key: key, url: item.url, startedAt: startedAt)
        }
        activeItem.timeoutWorkItem = timeoutWork
        active[key] = activeItem
        stateQueue.asyncAfter(deadline: .now() + downloadTimeoutSeconds, execute: timeoutWork)
        task.resume()
    }

    private func handleDownloadTimeout(key: String, url: URL, startedAt: CFTimeInterval) {
        guard let activeItem = active[key] else { return }
        activeItem.task.cancel()
        NSLog("[PDFEager] download_timeout key=\(key.prefix(8))")
        finishDownload(
            key: key,
            url: url,
            result: .failure(CacheError.timeout),
            callbacks: activeItem.callbacks,
            startedAt: startedAt
        )
    }

    private func handleDownloadCompletion(key: String,
                                          url: URL,
                                          priority: Int,
                                          attempt: Int,
                                          startedAt: CFTimeInterval,
                                          location: URL?,
                                          response: URLResponse?,
                                          error: Error?,
                                          callbacks: [(Result<PreparedPDF, Error>) -> Void],
                                          reason: String) {
        let work = { [weak self] in
            guard let self else { return }

            let elapsedMs = Int((monotonicNow() - startedAt) * 1000.0)
            let http = response as? HTTPURLResponse

            var effectiveError = error
            if debugForceRetryCount > 0, attempt < debugForceRetryCount {
                if effectiveError == nil {
                    NSLog("[PDFEager] debug_forced_retry key=\(key.prefix(8)) attempt=\(attempt)")
                }
                effectiveError = NSError(
                    domain: NSURLErrorDomain,
                    code: NSURLErrorTimedOut,
                    userInfo: [NSLocalizedDescriptionKey: "debug_forced_retry"]
                )
            }

            if let error = effectiveError {
                let ns = error as NSError
                let resumeData = ns.userInfo[NSURLSessionDownloadTaskResumeData] as? Data
                if self.shouldRetry(error: error, attempt: attempt) {
                    let delay = self.retryDelaySeconds(attempt: attempt)
                    NSLog("[PDFEager] download_retry key=\(key.prefix(8)) attempt=\(attempt + 1) delay=\(String(format: "%.2f", delay)) error=\(error)")
                    self.retryDownload(
                        key: key,
                        url: url,
                        priority: priority,
                        attempt: attempt + 1,
                        resumeData: resumeData,
                        callbacks: callbacks,
                        reason: reason,
                        delaySeconds: delay
                    )
                    return
                }
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) error=\(error)")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(error),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }

            if let http, !(200...299).contains(http.statusCode) {
                let err = CacheError.badStatus(http.statusCode)
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) status=\(http.statusCode)")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(err),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }

            guard let location else {
                let err = CacheError.missingTempFile
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) missing_temp")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(err),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }

            let mimeType = http?.value(forHTTPHeaderField: "Content-Type")
            let mimeOK = pdfMimeTypeLooksValid(mimeType)
            guard let inputHandle = try? FileHandle(forReadingFrom: location) else {
                let err = CacheError.missingTempFile
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) missing_temp path=\(location.path)")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(err),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }
            defer { try? inputHandle.close() }

            let headerData = inputHandle.readData(ofLength: 5)
            let headerOK = dataHasPDFHeader(headerData)
            guard mimeOK || headerOK else {
                let err = CacheError.invalidContentType(mimeType)
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) invalid_mime=\(mimeType ?? "nil")")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(err),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }
            guard headerOK else {
                let err = CacheError.invalidPDF
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) invalid_pdf_header")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(err),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }

            let finalURL = self.cachedFileURL(forKey: key)
            let partialURL = self.partialFileURL(forKey: key)
            self.removeFile(partialURL)
            self.removeFile(finalURL)
            self.createCacheDirectories()

            guard FileManager.default.createFile(atPath: partialURL.path, contents: nil, attributes: nil),
                  let outputHandle = try? FileHandle(forWritingTo: partialURL) else {
                self.removeFile(partialURL)
                self.removeFile(finalURL)
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) move_failed error=output_create_failed")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(CacheError.fileMoveFailed),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }
            defer { try? outputHandle.close() }

            var fileSize = Int64(headerData.count)
            if !headerData.isEmpty {
                outputHandle.write(headerData)
            }
            let bufferSize = 1 << 20
            while true {
                let chunk = inputHandle.readData(ofLength: bufferSize)
                if chunk.isEmpty { break }
                fileSize += Int64(chunk.count)
                outputHandle.write(chunk)
            }

            do {
                try FileManager.default.moveItem(at: partialURL, to: finalURL)
            } catch {
                self.removeFile(partialURL)
                self.removeFile(finalURL)
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) move_failed error=\(error)")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(CacheError.fileMoveFailed),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }

            let modified = (try? finalURL.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate
            self.logLifecycleTransition(
                key: key,
                stage: .downloaded,
                url: url,
                fileURL: finalURL,
                fileSize: fileSize,
                lastModified: modified,
                message: "ms=\(elapsedMs)"
            )

            NSLog("[PDFEager] download_complete key=\(key.prefix(8)) ms=\(elapsedMs) bytes=\(fileSize)")
            let prepared = PreparedPDF(fileURL: finalURL, byteCount: fileSize, lastModified: modified)
            self.finishDownload(
                key: key,
                url: url,
                result: .success(prepared),
                callbacks: callbacks,
                startedAt: startedAt
            )
        }
        if DispatchQueue.getSpecific(key: ioQueueKey) != nil {
            work()
        } else {
            ioQueue.sync(execute: work)
        }
    }

	    private func finishDownload(key: String,
	                                url: URL,
	                                result: Result<PreparedPDF, Error>,
	                                callbacks: [(Result<PreparedPDF, Error>) -> Void],
	                                startedAt: CFTimeInterval) {
	        stateQueue.async { [weak self] in
	            guard let self else { return }
	            let activeItem = self.active.removeValue(forKey: key)
	            activeItem?.timeoutWorkItem?.cancel()
	            let callbacksToFire = activeItem?.callbacks ?? callbacks

	            switch result {
	            case .success(let prepared):
	                self.ready[key] = prepared
	                self.failures.removeValue(forKey: key)
	                self.prefetchSuccessCount += 1
	                self.prefetchBytes += prepared.byteCount
	            case .failure(let error):
	                self.failures[key] = error
	                self.prefetchFailureCount += 1
	                let msg = String(describing: error)
	                self.lastFailureMessage = msg
	                self.logLifecycleTransition(
	                    key: key,
	                    stage: .failed,
	                    url: url,
	                    message: msg
	                )
	            }

	            self.drainQueueLocked()

	            DispatchQueue.main.async {
	                callbacksToFire.forEach { $0(result) }
	            }

	            self.logPrefetchStatsIfNeeded()
	        }
	    }

    private func logPrefetchStatsIfNeeded() {
        let total = prefetchSuccessCount + prefetchFailureCount
        guard total - prefetchLastLoggedCount >= PDF_CACHE_PREFETCH_LOG_EVERY else { return }
        prefetchLastLoggedCount = total

        let elapsed = max(0.1, monotonicNow() - (prefetchStartTime ?? monotonicNow()))
        let mbps = (Double(prefetchBytes) / (1024.0 * 1024.0)) / elapsed
        NSLog("[PDFEager] throughput completed=\(prefetchSuccessCount) failed=\(prefetchFailureCount) rateMBps=\(String(format: "%.2f", mbps))")
    }

    private func shouldRetry(error: Error, attempt: Int) -> Bool {
        guard attempt < maxRetryCount else { return false }
        if error is CacheError { return false }
        let ns = error as NSError
        return ns.domain == NSURLErrorDomain
    }

    private func retryDelaySeconds(attempt: Int) -> TimeInterval {
        let base: TimeInterval = 0.6
        let pow2 = pow(2.0, Double(max(0, attempt)))
        return min(6.0, base * pow2)
    }

	    private func retryDownload(key: String,
	                               url: URL,
	                               priority: Int,
	                               attempt: Int,
	                               resumeData: Data?,
	                               callbacks: [(Result<PreparedPDF, Error>) -> Void],
	                               reason: String,
                                    delaySeconds: TimeInterval) {
        stateQueue.async { [weak self] in
            guard let self else { return }
            // Carry all callbacks currently attached to the active download so none are dropped on retry.
            let callbacksToCarry = self.active.removeValue(forKey: key)?.callbacks ?? callbacks

            self.orderCounter += 1
            let item = PendingItem(
                url: url,
                priority: priority,
                order: self.orderCounter,
                callbacks: callbacksToCarry,
                attempt: attempt,
                resumeData: resumeData,
                earliestStart: monotonicNow() + delaySeconds,
                reason: reason
            )
            self.pending[key] = item
            self.drainQueueLocked()
        }
    }

    private func logLifecycleTransition(key: String,
                                        stage: LifecycleStage,
                                        url: URL,
                                        fileURL: URL? = nil,
                                        fileSize: Int64? = nil,
                                        lastModified: Date? = nil,
                                        message: String? = nil) {
        guard DispatchQueue.getSpecific(key: stateQueueKey) == 1 else {
            stateQueue.async { [weak self] in
                self?.logLifecycleTransition(
                    key: key,
                    stage: stage,
                    url: url,
                    fileURL: fileURL,
                    fileSize: fileSize,
                    lastModified: lastModified,
                    message: message
                )
            }
            return
        }

        let now = monotonicNow()
        let previous = lifecycleRecords[key]
        let deltaMs = previous == nil ? 0 : (now - previous!.timestamp) * 1000.0
        lifecycleRecords[key] = LifecycleRecord(stage: stage, timestamp: now)
        stageCounters[stage, default: 0] += 1

        var components: [String] = []
        components.append("key=\(String(key.prefix(8)))")
        components.append("stage=\(stage.rawValue)")
        components.append("thread=\(Thread.isMainThread ? "main" : "bg")")
        components.append("delta_ms=\(String(format: "%.1f", deltaMs))")
        components.append("url=\(url.absoluteString)")

        if let meta = metadataByKey[key] {
            if let idx = meta.paperIndex {
                components.append("paperIndex=\(idx)")
            }
            if let id = meta.stableID, !id.isEmpty {
                components.append("stableID=\(id)")
            }
        }

        if let localPath = fileURL {
            components.append("local=\"\(localPath.path)\"")
        }
        if let size = fileSize {
            components.append("bytes=\(size)")
        }
        if let modified = lastModified {
            components.append("mtime=\(Int(modified.timeIntervalSince1970))")
        }
        if let note = message {
            components.append("msg=\"\(note)\"")
        }

        NSLog("[PDFLife] \(components.joined(separator: " "))")
        logCacheSummaryIfNeeded()
    }

    private func logCacheSummaryIfNeeded() {
        let now = monotonicNow()
        if let last = lastSummaryLogTime, now - last < 1.5 { return }
        lastSummaryLogTime = now
        let pendingCount = pending.count
        let downloadingCount = active.count
        let readyCount = ready.count
        let queuedTotal = stageCounters[.prefetchQueued] ?? 0
        let downloadedTotal = stageCounters[.downloaded] ?? 0
        let validatedTotal = stageCounters[.validated] ?? 0
        let renderedTotal = stageCounters[.rendered] ?? 0
        let failedTotal = stageCounters[.failed] ?? 0
        let lastError = lastFailureMessage ?? "none"
        NSLog("[PDFEager] cache_summary pending=\(pendingCount) downloading=\(downloadingCount) ready=\(readyCount) queued_total=\(queuedTotal) downloaded_total=\(downloadedTotal) validated_total=\(validatedTotal) rendered_total=\(renderedTotal) failed_total=\(failedTotal) lastError=\(lastError)")
    }

    private func removeFile(_ url: URL) {
        try? FileManager.default.removeItem(at: url)
    }
}


// MARK: - Picker Window Controller

private final class ElasticRowView: NSTableRowView {
    var isHeaderRow: Bool = false {
        didSet {
            hover = false
            updateState(animated: false, preset: .crisp)
        }
    }
    var rowIndex: Int = 0 {
        didSet { updateGlassAppearance() }
    }
    var reduceMotionProvider: () -> Bool = { false }
    var isActiveWindowProvider: () -> Bool = { true }
    var animationEnabledProvider: () -> Bool = { true }
    var hoverChanged: ((Int, Bool) -> Void)?
    weak var horizontalAlignmentReferenceView: NSView?

    private var hover = false
    private var tracking: NSTrackingArea?
    private let outlineLayer = CAShapeLayer()
    private let edgeLayer = CAShapeLayer()
    private let selectionLayer = CALayer()
    private let hoverLayer = CALayer()
    private let tabInsetX: CGFloat = 6
    private let tabContractInsetX: CGFloat = 8
    fileprivate static let tabInsetY: CGFloat = 1

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true

        outlineLayer.fillColor = NSColor.clear.cgColor
        outlineLayer.lineWidth = 1
        outlineLayer.lineJoin = .round
        outlineLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0

        edgeLayer.fillColor = NSColor.clear.cgColor
        edgeLayer.lineWidth = 1
        edgeLayer.lineJoin = .round
        edgeLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0

        hoverLayer.masksToBounds = true
        hoverLayer.backgroundColor = NSColor.clear.cgColor

        selectionLayer.masksToBounds = true
        selectionLayer.backgroundColor = NSColor.clear.cgColor

        if let root = layer {
            root.masksToBounds = false
            root.insertSublayer(hoverLayer, at: 0)
            root.insertSublayer(selectionLayer, above: hoverLayer)
            root.insertSublayer(edgeLayer, above: selectionLayer)
            root.insertSublayer(outlineLayer, above: edgeLayer)
        }
        updateState(animated: false)
    }

    required init?(coder: NSCoder) { fatalError() }

    override func drawSelection(in dirtyRect: NSRect) {
        // Selection is rendered via CALayers; suppress default row highlight.
    }
    
    override func drawBackground(in dirtyRect: NSRect) {
        // Default state is text-only on the unified table glass surface.
    }
    
    override func drawSeparator(in dirtyRect: NSRect) {
        // No per-row separators; the list reads like a Safari context menu.
    }

    override var isSelected: Bool {
        didSet { updateState(animated: true, preset: .microBounce) }
    }

    override var isEmphasized: Bool {
        didSet { updateState(animated: true, preset: .crisp) }
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let tracking { removeTrackingArea(tracking) }

        guard !isHeaderRow else { return }

        let opts: NSTrackingArea.Options = [.mouseEnteredAndExited, .activeAlways, .inVisibleRect]
        let area = NSTrackingArea(rect: bounds, options: opts, owner: self, userInfo: nil)
        addTrackingArea(area)
        tracking = area
    }

    override func mouseEntered(with event: NSEvent) {
        hover = true
        hoverChanged?(rowIndex, true)
        updateState(animated: true, preset: .microBounce)
    }

    override func mouseExited(with event: NSEvent) {
        hover = false
        hoverChanged?(rowIndex, false)
        updateState(animated: true, preset: .microBounce)
    }

    override func layout() {
        super.layout()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        outlineLayer.frame = bounds
        edgeLayer.frame = bounds
        updateRowGeometry()
        CATransaction.commit()
    }

    func refreshDepth(animated: Bool, preset: SpringPreset = .microBounce) {
        updateState(animated: animated, preset: preset)
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        updateGlassAppearance()
    }

    private func updateRowGeometry() {
        let b = bounds
        guard b.width > 1, b.height > 1 else { return }

        // Apple-quality “content width contract”:
        // The hover/selection “glass tab” must match the search bar glass left/right edges exactly.
        // We solve this by aligning in window coordinates (no reliance on NSTableView/NSScrollView sizing quirks).
        let tabRect: NSRect = {
            guard let ref = horizontalAlignmentReferenceView,
                  let rowWindow = window,
                  ref.window === rowWindow else {
                return b.insetBy(dx: tabInsetX, dy: Self.tabInsetY)
            }

            let refInWindow = ref.convert(ref.bounds, to: nil)
            let rowInWindow = convert(bounds, to: nil)

            let rawMinX = refInWindow.minX - rowInWindow.minX
            let rawMaxX = refInWindow.maxX - rowInWindow.minX
            var minX = rawMinX + tabContractInsetX
            var maxX = rawMaxX - tabContractInsetX
            minX = max(0, min(b.width, minX))
            maxX = max(0, min(b.width, maxX))
            if maxX <= minX {
                // If the contract is too tight (very narrow rows), fall back to the full contract width.
                minX = max(0, min(b.width, rawMinX))
                maxX = max(0, min(b.width, rawMaxX))
            }
            let w = max(1, maxX - minX)
            return NSRect(x: minX, y: Self.tabInsetY, width: w, height: max(1, b.height - (2 * Self.tabInsetY)))
        }()
        let radius = min(12, max(8, tabRect.height / 2))

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        hoverLayer.frame = tabRect
        selectionLayer.frame = tabRect
        hoverLayer.cornerRadius = radius
        selectionLayer.cornerRadius = radius

        let inset = max(0.5, outlineLayer.lineWidth / 2)
        let rect = tabRect.insetBy(dx: inset, dy: inset)
        let pathRadius = max(0, radius - inset)
        let path = CGPath(roundedRect: rect, cornerWidth: pathRadius, cornerHeight: pathRadius, transform: nil)
        outlineLayer.path = path
        edgeLayer.path = path
        CATransaction.commit()
    }

    private func updateGlassAppearance() {
        let active = isActiveWindowProvider()
        let dark = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let selected = isSelected && !isHeaderRow
        let hovered = hover && !isHeaderRow
        let showTab = selected || hovered

        // Safari-like glass menu tab strokes (no per-row background in the default state).
        let inactiveScale: CGFloat = active ? 1.0 : 0.82
        let lightStrokeAlpha: CGFloat = (selected ? (dark ? 0.34 : 0.16) : (dark ? 0.26 : 0.12)) * inactiveScale
        let darkStrokeAlpha: CGFloat = (selected ? (dark ? 0.22 : 0.10) : (dark ? 0.16 : 0.08)) * inactiveScale

        outlineLayer.strokeColor = NSColor.white.withAlphaComponent(showTab ? lightStrokeAlpha : 0).cgColor
        edgeLayer.strokeColor = NSColor.black.withAlphaComponent(showTab ? darkStrokeAlpha : 0).cgColor
    }

    private func updateState(animated: Bool, preset: SpringPreset = .microBounce) {
        guard let layer else { return }

        let reduceMotion = reduceMotionProvider()
        let motionEnabled = animationEnabledProvider()
        let active = isActiveWindowProvider()
        let selected = isSelected && !isHeaderRow
        let hovered = hover && !isHeaderRow

        updateRowGeometry()
        updateGlassAppearance()

        // Context-menu style: rows are text-only by default; only hover/selection draws a rounded tab.
        let dark = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let accent = resolvedSystemColor(.controlAccentColor)
        let inactiveScale: CGFloat = active ? 1.0 : 0.82

        let hoverFill = accent.withAlphaComponent((dark ? 0.12 : 0.10) * inactiveScale)
        let selectFill = accent.withAlphaComponent((dark ? 0.20 : 0.16) * inactiveScale)
        hoverLayer.backgroundColor = hoverFill.cgColor
        selectionLayer.backgroundColor = selectFill.cgColor

        func setOpacity(_ target: CALayer, to value: Float, duration: CFTimeInterval) {
            let from = target.presentation()?.opacity ?? target.opacity
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            target.opacity = value
            CATransaction.commit()
            guard animated, motionEnabled, !reduceMotion else { return }
            let anim = CABasicAnimation(keyPath: "opacity")
            anim.fromValue = from
            anim.toValue = value
            anim.duration = duration
            anim.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            target.add(anim, forKey: "fade_opacity")
        }

        setOpacity(hoverLayer, to: (hovered && !selected) ? 1.0 : 0.0, duration: 0.11)
        setOpacity(selectionLayer, to: selected ? 1.0 : 0.0, duration: 0.11)
        setOpacity(outlineLayer, to: (selected || hovered) ? 1.0 : 0.0, duration: 0.10)
        setOpacity(edgeLayer, to: (selected || hovered) ? 1.0 : 0.0, duration: 0.10)

        // Keep the row itself stable (no lift/scale/shadow) for a Safari-like menu feel.
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.transform = CATransform3DIdentity
        layer.shadowOpacity = 0
        layer.shadowRadius = 0
        layer.shadowOffset = .zero
        CATransaction.commit()
    }
}

private final class GlassMenuRowView: NSTableRowView {
    var rowInsets = NSEdgeInsets(top: 3, left: 6, bottom: 3, right: 6)
    var isActiveWindowProvider: () -> Bool = { true }
    var isInteractive: Bool = true {
        didSet {
            if !isInteractive, let tracking { removeTrackingArea(tracking) }
            if !isInteractive { hover = false }
            updateState(animated: false)
        }
    }
    var rowIndex: Int = 0
    var hoverChanged: ((Int, Bool) -> Void)?
    var outlineOnly = false {
        didSet { updateState(animated: false) }
    }

    private var hover = false
    private var tracking: NSTrackingArea?
    private let hoverLayer = CALayer()
    private let selectionLayer = CALayer()
    private let outlineLayer = CAShapeLayer()
    private let edgeLayer = CAShapeLayer()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        hoverLayer.backgroundColor = NSColor.clear.cgColor
        selectionLayer.backgroundColor = NSColor.clear.cgColor
        outlineLayer.fillColor = NSColor.clear.cgColor
        outlineLayer.strokeColor = NSColor.clear.cgColor
        outlineLayer.lineWidth = 1
        outlineLayer.lineJoin = .round
        outlineLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
        outlineLayer.opacity = 0

        edgeLayer.fillColor = NSColor.clear.cgColor
        edgeLayer.strokeColor = NSColor.clear.cgColor
        edgeLayer.lineWidth = 1
        edgeLayer.lineJoin = .round
        edgeLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
        edgeLayer.opacity = 0
        if let root = layer {
            root.masksToBounds = false
            root.insertSublayer(hoverLayer, at: 0)
            root.insertSublayer(selectionLayer, above: hoverLayer)
            root.insertSublayer(edgeLayer, above: selectionLayer)
            root.insertSublayer(outlineLayer, above: edgeLayer)
        }
    }

    required init?(coder: NSCoder) { fatalError() }

    override func drawSelection(in dirtyRect: NSRect) {
        // Selection is rendered by layers.
    }

    override func drawBackground(in dirtyRect: NSRect) {
        // Default is transparent.
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let tracking { removeTrackingArea(tracking) }
        guard isInteractive else { return }
        let opts: NSTrackingArea.Options = [.mouseEnteredAndExited, .activeAlways, .inVisibleRect]
        let area = NSTrackingArea(rect: bounds, options: opts, owner: self, userInfo: nil)
        addTrackingArea(area)
        tracking = area
    }

    override func mouseEntered(with event: NSEvent) {
        guard isInteractive else { return }
        hover = true
        hoverChanged?(rowIndex, true)
        updateState(animated: true)
    }

    override func mouseExited(with event: NSEvent) {
        guard isInteractive else { return }
        hover = false
        hoverChanged?(rowIndex, false)
        updateState(animated: true)
    }

    func setHoverState(_ hovered: Bool, animated: Bool, notify: Bool = true) {
        guard isInteractive, hover != hovered else { return }
        hover = hovered
        if notify {
            hoverChanged?(rowIndex, hovered)
        }
        updateState(animated: animated)
    }

    override var isSelected: Bool {
        didSet { updateState(animated: true) }
    }

    override func layout() {
        super.layout()
        updateRowGeometry()
    }

    private func updateRowGeometry() {
        let b = bounds
        guard b.width > 1, b.height > 1 else { return }
        let rect = NSRect(
            x: rowInsets.left,
            y: rowInsets.bottom,
            width: max(1, b.width - rowInsets.left - rowInsets.right),
            height: max(1, b.height - rowInsets.top - rowInsets.bottom)
        )
        let radius = min(10, rect.height / 2)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        hoverLayer.frame = rect
        selectionLayer.frame = rect
        hoverLayer.cornerRadius = radius
        selectionLayer.cornerRadius = radius
        outlineLayer.frame = b
        edgeLayer.frame = b
        let inset = max(0.5, outlineLayer.lineWidth / 2)
        let outlineRect = rect.insetBy(dx: inset, dy: inset)
        let outlineRadius = max(0, radius - inset)
        let path = CGPath(roundedRect: outlineRect,
                          cornerWidth: outlineRadius,
                          cornerHeight: outlineRadius,
                          transform: nil)
        outlineLayer.path = path
        edgeLayer.path = path
        CATransaction.commit()
    }

    private func updateState(animated: Bool) {
        guard let layer else { return }
        let active = isActiveWindowProvider()
        let selected = isInteractive && isSelected
        let hovered = isInteractive && hover
        let dark = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let inactiveScale: CGFloat = active ? 1.0 : 0.82

        func setOpacity(_ target: CALayer, to value: Float, duration: CFTimeInterval) {
            let from = target.presentation()?.opacity ?? target.opacity
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            target.opacity = value
            CATransaction.commit()
            guard animated else { return }
            let anim = CABasicAnimation(keyPath: "opacity")
            anim.fromValue = from
            anim.toValue = value
            anim.duration = duration
            anim.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            target.add(anim, forKey: "fade_opacity")
        }

        if outlineOnly {
            hoverLayer.backgroundColor = NSColor.clear.cgColor
            selectionLayer.backgroundColor = NSColor.clear.cgColor

            let showTab = selected || hovered
            let lightStrokeAlpha: CGFloat = (selected ? (dark ? 0.34 : 0.16) : (dark ? 0.26 : 0.12)) * inactiveScale
            let darkStrokeAlpha: CGFloat = (selected ? (dark ? 0.22 : 0.10) : (dark ? 0.16 : 0.08)) * inactiveScale

            outlineLayer.strokeColor = NSColor.white.withAlphaComponent(showTab ? lightStrokeAlpha : 0).cgColor
            edgeLayer.strokeColor = NSColor.black.withAlphaComponent(showTab ? darkStrokeAlpha : 0).cgColor

            setOpacity(hoverLayer, to: 0.0, duration: 0.08)
            setOpacity(selectionLayer, to: 0.0, duration: 0.08)
            setOpacity(outlineLayer, to: showTab ? 1.0 : 0.0, duration: 0.10)
            setOpacity(edgeLayer, to: showTab ? 1.0 : 0.0, duration: 0.10)
        } else {
            let accent = resolvedSystemColor(.controlAccentColor)
            let hoverFill = accent.withAlphaComponent((dark ? 0.14 : 0.10) * inactiveScale)
            let selectFill = accent.withAlphaComponent((dark ? 0.22 : 0.16) * inactiveScale)
            hoverLayer.backgroundColor = hoverFill.cgColor
            selectionLayer.backgroundColor = selectFill.cgColor

            let hoverVisible = hovered && !selected
            setOpacity(hoverLayer, to: hoverVisible ? 1.0 : 0.0, duration: 0.11)
            setOpacity(selectionLayer, to: selected ? 1.0 : 0.0, duration: 0.11)
            setOpacity(outlineLayer, to: 0.0, duration: 0.08)
            setOpacity(edgeLayer, to: 0.0, duration: 0.08)
        }

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.transform = CATransform3DIdentity
        layer.shadowOpacity = 0
        layer.shadowRadius = 0
        layer.shadowOffset = .zero
        CATransaction.commit()
    }
}

private final class ContextMenuItemView: NSView {
    static let contentInsets = NSEdgeInsets(top: 3, left: 16, bottom: 3, right: 16)
    static let minWidth: CGFloat = 180
    private static let highlightInsetX: CGFloat = 2
    private static let highlightInsetY: CGFloat = 1
    private static let highlightCornerRadius: CGFloat = 4

    private let textField = NSTextField(labelWithString: "")
    private let highlightLayer = CALayer()
    private var tracking: NSTrackingArea?
    private var isHovering = false
    private var isMenuHighlighted = false
    private var lastActiveState = false

    var reduceMotionProvider: () -> Bool = { false }
    weak var menuItem: NSMenuItem? {
        didSet { updateAppearance(animated: false) }
    }

    static func rowHeight(for font: NSFont) -> CGFloat {
        let base = ceil(font.ascender - font.descender)
        return max(20, base + contentInsets.top + contentInsets.bottom)
    }

    init(frame: NSRect, title: String, font: NSFont) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.masksToBounds = false

        highlightLayer.backgroundColor = NSColor.clear.cgColor
        highlightLayer.cornerRadius = Self.highlightCornerRadius
        layer?.addSublayer(highlightLayer)

        textField.font = font
        textField.lineBreakMode = .byTruncatingTail
        textField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        textField.stringValue = title
        addSubview(textField)

        updateAppearance(animated: false)
    }

    required init?(coder: NSCoder) { fatalError() }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let tracking { removeTrackingArea(tracking) }
        let opts: NSTrackingArea.Options = [.mouseEnteredAndExited, .activeAlways, .inVisibleRect]
        let area = NSTrackingArea(rect: bounds, options: opts, owner: self, userInfo: nil)
        addTrackingArea(area)
        tracking = area
    }

    func setMenuHighlighted(_ highlighted: Bool, animated: Bool) {
        isMenuHighlighted = highlighted
        updateAppearance(animated: animated)
    }

    override func mouseEntered(with event: NSEvent) {
        isHovering = true
        updateAppearance(animated: true)
    }

    override func mouseExited(with event: NSEvent) {
        isHovering = false
        updateAppearance(animated: true)
    }

    override func mouseDown(with event: NSEvent) {
        guard let item = menuItem, item.isEnabled else { return }
        if let action = item.action {
            NSApp.sendAction(action, to: item.target, from: item)
        }
        item.menu?.cancelTracking()
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        bounds.contains(point) ? self : nil
    }

    override func layout() {
        super.layout()
        let insets = Self.contentInsets
        let textRect = NSRect(
            x: insets.left,
            y: insets.bottom,
            width: max(1, bounds.width - insets.left - insets.right),
            height: max(1, bounds.height - insets.top - insets.bottom)
        )
        textField.frame = textRect

        let highlightRect = bounds.insetBy(dx: Self.highlightInsetX, dy: Self.highlightInsetY)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        highlightLayer.frame = highlightRect
        highlightLayer.cornerRadius = Self.highlightCornerRadius
        CATransaction.commit()
    }

    private func updateAppearance(animated: Bool) {
        let enabled = menuItem?.isEnabled ?? true
        let active = enabled && (isHovering || isMenuHighlighted)
        let highlightColor = active ? resolvedSystemColor(.selectedMenuItemColor) : .clear

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        highlightLayer.backgroundColor = highlightColor.cgColor
        CATransaction.commit()

        if !enabled {
            textField.textColor = NSColor.disabledControlTextColor
        } else if active {
            textField.textColor = NSColor.selectedMenuItemTextColor
        } else {
            textField.textColor = resolvedSystemColor(.labelColor)
        }

        let shouldAnimate = animated && (active != lastActiveState)
        lastActiveState = active
        applyHoverBounce(to: textField,
                         hovered: active,
                         animated: shouldAnimate,
                         reduceMotion: reduceMotionProvider())
    }
}

private final class MenuSeparatorView: NSView {
    var lineInsets = NSEdgeInsets(top: 0, left: 12, bottom: 0, right: 12)
    var lineThickness: CGFloat = 1
    var colorProvider: () -> NSColor = { resolvedSystemColor(.separatorColor).withAlphaComponent(0.35) }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        let w = bounds.width - lineInsets.left - lineInsets.right
        guard w > 1 else { return }
        let scale = window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0
        let thickness = max(1.0 / scale, lineThickness / scale)
        let y = round((bounds.midY - (thickness / 2)) * scale) / scale
        let rect = NSRect(x: lineInsets.left,
                          y: y,
                          width: w,
                          height: thickness)
        colorProvider().setFill()
        rect.fill()
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        needsDisplay = true
    }
}

final class PickerWindowController: NSWindowController,
	                                   NSWindowDelegate,
                                       NSSplitViewDelegate,
	                                   NSTableViewDataSource,
	                                   NSTableViewDelegate,
	                                   NSSearchFieldDelegate,
	                                   NSMenuDelegate,
                                   WKNavigationDelegate {

	    private let publicationStore = PublicationStore()
	    private let searchIndex = SearchIndex()
	    private var paginator = Paginator()
        private let settingsSnapshot: AppSettings = AppSettingsStore.shared.current
	    private var currentPageIndex: Int = 0
	    private var suggestions: [SearchSuggestion] = []
	    private var suggestionSelectionIndex: Int = -1
	    private var suggestionsVisible: Bool = false
	    private var menuItems: [MenuItem] = []
	    private var menuAnchorView: NSView?
	    private var menuSelectionHandler: ((MenuItem) -> Void)?
	    private var keywordsFromAppleScript: [String] = []
        private var recipientNameFromAppleScript: String?
        private var recipientEmailFromAppleScript: String?
	    private let pdfCache = PDFCacheManager()
	    private var pdfLoadToken: Int = 0
	    private var rightHorizontalScrollLocks: [ObjectIdentifier: HorizontalScrollLock] = [:]
	    private var hoveredDataRow: Int?
	    private var hoveredSuggestionRow: Int?
	    private var leftTableUnderlayView: NSView?
	    private var tableScrollObserver: Any?
    private var appTerminationObserver: Any?
    private var rootGlassTintObservers: [Any] = []
    private var rootGlassTintDistributedObservers: [Any] = []
    private var rootGlassTintRecomputeWorkItem: DispatchWorkItem?
    private var listRenderStartTime: CFTimeInterval?
    private var listRenderLogged: Bool = false
    private enum PDFCacheCleanupState { case idle, cleaning, cleaned }
    private var pdfCacheCleanupState: PDFCacheCleanupState = .idle
    private var didLogDebugPDFOverride: Bool = false

    private var allItems: [Paper] { publicationStore.all }
    private var filtered: [Paper] { publicationStore.filtered }

    private var windowBackgroundView: NSView = PassthroughView(frame: .zero)
    private var windowBackgroundImageView: StaticBackgroundImageView?
    private var cachedTitlebarTintFromWindowBackground: NSColor?
    private var titlebarTintView: NSView?
    private var titlebarDividerView: NSView?
    private var titlebarDividerHeightConstraint: NSLayoutConstraint?
    fileprivate var leftCardBackgroundImageView: StaticBackgroundImageView?
    private var rightCardBackgroundImageView: StaticBackgroundImageView?
    fileprivate var leftCardGlowView: CardEdgeGlowView?
    private var rightCardGlowView: CardEdgeGlowView?
    private var glassContainerView: NSView?
    private var glassContainerContentView: NSView?
    fileprivate let searchContainer = SearchFocusContainer(frame: .zero)
    private let searchContentView = NSView(frame: .zero)
    private let headerControlsContainer = HeaderHitTestContainer(frame: .zero)
    private let suggestionsContainer = NSView(frame: .zero)
    private var suggestionsBackground: NSView = PassthroughView(frame: .zero)
    private let suggestionsScroll = NoScrollScrollView(frame: .zero)
    private let suggestionsTable = NoScrollTableView(frame: .zero)
    private let menuShield = MenuDismissView(frame: .zero)
    private let menuContainer = NSView(frame: .zero)
    private var menuBackground: NSView = PassthroughView(frame: .zero)
    private let menuScroll = NoScrollScrollView(frame: .zero)
    private let menuTable = MenuTableView(frame: .zero)
    private var menuOpensUpward = false
    private var searchBackground: NSView = PassthroughView(frame: .zero)
    private let searchOutlineLayer = CAShapeLayer()
    private let searchInnerOutlineLayer = CAShapeLayer()
    private let searchHighlightLayer = CAGradientLayer()
    private let searchFalloffLayer = CAGradientLayer()
    private let searchCenterGlowLayer = CAGradientLayer()
    private let searchMaskLayer = CAShapeLayer()
    private let searchContainerClipLayer = CAShapeLayer()
    private var searchTracking: NSTrackingArea?
    private var searchHover: Bool = false
    private var searchFocused: Bool = false
    private let searchField = NSSearchField(frame: .zero)
    private let searchContainerHeight: CGFloat = 36
    private let searchContainerGap: CGFloat = 8
    private let searchContainerTopInset: CGFloat = 16
    private let searchContentInsetX: CGFloat = 12
    private let searchContentInsetY: CGFloat = 4
    private let headerControlsTopInset: CGFloat = 12
    private let searchFieldMinimumWidth: CGFloat = 140
    private let toolbarControls = NSStackView()
    private let sidebarControlContainer = NSView(frame: .zero)
    private let navControlContainer = NSView(frame: .zero)
    private let pageControlContainer = NSView(frame: .zero)
    private var sidebarControlBackground: NSView = PassthroughView(frame: .zero)
    private var navControlBackground: NSView = PassthroughView(frame: .zero)
    private var pageControlBackground: NSView = PassthroughView(frame: .zero)
    private let sidebarDivider = GlassSeparatorView(frame: .zero)
    private let navDivider = GlassSeparatorView(frame: .zero)
    private let sidebarToggleButton = GlassToolbarButton(frame: .zero)
    private let sidebarMenuButton = GlassToolbarButton(frame: .zero)
    private let backButton = GlassToolbarButton(frame: .zero)
    private let forwardButton = GlassToolbarButton(frame: .zero)
    private let sidebarControlOrnamentOverlay = ShareStyleCapsuleOrnamentOverlayView(frame: .zero)
    private let navControlOrnamentOverlay = ShareStyleCapsuleOrnamentOverlayView(frame: .zero)
    private let rightAuxCardOrnamentOverlay = ShareStyleRoundedRectOrnamentOverlayView(cornerRadius: PANEL_CORNER_RADIUS)
    private let pageMenuButton = GlassToolbarMenuButton(frame: .zero)
    private let rightPanelLeftEdgeButton = ShareToolbarButton(frame: .zero)
    private let rightPanelZoteroEdgeButton = ShareToolbarButton(frame: .zero)
    private let rightPanelRightEdgeButton = ShareToolbarButton(frame: .zero)
    private let rightPanelSettingsEdgeButton = ShareToolbarButton(frame: .zero)
    private var rightPanelLeftEdgeButtonBackground: NSView?
    private var rightPanelZoteroEdgeButtonBackground: NSView?
    private var rightPanelRightEdgeButtonBackground: NSView?
    private var rightPanelSettingsEdgeButtonBackground: NSView?
    private let rightPanelPillControl = MorphingGlassPillControl(frame: .zero)
    fileprivate let splitView = GapSplitView(frame: .zero)
    private var splitDividerHandle: SplitDividerHandleView?

    // Third panel: implemented as a nested split view inside the existing right side,
    // so the current left|viewer divider logic and constraints remain unchanged.
    private let rightSplitContainer = NSView(frame: .zero)
    private let rightSplitView = GapSplitView(frame: .zero)
    private var rightSplitDividerHandle: SplitDividerHandleView?
    private var rightSplitResizeObserver: Any?
    private var rightSplitWillResizeObserver: Any?
    private var rightSplitDividerSpringTimer: Timer?
    private let rightSplitDividerSpringLayer = CALayer()
    private var rightSplitDividerSpringToken: Int = 0
    private var rightAuxPanelVisible: Bool = false
    private var lastRightAuxPanelWidth: CGFloat = 420
    private let minRightAuxPanelWidth: CGFloat = 260
    private var rightAuxContainer: NSView = NSView(frame: .zero)
    private let rightAuxContentView = NSView(frame: .zero)

    // Right-aux: header (title + underline).
    private let rightAuxHeaderLabel = NSTextField(labelWithString: "Chat Session")
    private let rightAuxHeaderRule = NSView(frame: .zero)

    // Third panel: bottom "Ask" bar (Spotlight-style embedded glass search field).
    private let rightAuxAskContainer = SearchFocusContainer(frame: .zero)
    private let rightAuxAskContentView = NSView(frame: .zero)
    private var rightAuxAskBackground: NSView = PassthroughView(frame: .zero)
    private let rightAuxAskOutlineLayer = CAShapeLayer()
    private let rightAuxAskInnerOutlineLayer = CAShapeLayer()
    private let rightAuxAskHighlightLayer = CAGradientLayer()
    private let rightAuxAskFalloffLayer = CAGradientLayer()
    private let rightAuxAskCenterGlowLayer = CAGradientLayer()
    private let rightAuxAskMaskLayer = CAShapeLayer()
    private var rightAuxAskTracking: NSTrackingArea?
    private var rightAuxAskHover: Bool = false
    private var rightAuxAskFocused: Bool = false
    private let rightAuxAskField = NSSearchField(frame: .zero)
    private let rightAuxAskSendIconView = NSImageView(frame: .zero)

    // Right-aux: glassy separator above the typing bar.
    private let rightAuxAskSeparatorView = NSView(frame: .zero)
    private let rightAuxAskSeparatorGradient = CAGradientLayer()
    private let rightAuxAskSeparatorHighlight = CAGradientLayer()

    fileprivate var leftContainer: NSView = NSView(frame: .zero)
    private let leftCardOrnamentOverlay = ShareStyleRoundedRectOrnamentOverlayView(cornerRadius: PANEL_CORNER_RADIUS)
    private let leftContentView = NSView(frame: .zero)
    private let leftHeaderBar = NSView(frame: .zero)
    private let leftHeaderLabel = NSTextField(labelWithString: "")
    private let leftHeaderRule = NSView(frame: .zero)

    private let tableView = NoScrollTableView(frame: .zero)
    private let tableScroll = NoScrollScrollView(frame: .zero)
    private let pageStepperContainer = NSView(frame: .zero)
    private var pageStepperBackground: NSView = PassthroughView(frame: .zero)
    private let pagePrevButton = GlassToolbarButton(frame: .zero)
    private let pageNextButton = GlassToolbarButton(frame: .zero)

    private var rightContainer: NSView = NSView(frame: .zero)
    private let rightCompositeContainer = NSView(frame: .zero)
    private var rightSecondaryContainer: GlassCardView?
    private var rightPrimaryTrailingConstraint: NSLayoutConstraint?
    private var rightPrimaryWidthConstraint: NSLayoutConstraint?
    private var rightSecondaryLeadingConstraint: NSLayoutConstraint?
    private var rightSecondaryWidthConstraint: NSLayoutConstraint?
    private let rightContentView = NSView(frame: .zero)
    private let rightPanelContentHost = RightPanelContentHostView(frame: .zero)
    private let rightPDFBackgroundView = PassthroughView(frame: .zero)
    private let detailsWebView = HorizontalLockedWKWebView(frame: .zero)
    private let pdfView = ZoomablePDFView(frame: .zero)
    private let rightPanelTransitionBlurView = PassthroughVisualEffectView(frame: .zero)
    private let pdfRenderQueue = DispatchQueue(label: "arxiv.pdf.render", qos: .userInitiated, attributes: .concurrent)
    private var pendingRenderWork: DispatchWorkItem?
    private let pdfDocumentCache = NSCache<NSString, PDFDocument>()
    private var pdfScrollDebugOverlay: PDFScrollDebugOverlay?
    private var annotationController: PDFAnnotationCoordinator?

    private var isShowingPDF: Bool = false
    private let pdfZoomStep: CGFloat = 0.1
    private var pdfMagnifyActive: Bool = false
    private var pdfMagnifyAnchorPoint: NSPoint = .zero
    private var pdfMagnifyAnchorPage: PDFPage?
        private var pdfGestureMagnifyBaseScale: CGFloat = 1.0
        private var pdfMagnificationGestureRecognizer: NSMagnificationGestureRecognizer?
    private var pdfZoomCenterAnchorPoint: NSPoint = .zero
    private var pdfZoomCenterAnchorPage: PDFPage?
    private var pdfZoomDebugEnabled: Bool {
        ProcessInfo.processInfo.environment["ARXIV_PDF_ZOOM_DEBUG"] == "1" || settingsSnapshot.advancedDeveloper.enablePDFZoomDebug
    }
    private let pdfZoomDebugAssertEnabled: Bool = ProcessInfo.processInfo.environment["ARXIV_PDF_ZOOM_ASSERT"] == "1"
    private var didRunPDFZoomRepro: Bool = false
    private var pdfZoomReproWorkItem: DispatchWorkItem?
    private var lastTempHTMLURL: URL?

    private var pdfFindHUD: NSView = NSView(frame: .zero)
    private var pdfFindBackgroundView: NSView = NSView(frame: .zero)
    private let pdfFindContentView = NSView(frame: .zero)
    private let pdfFindOutlineLayer = CAShapeLayer()
    private let pdfFindHighlightLayer = CAGradientLayer()
    private let pdfFindFalloffLayer = CAGradientLayer()
    private let pdfFindField = NSSearchField(frame: .zero)
    private let pdfFindCountLabel = NSTextField(labelWithString: "")
    private let pdfFindPrevButton = GlassToolbarButton(frame: .zero)
    private let pdfFindNextButton = GlassToolbarButton(frame: .zero)
    private var pdfFindResults: [PDFSelection] = []
    private var pdfFindIndex: Int = -1
    private var pdfFindQuery: String = ""
    private var pdfFindTracking: NSTrackingArea?
    private var pdfFindHover: Bool = false
    private var pdfFindFocused: Bool = false
    private var pdfFindVisibilityWorkItem: DispatchWorkItem?
    private var pdfFindDepthWorkItem: DispatchWorkItem?

    private var loadingOverlay: NSView = NSView(frame: .zero)
    private let loadingSpinner = NSProgressIndicator(frame: .zero)
    private let loadingLabel = NSTextField(labelWithString: "Scanning Mail…")

    private let listFont = NSFont.systemFont(ofSize: 14)
    private let listBoldFont = NSFont.boldSystemFont(ofSize: 14)
	    private let leftRowTitleFont = NSFont.systemFont(ofSize: 12.75, weight: .regular)
	    private let leftRowSecondaryFont = NSFont.systemFont(ofSize: 12.75, weight: .regular)
	    private let leftRowSecondaryEmphasisFont = NSFont.systemFont(ofSize: 12.75, weight: .medium)
    private let suggestionTitleFont = NSFont.systemFont(ofSize: 13, weight: .medium)
    private let suggestionSubtitleFont = NSFont.systemFont(ofSize: 11.5, weight: .regular)
    private let suggestionRowHeight: CGFloat = 44
    private let suggestionTextInsetX: CGFloat = 16
    private let dropdownHorizontalInset: CGFloat = 10
    private let menuRowHeight: CGFloat = 24
    private let menuSummaryRowHeight: CGFloat = 24
    private let menuSeparatorHeight: CGFloat = 8
    private let menuCornerRadius: CGFloat = 12
    private let menuMinWidth: CGFloat = 180
    private let menuVerticalGap: CGFloat = 6
    private let menuAnchorInsetX: CGFloat = 4
    private let menuCheckmarkSize: CGFloat = 11
    private let menuCheckmarkLeading: CGFloat = 12
    private let menuCheckmarkTextGap: CGFloat = 8
    private var menuTextTrailing: CGFloat { menuTextLeading }
    private let menuRowInsets = NSEdgeInsets(top: 2, left: 6, bottom: 2, right: 6)
    private lazy var dropdownContentInsets = NSEdgeInsets(top: 10,
                                                          left: dropdownHorizontalInset,
                                                          bottom: 10,
                                                          right: dropdownHorizontalInset)
    private let menuFont = NSFont.systemFont(ofSize: 13, weight: .regular)
    private let menuSummaryFont = NSFont.systemFont(ofSize: 13, weight: .medium)
    private let leftRowIconSize: CGFloat = 14
    private let leftRowIconSpacing: CGFloat = 6
    private lazy var leftRowIconImage: NSImage? = {
        let config = NSImage.SymbolConfiguration(pointSize: leftRowIconSize, weight: .regular)
        let base = NSImage(systemSymbolName: "note.text", accessibilityDescription: nil)
            ?? NSImage(systemSymbolName: "doc.text", accessibilityDescription: nil)
        let image = base?.withSymbolConfiguration(config) ?? base
        image?.isTemplate = true
        return image
    }()
    private lazy var menuCheckmarkImage: NSImage? = {
        let config = NSImage.SymbolConfiguration(pointSize: menuCheckmarkSize, weight: .semibold)
        let base = NSImage(systemSymbolName: "checkmark", accessibilityDescription: nil)
        let image = base?.withSymbolConfiguration(config) ?? base
        image?.isTemplate = true
        return image
    }()
    private var keywordSeparatorGap: CGFloat {
        // Space between the two columns; use a single-space width with a tiny buffer.
        let width = (" " as NSString).size(withAttributes: [.font: leftRowSecondaryFont]).width
        return width + 3
    }

    private var menuTextLeading: CGFloat {
        menuCheckmarkLeading + menuCheckmarkSize + menuCheckmarkTextGap
    }

    private let leftCellInsetX: CGFloat = 8
    private let leftCellInsetY: CGFloat = 4
    private var leftCellBottomInsetY: CGFloat {
        max(0, leftCellInsetY - ElasticRowView.tabInsetY)
    }
    private var leftCellVerticalInsetY: CGFloat {
        leftCellInsetY + leftCellBottomInsetY
    }
    private let leftTableUnderlayBottomPadding: CGFloat = 8
    private let minRowHeight: CGFloat = 28
    private var leftRowTextInset: CGFloat {
        leftCellInsetX + leftRowIconSize + leftRowIconSpacing
    }

    private var keywordColumnTabX: CGFloat = 320
    private var cachedMaxLeftTextWidth: CGFloat = 0
    private var cachedRowNumberDigits: Int = 1
    private var headerFramesFrozen = false
    private var cachedHeaderBarFrame = NSRect.zero
    private var cachedHeaderLabelFrame = NSRect.zero
    private var cachedHeaderRuleFrame = NSRect.zero
    private let headerRowHeight: CGFloat = 24

    private var keyMonitor: Any?
    private var pdfWheelMonitor: Any?
    private var selectionClearMonitor: Any?
    private var dividerDragEndMonitor: Any?
    private var windowResizeObserver: Any?
	    private var splitResizeObserver: Any?
    private var splitWillResizeObserver: Any?
    private var hitTestMoveMonitor: Any?
    private var hitTestDownMonitor: Any?
    private var hitTestUpMonitor: Any?
    private var pdfSelectDownMonitor: Any?
    private var pdfSelectDragMonitor: Any?
    private var pdfSelectUpMonitor: Any?
    private var hitTestOverlay: DebugHitTestOverlayView?
    private var layoutDebugDownMonitor: Any?
    private var layoutDebugDragMonitor: Any?
    private var layoutDebugUpMonitor: Any?
    private var layoutDebugDragArmed = false
    private var layoutDebugLastDragLogTime: TimeInterval = 0
    private var layoutDebugOverlay: DebugLayoutOverlayView?
    private weak var layoutDebugRootView: NSView?
    private var dividerDragActive = false
    private var systemDividerDragStartX: CGFloat = 0
    private var systemDividerDragStartLeftWidth: CGFloat = 0
    private var systemDividerDragPendingSplitModeExit = false
    private var dividerHovering = false
	    private var windowFocusObservers: [Any] = []
	    private var windowLiveResizeEndObserver: Any?
	    private var windowScreenObserver: Any?
	    private var dividerSettleWorkItem: DispatchWorkItem?
        private var splitDividerSpringTimer: Timer?
        private let splitDividerSpringLayer = CALayer()
        private var splitDividerSpringToken: Int = 0
	    private var suggestionsVisibilityWorkItem: DispatchWorkItem?
	    private var menuVisibilityWorkItem: DispatchWorkItem?
    private var searchBackgroundFrameObserver: Any?
    private var sidebarVisible = true
    private var lastSidebarWidth: CGFloat = 520
    private var lastRightPanelWidth: CGFloat = 0
    private var rightPanelSplitModeActive = false
    private var didApplyInitialSidebarLayout = false
    private var allowSidebarCollapse = false
    private var sidebarTransitionInProgress = false
    private let minSidebarWidth: CGFloat = 220
    private let maxSidebarWidthFraction: CGFloat = 0.6 // Limit left card growth to 60% of feasible span.
    private let minRightPanelWidth: CGFloat = 260
    private var suppressRowAnimations = false
    private var selectionChangeFromCode = false

    // SidebarAnimator (left sidebar slide)
    private lazy var sidebarAnimator: SidebarAnimator = SidebarAnimator(owner: self)

    private var chatStressToken: UInt64 = 0

    private enum RightPanelViewMode: String {
        case details = "html"
        case pdf = "pdf"
    }

    private func zIndex(in root: NSView, view: NSView?) -> Int? {
        guard let view else { return nil }
        return root.subviews.firstIndex(where: { $0 === view })
    }

    private func updateLayoutDebugOverlay(reason: String) {
        guard debugLayoutEnabled else { return }
        guard let root = layoutDebugRootView ?? window?.contentView else { return }
        guard let overlay = layoutDebugOverlay else { return }

        func rectInRoot(_ view: NSView?) -> NSRect {
            guard let view else { return .zero }
            // Avoid converting coordinates for views not mounted under the same root.
            guard view.window === root.window else { return .zero }
            var current: NSView? = view
            while let c = current {
                if c === root { return view.convert(view.bounds, to: root) }
                current = c.superview
            }
            return .zero
        }

        func siblingIndex(_ view: NSView?) -> Int? {
            guard let view, let parent = view.superview else { return nil }
            return parent.subviews.firstIndex(where: { $0 === view })
        }

        let leftRect = rectInRoot(leftContainer)
        let rightRect = rectInRoot(rightSplitContainer)
        let rightSplitRect = rectInRoot(rightSplitView)
        let rightCompositeRect = rectInRoot(rightCompositeContainer)
        let rightAuxRect = rectInRoot(rightAuxContainer)
        let rightPrimaryRect = rectInRoot(rightContainer)
        let rightSecondaryRect = rectInRoot(rightSecondaryContainer)

        let dividerRectInRoot: NSRect = {
            let r = splitView.dividerRect(at: 0)
            return splitView.convert(r, to: root)
        }()
        let handleRect = rectInRoot(splitDividerHandle)

        let outerZ = zIndex(in: root, view: splitView) ?? -1
        let leftZ = zIndex(in: root, view: leftContainer) ?? -1
        let rightZ = zIndex(in: root, view: rightSplitContainer) ?? -1
        let handleZ = zIndex(in: root, view: splitDividerHandle) ?? -1
        let overlayZ = zIndex(in: root, view: overlay) ?? -1

          let rightSplitSibling = siblingIndex(rightSplitView)
          let rightCompositeSibling = siblingIndex(rightCompositeContainer)
          let rightAuxSibling = siblingIndex(rightAuxContainer)

        overlay.update(items: [
            .init(name: "splitView",
                  rect: rectInRoot(splitView),
                  color: .systemOrange,
                  label: "splitView z=\(outerZ) \(Int(splitView.bounds.width))x\(Int(splitView.bounds.height))"),
            .init(name: "left",
                  rect: leftRect,
                  color: .systemGreen,
                  label: "left z=\(leftZ) w=\(Int(leftContainer.frame.width)) visible=\(sidebarVisible)"),
            .init(name: "right",
                  rect: rightRect,
                  color: .systemBlue,
                  label: "right z=\(rightZ) w=\(Int(rightSplitContainer.frame.width)) aux=\(rightAuxPanelVisible)"),
            .init(name: "right_split",
                rect: rightSplitRect,
                color: .systemTeal,
                label: "rightSplitView sib=\(rightSplitSibling.map(String.init) ?? "-") subviews=\(rightSplitView.subviews.count)"),
            .init(name: "right_composite",
                rect: rightCompositeRect,
                color: .systemIndigo,
                label: "rightComposite sib=\(rightCompositeSibling.map(String.init) ?? "-") w=\(Int(rightCompositeContainer.frame.width))"),
            .init(name: "right_primary",
                rect: rightPrimaryRect,
                color: .systemCyan,
                label: "rightContainer w=\(Int(rightContainer.frame.width))"),
            .init(name: "right_secondary",
                rect: rightSecondaryRect,
                color: .systemYellow,
                label: "rightSecondary split=\(rightPanelSplitModeActive) hidden=\(rightSecondaryContainer?.isHidden ?? true) w=\(Int(rightSecondaryContainer?.frame.width ?? 0))"),
            .init(name: "right_aux",
                rect: rightAuxRect,
                color: .systemBrown,
                label: "rightAux sib=\(rightAuxSibling.map(String.init) ?? "-") mounted=\(rightAuxContainer.superview != nil) w=\(Int(rightAuxContainer.frame.width))"),
            .init(name: "divider_hitbox",
                  rect: dividerRectInRoot,
                  color: .systemRed,
                  label: "dividerRect w=\(Int(dividerRectInRoot.width)) z?"),
            .init(name: "divider_handle",
                  rect: handleRect,
                  color: .systemPink,
                  label: "handle z=\(handleZ) w=\(Int(handleRect.width)) drag=\(dividerDragActive)"),
            .init(name: "overlay",
                  rect: overlay.bounds,
                  color: .systemPurple,
                  label: "overlay z=\(overlayZ) reason=\(reason)"),
        ])

        layoutLog("overlay_update reason=\(reason) left=\(Int(leftContainer.frame.width)) right=\(Int(rightSplitContainer.frame.width)) divider=\(Int(dividerRectInRoot.width)) handle=\(Int(handleRect.width))")
    }

    private func installLayoutDebugEventTracing() {
        guard debugLayoutEnabled else { return }
        guard layoutDebugDownMonitor == nil else { return }

        window?.acceptsMouseMovedEvents = true

        layoutDebugDownMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseDown) { [weak self] event in
            guard let self else { return event }
            guard let rootView = self.window?.contentView else { return event }
            let point = event.locationInWindow
            let hit = rootView.hitTest(point)

            var chain: [String] = []
            var current = hit
            while let view = current {
                chain.append(String(describing: type(of: view)))
                current = view.superview
            }

            let dividerHit = (self.dividerRectInWindow()?.contains(point) == true)
            layoutLog("mouse_down x=\(String(format: "%.1f", point.x)) y=\(String(format: "%.1f", point.y)) dividerHit=\(dividerHit) hit=\(self.describeHitView(hit)) chain=\(chain.joined(separator: " -> "))")
            self.layoutDebugDragArmed = dividerHit
            self.layoutDebugLastDragLogTime = event.timestamp
            self.updateLayoutDebugOverlay(reason: "mouse_down")
            return event
        }

        layoutDebugDragMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseDragged) { [weak self] event in
            guard let self else { return event }
            guard self.layoutDebugDragArmed else { return event }
            let t = event.timestamp
            if t - self.layoutDebugLastDragLogTime > 0.05 {
                self.layoutDebugLastDragLogTime = t
                layoutLog("mouse_drag left=\(Int(self.leftContainer.frame.width)) right=\(Int(self.rightSplitContainer.frame.width)) pressed=\((NSEvent.pressedMouseButtons & 1) != 0)")
                self.updateLayoutDebugOverlay(reason: "mouse_drag")
            }
            return event
        }

        layoutDebugUpMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseUp) { [weak self] event in
            guard let self else { return event }
            let point = event.locationInWindow
            layoutLog("mouse_up x=\(String(format: "%.1f", point.x)) y=\(String(format: "%.1f", point.y)) left=\(Int(self.leftContainer.frame.width)) right=\(Int(self.rightSplitContainer.frame.width))")
            self.layoutDebugDragArmed = false
            self.updateLayoutDebugOverlay(reason: "mouse_up")
            return event
        }
    }

    private enum RightPanelTransitionState: Equatable {
        case idle(RightPanelViewMode)
        case transition(from: RightPanelViewMode, to: RightPanelViewMode)
    }

    // Right-panel view-mode transition lives in `transitionRightPanel`.
    // Divider safety: only layers inside `rightPanelContentHost` are animated; split-view constraints untouched.
    // Motion tuning is centralized in `RightPanelTransitionSpec`.
    private struct RightPanelTransitionSpec {
        let fastCycleThreshold: CFTimeInterval = 0.55
        let fastDuration: CFTimeInterval = 0.22
        let normalDuration: CFTimeInterval = 0.28
        let fastScale: CGFloat = 0.997
        let normalScale: CGFloat = 0.994
        let fastTranslationX: CGFloat = 8
        let normalTranslationX: CGFloat = 11
        let incomingHitTestEnableFraction: CFTimeInterval = 0.4
        let blurEnabled: Bool = true
        let blurMaxOpacity: CGFloat = 0.06
        let blurFadeFraction: CFTimeInterval = 0.35

        func duration(forFastCycle fastCycle: Bool) -> CFTimeInterval {
            fastCycle ? fastDuration : normalDuration
        }

        func scale(forFastCycle fastCycle: Bool) -> CGFloat {
            fastCycle ? fastScale : normalScale
        }

        func translationX(forFastCycle fastCycle: Bool) -> CGFloat {
            fastCycle ? fastTranslationX : normalTranslationX
        }

        func springPreset(forFastCycle fastCycle: Bool) -> SpringPreset {
            fastCycle ? .panelTransitionFast : .panelTransition
        }
    }
    private let rightPanelTransition = RightPanelTransitionSpec()
    private var rightPanelTransitionState: RightPanelTransitionState = .idle(.details)
    private var pendingRightPanelTransitionTarget: RightPanelViewMode?
    private var viewModeTransitionToken: Int = 0
    private var viewModeTransitionWorkItem: DispatchWorkItem?
    private var lastViewModeSwitchTime: CFTimeInterval = 0
    private let sidebarWidthDefaultsKey = "astroStack.sidebarWidth"
    private let sidebarVisibleDefaultsKey = "astroStack.sidebarVisible"
    private let legacySidebarWidthDefaultsKey = "arxivPicker.sidebarWidth"
    private let legacySidebarVisibleDefaultsKey = "arxivPicker.sidebarVisible"

    private let rowMenu = NSMenu(title: "Row Menu")

    private struct SelectionHistoryEntry: Equatable {
        let key: PaperKey
        var isShowingPDF: Bool
    }

    private var selectionHistory: [SelectionHistoryEntry] = []
    private var selectionHistoryIndex: Int = -1
    private var historyNavigationInProgress = false

    private struct RootGlassThemeSignature: Equatable {
        let accentR: Int
        let accentG: Int
        let accentB: Int
        let isDark: Bool
        let bgR: Int
        let bgG: Int
        let bgB: Int
        let alpha: Int
    }

    private struct RootGlassTheme {
        // RootGlassTint (intended visual result).
        let rootTint: NSColor
        let rootTintHighlight: NSColor
        let rootTintShadow: NSColor
        // Compensated tint applied to the actual glass view (so perceived tint remains stable across wallpapers).
        let compensatedFill: NSColor
        // Specialized keyword highlight tint derived from RootGlassTint.
        let keywordHighlight: NSColor
        // Diagnostics
        let rawAccent: NSColor
        let backgroundSample: NSColor
    }

    private var cachedRootGlassThemeSignature: RootGlassThemeSignature?
    private var cachedRootGlassTheme: RootGlassTheme?

    private let payloadPathToWatch: String?
    private var pollTimer: Timer?

    fileprivate var shouldReduceMotion: Bool {
        NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    }

    private func isWindowActiveForAppearance() -> Bool {
        // Lock visuals to the active look so glass/vibrancy never dims on resign-key.
        true
    }

    private var searchDebugEnabled: Bool {
        ProcessInfo.processInfo.environment["ARXIV_SEARCH_DEBUG"] == "1"
    }

    private func terminalDefaultProfileBackgroundColor() -> NSColor? {
        let defaults = UserDefaults(suiteName: "com.apple.Terminal")
        guard let profile = defaults?.string(forKey: "Default Window Settings"),
              let windowSettings = defaults?.dictionary(forKey: "Window Settings"),
              let profileDict = windowSettings[profile] as? [String: Any] else {
            return nil
        }
        let data = (profileDict["BackgroundColor"] as? Data) ?? (profileDict["Background Color"] as? Data)
        guard let data else { return nil }
        guard let color = try? NSKeyedUnarchiver.unarchivedObject(ofClass: NSColor.self, from: data) else {
            return nil
        }
        return color.usingColorSpace(.sRGB) ?? color
    }

    private func terminalDefaultProfileFallbackColor() -> NSColor {
        NSColor(srgbRed: 0.3916090727, green: 0.08498670906, blue: 0.06663744152, alpha: 0.4927956587)
    }

    private func iconAppearanceCustomTintColor() -> NSColor? {
        guard let raw = UserDefaults.standard.string(forKey: "AppleIconAppearanceCustomTintColor") else { return nil }
        let parts = raw.split(whereSeparator: { $0 == " " || $0 == "\t" })
        guard parts.count >= 3 else { return nil }
        let values = parts.prefix(4).compactMap { Double($0) }
        guard values.count >= 3 else { return nil }
        let r = CGFloat(values[0])
        let g = CGFloat(values[1])
        let b = CGFloat(values[2])
        let a = values.count >= 4 ? CGFloat(values[3]) : 1.0
        return NSColor(srgbRed: r, green: g, blue: b, alpha: a)
    }

    private func iconAppearanceBaseTintColor() -> NSColor {
        // RootGlassTint must derive from the user's macOS Accent/Tint color (no hard-coded palette).
        resolvedSystemColor(.controlAccentColor)
    }

    private func rootGlassDebugEnabled() -> Bool {
        DEBUG_ROOT_GLASS_TINT || ProcessInfo.processInfo.environment["ARXIV_DEBUG_ROOT_GLASS_TINT"] == "1"
    }

    private func debugRootGlass(_ message: String) {
        guard rootGlassDebugEnabled() else { return }
        NSLog("[RootGlassTint] \(message)")
    }

    private func colorSignature255(_ color: NSColor) -> (Int, Int, Int) {
        let c = color.usingColorSpace(.deviceRGB) ?? color
        return (
            Int(max(0, min(255, round(c.redComponent * 255)))),
            Int(max(0, min(255, round(c.greenComponent * 255)))),
            Int(max(0, min(255, round(c.blueComponent * 255))))
        )
    }

    private func appleIconStyleTint(from accent: NSColor, isDark: Bool) -> NSColor {
        // "Tinted app icon background" interpretation:
        // richer, slightly darker, more saturated than raw accent, with a gentle tonal curve.
        let color = (accent.usingColorSpace(.deviceRGB) ?? accent)
        var h: CGFloat = 0
        var s: CGFloat = 0
        var v: CGFloat = 0
        var a: CGFloat = 0
        color.getHue(&h, saturation: &s, brightness: &v, alpha: &a)

        let satBoost: CGFloat = isDark ? 1.28 : 1.18
        let briMul: CGFloat = isDark ? 0.70 : 0.78
        let briBias: CGFloat = isDark ? 0.02 : 0.00
        let gamma: CGFloat = isDark ? 1.06 : 1.04

        let sat = min(1.0, max(0.0, s * satBoost))
        var bri = min(1.0, max(0.0, v * briMul + briBias))
        bri = CGFloat(pow(Double(bri), Double(gamma)))

        let out = NSColor(calibratedHue: h, saturation: sat, brightness: bri, alpha: 1.0)
        return out.usingColorSpace(.deviceRGB) ?? out
    }

    private func appleIconDepthTones(from base: NSColor, isDark: Bool) -> (NSColor, NSColor) {
        let c = base.usingColorSpace(.deviceRGB) ?? base
        var h: CGFloat = 0
        var s: CGFloat = 0
        var v: CGFloat = 0
        var a: CGFloat = 0
        c.getHue(&h, saturation: &s, brightness: &v, alpha: &a)

        let hiV = min(1.0, v + (isDark ? 0.08 : 0.06))
        let loV = max(0.0, v - (isDark ? 0.10 : 0.08))
        let hiS = max(0.0, min(1.0, s * (isDark ? 0.96 : 0.94)))
        let loS = max(0.0, min(1.0, s * (isDark ? 1.02 : 1.00)))

        let hi = NSColor(calibratedHue: h, saturation: hiS, brightness: hiV, alpha: 1.0)
        let lo = NSColor(calibratedHue: h, saturation: loS, brightness: loV, alpha: 1.0)
        return (hi.usingColorSpace(.deviceRGB) ?? hi, lo.usingColorSpace(.deviceRGB) ?? lo)
    }

    private func keywordHighlightTint(from root: NSColor, isDark: Bool) -> NSColor {
        // Same hue identity; slightly higher chroma and a touch brighter, with restrained translucency.
        let c = root.usingColorSpace(.deviceRGB) ?? root
        var h: CGFloat = 0
        var s: CGFloat = 0
        var v: CGFloat = 0
        var a: CGFloat = 0
        c.getHue(&h, saturation: &s, brightness: &v, alpha: &a)

        let sat = min(1.0, max(0.0, s * (isDark ? 1.10 : 1.08)))
        let bri = min(1.0, max(0.0, v + (isDark ? 0.05 : 0.03)))
        let alpha = isDark ? 0.28 : 0.20
        let out = NSColor(calibratedHue: h, saturation: sat, brightness: bri, alpha: alpha)
        return out.usingColorSpace(.deviceRGB) ?? out
    }

    private func sampleWindowBackgroundColorBehindFirstCard(samplePixels: Int = 60) -> NSColor {
        // Estimate the background behind the first glass card.
        // Avoid `cacheDisplay` snapshots during startup (can throw AppKit exceptions before the first paint).
        // Use a stable, amortized approximation: composite the wallpaper's average color over the window base.
        let base = (window?.backgroundColor ?? NSColor.black).usingColorSpace(.deviceRGB) ?? NSColor.black
        guard let image = windowBackgroundImageView?.image,
              let avg = averageColor(from: image, sampleSize: max(16, min(96, samplePixels))) else {
            return base
        }
        let t = max(0.0, min(1.0, WINDOW_BACKGROUND_IMAGE_ALPHA))
        return blend(base, (avg.usingColorSpace(.deviceRGB) ?? avg), t: t)
    }

    private func compensatedTintForPerceivedTarget(target: NSColor,
                                                   background: NSColor,
                                                   effectiveAlpha: CGFloat) -> NSColor {
        // Inverse-blend compensation (linear): choose a tint that, when alpha-composited over the sampled background,
        // yields the intended RootGlassTint (stability across wallpaper changes).
        let a = max(0.0001, min(1.0, effectiveAlpha))
        let t = target.usingColorSpace(.deviceRGB) ?? target
        let b = background.usingColorSpace(.deviceRGB) ?? background

        let targetRGB = (srgbToLinear(t.redComponent), srgbToLinear(t.greenComponent), srgbToLinear(t.blueComponent))
        let underRGB = (srgbToLinear(b.redComponent), srgbToLinear(b.greenComponent), srgbToLinear(b.blueComponent))
        let needed = inverseCompositeRGBLinear(targetRGB: targetRGB, underRGB: underRGB, sourceAlpha: a)
        return NSColor(srgbRed: linearToSrgb(needed.0),
                       green: linearToSrgb(needed.1),
                       blue: linearToSrgb(needed.2),
                       alpha: a)
    }

    private func rootGlassTheme() -> RootGlassTheme {
        let isDark = (window?.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua)

        // A) System accent/tint (dynamic, appearance-aware).
        let rawAccent = iconAppearanceBaseTintColor()

        // B) Background estimate for compensation (sample rendered wallpaper behind the first card).
        let bg = sampleWindowBackgroundColorBehindFirstCard()

        // C) Apple "tinted icon background" transform (our intended RootGlassTint).
        let rootTint = appleIconStyleTint(from: rawAccent, isDark: isDark)
        let (hi, lo) = appleIconDepthTones(from: rootTint, isDark: isDark)

        // Stable, representative alpha for the first glass card tint.
        // PANEL_GLASS_ALPHA_MULTIPLIER drives panel transparency without affecting other glass UI.
        let alphaBase = max(0.02, min(0.95, PANEL_GLASS_GRAY_TINT_ALPHA))
        let effectiveAlpha = max(0.01, min(0.95, glassAlpha(alphaBase) * PANEL_GLASS_ALPHA_MULTIPLIER))

        let sigAccent = colorSignature255(rawAccent)
        let sigBG = colorSignature255(bg)
        let sig = RootGlassThemeSignature(
            accentR: sigAccent.0, accentG: sigAccent.1, accentB: sigAccent.2,
            isDark: isDark,
            bgR: sigBG.0, bgG: sigBG.1, bgB: sigBG.2,
            alpha: Int(max(0, min(255, round(effectiveAlpha * 255))))
        )

        if let cachedSig = cachedRootGlassThemeSignature, cachedSig == sig, let cached = cachedRootGlassTheme {
            return cached
        }

        let compensated = compensatedTintForPerceivedTarget(target: rootTint, background: bg, effectiveAlpha: effectiveAlpha)
        let keyword = keywordHighlightTint(from: rootTint, isDark: isDark)

        let theme = RootGlassTheme(
            rootTint: rootTint,
            rootTintHighlight: hi,
            rootTintShadow: lo,
            compensatedFill: compensated,
            keywordHighlight: keyword,
            rawAccent: rawAccent,
            backgroundSample: bg
        )

        cachedRootGlassThemeSignature = sig
        cachedRootGlassTheme = theme

        debugRootGlass("accent=\(sigAccent) bg=\(sigBG) dark=\(isDark) alpha=\(sig.alpha) root=\(cssRGBA(rootTint)) compensated=\(cssRGBA(compensated)) kw=\(cssRGBA(keyword))")
        return theme
    }

    private func installRootGlassTintObservers() {
        guard rootGlassTintObservers.isEmpty else { return }
        // Accent/tint color changes propagate through system color updates.
        rootGlassTintObservers.append(
            NotificationCenter.default.addObserver(
                forName: NSColor.systemColorsDidChangeNotification,
                object: nil,
                queue: .main
            ) { [weak self] _ in
                self?.scheduleRootGlassTintApply(reason: "system_colors")
            }
        )
        // Light/Dark appearance changes. (No public NSApplication appearance-change notification on some SDKs,
        // so listen to the system distributed notification instead.)
        if rootGlassTintDistributedObservers.isEmpty {
            rootGlassTintDistributedObservers.append(
                DistributedNotificationCenter.default().addObserver(
                    forName: Notification.Name("AppleInterfaceThemeChangedNotification"),
                    object: nil,
                    queue: .main
                ) { [weak self] _ in
                    self?.scheduleRootGlassTintApply(reason: "appearance")
                }
            )
        }
        scheduleRootGlassTintApply(reason: "startup", delay: 0.0)
    }

    private func scheduleRootGlassTintApply(reason: String, delay: TimeInterval = 0.06) {
        rootGlassTintRecomputeWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in
            self?.applyRootGlassTintToUI(reason: reason)
        }
        rootGlassTintRecomputeWorkItem = work
        if delay <= 0 {
            DispatchQueue.main.async(execute: work)
        } else {
            DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
        }
    }

    private func updateToolbarGlassCardTint(_ glass: GlassCardView, tint: NSColor) {
        var config = glass.config
        config.tint = tint
        glass.updateConfig(config)
    }

    private func toolbarGlassTintColor() -> NSColor {
        embeddedSearchTintColor(focused: false, hovered: false) ?? baseGlassStyleTintColor()
    }

    private func updateToolbarGlassTint() {
        // Match toolbar glass + pill tint to the search bar glass.
        let toolbarTint = toolbarGlassTintColor()
        applyEmbeddedSearchBarTheme(to: sidebarControlBackground)
        applyEmbeddedSearchBarTheme(to: navControlBackground)
        if let leftGlass = rightPanelLeftEdgeButtonBackground {
            applyEmbeddedSearchBarTheme(to: leftGlass)
        }
        if let zoteroGlass = rightPanelZoteroEdgeButtonBackground {
            applyEmbeddedSearchBarTheme(to: zoteroGlass)
        }
        if let rightGlass = rightPanelRightEdgeButtonBackground {
            applyEmbeddedSearchBarTheme(to: rightGlass)
        }
        if let settingsGlass = rightPanelSettingsEdgeButtonBackground {
            applyEmbeddedSearchBarTheme(to: settingsGlass)
        }
        if let glass = pageControlBackground as? NSGlassEffectView {
            glass.tintColor = toolbarTint
        } else if let effect = pageControlBackground as? NSVisualEffectView {
            effect.layer?.backgroundColor = toolbarTint.cgColor
        }
        rightPanelPillControl.updateTint(toolbarTint)
        applyToolbarGlassRecipe(reason: "tint")
        updateToolbarSeparatorStyle()
    }

    private func toolbarSeparatorPalette() -> (fill: NSColor, glow: NSColor, glowOpacity: Float) {
        let base = (baseGlassStyleTintColor().usingColorSpace(.deviceRGB) ?? baseGlassStyleTintColor())
        let isDark = (window?.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua)
        let isActive = isWindowActiveForAppearance()
        let fillAlpha: CGFloat = isDark ? (isActive ? 0.18 : 0.12) : (isActive ? 0.12 : 0.08)
        let glowAlpha: CGFloat = isDark ? (isActive ? 0.35 : 0.22) : (isActive ? 0.26 : 0.18)
        let glowOpacity: Float = isDark ? (isActive ? 0.42 : 0.24) : (isActive ? 0.30 : 0.18)
        let fill = NSColor(srgbRed: base.redComponent,
                           green: base.greenComponent,
                           blue: base.blueComponent,
                           alpha: fillAlpha)
        let glow = NSColor.white.withAlphaComponent(glowAlpha)
        return (fill, glow, glowOpacity)
    }

    private func splitDividerPalette() -> (fill: NSColor, glow: NSColor, glowOpacity: Float) {
        let base = toolbarSeparatorPalette()
        let fill = base.fill.withAlphaComponent(min(1, base.fill.alphaComponent + 0.08))
        let glow = base.glow.withAlphaComponent(min(1, base.glow.alphaComponent + 0.06))
        let glowOpacity = min(1, base.glowOpacity + 0.08)
        return (fill, glow, glowOpacity)
    }

    private func updateToolbarSeparatorStyle() {
        let palette = toolbarSeparatorPalette()
        sidebarDivider.apply(fill: palette.fill, glow: palette.glow, glowOpacity: palette.glowOpacity)

        // Back/forward divider: match the Share-style black-glass border energy.
        // Keep it subtle and consistent across active/inactive + light/dark.
        let isDark = (window?.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua)
        let isActive = isWindowActiveForAppearance()
        let fillAlpha: CGFloat = isDark ? (isActive ? 0.32 : 0.22) : (isActive ? 0.34 : 0.26)
        let glowAlpha: CGFloat = isDark ? (isActive ? 0.16 : 0.10) : (isActive ? 0.14 : 0.08)
        let glowOpacity: Float = isDark ? (isActive ? 0.22 : 0.12) : (isActive ? 0.18 : 0.10)
        navDivider.apply(fill: NSColor.black.withAlphaComponent(fillAlpha),
                         glow: NSColor.white.withAlphaComponent(glowAlpha),
                         glowOpacity: glowOpacity)
        updateSplitDividerAppearance()
    }

    private func updateSplitDividerAppearance() {
        splitDividerHandle?.refreshStyle()
    }

    private func applyRootGlassTintToUI(reason: String) {
        let shouldRefreshResolvedColors = (reason == "startup"
                                           || reason == "system_colors"
                                           || reason == "appearance")
        // Panels are GlassCardView (layer-only); tint updates are handled internally on appearance change.

        updateToolbarGlassTint()
        updateCardEdgeGlowIntensity()
        updateEmbeddedSearchAppearance(animated: false)
        applySearchBarTheme(to: pdfFindBackgroundView)
        updatePDFFindCapsuleGeometry()
        if shouldRefreshResolvedColors {
            refreshResolvedSystemColors()
        }

        // Ensure keyword highlights stay unified with RootGlassTint.
        if isShowingPDF == false { updateDetails() }
    }

    private func refreshResolvedSystemColors() {
        let searchForeground = mainSearchForegroundColor()
        applySearchFieldTheme(searchField,
                              placeholder: "Search",
                              textColor: searchForeground,
                              placeholderColor: searchForeground,
                              iconColor: searchForeground)

        leftHeaderLabel.textColor = resolvedSystemColor(.secondaryLabelColor)
        updateRightAuxAskSeparatorStyle()
        leftHeaderRule.layer?.backgroundColor = resolvedSystemColor(.separatorColor).cgColor
        rightContainer.layer?.borderColor = resolvedSystemColor(.separatorColor).cgColor
        loadingLabel.textColor = resolvedSystemColor(.labelColor)

        sidebarToggleButton.updateTint()
        sidebarMenuButton.updateTint()
        backButton.updateTint()
        forwardButton.updateTint()
        pageMenuButton.updateTint()

        rightPanelLeftEdgeButton.restingTintColor = searchForeground
        rightPanelZoteroEdgeButton.restingTintColor = searchForeground
        rightPanelRightEdgeButton.restingTintColor = searchForeground
        rightPanelSettingsEdgeButton.restingTintColor = searchForeground
        rightPanelLeftEdgeButton.updateTint()
        rightPanelZoteroEdgeButton.updateTint()
        rightPanelRightEdgeButton.updateTint()
        rightPanelSettingsEdgeButton.updateTint()

        updateVisibleRowSelectionStyling()
        refreshSuggestionTextColors()
        refreshMenuTextColors()
    }

    private func macOSIconTintAdjustedColor(from base: NSColor) -> NSColor {
        let color = base.usingColorSpace(.deviceRGB) ?? base
        var hue: CGFloat = 0
        var saturation: CGFloat = 0
        var brightness: CGFloat = 0
        var alpha: CGFloat = 0
        color.getHue(&hue, saturation: &saturation, brightness: &brightness, alpha: &alpha)

        let hueShift = LIQUID_GLASS_TINT_HUE_SHIFT
        let satBase = saturation * LIQUID_GLASS_TINT_SATURATION_MULTIPLIER + LIQUID_GLASS_TINT_SATURATION_BIAS
        let sat = min(1.0, max(0.0, satBase * WINDOW_GLASS_TINT_SATURATION))
        var bri = min(1.0, max(0.0, brightness * LIQUID_GLASS_TINT_BRIGHTNESS_MULTIPLIER + LIQUID_GLASS_TINT_BRIGHTNESS_BIAS))
        bri = CGFloat(pow(Double(bri), Double(LIQUID_GLASS_TINT_BRIGHTNESS_GAMMA)))
        let h = hue + hueShift
        let adjustedHue = h < 0 ? h + 1 : (h > 1 ? h - 1 : h)
        return NSColor(calibratedHue: adjustedHue, saturation: sat, brightness: bri, alpha: alpha)
    }

    private func liquidGlassAppTintBaseColor() -> NSColor {
        iconAppearanceBaseTintColor()
    }

    private func liquidGlassIconTintColor() -> NSColor {
        macOSIconTintAdjustedColor(from: liquidGlassAppTintBaseColor())
    }

	    private func windowGlassTintColor() -> NSColor {
	        // Compatibility shim: “window glass” no longer exists at the root; use the next dominant glass layer.
	        baseGlassStyleTintColor()
	    }

		    private func windowGlassAdjustedTintColor() -> NSColor {
		        // Kept for call-site stability; window-level underlay adjustments no longer apply.
		        windowGlassTintColor()
		    }

		    private func baseGlassStyleTintColor() -> NSColor {
		        // Authoritative base for UI that previously referenced “window glass”.
		        // Derived from RootGlassTint, but with a lighter alpha so it reads as a subtle top-level reference.
		        let root = rootGlassTheme().rootTint.usingColorSpace(.deviceRGB) ?? rootGlassTheme().rootTint
		        let a = glassAlpha(max(0.0, min(1.0, WINDOW_GLASS_TINT_ALPHA)))
		        return NSColor(srgbRed: root.redComponent, green: root.greenComponent, blue: root.blueComponent, alpha: a)
		    }

		    private func spotlightSearchTintColor() -> NSColor {
		        let base = windowGlassAdjustedTintColor()
		        let boosted = min(1.0, base.alphaComponent * SPOTLIGHT_SEARCH_GLASS_ALPHA_MULTIPLIER)
		        return base.withAlphaComponent(boosted)
		    }

		    private func compensatedSearchBarTintColor() -> NSColor {
	        // Inverse-blend compensation:
	        // Goal/acceptance test: search bar fill matches the window glass around the top-left buttons.
	        // Because the search bar sits above the left glass card, the card’s tint “double-tints” the blur.
	        // We approximate the stack and solve the inverse alpha composite per channel (linear space):
	        // C_out = a * C_tint + (1 - a) * C_under  =>  C_tint = (C_target - (1 - a) * C_under) / a
	        let target = (windowGlassAdjustedTintColor().usingColorSpace(.deviceRGB) ?? windowGlassAdjustedTintColor())
	        let searchAlpha = max(0.02, min(0.9, target.alphaComponent))

	        // Approximate what the search bar sits on: left card tint composited over the window glass tint.
	        let cardTint = (cardGlassTintColor().usingColorSpace(.deviceRGB) ?? cardGlassTintColor())
	        let targetRGB = (srgbToLinear(target.redComponent), srgbToLinear(target.greenComponent), srgbToLinear(target.blueComponent))
	        let cardRGB = (srgbToLinear(cardTint.redComponent), srgbToLinear(cardTint.greenComponent), srgbToLinear(cardTint.blueComponent))
	        let underRGB = compositeRGBLinear(sourceRGB: cardRGB, sourceAlpha: cardTint.alphaComponent, destRGB: targetRGB)

	        let neededRGB = inverseCompositeRGBLinear(targetRGB: targetRGB, underRGB: underRGB, sourceAlpha: searchAlpha)
	        let out = NSColor(srgbRed: linearToSrgb(neededRGB.0),
	                          green: linearToSrgb(neededRGB.1),
	                          blue: linearToSrgb(neededRGB.2),
	                          alpha: searchAlpha)
	        // User-facing adjustment: tweak perceived brightness without changing the blend math above.
	        let adj = max(-1.0, min(1.0, SEARCH_BAR_TINT_BRIGHTNESS_ADJUST))
	        if adj >= 0 {
	            let white = NSColor.white.withAlphaComponent(out.alphaComponent)
	            return blend(out, white, t: adj)
	        } else {
	            let black = NSColor.black.withAlphaComponent(out.alphaComponent)
	            return blend(out, black, t: -adj)
	        }
	    }

    private func spotlightSearchOutlineColor() -> NSColor {
        let tint = windowGlassAdjustedTintColor()
        let lum = relativeLuminance(tint)
        if lum < 0.5 {
            return NSColor.white.withAlphaComponent(SPOTLIGHT_SEARCH_OUTLINE_LIGHT_ALPHA)
        }
        return NSColor.black.withAlphaComponent(SPOTLIGHT_SEARCH_OUTLINE_DARK_ALPHA)
    }

    private func spotlightSearchHighlightColors() -> [CGColor] {
        [
            NSColor.white.withAlphaComponent(SPOTLIGHT_SEARCH_HIGHLIGHT_TOP_ALPHA).cgColor,
            NSColor.white.withAlphaComponent(SPOTLIGHT_SEARCH_HIGHLIGHT_MID_ALPHA).cgColor,
            NSColor.clear.cgColor
        ]
    }

    private func spotlightSearchFalloffColors() -> [CGColor] {
        [
            NSColor.clear.cgColor,
            NSColor.black.withAlphaComponent(SPOTLIGHT_SEARCH_FALLOFF_ALPHA).cgColor
        ]
    }

    private func windowGlassFallbackOverlayColor() -> NSColor {
        let tint = windowGlassTintColor()
        return tint.withAlphaComponent(min(1.0, tint.alphaComponent * 0.7))
    }

    private struct SearchBarTheme {
        let tintColor: NSColor
        let fallbackMaterial: NSVisualEffectView.Material
        let fallbackBlending: NSVisualEffectView.BlendingMode
        let fallbackState: NSVisualEffectView.State
        let emphasized: Bool
        let shadowColor: NSColor
        let shadowOpacity: Float
        let shadowRadius: CGFloat
        let shadowOffset: CGSize
        let font: NSFont
        let secondaryFont: NSFont
        let textColor: NSColor
        let placeholderColor: NSColor
    }

	    private func currentSearchBarTheme() -> SearchBarTheme {
	        let tint = spotlightSearchTintColor()
	        let font = NSFont.systemFont(ofSize: 14.5, weight: .medium)
	        let secondaryFont = NSFont.systemFont(ofSize: 11, weight: .regular)
	        let textColor = colorFromHex(SPOTLIGHT_SEARCH_TEXT_COLOR_HEX)
	            ?? NSColor.white.withAlphaComponent(0.93)
	        let placeholderColor = textColor.withAlphaComponent(SPOTLIGHT_SEARCH_PLACEHOLDER_ALPHA)
        return SearchBarTheme(
            tintColor: tint,
            fallbackMaterial: .headerView,
            fallbackBlending: .withinWindow,
            fallbackState: .active,
            emphasized: true,
            shadowColor: NSColor.black.withAlphaComponent(0.35),
            shadowOpacity: 0.22,
            shadowRadius: 10,
            shadowOffset: CGSize(width: 0, height: -1),
            font: font,
            secondaryFont: secondaryFont,
            textColor: textColor,
            placeholderColor: placeholderColor
        )
    }

    // MARK: iMessage-style glass compose field

    private struct IMessageGlassFieldTheme {
        let tintColor: NSColor
        let fallbackMaterial: NSVisualEffectView.Material
        let fallbackBlending: NSVisualEffectView.BlendingMode
        let fallbackState: NSVisualEffectView.State
        let emphasized: Bool
        let font: NSFont
        let textColor: NSColor
        let placeholderColor: NSColor
        let strokeAlpha: CGFloat
        let innerStrokeAlpha: CGFloat
        let highlightTopAlpha: CGFloat
        let innerShadowBottomAlpha: CGFloat
        let shadowColor: NSColor
        let shadowOpacity: Float
        let shadowRadius: CGFloat
        let shadowOffset: CGSize
    }

    private func currentIMessageGlassFieldTheme() -> IMessageGlassFieldTheme {
        let appearance = activeAppearance()
        let isDark = (appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua)

        // Warm, softly tinted glass (still translucent).
        let base = (baseGlassStyleTintColor().usingColorSpace(.deviceRGB) ?? baseGlassStyleTintColor())
        let warm = (resolvedSystemColor(.systemYellow).usingColorSpace(.deviceRGB) ?? NSColor.systemYellow)
        let tint = blend(base.withAlphaComponent(1.0), warm.withAlphaComponent(1.0), t: 0.60)
            .withAlphaComponent(glassAlpha(isDark ? 0.26 : 0.22))

        let font = NSFont.systemFont(ofSize: 17, weight: .regular)
        // iMessage-like placeholder reads as near-white on warm glass.
        let placeholder = NSColor.white.withAlphaComponent(isDark ? 0.82 : 0.78)
        let text = NSColor.white.withAlphaComponent(isDark ? 0.94 : 0.92)

        // Hairline stroke & shaping.
        let strokeAlpha: CGFloat = isDark ? 0.16 : 0.18
        let innerStrokeAlpha: CGFloat = isDark ? 0.07 : 0.08
        let highlightTopAlpha: CGFloat = 0.11
        let innerShadowBottomAlpha: CGFloat = isDark ? 0.06 : 0.05

        // Minimal lift.
        let shadowColor = NSColor.black.withAlphaComponent(isDark ? 0.42 : 0.32)
        let shadowOpacity: Float = isDark ? 0.14 : 0.10
        let shadowRadius: CGFloat = isDark ? 10 : 8
        let shadowOffset = CGSize(width: 0, height: -0.6)

        return IMessageGlassFieldTheme(
            tintColor: tint,
            fallbackMaterial: .hudWindow,
            fallbackBlending: .withinWindow,
            fallbackState: .active,
            emphasized: true,
            font: font,
            textColor: text,
            placeholderColor: placeholder,
            strokeAlpha: strokeAlpha,
            innerStrokeAlpha: innerStrokeAlpha,
            highlightTopAlpha: highlightTopAlpha,
            innerShadowBottomAlpha: innerShadowBottomAlpha,
            shadowColor: shadowColor,
            shadowOpacity: shadowOpacity,
            shadowRadius: shadowRadius,
            shadowOffset: shadowOffset
        )
    }

    private func iMessagePlaceholder(_ text: String, theme: IMessageGlassFieldTheme) -> NSAttributedString {
        let style = NSMutableParagraphStyle()
        style.lineBreakMode = .byClipping
        return NSAttributedString(
            string: text,
            attributes: [
                .foregroundColor: theme.placeholderColor,
                .font: theme.font,
                .paragraphStyle: style
            ]
        )
    }

    private func applyIMessageGlassFieldTheme(_ field: NSSearchField, placeholder: String) {
        let theme = currentIMessageGlassFieldTheme()
        let placeholderAttr = iMessagePlaceholder(placeholder, theme: theme)

        let previousCell = field.cell as? NSSearchFieldCell
        let preservedMenuTemplate = previousCell?.searchMenuTemplate?.copy() as? NSMenu
            ?? previousCell?.searchMenuTemplate
        let cell = (previousCell as? CenteredSearchFieldCell) ?? CenteredSearchFieldCell(textCell: "")
        if let menuTemplate = preservedMenuTemplate {
            cell.searchMenuTemplate = menuTemplate
        }
        cell.font = theme.font
        cell.placeholderAttributedString = placeholderAttr
        cell.controlSize = .large
        cell.usesSingleLineMode = true
        cell.wraps = false
        cell.isScrollable = true
        cell.lineBreakMode = .byClipping
        cell.truncatesLastVisibleLine = false
        cell.backgroundColor = .clear
        cell.drawsBackground = false
        cell.textColor = theme.textColor
        field.cell = cell

        field.font = theme.font
        field.textColor = theme.textColor
        field.placeholderString = placeholder
        field.placeholderAttributedString = placeholderAttr
        field.lineBreakMode = .byClipping
        field.usesSingleLineMode = true
        field.maximumNumberOfLines = 1
        field.drawsBackground = false
        field.isBordered = false
        field.isBezeled = false
        field.focusRingType = .none
        field.isEditable = true
        field.isSelectable = true
        field.isEnabled = true
        field.controlSize = .large
    }

    private func applyIMessageGlassBackgroundTheme(to background: NSView) {
        let theme = currentIMessageGlassFieldTheme()
        if let glass = background as? NSGlassEffectView {
            glass.style = .regular
            glass.tintColor = theme.tintColor
        } else if let effect = background as? NSVisualEffectView {
            effect.material = theme.fallbackMaterial
            effect.blendingMode = theme.fallbackBlending
            effect.state = theme.fallbackState
            effect.isEmphasized = theme.emphasized
            effect.layer?.backgroundColor = theme.tintColor.cgColor
        }

        background.wantsLayer = true
        background.layer?.shadowColor = theme.shadowColor.cgColor
        background.layer?.shadowOpacity = theme.shadowOpacity
        background.layer?.shadowRadius = theme.shadowRadius
        background.layer?.shadowOffset = theme.shadowOffset
        enforceStableVisualEffectState(background)
    }

    private func enforceStableVisualEffectState(_ view: NSView) {
        // iMessage-like fields should not collapse/shift when window becomes inactive.
        if let effect = view as? NSVisualEffectView {
            effect.state = .active
        }
    }

	    private func searchBarPlaceholder(_ text: String, theme: SearchBarTheme, color: NSColor? = nil) -> NSAttributedString {
	        let style = NSMutableParagraphStyle()
	        style.lineBreakMode = .byClipping
	        let placeholderColor = color ?? theme.placeholderColor
	        return NSAttributedString(
	            string: text,
	            attributes: [
	                .foregroundColor: placeholderColor,
	                .font: theme.font,
	                .kern: -0.15,
	                .paragraphStyle: style
	            ]
	        )
	    }

    private func applySearchBarTheme(to background: NSView) {
        let theme = currentSearchBarTheme()
        // Match the main search bar glass tint exactly (avoid the extra Spotlight-style boost used elsewhere).
        let tint = embeddedSearchTintColor(focused: false, hovered: false)
            ?? toolbarGlassTintColor()
        if let glass = background as? NSGlassEffectView {
            glass.style = .regular
            glass.tintColor = tint
        } else if let effect = background as? NSVisualEffectView {
            effect.material = theme.fallbackMaterial
            effect.blendingMode = theme.fallbackBlending
            effect.state = theme.fallbackState
            effect.isEmphasized = theme.emphasized
            effect.layer?.backgroundColor = tint.cgColor
        } else if let card = background as? GlassCardView {
            var config = card.config
            config.tint = tint
            card.updateConfig(config)
        }

        background.wantsLayer = true
        background.layer?.shadowColor = theme.shadowColor.cgColor
        background.layer?.shadowOpacity = theme.shadowOpacity
        background.layer?.shadowRadius = theme.shadowRadius
        background.layer?.shadowOffset = theme.shadowOffset
        enforceActiveVisualEffectState(background)
    }
	
	    // MARK: Embedded search bar (inset, carved-into-glass look)
	
            private func embeddedSearchTintColor(focused: Bool, hovered: Bool) -> NSColor? {
		        _ = focused
		        _ = hovered
		        // Compensated tint so the search bar reads as the same glass tint as the window UI glass.
		        return compensatedSearchBarTintColor()
		    }

            private struct EmbeddedSearchOrnaments {
                let outlineLayer: CAShapeLayer
                let innerOutlineLayer: CAShapeLayer
                let highlightLayer: CAGradientLayer
                let falloffLayer: CAGradientLayer
                let centerGlowLayer: CAGradientLayer
                let maskLayer: CAShapeLayer
            }

            private var embeddedSearchOrnamentsByView: [ObjectIdentifier: EmbeddedSearchOrnaments] = [:]

            private func ensureEmbeddedSearchOrnaments(on background: NSView) {
                guard let layer = background.layer else { return }
                let id = ObjectIdentifier(background)
                if embeddedSearchOrnamentsByView[id] != nil { return }

                let outline = CAShapeLayer()
                let inner = CAShapeLayer()
                let highlight = CAGradientLayer()
                let falloff = CAGradientLayer()
                let centerGlow = CAGradientLayer()
                let mask = CAShapeLayer()

                outline.fillColor = NSColor.clear.cgColor
                inner.fillColor = NSColor.clear.cgColor
                outline.lineJoin = .round
                outline.lineCap = .round
                inner.lineJoin = .round
                inner.lineCap = .round

                let scale = max(1.0, background.window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0)
                outline.contentsScale = scale
                inner.contentsScale = scale
                highlight.contentsScale = scale
                falloff.contentsScale = scale
                centerGlow.contentsScale = scale
                mask.contentsScale = scale

                outline.lineWidth = SPOTLIGHT_SEARCH_OUTLINE_WIDTH
                inner.lineWidth = SPOTLIGHT_SEARCH_OUTLINE_WIDTH

                highlight.startPoint = CGPoint(x: 0.5, y: 1.0)
                highlight.endPoint = CGPoint(x: 0.5, y: 0.0)
                falloff.startPoint = CGPoint(x: 0.5, y: 1.0)
                falloff.endPoint = CGPoint(x: 0.5, y: 0.0)
                if #available(macOS 10.14, *) {
                    centerGlow.type = .radial
                }
                centerGlow.startPoint = CGPoint(x: 0.5, y: 0.5)
                centerGlow.endPoint = CGPoint(x: 1.0, y: 1.0)

                layer.addSublayer(centerGlow)
                layer.addSublayer(highlight)
                layer.addSublayer(falloff)
                layer.addSublayer(inner)
                layer.addSublayer(outline)
                layer.mask = mask

                embeddedSearchOrnamentsByView[id] = EmbeddedSearchOrnaments(
                    outlineLayer: outline,
                    innerOutlineLayer: inner,
                    highlightLayer: highlight,
                    falloffLayer: falloff,
                    centerGlowLayer: centerGlow,
                    maskLayer: mask
                )
            }

            private func updateEmbeddedSearchOrnaments(_ background: NSView, cornerRadius: CGFloat) {
                guard let layer = background.layer else { return }
                let id = ObjectIdentifier(background)
                guard let o = embeddedSearchOrnamentsByView[id] else { return }

                // Match the Share-style outline recipe but rendered in white.
                let borderAlpha: CGFloat = 0.78
                let innerBorderAlpha: CGFloat = 0.34
                let highlightTopAlpha: CGFloat = 0.18
                let highlightMidAlpha: CGFloat = 0.06
                let falloffAlpha: CGFloat = 0.18
                let centerGlowAlpha: CGFloat = 0.07

                let bounds = background.bounds
                let outerRect = bounds.insetBy(dx: SPOTLIGHT_SEARCH_OUTLINE_WIDTH / 2, dy: SPOTLIGHT_SEARCH_OUTLINE_WIDTH / 2)
                let innerRect = bounds.insetBy(dx: SPOTLIGHT_SEARCH_OUTLINE_WIDTH / 2 + 1.0, dy: SPOTLIGHT_SEARCH_OUTLINE_WIDTH / 2 + 1.0)
                let outerPath = CGPath(roundedRect: outerRect,
                                       cornerWidth: max(0, cornerRadius - (SPOTLIGHT_SEARCH_OUTLINE_WIDTH / 2)),
                                       cornerHeight: max(0, cornerRadius - (SPOTLIGHT_SEARCH_OUTLINE_WIDTH / 2)),
                                       transform: nil)
                let innerPath = CGPath(roundedRect: innerRect,
                                       cornerWidth: max(0, cornerRadius - (SPOTLIGHT_SEARCH_OUTLINE_WIDTH / 2) - 1.0),
                                       cornerHeight: max(0, cornerRadius - (SPOTLIGHT_SEARCH_OUTLINE_WIDTH / 2) - 1.0),
                                       transform: nil)
                let maskPath = CGPath(roundedRect: bounds,
                                      cornerWidth: cornerRadius,
                                      cornerHeight: cornerRadius,
                                      transform: nil)

                CATransaction.begin()
                CATransaction.setDisableActions(true)
                o.outlineLayer.frame = bounds
                o.innerOutlineLayer.frame = bounds
                o.highlightLayer.frame = bounds
                o.falloffLayer.frame = bounds
                o.centerGlowLayer.frame = bounds
                o.maskLayer.frame = bounds

                o.outlineLayer.path = outerPath
                o.innerOutlineLayer.path = innerPath
                o.maskLayer.path = maskPath

                o.outlineLayer.strokeColor = NSColor.white.withAlphaComponent(borderAlpha).cgColor
                o.innerOutlineLayer.strokeColor = NSColor.white.withAlphaComponent(innerBorderAlpha).cgColor
                o.highlightLayer.colors = [
                    NSColor.white.withAlphaComponent(highlightTopAlpha).cgColor,
                    NSColor.white.withAlphaComponent(highlightMidAlpha).cgColor,
                    NSColor.clear.cgColor
                ]
                o.falloffLayer.colors = [
                    NSColor.clear.cgColor,
                    NSColor.white.withAlphaComponent(falloffAlpha).cgColor
                ]
                o.centerGlowLayer.colors = [
                    NSColor.white.withAlphaComponent(centerGlowAlpha).cgColor,
                    NSColor.clear.cgColor
                ]
                // Keep the layer itself clean; the ornamentation defines the capsule edge.
                layer.shadowOpacity = 0
                layer.shadowRadius = 0
                layer.shadowOffset = .zero
                CATransaction.commit()
            }
	
	    private func applyEmbeddedSearchBarTheme(to background: NSView) {
	        let tint = embeddedSearchTintColor(focused: false, hovered: false)
	        if let glass = background as? NSGlassEffectView {
	            glass.style = .regular
	            glass.tintColor = tint
	        } else if let effect = background as? NSVisualEffectView {
	            let theme = currentSearchBarTheme()
	            effect.material = theme.fallbackMaterial
	            effect.blendingMode = theme.fallbackBlending
	            effect.state = theme.fallbackState
	            effect.isEmphasized = theme.emphasized
	            effect.layer?.backgroundColor = (tint ?? .clear).cgColor
	        }
	
	        background.wantsLayer = true
	        background.layer?.shadowOpacity = 0
	        background.layer?.shadowRadius = 0
	        background.layer?.shadowOffset = .zero
	        enforceActiveVisualEffectState(background)
	    }

            private struct ToolbarEdgeBlackBorderOrnaments {
                let outlineLayer: CAShapeLayer
                let innerOutlineLayer: CAShapeLayer
                let highlightLayer: CAGradientLayer
                let falloffLayer: CAGradientLayer
            }

            private var toolbarEdgeBlackBorderByView: [ObjectIdentifier: ToolbarEdgeBlackBorderOrnaments] = [:]

            private func ensureToolbarEdgeBlackBorder(on background: NSView) {
                guard let layer = background.layer else { return }
                let id = ObjectIdentifier(background)
                if toolbarEdgeBlackBorderByView[id] != nil { return }

                let outline = CAShapeLayer()
                let inner = CAShapeLayer()
                let highlight = CAGradientLayer()
                let falloff = CAGradientLayer()

                outline.fillColor = NSColor.clear.cgColor
                inner.fillColor = NSColor.clear.cgColor
                outline.lineJoin = .round
                outline.lineCap = .round
                inner.lineJoin = .round
                inner.lineCap = .round

                let scale = max(1.0, background.window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0)
                outline.contentsScale = scale
                inner.contentsScale = scale
                highlight.contentsScale = scale
                falloff.contentsScale = scale

                outline.lineWidth = 1
                inner.lineWidth = 1

                highlight.startPoint = CGPoint(x: 0.5, y: 1.0)
                highlight.endPoint = CGPoint(x: 0.5, y: 0.0)
                falloff.startPoint = CGPoint(x: 0.5, y: 1.0)
                falloff.endPoint = CGPoint(x: 0.5, y: 0.0)

                layer.addSublayer(highlight)
                layer.addSublayer(falloff)
                layer.addSublayer(inner)
                layer.addSublayer(outline)

                toolbarEdgeBlackBorderByView[id] = ToolbarEdgeBlackBorderOrnaments(
                    outlineLayer: outline,
                    innerOutlineLayer: inner,
                    highlightLayer: highlight,
                    falloffLayer: falloff
                )
            }

            private func updateToolbarEdgeBlackBorder(_ background: NSView, cornerRadius: CGFloat) {
                guard let layer = background.layer else { return }
                let id = ObjectIdentifier(background)
                guard let o = toolbarEdgeBlackBorderByView[id] else { return }

                // Keep the outer rim decisively black while preserving a subtle glass highlight.
                let borderAlpha: CGFloat = 0.70
                let innerBorderAlpha: CGFloat = 0.32
                let highlightTopAlpha: CGFloat = 0.18
                let highlightMidAlpha: CGFloat = 0.06
                let falloffAlpha: CGFloat = 0.18

                let bounds = background.bounds
                let outerRect = bounds.insetBy(dx: 0.5, dy: 0.5)
                let innerRect = bounds.insetBy(dx: 1.5, dy: 1.5)
                let outerPath = CGPath(roundedRect: outerRect,
                                       cornerWidth: max(0, cornerRadius - 0.5),
                                       cornerHeight: max(0, cornerRadius - 0.5),
                                       transform: nil)
                let innerPath = CGPath(roundedRect: innerRect,
                                       cornerWidth: max(0, cornerRadius - 1.5),
                                       cornerHeight: max(0, cornerRadius - 1.5),
                                       transform: nil)

                CATransaction.begin()
                CATransaction.setDisableActions(true)
                o.outlineLayer.frame = bounds
                o.innerOutlineLayer.frame = bounds
                o.highlightLayer.frame = bounds
                o.falloffLayer.frame = bounds

                o.outlineLayer.path = outerPath
                o.innerOutlineLayer.path = innerPath

                o.outlineLayer.strokeColor = NSColor.black.withAlphaComponent(borderAlpha).cgColor
                o.innerOutlineLayer.strokeColor = NSColor.black.withAlphaComponent(innerBorderAlpha).cgColor
                o.highlightLayer.colors = [
                    NSColor.white.withAlphaComponent(highlightTopAlpha).cgColor,
                    NSColor.white.withAlphaComponent(highlightMidAlpha).cgColor,
                    NSColor.clear.cgColor
                ]
                o.falloffLayer.colors = [
                    NSColor.clear.cgColor,
                    NSColor.black.withAlphaComponent(falloffAlpha).cgColor
                ]

                // Ensure the border reads as a capsule.
                layer.masksToBounds = true
                layer.shadowOpacity = 0
                layer.shadowRadius = 0
                layer.shadowOffset = .zero
                CATransaction.commit()
            }

            private func applyToolbarEdgeBlackGlassyBorder(to background: NSView, cornerRadius: CGFloat) {
                background.wantsLayer = true
                ensureToolbarEdgeBlackBorder(on: background)
                updateToolbarEdgeBlackBorder(background, cornerRadius: cornerRadius)
            }
	
	    private func updateEmbeddedSearchAppearance(animated: Bool) {
            let focused = searchFocused
            let hovered = searchHover
            let hasQuery = !searchField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            let engaged = focused || suggestionsVisible || hasQuery
            updateEmbeddedSearchAppearance(
                background: searchBackground,
                focused: focused,
                hovered: hovered,
                engaged: engaged,
                outlineLayer: searchOutlineLayer,
                innerOutlineLayer: searchInnerOutlineLayer,
                highlightLayer: searchHighlightLayer,
                falloffLayer: searchFalloffLayer,
                centerGlowLayer: searchCenterGlowLayer,
                animated: animated
            )
	    }

        private func updateEmbeddedSearchAppearance(background: NSView,
                                                   focused: Bool,
                                                   hovered: Bool,
                                                   engaged: Bool,
                                                   outlineLayer: CAShapeLayer,
                                                   innerOutlineLayer: CAShapeLayer,
                                                   highlightLayer: CAGradientLayer,
                                                   falloffLayer: CAGradientLayer,
                                                   centerGlowLayer: CAGradientLayer,
                                                   animated: Bool) {
            guard let layer = background.layer else { return }
            let reduce = shouldReduceMotion || !animated

            let borderAlpha: CGFloat = engaged ? 0.20 : (hovered ? 0.12 : 0.09)
            let innerBorderAlpha: CGFloat = engaged ? 0.12 : (hovered ? 0.08 : 0.06)

            let highlightTopAlpha: CGFloat = engaged ? 0.32 : (hovered ? 0.24 : 0.18)
            let highlightMidAlpha: CGFloat = engaged ? 0.14 : (hovered ? 0.09 : 0.06)
            let falloffAlpha: CGFloat = engaged ? 0.34 : (hovered ? 0.28 : 0.26)
            let centerGlowAlpha: CGFloat = engaged ? 0.14 : (hovered ? 0.08 : 0.07)

            let tint = embeddedSearchTintColor(focused: focused, hovered: hovered)

            CATransaction.begin()
            if reduce {
                CATransaction.setDisableActions(true)
            } else {
                CATransaction.setAnimationDuration(0.14)
                CATransaction.setAnimationTimingFunction(CAMediaTimingFunction(name: .easeInEaseOut))
            }

            // Ensure any previous “floating pill” transforms/shadows are cleared.
            layer.transform = CATransform3DIdentity
            layer.shadowOpacity = 0
            layer.shadowRadius = 0
            layer.shadowOffset = .zero

            outlineLayer.strokeColor = NSColor.white.withAlphaComponent(borderAlpha).cgColor
            innerOutlineLayer.strokeColor = NSColor.white.withAlphaComponent(innerBorderAlpha).cgColor

            highlightLayer.colors = [
                NSColor.white.withAlphaComponent(highlightTopAlpha).cgColor,
                NSColor.white.withAlphaComponent(highlightMidAlpha).cgColor,
                NSColor.clear.cgColor
            ]
            falloffLayer.colors = [
                NSColor.clear.cgColor,
                NSColor.black.withAlphaComponent(falloffAlpha).cgColor
            ]
            centerGlowLayer.colors = [
                NSColor.white.withAlphaComponent(centerGlowAlpha).cgColor,
                NSColor.clear.cgColor
            ]

            if let glass = background as? NSGlassEffectView {
                glass.tintColor = tint
            } else if let effect = background as? NSVisualEffectView {
                effect.layer?.backgroundColor = (tint ?? .clear).cgColor
            }

            CATransaction.commit()
        }

    private func applySearchFieldTheme(_ field: NSSearchField,
                                       placeholder: String,
                                       textColor: NSColor? = nil,
                                       placeholderColor: NSColor? = nil,
                                       iconColor: NSColor? = nil) {
        let theme = currentSearchBarTheme()
        let resolvedTextColor = textColor ?? theme.textColor
        let placeholderAttr = searchBarPlaceholder(placeholder, theme: theme, color: placeholderColor)

        let previousCell = field.cell as? NSSearchFieldCell
        let preservedMenuTemplate = previousCell?.searchMenuTemplate?.copy() as? NSMenu
            ?? previousCell?.searchMenuTemplate
        let cell = (previousCell as? CenteredSearchFieldCell) ?? CenteredSearchFieldCell(textCell: "")
        if let menuTemplate = preservedMenuTemplate {
            // Keep the stock search menu so the magnifier button still drops down the history template.
            cell.searchMenuTemplate = menuTemplate
        }
        cell.font = theme.font
        cell.placeholderAttributedString = placeholderAttr
        cell.controlSize = .large
        cell.usesSingleLineMode = true
        cell.wraps = false
        cell.isScrollable = true
        cell.lineBreakMode = .byClipping
        cell.truncatesLastVisibleLine = false
        cell.backgroundColor = .clear
        cell.drawsBackground = false
        cell.textColor = resolvedTextColor
        field.cell = cell

        field.font = theme.font
        field.textColor = resolvedTextColor
        field.placeholderString = placeholder
        field.placeholderAttributedString = placeholderAttr
        field.lineBreakMode = .byClipping
        field.usesSingleLineMode = true
        field.maximumNumberOfLines = 1
        field.drawsBackground = false
        field.isBordered = false
        field.isBezeled = false
        field.focusRingType = .none
        field.isEditable = true
        field.isSelectable = true
        field.isEnabled = true
        field.controlSize = .large

        if let iconColor {
            applySearchFieldIconColor(field, color: iconColor)
        }
    }

	    private func applySearchFieldIconColor(_ field: NSSearchField, color: NSColor) {
	        guard let cell = field.cell as? NSSearchFieldCell else { return }
	        if let image = cell.searchButtonCell?.image {
	            let tinted = tintedImage(image, color: color)
	            cell.searchButtonCell?.image = tinted
	            cell.searchButtonCell?.alternateImage = tinted
	        }
	        if let image = cell.cancelButtonCell?.image {
	            let tinted = tintedImage(image, color: color)
	            cell.cancelButtonCell?.image = tinted
	            cell.cancelButtonCell?.alternateImage = tinted
	        }
	    }

    private func applySearchBarDepth(to view: NSView, focused: Bool, hovered: Bool, animated: Bool) {
        guard let layer = view.layer else { return }
        let reduce = shouldReduceMotion

        let focusBoost: CGFloat = focused ? SPOTLIGHT_SEARCH_FOCUS_SCALE_BOOST : 0.0
        let hoverBoost: CGFloat = hovered ? SPOTLIGHT_SEARCH_HOVER_SCALE_BOOST : 0.0
        let targetScale = 1.0 + min(0.025, focusBoost + hoverBoost)
        let targetShadowOpacity: Float = focused ? 0.32 : (hovered ? 0.22 : currentSearchBarTheme().shadowOpacity)
        let targetShadowRadius: CGFloat = focused ? 8 : (hovered ? 6 : currentSearchBarTheme().shadowRadius)
        let targetShadowOffset = CGSize(width: 0, height: focused ? -0.9 : -0.5)
        let transform = CATransform3DMakeScale(targetScale, targetScale, 1.0)

        if animated {
            animateLayer(layer, keyPath: "transform", to: transform, preset: .microBounce, reduceMotion: reduce, basicDuration: 0.16)
            animateLayer(layer, keyPath: "shadowOpacity", to: targetShadowOpacity, preset: .microBounce, reduceMotion: reduce, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowRadius", to: targetShadowRadius, preset: .microBounce, reduceMotion: reduce, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowOffset", to: targetShadowOffset, preset: .microBounce, reduceMotion: reduce, basicDuration: 0.14)
        } else {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.transform = transform
            layer.shadowOpacity = targetShadowOpacity
            layer.shadowRadius = targetShadowRadius
            layer.shadowOffset = targetShadowOffset
            CATransaction.commit()
        }
    }

    private func panelClearGlassTintColor() -> NSColor {
        NSColor(white: 1.0, alpha: max(0.0, min(1.0, PANEL_CLEAR_GLASS_TINT_ALPHA)))
    }

    private func baseLiquidGlassConfig() -> GlassCardKit.GlassCardConfig {
        var config = GlassCardKit.GlassCardConfig()
        config.transmission = DROPDOWN_GLASS_TRANSMISSION
        config.diffusionAmount = DROPDOWN_GLASS_DIFFUSION_AMOUNT
        return config
    }

    private func dropdownGlassConfig() -> GlassCardKit.GlassCardConfig {
        var config = baseLiquidGlassConfig()
        config.cornerRadius = menuCornerRadius
        config.tint = panelClearGlassTintColor()
        return config
    }

    private func makeDropdownGlassCard() -> GlassCardView {
        let config = dropdownGlassConfig()
        let card = GlassCardKit.makeGlassCard(config: config) { [weak self] rectInWindow, scale in
            self?.captureWindowBackgroundRegion(in: rectInWindow, scale: scale)
        }
        card.translatesAutoresizingMaskIntoConstraints = true
        card.wantsLayer = true
        if #available(macOS 10.13, *) {
            card.layer?.cornerCurve = .continuous
        }
        return card
    }

    private func makeRightSecondaryGlassCard() -> GlassCardView {
        let config = dropdownGlassConfig()
        let card = GlassCardKit.makeGlassCard(config: config) { [weak self] rectInWindow, scale in
            self?.captureWindowBackgroundRegion(in: rectInWindow, scale: scale)
        }
        card.translatesAutoresizingMaskIntoConstraints = false
        card.wantsLayer = true
        if #available(macOS 10.13, *) {
            card.layer?.cornerCurve = .continuous
        }
        return card
    }

    private func makeToolbarButtonGlassCard(tint: NSColor) -> GlassCardView {
        let config = toolbarGlassConfig(cornerRadius: 10, tint: tint)
        let card = GlassCardKit.makeGlassCard(config: config) { [weak self] rectInWindow, scale in
            self?.captureWindowBackgroundRegion(in: rectInWindow, scale: scale)
        }
        card.translatesAutoresizingMaskIntoConstraints = true
        card.wantsLayer = true
        if #available(macOS 10.13, *) {
            card.layer?.cornerCurve = .continuous
        }
        return card
    }

    private func makeToolbarGroupGlassCard(cornerRadius: CGFloat, tint: NSColor) -> GlassCardView {
        let config = toolbarGlassConfig(cornerRadius: cornerRadius, tint: tint)
        let card = GlassCardKit.makeGlassCard(config: config) { [weak self] rectInWindow, scale in
            self?.captureWindowBackgroundRegion(in: rectInWindow, scale: scale)
        }
        card.translatesAutoresizingMaskIntoConstraints = false
        card.wantsLayer = true
        if #available(macOS 10.13, *) {
            card.layer?.cornerCurve = .continuous
        }
        return card
    }

    private func cardGlassTintColor() -> NSColor {
        // Neutral “clear glass” tint: no hue, but very low alpha so the background passes through (~90% translucent).
        // This affects only the glass material's tinting, not the opacity of the panel content.
        return NSColor(white: 0.0, alpha: max(0.0, min(1.0, PANEL_CLEAR_GLASS_TINT_ALPHA)))
    }

	    private func leftTableUnderlayTintColor() -> NSColor {
	        let w = max(0.0, min(1.0, LEFT_TABLE_UNDERLAY_TINT_WHITE))
	        let a = max(0.0, min(1.0, LEFT_TABLE_UNDERLAY_TINT_ALPHA))
	        return applyGlassTransparency(NSColor(white: w, alpha: a))
	    }

    private func rightCardBaseColor() -> NSColor {
        let glassBase = windowGlassTintColor().withAlphaComponent(1.0)
        if let image = rightCardBackgroundImageView?.image,
           let avg = averageColor(from: image) {
            let t = max(0.0, min(1.0, RIGHT_CARD_BACKGROUND_IMAGE_ALPHA))
            return blend(glassBase, avg, t: t)
        }
        if let image = windowBackgroundImageView?.image,
           let avg = averageColor(from: image) {
            let t = max(0.0, min(1.0, WINDOW_BACKGROUND_IMAGE_ALPHA * 0.6))
            return blend(glassBase, avg, t: t)
        }
        return glassBase
    }

    private func rightCardTextPalette() -> TextPalette {
        adaptiveTextPalette(baseColor: rightCardBaseColor(), linkHex: RIGHT_LINK_COLOR_HEX)
    }

    private var uiDebugEnabled: Bool {
        ProcessInfo.processInfo.environment["ARXIV_UI_DEBUG"] == "1" || settingsSnapshot.advancedDeveloper.enableUIDebug
    }

    private var pdfSelectDebugEnabled: Bool {
        ProcessInfo.processInfo.environment["ARXIV_PDF_SELECT_DEBUG"] == "1"
    }

    private var samplePDFEnabled: Bool {
        ProcessInfo.processInfo.environment["ARXIV_SAMPLE_PDF"] == "1"
    }

    private func uiLog(_ message: String) {
        guard uiDebugEnabled else { return }
        NSLog("[UIDebug] \(message)")
    }

    private func pdfSelectLog(_ message: String) {
        guard pdfSelectDebugEnabled else { return }
        NSLog("[PDFSelectDebug] \(message)")
    }

    private func installSamplePDFIfNeeded() {
        guard samplePDFEnabled else { return }
        let doc = makeSampleTextPDFDocument()
        pdfView.document = doc
        hideLoading()
        hidePDFFindHUD()
        showPDFPanel(animated: false)
        pdfSelectLog("installed_sample_pdf pages=\(doc.pageCount)")
    }

    private func makeSampleTextPDFDocument() -> PDFDocument {
        let data = NSMutableData()
        guard let consumer = CGDataConsumer(data: data as CFMutableData) else {
            return PDFDocument()
        }

        var mediaBox = CGRect(x: 0, y: 0, width: 612, height: 792) // US Letter @ 72 dpi
        guard let ctx = CGContext(consumer: consumer, mediaBox: &mediaBox, nil) else {
            return PDFDocument()
        }

        ctx.beginPDFPage(nil)
        ctx.setFillColor(NSColor.white.cgColor)
        ctx.fill(mediaBox)

        let text = """
    WATCHER FAKE PDF (selection test)

Drag to highlight this text.
Use Shift+Arrow keys to extend selection once the PDF view is focused.

The quick brown fox jumps over the lazy dog.
0123456789 — Symbols: α β γ ∑ ∫ ≤ ≥ ≠
"""

        let attr = NSAttributedString(
            string: text,
            attributes: [
                .font: NSFont.systemFont(ofSize: 16, weight: .regular),
                .foregroundColor: NSColor.black
            ]
        )

        ctx.saveGState()
        ctx.textMatrix = .identity
        ctx.translateBy(x: 0, y: mediaBox.height)
        ctx.scaleBy(x: 1, y: -1)

        let frameRect = mediaBox.insetBy(dx: 72, dy: 72)
        let path = CGPath(rect: frameRect, transform: nil)
        let framesetter = CTFramesetterCreateWithAttributedString(attr as CFAttributedString)
        let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: 0, length: attr.length), path, nil)
        CTFrameDraw(frame, ctx)

        ctx.restoreGState()
        ctx.endPDFPage()
        ctx.closePDF()

        return PDFDocument(data: data as Data) ?? PDFDocument()
    }

    private var viewModeTransitionDebugEnabled: Bool {
        ProcessInfo.processInfo.environment["ARXIV_VIEWMODE_DEBUG"] == "1"
    }

    private func viewModeLog(_ message: String) {
        guard viewModeTransitionDebugEnabled else { return }
        NSLog("[ViewModeTransition] \(message)")
    }

    private func debugConstraintDescription(_ constraint: NSLayoutConstraint) -> String {
        func describeItem(_ item: AnyObject?) -> String {
            guard let item else { return "nil" }
            if let view = item as? NSView {
                let addr = Unmanaged.passUnretained(view).toOpaque()
                let id = view.identifier?.rawValue ?? ""
                let label = debugViewLabel(view)
                let labelPart = label.isEmpty ? "" : " label=\(label)"
                let idPart = id.isEmpty ? "" : " id=\(id)"
                return "\(type(of: view)):\(addr)\(labelPart)\(idPart)"
            }
            return "\(item)"
        }

        let first = describeItem(constraint.firstItem)
        let second = describeItem(constraint.secondItem)
        let relation: String
        switch constraint.relation {
        case .lessThanOrEqual: relation = "<="
        case .equal: relation = "=="
        case .greaterThanOrEqual: relation = ">="
        @unknown default: relation = "?"
        }
        let id = constraint.identifier ?? ""
        return "[\(id)] \(first).\(constraint.firstAttribute) \(relation) \(second).\(constraint.secondAttribute) + \(String(format: "%.2f", constraint.constant)) pri=\(Int(constraint.priority.rawValue)) active=\(constraint.isActive)"
    }

    private func debugViewChain(from view: NSView, maxDepth: Int = 10) -> String {
        var parts: [String] = []
        var current: NSView? = view
        var depth = 0
        while let v = current, depth < maxDepth {
            let addr = Unmanaged.passUnretained(v).toOpaque()
            let id = v.identifier?.rawValue ?? ""
            let label = debugViewLabel(v)
            var piece = "\(type(of: v)):\(addr)"
            if !label.isEmpty { piece += " label=\(label)" }
            if !id.isEmpty { piece += " id=\(id)" }
            parts.append(piece)
            current = v.superview
            depth += 1
        }
        return parts.joined(separator: " -> ")
    }

    private func debugLogConstraints(for view: NSView, label: String) {
        let h = view.constraintsAffectingLayout(for: .horizontal)
        let v = view.constraintsAffectingLayout(for: .vertical)
        uiLog("constraints \(label) h=\(h.count) v=\(v.count)")
        for c in h { uiLog("  H \(debugConstraintDescription(c))") }
        for c in v { uiLog("  V \(debugConstraintDescription(c))") }
        if let superview = view.superview {
            let related = superview.constraints.filter { $0.firstItem as? NSView === view || $0.secondItem as? NSView === view }
            uiLog("  superview constraints \(label) count=\(related.count)")
            for c in related { uiLog("    S \(debugConstraintDescription(c))") }
        }
    }

    private func launchAuditConstraintConstants(reason: String, threshold: CGFloat = 1_000_000) {
        guard launchDebugEnabled, let root = window?.contentView else { return }
        var seen = Set<ObjectIdentifier>()
        var anomalies: [NSLayoutConstraint] = []

        func consider(_ constraint: NSLayoutConstraint) {
            let id = ObjectIdentifier(constraint)
            guard !seen.contains(id) else { return }
            seen.insert(id)
            let constant = constraint.constant
            if !constant.isFinite || abs(constant) > threshold {
                anomalies.append(constraint)
            }
        }

        func walk(_ view: NSView) {
            for c in view.constraints { consider(c) }
            for c in view.constraintsAffectingLayout(for: .horizontal) { consider(c) }
            for c in view.constraintsAffectingLayout(for: .vertical) { consider(c) }
            for sub in view.subviews { walk(sub) }
        }

        walk(root)
        launchLog("constraint_audit reason=\(reason) anomalies=\(anomalies.count)")
        for c in anomalies {
            launchLog("constraint_anomaly \(debugConstraintDescription(c))")
			if let v = c.firstItem as? NSView {
				launchLog("constraint_anomaly_firstItem_chain \(debugViewChain(from: v))")
			}
        }
    }

    private func debugViewLabel(_ view: NSView) -> String {
        if view === splitView { return "SplitView" }
        if view === leftContainer { return "LeftPanel" }
        if view === rightContainer { return "RightPanel" }
        if view === searchContainer { return "SearchContainer" }
        if view === headerControlsContainer { return "HeaderControls" }
        if view === suggestionsContainer { return "SuggestionsContainer" }
        if view === menuContainer { return "MenuContainer" }
        return ""
    }

    private func debugDumpViewTree(from view: NSView, depth: Int = 0) {
        let indent = String(repeating: "  ", count: depth)
        let addr = Unmanaged.passUnretained(view).toOpaque()
        let label = debugViewLabel(view)
        let frame = view.frame
        uiLog("\(indent)\(type(of: view)) \(addr) \(label) frame=\(String(format: "%.1f", frame.origin.x)),\(String(format: "%.1f", frame.origin.y)) \(String(format: "%.1f", frame.size.width))x\(String(format: "%.1f", frame.size.height)) tamic=\(view.translatesAutoresizingMaskIntoConstraints) hidden=\(view.isHidden)")
        for (index, sub) in view.subviews.enumerated() {
            uiLog("\(indent)  [\(index)]")
            debugDumpViewTree(from: sub, depth: depth + 1)
        }
    }

    private func debugDumpViewHierarchy(reason: String) {
        guard uiDebugEnabled, let root = window?.contentView else { return }
        uiLog("view_tree_begin reason=\(reason)")
        debugDumpViewTree(from: root)
        debugLogConstraints(for: splitView, label: "splitView")
        debugLogConstraints(for: leftContainer, label: "leftContainer")
        debugLogConstraints(for: rightContainer, label: "rightContainer")
        if let rect = dividerRectInWindow() {
            uiLog("divider_rect window=\(String(format: "%.1f", rect.origin.x)),\(String(format: "%.1f", rect.origin.y)) \(String(format: "%.1f", rect.size.width))x\(String(format: "%.1f", rect.size.height))")
        } else {
            uiLog("divider_rect window=nil")
        }
        uiLog("view_tree_end reason=\(reason)")
    }

    private func debugProbeDividerHitTest(reason: String) {
        guard uiDebugEnabled, let root = window?.contentView,
              let rect = dividerRectInWindow() else { return }
        let point = NSPoint(x: rect.midX, y: rect.midY)
        let hit = root.hitTest(point)
        var chain: [String] = []
        var current = hit
        while let view = current {
            chain.append(String(describing: type(of: view)))
            current = view.superview
        }
        let chainText = chain.joined(separator: " -> ")
        uiLog("divider_probe reason=\(reason) point=\(String(format: "%.1f", point.x)),\(String(format: "%.1f", point.y)) hit=\(describeHitView(hit)) chain=\(chainText)")
    }

    private func debugProbeToolbarHitTests(reason: String) {
        guard uiDebugEnabled, let root = window?.contentView else { return }

        func probe(_ view: NSView, name: String) {
            guard let viewWindow = view.window, let rootWindow = root.window, viewWindow === rootWindow else {
                uiLog("hit_probe skip name=\(name) reason=\(reason) window_mismatch")
                return
            }
            let rectInWindow = view.convert(view.bounds, to: nil)
            let point = NSPoint(x: rectInWindow.midX, y: rectInWindow.midY)
            let hit = root.hitTest(point)
            var chain: [String] = []
            var current = hit
            while let v = current {
                chain.append(String(describing: type(of: v)))
                current = v.superview
            }
            let pointText = "\(String(format: "%.1f", point.x)),\(String(format: "%.1f", point.y))"
            let chainText = chain.joined(separator: " -> ")
            uiLog("hit_probe name=\(name) reason=\(reason) point=\(pointText) hit=\(describeHitView(hit)) chain=\(chainText)")
        }

        probe(sidebarToggleButton, name: "sidebar_toggle")
        probe(sidebarMenuButton, name: "sidebar_menu")
        probe(backButton, name: "nav_back")
        probe(forwardButton, name: "nav_forward")
        probe(rightPanelPillControl, name: "pill")
    }

    private func debugProbeViewerHitTest(reason: String) {
        guard uiDebugEnabled, let root = window?.contentView else { return }
        guard let viewWindow = rightPanelContentHost.window,
              let rootWindow = root.window,
              viewWindow === rootWindow else {
            uiLog("viewer_probe skip reason=\(reason) window_mismatch")
            return
        }
        let rectInWindow = rightPanelContentHost.convert(rightPanelContentHost.bounds, to: nil)
        let point = NSPoint(x: rectInWindow.midX, y: rectInWindow.midY)
        let hit = root.hitTest(point)
        uiLog("viewer_probe reason=\(reason) host=\(Int(rectInWindow.width))x\(Int(rectInWindow.height)) isShowingPDF=\(isShowingPDF) pdfHidden=\(pdfView.isHidden) detailsHidden=\(detailsWebView.isHidden) hit=\(describeHitView(hit))")
    }

    private func dividerRectInWindow() -> NSRect? {
        guard splitView.subviews.count >= 2 else { return nil }
        let rect = splitView.dividerRect(at: 0)
        guard rect.width > 0, rect.height > 0 else { return nil }
        return splitView.convert(rect, to: nil)
    }

    private func logDividerState(_ event: String) {
        guard uiDebugEnabled else { return }
        let leftW = leftContainer.frame.width
        let rightW = rightContainer.frame.width
        let totalW = splitView.bounds.width
        let dividerX = splitView.dividerRect(at: 0).minX
        uiLog("divider_\(event) left=\(Int(leftW)) right=\(Int(rightW)) total=\(Int(totalW)) pos=\(Int(dividerX))")
    }

    private func describeHitView(_ view: NSView?) -> String {
        guard let view else { return "nil" }
        let name = String(describing: type(of: view))
        let frame = view.frame
        return "\(name) frame=\(Int(frame.origin.x)),\(Int(frame.origin.y)) \(Int(frame.size.width))x\(Int(frame.size.height)) hidden=\(view.isHidden)"
    }

    private func logSearchDebug(_ message: String) {
        guard searchDebugEnabled else { return }
        NSLog("[SearchDebug] \(message)")
    }

    private func enforceActiveVisualEffectState(_ view: NSView) {
        // Keep effect views stable across active/inactive and appearance changes.
        // Do NOT force emphasis here; emphasis affects perceived brightness (especially in Light Mode).
        if let effect = view as? NSVisualEffectView {
            effect.state = .followsWindowActiveState
        }
    }

    private func makeGlassEffectView(passthrough: Bool = false,
                                     cornerRadius: CGFloat = 0,
                                     tintColor: NSColor? = nil,
                                     style: NSGlassEffectView.Style = .regular,
                                     fallbackMaterial: NSVisualEffectView.Material = .hudWindow,
                                     fallbackBlending: NSVisualEffectView.BlendingMode = .withinWindow,
                                     fallbackState: NSVisualEffectView.State = .active,
                                     emphasized: Bool = true,
                                     forceVisualEffectFallback: Bool = false) -> NSView {
        if !forceVisualEffectFallback, #available(macOS 26.0, *) {
            let view: NSGlassEffectView = passthrough ? PassthroughGlassEffectView(frame: .zero) : NSGlassEffectView(frame: .zero)
            view.cornerRadius = cornerRadius
            view.tintColor = tintColor
            view.style = style
            view.translatesAutoresizingMaskIntoConstraints = false
            enforceActiveVisualEffectState(view)
            return view
        }

        let view: NSVisualEffectView = passthrough ? PassthroughVisualEffectView(frame: .zero) : NSVisualEffectView(frame: .zero)
        view.blendingMode = fallbackBlending
        view.material = fallbackMaterial
        view.state = fallbackState
        view.isEmphasized = emphasized
        view.translatesAutoresizingMaskIntoConstraints = false
        view.wantsLayer = true
        view.layer?.cornerRadius = cornerRadius
        view.layer?.masksToBounds = true
        if #available(macOS 10.13, *) {
            view.layer?.cornerCurve = .continuous
        }
        if let tint = tintColor {
            view.layer?.backgroundColor = tint.cgColor
        }
        enforceActiveVisualEffectState(view)
        return view
    }

    private func embedContentView(_ content: NSView, into host: NSView) {
        if #available(macOS 26.0, *), let glass = host as? NSGlassEffectView {
            glass.contentView = content
            content.frame = glass.bounds
            content.autoresizingMask = [.width, .height]
        } else {
            if let effect = host as? NSVisualEffectView {
                effect.addSubview(content)
            } else {
                host.addSubview(content)
            }
            content.frame = host.bounds
            content.autoresizingMask = [.width, .height]
        }
    }

    private func installGlassContainerIfAvailable(on content: NSView) -> NSView {
        glassContainerView = nil
        glassContainerContentView = nil
        return content
    }

	    init(payloadPathToWatch: String?) {
	        self.payloadPathToWatch = payloadPathToWatch
        launchLog("PickerWindowController.init start payloadPath=\(payloadPathToWatch ?? "nil")")

	        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1700, height: 900),
            styleMask: [.titled, .closable, .resizable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "\(APP_DISPLAY_NAME)"
        window.center()
        launchLog("window created frame=\(NSStringFromRect(window.frame))")

	        super.init(window: window)
	        window.delegate = self

	        configureWindowAppearance()
        launchLog("configureWindowAppearance done")
	        setupUI()
        launchLog("setupUI done")
        installRootGlassTintObservers()
        setupPinnedHeader()
        setupRightPanelViews()
        setupPDFFindHUD()
        setupLoadingOverlay()
        installSamplePDFIfNeeded()
        runRightPanelTransitionStressTestIfRequested()
        installCacheLifecycleObservers()
        pdfDocumentCache.countLimit = 12

        beginWaitingIfNeeded()
        launchLog("PickerWindowController.init end window=\(window.isVisible ? "visible" : "hidden")")
    }

    required init?(coder: NSCoder) { fatalError() }

	    deinit {
        if let keyMonitor { NSEvent.removeMonitor(keyMonitor) }
        if let pdfWheelMonitor { NSEvent.removeMonitor(pdfWheelMonitor) }
        if let selectionClearMonitor { NSEvent.removeMonitor(selectionClearMonitor) }
        if let dividerDragEndMonitor { NSEvent.removeMonitor(dividerDragEndMonitor) }
        if let windowResizeObserver { NotificationCenter.default.removeObserver(windowResizeObserver) }
        if let splitResizeObserver { NotificationCenter.default.removeObserver(splitResizeObserver) }
        if let splitWillResizeObserver { NotificationCenter.default.removeObserver(splitWillResizeObserver) }
        if let hitTestMoveMonitor { NSEvent.removeMonitor(hitTestMoveMonitor) }
        if let hitTestDownMonitor { NSEvent.removeMonitor(hitTestDownMonitor) }
        if let hitTestUpMonitor { NSEvent.removeMonitor(hitTestUpMonitor) }
        if let pdfSelectDownMonitor { NSEvent.removeMonitor(pdfSelectDownMonitor) }
        if let pdfSelectDragMonitor { NSEvent.removeMonitor(pdfSelectDragMonitor) }
        if let pdfSelectUpMonitor { NSEvent.removeMonitor(pdfSelectUpMonitor) }
        for obs in windowFocusObservers { NotificationCenter.default.removeObserver(obs) }
        if let windowLiveResizeEndObserver { NotificationCenter.default.removeObserver(windowLiveResizeEndObserver) }
        if let windowScreenObserver { NotificationCenter.default.removeObserver(windowScreenObserver) }
        for obs in rootGlassTintObservers { NotificationCenter.default.removeObserver(obs) }
        rootGlassTintObservers.removeAll()
        for obs in rootGlassTintDistributedObservers { DistributedNotificationCenter.default().removeObserver(obs) }
        rootGlassTintDistributedObservers.removeAll()
	        dividerSettleWorkItem?.cancel()
        viewModeTransitionWorkItem?.cancel()
	        if let u = lastTempHTMLURL { try? FileManager.default.removeItem(at: u) }
	        pollTimer?.invalidate()
	        if let searchBackgroundFrameObserver { NotificationCenter.default.removeObserver(searchBackgroundFrameObserver) }
	        if let tableScrollObserver { NotificationCenter.default.removeObserver(tableScrollObserver) }
        if let appTerminationObserver { NotificationCenter.default.removeObserver(appTerminationObserver) }
        splitDividerSpringTimer?.invalidate()
	        if pdfCacheCleanupState != .cleaned {
	            pdfCache.cleanupOnExit()
	        }
	    }

    func windowWillClose(_ notification: Notification) {
        beginPDFCacheCleanup(reason: "window_close", terminateAfter: true)
    }

    func windowDidBecomeKey(_ notification: Notification) {
        ensureDefaultSelectionIfNeeded(reason: "window-key")
    }

	    private func beginPDFCacheCleanup(reason: String, terminateAfter: Bool) {
	        if pdfCacheCleanupState == .cleaned {
	            if terminateAfter { NSApp.terminate(nil) }
	            return
	        }
	        if pdfCacheCleanupState == .cleaning { return }
	        pdfCacheCleanupState = .cleaning

	        let dir = pdfCache.sessionDirectory.path
	        NSLog("[PDFEager] cleanup_start reason=\(reason) dir=\(dir)")
	        DispatchQueue.global(qos: .utility).async { [weak self] in
	            guard let self else { return }
	            self.pdfCache.cleanupOnExit()
	            self.pdfDocumentCache.removeAllObjects()
	            DispatchQueue.main.async {
	                self.pdfCacheCleanupState = .cleaned
	                if terminateAfter { NSApp.terminate(nil) }
	            }
	        }
	    }

    // Public entry point so main() can apply STDIN payload immediately (fixes “does nothing”).
    func ingestPayloadIfPresent(_ payload: Payload?) {
        guard let payload, !payload.papers.isEmpty else { return }
        DispatchQueue.main.async {
            self.applyPayload(payload)
        }
    }

    // MARK: UI setup

		    private func configureWindowAppearance() {
		        guard let window else { return }
		        // Window root is now a true image backdrop (no root vibrancy/blur).
		        window.isOpaque = true
		        window.backgroundColor = WINDOW_BACKGROUND_SOLID_COLOR
		        window.contentView?.wantsLayer = true
		        window.contentView?.layer?.backgroundColor = WINDOW_BACKGROUND_SOLID_COLOR.cgColor

        // Enforce window size limits.
        window.minSize = NSSize(width: 760, height: 480)
        window.maxSize = NSSize(width: 3200, height: 2400)
        installTitlebarTintBackground()
    }

    private func installTitlebarTintBackground() {
        guard let window else { return }
        // Make the system titlebar background transparent so our custom tint can show through.
        window.titlebarAppearsTransparent = true

        guard let titlebarContainer = window.standardWindowButton(.closeButton)?.superview else { return }
        let desiredTint = windowGlassAdjustedTintColor()

        let tintView: NSView
        if let existing = titlebarTintView {
            // If we previously installed a non-effect view, replace it so the tint actually matches the search glass.
            let isEffect = (existing is NSVisualEffectView) || (existing is NSGlassEffectView)
            if !isEffect {
                existing.removeFromSuperview()
                titlebarTintView = nil
            }
        }
        if let existing = titlebarTintView {
            tintView = existing
        } else {
            // Use a passthrough glass/effect view so the titlebar reads like the same surface as the search bar.
            if #available(macOS 26.0, *) {
                let v = PassthroughGlassEffectView(frame: titlebarContainer.bounds)
                v.translatesAutoresizingMaskIntoConstraints = false
                v.wantsLayer = true
                v.layer?.masksToBounds = true
                if #available(macOS 10.13, *) { v.layer?.cornerCurve = .continuous }
                titlebarContainer.addSubview(v, positioned: .below, relativeTo: nil)
                NSLayoutConstraint.activate([
                    v.leadingAnchor.constraint(equalTo: titlebarContainer.leadingAnchor),
                    v.trailingAnchor.constraint(equalTo: titlebarContainer.trailingAnchor),
                    v.topAnchor.constraint(equalTo: titlebarContainer.topAnchor),
                    v.bottomAnchor.constraint(equalTo: titlebarContainer.bottomAnchor),
                ])
                titlebarTintView = v
                tintView = v
            } else {
                let v = PassthroughVisualEffectView(frame: titlebarContainer.bounds)
                v.translatesAutoresizingMaskIntoConstraints = false
                v.wantsLayer = true
                v.layer?.masksToBounds = true
                if #available(macOS 10.13, *) { v.layer?.cornerCurve = .continuous }
                // Match the search bar's fallback material choices.
                v.material = currentSearchBarTheme().fallbackMaterial
                v.blendingMode = currentSearchBarTheme().fallbackBlending
                v.state = currentSearchBarTheme().fallbackState
                v.isEmphasized = currentSearchBarTheme().emphasized
                titlebarContainer.addSubview(v, positioned: .below, relativeTo: nil)
                NSLayoutConstraint.activate([
                    v.leadingAnchor.constraint(equalTo: titlebarContainer.leadingAnchor),
                    v.trailingAnchor.constraint(equalTo: titlebarContainer.trailingAnchor),
                    v.topAnchor.constraint(equalTo: titlebarContainer.topAnchor),
                    v.bottomAnchor.constraint(equalTo: titlebarContainer.bottomAnchor),
                ])
                titlebarTintView = v
                tintView = v
            }
        }

        if tintView.translatesAutoresizingMaskIntoConstraints {
            tintView.frame = titlebarContainer.bounds
        }
        if #available(macOS 26.0, *), let glass = tintView as? NSGlassEffectView {
            glass.style = .regular
            glass.tintColor = desiredTint
        } else if let effect = tintView as? NSVisualEffectView {
            // Ensure the layer color is driven explicitly; otherwise the titlebar can drift on some appearances.
            effect.layer?.backgroundColor = desiredTint.cgColor
        } else {
            tintView.wantsLayer = true
            tintView.layer?.backgroundColor = desiredTint.cgColor
        }

        installTitlebarDivider(in: tintView)
    }

    private func installTitlebarDivider(in tintView: NSView) {
        let divider: NSView
        if let existing = titlebarDividerView, existing.superview === tintView {
            divider = existing
        } else {
            let v = PassthroughView(frame: .zero)
            v.translatesAutoresizingMaskIntoConstraints = false
            v.wantsLayer = true
            tintView.addSubview(v)
            let edgeConstraint: NSLayoutConstraint
            if tintView.isFlipped {
                edgeConstraint = v.bottomAnchor.constraint(equalTo: tintView.bottomAnchor)
            } else {
                edgeConstraint = v.topAnchor.constraint(equalTo: tintView.topAnchor)
            }
            NSLayoutConstraint.activate([
                v.leadingAnchor.constraint(equalTo: tintView.leadingAnchor),
                v.trailingAnchor.constraint(equalTo: tintView.trailingAnchor),
                edgeConstraint,
            ])
            titlebarDividerView = v
            divider = v
        }

        let scale = max(1.0, window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0)
        let thickness = 1.0 / scale
        titlebarDividerHeightConstraint?.isActive = false
        titlebarDividerHeightConstraint = divider.heightAnchor.constraint(equalToConstant: thickness)
        titlebarDividerHeightConstraint?.isActive = true
        divider.layer?.contentsScale = scale
        divider.layer?.backgroundColor = NSColor.black.cgColor
    }

    private func leftCardCornerRadius() -> CGFloat {
        if #available(macOS 26.0, *), let glass = leftContainer as? NSGlassEffectView {
            return glass.cornerRadius
        }
        return leftContainer.layer?.cornerRadius ?? PANEL_CORNER_RADIUS
    }

    private func rightCardCornerRadius() -> CGFloat {
        if #available(macOS 26.0, *), let glass = rightContainer as? NSGlassEffectView {
            return glass.cornerRadius
        }
        return rightContainer.layer?.cornerRadius ?? PANEL_CORNER_RADIUS
    }

    private func setupWindowBackgroundImage(in content: NSView) {
        guard windowBackgroundImageView == nil else { return }
        let maxPx = recommendedBackgroundMaxPixelDim(for: window)
        let image = loadBackgroundImage(from: WINDOW_BACKGROUND_IMAGE_PATH, maxPixelDim: maxPx, preserveAnimated: true)
        let imageView = StaticBackgroundImageView(frame: .zero)
        imageView.translatesAutoresizingMaskIntoConstraints = false
        // Hard guarantee: the window background reads as solid white when no image is configured.
        imageView.baseColor = WINDOW_BACKGROUND_SOLID_COLOR
        imageView.image = image
        imageView.alphaValue = (image != nil) ? WINDOW_BACKGROUND_IMAGE_ALPHA : 1.0
        if let screen = window?.screen ?? NSScreen.main {
            imageView.updateBackingScale(screen.backingScaleFactor)
        }
        // The window background must fill the full window rect (no rounded clipping at the top edges/titlebar).
        imageView.layer?.cornerRadius = 0
        imageView.layer?.masksToBounds = true

        content.addSubview(imageView, positioned: .below, relativeTo: nil)
        NSLayoutConstraint.activate([
            imageView.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            imageView.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            imageView.topAnchor.constraint(equalTo: content.topAnchor),
            imageView.bottomAnchor.constraint(equalTo: content.bottomAnchor)
        ])

        windowBackgroundImageView = imageView

        // Keep the titlebar tint consistent with the window background when a wallpaper is present.
        // We use the dominant hue (not a hand-tuned constant) so the UI bar tracks the image.
        if let image, let dominant = dominantHueColor(from: image) {
            let base = (window?.backgroundColor ?? NSColor.black).usingColorSpace(.deviceRGB) ?? NSColor.black
            let d = dominant.usingColorSpace(.deviceRGB) ?? dominant
            let a = max(0.0, min(1.0, WINDOW_BACKGROUND_IMAGE_ALPHA))
            let r = a * d.redComponent + (1.0 - a) * base.redComponent
            let g = a * d.greenComponent + (1.0 - a) * base.greenComponent
            let b = a * d.blueComponent + (1.0 - a) * base.blueComponent
            cachedTitlebarTintFromWindowBackground = NSColor(srgbRed: r, green: g, blue: b, alpha: 1.0)
        } else {
            cachedTitlebarTintFromWindowBackground = nil
        }
        installTitlebarTintBackground()
        // Background underlay changed; recompute RootGlassTint compensation (amortized).
        cachedRootGlassThemeSignature = nil
        cachedRootGlassTheme = nil
        scheduleRootGlassTintApply(reason: "window_bg_image", delay: 0.0)

        // Background changed; re-render panel liquid glass textures (amortized by the card view).
        (leftContainer as? GlassCardView)?.invalidateGlass(reason: "window_bg_image")
        (rightContainer as? GlassCardView)?.invalidateGlass(reason: "window_bg_image")
        rightSecondaryContainer?.invalidateGlass(reason: "window_bg_image")
        sidebarControlBackground.needsDisplay = true
        sidebarControlBackground.layer?.setNeedsDisplay()
        rightPanelLeftEdgeButtonBackground?.needsDisplay = true
        rightPanelLeftEdgeButtonBackground?.layer?.setNeedsDisplay()
        rightPanelRightEdgeButtonBackground?.needsDisplay = true
        rightPanelRightEdgeButtonBackground?.layer?.setNeedsDisplay()
        navControlBackground.needsDisplay = true
        navControlBackground.layer?.setNeedsDisplay()
    }

    private func captureWindowBackgroundRegion(in rectInWindow: CGRect, scale: CGFloat) -> CGImage? {
        guard let bgView = windowBackgroundImageView else { return nil }
        let rectInBG = bgView.convert(rectInWindow, from: nil)
        return bgView.snapshotCGImage(in: rectInBG, scale: scale)
    }

    private func updateWindowBackgroundBackingScale() {
        guard let imageView = windowBackgroundImageView else { return }
        if let screen = window?.screen ?? NSScreen.main {
            imageView.updateBackingScale(screen.backingScaleFactor)
        }
    }

    private func setupLeftCardBackgroundImage(in root: NSView, below view: NSView) {
        guard leftCardBackgroundImageView == nil else { return }
        let maxPx = recommendedBackgroundMaxPixelDim(for: window)
        guard let image = loadBackgroundImage(from: BACKGROUND_IMAGE_PATH, maxPixelDim: maxPx, preserveAnimated: true) else { return }
        let imageView = StaticBackgroundImageView(frame: .zero)
        imageView.translatesAutoresizingMaskIntoConstraints = true
        imageView.image = image
        imageView.alphaValue = LEFT_CARD_BACKGROUND_IMAGE_ALPHA
        if let screen = window?.screen ?? NSScreen.main {
            imageView.updateBackingScale(screen.backingScaleFactor)
        }

        root.addSubview(imageView, positioned: .below, relativeTo: view)
        leftCardBackgroundImageView = imageView
        updateLeftCardBackgroundFrame()
    }

    private func updateLeftCardBackgroundFrame() {
        guard let root = splitView.superview else { return }
        let leftFrameInRoot = leftContainer.convert(leftContainer.bounds, to: root)

        if let imageView = leftCardBackgroundImageView {
            if imageView.frame != leftFrameInRoot {
                imageView.frame = leftFrameInRoot
            }

            if let layer = imageView.layer {
                let radius = leftCardCornerRadius()
                layer.cornerRadius = radius
                layer.masksToBounds = true
                if #available(macOS 10.13, *) {
                    layer.cornerCurve = leftContainer.layer?.cornerCurve ?? .continuous
                }
            }

            imageView.needsLayout = true
            if let screen = window?.screen ?? NSScreen.main {
                imageView.updateBackingScale(screen.backingScaleFactor)
            }
        }

        updateLeftCardEdgeGlowFrame()
    }

    private func setupRightCardBackgroundImage(in root: NSView, below view: NSView) {
        guard rightCardBackgroundImageView == nil else { return }
        let maxPx = recommendedBackgroundMaxPixelDim(for: window)
        guard let image = loadBackgroundImage(from: RIGHT_CARD_BACKGROUND_IMAGE_PATH, maxPixelDim: maxPx, preserveAnimated: true) else { return }
        let imageView = StaticBackgroundImageView(frame: .zero)
        imageView.translatesAutoresizingMaskIntoConstraints = true
        imageView.image = image
        imageView.alphaValue = RIGHT_CARD_BACKGROUND_IMAGE_ALPHA
        if let screen = window?.screen ?? NSScreen.main {
            imageView.updateBackingScale(screen.backingScaleFactor)
        }

        root.addSubview(imageView, positioned: .below, relativeTo: view)
        rightCardBackgroundImageView = imageView
        updateRightCardBackgroundFrame()
    }

    private func cardEdgeGlowColor() -> NSColor {
        // Tie the decorative edge glow to RootGlassTint so the card reads as a tinted Apple glass surface.
        blend(NSColor.white, rootGlassTheme().rootTintHighlight, t: 0.35)
    }

    private func applyCardEdgeGlowStyle(_ view: CardEdgeGlowView) {
        let active = isWindowActiveForAppearance()
        view.glowColor = cardEdgeGlowColor()
        view.strokeAlpha = active ? 0.36 : 0.24
        view.glowOpacity = active ? 0.55 : 0.36
        view.glowRadius = active ? 20 : 16
        view.glowOffset = .zero
    }

    private func setupLeftCardEdgeGlow(in root: NSView, below view: NSView) {
        guard leftCardGlowView == nil else { return }
        let glowView = CardEdgeGlowView(frame: .zero)
        glowView.translatesAutoresizingMaskIntoConstraints = true
        applyCardEdgeGlowStyle(glowView)
        root.addSubview(glowView, positioned: .below, relativeTo: view)
        leftCardGlowView = glowView
        updateLeftCardEdgeGlowFrame()
    }

    private func setupRightCardEdgeGlow(in root: NSView, below view: NSView) {
        guard rightCardGlowView == nil else { return }
        let glowView = CardEdgeGlowView(frame: .zero)
        glowView.translatesAutoresizingMaskIntoConstraints = true
        applyCardEdgeGlowStyle(glowView)
        root.addSubview(glowView, positioned: .below, relativeTo: view)
        rightCardGlowView = glowView
        updateRightCardEdgeGlowFrame()
    }

    private func updateRightCardBackgroundFrame() {
        guard let root = splitView.superview else { return }
        let rightFrameInRoot = rightContainer.convert(rightContainer.bounds, to: root)

        if let imageView = rightCardBackgroundImageView {
            if imageView.frame != rightFrameInRoot {
                imageView.frame = rightFrameInRoot
            }

            if let layer = imageView.layer {
                let radius = rightCardCornerRadius()
                layer.cornerRadius = radius
                layer.masksToBounds = true
                if #available(macOS 10.13, *) {
                    layer.cornerCurve = rightContainer.layer?.cornerCurve ?? .continuous
                }
            }

            imageView.needsLayout = true
            if let screen = window?.screen ?? NSScreen.main {
                imageView.updateBackingScale(screen.backingScaleFactor)
            }
        }

        updateRightCardEdgeGlowFrame()
    }

    private func updateLeftCardEdgeGlowFrame() {
        guard let glowView = leftCardGlowView else { return }
        guard let root = splitView.superview else { return }
        let leftFrameInRoot = leftContainer.convert(leftContainer.bounds, to: root)
        if glowView.frame != leftFrameInRoot {
            glowView.frame = leftFrameInRoot
        }
        glowView.cornerRadius = leftCardCornerRadius()
    }

    private func updateRightCardEdgeGlowFrame() {
        guard let glowView = rightCardGlowView else { return }
        guard let root = splitView.superview else { return }
        let rightFrameInRoot = rightContainer.convert(rightContainer.bounds, to: root)
        if glowView.frame != rightFrameInRoot {
            glowView.frame = rightFrameInRoot
        }
        glowView.cornerRadius = rightCardCornerRadius()
    }

    func updateSplitDividerHandleFrame() {
        guard let root = splitView.superview,
              let handle = splitDividerHandle else { return }
        guard splitView.subviews.count >= 2 else {
            handle.isHidden = true
            return
        }
        let rect = splitView.dividerRect(at: 0)
        guard rect.width > 0, rect.height > 0 else {
            handle.isHidden = true
            return
        }
        let rectInRoot = splitView.convert(rect, to: root)
        if handle.frame != rectInRoot {
            handle.frame = rectInRoot
            handle.needsLayout = true
        }
        if handle.isHidden { handle.isHidden = false }
    }

    private func updateRightSplitDividerHandleFrame() {
        guard let root = splitView.superview,
              let handle = rightSplitDividerHandle else { return }
        guard rightAuxPanelVisible, rightSplitView.subviews.count >= 2 else {
            handle.isHidden = true
            return
        }
        let rect = rightSplitView.dividerRect(at: 0)
        guard rect.width > 0, rect.height > 0 else {
            handle.isHidden = true
            return
        }
        let rectInRoot = rightSplitView.convert(rect, to: root)
        if handle.frame != rectInRoot {
            handle.frame = rectInRoot
            handle.needsLayout = true
        }
        if handle.isHidden { handle.isHidden = false }
    }

    private func updateCardEdgeGlowIntensity() {
        if let leftGlow = leftCardGlowView { applyCardEdgeGlowStyle(leftGlow) }
        if let rightGlow = rightCardGlowView { applyCardEdgeGlowStyle(rightGlow) }
    }

	    private func setupWindowBackgroundMaterial(in content: NSView) {
	        // Intentionally disabled: the window root no longer uses liquid-glass/vibrancy.
	        // Ensure any previously-installed root glass is removed deterministically.
	        if windowBackgroundView.superview != nil {
	            windowBackgroundView.removeFromSuperview()
	        }
	        windowBackgroundView = PassthroughView(frame: .zero)
	    }

    private func restoreSidebarStateFromDefaults() {
        let defaults = UserDefaults.standard
        let storedWidthValue = (defaults.object(forKey: sidebarWidthDefaultsKey) as? Double)
            ?? (defaults.object(forKey: legacySidebarWidthDefaultsKey) as? Double)
            ?? 0
        if storedWidthValue.isFinite, storedWidthValue > 0 {
            lastSidebarWidth = max(minSidebarWidth, CGFloat(storedWidthValue))
        }

        var forcedToVisible = false
        let hasNewVisibleKey = (defaults.object(forKey: sidebarVisibleDefaultsKey) != nil)
        let hasLegacyVisibleKey = (defaults.object(forKey: legacySidebarVisibleDefaultsKey) != nil)
        if hasNewVisibleKey || hasLegacyVisibleKey {
            let storedVisible = hasNewVisibleKey
                ? defaults.bool(forKey: sidebarVisibleDefaultsKey)
                : defaults.bool(forKey: legacySidebarVisibleDefaultsKey)
            if storedVisible {
                sidebarVisible = true
            } else if storedWidthValue > 12 {
                sidebarVisible = false
            } else {
                sidebarVisible = true
                forcedToVisible = true
            }
        }

        if forcedToVisible {
            persistSidebarVisibility(true)
            persistSidebarWidth(lastSidebarWidth)
        }
    }

    private func persistSidebarWidth(_ width: CGFloat) {
        UserDefaults.standard.set(Double(width), forKey: sidebarWidthDefaultsKey)
        UserDefaults.standard.set(Double(width), forKey: legacySidebarWidthDefaultsKey)
    }

    private func persistSidebarVisibility(_ visible: Bool) {
        UserDefaults.standard.set(visible, forKey: sidebarVisibleDefaultsKey)
        UserDefaults.standard.set(visible, forKey: legacySidebarVisibleDefaultsKey)
    }

    private var sidebarClampInProgress = false

    private func desiredMinSidebarWidthForCurrentPage(maxLeft: CGFloat) -> CGFloat {
        guard sidebarVisible else { return 0 }
        guard maxLeft.isFinite, maxLeft > 0 else { return 0 }

        // Use current page rows when pagination is ready; otherwise fall back to the early-launch slice.
        let range: Range<Int>
        if paginator.pageCount > 0 {
            range = paginator.range(forPage: currentPageIndex)
        } else {
            range = launchPageRangeForSidebarSizing()
        }

        let authorW = maxAuthorYearWidthForLaunchRows(range)

        // Symmetric bezel around the Author&Year text:
        // - PANEL_INSET is the card's left/right inset.
        // - leftRowTextInset is the list's internal leading inset to where the Author&Year text starts.
        // Apply the same combined inset on both sides so the text isn't flush to either edge.
        let bezelX = PANEL_INSET + leftRowTextInset
        let needed = authorW + (2 * bezelX)
        return min(maxLeft, max(minSidebarWidth, needed))
    }

    private func enforceSidebarWidthBounds(reason: String) {
        guard !sidebarClampInProgress else { return }
        guard !sidebarTransitionInProgress else { return }
        guard !dividerDragActive else { return }

        let total = splitView.bounds.width
        guard total > 80 else { return }

        let divider = splitView.dividerThickness
        let maxLeftPotential = total - divider - minOuterRightContainerWidth()
        let maxLeft = cappedSidebarMaxWidth(forPotential: maxLeftPotential)
        let current = leftContainer.frame.width

        let desired: CGFloat
        if sidebarVisible {
            let minLeft = desiredMinSidebarWidthForCurrentPage(maxLeft: maxLeft)
            desired = min(max(current, minLeft), maxLeft)
        } else {
            // When hidden, allow full collapse (override min width) but never exceed max.
            desired = 0
        }

        if abs(desired - current) < 0.5 { return }

        layoutLog("sidebar_clamp_calc reason=\(reason) total=\(Int(total)) divider=\(Int(divider)) rightMin=\(Int(minOuterRightContainerWidth())) current=\(Int(current)) desired=\(Int(desired)) maxLeft=\(Int(maxLeft)) potentialLeft=\(Int(maxLeftPotential))")

        sidebarClampInProgress = true
        let prevAllowCollapse = allowSidebarCollapse
        if !sidebarVisible { allowSidebarCollapse = true }
        splitView.setPosition(desired, ofDividerAt: 0)
        splitView.adjustSubviews()
        allowSidebarCollapse = prevAllowCollapse
        sidebarClampInProgress = false

        // IMPORTANT: clamping the split position changes `leftContainer` width. The search bar glass
        // is explicitly framed from `leftContainer` in `layoutLeftContainerSubviews()`, so we must
        // re-run that layout pass after any clamp to keep the horizontal extent slaved.
        layoutLeftContainerSubviews()

        if sidebarVisible {
            // If we restored or persisted an out-of-range width, fix it once bounds are real.
            let persistedMin = desiredMinSidebarWidthForCurrentPage(maxLeft: maxLeft)
            let clampedStored = min(max(lastSidebarWidth, persistedMin), maxLeft)
            if abs(clampedStored - lastSidebarWidth) >= 0.5 {
                lastSidebarWidth = clampedStored
                persistSidebarWidth(clampedStored)
            }
        }

        uiLog("sidebar_clamp reason=\(reason) current=\(Int(current)) desired=\(Int(desired)) maxLeft=\(Int(maxLeft)) total=\(Int(total))")
    }

    // Toolbar responsiveness: scale toolbar controls dynamically while preserving hit targets + legibility.
    private let toolbarControlScale: CGFloat = 1.3  // Legacy constant (kept for compatibility).
    private let toolbarControlScaleBase: CGFloat = 1.3
    private let toolbarControlScaleMin: CGFloat = 1.05
    private let toolbarBaseSpacing: CGFloat = 8
    private let toolbarMinSpacing: CGFloat = 4
    private let pageStepperButtonSpacing: CGFloat = 12
    private let pageStepperHorizontalPadding: CGFloat = 8
    private let pageStepperBottomInset: CGFloat = 10
    private var pageStepperButtonSize: CGFloat { 24 * toolbarControlScaleBase }
    private var pageStepperHeight: CGFloat { pageStepperButtonSize + 6 }
    // Minimum interactive size for toolbar controls. Keep it above “micro-control” territory.
    private let toolbarMinHitSize: CGFloat = 24
    // Separation-to-scale mapping (distance between adjacent toolbar buttons, in root coords).
    private let toolbarSeparationMin: CGFloat = 44   // at/under this, icons at sMin
    private let toolbarSeparationMax: CGFloat = 220  // at/over this, icons at sMax
    private let navDividerWidth: CGFloat = 1
    private let navDividerHeight: CGFloat = 18
    private var toolbarControlScaleCurrent: CGFloat = 1.3
    private var toolbarControlHeight: CGFloat = 0
    private var toolbarSpacingCurrent: CGFloat = 8
    private var navInset: CGFloat = 5
    private var pageInset: CGFloat = 10
    private var pageMinWidthBase: CGFloat = 96
    private var toolbarScaleDebugEnabled: Bool {
        ProcessInfo.processInfo.environment["ARXIV_TOOLBAR_SCALE_DEBUG"] == "1"
    }

    // Window-resize-driven toolbar scaling: spring tracker with an Apple-like cubic-ease fallback.
    // Scale coupling rules (s is normalized in [sMin,sMax]):
    // - font/icon: s^1.00
    // - padding/spacing: s^0.95
    // - corner radius: s^0.90
    // - border thickness: s^0.65
    private struct ToolbarResizeMotionSpec {
        // Tuned set (apply consistently): quick settle, lightly under-damped.
        // 95% settle after stop: ~3/(ζω) => with ζ=0.84 and ω in [14,16] -> ~180–255ms.
        let dampingRatio: CGFloat = 0.84
        let omegaSmallDelta: CGFloat = 16.0
        let omegaLargeDelta: CGFloat = 14.0
        let omegaLargeDeltaThreshold: CGFloat = 0.12 // normalized scale delta where we clamp ω.

        // Fallback ease (Apple-like cubic-bezier). Never linear.
        let easeDuration: CFTimeInterval = 0.18
        // “Standard” curve: (0.2, 0.0, 0.2, 1.0)
        let easeC1 = CGPoint(x: 0.2, y: 0.0)
        let easeC2 = CGPoint(x: 0.2, y: 1.0)
    }

    private struct CubicBezier {
        let c1: CGPoint
        let c2: CGPoint

        // Returns y for a given x in [0,1] by solving x(u)=x and evaluating y(u).
        func value(at x: CGFloat) -> CGFloat {
            let t = max(0, min(1, x))
            // Bezier control points: P0=(0,0), P1=c1, P2=c2, P3=(1,1)
            func bx(_ u: CGFloat) -> CGFloat {
                let inv = 1 - u
                let a = inv * inv * inv * 0
                let b = 3 * inv * inv * u * c1.x
                let c = 3 * inv * u * u * c2.x
                let d = u * u * u * 1
                return a + b + c + d
            }
            func by(_ u: CGFloat) -> CGFloat {
                let inv = 1 - u
                let a = inv * inv * inv * 0
                let b = 3 * inv * inv * u * c1.y
                let c = 3 * inv * u * u * c2.y
                let d = u * u * u * 1
                return a + b + c + d
            }

            // Newton-Raphson on u to match bx(u)=t
            var u = t
            for _ in 0..<6 {
                let xU = bx(u)
                let dx = xU - t
                if abs(dx) < 1e-5 { break }
                // derivative of bx
                let inv = 1 - u
                let d1 = 3 * inv * inv * (c1.x - 0)
                let d2 = 6 * inv * u * (c2.x - c1.x)
                let d3 = 3 * u * u * (1 - c2.x)
                let dBx = d1 + d2 + d3
                if abs(dBx) < 1e-6 { break }
                u = max(0, min(1, u - dx / dBx))
            }
            return max(0, min(1, by(u)))
        }
    }

    private struct SpringTracker {
        var value: CGFloat
        var velocity: CGFloat
        var target: CGFloat

        mutating func reset(to value: CGFloat) {
            self.value = value
            self.velocity = 0
            self.target = value
        }

        mutating func step(dt rawDt: CFTimeInterval, dampingRatio: CGFloat, omega: CGFloat) {
            let dt = CGFloat(max(1.0 / 240.0, min(1.0 / 30.0, rawDt)))
            // x'' + 2ζω x' + ω^2 (x - target) = 0
            let x = value
            let v = velocity
            let a = (-2 * dampingRatio * omega * v) - (omega * omega * (x - target))
            let vNext = v + a * dt
            let xNext = x + vNext * dt
            velocity = vNext
            value = xNext
        }

        func isSettled(tolerance: CGFloat) -> Bool {
            abs(value - target) <= tolerance && abs(velocity) <= tolerance * 2
        }
    }

    private struct ToolbarScaleMetrics: Equatable {
        let normalizedScale: CGFloat
        let controlHeight: CGFloat
        let buttonSize: CGFloat
        let navButtonWidth: CGFloat
        let navInset: CGFloat
        let pageInset: CGFloat
        let pageMinWidth: CGFloat
        let spacing: CGFloat
        let cornerRadius: CGFloat
        let symbolPointSize: CGFloat
        let pageFontSize: CGFloat
        let borderThickness: CGFloat
    }

    private let toolbarMotionSpec = ToolbarResizeMotionSpec()
    private var toolbarScaleTracker = SpringTracker(value: 1.0, velocity: 0, target: 1.0)
    private var toolbarScaleEaseStartTime: CFTimeInterval = 0
    private var toolbarScaleEaseStartValue: CGFloat = 1.0
    private var toolbarScaleEaseTarget: CGFloat = 1.0
    private var toolbarScaleUseEaseFallback: Bool = false
    private var toolbarScaleTickTimer: Timer?
    private var toolbarScaleLastTickTime: CFTimeInterval = 0
    private var toolbarScaleLastApplied: ToolbarScaleMetrics?
    private var toolbarScaleLastTargetChangeTime: CFTimeInterval = 0
    private var toolbarScalePrevError: CGFloat = 0

    private var toolbarPerfEnabled: Bool {
        ProcessInfo.processInfo.environment["ARXIV_TOOLBAR_RESIZE_PERF"] == "1"
    }

    private func powScale(_ s: CGFloat, _ exp: CGFloat) -> CGFloat {
        CGFloat(pow(Double(max(0, s)), Double(exp)))
    }

    private var toolbarNormalizedScaleMin: CGFloat {
        // Dynamic toolbar scaling disabled; lock normalized scale to 1.0.
        1.0
    }

    // Pure distance->scale function (monotonic, normalized 0–1 input, clamped).
    private func scaleForDistance(_ d: CGFloat, dMin: CGFloat, dMax: CGFloat, sMin: CGFloat, sMax: CGFloat) -> CGFloat {
        let dm = max(0, dMin)
        let dM = max(dm + 0.0001, dMax) // avoid divide-by-zero
        let t = max(0, min(1, (d - dm) / (dM - dm)))
        return sMin + (sMax - sMin) * t
    }

    private func toolbarButtonCenterDistances() -> ([CGFloat], CGFloat) {
        guard let root = headerControlsContainer.superview else { return ([], 0) }
        let buttons = toolbarControls.arrangedSubviews
        guard buttons.count >= 2 else { return ([], 0) }
        let centers = buttons.map { view -> CGFloat in
            let frame = view.convert(view.bounds, to: root)
            return frame.midX
        }.sorted()
        var gaps: [CGFloat] = []
        for i in 1..<centers.count {
            gaps.append(max(0, centers[i] - centers[i-1]))
        }
        let avg = gaps.reduce(0, +) / CGFloat(gaps.count)
        return (gaps, avg)
    }

    private func toolbarNormalizedScaleTarget(fromSeparation separation: CGFloat) -> CGFloat {
        // Map measured separation to normalized scale [sMin, 1].
        return scaleForDistance(separation,
                                dMin: toolbarSeparationMin,
                                dMax: toolbarSeparationMax,
                                sMin: toolbarNormalizedScaleMin,
                                sMax: 1.0)
    }

    private func toolbarAvailableWidthForScale() -> CGFloat {
        if let root = headerControlsContainer.superview {
            let rightRegionFrame = rightSplitContainer.convert(rightSplitContainer.bounds, to: root)
            return max(0, rightRegionFrame.minX - WINDOW_BEZEL_INSET)
        }
        if let window {
            return max(0, window.frame.width - (2 * WINDOW_BEZEL_INSET))
        }
        return 0
    }

    private func updateToolbarScaleForWindowSize(reason: String, immediate: Bool = false) {
        guard window != nil else { return }

        let target: CGFloat = 1.0

        if immediate {
            toolbarScaleUseEaseFallback = false
            toolbarScaleTracker.reset(to: target)
            toolbarScaleLastApplied = nil
            applyToolbarMetricsIfNeeded(metrics: toolbarMetrics(forNormalizedScale: target))
            return
        }

        // If we already fell back due to instability, keep easing until we settle.
        setToolbarScaleTarget(normalizedScale: target, preferEaseFallback: toolbarScaleUseEaseFallback)
    }

    private func toolbarMetrics(forNormalizedScale s: CGFloat) -> ToolbarScaleMetrics {
        let sClamped = max(toolbarNormalizedScaleMin, min(1.0, s))

        // Base sizes are defined at scaleBase (wide window). All scaling derives from normalizedScale.
        let baseControlHeight = 32 * toolbarControlScaleBase
        let baseButtonSize = 24 * toolbarControlScaleBase
        let baseNavButtonWidth = 30 * toolbarControlScaleBase
        let baseSpacing = toolbarBaseSpacing
        let baseNavInset: CGFloat = 5
        let basePageInset: CGFloat = 10
        let basePageMinWidth: CGFloat = pageMinWidthBase
        let baseCornerRadius: CGFloat = baseControlHeight / 2
        let baseSymbolPointSize: CGFloat = 13 * toolbarControlScaleBase
        let basePageFontSize: CGFloat = 12.5
        let baseBorderThickness: CGFloat = 1.0

        // Keep scale coupling intuitive: when spacing compresses, controls shrink too.
        // (Previously, controls could hit a larger minimum while spacing kept shrinking,
        // which reads visually as “inverted scaling”.)
        let controlHeight = max(toolbarMinHitSize, baseControlHeight * powScale(sClamped, 1.00))
        let buttonSize = max(toolbarMinHitSize, baseButtonSize * powScale(sClamped, 1.00))
        let navButtonWidth = max(toolbarMinHitSize, baseNavButtonWidth * powScale(sClamped, 1.00))
        let spacing = max(toolbarMinSpacing, min(baseSpacing, baseSpacing * powScale(sClamped, 1.00)))
        let navInset = max(3, min(baseNavInset, baseNavInset * powScale(sClamped, 1.00)))
        let pageInset = max(6, min(basePageInset, basePageInset * powScale(sClamped, 1.00)))
        let pageMinWidth = max(72, min(basePageMinWidth, basePageMinWidth * powScale(sClamped, 1.00)))

        var cornerRadius = baseCornerRadius * powScale(sClamped, 0.90)
        cornerRadius = max(10, min(controlHeight / 2, cornerRadius))

        let symbolPointSize = max(11, min(19, baseSymbolPointSize * powScale(sClamped, 1.00)))
        let pageFontSize = max(11.5, min(13.5, basePageFontSize * powScale(sClamped, 1.00)))
        let borderThickness = max(0.80, min(1.10, baseBorderThickness * powScale(sClamped, 0.65)))

        return ToolbarScaleMetrics(
            normalizedScale: sClamped,
            controlHeight: controlHeight,
            buttonSize: buttonSize,
            navButtonWidth: navButtonWidth,
            navInset: navInset,
            pageInset: pageInset,
            pageMinWidth: pageMinWidth,
            spacing: spacing,
            cornerRadius: cornerRadius,
            symbolPointSize: symbolPointSize,
            pageFontSize: pageFontSize,
            borderThickness: borderThickness
        )
    }

    private func toolbarOmega(forDelta delta: CGFloat) -> CGFloat {
        let t = max(0, min(1, delta / max(0.001, toolbarMotionSpec.omegaLargeDeltaThreshold)))
        return toolbarMotionSpec.omegaSmallDelta + (toolbarMotionSpec.omegaLargeDelta - toolbarMotionSpec.omegaSmallDelta) * t
    }

    private func ensureToolbarScaleTickerRunning() {
        if toolbarScaleTickTimer != nil { return }
        toolbarScaleLastTickTime = monotonicNow()
        toolbarScaleTickTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            self?.tickToolbarScale()
        }
        if let timer = toolbarScaleTickTimer {
            RunLoop.main.add(timer, forMode: .common)
        }
    }

    private func stopToolbarScaleTickerIfIdle() {
        guard let timer = toolbarScaleTickTimer else { return }
        // Only stop when we’re fully settled (prevents “snap” after live resize end).
        if toolbarScaleUseEaseFallback {
            let done = (monotonicNow() - toolbarScaleEaseStartTime) >= toolbarMotionSpec.easeDuration
            if done {
                timer.invalidate()
                toolbarScaleTickTimer = nil
            }
            return
        }
        if toolbarScaleTracker.isSettled(tolerance: 0.0015) {
            timer.invalidate()
            toolbarScaleTickTimer = nil
        }
    }

    private func setToolbarScaleTarget(normalizedScale s: CGFloat, preferEaseFallback: Bool) {
        let clamped = max(toolbarNormalizedScaleMin, min(1.0, s))

        // Don’t churn timers if the target isn’t actually changing.
        let targetEps: CGFloat = 0.0006
        if abs(toolbarScaleTracker.target - clamped) < targetEps && toolbarScaleUseEaseFallback == preferEaseFallback {
            return
        }

        toolbarScaleUseEaseFallback = preferEaseFallback
        toolbarScaleLastTargetChangeTime = monotonicNow()
        toolbarScalePrevError = toolbarScaleTracker.value - clamped

        if preferEaseFallback {
            toolbarScaleEaseStartTime = monotonicNow()
            toolbarScaleEaseStartValue = toolbarScaleTracker.value
            toolbarScaleEaseTarget = clamped
            toolbarScaleTracker.target = clamped
        } else {
            toolbarScaleTracker.target = clamped
        }
        ensureToolbarScaleTickerRunning()
    }

    private func tickToolbarScale() {
        let now = monotonicNow()
        let dt = now - (toolbarScaleLastTickTime > 0 ? toolbarScaleLastTickTime : now)
        toolbarScaleLastTickTime = now

        if NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            toolbarScaleTracker.value = toolbarScaleTracker.target
            toolbarScaleTracker.velocity = 0
        } else if toolbarScaleUseEaseFallback {
            let bez = CubicBezier(c1: toolbarMotionSpec.easeC1, c2: toolbarMotionSpec.easeC2)
            let t = CGFloat(min(1.0, max(0.0, (now - toolbarScaleEaseStartTime) / max(0.001, toolbarMotionSpec.easeDuration))))
            let eased = bez.value(at: t)
            toolbarScaleTracker.value = toolbarScaleEaseStartValue + (toolbarScaleEaseTarget - toolbarScaleEaseStartValue) * eased
            toolbarScaleTracker.velocity = 0
        } else {
            let delta = abs(toolbarScaleTracker.target - toolbarScaleTracker.value)
            let omega = toolbarOmega(forDelta: delta)
            toolbarScaleTracker.step(dt: dt, dampingRatio: toolbarMotionSpec.dampingRatio, omega: omega)

            // Stability guardrails:
            // - If we see numerical instability (NaN/Inf) or runaway error, switch to cubic ease.
            // - If we overshoot beyond 3% after resize has effectively stopped, switch to ease.
            let v = toolbarScaleTracker.value
            let vel = toolbarScaleTracker.velocity
            let target = toolbarScaleTracker.target
            let err = v - target

            let isFinite = v.isFinite && vel.isFinite && target.isFinite
            let runaway = abs(err) > 0.20 || abs(vel) > 4.0
            if !isFinite || runaway {
                setToolbarScaleTarget(normalizedScale: target, preferEaseFallback: true)
            } else {
                // Overshoot cap is only meaningful when target is stable and we’re not in live resize.
                let targetStable = (now - toolbarScaleLastTargetChangeTime) >= 0.05
                let notLive = (window?.inLiveResize != true)
                if targetStable && notLive {
                    let crossed = (toolbarScalePrevError.sign != err.sign) && (toolbarScalePrevError != 0)
                    if crossed {
                        let overshootCap = 0.03 * max(0.001, abs(target))
                        if abs(err) > overshootCap {
                            setToolbarScaleTarget(normalizedScale: target, preferEaseFallback: true)
                        }
                    }
                }
                toolbarScalePrevError = err
            }
        }

        applyToolbarMetricsIfNeeded(metrics: toolbarMetrics(forNormalizedScale: toolbarScaleTracker.value))
        stopToolbarScaleTickerIfIdle()
    }

    private func applyToolbarMetricsIfNeeded(metrics: ToolbarScaleMetrics) {
        let duringDividerDrag = dividerDragActive

        // Avoid re-applying tiny deltas (prevents micro-jitter on continuous resize).
        if let last = toolbarScaleLastApplied {
            let eps: CGFloat = 0.002
            if abs(last.normalizedScale - metrics.normalizedScale) < eps && window?.inLiveResize != true {
                return
            }
        }

        let t0 = toolbarPerfEnabled ? monotonicNow() : 0

        // Keep legacy derived values updated for other layout code paths.
        toolbarControlScaleCurrent = toolbarControlScaleBase * metrics.normalizedScale
        toolbarControlHeight = metrics.controlHeight
        toolbarSpacingCurrent = metrics.spacing
        navInset = metrics.navInset
        pageInset = metrics.pageInset

        toolbarControls.spacing = metrics.spacing

        // Update constraint constants (hit targets clamped by metrics).
        let navWidth = (2 * metrics.navButtonWidth) + navDividerWidth + (2 * metrics.navInset)
        sidebarWidthConstraint?.constant = navWidth
        sidebarHeightConstraint?.constant = metrics.controlHeight
        navWidthConstraint?.constant = navWidth
        navHeightConstraint?.constant = metrics.controlHeight
        pageWidthConstraint?.constant = metrics.pageMinWidth
        pageHeightConstraint?.constant = metrics.controlHeight

        sidebarToggleWidthConstraint?.constant = metrics.navButtonWidth
        sidebarToggleHeightConstraint?.constant = metrics.buttonSize
        sidebarMenuWidthConstraint?.constant = metrics.navButtonWidth
        sidebarMenuHeightConstraint?.constant = metrics.buttonSize
        backWidthConstraint?.constant = metrics.navButtonWidth
        backHeightConstraint?.constant = metrics.buttonSize
        forwardWidthConstraint?.constant = metrics.navButtonWidth
        forwardHeightConstraint?.constant = metrics.buttonSize
        pageMenuHeightConstraint?.constant = metrics.buttonSize
        pageMenuLeadingConstraint?.constant = metrics.pageInset
        pageMenuTrailingConstraint?.constant = -metrics.pageInset

        // Update icon sizes + text sizes using the coupled scale.
        let symbolConfig = NSImage.SymbolConfiguration(pointSize: metrics.symbolPointSize, weight: .regular)

        updateSidebarToggleIcon()
        sidebarMenuButton.image = NSImage(systemSymbolName: "chevron.down", accessibilityDescription: nil)?.withSymbolConfiguration(symbolConfig)
        backButton.image = NSImage(systemSymbolName: "chevron.left", accessibilityDescription: nil)?.withSymbolConfiguration(symbolConfig)
        forwardButton.image = NSImage(systemSymbolName: "chevron.right", accessibilityDescription: nil)?.withSymbolConfiguration(symbolConfig)
        pageMenuButton.image = NSImage(systemSymbolName: "chevron.down", accessibilityDescription: nil)?.withSymbolConfiguration(symbolConfig)
        rightPanelZoteroEdgeButton.image = zoteroMonogramTemplateImage(pointSize: metrics.symbolPointSize, weight: .semibold)

        // Right-panel edge button symbols (Chat/Share/Settings).
        let chatNames = ["bubble.left.and.bubble.right", "message", "bubble.left"]
        var leftEdgeImage: NSImage?
        for name in chatNames {
            if let img = NSImage(systemSymbolName: name, accessibilityDescription: nil) { leftEdgeImage = img; break }
        }
        rightPanelLeftEdgeButton.image = leftEdgeImage?.withSymbolConfiguration(symbolConfig)

        let shareNames = ["square.and.arrow.up", "square.and.arrow.up.on.square", "square.and.arrow.up.circle"]
        var rightEdgeImage: NSImage?
        for name in shareNames {
            if let img = NSImage(systemSymbolName: name, accessibilityDescription: nil) { rightEdgeImage = img; break }
        }
        rightPanelRightEdgeButton.image = rightEdgeImage?.withSymbolConfiguration(symbolConfig)

        let settingsNames = ["gearshape", "gear", "gearshape.fill"]
        var settingsImage: NSImage?
        for name in settingsNames {
            if let img = NSImage(systemSymbolName: name, accessibilityDescription: nil) { settingsImage = img; break }
        }
        rightPanelSettingsEdgeButton.image = settingsImage?.withSymbolConfiguration(symbolConfig)

        // Page menu font scales with s^1.00.
        pageMenuButton.font = NSFont.systemFont(ofSize: metrics.pageFontSize, weight: .medium)
        pageMenuButton.updateTint()

        // Apply corner radius scaling (s^0.90) without ever shrinking below safe bounds.
        sidebarControlBackground.wantsLayer = true
        sidebarControlBackground.layer?.cornerRadius = metrics.cornerRadius
        navControlBackground.wantsLayer = true
        navControlBackground.layer?.cornerRadius = metrics.cornerRadius
        pageControlBackground.wantsLayer = true
        pageControlBackground.layer?.cornerRadius = metrics.cornerRadius
        if #available(macOS 10.13, *) {
            sidebarControlBackground.layer?.cornerCurve = .continuous
            navControlBackground.layer?.cornerCurve = .continuous
            pageControlBackground.layer?.cornerCurve = .continuous
        }
        if #available(macOS 26.0, *) {
            (sidebarControlBackground as? NSGlassEffectView)?.cornerRadius = metrics.cornerRadius
            (navControlBackground as? NSGlassEffectView)?.cornerRadius = metrics.cornerRadius
            (pageControlBackground as? NSGlassEffectView)?.cornerRadius = metrics.cornerRadius
        }

        sidebarToggleButton.setCornerRadius(metrics.cornerRadius)
        sidebarMenuButton.setCornerRadius(metrics.cornerRadius)
        backButton.setCornerRadius(metrics.cornerRadius, maskedCorners: [.layerMinXMinYCorner, .layerMinXMaxYCorner])
        forwardButton.setCornerRadius(metrics.cornerRadius, maskedCorners: [.layerMaxXMinYCorner, .layerMaxXMaxYCorner])
        pageMenuButton.setCornerRadius(metrics.cornerRadius)

        // Border thickness scaling for the pill’s glass rim/lines (s^0.65).
        var pillConfig = GlassCardKit.GlassCardConfig()
        pillConfig.cornerRadius = metrics.controlHeight / 2
        pillConfig.tint = toolbarGlassTintColor()
        pillConfig.transmission = (isDarkForToolbarGlass() ? TOOLBAR_GLASS_TRANSMISSION_DARK : TOOLBAR_GLASS_TRANSMISSION_LIGHT)
        pillConfig.diffusionAmount = (isDarkForToolbarGlass() ? TOOLBAR_GLASS_DIFFUSION_DARK : TOOLBAR_GLASS_DIFFUSION_LIGHT)
        pillConfig.refractionStrength = (isDarkForToolbarGlass() ? TOOLBAR_GLASS_REFRACTION_STRENGTH_DARK : TOOLBAR_GLASS_REFRACTION_STRENGTH_LIGHT)
        pillConfig.fresnelStrength = (isDarkForToolbarGlass() ? TOOLBAR_GLASS_FRESNEL_STRENGTH_DARK : TOOLBAR_GLASS_FRESNEL_STRENGTH_LIGHT)
        pillConfig.specularIntensity = (isDarkForToolbarGlass() ? TOOLBAR_GLASS_SPECULAR_DARK : TOOLBAR_GLASS_SPECULAR_LIGHT)
        pillConfig.shadowStyle = {
            var s = GlassCardKit.ShadowStyle.subtle
            s.bottomAlpha = (isDarkForToolbarGlass() ? TOOLBAR_GLASS_SHADOW_BOTTOM_DARK : TOOLBAR_GLASS_SHADOW_BOTTOM_LIGHT)
            if !isDarkForToolbarGlass() { s.rimOpacity *= TOOLBAR_GLASS_RIM_OPACITY_LIGHT_SCALE }
            return s
        }()
        pillConfig.borderStyle = {
            var b = GlassCardKit.BorderStyle.clearRim
            if !isDarkForToolbarGlass() {
                b.rimDarkAlpha *= 0.82
                b.outerAlpha *= 0.92
                b.innerAlpha *= 0.95
                b.dispersionAlpha *= 0.90
            }
            return b
        }()
        pillConfig.thickness = metrics.borderThickness
        rightPanelPillControl.applyConfig(pillConfig)

        // Make the most recent metrics visible to other layout helpers.
        toolbarScaleLastApplied = metrics

        headerControlsContainer.needsLayout = true
        if !duringDividerDrag {
            headerControlsContainer.layoutSubtreeIfNeeded()
            layoutToolbarControls()
            layoutViewerAnchoredHeaderControls()
        } else {
            // Keep divider drags responsive: avoid full layout passes.
            if let root = headerControlsContainer.superview {
                layoutRightPanelPillControl(in: root)
            }
        }

        if toolbarPerfEnabled {
            let ms = Int((monotonicNow() - t0) * 1000.0)
            if ms > 20 {
                NSLog("[ToolbarResizePerf] apply_ms=\(ms) scale=\(String(format: "%.3f", metrics.normalizedScale))")
            }
        }
    }
    
    // Constraint handles for responsive toolbar updates during live resize.
    private var sidebarWidthConstraint: NSLayoutConstraint?
    private var navWidthConstraint: NSLayoutConstraint?
    private var pageWidthConstraint: NSLayoutConstraint?
    private var sidebarHeightConstraint: NSLayoutConstraint?
    private var navHeightConstraint: NSLayoutConstraint?
    private var pageHeightConstraint: NSLayoutConstraint?
    private var sidebarToggleWidthConstraint: NSLayoutConstraint?
    private var sidebarToggleHeightConstraint: NSLayoutConstraint?
    private var sidebarMenuWidthConstraint: NSLayoutConstraint?
    private var sidebarMenuHeightConstraint: NSLayoutConstraint?
    private var backWidthConstraint: NSLayoutConstraint?
    private var backHeightConstraint: NSLayoutConstraint?
    private var forwardWidthConstraint: NSLayoutConstraint?
    private var forwardHeightConstraint: NSLayoutConstraint?
    private var pageMenuHeightConstraint: NSLayoutConstraint?
    private var pageMenuLeadingConstraint: NSLayoutConstraint?
    private var pageMenuTrailingConstraint: NSLayoutConstraint?

    // Toolbar/pill glass debug instrumentation.
    // Set `ARXIV_TOOLBAR_GLASS_DEBUG=1` to log effective appearance + recipe parameters.
    private var toolbarGlassDebugEnabled: Bool {
        ProcessInfo.processInfo.environment["ARXIV_TOOLBAR_GLASS_DEBUG"] == "1" || settingsSnapshot.advancedDeveloper.enableToolbarGlassDebug
    }

    private func toolbarGlassLog(_ message: String) {
        guard toolbarGlassDebugEnabled else { return }
        NSLog("[ToolbarGlass] \(message)")
    }

    private func isDarkForToolbarGlass() -> Bool {
        let appearance = window?.effectiveAppearance ?? NSApplication.shared.effectiveAppearance
        return (appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua)
    }

    private func toolbarGlassConfig(cornerRadius: CGFloat, tint: NSColor) -> GlassCardKit.GlassCardConfig {
        // Dropdown glass is intentionally “milky” (high diffusion, low transmission).
        // Toolbar/pill glass must be clear + luminous in Light Mode (subtle blur, high transmission).
        let dark = isDarkForToolbarGlass()

        var config = GlassCardKit.GlassCardConfig()
        config.cornerRadius = cornerRadius
        config.tint = tint

        config.transmission = dark ? TOOLBAR_GLASS_TRANSMISSION_DARK : TOOLBAR_GLASS_TRANSMISSION_LIGHT
        config.diffusionAmount = dark ? TOOLBAR_GLASS_DIFFUSION_DARK : TOOLBAR_GLASS_DIFFUSION_LIGHT
        config.refractionStrength = dark ? TOOLBAR_GLASS_REFRACTION_STRENGTH_DARK : TOOLBAR_GLASS_REFRACTION_STRENGTH_LIGHT
        config.fresnelStrength = dark ? TOOLBAR_GLASS_FRESNEL_STRENGTH_DARK : TOOLBAR_GLASS_FRESNEL_STRENGTH_LIGHT
        config.specularIntensity = dark ? TOOLBAR_GLASS_SPECULAR_DARK : TOOLBAR_GLASS_SPECULAR_LIGHT

        var shadow = config.shadowStyle
        shadow.bottomAlpha = dark ? TOOLBAR_GLASS_SHADOW_BOTTOM_DARK : TOOLBAR_GLASS_SHADOW_BOTTOM_LIGHT
        if !dark {
            shadow.rimOpacity *= TOOLBAR_GLASS_RIM_OPACITY_LIGHT_SCALE
        }
        config.shadowStyle = shadow

        var border = config.borderStyle
        if !dark {
            // Reduce dark rim energy in Light Mode (prevents gray/smoky read on white).
            border.rimDarkAlpha *= 0.82
            border.outerAlpha *= 0.92
            border.innerAlpha *= 0.95
            border.dispersionAlpha *= 0.90
        }
        config.borderStyle = border

        let a = (tint.usingColorSpace(.deviceRGB) ?? tint).alphaComponent
        toolbarGlassLog(String(format: "recipe dark=%@ transmission=%.2f diffusion=%.2f refr=%.2f fresnel=%.2f spec=%.2f shadowBottom=%.2f tintA=%.3f",
                              dark ? "true" : "false",
                              config.transmission,
                              config.diffusionAmount,
                              config.refractionStrength,
                              config.fresnelStrength,
                              config.specularIntensity,
                              config.shadowStyle.bottomAlpha,
                              a))
        return config
    }

    private func applyToolbarGlassRecipe(reason: String) {
        guard toolbarControlHeight > 0 else { return }

        let appearance = window?.effectiveAppearance ?? NSApplication.shared.effectiveAppearance
        let match = appearance.bestMatch(from: [.darkAqua, .aqua])
        toolbarGlassLog("apply reason=\(reason) match=\(match?.rawValue ?? "nil")")

        let tint = toolbarGlassTintColor()

        // Group backgrounds.
        applyEmbeddedSearchBarTheme(to: sidebarControlBackground)
        applyEmbeddedSearchBarTheme(to: navControlBackground)

        // Edge buttons.
        if let left = rightPanelLeftEdgeButtonBackground {
            applyEmbeddedSearchBarTheme(to: left)
        }
        if let zotero = rightPanelZoteroEdgeButtonBackground {
            applyEmbeddedSearchBarTheme(to: zotero)
        }
        if let right = rightPanelRightEdgeButtonBackground {
            applyEmbeddedSearchBarTheme(to: right)
        }
        if let settings = rightPanelSettingsEdgeButtonBackground {
            applyEmbeddedSearchBarTheme(to: settings)
        }

        // Pill control.
        rightPanelPillControl.applyConfig(toolbarGlassConfig(cornerRadius: toolbarControlHeight / 2, tint: tint))

        // Page control (NSVisualEffect fallback): avoid the “heavy” emphasized look in Light Mode.
        if let effect = pageControlBackground as? NSVisualEffectView {
            effect.isEmphasized = isDarkForToolbarGlass()
        }
    }

    private func toolbarSymbolConfig() -> NSImage.SymbolConfiguration {
        NSImage.SymbolConfiguration(pointSize: 13 * toolbarControlScale, weight: .regular)
    }

    private func sidebarToggleSymbol(visible: Bool) -> NSImage? {
        let names: [String]
        if visible {
            names = ["sidebar.leading", "sidebar.left"]
        } else {
            names = ["sidebar.leading.slash", "sidebar.left.slash", "sidebar.trailing", "sidebar.right", "sidebar.leading", "sidebar.left"]
        }
        for name in names {
            if let image = NSImage(systemSymbolName: name, accessibilityDescription: nil) {
                return image.withSymbolConfiguration(toolbarSymbolConfig())
            }
        }
        return nil
    }

    private func updateSidebarToggleIcon() {
        sidebarToggleButton.image = sidebarToggleSymbol(visible: sidebarVisible)
    }

    private func setupToolbarControls() {
        let controlHeight: CGFloat = 32 * toolbarControlScaleBase
        let buttonSize: CGFloat = 24 * toolbarControlScaleBase
        let navButtonWidth: CGFloat = 30 * toolbarControlScaleBase
        let navDividerWidth: CGFloat = 1
        let navInset: CGFloat = 5
        let navWidth = (2 * navButtonWidth) + navDividerWidth + (2 * navInset)
        let pageInset: CGFloat = 10
        let pageMinWidth: CGFloat = pageMinWidthBase

        let toolbarTint = toolbarGlassTintColor()
        toolbarControlHeight = controlHeight

        // Pill glass MUST NOT reuse dropdown/base glass (those are intentionally over-frosted).
        // Use a dedicated toolbar recipe that becomes extra clear/bright in Light Mode.
        rightPanelPillControl.applyConfig(toolbarGlassConfig(cornerRadius: controlHeight / 2, tint: toolbarTint))
        rightPanelPillControl.backgroundProvider = { [weak self] rectInWindow, scale in
            self?.captureWindowBackgroundRegion(in: rectInWindow, scale: scale)
        }
        rightPanelPillControl.reduceMotionProvider = { [weak self] in
            self?.shouldReduceMotion ?? false
        }
        rightPanelPillControl.mirroredHorizontally = true
        rightPanelPillControl.pathAnimationPreset = .microBounce
        rightPanelPillControl.pathAnimationDuration = 0.5
        rightPanelPillControl.translatesAutoresizingMaskIntoConstraints = true
        rightPanelPillControl.onActivate = { [weak self] in
            self?.triggerRightPanelPillTransition()
        }
        rightPanelPillControl.backgroundThemeApplier = { [weak self] background in
            guard let self else { return }
            self.applyEmbeddedSearchBarTheme(to: background)
        }

        let searchTheme = currentSearchBarTheme()
        sidebarControlBackground = makeGlassEffectView(
            passthrough: true,
            cornerRadius: controlHeight / 2,
            tintColor: nil,
            style: .regular,
            fallbackMaterial: searchTheme.fallbackMaterial,
            fallbackBlending: searchTheme.fallbackBlending,
            fallbackState: searchTheme.fallbackState,
            emphasized: searchTheme.emphasized
        )
        applyEmbeddedSearchBarTheme(to: sidebarControlBackground)
        navControlBackground = makeGlassEffectView(
            passthrough: true,
            cornerRadius: controlHeight / 2,
            tintColor: nil,
            style: .regular,
            fallbackMaterial: searchTheme.fallbackMaterial,
            fallbackBlending: searchTheme.fallbackBlending,
            fallbackState: searchTheme.fallbackState,
            emphasized: searchTheme.emphasized
        )
        applyEmbeddedSearchBarTheme(to: navControlBackground)

        pageControlBackground = makeGlassEffectView(
            passthrough: true,
            cornerRadius: controlHeight / 2,
            tintColor: toolbarTint,
            style: .regular,
            fallbackMaterial: .headerView,
            fallbackBlending: .withinWindow,
            fallbackState: .active,
            emphasized: true
        )
        pageControlBackground.wantsLayer = true

        toolbarControls.translatesAutoresizingMaskIntoConstraints = false
        toolbarControls.orientation = .horizontal
        toolbarControls.alignment = .centerY
        toolbarControls.spacing = 8
        toolbarControls.setContentHuggingPriority(.required, for: .horizontal)
        toolbarControls.setContentCompressionResistancePriority(.required, for: .horizontal)

        sidebarControlContainer.translatesAutoresizingMaskIntoConstraints = false
        navControlContainer.translatesAutoresizingMaskIntoConstraints = false
        pageControlContainer.translatesAutoresizingMaskIntoConstraints = false

        sidebarControlContainer.addSubview(sidebarControlBackground)
        sidebarControlContainer.addSubview(sidebarControlOrnamentOverlay, positioned: .above, relativeTo: sidebarControlBackground)
        sidebarControlContainer.addSubview(sidebarDivider)
        sidebarControlContainer.addSubview(sidebarToggleButton)
        sidebarControlContainer.addSubview(sidebarMenuButton)

        navControlContainer.addSubview(navControlBackground)
        navControlContainer.addSubview(navControlOrnamentOverlay, positioned: .above, relativeTo: navControlBackground)
        navControlContainer.addSubview(navDivider)
        navControlContainer.addSubview(backButton)
        navControlContainer.addSubview(forwardButton)

        pageControlContainer.addSubview(pageControlBackground)
        pageControlContainer.addSubview(pageMenuButton)

        let leftEdgeGlass = makeGlassEffectView(
            passthrough: true,
            cornerRadius: controlHeight / 2,
            tintColor: nil,
            style: .regular,
            fallbackMaterial: searchTheme.fallbackMaterial,
            fallbackBlending: searchTheme.fallbackBlending,
            fallbackState: searchTheme.fallbackState,
            emphasized: searchTheme.emphasized
        )
        let zoteroEdgeGlass = makeGlassEffectView(
            passthrough: true,
            cornerRadius: controlHeight / 2,
            tintColor: nil,
            style: .regular,
            fallbackMaterial: searchTheme.fallbackMaterial,
            fallbackBlending: searchTheme.fallbackBlending,
            fallbackState: searchTheme.fallbackState,
            emphasized: searchTheme.emphasized
        )
        let rightEdgeGlass = makeGlassEffectView(
            passthrough: true,
            cornerRadius: controlHeight / 2,
            tintColor: nil,
            style: .regular,
            fallbackMaterial: searchTheme.fallbackMaterial,
            fallbackBlending: searchTheme.fallbackBlending,
            fallbackState: searchTheme.fallbackState,
            emphasized: searchTheme.emphasized
        )
        let settingsEdgeGlass = makeGlassEffectView(
            passthrough: true,
            cornerRadius: controlHeight / 2,
            tintColor: nil,
            style: .regular,
            fallbackMaterial: searchTheme.fallbackMaterial,
            fallbackBlending: searchTheme.fallbackBlending,
            fallbackState: searchTheme.fallbackState,
            emphasized: searchTheme.emphasized
        )
        applyEmbeddedSearchBarTheme(to: leftEdgeGlass)
        applyEmbeddedSearchBarTheme(to: zoteroEdgeGlass)
        applyEmbeddedSearchBarTheme(to: rightEdgeGlass)
        applyEmbeddedSearchBarTheme(to: settingsEdgeGlass)
        rightPanelLeftEdgeButtonBackground = leftEdgeGlass
        rightPanelZoteroEdgeButtonBackground = zoteroEdgeGlass
        rightPanelRightEdgeButtonBackground = rightEdgeGlass
        rightPanelSettingsEdgeButtonBackground = settingsEdgeGlass

        toolbarControls.addArrangedSubview(sidebarControlContainer)
        toolbarControls.addArrangedSubview(navControlContainer)
        toolbarControls.addArrangedSubview(pageControlContainer)

        let symbolConfig = NSImage.SymbolConfiguration(pointSize: 13 * toolbarControlScaleBase, weight: .regular)
        updateSidebarToggleIcon()
        sidebarToggleButton.target = self
        sidebarToggleButton.action = #selector(toggleSidebar)
        sidebarToggleButton.updateTint()

        let sidebarMenuImage = NSImage(systemSymbolName: "chevron.down", accessibilityDescription: nil)?
            .withSymbolConfiguration(symbolConfig)
        sidebarMenuButton.image = sidebarMenuImage
        sidebarMenuButton.target = self
        sidebarMenuButton.action = #selector(showSidebarMenu)
        sidebarMenuButton.updateTint()

        let backImage = NSImage(systemSymbolName: "chevron.left", accessibilityDescription: nil)?
            .withSymbolConfiguration(symbolConfig)
        let forwardImage = NSImage(systemSymbolName: "chevron.right", accessibilityDescription: nil)?
            .withSymbolConfiguration(symbolConfig)
        backButton.image = backImage
        forwardButton.image = forwardImage
        backButton.target = self
        forwardButton.target = self
        backButton.action = #selector(navigateBack)
        forwardButton.action = #selector(navigateForward)
        backButton.updateTint()
        forwardButton.updateTint()

        pageMenuButton.title = "Page 1"
        pageMenuButton.font = NSFont.systemFont(ofSize: 12.5, weight: .medium)
        pageMenuButton.image = NSImage(systemSymbolName: "chevron.down", accessibilityDescription: nil)?
            .withSymbolConfiguration(symbolConfig)
        pageMenuButton.target = self
        pageMenuButton.action = #selector(showPageMenu)
        pageMenuButton.updateTint()
        pageMenuButton.setContentHuggingPriority(.required, for: .horizontal)
        pageMenuButton.setContentCompressionResistancePriority(.required, for: .horizontal)

        let chatNames = [
            "bubble.left.and.bubble.right",
            "message",
            "bubble.left"
        ]
        var leftEdgeImage: NSImage?
        for name in chatNames {
            if let img = NSImage(systemSymbolName: name, accessibilityDescription: nil) {
                leftEdgeImage = img
                break
            }
        }
        leftEdgeImage = leftEdgeImage?.withSymbolConfiguration(symbolConfig)
        let shareNames = [
            "square.and.arrow.up",
            "square.and.arrow.up.on.square",
            "square.and.arrow.up.circle"
        ]
        var rightEdgeImage: NSImage?
        for name in shareNames {
            if let img = NSImage(systemSymbolName: name, accessibilityDescription: nil) {
                rightEdgeImage = img
                break
            }
        }
        rightEdgeImage = rightEdgeImage?.withSymbolConfiguration(symbolConfig)

        let settingsNames = [
            "gearshape",
            "gear",
            "gearshape.fill"
        ]
        var settingsImage: NSImage?
        for name in settingsNames {
            if let img = NSImage(systemSymbolName: name, accessibilityDescription: nil) {
                settingsImage = img
                break
            }
        }
        settingsImage = settingsImage?.withSymbolConfiguration(symbolConfig)

        rightPanelLeftEdgeButton.image = leftEdgeImage
        rightPanelZoteroEdgeButton.image = zoteroMonogramTemplateImage(pointSize: 13 * toolbarControlScaleCurrent, weight: .semibold)
        rightPanelRightEdgeButton.image = rightEdgeImage
        rightPanelSettingsEdgeButton.image = settingsImage
        rightPanelLeftEdgeButton.updateTint()
        rightPanelZoteroEdgeButton.updateTint()
        rightPanelRightEdgeButton.updateTint()
        rightPanelSettingsEdgeButton.updateTint()

        // Rightmost toolbar edge button toggles the third (right) panel.
        rightPanelLeftEdgeButton.target = self
        rightPanelLeftEdgeButton.action = #selector(toggleRightPanel)

        // Save to Zotero button: positioned immediately left of Chat Session toggle.
        rightPanelZoteroEdgeButton.target = self
        rightPanelZoteroEdgeButton.action = #selector(saveCurrentPaperToZotero)
        rightPanelZoteroEdgeButton.toolTip = "Save to Zotero"

        // Share button: open the system default mail client (Mail.app when configured as default).
        rightPanelRightEdgeButton.target = self
        rightPanelRightEdgeButton.action = #selector(shareCurrentPaperByEmail)

        // Settings button: open the settings window.
        rightPanelSettingsEdgeButton.target = SettingsWindowController.shared
        rightPanelSettingsEdgeButton.action = #selector(SettingsWindowController.openSettings(_:))
        updateRightAuxToggleButtonAppearance()

        updateToolbarSeparatorStyle()

        sidebarControlBackground.translatesAutoresizingMaskIntoConstraints = false
        navControlBackground.translatesAutoresizingMaskIntoConstraints = false
        sidebarControlOrnamentOverlay.translatesAutoresizingMaskIntoConstraints = false
        navControlOrnamentOverlay.translatesAutoresizingMaskIntoConstraints = false
        sidebarToggleButton.translatesAutoresizingMaskIntoConstraints = false
        sidebarMenuButton.translatesAutoresizingMaskIntoConstraints = false
        backButton.translatesAutoresizingMaskIntoConstraints = false
        forwardButton.translatesAutoresizingMaskIntoConstraints = false
        pageControlBackground.translatesAutoresizingMaskIntoConstraints = false
        pageMenuButton.translatesAutoresizingMaskIntoConstraints = false
        sidebarDivider.translatesAutoresizingMaskIntoConstraints = false
        navDivider.translatesAutoresizingMaskIntoConstraints = false
        rightPanelLeftEdgeButton.translatesAutoresizingMaskIntoConstraints = true
        rightPanelZoteroEdgeButton.translatesAutoresizingMaskIntoConstraints = true
        rightPanelRightEdgeButton.translatesAutoresizingMaskIntoConstraints = true
        rightPanelSettingsEdgeButton.translatesAutoresizingMaskIntoConstraints = true

        // Capture constraint handles so window resize can update constants smoothly.
        sidebarWidthConstraint = sidebarControlContainer.widthAnchor.constraint(equalToConstant: navWidth)
        sidebarHeightConstraint = sidebarControlContainer.heightAnchor.constraint(equalToConstant: controlHeight)

        navWidthConstraint = navControlContainer.widthAnchor.constraint(equalToConstant: navWidth)
        navHeightConstraint = navControlContainer.heightAnchor.constraint(equalToConstant: controlHeight)

        pageHeightConstraint = pageControlContainer.heightAnchor.constraint(equalToConstant: controlHeight)
        pageWidthConstraint = pageControlContainer.widthAnchor.constraint(greaterThanOrEqualToConstant: pageMinWidth)

        sidebarToggleWidthConstraint = sidebarToggleButton.widthAnchor.constraint(equalToConstant: navButtonWidth)
        sidebarToggleHeightConstraint = sidebarToggleButton.heightAnchor.constraint(equalToConstant: buttonSize)
        sidebarMenuWidthConstraint = sidebarMenuButton.widthAnchor.constraint(equalToConstant: navButtonWidth)
        sidebarMenuHeightConstraint = sidebarMenuButton.heightAnchor.constraint(equalToConstant: buttonSize)
        backWidthConstraint = backButton.widthAnchor.constraint(equalToConstant: navButtonWidth)
        backHeightConstraint = backButton.heightAnchor.constraint(equalToConstant: buttonSize)
        forwardWidthConstraint = forwardButton.widthAnchor.constraint(equalToConstant: navButtonWidth)
        forwardHeightConstraint = forwardButton.heightAnchor.constraint(equalToConstant: buttonSize)
        pageMenuLeadingConstraint = pageMenuButton.leadingAnchor.constraint(equalTo: pageControlContainer.leadingAnchor, constant: pageInset)
        pageMenuTrailingConstraint = pageMenuButton.trailingAnchor.constraint(equalTo: pageControlContainer.trailingAnchor, constant: -pageInset)
        pageMenuHeightConstraint = pageMenuButton.heightAnchor.constraint(equalToConstant: buttonSize)

        NSLayoutConstraint.activate([
            sidebarWidthConstraint!,
            sidebarHeightConstraint!,

            navWidthConstraint!,
            navHeightConstraint!,

            pageHeightConstraint!,
            pageWidthConstraint!,

            sidebarControlBackground.leadingAnchor.constraint(equalTo: sidebarControlContainer.leadingAnchor),
            sidebarControlBackground.trailingAnchor.constraint(equalTo: sidebarControlContainer.trailingAnchor),
            sidebarControlBackground.topAnchor.constraint(equalTo: sidebarControlContainer.topAnchor),
            sidebarControlBackground.bottomAnchor.constraint(equalTo: sidebarControlContainer.bottomAnchor),

            sidebarControlOrnamentOverlay.leadingAnchor.constraint(equalTo: sidebarControlContainer.leadingAnchor),
            sidebarControlOrnamentOverlay.trailingAnchor.constraint(equalTo: sidebarControlContainer.trailingAnchor),
            sidebarControlOrnamentOverlay.topAnchor.constraint(equalTo: sidebarControlContainer.topAnchor),
            sidebarControlOrnamentOverlay.bottomAnchor.constraint(equalTo: sidebarControlContainer.bottomAnchor),

            navControlBackground.leadingAnchor.constraint(equalTo: navControlContainer.leadingAnchor),
            navControlBackground.trailingAnchor.constraint(equalTo: navControlContainer.trailingAnchor),
            navControlBackground.topAnchor.constraint(equalTo: navControlContainer.topAnchor),
            navControlBackground.bottomAnchor.constraint(equalTo: navControlContainer.bottomAnchor),

            navControlOrnamentOverlay.leadingAnchor.constraint(equalTo: navControlContainer.leadingAnchor),
            navControlOrnamentOverlay.trailingAnchor.constraint(equalTo: navControlContainer.trailingAnchor),
            navControlOrnamentOverlay.topAnchor.constraint(equalTo: navControlContainer.topAnchor),
            navControlOrnamentOverlay.bottomAnchor.constraint(equalTo: navControlContainer.bottomAnchor),

            pageControlBackground.leadingAnchor.constraint(equalTo: pageControlContainer.leadingAnchor),
            pageControlBackground.trailingAnchor.constraint(equalTo: pageControlContainer.trailingAnchor),
            pageControlBackground.topAnchor.constraint(equalTo: pageControlContainer.topAnchor),
            pageControlBackground.bottomAnchor.constraint(equalTo: pageControlContainer.bottomAnchor),

            sidebarToggleButton.leadingAnchor.constraint(equalTo: sidebarControlContainer.leadingAnchor, constant: navInset),
            sidebarToggleButton.centerYAnchor.constraint(equalTo: sidebarControlContainer.centerYAnchor),
            sidebarToggleWidthConstraint!,
            sidebarToggleHeightConstraint!,

            sidebarDivider.leadingAnchor.constraint(equalTo: sidebarToggleButton.trailingAnchor),
            sidebarDivider.centerYAnchor.constraint(equalTo: sidebarControlContainer.centerYAnchor),
            sidebarDivider.widthAnchor.constraint(equalToConstant: navDividerWidth),
            sidebarDivider.heightAnchor.constraint(equalToConstant: 18),

            sidebarMenuButton.leadingAnchor.constraint(equalTo: sidebarDivider.trailingAnchor),
            sidebarMenuButton.trailingAnchor.constraint(equalTo: sidebarControlContainer.trailingAnchor, constant: -navInset),
            sidebarMenuButton.centerYAnchor.constraint(equalTo: sidebarControlContainer.centerYAnchor),
            sidebarMenuWidthConstraint!,
            sidebarMenuHeightConstraint!,

            backButton.leadingAnchor.constraint(equalTo: navControlContainer.leadingAnchor, constant: navInset),
            backButton.centerYAnchor.constraint(equalTo: navControlContainer.centerYAnchor),
            backWidthConstraint!,
            backHeightConstraint!,

            navDivider.leadingAnchor.constraint(equalTo: backButton.trailingAnchor),
            navDivider.centerYAnchor.constraint(equalTo: navControlContainer.centerYAnchor),
            navDivider.widthAnchor.constraint(equalToConstant: navDividerWidth),
            navDivider.heightAnchor.constraint(equalToConstant: 18),

            forwardButton.leadingAnchor.constraint(equalTo: navDivider.trailingAnchor),
            forwardButton.trailingAnchor.constraint(equalTo: navControlContainer.trailingAnchor, constant: -navInset),
            forwardButton.centerYAnchor.constraint(equalTo: navControlContainer.centerYAnchor),
            forwardWidthConstraint!,
            forwardHeightConstraint!,

            pageMenuLeadingConstraint!,
            pageMenuTrailingConstraint!,
            pageMenuButton.centerYAnchor.constraint(equalTo: pageControlContainer.centerYAnchor),
            pageMenuHeightConstraint!
        ])

        pageControlContainer.isHidden = true
        layoutToolbarControls()
        updateNavigationButtons()

        // Initialize resize-driven scale tracker at the current normalized scale.
        toolbarScaleTracker.reset(to: 1.0)
        toolbarScaleLastApplied = nil
        // Apply initial metrics immediately so later resize deltas are continuous.
        applyToolbarMetricsIfNeeded(metrics: toolbarMetrics(forNormalizedScale: 1.0))

        // Apply the correct appearance-aware glass recipe at startup.
        applyToolbarGlassRecipe(reason: "setup")
    }

    private func setupSuggestionsDropdown() {
        suggestionsBackground = makeDropdownGlassCard()

        suggestionsContainer.translatesAutoresizingMaskIntoConstraints = true
        suggestionsContainer.wantsLayer = true
        suggestionsContainer.isHidden = true
        if let layer = suggestionsContainer.layer {
            layer.opacity = 0
            layer.anchorPoint = CGPoint(x: 0.5, y: 1.0)
        }

        suggestionsTable.headerView = nil
        suggestionsTable.dataSource = self
        suggestionsTable.delegate = self
        suggestionsTable.focusRingType = .none
        suggestionsTable.allowsEmptySelection = true
        suggestionsTable.allowsMultipleSelection = false
        suggestionsTable.selectionHighlightStyle = .none
        suggestionsTable.backgroundColor = .clear
        suggestionsTable.usesAlternatingRowBackgroundColors = false
        suggestionsTable.intercellSpacing = .zero
        suggestionsTable.columnAutoresizingStyle = .uniformColumnAutoresizingStyle
        suggestionsTable.target = self
        suggestionsTable.action = #selector(suggestionClicked)
        if suggestionsTable.tableColumns.isEmpty {
            let col = NSTableColumn(identifier: .init("suggestion"))
            col.title = ""
            col.resizingMask = .autoresizingMask
            suggestionsTable.addTableColumn(col)
        }

        suggestionsScroll.drawsBackground = false
        suggestionsScroll.backgroundColor = .clear
        suggestionsScroll.hasVerticalScroller = false
        suggestionsScroll.hasHorizontalScroller = false
        suggestionsScroll.verticalScrollElasticity = .none
        suggestionsScroll.horizontalScrollElasticity = .none
        suggestionsScroll.automaticallyAdjustsContentInsets = false
        suggestionsScroll.contentInsets = dropdownContentInsets
        suggestionsScroll.documentView = suggestionsTable

        suggestionsContainer.addSubview(suggestionsBackground)
        suggestionsContainer.addSubview(suggestionsScroll)
    }

    private func setupMenuPanel() {
        let card = makeDropdownGlassCard()
        menuBackground = card

        menuContainer.translatesAutoresizingMaskIntoConstraints = true
        menuContainer.wantsLayer = true
        menuContainer.isHidden = true
        if let layer = menuContainer.layer {
            layer.opacity = 0
            layer.anchorPoint = CGPoint(x: 0.5, y: 1.0)
        }

        menuTable.headerView = nil
        menuTable.dataSource = self
        menuTable.delegate = self
        menuTable.focusRingType = .none
        menuTable.selectionHighlightStyle = .none
        menuTable.backgroundColor = .clear
        menuTable.usesAlternatingRowBackgroundColors = false
        menuTable.intercellSpacing = .zero
        menuTable.columnAutoresizingStyle = .uniformColumnAutoresizingStyle
        menuTable.target = self
        menuTable.action = #selector(menuRowClicked)
        if menuTable.tableColumns.isEmpty {
            let col = NSTableColumn(identifier: .init("menu"))
            col.title = ""
            col.resizingMask = .autoresizingMask
            menuTable.addTableColumn(col)
        }

        menuScroll.drawsBackground = false
        menuScroll.backgroundColor = .clear
        menuScroll.hasVerticalScroller = false
        menuScroll.hasHorizontalScroller = false
        menuScroll.verticalScrollElasticity = .none
        menuScroll.horizontalScrollElasticity = .none
        menuScroll.automaticallyAdjustsContentInsets = false
        menuScroll.contentInsets = dropdownContentInsets
        menuScroll.documentView = menuTable

        menuContainer.addSubview(menuBackground)
        menuContainer.addSubview(menuScroll)

        menuShield.translatesAutoresizingMaskIntoConstraints = true
        menuShield.wantsLayer = false
        menuShield.isHidden = true
        menuShield.onDismiss = { [weak self] in
            self?.setMenuVisible(false, animated: true)
        }
    }

    private func setupSplitDividerHandle(in root: NSView) {
        guard splitDividerHandle == nil else { return }
        let handle = SplitDividerHandleView(frame: .zero)
        handle.translatesAutoresizingMaskIntoConstraints = true
        handle.isHidden = true
        handle.debugName = "outer_divider_handle"
        handle.paletteProvider = { [weak self] in
            self?.splitDividerPalette() ?? (
                fill: resolvedSystemColor(.separatorColor).withAlphaComponent(0.2),
                glow: NSColor.white.withAlphaComponent(0.2),
                glowOpacity: 0.2
            )
        }
        handle.positionProvider = { [weak self] in
            self?.leftContainer.frame.width ?? 0
        }
        handle.clampPosition = { [weak self] proposed in
            self?.clampSidebarWidth(proposed) ?? proposed
        }
        handle.applyPosition = { [weak self] position in
            guard let self else { return }
            self.splitView.setPosition(position, ofDividerAt: 0)
            self.splitView.adjustSubviews()
            self.updateSplitDividerHandleFrame()
            self.updateLayoutDebugOverlay(reason: "divider_apply")
        }
        handle.onDragBegin = { [weak self] in
            guard let self else { return }
            self.cancelSplitDividerSpringAnimation()
            if self.rightPanelSplitModeActive {
                self.setRightPanelSplitMode(false, animated: false)
            }
            self.dividerDragActive = true
            self.logDividerState("drag_begin")
            self.updateLayoutDebugOverlay(reason: "drag_begin")
        }
        handle.onDragEnd = { [weak self] in
            guard let self else { return }
            if self.dividerDragActive {
                self.logDividerState("drag_end")
            }
            self.dividerDragActive = false
            self.schedulePanelSettle()
            self.debugDumpViewHierarchy(reason: "divider_drag_end")
            self.debugProbeDividerHitTest(reason: "divider_drag_end")
            self.updateLayoutDebugOverlay(reason: "drag_end")
        }
        root.addSubview(handle, positioned: .above, relativeTo: splitView)
        splitDividerHandle = handle
        updateSplitDividerHandleFrame()
        handle.refreshStyle()
    }

    private func setupRightSplitDividerHandle(in root: NSView) {
        guard rightSplitDividerHandle == nil else { return }
        let handle = SplitDividerHandleView(frame: .zero)
        handle.translatesAutoresizingMaskIntoConstraints = true
        handle.isHidden = true
        handle.debugName = "right_divider_handle"
        handle.paletteProvider = { [weak self] in
            self?.splitDividerPalette() ?? (
                fill: resolvedSystemColor(.separatorColor).withAlphaComponent(0.2),
                glow: NSColor.white.withAlphaComponent(0.2),
                glowOpacity: 0.2
            )
        }
        handle.positionProvider = { [weak self] in
            self?.rightCompositeContainer.frame.width ?? 0
        }
        handle.clampPosition = { [weak self] proposed in
            self?.clampRightAuxDividerPosition(proposed) ?? proposed
        }
        handle.applyPosition = { [weak self] position in
            guard let self else { return }
            self.rightSplitView.setPosition(position, ofDividerAt: 0)
            self.updateRightSplitDividerHandleFrame()
        }
        handle.onDragBegin = { [weak self] in
            self?.cancelRightSplitDividerSpringAnimation()
        }
        handle.onDragEnd = { [weak self] in
            self?.schedulePanelSettle()
        }
        root.addSubview(handle, positioned: .above, relativeTo: splitView)
        rightSplitDividerHandle = handle
        updateRightSplitDividerHandleFrame()
        handle.refreshStyle()
    }

    private func installHitTestDebugging(in root: NSView) {
        guard uiDebugEnabled else { return }
        window?.acceptsMouseMovedEvents = true

        UserDefaults.standard.set(true, forKey: "NSConstraintBasedLayoutLogUnsatisfiable")

        if hitTestOverlay == nil {
            let overlay = DebugHitTestOverlayView(frame: root.bounds)
            overlay.translatesAutoresizingMaskIntoConstraints = true
            overlay.autoresizingMask = [.width, .height]
            root.addSubview(overlay, positioned: .above, relativeTo: menuContainer)
            hitTestOverlay = overlay
        }

        if hitTestMoveMonitor == nil {
            hitTestMoveMonitor = NSEvent.addLocalMonitorForEvents(matching: .mouseMoved) { [weak self] event in
                guard let self else { return event }
                guard let rootView = self.window?.contentView,
                      let overlay = self.hitTestOverlay else { return event }
                let hit = rootView.hitTest(event.locationInWindow)
                if let hit {
                    let rect = hit.convert(hit.bounds, to: overlay)
                    overlay.update(rect: rect)
                } else {
                    overlay.hide()
                }
                if let dividerRect = self.dividerRectInWindow(),
                   dividerRect.contains(event.locationInWindow) {
                    NSCursor.resizeLeftRight.set()
                    if !self.dividerHovering {
                        self.dividerHovering = true
                        self.uiLog("divider_hover begin location=\(String(format: "%.1f", event.locationInWindow.x)),\(String(format: "%.1f", event.locationInWindow.y))")
                    }
                } else if self.dividerHovering {
                    self.dividerHovering = false
                    self.uiLog("divider_hover end")
                }
                return event
            }
        }

        if hitTestDownMonitor == nil {
            hitTestDownMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseDown) { [weak self] event in
                guard let self else { return event }
                if let rootView = self.window?.contentView {
                    let hit = rootView.hitTest(event.locationInWindow)
                    var chain: [String] = []
                    var current = hit
                    while let view = current {
                        chain.append(String(describing: type(of: view)))
                        current = view.superview
                    }
                    let chainText = chain.joined(separator: " -> ")
                    self.uiLog("mouse_down location=\(String(format: "%.1f", event.locationInWindow.x)),\(String(format: "%.1f", event.locationInWindow.y)) hit=\(self.describeHitView(hit)) chain=\(chainText)")
                }
                if let dividerRect = self.dividerRectInWindow(),
                   dividerRect.contains(event.locationInWindow) {
                    self.cancelSplitDividerSpringAnimation()
                    if self.rightPanelSplitModeActive {
                        self.setRightPanelSplitMode(false, animated: false)
                    }
                    self.dividerDragActive = true
                    self.logDividerState("drag_begin")
                }
                return event
            }
        }

        if hitTestUpMonitor == nil {
            hitTestUpMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseUp) { [weak self] event in
                guard let self else { return event }
                if self.dividerDragActive {
                    self.logDividerState("drag_end")
                    self.dividerDragActive = false
                    self.debugDumpViewHierarchy(reason: "divider_drag_end")
                    self.debugProbeDividerHitTest(reason: "divider_drag_end")
                }
                return event
            }
        }
    }

    private func installPDFSelectionDebuggingIfNeeded() {
        guard pdfSelectDebugEnabled else { return }

        func chainText(from hit: NSView?) -> String {
            var chain: [String] = []
            var current = hit
            while let view = current {
                chain.append(String(describing: type(of: view)))
                current = view.superview
            }
            return chain.joined(separator: " -> ")
        }

        func snapshotSelection() -> (length: Int, pages: Int) {
            guard let selection = pdfView.currentSelection else { return (0, 0) }
            let length = selection.string?.count ?? 0
            let pages = selection.pages.count
            return (length, pages)
        }

        if pdfSelectDownMonitor == nil {
            pdfSelectDownMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseDown) { [weak self] event in
                guard let self else { return event }
                guard let root = self.window?.contentView else { return event }
                let hit = root.hitTest(event.locationInWindow)
                let inPDF = (hit != nil) ? (hit!.isDescendant(of: self.pdfView) || hit === self.pdfView) : false
                let sel = snapshotSelection()
                self.pdfSelectLog("down loc=\(String(format: "%.1f", event.locationInWindow.x)),\(String(format: "%.1f", event.locationInWindow.y)) isShowingPDF=\(self.isShowingPDF) loadingHidden=\(self.loadingOverlay.isHidden) hit=\(self.describeHitView(hit)) inPDF=\(inPDF) selLen=\(sel.length) selPages=\(sel.pages) chain=\(chainText(from: hit))")
                return event
            }
        }

        if pdfSelectDragMonitor == nil {
            pdfSelectDragMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseDragged) { [weak self] event in
                guard let self else { return event }
                guard let root = self.window?.contentView else { return event }
                let hit = root.hitTest(event.locationInWindow)
                let inPDF = (hit != nil) ? (hit!.isDescendant(of: self.pdfView) || hit === self.pdfView) : false
                let sel = snapshotSelection()
                self.pdfSelectLog("drag loc=\(String(format: "%.1f", event.locationInWindow.x)),\(String(format: "%.1f", event.locationInWindow.y)) hit=\(self.describeHitView(hit)) inPDF=\(inPDF) selLen=\(sel.length)")
                return event
            }
        }

        if pdfSelectUpMonitor == nil {
            pdfSelectUpMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseUp) { [weak self] event in
                guard let self else { return event }
                guard let root = self.window?.contentView else { return event }
                let hit = root.hitTest(event.locationInWindow)
                let inPDF = (hit != nil) ? (hit!.isDescendant(of: self.pdfView) || hit === self.pdfView) : false
                let sel = snapshotSelection()
                self.pdfSelectLog("up loc=\(String(format: "%.1f", event.locationInWindow.x)),\(String(format: "%.1f", event.locationInWindow.y)) hit=\(self.describeHitView(hit)) inPDF=\(inPDF) selLen=\(sel.length) selPages=\(sel.pages)")
                return event
            }
        }
    }

	    private func setupUI() {
        launchLog("setupUI start")
	        guard let content = window?.contentView else {
                launchLog("setupUI abort: window contentView nil")
                return
            }

            let root = installGlassContainerIfAvailable(on: content)
            layoutDebugRootView = root
            if debugLayoutEnabled, layoutDebugOverlay == nil {
                let overlay = DebugLayoutOverlayView(frame: root.bounds)
                overlay.translatesAutoresizingMaskIntoConstraints = true
                overlay.autoresizingMask = [.width, .height]
                root.addSubview(overlay, positioned: .above, relativeTo: nil)
                layoutDebugOverlay = overlay
            }
            installLayoutDebugEventTracing()

	        setupWindowBackgroundImage(in: content)
	        setupWindowBackgroundMaterial(in: content)
        restoreSidebarStateFromDefaults()

	        searchField.delegate = self
	        searchField.target = self
	        searchField.action = #selector(searchChanged)
	        searchField.translatesAutoresizingMaskIntoConstraints = false
	        searchField.controlSize = .large
	        searchField.wantsLayer = false
	        searchField.refusesFirstResponder = false
	        searchField.setContentHuggingPriority(.defaultLow, for: .horizontal)
	        searchField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

	        // Match the PDF find bar typography (same font + metrics) while keeping the main search colors.
            let searchForeground = mainSearchForegroundColor()
	        applySearchFieldTheme(searchField,
	                              placeholder: "Search",
	                              textColor: searchForeground,
	                              placeholderColor: searchForeground,
	                              iconColor: searchForeground)

	        let searchTheme = currentSearchBarTheme()
		        searchBackground = makeGlassEffectView(
		            passthrough: true,
		            cornerRadius: 14,
		            tintColor: nil,
	            style: .regular,
	            fallbackMaterial: searchTheme.fallbackMaterial,
	            fallbackBlending: searchTheme.fallbackBlending,
	            fallbackState: searchTheme.fallbackState,
	            emphasized: searchTheme.emphasized
	        )
	        applyEmbeddedSearchBarTheme(to: searchBackground)
	        searchBackground.postsFrameChangedNotifications = true
	        searchOutlineLayer.fillColor = NSColor.clear.cgColor
	        searchOutlineLayer.strokeColor = NSColor.white.withAlphaComponent(0.09).cgColor
	        searchOutlineLayer.lineWidth = SPOTLIGHT_SEARCH_OUTLINE_WIDTH
	        searchOutlineLayer.lineJoin = .round
	        searchOutlineLayer.lineCap = .round
	        searchOutlineLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
	        searchInnerOutlineLayer.fillColor = NSColor.clear.cgColor
	        searchInnerOutlineLayer.strokeColor = NSColor.white.withAlphaComponent(0.06).cgColor
	        searchInnerOutlineLayer.lineWidth = SPOTLIGHT_SEARCH_OUTLINE_WIDTH
	        searchInnerOutlineLayer.lineJoin = .round
	        searchInnerOutlineLayer.lineCap = .round
	        searchInnerOutlineLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
	        if #available(macOS 10.14, *) {
	            searchCenterGlowLayer.type = .radial
	        }
	        searchCenterGlowLayer.startPoint = CGPoint(x: 0.5, y: 0.5)
	        searchCenterGlowLayer.endPoint = CGPoint(x: 1.0, y: 1.0)
	        searchCenterGlowLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
	        searchHighlightLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
	        searchFalloffLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
	        searchHighlightLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
	        searchHighlightLayer.endPoint = CGPoint(x: 0.5, y: 0.0)
	        searchFalloffLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
	        searchFalloffLayer.endPoint = CGPoint(x: 0.5, y: 0.0)
	        searchBackground.layer?.addSublayer(searchCenterGlowLayer)
	        searchBackground.layer?.addSublayer(searchHighlightLayer)
		        searchBackground.layer?.addSublayer(searchFalloffLayer)
			        searchBackground.layer?.addSublayer(searchInnerOutlineLayer)
			        searchBackground.layer?.addSublayer(searchOutlineLayer)
			        searchBackground.layer?.mask = searchMaskLayer

		        setupToolbarControls()
		        setupSuggestionsDropdown()
		        setupMenuPanel()
		        updateToolbarEmphasis()

        splitView.isVertical = true
        splitView.dividerStyle = .thin
        splitView.gap = PANEL_INTER_CARD_GAP
        splitView.translatesAutoresizingMaskIntoConstraints = false

        // Keep divider draggable, and remove “hard line” look
        splitView.setValue(NSColor.clear, forKey: "dividerColor")
        splitView.delegate = self

        setupLeftPanelChrome()
        setupTable()
        setupPageStepper()
        setupRightPanelChrome()
        setupRightCompositeContainer()
            setupRightAuxPanelChrome()
            setupRightSplitContainer()

        leftHeaderBar.translatesAutoresizingMaskIntoConstraints = true
        leftHeaderRule.translatesAutoresizingMaskIntoConstraints = true
        tableScroll.translatesAutoresizingMaskIntoConstraints = true

	        leftContentView.addSubview(leftHeaderBar)
	        leftContentView.addSubview(leftHeaderRule)
	        leftContentView.addSubview(tableScroll)
            leftContentView.addSubview(pageStepperContainer)
	        setupLeftTableUnderlay()

            splitView.addArrangedSubview(leftContainer)
            splitView.addArrangedSubview(rightSplitContainer)

            // Ensure the viewer pane stays meaningfully sized.
            // Without explicit priorities, a bad persisted width or intrinsic sizing can cause the left
            // pane to dominate and make the divider feel "stuck".
            splitView.setHoldingPriority(.defaultLow, forSubviewAt: 0)
            splitView.setHoldingPriority(.defaultHigh, forSubviewAt: 1)
            leftContainer.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
            rightSplitContainer.setContentCompressionResistancePriority(.defaultHigh, for: .horizontal)

	        searchContainer.translatesAutoresizingMaskIntoConstraints = true
	        searchContainer.wantsLayer = true
	        searchContainer.layer?.backgroundColor = NSColor.clear.cgColor
	        searchContainerClipLayer.fillColor = NSColor.white.cgColor
	        searchContainer.layer?.mask = searchContainerClipLayer
        searchContainer.focusTarget = searchField
	        searchContainer.addSubview(searchBackground) // background first
	        searchContainer.addSubview(searchContentView)

	        searchContentView.translatesAutoresizingMaskIntoConstraints = false
	        searchContentView.wantsLayer = false
        searchContentView.addSubview(searchField)

        headerControlsContainer.translatesAutoresizingMaskIntoConstraints = true
        headerControlsContainer.wantsLayer = false
        headerControlsContainer.addSubview(toolbarControls)

        root.addSubview(splitView)
        setupSplitDividerHandle(in: root)
            setupRightSplitDividerHandle(in: root)
        root.addSubview(searchContainer, positioned: .above, relativeTo: splitView)
        root.addSubview(headerControlsContainer, positioned: .above, relativeTo: searchContainer)
        if let leftGlass = rightPanelLeftEdgeButtonBackground {
            root.addSubview(leftGlass)
        }
        if let zoteroGlass = rightPanelZoteroEdgeButtonBackground {
            root.addSubview(zoteroGlass)
        }
        if let rightGlass = rightPanelRightEdgeButtonBackground {
            root.addSubview(rightGlass)
        }
        if let settingsGlass = rightPanelSettingsEdgeButtonBackground {
            root.addSubview(settingsGlass)
        }
        root.addSubview(rightPanelLeftEdgeButton)
        root.addSubview(rightPanelZoteroEdgeButton)
        root.addSubview(rightPanelRightEdgeButton)
        root.addSubview(rightPanelSettingsEdgeButton)

        rightPanelPillControl.onExpansionStateChanged = { [weak self] _ in
            // Keep the pill tab centered on the viewer after every expand/collapse cycle.
            // Defer to the next runloop tick so we don't fight in-flight CoreAnimation commits.
            DispatchQueue.main.async { [weak self] in
                self?.layoutViewerAnchoredHeaderControls()
            }
            // Also re-center after the morph animation fully settles; the bounce preset can drift
            // slightly while its transform scales, so schedule a second layout after the animation
            // duration has elapsed.
            DispatchQueue.main.asyncAfter(deadline: .now() + ((self?.rightPanelPillControl.pathAnimationDuration ?? 0.5) + 0.05)) { [weak self] in
                self?.layoutViewerAnchoredHeaderControls()
            }
        }

        root.addSubview(rightPanelPillControl, positioned: .above, relativeTo: headerControlsContainer)
        root.addSubview(menuShield, positioned: .above, relativeTo: headerControlsContainer)
        root.addSubview(menuContainer, positioned: .above, relativeTo: menuShield)
        root.addSubview(suggestionsContainer, positioned: .above, relativeTo: nil)
        if let layer = suggestionsContainer.layer {
            layer.zPosition = 10_000
        }
	        setupLeftCardBackgroundImage(in: root, below: splitView)
	        setupRightCardBackgroundImage(in: root, below: splitView)
	        setupLeftCardEdgeGlow(in: root, below: splitView)
	        // Right-card edge glow is purely decorative and can appear as an unintended underlay under some tints.
	        // Keep it disabled to avoid any “ghost layer” behind the right glass card.
        installHitTestDebugging(in: root)
        installPDFSelectionDebuggingIfNeeded()
        updateLayoutDebugOverlay(reason: "setup")

	        logSearchDebug("searchField placeholder=\(searchField.placeholderString ?? "") textColor=\(String(describing: searchField.textColor)) wantsLayer=\(searchField.wantsLayer)")
	        if let cell = searchField.cell as? NSSearchFieldCell {
	            logSearchDebug("searchField cell placeholder=\(cell.placeholderAttributedString?.string ?? "") icon=\(String(describing: cell.searchButtonCell?.image))")
	        }

        let searchMinWidth = searchField.widthAnchor.constraint(greaterThanOrEqualToConstant: searchFieldMinimumWidth)
        searchMinWidth.priority = .defaultLow

	        NSLayoutConstraint.activate([
	            searchBackground.leadingAnchor.constraint(equalTo: searchContainer.leadingAnchor),
	            searchBackground.trailingAnchor.constraint(equalTo: searchContainer.trailingAnchor),
	            searchBackground.topAnchor.constraint(equalTo: searchContainer.topAnchor),
	            searchBackground.bottomAnchor.constraint(equalTo: searchContainer.bottomAnchor),

	            searchContentView.leadingAnchor.constraint(equalTo: searchContainer.leadingAnchor, constant: searchContentInsetX),
	            searchContentView.trailingAnchor.constraint(equalTo: searchContainer.trailingAnchor, constant: -searchContentInsetX),
	            searchContentView.topAnchor.constraint(equalTo: searchContainer.topAnchor, constant: searchContentInsetY),
	            searchContentView.bottomAnchor.constraint(equalTo: searchContainer.bottomAnchor, constant: -searchContentInsetY),

            toolbarControls.leadingAnchor.constraint(equalTo: headerControlsContainer.leadingAnchor),
            toolbarControls.trailingAnchor.constraint(equalTo: headerControlsContainer.trailingAnchor),
            toolbarControls.topAnchor.constraint(equalTo: headerControlsContainer.topAnchor),
            toolbarControls.bottomAnchor.constraint(equalTo: headerControlsContainer.bottomAnchor),

            searchField.centerYAnchor.constraint(equalTo: searchContentView.centerYAnchor),
            searchField.leadingAnchor.constraint(equalTo: searchContentView.leadingAnchor),
            searchField.trailingAnchor.constraint(equalTo: searchContentView.trailingAnchor),
            searchField.heightAnchor.constraint(equalToConstant: 28),
            searchMinWidth,

            splitView.topAnchor.constraint(equalTo: root.topAnchor,
                                           constant: searchContainerTopInset + searchContainerHeight + searchContainerGap),
            splitView.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: WINDOW_BEZEL_INSET),
            splitView.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -WINDOW_BEZEL_INSET),
            splitView.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -WINDOW_BEZEL_INSET),
        ])

	        windowResizeObserver = NotificationCenter.default.addObserver(
	            forName: NSWindow.didResizeNotification,
	            object: window,
	            queue: .main
	        ) { [weak self] _ in
	            self?.installTitlebarTintBackground()
	            self?.scheduleRootGlassTintApply(reason: "window_resize", delay: 0.12)
            self?.updateToolbarScaleForWindowSize(reason: "window_resize")
            self?.layoutLeftContainerSubviews()
            self?.layoutRightPanelSubviews()
            self?.updateSplitDividerHandleFrame()
            self?.reflowLeft()
            if self?.isShowingPDF == false { self?.updateDetails() }
            self?.nudgePanelForResize()
            self?.refreshVisibleRowDepth(animated: true)
            self?.updateSearchCapsuleGeometry()
            self?.updateSearchDepth(animated: true)
            self?.layoutToolbarControls()
            self?.enforceSidebarWidthBounds(reason: "window_resize")
                self?.updateLayoutDebugOverlay(reason: "window_resize")
                self?.updateRightSplitDividerHandleFrame()
        }

        windowScreenObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.didChangeScreenNotification,
            object: window,
            queue: .main
        ) { [weak self] _ in
            self?.updateLeftCardBackgroundFrame()
            self?.updateRightCardBackgroundFrame()
            self?.updateWindowBackgroundBackingScale()
        }

        splitWillResizeObserver = NotificationCenter.default.addObserver(
            forName: NSSplitView.willResizeSubviewsNotification,
            object: splitView,
            queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            // Detect native split-view dragging (when the user drags the divider itself).
            // Our custom `SplitDividerHandleView` sets `dividerDragActive` explicitly, but
            // AppKit-driven divider drags otherwise look like ordinary resize notifications.
            if !self.dividerDragActive,
               !self.sidebarTransitionInProgress,
               (NSEvent.pressedMouseButtons & 1) != 0,
               let window = self.window,
               let dividerRect = self.dividerRectInWindow(),
               dividerRect.contains(window.mouseLocationOutsideOfEventStream) {
                self.cancelSplitDividerSpringAnimation()
                self.dividerDragActive = true
                self.systemDividerDragStartX = window.mouseLocationOutsideOfEventStream.x
                self.systemDividerDragStartLeftWidth = self.leftContainer.frame.width
                self.systemDividerDragPendingSplitModeExit = self.rightPanelSplitModeActive
                self.logDividerState("drag_begin_system")
                layoutLog("drag_begin_system left=\(Int(self.leftContainer.frame.width)) right=\(Int(self.rightSplitContainer.frame.width))")
                self.updateLayoutDebugOverlay(reason: "drag_begin_system")
            }

            if self.uiDebugEnabled, self.dividerDragActive {
                self.logDividerState("drag_will_resize")
            }
                if debugLayoutEnabled {
                    self.updateLayoutDebugOverlay(reason: self.dividerDragActive ? "drag_will_resize" : "split_will_resize")
                }
        }

        splitResizeObserver = NotificationCenter.default.addObserver(
            forName: NSSplitView.didResizeSubviewsNotification,
            object: splitView,
            queue: .main
        ) { [weak self] _ in
            // During live divider drags, do the minimum work possible.
            // Constraint/layout churn here can fight AppKit’s interactive divider updates and
            // make dragging feel “stuck” (especially with nested split views + glass cards).
	            if let self {
                // Apply toolbar scaling for divider changes as well.
                self.updateToolbarScaleForWindowSize(reason: self.dividerDragActive ? "split_divider_drag" : "split_resize")
            }
	            if let self, self.dividerDragActive {
                self.updateSplitDividerHandleFrame()
                self.updateRightSplitDividerHandleFrame()
                self.layoutLeftContainerSubviews(duringDividerDrag: true)
                self.logDividerState("drag_update")

                // Avoid a visual snap on mere mouse-down: only exit split-mode
                // once the user has actually moved the pointer.
                if self.systemDividerDragPendingSplitModeExit,
                   let window = self.window {
                    let dx = window.mouseLocationOutsideOfEventStream.x - self.systemDividerDragStartX
                    let dLeft = self.leftContainer.frame.width - self.systemDividerDragStartLeftWidth
                    if abs(dx) >= 2 || abs(dLeft) >= 1 {
                        self.systemDividerDragPendingSplitModeExit = false
                        if self.rightPanelSplitModeActive {
                            layoutLog("drag_exit_right_split_mode dx=\(Int(dx)) dLeft=\(Int(dLeft))")
                            self.setRightPanelSplitMode(false, animated: false)
                            self.updateLayoutDebugOverlay(reason: "drag_exit_right_split_mode")
                        }
                    }
                }

                // End native drag when the mouse is released.
                if (NSEvent.pressedMouseButtons & 1) == 0 {
                    self.dividerDragActive = false
                    self.systemDividerDragPendingSplitModeExit = false
                    self.logDividerState("drag_end_system")
                    layoutLog("drag_end_system left=\(Int(self.leftContainer.frame.width)) right=\(Int(self.rightSplitContainer.frame.width))")
                    self.schedulePanelSettle()
                    self.enforceSidebarWidthBounds(reason: "drag_end")
                    self.debugDumpViewHierarchy(reason: "divider_drag_end")
                    self.debugProbeDividerHitTest(reason: "divider_drag_end")
                    self.updateLayoutDebugOverlay(reason: "drag_end_system")
                }
                return
            }

            self?.scheduleRootGlassTintApply(reason: "split_resize", delay: 0.12)
            self?.layoutLeftContainerSubviews()
            self?.layoutRightPanelSubviews()
            self?.reflowLeft()
            if self?.isShowingPDF == false { self?.updateDetails() }
            self?.nudgePanelForResize()
            self?.updateSearchCapsuleGeometry()
            self?.updateSearchDepth(animated: true)
            self?.enforceSidebarWidthBounds(reason: "split_resize")
            self?.updateSidebarStateFromSplit()
            self?.updateSplitDividerHandleFrame()
            self?.updateRightSplitDividerHandleFrame()
                if debugLayoutEnabled {
                    self?.updateLayoutDebugOverlay(reason: "split_resize")
                }
        }

            rightSplitWillResizeObserver = NotificationCenter.default.addObserver(
                forName: NSSplitView.willResizeSubviewsNotification,
                object: rightSplitView,
                queue: .main
            ) { [weak self] _ in
                guard let self else { return }
                if self.uiDebugEnabled {
                    self.uiLog("right_divider_will_resize")
                }
                // The system warning "NSLayoutConstraintNumberExceedsLimit" often means AppKit
                // has clamped a constraint constant. Sample constraint constants right here while
                // the layout engine is active so we can attribute the offending constraint.
                self.launchAuditConstraintConstants(reason: "right_divider_will_resize", threshold: 10_000)
            }

            rightSplitResizeObserver = NotificationCenter.default.addObserver(
                forName: NSSplitView.didResizeSubviewsNotification,
                object: rightSplitView,
                queue: .main
            ) { [weak self] _ in
                guard let self else { return }
                self.updateToolbarScaleForWindowSize(reason: "right_split_resize")
                self.scheduleRootGlassTintApply(reason: "right_split_resize", delay: 0.12)
                self.layoutRightPanelSubviews()
                self.layoutViewerAnchoredHeaderControls()
                self.updateRightSplitDividerHandleFrame()
                if self.rightAuxPanelVisible {
                    self.lastRightAuxPanelWidth = self.rightAuxPanelWidth()
                }
            }

        windowFocusObservers.append(
            NotificationCenter.default.addObserver(
                forName: NSWindow.didBecomeKeyNotification,
                object: window,
                queue: .main
            ) { [weak self] _ in
                self?.updateLeftPanelDepth(animated: true, reason: .focus)
                self?.refreshVisibleRowDepth(animated: true)
                self?.updateVisibleRowSelectionStyling()
                self?.updateCardEdgeGlowIntensity()
                self?.updateToolbarEmphasis()
                self?.refreshMenuTextColors()
            }
        )

        windowFocusObservers.append(
            NotificationCenter.default.addObserver(
                forName: NSWindow.didResignKeyNotification,
                object: window,
                queue: .main
            ) { [weak self] _ in
                self?.updateLeftPanelDepth(animated: true, reason: .focus)
                self?.refreshVisibleRowDepth(animated: true)
                self?.updateVisibleRowSelectionStyling()
                self?.updateCardEdgeGlowIntensity()
                self?.updateToolbarEmphasis()
                self?.refreshMenuTextColors()
            }
        )

        windowLiveResizeEndObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.didEndLiveResizeNotification,
            object: window,
            queue: .main
        ) { [weak self] _ in
            self?.scheduleRootGlassTintApply(reason: "live_resize_end", delay: 0.0)
            self?.updateToolbarScaleForWindowSize(reason: "live_resize_end")
            self?.schedulePanelSettle()
        }

        func applyInitialLayoutWhenReady(attempt: Int) {
            // Avoid applying split positions before AppKit has produced real frames.
            // When done too early, the right panel can end up effectively 0-sized until a later interaction.
            let boundsReady = self.splitView.bounds.width > 80 && self.splitView.bounds.height > 80
            if !boundsReady {
                if attempt < 12 {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.04) {
                        applyInitialLayoutWhenReady(attempt: attempt + 1)
                    }
                }
                return
            }

            // On some runs a previously persisted sidebar width can be wildly too large (e.g. from a prior
            // regression). If we apply it verbatim, the viewer panel launches effectively "closed".
            // For initial layout, keep a more comfortable minimum for the viewer.
            let total = self.splitView.bounds.width
            let divider = self.splitView.dividerThickness
            let minRightComfort = max(self.minOuterRightContainerWidth(), self.minRightPanelWidth * 2)
            let maxLeft = self.cappedSidebarMaxWidth(forPotential: total - divider - minRightComfort)

            // Always launch with the left panel visible.
            // Bootstrap with a conservative width (so the table can compute row/pagination metrics),
            // then tighten to a content-fit width (Author&Year + 2 keywords).
            self.sidebarVisible = true
            let bootstrapLeft = min(maxLeft, max(self.minSidebarWidth, maxLeft * INITIAL_SIDEBAR_WIDTH_FRACTION_OF_MAX))
            self.splitView.setPosition(bootstrapLeft, ofDividerAt: 0)
            self.splitView.adjustSubviews()

            self.layoutLeftContainerSubviews()
            self.layoutRightPanelSubviews()
            self.updateSplitDividerHandleFrame()

            // Ensure the Chat Session (right aux) panel truly starts hidden on first launch:
            // keep it collapsed to ~0 width (not just transparent).
            self.rightAuxPanelVisible = false
            self.rightAuxContainer.alphaValue = 0
            self.ensureRightAuxCollapsedIfHidden()
            // One extra tick helps when nested split bounds finalize slightly later.
            DispatchQueue.main.async { [weak self] in
                self?.ensureRightAuxCollapsedIfHidden()
            }
            self.reflowLeft()

            let contentFitLeft = self.desiredLaunchSidebarWidth(maxLeft: maxLeft)
            if abs(contentFitLeft - self.leftContainer.frame.width) >= 0.5 {
                self.splitView.setPosition(contentFitLeft, ofDividerAt: 0)
                self.splitView.adjustSubviews()
                self.layoutLeftContainerSubviews()
                self.layoutRightPanelSubviews()
                self.updateSplitDividerHandleFrame()
                self.reflowLeft()
            }
            self.updateLeftPanelDepth(animated: false)
            self.refreshVisibleRowDepth(animated: false, preset: .crisp)
            self.updateSearchCapsuleGeometry()
            self.updateSearchDepth(animated: false)
            self.updateCardEdgeGlowIntensity()
            self.layoutToolbarControls()
            self.updateToolbarScaleForWindowSize(reason: "initial", immediate: true)
                self.enforceSidebarWidthBounds(reason: "initial")
                self.didApplyInitialSidebarLayout = true
            self.updateSidebarStateFromSplit()
            self.updateNavigationButtons()
                self.updateLayoutDebugOverlay(reason: "initial")
            self.debugDumpViewHierarchy(reason: "initial")
            self.debugProbeDividerHitTest(reason: "initial")
            self.debugProbeToolbarHitTests(reason: "initial")
            self.debugProbeViewerHitTest(reason: "initial")
            self.launchAuditConstraintConstants(reason: "initial", threshold: 10_000)
        }

        DispatchQueue.main.async {
            applyInitialLayoutWhenReady(attempt: 0)
        }

        // Optional: smoke-test the Chat panel mount/unmount on launch.
        // Enable with `ARXIV_CHAT_SMOKE=1`.
        if ProcessInfo.processInfo.environment["ARXIV_CHAT_SMOKE"] == "1" {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
                self?.setRightAuxPanelVisible(true, animated: false)
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.1) { [weak self] in
                self?.setRightAuxPanelVisible(false, animated: false)
            }
        }

        // Optional: rapid toggle stress (layout stability + no perceived lag under repeated clicks).
        // Enable with `ARXIV_CHAT_STRESS=1`.
        runChatRapidToggleStressIfEnabled()

        setupKeyHandling()
        setupPDFWheelRouting()
        setupSelectionClearMonitor()
        setupDividerDragEndMonitor()
        launchLog("setupUI end")
    }

    private func setupPDFWheelRouting() {
        guard pdfWheelMonitor == nil else { return }
        pdfWheelMonitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { [weak self] event in
            guard let self else { return event }
            guard self.window?.isKeyWindow == true else { return event }
            guard self.isShowingPDF, self.pdfView.isHidden == false else { return event }
            guard event.window === self.window else { return event }

            // Avoid intercepting modifier-driven scroll gestures (e.g. Cmd-scroll zoom).
            if event.modifierFlags.contains(.command) { return event }

            let p = self.pdfView.convert(event.locationInWindow, from: nil)
            guard self.pdfView.bounds.contains(p) else { return event }

            if self.pdfView.routeScrollWheel(event) {
                return nil
            }
            return event
        }
    }

	    private func setupLeftPanelChrome() {
	        // GlassCardKit: match the dropdown liquid glass effect across panels.
        var cardConfig = baseLiquidGlassConfig()
        cardConfig.cornerRadius = PANEL_CORNER_RADIUS
        // Keep the panel as clear, white glass so content appears over a neutral backdrop.
        cardConfig.tint = panelClearGlassTintColor()
        let card = GlassCardKit.makeGlassCard(config: cardConfig) { [weak self] rectInWindow, scale in
            self?.captureWindowBackgroundRegion(in: rectInWindow, scale: scale)
        }
	        leftContainer = card
            // The outer split view uses `addArrangedSubview`, so its panes must participate in Auto Layout.
            // Keeping autoresizing-mask translation enabled can cause AppKit to synthesize placeholder
            // constraints that fight divider dragging (observed as “stuck” drags).
            leftContainer.translatesAutoresizingMaskIntoConstraints = false
	        leftContainer.wantsLayer = true
	        leftContainer.layer?.cornerRadius = PANEL_CORNER_RADIUS
	        leftContainer.layer?.backgroundColor = NSColor.clear.cgColor
	        leftContainer.layer?.masksToBounds = true
	        embedContentView(leftContentView, into: leftContainer)

        // Share-style black/glassy border ornaments for the left glass card.
        leftCardOrnamentOverlay.cornerRadius = PANEL_CORNER_RADIUS
        leftCardOrnamentOverlay.frame = leftContainer.bounds
        leftCardOrnamentOverlay.autoresizingMask = [.width, .height]
        leftCardOrnamentOverlay.translatesAutoresizingMaskIntoConstraints = true
        if leftCardOrnamentOverlay.superview == nil {
            leftContainer.addSubview(leftCardOrnamentOverlay, positioned: .above, relativeTo: leftContentView)
        }
	    }

    private func runChatRapidToggleStressIfEnabled() {
        guard ProcessInfo.processInfo.environment["ARXIV_CHAT_STRESS"] == "1" else { return }

        let env = ProcessInfo.processInfo.environment
        let cycles = max(1, Int(env["ARXIV_CHAT_STRESS_CYCLES"] ?? "14") ?? 14)
        let interval = max(0.02, Double(env["ARXIV_CHAT_STRESS_INTERVAL"] ?? "0.06") ?? 0.06)
        let startDelay = max(0.2, Double(env["ARXIV_CHAT_STRESS_DELAY"] ?? "0.9") ?? 0.9)
        let animated = (env["ARXIV_CHAT_STRESS_ANIMATED"] ?? "1") != "0"

        chatStressToken &+= 1
        let token = chatStressToken
        uiLog("chat_stress_start cycles=\(cycles) interval=\(String(format: "%.3f", interval)) delay=\(String(format: "%.2f", startDelay)) animated=\(animated)")

        DispatchQueue.main.asyncAfter(deadline: .now() + startDelay) { [weak self] in
            guard let self, token == self.chatStressToken else { return }

            func assertInvariant(_ label: String) {
                // 1) Visible flag implies aux view is fully opaque.
                if self.rightAuxPanelVisible && self.rightAuxContainer.alphaValue < 0.95 {
                    self.uiLog("chat_stress_invariant_fail \(label) visible=true alpha=\(String(format: "%.2f", self.rightAuxContainer.alphaValue))")
                }
                // 2) Not visible implies we keep it collapsed and fully transparent.
                if !self.rightAuxPanelVisible && self.rightAuxContainer.alphaValue > 0.05 {
                    self.uiLog("chat_stress_invariant_fail \(label) visible=false alpha=\(String(format: "%.2f", self.rightAuxContainer.alphaValue))")
                }
                if !self.rightAuxPanelVisible {
                    let auxW = Int(self.rightAuxPanelWidth())
                    if auxW > 2 {
                        self.uiLog("chat_stress_invariant_warn \(label) auxWidth=\(auxW) expected~0")
                    }
                }
            }

            var i = 0
            func step() {
                guard token == self.chatStressToken else { return }
                if i >= cycles {
                    assertInvariant("done")
                    self.launchAuditConstraintConstants(reason: "chat_stress_done", threshold: 10_000)
                    self.uiLog("chat_stress_done")
                    return
                }

                let opening = (i % 2 == 0)
                ChatLatencyProbe.shared.markButtonAction(opening: opening)
                self.setRightAuxPanelVisible(opening, animated: animated)
                assertInvariant("step_\(i)")
                i += 1
                DispatchQueue.main.asyncAfter(deadline: .now() + interval) {
                    step()
                }
            }

            step()
        }
    }

    private func recordRightPanelWidthIfNeeded() {
        guard !rightPanelSplitModeActive, sidebarVisible else { return }
        let width = rightContainer.frame.width
        if width > 0 { lastRightPanelWidth = width }
    }

    private func targetRightPanelWidthForSplit() -> CGFloat {
        let total = rightCompositeContainer.bounds.width
        let fallback = max(minRightPanelWidth, total > 1 ? total * 0.6 : minRightPanelWidth)
        let stored = lastRightPanelWidth > 0 ? lastRightPanelWidth : fallback
        let maxPrimary = max(minRightPanelWidth, total - 1)
        return min(max(stored, minRightPanelWidth), maxPrimary)
    }

    private func clampRightPanelWidthForSplit() {
        guard rightPanelSplitModeActive,
              let constraint = rightPrimaryWidthConstraint,
              constraint.isActive else { return }
        let maxPrimary = max(minRightPanelWidth, rightCompositeContainer.bounds.width - 1)
        if constraint.constant > maxPrimary {
            constraint.constant = maxPrimary
            rightCompositeContainer.layoutSubtreeIfNeeded()
        }
    }

    private func setRightPanelSplitMode(_ active: Bool, animated: Bool, preset: SpringPreset = .soft) {
        guard let secondary = rightSecondaryContainer,
              rightPanelSplitModeActive != active else { return }

        layoutLog("right_splitmode_toggle active=\(active) before primaryW=\(Int(rightContainer.frame.width)) secondaryW=\(Int(secondary.frame.width)) secondaryHidden=\(secondary.isHidden)")

        rightPanelSplitModeActive = active
        let reduce = shouldReduceMotion || !animated

        if active {
            recordRightPanelWidthIfNeeded()
            secondary.isHidden = false
            rightPrimaryTrailingConstraint?.isActive = false
            rightPrimaryWidthConstraint?.constant = targetRightPanelWidthForSplit()
            rightPrimaryWidthConstraint?.isActive = true
            rightSecondaryWidthConstraint?.isActive = false
            rightSecondaryLeadingConstraint?.isActive = true
            rightCompositeContainer.layoutSubtreeIfNeeded()

            secondary.invalidateGlass(reason: "right_secondary_show")
            if let layer = secondary.layer {
                if reduce {
                    CATransaction.begin()
                    CATransaction.setDisableActions(true)
                    layer.opacity = 1
                    layer.transform = CATransform3DIdentity
                    CATransaction.commit()
                } else {
                    CATransaction.begin()
                    CATransaction.setDisableActions(true)
                    layer.opacity = 0
                    layer.transform = CATransform3DMakeScale(0.98, 0.98, 1.0)
                    CATransaction.commit()
                    animateLayer(layer, keyPath: "opacity", to: 1, preset: preset, reduceMotion: false, basicDuration: 0.22)
                    animateLayer(layer, keyPath: "transform", to: CATransform3DIdentity, preset: preset, reduceMotion: false, basicDuration: 0.26)
                }
            }
        } else {
            rightPrimaryTrailingConstraint?.isActive = true
            rightPrimaryWidthConstraint?.isActive = false
            rightSecondaryLeadingConstraint?.isActive = false
            rightSecondaryWidthConstraint?.isActive = true
            rightCompositeContainer.layoutSubtreeIfNeeded()

            guard let layer = secondary.layer else {
                secondary.isHidden = true
                return
            }
            if reduce {
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                layer.opacity = 1
                layer.transform = CATransform3DIdentity
                CATransaction.commit()
                secondary.isHidden = true
            } else {
                animateLayer(layer, keyPath: "opacity", to: 0, preset: preset, reduceMotion: false, basicDuration: 0.18)
                let shrink = CATransform3DMakeScale(0.98, 0.98, 1.0)
                animateLayer(layer, keyPath: "transform", to: shrink, preset: preset, reduceMotion: false, basicDuration: 0.22)
                let duration = springSpec(for: preset).settleCap
                DispatchQueue.main.asyncAfter(deadline: .now() + duration) {
                    secondary.isHidden = true
                    CATransaction.begin()
                    CATransaction.setDisableActions(true)
                    layer.opacity = 1
                    layer.transform = CATransform3DIdentity
                    CATransaction.commit()
                }
            }
        }
        layoutRightPanelSubviews()

        layoutLog("right_splitmode_done active=\(rightPanelSplitModeActive) after primaryW=\(Int(rightContainer.frame.width)) secondaryW=\(Int(secondary.frame.width)) secondaryHidden=\(secondary.isHidden)")
    }

    // MARK: Split view sizing

    private func minOuterRightContainerWidth() -> CGFloat {
        // Outer split view's right side must be wide enough for the HTML/PDF panel,
        // plus the third panel (and its divider) when it is open.
        if rightAuxPanelVisible {
            return minRightPanelWidth + rightSplitView.dividerThickness + minRightAuxPanelWidth
        }
        return minRightPanelWidth
    }

    private func cappedSidebarMaxWidth(forPotential potential: CGFloat) -> CGFloat {
        guard potential.isFinite else { return 0 }
        return max(0, potential * maxSidebarWidthFraction)
    }

    private func clampSidebarWidth(_ proposedPosition: CGFloat) -> CGFloat {
        let total = splitView.bounds.width
        let divider = splitView.dividerThickness
        let maxLeftPotential = total - divider - minOuterRightContainerWidth()
        let maxLeft = cappedSidebarMaxWidth(forPotential: maxLeftPotential)
        let minLeft = min(minSidebarWidth, maxLeft)
        if allowSidebarCollapse {
            return max(0, min(proposedPosition, maxLeft))
        }
        return min(max(proposedPosition, minLeft), maxLeft)
    }

    func splitView(_ splitView: NSSplitView,
                   constrainSplitPosition proposedPosition: CGFloat,
                   ofSubviewAt dividerIndex: Int) -> CGFloat {
        if splitView === self.splitView {
            return clampSidebarWidth(proposedPosition)
        }
        if splitView === rightSplitView {
            return clampRightAuxDividerPosition(proposedPosition)
        }
        return proposedPosition
    }

    func splitView(_ splitView: NSSplitView,
                   constrainMaxCoordinate proposedMax: CGFloat,
                   ofSubviewAt dividerIndex: Int) -> CGFloat {
        // `constrainSplitPosition` is used primarily for user-driven divider drags.
        // During window resizes / AppKit layout passes, the split view can temporarily
        // try to squeeze the right pane to an infeasible width (observed as right≈20px).
        // Constrain the divider coordinate here so the right viewer stays open.
        if splitView === self.splitView, dividerIndex == 0 {
            let total = splitView.bounds.width
            let divider = splitView.dividerThickness
            let maxLeft = cappedSidebarMaxWidth(forPotential: total - divider - minOuterRightContainerWidth())
            return min(proposedMax, maxLeft)
        }
        if splitView === rightSplitView, dividerIndex == 0 {
            return min(proposedMax, clampRightAuxDividerPosition(proposedMax))
        }
        return proposedMax
    }

    func splitView(_ splitView: NSSplitView,
                   constrainMinCoordinate proposedMin: CGFloat,
                   ofSubviewAt dividerIndex: Int) -> CGFloat {
        if splitView === self.splitView, dividerIndex == 0 {
            let total = splitView.bounds.width
            let divider = splitView.dividerThickness
            let maxLeft = cappedSidebarMaxWidth(forPotential: total - divider - minOuterRightContainerWidth())
            if allowSidebarCollapse || !sidebarVisible {
                return max(0, min(proposedMin, maxLeft))
            }
            let minLeft = min(minSidebarWidth, maxLeft)
            return min(max(proposedMin, minLeft), maxLeft)
        }
        if splitView === rightSplitView, dividerIndex == 0 {
            return max(0, clampRightAuxDividerPosition(proposedMin))
        }
        return proposedMin
    }

    func splitView(_ splitView: NSSplitView, canCollapseSubview subview: NSView) -> Bool {
        if splitView === self.splitView {
            // Needed so AppKit permits a fully collapsed sidebar width.
            return subview === leftContainer
        }
        if splitView === rightSplitView {
            return subview === rightAuxContainer
        }
        return false
    }

    private enum PanelMotionReason { case focus, resize, settle }
    private enum SidebarTransitionStyle { case standard, pill }

    private func updateLeftPanelDepth(animated: Bool,
                                      reason: PanelMotionReason = .focus,
                                      gestureVelocity: CGFloat = 0.0) {
        _ = animated
        _ = reason
        _ = gestureVelocity
        // GlassCardView has no emphasis state.
    }

    private func nudgePanelForResize() {
        updateLeftPanelDepth(animated: true, reason: .resize)
        schedulePanelSettle()
    }

    private func schedulePanelSettle(velocity: CGFloat = 0.0) {
        dividerSettleWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in
            self?.updateLeftPanelDepth(animated: true, reason: .settle, gestureVelocity: velocity)
            self?.refreshVisibleRowDepth(animated: true, preset: .microBounce)
        }
        dividerSettleWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.16, execute: work)
    }

    private func refreshVisibleRowDepth(animated: Bool, preset: SpringPreset = .crisp) {
        let visible = tableView.rows(in: tableView.visibleRect)
        guard visible.length > 0 else { return }

        for row in visible.location..<(visible.location + visible.length) {
            guard let rowView = tableView.rowView(atRow: row, makeIfNecessary: false) as? ElasticRowView else { continue }
            rowView.isHeaderRow = (row == 0)
            rowView.rowIndex = row
            rowView.reduceMotionProvider = { [weak self] in self?.shouldReduceMotion ?? false }
            rowView.isActiveWindowProvider = { [weak self] in self?.isWindowActiveForAppearance() ?? true }
            rowView.refreshDepth(animated: animated, preset: preset)
        }
    }

    private func setupPinnedHeader() {
        leftHeaderBar.wantsLayer = true
        leftHeaderBar.layer?.backgroundColor = NSColor.clear.cgColor
        leftHeaderBar.autoresizingMask = []
        leftHeaderBar.addSubview(leftHeaderLabel)

        leftHeaderLabel.translatesAutoresizingMaskIntoConstraints = true
        leftHeaderLabel.autoresizingMask = []
        leftHeaderLabel.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        leftHeaderLabel.textColor = leftHeaderTextColor()
        leftHeaderLabel.alignment = .left
        leftHeaderLabel.backgroundColor = .clear
        leftHeaderLabel.lineBreakMode = .byTruncatingTail

        leftHeaderRule.wantsLayer = true
        leftHeaderRule.layer?.backgroundColor = resolvedSystemColor(.separatorColor).cgColor
        leftHeaderRule.autoresizingMask = []

        updateLeftHeaderText()
        leftHeaderBar.isHidden = true
        leftHeaderRule.isHidden = true

        searchBackgroundFrameObserver = NotificationCenter.default.addObserver(
            forName: NSView.frameDidChangeNotification,
            object: searchBackground,
            queue: .main
        ) { [weak self] _ in
            self?.updateSearchCapsuleGeometry()
        }
        installSearchTracking()
    }

	    private func updateSearchCapsuleGeometry() {
	        guard let layer = searchBackground.layer else { return }
	        let b = searchBackground.bounds
	        guard b.width > 1, b.height > 1 else { return }

	        let lineWidth: CGFloat = max(1, SPOTLIGHT_SEARCH_OUTLINE_WIDTH)
	        let inset = lineWidth / 2
	        let rect = b.insetBy(dx: inset, dy: inset)
	        let radius = rect.height / 2
	        let path = CGPath(roundedRect: rect, cornerWidth: radius, cornerHeight: radius, transform: nil)
	        let innerRect = b.insetBy(dx: inset + 1.0, dy: inset + 1.0)
	        let innerRadius = max(0, innerRect.height / 2)
	        let innerPath = CGPath(roundedRect: innerRect, cornerWidth: innerRadius, cornerHeight: innerRadius, transform: nil)

	        CATransaction.begin()
	        CATransaction.setDisableActions(true)
	        layer.masksToBounds = true
	        layer.cornerRadius = radius
	        if let glass = searchBackground as? NSGlassEffectView {
	            glass.cornerRadius = radius
	        }
	        searchOutlineLayer.lineWidth = lineWidth
	        searchOutlineLayer.path = path
	        searchInnerOutlineLayer.lineWidth = lineWidth
	        searchInnerOutlineLayer.path = innerPath
	        searchMaskLayer.path = path
	        searchCenterGlowLayer.frame = b
	        searchCenterGlowLayer.locations = [0.0, 1.0]
	        searchHighlightLayer.frame = b
	        searchHighlightLayer.locations = [0.0, 0.55, 1.0]
	        searchFalloffLayer.frame = b
	        searchFalloffLayer.locations = [0.0, 1.0]
	        if let containerLayer = searchContainer.layer {
	            containerLayer.shadowPath = path
	        }
	        CATransaction.commit()
	
	        updateEmbeddedSearchAppearance(animated: false)
	        layoutSuggestionsDropdown()
	    }

    private func updatePDFFindCapsuleGeometry() {
        guard let layer = pdfFindBackgroundView.layer else { return }
        let b = pdfFindBackgroundView.bounds
        guard b.width > 1, b.height > 1 else { return }

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        let radius = b.height / 2
        if let card = pdfFindBackgroundView as? GlassCardView {
            card.cornerRadius = radius
        } else {
            layer.masksToBounds = true
            layer.cornerRadius = radius
            if let glass = pdfFindBackgroundView as? NSGlassEffectView {
                glass.cornerRadius = radius
            }
        }
        if pdfFindOutlineLayer.superlayer != nil {
            let lineWidth: CGFloat = max(1, SPOTLIGHT_SEARCH_OUTLINE_WIDTH)
            let inset = lineWidth / 2
            let rect = b.insetBy(dx: inset, dy: inset)
            let outlineRadius = rect.height / 2
            let path = CGPath(roundedRect: rect,
                              cornerWidth: outlineRadius,
                              cornerHeight: outlineRadius,
                              transform: nil)
            pdfFindOutlineLayer.lineWidth = lineWidth
            pdfFindOutlineLayer.strokeColor = spotlightSearchOutlineColor().cgColor
            pdfFindOutlineLayer.path = path
            pdfFindHighlightLayer.frame = b
            pdfFindHighlightLayer.colors = spotlightSearchHighlightColors()
            pdfFindHighlightLayer.locations = [0.0, 0.55, 1.0]
            pdfFindFalloffLayer.frame = b
            pdfFindFalloffLayer.colors = spotlightSearchFalloffColors()
            pdfFindFalloffLayer.locations = [0.0, 1.0]
        }
        CATransaction.commit()
    }

    private func installSearchTracking() {
        if let tracking = searchTracking {
            searchField.removeTrackingArea(tracking)
        }
        let opts: NSTrackingArea.Options = [.mouseEnteredAndExited, .activeAlways, .inVisibleRect]
        let area = NSTrackingArea(rect: searchField.bounds, options: opts, owner: self, userInfo: nil)
        searchField.addTrackingArea(area)
        searchTracking = area
    }

    private func installPDFFindTracking() {
        if let tracking = pdfFindTracking {
            pdfFindField.removeTrackingArea(tracking)
        }
        let opts: NSTrackingArea.Options = [.mouseEnteredAndExited, .activeAlways, .inVisibleRect]
        let area = NSTrackingArea(rect: pdfFindField.bounds, options: opts, owner: self, userInfo: nil)
        pdfFindField.addTrackingArea(area)
        pdfFindTracking = area
    }

    override func mouseEntered(with event: NSEvent) {
        if event.trackingArea == searchTracking {
            searchHover = true
            updateSearchDepth(animated: true)
        } else if event.trackingArea == rightAuxAskTracking {
            rightAuxAskHover = true
            updateRightAuxAskDepth(animated: true)
        } else if event.trackingArea == pdfFindTracking {
            pdfFindHover = true
            updatePDFFindDepth(animated: true)
        }
        super.mouseEntered(with: event)
    }

    override func mouseExited(with event: NSEvent) {
        if event.trackingArea == searchTracking {
            searchHover = false
            updateSearchDepth(animated: true)
        } else if event.trackingArea == rightAuxAskTracking {
            rightAuxAskHover = false
            updateRightAuxAskDepth(animated: true)
        } else if event.trackingArea == pdfFindTracking {
            pdfFindHover = false
            updatePDFFindDepth(animated: true)
        }
        super.mouseExited(with: event)
    }

    private func updateSearchDepth(animated: Bool) {
        updateEmbeddedSearchAppearance(animated: animated)
        updateSearchHoverMotion(animated: animated)
        enforceActiveVisualEffectState(searchBackground)
    }

    private func updateSearchContainerAnchor() {
        guard let layer = searchContainer.layer else { return }
        let anchor = CGPoint(x: 0.5, y: 0.5)
        let position = CGPoint(x: searchContainer.frame.midX, y: searchContainer.frame.midY)

        guard layer.anchorPoint != anchor || layer.position != position else { return }
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.anchorPoint = anchor
        layer.position = position
        CATransaction.commit()
    }

    private func cornerInset(at distance: CGFloat, radius: CGFloat) -> CGFloat {
        guard radius > 0, distance < radius else { return 0 }
        let clamped = max(0, min(distance, radius))
        let under = max(0, (radius * radius) - (clamped * clamped))
        return radius - sqrt(under)
    }

    private func maxSearchHoverScale(lift: CGFloat) -> CGFloat {
        guard let root = searchContainer.superview else { return 1.0 }
        let searchFrame = searchContainer.frame
        guard searchFrame.width > 1 else { return 1.0 }

        let leftFrame = leftContainer.convert(leftContainer.bounds, to: root)
        let leftInset = max(0, searchFrame.minX - leftFrame.minX)
        let rightInset = max(0, leftFrame.maxX - searchFrame.maxX)
        let minInset = min(leftInset, rightInset)

        let radius = leftCardCornerRadius()
        let topInsetRaw = max(0, leftFrame.maxY - searchFrame.maxY)
        let bottomInsetRaw = max(0, searchFrame.minY - leftFrame.minY)
        let topInset = max(0, topInsetRaw + min(lift, 0))
        let bottomInset = bottomInsetRaw
        let cornerInset = max(cornerInset(at: topInset, radius: radius),
                              cornerInset(at: bottomInset, radius: radius))
        let safeInset = max(0, minInset - cornerInset)

        return max(1.0, 1.0 + (2.0 * safeInset / searchFrame.width))
    }

    private func updateSearchHoverMotion(animated: Bool) {
        guard let layer = searchContainer.layer else { return }
        let reduceMotion = shouldReduceMotion || !animated
        let isActive = searchHover && searchField.isEnabled

        updateSearchContainerAnchor()
        let baseScale: CGFloat = isActive ? 1.02 : 1.0
        let lift: CGFloat = isActive ? -0.8 : 0.0
        let scale: CGFloat = isActive ? min(baseScale, maxSearchHoverScale(lift: lift)) : 1.0
        var transform = CATransform3DIdentity
        transform = CATransform3DTranslate(transform, 0, lift, 0)
        transform = CATransform3DScale(transform, scale, scale, 1.0)

        let glowColor = (NSColor.white.usingColorSpace(.deviceRGB) ?? NSColor.white)
        let targetShadowOpacity: Float = isActive ? 0.22 : 0.0
        let targetShadowRadius: CGFloat = isActive ? 6 : 0
        let targetShadowOffset = CGSize(width: 0, height: isActive ? -1.0 : 0)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.shadowColor = glowColor.cgColor
        CATransaction.commit()

        if reduceMotion {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.transform = transform
            layer.shadowOpacity = targetShadowOpacity
            layer.shadowRadius = targetShadowRadius
            layer.shadowOffset = targetShadowOffset
            CATransaction.commit()
        } else {
            animateLayer(layer, keyPath: "transform", to: transform, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowOpacity", to: targetShadowOpacity, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowRadius", to: targetShadowRadius, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
            animateLayer(layer, keyPath: "shadowOffset", to: targetShadowOffset, preset: .microBounce, reduceMotion: false, basicDuration: 0.14)
        }
    }

    private func updatePDFFindDepth(animated: Bool) {
        if let layer = pdfFindBackgroundView.layer,
           layer.animation(forKey: "pdfFindTransform") != nil {
            return
        }
        applySearchBarDepth(to: pdfFindBackgroundView, focused: pdfFindFocused, hovered: pdfFindHover, animated: animated)
        enforceActiveVisualEffectState(pdfFindBackgroundView)
    }

    private func pdfFindTransform(scaleX: CGFloat, scaleY: CGFloat, yOffset: CGFloat) -> CATransform3D {
        var transform = CATransform3DIdentity
        transform = CATransform3DScale(transform, scaleX, scaleY, 1.0)
        transform = CATransform3DTranslate(transform, 0, yOffset, 0)
        return transform
    }

    private func pdfFindHiddenTransform() -> CATransform3D {
        pdfFindTransform(
            scaleX: PDF_FIND_DISMISS_END_SCALE_X,
            scaleY: PDF_FIND_DISMISS_END_SCALE_Y,
            yOffset: PDF_FIND_DISMISS_END_Y_OFFSET
        )
    }

    private func currentLayerTransform(_ layer: CALayer) -> CATransform3D {
        layer.presentation()?.transform ?? layer.transform
    }

    private func currentLayerOpacity(_ layer: CALayer) -> Float {
        layer.presentation()?.opacity ?? layer.opacity
    }

    private func currentLayerShadowOpacity(_ layer: CALayer) -> Float {
        layer.presentation()?.shadowOpacity ?? layer.shadowOpacity
    }

    private func currentLayerShadowRadius(_ layer: CALayer) -> CGFloat {
        if let value = layer.presentation()?.value(forKeyPath: "shadowRadius") as? NSNumber {
            return CGFloat(truncating: value)
        }
        return layer.shadowRadius
    }

    private func currentLayerShadowOffset(_ layer: CALayer) -> CGSize {
        if let value = layer.presentation()?.value(forKeyPath: "shadowOffset") as? NSValue {
            return value.sizeValue
        }
        return layer.shadowOffset
    }

    private func addKeyframeAnimation(_ layer: CALayer,
                                      keyPath: String,
                                      values: [Any],
                                      keyTimes: [NSNumber],
                                      duration: CFTimeInterval,
                                      timingFunctions: [CAMediaTimingFunction],
                                      key: String) {
        let animation = CAKeyframeAnimation(keyPath: keyPath)
        animation.values = values
        animation.keyTimes = keyTimes
        animation.timingFunctions = timingFunctions
        animation.duration = duration
        animation.isRemovedOnCompletion = true
        layer.add(animation, forKey: key)
    }

    private func setPDFFindHUDVisible(_ visible: Bool, animated: Bool) {
        pdfFindVisibilityWorkItem?.cancel()
        pdfFindDepthWorkItem?.cancel()
        guard let backgroundLayer = pdfFindBackgroundView.layer else {
            pdfFindHUD.isHidden = !visible
            return
        }
        let contentLayer = pdfFindContentView.layer

        let theme = currentSearchBarTheme()
        let reduce = shouldReduceMotion || !animated
        let targetTransform = CATransform3DIdentity
        let targetShadowOpacity = theme.shadowOpacity
        let targetShadowRadius = theme.shadowRadius
        let targetShadowOffset = theme.shadowOffset

        let liveTransform = currentLayerTransform(backgroundLayer)
        let liveOpacity = currentLayerOpacity(backgroundLayer)
        let liveShadowOpacity = currentLayerShadowOpacity(backgroundLayer)
        let liveShadowRadius = currentLayerShadowRadius(backgroundLayer)
        let liveShadowOffset = currentLayerShadowOffset(backgroundLayer)

        backgroundLayer.removeAnimation(forKey: "pdfFindTransform")
        backgroundLayer.removeAnimation(forKey: "pdfFindOpacity")
        backgroundLayer.removeAnimation(forKey: "pdfFindShadowOpacity")
        backgroundLayer.removeAnimation(forKey: "pdfFindShadowRadius")
        backgroundLayer.removeAnimation(forKey: "pdfFindShadowOffset")
        contentLayer?.removeAnimation(forKey: "pdfFindContentTransform")
        contentLayer?.removeAnimation(forKey: "pdfFindContentOpacity")

        if visible {
            let wasHidden = pdfFindHUD.isHidden
            if wasHidden {
                pdfFindHUD.isHidden = false
                layoutPDFFindHUDSubviews()
            }

            let startTransform = wasHidden
                ? pdfFindTransform(
                    scaleX: PDF_FIND_APPEAR_START_SCALE_X,
                    scaleY: PDF_FIND_APPEAR_START_SCALE_Y,
                    yOffset: PDF_FIND_APPEAR_START_Y_OFFSET
                )
                : liveTransform
            let startOpacity: Float = wasHidden ? 0 : liveOpacity
            let startShadowOpacity: Float = wasHidden ? 0 : liveShadowOpacity
            let startShadowRadius: CGFloat = wasHidden ? 0 : liveShadowRadius

            if let contentLayer, wasHidden {
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                contentLayer.opacity = 0
                contentLayer.transform = startTransform
                CATransaction.commit()
            }

            if reduce {
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                backgroundLayer.transform = startTransform
                backgroundLayer.opacity = startOpacity
                backgroundLayer.shadowOpacity = startShadowOpacity
                backgroundLayer.shadowRadius = startShadowRadius
                backgroundLayer.shadowOffset = targetShadowOffset
                CATransaction.commit()

                animateLayer(backgroundLayer, keyPath: "transform", to: targetTransform, preset: .crisp, reduceMotion: true, basicDuration: 0.2)
                animateLayer(backgroundLayer, keyPath: "opacity", to: 1, preset: .crisp, reduceMotion: true, basicDuration: 0.16)
                animateLayer(backgroundLayer, keyPath: "shadowOpacity", to: targetShadowOpacity, preset: .crisp, reduceMotion: true, basicDuration: 0.16)
                animateLayer(backgroundLayer, keyPath: "shadowRadius", to: targetShadowRadius, preset: .crisp, reduceMotion: true, basicDuration: 0.16)
                if let contentLayer {
                    CATransaction.begin()
                    CATransaction.setDisableActions(true)
                    contentLayer.transform = startTransform
                    contentLayer.opacity = startOpacity
                    CATransaction.commit()
                    animateLayer(contentLayer, keyPath: "transform", to: targetTransform, preset: .crisp, reduceMotion: true, basicDuration: 0.2)
                    animateLayer(contentLayer, keyPath: "opacity", to: 1, preset: .crisp, reduceMotion: true, basicDuration: 0.16)
                }
                return
            }

            CATransaction.begin()
            CATransaction.setDisableActions(true)
            backgroundLayer.transform = targetTransform
            backgroundLayer.opacity = 1
            backgroundLayer.shadowOpacity = targetShadowOpacity
            backgroundLayer.shadowRadius = targetShadowRadius
            backgroundLayer.shadowOffset = targetShadowOffset
            CATransaction.commit()

            let overshootTransform = pdfFindTransform(
                scaleX: PDF_FIND_APPEAR_OVERSHOOT_SCALE_X,
                scaleY: PDF_FIND_APPEAR_OVERSHOOT_SCALE_Y,
                yOffset: PDF_FIND_APPEAR_OVERSHOOT_Y_OFFSET
            )
            let transformValues: [Any] = [
                NSValue(caTransform3D: startTransform),
                NSValue(caTransform3D: overshootTransform),
                NSValue(caTransform3D: targetTransform)
            ]
            let transformTimes: [NSNumber] = [
                0,
                NSNumber(value: Double(PDF_FIND_APPEAR_OVERSHOOT_TIME)),
                1
            ]
            addKeyframeAnimation(
                backgroundLayer,
                keyPath: "transform",
                values: transformValues,
                keyTimes: transformTimes,
                duration: PDF_FIND_APPEAR_DURATION,
                timingFunctions: [
                    CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.2, 1.0),
                    CAMediaTimingFunction(controlPoints: 0.2, 0.8, 0.2, 1.0)
                ],
                key: "pdfFindTransform"
            )

            let opacityValues: [NSNumber] = [
                NSNumber(value: Double(startOpacity)),
                1,
                1
            ]
            let opacityTimes: [NSNumber] = [
                0,
                NSNumber(value: Double(PDF_FIND_OPACITY_RAMP_TIME)),
                1
            ]
            addKeyframeAnimation(
                backgroundLayer,
                keyPath: "opacity",
                values: opacityValues,
                keyTimes: opacityTimes,
                duration: PDF_FIND_APPEAR_DURATION,
                timingFunctions: [
                    CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.2, 1.0),
                    CAMediaTimingFunction(controlPoints: 0.2, 0.8, 0.2, 1.0)
                ],
                key: "pdfFindOpacity"
            )

            let shadowOpacityValues: [NSNumber] = [
                NSNumber(value: Double(startShadowOpacity)),
                NSNumber(value: Double(targetShadowOpacity)),
                NSNumber(value: Double(targetShadowOpacity))
            ]
            addKeyframeAnimation(
                backgroundLayer,
                keyPath: "shadowOpacity",
                values: shadowOpacityValues,
                keyTimes: opacityTimes,
                duration: PDF_FIND_APPEAR_DURATION,
                timingFunctions: [
                    CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.2, 1.0),
                    CAMediaTimingFunction(controlPoints: 0.2, 0.8, 0.2, 1.0)
                ],
                key: "pdfFindShadowOpacity"
            )

            let shadowRadiusValues: [NSNumber] = [
                NSNumber(value: Double(startShadowRadius)),
                NSNumber(value: Double(targetShadowRadius)),
                NSNumber(value: Double(targetShadowRadius))
            ]
            addKeyframeAnimation(
                backgroundLayer,
                keyPath: "shadowRadius",
                values: shadowRadiusValues,
                keyTimes: opacityTimes,
                duration: PDF_FIND_APPEAR_DURATION,
                timingFunctions: [
                    CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.2, 1.0),
                    CAMediaTimingFunction(controlPoints: 0.2, 0.8, 0.2, 1.0)
                ],
                key: "pdfFindShadowRadius"
            )

            if let contentLayer {
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                contentLayer.transform = targetTransform
                contentLayer.opacity = 1
                CATransaction.commit()

                let contentTransformValues: [Any] = [
                    NSValue(caTransform3D: startTransform),
                    NSValue(caTransform3D: overshootTransform),
                    NSValue(caTransform3D: targetTransform)
                ]
                addKeyframeAnimation(
                    contentLayer,
                    keyPath: "transform",
                    values: contentTransformValues,
                    keyTimes: transformTimes,
                    duration: PDF_FIND_APPEAR_DURATION,
                    timingFunctions: [
                        CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.2, 1.0),
                        CAMediaTimingFunction(controlPoints: 0.2, 0.8, 0.2, 1.0)
                    ],
                    key: "pdfFindContentTransform"
                )

                let contentOpacityValues: [NSNumber] = [
                    NSNumber(value: Double(startOpacity)),
                    1,
                    1
                ]
                addKeyframeAnimation(
                    contentLayer,
                    keyPath: "opacity",
                    values: contentOpacityValues,
                    keyTimes: opacityTimes,
                    duration: PDF_FIND_APPEAR_DURATION,
                    timingFunctions: [
                        CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.2, 1.0),
                        CAMediaTimingFunction(controlPoints: 0.2, 0.8, 0.2, 1.0)
                    ],
                    key: "pdfFindContentOpacity"
                )
            }

            let depthWorkItem = DispatchWorkItem { [weak self] in
                self?.updatePDFFindDepth(animated: true)
            }
            pdfFindDepthWorkItem = depthWorkItem
            DispatchQueue.main.asyncAfter(deadline: .now() + PDF_FIND_APPEAR_DURATION, execute: depthWorkItem)
        } else {
            guard !pdfFindHUD.isHidden else { return }

            let currentTransform = liveTransform
            let currentOpacity = liveOpacity
            let currentShadowOpacity = liveShadowOpacity
            let currentShadowRadius = liveShadowRadius
            let endTransform = pdfFindHiddenTransform()

            if reduce {
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                backgroundLayer.transform = currentTransform
                backgroundLayer.opacity = currentOpacity
                backgroundLayer.shadowOpacity = currentShadowOpacity
                backgroundLayer.shadowRadius = currentShadowRadius
                backgroundLayer.shadowOffset = liveShadowOffset
                CATransaction.commit()

                animateLayer(backgroundLayer, keyPath: "transform", to: endTransform, preset: .crisp, reduceMotion: true, basicDuration: 0.16)
                animateLayer(backgroundLayer, keyPath: "opacity", to: 0, preset: .crisp, reduceMotion: true, basicDuration: 0.16)
                animateLayer(backgroundLayer, keyPath: "shadowOpacity", to: 0, preset: .crisp, reduceMotion: true, basicDuration: 0.16)
                animateLayer(backgroundLayer, keyPath: "shadowRadius", to: 0, preset: .crisp, reduceMotion: true, basicDuration: 0.16)
                if let contentLayer {
                    CATransaction.begin()
                    CATransaction.setDisableActions(true)
                    contentLayer.transform = currentTransform
                    contentLayer.opacity = currentOpacity
                    CATransaction.commit()
                    animateLayer(contentLayer, keyPath: "transform", to: endTransform, preset: .crisp, reduceMotion: true, basicDuration: 0.16)
                    animateLayer(contentLayer, keyPath: "opacity", to: 0, preset: .crisp, reduceMotion: true, basicDuration: 0.16)
                }
                let workItem = DispatchWorkItem { [weak self] in
                    self?.pdfFindHUD.isHidden = true
                }
                pdfFindVisibilityWorkItem = workItem
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.18, execute: workItem)
                return
            }

            CATransaction.begin()
            CATransaction.setDisableActions(true)
            backgroundLayer.transform = endTransform
            backgroundLayer.opacity = 0
            backgroundLayer.shadowOpacity = 0
            backgroundLayer.shadowRadius = 0
            backgroundLayer.shadowOffset = .zero
            CATransaction.commit()

            let tensionTransform = pdfFindTransform(
                scaleX: PDF_FIND_DISMISS_TENSION_SCALE_X,
                scaleY: PDF_FIND_DISMISS_TENSION_SCALE_Y,
                yOffset: PDF_FIND_DISMISS_TENSION_Y_OFFSET
            )
            let overshootTransform = pdfFindTransform(
                scaleX: PDF_FIND_DISMISS_OVERSHOOT_SCALE_X,
                scaleY: PDF_FIND_DISMISS_OVERSHOOT_SCALE_Y,
                yOffset: PDF_FIND_DISMISS_OVERSHOOT_Y_OFFSET
            )

            let transformValues: [Any]
            let transformTimes: [NSNumber]
            let transformTiming: [CAMediaTimingFunction]

            if currentOpacity < 0.4 {
                transformValues = [
                    NSValue(caTransform3D: currentTransform),
                    NSValue(caTransform3D: endTransform)
                ]
                transformTimes = [0, 1]
                transformTiming = [
                    CAMediaTimingFunction(controlPoints: 0.3, 0.1, 0.2, 1.0)
                ]
            } else {
                transformValues = [
                    NSValue(caTransform3D: currentTransform),
                    NSValue(caTransform3D: tensionTransform),
                    NSValue(caTransform3D: overshootTransform),
                    NSValue(caTransform3D: endTransform)
                ]
                transformTimes = [
                    0,
                    NSNumber(value: Double(PDF_FIND_DISMISS_TENSION_TIME)),
                    NSNumber(value: Double(PDF_FIND_DISMISS_OVERSHOOT_TIME)),
                    1
                ]
                transformTiming = [
                    CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.2, 1.0),
                    CAMediaTimingFunction(controlPoints: 0.2, 0.1, 0.2, 1.0),
                    CAMediaTimingFunction(controlPoints: 0.2, 0.6, 0.2, 1.0)
                ]
            }

            addKeyframeAnimation(
                backgroundLayer,
                keyPath: "transform",
                values: transformValues,
                keyTimes: transformTimes,
                duration: PDF_FIND_DISMISS_DURATION,
                timingFunctions: transformTiming,
                key: "pdfFindTransform"
            )

            let opacityValues: [NSNumber] = [
                NSNumber(value: Double(currentOpacity)),
                0.5,
                0
            ]
            let opacityTimes: [NSNumber] = [
                0,
                NSNumber(value: Double(PDF_FIND_DISMISS_TENSION_TIME)),
                1
            ]
            addKeyframeAnimation(
                backgroundLayer,
                keyPath: "opacity",
                values: opacityValues,
                keyTimes: opacityTimes,
                duration: PDF_FIND_DISMISS_DURATION,
                timingFunctions: [
                    CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.2, 1.0),
                    CAMediaTimingFunction(controlPoints: 0.2, 0.1, 0.2, 1.0)
                ],
                key: "pdfFindOpacity"
            )

            let shadowOpacityValues: [NSNumber] = [
                NSNumber(value: Double(currentShadowOpacity)),
                0,
                0
            ]
            addKeyframeAnimation(
                backgroundLayer,
                keyPath: "shadowOpacity",
                values: shadowOpacityValues,
                keyTimes: opacityTimes,
                duration: PDF_FIND_DISMISS_DURATION,
                timingFunctions: [
                    CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.2, 1.0),
                    CAMediaTimingFunction(controlPoints: 0.2, 0.1, 0.2, 1.0)
                ],
                key: "pdfFindShadowOpacity"
            )

            let shadowRadiusValues: [NSNumber] = [
                NSNumber(value: Double(currentShadowRadius)),
                0,
                0
            ]
            addKeyframeAnimation(
                backgroundLayer,
                keyPath: "shadowRadius",
                values: shadowRadiusValues,
                keyTimes: opacityTimes,
                duration: PDF_FIND_DISMISS_DURATION,
                timingFunctions: [
                    CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.2, 1.0),
                    CAMediaTimingFunction(controlPoints: 0.2, 0.1, 0.2, 1.0)
                ],
                key: "pdfFindShadowRadius"
            )

            if let contentLayer {
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                contentLayer.opacity = 0
                CATransaction.commit()
                addKeyframeAnimation(
                    contentLayer,
                    keyPath: "transform",
                    values: transformValues,
                    keyTimes: transformTimes,
                    duration: PDF_FIND_DISMISS_DURATION,
                    timingFunctions: transformTiming,
                    key: "pdfFindContentTransform"
                )
                addKeyframeAnimation(
                    contentLayer,
                    keyPath: "opacity",
                    values: opacityValues,
                    keyTimes: opacityTimes,
                    duration: PDF_FIND_DISMISS_DURATION,
                    timingFunctions: [
                        CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.2, 1.0),
                        CAMediaTimingFunction(controlPoints: 0.2, 0.1, 0.2, 1.0)
                    ],
                    key: "pdfFindContentOpacity"
                )
            }

            let workItem = DispatchWorkItem { [weak self] in
                guard let self else { return }
                self.pdfFindHUD.isHidden = true
                if let layer = self.pdfFindBackgroundView.layer {
                    CATransaction.begin()
                    CATransaction.setDisableActions(true)
                    layer.transform = targetTransform
                    layer.opacity = 1
                    layer.shadowOpacity = targetShadowOpacity
                    layer.shadowRadius = targetShadowRadius
                    layer.shadowOffset = targetShadowOffset
                    CATransaction.commit()
                }
            }
            pdfFindVisibilityWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + PDF_FIND_DISMISS_DURATION, execute: workItem)
        }
    }

    private func layoutSearchContainer(ensureLayout: Bool = true) {
        guard let root = searchContainer.superview else { return }
        if ensureLayout {
            root.layoutSubtreeIfNeeded()
            splitView.layoutSubtreeIfNeeded()
        }

        let leftFrameInRoot = leftContainer.convert(leftContainer.bounds, to: root)

        // Inset the search glass so the leftContainer reads as a bezel behind it.
        let insetX: CGFloat = PANEL_INSET
        let contentWidth = max(0, leftFrameInRoot.width - (2 * insetX))
        let x = leftFrameInRoot.minX + insetX
        let y = leftFrameInRoot.maxY - PANEL_INSET - searchContainerHeight
        searchContainer.frame = NSRect(x: x, y: y, width: contentWidth, height: searchContainerHeight)
        if ensureLayout {
            searchContainer.layoutSubtreeIfNeeded()
        }
        updateSearchContainerAnchor()
        updateSearchContainerClip()
        updateSearchCapsuleGeometry()
        if !suggestionsContainer.isHidden && !suggestions.isEmpty {
            layoutSuggestionsDropdown()
        }
        layoutHeaderControls()
    }

    private func updateSearchContainerClip() {
        guard let root = searchContainer.superview,
              let layer = searchContainer.layer else { return }

        let leftFrameInRoot = leftContainer.convert(leftContainer.bounds, to: root)
        let searchFrameInRoot = searchContainer.frame
        let clipInRoot = searchFrameInRoot.intersection(leftFrameInRoot)
        let clipInSearch: NSRect
        if clipInRoot.isNull || clipInRoot.isEmpty {
            clipInSearch = .zero
        } else {
            clipInSearch = searchContainer.convert(clipInRoot, from: root)
        }

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        searchContainerClipLayer.frame = searchContainer.bounds
        searchContainerClipLayer.path = CGPath(rect: clipInSearch, transform: nil)
        layer.mask = searchContainerClipLayer
        CATransaction.commit()
    }

    private func layoutHeaderControls() {
        guard let root = headerControlsContainer.superview else { return }
        root.layoutSubtreeIfNeeded()

        let leftFrameInRoot = leftContainer.convert(leftContainer.bounds, to: root)
        var size = toolbarControls.fittingSize
        if !size.width.isFinite || size.width <= 0 {
            size.width = max(0, root.bounds.width - leftFrameInRoot.minX - WINDOW_BEZEL_INSET)
        } else {
            let availableWidth = max(0, root.bounds.width - leftFrameInRoot.minX - WINDOW_BEZEL_INSET)
            if availableWidth > 0 {
                size.width = min(size.width, availableWidth)
            }
        }
        let x = max(root.bounds.minX, min(leftFrameInRoot.minX, root.bounds.maxX - size.width))
        let y = root.bounds.maxY - headerControlsTopInset - size.height
        headerControlsContainer.frame = NSRect(x: x, y: y, width: size.width, height: size.height)
        headerControlsContainer.layoutSubtreeIfNeeded()
        layoutRightPanelPillControl(in: root)
        if !menuContainer.isHidden {
            layoutMenuPanel()
        }
    }

    private func layoutRightPanelPillControl(in root: NSView) {
        let rightFrameInRoot = rightContainer.convert(rightContainer.bounds, to: root)
        let inset: CGFloat = 12
        let availableWidth = max(0, rightFrameInRoot.width - (2 * inset))
        guard availableWidth > 24 else {
            rightPanelPillControl.isHidden = true
            return
        }

        rightPanelPillControl.isHidden = false
        let baseHeight = toolbarControlHeight > 0 ? toolbarControlHeight : (32 * toolbarControlScaleCurrent)
        let scale = max(0.86, min(1.15, rightFrameInRoot.width / 720))
        let height = baseHeight * scale
        let minWidth = height * 4.4
        let maxWidth = height * 8.0
        let targetWidth = min(rightFrameInRoot.width * 0.6, maxWidth)
        let width = min(availableWidth, max(minWidth, targetWidth))
        // Keep the pill horizontally centered on the viewer (PDF or HTML) while staying in the
        // header band vertically.
        let viewerAnchorFrame: NSRect = {
            if isShowingPDF, pdfView.isHidden == false, pdfView.window === root.window {
                let f = pdfView.convert(pdfView.bounds, to: root)
                if f.isEmpty == false { return f }
            }
            if detailsWebView.isHidden == false, detailsWebView.window === root.window {
                let f = detailsWebView.convert(detailsWebView.bounds, to: root)
                if f.isEmpty == false { return f }
            }
            return rightFrameInRoot
        }()

        let x = viewerAnchorFrame.midX - (width / 2)
        let y = headerControlsContainer.frame.midY - (height / 2)
        var alignedFrame = pixelAlignedRect(NSRect(x: x, y: y, width: width, height: height), in: root)

        // Keep the pill from covering header controls (especially the sidebar button) in narrow layouts.
        let headerFrame = headerControlsContainer.frame.insetBy(dx: -8, dy: -4)
        if alignedFrame.intersects(headerFrame) {
            let clearance: CGFloat = 8
            let safeLeft = headerFrame.maxX + clearance
            let safeRight = rightFrameInRoot.maxX - inset
            let maxPillWidth = max(0, safeRight - safeLeft)
            guard maxPillWidth >= minWidth else {
                rightPanelPillControl.isHidden = true
                return
            }
            alignedFrame.size.width = min(alignedFrame.size.width, maxPillWidth)
            alignedFrame.origin.x = min(max(alignedFrame.origin.x, safeLeft),
                                        safeRight - alignedFrame.size.width)
            alignedFrame = pixelAlignedRect(alignedFrame, in: root)
        }

        rightPanelPillControl.frame = alignedFrame
        rightPanelPillControl.needsLayout = true
        // Important: if the pill moves under a stationary cursor (e.g. after opening the
        // Chat Session panel), AppKit won't send a new mouseEntered. Re-sync hover now.
        rightPanelPillControl.syncHoverFromCurrentMouseLocation(animated: true)
        layoutRightPanelEdgeButtons(in: root)
    }

    private func layoutRightPanelEdgeButtons(in root: NSView) {
                guard let leftGlass = rightPanelLeftEdgeButtonBackground,
                            let zoteroGlass = rightPanelZoteroEdgeButtonBackground,
                            let rightGlass = rightPanelRightEdgeButtonBackground,
                            let settingsGlass = rightPanelSettingsEdgeButtonBackground else {
            return
        }

        let rightFrameInRoot = rightContainer.convert(rightContainer.bounds, to: root)
        let buttonHeight = toolbarControlHeight > 0 ? toolbarControlHeight : (32 * toolbarControlScaleCurrent)
        let buttonWidth: CGFloat = max(toolbarMinHitSize, 30 * toolbarControlScaleCurrent)
        let horizontalInset: CGFloat = 6
        // Two-button cluster on the left (Share + Settings) and two-button cluster on the right (Zotero + panel toggle).
        let requiredWidth = (4 * buttonWidth) + (4 * horizontalInset)
        guard rightFrameInRoot.width >= requiredWidth else {
            leftGlass.isHidden = true
            zoteroGlass.isHidden = true
            rightGlass.isHidden = true
            settingsGlass.isHidden = true
            rightPanelLeftEdgeButton.isHidden = true
            rightPanelZoteroEdgeButton.isHidden = true
            rightPanelRightEdgeButton.isHidden = true
            rightPanelSettingsEdgeButton.isHidden = true
            return
        }

        let centerY = headerControlsContainer.frame.midY
        let buttonY = centerY - (buttonHeight / 2)
        // When the sidebar is collapsed, the right panel slides underneath the left toolbar.
        // Keep the leftmost right-panel edge button to the right of the toolbar controls.
        let clearance: CGFloat = 10
        let minLeftX = (!sidebarVisible) ? (headerControlsContainer.frame.maxX + clearance) : (-CGFloat.greatestFiniteMagnitude)
        let leftX = max(rightFrameInRoot.minX + horizontalInset, minLeftX)
        let middleX = leftX + buttonWidth + horizontalInset
        let rightX = rightFrameInRoot.maxX - horizontalInset - buttonWidth
        let zoteroX = rightX - buttonWidth - horizontalInset

        // If the toolbar takes too much space, hide the edge buttons rather than overlapping.
        // If the available width is too small to keep clusters distinct, hide the edge buttons rather than overlap.
        if middleX > (zoteroX - horizontalInset) {
            leftGlass.isHidden = true
            zoteroGlass.isHidden = true
            rightGlass.isHidden = true
            settingsGlass.isHidden = true
            rightPanelLeftEdgeButton.isHidden = true
            rightPanelZoteroEdgeButton.isHidden = true
            rightPanelRightEdgeButton.isHidden = true
            rightPanelSettingsEdgeButton.isHidden = true
            return
        }

        // Keep the panel toggle on the far right; keep Share on the left edge, with Settings immediately to its right.
        // NOTE: Existing naming is historical: `rightPanelRightEdgeButton` is the Share button.
        let shareFrame = pixelAlignedRect(NSRect(x: leftX, y: buttonY, width: buttonWidth, height: buttonHeight), in: root)
        let settingsFrame = pixelAlignedRect(NSRect(x: middleX, y: buttonY, width: buttonWidth, height: buttonHeight), in: root)
        let zoteroFrame = pixelAlignedRect(NSRect(x: zoteroX, y: buttonY, width: buttonWidth, height: buttonHeight), in: root)
        let toggleFrame = pixelAlignedRect(NSRect(x: rightX, y: buttonY, width: buttonWidth, height: buttonHeight), in: root)

        leftGlass.frame = toggleFrame
        zoteroGlass.frame = zoteroFrame
        rightGlass.frame = shareFrame
        settingsGlass.frame = settingsFrame
        rightPanelLeftEdgeButton.frame = toggleFrame
        rightPanelZoteroEdgeButton.frame = zoteroFrame
        rightPanelRightEdgeButton.frame = shareFrame
        rightPanelSettingsEdgeButton.frame = settingsFrame
        leftGlass.isHidden = false
        zoteroGlass.isHidden = false
        rightGlass.isHidden = false
        settingsGlass.isHidden = false
        rightPanelLeftEdgeButton.isHidden = false
        rightPanelZoteroEdgeButton.isHidden = false
        rightPanelRightEdgeButton.isHidden = false
        rightPanelSettingsEdgeButton.isHidden = false

        let cornerRadius = shareFrame.height / 2
        leftGlass.wantsLayer = true
        zoteroGlass.wantsLayer = true
        rightGlass.wantsLayer = true
        settingsGlass.wantsLayer = true
        leftGlass.layer?.cornerRadius = cornerRadius
        zoteroGlass.layer?.cornerRadius = cornerRadius
        rightGlass.layer?.cornerRadius = cornerRadius
        settingsGlass.layer?.cornerRadius = cornerRadius
        if #available(macOS 10.13, *) {
            leftGlass.layer?.cornerCurve = .continuous
            zoteroGlass.layer?.cornerCurve = .continuous
            rightGlass.layer?.cornerCurve = .continuous
            settingsGlass.layer?.cornerCurve = .continuous
        }

        if #available(macOS 26.0, *) {
            (leftGlass as? NSGlassEffectView)?.cornerRadius = cornerRadius
            (zoteroGlass as? NSGlassEffectView)?.cornerRadius = cornerRadius
            (rightGlass as? NSGlassEffectView)?.cornerRadius = cornerRadius
            (settingsGlass as? NSGlassEffectView)?.cornerRadius = cornerRadius
        }
        rightPanelLeftEdgeButton.setCornerRadius(cornerRadius)
        rightPanelZoteroEdgeButton.setCornerRadius(cornerRadius)
        rightPanelRightEdgeButton.setCornerRadius(cornerRadius)
        rightPanelSettingsEdgeButton.setCornerRadius(cornerRadius)

        // Requested: black, glassy borders for Share, Settings, Save to Zotero, and Chat Session buttons.
        applyToolbarEdgeBlackGlassyBorder(to: leftGlass, cornerRadius: cornerRadius)
        applyToolbarEdgeBlackGlassyBorder(to: zoteroGlass, cornerRadius: cornerRadius)
        applyToolbarEdgeBlackGlassyBorder(to: rightGlass, cornerRadius: cornerRadius)
        applyToolbarEdgeBlackGlassyBorder(to: settingsGlass, cornerRadius: cornerRadius)
        rightPanelLeftEdgeButton.needsLayout = true
        rightPanelZoteroEdgeButton.needsLayout = true
        rightPanelRightEdgeButton.needsLayout = true
        rightPanelSettingsEdgeButton.needsLayout = true
    }

    private func layoutViewerAnchoredHeaderControls() {
        guard let root = headerControlsContainer.superview else { return }
        root.layoutSubtreeIfNeeded()
        layoutRightPanelPillControl(in: root)
    }

    private func suggestionTitleMaxWidth() -> CGFloat {
        guard !suggestions.isEmpty else { return 0 }
        let titleAttrs: [NSAttributedString.Key: Any] = [.font: suggestionTitleFont]
        var maxWidth: CGFloat = 0
        for suggestion in suggestions {
            let titleWidth = (suggestion.title as NSString).size(withAttributes: titleAttrs).width
            if titleWidth > maxWidth { maxWidth = titleWidth }
        }
        // Include hover scale so padding stays symmetric when text bounces.
        let hoverScale = max(1.0, ROW_TEXT_HOVER_SCALE)
        return ceil(maxWidth * hoverScale)
    }

    private func pixelAlignedRect(_ rect: NSRect, in view: NSView) -> NSRect {
        let scale = max(1.0, view.window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0)
        let minX = round(rect.minX * scale) / scale
        let minY = round(rect.minY * scale) / scale
        let maxX = round(rect.maxX * scale) / scale
        let maxY = round(rect.maxY * scale) / scale
        return NSRect(x: minX, y: minY, width: max(0, maxX - minX), height: max(0, maxY - minY))
    }

    private func layoutSuggestionsDropdown(ensureLayout: Bool = true) {
        guard let root = searchContainer.superview else { return }
        if ensureLayout {
            root.layoutSubtreeIfNeeded()
        }

        let anchorFrame = searchContainer.convert(searchContainer.bounds, to: root)

        // Size the dropdown by the longest visible title string (plus padding/insets),
        // and keep it independent of the left panel width.
        let titleWidth = suggestionTitleMaxWidth()
        let innerWidth = titleWidth + (suggestionTextInsetX * 2)
        let insetWidth = suggestionsScroll.contentInsets.left + suggestionsScroll.contentInsets.right
        var width = max(anchorFrame.width, innerWidth + insetWidth)

        // Clamp within the root bounds so it never renders off-screen.
        let screenMargin: CGFloat = 6
        let maxWidth = max(1, root.bounds.width - (screenMargin * 2))
        width = min(width, maxWidth)

        // Left-align to the search bar, then clamp so the entire dropdown stays visible.
        var x = anchorFrame.minX
        x = max(root.bounds.minX + screenMargin, min(x, root.bounds.maxX - screenMargin - width))
        let maxRows = min(8, suggestions.count)
        let contentHeight = CGFloat(maxRows) * suggestionRowHeight + suggestionsScroll.contentInsets.top + suggestionsScroll.contentInsets.bottom
        let height = max(0, contentHeight)
        let y = anchorFrame.minY - 6 - height

        let alignedFrame = pixelAlignedRect(NSRect(x: x, y: y, width: width, height: height), in: root)
        suggestionsContainer.frame = alignedFrame
        suggestionsBackground.frame = suggestionsContainer.bounds
        suggestionsScroll.frame = suggestionsContainer.bounds
        suggestionsTable.frame = suggestionsScroll.bounds
        if let col = suggestionsTable.tableColumns.first {
            col.width = max(1, suggestionsScroll.contentSize.width)
        }

        if let layer = suggestionsContainer.layer {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.anchorPoint = CGPoint(x: 0.5, y: 1.0)
            layer.position = CGPoint(x: suggestionsContainer.frame.midX, y: suggestionsContainer.frame.maxY)
            CATransaction.commit()
        }
        updateSuggestionsShadow()
    }

    private func menuAnchorFrameInRoot(for anchor: NSView, root: NSView) -> NSRect {
        guard let anchorWindow = anchor.window,
              let rootWindow = root.window,
              anchorWindow === rootWindow else {
            return anchor.convert(anchor.bounds, to: root)
        }

        let frameInWindow = anchor.convert(anchor.bounds, to: nil)
        return root.convert(frameInWindow, from: nil)
    }

    private func menuAlignedX(anchorFrame: NSRect, width: CGFloat, rootBounds: NSRect) -> CGFloat {
        let targetX = anchorFrame.minX + menuAnchorInsetX
        let minX = rootBounds.minX + PANEL_INSET
        let maxX = max(minX, rootBounds.maxX - width - PANEL_INSET)
        return min(maxX, max(minX, targetX))
    }

    private func layoutMenuPanel() {
        guard let root = menuContainer.superview,
              let anchor = menuAnchorView else { return }
        root.layoutSubtreeIfNeeded()

        let anchorFrame = menuAnchorFrameInRoot(for: anchor, root: root)
        let maxWidth = max(1, root.bounds.width - (2 * PANEL_INSET))
        let width = min(menuPreferredWidth(for: menuItems, anchorWidth: anchorFrame.width), maxWidth)
        let rowsHeight = menuItems.enumerated().reduce(CGFloat(0)) { partial, entry in
            let rowHeight = tableView(menuTable, heightOfRow: entry.offset)
            return partial + rowHeight
        }
        let height = max(1, rowsHeight + menuScroll.contentInsets.top + menuScroll.contentInsets.bottom)
        let x = menuAlignedX(anchorFrame: anchorFrame, width: width, rootBounds: root.bounds)

        let minY = PANEL_INSET
        let maxY = max(minY, root.bounds.height - height - PANEL_INSET)
        let belowY = anchorFrame.minY - menuVerticalGap - height
        let aboveY = anchorFrame.maxY + menuVerticalGap
        let fitsBelow = belowY >= minY
        let fitsAbove = aboveY <= maxY
        let y: CGFloat
        if fitsBelow || !fitsAbove {
            menuOpensUpward = false
            y = max(minY, min(maxY, belowY))
        } else {
            menuOpensUpward = true
            y = max(minY, min(maxY, aboveY))
        }

        menuContainer.frame = NSRect(x: x, y: y, width: width, height: height)
        menuBackground.frame = menuContainer.bounds
        menuScroll.frame = menuContainer.bounds
        menuTable.frame = menuScroll.bounds
        if let col = menuTable.tableColumns.first {
            col.width = max(1, menuScroll.contentSize.width)
        }

        if let layer = menuContainer.layer {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.anchorPoint = CGPoint(x: 0.5, y: menuOpensUpward ? 0.0 : 1.0)
            layer.position = CGPoint(x: menuContainer.frame.midX,
                                     y: menuOpensUpward ? menuContainer.frame.minY : menuContainer.frame.maxY)
            CATransaction.commit()
        }

        menuShield.frame = root.bounds
        updateMenuShadow()
    }

    private func updateDropdownShadow(for container: NSView, offset overrideOffset: CGSize? = nil) {
        guard let layer = container.layer else { return }
        let dark = window?.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let active = isWindowActiveForAppearance()
        let opacity: Float = dark ? (active ? 0.34 : 0.24) : (active ? 0.24 : 0.18)
        let radius: CGFloat = dark ? 18 : 16
        let offset = overrideOffset ?? CGSize(width: 0, height: -3)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.cornerRadius = menuCornerRadius
        layer.masksToBounds = false
        layer.shadowColor = NSColor.black.cgColor
        layer.shadowOpacity = opacity
        layer.shadowRadius = radius
        layer.shadowOffset = offset
        layer.shadowPath = CGPath(roundedRect: container.bounds,
                                  cornerWidth: menuCornerRadius,
                                  cornerHeight: menuCornerRadius,
                                  transform: nil)
        CATransaction.commit()
    }

    private func updateMenuShadow() {
        updateDropdownShadow(for: menuContainer)
    }

    private func updateSuggestionsShadow() {
        updateDropdownShadow(for: suggestionsContainer, offset: .zero)
    }

    private func setSuggestionsVisible(_ visible: Bool, animated: Bool) {
        let wasVisible = suggestionsVisible
        suggestionsVisibilityWorkItem?.cancel()
        suggestionsVisible = visible
        updateSearchDepth(animated: animated)

        guard let layer = suggestionsContainer.layer else {
            suggestionsContainer.isHidden = !visible
            return
        }

        if visible {
            // Always keep the dropdown on top if it overlaps other controls.
            if let root = suggestionsContainer.superview {
                root.addSubview(suggestionsContainer, positioned: .above, relativeTo: nil)
            }
            suggestionsContainer.layer?.zPosition = 10_000
            if wasVisible, !suggestionsContainer.isHidden {
                layoutSuggestionsDropdown()
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                layer.opacity = 1
                layer.transform = CATransform3DIdentity
                CATransaction.commit()
                updateSuggestionsShadow()
                return
            }
            suggestionsContainer.isHidden = false
            layoutSuggestionsDropdown()
            if let card = suggestionsBackground as? GlassCardView {
                card.invalidateGlass(reason: "suggestions_show")
            }
            let startTransform = CATransform3DTranslate(CATransform3DMakeScale(0.98, 0.98, 1.0), 0, -6, 0)
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.opacity = 0
            layer.transform = startTransform
            CATransaction.commit()
            animateLayer(layer, keyPath: "opacity", to: 1, preset: .crisp, reduceMotion: shouldReduceMotion || !animated, basicDuration: 0.16)
            animateLayer(layer, keyPath: "transform", to: CATransform3DIdentity, preset: .crisp, reduceMotion: shouldReduceMotion || !animated, basicDuration: 0.18)
        } else {
            if !wasVisible, suggestionsContainer.isHidden {
                return
            }
            suggestionsTable.deselectAll(nil)
            clearSuggestionHover(animated: false)
            refreshSuggestionTextColors()
            let endTransform = CATransform3DTranslate(CATransform3DMakeScale(0.98, 0.98, 1.0), 0, -6, 0)
            animateLayer(layer, keyPath: "opacity", to: 0, preset: .crisp, reduceMotion: shouldReduceMotion || !animated, basicDuration: 0.14)
            animateLayer(layer, keyPath: "transform", to: endTransform, preset: .crisp, reduceMotion: shouldReduceMotion || !animated, basicDuration: 0.16)
            let work = DispatchWorkItem { [weak self] in
                self?.suggestionsContainer.isHidden = true
            }
            suggestionsVisibilityWorkItem = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.16, execute: work)
        }
    }

    private func setMenuVisible(_ visible: Bool, animated: Bool) {
        menuVisibilityWorkItem?.cancel()
        menuShield.isHidden = !visible
        guard let layer = menuContainer.layer else {
            menuContainer.isHidden = !visible
            return
        }

        if visible {
            menuContainer.isHidden = false
            layoutMenuPanel()
            if let card = menuBackground as? GlassCardView {
                card.invalidateGlass(reason: "menu_show")
            }
            let yOffset: CGFloat = menuOpensUpward ? -6 : 6
            let startTransform = CATransform3DTranslate(CATransform3DMakeScale(0.98, 0.98, 1.0), 0, yOffset, 0)
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.opacity = 0
            layer.transform = startTransform
            CATransaction.commit()
            animateLayer(layer, keyPath: "opacity", to: 1, preset: .crisp, reduceMotion: shouldReduceMotion || !animated, basicDuration: 0.16)
            animateLayer(layer, keyPath: "transform", to: CATransform3DIdentity, preset: .microBounce, reduceMotion: shouldReduceMotion || !animated, basicDuration: 0.18)
        } else {
            let yOffset: CGFloat = menuOpensUpward ? -6 : 6
            let endTransform = CATransform3DTranslate(CATransform3DMakeScale(0.98, 0.98, 1.0), 0, yOffset, 0)
            animateLayer(layer, keyPath: "opacity", to: 0, preset: .crisp, reduceMotion: shouldReduceMotion || !animated, basicDuration: 0.14)
            animateLayer(layer, keyPath: "transform", to: endTransform, preset: .microBounce, reduceMotion: shouldReduceMotion || !animated, basicDuration: 0.16)
            let work = DispatchWorkItem { [weak self] in
                self?.menuContainer.isHidden = true
                self?.menuSelectionHandler = nil
                self?.menuAnchorView = nil
            }
            menuVisibilityWorkItem = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.16, execute: work)
        }
    }

    private func layoutToolbarControls() {
        // Respect resize-driven coupled corner radius when available.
        let radius: CGFloat = toolbarScaleLastApplied?.cornerRadius ?? max(10, sidebarControlContainer.bounds.height / 2)
        sidebarControlBackground.wantsLayer = true
        sidebarControlBackground.layer?.cornerRadius = radius
        if #available(macOS 10.13, *) {
            sidebarControlBackground.layer?.cornerCurve = .continuous
        }
        navControlBackground.wantsLayer = true
        navControlBackground.layer?.cornerRadius = radius
        if #available(macOS 10.13, *) {
            navControlBackground.layer?.cornerCurve = .continuous
        }
        sidebarToggleButton.setCornerRadius(radius)
        sidebarMenuButton.setCornerRadius(radius)
        backButton.setCornerRadius(radius, maskedCorners: [.layerMinXMinYCorner, .layerMinXMaxYCorner])
        forwardButton.setCornerRadius(radius, maskedCorners: [.layerMaxXMinYCorner, .layerMaxXMaxYCorner])
        let edgeRadius: CGFloat
        if let metrics = toolbarScaleLastApplied {
            edgeRadius = max(0, metrics.controlHeight / 2)
        } else {
            edgeRadius = max(0, rightPanelLeftEdgeButton.bounds.height / 2)
        }
        if edgeRadius > 0 {
            rightPanelLeftEdgeButton.setCornerRadius(edgeRadius)
            rightPanelRightEdgeButton.setCornerRadius(edgeRadius)
            rightPanelLeftEdgeButtonBackground?.wantsLayer = true
            rightPanelRightEdgeButtonBackground?.wantsLayer = true
            rightPanelLeftEdgeButtonBackground?.layer?.cornerRadius = edgeRadius
            rightPanelRightEdgeButtonBackground?.layer?.cornerRadius = edgeRadius
            if #available(macOS 10.13, *) {
                rightPanelLeftEdgeButtonBackground?.layer?.cornerCurve = .continuous
                rightPanelRightEdgeButtonBackground?.layer?.cornerCurve = .continuous
            }
        }
    }

    private func updateToolbarLayoutForWindowSize() {
        updateToolbarScaleForWindowSize(reason: "legacy_update")
    }


    private func updateToolbarEmphasis() {
        enforceActiveVisualEffectState(pageControlBackground)
        updateToolbarSeparatorStyle()
        updateMenuShadow()
    }

    private func updateNavigationButtons() {
        let canGoBack = selectionHistoryIndex > 0
        let canGoForward = selectionHistoryIndex >= 0 && selectionHistoryIndex < (selectionHistory.count - 1)
        backButton.isEnabled = canGoBack
        forwardButton.isEnabled = canGoForward
        backButton.updateTint()
        forwardButton.updateTint()
    }

    private func recordSelectionHistory(for key: PaperKey, viewMode: Bool, reason: String) {
        guard !historyNavigationInProgress else { return }
        if selectionHistoryIndex >= 0, selectionHistoryIndex < selectionHistory.count {
            if selectionHistory[selectionHistoryIndex].key == key {
                if selectionHistory[selectionHistoryIndex].isShowingPDF != viewMode {
                    selectionHistory[selectionHistoryIndex].isShowingPDF = viewMode
                    uiLog("history_update index=\(selectionHistoryIndex) mode=\(viewMode) reason=\(reason)")
                }
                return
            }
        }

        if selectionHistoryIndex + 1 < selectionHistory.count {
            selectionHistory.removeSubrange((selectionHistoryIndex + 1)..<selectionHistory.count)
        }

        selectionHistory.append(SelectionHistoryEntry(key: key, isShowingPDF: viewMode))
        selectionHistoryIndex = selectionHistory.count - 1
        uiLog("history_push index=\(selectionHistoryIndex) count=\(selectionHistory.count) mode=\(viewMode) reason=\(reason)")
        updateNavigationButtons()
    }

    private func updateCurrentHistoryViewMode(_ isShowingPDF: Bool, reason: String) {
        guard selectionHistoryIndex >= 0, selectionHistoryIndex < selectionHistory.count else { return }
        if selectionHistory[selectionHistoryIndex].isShowingPDF != isShowingPDF {
            selectionHistory[selectionHistoryIndex].isShowingPDF = isShowingPDF
            uiLog("history_viewmode index=\(selectionHistoryIndex) mode=\(isShowingPDF) reason=\(reason)")
        }
    }

    private func nextHistoryIndex(from index: Int, delta: Int) -> Int? {
        var i = index + delta
        while i >= 0, i < selectionHistory.count {
            if filteredIndex(for: selectionHistory[i].key) != nil {
                return i
            }
            i += delta
        }
        return nil
    }

    private func applyHistoryEntry(at index: Int, reason: String) {
        guard index >= 0, index < selectionHistory.count else { return }
        let entry = selectionHistory[index]
        guard let targetIndex = filteredIndex(for: entry.key) else {
            uiLog("history_missing index=\(index) reason=\(reason)")
            return
        }

        historyNavigationInProgress = true
        defer { historyNavigationInProgress = false }
        selectionHistoryIndex = index
        uiLog("history_apply index=\(index) mode=\(entry.isShowingPDF) reason=\(reason)")

        if entry.isShowingPDF {
            isShowingPDF = true
            selectFilteredIndex(targetIndex, scroll: true, reason: "history-\(reason)")
        } else {
            if isShowingPDF {
                showDetailsPanel(animated: true, updateContent: false)
            }
            isShowingPDF = false
            selectFilteredIndex(targetIndex, scroll: true, reason: "history-\(reason)")
        }
        updateNavigationButtons()
    }

    private func triggerRightPanelPillTransition() {
        if !sidebarVisible && rightPanelSplitModeActive { return }
        uiLog("pill_transition_trigger")
        setSidebarVisible(false, animated: true, style: .pill)
    }

    @objc private func toggleSidebar() {
        let beforeLeft = Int(leftContainer.frame.width)
        let beforeRight = Int(rightSplitContainer.frame.width)
        uiLog("sidebar_button_click visible=\(sidebarVisible)")
        layoutLog("sidebar_toggle_enter visible=\(sidebarVisible) left=\(beforeLeft) right=\(beforeRight)")
        setSidebarVisible(!sidebarVisible, animated: true)
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            layoutLog("sidebar_toggle_exit visible=\(self.sidebarVisible) left=\(Int(self.leftContainer.frame.width)) right=\(Int(self.rightSplitContainer.frame.width))")
            self.updateLayoutDebugOverlay(reason: "sidebar_toggle")
        }
    }

    @objc private func toggleRightPanel() {
        let opening = !rightAuxPanelVisible
        ChatLatencyProbe.shared.markButtonAction(opening: opening)
        // No animations for the Chat Session panel toggle: this should feel instantaneous.
        setRightAuxPanelVisible(opening, animated: false)
    }

    @objc private func saveCurrentPaperToZotero() {
        guard let idx = selectedFilteredIndex(), idx >= 0, idx < filtered.count else {
            NSSound.beep()
            return
        }

        let paper = filtered[idx]
        let canonical = ArxivShareURL.canonicalAbsURL(from: paper.url)
        let urlString = (canonical?.absoluteString ?? paper.url).trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: urlString), !urlString.isEmpty else {
            NSSound.beep()
            return
        }

        // Minimal, reliable behavior:
        // - copy the canonical arXiv URL (so it can be pasted into Zotero)
        // - open the arXiv page (so Zotero Connector / browser translator can save it)
        paste(urlString)
        NSWorkspace.shared.open(url)
    }

    private func zoteroMonogramTemplateImage(pointSize: CGFloat, weight: NSFont.Weight) -> NSImage? {
        let ps = max(9, pointSize)
        let font = NSFont.systemFont(ofSize: ps, weight: weight)
        let attrs: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: NSColor.black,
            .kern: -0.2
        ]
        let text = NSAttributedString(string: "Z", attributes: attrs)
        let textSize = text.size()

        // Slightly larger canvas to mimic SF Symbol insets.
        let canvas = NSSize(width: ceil(max(textSize.width, ps) + 2), height: ceil(max(textSize.height, ps) + 2))
        let image = NSImage(size: canvas)
        image.isTemplate = true
        image.lockFocusFlipped(false)
        NSColor.clear.setFill()
        NSBezierPath(rect: NSRect(origin: .zero, size: canvas)).fill()
        let x = round((canvas.width - textSize.width) / 2)
        let y = round((canvas.height - textSize.height) / 2)
        text.draw(at: NSPoint(x: x, y: y))
        image.unlockFocus()
        return image
    }

    @objc private func shareCurrentPaperByEmail() {
        guard let idx = selectedFilteredIndex(), idx >= 0, idx < filtered.count else {
            NSSound.beep()
            return
        }

        let paper = filtered[idx]
        let canonical = ArxivShareURL.canonicalAbsURL(from: paper.url)
        let urlString = (canonical?.absoluteString ?? paper.url).trimmingCharacters(in: .whitespacesAndNewlines)

        guard !urlString.isEmpty else {
            NSSound.beep()
            return
        }

        let safeTitle = decodeTeXAccents(paper.title).trimmingCharacters(in: .whitespacesAndNewlines)
        let subject = safeTitle.isEmpty ? "arXiv paper" : safeTitle

        let body = mailShareBody(recipientName: recipientNameFromAppleScript, arxivAbsURL: urlString)
        let toAddressRaw = (recipientEmailFromAppleScript ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let toAddress = toAddressRaw.contains("@") ? toAddressRaw : nil

        let shareT0 = monotonicNow()
        let mailWasRunning = (mailAppRunning() != nil)
        let frontmostBefore = NSWorkspace.shared.frontmostApplication?.bundleIdentifier ?? "(none)"
        MailShareDiagnostics.log("share_click t=\(String(format: "%.3f", shareT0)) mailRunning=\(mailWasRunning) frontmost=\(frontmostBefore)")

        if MailShareDiagnostics.forceAppleScript {
            MailShareDiagnostics.log("share_force_applescript=1")
            runAppleScriptAsync(mailComposeAppleScript(subject: subject, body: body, toAddress: toAddress), label: "compose_fallback_forced")
            return
        }

        if #available(macOS 10.15, *) {
            // Prelaunch Mail without stealing focus.
            ensureMailLaunchedForShare(activates: false, completion: nil)
        }

        var attemptedService = false
        func attemptSharingServiceCompose() {
            guard let service = NSSharingService(named: .composeEmail) else { return }
            attemptedService = true
            service.subject = subject
            if let toAddress {
                service.recipients = [toAddress]
            }
            MailShareDiagnostics.log("share_compose_request via=NSSharingService")
            service.perform(withItems: [body])
        }

        attemptSharingServiceCompose()
        // One-shot: bring Mail forward and minimize viewer windows exactly once.
        runAppleScriptAsync(mailActivateAndMinimizeViewerOnceAppleScript(subject: subject), label: "activate_and_minimize_once")

        // Deterministic fallback (no repeated activate/minimize loops, to avoid visible flicker).
        let initialTimeout: TimeInterval = mailWasRunning ? 0.25 : 0.55
        DispatchQueue.main.asyncAfter(deadline: .now() + initialTimeout) {
            let frontmost1 = NSWorkspace.shared.frontmostApplication?.bundleIdentifier
            MailShareDiagnostics.log("share_check_1 frontmost=\(frontmost1 ?? "(none)") attemptedService=\(attemptedService)")

            if frontmost1 == "com.apple.mail" { return }

            MailShareDiagnostics.log("share_fallback_applescript")
            runAppleScriptAsync(mailComposeAppleScript(subject: subject, body: body, toAddress: toAddress), label: "compose_fallback")
        }
    }

    private func updateRightAuxToggleButtonAppearance() {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        defer { CATransaction.commit() }
        // Existing toolbar convention: subtle accent glow when a toggle is active.
        if rightAuxPanelVisible {
            rightPanelLeftEdgeButton.restingGlowColor = resolvedSystemColor(.controlAccentColor).withAlphaComponent(0.55)
        } else {
            rightPanelLeftEdgeButton.restingGlowColor = nil
        }
        rightPanelLeftEdgeButton.updateTint()
        // Avoid doing potentially expensive glass invalidation synchronously on the input path.
        DispatchQueue.main.async { [weak self] in
            self?.rightPanelLeftEdgeButton.invalidateLiquidGlass(reason: "right_aux_toggle")
        }
    }

    private func clampRightAuxDividerPosition(_ proposedPosition: CGFloat) -> CGFloat {
        // Divider between [rightCompositeContainer] and [rightAuxContainer].
        let total = rightSplitView.bounds.width
        let divider = rightSplitView.dividerThickness
        let maxPrimaryNoNegativeAux = max(0, total - divider)
        let minPrimary = min(minRightPanelWidth, maxPrimaryNoNegativeAux)
        let minAux = minRightAuxPanelWidth

        // If the window is too small to satisfy both mins simultaneously, prioritize
        // non-negative widths (aux can shrink below its nominal min).
        let maxPrimaryFromAuxMin = total - divider - minAux
        let maxPrimary: CGFloat
        if maxPrimaryFromAuxMin >= minPrimary {
            maxPrimary = min(maxPrimaryNoNegativeAux, maxPrimaryFromAuxMin)
        } else {
            maxPrimary = maxPrimaryNoNegativeAux
        }
        return min(max(proposedPosition, minPrimary), maxPrimary)
    }

    private func rightAuxPanelWidth() -> CGFloat {
        guard rightAuxPanelVisible, rightSplitView.subviews.count >= 2 else { return 0 }
        let total = rightSplitView.bounds.width
        let divider = rightSplitView.dividerThickness
        let primary = rightCompositeContainer.frame.width
        return max(0, total - divider - primary)
    }

    private func rightAuxTargetWidth() -> CGFloat {
        let total = rightSplitView.bounds.width
        let divider = rightSplitView.dividerThickness
        let maxAux = max(0, total - divider - minRightPanelWidth)
        if maxAux <= 0 { return 0 }
        // Default open width: ~20% of the maximum possible aux width.
        // This keeps the chat panel consistently sized on open.
        let desired = max(minRightAuxPanelWidth, maxAux * 0.20)
        return min(desired, maxAux)
    }

    private func ensureRightAuxCollapsedIfHidden() {
        guard !rightAuxPanelVisible, rightSplitView.subviews.count >= 2 else { return }
        let total = rightSplitView.bounds.width
        guard total > 2 else { return }
        let divider = rightSplitView.dividerThickness
        let collapsedPos = max(0, total - divider)
        rightSplitView.setPosition(collapsedPos, ofDividerAt: 0)
        rightSplitView.adjustSubviews()
    }

    private func setRightAuxPanelVisible(_ visible: Bool, animated: Bool) {
        guard visible != rightAuxPanelVisible else {
            updateRightAuxToggleButtonAppearance()
            return
        }

        // Ensure we never carry over any in-flight spring/timer updates while toggling.
        // Also disable implicit layer actions so the split/handle/button updates apply immediately.
        cancelRightSplitDividerSpringAnimation()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        defer { CATransaction.commit() }

        layoutLog("right_aux_toggle visible=\(visible) before outerLeft=\(Int(leftContainer.frame.width)) outerRight=\(Int(rightSplitContainer.frame.width)) innerTotal=\(Int(rightSplitView.bounds.width)) innerPrimary=\(Int(rightCompositeContainer.frame.width)) auxMounted=\(rightAuxContainer.superview != nil)")

        if visible {
            // Auto-hide the sidebar if opening chat would push it below its minimum width.
            let outerTotal = splitView.bounds.width
            let outerDivider = splitView.dividerThickness
            let requiredRightWhenChatOpen = minRightPanelWidth + rightSplitView.dividerThickness + minRightAuxPanelWidth
            let maxLeftIfChatOpens = cappedSidebarMaxWidth(forPotential: outerTotal - outerDivider - requiredRightWhenChatOpen)
            if sidebarVisible && maxLeftIfChatOpens < minSidebarWidth {
                layoutLog("right_aux_autohide_left maxLeft=\(Int(maxLeftIfChatOpens)) min=\(Int(minSidebarWidth))")
                setSidebarVisible(false, animated: false)
            }

            rightAuxPanelVisible = true
            rightAuxContainer.alphaValue = 1
            updateRightAuxToggleButtonAppearance()

            // Ensure the outer split view leaves enough space for the viewer + third panel.
            // Keep synchronous work minimal so the animation can be committed immediately.
            let maxLeft = cappedSidebarMaxWidth(forPotential: outerTotal - outerDivider - minOuterRightContainerWidth())
            if leftContainer.frame.width > maxLeft {
                splitView.setPosition(maxLeft, ofDividerAt: 0)
                splitView.adjustSubviews()
                updateSplitDividerHandleFrame()
            }

            let total = rightSplitView.bounds.width
            let divider = rightSplitView.dividerThickness
            let targetAux = rightAuxTargetWidth()
            let targetPos = clampRightAuxDividerPosition(max(0, total - divider - targetAux))
            // Force non-animated updates for the rightmost panel toggle.
            animateRightSplitDivider(to: targetPos, preset: .soft, animated: false) { [weak self] in
                guard let self else { return }
                self.lastRightAuxPanelWidth = self.rightAuxPanelWidth()
                // Do the heavier follow-up work on the next tick so the divider move can present immediately.
                DispatchQueue.main.async { [weak self] in
                    guard let self else { return }
                    self.layoutViewerAnchoredHeaderControls()
                    self.updateRightSplitDividerHandleFrame()
                    layoutLog("right_aux_open_done innerPrimary=\(Int(self.rightCompositeContainer.frame.width)) auxW=\(Int(self.rightAuxPanelWidth()))")
                }
            }
            return
        }

        // Closing: animate collapsed, then hide so it consumes zero width and intercepts no events.
	    // Capture width before collapse so reopening restores it.
	    let preCloseWidth = rightAuxPanelWidth()
	    if preCloseWidth.isFinite, preCloseWidth > 0 {
	        lastRightAuxPanelWidth = max(minRightAuxPanelWidth, preCloseWidth)
	    }
        rightAuxPanelVisible = false
        rightAuxContainer.alphaValue = 0
        updateRightAuxToggleButtonAppearance()

        let total = rightSplitView.bounds.width
        let divider = rightSplitView.dividerThickness
        let collapsedPos = max(0, total - divider)
        // Force non-animated updates for the rightmost panel toggle.
        animateRightSplitDivider(to: collapsedPos, preset: .soft, animated: false) { [weak self] in
            guard let self else { return }
            // Do the heavier follow-up work on the next tick so the collapse can present immediately.
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
	            self.layoutViewerAnchoredHeaderControls()
                self.updateRightSplitDividerHandleFrame()
                layoutLog("right_aux_close_done innerPrimary=\(Int(self.rightCompositeContainer.frame.width)) auxAlpha=\(String(format: "%.2f", self.rightAuxContainer.alphaValue))")
            }
        }
    }

    private func cancelRightSplitDividerSpringAnimation() {
        rightSplitDividerSpringToken &+= 1
        rightSplitDividerSpringTimer?.invalidate()
        rightSplitDividerSpringTimer = nil
        rightSplitDividerSpringLayer.removeAllAnimations()
    }

    private func animateRightSplitDivider(to targetPosition: CGFloat,
                                         preset: SpringPreset,
                                         animated: Bool,
                                         completion: (() -> Void)? = nil) {
        cancelRightSplitDividerSpringAnimation()
        let reduce = shouldReduceMotion || !animated
        if reduce {
            rightSplitView.setPosition(targetPosition, ofDividerAt: 0)
            rightSplitView.adjustSubviews()
            ChatLatencyProbe.shared.markAnimationCommitted()
            completion?()
            return
        }

        let from = rightCompositeContainer.frame.width
        // Immediate response: nudge divider toward target in the same runloop tick.
        let delta = targetPosition - from
        if abs(delta) > 0.5 {
            let nudgeMagnitude = max(2.0, min(18.0, abs(delta) * 0.08))
            let nudgedFrom = from + (delta >= 0 ? nudgeMagnitude : -nudgeMagnitude)
            rightSplitView.setPosition(nudgedFrom, ofDividerAt: 0)
            rightSplitView.adjustSubviews()
        }

        let fromAfterNudge = rightCompositeContainer.frame.width
        let spec = springSpec(for: preset)
        let spring = CASpringAnimation(keyPath: "position.x")
        spring.mass = spec.mass
        spring.stiffness = spec.stiffness
        spring.damping = spec.damping
        spring.initialVelocity = spec.initialVelocity
        spring.fromValue = fromAfterNudge
        spring.toValue = targetPosition
        spring.duration = min(spring.settlingDuration, spec.settleCap)
        spring.isRemovedOnCompletion = true

        rightSplitDividerSpringLayer.position = CGPoint(x: targetPosition, y: 0)
        rightSplitDividerSpringLayer.add(spring, forKey: "right_divider_spring")
        ChatLatencyProbe.shared.markAnimationCommitted()

        let duration = spring.duration
        let startTime = CACurrentMediaTime()
        rightSplitDividerSpringToken &+= 1
        let token = rightSplitDividerSpringToken

        let timer = Timer(timeInterval: 1.0 / 60.0, repeats: true) { [weak self] timer in
            guard let self, token == self.rightSplitDividerSpringToken else {
                timer.invalidate()
                return
            }
            let now = CACurrentMediaTime()
            if now - startTime >= duration {
                timer.invalidate()
                self.rightSplitView.setPosition(targetPosition, ofDividerAt: 0)
                self.rightSplitView.adjustSubviews()
                completion?()
                return
            }
            if let presentation = self.rightSplitDividerSpringLayer.presentation() {
                self.rightSplitView.setPosition(presentation.position.x, ofDividerAt: 0)
                self.rightSplitView.adjustSubviews()
            }
        }
        rightSplitDividerSpringTimer = timer
        RunLoop.main.add(timer, forMode: .common)
    }

    @objc private func showSidebarMenu() {
        presentPageMenu(anchor: sidebarMenuButton)
    }

    @objc private func showPageMenu() {
        presentPageMenu(anchor: pageMenuButton)
    }

    private func presentPageMenu(anchor: NSView) {
        let items = buildPageMenuItems()
        let activeIndex = max(0, min(currentPageIndex, max(0, paginator.pageCount - 1)))
        let selectedRow = menuRowIndex(forPageIndex: activeIndex, in: items)
        presentMenu(items: items, anchor: anchor, selectedRow: selectedRow) { [weak self] item in
            guard let self else { return }
            if item.kind == .page, let pageIndex = item.actionIndex {
                self.selectPage(pageIndex)
            }
        }
    }

    @objc private func stepToPreviousPage() {
        selectPage(currentPageIndex - 1)
    }

    @objc private func stepToNextPage() {
        selectPage(currentPageIndex + 1)
    }

    private func buildPageMenuItems() -> [MenuItem] {
        let count = max(0, paginator.pageCount)
        let activeIndex = max(0, min(currentPageIndex, max(0, count - 1)))

        guard count > 0 else { return [] }

        var items: [MenuItem] = []
        for i in 0..<count {
            let checked = (i == activeIndex)
            items.append(MenuItem(kind: .page,
                                  title: "Page \(i + 1)",
                                  isEnabled: true,
                                  isChecked: checked,
                                  actionIndex: i))
        }
        return items
    }

    private func menuRowIndex(forPageIndex index: Int, in items: [MenuItem]) -> Int? {
        items.firstIndex { $0.kind == .page && $0.actionIndex == index }
    }

    private func presentMenu(items: [MenuItem],
                             anchor: NSView,
                             selectedRow: Int?,
                             handler: @escaping (MenuItem) -> Void) {
        if !menuContainer.isHidden, menuAnchorView === anchor {
            setMenuVisible(false, animated: true)
            return
        }
        menuItems = items
        menuAnchorView = anchor
        menuSelectionHandler = handler
        menuTable.reloadData()
        if let selectedRow, selectedRow >= 0, selectedRow < items.count {
            menuTable.selectRowIndexes(IndexSet(integer: selectedRow), byExtendingSelection: false)
        } else {
            menuTable.deselectAll(nil)
        }
        layoutMenuPanel()
        setMenuVisible(true, animated: true)
    }

    @objc private func menuRowClicked() {
        let row = menuTable.clickedRow
        performMenuSelection(at: row)
    }

    private func performMenuSelection(at row: Int) {
        guard row >= 0, row < menuItems.count else { return }
        guard menuItems[row].isSelectable else { return }
        menuSelectionHandler?(menuItems[row])
        setMenuVisible(false, animated: true)
    }

    private func moveMenuSelection(_ delta: Int) {
        let selectable = menuItems.enumerated().compactMap { $0.element.isSelectable ? $0.offset : nil }
        guard !selectable.isEmpty else { return }
        let currentRow = menuTable.selectedRow
        if let idx = selectable.firstIndex(of: currentRow) {
            let nextIndex = max(0, min(selectable.count - 1, idx + delta))
            let row = selectable[nextIndex]
            menuTable.selectRowIndexes(IndexSet(integer: row), byExtendingSelection: false)
            menuTable.scrollRowToVisible(row)
            return
        }

        let row = (delta >= 0) ? selectable.first! : selectable.last!
        menuTable.selectRowIndexes(IndexSet(integer: row), byExtendingSelection: false)
        menuTable.scrollRowToVisible(row)
    }

    private func activateMenuSelection() {
        performMenuSelection(at: menuTable.selectedRow)
    }

    private func selectPage(_ index: Int) {
        let clamped = max(0, min(index, max(0, paginator.pageCount - 1)))
        guard clamped != currentPageIndex else { return }
        currentPageIndex = clamped
        updatePageControlTitle()
        updatePageStepperState()
        tableView.reloadData()
        DispatchQueue.main.async { [weak self] in
            self?.enforceSidebarWidthBounds(reason: "page_select")
        }
        let targetIndex = paginator.range(forPage: currentPageIndex).lowerBound
        if targetIndex >= 0, targetIndex < filtered.count {
            selectFilteredIndex(targetIndex, scroll: true, reason: "page-select")
        }
    }

    @objc private func suggestionClicked() {
        let row = suggestionsTable.clickedRow
        guard row >= 0, row < suggestions.count else { return }
        acceptSuggestion(at: row)
    }

    private func acceptSuggestion(at index: Int) {
        guard index >= 0, index < suggestions.count else { return }
        let suggestion = suggestions[index]
        if let filteredIndex = filteredIndex(for: suggestion.paperKey) {
            selectFilteredIndex(filteredIndex, scroll: true, reason: "suggestion")
        }
        setSuggestionsVisible(false, animated: true)
    }

    private func moveSuggestionSelection(_ delta: Int) {
        guard !suggestions.isEmpty else { return }
        let current = suggestionsTable.selectedRow
        let next: Int
        if current < 0 {
            next = delta > 0 ? 0 : (suggestions.count - 1)
        } else {
            next = max(0, min(suggestions.count - 1, current + delta))
        }
        suggestionsTable.selectRowIndexes(IndexSet(integer: next), byExtendingSelection: false)
        suggestionsTable.scrollRowToVisible(next)
        suggestionSelectionIndex = next
        refreshSuggestionTextColors()
    }

    private func acceptSuggestionSelection() {
        let row = suggestionsTable.selectedRow >= 0 ? suggestionsTable.selectedRow : 0
        acceptSuggestion(at: row)
    }

    @objc private func sidebarMenuShow() {
        setSidebarVisible(true, animated: true)
    }

    @objc private func sidebarMenuHide() {
        setSidebarVisible(false, animated: true)
    }

    fileprivate func cancelSplitDividerSpringAnimation() {
        splitDividerSpringToken &+= 1
        splitDividerSpringTimer?.invalidate()
        splitDividerSpringTimer = nil
        splitDividerSpringLayer.removeAllAnimations()
    }

    fileprivate func animateSplitViewDivider(to targetWidth: CGFloat,
                                            preset: SpringPreset,
                                            completion: (() -> Void)? = nil) {
        cancelSplitDividerSpringAnimation()
        let reduce = shouldReduceMotion
        if reduce {
            splitView.setPosition(targetWidth, ofDividerAt: 0)
            splitView.adjustSubviews()
            updateSplitDividerHandleFrame()
            completion?()
            return
        }

        let fromWidth = leftContainer.frame.width
        let spec = springSpec(for: preset)
        let spring = CASpringAnimation(keyPath: "position.x")
        spring.mass = spec.mass
        spring.stiffness = spec.stiffness
        spring.damping = spec.damping
        spring.initialVelocity = spec.initialVelocity
        spring.fromValue = fromWidth
        spring.toValue = targetWidth
        spring.duration = min(spring.settlingDuration, spec.settleCap)
        spring.isRemovedOnCompletion = true

        splitDividerSpringLayer.position = CGPoint(x: targetWidth, y: 0)
        splitDividerSpringLayer.add(spring, forKey: "divider_spring")

        let duration = spring.duration
        let startTime = CACurrentMediaTime()
        splitDividerSpringToken &+= 1
        let token = splitDividerSpringToken

        let timer = Timer(timeInterval: 1.0 / 60.0, repeats: true) { [weak self] timer in
            guard let self, token == self.splitDividerSpringToken else {
                timer.invalidate()
                return
            }
            let now = CACurrentMediaTime()
            if now - startTime >= duration {
                timer.invalidate()
                self.splitView.setPosition(targetWidth, ofDividerAt: 0)
                self.splitView.adjustSubviews()
                self.updateSplitDividerHandleFrame()
                completion?()
                return
            }
            if let presentation = self.splitDividerSpringLayer.presentation() {
                self.splitView.setPosition(presentation.position.x, ofDividerAt: 0)
                self.splitView.adjustSubviews()
                self.updateSplitDividerHandleFrame()
            }
        }
        splitDividerSpringTimer = timer
        RunLoop.main.add(timer, forMode: .common)
    }

    private func setSidebarVisible(_ visible: Bool,
                                   animated: Bool,
                                   style: SidebarTransitionStyle = .standard) {
        let wasVisible = sidebarVisible

        if !visible, style == .pill, sidebarVisible {
            let width = rightContainer.frame.width
            if width > 0 { lastRightPanelWidth = width }
        }
        sidebarVisible = visible
        persistSidebarVisibility(visible)
        updateSidebarToggleIcon()
        uiLog("sidebar_toggle visible=\(visible) animated=\(animated)")
        if visible {
            let currentWidth = leftContainer.frame.width
            if currentWidth > 12 {
                lastSidebarWidth = currentWidth
                persistSidebarWidth(currentWidth)
            }
        }

        let total = splitView.bounds.width
        let divider = splitView.dividerThickness
        let maxLeft = cappedSidebarMaxWidth(forPotential: total - divider - minOuterRightContainerWidth())
        let contentMin = desiredMinSidebarWidthForCurrentPage(maxLeft: maxLeft)
        let targetWidth: CGFloat = visible ? min(maxLeft, max(contentMin, lastSidebarWidth)) : 0
        if visible {
            persistSidebarWidth(targetWidth)
            updatePageStepperState(triggerLayout: false)
        }

        if !visible {
            allowSidebarCollapse = true
        }

        let reduce = shouldReduceMotion
        let shouldAnimate = animated && !reduce
        sidebarTransitionInProgress = true

        cancelSplitDividerSpringAnimation()

        if visible {
            if rightPanelSplitModeActive {
                setRightPanelSplitMode(false, animated: shouldAnimate, preset: .soft)
            }
        } else {
            if style == .pill {
                setRightPanelSplitMode(true, animated: shouldAnimate, preset: .soft)
            } else if rightPanelSplitModeActive {
                setRightPanelSplitMode(false, animated: false)
            }
        }

        guard shouldAnimate else {
            splitView.setPosition(targetWidth, ofDividerAt: 0)
            splitView.adjustSubviews()
            if !visible { allowSidebarCollapse = false }
            sidebarTransitionInProgress = false
            leftContainer.setAccessibilityHidden(!visible)
            layoutLeftContainerSubviews()
            updatePageStepperState(triggerLayout: false)
            return
        }

        // Smooth slide with coordinated divider handling (via SidebarAnimator).
        sidebarAnimator.prepare(leftTargetWidth: targetWidth,
                               leftOpeningFromCollapsed: (!wasVisible && visible))

        sidebarAnimator.animateLeft(show: visible, animated: true) { [weak self] in
            guard let self else { return }
            if !visible { self.allowSidebarCollapse = false }
            self.sidebarTransitionInProgress = false
            self.leftContainer.setAccessibilityHidden(!visible)
            self.updateSplitDividerHandleFrame()
            self.layoutLeftContainerSubviews()
            self.updatePageStepperState(triggerLayout: false)
        }
    }

    private func updateSidebarStateFromSplit() {
        guard didApplyInitialSidebarLayout else { return }
        guard !sidebarTransitionInProgress else { return }
        let width = leftContainer.frame.width
        if width > 12 {
            sidebarVisible = true
            lastSidebarWidth = width
            persistSidebarWidth(width)
        } else {
            sidebarVisible = false
        }
        uiLog("sidebar_split_state width=\(Int(width)) visible=\(sidebarVisible)")
        persistSidebarVisibility(sidebarVisible)
        updateSidebarToggleIcon()
    }

    @objc private func navigateBack() {
        guard let target = nextHistoryIndex(from: selectionHistoryIndex, delta: -1) else {
            uiLog("history_nav back unavailable index=\(selectionHistoryIndex)")
            return
        }
        applyHistoryEntry(at: target, reason: "back")
    }

    @objc private func navigateForward() {
        guard let target = nextHistoryIndex(from: selectionHistoryIndex, delta: 1) else {
            uiLog("history_nav forward unavailable index=\(selectionHistoryIndex)")
            return
        }
        applyHistoryEntry(at: target, reason: "forward")
    }

	    func controlTextDidBeginEditing(_ obj: Notification) {
	        if obj.object as? NSSearchField === searchField {
	            searchFocused = true
                uiLog("search_focus begin")
	            suppressRowAnimations = true
	            refreshVisibleRowDepth(animated: false)
	            updateSearchDepth(animated: true)
	            updateSuggestions(for: normalizedSearchQuery(searchField.stringValue))
	            if let editor = window?.fieldEditor(false, for: searchField) as? NSTextView {
	                let text = mainSearchForegroundColor()
	                editor.textColor = text
	                editor.insertionPointColor = text
	                var attrs = editor.typingAttributes
	                attrs[.font] = currentSearchBarTheme().font
	                attrs[.foregroundColor] = text
	                attrs[.kern] = -0.15
	                editor.typingAttributes = attrs
	                logSearchDebug("fieldEditor active textColor=\(String(describing: editor.textColor)) alpha=\(editor.alphaValue)")
	            } else {
	                logSearchDebug("fieldEditor missing")
	            }
	        } else if obj.object as? NSSearchField === rightAuxAskField {
            rightAuxAskFocused = true
            updateRightAuxAskDepth(animated: true)
            if let editor = window?.fieldEditor(false, for: rightAuxAskField) as? NSTextView {
                let text = mainSearchForegroundColor()
                editor.textColor = text
                editor.insertionPointColor = text
                var attrs = editor.typingAttributes
                attrs[.font] = leftRowTitleFont
                attrs[.foregroundColor] = text
                attrs[.kern] = -0.15
                editor.typingAttributes = attrs
            }
	        } else if obj.object as? NSSearchField === pdfFindField {
            pdfFindFocused = true
            updatePDFFindDepth(animated: true)
        }
    }

	    func controlTextDidEndEditing(_ obj: Notification) {
	        if obj.object as? NSSearchField === searchField {
	            searchFocused = false
                uiLog("search_focus end")
	            suppressRowAnimations = false
	            refreshVisibleRowDepth(animated: false)
	            updateSearchDepth(animated: true)
	            setSuggestionsVisible(false, animated: true)
	        } else if obj.object as? NSSearchField === rightAuxAskField {
            rightAuxAskFocused = false
            updateRightAuxAskDepth(animated: true)
        } else if obj.object as? NSSearchField === pdfFindField {
            pdfFindFocused = false
            updatePDFFindDepth(animated: true)
        }
    }

    func controlTextDidChange(_ obj: Notification) {
        if obj.object as? NSSearchField === searchField {
            searchChanged()
        } else if obj.object as? NSSearchField === rightAuxAskField {
            updateRightAuxAskDepth(animated: true)
        } else if obj.object as? NSSearchField === pdfFindField {
            pdfFindQueryDidChange()
        }
    }

            private func layoutLeftContainerSubviews(duringDividerDrag: Bool = false) {
            defer { updateLeftCardBackgroundFrame() }
            // Keep the panel “bezel” stable under window resize and split-view drags.
            // This method lays out subviews using explicit frames, so we must ensure the
            // container bounds we read are current before computing insets.
            if !duringDividerDrag {
                splitView.layoutSubtreeIfNeeded()
                leftContainer.layoutSubtreeIfNeeded()
                leftContentView.layoutSubtreeIfNeeded()
            }
            updatePageStepperState(triggerLayout: false)
            // Apple-like inset padding inside bordered left panel (rows go full width).
            let bounds = leftContentView.bounds
	        let topInset = PANEL_INSET + searchContainerHeight + searchContainerGap
            // Give the leftContainer a visible “bezel”: inset the content glass (table + search).
            let rowInsetX: CGFloat = PANEL_INSET
            let w = max(1, bounds.width - (2 * rowInsetX))
	        let h = max(bounds.height - PANEL_INSET - topInset, 0)
	        let ib = NSRect(
	            x: bounds.minX + rowInsetX,
	            y: bounds.minY + PANEL_INSET,
	            width: w,
	            height: h
	        )

	        // If header bar is hidden, let the table fill the space and clear caches.
	        if leftHeaderBar.isHidden {
	            headerFramesFrozen = false
	            cachedHeaderBarFrame = .zero
	            cachedHeaderLabelFrame = .zero
	            cachedHeaderRuleFrame = .zero
                let showPageStepper = !pageStepperContainer.isHidden
                let reservedStepperHeight = showPageStepper ? (pageStepperHeight + pageStepperBottomInset) : 0
                tableScroll.frame = NSRect(x: ib.minX, y: ib.minY, width: w, height: h)
                updateTableBottomInset(showPageStepper: showPageStepper)
                if showPageStepper {
                    layoutPageStepper(in: ib, tableFrame: tableScroll.frame, reservedHeight: reservedStepperHeight)
                } else {
                    pageStepperContainer.frame = .zero
                }
                layoutSearchContainer(ensureLayout: !duringDividerDrag)
	            layoutLeftTableUnderlay()
	            return
	        }

        // Compute header frames only when we have meaningful dimensions; freeze once computed.
        if !headerFramesFrozen || cachedHeaderBarFrame.width <= 0 || cachedHeaderBarFrame.height <= 0 {
            if w > 80 && h > 60 {
                let headerH: CGFloat = 26
                let ruleH: CGFloat = 1

	                let headerY = ib.maxY - headerH
	                cachedHeaderBarFrame = NSRect(x: ib.minX, y: headerY, width: w, height: headerH)
                    cachedHeaderLabelFrame = NSRect(x: leftRowTextInset, y: 3, width: w - (2 * leftRowTextInset), height: headerH - 6)
	                cachedHeaderRuleFrame = NSRect(x: ib.minX, y: headerY - ruleH, width: w, height: ruleH)
	                headerFramesFrozen = true
	            }
	        }

        // Use cached frames if available; otherwise fallback to current geometry.
        if cachedHeaderBarFrame.width > 0 && cachedHeaderBarFrame.height > 0 {
            leftHeaderBar.frame = cachedHeaderBarFrame
            leftHeaderLabel.frame = cachedHeaderLabelFrame
            leftHeaderRule.frame = cachedHeaderRuleFrame
        } else {
            let headerH: CGFloat = 26
	            let ruleH: CGFloat = 1
	            let headerY = ib.maxY - headerH
	            leftHeaderBar.frame = NSRect(x: ib.minX, y: headerY, width: w, height: headerH)
                leftHeaderLabel.frame = NSRect(x: leftRowTextInset, y: 3, width: w - (2 * leftRowTextInset), height: headerH - 6)
	            leftHeaderRule.frame = NSRect(x: ib.minX, y: headerY - ruleH, width: w, height: ruleH)
	        }

                let headerH = leftHeaderBar.frame.height
                let ruleH = leftHeaderRule.frame.height
                let showPageStepper = !pageStepperContainer.isHidden
                let reservedStepperHeight = showPageStepper ? (pageStepperHeight + pageStepperBottomInset) : 0
                let tableHeight = max(0, h - headerH - ruleH)
                tableScroll.frame = NSRect(x: ib.minX, y: ib.minY, width: w, height: tableHeight)
                updateTableBottomInset(showPageStepper: showPageStepper)
                if showPageStepper {
                    layoutPageStepper(in: ib, tableFrame: tableScroll.frame, reservedHeight: reservedStepperHeight)
                } else {
                    pageStepperContainer.frame = .zero
                }
                layoutSearchContainer(ensureLayout: !duringDividerDrag)
		        layoutLeftTableUnderlay()
		    }

    private func layoutPageStepper(in insetBounds: NSRect, tableFrame: NSRect, reservedHeight: CGFloat) {
        guard !pageStepperContainer.isHidden, reservedHeight > 0 else { return }

        let buttonSize = pageStepperButtonSize
        let height = pageStepperHeight
        let width = (2 * buttonSize) + pageStepperButtonSpacing + (2 * pageStepperHorizontalPadding)

        // Anchor the stepper to the bottom of the left card instead of near the header.
        let y = insetBounds.minY + pageStepperBottomInset
        let x = insetBounds.midX - (width / 2)
        let frame = NSRect(x: round(x), y: round(y), width: width, height: height)

        pageStepperContainer.frame = frame
        pageStepperBackground.frame = pageStepperContainer.bounds
        if let layer = pageStepperBackground.layer {
            let radius = height / 2
            layer.cornerRadius = radius
            if #available(macOS 10.13, *) {
                layer.cornerCurve = .continuous
            }
        }

        let buttonY = round((height - buttonSize) / 2)
        pagePrevButton.frame = NSRect(
            x: pageStepperHorizontalPadding,
            y: buttonY,
            width: buttonSize,
            height: buttonSize
        )
        pageNextButton.frame = NSRect(
            x: frame.width - pageStepperHorizontalPadding - buttonSize,
            y: buttonY,
            width: buttonSize,
            height: buttonSize
        )
    }

    private func updateTableBottomInset(showPageStepper: Bool) {
        let bottomInset = PANEL_INSET + (showPageStepper ? (pageStepperHeight + pageStepperBottomInset) : 0)
        tableScroll.contentInsets = NSEdgeInsets(top: PANEL_INSET, left: 0, bottom: bottomInset, right: 0)
    }

    private func leftListContentContract(in bounds: NSRect) -> (CGFloat, CGFloat) {
        guard let root = searchContainer.superview else { return (0, max(1, bounds.width)) }
        let contentFrameInRoot = leftContentView.convert(leftContentView.bounds, to: root)
        let contractXInRoot = contentFrameInRoot.minX + PANEL_INSET
        let contractWInRoot = max(contentFrameInRoot.width - (2 * PANEL_INSET), 0)

        let leftX = leftContentView.convert(NSPoint(x: contractXInRoot, y: 0), from: root).x
        let rightX = leftContentView.convert(NSPoint(x: contractXInRoot + contractWInRoot, y: 0), from: root).x

        let x = max(0, min(bounds.width, leftX))
        let r = max(x, min(bounds.width, rightX))
        return (x, max(1, r - x))
    }

	    private func setupLeftTableUnderlay() {
	        guard leftTableUnderlayView == nil else { return }
        let underlay = makeGlassEffectView(
            passthrough: true,
            cornerRadius: 14,
            tintColor: leftTableUnderlayTintColor(),
            style: .regular,
            fallbackMaterial: .sidebar,
            fallbackBlending: .withinWindow,
            fallbackState: .active,
            emphasized: true
        )
	        underlay.translatesAutoresizingMaskIntoConstraints = true
	        underlay.wantsLayer = true
	        underlay.layer?.masksToBounds = true
	        if #available(macOS 10.13, *) {
	            underlay.layer?.cornerCurve = .continuous
	        }

            ensureEmbeddedSearchOrnaments(on: underlay)

	        leftContentView.addSubview(underlay, positioned: .below, relativeTo: tableScroll)
	        leftTableUnderlayView = underlay
	        layoutLeftTableUnderlay()
	    }

			    private func layoutLeftTableUnderlay() {
			        guard let underlay = leftTableUnderlayView else { return }
        var frame = tableScroll.frame
        let desiredHeight = min(
            frame.height,
            tableScroll.contentInsets.top + leftTableContentHeight() + leftTableUnderlayBottomPadding
        )

        frame.origin.y = frame.maxY - desiredHeight
        frame.size.height = desiredHeight
        underlay.frame = frame
			        let radius: CGFloat = 14
			        underlay.layer?.cornerRadius = radius
			        if #available(macOS 26.0, *), let glass = underlay as? NSGlassEffectView {
			            glass.cornerRadius = radius
			            glass.tintColor = leftTableUnderlayTintColor()
			        }
            updateEmbeddedSearchOrnaments(underlay, cornerRadius: radius)
			    }

		private func leftTableContentHeight() -> CGFloat {
			let rows = tableView.numberOfRows
			guard rows > 0 else { return 0 }
			var height: CGFloat = 0
			for row in 0..<rows {
				height += tableView(tableView, heightOfRow: row)
			}
			return height
		}

    private func setupTable() {
        let col = NSTableColumn(identifier: .init("left"))
        col.title = ""
        col.resizingMask = []
        tableView.addTableColumn(col)
        tableView.headerView = nil

        tableView.dataSource = self
        tableView.delegate = self

        if #available(macOS 11.0, *) {
            tableView.style = .fullWidth
        }
        tableView.usesAlternatingRowBackgroundColors = false
        tableView.focusRingType = .none
        tableView.allowsEmptySelection = true
        tableView.allowsMultipleSelection = false
        tableView.selectionHighlightStyle = .none
        tableView.backgroundColor = .clear

        tableView.target = self
        tableView.action = #selector(singleClick)
        tableView.doubleAction = #selector(doubleClick)

        tableView.usesAutomaticRowHeights = false
        tableView.intercellSpacing = NSSize(width: 0, height: 0)
        // Disable automatic column sizing; width is driven by layout.
        tableView.columnAutoresizingStyle = .noColumnAutoresizing

        tableScroll.drawsBackground = false
        tableScroll.backgroundColor = .clear
        tableScroll.hasHorizontalScroller = true
        tableScroll.horizontalScrollElasticity = .automatic
        tableScroll.verticalScrollElasticity = .none
        tableScroll.usesPredominantAxisScrolling = false
        // Keep the row “glass tabs” aligned to the same right edge as the search bar by avoiding
        // any reserved scroller gutter in the left panel.
        tableScroll.hasVerticalScroller = false
        tableScroll.autohidesScrollers = true
        tableScroll.scrollerStyle = .overlay
        tableScroll.usesPredominantAxisScrolling = true
        tableScroll.automaticallyAdjustsContentInsets = false
        // Horizontal extent is controlled by layoutLeftContainerSubviews() to respect the panel inset.
        tableScroll.contentInsets = NSEdgeInsets(top: PANEL_INSET, left: 0, bottom: PANEL_INSET, right: 0)

        tableScroll.documentView = tableView
        tableScroll.contentView.postsBoundsChangedNotifications = true

        rowMenu.delegate = self
        tableView.menu = rowMenu
    }

    private func setupPageStepper() {
        pageStepperContainer.translatesAutoresizingMaskIntoConstraints = true
        pageStepperContainer.wantsLayer = false
        pageStepperContainer.isHidden = true

        // Keep the pager fully transparent—only the chevron icons should be visible.
        let background = makeGlassEffectView(
            passthrough: true,
            cornerRadius: pageStepperHeight / 2,
            tintColor: .clear,
            style: .regular,
            fallbackMaterial: .sidebar,
            fallbackBlending: .withinWindow,
            fallbackState: .active,
            emphasized: false
        )
        background.isHidden = true
        background.alphaValue = 0
        background.translatesAutoresizingMaskIntoConstraints = true
        background.wantsLayer = true
        background.layer?.masksToBounds = true
        pageStepperBackground = background
        pageStepperContainer.addSubview(background)

        let symbolConfig = NSImage.SymbolConfiguration(pointSize: 13 * toolbarControlScaleBase, weight: .regular)
        pagePrevButton.image = NSImage(systemSymbolName: "chevron.left", accessibilityDescription: nil)?.withSymbolConfiguration(symbolConfig)
        pageNextButton.image = NSImage(systemSymbolName: "chevron.right", accessibilityDescription: nil)?.withSymbolConfiguration(symbolConfig)
        pagePrevButton.target = self
        pageNextButton.target = self
        pagePrevButton.action = #selector(stepToPreviousPage)
        pageNextButton.action = #selector(stepToNextPage)
        pagePrevButton.restingGlowColor = nil
        pageNextButton.restingGlowColor = nil
        // Bottom-left pager: force white chevrons (independent of appearance).
        pagePrevButton.restingTintColor = .white
        pageNextButton.restingTintColor = .white
        pagePrevButton.layer?.backgroundColor = NSColor.clear.cgColor
        pageNextButton.layer?.backgroundColor = NSColor.clear.cgColor
        pagePrevButton.updateTint()
        pageNextButton.updateTint()

        pagePrevButton.translatesAutoresizingMaskIntoConstraints = true
        pageNextButton.translatesAutoresizingMaskIntoConstraints = true
        pageStepperContainer.addSubview(pagePrevButton)
        pageStepperContainer.addSubview(pageNextButton)
    }

	    private func setupRightPanelChrome() {
	        rightContainer = makePrimaryGlassPanelChrome()
	        embedContentView(rightContentView, into: rightContainer)
	    }

    private func makePrimaryGlassPanelChrome() -> NSView {
        // The PDF viewer container should be *opaque* and non-glassy.
        // Use a plain layer-backed view (no vibrancy/blur) with a solid white fill.
        let panel = NSView(frame: .zero)
        panel.translatesAutoresizingMaskIntoConstraints = false
        panel.wantsLayer = true
        panel.layer?.cornerRadius = PANEL_CORNER_RADIUS
        panel.layer?.backgroundColor = NSColor.white.cgColor
        panel.layer?.borderWidth = PANEL_BORDER_WIDTH
        panel.layer?.borderColor = resolvedSystemColor(.separatorColor).cgColor
        panel.layer?.masksToBounds = true
        if #available(macOS 10.13, *) {
            panel.layer?.cornerCurve = .continuous
        }
        return panel
    }

    private func setupRightAuxPanelChrome() {
        // Third panel (chat-session) must match the left-hand panel glass exactly.
        var cardConfig = baseLiquidGlassConfig()
        cardConfig.cornerRadius = PANEL_CORNER_RADIUS
        cardConfig.tint = panelClearGlassTintColor()
        let card = GlassCardKit.makeGlassCard(config: cardConfig) { [weak self] rectInWindow, scale in
            self?.captureWindowBackgroundRegion(in: rectInWindow, scale: scale)
        }
        rightAuxContainer = card
        rightAuxContainer.translatesAutoresizingMaskIntoConstraints = true
        rightAuxContainer.wantsLayer = true
        rightAuxContainer.layer?.cornerRadius = PANEL_CORNER_RADIUS
        rightAuxContainer.layer?.backgroundColor = NSColor.clear.cgColor
        rightAuxContainer.layer?.masksToBounds = true
        embedContentView(rightAuxContentView, into: rightAuxContainer)
        rightAuxContentView.wantsLayer = false

        // Share-style black/glassy border ornaments for the rightmost (Chat Session) glass card.
        rightAuxCardOrnamentOverlay.cornerRadius = PANEL_CORNER_RADIUS
        rightAuxCardOrnamentOverlay.frame = rightAuxContainer.bounds
        rightAuxCardOrnamentOverlay.autoresizingMask = [.width, .height]
        rightAuxCardOrnamentOverlay.translatesAutoresizingMaskIntoConstraints = true
        if rightAuxCardOrnamentOverlay.superview == nil {
            rightAuxContainer.addSubview(rightAuxCardOrnamentOverlay, positioned: .above, relativeTo: rightAuxContentView)
        }

        // Header (Chat Session + underline)
        rightAuxHeaderLabel.translatesAutoresizingMaskIntoConstraints = true
        rightAuxHeaderLabel.autoresizingMask = []
        rightAuxHeaderLabel.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        rightAuxHeaderLabel.textColor = leftHeaderTextColor()
        rightAuxHeaderLabel.alignment = .left
        rightAuxHeaderLabel.backgroundColor = .clear
        rightAuxHeaderLabel.lineBreakMode = .byTruncatingTail

        rightAuxHeaderRule.wantsLayer = true
        rightAuxHeaderRule.layer?.backgroundColor = resolvedSystemColor(.separatorColor).cgColor
        rightAuxHeaderRule.autoresizingMask = []

        if rightAuxHeaderLabel.superview == nil {
            rightAuxContentView.addSubview(rightAuxHeaderLabel)
        }
        if rightAuxHeaderRule.superview == nil {
            rightAuxContentView.addSubview(rightAuxHeaderRule)
        }

        setupRightAuxAskBar()
    }

    private func setupRightAuxAskBar() {
        rightAuxAskField.delegate = self
        rightAuxAskField.translatesAutoresizingMaskIntoConstraints = false
        rightAuxAskField.controlSize = .large
        rightAuxAskField.wantsLayer = false
        rightAuxAskField.refusesFirstResponder = false

        rightAuxAskSendIconView.translatesAutoresizingMaskIntoConstraints = false
        rightAuxAskSendIconView.imageAlignment = .alignCenter
        rightAuxAskSendIconView.imageScaling = .scaleProportionallyDown
        rightAuxAskSendIconView.wantsLayer = false

        // Chat input should match the main search bar look (tint + typography).
        let searchForeground = mainSearchForegroundColor()
        applySearchFieldTheme(rightAuxAskField,
                              placeholder: "Ask",
                              textColor: searchForeground,
                              placeholderColor: searchForeground,
                              iconColor: searchForeground)
        removeSearchFieldIcons(rightAuxAskField)

        // Right-aligned send icon (Apple-like) on the ask bar.
        updateRightAuxAskSendIconAppearance()

        // Typography: match the publication table row text size.
        let chatFont = leftRowTitleFont
        rightAuxAskField.font = chatFont
        if let cell = rightAuxAskField.cell as? NSSearchFieldCell {
            cell.font = chatFont
        }
        let placeholderStyle = NSMutableParagraphStyle()
        placeholderStyle.lineBreakMode = .byClipping

        let placeholderColor = searchForeground
        let italicFont = (NSFontManager.shared.convert(chatFont, toHaveTrait: .italicFontMask))
        let placeholderFont = italicFont

        let askPlaceholder = NSAttributedString(
            string: "Ask...",
            attributes: [
                .foregroundColor: placeholderColor,
                .font: placeholderFont,
                .kern: -0.15,
                .paragraphStyle: placeholderStyle
            ]
        )
        rightAuxAskField.placeholderAttributedString = askPlaceholder
        if let cell = rightAuxAskField.cell as? NSSearchFieldCell {
            cell.placeholderAttributedString = askPlaceholder
        }

        // Glass capsule: reuse embedded search bar glass tint.
        let theme = currentSearchBarTheme()
        rightAuxAskBackground = makeGlassEffectView(
            passthrough: true,
            cornerRadius: 0,
            tintColor: nil,
            style: .regular,
            fallbackMaterial: theme.fallbackMaterial,
            fallbackBlending: theme.fallbackBlending,
            fallbackState: theme.fallbackState,
            emphasized: theme.emphasized
        )
        applyEmbeddedSearchBarTheme(to: rightAuxAskBackground)

        rightAuxAskOutlineLayer.fillColor = NSColor.clear.cgColor
        rightAuxAskOutlineLayer.strokeColor = NSColor.white.withAlphaComponent(0.16).cgColor
        rightAuxAskOutlineLayer.lineWidth = SPOTLIGHT_SEARCH_OUTLINE_WIDTH
        rightAuxAskOutlineLayer.lineJoin = .round
        rightAuxAskOutlineLayer.lineCap = .round
        rightAuxAskOutlineLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0

        rightAuxAskInnerOutlineLayer.fillColor = NSColor.clear.cgColor
        rightAuxAskInnerOutlineLayer.strokeColor = NSColor.white.withAlphaComponent(0.07).cgColor
        rightAuxAskInnerOutlineLayer.lineWidth = SPOTLIGHT_SEARCH_OUTLINE_WIDTH
        rightAuxAskInnerOutlineLayer.lineJoin = .round
        rightAuxAskInnerOutlineLayer.lineCap = .round
        rightAuxAskInnerOutlineLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0

        if #available(macOS 10.14, *) {
            rightAuxAskCenterGlowLayer.type = .radial
        }
        rightAuxAskCenterGlowLayer.startPoint = CGPoint(x: 0.5, y: 0.5)
        rightAuxAskCenterGlowLayer.endPoint = CGPoint(x: 1.0, y: 1.0)
        rightAuxAskCenterGlowLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0

        rightAuxAskHighlightLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
        rightAuxAskFalloffLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
        rightAuxAskHighlightLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
        rightAuxAskHighlightLayer.endPoint = CGPoint(x: 0.5, y: 0.0)
        rightAuxAskFalloffLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
        rightAuxAskFalloffLayer.endPoint = CGPoint(x: 0.5, y: 0.0)

        rightAuxAskBackground.layer?.addSublayer(rightAuxAskCenterGlowLayer)
        rightAuxAskBackground.layer?.addSublayer(rightAuxAskHighlightLayer)
        rightAuxAskBackground.layer?.addSublayer(rightAuxAskFalloffLayer)
        rightAuxAskBackground.layer?.addSublayer(rightAuxAskInnerOutlineLayer)
        rightAuxAskBackground.layer?.addSublayer(rightAuxAskOutlineLayer)
        rightAuxAskBackground.layer?.mask = rightAuxAskMaskLayer

        rightAuxAskContainer.translatesAutoresizingMaskIntoConstraints = true
        rightAuxAskContainer.wantsLayer = true
        rightAuxAskContainer.layer?.backgroundColor = NSColor.clear.cgColor
        rightAuxAskContainer.focusTarget = rightAuxAskField
        rightAuxAskContainer.onAppearanceChanged = { [weak self] in
            self?.updateRightAuxAskSeparatorStyle()
            self?.updateRightAuxAskDepth(animated: false)
            self?.updateRightAuxAskSendIconAppearance()
        }

        rightAuxAskSeparatorView.translatesAutoresizingMaskIntoConstraints = true
        rightAuxAskSeparatorView.autoresizingMask = []
        rightAuxAskSeparatorView.wantsLayer = true
        rightAuxAskSeparatorView.layer?.masksToBounds = true
        rightAuxAskSeparatorView.layer?.borderWidth = 1.0
        rightAuxAskSeparatorView.layer?.shadowOffset = .zero
        rightAuxAskSeparatorView.layer?.shadowRadius = 10
        rightAuxAskSeparatorView.layer?.shadowOpacity = 0.18

        rightAuxAskSeparatorGradient.startPoint = CGPoint(x: 0.0, y: 0.5)
        rightAuxAskSeparatorGradient.endPoint = CGPoint(x: 1.0, y: 0.5)
        rightAuxAskSeparatorGradient.locations = [0.0, 0.5, 1.0]

        rightAuxAskSeparatorHighlight.startPoint = CGPoint(x: 0.0, y: 0.5)
        rightAuxAskSeparatorHighlight.endPoint = CGPoint(x: 1.0, y: 0.5)
        rightAuxAskSeparatorHighlight.locations = [0.0, 0.5, 1.0]

        if let sepLayer = rightAuxAskSeparatorView.layer {
            sepLayer.addSublayer(rightAuxAskSeparatorGradient)
            sepLayer.addSublayer(rightAuxAskSeparatorHighlight)
        }
        updateRightAuxAskSeparatorStyle()
        if rightAuxAskSeparatorView.superview == nil {
            rightAuxContentView.addSubview(rightAuxAskSeparatorView)
        }
        rightAuxAskContainer.addSubview(rightAuxAskBackground)
        rightAuxAskContainer.addSubview(rightAuxAskContentView)

        rightAuxAskContentView.translatesAutoresizingMaskIntoConstraints = false
        rightAuxAskContentView.wantsLayer = false
        rightAuxAskContentView.addSubview(rightAuxAskField)
        rightAuxAskContentView.addSubview(rightAuxAskSendIconView)

        rightAuxContentView.addSubview(rightAuxAskContainer)

        let minWidth = rightAuxAskField.widthAnchor.constraint(greaterThanOrEqualToConstant: searchFieldMinimumWidth)
        minWidth.priority = .defaultLow
        NSLayoutConstraint.activate([
            rightAuxAskBackground.leadingAnchor.constraint(equalTo: rightAuxAskContainer.leadingAnchor),
            rightAuxAskBackground.trailingAnchor.constraint(equalTo: rightAuxAskContainer.trailingAnchor),
            rightAuxAskBackground.topAnchor.constraint(equalTo: rightAuxAskContainer.topAnchor),
            rightAuxAskBackground.bottomAnchor.constraint(equalTo: rightAuxAskContainer.bottomAnchor),

            rightAuxAskContentView.leadingAnchor.constraint(equalTo: rightAuxAskContainer.leadingAnchor, constant: searchContentInsetX),
            rightAuxAskContentView.trailingAnchor.constraint(equalTo: rightAuxAskContainer.trailingAnchor, constant: -searchContentInsetX),
            rightAuxAskContentView.topAnchor.constraint(equalTo: rightAuxAskContainer.topAnchor, constant: searchContentInsetY),
            rightAuxAskContentView.bottomAnchor.constraint(equalTo: rightAuxAskContainer.bottomAnchor, constant: -searchContentInsetY),

            rightAuxAskSendIconView.centerYAnchor.constraint(equalTo: rightAuxAskContentView.centerYAnchor),
            rightAuxAskSendIconView.leadingAnchor.constraint(equalTo: rightAuxAskContentView.leadingAnchor),
            rightAuxAskSendIconView.widthAnchor.constraint(equalToConstant: 18),
            rightAuxAskSendIconView.heightAnchor.constraint(equalToConstant: 18),

            rightAuxAskField.centerYAnchor.constraint(equalTo: rightAuxAskContentView.centerYAnchor),
            rightAuxAskField.leadingAnchor.constraint(equalTo: rightAuxAskSendIconView.trailingAnchor, constant: 8),
            rightAuxAskField.trailingAnchor.constraint(equalTo: rightAuxAskContentView.trailingAnchor),
            rightAuxAskField.heightAnchor.constraint(equalToConstant: 28),
            minWidth
        ])

        installRightAuxAskTracking()
        updateRightAuxAskDepth(animated: false)
    }

    private func updateRightAuxAskSendIconAppearance() {
        let tint = mainSearchForegroundColor()
        let iconPointSize: CGFloat = 14
        let config = NSImage.SymbolConfiguration(pointSize: iconPointSize, weight: .regular)
        let base = NSImage(systemSymbolName: "paperplane.fill", accessibilityDescription: "Send") ?? NSImage()
        let icon = base.withSymbolConfiguration(config) ?? base
        icon.isTemplate = true
        rightAuxAskSendIconView.image = icon
        if #available(macOS 10.14, *) {
            rightAuxAskSendIconView.contentTintColor = tint
        }
    }

    private func updateRightAuxAskSeparatorStyle() {
        let base = resolvedSystemColor(.labelColor)
        let glassLine = base.withAlphaComponent(0.20)
        let edgeFade = base.withAlphaComponent(0.0)
        let highlight = base.withAlphaComponent(0.32)
        let border = base.withAlphaComponent(0.09)

        rightAuxAskSeparatorView.layer?.backgroundColor = base.withAlphaComponent(0.05).cgColor
        rightAuxAskSeparatorView.layer?.borderColor = border.cgColor
        rightAuxAskSeparatorView.layer?.shadowColor = highlight.cgColor

        rightAuxAskSeparatorGradient.colors = [edgeFade.cgColor, glassLine.cgColor, edgeFade.cgColor]
        rightAuxAskSeparatorHighlight.colors = [NSColor.white.withAlphaComponent(0.0).cgColor,
                                               NSColor.white.withAlphaComponent(0.16).cgColor,
                                               NSColor.white.withAlphaComponent(0.0).cgColor]
    }

    private func removeSearchFieldIcons(_ field: NSSearchField) {
        guard let cell = field.cell as? NSSearchFieldCell else { return }
        cell.searchButtonCell = nil
        cell.cancelButtonCell = nil
    }

    private func installRightAuxAskTracking() {
        if let tracking = rightAuxAskTracking {
            rightAuxAskField.removeTrackingArea(tracking)
        }
        let opts: NSTrackingArea.Options = [.mouseEnteredAndExited, .activeAlways, .inVisibleRect]
        let area = NSTrackingArea(rect: rightAuxAskField.bounds, options: opts, owner: self, userInfo: nil)
        rightAuxAskField.addTrackingArea(area)
        rightAuxAskTracking = area
    }

    private func updateRightAuxAskDepth(animated: Bool) {
        let focused = rightAuxAskFocused
        let hovered = rightAuxAskHover
        let hasQuery = !rightAuxAskField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let engaged = focused || hasQuery

        updateEmbeddedSearchAppearance(
            background: rightAuxAskBackground,
            focused: focused,
            hovered: hovered,
            engaged: engaged,
            outlineLayer: rightAuxAskOutlineLayer,
            innerOutlineLayer: rightAuxAskInnerOutlineLayer,
            highlightLayer: rightAuxAskHighlightLayer,
            falloffLayer: rightAuxAskFalloffLayer,
            centerGlowLayer: rightAuxAskCenterGlowLayer,
            animated: animated
        )
        enforceActiveVisualEffectState(rightAuxAskBackground)
    }

    private func updateIMessageGlassFieldAppearance(engaged: Bool,
                                                   hovered: Bool,
                                                   outlineLayer: CAShapeLayer,
                                                   innerOutlineLayer: CAShapeLayer,
                                                   highlightLayer: CAGradientLayer,
                                                   innerShadowLayer: CAGradientLayer,
                                                   centerGlowLayer: CAGradientLayer,
                                                   theme: IMessageGlassFieldTheme,
                                                   animated: Bool) {
        let reduce = shouldReduceMotion || !animated
        let strokeBoost: CGFloat = engaged ? 1.10 : (hovered ? 1.05 : 1.0)
        let highlightBoost: CGFloat = engaged ? 1.10 : (hovered ? 1.06 : 1.0)
        let innerShadowBoost: CGFloat = engaged ? 1.05 : 1.0

        CATransaction.begin()
        if reduce {
            CATransaction.setDisableActions(true)
        } else {
            CATransaction.setAnimationDuration(0.14)
            CATransaction.setAnimationTimingFunction(CAMediaTimingFunction(name: .easeInEaseOut))
        }

        outlineLayer.strokeColor = NSColor.white.withAlphaComponent(theme.strokeAlpha * strokeBoost).cgColor
        innerOutlineLayer.strokeColor = NSColor.white.withAlphaComponent(theme.innerStrokeAlpha * strokeBoost).cgColor

        // Specular top highlight: faint (top-to-bottom) white gradient.
        highlightLayer.locations = [0.0, 1.0]
        highlightLayer.colors = [
            NSColor.white.withAlphaComponent(theme.highlightTopAlpha * highlightBoost).cgColor,
            NSColor.clear.cgColor
        ]

        // Extremely subtle inner shadow (pressed glass curvature), bottom-weighted.
        innerShadowLayer.locations = [0.0, 1.0]
        innerShadowLayer.colors = [
            NSColor.clear.cgColor,
            NSColor.black.withAlphaComponent(theme.innerShadowBottomAlpha * innerShadowBoost).cgColor
        ]

        // Keep any extra glow essentially off (iMessage reads clean, not "Spotlight" center-glow).
        centerGlowLayer.locations = [0.0, 1.0]
        centerGlowLayer.colors = [
            NSColor.white.withAlphaComponent(0.0).cgColor,
            NSColor.clear.cgColor
        ]

        CATransaction.commit()
    }

    private func setupRightCompositeContainer() {
        rightCompositeContainer.translatesAutoresizingMaskIntoConstraints = true
        rightCompositeContainer.wantsLayer = false

        // These subviews are sized via explicit Auto Layout constraints; disable
        // autoresizing-mask translation to avoid AppKit creating huge placeholder
        // constraints (which can trigger NSLayoutConstraintNumberExceedsLimit).
        rightContainer.translatesAutoresizingMaskIntoConstraints = false
        rightCompositeContainer.addSubview(rightContainer)

        let secondary = makeRightSecondaryGlassCard()
        rightSecondaryContainer = secondary
        secondary.translatesAutoresizingMaskIntoConstraints = false
        rightCompositeContainer.addSubview(secondary)
        secondary.isHidden = true

        NSLayoutConstraint.activate([
            rightContainer.leadingAnchor.constraint(equalTo: rightCompositeContainer.leadingAnchor),
            rightContainer.topAnchor.constraint(equalTo: rightCompositeContainer.topAnchor),
            rightContainer.bottomAnchor.constraint(equalTo: rightCompositeContainer.bottomAnchor),

            secondary.topAnchor.constraint(equalTo: rightCompositeContainer.topAnchor),
            secondary.bottomAnchor.constraint(equalTo: rightCompositeContainer.bottomAnchor),
            secondary.trailingAnchor.constraint(equalTo: rightCompositeContainer.trailingAnchor),
        ])

        rightPrimaryTrailingConstraint = rightContainer.trailingAnchor.constraint(equalTo: rightCompositeContainer.trailingAnchor)
        rightPrimaryTrailingConstraint?.isActive = true

        rightPrimaryWidthConstraint = rightContainer.widthAnchor.constraint(equalToConstant: 0)
        rightPrimaryWidthConstraint?.isActive = false

        rightSecondaryLeadingConstraint = secondary.leadingAnchor.constraint(equalTo: rightContainer.trailingAnchor)
        rightSecondaryLeadingConstraint?.isActive = false

        rightSecondaryWidthConstraint = secondary.widthAnchor.constraint(equalToConstant: 0)
        rightSecondaryWidthConstraint?.isActive = true
    }

    private func setupRightSplitContainer() {
        // The outer split view uses `addArrangedSubview`, so this container must be Auto Layout–managed.
        // Leaving autoresizing-mask translation enabled can create placeholder constraints that pin widths.
        rightSplitContainer.translatesAutoresizingMaskIntoConstraints = false
        rightSplitContainer.wantsLayer = false

        rightSplitView.isVertical = true
        rightSplitView.dividerStyle = .thin
        rightSplitView.gap = PANEL_INTER_CARD_GAP
        // Keep the divider hit area but remove the hard line.
        rightSplitView.setValue(NSColor.clear, forKey: "dividerColor")
        rightSplitView.delegate = self
        // Important: rightSplitContainer participates in Auto Layout, so do NOT rely on an initial
        // frame + autoresizing-mask translation here; at setup time the bounds can be zero, which
        // pins the split view to a zero-size layout.
        rightSplitView.translatesAutoresizingMaskIntoConstraints = false

        // Pre-mount both panes to eliminate toggle-time view construction/mounting.
        if rightCompositeContainer.superview != nil { rightCompositeContainer.removeFromSuperview() }
        if rightAuxContainer.superview != nil { rightAuxContainer.removeFromSuperview() }
        rightSplitView.addArrangedSubview(rightCompositeContainer)
        rightSplitView.addArrangedSubview(rightAuxContainer)
        // Keep the aux view mounted and not hidden so toggling doesn't trigger hide/unhide work.
        // When “closed” we collapse its width to ~0 and set alpha to 0.
        rightAuxContainer.isHidden = false
        rightAuxContainer.alphaValue = 0
        rightSplitContainer.addSubview(rightSplitView)

        NSLayoutConstraint.activate([
            rightSplitView.leadingAnchor.constraint(equalTo: rightSplitContainer.leadingAnchor),
            rightSplitView.trailingAnchor.constraint(equalTo: rightSplitContainer.trailingAnchor),
            rightSplitView.topAnchor.constraint(equalTo: rightSplitContainer.topAnchor),
            rightSplitView.bottomAnchor.constraint(equalTo: rightSplitContainer.bottomAnchor),
        ])

        rightAuxPanelVisible = false
        ensureRightAuxCollapsedIfHidden()
    }

    private func enforceWhitePDFBackground() {
        let bg = NSColor.white

        pdfView.wantsLayer = true
        pdfView.layer?.backgroundColor = bg.cgColor
        pdfView.backgroundColor = bg

        // IMPORTANT: Avoid forcing layer-backing on PDFKit's internal document/page views.
        // Some PDFKit internals assume view-backed drawing; making them layer-backed can
        // result in flipped/rotated output (appearing upside down and/or mirrored).
        //
        // So: only apply explicit backgrounds to safe container views (scroll/clip), and
        // use KVC backgroundColor where available without changing wantsLayer elsewhere.
        func paint(_ view: NSView) {
            if view is NSScroller { return }

            if view === pdfView {
                view.wantsLayer = true
                view.layer?.backgroundColor = bg.cgColor
            }

            if let scroll = view as? NSScrollView {
                scroll.drawsBackground = true
                scroll.backgroundColor = bg
                scroll.wantsLayer = true
                scroll.layer?.backgroundColor = bg.cgColor

                let clip = scroll.contentView
                clip.drawsBackground = true
                clip.backgroundColor = bg
                // Clip views are safe to layer-back; they don't render PDF content directly.
                clip.wantsLayer = true
                clip.layer?.backgroundColor = bg.cgColor
            } else if let clip = view as? NSClipView {
                clip.drawsBackground = true
                clip.backgroundColor = bg
                // Avoid changing wantsLayer here; NSScrollView.contentView path above covers it.
            }

            // Some PDFKit internal views respond to KVC backgroundColor.
            if view.responds(to: Selector(("setBackgroundColor:"))) {
                view.setValue(bg, forKey: "backgroundColor")
            }

            for sub in view.subviews { paint(sub) }
        }

        paint(pdfView)

        rightContainer.wantsLayer = true
    }

	    private func setupRightPanelViews() {
	        detailsWebView.setValue(false, forKey: "drawsBackground")
	        detailsWebView.wantsLayer = true
	        detailsWebView.layer?.backgroundColor = NSColor.clear.cgColor
	        detailsWebView.navigationDelegate = self
	        detailsWebView.allowsBackForwardNavigationGestures = false
		
	        // WKWebView owns an internal scroll view (enclosingScrollView is usually nil).
	        if let scroll = descendantScrollViews(in: detailsWebView).first {
	            scroll.drawsBackground = false
	            scroll.backgroundColor = NSColor.clear
	            scroll.wantsLayer = true
	            scroll.layer?.backgroundColor = NSColor.clear.cgColor
	            scroll.contentView.drawsBackground = false
	            scroll.contentView.backgroundColor = NSColor.clear
	            scroll.contentView.wantsLayer = true
	            scroll.contentView.layer?.backgroundColor = NSColor.clear.cgColor
	        }
	        applyDetailsWebViewRoundedClipping()

            // Keep PDFKit interaction intact (text selection handled by PDFKit).
            pdfView.autoScales = true
	        pdfView.displayMode = .singlePageContinuous
	        // Remove PDFKit page gutters/shadows so the PDF blends into the white panel.
	        pdfView.displaysPageBreaks = false
        pdfView.pageBreakMargins = NSEdgeInsetsZero
        pdfView.onMagnify = { [weak self] event in
            return self?.handlePDFMagnify(event) ?? false
        }

        pdfView.onAnnotateRequest = { [weak self] pointInView, page in
            self?.annotationController?.beginAnnotation(at: pointInView, page: page)
        }

        // Trackpad pinch-to-zoom (Preview-like): route magnification gesture to our anchored zoom.
        // Some environments/devices do not reliably deliver NSEvent.magnify to PDFView; a gesture
        // recognizer makes pinch support deterministic.
        if pdfMagnificationGestureRecognizer == nil {
            pdfView.allowedTouchTypes = [.indirect, .direct]
            let gr = NSMagnificationGestureRecognizer(target: self, action: #selector(handlePDFMagnificationGesture(_:)))
            pdfView.addGestureRecognizer(gr)
            pdfMagnificationGestureRecognizer = gr
        }

        pdfView.isHidden = true
        pdfView.allowsHitTesting = true
        detailsWebView.allowsHitTesting = true
        rightPDFBackgroundView.wantsLayer = true
        rightPDFBackgroundView.layer?.backgroundColor = NSColor.white.cgColor
        rightPDFBackgroundView.isHidden = true

        // Avoid autoresizing-mask translation creating huge placeholder constraints during split-view resizes.
        rightPanelContentHost.translatesAutoresizingMaskIntoConstraints = false
        rightPanelContentHost.wantsLayer = true
        rightPanelTransitionBlurView.translatesAutoresizingMaskIntoConstraints = false
        rightPanelTransitionBlurView.blendingMode = .withinWindow
        rightPanelTransitionBlurView.material = .contentBackground
        rightPanelTransitionBlurView.state = .active
        rightPanelTransitionBlurView.isEmphasized = true
        rightPanelTransitionBlurView.wantsLayer = true
        rightPanelTransitionBlurView.layer?.opacity = 0
        rightPanelTransitionBlurView.isHidden = true
        enforceActiveVisualEffectState(rightPanelTransitionBlurView)

        detailsWebView.translatesAutoresizingMaskIntoConstraints = false
        pdfView.translatesAutoresizingMaskIntoConstraints = false
		loadingOverlay.translatesAutoresizingMaskIntoConstraints = false
        pdfFindHUD.translatesAutoresizingMaskIntoConstraints = true
        rightPDFBackgroundView.translatesAutoresizingMaskIntoConstraints = true

        rightContentView.addSubview(rightPDFBackgroundView)
        rightContentView.addSubview(rightPanelContentHost)
        rightPanelContentHost.addSubview(detailsWebView)
        rightPanelContentHost.addSubview(pdfView)
        rightPanelContentHost.addSubview(rightPanelTransitionBlurView)
        annotationController = PDFAnnotationCoordinator(
            pdfView: pdfView,
            hostView: rightPanelContentHost,
            dropdownGlassFactory: { [weak self] in
                guard let self else { return AnnotationComposerViewController.makeFallbackDropdownGlass() }
                return self.makeDropdownGlassCard()
            }
        )

        NSLayoutConstraint.activate([
            // Host fills the right content view inset by the panel padding.
            rightPanelContentHost.leadingAnchor.constraint(equalTo: rightContentView.leadingAnchor, constant: PANEL_INSET),
            rightPanelContentHost.trailingAnchor.constraint(equalTo: rightContentView.trailingAnchor, constant: -PANEL_INSET),
            rightPanelContentHost.topAnchor.constraint(equalTo: rightContentView.topAnchor, constant: PANEL_INSET),
            rightPanelContentHost.bottomAnchor.constraint(equalTo: rightContentView.bottomAnchor, constant: -PANEL_INSET),

            // Content fills the host.
            detailsWebView.leadingAnchor.constraint(equalTo: rightPanelContentHost.leadingAnchor),
            detailsWebView.trailingAnchor.constraint(equalTo: rightPanelContentHost.trailingAnchor),
            detailsWebView.topAnchor.constraint(equalTo: rightPanelContentHost.topAnchor),
            detailsWebView.bottomAnchor.constraint(equalTo: rightPanelContentHost.bottomAnchor),

            pdfView.leadingAnchor.constraint(equalTo: rightPanelContentHost.leadingAnchor),
            pdfView.trailingAnchor.constraint(equalTo: rightPanelContentHost.trailingAnchor),
            pdfView.topAnchor.constraint(equalTo: rightPanelContentHost.topAnchor),
            pdfView.bottomAnchor.constraint(equalTo: rightPanelContentHost.bottomAnchor),

            rightPanelTransitionBlurView.leadingAnchor.constraint(equalTo: rightPanelContentHost.leadingAnchor),
            rightPanelTransitionBlurView.trailingAnchor.constraint(equalTo: rightPanelContentHost.trailingAnchor),
            rightPanelTransitionBlurView.topAnchor.constraint(equalTo: rightPanelContentHost.topAnchor),
            rightPanelTransitionBlurView.bottomAnchor.constraint(equalTo: rightPanelContentHost.bottomAnchor),
        ])

        installRightPanelScrollRestrictions()

        enforceWhitePDFBackground()

        detailsWebView.loadHTMLString(buildDetailsStatusHTML("Waiting for Mail scan…", paperIndex: nil, paperTotal: nil, leftHeaderText: nil, centerHeaderText: nil), baseURL: nil)
    }

    private func installRightPanelScrollRestrictions() {
        // Details panel: allow vertical scrolling, suppress all horizontal panning/elasticity.
        for sv in descendantScrollViews(in: detailsWebView) {
            ensureHorizontalLock(for: sv, lockedX: 0, clampVertical: true)
            sv.verticalScrollElasticity = .none // no rubber-banding on HTML pane
        }
        detailsWebView.lockedX = 0

        // PDFView embeds its own scroll view; clamp horizontal panning there too.
        for sv in descendantScrollViews(in: pdfView) {
            // PDFKit uses custom clip view subclasses for selection/interaction.
            // Swapping the clip view can break text drag-selection.
            ensureHorizontalLock(for: sv, lockedX: 0, swapClipView: false)
            sv.verticalScrollElasticity = .none // no rubber-banding on PDF pane
        }

        installPDFScrollDebuggingIfNeeded()
    }

    private func installPDFScrollDebuggingIfNeeded() {
        guard PDFScrollDebugState.shared.enabled else { return }
        guard let scrollView = pdfPrimaryScrollView() else { return }
        if let overlay = pdfScrollDebugOverlay, overlay.matches(scrollView: scrollView) {
            return
        }
        pdfScrollDebugOverlay = PDFScrollDebugOverlay(hostView: rightContentView, scrollView: scrollView)
    }

    private func layoutPDFScrollDebugOverlay() {
        guard let overlay = pdfScrollDebugOverlay else { return }
        overlay.setHidden(!isShowingPDF)
        overlay.layout(in: rightContentView.bounds)
    }

    private func ensureHorizontalLock(
        for scrollView: NSScrollView,
        lockedX: CGFloat,
        clampVertical: Bool = false,
        swapClipView: Bool = true
    ) {
        let id = ObjectIdentifier(scrollView)
        if let lock = rightHorizontalScrollLocks[id] {
            lock.updateLockedX(lockedX)
            return
        }
        rightHorizontalScrollLocks[id] = HorizontalScrollLock(scrollView: scrollView, lockedX: lockedX, clampVertical: clampVertical, swapClipView: swapClipView)
    }

    private func descendantScrollViews(in root: NSView) -> [NSScrollView] {
        var out: [NSScrollView] = []
        func walk(_ view: NSView) {
            if let sv = view as? NSScrollView { out.append(sv) }
            for sub in view.subviews { walk(sub) }
        }
        walk(root)
        return out
    }

	    private func layoutRightPanelSubviews() {
        defer { updateRightCardBackgroundFrame() }
        // Apple-like inset padding inside bordered right panel
        let ib = rightContentView.bounds.insetBy(dx: PANEL_INSET, dy: PANEL_INSET)

        rightPDFBackgroundView.frame = rightContentView.bounds
        if let layer = rightPDFBackgroundView.layer {
            layer.cornerRadius = rightCardCornerRadius()
            layer.masksToBounds = true
            if #available(macOS 10.13, *) {
                layer.cornerCurve = rightContainer.layer?.cornerCurve ?? .continuous
            }
        }
        // Constrained: rightPanelContentHost fills rightContentView with PANEL_INSET.
        if let hostLayer = rightPanelContentHost.layer {
            // Transition safety: clip transforms to the right panel content bounds.
            // Divider safety: this is confined to the content host; split-view layout is untouched.
            hostLayer.cornerRadius = rightCardCornerRadius()
            hostLayer.masksToBounds = true
            if #available(macOS 10.13, *) {
                hostLayer.cornerCurve = rightContainer.layer?.cornerCurve ?? .continuous
            }
        }

        if let blurLayer = rightPanelTransitionBlurView.layer {
            blurLayer.cornerRadius = rightCardCornerRadius()
            blurLayer.masksToBounds = true
            if #available(macOS 10.13, *) {
                blurLayer.cornerCurve = rightContainer.layer?.cornerCurve ?? .continuous
            }
        }
            _ = ib // now constraint-driven
	        applyDetailsWebViewRoundedClipping()

        layoutLoadingOverlaySubviews()
        layoutPDFFindHUDSubviews()

        if isShowingPDF {
            enforceWhitePDFBackground()
        }
        layoutPDFScrollDebugOverlay()
        recordRightPanelWidthIfNeeded()
        clampRightPanelWidthForSplit()
        layoutRightAuxPanelSubviews()
    }

    private func layoutRightAuxPanelSubviews() {
        guard rightAuxContainer.superview != nil else { return }
        let b = rightAuxContentView.bounds
        guard b.width > 1, b.height > 1 else { return }

        let insetX: CGFloat = PANEL_INSET
        let insetY: CGFloat = PANEL_INSET
        let width = max(0, b.width - (2 * insetX))

        // Header at top: "Chat Session" + underline.
        let headerLabelH: CGFloat = 16
        let headerGapBelowLabel: CGFloat = 6
        let headerRuleH: CGFloat = 1
        let headerLabelY = max(insetY, b.height - insetY - headerLabelH)
        rightAuxHeaderLabel.frame = NSRect(x: insetX,
                                           y: headerLabelY,
                                           width: width,
                                           height: headerLabelH)
        let ruleY = max(insetY, headerLabelY - headerGapBelowLabel - headerRuleH)
        rightAuxHeaderRule.frame = NSRect(x: insetX,
                                          y: ruleY,
                                          width: width,
                                          height: headerRuleH)

        rightAuxAskContainer.frame = NSRect(
            x: insetX,
            y: insetY,
            width: width,
            height: searchContainerHeight
        )

        // Separator line above the typing/ask bar.
        let sepH: CGFloat = 3.0
        let sepGapAboveAsk: CGFloat = 10.0
        let sepOvershoot: CGFloat = 12.0
        let sepY = rightAuxAskContainer.frame.maxY + sepGapAboveAsk
        var sepX = insetX - sepOvershoot
        var sepW = width + (2 * sepOvershoot)
        if sepX < insetX {
            sepW -= (insetX - sepX)
            sepX = insetX
        }
        sepW = min(sepW, max(0, insetX + width - sepX))
        rightAuxAskSeparatorView.frame = NSRect(x: sepX, y: sepY, width: max(0, sepW), height: sepH)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        rightAuxAskSeparatorView.layer?.cornerRadius = sepH / 2
        rightAuxAskSeparatorGradient.frame = rightAuxAskSeparatorView.bounds
        rightAuxAskSeparatorGradient.cornerRadius = sepH / 2
        rightAuxAskSeparatorHighlight.frame = rightAuxAskSeparatorView.bounds
        rightAuxAskSeparatorHighlight.cornerRadius = sepH / 2
        CATransaction.commit()
        rightAuxAskContainer.layoutSubtreeIfNeeded()
        updateRightAuxAskCapsuleGeometry()
        installRightAuxAskTracking()
    }

    private func updateRightAuxAskCapsuleGeometry() {
        guard let layer = rightAuxAskBackground.layer else { return }
        let b = rightAuxAskBackground.bounds
        guard b.width > 1, b.height > 1 else { return }

        let lineWidth: CGFloat = max(1, SPOTLIGHT_SEARCH_OUTLINE_WIDTH)
        let inset = lineWidth / 2
        let rect = b.insetBy(dx: inset, dy: inset)
        let radius = rect.height / 2
        let path = CGPath(roundedRect: rect, cornerWidth: radius, cornerHeight: radius, transform: nil)
        let innerRect = b.insetBy(dx: inset + 1.0, dy: inset + 1.0)
        let innerRadius = max(0, innerRect.height / 2)
        let innerPath = CGPath(roundedRect: innerRect, cornerWidth: innerRadius, cornerHeight: innerRadius, transform: nil)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.masksToBounds = true
        layer.cornerRadius = radius
        layer.shadowPath = path
        if let glass = rightAuxAskBackground as? NSGlassEffectView {
            glass.cornerRadius = radius
        }
        rightAuxAskOutlineLayer.lineWidth = lineWidth
        rightAuxAskOutlineLayer.path = path
        rightAuxAskInnerOutlineLayer.lineWidth = lineWidth
        rightAuxAskInnerOutlineLayer.path = innerPath
        rightAuxAskMaskLayer.path = path
        rightAuxAskCenterGlowLayer.frame = b
        rightAuxAskCenterGlowLayer.locations = [0.0, 1.0]
        rightAuxAskHighlightLayer.frame = b
        rightAuxAskHighlightLayer.locations = [0.0, 1.0]
        rightAuxAskFalloffLayer.frame = b
        rightAuxAskFalloffLayer.locations = [0.0, 1.0]
        if let containerLayer = rightAuxAskContainer.layer {
            containerLayer.shadowPath = path
        }
        CATransaction.commit()

        updateRightAuxAskDepth(animated: false)
    }

    // MARK: Loading overlay (CENTERED)

    private func setupLoadingOverlay() {
        loadingOverlay = makeGlassEffectView(
            passthrough: false,
            cornerRadius: PANEL_CORNER_RADIUS,
            tintColor: nil,
            style: .regular,
            fallbackMaterial: .hudWindow,
            fallbackBlending: .withinWindow,
            fallbackState: .active,
            emphasized: true
        )
        loadingOverlay.translatesAutoresizingMaskIntoConstraints = false
        loadingOverlay.wantsLayer = true
        loadingOverlay.layer?.cornerRadius = PANEL_CORNER_RADIUS
        loadingOverlay.layer?.masksToBounds = true
        loadingOverlay.isHidden = true

        loadingSpinner.style = .spinning
        loadingSpinner.isIndeterminate = true
        loadingSpinner.controlSize = .regular

        loadingLabel.font = NSFont.systemFont(ofSize: 13)
        loadingLabel.textColor = resolvedSystemColor(.labelColor)
        loadingLabel.alignment = .center

        rightContentView.addSubview(loadingOverlay)
        NSLayoutConstraint.activate([
            loadingOverlay.leadingAnchor.constraint(equalTo: rightContentView.leadingAnchor, constant: PANEL_INSET),
            loadingOverlay.trailingAnchor.constraint(equalTo: rightContentView.trailingAnchor, constant: -PANEL_INSET),
            loadingOverlay.topAnchor.constraint(equalTo: rightContentView.topAnchor, constant: PANEL_INSET),
            loadingOverlay.bottomAnchor.constraint(equalTo: rightContentView.bottomAnchor, constant: -PANEL_INSET),
        ])
        loadingOverlay.addSubview(loadingSpinner)
        loadingOverlay.addSubview(loadingLabel)
    }

	    private func installCacheLifecycleObservers() {
	        appTerminationObserver = NotificationCenter.default.addObserver(
	            forName: NSApplication.willTerminateNotification,
	            object: nil,
	            queue: .main
	        ) { [weak self] _ in
	            guard let self else { return }
	            if self.pdfCacheCleanupState == .cleaned { return }
	            self.pdfCacheCleanupState = .cleaning
	            NSLog("[PDFEager] cleanup_start reason=will_terminate dir=\(self.pdfCache.sessionDirectory.path)")
	            self.pdfCache.cleanupOnExit()
	            self.pdfCacheCleanupState = .cleaned
	        }
	    }

    private func layoutLoadingOverlaySubviews() {
        let b = loadingOverlay.bounds
        guard b.width > 10, b.height > 10 else { return }

        let spinnerSize: CGFloat = 18
        let labelH: CGFloat = 18
        let gap: CGFloat = 10

        let groupH = spinnerSize + gap + labelH
        let startY = (b.height - groupH) / 2

        loadingSpinner.frame = NSRect(
            x: (b.width - spinnerSize) / 2,
            y: startY + labelH + gap,
            width: spinnerSize,
            height: spinnerSize
        )
        loadingLabel.frame = NSRect(
            x: 24,
            y: startY,
            width: b.width - 48,
            height: labelH
        )
    }

    private func showLoading(_ msg: String) {
        loadingLabel.stringValue = msg
        loadingOverlay.isHidden = false
        loadingSpinner.startAnimation(nil)
        DispatchQueue.main.async { self.layoutRightPanelSubviews() }
    }

    private func hideLoading() {
        loadingSpinner.stopAnimation(nil)
        loadingOverlay.isHidden = true
    }

	    // MARK: PDF Cache + Prefetch

    private func debugPDFOverrideURL() -> URL? {
        let raw = (ProcessInfo.processInfo.environment["ARXIV_DEBUG_PDF_URL_OVERRIDE"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !raw.isEmpty else { return nil }
        guard let url = URL(string: raw) else {
            NSLog("[PDFEager] debug_override_pdf_url_invalid=\(raw)")
            return nil
        }
        if !didLogDebugPDFOverride {
            didLogDebugPDFOverride = true
            NSLog("[PDFEager] debug_override_pdf_url=\(raw)")
        }
        return url
    }

    private func pdfURL(for paper: Paper) -> URL? {
        if let override = debugPDFOverrideURL() { return override }
        guard let pdfURLStr = arxivPDFFromAbs(url: paper.url),
              let pdfURL = URL(string: pdfURLStr) else {
            return nil
        }
        return normalizedPDFURL(pdfURL)
    }

    private func pdfMetadata(for paper: Paper, url: URL) -> PDFCacheManager.Metadata {
        let stableID = arxivID(fromAbsURL: paper.url)
        return PDFCacheManager.Metadata(url: url, paperIndex: paper.index, stableID: stableID)
    }

    private func pdfMetadata(with url: URL) -> PDFCacheManager.Metadata {
        let stableID = arxivIDFromPDFURL(url)
        return PDFCacheManager.Metadata(url: url, paperIndex: nil, stableID: stableID)
    }

    private func prefetchRequest(for paper: Paper) -> PDFCacheManager.PrefetchRequest? {
        guard let url = pdfURL(for: paper) else { return nil }
        return PDFCacheManager.PrefetchRequest(
            url: url,
            metadata: pdfMetadata(for: paper, url: url)
        )
    }

    private func arxivIDFromPDFURL(_ url: URL) -> String? {
        guard let host = url.host?.lowercased(), host.hasSuffix("arxiv.org") else { return nil }
        guard url.path.lowercased().hasPrefix("/pdf/") else { return nil }
        var identifier = url.path.dropFirst("/pdf/".count)
        if identifier.lowercased().hasSuffix(".pdf") {
            identifier = identifier.dropLast(4)
        }
        return identifier.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    private func normalizedPDFURL(_ url: URL) -> URL {
        guard !url.isFileURL else { return url }
	        guard var comps = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return url }
	        comps.fragment = nil
	        comps.query = nil
	        if (comps.scheme ?? "").lowercased() == "http" {
	            comps.scheme = "https"
	        }
	        if let host = comps.host?.lowercased(), host.hasSuffix("arxiv.org"), comps.path.hasPrefix("/pdf/") {
	            if !comps.path.lowercased().hasSuffix(".pdf") {
	                comps.path += ".pdf"
	            }
	        }
	        return comps.url ?? url
	    }

    private func prefetchAllPapers(reason: String) {
        // Enqueue synchronously so any immediate user action can subscribe to pending downloads
        // (without triggering on-demand network requests).
        let requests = allItems.compactMap { prefetchRequest(for: $0) }
        NSLog("[PDFEager] eager_enqueue_all count=\(requests.count) reason=\(reason)")
        pdfCache.prefetch(requests, priority: 3, reason: reason)
    }

    private func prefetchNeighborPDFs(around index: Int, radius: Int = 2, reason: String) {
        guard index >= 0, index < filtered.count else { return }
        let start = max(0, index - radius)
        let end = min(filtered.count - 1, index + radius)
        guard start <= end else { return }

        var requests: [PDFCacheManager.PrefetchRequest] = []
        for i in start...end where i != index {
            if let req = prefetchRequest(for: filtered[i]) {
                requests.append(req)
            }
        }
        guard !requests.isEmpty else { return }
        pdfCache.prefetch(requests, priority: 2, reason: reason)
    }

	    private func applyPDFDocument(_ doc: PDFDocument,
	                                  token: Int,
	                                  source: String,
	                                  startTime: CFTimeInterval,
	                                  cacheKey: String) {
	        guard pdfLoadToken == token else { return }

        // Deterministic PDFView reset (single persistent PDFView):
        // Clear selection/state, then swap documents atomically without blanking the view.
        pdfView.highlightedSelections = nil
        pdfView.clearSelection()
        resetPDFFindResults(clearHighlights: false)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        pdfView.document = doc
	        CATransaction.commit()
	        pdfView.autoScales = true
	        pdfView.goToFirstPage(nil)
        resetPDFMagnifyState()
	        installRightPanelScrollRestrictions()
	        enforceWhitePDFBackground()
        annotationController?.refreshIcons()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
            self.installRightPanelScrollRestrictions()
            self.enforceWhitePDFBackground()
            self.annotationController?.refreshIcons()
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            self.enforceWhitePDFBackground()
            self.annotationController?.refreshIcons()
        }
        hideLoading()

        runPDFZoomReproIfRequested()

        let elapsedMs = Int((monotonicNow() - startTime) * 1000.0)
        let keyLabel = cacheKey.isEmpty ? "none" : String(cacheKey.prefix(8))
        perfLog("pdf_open_ms=\(elapsedMs) source=\(source) key=\(keyLabel)")
    }

    private func logListRenderIfNeeded() {
        guard let start = listRenderStartTime, listRenderLogged == false else { return }
        listRenderLogged = true
        let elapsedMs = Int((monotonicNow() - start) * 1000.0)
        perfLog("list_first_render_ms=\(elapsedMs) rows=\(filtered.count)")
    }

    // MARK: PDF Find HUD (Cmd-F)

    private func setupPDFFindHUD() {
        let searchTheme = currentSearchBarTheme()
        let findTint = toolbarGlassTintColor()
        pdfFindHUD = NSView(frame: .zero)
        pdfFindHUD.translatesAutoresizingMaskIntoConstraints = true
        pdfFindHUD.isHidden = true

        pdfFindBackgroundView = makeToolbarButtonGlassCard(tint: findTint)
        pdfFindBackgroundView.translatesAutoresizingMaskIntoConstraints = true
        pdfFindBackgroundView.wantsLayer = true
        applySearchBarTheme(to: pdfFindBackgroundView)
        if let card = pdfFindBackgroundView as? GlassCardView {
            card.cornerRadius = 12
        } else {
            pdfFindBackgroundView.layer?.cornerRadius = 12
        }
        pdfFindBackgroundView.layer?.masksToBounds = true

        pdfFindContentView.translatesAutoresizingMaskIntoConstraints = true
        pdfFindContentView.wantsLayer = true
        pdfFindContentView.layer?.opacity = 0

        pdfFindOutlineLayer.fillColor = NSColor.clear.cgColor
        pdfFindOutlineLayer.lineJoin = .round
        pdfFindOutlineLayer.lineCap = .round
        pdfFindOutlineLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
        pdfFindHighlightLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
        pdfFindFalloffLayer.contentsScale = NSScreen.main?.backingScaleFactor ?? 2.0
        pdfFindHighlightLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
        pdfFindHighlightLayer.endPoint = CGPoint(x: 0.5, y: 0.0)
        pdfFindFalloffLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
        pdfFindFalloffLayer.endPoint = CGPoint(x: 0.5, y: 0.0)
        pdfFindFalloffLayer.opacity = 0.75
        let pdfFindForeground = inkyBlackColor()
        applySearchFieldTheme(pdfFindField,
                              placeholder: "Find in PDF",
                              textColor: pdfFindForeground,
                              placeholderColor: pdfFindForeground,
                              iconColor: pdfFindForeground)
        pdfFindField.target = self
        pdfFindField.action = #selector(pdfFindSubmitted)
        pdfFindField.delegate = self
        if let cell = pdfFindField.cell as? NSSearchFieldCell {
            cell.cancelButtonCell = nil
        }

        pdfFindCountLabel.font = NSFont.monospacedDigitSystemFont(ofSize: searchTheme.secondaryFont.pointSize,
                                                                  weight: .regular)
        pdfFindCountLabel.textColor = pdfFindForeground
        pdfFindCountLabel.alignment = .center
        pdfFindCountLabel.usesSingleLineMode = true
        pdfFindCountLabel.lineBreakMode = .byClipping

        let pdfFindPrevGlass = makeToolbarButtonGlassCard(tint: findTint)
        let pdfFindNextGlass = makeToolbarButtonGlassCard(tint: findTint)

        let symbolConfig = toolbarSymbolConfig()
        pdfFindPrevButton.image = NSImage(systemSymbolName: "chevron.left", accessibilityDescription: nil)?
            .withSymbolConfiguration(symbolConfig)
        pdfFindNextButton.image = NSImage(systemSymbolName: "chevron.right", accessibilityDescription: nil)?
            .withSymbolConfiguration(symbolConfig)
        pdfFindPrevButton.target = self
        pdfFindNextButton.target = self
        pdfFindPrevButton.action = #selector(pdfFindPreviousMatch)
        pdfFindNextButton.action = #selector(pdfFindNextMatch)
        pdfFindPrevButton.restingTintColor = pdfFindForeground
        pdfFindNextButton.restingTintColor = pdfFindForeground
        pdfFindPrevButton.updateTint()
        pdfFindNextButton.updateTint()
        pdfFindPrevButton.attachLiquidGlassBackground(pdfFindPrevGlass)
        pdfFindNextButton.attachLiquidGlassBackground(pdfFindNextGlass)

        pdfFindHUD.addSubview(pdfFindBackgroundView)
        pdfFindHUD.addSubview(pdfFindContentView)
        pdfFindContentView.addSubview(pdfFindField)
        pdfFindContentView.addSubview(pdfFindCountLabel)
        pdfFindContentView.addSubview(pdfFindPrevGlass)
        pdfFindContentView.addSubview(pdfFindNextGlass)
        pdfFindContentView.addSubview(pdfFindPrevButton)
        pdfFindContentView.addSubview(pdfFindNextButton)
        rightContentView.addSubview(pdfFindHUD)
        installPDFFindTracking()
        updatePDFFindControls()
    }

    private func layoutPDFFindHUDSubviews() {
        guard !pdfFindHUD.isHidden else { return }
        let ib = rightContentView.bounds.insetBy(dx: PANEL_INSET, dy: PANEL_INSET)

        let hudW: CGFloat = min(420, ib.width - 24)
        let hudH: CGFloat = 46
        let x = ib.minX + (ib.width - hudW) / 2
        let y = ib.maxY - hudH - 14

        pdfFindHUD.frame = NSRect(x: x, y: y, width: hudW, height: hudH)
        pdfFindBackgroundView.frame = pdfFindHUD.bounds
        pdfFindContentView.frame = pdfFindHUD.bounds
        let fieldHeight: CGFloat = 26
        let contentInsetX: CGFloat = 12
        let contentInsetRight: CGFloat = 12
        let fieldToControlsGap: CGFloat = 8
        let controlGap: CGFloat = 6
        let arrowButtonSize: CGFloat = 20
        let countWidth: CGFloat = 72
        let labelHeight = max(14, pdfFindCountLabel.intrinsicContentSize.height)
        let fieldY = round((hudH - fieldHeight) / 2)
        let labelY = round((hudH - labelHeight) / 2)
        let buttonY = round((hudH - arrowButtonSize) / 2)

        let rightControlsWidth = (2 * arrowButtonSize) + countWidth + (2 * controlGap)
        let availableFieldWidth = hudW - contentInsetX - contentInsetRight - rightControlsWidth - fieldToControlsGap
        let fieldWidth = max(0, availableFieldWidth)
        let controlsX = hudW - contentInsetRight - rightControlsWidth

        pdfFindField.frame = NSRect(x: contentInsetX, y: fieldY, width: fieldWidth, height: fieldHeight)
        pdfFindPrevButton.frame = NSRect(x: controlsX,
                                         y: buttonY,
                                         width: arrowButtonSize,
                                         height: arrowButtonSize)
        pdfFindCountLabel.frame = NSRect(x: controlsX + arrowButtonSize + controlGap,
                                         y: labelY,
                                         width: countWidth,
                                         height: labelHeight)
        pdfFindNextButton.frame = NSRect(x: controlsX + arrowButtonSize + controlGap + countWidth + controlGap,
                                         y: buttonY,
                                         width: arrowButtonSize,
                                         height: arrowButtonSize)
        pdfFindPrevButton.setCornerRadius(arrowButtonSize / 2)
        pdfFindNextButton.setCornerRadius(arrowButtonSize / 2)
        pdfFindPrevButton.needsLayout = true
        pdfFindNextButton.needsLayout = true

        let radius = hudH / 2
        if let card = pdfFindBackgroundView as? GlassCardView {
            card.cornerRadius = radius
        } else if let glass = pdfFindBackgroundView as? NSGlassEffectView {
            glass.cornerRadius = radius
        }
        if let layer = pdfFindBackgroundView.layer {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.cornerRadius = radius
            layer.masksToBounds = true
            layer.anchorPoint = CGPoint(x: 0.5, y: 0.5)
            layer.position = CGPoint(x: layer.bounds.midX, y: layer.bounds.midY)
            CATransaction.commit()
        }
        if let layer = pdfFindContentView.layer {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.anchorPoint = CGPoint(x: 0.5, y: 0.5)
            layer.position = CGPoint(x: layer.bounds.midX, y: layer.bounds.midY)
            CATransaction.commit()
        }

        installPDFFindTracking()
        updatePDFFindCapsuleGeometry()
        updatePDFFindDepth(animated: false)
    }

    private func showPDFFindHUD() {
        guard isShowingPDF else { return }
        pdfFindHover = false
        pdfFindFocused = false
        setPDFFindHUDVisible(true, animated: true)
        resetPDFFindResults(clearHighlights: true)
        window?.makeFirstResponder(pdfFindField)
    }

    private func hidePDFFindHUD() {
        resetPDFFindResults(clearHighlights: true)
        pdfFindHover = false
        pdfFindFocused = false
        updatePDFFindDepth(animated: false)
        setPDFFindHUDVisible(false, animated: true)
    }

    @objc private func pdfFindSubmitted() {
        let mods = NSEvent.modifierFlags.intersection(.deviceIndependentFlagsMask)
        let backwards = mods.contains(.shift)
        let q = normalizedPDFFindQuery(pdfFindField.stringValue)
        guard !q.isEmpty else { return }
        navigatePDFFind(delta: backwards ? -1 : 1, query: q, beepOnEmpty: true)
    }

    @objc private func pdfFindPreviousMatch() {
        navigatePDFFind(delta: -1, query: pdfFindField.stringValue, beepOnEmpty: true)
    }

    @objc private func pdfFindNextMatch() {
        navigatePDFFind(delta: 1, query: pdfFindField.stringValue, beepOnEmpty: true)
    }

    private func normalizedPDFFindQuery(_ query: String) -> String {
        query.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func pdfFindQueryDidChange() {
        let q = normalizedPDFFindQuery(pdfFindField.stringValue)
        guard !q.isEmpty else {
            resetPDFFindResults(clearHighlights: true)
            return
        }
        rebuildPDFFindResults(for: q)
    }

    private func resetPDFFindResults(clearHighlights: Bool) {
        pdfFindResults = []
        pdfFindIndex = -1
        pdfFindQuery = ""
        if clearHighlights {
            pdfView.highlightedSelections = nil
            pdfView.clearSelection()
        }
        updatePDFFindControls()
    }

    private func updatePDFFindControls() {
        let total = pdfFindResults.count
        let current = (total > 0 && pdfFindIndex >= 0) ? (min(pdfFindIndex, total - 1) + 1) : 0
        pdfFindCountLabel.stringValue = "\(current)/\(total)"

        let prevEnabled = total > 0 && pdfFindIndex > 0
        let nextEnabled = total > 0 && pdfFindIndex >= 0 && pdfFindIndex < total - 1
        pdfFindPrevButton.isEnabled = prevEnabled
        pdfFindNextButton.isEnabled = nextEnabled
        pdfFindPrevButton.alphaValue = prevEnabled ? 1.0 : 0.45
        pdfFindNextButton.alphaValue = nextEnabled ? 1.0 : 0.45
    }

    private func rebuildPDFFindResults(for query: String) {
        guard let doc = pdfView.document else {
            pdfFindQuery = query
            pdfFindResults = []
            pdfFindIndex = -1
            pdfView.highlightedSelections = nil
            pdfView.clearSelection()
            updatePDFFindControls()
            return
        }
        pdfFindQuery = query
        pdfFindResults = doc.findString(query, withOptions: [.caseInsensitive])
        if pdfFindResults.isEmpty {
            pdfFindIndex = -1
            pdfView.highlightedSelections = nil
            pdfView.clearSelection()
            updatePDFFindControls()
            return
        }
        pdfFindIndex = 0
        goToPDFFindMatch(at: pdfFindIndex)
        updatePDFFindControls()
    }

    private func navigatePDFFind(delta: Int, query: String, beepOnEmpty: Bool) {
        let normalized = normalizedPDFFindQuery(query)
        guard !normalized.isEmpty else {
            resetPDFFindResults(clearHighlights: true)
            return
        }

        let needsRebuild = normalized != pdfFindQuery || pdfFindResults.isEmpty
        if needsRebuild {
            rebuildPDFFindResults(for: normalized)
        }

        if pdfFindResults.isEmpty {
            if beepOnEmpty { NSSound.beep() }
            updatePDFFindControls()
            return
        }

        if needsRebuild {
            return
        }

        if pdfFindIndex < 0 {
            pdfFindIndex = 0
        }

        let target = max(0, min(pdfFindResults.count - 1, pdfFindIndex + delta))
        guard target != pdfFindIndex else {
            updatePDFFindControls()
            return
        }

        pdfFindIndex = target
        goToPDFFindMatch(at: pdfFindIndex)
        updatePDFFindControls()
    }

    private func goToPDFFindMatch(at index: Int) {
        guard index >= 0, index < pdfFindResults.count else { return }
        let selection = pdfFindResults[index]
        pdfView.setCurrentSelection(selection, animate: false)
        pdfView.highlightedSelections = [selection]

        guard let page = selection.pages.first as? PDFPage,
              let scrollView = descendantScrollViews(in: pdfView).first,
              let docView = scrollView.documentView else {
            pdfView.scrollSelectionToVisible(nil)
            return
        }

        // Convert PDF page coordinates -> PDFView -> documentView so scroll positions
        // are computed in the same space as the clip view bounds, then clamp to doc limits.
        let matchRectInView = pdfView.convert(selection.bounds(for: page), from: page)
        let matchRectInDoc = pdfView.convert(matchRectInView, to: docView)
        let viewportHeight = scrollView.contentView.bounds.height
        let minY = docView.bounds.minY
        let maxY = max(minY, docView.bounds.maxY - viewportHeight)
        let targetY = max(minY, min(maxY, matchRectInDoc.midY - viewportHeight / 2))

        let clipView = scrollView.contentView
        clipView.setBoundsOrigin(NSPoint(x: clipView.bounds.origin.x, y: targetY))
        scrollView.reflectScrolledClipView(clipView)
    }

    // MARK: Click handling

    private func setupSelectionClearMonitor() {
        guard selectionClearMonitor == nil else { return }
        selectionClearMonitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] event in
            guard let self else { return event }
            self.clearListSelectionIfNeeded(for: event)
            return event
        }
    }

    private func setupDividerDragEndMonitor() {
        guard dividerDragEndMonitor == nil else { return }
        dividerDragEndMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseUp) { [weak self] event in
            guard let self else { return event }
            // Native split-view divider drags can end without another didResize notification.
            // If we don't clear this flag, later drags/resizes can appear “stuck”.
            if self.dividerDragActive {
                self.dividerDragActive = false
                self.systemDividerDragPendingSplitModeExit = false
                self.logDividerState("drag_end_mouse_up")
                self.schedulePanelSettle()
                self.enforceSidebarWidthBounds(reason: "drag_end_mouse_up")
                if debugLayoutEnabled {
                    self.updateLayoutDebugOverlay(reason: "drag_end_mouse_up")
                }
            }
            return event
        }
    }

    private func clearListSelectionIfNeeded(for event: NSEvent) {
        guard let window, window.isKeyWindow else { return }
        let pointInTable = tableView.convert(event.locationInWindow, from: nil)
        // Only clear selection when the user clicks empty space *within* the table.
        // Clicking elsewhere (e.g. the PDF viewer) should not clear the current paper selection.
        guard tableView.bounds.contains(pointInTable) else { return }
        let row = tableView.row(at: pointInTable)
        guard row < 0 else { return }
        if tableView.selectedRow >= 0 {
            tableView.deselectAll(nil)
        }
    }

    // MARK: Key handling (Enter / Cmd-F / Esc / Cmd-Shift-E)

    private func setupKeyHandling() {
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] e in
            guard let self, self.window?.isKeyWindow == true else { return e }

            let mods = e.modifierFlags.intersection(.deviceIndependentFlagsMask)
            let key = (e.charactersIgnoringModifiers ?? "").lowercased()

            // Debug hotkey: deterministic PDF zoom repro (Cmd-Opt-Shift-R)
            if self.pdfZoomDebugEnabled && mods.contains([.command, .option, .shift]) && key == "r" {
                self.runPDFZoomRepro()
                return nil
            }

            if e.keyCode == 53 {
                if !self.menuContainer.isHidden {
                    self.setMenuVisible(false, animated: true)
                    return nil
                }
                if self.suggestionsVisible {
                    self.setSuggestionsVisible(false, animated: true)
                    return nil
                }
            }

            if !self.menuContainer.isHidden {
                switch e.keyCode {
                case 125: // down
                    self.moveMenuSelection(1)
                    return nil
                case 126: // up
                    self.moveMenuSelection(-1)
                    return nil
                case 36, 76: // Return / Enter
                    self.activateMenuSelection()
                    return nil
                default:
                    break
                }
            }

            if self.searchFocused {
                if self.suggestionsVisible {
                    switch e.keyCode {
                    case 125: // down
                        self.moveSuggestionSelection(1)
                        return nil
                    case 126: // up
                        self.moveSuggestionSelection(-1)
                        return nil
                    case 36, 76: // Return / Enter
                        self.acceptSuggestionSelection()
                        return nil
                    case 53: // Esc handled above
                        return nil
                    default:
                        break
                    }
                } else {
                    // Allow text navigation when suggestions are not visible.
                    if e.keyCode == 125 || e.keyCode == 126 {
                        return e
                    }
                    if e.keyCode == 36 || e.keyCode == 76 {
                        return e
                    }
                }
            }

            // When the PDF pane is visible and PDFKit (or our PDFView) is the active responder,
            // do NOT steal navigation keys; they should scroll the PDF.
            if self.isShowingPDF {
                if let responderView = self.window?.firstResponder as? NSView,
                   responderView.isDescendant(of: self.pdfView) {
                    switch e.keyCode {
                    case 125, 126, 116, 121, 49, 115, 119: // ↓ ↑ PageUp PageDown Space Home End
                        return e
                    default:
                        break
                    }
                }
            }

            // Key routing note:
            // We capture ↑/↓ at the app level so list navigation keeps working even when PDFKit's view hierarchy
            // is the first responder (PDFView/scroll views tend to consume arrow-key events).

	            // Cmd-Shift-E exits for Shortcuts continuation
	            if mods.contains([.command, .shift]) && key == "e" {
	                self.window?.close()
	                return nil
	            }

            // Esc: only act when PDF or its find HUD is active; otherwise swallow to avoid cancel/close.
            if e.keyCode == 53 {
                if !self.pdfFindHUD.isHidden {
                    self.hidePDFFindHUD()
                    return nil
                }
                if self.isShowingPDF {
                    self.showDetailsPanel()
                    return nil
                }
                return nil
            }

            // Cmd-F: open PDF find when PDF is showing
            if mods.contains(.command) && key == "f" {
                if self.isShowingPDF {
                    self.showPDFFindHUD()
                    return nil
                }
                return e
            }

            if mods.contains(.command) && (key == "=" || key == "+") {
                if self.isShowingPDF {
                    self.zoomPDFStep(increase: true)
                    return nil
                }
                return e
            }

            if mods.contains(.command) && (key == "-" || key == "_") {
                if self.isShowingPDF {
                    self.zoomPDFStep(increase: false)
                    return nil
                }
                return e
            }

            // Enter/Return opens PDF in right panel
            switch e.keyCode {
            case 125: // down
                if let idx = self.selectedFilteredIndex() {
                    self.select(idx + 1)
                } else if !self.filtered.isEmpty {
                    self.select(0)
                }
                return nil
            case 126: // up
                if let idx = self.selectedFilteredIndex() {
                    self.select(idx - 1)
                }
                return nil
            case 36, 76: // Return / Enter
                if let dataRow = self.selectedFilteredIndex() {
                    // Enter-key PDF switching uses the same canonical presenter as details-panel PDF link clicks.
                    self.openPDFInRightPanel(forRow: dataRow, trigger: "keyboard-enter")
                }
                return nil
            default:
                return e
            }
        }
    }

    private func select(_ globalIndex: Int) {
        guard !filtered.isEmpty else { return }
        let clamped = max(0, min(globalIndex, filtered.count - 1))
        selectFilteredIndex(clamped, scroll: true, reason: "keyboard-updown")
    }

    // MARK: Context menu (right-click)

    func menuNeedsUpdate(_ menu: NSMenu) {
        guard menu === rowMenu else { return }
        menu.removeAllItems()

        let clickedRow = tableView.clickedRow
        guard let dataRow = globalIndex(forTableRow: clickedRow),
              dataRow >= 0, dataRow < filtered.count else {
            let item = menu.addItem(withTitle: "No row", action: nil, keyEquivalent: "")
            item.isEnabled = false
            configureContextMenuItemViews(menu)
            return
        }

        if tableView.selectedRow != clickedRow {
            tableView.selectRowIndexes(IndexSet(integer: clickedRow), byExtendingSelection: false)
            if !isShowingPDF { updateDetails() }
        }

        menu.addItem(withTitle: "Open arXiv (abs)", action: #selector(ctxOpenAbs(_:)), keyEquivalent: "")
        menu.addItem(withTitle: "Open PDF", action: #selector(ctxOpenPDF(_:)), keyEquivalent: "")
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Copy citation", action: #selector(ctxCopyCitation(_:)), keyEquivalent: "")
        menu.addItem(withTitle: "Copy BibTeX link", action: #selector(ctxCopyBibtexLink(_:)), keyEquivalent: "")
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Copy Title", action: #selector(ctxCopyTitle(_:)), keyEquivalent: "")
        menu.addItem(withTitle: "Copy Authors", action: #selector(ctxCopyAuthors(_:)), keyEquivalent: "")

        for item in menu.items { item.target = self }
        configureContextMenuItemViews(menu)
    }

    func menu(_ menu: NSMenu, willHighlight item: NSMenuItem?) {
        guard menu === rowMenu else { return }
        for menuItem in menu.items {
            guard let view = menuItem.view as? ContextMenuItemView else { continue }
            view.setMenuHighlighted(menuItem == item, animated: true)
        }
    }

    func menuDidClose(_ menu: NSMenu) {
        guard menu === rowMenu else { return }
        for menuItem in menu.items {
            guard let view = menuItem.view as? ContextMenuItemView else { continue }
            view.setMenuHighlighted(false, animated: false)
        }
    }

    private func configureContextMenuItemViews(_ menu: NSMenu) {
        let font = NSFont.menuFont(ofSize: 0)
        let textWidths = menu.items
            .filter { !$0.isSeparatorItem }
            .map { ($0.title as NSString).size(withAttributes: [.font: font]).width }
        let maxTextWidth = textWidths.max() ?? 0
        let itemWidth = max(ContextMenuItemView.minWidth,
                            ceil(maxTextWidth + ContextMenuItemView.contentInsets.left + ContextMenuItemView.contentInsets.right))
        let rowHeight = ContextMenuItemView.rowHeight(for: font)

        for item in menu.items where !item.isSeparatorItem {
            let view = ContextMenuItemView(
                frame: NSRect(x: 0, y: 0, width: itemWidth, height: rowHeight),
                title: item.title,
                font: font
            )
            view.menuItem = item
            view.reduceMotionProvider = { [weak self] in self?.shouldReduceMotion ?? false }
            item.view = view
        }
    }

    private func paste(_ s: String) {
        let pb = NSPasteboard.general
        pb.clearContents()
        pb.setString(s, forType: .string)
    }

    private func currentRowPaperFromMenu() -> (row: Int, paper: Paper)? {
        let rRaw = tableView.clickedRow >= 0 ? tableView.clickedRow : tableView.selectedRow
        guard let r = globalIndex(forTableRow: rRaw) else { return nil }
        guard r >= 0, r < filtered.count else { return nil }
        return (r, filtered[r])
    }

    @objc private func ctxOpenAbs(_ sender: Any?) {
        guard let (_, p) = currentRowPaperFromMenu() else { return }
        let abs = stripLeadingLabel(p.url, label: "URL").trimmingCharacters(in: .whitespacesAndNewlines)
        guard let u = URL(string: abs), !abs.isEmpty else { return }
        NSWorkspace.shared.open(u)
    }

    @objc private func ctxOpenPDF(_ sender: Any?) {
        guard let (r, _) = currentRowPaperFromMenu() else { return }
        openPDFInRightPanel(forRow: r, trigger: "context-menu")
    }

    @objc private func ctxCopyTitle(_ sender: Any?) {
        guard let (_, p) = currentRowPaperFromMenu() else { return }
        paste(decodeTeXAccents(p.title))
    }

    @objc private func ctxCopyAuthors(_ sender: Any?) {
        guard let (_, p) = currentRowPaperFromMenu() else { return }
        paste(decodeTeXAccents(stripLeadingLabel(p.authors, label: "Authors")))
    }

    @objc private func ctxCopyBibtexLink(_ sender: Any?) {
        guard let (_, p) = currentRowPaperFromMenu() else { return }
        guard let id = arxivID(fromAbsURL: p.url), !id.isEmpty else { return }
        paste("https://arxiv.org/bibtex/\(id)")
    }

    @objc private func ctxCopyCitation(_ sender: Any?) {
        guard let (_, p) = currentRowPaperFromMenu() else { return }

        let year = extractYear(from: p.dateLine)
        let id = arxivID(fromAbsURL: p.url) ?? ""
        let abs = stripLeadingLabel(p.url, label: "URL").trimmingCharacters(in: .whitespacesAndNewlines)

        let authorShort = decodeTeXAccents(leftAuthorYearText(paper: p))
        let title = decodeTeXAccents(p.title)

        var parts: [String] = []
        parts.append(authorShort)
        parts.append("“\(title)”")
        if !id.isEmpty { parts.append("arXiv:\(id)") }
        else if !abs.isEmpty { parts.append(abs) }
        if !year.isEmpty, !authorShort.contains(year) { parts.append("(\(year))") }

        paste(parts.joined(separator: ". "))
    }

    // MARK: Click actions

    @objc private func singleClick() {
        uiLog("row_click single selectedRow=\(tableView.selectedRow) clickedRow=\(tableView.clickedRow)")
        if tableView.selectedRow == 0 {
            select(0)
            return
        }
    }

    @objc private func doubleClick() {
        uiLog("row_click double selectedRow=\(tableView.selectedRow) clickedRow=\(tableView.clickedRow)")
        let row = tableView.clickedRow
        guard row > 0 else { return }
        if let idx = globalIndex(forTableRow: row) {
            openAbs(idx)
        }
    }

    private func openAbs(_ row: Int) {
        guard row >= 0, row < filtered.count else { return }
        let p = filtered[row]
        let abs = stripLeadingLabel(p.url, label: "URL").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !abs.isEmpty, let u = URL(string: abs) else { return }
        NSWorkspace.shared.open(u)
    }

    // MARK: Details HTML load

	    private func loadHTMLWithLocalAccess(_ html: String) {
	        if let u = lastTempHTMLURL { try? FileManager.default.removeItem(at: u) }

        let dir = FileManager.default.temporaryDirectory
        let file = dir.appendingPathComponent("arxiv_picker_\(UUID().uuidString).html")
        lastTempHTMLURL = file

	        do {
	            try html.data(using: .utf8)?.write(to: file, options: [.atomic])
	        } catch {
		            detailsWebView.loadHTMLString(html, baseURL: nil)
		            DispatchQueue.main.async { [weak self] in
		                self?.installRightPanelScrollRestrictions()
		                self?.applyDetailsWebViewRoundedClipping()
		            }
		            return
		        }

	        detailsWebView.loadFileURL(file, allowingReadAccessTo: URL(fileURLWithPath: "/"))
	        DispatchQueue.main.async { [weak self] in
	            self?.installRightPanelScrollRestrictions()
	            self?.applyDetailsWebViewRoundedClipping()
	        }
	    }

	    private func applyDetailsWebViewRoundedClipping() {
	        // Persistent rounded clipping for WKWebView requires applying the same mask to the
	        // actual scrolling/clipping surfaces (webView, scrollView, and the clip view).
	        let radius = rightCardCornerRadius()

	        func apply(_ view: NSView?) {
	            guard let view else { return }
	            view.wantsLayer = true
	            view.layer?.masksToBounds = true
	            view.layer?.cornerRadius = radius
	            if #available(macOS 10.13, *) {
	                view.layer?.cornerCurve = .continuous
	            }
	        }

	        apply(detailsWebView)

	        guard let scroll = descendantScrollViews(in: detailsWebView).first else { return }
	        scroll.drawsBackground = false
	        scroll.backgroundColor = NSColor.clear
	        scroll.horizontalScrollElasticity = .none
	        scroll.verticalScrollElasticity = .none
	        scroll.hasHorizontalScroller = false

	        scroll.contentView.drawsBackground = false
	        scroll.contentView.backgroundColor = NSColor.clear

	        apply(scroll)
	        apply(scroll.contentView) // critical: NSClipView (or HorizontalLockClipView) is the clip surface
	        apply(scroll.documentView)
	    }

	    private func updateDetails() {
	        guard let idx = selectedFilteredIndex() else { return }
	        guard idx >= 0, idx < filtered.count else { return }
	        let p = filtered[idx]

        var terms = keywordsFromAppleScript
        let q = searchField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if !q.isEmpty { terms.append(q) }
        let present = keywordsPresent(in: p, keywords: terms)

        // Keyword highlighting must derive from the same RootGlassTint pipeline as the first glass card.
        let highlight = cssRGBA(rootGlassTheme().keywordHighlight)
        let palette = rightCardTextPalette()

	        let html = buildDetailsHTML(paper: p,
	                                   keywordsForHighlight: present,
	                                   highlightCSS: highlight,
	                                   textPalette: palette,
	                                   paperIndex: idx + 1,
	                                   paperTotal: filtered.count)
	        loadHTMLWithLocalAccess(html)
	    }

    // MARK: Details PDF link routing

    func webView(_ webView: WKWebView,
                 decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard navigationAction.navigationType == .linkActivated,
              let url = navigationAction.request.url else {
            decisionHandler(.allow)
            return
        }

	        // Route PDF link clicks through the canonical PDF presentation pipeline (same as Enter-key flow).
	        if urlLooksLikePDF(url) {
	            presentPDF(remoteURL: url, trigger: "details-link", animateViewMode: true)
	            decisionHandler(.cancel)
	            return
	        }

	        // For all non-PDF links (including the clickable title), open in the system default browser
	        // instead of navigating inside the embedded details view.
	        if let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https" {
	            NSWorkspace.shared.open(url)
	            decisionHandler(.cancel)
	            return
	        }

	        decisionHandler(.allow)
	    }

    private func urlLooksLikePDF(_ url: URL) -> Bool {
        let path = url.path.lowercased()
        return path.hasSuffix(".pdf") || path.contains("/pdf/")
    }

private func buildDetailsStatusHTML(_ message: String, paperIndex: Int? = nil, paperTotal: Int? = nil, leftHeaderText: String? = nil, centerHeaderText: String? = nil) -> String {
		        let detailsLightBG = NSColor.white
		        let detailsDarkBG = NSColor(srgbRed: 0.11, green: 0.11, blue: 0.12, alpha: 1.0)
		        let lightPalette = adaptiveTextPalette(baseColor: detailsLightBG, linkHex: RIGHT_LINK_COLOR_HEX)
		        let darkPalette = adaptiveTextPalette(baseColor: detailsDarkBG, linkHex: RIGHT_LINK_COLOR_HEX)
		        let leftText = (leftHeaderText ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
		        let centerText = (centerHeaderText ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
		        let countText: String = {
		            guard let idx = paperIndex, let total = paperTotal else { return "" }
		            let t = max(0, total)
		            let i = (t == 0) ? 0 : max(1, min(t, idx))
		            return "Paper \(i)/\(t)"
		        }()
	        return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    :root {
      --bg: \(cssRGBA(detailsLightBG));
      --text-primary: \(cssRGBA(lightPalette.primary));
      --text-secondary: \(cssRGBA(lightPalette.secondary));
      --text-muted: \(cssRGBA(lightPalette.muted));
      --text-link: \(cssRGBA(lightPalette.link));
      --rule: \(cssRGBA(lightPalette.rule));
      --code-fg: \(cssRGBA(lightPalette.codeText));
      --code-bg: \(cssRGBA(lightPalette.codeBackground));
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --bg: \(cssRGBA(detailsDarkBG));
        --text-primary: \(cssRGBA(darkPalette.primary));
        --text-secondary: \(cssRGBA(darkPalette.secondary));
        --text-muted: \(cssRGBA(darkPalette.muted));
        --text-link: \(cssRGBA(darkPalette.link));
        --rule: \(cssRGBA(darkPalette.rule));
        --code-fg: \(cssRGBA(darkPalette.codeText));
        --code-bg: \(cssRGBA(darkPalette.codeBackground));
      }
    }

		    html, body { height: 100%; background: transparent; overflow-x: hidden; overscroll-behavior: none; overscroll-behavior-y: none; }
		    body {
		      margin: 0;
		      color: var(--text-secondary);
		      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
		      line-height: 1.35;
		    }

		    .page-shell {
		      min-height: 100vh;
		      background: var(--bg);
		      border-radius: \(PANEL_CORNER_RADIUS)px;
		      overflow: hidden;
		      position: relative;
		      padding: 18px 18px 18px 18px;
		      box-sizing: border-box;
		    }
		    a { color: var(--text-link); text-decoration: underline; }

	    /* Static page header: stays at the top of the document and scrolls away (not fixed/sticky). */
	    .page-header {
	      display: grid;
	      grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) minmax(0, 1fr);
	      align-items: start;
	      column-gap: 12px;
	      margin: 0 0 12px 0;
	    }

	    .chrome-left,
	    .chrome-center,
	    .chrome-right {
	      font-size: 11px;
	      font-weight: 500;
	      letter-spacing: 0.1px;
	      color: var(--text-muted);
	      opacity: 0.95;
	      user-select: none;
	      pointer-events: none;
	      font-variant-numeric: tabular-nums;
	      min-width: 0;
	    }

	    .chrome-left {
	      text-align: left;
	      white-space: nowrap;
	      overflow: hidden;
	      text-overflow: ellipsis;
	    }

	    .chrome-center {
	      text-align: center;
	      white-space: normal;
	      overflow-wrap: anywhere;
	      word-break: break-word;
	      line-height: 1.25;
	    }

	    .chrome-right {
	      text-align: right;
	      white-space: nowrap;
	      overflow: hidden;
	      text-overflow: ellipsis;
	    }
		  </style>
		</head>
			<body>
			  <div class="page-shell">
			  <div class="page-header">
			    <div class="chrome-left">\(htmlEscape(leftText))</div>
			    <div class="chrome-center">\(htmlEscape(centerText))</div>
			    <div class="chrome-right">\(htmlEscape(countText))</div>
			  </div>
			  <div class="status">\(htmlEscape(message))</div>
			  </div>
			</body>
			</html>
"""
			    }

    // MARK: PDF view

	    private func showDetailsPanel(animated: Bool = true, updateContent: Bool = true) {
	        hidePDFFindHUD()
	        isShowingPDF = false
        resetPDFMagnifyState()
	        pdfLoadToken &+= 1 // invalidate any in-flight PDF load completions
	        hideLoading()
	        transitionRightPanel(toPDF: false, animated: animated)
        
        rightContainer.wantsLayer = true
        
        if updateContent {
            updateDetails()
        }
        updateCurrentHistoryViewMode(false, reason: "show_details")
        updateNavigationButtons()
    }

    private func showPDFPanel(animated: Bool = true) {
        isShowingPDF = true
        transitionRightPanel(toPDF: true, animated: animated)
        enforceWhitePDFBackground()
        updateCurrentHistoryViewMode(true, reason: "show_pdf")
        updateNavigationButtons()

        // Make keyboard scrolling work immediately when the PDF becomes visible.
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            guard self.window?.isKeyWindow == true else { return }
            if self.pdfFindHUD.isHidden {
                self.window?.makeFirstResponder(self.pdfView)
            }
        }
    }

    private func setRightPanelHitTesting(_ view: NSView, enabled: Bool) {
        (view as? HitTestControlling)?.allowsHitTesting = enabled
    }

    private func describeRightPanelState(_ state: RightPanelTransitionState) -> String {
        switch state {
        case .idle(let mode):
            return "idle(\(mode.rawValue))"
        case .transition(let from, let to):
            return "transition(\(from.rawValue)->\(to.rawValue))"
        }
    }

    private func animateOpacity(_ layer: CALayer?,
                                from: Float,
                                to: Float,
                                duration: CFTimeInterval,
                                timing: CAMediaTimingFunctionName = .easeOut,
                                key: String) {
        guard let layer else { return }
        layer.removeAnimation(forKey: key)
        let animation = CABasicAnimation(keyPath: "opacity")
        animation.fromValue = from
        animation.toValue = to
        animation.duration = duration
        animation.timingFunction = CAMediaTimingFunction(name: timing)
        layer.add(animation, forKey: key)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.opacity = to
        CATransaction.commit()
    }

    private func snapRightPanel(to targetMode: RightPanelViewMode,
                                showView: NSView,
                                hideView: NSView,
                                reason: String) {
        viewModeTransitionToken &+= 1
        viewModeTransitionWorkItem?.cancel()
        pendingRightPanelTransitionTarget = nil
        rightPanelTransitionState = .idle(targetMode)

        showView.wantsLayer = true
        hideView.wantsLayer = true
        showView.layer?.removeAllAnimations()
        hideView.layer?.removeAllAnimations()

        rightPanelTransitionBlurView.layer?.removeAllAnimations()
        rightPanelTransitionBlurView.isHidden = true
        if let blurLayer = rightPanelTransitionBlurView.layer {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            blurLayer.opacity = 0
            CATransaction.commit()
        }

        if let backgroundLayer = rightPDFBackgroundView.layer {
            backgroundLayer.removeAllAnimations()
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            backgroundLayer.opacity = targetMode == .pdf ? 1 : 0
            CATransaction.commit()
        }
        rightPDFBackgroundView.isHidden = targetMode != .pdf

        showView.isHidden = false
        hideView.isHidden = true
        showView.alphaValue = 1.0
        hideView.alphaValue = 1.0
        rightPanelContentHost.addSubview(showView, positioned: .above, relativeTo: hideView)
        setRightPanelHitTesting(showView, enabled: true)
        setRightPanelHitTesting(hideView, enabled: false)

        if let layer = showView.layer {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.opacity = 1
            layer.transform = CATransform3DIdentity
            CATransaction.commit()
        }
        if let layer = hideView.layer {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.opacity = 1
            layer.transform = CATransform3DIdentity
            CATransaction.commit()
        }

        viewModeLog("transition_snap reason=\(reason) state=\(describeRightPanelState(rightPanelTransitionState))")
    }

    private func transitionRightPanel(toPDF: Bool, animated: Bool) {
        let targetMode: RightPanelViewMode = toPDF ? .pdf : .details
        let showView = toPDF ? pdfView : detailsWebView
        let hideView = toPDF ? detailsWebView : pdfView

        guard animated, !shouldReduceMotion else {
            let reason = animated ? "reduce_motion" : "no_animation"
            snapRightPanel(to: targetMode, showView: showView, hideView: hideView, reason: reason)
            return
        }

        if case .transition = rightPanelTransitionState {
            if case .transition(_, let to) = rightPanelTransitionState, to == targetMode {
                viewModeLog("transition_inflight target=\(targetMode.rawValue) state=\(describeRightPanelState(rightPanelTransitionState))")
                return
            }
            pendingRightPanelTransitionTarget = targetMode
            viewModeLog("transition_queued target=\(targetMode.rawValue) state=\(describeRightPanelState(rightPanelTransitionState))")
            return
        }

        let fromMode: RightPanelViewMode
        switch rightPanelTransitionState {
        case .idle(let mode):
            fromMode = mode
        case .transition(let from, _):
            fromMode = from
        }

        if fromMode == targetMode {
            snapRightPanel(to: targetMode, showView: showView, hideView: hideView, reason: "already_visible")
            return
        }

        rightPanelTransitionState = .transition(from: fromMode, to: targetMode)
        pendingRightPanelTransitionTarget = nil

        viewModeTransitionToken &+= 1
        let token = viewModeTransitionToken
        viewModeTransitionWorkItem?.cancel()

        showView.wantsLayer = true
        hideView.wantsLayer = true
        showView.layer?.removeAllAnimations()
        hideView.layer?.removeAllAnimations()

        if let blurLayer = rightPanelTransitionBlurView.layer {
            blurLayer.removeAllAnimations()
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            blurLayer.opacity = 0
            CATransaction.commit()
        }
        rightPanelTransitionBlurView.isHidden = true

        let startTime = monotonicNow()
        let fastCycle = (startTime - lastViewModeSwitchTime) < rightPanelTransition.fastCycleThreshold
        lastViewModeSwitchTime = startTime
        let duration = rightPanelTransition.duration(forFastCycle: fastCycle)
        let transitionScale = rightPanelTransition.scale(forFastCycle: fastCycle)
        let offsetX = rightPanelTransition.translationX(forFastCycle: fastCycle)
        let direction: CGFloat = toPDF ? 1 : -1
        let incomingX = direction * offsetX
        let outgoingX = -direction * offsetX
        let springPreset = rightPanelTransition.springPreset(forFastCycle: fastCycle)

        let startHostSize = rightPanelContentHost.bounds.size
        let startContainerSize = rightContainer.bounds.size
        viewModeLog("transition_start t=\(String(format: "%.4f", startTime)) from=\(fromMode.rawValue) to=\(targetMode.rawValue) duration=\(String(format: "%.2f", duration)) fast=\(fastCycle) host=\(Int(startHostSize.width))x\(Int(startHostSize.height)) container=\(Int(startContainerSize.width))x\(Int(startContainerSize.height)) state=\(describeRightPanelState(rightPanelTransitionState))")

        showView.isHidden = false
        hideView.isHidden = false
        rightPanelContentHost.addSubview(showView, positioned: .above, relativeTo: hideView)

        setRightPanelHitTesting(hideView, enabled: false)
        setRightPanelHitTesting(showView, enabled: false)

        let incomingEnableDelay = duration * rightPanelTransition.incomingHitTestEnableFraction
        DispatchQueue.main.asyncAfter(deadline: .now() + incomingEnableDelay) { [weak self] in
            guard let self, self.viewModeTransitionToken == token else { return }
            self.setRightPanelHitTesting(showView, enabled: true)
        }

        if let backgroundLayer = rightPDFBackgroundView.layer {
            rightPDFBackgroundView.isHidden = false
            backgroundLayer.removeAllAnimations()
            let startOpacity: Float = toPDF ? 0 : 1
            let endOpacity: Float = toPDF ? 1 : 0
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            backgroundLayer.opacity = startOpacity
            CATransaction.commit()
            animateOpacity(backgroundLayer,
                           from: startOpacity,
                           to: endOpacity,
                           duration: duration * 0.75,
                           timing: .easeOut,
                           key: "right_panel_bg")
        }

        if rightPanelTransition.blurEnabled, let blurLayer = rightPanelTransitionBlurView.layer {
            rightPanelTransitionBlurView.isHidden = false
            rightPanelContentHost.addSubview(rightPanelTransitionBlurView, positioned: .above, relativeTo: showView)
            let maxOpacity = Float(rightPanelTransition.blurMaxOpacity)
            let blurDuration = max(0.08, duration * rightPanelTransition.blurFadeFraction)
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            blurLayer.opacity = maxOpacity
            CATransaction.commit()
            animateOpacity(blurLayer,
                           from: maxOpacity,
                           to: 0,
                           duration: blurDuration,
                           timing: .easeOut,
                           key: "right_panel_blur")
        }

        var showStart = CATransform3DIdentity
        showStart = CATransform3DTranslate(showStart, incomingX, 0, 0)
        showStart = CATransform3DScale(showStart, transitionScale, transitionScale, 1.0)
        var hideEnd = CATransform3DIdentity
        hideEnd = CATransform3DTranslate(hideEnd, outgoingX, 0, 0)
        hideEnd = CATransform3DScale(hideEnd, transitionScale, transitionScale, 1.0)

        if let layer = showView.layer {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.opacity = 0
            layer.transform = showStart
            CATransaction.commit()
            // Opacity should be a clean crossfade (no spring wobble).
            animateOpacity(layer, from: 0, to: 1, duration: duration, timing: .easeOut, key: "right_panel_in_opacity")
            animateLayer(layer, keyPath: "transform", to: CATransform3DIdentity, preset: springPreset, reduceMotion: false, basicDuration: duration)
        }
        if let layer = hideView.layer {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.opacity = 1
            layer.transform = CATransform3DIdentity
            CATransaction.commit()
            animateOpacity(layer, from: 1, to: 0, duration: duration, timing: .easeIn, key: "right_panel_out_opacity")
            animateLayer(layer, keyPath: "transform", to: hideEnd, preset: springPreset, reduceMotion: false, basicDuration: duration)
        }

        let work = DispatchWorkItem { [weak self] in
            guard let self, self.viewModeTransitionToken == token else { return }
            hideView.isHidden = true
            self.setRightPanelHitTesting(hideView, enabled: false)
            self.setRightPanelHitTesting(showView, enabled: true)
            if let layer = hideView.layer {
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                layer.opacity = 1
                layer.transform = CATransform3DIdentity
                CATransaction.commit()
            }
            if targetMode == .details {
                if let backgroundLayer = self.rightPDFBackgroundView.layer {
                    CATransaction.begin()
                    CATransaction.setDisableActions(true)
                    backgroundLayer.opacity = 0
                    CATransaction.commit()
                }
                self.rightPDFBackgroundView.isHidden = true
            }

            self.rightPanelTransitionBlurView.isHidden = true
            if let blurLayer = self.rightPanelTransitionBlurView.layer {
                blurLayer.removeAllAnimations()
                CATransaction.begin()
                CATransaction.setDisableActions(true)
                blurLayer.opacity = 0
                CATransaction.commit()
            }

            self.rightPanelTransitionState = .idle(targetMode)
            let endHostSize = self.rightPanelContentHost.bounds.size
            let endContainerSize = self.rightContainer.bounds.size
            if abs(endHostSize.width - startHostSize.width) > 0.5 ||
                abs(endHostSize.height - startHostSize.height) > 0.5 ||
                abs(endContainerSize.width - startContainerSize.width) > 0.5 ||
                abs(endContainerSize.height - startContainerSize.height) > 0.5 {
                self.viewModeLog("transition_resize host=\(Int(startHostSize.width))x\(Int(startHostSize.height))->\(Int(endHostSize.width))x\(Int(endHostSize.height)) container=\(Int(startContainerSize.width))x\(Int(startContainerSize.height))->\(Int(endContainerSize.width))x\(Int(endContainerSize.height))")
            }
            let endTime = monotonicNow()
            let elapsedMs = Int((endTime - startTime) * 1000.0)
            self.viewModeLog("transition_end t=\(String(format: "%.4f", endTime)) to=\(targetMode.rawValue) elapsed_ms=\(elapsedMs) state=\(self.describeRightPanelState(self.rightPanelTransitionState))")

            if let pending = self.pendingRightPanelTransitionTarget, pending != targetMode {
                self.pendingRightPanelTransitionTarget = nil
                self.transitionRightPanel(toPDF: pending == .pdf, animated: true)
            } else {
                self.pendingRightPanelTransitionTarget = nil
            }
        }
        viewModeTransitionWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + duration, execute: work)
    }

    private func runRightPanelTransitionStressTestIfRequested() {
        guard ProcessInfo.processInfo.environment["ARXIV_VIEWMODE_STRESS"] == "1" else { return }
        let requested = Int(ProcessInfo.processInfo.environment["ARXIV_VIEWMODE_STRESS_COUNT"] ?? "")
        let totalSwitches = max(20, min(30, requested ?? 24))
        let interval = max(rightPanelTransition.normalDuration, rightPanelTransition.fastDuration) + 0.06
        let initialDelay: CFTimeInterval = 0.8

        var remaining = totalSwitches
        var showNextPDF = !isShowingPDF
        NSLog("[ViewModeStress] start switches=\(totalSwitches) interval=\(interval)")

        func step() {
            guard remaining > 0 else {
                NSLog("[ViewModeStress] complete switches=\(totalSwitches)")
                return
            }
            if showNextPDF {
                showPDFPanel(animated: true)
            } else {
                showDetailsPanel(animated: true, updateContent: false)
            }
            showNextPDF.toggle()
            remaining -= 1
            DispatchQueue.main.asyncAfter(deadline: .now() + interval, execute: step)
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + initialDelay, execute: step)
    }

    // MARK: PDF Zoom

    private func resetPDFMagnifyState() {
        pdfMagnifyActive = false
        pdfMagnifyAnchorPoint = .zero
        pdfMagnifyAnchorPage = nil
    }

    private func pdfPrimaryScrollView() -> NSScrollView? {
        let scrollViews = descendantScrollViews(in: pdfView)
        if scrollViews.count == 1 {
            return scrollViews[0]
        }
        return scrollViews.first(where: { $0.documentView != nil }) ?? scrollViews.first
    }

    private func pdfVisibleRectInView() -> NSRect {
        if let scrollView = pdfPrimaryScrollView() {
            let clip = scrollView.contentView
            return pdfView.convert(clip.bounds, from: clip)
        }
        return pdfView.bounds
    }

    private func pdfMouseLocationInView() -> NSPoint? {
        guard let window = pdfView.window else { return nil }
        let windowPoint = window.convertPoint(fromScreen: NSEvent.mouseLocation)
        return pdfView.convert(windowPoint, from: nil)
    }

    private func pdfCenterAnchor(visibleRect: NSRect) -> (point: NSPoint, page: PDFPage?) {
        let viewCenter = NSPoint(x: visibleRect.midX, y: visibleRect.midY)
        let page = pdfView.page(for: viewCenter, nearest: false)
        return (viewCenter, page)
    }

    private func pdfZoomAnchor(for event: NSEvent?, allowMouseLocation: Bool) -> (point: NSPoint, page: PDFPage?) {
        let visibleRect = pdfVisibleRectInView()
        if let event {
            let point = pdfView.convert(event.locationInWindow, from: nil)
            if visibleRect.contains(point) {
                return (point, pdfView.page(for: point, nearest: false))
            }
        }
        if allowMouseLocation, let point = pdfMouseLocationInView() {
            if visibleRect.contains(point) {
                return (point, pdfView.page(for: point, nearest: false))
            }
        }
        return pdfCenterAnchor(visibleRect: visibleRect)
    }

    /// Recalculate and record the current visible center so subsequent zooms keep referencing the latest geometry.
    private func recalculatePDFZoomCenterAnchor() {
        let center = pdfCenterAnchor(visibleRect: pdfVisibleRectInView())
        pdfZoomCenterAnchorPoint = center.point
        pdfZoomCenterAnchorPage = center.page
    }

    private func pdfZoomDebugPageLabel(_ page: PDFPage?) -> String {
        guard let page else { return "none" }
        if let doc = pdfView.document {
            return "\(doc.index(for: page))"
        }
        return page.label ?? "?"
    }

    private func pdfZoomDebugLog(step: String,
                                 sOld: CGFloat,
                                 sNew: CGFloat,
                                 clip: NSClipView,
                                 docView: NSView?,
                                 anchorView: NSPoint,
                                 page: PDFPage?,
                                 pagePoint: NSPoint?,
                                 clipOriginBefore: NSPoint,
                                 clipOriginAfterTarget: NSPoint?,
                                 clipOriginAfterClamp: NSPoint?,
                                 anchorAfterScale: NSPoint?,
                                 anchorFinal: NSPoint?) {
        guard pdfZoomDebugEnabled else { return }

        let viewportSize = clip.bounds.size
        let docFrame = docView?.frame ?? .zero
        let visibleRect = pdfVisibleRectInView()

        let axSmall = docFrame.width < viewportSize.width
        let aySmall = docFrame.height < viewportSize.height

        func p(_ pt: NSPoint?) -> NSPoint {
            pt ?? NSPoint(x: CGFloat.nan, y: CGFloat.nan)
        }

        let clipAfterTarget = p(clipOriginAfterTarget)
        let clipAfterClamp = p(clipOriginAfterClamp)
        let aAfterScale = p(anchorAfterScale)
        let aFinal = p(anchorFinal)
        let aPage = p(pagePoint)

        let delta = NSPoint(x: aAfterScale.x - anchorView.x, y: aAfterScale.y - anchorView.y)
        let err = NSPoint(x: aFinal.x - anchorView.x, y: aFinal.y - anchorView.y)
        let errMag = hypot(err.x, err.y)

        NSLog(
            "[PDFZoom] step=%@ s=%.4f->%.4f viewport=%.1fx%.1f clipO_before=(%.2f,%.2f) clipO_target=(%.2f,%.2f) clipO_clamp=(%.2f,%.2f) docFrame=(%.2f,%.2f %.1fx%.1f) vis=(%.2f,%.2f %.1fx%.1f) mode_small=(%@,%@) A_v=(%.2f,%.2f) page=%@ A_page=(%.2f,%.2f) A_v_afterScale=(%.2f,%.2f) delta=(%.2f,%.2f) A_v_final=(%.2f,%.2f) err=(%.2f,%.2f) errMag=%.2f",
            step,
            sOld, sNew,
            viewportSize.width, viewportSize.height,
            clipOriginBefore.x, clipOriginBefore.y,
            clipAfterTarget.x, clipAfterTarget.y,
            clipAfterClamp.x, clipAfterClamp.y,
            docFrame.origin.x, docFrame.origin.y, docFrame.size.width, docFrame.size.height,
            visibleRect.origin.x, visibleRect.origin.y, visibleRect.size.width, visibleRect.size.height,
            axSmall ? "1" : "0", aySmall ? "1" : "0",
            anchorView.x, anchorView.y,
            pdfZoomDebugPageLabel(page),
            aPage.x, aPage.y,
            aAfterScale.x, aAfterScale.y,
            delta.x, delta.y,
            aFinal.x, aFinal.y,
            err.x, err.y,
            errMag
        )
    }

    private func runPDFZoomReproIfRequested() {
        guard ProcessInfo.processInfo.environment["ARXIV_PDF_ZOOM_REPRO"] == "1" else { return }
        guard didRunPDFZoomRepro == false else { return }
        didRunPDFZoomRepro = true

        // Allow the PDFView to finish swapping documents/layout.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
            self?.runPDFZoomRepro()
        }
    }

    private func runPDFZoomRepro() {
        guard isShowingPDF else { return }

        if let path = ProcessInfo.processInfo.environment["ARXIV_PDF_ZOOM_REPRO_PDF_PATH"],
           !path.isEmpty,
           FileManager.default.fileExists(atPath: path),
           let url = URL(string: "file://\(path)"),
           let doc = PDFDocument(url: url),
           doc.pageCount > 0 {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            pdfView.document = doc
            CATransaction.commit()
            pdfView.goToFirstPage(nil)
        }

        guard pdfView.document != nil else { return }
        guard let scrollView = pdfPrimaryScrollView(), let docView = scrollView.documentView else { return }
        let clip = scrollView.contentView

        // Known zoom-in value where page edges are typically not visible.
        let center = pdfCenterAnchor(visibleRect: pdfVisibleRectInView())
        applyPDFScale(2.0, anchor: center.point, page: center.page)

        // Known scroll position (middle of document) in documentView coordinates.
        let viewportHeight = clip.bounds.height
        let minY = docView.bounds.minY
        let maxY = max(minY, docView.bounds.maxY - viewportHeight)
        let midY = (minY + maxY) / 2
        let originTarget = NSPoint(x: clip.bounds.origin.x, y: midY)
        let originClamped = clampPDFScrollOrigin(originTarget, clip: clip, docView: docView)
        if let lock = rightHorizontalScrollLocks[ObjectIdentifier(scrollView)] {
            lock.updateLockedX(originClamped.x, clamp: false)
        }
        clip.setBoundsOrigin(originClamped)
        scrollView.reflectScrolledClipView(clip)

        let cycles = Int(ProcessInfo.processInfo.environment["ARXIV_PDF_ZOOM_REPRO_CYCLES"] ?? "") ?? 12
        let interval = Double(ProcessInfo.processInfo.environment["ARXIV_PDF_ZOOM_REPRO_INTERVAL"] ?? "") ?? 0.12
        var remaining = max(2, cycles * 2)
        var zoomInNext = true

        pdfZoomReproWorkItem?.cancel()

        func step() {
            guard remaining > 0 else {
                NSLog("[PDFZoomRepro] complete")
                return
            }
            remaining -= 1
            let factor: CGFloat = zoomInNext ? 1.1 : (1.0 / 1.1)
            zoomInNext.toggle()
            let anchor = self.pdfCenterAnchor(visibleRect: self.pdfVisibleRectInView())
            let target = self.pdfView.scaleFactor * factor
            self.applyPDFScale(target, anchor: anchor.point, page: anchor.page)
            DispatchQueue.main.asyncAfter(deadline: .now() + interval, execute: step)
        }

        NSLog("[PDFZoomRepro] start cycles=\(cycles) interval=\(interval)")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: step)
    }

    private func clampPDFScrollOrigin(_ origin: NSPoint, clip: NSClipView, docView: NSView?) -> NSPoint {
        var out = origin
        guard let docView else {
            return clip.constrainBoundsRect(NSRect(origin: out, size: clip.bounds.size)).origin
        }

        let clipSize = clip.bounds.size
        let docFrame = docView.frame

        if docFrame.width >= clipSize.width {
            let minX = docFrame.minX
            let maxX = max(minX, docFrame.maxX - clipSize.width)
            out.x = min(max(out.x, minX), maxX)
        } else {
            out.x = docFrame.minX + (docFrame.width - clipSize.width) / 2
        }

        if docFrame.height >= clipSize.height {
            let minY = docFrame.minY
            let maxY = max(minY, docFrame.maxY - clipSize.height)
            out.y = min(max(out.y, minY), maxY)
        } else {
            out.y = docFrame.minY + (docFrame.height - clipSize.height) / 2
        }

        return out
    }

    private func clampPDFScale(_ scale: CGFloat) -> CGFloat {
        var clamped = scale
        let minScale = pdfView.minScaleFactor
        let maxScale = pdfView.maxScaleFactor
        if minScale > 0 { clamped = max(clamped, minScale) }
        if maxScale > 0 { clamped = min(clamped, maxScale) }
        return clamped
    }

    private func applyPDFScale(_ scale: CGFloat, anchor: NSPoint, page: PDFPage?) {
        guard pdfView.document != nil else { return }
        let clamped = clampPDFScale(scale)
        let currentScale = pdfView.scaleFactor
        guard abs(clamped - currentScale) > 0.0001 else { return }

        pdfView.autoScales = false

        guard let scrollView = pdfPrimaryScrollView(),
              let docViewBefore = scrollView.documentView else {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            pdfView.scaleFactor = clamped
            CATransaction.commit()
            recalculatePDFZoomCenterAnchor()
            return
        }

        let clip = scrollView.contentView
        let lock = rightHorizontalScrollLocks[ObjectIdentifier(scrollView)]

        // Resolve a page deterministically; using nearest=false can return nil when anchored in whitespace.
        let resolvedPage = page
            ?? pdfView.page(for: anchor, nearest: true)
            ?? pdfView.currentPage
            ?? pdfView.document?.page(at: 0)

        guard let resolvedPage else {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            pdfView.scaleFactor = clamped
            CATransaction.commit()
            recalculatePDFZoomCenterAnchor()
            return
        }

        // Compute the anchor's offset within the visible document rect (document-view coordinates).
        // This is robust to flipped coordinate systems and avoids mixing clip/doc coordinate spaces.
        let visibleDocRectBefore = clip.documentVisibleRect
        let anchorDocBefore = pdfView.convert(anchor, to: docViewBefore)
        let offsetInViewport = NSPoint(x: anchorDocBefore.x - visibleDocRectBefore.origin.x,
                                       y: anchorDocBefore.y - visibleDocRectBefore.origin.y)

        // During zoom, allow PDFKit/AppKit to adjust both X and Y to preserve the anchor.
        lock?.setLocksHorizontal(false)

        // Snapshot the anchor in page coordinates, then re-find it after scaling.
        let pagePoint = pdfView.convert(anchor, to: resolvedPage)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        pdfView.scaleFactor = clamped
        CATransaction.commit()

        pdfView.layoutSubtreeIfNeeded()
        scrollView.layoutSubtreeIfNeeded()

        let docViewAfter = scrollView.documentView ?? docViewBefore
        let anchorViewAfter = pdfView.convert(pagePoint, from: resolvedPage)
        let anchorDocAfter = pdfView.convert(anchorViewAfter, to: docViewAfter)

        let targetOriginDoc = NSPoint(x: anchorDocAfter.x - offsetInViewport.x,
                                      y: anchorDocAfter.y - offsetInViewport.y)

        clip.scroll(to: targetOriginDoc)
        scrollView.reflectScrolledClipView(clip)

        // Re-lock horizontal at the post-zoom X so gestures don't pan horizontally,
        // while preserving the new anchor-consistent X (fixes "zoom drifts left").
        let postZoomOrigin = clip.bounds.origin
        lock?.updateLockedX(postZoomOrigin.x, clamp: false)
        lock?.setLocksHorizontal(true)

        recalculatePDFZoomCenterAnchor()
    }

    private func zoomPDFStep(increase: Bool) {
        guard isShowingPDF, pdfView.document != nil else { return }
        let step = pdfZoomStep
        let current = pdfView.scaleFactor
        let epsilon: CGFloat = 0.0001
        let target: CGFloat
        if increase {
            let next = floor((current + epsilon) / step) + 1
            target = next * step
        } else {
            let prev = ceil((current - epsilon) / step) - 1
            target = prev * step
        }
        let anchor = pdfZoomAnchor(for: nil, allowMouseLocation: false)
        applyPDFScale(target, anchor: anchor.point, page: anchor.page)
    }

    private func handlePDFMagnify(_ event: NSEvent) -> Bool {
        guard isShowingPDF, pdfView.document != nil else { return false }
        let phase = event.phase
        if phase == [] {
            let anchor = pdfZoomAnchor(for: event, allowMouseLocation: true)
            let target = pdfView.scaleFactor * (1 + event.magnification)
            applyPDFScale(target, anchor: anchor.point, page: anchor.page)
            return true
        }

        if phase.contains(.began) || !pdfMagnifyActive {
            let anchor = pdfZoomAnchor(for: event, allowMouseLocation: true)
            pdfMagnifyAnchorPoint = anchor.point
            pdfMagnifyAnchorPage = anchor.page
            pdfMagnifyActive = true
        }

        let target = pdfView.scaleFactor * (1 + event.magnification)
        applyPDFScale(target, anchor: pdfMagnifyAnchorPoint, page: pdfMagnifyAnchorPage)

        if phase.contains(.ended) || phase.contains(.cancelled) {
            pdfMagnifyActive = false
        }

        return true
    }

    @objc private func handlePDFMagnificationGesture(_ gr: NSMagnificationGestureRecognizer) {
        guard isShowingPDF, pdfView.document != nil else { return }

        switch gr.state {
        case .began:
            pdfGestureMagnifyBaseScale = pdfView.scaleFactor
            let anchor = gr.location(in: pdfView)
            pdfMagnifyAnchorPoint = anchor
            pdfMagnifyAnchorPage = pdfView.page(for: anchor, nearest: true)
            pdfMagnifyActive = true
            pdfView.suppressMagnifyEvents = true

        case .changed:
            guard pdfMagnifyActive else { return }
            let target = pdfGestureMagnifyBaseScale * (1 + gr.magnification)
            applyPDFScale(target, anchor: pdfMagnifyAnchorPoint, page: pdfMagnifyAnchorPage)

        case .ended, .cancelled, .failed:
            pdfMagnifyActive = false
            pdfView.suppressMagnifyEvents = false
            gr.magnification = 0

        default:
            break
        }
    }

	    // Canonical PDF presentation pipeline (used by Enter-key flow and by PDF link clicks in the details panel).
	    private func presentPDF(remoteURL: URL, trigger: String, animateViewMode: Bool = false) {
	        let normalizedURL = normalizedPDFURL(remoteURL)
        let metadata = metadataForCurrentSelection(for: normalizedURL)
        pdfCache.registerMetadata(metadata, for: normalizedURL)
        let demandRequest = PDFCacheManager.PrefetchRequest(url: normalizedURL, metadata: metadata)
        pdfCache.prefetch([demandRequest], priority: 1, reason: "present/on-demand")
	        pdfLoadToken &+= 1
	        let token = pdfLoadToken
	        let startTime = monotonicNow()
	        let cacheKey = pdfCache.cacheKey(for: normalizedURL)
	        let state = pdfCache.debugStateDescription(for: normalizedURL)
	        NSLog("[PDFEager] pdf_present_request trigger=\(trigger) key=\(cacheKey.prefix(8)) state=\(state)")

	        if isShowingPDF {
	            showPDFPanel(animated: false)
	        }
	        hidePDFFindHUD()
	        hideLoading()

	        let handlePrepared: (PDFCacheManager.PreparedPDF, String) -> Void = { [weak self] prepared, source in
	            self?.renderPreparedPDF(
	                prepared,
	                remoteURL: normalizedURL,
	                token: token,
	                startTime: startTime,
	                source: source,
	                cacheKey: cacheKey,
	                animateViewMode: animateViewMode
	            )
	        }

	        if let prepared = pdfCache.preparedPDFIfReady(for: normalizedURL) {
	            handlePrepared(prepared, "local-ready")
	            return
	        }

	        pdfCache.whenPreparedPDF(for: normalizedURL) { [weak self] result in
	            guard let self, self.pdfLoadToken == token else { return }
	            switch result {
	            case .success(let prepared):
	                handlePrepared(prepared, "local-wait")
	            case .failure(let error):
	                NSLog("[PDFEager] pdf_present_failed trigger=\(trigger) key=\(cacheKey.prefix(8)) error=\(error)")
	                self.pdfCache.trackLifecycleStage(.failed,
	                                                  for: normalizedURL,
	                                                  message: "presentError \(error)")
	                self.showDetailsStatus(message: "PDF is still preparing or failed to download.")
	            }
	        }
	    }

	    private func renderPreparedPDF(_ prepared: PDFCacheManager.PreparedPDF,
	                                   remoteURL: URL,
	                                   token: Int,
	                                   startTime: CFTimeInterval,
	                                   source: String,
	                                   cacheKey: String,
	                                   animateViewMode: Bool) {
	        pdfCache.trackLifecycleStage(.renderQueued,
	                                     for: remoteURL,
	                                     fileURL: prepared.fileURL,
	                                     fileSize: prepared.byteCount,
	                                     lastModified: prepared.lastModified,
	                                     message: source)

	        pendingRenderWork?.cancel()
	        var workItem: DispatchWorkItem!
	        workItem = DispatchWorkItem { [weak self] in
	            guard let self else { return }
	            guard workItem?.isCancelled == false else { return }
	            guard self.pdfLoadToken == token else { return }
	            let cacheKeyObj = cacheKey as NSString
	            var document: PDFDocument?

	            if let cached = self.pdfDocumentCache.object(forKey: cacheKeyObj) {
	                document = cached
	                self.pdfCache.trackLifecycleStage(.validated,
	                                                  for: remoteURL,
	                                                  fileURL: prepared.fileURL,
	                                                  fileSize: prepared.byteCount,
	                                                  lastModified: prepared.lastModified,
	                                                  message: "cache-hit pageCount=\(cached.pageCount)")
	            } else {
	                autoreleasepool {
	                    let candidate = PDFDocument(url: prepared.fileURL)
	                    if let candidate = candidate, candidate.pageCount > 0 {
	                        self.pdfDocumentCache.setObject(candidate, forKey: cacheKeyObj)
	                        self.pdfCache.trackLifecycleStage(.validated,
	                                                          for: remoteURL,
	                                                          fileURL: prepared.fileURL,
	                                                          fileSize: prepared.byteCount,
	                                                          lastModified: prepared.lastModified,
	                                                          message: "pageCount=\(candidate.pageCount)")
	                    }
	                    document = candidate
	                }
	            }

	            guard let validated = document, validated.pageCount > 0 else {
	                let reason = document == nil ? "pdfkit_init_failed" : "empty-page-count"
	                self.pdfCache.trackLifecycleStage(.failed,
	                                                  for: remoteURL,
	                                                  fileURL: prepared.fileURL,
	                                                  fileSize: prepared.byteCount,
	                                                  lastModified: prepared.lastModified,
	                                                  message: reason)
                DispatchQueue.main.async {
                    self.pendingRenderWork = nil
                    self.presentPDFRenderFailure(message: "PDF could not be rendered (\(reason)).")
                }
	                return
	            }

	            DispatchQueue.main.async {
	                guard self.pdfLoadToken == token else { return }
	                self.pendingRenderWork = nil
	                let shouldAnimate = animateViewMode && !self.isShowingPDF
	                self.showPDFPanel(animated: shouldAnimate)
	                self.applyPDFDocument(
	                    validated,
	                    token: token,
	                    source: source,
	                    startTime: startTime,
	                    cacheKey: cacheKey
	                )
	                self.pdfCache.trackLifecycleStage(.rendered,
	                                                  for: remoteURL,
	                                                  fileURL: prepared.fileURL,
	                                                  fileSize: prepared.byteCount,
	                                                  lastModified: prepared.lastModified,
	                                                  message: "source=\(source)")
	            }
	        }

	        pendingRenderWork = workItem
	        pdfRenderQueue.async(execute: workItem)
	    }

	    private func metadataForCurrentSelection(for url: URL) -> PDFCacheManager.Metadata {
	        if let idx = selectedFilteredIndex() {
	            return pdfMetadata(for: filtered[idx], url: url)
	        }
	        return pdfMetadata(with: url)
	    }

	    private func headerValues(for filteredIndex: Int) -> (date: String?, authors: String?)? {
	        guard filteredIndex >= 0, filteredIndex < filtered.count else { return nil }
	        let paper = filtered[filteredIndex]
	        let rawAuthors = stripLeadingLabel(paper.authors, label: "Authors")
	        let authorText = decodeTeXAccents(rawAuthors)
	            .replacingOccurrences(of: "\n", with: " ")
	            .components(separatedBy: .whitespacesAndNewlines)
	            .filter { !$0.isEmpty }
	            .joined(separator: " ")
	        let dateText = dateOnlyDisplayString(from: paper.dateLine)
	        return (dateText, authorText)
	    }

	    private func showDetailsStatus(message: String) {
	        guard !isShowingPDF else { return }
	        let idx = selectedFilteredIndex()
	        let total = filtered.count
	        let headers = idx.flatMap { headerValues(for: $0) }
	        detailsWebView.loadHTMLString(
	            buildDetailsStatusHTML(
	                message,
	                paperIndex: idx.map { $0 + 1 },
	                paperTotal: total,
	                leftHeaderText: headers?.date,
	                centerHeaderText: headers?.authors
	            ),
	            baseURL: nil
	        )
	    }

	    private func presentPDFRenderFailure(message: String) {
	        showDetailsStatus(message: message)
	    }

    private func openPDFInRightPanel(forRow row: Int, trigger: String) {
        guard row >= 0, row < filtered.count else { return }
        let p = filtered[row]
        guard let pdfURL = pdfURL(for: p) else {
            openAbs(row)
            return
        }
        presentPDF(remoteURL: pdfURL, trigger: trigger, animateViewMode: true)
    }

    // MARK: Search (left)

    private func normalizedSearchQuery(_ raw: String) -> String {
        raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private func tokenizedPrefixMatch(query: String, text: String) -> Bool {
        guard !query.isEmpty else { return true }
        let tokens = text.lowercased().split { ch in
            !(ch.isLetter || ch.isNumber)
        }
        return tokens.contains { $0.hasPrefix(query) }
    }

    private func paperMatchesPrefix(_ paper: Paper, query: String) -> Bool {
        let authorYear = decodeTeXAccents(leftAuthorYearText(paper: paper))
        let title = decodeTeXAccents(paper.title)
        let cats = decodeTeXAccents(stripLeadingLabel(paper.categories, label: "Categories"))
        let abs = decodeTeXAccents(paper.abstractText)
        var parts = [authorYear, title, cats, abs]
        if !keywordsFromAppleScript.isEmpty {
            let present = keywordsPresent(in: paper, keywords: keywordsFromAppleScript)
            if !present.isEmpty { parts.append(present.joined(separator: " ")) }
        }
        let corpus = parts.joined(separator: " ").lowercased()
        let q = query.lowercased()
        return corpus.contains(q)
    }

    @objc private func searchChanged() {
        let q = normalizedSearchQuery(searchField.stringValue)
        logSearchDebug("searchChanged value=\(searchField.stringValue) textColor=\(String(describing: searchField.textColor))")
        let priorSelected: Paper? = {
            let row = tableView.selectedRow
            guard let idx = globalIndex(forTableRow: row) else { return nil }
            guard idx >= 0, idx < filtered.count else { return nil }
            return filtered[idx]
        }()
        if q.isEmpty {
            publicationStore.setFiltered(allItems)
        } else {
            publicationStore.setFiltered(allItems.filter { paperMatchesPrefix($0, query: q) })
        }

        reflowLeft()
        updateSuggestions(for: q)

        if !filtered.isEmpty {
            if let priorSelected,
               let idx = filtered.firstIndex(of: priorSelected) {
                selectFilteredIndex(idx, scroll: true, reason: "search-preserve")
            } else {
                selectFilteredIndex(0, scroll: true, reason: "search-first")
            }
            updateNavigationButtons()
        } else {
            detailsWebView.loadHTMLString(buildDetailsStatusHTML("No matches.", paperIndex: nil, paperTotal: 0, leftHeaderText: nil, centerHeaderText: nil), baseURL: nil)
            // If we were showing a PDF, force the right panel back to the details view so the
            // search result state is visible even when no results or no PDF.
            if isShowingPDF {
                showDetailsPanel(animated: false, updateContent: false)
            }
            updateNavigationButtons()
        }
    }

    private func updateSuggestions(for query: String) {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else {
            clearSuggestionHover(animated: false)
            suggestions = []
            suggestionsTable.reloadData()
            suggestionSelectionIndex = -1
            setSuggestionsVisible(false, animated: true)
            return
        }

        let results = searchIndex.suggest(query: q, maxResults: 8)
        let filteredResults = results.filter { filteredIndex(for: $0.paperKey) != nil }
        let previousSuggestions = suggestions
        let previousCount = suggestions.count
        let suggestionsChanged = filteredResults != previousSuggestions
        suggestions = filteredResults
        suggestionsTable.deselectAll(nil)
        suggestionSelectionIndex = -1
        if suggestionsChanged {
            clearSuggestionHover(animated: false)
        }
        if suggestions.count != previousCount {
            suggestionsTable.reloadData()
        }
        layoutSuggestionsDropdown()
        if suggestions.isEmpty {
            setSuggestionsVisible(false, animated: true)
        } else {
            setSuggestionsVisible(true, animated: true)
        }
        syncSuggestionHoverFromMouse(animated: false)
        refreshSuggestionTextColors()
    }

    // MARK: Pagination + selection mapping

    private func availableListHeight() -> CGFloat {
        max(1, tableScroll.bounds.height)
    }

    private func rowHeightForFilteredIndex(_ index: Int) -> CGFloat {
        guard index >= 0, index < filtered.count else { return minRowHeight }
        let wrapW = leftWrapWidth()

        let leftW = max(1, min(keywordColumnTabX, wrapW))
        let gap = keywordSeparatorGap
        let rightW = max(1, wrapW - (leftW + gap))

        let pstyle = NSMutableParagraphStyle()
        pstyle.lineBreakMode = .byWordWrapping

        let colors = leftRowTextColors(isSelected: false, isActive: true)
        let paper = filtered[index]

        let leftAttr = leftAttributedAuthorText(
            for: paper,
            rowNumber: index + 1,
            paragraphStyle: pstyle,
            titleFont: leftRowTitleFont,
            secondaryFont: leftRowSecondaryFont,
            titleColor: colors.title,
            secondaryColor: colors.secondary
        )
        let leftBounding = leftAttr.boundingRect(
            with: NSSize(width: leftW, height: .greatestFiniteMagnitude),
            options: [.usesLineFragmentOrigin, .usesFontLeading]
        )

        let rightAttr = leftAttributedKeywordsText(
            for: paper,
            paragraphStyle: pstyle,
            secondaryFont: leftRowSecondaryFont,
            secondaryEmphasisFont: leftRowSecondaryEmphasisFont,
            secondaryColor: colors.secondary
        )
        let rightBounding = (rightAttr?.boundingRect(
            with: NSSize(width: rightW, height: .greatestFiniteMagnitude),
            options: [.usesLineFragmentOrigin, .usesFontLeading]
        )) ?? .zero

        let h = ceil(max(leftBounding.height, rightBounding.height)) + leftCellVerticalInsetY
        return max(minRowHeight, h)
    }

    private func recomputePagination(preserveSelection: Bool, reason: String) {
        let priorSelectedIndex = preserveSelection ? selectedFilteredIndex() : nil
        let availableHeight = availableListHeight()
        let inset = max(0, tableScroll.contentInsets.top)

        paginator.recompute(
            itemCount: filtered.count,
            availableHeight: availableHeight,
            minTopBottomInset: inset,
            headerRowHeight: headerRowHeight,
            rowHeightForFilteredIndex: { [weak self] idx in
                self?.rowHeightForFilteredIndex(idx) ?? self?.minRowHeight ?? 24
            }
        )

        if let idx = priorSelectedIndex,
           let page = paginator.pageIndex(containingGlobalFilteredIndex: idx) {
            // Keep the user on the closest equivalent page after resizing or filtering.
            currentPageIndex = page
        } else {
            currentPageIndex = max(0, min(currentPageIndex, max(0, paginator.pageCount - 1)))
        }

        updatePageControlVisibility()
        updatePageControlTitle()
        updatePageStepperState()

        if let idx = priorSelectedIndex {
            selectFilteredIndex(idx, scroll: false, reason: "pagination-preserve-\(reason)")
        }
    }

    private func globalIndex(forTableRow row: Int) -> Int? {
        // Table row (current page slice) → global filtered index mapping.
        guard row > 0 else { return nil } // row 0 is header
        let range = paginator.range(forPage: currentPageIndex)
        let dataRow = row - 1
        let idx = range.lowerBound + dataRow
        guard idx >= range.lowerBound, idx < range.upperBound else { return nil }
        return idx
    }

    private func tableRow(forGlobalFilteredIndex idx: Int) -> Int? {
        let range = paginator.range(forPage: currentPageIndex)
        guard range.contains(idx) else { return nil }
        return (idx - range.lowerBound) + 1
    }

    private func selectedFilteredIndex() -> Int? {
        globalIndex(forTableRow: tableView.selectedRow)
    }

    private func ensureDefaultSelectionIfNeeded(reason: String) {
        guard selectedFilteredIndex() == nil else { return }
        guard !filtered.isEmpty else { return }
        selectFilteredIndex(0, scroll: true, reason: reason)
    }

    private func selectFilteredIndex(_ idx: Int, scroll: Bool, reason: String) {
        guard idx >= 0, idx < filtered.count else { return }

        // Search → page navigation: move to the owning page before selecting the row.
        if let page = paginator.pageIndex(containingGlobalFilteredIndex: idx),
           page != currentPageIndex {
            currentPageIndex = page
            updatePageControlTitle()
            updatePageStepperState()
            tableView.reloadData()
            DispatchQueue.main.async { [weak self] in
                self?.enforceSidebarWidthBounds(reason: "page_change_select")
            }
        }

        guard let row = tableRow(forGlobalFilteredIndex: idx) else { return }
        let priorRow = tableView.selectedRow
        if priorRow != row {
            selectionChangeFromCode = true
            tableView.selectRowIndexes(IndexSet(integer: row), byExtendingSelection: false)
            selectionChangeFromCode = false
        }
        if scroll { tableView.scrollRowToVisible(row) }
        if isShowingPDF {
            if let url = pdfURL(for: filtered[idx]) {
                presentPDF(remoteURL: url, trigger: "select-\(reason)")
                prefetchNeighborPDFs(around: idx, reason: "select-\(reason)")
            } else {
                // If there is no PDF for this selection, switch to the HTML/details view so the search still works.
                showDetailsPanel(animated: true, updateContent: true)
            }
        } else {
            updateDetails()
        }
        updateNavigationButtons()
    }

    private func filteredIndex(for key: PaperKey) -> Int? {
        filtered.firstIndex { $0.key == key }
    }

    private func updatePageControlVisibility() {
        // Hide the page navigation control so the publications table no longer exposes pagination UI.
        pageControlContainer.isHidden = true
        layoutHeaderControls()
    }

    private func updatePageControlTitle() {
        let page = max(0, min(currentPageIndex, max(0, paginator.pageCount - 1)))
        let title = "Page \(page + 1)"
        if pageMenuButton.title != title {
            pageMenuButton.title = title
            pageMenuButton.updateTint()
        }
    }

    private var pageStepperRelayoutInProgress = false
    private func updatePageStepperState(triggerLayout: Bool = true) {
        let pageCount = paginator.pageCount
        // Always show when the sidebar is visible; gate enablement (not visibility) on page count.
        let sidebarShown = sidebarVisible || leftContainer.frame.width > 2
        let shouldShow = sidebarShown
        let wasHidden = pageStepperContainer.isHidden
        pageStepperContainer.isHidden = !shouldShow

        let canStepBack = (pageCount > 1) && currentPageIndex > 0
        let canStepForward = (pageCount > 1) && currentPageIndex < max(0, pageCount - 1)
        pagePrevButton.isEnabled = canStepBack
        pageNextButton.isEnabled = canStepForward
        pagePrevButton.updateTint()
        pageNextButton.updateTint()

        if triggerLayout, wasHidden != pageStepperContainer.isHidden, !pageStepperRelayoutInProgress {
            pageStepperRelayoutInProgress = true
            layoutLeftContainerSubviews()
            pageStepperRelayoutInProgress = false
        }
    }

    // MARK: Left layout

        private func leftPreferredColumnWidth() -> CGFloat {
            // Ensure the column can grow beyond the viewport so users can pan horizontally.
            let visible = max(220, tableScroll.contentSize.width)
            let contentFit = max(220, desiredMinSidebarWidthForCurrentPage(maxLeft: .greatestFiniteMagnitude) - (2 * PANEL_INSET))
            return max(visible, contentFit)
        }

        private func reflowLeft() {
            // Ensure split view sizing is fresh before measuring column widths.
            layoutLeftContainerSubviews()
            leftContainer.layoutSubtreeIfNeeded()
            tableScroll.layoutSubtreeIfNeeded()
            if let col = tableView.tableColumns.first {
                col.width = leftPreferredColumnWidth()
            }

            recomputeKeywordTabX()
            updateLeftHeaderText()

	        recomputePagination(preserveSelection: true, reason: "reflow")
	        let visibleRows = max(0, paginator.range(forPage: currentPageIndex).count)
	        tableView.noteHeightOfRows(withIndexesChanged: IndexSet(integersIn: 0...max(0, visibleRows)))
	        tableView.reloadData()
	        tableView.layoutSubtreeIfNeeded()
	        tableScroll.layoutSubtreeIfNeeded()
	        layoutLeftTableUnderlay()

	        tableView.menu = rowMenu

            // Keep the sidebar minimum width aligned to the current page's Author&Year strings.
            // (When the sidebar is hidden, this is intentionally a no-op.)
            enforceSidebarWidthBounds(reason: "reflow")
	    }

    private func launchPageRangeForSidebarSizing() -> Range<Int> {
        // Prefer the current page range once pagination is available.
        if paginator.pageCount > 0 {
            let r = paginator.range(forPage: currentPageIndex)
            if !r.isEmpty { return r }
        }

        // Fallback: early launch before pagination is computed.
        if filtered.isEmpty { return 0..<0 }
        return 0..<min(filtered.count, 24)
    }

    private func measureSingleLineWidth(_ s: NSAttributedString) -> CGFloat {
        let rect = s.boundingRect(
            with: NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude),
            options: [.usesLineFragmentOrigin, .usesFontLeading]
        )
        return ceil(max(0, rect.width))
    }

    private func maxAuthorYearWidthForLaunchRows(_ range: Range<Int>) -> CGFloat {
        guard !range.isEmpty else { return 0 }
        let pstyle = NSMutableParagraphStyle()
        pstyle.lineBreakMode = .byClipping
        let colors = leftRowTextColors(isSelected: false, isActive: true)

        var maxWidth: CGFloat = 0
        for idx in range {
            guard idx >= 0, idx < filtered.count else { continue }
            let attr = leftAttributedAuthorText(
                for: filtered[idx],
                rowNumber: idx + 1,
                paragraphStyle: pstyle,
                titleFont: leftRowTitleFont,
                secondaryFont: leftRowSecondaryFont,
                titleColor: colors.title,
                secondaryColor: colors.secondary
            )
            let w = measureSingleLineWidth(attr)
            if w > maxWidth { maxWidth = w }
        }

        return maxWidth
    }

    private func maxTwoKeywordWidthForLaunchRows(_ range: Range<Int>) -> CGFloat {
        guard !range.isEmpty else { return 0 }
        guard !keywordsFromAppleScript.isEmpty else { return 0 }

        let pstyle = NSMutableParagraphStyle()
        pstyle.lineBreakMode = .byClipping
        let colors = leftRowTextColors(isSelected: false, isActive: true)

        var maxWidth: CGFloat = 0
        for idx in range {
            guard idx >= 0, idx < filtered.count else { continue }
            let present = dedupePluralKeywordsForDisplay(
                keywordsPresent(in: filtered[idx], keywords: keywordsFromAppleScript)
            )
            let two = Array(present.prefix(2))
            guard !two.isEmpty else { continue }

            let result = NSMutableAttributedString(
                string: "",
                attributes: [
                    .font: leftRowSecondaryFont,
                    .paragraphStyle: pstyle,
                    .foregroundColor: colors.secondary
                ]
            )

            for (i, kw) in two.enumerated() {
                if i > 0 {
                    result.append(NSAttributedString(
                        string: ", ",
                        attributes: [
                            .font: leftRowSecondaryFont,
                            .paragraphStyle: pstyle,
                            .foregroundColor: colors.secondary
                        ]
                    ))
                }
                result.append(NSAttributedString(
                    string: kw,
                    attributes: [
                        .font: leftRowSecondaryEmphasisFont,
                        .paragraphStyle: pstyle,
                        .foregroundColor: colors.secondary
                    ]
                ))
            }

            let w = measureSingleLineWidth(result)
            if w > maxWidth { maxWidth = w }
        }

        return maxWidth
    }

    private func desiredLaunchSidebarWidth(maxLeft: CGFloat) -> CGFloat {
        // Tight launch sizing: fit all Author&Year strings from the populated rows,
        // and reserve width for up to 2 keywords (but do not size to fit more).
        let range = launchPageRangeForSidebarSizing()
        let authorW = maxAuthorYearWidthForLaunchRows(range)
        let kw2W = maxTwoKeywordWidthForLaunchRows(range)

        let gutter: CGFloat = 10
        let tabX = max(180, authorW + gutter)
        let keywordHeaderMin = ("Keyword(s)" as NSString).size(withAttributes: [.font: leftRowSecondaryFont]).width
        let rightW = max(keywordHeaderMin + 10, kw2W)

        let neededColumnWidth = leftRowTextInset + tabX + keywordSeparatorGap + rightW + leftRowTextInset
        let neededLeftContainerWidth = neededColumnWidth + (2 * PANEL_INSET)

        return min(maxLeft, max(minSidebarWidth, neededLeftContainerWidth))
    }

    private func rebuildLeftColumnMetrics() {
        let total = max(1, allItems.count)
        cachedRowNumberDigits = String(total).count

        var maxLeftWidth: CGFloat = 0
        let attrs: [NSAttributedString.Key: Any] = [.font: leftRowTitleFont]

        for (i, p) in allItems.enumerated() {
            let prefix = "\(i + 1). "
            let leftText = prefix + decodeTeXAccents(leftAuthorYearText(paper: p))
            let w = (leftText as NSString).size(withAttributes: attrs).width
            if w > maxLeftWidth { maxLeftWidth = w }
        }

        cachedMaxLeftTextWidth = maxLeftWidth
    }

    private func stableRowNumberDigits() -> Int {
        if cachedRowNumberDigits > 0 { return cachedRowNumberDigits }
        return max(1, String(max(1, allItems.count)).count)
    }

    private func leftWrapWidth() -> CGFloat {
        let colW = max(220, (tableView.tableColumns.first?.width ?? tableView.bounds.width))
        return max(120, colW - (2 * leftRowTextInset) - 2)
    }

    private func recomputeKeywordTabX() {
        let colW = max(220, (tableView.tableColumns.first?.width ?? tableView.bounds.width))
        let available = max(160, colW - (2 * leftRowTextInset))

        if cachedMaxLeftTextWidth <= 0 {
            rebuildLeftColumnMetrics()
        }

        let gutter: CGFloat = 10
        var tabX = cachedMaxLeftTextWidth + gutter

        // Keep some room for the keyword column, but don't reserve so much that
        // author/year wraps unnecessarily (keywords can wrap too).
        let keywordHeaderMin = ("Keyword(s)" as NSString).size(withAttributes: [.font: leftRowSecondaryFont]).width
        let minRight: CGFloat = max(70, keywordHeaderMin + 10)
        let maxTab = max(120, available - minRight)
        tabX = min(tabX, maxTab)
        tabX = max(tabX, 180)

        keywordColumnTabX = tabX
    }

    private func applyTwoColumnTabStops(to pstyle: NSMutableParagraphStyle) {
        let tabX = keywordColumnTabX
        let t1 = NSTextTab(textAlignment: .left, location: tabX, options: [:])
        let t2 = NSTextTab(textAlignment: .left, location: tabX + keywordSeparatorGap, options: [:])
        pstyle.tabStops = [t1, t2]
        pstyle.defaultTabInterval = tabX + keywordSeparatorGap
    }

    private func updateLeftHeaderText() {
        let pstyle = NSMutableParagraphStyle()
        pstyle.lineBreakMode = .byClipping
        applyTwoColumnTabStops(to: pstyle)

        // Use two tab characters so the keyword column always lands on the
        // second tab stop (tabX + gap) for consistent spacing/alignment.
        let headerString = "Author & Year\t\tKeyword(s)"
        let attr = NSAttributedString(
            string: headerString,
            attributes: [
                .font: NSFont.systemFont(ofSize: 12, weight: .semibold),
                .foregroundColor: leftHeaderTextColor(),
                .paragraphStyle: pstyle
            ]
        )
        leftHeaderLabel.attributedStringValue = attr
    }

    private final class LeftTwoColumnCellView: NSTableCellView {
        let leftField = NSTextField(labelWithString: "")
        let rightField = NSTextField(labelWithString: "")

        private var leftLeading: NSLayoutConstraint!
        private var leftTop: NSLayoutConstraint!
        private var leftBottomMax: NSLayoutConstraint!
        private var leftWidth: NSLayoutConstraint!

        private var rightLeading: NSLayoutConstraint!
        private var rightTop: NSLayoutConstraint!
        private var rightBottomMax: NSLayoutConstraint!
        private var rightTrailing: NSLayoutConstraint!

        override init(frame frameRect: NSRect) {
            super.init(frame: frameRect)

            leftField.translatesAutoresizingMaskIntoConstraints = false
            leftField.backgroundColor = .clear
            leftField.maximumNumberOfLines = 1
            leftField.usesSingleLineMode = true
            leftField.cell?.wraps = false
            leftField.cell?.isScrollable = false
            leftField.lineBreakMode = .byTruncatingTail
            leftField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

            rightField.translatesAutoresizingMaskIntoConstraints = false
            rightField.backgroundColor = .clear
            rightField.maximumNumberOfLines = 1
            rightField.usesSingleLineMode = true
            rightField.cell?.wraps = false
            rightField.cell?.isScrollable = false
            rightField.lineBreakMode = .byTruncatingTail
            rightField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

            addSubview(leftField)
            addSubview(rightField)

            leftLeading = leftField.leadingAnchor.constraint(equalTo: leadingAnchor)
            leftTop = leftField.topAnchor.constraint(equalTo: topAnchor)
            leftBottomMax = leftField.bottomAnchor.constraint(lessThanOrEqualTo: bottomAnchor)
            leftWidth = leftField.widthAnchor.constraint(equalToConstant: 200)

            rightLeading = rightField.leadingAnchor.constraint(equalTo: leadingAnchor)
            rightTop = rightField.topAnchor.constraint(equalTo: topAnchor)
            rightBottomMax = rightField.bottomAnchor.constraint(lessThanOrEqualTo: bottomAnchor)
            rightTrailing = rightField.trailingAnchor.constraint(equalTo: trailingAnchor)

            NSLayoutConstraint.activate([
                leftLeading,
                leftTop,
                leftBottomMax,
                leftWidth,
                rightLeading,
                rightTop,
                rightBottomMax,
                rightTrailing
            ])

            textField = leftField
            rightField.tag = 2
        }

        required init?(coder: NSCoder) {
            fatalError("init(coder:) has not been implemented")
        }

        func updateLayout(leadingInset: CGFloat,
                          trailingInset: CGFloat,
                          topInset: CGFloat,
                          bottomInset: CGFloat,
                          leftColumnWidth: CGFloat,
                          gap: CGFloat) {
            leftLeading.constant = leadingInset
            leftTop.constant = topInset
            leftBottomMax.constant = -bottomInset
            leftWidth.constant = max(1, leftColumnWidth)

            rightLeading.constant = leadingInset + max(1, leftColumnWidth) + gap
            rightTop.constant = topInset
            rightBottomMax.constant = -bottomInset
            rightTrailing.constant = -trailingInset

            leftField.preferredMaxLayoutWidth = max(1, leftColumnWidth)
            let rightW = max(1, bounds.width - (leadingInset + max(1, leftColumnWidth) + gap) - trailingInset)
            rightField.preferredMaxLayoutWidth = rightW
        }
    }

    // MARK: Table
    func numberOfRows(in tableView: NSTableView) -> Int {
        if tableView === suggestionsTable {
            return suggestions.count
        }
        if tableView === menuTable {
            return menuItems.count
        }
        return paginator.range(forPage: currentPageIndex).count + 1 // +1 for header row
    }

    func tableView(_ tableView: NSTableView, shouldSelectRow row: Int) -> Bool {
        if tableView === suggestionsTable {
            return row >= 0
        }
        if tableView === menuTable {
            guard row >= 0, row < menuItems.count else { return false }
            return menuItems[row].isSelectable
        }
        return row > 0 // prevent selecting header row
    }

    func tableView(_ tableView: NSTableView, rowViewForRow row: Int) -> NSTableRowView? {
        if tableView === suggestionsTable {
            let view = GlassMenuRowView()
            view.rowInsets = NSEdgeInsets(top: 6, left: 10, bottom: 6, right: 10)
            view.isActiveWindowProvider = { [weak self] in self?.isWindowActiveForAppearance() ?? true }
            return view
        }
        if tableView === menuTable {
            guard row >= 0, row < menuItems.count else { return nil }
            let item = menuItems[row]
            if item.kind == .separator {
                return NSTableRowView()
            }
            let view = GlassMenuRowView()
            view.rowInsets = menuRowInsets
            view.isActiveWindowProvider = { [weak self] in self?.isWindowActiveForAppearance() ?? true }
            view.outlineOnly = true
            view.isInteractive = item.isSelectable
            return view
        }
        let view = ElasticRowView()
        view.isHeaderRow = (row == 0)
        view.rowIndex = row
        view.reduceMotionProvider = { [weak self] in self?.shouldReduceMotion ?? false }
        view.isActiveWindowProvider = { [weak self] in self?.isWindowActiveForAppearance() ?? true }
        view.animationEnabledProvider = { [weak self] in !(self?.suppressRowAnimations ?? false) }
        view.horizontalAlignmentReferenceView = searchBackground
        view.hoverChanged = { [weak self] rowIndex, isHovered in
            self?.handleRowHover(rowIndex, isHovered: isHovered)
        }
        return view
    }

    func tableView(_ tableView: NSTableView, heightOfRow row: Int) -> CGFloat {
        if tableView === suggestionsTable {
            return suggestionRowHeight
        }
        if tableView === menuTable {
            guard row >= 0, row < menuItems.count else { return menuRowHeight }
            switch menuItems[row].kind {
            case .summary:
                return menuSummaryRowHeight
            case .separator:
                return menuSeparatorHeight
            case .page, .action:
                return menuRowHeight
            }
        }
        if row == 0 { return headerRowHeight }
        // Publication rows are single-line (truncated), so row heights are fixed.
        return minRowHeight
    }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        if tableView === suggestionsTable {
            guard row >= 0, row < suggestions.count else { return nil }
            let cellId = NSUserInterfaceItemIdentifier("suggestionCell")
            if let existing = tableView.makeView(withIdentifier: cellId, owner: self) as? NSTableCellView {
                configureSuggestionCell(existing, row: row)
                return existing
            }
            let cellView = NSTableCellView(frame: .zero)
            cellView.identifier = cellId

            let titleField = NSTextField(labelWithString: "")
            titleField.translatesAutoresizingMaskIntoConstraints = false
            titleField.font = suggestionTitleFont
            titleField.lineBreakMode = .byTruncatingTail
            titleField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

            let subtitleField = NSTextField(labelWithString: "")
            subtitleField.translatesAutoresizingMaskIntoConstraints = false
            subtitleField.font = suggestionSubtitleFont
            subtitleField.lineBreakMode = .byTruncatingTail
            subtitleField.textColor = resolvedSystemColor(.secondaryLabelColor)
            subtitleField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

            cellView.addSubview(titleField)
            cellView.addSubview(subtitleField)
            cellView.textField = titleField
            subtitleField.tag = 2

            NSLayoutConstraint.activate([
                titleField.leadingAnchor.constraint(equalTo: cellView.leadingAnchor, constant: suggestionTextInsetX),
                titleField.trailingAnchor.constraint(equalTo: cellView.trailingAnchor, constant: -suggestionTextInsetX),
                titleField.topAnchor.constraint(equalTo: cellView.topAnchor, constant: 6),
                subtitleField.leadingAnchor.constraint(equalTo: cellView.leadingAnchor, constant: suggestionTextInsetX),
                subtitleField.trailingAnchor.constraint(equalTo: cellView.trailingAnchor, constant: -suggestionTextInsetX),
                subtitleField.topAnchor.constraint(equalTo: titleField.bottomAnchor, constant: 2),
                subtitleField.bottomAnchor.constraint(equalTo: cellView.bottomAnchor, constant: -6)
            ])
            configureSuggestionCell(cellView, row: row)
            return cellView
        }

        if tableView === menuTable {
            guard row >= 0, row < menuItems.count else { return nil }
            let item = menuItems[row]
            if item.kind == .separator {
                let sepId = NSUserInterfaceItemIdentifier("menuSeparator")
                if let existing = tableView.makeView(withIdentifier: sepId, owner: self) as? MenuSeparatorView {
                    configureMenuSeparator(existing)
                    return existing
                }
                let view = MenuSeparatorView(frame: .zero)
                view.identifier = sepId
                configureMenuSeparator(view)
                return view
            }

            let cellId = NSUserInterfaceItemIdentifier("menuCell")
            if let existing = tableView.makeView(withIdentifier: cellId, owner: self) as? NSTableCellView {
                configureMenuCell(existing, row: row)
                return existing
            }
            let cellView = NSTableCellView(frame: .zero)
            cellView.identifier = cellId

            let check = NSImageView(frame: .zero)
            check.translatesAutoresizingMaskIntoConstraints = false
            check.imageScaling = .scaleProportionallyDown
            check.setContentCompressionResistancePriority(.required, for: .horizontal)
            cellView.addSubview(check)
            cellView.imageView = check

            let tf = NSTextField(labelWithString: "")
            tf.translatesAutoresizingMaskIntoConstraints = false
            tf.lineBreakMode = .byTruncatingTail
            tf.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
            cellView.addSubview(tf)
            cellView.textField = tf

            NSLayoutConstraint.activate([
                check.leadingAnchor.constraint(equalTo: cellView.leadingAnchor, constant: menuCheckmarkLeading),
                check.centerYAnchor.constraint(equalTo: cellView.centerYAnchor),
                check.widthAnchor.constraint(equalToConstant: menuCheckmarkSize),
                check.heightAnchor.constraint(equalToConstant: menuCheckmarkSize),

                tf.leadingAnchor.constraint(equalTo: cellView.leadingAnchor, constant: menuTextLeading),
                tf.trailingAnchor.constraint(equalTo: cellView.trailingAnchor, constant: -menuTextTrailing),
                tf.centerYAnchor.constraint(equalTo: cellView.centerYAnchor)
            ])
            configureMenuCell(cellView, row: row)
            return cellView
        }

        guard row >= 0, row <= paginator.range(forPage: currentPageIndex).count else { return nil }

        let cellId = NSUserInterfaceItemIdentifier("leftCell")

        if let existing = tableView.makeView(withIdentifier: cellId, owner: self) as? LeftTwoColumnCellView {
            let selected = tableView.selectedRowIndexes.contains(row)
            let active = isWindowActiveForAppearance()
            existing.updateLayout(
                leadingInset: leftRowTextInset,
                trailingInset: leftRowTextInset,
                topInset: leftCellInsetY,
                bottomInset: leftCellBottomInsetY,
                leftColumnWidth: keywordColumnTabX,
                gap: keywordSeparatorGap
            )
            configureLeftCell(existing, row: row, isSelected: selected, isActive: active)
            return existing
        }

        let cellView = LeftTwoColumnCellView(frame: .zero)
        cellView.identifier = cellId
        let selected = tableView.selectedRowIndexes.contains(row)
        let active = isWindowActiveForAppearance()
        cellView.updateLayout(
            leadingInset: leftRowTextInset,
            trailingInset: leftRowTextInset,
            topInset: leftCellInsetY,
            bottomInset: leftCellBottomInsetY,
            leftColumnWidth: keywordColumnTabX,
            gap: keywordSeparatorGap
        )
        configureLeftCell(cellView, row: row, isSelected: selected, isActive: active)
        return cellView
    }

    func tableView(_ tableView: NSTableView, didAdd rowView: NSTableRowView, forRow row: Int) {
        if tableView === suggestionsTable {
            configureSuggestionRowView(rowView, row: row)
            return
        }
        if tableView === menuTable {
            configureMenuRowView(rowView, row: row)
            return
        }
        guard row >= 0, row <= paginator.range(forPage: currentPageIndex).count else { return }
        if row == 1 { logListRenderIfNeeded() }
        if let elastic = rowView as? ElasticRowView {
            elastic.isHeaderRow = (row == 0)
            elastic.rowIndex = row
            elastic.reduceMotionProvider = { [weak self] in self?.shouldReduceMotion ?? false }
            elastic.isActiveWindowProvider = { [weak self] in self?.isWindowActiveForAppearance() ?? true }
            elastic.refreshDepth(animated: false, preset: .crisp)
        }
        guard let cell = rowView.view(atColumn: 0) as? LeftTwoColumnCellView else { return }
        cell.updateLayout(
            leadingInset: leftRowTextInset,
            trailingInset: leftRowTextInset,
            topInset: leftCellInsetY,
            bottomInset: leftCellBottomInsetY,
            leftColumnWidth: keywordColumnTabX,
            gap: keywordSeparatorGap
        )
        cell.layoutSubtreeIfNeeded()
        let selected = rowView.isSelected
        let active = isWindowActiveForAppearance()
        configureLeftCell(cell, row: row, isSelected: selected, isActive: active)
    }

    func tableViewSelectionDidChange(_ notification: Notification) {
        if let table = notification.object as? NSTableView, table === suggestionsTable {
            suggestionSelectionIndex = table.selectedRow
            refreshSuggestionTextColors()
            return
        }
        if let table = notification.object as? NSTableView, table === menuTable {
            refreshMenuTextBounce(animated: true)
            return
        }
        updateVisibleRowSelectionStyling()
        var fellBackToDetails = false
        if let idx = selectedFilteredIndex(), idx >= 0, idx < filtered.count {
            let key = filtered[idx].key
            uiLog("row_selection_change row=\(tableView.selectedRow) dataRow=\(idx)")
            recordSelectionHistory(for: key, viewMode: isShowingPDF, reason: "table-selection")
            if isShowingPDF && !selectionChangeFromCode {
                if let url = pdfURL(for: filtered[idx]) {
                    presentPDF(remoteURL: url, trigger: "table-selection")
                    prefetchNeighborPDFs(around: idx, reason: "table-selection")
                } else {
                    // Items without PDFs should still react to selection while the PDF view is showing.
                    showDetailsPanel(animated: true, updateContent: true)
                    fellBackToDetails = true
                }
            }
        } else {
            uiLog("row_selection_change row=\(tableView.selectedRow) dataRow=nil")
        }
        if !isShowingPDF && !selectionChangeFromCode && !fellBackToDetails { updateDetails() }
        updateNavigationButtons()
    }

    private func updateVisibleRowSelectionStyling() {
        let visible = tableView.rows(in: tableView.visibleRect)
        guard visible.length > 0 else { return }
        let active = isWindowActiveForAppearance()

        for row in visible.location..<(visible.location + visible.length) {
            guard let rowView = tableView.rowView(atRow: row, makeIfNecessary: false),
                let cell = rowView.view(atColumn: 0) as? LeftTwoColumnCellView else { continue }
            let selected = rowView.isSelected
            configureLeftCell(cell, row: row, isSelected: selected, isActive: active)
        }
    }

    private func applySuggestionTextBounce(row: Int, hovered: Bool, animated: Bool) {
        guard row >= 0, row < suggestions.count else { return }
        guard let cell = suggestionsTable.view(atColumn: 0, row: row, makeIfNecessary: false) as? NSTableCellView else { return }
        let reduce = shouldReduceMotion
        applyHoverBounce(to: cell.textField, hovered: hovered, animated: animated, reduceMotion: reduce)
        if let subtitle = cell.viewWithTag(2) as? NSTextField {
            applyHoverBounce(to: subtitle, hovered: hovered, animated: animated, reduceMotion: reduce)
        }
    }

    private func handleSuggestionHover(_ row: Int, isHovered: Bool) {
        guard row >= 0, row < suggestions.count else { return }
        if isHovered {
            hoveredSuggestionRow = row
        } else if hoveredSuggestionRow == row {
            hoveredSuggestionRow = nil
        }
        applySuggestionTextBounce(row: row, hovered: isHovered, animated: true)
    }

    private func handleRowHover(_ row: Int, isHovered: Bool) {
        if let cell = tableView.view(atColumn: 0, row: row, makeIfNecessary: false) as? LeftTwoColumnCellView {
            applyHoverBounce(to: cell.leftField,
                             hovered: isHovered,
                             animated: true,
                             reduceMotion: shouldReduceMotion)
            applyHoverBounce(to: cell.rightField,
                             hovered: isHovered,
                             animated: true,
                             reduceMotion: shouldReduceMotion)
        }
        guard let dataRow = globalIndex(forTableRow: row) else { return }
        guard dataRow >= 0, dataRow < filtered.count else { return }
        uiLog("row_hover tableRow=\(row) dataRow=\(dataRow) hover=\(isHovered)")
        if isHovered {
            hoveredDataRow = dataRow
        } else if hoveredDataRow == dataRow {
            hoveredDataRow = nil
        }
    }

    private func leftAttributedAuthorText(for paper: Paper,
                                         rowNumber: Int,
                                         paragraphStyle: NSParagraphStyle,
                                         titleFont: NSFont,
                                         secondaryFont: NSFont,
                                         titleColor: NSColor,
                                         secondaryColor: NSColor) -> NSAttributedString {
        let base = decodeTeXAccents(leftAuthorYearText(paper: paper))

        // Left-align row text: no digit-padding for the row-number prefix.
        let prefix = "\(rowNumber). "

        let result = NSMutableAttributedString(
            string: prefix,
            attributes: [
                .font: secondaryFont,
                .paragraphStyle: paragraphStyle,
                .foregroundColor: secondaryColor
            ]
        )

        result.append(NSAttributedString(
            string: base,
            attributes: [
                .font: titleFont,
                .paragraphStyle: paragraphStyle,
                .foregroundColor: titleColor
            ]
        ))
        return result
    }

    private func leftAttributedKeywordsText(for paper: Paper,
                                           paragraphStyle: NSParagraphStyle,
                                           secondaryFont: NSFont,
                                           secondaryEmphasisFont: NSFont,
                                           secondaryColor: NSColor) -> NSAttributedString? {
        let present = dedupePluralKeywordsForDisplay(
            keywordsPresent(in: paper, keywords: keywordsFromAppleScript)
        )
        guard !present.isEmpty else { return nil }

        let result = NSMutableAttributedString(
            string: "",
            attributes: [
                .font: secondaryFont,
                .paragraphStyle: paragraphStyle,
                .foregroundColor: secondaryColor
            ]
        )

        for (i, kw) in present.enumerated() {
            if i > 0 {
                result.append(NSAttributedString(
                    string: ", ",
                    attributes: [
                        .font: secondaryFont,
                        .paragraphStyle: paragraphStyle,
                        .foregroundColor: secondaryColor
                    ]
                ))
            }
            result.append(NSAttributedString(
                string: kw,
                attributes: [
                    .font: secondaryEmphasisFont,
                    .paragraphStyle: paragraphStyle,
                    .foregroundColor: secondaryColor
                ]
            ))
        }
        return result
    }

    private func leftHeaderTextColor() -> NSColor {
        let base = resolvedSystemColor(.secondaryLabelColor)
        guard let tint = colorFromHex(LIQUID_GLASS_TINT_HEX) else { return base }
        let dark = window?.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let blendAmount: CGFloat = dark ? 0.12 : 0.2
        return blend(base, tint, t: blendAmount)
    }

    private func leftRowTextColors(isSelected: Bool, isActive: Bool) -> (title: NSColor, secondary: NSColor) {
        let dark = window?.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua

        if dark {
            // Safari-like menu typography: softened near-white on glass.
            if isSelected {
                let title = NSColor.white.withAlphaComponent(isActive ? 0.96 : 0.88)
                let secondary = NSColor.white.withAlphaComponent(isActive ? 0.78 : 0.70)
                return (title, secondary)
            }
            let title = NSColor.white.withAlphaComponent(isActive ? 0.90 : 0.82)
            let secondary = NSColor.white.withAlphaComponent(isActive ? 0.64 : 0.58)
            return (title, secondary)
        } else {
            // Light contexts: keep crisp, menu-like dark text with slight softness.
            if isSelected {
                let title = resolvedSystemColor(.labelColor).withAlphaComponent(isActive ? 0.94 : 0.86)
                let secondary = resolvedSystemColor(.labelColor).withAlphaComponent(isActive ? 0.72 : 0.64)
                return (title, secondary)
            }
            let title = resolvedSystemColor(.labelColor).withAlphaComponent(isActive ? 0.90 : 0.82)
            let secondary = resolvedSystemColor(.secondaryLabelColor).withAlphaComponent(isActive ? 0.84 : 0.76)
            return (title, secondary)
        }
    }

	    private func configureLeftCell(_ cell: LeftTwoColumnCellView, row: Int, isSelected: Bool, isActive: Bool) {
	        let pstyle = NSMutableParagraphStyle()
            pstyle.lineBreakMode = (row == 0) ? .byClipping : .byTruncatingTail

	        if row == 0 {
	            let headerAttrs: [NSAttributedString.Key: Any] = [
	                .font: NSFont.systemFont(ofSize: 12.5, weight: .medium),
	                .foregroundColor: leftHeaderTextColor(),
	                .kern: -0.15,
	                .paragraphStyle: pstyle
	            ]
	            cell.leftField.attributedStringValue = NSAttributedString(string: "Author & Year", attributes: headerAttrs)
	            cell.rightField.attributedStringValue = NSAttributedString(string: "Keyword(s)", attributes: headerAttrs)
	            applyHoverBounce(to: cell.leftField, hovered: false, animated: false, reduceMotion: shouldReduceMotion)
	            applyHoverBounce(to: cell.rightField, hovered: false, animated: false, reduceMotion: shouldReduceMotion)
	            return
	        }

        guard let dataRow = globalIndex(forTableRow: row) else { return }
        let colors = leftRowTextColors(isSelected: isSelected, isActive: isActive)
        let paper = filtered[dataRow]

        cell.leftField.attributedStringValue = leftAttributedAuthorText(
            for: paper,
            rowNumber: dataRow + 1,
            paragraphStyle: pstyle,
            titleFont: leftRowTitleFont,
            secondaryFont: leftRowSecondaryFont,
            titleColor: colors.title,
            secondaryColor: colors.secondary
        )

        if let kwAttr = leftAttributedKeywordsText(
            for: paper,
            paragraphStyle: pstyle,
            secondaryFont: leftRowSecondaryFont,
            secondaryEmphasisFont: leftRowSecondaryEmphasisFont,
            secondaryColor: colors.secondary
        ) {
            cell.rightField.attributedStringValue = kwAttr
        } else {
            cell.rightField.stringValue = ""
        }

        let hovered = (dataRow == hoveredDataRow)
        applyHoverBounce(to: cell.leftField, hovered: hovered, animated: false, reduceMotion: shouldReduceMotion)
        applyHoverBounce(to: cell.rightField, hovered: hovered, animated: false, reduceMotion: shouldReduceMotion)
    }

    private func configureSuggestionCell(_ cell: NSTableCellView, row: Int) {
        guard row >= 0, row < suggestions.count else { return }
        let suggestion = suggestions[row]
        let selected = suggestionsTable.selectedRow == row
        let active = isWindowActiveForAppearance()
        let titleColor = selected ? NSColor.white.withAlphaComponent(active ? 0.96 : 0.86) : resolvedSystemColor(.labelColor)
        let subtitleColor = selected ? NSColor.white.withAlphaComponent(active ? 0.72 : 0.62) : resolvedSystemColor(.secondaryLabelColor)

        cell.textField?.stringValue = suggestion.title
        cell.textField?.textColor = titleColor
        let hovered = hoveredSuggestionRow == row
        let reduce = shouldReduceMotion
        applyHoverBounce(to: cell.textField, hovered: hovered, animated: false, reduceMotion: reduce)
        if let subtitle = cell.viewWithTag(2) as? NSTextField {
            subtitle.stringValue = suggestion.subtitle
            subtitle.textColor = subtitleColor
            applyHoverBounce(to: subtitle, hovered: hovered, animated: false, reduceMotion: reduce)
        }
    }

    private func menuTextColor(for item: MenuItem, isActive: Bool) -> NSColor {
        let dark = window?.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        if item.kind == .summary {
            if dark {
                return NSColor.white.withAlphaComponent(isActive ? 0.72 : 0.62)
            }
            return resolvedSystemColor(.secondaryLabelColor).withAlphaComponent(isActive ? 0.90 : 0.80)
        }
        if !item.isEnabled {
            return resolvedSystemColor(.tertiaryLabelColor)
        }
        if dark {
            return NSColor.white.withAlphaComponent(isActive ? 0.90 : 0.78)
        }
        return resolvedSystemColor(.labelColor).withAlphaComponent(isActive ? 0.92 : 0.82)
    }

    private func configureMenuCell(_ cell: NSTableCellView, row: Int) {
        guard row >= 0, row < menuItems.count else { return }
        let item = menuItems[row]
        let active = isWindowActiveForAppearance()
        let textColor = menuTextColor(for: item, isActive: active)

        cell.textField?.stringValue = item.title
        cell.textField?.font = (item.kind == .summary) ? menuSummaryFont : menuFont
        cell.textField?.textColor = textColor

        if let check = cell.imageView {
            check.image = menuCheckmarkImage
            check.contentTintColor = textColor
            check.isHidden = !item.isChecked
            check.alphaValue = item.isChecked ? (item.kind == .summary ? 0.72 : 0.90) : 0.0
        }

        let selected = menuTable.selectedRowIndexes.contains(row)
        applyHoverBounce(to: cell.textField,
                         hovered: selected,
                         animated: false,
                         reduceMotion: shouldReduceMotion)
    }

    private func menuSeparatorColor() -> NSColor {
        let dark = window?.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let alpha: CGFloat = dark ? 0.28 : 0.20
        return resolvedSystemColor(.separatorColor).withAlphaComponent(alpha)
    }

    private func configureMenuSeparator(_ view: MenuSeparatorView) {
        view.lineInsets = NSEdgeInsets(top: 0, left: menuTextLeading, bottom: 0, right: menuTextTrailing)
        view.colorProvider = { [weak self] in
            self?.menuSeparatorColor() ?? resolvedSystemColor(.separatorColor).withAlphaComponent(0.2)
        }
    }

    private func menuPreferredWidth(for items: [MenuItem], anchorWidth: CGFloat) -> CGFloat {
        var maxTextWidth: CGFloat = 0
        for item in items where item.kind != .separator {
            let font = (item.kind == .summary) ? menuSummaryFont : menuFont
            let w = (item.title as NSString).size(withAttributes: [.font: font]).width
            if w > maxTextWidth { maxTextWidth = w }
        }
        let horizontalInset = dropdownContentInsets.left + dropdownContentInsets.right
        let contentWidth = menuTextLeading + maxTextWidth + menuTextTrailing + horizontalInset
        let base = max(menuMinWidth, anchorWidth + 40 + horizontalInset)
        return max(base, ceil(contentWidth))
    }

    private func configureSuggestionRowView(_ rowView: NSTableRowView, row: Int) {
        if let glass = rowView as? GlassMenuRowView {
            glass.isActiveWindowProvider = { [weak self] in self?.isWindowActiveForAppearance() ?? true }
            glass.rowIndex = row
            glass.hoverChanged = { [weak self] rowIndex, isHovered in
                self?.handleSuggestionHover(rowIndex, isHovered: isHovered)
            }
            let shouldHover = (hoveredSuggestionRow == row)
            glass.setHoverState(shouldHover, animated: false, notify: false)
        }
        if let cell = rowView.view(atColumn: 0) as? NSTableCellView {
            configureSuggestionCell(cell, row: row)
        }
    }

    private func configureMenuRowView(_ rowView: NSTableRowView, row: Int) {
        if let glass = rowView as? GlassMenuRowView {
            glass.isActiveWindowProvider = { [weak self] in self?.isWindowActiveForAppearance() ?? true }
            glass.outlineOnly = true
            if row >= 0, row < menuItems.count {
                glass.isInteractive = menuItems[row].isSelectable
            }
        }
        if let cell = rowView.view(atColumn: 0) as? NSTableCellView,
           cell.textField != nil {
            configureMenuCell(cell, row: row)
        }
    }

    private func clearSuggestionHover(animated: Bool) {
        hoveredSuggestionRow = nil
        let visible = suggestionsTable.rows(in: suggestionsTable.visibleRect)
        guard visible.length > 0 else { return }
        for row in visible.location..<(visible.location + visible.length) {
            guard let rowView = suggestionsTable.rowView(atRow: row, makeIfNecessary: false) as? GlassMenuRowView else { continue }
            rowView.setHoverState(false, animated: animated, notify: false)
        }
    }

    private func refreshSuggestionTextColors() {
        let visible = suggestionsTable.rows(in: suggestionsTable.visibleRect)
        guard visible.length > 0 else { return }
        for row in visible.location..<(visible.location + visible.length) {
            if let cell = suggestionsTable.view(atColumn: 0, row: row, makeIfNecessary: false) as? NSTableCellView {
                configureSuggestionCell(cell, row: row)
            }
        }
    }

    private func syncSuggestionHoverFromMouse(animated: Bool) {
        guard suggestionsVisible, let window = suggestionsTable.window else {
            hoveredSuggestionRow = nil
            return
        }
        let mouseInWindow = window.mouseLocationOutsideOfEventStream
        let mouseInTable = suggestionsTable.convert(mouseInWindow, from: nil)
        let row = suggestionsTable.row(at: mouseInTable)
        let hoverRow = (row >= 0 && row < suggestions.count) ? row : nil
        hoveredSuggestionRow = hoverRow

        let visible = suggestionsTable.rows(in: suggestionsTable.visibleRect)
        guard visible.length > 0 else { return }
        for r in visible.location..<(visible.location + visible.length) {
            guard let rowView = suggestionsTable.rowView(atRow: r, makeIfNecessary: true) as? GlassMenuRowView else { continue }
            rowView.setHoverState(r == row, animated: animated, notify: false)
        }
    }

    private func refreshMenuTextColors() {
        guard !menuContainer.isHidden else { return }
        let visible = menuTable.rows(in: menuTable.visibleRect)
        guard visible.length > 0 else { return }
        for row in visible.location..<(visible.location + visible.length) {
            guard row >= 0, row < menuItems.count else { continue }
            if menuItems[row].kind == .separator { continue }
            if let cell = menuTable.view(atColumn: 0, row: row, makeIfNecessary: false) as? NSTableCellView {
                configureMenuCell(cell, row: row)
            }
        }
    }

    private func refreshMenuTextBounce(animated: Bool) {
        let visible = menuTable.rows(in: menuTable.visibleRect)
        guard visible.length > 0 else { return }
        for row in visible.location..<(visible.location + visible.length) {
            guard row >= 0, row < menuItems.count else { continue }
            if menuItems[row].kind == .separator { continue }
            if let cell = menuTable.view(atColumn: 0, row: row, makeIfNecessary: false) as? NSTableCellView {
                let selected = menuTable.selectedRowIndexes.contains(row)
                applyHoverBounce(to: cell.textField,
                                 hovered: selected,
                                 animated: animated,
                                 reduceMotion: shouldReduceMotion)
            }
        }
    }

    // MARK: Payload wait-mode

    private func beginWaitingIfNeeded() {
        guard let path = payloadPathToWatch, !path.isEmpty else { return }

        showLoading("Scanning Mail…")

        pollTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
            guard let self else { return }
            if FileManager.default.fileExists(atPath: path) {
                do {
                    let data = try Data(contentsOf: URL(fileURLWithPath: path))
                    guard let text = String(data: data, encoding: .utf8) else { return }
                    if let payload = decodePayload(text), !payload.papers.isEmpty {
                        try? FileManager.default.removeItem(atPath: path)
                        self.applyPayload(payload)
                    }
                } catch {
                    // keep polling
                }
            }
        }
    }

    private func applyPayload(_ payload: Payload) {
        listRenderStartTime = monotonicNow()
        listRenderLogged = false
        currentPageIndex = 0
        publicationStore.setAll(payload.papers)
        publicationStore.setFiltered(payload.papers)
        self.keywordsFromAppleScript = payload.keywords
        self.recipientNameFromAppleScript = payload.recipientName
        self.recipientEmailFromAppleScript = payload.recipientEmail
        searchIndex.rebuild(from: payload.papers)
        selectionHistory.removeAll()
        selectionHistoryIndex = -1
        updateNavigationButtons()

        let earlyHotCount = min(12, filtered.count)
        if earlyHotCount > 0 {
            let earlyRequests = filtered.prefix(earlyHotCount).compactMap { prefetchRequest(for: $0) }
            pdfCache.prefetch(earlyRequests, priority: 2, reason: "payload-load/early-top")
        }
        prefetchAllPapers(reason: "payload-load/all")

        rebuildLeftColumnMetrics()

        hideLoading()

        layoutLeftContainerSubviews()
        layoutRightPanelSubviews()
        reflowLeft()

        if !filtered.isEmpty {
            selectFilteredIndex(0, scroll: true, reason: "payload-first")
            updateDetails()
        }
    }
}


// MARK: - Input decoding

func readAllStdin() -> String {
    // Check if stdin is a TTY (terminal) - if so, there's no piped data
    if isatty(FileHandle.standardInput.fileDescriptor) != 0 {
        return ""
    }
    
    // Check if there's data available without blocking
    var pollfd = Darwin.pollfd(fd: FileHandle.standardInput.fileDescriptor, events: Int16(POLLIN), revents: 0)
    let pollResult = poll(&pollfd, 1, 0) // 0 timeout = non-blocking
    
    if pollResult <= 0 {
        return ""
    }
    
    // Data is available, read it
    if let data = try? FileHandle.standardInput.readToEnd(),
       let text = String(data: data, encoding: .utf8) {
        return text
    }
    
    return ""
}

func decodePayload(_ s: String) -> Payload? {
    let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !t.isEmpty, let data = t.data(using: .utf8) else { return nil }

    if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
       let papersArr = obj["papers"] as? [[String: Any]] {

        let keywords = (obj["keywords"] as? [String]) ?? []
        let recipientName = (obj["recipientName"] as? String)
        let recipientEmail = (obj["recipientEmail"] as? String)

        let papers: [Paper] = papersArr.enumerated().compactMap { i, d in
            guard let title = d["title"] as? String else { return nil }
            return Paper(
                index: d["index"] as? Int ?? i,
                title: title,
                authors: d["authors"] as? String ?? "",
                categories: d["categories"] as? String ?? "",
                dateLine: d["dateLine"] as? String ?? "",
                url: d["url"] as? String ?? "",
                comments: d["comments"] as? String ?? "",
                abstractText: d["abstractText"] as? String ?? ""
            )
        }

        return Payload(papers: papers, keywords: keywords, recipientName: recipientName, recipientEmail: recipientEmail)
    }

    return nil
}


// MARK: - Settings (isolated, additive)

private extension Notification.Name {
    static let astroStackSettingsDidChange = Notification.Name("astroStack.settings.didChange")
}

struct AppSettings: Codable, Equatable {
    static let currentSchemaVersion: Int = 1

    struct Appearance: Codable, Equatable {
        enum AppAppearanceOverride: String, Codable {
            case followSystem
            case light
            case dark
        }

        var appearanceOverride: AppAppearanceOverride = .followSystem
    }

    struct LayoutPanels: Codable, Equatable {
        // Intentionally minimal; layout resets are explicit actions (not automatic behavior changes).
        var reserved: Bool = false
    }

    struct DocumentsPDF: Codable, Equatable {
        var reserved: Bool = false
    }

    struct Search: Codable, Equatable {
        var reserved: Bool = false
    }

    struct SharingExport: Codable, Equatable {
        var reserved: Bool = false
    }

    struct AdvancedDeveloper: Codable, Equatable {
        // Defensive: defaults reproduce current behavior exactly.
        // These flags are read once at controller init, so changes require relaunch.
        var enableUIDebug: Bool = false
        var enableToolbarGlassDebug: Bool = false
        var enablePDFZoomDebug: Bool = false
    }

    var schemaVersion: Int = AppSettings.currentSchemaVersion
    var appearance: Appearance = Appearance()
    var layoutPanels: LayoutPanels = LayoutPanels()
    var documentsPDF: DocumentsPDF = DocumentsPDF()
    var search: Search = Search()
    var sharingExport: SharingExport = SharingExport()
    var advancedDeveloper: AdvancedDeveloper = AdvancedDeveloper()
}

final class AppSettingsStore {
    static let shared = AppSettingsStore()

    private struct Persistence {
        static let defaultsKey = "astroStack.settings.v1"
    }

    private let lock = NSLock()
    private var cached: AppSettings = AppSettings()
    private var loaded = false

    private init() {}

    var current: AppSettings {
        lock.lock()
        defer { lock.unlock() }
        ensureLoadedLocked()
        if cached.schemaVersion != AppSettings.currentSchemaVersion {
            // Defensive: if schema drifts, fall back to defaults rather than attempting risky migration.
            cached = AppSettings()
            cached.schemaVersion = AppSettings.currentSchemaVersion
            persistLocked(cached)
        }
        return cached
    }

    func update(_ mutate: (inout AppSettings) -> Void) {
        lock.lock()
        ensureLoadedLocked()
        var next = cached
        mutate(&next)
        if next == cached {
            lock.unlock()
            return
        }
        cached = next
        persistLocked(next)
        lock.unlock()

        NotificationCenter.default.post(name: .astroStackSettingsDidChange, object: nil)
    }

    func resetToDefaults() {
        lock.lock()
        cached = AppSettings()
        UserDefaults.standard.removeObject(forKey: Persistence.defaultsKey)
        loaded = true
        lock.unlock()

        NotificationCenter.default.post(name: .astroStackSettingsDidChange, object: nil)
    }

    private func loadLocked() -> AppSettings? {
        guard let data = UserDefaults.standard.data(forKey: Persistence.defaultsKey) else { return nil }
        do {
            let decoder = JSONDecoder()
            return try decoder.decode(AppSettings.self, from: data)
        } catch {
            return nil
        }
    }

    private func persistLocked(_ settings: AppSettings) {
        do {
            let encoder = JSONEncoder()
            if #available(macOS 10.13, *) {
                encoder.outputFormatting = [.sortedKeys]
            }
            let data = try encoder.encode(settings)
            UserDefaults.standard.set(data, forKey: Persistence.defaultsKey)
        } catch {
            // Persistence failures are non-fatal; keep in-memory copy.
        }
    }

    private func ensureLoadedLocked() {
        guard !loaded else { return }
        cached = loadLocked() ?? AppSettings()
        loaded = true
    }
}

private enum AppSettingsBootstrap {
    static func applyAppAppearanceOverrideIfNeeded(_ app: NSApplication) {
        let settings = AppSettingsStore.shared.current
        switch settings.appearance.appearanceOverride {
        case .followSystem:
            app.appearance = nil
        case .light:
            app.appearance = NSAppearance(named: .aqua)
        case .dark:
            app.appearance = NSAppearance(named: .darkAqua)
        }
    }
}

private enum SettingsMenuIntegrator {
    static func installIfNeeded() {
        let appName = ProcessInfo.processInfo.processName

        if NSApp.mainMenu == nil {
            let main = NSMenu(title: "Main")

            let appItem = NSMenuItem()
            let appMenu = NSMenu(title: appName)
            appItem.submenu = appMenu
            main.addItem(appItem)

            // Basic, standard app menu items. Keep minimal; do not alter other menus.
            appMenu.addItem(withTitle: "About \(appName)", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
            appMenu.addItem(NSMenuItem.separator())

            // Settings item is inserted below.
            let servicesItem = NSMenuItem(title: "Services", action: nil, keyEquivalent: "")
            let services = NSMenu(title: "Services")
            servicesItem.submenu = services
            NSApp.servicesMenu = services
            appMenu.addItem(servicesItem)
            appMenu.addItem(NSMenuItem.separator())
            appMenu.addItem(withTitle: "Hide \(appName)", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
            let hideOthers = NSMenuItem(title: "Hide Others", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
            hideOthers.keyEquivalentModifierMask = [.command, .option]
            appMenu.addItem(hideOthers)
            appMenu.addItem(withTitle: "Show All", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
            appMenu.addItem(NSMenuItem.separator())
            appMenu.addItem(withTitle: "Quit \(appName)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

            NSApp.mainMenu = main
        }

        guard let mainMenu = NSApp.mainMenu else { return }
        let appMenuItem = mainMenu.items.first(where: { $0.submenu != nil }) ?? mainMenu.item(at: 0)
        guard let appMenu = appMenuItem?.submenu else { return }

        let wantsSettingsTitle: String
        if #available(macOS 13.0, *) {
            wantsSettingsTitle = "Settings…"
        } else {
            wantsSettingsTitle = "Preferences…"
        }

        if appMenu.items.contains(where: { $0.title == wantsSettingsTitle }) {
            return
        }

        let settingsItem = NSMenuItem(title: wantsSettingsTitle, action: #selector(SettingsWindowController.openSettings(_:)), keyEquivalent: ",")
        settingsItem.keyEquivalentModifierMask = [.command]
        settingsItem.target = SettingsWindowController.shared

        // Insert after About + separator if present.
        let insertIndex: Int = {
            if let aboutIndex = appMenu.items.firstIndex(where: { $0.action == #selector(NSApplication.orderFrontStandardAboutPanel(_:)) }) {
                return min(appMenu.items.count, aboutIndex + 2)
            }
            return min(appMenu.items.count, 1)
        }()

        appMenu.insertItem(settingsItem, at: insertIndex)

        // Ensure standard separation from Services/Hide/Quit groups.
        let settingsIndex = insertIndex
        if appMenu.items.indices.contains(settingsIndex + 1), !appMenu.items[settingsIndex + 1].isSeparatorItem {
            appMenu.insertItem(.separator(), at: settingsIndex + 1)
        }
    }
}

final class SettingsWindowController: NSWindowController, NSWindowDelegate {
    static let shared = SettingsWindowController()

    private weak var previouslyKeyWindow: NSWindow?

    private init() {
        super.init(window: nil)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    @objc func openSettings(_ sender: Any?) {
        if window == nil {
            let tabVC = SettingsTabViewController()

            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 720, height: 520),
                             styleMask: [.titled, .closable, .miniaturizable],
                             backing: .buffered,
                             defer: false)
            w.title = "Settings"
            w.isReleasedWhenClosed = false
            w.contentViewController = tabVC
            w.delegate = self
            if #available(macOS 11.0, *) {
                w.toolbarStyle = .preference
            }
            self.window = w
        }

        previouslyKeyWindow = NSApp.keyWindow
        window?.center()
        showWindow(sender)
        window?.makeKeyAndOrderFront(sender)
        NSApp.activate(ignoringOtherApps: true)
    }

    func windowWillClose(_ notification: Notification) {
        // Restore focus to the previously key window when possible.
        if let prev = previouslyKeyWindow, prev.isVisible {
            prev.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
        previouslyKeyWindow = nil
    }
}

private final class SettingsTabViewController: NSTabViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        tabStyle = .toolbar

        addTab(.appearance)
        addTab(.layoutPanels)
        addTab(.documentsPDF)
        addTab(.search)
        addTab(.sharingExport)
        addTab(.advancedDeveloper)
    }

    private func addTab(_ kind: SettingsPaneViewController.Kind) {
        let vc = SettingsPaneViewController(kind: kind)
        let item = NSTabViewItem(viewController: vc)
        item.label = kind.title
        item.image = kind.image
        addTabViewItem(item)
    }
}

private final class SettingsPaneViewController: NSViewController {
    enum Kind {
        case appearance
        case layoutPanels
        case documentsPDF
        case search
        case sharingExport
        case advancedDeveloper

        var title: String {
            switch self {
            case .appearance: return "Appearance"
            case .layoutPanels: return "Layout & Panels"
            case .documentsPDF: return "Documents / PDF"
            case .search: return "Search"
            case .sharingExport: return "Sharing & Export"
            case .advancedDeveloper: return "Advanced / Developer"
            }
        }

        var image: NSImage? {
            let name: String
            switch self {
            case .appearance: name = "paintpalette"
            case .layoutPanels: name = "rectangle.split.3x1"
            case .documentsPDF: name = "doc.richtext"
            case .search: name = "magnifyingglass"
            case .sharingExport: name = "square.and.arrow.up"
            case .advancedDeveloper: name = "gearshape"
            }
            return NSImage(systemSymbolName: name, accessibilityDescription: nil)
        }
    }

    private let kind: Kind

    init(kind: Kind) {
        self.kind = kind
        super.init(nibName: nil, bundle: nil)
        self.title = kind.title
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func loadView() {
        view = NSView(frame: .zero)
        view.translatesAutoresizingMaskIntoConstraints = false
    }

    override func viewDidLoad() {
        super.viewDidLoad()

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.distribution = .fill
        stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false

        let intro = NSTextField(wrappingLabelWithString: introText())
        intro.textColor = resolvedSystemColor(.secondaryLabelColor)
        intro.font = NSFont.systemFont(ofSize: 12)
        intro.translatesAutoresizingMaskIntoConstraints = false

        stack.addArrangedSubview(intro)
        stack.setCustomSpacing(18, after: intro)

        buildControls(into: stack)

        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: view.trailingAnchor, constant: -20),
            stack.topAnchor.constraint(equalTo: view.topAnchor, constant: 20)
        ])
    }

    private func introText() -> String {
        switch kind {
        case .appearance:
            return "Defaults reproduce the current look exactly. Appearance changes apply on next launch unless stated otherwise."
        case .layoutPanels:
            return "Defaults preserve current layout behavior. Layout resets are explicit and require confirmation."
        case .documentsPDF:
            return "Defaults preserve current PDF performance and interaction. No performance-sensitive toggles are enabled by default."
        case .search:
            return "Defaults preserve current search dropdown sizing, alignment, and glass appearance."
        case .sharingExport:
            return "Defaults preserve current share behavior and temporary file handling."
        case .advancedDeveloper:
            return "Developer options are opt-in and safe to disable. Changes take effect on next launch."
        }
    }

    private func buildControls(into stack: NSStackView) {
        switch kind {
        case .appearance:
            let label = NSTextField(labelWithString: "App appearance")
            label.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
            stack.addArrangedSubview(label)

            let pop = NSPopUpButton(frame: .zero, pullsDown: false)
            pop.addItems(withTitles: ["Follow System (Default)", "Light", "Dark"])
            pop.target = self
            pop.action = #selector(onAppearancePopup(_:))
            syncAppearancePopup(pop)
            stack.addArrangedSubview(pop)

            let note = NSTextField(wrappingLabelWithString: "This changes only the app-wide appearance override. It does not modify any glass recipes, blur radii, animation curves, or spacing unless you opt in.")
            note.textColor = resolvedSystemColor(.tertiaryLabelColor)
            note.font = NSFont.systemFont(ofSize: 11)
            stack.addArrangedSubview(note)

        case .layoutPanels:
            let label = NSTextField(labelWithString: "Reset")
            label.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
            stack.addArrangedSubview(label)

            let reset = NSButton(title: "Reset Layout & Panels…", target: self, action: #selector(onResetLayout(_:)))
            stack.addArrangedSubview(reset)

            let note = NSTextField(wrappingLabelWithString: "Clears stored panel width/visibility preferences. Applies next launch.")
            note.textColor = resolvedSystemColor(.tertiaryLabelColor)
            note.font = NSFont.systemFont(ofSize: 11)
            stack.addArrangedSubview(note)

        case .documentsPDF:
            let label = NSTextField(labelWithString: "PDF")
            label.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
            stack.addArrangedSubview(label)

            let note = NSTextField(wrappingLabelWithString: "No PDF performance controls are exposed yet because changing them risks scroll stability and rendering latency. Defaults remain unchanged.")
            note.textColor = resolvedSystemColor(.secondaryLabelColor)
            note.font = NSFont.systemFont(ofSize: 12)
            stack.addArrangedSubview(note)

        case .search:
            let label = NSTextField(labelWithString: "Search")
            label.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
            stack.addArrangedSubview(label)

            let note = NSTextField(wrappingLabelWithString: "No search sizing tunables are exposed yet; dropdown symmetry and glass styling remain locked to current behavior.")
            note.textColor = resolvedSystemColor(.secondaryLabelColor)
            note.font = NSFont.systemFont(ofSize: 12)
            stack.addArrangedSubview(note)

        case .sharingExport:
            let label = NSTextField(labelWithString: "Sharing")
            label.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
            stack.addArrangedSubview(label)

            let note = NSTextField(wrappingLabelWithString: "No sharing/export tunables are exposed yet; defaults remain unchanged to avoid altering disk retention behavior.")
            note.textColor = resolvedSystemColor(.secondaryLabelColor)
            note.font = NSFont.systemFont(ofSize: 12)
            stack.addArrangedSubview(note)

        case .advancedDeveloper:
            let label = NSTextField(labelWithString: "Debug")
            label.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
            stack.addArrangedSubview(label)

            let uiDebug = NSButton(checkboxWithTitle: "Enable UI debug overlays (next launch)", target: self, action: #selector(onToggleDeveloperCheckbox(_:)))
            uiDebug.identifier = NSUserInterfaceItemIdentifier("dev.ui")
            stack.addArrangedSubview(uiDebug)

            let glassDebug = NSButton(checkboxWithTitle: "Enable toolbar glass debug logging (next launch)", target: self, action: #selector(onToggleDeveloperCheckbox(_:)))
            glassDebug.identifier = NSUserInterfaceItemIdentifier("dev.glass")
            stack.addArrangedSubview(glassDebug)

            let pdfZoomDebug = NSButton(checkboxWithTitle: "Enable PDF zoom repro hotkey (next launch)", target: self, action: #selector(onToggleDeveloperCheckbox(_:)))
            pdfZoomDebug.identifier = NSUserInterfaceItemIdentifier("dev.pdfzoom")
            stack.addArrangedSubview(pdfZoomDebug)

            syncDeveloperCheckboxes([uiDebug, glassDebug, pdfZoomDebug])

            stack.setCustomSpacing(18, after: pdfZoomDebug)

            let reset = NSButton(title: "Reset All Settings…", target: self, action: #selector(onResetAllSettings(_:)))
            stack.addArrangedSubview(reset)
        }
    }

    private func syncAppearancePopup(_ pop: NSPopUpButton) {
        let settings = AppSettingsStore.shared.current
        switch settings.appearance.appearanceOverride {
        case .followSystem: pop.selectItem(at: 0)
        case .light: pop.selectItem(at: 1)
        case .dark: pop.selectItem(at: 2)
        }
    }

    private func syncDeveloperCheckboxes(_ buttons: [NSButton]) {
        let settings = AppSettingsStore.shared.current
        for b in buttons {
            switch b.identifier?.rawValue {
            case "dev.ui":
                b.state = settings.advancedDeveloper.enableUIDebug ? .on : .off
            case "dev.glass":
                b.state = settings.advancedDeveloper.enableToolbarGlassDebug ? .on : .off
            case "dev.pdfzoom":
                b.state = settings.advancedDeveloper.enablePDFZoomDebug ? .on : .off
            default:
                break
            }
        }
    }

    @objc private func onAppearancePopup(_ sender: NSPopUpButton) {
        let idx = sender.indexOfSelectedItem
        let next: AppSettings.Appearance.AppAppearanceOverride
        switch idx {
        case 1: next = .light
        case 2: next = .dark
        default: next = .followSystem
        }
        AppSettingsStore.shared.update { s in
            s.appearance.appearanceOverride = next
        }
    }

    @objc private func onToggleDeveloperCheckbox(_ sender: NSButton) {
        let isOn = (sender.state == .on)
        AppSettingsStore.shared.update { s in
            switch sender.identifier?.rawValue {
            case "dev.ui":
                s.advancedDeveloper.enableUIDebug = isOn
            case "dev.glass":
                s.advancedDeveloper.enableToolbarGlassDebug = isOn
            case "dev.pdfzoom":
                s.advancedDeveloper.enablePDFZoomDebug = isOn
            default:
                break
            }
        }
    }

    @objc private func onResetAllSettings(_ sender: Any?) {
        let alert = NSAlert()
        alert.messageText = "Reset All Settings?"
        alert.informativeText = "This resets AstroStack settings to defaults. It does not delete cached PDFs or other temporary files."
        alert.addButton(withTitle: "Reset")
        alert.addButton(withTitle: "Cancel")
        alert.alertStyle = .warning
        let response = alert.runModal()
        guard response == .alertFirstButtonReturn else { return }
        AppSettingsStore.shared.resetToDefaults()
    }

    @objc private func onResetLayout(_ sender: Any?) {
        let alert = NSAlert()
        alert.messageText = "Reset Layout & Panels?"
        alert.informativeText = "This clears stored panel widths and visibility preferences and will take effect on next launch."
        alert.addButton(withTitle: "Reset")
        alert.addButton(withTitle: "Cancel")
        alert.alertStyle = .warning
        let response = alert.runModal()
        guard response == .alertFirstButtonReturn else { return }

        // Clear known layout keys (new + legacy) without touching other subsystems.
        let defaults = UserDefaults.standard
        [
            "astroStack.sidebarWidth",
            "astroStack.sidebarVisible",
            "arxivPicker.sidebarWidth",
            "arxivPicker.sidebarVisible"
        ].forEach { defaults.removeObject(forKey: $0) }
    }
}

// MARK: - Main

// Ensure the app presents itself as AstroStack in UI surfaces (menu bar, app switcher).
ProcessInfo.processInfo.processName = APP_DISPLAY_NAME

if ProcessInfo.processInfo.environment["ARXIV_RUN_PILL_ANIMATION_TESTS"] == "1" {
    #if canImport(XCTest)
    let _ = NSApplication.shared
    let suite = XCTestSuite(forTestCaseClass: PillAnimationStabilityTests.self)
    suite.run()
    let run = suite.testRun as? XCTestSuiteRun
    let failures = (run?.totalFailureCount ?? 0)
    let unexpected = (run?.unexpectedExceptionCount ?? 0)
    NSLog("[PILL_TESTS] failures=\(failures) unexpected=\(unexpected)")
    Darwin.exit((failures == 0 && unexpected == 0) ? 0 : 3)
    #else
    let failures = PillAnimationDeterministicTests.run()
    Darwin.exit(failures == 0 ? 0 : 3)
    #endif
}

if ProcessInfo.processInfo.environment["ARXIV_RUN_SETTINGS_TESTS"] == "1" {
    #if canImport(XCTest)
    let _ = NSApplication.shared
    let suite = XCTestSuite(forTestCaseClass: SettingsNonRegressionTests.self)
    suite.run()
    let run = suite.testRun as? XCTestSuiteRun
    let failures = (run?.totalFailureCount ?? 0)
    let unexpected = (run?.unexpectedExceptionCount ?? 0)
    NSLog("[SETTINGS_TESTS] failures=\(failures) unexpected=\(unexpected)")
    Darwin.exit((failures == 0 && unexpected == 0) ? 0 : 3)
    #else
    let failures = SettingsNonRegressionDeterministicTests.run()
    Darwin.exit(failures == 0 ? 0 : 3)
    #endif
}

let payloadPath = ProcessInfo.processInfo.environment["ARXIV_PAYLOAD_PATH"]
launchLog("entrypoint payloadPath=\(payloadPath ?? "nil")")

// Read STDIN *before* starting the runloop (critical fix)
let stdinText = readAllStdin()
let stdinPayload = decodePayload(stdinText)
launchLog("stdin bytes=\(stdinText.utf8.count) payload=\(stdinPayload != nil)")

let app = NSApplication.shared
launchLog("NSApplication.shared created")
app.setActivationPolicy(.regular)
launchLog("activationPolicy set to regular")

runShareSelfTestIfEnabled()

SettingsMenuIntegrator.installIfNeeded()
AppSettingsBootstrap.applyAppAppearanceOverrideIfNeeded(app)

let controller = PickerWindowController(payloadPathToWatch: payloadPath)
launchLog("controller created window=\(controller.window != nil)")
controller.showWindow(nil)
launchLog("showWindow called visible=\(controller.window?.isVisible ?? false)")
NSApp.activate(ignoringOtherApps: true)
launchLog("activate called")

DispatchQueue.main.async {
    guard let window = controller.window else { return }

    // Ensure we become key/front deterministically; `showWindow` can leave the window visible
    // but not key in some launch contexts.
    NSApp.activate(ignoringOtherApps: true)

    if window.screen == nil, let screen = NSScreen.screens.first {
        let targetSize = NSSize(width: min(1700, screen.visibleFrame.width),
                                height: min(900, screen.visibleFrame.height))
        let origin = NSPoint(x: screen.visibleFrame.midX - (targetSize.width / 2),
                             y: screen.visibleFrame.midY - (targetSize.height / 2))
        window.setFrame(NSRect(origin: origin, size: targetSize), display: true)
    }

    window.makeKeyAndOrderFront(nil)
    window.contentView?.layoutSubtreeIfNeeded()
    window.displayIfNeeded()
    launchLog("window presented frame=\(NSStringFromRect(window.frame)) visible=\(window.isVisible) key=\(window.isKeyWindow) screen=\(String(describing: window.screen))")
}

if ProcessInfo.processInfo.environment["ARXIV_UI_DEBUG"] == "1" {
    weak var weakController = controller
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
        let window = weakController?.window
        let frameText = window.map { NSStringFromRect($0.frame) } ?? "nil"
        let screenText = window?.screen.map { NSStringFromRect($0.frame) } ?? "nil"
        NSLog("[UIDebug] windows=\(NSApp.windows.count) visible=\(window?.isVisible ?? false) key=\(window?.isKeyWindow ?? false) occluded=\(window?.occlusionState.rawValue ?? 0) frame=\(frameText) screen=\(screenText)")
    }
}

if launchDebugEnabled {
    weak var weakController = controller
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
        let window = weakController?.window
        let frameText = window.map { NSStringFromRect($0.frame) } ?? "nil"
        let screenText = window?.screen.map { NSStringFromRect($0.frame) } ?? "nil"
        launchLog("post-show windows=\(NSApp.windows.count) visible=\(window?.isVisible ?? false) key=\(window?.isKeyWindow ?? false) occluded=\(window?.occlusionState.rawValue ?? 0) frame=\(frameText) screen=\(screenText)")
    }
}

// If caller provided payload via STDIN, apply it immediately.
controller.ingestPayloadIfPresent(stdinPayload)

// If STDIN had payload AND a watch-path is set, also write it for parity with the file-based pipeline.
if let _ = stdinPayload, let path = payloadPath, !path.isEmpty {
    try? stdinText.data(using: .utf8)?.write(to: URL(fileURLWithPath: path), options: [.atomic])
}

if launchCheckEnabled {
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
        let window = controller.window
        let visible = window?.isVisible ?? false
        let hasScreen = (window?.screen != nil)
        let ok = visible && hasScreen
        NSLog("[LAUNCH_CHECK] visible=\(visible) screen=\(hasScreen) windows=\(NSApp.windows.count)")
        Darwin.exit(ok ? 0 : 2)
    }
}

launchLog("runloop start")
NSApp.run()
