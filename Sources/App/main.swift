import AppKit

// Keep a strong reference to the delegate for the app lifetime.
let app = NSApplication.shared
let mode = AppLaunchMode.resolve(arguments: CommandLine.arguments)
if mode == .backgroundRefresh {
    app.setActivationPolicy(.prohibited)
} else {
    app.setActivationPolicy(.regular)
}
let delegate = AppDelegate(launchMode: mode)
app.delegate = delegate
app.run()
