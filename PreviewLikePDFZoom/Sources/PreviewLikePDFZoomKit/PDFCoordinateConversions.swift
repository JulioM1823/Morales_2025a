import AppKit
import PDFKit

public enum PDFCoordinateConversions {
    /// Returns the primary scroll view used by PDFKit inside the given PDFView.
    /// PDFView's internal structure changes across macOS versions; this walks the subview tree.
    public static func primaryScrollView(in pdfView: PDFView) -> NSScrollView? {
        var found: [NSScrollView] = []
        func walk(_ v: NSView) {
            if let sv = v as? NSScrollView { found.append(sv) }
            for sub in v.subviews { walk(sub) }
        }
        walk(pdfView)
        if found.count == 1 { return found[0] }
        return found.first(where: { $0.documentView != nil }) ?? found.first
    }

    public static func visibleRectInPDFView(_ pdfView: PDFView) -> NSRect {
        if let scrollView = primaryScrollView(in: pdfView) {
            let clip = scrollView.contentView
            return pdfView.convert(clip.bounds, from: clip)
        }
        return pdfView.bounds
    }

    public static func mouseLocationInPDFView(_ pdfView: PDFView) -> NSPoint? {
        guard let window = pdfView.window else { return nil }
        let windowPoint = window.convertPoint(fromScreen: NSEvent.mouseLocation)
        return pdfView.convert(windowPoint, from: nil)
    }

    public static func anchorPointInPDFView(
        pdfView: PDFView,
        event: NSEvent?,
        allowMouseLocation: Bool
    ) -> (pointInPDFView: NSPoint, page: PDFPage?) {
        let visibleRect = visibleRectInPDFView(pdfView)

        if let event {
            let p = pdfView.convert(event.locationInWindow, from: nil)
            if visibleRect.contains(p) {
                if let page = pdfView.page(for: p, nearest: false) {
                    return (p, page)
                }
            }
        }

        if allowMouseLocation, let p = mouseLocationInPDFView(pdfView) {
            if visibleRect.contains(p) {
                if let page = pdfView.page(for: p, nearest: false) {
                    return (p, page)
                }
            }
        }

        let center = NSPoint(x: visibleRect.midX, y: visibleRect.midY)
        return (center, pdfView.page(for: center, nearest: false))
    }

    public static func clampScrollOrigin(
        _ origin: NSPoint,
        clipView: NSClipView,
        documentView: NSView?
    ) -> NSPoint {
        var out = origin
        guard let documentView else {
            return clipView.constrainBoundsRect(NSRect(origin: out, size: clipView.bounds.size)).origin
        }

        let clipSize = clipView.bounds.size
        let docFrame = documentView.frame

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

    public static func pixelAlignedScrollOrigin(_ origin: NSPoint, in view: NSView?) -> NSPoint {
        guard let window = view?.window else { return origin }
        let scale = max(1.0, window.backingScaleFactor)
        func align(_ v: CGFloat) -> CGFloat { (v * scale).rounded() / scale }
        return NSPoint(x: align(origin.x), y: align(origin.y))
    }
}
