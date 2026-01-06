import AppKit
import PDFKit
import os

public final class ZoomController {
    public enum Reason: String, Sendable {
        case keyboard
        case pinch
        case modeChange
        case windowResize
        case programmatic
    }

    public struct Budgets: Sendable {
        public var softWarnMs: Double = 8
        public var hardFailMs: Double = 60

        public init() {}
    }

    private let log: OSLog
    private let signpostLog: OSLog

    public private(set) var mode: ZoomMode = .fitToWidth
    public var budgets = Budgets()

    private weak var pdfView: PDFView?

    private var isApplyingZoom: Bool = false

    // Pinch coalescing.
    private var pinchSession: PinchSession?
    private var pendingPinchTargetScale: CGFloat?
    private var pendingPinchApplyScheduled: Bool = false

    public init(pdfView: PDFView, subsystem: String = "PreviewLikePDFZoom", category: String = "zoom") {
        self.pdfView = pdfView
        self.log = OSLog(subsystem: subsystem, category: category)
        self.signpostLog = OSLog(subsystem: subsystem, category: category + ".signpost")

        // We manage scale manually.
        pdfView.autoScales = false
    }

    // MARK: Public API

    public func setMode(_ newMode: ZoomMode, reason: Reason = .modeChange) {
        mode = newMode
        applyMode(reason: reason)
    }

    public func zoomStep(direction: ZoomLadder.Direction, event: NSEvent? = nil) {
        guard let pdfView, pdfView.document != nil else { return }
        let anchor = PDFCoordinateConversions.anchorPointInPDFView(
            pdfView: pdfView,
            event: event,
            allowMouseLocation: true
        )

        let current = pdfView.scaleFactor
        let next = ZoomLadder.nextStep(from: current, direction: direction)
        setMode(.custom(scale: next), reason: .keyboard)
        applyZoom(targetScale: next, anchorInPDFView: anchor.pointInPDFView, anchorPage: anchor.page, reason: .keyboard)
    }

    /// Canonical zoom pipeline: *all* zoom changes flow through here.
    ///
    /// - Parameters:
    ///   - targetScale: Desired scale factor.
    ///   - anchorInPDFView: Anchor point in PDFView coordinates. If nil, uses visible center.
    ///   - reason: Used for logging/testing.
    public func applyZoom(
        targetScale: CGFloat,
        anchorInPDFView: NSPoint?,
        reason: Reason
    ) {
        guard let pdfView, pdfView.document != nil else { return }
        let resolvedAnchor: (NSPoint, PDFPage?)
        if let anchorInPDFView {
            resolvedAnchor = (anchorInPDFView, pdfView.page(for: anchorInPDFView, nearest: false))
        } else {
            let vis = PDFCoordinateConversions.visibleRectInPDFView(pdfView)
            let center = NSPoint(x: vis.midX, y: vis.midY)
            resolvedAnchor = (center, pdfView.page(for: center, nearest: false))
        }
        applyZoom(targetScale: targetScale, anchorInPDFView: resolvedAnchor.0, anchorPage: resolvedAnchor.1, reason: reason)
    }

    /// Trackpad pinch path with coalescing and stable anchoring.
    public func handleMagnify(_ event: NSEvent) -> Bool {
        guard let pdfView, pdfView.document != nil else { return false }

        let phase = event.phase

        if phase.contains(.began) || pinchSession == nil {
            let anchor = PDFCoordinateConversions.anchorPointInPDFView(
                pdfView: pdfView,
                event: event,
                allowMouseLocation: true
            )
            pinchSession = PinchSession(anchorPointInPDFView: anchor.pointInPDFView, anchorPage: anchor.page)
        }

        // Compute new target scale from current (not from accumulating magnification deltas),
        // and coalesce to at most once per runloop.
        let current = pdfView.scaleFactor
        let rawTarget = current * (1 + event.magnification)
        pendingPinchTargetScale = rawTarget

        if !pendingPinchApplyScheduled {
            pendingPinchApplyScheduled = true
            DispatchQueue.main.async { [weak self] in
                self?.flushPendingPinchScale()
            }
        }

        if phase.contains(.ended) || phase.contains(.cancelled) {
            // Final commit (ensure last pending scale applied).
            flushPendingPinchScale()
            pinchSession = nil
        }

        return true
    }

