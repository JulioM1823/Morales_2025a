import AppKit
import os

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let log = Logger(subsystem: APP_LOG_SUBSYSTEM, category: "app")
    private let mailScanService = MailScanService()
    private let publicationCache = PublicationCacheStore.shared
    private let launchMode: AppLaunchMode
    private var controller: PickerWindowController?
    private var scanInFlight = false
    private var refreshTimer: Timer?
    private var scheduleObservers: [(NotificationCenter, Any)] = []
    private var quitKeyMonitor: Any?

    private enum ScanContext {
        case initialNoCache
        case refresh
    }

    init(launchMode: AppLaunchMode = .normal) {
        self.launchMode = launchMode
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        logLaunchFlagsIfNeeded()

        let app = NSApplication.shared
        if launchMode == .normal {
            app.setActivationPolicy(.regular)
            applyAppDisplayNameIfNeeded()
        }

        if launchMode == .backgroundRefresh {
            performBackgroundRefresh()
            return
        }

        SettingsMenuIntegrator.installIfNeeded()
        AppSettingsBootstrap.applyAppAppearanceOverrideIfNeeded(app)
        AppearanceManager.shared.startIfNeeded()

        let controller = PickerWindowController()
        self.controller = controller
        controller.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)

        DispatchQueue.main.async { [weak controller] in
            guard let window = controller?.window else { return }

            // Ensure we become key/front deterministically; `showWindow` can leave the window visible
            // but not key in some launch contexts.
            NSApp.activate(ignoringOtherApps: true)

            if window.screen == nil, let screen = NSScreen.screens.first {
                let targetSize = NSSize(width: min(1700, screen.visibleFrame.width),
                                        height: min(900, screen.visibleFrame.height))
                let origin = NSPoint(x: screen.visibleFrame.midX - (targetSize.width / 2),
                                     y: screen.visibleFrame.midY - (targetSize.height / 2))
                window.setFrame(NSRect(origin: origin, size: targetSize), display: true)
            }

            window.makeKeyAndOrderFront(nil)
            window.contentView?.layoutSubtreeIfNeeded()
            window.displayIfNeeded()
        }

        let cachedPayload = publicationCache.cachedPayload()
        if let cachedPayload {
            controller.ingestPayload(cachedPayload, allowEmpty: true)
        }
        let hasCachedData = (cachedPayload?.papers.isEmpty == false)
        controller.setLoadingVisible(!hasCachedData, message: hasCachedData ? nil : "Scanning Mail…")

        scheduleDailyRefresh()
        installScheduleObservers()
        DispatchQueue.global(qos: .utility).async {
            LaunchAgentManager.ensureInstalled()
        }

        DispatchQueue.main.async { [weak self] in
            self?.performInitialRefresh(hasCachedData: hasCachedData)
        }

        installQuitShortcutMonitor()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let quitKeyMonitor {
            NSEvent.removeMonitor(quitKeyMonitor)
            self.quitKeyMonitor = nil
        }
        refreshTimer?.invalidate()
        refreshTimer = nil
        for (center, token) in scheduleObservers {
            center.removeObserver(token)
        }
        scheduleObservers.removeAll()
    }

    private func performInitialRefresh(hasCachedData: Bool) {
        let state = publicationCache.cachedState()
        let now = Date()
        let lastScheduled = DenverRefreshSchedule.lastRefreshDate(before: now)
        let lastSuccess = state.lastRefreshSuccessAt ?? state.lastScanAt
        let missedSchedule = (lastSuccess == nil) || ((lastSuccess ?? .distantPast) < lastScheduled)

        if !hasCachedData {
            let scanning = AppSettingsStore.shared.current.resolvedMailScanning
            startMailScan(since: nil, scanning: scanning, context: .initialNoCache, showLoading: true)
            return
        }

        if missedSchedule {
            checkForNewMailAndScan(reason: "missed_schedule", context: .refresh, showLoading: false)
        }
    }

    private func checkForNewMailAndScan(reason: String,
                                        context: ScanContext,
                                        showLoading: Bool,
                                        completion: (() -> Void)? = nil) {
        guard !scanInFlight else { return }
        let scanning = AppSettingsStore.shared.current.resolvedMailScanning
        let state = publicationCache.cachedState()
        publicationCache.recordRefreshAttempt(Date())

        guard let since = state.lastScanMessageDate else {
            startMailScan(since: nil, scanning: scanning, context: context, showLoading: showLoading, completion: completion)
            return
        }

        mailScanService.checkForNewMessages(since: since, scanning: scanning) { [weak self] result in
            DispatchQueue.main.async {
                guard let self else { return }
                switch result {
                case .success(let check):
                    if check.messageCount > 0 {
                        self.startMailScan(since: since,
                                           scanning: scanning,
                                           context: context,
                                           showLoading: showLoading,
                                           completion: completion)
                    } else {
                        self.log.info("mail refresh skipped: no new messages (reason=\(reason, privacy: .public))")
                        _ = self.publicationCache.refreshWithoutScan(at: Date())
                        let payload = self.publicationCache.cachedPayload()
                        self.controller?.ingestPayload(payload, allowEmpty: true)
                        completion?()
                    }
                case .failure(let error):
                    self.log.error("mail refresh check failed: \(error.description, privacy: .public)")
                    completion?()
                }
            }
        }
    }

    private func startMailScan(since: Date?,
                               scanning: AppSettings.Mail.Scanning,
                               context: ScanContext,
                               showLoading: Bool,
                               completion: (() -> Void)? = nil) {
        guard !scanInFlight else { return }
        scanInFlight = true
        if showLoading {
            controller?.setLoadingVisible(true, message: "Scanning Mail…")
        }
        publicationCache.recordRefreshAttempt(Date())
        mailScanService.scan(mode: .full, since: since, scanning: scanning) { [weak self] result in
            DispatchQueue.main.async {
                guard let self else { return }
                self.scanInFlight = false
                self.handleScanResult(result, context: context)
                completion?()
            }
        }
    }

    private func installQuitShortcutMonitor() {
        guard quitKeyMonitor == nil else { return }
        quitKeyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self else { return event }
            let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            if flags.contains(.command) {
                let chars = event.charactersIgnoringModifiers?.lowercased() ?? ""
                if chars == "q" {
                    NSApp.terminate(self)
                    return nil
                }
            }
            return event
        }
    }

    private func performBackgroundRefresh() {
        let now = Date()
        if !shouldRunScheduledRefresh(now: now) {
            NSApp.terminate(nil)
            return
        }
        checkForNewMailAndScan(reason: "launchd",
                               context: .refresh,
                               showLoading: false) {
            NSApp.terminate(nil)
        }
    }

    private func shouldRunScheduledRefresh(now: Date) -> Bool {
        let state = publicationCache.cachedState()
        let lastScheduled = DenverRefreshSchedule.lastRefreshDate(before: now)
        let lastSuccess = state.lastRefreshSuccessAt ?? state.lastScanAt
        return (lastSuccess == nil) || ((lastSuccess ?? .distantPast) < lastScheduled)
    }

    private func scheduleDailyRefresh() {
        refreshTimer?.invalidate()
        let next = DenverRefreshSchedule.nextRefreshDate(after: Date())
        let interval = max(5.0, next.timeIntervalSinceNow)
        refreshTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: false) { [weak self] _ in
            self?.handleScheduledRefresh()
        }
    }

    private func handleScheduledRefresh() {
        checkForNewMailAndScan(reason: "scheduled", context: .refresh, showLoading: false)
        scheduleDailyRefresh()
    }

    private func installScheduleObservers() {
        guard scheduleObservers.isEmpty else { return }
        let center = NotificationCenter.default
        let workspaceCenter = NSWorkspace.shared.notificationCenter
        scheduleObservers.append((center,
                                  center.addObserver(forName: .NSSystemClockDidChange,
                                                     object: nil,
                                                     queue: .main) { [weak self] _ in
            self?.scheduleDailyRefresh()
        }))
        scheduleObservers.append((center,
                                  center.addObserver(forName: .NSSystemTimeZoneDidChange,
                                                     object: nil,
                                                     queue: .main) { [weak self] _ in
            self?.scheduleDailyRefresh()
        }))
        scheduleObservers.append((workspaceCenter,
                                  workspaceCenter.addObserver(forName: NSWorkspace.didWakeNotification,
                                                              object: nil,
                                                              queue: .main) { [weak self] _ in
            self?.scheduleDailyRefresh()
        }))
    }

    private func handleScanResult(_ result: Result<MailScanOutcome, MailScanError>,
                                  context: ScanContext) {
        controller?.setLoadingVisible(false, message: nil)
        switch result {
        case .success(let outcome):
            _ = publicationCache.applyScanPayload(outcome.payload,
                                                  scannedAt: Date(),
                                                  lookbackDays: PublicationCacheStore.defaultLookbackDays)
            let updatedPayload = publicationCache.cachedPayload()
            controller?.ingestPayload(updatedPayload, allowEmpty: true)
            if context == .initialNoCache,
               launchMode == .normal,
               (updatedPayload?.papers.isEmpty ?? true) {
                presentAlert(title: "No arXiv emails found",
                             message: "No publications matched your filters.")
            }
        case .failure(let error):
            log.error("mail scan failed: \(error.description)")
            if context == .initialNoCache, launchMode == .normal {
                presentAlert(title: error.alertTitle,
                             message: error.description)
            }
        }
    }

    private func presentAlert(title: String, message: String) {
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = title
        alert.informativeText = message
        if let window = controller?.window {
            alert.beginSheetModal(for: window, completionHandler: nil)
        } else {
            alert.runModal()
        }
    }
}
