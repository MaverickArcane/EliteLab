import AppKit
import Foundation

func trace(_ message: String) {
    if CommandLine.arguments.contains("--ui-check") { fputs("UI check: \(message)\n", stderr) }
}

// The private stdin/stdout pipe accepts fixed actions, never shell commands.
func backend(check: Bool) -> Process {
    let root = Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/app")
    let process = Process()
    process.executableURL = root.appendingPathComponent("runtime/bin/python3")
    process.currentDirectoryURL = root
    process.arguments = ["-E", "-s", "-B", "-u", "-m", "elitelab.macos_desktop"] + (check ? ["--check"] : [])
    process.environment = ProcessInfo.processInfo.environment.filter { !$0.key.uppercased().hasPrefix("PYTHON") }
    return process
}

final class Desktop: NSObject, NSApplicationDelegate {
    let process = backend(check: false)
    let input = Pipe()
    let output = Pipe()
    var item: NSStatusItem!
    var login: NSMenuItem!
    var quitting = false
    var receivedError = false
    var checkStep = 0
    let checking = CommandLine.arguments.contains("--ui-check")

    func applicationDidFinishLaunching(_ notification: Notification) {
        trace("application launched")
        NSApp.setActivationPolicy(.accessory)
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "EliteLab"
        let menu = NSMenu()
        for (title, action) in [("Open dashboard", #selector(openDashboard)), ("Open setup", #selector(openSetup)),
                                ("Start at login", #selector(toggleLogin)), ("Quit EliteLab", #selector(quit))] {
            let entry = NSMenuItem(title: title, action: action, keyEquivalent: "")
            entry.target = self
            menu.addItem(entry)
        }
        login = menu.items[2]
        item.menu = menu
        trace("menu created")
        process.standardInput = input
        process.standardOutput = output
        process.terminationHandler = { [weak self] process in
            // terminateLater runs a nested modal loop. A callback queued on the
            // serial main dispatch queue can deadlock when Quit began there.
            RunLoop.main.perform(inModes: [.default, .modalPanel, .eventTracking]) {
                guard let self = self else { return }
                if self.checking { exit(process.terminationStatus == 0 && self.checkStep == 5 ? 0 : 1) }
                if process.terminationStatus != 0 && !self.receivedError {
                    self.alert("EliteLab stopped unexpectedly. Check the desktop log in Library/Application Support/EliteLab/logs.")
                }
                if self.quitting { NSApp.reply(toApplicationShouldTerminate: true) }
                else { NSApp.terminate(nil) }
            }
        }
        do {
            try process.run()
            trace("backend launched")
            // Release the parent's copies so EOF detects either side exiting.
            output.fileHandleForWriting.closeFile()
            input.fileHandleForReading.closeFile()
            DispatchQueue.global().async { [weak self] in
                guard let self = self else { return }
                var pending = Data()
                while true {
                    let data = self.output.fileHandleForReading.availableData
                    if data.isEmpty { break }
                    pending.append(data)
                    while let end = pending.firstIndex(of: 10) {
                        let line = pending.prefix(upTo: end)
                        pending.removeSubrange(...end)
                        if let message = try? JSONSerialization.jsonObject(with: line) as? [String: Any] {
                            DispatchQueue.main.async { self.receive(message) }
                        }
                    }
                }
            }
            if checking {
                DispatchQueue.main.asyncAfter(deadline: .now() + 90) { exit(2) }
            }
        } catch {
            if checking { fputs("\(error)\n", stderr); exit(1) }
            alert("EliteLab could not start: \(error)")
            NSApp.terminate(nil)
        }
    }

    func receive(_ message: [String: Any]) {
        trace("received \(message["event"] ?? "unknown") \(message["action"] ?? "")")
        if let state = message["login"] as? String {
            login.state = state == "enabled" ? .on : .off
        }
        if message["event"] as? String == "error" {
            receivedError = true
            if checking { fputs("\(message)\n", stderr); exit(1) }
            alert(message["message"] as? String ?? "EliteLab could not complete the action.")
        }
        if checking {
            // Drive the actual menu targets against the packaged server on CI.
            let event = message["event"] as? String
            if checkStep == 0 && event == "ready" {
                guard login.state == .off else { exit(1) }
                checkStep = 1; item.menu?.performActionForItem(at: 2)
            } else if event == "result" {
                switch checkStep {
                case 1:
                    guard login.state == .on else { exit(1) }
                    checkStep = 2; item.menu?.performActionForItem(at: 2)
                case 2:
                    guard login.state == .off else { exit(1) }
                    checkStep = 3; item.menu?.performActionForItem(at: 0)
                case 3:
                    checkStep = 4; item.menu?.performActionForItem(at: 1)
                case 4:
                    checkStep = 5; item.menu?.performActionForItem(at: 3)
                default: exit(1)
                }
            }
        }
    }

    func alert(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "EliteLab"
        alert.informativeText = message
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }

    func send(_ action: String) {
        guard process.isRunning else { return }
        do { try input.fileHandleForWriting.write(contentsOf: Data((action + "\n").utf8)) }
        catch { input.fileHandleForWriting.closeFile() }
    }
    @objc func openDashboard() { send("open") }
    @objc func openSetup() { send("setup") }
    @objc func toggleLogin() { send("login") }
    @objc func quit() { NSApp.terminate(nil) }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        send("open")
        return false
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if !process.isRunning { return .terminateNow }
        if !quitting { quitting = true; send("quit") }
        return .terminateLater
    }
}

if CommandLine.arguments.contains("--check") {
    let process = backend(check: true)
    process.standardInput = FileHandle.nullDevice
    do { try process.run(); process.waitUntilExit(); exit(process.terminationStatus) }
    catch { fputs("\(error)\n", stderr); exit(1) }
}
signal(SIGPIPE, SIG_IGN)
trace("creating application")
let app = NSApplication.shared
trace("creating delegate")
let delegate = Desktop()
app.delegate = delegate
trace("entering run loop")
app.run()
