#!/usr/bin/env swift
import AppKit

// Usage:
//   arxiv-hud.swift /path/to/status.txt
// The app polls the file for the latest status message.
// If the file contains "__CLOSE__", the HUD exits.

final class HUDApp: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private let label = NSTextField(labelWithString: "Working…")
    private let statusFile: String
    private var lastContents: String = ""
    private var timer: Timer?

    init(statusFile: String) {
        self.statusFile = statusFile
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)

        let w: CGFloat = 360
        let h: CGFloat = 120

        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: w, height: h),
            styleMask: [.titled],
            backing: .buffered,
            defer: false
        )
        win.isReleasedWhenClosed = false
        win.level = .floating
        win.title = ""
        win.titleVisibility = .hidden
        win.titlebarAppearsTransparent = true
        win.isMovableByWindowBackground = true
        win.standardWindowButton(.closeButton)?.isHidden = true
        win.standardWindowButton(.miniaturizeButton)?.isHidden = true
        win.standardWindowButton(.zoomButton)?.isHidden = true

        let v = NSVisualEffectView(frame: win.contentView!.bounds)
        v.autoresizingMask = [.width, .height]
        v.material = .hudWindow
        v.blendingMode = .behindWindow
        v.state = .active

        label.font = NSFont.systemFont(ofSize: 15, weight: .medium)
        label.alignment = .center
        label.textColor = .labelColor
        label.lineBreakMode = .byTruncatingTail
        label.frame = NSRect(x: 16, y: 62, width: w - 32, height: 22)

        let spinner = NSProgressIndicator(frame: NSRect(x: (w - 20) / 2, y: 30, width: 20, height: 20))
        spinner.style = .spinning
        spinner.controlSize = .regular
        spinner.startAnimation(nil)

        v.addSubview(label)
        v.addSubview(spinner)
        win.contentView = v

        win.center()
        win.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        self.window = win

        // Poll the status file.
        timer = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { [weak self] _ in
            self?.pollStatusFile()
        }
        RunLoop.main.add(timer!, forMode: .common)
        pollStatusFile()
    }

    private func pollStatusFile() {
        let contents = (try? String(contentsOfFile: statusFile, encoding: .utf8)) ?? ""
        let trimmed = contents.trimmingCharacters(in: .whitespacesAndNewlines)

        if trimmed == "__CLOSE__" {
            timer?.invalidate()
            timer = nil
            NSApp.terminate(nil)
            return
        }

        if trimmed.isEmpty {
            if lastContents != "" {
                lastContents = ""
                label.stringValue = "Working…"
            }
            return
        }

        if trimmed != lastContents {
            lastContents = trimmed
            label.stringValue = trimmed
        }
    }
}

let args = CommandLine.arguments
guard args.count >= 2 else { exit(2) }
let statusFile = args[1]

let app = NSApplication.shared
let d = HUDApp(statusFile: statusFile)
app.delegate = d
app.run()