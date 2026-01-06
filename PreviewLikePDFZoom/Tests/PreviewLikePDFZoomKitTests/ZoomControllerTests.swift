import XCTest
import AppKit
import PDFKit
@testable import PreviewLikePDFZoomKit

@MainActor
final class ZoomControllerTests: XCTestCase {
    private func makeHarness(viewport: CGSize) throws -> (window: NSWindow, pdfView: PDFView, zoom: ZoomController) {
        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: viewport),
            styleMask: [.titled],
            backing: .buffered,
            defer: false
        )
        let pdfView = PDFView(frame: NSRect(origin: .zero, size: viewport))
        pdfView.displayMode = .singlePageContinuous
        pdfView.displayDirection = .vertical
        pdfView.backgroundColor = .white
        pdfView.autoScales = false

        window.contentView = pdfView
        window.layoutIfNeeded()

        let zoom = ZoomController(pdfView: pdfView, subsystem: "PreviewLikePDFZoom.Tests", category: "zoom")
        zoom.budgets.softWarnMs = 9999 // tests shouldn't spam logs
        zoom.budgets.hardFailMs = 9999
        return (window, pdfView, zoom)
    }

    private func loadTestPDF(into pdfView: PDFView) throws {
        let tmp = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("test_one_page.pdf")
        try TestPDFFactory.makeOnePagePDF(url: tmp)
        guard let doc = PDFDocument(url: tmp) else {
            throw NSError(domain: "ZoomControllerTests", code: 1)
        }
        pdfView.document = doc
        pdfView.goToFirstPage(nil)
        pdfView.layoutSubtreeIfNeeded()
    }

    func testAnchorRoundTrip_NoDriftWithinHalfPixel() throws {
        let (window, pdfView, zoom) = try makeHarness(viewport: CGSize(width: 800, height: 600))
        _ = window
        try loadTestPDF(into: pdfView)

        // Set a known starting scale.
        zoom.setMode(.custom(scale: 1.2), reason: .programmatic)
        zoom.applyZoom(targetScale: 1.2, anchorInPDFView: nil, reason: .programmatic)

        // Choose an anchor point inside content.
        let vis = PDFCoordinateConversions.visibleRectInPDFView(pdfView)
        let anchor = NSPoint(x: vis.minX + 120, y: vis.minY + 160)
        guard let page = pdfView.page(for: anchor, nearest: false) else {
            XCTFail("Anchor not on page")
            return
        }
        let pagePoint = pdfView.convert(anchor, to: page)

        // Zoom in/out deterministically.
        for _ in 0..<12 {
            let next = ZoomLadder.nextStep(from: pdfView.scaleFactor, direction: .in)
            zoom.applyZoom(targetScale: next, anchorInPDFView: anchor, reason: .keyboard)
        }
        for _ in 0..<12 {
            let next = ZoomLadder.nextStep(from: pdfView.scaleFactor, direction: .out)
            zoom.applyZoom(targetScale: next, anchorInPDFView: anchor, reason: .keyboard)
        }

        // Where does the original content point land?
        let finalAnchor = pdfView.convert(pagePoint, from: page)
        XCTAssertLessThanOrEqual(abs(finalAnchor.x - anchor.x), 0.5)
        XCTAssertLessThanOrEqual(abs(finalAnchor.y - anchor.y), 0.5)
    }

    func testBoundsClamping_NoOverscrollVoid() throws {
        let (window, pdfView, zoom) = try makeHarness(viewport: CGSize(width: 700, height: 500))
        _ = window
        try loadTestPDF(into: pdfView)

        zoom.setMode(.custom(scale: 2.0), reason: .programmatic)
        zoom.applyZoom(targetScale: 2.0, anchorInPDFView: nil, reason: .programmatic)

        guard let scrollView = PDFCoordinateConversions.primaryScrollView(in: pdfView),
              let docView = scrollView.documentView else {
            XCTFail("Missing scrollView/docView")
            return
        }
        let clip = scrollView.contentView

        // Force scroll to top-most and bottom-most, then apply large zoom deltas.
        let top = NSPoint(x: docView.frame.minX, y: docView.frame.minY)
        clip.setBoundsOrigin(top)
        scrollView.reflectScrolledClipView(clip)

        zoom.applyZoom(targetScale: 3.0, anchorInPDFView: nil, reason: .keyboard)

        var origin = clip.bounds.origin
        let clampedTop = PDFCoordinateConversions.clampScrollOrigin(origin, clipView: clip, documentView: docView)
        XCTAssertEqual(origin.x, clampedTop.x, accuracy: 0.01)
        XCTAssertEqual(origin.y, clampedTop.y, accuracy: 0.01)

        let bottom = NSPoint(x: docView.frame.minX, y: max(docView.frame.minY, docView.frame.maxY - clip.bounds.height))
        clip.setBoundsOrigin(bottom)
        scrollView.reflectScrolledClipView(clip)

        zoom.applyZoom(targetScale: 1.1, anchorInPDFView: nil, reason: .keyboard)

        origin = clip.bounds.origin
        let clampedBottom = PDFCoordinateConversions.clampScrollOrigin(origin, clipView: clip, documentView: docView)
        XCTAssertEqual(origin.x, clampedBottom.x, accuracy: 0.01)
        XCTAssertEqual(origin.y, clampedBottom.y, accuracy: 0.01)
    }

    func testStress_AlternatingZoomAndResize_IsDeterministic() throws {
        let (window, pdfView, zoom) = try makeHarness(viewport: CGSize(width: 800, height: 600))
        try loadTestPDF(into: pdfView)

        zoom.setMode(.custom(scale: 1.4), reason: .programmatic)
        zoom.applyZoom(targetScale: 1.4, anchorInPDFView: nil, reason: .programmatic)

        func runSequence() -> (scale: CGFloat, origin: NSPoint) {
            for i in 0..<50 {
                let dir: ZoomLadder.Direction = (i % 2 == 0) ? .in : .out
                let next = ZoomLadder.nextStep(from: pdfView.scaleFactor, direction: dir)
                zoom.applyZoom(targetScale: next, anchorInPDFView: nil, reason: .keyboard)

                let newSize = CGSize(width: (i % 3 == 0) ? 760 : 820, height: (i % 4 == 0) ? 560 : 620)
                window.setContentSize(newSize)
                window.contentView?.setFrameSize(newSize)
                window.layoutIfNeeded()
                zoom.handleViewportResize(reason: .windowResize)
            }

            let scale = pdfView.scaleFactor
            let origin: NSPoint
            if let sv = PDFCoordinateConversions.primaryScrollView(in: pdfView) {
                origin = sv.contentView.bounds.origin
            } else {
                origin = .zero
            }
            return (scale, origin)
        }

        let a = runSequence()
        // Reset to identical starting state and re-run.
        try loadTestPDF(into: pdfView)
        zoom.setMode(.custom(scale: 1.4), reason: .programmatic)
        zoom.applyZoom(targetScale: 1.4, anchorInPDFView: nil, reason: .programmatic)
        let b = runSequence()

        XCTAssertEqual(a.scale, b.scale, accuracy: 0.0001)
        XCTAssertEqual(a.origin.x, b.origin.x, accuracy: 0.5)
        XCTAssertEqual(a.origin.y, b.origin.y, accuracy: 0.5)
    }

    func testSnapshot_ZoomAnchoredAtCenter() throws {
        let record = (ProcessInfo.processInfo.environment["SNAPSHOT_RECORD"] == "1")
        let (window, pdfView, zoom) = try makeHarness(viewport: CGSize(width: 640, height: 480))
        _ = window
        try loadTestPDF(into: pdfView)

        zoom.setMode(.custom(scale: 1.0), reason: .programmatic)
        zoom.applyZoom(targetScale: 1.0, anchorInPDFView: nil, reason: .programmatic)

        // Zoom a few steps around center.
        zoom.applyZoom(targetScale: 1.5, anchorInPDFView: nil, reason: .keyboard)
        zoom.applyZoom(targetScale: 1.0, anchorInPDFView: nil, reason: .keyboard)

        pdfView.layoutSubtreeIfNeeded()
        let png = SnapshotTesting.pngData(of: pdfView)
        try SnapshotTesting.assertSnapshot(named: "center_zoom_roundtrip", data: png, record: record)
    }

    func testPerformance_KeyboardZoomBudget() throws {
        let (window, pdfView, zoom) = try makeHarness(viewport: CGSize(width: 800, height: 600))
        _ = window
        try loadTestPDF(into: pdfView)

        let iterations = 25
        let t0 = CACurrentMediaTime()
        for _ in 0..<iterations {
            let next = ZoomLadder.nextStep(from: pdfView.scaleFactor, direction: .in)
            zoom.applyZoom(targetScale: next, anchorInPDFView: nil, reason: .keyboard)
        }
        let elapsedMs = (CACurrentMediaTime() - t0) * 1000.0
        let avgMs = elapsedMs / Double(iterations)

        // Hard fail gate. Tune via env var if needed.
        let budget = Double(ProcessInfo.processInfo.environment["ZOOM_TEST_BUDGET_MS"] ?? "60") ?? 60
        XCTAssertLessThanOrEqual(avgMs, budget, "avgMs=\(avgMs) budget=\(budget)")
    }
}
