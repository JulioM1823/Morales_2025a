import AppKit
import Foundation
import os

enum MailScanError: Error, CustomStringConvertible {
    case scriptNotFound(path: String)
    case scriptLoadFailed(path: String, message: String)
    case scriptCompileFailed(details: String)
    case executionFailed(message: String, code: Int?, details: String)
    case timedOut(details: String)
    case notAuthorized(details: String)
    case mailUnavailable(details: String)
    case invalidResult(details: String)
    case internalFailure(details: String)

    var alertTitle: String {
        switch self {
        case .scriptNotFound:
            return "Mail scan script not found"
        case .scriptLoadFailed:
            return "Mail scan script load failed"
        case .scriptCompileFailed:
            return "Mail scan AppleScript compile failed"
        case .executionFailed:
            return "Mail scan AppleScript execution failed"
        case .timedOut:
            return "Mail scan timed out"
        case .notAuthorized:
            return "Mail automation not authorized"
        case .mailUnavailable:
            return "Mail not available"
        case .invalidResult:
            return "Mail scan returned invalid payload"
        case .internalFailure:
            return "Mail scan internal failure"
        }
    }

    var description: String {
        switch self {
        case .scriptNotFound(let path):
            return "Mail scan script not found at: \(path)"
        case .scriptLoadFailed(let path, let message):
            return "Failed to load mail scan script at \(path).\n\(message)"
        case .scriptCompileFailed(let details):
            return details
        case .executionFailed(let message, let code, let details):
            if let code {
                return "Mail scan AppleScript execution failed (\(code)): \(message)\n\(details)"
            }
            return "Mail scan AppleScript execution failed: \(message)\n\(details)"
        case .timedOut(let details):
            return "Mail did not respond in time.\n\(details)"
        case .notAuthorized(let details):
            return "AstroStack is not authorized to access Mail.\n\(details)"
        case .mailUnavailable(let details):
            return "Mail is unavailable or not responding.\n\(details)"
        case .invalidResult(let details):
            return "Mail scan returned invalid payload.\n\(details)"
        case .internalFailure(let details):
            return "Mail scan failed due to an internal error.\n\(details)"
        }
    }

    var isRetryable: Bool {
        switch self {
        case .timedOut, .mailUnavailable:
            return true
        case .executionFailed(_, let code, _):
            return code == -600 || code == -609
        default:
            return false
        }
    }
}

struct MailScanOutcome {
    let payload: Payload
    let wasEmpty: Bool
}

enum MailScanMode {
    case full
    case checkOnly
}

struct MailScanCheckOutcome {
    let messageCount: Int
    let latestMessageDate: Date?
}

private struct ProcessResult {
    let command: String
    let launchPath: String
    let arguments: [String]
    let stdout: String
    let stderr: String
    let exitCode: Int32
    let durationMs: Int
}

private final class MailScanDiagnostics {
    private let logger: Logger
    private let logURL: URL
    private let queue = DispatchQueue(label: "mail-scan.diagnostics")
    private let formatter: DateFormatter
    private(set) var scriptDebugLogPath: String?

    init(logger: Logger) {
        self.logger = logger
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        self.formatter = formatter
        let token = UUID().uuidString
        let stamp = formatter.string(from: Date())
        let dir = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
        self.logURL = dir.appendingPathComponent("arxiv_mail_scan_diag_\(stamp)_\(token).log")
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        log("diagnostics log path: \(logURL.path)")
    }

    var logPath: String { logURL.path }

    func log(_ message: String, console: Bool = true) {
        let stamp = formatter.string(from: Date())
        let line = "[\(stamp)] \(message)"
        append(line + "\n")
        if console {
            logger.info("\(line, privacy: .public)")
        }
    }

    func setScriptDebugLogPath(_ path: String) {
        scriptDebugLogPath = path
        log("script debug log path: \(path)")
    }

    func logBlock(_ title: String, body: String) {
        log("BEGIN \(title)")
        append(body)
        if !body.hasSuffix("\n") { append("\n") }
        log("END \(title)")
    }

