import AppKit
import PDFKit
import PreviewLikePDFZoomKit

@main
final class PreviewLikePDFZoomApp: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private let pdfView = ControlledPDFView(frame: .zero)
    private var zoomController: ZoomController!

    func applicationDidFinishLaunching(_ notification: Notification) {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)

        let w: CGFloat = 980
        let h: CGFloat = 720

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: w, height: h),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Preview-like PDF Zoom"
        window.center()

        // PDFView configuration (continuous scrolling like Preview).
        pdfView.translatesAutoresizingMaskIntoConstraints = false
        pdfView.displayMode = .singlePageContinuous
        pdfView.displayDirection = .vertical
        pdfView.displaysAsBook = false
        pdfView.backgroundColor = NSColor.windowBackgroundColor
        pdfView.autoScales = false

        let host = NSView(frame: .zero)
        host.translatesAutoresizingMaskIntoConstraints = false
        host.addSubview(pdfView)
        NSLayoutConstraint.activate([
            pdfView.leadingAnchor.constraint(equalTo: host.leadingAnchor),
            pdfView.trailingAnchor.constraint(equalTo: host.trailingAnchor),
            pdfView.topAnchor.constraint(equalTo: host.topAnchor),
            pdfView.bottomAnchor.constraint(equalTo: host.bottomAnchor)
        ])

        window.contentView = host

        zoomController = ZoomController(pdfView: pdfView)
        pdfView.onMagnify = { [weak self] event in
            guard let self else { return false }
            return self.zoomController.handleMagnify(event)
        }

        installMenu()

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(windowDidResize(_:)),
            name: NSWindow.didResizeNotification,
            object: window
        )

        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        // If a PDF path was passed in, open it.
        let args = CommandLine.arguments
        if args.count >= 2 {
            openPDF(atPath: args[1])
        } else {
            // Start empty; user can File > Open.
        }
    }

    @objc private func windowDidResize(_ note: Notification) {
        zoomController.handleViewportResize()
    }

    // MARK: - Menu + Commands

    private func installMenu() {
        let mainMenu = NSMenu()
        NSApp.mainMenu = mainMenu

        let appItem = NSMenuItem()
        mainMenu.addItem(appItem)
        let appMenu = NSMenu()
        appItem.submenu = appMenu
        appMenu.addItem(withTitle: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        let fileItem = NSMenuItem()
        mainMenu.addItem(fileItem)
        let fileMenu = NSMenu(title: "File")
        fileItem.submenu = fileMenu
        fileMenu.addItem(withTitle: "Open…", action: #selector(openDocument(_:)), keyEquivalent: "o")

        let viewItem = NSMenuItem()
        mainMenu.addItem(viewItem)
        let viewMenu = NSMenu(title: "View")
        viewItem.submenu = viewMenu

        let zoomIn = NSMenuItem(title: "Zoom In", action: #selector(zoomIn(_:)), keyEquivalent: "+")
        zoomIn.keyEquivalentModifierMask = [.command]
        viewMenu.addItem(zoomIn)

        let zoomOut = NSMenuItem(title: "Zoom Out", action: #selector(zoomOut(_:)), keyEquivalent: "-")
        zoomOut.keyEquivalentModifierMask = [.command]
        viewMenu.addItem(zoomOut)

        viewMenu.addItem(.separator())

        let actual = NSMenuItem(title: "Actual Size", action: #selector(actualSize(_:)), keyEquivalent: "0")
        actual.keyEquivalentModifierMask = [.command]
        viewMenu.addItem(actual)

        let fitWidth = NSMenuItem(title: "Zoom to Fit Width", action: #selector(fitToWidth(_:)), keyEquivalent: "9")
        fitWidth.keyEquivalentModifierMask = [.command]
        viewMenu.addItem(fitWidth)

        let fitPage = NSMenuItem(title: "Zoom to Fit Page", action: #selector(fitToPage(_:)), keyEquivalent: "8")
        fitPage.keyEquivalentModifierMask = [.command]
        viewMenu.addItem(fitPage)
    }

    @objc private func openDocument(_ sender: Any?) {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.pdf]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.beginSheetModal(for: window) { [weak self] resp in
            guard let self else { return }
            if resp == .OK, let url = panel.url {
                self.openPDF(url: url)
            }
        }
    }

    private func openPDF(atPath path: String) {
        let url = URL(fileURLWithPath: path)
        openPDF(url: url)
    }

    private func openPDF(url: URL) {
        guard let doc = PDFDocument(url: url) else { return }
        pdfView.document = doc
        pdfView.goToFirstPage(nil)
        zoomController.setMode(.fitToWidth)
    }

    @objc private func zoomIn(_ sender: Any?) {
        zoomController.zoomStep(direction: .in)
    }

    @objc private func zoomOut(_ sender: Any?) {
        zoomController.zoomStep(direction: .out)
    }

    @objc private func actualSize(_ sender: Any?) {
        zoomController.setMode(.actualSize)
        zoomController.handleViewportResize(reason: .modeChange)
    }

    @objc private func fitToWidth(_ sender: Any?) {
        zoomController.setMode(.fitToWidth)
        zoomController.handleViewportResize(reason: .modeChange)
    }

    @objc private func fitToPage(_ sender: Any?) {
        zoomController.setMode(.fitToPage)
        zoomController.handleViewportResize(reason: .modeChange)
    }
}

private final class ControlledPDFView: PDFView {
    var onMagnify: ((NSEvent) -> Bool)?

    override var acceptsFirstResponder: Bool { true }

    override func magnify(with event: NSEvent) {
        if onMagnify?(event) == true { return }
        super.magnify(with: event)
    }
}
