import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 320, height: 200),
                         styleMask: [.titled, .closable],
                         backing: .buffered,
                         defer: false)
        w.title = "TmpWindow2"
        w.makeKeyAndOrderFront(nil)
        window = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            print("windows", NSApp.windows.count)
            exit(0)
        }
    }
}

let app = NSApplication.shared
_ = app.setActivationPolicy(.regular)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
