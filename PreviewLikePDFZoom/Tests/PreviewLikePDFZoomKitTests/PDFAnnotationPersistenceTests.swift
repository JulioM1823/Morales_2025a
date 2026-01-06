import XCTest
import PDFKit
import AppKit
@testable import PreviewLikePDFZoomKit

@MainActor
final class PDFAnnotationPersistenceTests: XCTestCase {

    private func makeSampleURL(_ name: String = "sample") throws -> URL {
        let tmp = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("\(name)_\(UUID().uuidString).pdf")
        try TestPDFFactory.makeTextPDF(url: tmp, text: "Introduction section for testing")
        return tmp
    }

    private func tempURL(_ name: String) -> URL {
        URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("\(name).pdf")
    }

    func test_pointNote_isEmbeddedInWrittenPDF_andReloads() throws {
        let input = try makeSampleURL("point_note_fixture")
        let output = tempURL("annotated_point_note")

        guard let doc = PDFDocument(url: input) else {
            XCTFail("Failed to load fixture PDF")
            return
        }

        XCTAssertTrue(doc.write(to: output), "Failed to write initial copy to temp output")

        guard let workingDoc = PDFDocument(url: output) else {
            XCTFail("Failed to reload working PDF")
            return
        }

        guard let page0 = workingDoc.page(at: 0) else {
            XCTFail("Missing page 0")
            return
        }

        let pageBounds = page0.bounds(for: .cropBox)
        let anchor = CGPoint(x: pageBounds.midX, y: pageBounds.midY)

        let note = PDFAnnotation(bounds: CGRect(x: anchor.x, y: anchor.y, width: 24, height: 24),
                                 forType: .text,
                                 withProperties: nil)
        note.contents = "Test note contents"
        note.color = NSColor.systemYellow

        page0.addAnnotation(note)

        XCTAssertTrue(workingDoc.write(to: output), "Failed to persist annotated PDF")

        guard let reloaded = PDFDocument(url: output),
              let reloadedPage0 = reloaded.page(at: 0) else {
            XCTFail("Failed to reload persisted PDF")
            return
        }

        let textNotes = reloadedPage0.annotations.filter { $0.type == PDFAnnotationSubtype.text.rawValue }
        XCTAssertFalse(textNotes.isEmpty, "Expected at least one text note annotation after reload")

        let match = textNotes.first { $0.contents == "Test note contents" }
        XCTAssertNotNil(match, "Reloaded PDF did not contain the expected note contents")

        if let match = match {
            let dx = abs(match.bounds.origin.x - note.bounds.origin.x)
            let dy = abs(match.bounds.origin.y - note.bounds.origin.y)
            XCTAssertLessThan(dx, 2.0, "X drift too large after reload")
            XCTAssertLessThan(dy, 2.0, "Y drift too large after reload")
        }
    }

    func test_highlight_isEmbedded_andQuadrilateralsSurviveReload() throws {
        let input = try makeSampleURL("highlight_fixture")
        let output = tempURL("annotated_highlight")

        guard let doc = PDFDocument(url: input) else {
            XCTFail("Failed to load fixture PDF")
            return
        }
        XCTAssertTrue(doc.write(to: output), "Failed to write initial copy")

        guard let workingDoc = PDFDocument(url: output),
              let page0 = workingDoc.page(at: 0) else {
            XCTFail("Failed to load working PDF")
            return
        }

        let selection = workingDoc.findString("Introduction", withOptions: [])?.first
        XCTAssertNotNil(selection, "Fixture must contain the word 'Introduction' for this test")
        guard let sel = selection else { return }

        let bounds = sel.bounds(for: page0)
        let highlight = PDFAnnotation(bounds: bounds, forType: .highlight, withProperties: nil)
        highlight.color = NSColor.systemYellow.withAlphaComponent(0.3)
        if let quads = sel.quadrilateralPoints(for: page0) {
            highlight.quadrilateralPoints = quads
        }

        page0.addAnnotation(highlight)

        XCTAssertTrue(workingDoc.write(to: output), "Failed to persist highlighted PDF")

        guard let reloaded = PDFDocument(url: output),
              let reloadedPage0 = reloaded.page(at: 0) else {
            XCTFail("Failed to reload persisted PDF")
            return
        }

        let highlights = reloadedPage0.annotations.filter { $0.type == PDFAnnotationSubtype.highlight.rawValue }
        XCTAssertFalse(highlights.isEmpty, "Expected highlight annotations after reload")

        let intersects = highlights.contains { $0.bounds.intersects(bounds.insetBy(dx: -2, dy: -2)) }
        XCTAssertTrue(intersects, "Reloaded highlight did not intersect expected selection region")
    }
}