    /// Call from your window/content view resize path.
    public func handleViewportResize(reason: Reason = .windowResize) {
        guard let pdfView, pdfView.document != nil else { return }

        let vis = PDFCoordinateConversions.visibleRectInPDFView(pdfView)
        let center = NSPoint(x: vis.midX, y: vis.midY)

        switch mode {
        case .fitToWidth, .fitToPage:
            applyMode(anchorOverride: center, reason: reason)
        case .actualSize:
            applyZoom(targetScale: 1.0, anchorInPDFView: center, reason: reason)
        case .custom(let s):
            applyZoom(targetScale: s, anchorInPDFView: center, reason: reason)
        }
    }

    // MARK: Internal

    private func flushPendingPinchScale() {
        guard pendingPinchApplyScheduled else { return }
        pendingPinchApplyScheduled = false

        guard let pdfView, let session = pinchSession else {
            pendingPinchTargetScale = nil
            return
        }

        guard let target = pendingPinchTargetScale else { return }
        pendingPinchTargetScale = nil

        // Pinch implies custom scale.
        mode = .custom(scale: target)
        applyZoom(targetScale: target, anchorInPDFView: session.anchorPointInPDFView, anchorPage: session.anchorPage, reason: .pinch)
    }

    private func applyMode(anchorOverride: NSPoint? = nil, reason: Reason) {
        guard let pdfView, pdfView.document != nil else { return }
        pdfView.autoScales = false

        let vis = PDFCoordinateConversions.visibleRectInPDFView(pdfView)
        let defaultAnchor = NSPoint(x: vis.midX, y: vis.midY)
        let anchor = anchorOverride ?? defaultAnchor

        switch mode {
        case .fitToWidth:
            let scale = computeFitToWidthScale(pdfView: pdfView)
            applyZoom(targetScale: scale, anchorInPDFView: anchor, reason: reason)
        case .fitToPage:
            let scale = computeFitToPageScale(pdfView: pdfView)
            applyZoom(targetScale: scale, anchorInPDFView: anchor, reason: reason)
        case .actualSize:
            applyZoom(targetScale: 1.0, anchorInPDFView: anchor, reason: reason)
        case .custom(let s):
            applyZoom(targetScale: s, anchorInPDFView: anchor, reason: reason)
        }
    }

    private func clampScale(_ scale: CGFloat, pdfView: PDFView) -> CGFloat {
        var clamped = scale
        let minScale = pdfView.minScaleFactor
        let maxScale = pdfView.maxScaleFactor
        if minScale > 0 { clamped = max(clamped, minScale) }
        if maxScale > 0 { clamped = min(clamped, maxScale) }
        return clamped
    }

    private func computeFitToWidthScale(pdfView: PDFView) -> CGFloat {
        guard let page = pdfView.currentPage ?? pdfView.document?.page(at: 0) else { return pdfView.scaleFactor }
        let vis = PDFCoordinateConversions.visibleRectInPDFView(pdfView)
        let pageBounds = page.bounds(for: pdfView.displayBox)
        guard pageBounds.width > 1 else { return pdfView.scaleFactor }

        // Visible rect is in PDFView coords; PDFView coords map 1:1 to its internal layout units.
        // PDFKit's scaleFactor scales page points to view points.
        // targetScale = visibleWidth / pageWidthInPoints.
        let scale = vis.width / pageBounds.width
        return clampScale(scale, pdfView: pdfView)
    }

    private func computeFitToPageScale(pdfView: PDFView) -> CGFloat {
        guard let page = pdfView.currentPage ?? pdfView.document?.page(at: 0) else { return pdfView.scaleFactor }
        let vis = PDFCoordinateConversions.visibleRectInPDFView(pdfView)
        let pageBounds = page.bounds(for: pdfView.displayBox)
        guard pageBounds.width > 1, pageBounds.height > 1 else { return pdfView.scaleFactor }

        let sx = vis.width / pageBounds.width
        let sy = vis.height / pageBounds.height
        return clampScale(min(sx, sy), pdfView: pdfView)
    }

