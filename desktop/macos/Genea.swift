import AppKit
import WebKit
import UniformTypeIdentifiers

struct Family: Codable {
    let id: String
    let name: String
}

final class Library {
    let root: URL
    var families: [Family] = []
    private var registry: URL { root.appendingPathComponent("libraries.json") }
    init(root: URL, resources: URL, includeDemos: Bool = true) throws {
        self.root = root
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        if FileManager.default.fileExists(atPath: registry.path) {
            families = try JSONDecoder().decode([Family].self, from: Data(contentsOf: registry))
        }
        for (id, name) in [("demo1", "Demo1 · 红楼梦"), ("demo2", "Demo2 · 百年孤独")] where includeDemos {
            let target = root.appendingPathComponent(id)
            if !FileManager.default.fileExists(atPath: target.path) {
                try FileManager.default.copyItem(at: resources.appendingPathComponent("seeds/\(id)/data"), to: target)
            }
            if !families.contains(where: { $0.id == id }) { families.append(Family(id: id, name: name)) }
        }
        try save()
    }
    func dataURL(_ family: Family) -> URL { root.appendingPathComponent(family.id) }
    func save() throws { try JSONEncoder().encode(families).write(to: registry, options: .atomic) }
    func ensureEditableFamily() throws {
        guard families.isEmpty else { return }
        let family = Family(id: "family-" + UUID().uuidString, name: "我的家谱")
        try FileManager.default.createDirectory(at: dataURL(family), withIntermediateDirectories: true)
        families.append(family)
        try save()
    }
    func importFamily(_ source: URL, name: String = "真实家谱") throws -> Family {
        let fm = FileManager.default
        guard fm.fileExists(atPath: source.appendingPathComponent("workspace.json").path) else {
            throw NSError(domain: "Genea", code: 1, userInfo: [NSLocalizedDescriptionKey: "请选择包含 workspace.json 的家谱数据文件夹。"])
        }
        let family = Family(id: "family-" + UUID().uuidString, name: name)
        let target = dataURL(family)
        try fm.createDirectory(at: target, withIntermediateDirectories: true)
        do {
            for name in ["workspace.json", "settings.json", "photos"] {
                let item = source.appendingPathComponent(name)
                if fm.fileExists(atPath: item.path) { try fm.copyItem(at: item, to: target.appendingPathComponent(name)) }
            }
            families.append(family)
            try save()
        } catch {
            families.removeAll { $0.id == family.id }
            try? fm.removeItem(at: target)
            throw error
        }
        return family
    }
}

final class Backend {
    private let process = Process()
    private let input = Pipe()
    private let output = Pipe()
    private var buffer = Data()
    private var didBecomeReady = false
    private var stopped = false
    init(resources: URL, data: URL, experimentalDefault: Bool) {
        let backend = resources.appendingPathComponent("backend")
        process.executableURL = resources.appendingPathComponent("Python/bin/python3.12")
        // Isolated Python does not add a script directory to sys.path; insert the bundled backend explicitly.
        let boot = "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name=\"__main__\")"
        process.arguments = ["-I", "-B", "-u", "-c", boot, backend.path,
            backend.appendingPathComponent("backend_bootstrap.py").path, "--data-dir", data.path] +
            (experimentalDefault ? ["--experimental-default"] : [])
        process.standardInput = input
        process.standardOutput = output
        process.standardError = FileHandle.standardError
    }
    func start(ready: @escaping (URL) -> Void, failed: @escaping () -> Void) throws {
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            guard let self = self else { return }
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            self.buffer.append(data)
            guard !self.didBecomeReady, let newline = self.buffer.firstIndex(of: 10) else { return }
            let line = self.buffer.prefix(upTo: newline)
            guard let info = try? JSONSerialization.jsonObject(with: line) as? [String: Any],
                  info["status"] as? String == "ready", let port = info["port"] as? Int,
                  let url = URL(string: "http://127.0.0.1:\(port)/") else {
                DispatchQueue.main.async { failed() }; return
            }
            self.didBecomeReady = true
            DispatchQueue.main.async { ready(url) }
        }
        process.terminationHandler = { [weak self] _ in
            guard let self = self, !self.stopped else { return }
            DispatchQueue.main.async { failed() }
        }
        try process.run()
    }
    func stop() {
        guard !stopped else { return }
        stopped = true
        output.fileHandleForReading.readabilityHandler = nil
        try? input.fileHandleForWriting.close()
        DispatchQueue.global().asyncAfter(deadline: .now() + 3) { [self] in
            if process.isRunning { process.terminate() }
        }
    }
    deinit { stop() }
}

