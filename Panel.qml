import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui

Item {
    id: root
    property var bar: null
    property var anchorItem: null
    property var hostWidget: null
    property string actionMessage: ""
    property string pendingAction: ""
    property var queuedCommands: []
    property int dpiDraft: -1
    property int pollingDraft: -1

    function formatInteger(value) {
        return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ",")
    }

    function close() { if (hostWidget) hostWidget.close() }
    function refreshStatus() {
        if (!hostWidget || statusProcess.running || commandProcess.running) return
        actionMessage = "Refreshing status…"
        statusProcess.command = [hostWidget.cliPath, "status", "--json"]
        statusProcess.running = true
    }
    function hasQueuedCommand(name) {
        return queuedCommands.some(function(command) { return command.name === name })
    }
    function runCommand(name, value) {
        if (!hostWidget) return
        if (commandProcess.running) {
            var nextQueue = queuedCommands.slice()
            var queuedIndex = nextQueue.findIndex(function(command) { return command.name === name })
            var queuedCommand = { name: name, value: String(value) }
            if (queuedIndex >= 0) nextQueue[queuedIndex] = queuedCommand
            else nextQueue.push(queuedCommand)
            queuedCommands = nextQueue
            actionMessage = "Applying latest setting…"
            return
        }
        startCommand(name, value)
    }
    function startCommand(name, value) {
        pendingAction = name
        actionMessage = "Applying…"
        commandProcess.command = [hostWidget.cliPath, name, String(value)]
        commandProcess.running = true
    }
    function handleCommandResult(line) {
        var result
        try { result = JSON.parse(line) } catch (e) { return }
        if (result.ok !== true) {
            actionMessage = queuedCommands.length ? "Previous setting failed; applying latest…"
                : String(result.error || "The mouse rejected that setting")
            if (!hasQueuedCommand("set-dpi") && pendingAction === "set-dpi") dpiDraft = hostWidget && hostWidget.dpi > 0 ? hostWidget.dpi : -1
            if (!hasQueuedCommand("set-polling") && pendingAction === "set-polling") pollingDraft = hostWidget && hostWidget.polling > 0 ? hostWidget.polling : -1
            return
        }
        actionMessage = queuedCommands.length ? "Applying latest setting…" : String(result.message || "Setting updated")
        if (hostWidget && pendingAction === "set-dpi" && Number.isInteger(result.dpi)) {
            if (!hasQueuedCommand("set-dpi")) dpiDraft = result.dpi
            hostWidget.dpi = result.dpi
            if (Number.isInteger(result.stage)) hostWidget.activeStage = result.stage
            if (Array.isArray(result.stages)) hostWidget.stages = result.stages
        }
        if (hostWidget && pendingAction === "set-polling" && Number.isInteger(result.polling)) {
            if (!hasQueuedCommand("set-polling")) pollingDraft = result.polling
            hostWidget.polling = result.polling
        }
    }
    function handleRefreshResult(output) {
        try {
            var value = JSON.parse(String(output || "").trim())
            if (value.connected === true && hostWidget) {
                hostWidget.applyStatus(value)
                if (Number.isInteger(value.dpi) && !commandProcess.running) dpiDraft = value.dpi
                if (Number.isInteger(value.polling) && !commandProcess.running) pollingDraft = value.polling
                actionMessage = "Status refreshed"
            } else {
                actionMessage = String(value.error || "Mouse status unavailable")
            }
        } catch (e) {
            actionMessage = statusError.text.trim() || "Status refresh returned no valid data"
        }
    }

    PopupCard {
        id: popup
        anchorItem: root.anchorItem
        owner: root
        bar: root.bar
        open: hostWidget ? hostWidget.panelOpen : false
        contentWidth: Style.space(456)
        contentHeight: contentColumn.implicitHeight + verticalContentInset

        Column {
            id: contentColumn
            width: popup.contentWidth - popup.padding * 2
            spacing: Style.space(14)

            Row {
                width: parent.width
                spacing: Style.space(10)
                Text {
                    textFormat: Text.PlainText
                    text: "󰍽"
                    color: Color.accent
                    font.family: root.bar ? root.bar.fontFamily : Style.font.family
                    font.pixelSize: Style.font.icon
                    anchors.verticalCenter: parent.verticalCenter
                }
                Column {
                    spacing: Style.space(2)
                    width: parent.width - 110
                    Text {
                        textFormat: Text.PlainText
                        text: "Attack Shark X11SE"
                        color: Color.foreground
                        font.family: root.bar ? root.bar.fontFamily : Style.font.family
                        font.pixelSize: Style.font.body
                        font.bold: true
                    }
                    Text {
                        textFormat: Text.PlainText
                        text: hostWidget && hostWidget.deviceState === "connected"
                            ? "Wireless receiver · Stage " + (hostWidget.activeStage || "—")
                            : (hostWidget ? hostWidget.errorMessage : "Connecting to receiver")
                        color: hostWidget && hostWidget.deviceState === "connected" ? Color.accent : Color.muted
                        font.family: root.bar ? root.bar.fontFamily : Style.font.family
                        font.pixelSize: Style.font.caption
                        elide: Text.ElideRight
                        width: parent.width
                    }
                }
                Button {
                    text: "Refresh"
                    bordered: true
                    foreground: root.bar ? root.bar.foreground : Color.foreground
                    background: root.bar ? root.bar.background : Color.background
                    fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                    fontSize: Style.font.caption
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: root.refreshStatus()
                }
            }

            Rectangle { width: parent.width; height: Style.space(1); color: Color.popups.border }

            Row {
                width: parent.width
                spacing: Style.space(8)

                Rectangle {
                    width: (parent.width - parent.spacing * 2) / 3
                    height: Style.space(70)
                    radius: Style.cornerRadius
                    color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.045)
                    border.width: 1
                    border.color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.09)
                    Column {
                        anchors.fill: parent
                        anchors.margins: Style.space(10)
                        spacing: Style.space(3)
                        Text {
                            textFormat: Text.PlainText
                            text: "BATTERY"
                            color: Color.muted
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Style.font.caption
                            font.bold: true
                        }
                        Text {
                            textFormat: Text.PlainText
                            text: hostWidget && hostWidget.battery >= 0 ? hostWidget.battery + "%" : "—"
                            color: Color.foreground
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Style.font.subtitle
                            font.bold: true
                        }
                    }
                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.margins: Style.space(10)
                        height: Style.space(3)
                        radius: height / 2
                        color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.12)
                        Rectangle {
                            width: parent.width * (hostWidget && hostWidget.battery >= 0 ? hostWidget.battery / 100 : 0)
                            height: parent.height
                            radius: parent.radius
                            color: Color.accent
                        }
                    }
                }

                Rectangle {
                    width: (parent.width - parent.spacing * 2) / 3
                    height: Style.space(70)
                    radius: Style.cornerRadius
                    color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.045)
                    border.width: 1
                    border.color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.09)
                    Column {
                        anchors.fill: parent
                        anchors.margins: Style.space(10)
                        spacing: Style.space(3)
                        Text {
                            textFormat: Text.PlainText
                            text: "ACTIVE DPI"
                            color: Color.muted
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Style.font.caption
                            font.bold: true
                        }
                        Text {
                            textFormat: Text.PlainText
                            text: root.displayDpi > 0 ? root.formatInteger(root.displayDpi) : "—"
                            color: Color.foreground
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Style.font.subtitle
                            font.bold: true
                        }
                    }
                }

                Rectangle {
                    width: (parent.width - parent.spacing * 2) / 3
                    height: Style.space(70)
                    radius: Style.cornerRadius
                    color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.045)
                    border.width: 1
                    border.color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.09)
                    Column {
                        anchors.fill: parent
                        anchors.margins: Style.space(10)
                        spacing: Style.space(3)
                        Text {
                            textFormat: Text.PlainText
                            text: "POLLING"
                            color: Color.muted
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Style.font.caption
                            font.bold: true
                        }
                        Text {
                            textFormat: Text.PlainText
                            text: root.displayPolling > 0
                                ? (root.displayPolling === 1000 ? "1,000" : root.displayPolling.toString()) + " Hz" : "—"
                            color: Color.foreground
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Style.font.subtitle
                            font.bold: true
                        }
                    }
                }
            }

            Column {
                width: parent.width
                spacing: Style.space(7)
                Text {
                    textFormat: Text.PlainText
                    text: "DPI PRESET"
                    color: Color.muted
                    font.family: root.bar ? root.bar.fontFamily : Style.font.family
                    font.pixelSize: Style.font.caption
                    font.bold: true
                }
                ButtonGroup {
                    width: parent.width
                    options: [
                        { value: "400", label: "400" },
                        { value: "800", label: "800" },
                        { value: "1200", label: "1,200" },
                        { value: "1600", label: "1,600" }
                    ]
                    value: String(root.displayDpi)
                    foreground: root.bar ? root.bar.foreground : Color.foreground
                    background: root.bar ? root.bar.background : Color.background
                    fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                    fontSize: Style.font.bodySmall
                    onChanged: function(value) {
                        root.dpiDraft = Number(value)
                        root.runCommand("set-dpi", Number(value))
                    }
                }
                ButtonGroup {
                    width: parent.width
                    options: [
                        { value: "2400", label: "2,400" },
                        { value: "3200", label: "3,200" },
                        { value: "6400", label: "6,400" }
                    ]
                    value: String(root.displayDpi)
                    foreground: root.bar ? root.bar.foreground : Color.foreground
                    background: root.bar ? root.bar.background : Color.background
                    fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                    fontSize: Style.font.bodySmall
                    onChanged: function(value) {
                        root.dpiDraft = Number(value)
                        root.runCommand("set-dpi", Number(value))
                    }
                }
            }

            Column {
                width: parent.width
                spacing: Style.space(7)
                Text {
                    textFormat: Text.PlainText
                    text: "POLLING RATE"
                    color: Color.muted
                    font.family: root.bar ? root.bar.fontFamily : Style.font.family
                    font.pixelSize: Style.font.caption
                    font.bold: true
                }
                ButtonGroup {
                    width: parent.width
                    options: [
                        { value: "125", label: "125 Hz" },
                        { value: "250", label: "250 Hz" },
                        { value: "500", label: "500 Hz" },
                        { value: "1000", label: "1,000 Hz" }
                    ]
                    value: String(root.displayPolling)
                    foreground: root.bar ? root.bar.foreground : Color.foreground
                    background: root.bar ? root.bar.background : Color.background
                    fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                    fontSize: Style.font.bodySmall
                    onChanged: function(value) {
                        root.pollingDraft = Number(value)
                        root.runCommand("set-polling", Number(value))
                    }
                }
            }

            Text {
                visible: root.actionMessage !== ""
                textFormat: Text.PlainText
                text: root.actionMessage
                color: root.actionMessage.indexOf("failed") >= 0 || root.actionMessage.indexOf("rejected") >= 0
                    ? Color.urgent : Color.muted
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
                wrapMode: Text.Wrap
                width: parent.width
                topPadding: Style.space(2)
            }
        }
    }

    Process {
        id: statusProcess
        running: false
        stdout: StdioCollector {
            id: statusOutput
            waitForEnd: true
            onStreamFinished: root.handleRefreshResult(statusOutput.text)
        }
        stderr: StdioCollector { id: statusError; waitForEnd: true }
        onExited: function(code) {
            if (code !== 0 && root.actionMessage.indexOf("Refreshing status") === 0)
                root.actionMessage = statusError.text.trim() || "Status refresh failed"
        }
    }

    Process {
        id: commandProcess
        running: false
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: root.handleCommandResult(text)
        }
        stderr: StdioCollector { id: commandStderr; waitForEnd: true }
        onExited: function(code) {
            if (code !== 0 && root.actionMessage === "Applying…") {
                root.actionMessage = "Command failed: " + commandStderr.text.trim()
                if (!root.hasQueuedCommand("set-dpi") && root.pendingAction === "set-dpi")
                    root.dpiDraft = root.hostWidget && root.hostWidget.dpi > 0 ? root.hostWidget.dpi : -1
                if (!root.hasQueuedCommand("set-polling") && root.pendingAction === "set-polling")
                    root.pollingDraft = root.hostWidget && root.hostWidget.polling > 0 ? root.hostWidget.polling : -1
            }
            root.pendingAction = ""
            if (root.queuedCommands.length > 0) {
                var nextQueue = root.queuedCommands.slice()
                var nextCommand = nextQueue.shift()
                root.queuedCommands = nextQueue
                root.startCommand(nextCommand.name, nextCommand.value)
            }
        }
    }

    readonly property int displayDpi: dpiDraft > 0
        ? dpiDraft
        : (hostWidget && hostWidget.dpi > 0 ? hostWidget.dpi : 800)
    readonly property int displayPolling: pollingDraft > 0
        ? pollingDraft
        : (hostWidget && hostWidget.polling > 0 ? hostWidget.polling : 500)

    Connections {
        target: root.hostWidget
        function onDpiChanged() {
            if (!commandProcess.running)
                root.dpiDraft = root.hostWidget && root.hostWidget.dpi > 0 ? root.hostWidget.dpi : -1
        }
        function onPollingChanged() {
            if (!commandProcess.running)
                root.pollingDraft = root.hostWidget && root.hostWidget.polling > 0 ? root.hostWidget.polling : -1
        }
    }
}
