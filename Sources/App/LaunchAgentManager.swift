import Foundation
import os

enum LaunchAgentManager {
    private static let log = Logger(subsystem: APP_LOG_SUBSYSTEM, category: "launch-agent")
    private static let label = "com.juliomorales.AstroStack.refresh"
    private static let startIntervalSeconds = 3600
    private static let scheduledHour = 23
    private static let scheduledMinute = 0

    static func ensureInstalled() {
        guard !isDisabled else { return }
        guard let execURL = Bundle.main.executableURL else {
            log.error("launch agent install skipped: missing executable URL")
            return
        }

        let fm = FileManager.default
        let launchAgents = fm.homeDirectoryForCurrentUser
            .appendingPathComponent("Library", isDirectory: true)
            .appendingPathComponent("LaunchAgents", isDirectory: true)
        let plistURL = launchAgents.appendingPathComponent("\(label).plist")
        let expected = makePlist(executablePath: execURL.path)

        do {
            try fm.createDirectory(at: launchAgents, withIntermediateDirectories: true, attributes: nil)
        } catch {
            log.error("launch agent install failed: \(error.localizedDescription, privacy: .public)")
            return
        }

        let needsWrite = !existingPlistMatches(expected, at: plistURL)
        if needsWrite {
            if writePlist(expected, to: plistURL) {
                log.info("launch agent plist updated at \(plistURL.path, privacy: .public)")
            }
        }

        loadAgent(at: plistURL, reload: needsWrite)
    }

    private static var isDisabled: Bool {
        let raw = (ProcessInfo.processInfo.environment["ASTROSTACK_DISABLE_LAUNCH_AGENT"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return raw == "1" || raw.lowercased() == "true"
    }

    private static func makePlist(executablePath: String) -> [String: Any] {
        [
            "Label": label,
            "ProgramArguments": [executablePath, "--refresh"],
            "StartInterval": startIntervalSeconds,
            "StartCalendarInterval": [
                "Hour": scheduledHour,
                "Minute": scheduledMinute
            ],
            "RunAtLoad": true,
            "ProcessType": "Background"
        ]
    }

    private static func existingPlistMatches(_ expected: [String: Any], at url: URL) -> Bool {
        guard let data = try? Data(contentsOf: url) else { return false }
        guard let plist = try? PropertyListSerialization.propertyList(from: data, options: [], format: nil) as? [String: Any] else {
            return false
        }
        guard let labelValue = plist["Label"] as? String, labelValue == label else { return false }
        guard let args = plist["ProgramArguments"] as? [String],
              let expectedArgs = expected["ProgramArguments"] as? [String],
              args == expectedArgs else { return false }
        guard let interval = plist["StartInterval"] as? Int,
              interval == startIntervalSeconds else { return false }
        if let cal = plist["StartCalendarInterval"] as? [String: Any] {
            let hourOk = (cal["Hour"] as? Int) == scheduledHour
            let minuteOk = (cal["Minute"] as? Int) == scheduledMinute
            if !hourOk || !minuteOk { return false }
        } else {
            return false
        }
        return true
    }

    private static func writePlist(_ plist: [String: Any], to url: URL) -> Bool {
        do {
            let data = try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
            try data.write(to: url, options: [.atomic])
            return true
        } catch {
            log.error("launch agent plist write failed: \(error.localizedDescription, privacy: .public)")
            return false
        }
    }

    private static func loadAgent(at url: URL, reload: Bool) {
        let uid = getuid()
        let guiTarget = "gui/\(uid)"

        if reload {
            _ = runLaunchctl(["bootout", guiTarget, url.path])
        }
        let bootstrap = runLaunchctl(["bootstrap", guiTarget, url.path])
        if bootstrap == 0 {
            _ = runLaunchctl(["enable", "\(guiTarget)/\(label)"])
        }
    }

    @discardableResult
    private static func runLaunchctl(_ arguments: [String]) -> Int32 {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        process.arguments = arguments
        do {
            try process.run()
            process.waitUntilExit()
            return process.terminationStatus
        } catch {
            log.error("launchctl failed: \(error.localizedDescription, privacy: .public)")
            return -1
        }
    }
}
