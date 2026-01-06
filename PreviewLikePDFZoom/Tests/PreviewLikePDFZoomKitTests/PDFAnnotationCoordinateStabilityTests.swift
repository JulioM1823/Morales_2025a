import XCTest
import PDFKit
import AppKit
@testable import PreviewLikePDFZoomKit

@MainActor
final class PDFAnnotationCoordinateStabilityTests: XCTestCase {

    private func sampleURL() throws -> URL {
        let url = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("coord_sample_\(UUID().uuidString).pdf")
        try TestPDFFactory.makeTextPDF(url: url, text: "Introduction coordinate test")
        return url
    }

    func test_pagePoint_toViewPoint_roundTrips_acrossZoomLevels() throws {
        let pdfView = PDFView(frame: CGRect(x: 0, y: 0, width: 900, height: 700))
        pdfView.autoScales = false
        pdfView.displayMode = .singlePageContinuous
        pdfView.displayDirection = .vertical

        let docURL = try sampleURL()
        guard let doc = PDFDocument(url: docURL), let page0 = doc.page(at: 0) else {
            XCTFail("Missing sample PDF")
            return
        }

        pdfView.document = doc
        pdfView.go(to: page0)

        let pageBounds = page0.bounds(for: .cropBox)
        let pagePoint = CGPoint(x: pageBounds.midX, y: pageBounds.midY)

        let zoomLevels: [CGFloat] = [0.75, 1.0, 1.25, 1.75, 2.0]
        for scale in zoomLevels {
            pdfView.scaleFactor = scale
            pdfView.layoutSubtreeIfNeeded()

            let viewPoint = pdfView.convert(pagePoint, from: page0)
            let roundTrip = pdfView.convert(viewPoint, to: page0)

            let dx = abs(roundTrip.x - pagePoint.x)
            let dy = abs(roundTrip.y - pagePoint.y)

            XCTAssertLessThan(dx, 0.5, "Round-trip X drift at scale \(scale)")
            XCTAssertLessThan(dy, 0.5, "Round-trip Y drift at scale \(scale)")
        }
    }

    func test_annotationIconAnchor_remainsStable_afterScroll() throws {
        let scrollView = NSScrollView(frame: CGRect(x: 0, y: 0, width: 900, height: 700))
        let pdfView = PDFView(frame: scrollView.bounds)
        scrollView.documentView = pdfView

        pdfView.autoScales = false
        pdfView.displayMode = .singlePageContinuous
        pdfView.displayDirection = .vertical
        pdfView.scaleFactor = 1.25

        let docURL = try sampleURL()
        guard let doc = PDFDocument(url: docURL), let page0 = doc.page(at: 0) else {
            XCTFail("Missing sample PDF")
            return
        }

        pdfView.document = doc
        pdfView.go(to: page0)

        let pageBounds = page0.bounds(for: .cropBox)
        let anchor = CGPoint(x: pageBounds.midX, y: pageBounds.midY)

        let before = pdfView.convert(anchor, from: page0)

        scrollView.contentView.scroll(to: CGPoint(x: 0, y: 200))
        scrollView.reflectScrolledClipView(scrollView.contentView)

        let after = pdfView.convert(anchor, from: page0)

        let roundTrip = pdfView.convert(after, to: page0)
        XCTAssertLessThan(abs(roundTrip.x - anchor.x), 0.5)
        XCTAssertLessThan(abs(roundTrip.y - anchor.y), 0.5)

        XCTAssertNotEqual(before, after, "Expected view coordinate to change after scroll")
    }
}
