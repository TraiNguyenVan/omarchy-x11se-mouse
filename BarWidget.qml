import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "trai.x11se-mouse"

    property bool panelOpen: false
    property int battery: -1
    property int dpi: -1
    property int polling: -1
    property int activeStage: 0
    property var stages: []
    property string chargeState: ""
    property string transport: ""
    property string deviceState: "Searching for X11SE mouse"
    property string errorMessage: ""
    property var panelItem: null
    property var capabilities: null
    property bool cacheUnavailable: false

    readonly property string cliPath: Qt.resolvedUrl("bin/x11se-mouse").toString().replace("file://", "")
    readonly property string barLabel: {
        if (deviceState !== "connected") return "-- · -- DPI · -- Hz"
        var batteryText = battery >= 0 ? battery + "%" : "--"
        var dpiText = dpi > 0 ? dpi + " DPI" : "-- DPI"
        var rateText = polling > 0 ? polling + " Hz" : "-- Hz"
        return batteryText + " · " + dpiText + " · " + rateText
    }

    readonly property string statusTooltip: {
        if (deviceState !== "connected") return errorMessage || "X11SE mouse not detected"
        var batteryText = battery >= 0
            ? battery + "%" + (chargeState ? " (" + chargeState + ")" : "")
            : "waiting for report"
        var dpiText = dpi > 0 ? dpi + " DPI" : "waiting for report"
        var rateText = polling > 0 ? polling + " Hz" : "waiting for report"
        return "Battery: " + batteryText + "\nDPI: " + dpiText + "\nPolling: " + rateText
    }

    function applyCacheWarnings(value) {
        if (!value || typeof value !== "object") return
        cacheUnavailable = Array.isArray(value.warnings) && value.warnings.some(function(w) {
            return w && w.code === "cache_unavailable"
        })
    }

    function applyStatus(value) {
        if (!value || typeof value !== "object") return
        applyCacheWarnings(value)
        if (value.connected !== true) {
            deviceState = "disconnected"
            battery = -1
            dpi = -1
            polling = -1
            activeStage = 0
            stages = []
            chargeState = ""
            errorMessage = String(value.error || "Mouse receiver not detected")
            return
        }
        deviceState = "connected"
        if (value.transport && value.transport !== transport) {
            battery = -1
            chargeState = ""
            transport = value.transport
        }
        errorMessage = String(value.error || "")
        if (Number.isInteger(value.battery) && value.battery >= 0 && value.battery <= 100) battery = value.battery
        if (Number.isInteger(value.dpi) && value.dpi > 0 && (!capabilities || value.dpi <= capabilities.maxReportedDpi)) dpi = value.dpi
        if (Number.isInteger(value.polling) && (!capabilities || capabilities.pollingRates.indexOf(value.polling) >= 0)) polling = value.polling
        if (Number.isInteger(value.stage) && value.stage >= 1 && (!capabilities || value.stage <= capabilities.stageCount)) activeStage = value.stage
        if (Array.isArray(value.stages) && (!capabilities || value.stages.length === capabilities.stageCount)) stages = value.stages
        if (["charging", "charged", "normal"].indexOf(value.chargeState) >= 0) chargeState = value.chargeState
    }

    function injectPanel() {
        var target = panelLoader.item
        if (!target) return
        panelItem = target
        if ("bar" in target) target.bar = root.bar
        if ("anchorItem" in target) target.anchorItem = button
        if ("hostWidget" in target) target.hostWidget = root
    }

    function open() { panelOpen = true }
    function close() { panelOpen = false }
    function togglePanel() { panelOpen = !panelOpen }

    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    Loader {
        id: panelLoader
        active: true
        source: Qt.resolvedUrl("Panel.qml")
        visible: false
        onLoaded: {
            root.injectPanel()
            Qt.callLater(root.injectPanel)
        }
    }

    IpcHandler {
        target: "trai.x11se-mouse"
        function open(): void { root.open() }
        function close(): void { root.close() }
        function toggle(): void { root.togglePanel() }
        function refresh(): void { if (!statusProcess.running) statusProcess.running = true }
    }

    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: "󰍽"
        tooltipText: root.statusTooltip
        onPressed: function(mouseButton) {
            if (mouseButton === Qt.LeftButton) root.togglePanel()
        }
    }

    Process {
        id: capabilityProcess
        running: true
        command: [root.cliPath, "capabilities"]
        stdout: StdioCollector { id: capabilityOutput; waitForEnd: true }
        onExited: function(code) {
            if (code !== 0) { console.warn("X11SE: could not load model capabilities"); return }
            try { root.capabilities = JSON.parse(capabilityOutput.text) }
            catch (e) { console.warn("X11SE: invalid model capabilities", e) }
        }
    }

    Process {
        id: statusProcess
        running: true
        command: [root.cliPath, "watch"]
        stdout: SplitParser {
            onRead: function(line) {
                try { root.applyStatus(JSON.parse(String(line))) } catch (e) {}
            }
        }
        onExited: restartProcess.restart()
    }

    Timer {
        id: restartProcess
        interval: 30000
        onTriggered: if (!statusProcess.running) statusProcess.running = true
    }
}
