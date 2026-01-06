import AppKit

let app = NSApplication.shared
_ = app.setActivationPolicy(.regular)

let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 300, height: 200),
                 styleMask: [.titled, .closable],
                 backing: .buffered,
                 defer: false)
w.title = "TmpWindow"
w.makeKeyAndOrderFront(nil)
app.activate(ignoringOtherApps: true)

DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
    let frameText = NSStringFromRect(w.frame)
    let screenText = w.screen.map { NSStringFromRect($0.frame) } ?? "nil"
    print("visible", w.isVisible, "key", w.isKeyWindow, "frame", frameText, "screen", screenText)
    exit(0)
}

app.run()