final class FamilyWindow: NSObject, NSWindowDelegate, WKUIDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    unowned let owner: AppDelegate
    let family: Family
    let window: NSWindow
    let webView: WKWebView
    let backend: Backend
    private let chooser = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 230, height: 28), pullsDown: false)
    private var permittedClose = false
    private var checkingClose = false
    private var backendFailed = false
    private var serviceURL: URL?
    private var smokeAttempts = 0
    init(owner: AppDelegate, family: Family) throws {
        self.owner = owner; self.family = family
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        let bridge = try String(contentsOf: owner.resources.appendingPathComponent("bridge.js"), encoding: .utf8)
        let preferencesURL = owner.library.dataURL(family).appendingPathComponent("preferences.json")
        let preferences = (try? Data(contentsOf: preferencesURL)) ?? Data("{}".utf8)
        let restored = (try? JSONSerialization.jsonObject(with: preferences)) as? [String: String] ?? [:]
        let restoredJSON = String(data: try JSONSerialization.data(withJSONObject: restored), encoding: .utf8)!
        let familyJSON = String(data: try JSONSerialization.data(withJSONObject: family.name, options: .fragmentsAllowed), encoding: .utf8)!
        config.userContentController.addUserScript(WKUserScript(source: "window.geneaPreferenceSnapshot = " + restoredJSON + ";", injectionTime: .atDocumentStart, forMainFrameOnly: true))
        config.userContentController.addUserScript(WKUserScript(source: "window.geneaFamilyName = " + familyJSON + ";", injectionTime: .atDocumentStart, forMainFrameOnly: true))
        config.userContentController.addUserScript(WKUserScript(source: bridge, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        webView = WKWebView(frame: .zero, configuration: config)
        backend = Backend(resources: owner.resources, data: owner.library.dataURL(family), experimentalDefault: family.id == "demo2")
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 940),
            styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        super.init()
        window.title = "Genea — " + family.name
        // The page header names the family; the title bar only carries the window controls and chooser.
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.isReleasedWhenClosed = false
        window.tabbingMode = .disallowed
        window.minSize = NSSize(width: 900, height: 640)
        window.contentView = webView
        window.delegate = self
        window.center()
        webView.uiDelegate = self; webView.navigationDelegate = self
        config.userContentController.add(self, name: "geneaClipboard")
        config.userContentController.add(self, name: "geneaPreferences")
        config.userContentController.add(self, name: "geneaAppearance")
        // Start from the remembered appearance so the bar never flashes the wrong tone; otherwise follow the system.
        let savedTheme = restored["genea-appearance"] ?? (restored["genea-theme"] == "mocha" ? "mocha" : nil)
        applyAppearance(dark: savedTheme.map { $0 == "mocha" })
        chooser.target = self; chooser.action = #selector(selectFamily(_:))
        refreshChooser()
        let accessory = NSTitlebarAccessoryViewController()
        accessory.view = chooser; accessory.layoutAttribute = .right
        window.addTitlebarAccessoryViewController(accessory)
        try backend.start(ready: { [weak self] url in
            self?.serviceURL = url
            self?.webView.load(URLRequest(url: url))
        }, failed: { [weak self] in self?.showBackendFailure() })
    }
    /// The page chrome (`--chrome` in styles.css), resolved for the window's current appearance.
    private static let chromeColor = NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(srgbRed: 0x1b / 255.0, green: 0x18 / 255.0, blue: 0x14 / 255.0, alpha: 1)
            : NSColor(srgbRed: 0xfa / 255.0, green: 0xf8 / 255.0, blue: 0xf3 / 255.0, alpha: 1)
    }
    /// An explicit page theme pins the window appearance; without one the window (and the page's
    /// prefers-color-scheme) keeps following the system, and the dynamic chrome color follows along.
    func applyAppearance(dark: Bool?) {
        if let dark = dark { window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua) } else { window.appearance = nil }
        window.backgroundColor = Self.chromeColor
        webView.underPageBackgroundColor = Self.chromeColor
    }
    func refreshChooser() {
        chooser.removeAllItems()
        chooser.addItems(withTitles: owner.library.families.map(\.name))
        chooser.selectItem(at: owner.library.families.firstIndex(where: { $0.id == family.id }) ?? 0)
    }
    @objc private func selectFamily(_ sender: NSPopUpButton) {
        let selected = owner.library.families[sender.indexOfSelectedItem]
        refreshChooser()
        if selected.id == family.id { return }
        confirmClose { [weak self] allowed in
            guard let self = self, allowed else { return }
            self.owner.open(selected)
            self.permittedClose = true
            self.window.close()
        }
    }
    private func showBackendFailure() {
        guard !backendFailed else { return }
        backendFailed = true
        if owner.smokeDirectory != nil { owner.smokeFailed = true; owner.finishSmoke(self, result: ["backendFailed": true]); return }
        let alert = NSAlert()
        alert.messageText = "本机家谱服务无法启动或已停止"
        alert.informativeText = "请关闭此窗口后重新打开。家谱保存在本机资料库中。"
        alert.beginSheetModal(for: window)
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if permittedClose { return true }
        guard !checkingClose else { return false }
        checkingClose = true
        confirmClose { [weak self] allowed in
            guard let self = self else { return }
            self.checkingClose = false
            if allowed { self.permittedClose = true; self.window.close() }
        }
        return false
    }
    func confirmClose(_ completion: @escaping (Bool) -> Void) {
        if webView.url == nil { completion(true); return }
        webView.evaluateJavaScript("window.geneaDesktop.closeStatus()") { [weak self] value, error in
            guard let self = self else { completion(false); return }
            guard let status = value as? [String: Any], error == nil else {
                self.askDiscard(message: "无法确认页面的保存状态。", completion: completion); return
            }
            if status["busy"] as? Bool == true {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { self.confirmClose(completion) }
            } else if status["dirty"] as? Bool == true {
                self.askDiscard(message: "当前档案或关系有未保存的修改。关闭后这些修改将会丢失。", completion: completion)
            } else { completion(true) }
        }
    }
    private func askDiscard(message: String, completion: @escaping (Bool) -> Void) {
        let alert = NSAlert(); alert.messageText = "放弃未保存的修改？"; alert.informativeText = message
        alert.addButton(withTitle: "继续编辑"); alert.addButton(withTitle: "放弃修改")
        alert.beginSheetModal(for: window) { response in completion(response == .alertSecondButtonReturn) }
    }
    func windowWillClose(_ notification: Notification) {
        backend.stop()
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "geneaClipboard")
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "geneaPreferences")
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "geneaAppearance")
        owner.windows.removeValue(forKey: family.id)
        owner.lastFamilyID = family.id
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, message.webView === webView,
              let body = message.body as? [String: Any] else { return }
        if message.name == "geneaAppearance" {
            guard let theme = body["theme"] as? String else { return }
            applyAppearance(dark: body["explicit"] as? Bool == true ? theme == "mocha" : nil)
            return
        }
        if message.name == "geneaPreferences" {
            guard let key = body["key"] as? String, ["genea-appearance", "genea-theme"].contains(key),
                  let value = body["value"] as? String else { return }
            let file = owner.library.dataURL(family).appendingPathComponent("preferences.json")
            var values = ((try? Data(contentsOf: file)).flatMap { try? JSONSerialization.jsonObject(with: $0) }) as? [String: String] ?? [:]
            values[key] = value
            do { try JSONSerialization.data(withJSONObject: values).write(to: file, options: .atomic) }
            catch {
                let alert = NSAlert(); alert.messageText = "外观偏好未能保存"; alert.informativeText = "本次外观已更新，请检查家谱资料库是否可写。"
                alert.beginSheetModal(for: window)
            }
            return
        }
        guard message.name == "geneaClipboard", let id = body["id"] as? Int, let text = body["text"] as? String else { return }
        NSPasteboard.general.clearContents()
        let copied = NSPasteboard.general.setString(text, forType: .string)
        webView.evaluateJavaScript("window.geneaDesktop.completeClipboard(\(id), \(copied ? "true" : "false"))")
    }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false; panel.canChooseFiles = true
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.allowedContentTypes = [.jpeg, .png, .gif, .webP]
        panel.beginSheetModal(for: window) { response in completionHandler(response == .OK ? panel.urls : nil) }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let url = navigationAction.request.url
        if url?.host == "127.0.0.1" && url?.port == serviceURL?.port { decisionHandler(.allow) }
        else { decisionHandler(.cancel) }
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if owner.smokeDirectory != nil { smokeReview() }
    }
    private func smokeReview() {
        webView.evaluateJavaScript("window.geneaDesktop.reviewStatus()") { [weak self] value, _ in
            guard let self = self else { return }
            let status = value as? [String: Any] ?? [:]
            self.smokeAttempts += 1
            if status["loaded"] as? Bool != true || (status["photoElements"] as? Int ?? 0) != (status["loadedPhotos"] as? Int ?? 0) {
                if self.smokeAttempts < 100 {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { self.smokeReview() }; return
                }
                self.owner.smokeFailed = true
            }
            if self.owner.reviewOnly {
                var result = status
                result["titlePresent"] = !self.window.title.isEmpty
                result["familySelectorItems"] = self.chooser.numberOfItems
                result["demoFamiliesVisible"] = self.owner.library.families.filter { $0.id == "demo1" || $0.id == "demo2" }.count
                self.owner.finishSmoke(self, result: result)
                return
            }
            self.webView.evaluateJavaScript("navigator.clipboard.writeText(\"Genea desktop clipboard smoke test\")")
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                var result = status
                result["clipboard"] = NSPasteboard.general.string(forType: .string) == "Genea desktop clipboard smoke test"
                if result["clipboard"] as? Bool != true { self.owner.smokeFailed = true }
                result["titlePresent"] = !self.window.title.isEmpty
                result["familySelectorItems"] = self.chooser.numberOfItems
                let config = WKSnapshotConfiguration()
                self.webView.takeSnapshot(with: config) { image, error in
                    if let image = image, let tiff = image.tiffRepresentation,
                       let bitmap = NSBitmapImageRep(data: tiff), let png = bitmap.representation(using: .png, properties: [:]),
                       let directory = self.owner.smokeDirectory {
                        do { try png.write(to: directory.appendingPathComponent(self.family.id + ".png")) }
                        catch { self.owner.smokeFailed = true }
                    } else { self.owner.smokeFailed = true }
                    result["snapshot"] = image != nil && error == nil
                    self.owner.finishSmoke(self, result: result)
                }
            }
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    let resources = Bundle.main.resourceURL!
    var library: Library!
    var windows: [String: FamilyWindow] = [:]
    /// The family whose window closed last; reopening the app brings it back.
    var lastFamilyID: String?
    var smokeDirectory: URL?
    var smokeFailed = false
    private var smokeResults: [String: [String: Any]] = [:]
    private var quitInProgress = false
    private var familyMenu = NSMenu(title: "家谱")
    private let arguments = CommandLine.arguments
    var reviewOnly: Bool { arguments.contains("--review-only") }
    func option(_ name: String) -> String? {
        guard let index = arguments.firstIndex(of: name), index + 1 < arguments.count else { return nil }
        return arguments[index + 1]
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let includeDemos = Bundle.main.object(forInfoDictionaryKey: "GeneaIncludeDemoSeeds") as? Bool ?? true
            let configuredLibrary = Bundle.main.object(forInfoDictionaryKey: "GeneaDefaultLibraryDirectory") as? String
            let root = (option("--library-dir") ?? configuredLibrary).map {
                URL(fileURLWithPath: ($0 as NSString).expandingTildeInPath, isDirectory: true)
            } ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Genea")
            library = try Library(root: root, resources: resources, includeDemos: includeDemos)
            if let path = option("--import-family") {
                _ = try library.importFamily(URL(fileURLWithPath: path, isDirectory: true),
                                             name: includeDemos ? "真实家谱" : "我的家谱")
            }
            // Import the requested real family before adding the no-demo empty fallback.
            try library.ensureEditableFamily()
            if let path = option("--smoke-test") {
                smokeDirectory = URL(fileURLWithPath: path, isDirectory: true)
                try FileManager.default.createDirectory(at: smokeDirectory!, withIntermediateDirectories: true)
            }
            buildMenus()
            if arguments.contains("--open-all") || smokeDirectory != nil { openAll() }
            else { open(library.families.first(where: { $0.id.hasPrefix("family-") }) ?? library.families[0]) }
            NSApp.activate(ignoringOtherApps: true)
        } catch { failStartup(error) }
    }
    private func failStartup(_ error: Error) {
        if smokeDirectory != nil { fputs("Genea smoke startup failed\n", stderr); exit(1) }
        let alert = NSAlert(); alert.messageText = "Genea 无法打开资料库"; alert.informativeText = error.localizedDescription
        alert.runModal(); NSApp.terminate(nil)
    }
    func open(_ family: Family) {
        if let existing = windows[family.id] { existing.window.makeKeyAndOrderFront(nil); return }
        do {
            let controller = try FamilyWindow(owner: self, family: family)
            windows[family.id] = controller
            controller.window.makeKeyAndOrderFront(nil)
        } catch { failStartup(error) }
    }
    @objc func openAll() { for family in library.families { open(family) } }
    @objc func openFamily(_ sender: NSMenuItem) {
        if let id = sender.representedObject as? String, let family = library.families.first(where: { $0.id == id }) { open(family) }
    }
    @objc func importFamily() {
        let panel = NSOpenPanel(); panel.title = "导入家谱副本"; panel.message = "选择包含 workspace.json 的数据文件夹。原始文件保持不变。"
        panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let source = panel.url else { return }
        do {
            let family = try library.importFamily(source)
            refreshFamilyMenu()
            for controller in windows.values { controller.refreshChooser() }
            open(family)
        } catch {
            let alert = NSAlert(); alert.messageText = "未能导入家谱"; alert.informativeText = error.localizedDescription; alert.runModal()
        }
    }
    private func item(_ title: String, _ action: Selector?, _ key: String = "", target: AnyObject? = nil) -> NSMenuItem {
        let result = NSMenuItem(title: title, action: action, keyEquivalent: key); result.target = target; return result
    }
    private func buildMenus() {
        let main = NSMenu()
        let appMenu = NSMenu(title: "Genea")
        appMenu.addItem(item("关于 Genea", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), target: NSApp))
        appMenu.addItem(.separator())
        appMenu.addItem(item("隐藏 Genea", #selector(NSApplication.hide(_:)), "h", target: NSApp))
        appMenu.addItem(item("退出 Genea", #selector(NSApplication.terminate(_:)), "q", target: NSApp))
        let appItem = NSMenuItem(title: "Genea", action: nil, keyEquivalent: ""); appItem.submenu = appMenu; main.addItem(appItem)
        let familyItem = NSMenuItem(title: "家谱", action: nil, keyEquivalent: ""); familyItem.submenu = familyMenu; main.addItem(familyItem)
        refreshFamilyMenu()
        let edit = NSMenu(title: "编辑")
        edit.addItem(item("剪切", #selector(NSText.cut(_:)), "x")); edit.addItem(item("复制", #selector(NSText.copy(_:)), "c"))
        edit.addItem(item("粘贴", #selector(NSText.paste(_:)), "v")); edit.addItem(item("全选", #selector(NSText.selectAll(_:)), "a"))
        let editItem = NSMenuItem(title: "编辑", action: nil, keyEquivalent: ""); editItem.submenu = edit; main.addItem(editItem)
        let windowMenu = NSMenu(title: "窗口")
        windowMenu.addItem(item("关闭窗口", #selector(NSWindow.performClose(_:)), "w"))
        windowMenu.addItem(item("最小化", #selector(NSWindow.performMiniaturize(_:)), "m"))
        let fullScreen = item("进入全屏幕", #selector(NSWindow.toggleFullScreen(_:)), "f")
        fullScreen.keyEquivalentModifierMask = [.control, .command]
        windowMenu.addItem(fullScreen)
        windowMenu.addItem(item("全部前置", #selector(NSApplication.arrangeInFront(_:)), target: NSApp))
        let windowItem = NSMenuItem(title: "窗口", action: nil, keyEquivalent: ""); windowItem.submenu = windowMenu; main.addItem(windowItem)
        NSApp.mainMenu = main; NSApp.windowsMenu = windowMenu
    }
    private func refreshFamilyMenu() {
        familyMenu.removeAllItems()
        familyMenu.addItem(item("导入家谱副本…", #selector(importFamily), "o", target: self))
        familyMenu.addItem(item("打开所有家谱窗口", #selector(openAll), target: self))
        familyMenu.addItem(.separator())
        for family in library.families {
            let entry = item(family.name, #selector(openFamily(_:)), target: self); entry.representedObject = family.id
            familyMenu.addItem(entry)
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    /// Clicking the Dock icon or opening the app again with no family window restores the last family.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        guard !flag, library != nil, !library.families.isEmpty else { return true }
        if let existing = windows.values.first {
            existing.window.makeKeyAndOrderFront(nil)
            return false
        }
        let family = library.families.first(where: { $0.id == lastFamilyID }) ??
            library.families.first(where: { $0.id.hasPrefix("family-") }) ?? library.families[0]
        open(family)
        return false
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitInProgress { return .terminateCancel }
        quitInProgress = true
        let controllers = Array(windows.values)
        func check(_ index: Int) {
            if index == controllers.count {
                for controller in controllers { controller.backend.stop() }
                sender.reply(toApplicationShouldTerminate: true); return
            }
            controllers[index].confirmClose { allowed in
                if allowed { check(index + 1) }
                else { self.quitInProgress = false; sender.reply(toApplicationShouldTerminate: false) }
            }
        }
        DispatchQueue.main.async { check(0) }
        return .terminateLater
    }
    func applicationWillTerminate(_ notification: Notification) { for controller in windows.values { controller.backend.stop() } }
    func finishSmoke(_ controller: FamilyWindow, result: [String: Any]) {
        guard smokeResults[controller.family.id] == nil else { return }
        smokeResults[controller.family.id] = result
        guard smokeResults.count == library.families.count, let directory = smokeDirectory else { return }
        do {
            let data = try JSONSerialization.data(withJSONObject: smokeResults, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: directory.appendingPathComponent("smoke.json"))
        } catch { smokeFailed = true }
        for controller in windows.values { controller.backend.stop() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { exit(self.smokeFailed ? 1 : 0) }
    }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.setActivationPolicy(.regular)
application.delegate = delegate
application.run()
