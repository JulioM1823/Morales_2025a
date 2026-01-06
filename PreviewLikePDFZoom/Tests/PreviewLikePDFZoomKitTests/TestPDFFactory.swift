import Foundation
import CoreGraphics
import UniformTypeIdentifiers
import AppKit

enum TestPDFFactory {
    static func makeOnePagePDF(url: URL, size: CGSize = CGSize(width: 612, height: 792)) throws {
        var mediaBox = CGRect(origin: .zero, size: size)
        guard let ctx = CGContext(url as CFURL, mediaBox: &mediaBox, nil) else {
            throw NSError(domain: "TestPDFFactory", code: 1)
        }

        ctx.beginPDFPage(nil)

        // Background
        ctx.setFillColor(CGColor(gray: 1.0, alpha: 1.0))
        ctx.fill(mediaBox)

        // Grid
        ctx.setStrokeColor(CGColor(gray: 0.9, alpha: 1.0))
        ctx.setLineWidth(1)
        for x in stride(from: 0.0, through: Double(size.width), by: 36.0) {
            ctx.move(to: CGPoint(x: x, y: 0))
            ctx.addLine(to: CGPoint(x: x, y: Double(size.height)))
        }
        for y in stride(from: 0.0, through: Double(size.height), by: 36.0) {
            ctx.move(to: CGPoint(x: 0, y: y))
            ctx.addLine(to: CGPoint(x: Double(size.width), y: y))
        }
        ctx.strokePath()

        // A few deterministic marks
        ctx.setStrokeColor(CGColor(red: 0.2, green: 0.4, blue: 0.9, alpha: 1.0))
        ctx.setLineWidth(3)
        ctx.stroke(CGRect(x: 72, y: 72, width: 180, height: 120))
        ctx.stroke(CGRect(x: 340, y: 540, width: 200, height: 160))

        // Diagonal line
        ctx.setStrokeColor(CGColor(red: 0.9, green: 0.2, blue: 0.2, alpha: 1.0))
        ctx.setLineWidth(2)
        ctx.move(to: CGPoint(x: 50, y: 50))
        ctx.addLine(to: CGPoint(x: size.width - 50, y: size.height - 50))
        ctx.strokePath()

        ctx.endPDFPage()
        ctx.closePDF()
    }

    static func makeTextPDF(url: URL, text: String = "Introduction", size: CGSize = CGSize(width: 612, height: 792)) throws {
        var mediaBox = CGRect(origin: .zero, size: size)
        guard let ctx = CGContext(url as CFURL, mediaBox: &mediaBox, nil) else {
            throw NSError(domain: "TestPDFFactory", code: 2)
        }

        ctx.beginPDFPage(nil)
        ctx.setFillColor(CGColor(gray: 1.0, alpha: 1.0))
        ctx.fill(mediaBox)

        let attr = NSAttributedString(
            string: text,
            attributes: [
                .font: NSFont.systemFont(ofSize: 24, weight: .regular),
                .foregroundColor: NSColor.black
            ]
        )

        let gc = NSGraphicsContext(cgContext: ctx, flipped: false)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = gc
        attr.draw(at: CGPoint(x: 72, y: size.height - 120))
        NSGraphicsContext.restoreGraphicsState()

        ctx.endPDFPage()
        ctx.closePDF()
    }
}