    private func append(_ text: String) {
        queue.sync {
            guard let data = text.data(using: .utf8) else { return }
            do {
                let handle = try FileHandle(forWritingTo: logURL)
                try handle.seekToEnd()
                try handle.write(contentsOf: data)
                try handle.close()
            } catch {
                logger.error("mail-scan diagnostics write failed: \(error.localizedDescription, privacy: .public)")
            }
        }
    }
}

final class MailScanService {
    private let log = Logger(subsystem: APP_LOG_SUBSYSTEM, category: "mail-scan")
    private let maxAttempts = 3
    private let baseBackoffSeconds: TimeInterval = 0.7
    private let maxMailLaunchWait: TimeInterval = 6.0

    func scan(mode: MailScanMode = .full,
              since: Date? = nil,
              scanning: AppSettings.Mail.Scanning,
              completion: @escaping (Result<MailScanOutcome, MailScanError>) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            autoreleasepool {
                let result = self.runWithRetries(mode: mode, since: since, scanning: scanning)
                completion(result)
            }
        }
    }

    func checkForNewMessages(since: Date?,
                             scanning: AppSettings.Mail.Scanning,
                             completion: @escaping (Result<MailScanCheckOutcome, MailScanError>) -> Void) {
        scan(mode: .checkOnly, since: since, scanning: scanning) { result in
            switch result {
            case .success(let outcome):
                let payload = outcome.payload
                let check = MailScanCheckOutcome(messageCount: payload.messageCount,
                                                 latestMessageDate: payload.latestMessageDate)
                completion(.success(check))
            case .failure(let error):
                completion(.failure(error))
            }
        }
    }

    private func runWithRetries(mode: MailScanMode,
                                since: Date?,
                                scanning: AppSettings.Mail.Scanning) -> Result<MailScanOutcome, MailScanError> {
        let mailWasRunning = (mailRunningApplication() != nil)
        defer {
            quitMailIfNeeded(initiallyRunning: mailWasRunning)
        }
        let normalizedScanning = scanning.normalized()
        let diagnostics = MailScanDiagnostics(logger: log)
        do {
            let (resourceURL, source) = try loadScriptSource(diagnostics: diagnostics)
            diagnostics.log("script resource path: \(resourceURL.path)")
            diagnostics.logBlock("AppleScript source", body: source)

            let scriptURL = try writeScriptToTemp(source: source, diagnostics: diagnostics)
            let compiledURL = scriptURL.deletingPathExtension().appendingPathExtension("scpt")
            diagnostics.log("compiled script path: \(compiledURL.path)")

            let compileResult = try runProcess(launchPath: "/usr/bin/osacompile",
                                               arguments: ["-o", compiledURL.path, scriptURL.path],
                                               label: "compile",
                                               diagnostics: diagnostics)
            if compileResult.exitCode != 0 {
                let details = compileFailureDetails(result: compileResult,
                                                    scriptURL: scriptURL,
                                                    source: source,
                                                    diagnostics: diagnostics)
                return .failure(.scriptCompileFailed(details: details))
            }

            let scriptDebugLogURL = URL(fileURLWithPath: diagnostics.logPath)
                .deletingPathExtension()
                .appendingPathExtension("script.log")
            FileManager.default.createFile(atPath: scriptDebugLogURL.path, contents: nil)
            diagnostics.setScriptDebugLogPath(scriptDebugLogURL.path)
            let baseEnv = ProcessInfo.processInfo.environment
            var scriptEnv = baseEnv.merging([
                "ARXIV_MAIL_DEBUG": "1",
                "ARXIV_MAIL_PROFILE": "1",
                "ARXIV_MAIL_DEBUG_LOG": scriptDebugLogURL.path
            ]) { _, new in new }
            if let since {
                let epoch = String(format: "%.3f", since.timeIntervalSince1970)
                scriptEnv["ARXIV_MAIL_SINCE_EPOCH"] = epoch
            }
            scriptEnv["ARXIV_MAIL_LOOKBACK_DAYS"] = String(normalizedScanning.lookbackDays)
            scriptEnv["ARXIV_MAIL_KEYWORDS"] = AppSettings.Mail.Scanning.keywordsCSV(from: normalizedScanning.keywords)
            if mode == .checkOnly {
                scriptEnv["ARXIV_MAIL_MODE"] = "check"
            }

            var lastError: MailScanError?
            for attempt in 1...maxAttempts {
                prelaunchMail()
                let execResult = try runProcess(launchPath: "/usr/bin/osascript",
                                                arguments: [compiledURL.path],
                                                label: "execute_attempt_\(attempt)",
                                                diagnostics: diagnostics,
                                                environment: scriptEnv)
                if execResult.exitCode == 0 {
                    let output = execResult.stdout
                    diagnostics.log("execution stdout bytes=\(output.utf8.count)")
                    guard let payload = PayloadDecoder.decode(output) else {
                        let details = """
                        Payload decode failed.
                        stdout:
                        \(output)
                        stderr:
                        \(execResult.stderr)
                        Diagnostics: \(diagnostics.logPath)
                        """
                        return .failure(.invalidResult(details: details))
                    }

                    let outcome = MailScanOutcome(payload: payload, wasEmpty: payload.papers.isEmpty)
                    return .success(outcome)
                }

                let parsed = parseScriptError(stderr: execResult.stderr, stdout: execResult.stdout)
                let details = executionFailureDetails(result: execResult,
                                                      scriptURL: compiledURL,
                                                      diagnostics: diagnostics)
                let error = classifyExecutionError(message: parsed.message, code: parsed.code, details: details)
                lastError = error
                log.error("mail-scan attempt \(attempt) failed: \(error.description)")
                guard error.isRetryable, attempt < maxAttempts else {
                    return .failure(error)
                }
                backoffSleep(attempt)
            }
            return .failure(lastError ?? .internalFailure(details: "Mail scan failed without a captured error. Diagnostics: \(diagnostics.logPath)"))
        } catch let error as MailScanError {
            log.error("mail-scan error: \(error.description)")
            return .failure(error)
        } catch {
            let details = "Unexpected error: \(error.localizedDescription)\nDiagnostics: \(diagnostics.logPath)"
            log.error("mail-scan error: \(details)")
            return .failure(.internalFailure(details: details))
        }
    }

    private func loadScriptSource(diagnostics: MailScanDiagnostics) throws -> (URL, String) {
        guard let url = Bundle.main.url(forResource: "MailScan", withExtension: "applescript") else {
            throw MailScanError.scriptNotFound(path: "(bundle resource MailScan.applescript missing)")
        }
        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            throw MailScanError.scriptLoadFailed(path: url.path, message: "Failed to read script data: \(error.localizedDescription)")
        }
        guard let source = String(data: data, encoding: .utf8) else {
            throw MailScanError.scriptLoadFailed(path: url.path, message: "Script is not valid UTF-8.")
        }
        diagnostics.log("script source bytes=\(data.count)")
        let hasCR = source.contains("\r")
        let hasCRLF = source.contains("\r\n")
        diagnostics.log("script newline check: hasCR=\(hasCR) hasCRLF=\(hasCRLF)")
        return (url, source)
    }

    private func writeScriptToTemp(source: String, diagnostics: MailScanDiagnostics) throws -> URL {
        let token = UUID().uuidString
        let dir = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
        let scriptURL = dir.appendingPathComponent("arxiv_mail_scan_\(token).applescript")
        guard let data = source.data(using: .utf8) else {
            throw MailScanError.internalFailure(details: "Failed to encode script as UTF-8. Diagnostics: \(diagnostics.logPath)")
        }
        do {
            try data.write(to: scriptURL, options: [.atomic])
        } catch {
            throw MailScanError.internalFailure(details: "Failed to write script to \(scriptURL.path): \(error.localizedDescription)\nDiagnostics: \(diagnostics.logPath)")
        }
        let readBack = try Data(contentsOf: scriptURL)
        if readBack != data {
            throw MailScanError.internalFailure(details: "Script write verification failed; file contents differ from source. Path: \(scriptURL.path)\nDiagnostics: \(diagnostics.logPath)")
        }
        diagnostics.log("script written to: \(scriptURL.path)")
        diagnostics.log("script file bytes=\(readBack.count)")
        return scriptURL
    }

    private func runProcess(launchPath: String,
                            arguments: [String],
                            label: String,
                            diagnostics: MailScanDiagnostics,
                            environment: [String: String]? = nil) throws -> ProcessResult {
        let command = commandString(launchPath: launchPath, arguments: arguments)
        diagnostics.log("\(label) command: \(command)")
        let process = Process()
        process.executableURL = URL(fileURLWithPath: launchPath)
        process.arguments = arguments
        if let environment {
            process.environment = environment
        }
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe
        let stdoutHandle = stdoutPipe.fileHandleForReading
        let stderrHandle = stderrPipe.fileHandleForReading
        var stdoutData = Data()
        var stderrData = Data()
        let dataLock = NSLock()
        let stdoutGroup = DispatchGroup()
        let stderrGroup = DispatchGroup()
        stdoutGroup.enter()
        stderrGroup.enter()
        stdoutHandle.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
                stdoutGroup.leave()
                return
            }
            dataLock.lock()
            stdoutData.append(data)
            dataLock.unlock()
        }
        stderrHandle.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
                stderrGroup.leave()
                return
            }
            dataLock.lock()
            stderrData.append(data)
            dataLock.unlock()
        }
        let start = Date()
        do {
            try process.run()
        } catch {
            stdoutHandle.readabilityHandler = nil
            stderrHandle.readabilityHandler = nil
            throw MailScanError.internalFailure(details: "Failed to start process \(command): \(error.localizedDescription)\nDiagnostics: \(diagnostics.logPath)")
        }
        process.waitUntilExit()
        // Ensure we capture any remaining output and stop handlers.
        stdoutHandle.readabilityHandler = nil
        stderrHandle.readabilityHandler = nil
        let tailStdout = stdoutHandle.readDataToEndOfFile()
        let tailStderr = stderrHandle.readDataToEndOfFile()
        if !tailStdout.isEmpty {
            dataLock.lock()
            stdoutData.append(tailStdout)
            dataLock.unlock()
        }
        if !tailStderr.isEmpty {
            dataLock.lock()
            stderrData.append(tailStderr)
            dataLock.unlock()
        }
        _ = stdoutGroup.wait(timeout: .now() + 2.0)
        _ = stderrGroup.wait(timeout: .now() + 2.0)
        let durationMs = Int(Date().timeIntervalSince(start) * 1000)
        let stdout = String(data: stdoutData, encoding: .utf8) ?? String(decoding: stdoutData, as: UTF8.self)
        let stderr = String(data: stderrData, encoding: .utf8) ?? String(decoding: stderrData, as: UTF8.self)
        let result = ProcessResult(command: command,
                                   launchPath: launchPath,
                                   arguments: arguments,
                                   stdout: stdout,
                                   stderr: stderr,
                                   exitCode: process.terminationStatus,
                                   durationMs: durationMs)
        diagnostics.log("\(label) exit=\(result.exitCode) duration_ms=\(durationMs)")
        diagnostics.logBlock("\(label) stdout", body: stdout)
        diagnostics.logBlock("\(label) stderr", body: stderr)
        return result
    }

    private func parseScriptError(stderr: String, stdout: String) -> (message: String, code: Int?) {
        let trimmed = stderr.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            let fallback = stdout.trimmingCharacters(in: .whitespacesAndNewlines)
            return (fallback.isEmpty ? "unknown" : fallback, extractErrorCode(text: fallback))
        }
        return (trimmed, extractErrorCode(text: trimmed))
    }

    private func extractErrorCode(text: String) -> Int? {
        let pattern = #"\((-?\d+)\)"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: []) else { return nil }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        guard let match = regex.firstMatch(in: text, options: [], range: range),
              match.numberOfRanges > 1,
              let codeRange = Range(match.range(at: 1), in: text) else {
            return nil
        }
        return Int(text[codeRange])
    }

    private func classifyExecutionError(message: String, code: Int?, details: String) -> MailScanError {
        if code == -1712 || message.localizedCaseInsensitiveContains("AppleEvent timed out") {
            return .timedOut(details: details)
        }
        if code == -1743 || message.localizedCaseInsensitiveContains("not authorized") {
            return .notAuthorized(details: details)
        }
        if code == -600 || code == -609 || message.localizedCaseInsensitiveContains("application isn't running") {
            return .mailUnavailable(details: details)
        }
        return .executionFailed(message: message, code: code, details: details)
    }

    private func compileFailureDetails(result: ProcessResult,
                                       scriptURL: URL,
                                       source: String,
                                       diagnostics: MailScanDiagnostics) -> String {
        let location = parseCompilerLocation(stderr: result.stderr)
        if let line = location.line {
            let lines = source.split(separator: "\n", omittingEmptySubsequences: false)
            if line > 0, line <= lines.count {
                diagnostics.log("compile error line \(line): \(lines[line - 1])")
            }
        }
        var locText = ""
        if let line = location.line {
            if let column = location.column {
                locText = " line \(line) col \(column)"
            } else {
                locText = " line \(line)"
            }
        }
        return """
        AppleScript compile failed\(locText) (exit \(result.exitCode)).
        Command: \(result.command)
        Script: \(scriptURL.path)
        stdout:
        \(result.stdout)
        stderr:
        \(result.stderr)
        Diagnostics: \(diagnostics.logPath)
        """
    }

    private func executionFailureDetails(result: ProcessResult,
                                         scriptURL: URL,
                                         diagnostics: MailScanDiagnostics) -> String {
        let scriptLogLine: String
        if let path = diagnostics.scriptDebugLogPath {
            scriptLogLine = "Script log: \(path)\n"
        } else {
            scriptLogLine = ""
        }
        return """
        AppleScript execution failed (exit \(result.exitCode)).
        Command: \(result.command)
        Script: \(scriptURL.path)
        stdout:
        \(result.stdout)
        stderr:
        \(result.stderr)
        \(scriptLogLine)Diagnostics: \(diagnostics.logPath)
        """
    }

    private func parseCompilerLocation(stderr: String) -> (line: Int?, column: Int?) {
        let pattern = #":(\d+)(?::(\d+))?:\s*error:"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: []) else { return (nil, nil) }
        let range = NSRange(stderr.startIndex..<stderr.endIndex, in: stderr)
        guard let match = regex.firstMatch(in: stderr, options: [], range: range) else {
            return (nil, nil)
        }
        var line: Int?
        var column: Int?
        if match.numberOfRanges > 1, let lineRange = Range(match.range(at: 1), in: stderr) {
            line = Int(stderr[lineRange])
        }
        if match.numberOfRanges > 2, let colRange = Range(match.range(at: 2), in: stderr) {
            column = Int(stderr[colRange])
        }
        return (line, column)
    }

    private func commandString(launchPath: String, arguments: [String]) -> String {
        let parts = ([launchPath] + arguments).map { shellQuote($0) }
        return parts.joined(separator: " ")
    }

    private func shellQuote(_ value: String) -> String {
        if value.isEmpty { return "''" }
        if value.rangeOfCharacter(from: .whitespacesAndNewlines) == nil &&
            value.rangeOfCharacter(from: CharacterSet(charactersIn: "'\"\\$`")) == nil {
            return value
        }
        let escaped = value.replacingOccurrences(of: "'", with: "'\"'\"'")
        return "'\(escaped)'"
    }

    private func prelaunchMail() {
        let mailID = "com.apple.mail"
        let running = NSRunningApplication.runningApplications(withBundleIdentifier: mailID)
        if running.isEmpty {
            _ = NSWorkspace.shared.launchApplication(withBundleIdentifier: mailID,
                                                     options: [.withoutActivation, .async],
                                                     additionalEventParamDescriptor: nil,
                                                     launchIdentifier: nil)
            waitForMailLaunch()
        }
    }

    private func mailRunningApplication() -> NSRunningApplication? {
        NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.mail").first
    }

    private func quitMailIfNeeded(initiallyRunning: Bool) {
        guard !initiallyRunning else { return }
        guard let app = mailRunningApplication() else { return }
        if app.isActive {
            log.info("mail scan: skip quit because Mail is active")
            return
        }
        _ = app.terminate()
        log.info("mail scan: requested Mail termination")
    }

    private func waitForMailLaunch() {
        let deadline = Date().addingTimeInterval(maxMailLaunchWait)
        while Date() < deadline {
            if !NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.mail").isEmpty {
                return
            }
            Thread.sleep(forTimeInterval: 0.15)
        }
    }

    private func backoffSleep(_ attempt: Int) {
        let delay = min(baseBackoffSeconds * Double(attempt), 3.0)
        Thread.sleep(forTimeInterval: delay)
    }
}