    private func applyZoom(
        targetScale: CGFloat,
        anchorInPDFView: NSPoint,
        anchorPage: PDFPage?,
        reason: Reason
    ) {
        guard let pdfView, pdfView.document != nil else { return }
        let clampedScale = clampScale(targetScale, pdfView: pdfView)
        let current = pdfView.scaleFactor
        guard abs(clampedScale - current) > 0.0001 else { return }

        // Prevent re-entrant feedback loops.
        if isApplyingZoom { return }
        isApplyingZoom = true
        defer { isApplyingZoom = false }

        let signpostID = OSSignpostID(log: signpostLog)
        os_signpost(.begin, log: signpostLog, name: "applyZoom", signpostID: signpostID,
                    "reason=%{public}@ s=%.4f->%.4f", reason.rawValue, current, clampedScale)

        let t0 = CACurrentMediaTime()

        pdfView.autoScales = false

        guard let scrollView = PDFCoordinateConversions.primaryScrollView(in: pdfView) else {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            pdfView.scaleFactor = clampedScale
            CATransaction.commit()
            os_signpost(.end, log: signpostLog, name: "applyZoom", signpostID: signpostID)
            return
        }

        let clip = scrollView.contentView
        let docView = scrollView.documentView

        let resolvedPage = anchorPage ?? pdfView.page(for: anchorInPDFView, nearest: false)
        let pagePoint = resolvedPage.map { pdfView.convert(anchorInPDFView, to: $0) }
        let anchorInClip = pdfView.convert(anchorInPDFView, to: clip)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        pdfView.scaleFactor = clampedScale
        CATransaction.commit()

        // Make sure PDFKit has a chance to update its internal document view geometry.
        // Keep this minimal; do not trigger expensive layout chains repeatedly.
        scrollView.layoutSubtreeIfNeeded()
        docView?.layoutSubtreeIfNeeded()

        if let resolvedPage, let pagePoint, let docView {
            let anchorAfterScaleInPDFView = pdfView.convert(pagePoint, from: resolvedPage)
            let docPointAfter = pdfView.convert(anchorAfterScaleInPDFView, to: docView)

            var originTarget = NSPoint(
                x: docPointAfter.x - anchorInClip.x,
                y: docPointAfter.y - anchorInClip.y
            )

            originTarget = PDFCoordinateConversions.pixelAlignedScrollOrigin(originTarget, in: pdfView)

            var originClamped = PDFCoordinateConversions.clampScrollOrigin(originTarget, clipView: clip, documentView: docView)
            originClamped = PDFCoordinateConversions.pixelAlignedScrollOrigin(originClamped, in: pdfView)

            CATransaction.begin()
            CATransaction.setDisableActions(true)
            clip.setBoundsOrigin(originClamped)
            scrollView.reflectScrolledClipView(clip)
            CATransaction.commit()
        }

        let elapsedMs = (CACurrentMediaTime() - t0) * 1000.0
        if elapsedMs >= budgets.softWarnMs {
            os_log("zoom_slow reason=%{public}@ ms=%.2f scale=%.4f", log: log, type: .info, reason.rawValue, elapsedMs, clampedScale)
        }
        if elapsedMs >= budgets.hardFailMs {
            os_log("zoom_TOO_SLOW reason=%{public}@ ms=%.2f scale=%.4f", log: log, type: .fault, reason.rawValue, elapsedMs, clampedScale)
            assertionFailure("Zoom apply exceeded hard budget: \(elapsedMs)ms")
        }

        os_signpost(.end, log: signpostLog, name: "applyZoom", signpostID: signpostID,
                    "ms=%.2f", elapsedMs)
    }

    private struct PinchSession {
        let anchorPointInPDFView: NSPoint
        let anchorPage: PDFPage?
    }
}
