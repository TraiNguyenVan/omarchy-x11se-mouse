import QtQuick
import Quickshell
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
    property string pendingValue: ""
    property bool actionError: false
    property var queuedCommands: []
    property int dpiDraft: -1
    property int pollingDraft: -1
    property int appearance: 0
    property bool editingPresets: false
    readonly property var capabilities: hostWidget ? hostWidget.capabilities : null
    readonly property var defaultPresets: capabilities ? capabilities.defaultPresets : []
    property var presets: []
    property var storedPresets: null
    property var presetDraft: []
    property var savingPresets: []
    property bool presetSaving: false
    readonly property var presetChoices: verifiedDpi.concat(defaultPresets).filter(function(n, i, values) { return values.indexOf(n) === i }).sort(function(a, b) { return a - b })
    readonly property var appearances: capabilities ? capabilities.appearances : []
    readonly property var verifiedDpi: capabilities ? capabilities.verifiedDpi : []
    readonly property var pollingRates: capabilities ? capabilities.pollingRates : []
    onCapabilitiesChanged: if (capabilities) Qt.callLater(initializePresets)
    function initializePresets() {
        if (capabilities) presets = validPresets(storedPresets) ? storedPresets.slice() : defaultPresets.slice()
    }
    readonly property bool connected: hostWidget && hostWidget.deviceState === "connected"
    readonly property var transportLabels: ({wired: "USB wired", receiver: "Wireless receiver"})
    readonly property bool lowBattery: hostWidget && hostWidget.battery >= 0 && hostWidget.battery <= 10
    readonly property var dpiOptions: {
        var values = verifiedDpi.map(function(n) { return { value: String(n), label: formatInteger(n) + " DPI" } })
        if (displayDpi <= 0 || verifiedDpi.indexOf(displayDpi) < 0)
            values.unshift({ value: String(displayDpi), label: displayDpi > 0 ? formatInteger(displayDpi) + " DPI" : "—" })
        return values
    }

    function formatInteger(value) {
        return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ",")
    }

    function validPresets(values) {
        return Array.isArray(values) && values.length === 7 && values.every(function(n, i) {
            return Number.isInteger(n) && presetChoices.indexOf(n) >= 0 && values.indexOf(n) === i
        })
    }
    function presetOptions(index) {
        return presetChoices.filter(function(n) { return n === presetDraft[index] || presetDraft.indexOf(n) < 0 })
            .map(function(n) { return { value: String(n), label: formatInteger(n) + " DPI" } })
    }
    function savePresetDraft() {
        if (presetSaving || !validPresets(presetDraft) || !hostWidget) return
        savingPresets = presetDraft.slice()
        presetSaving = true
        actionError = false
        actionMessage = "Saving presets…"
        presetSaveProcess.command = [hostWidget.cliPath, "save-presets", JSON.stringify(savingPresets)]
        presetSaveProcess.running = true
    }

    Process {
        id: presetLoadProcess
        command: root.hostWidget ? [root.hostWidget.cliPath, "get-presets"] : []
        running: root.hostWidget !== null
        stdout: StdioCollector { id: presetLoadOutput; waitForEnd: true }
        onExited: function(code) {
            try {
                var result = JSON.parse(presetLoadOutput.text)
                if (code !== 0 || result.ok !== true) throw new Error(result.error || "Could not read presets")
                root.storedPresets = result.presets
                root.initializePresets()
            } catch (e) {
                root.actionError = true
                root.actionMessage = "Could not read presets; check your configuration directory"
                console.warn("X11SE: failed to load presets:", e)
            }
        }
    }

    Process {
        id: presetSaveProcess
        stdout: StdioCollector { id: presetSaveOutput; waitForEnd: true }
        onExited: function(code) {
            root.presetSaving = false
            try {
                var result = JSON.parse(presetSaveOutput.text)
                if (code !== 0 || result.ok !== true) throw new Error(result.error || "Could not save presets")
                root.presets = root.savingPresets.slice()
                root.storedPresets = root.presets.slice()
                root.editingPresets = false
                root.actionError = false
                root.actionMessage = "Presets saved"
            } catch (e) {
                root.actionError = true
                root.actionMessage = "Could not save presets; check your configuration directory"
                console.warn("X11SE: failed to save presets:", e)
            }
        }
    }

    function close() { if (hostWidget) hostWidget.close() }
    function refreshStatus() {
        if (!hostWidget || statusProcess.running || commandProcess.running) return
        actionError = false
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
        pendingValue = String(value)
        actionError = false
        actionMessage = "Applying…"
        commandProcess.command = [hostWidget.cliPath, name, String(value)]
        commandProcess.running = true
    }
    function handleCommandResult(line) {
        var result
        try { result = JSON.parse(line) } catch (e) { return }
        if (hostWidget && result.ok === true) hostWidget.applyCacheWarnings(result)
        if (result.ok !== true) {
            actionError = true
            actionMessage = queuedCommands.length ? "Previous setting failed; applying latest…"
                : String(result.error || "The mouse rejected that setting")
            if (!hasQueuedCommand("set-dpi") && pendingAction === "set-dpi") dpiDraft = hostWidget && hostWidget.dpi > 0 ? hostWidget.dpi : -1
            if (!hasQueuedCommand("set-polling") && pendingAction === "set-polling") pollingDraft = hostWidget && hostWidget.polling > 0 ? hostWidget.polling : -1
            return
        }
        actionError = false
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
                actionError = false
                actionMessage = "Status refreshed"
            } else {
                actionError = true
                actionMessage = String(value.error || "Mouse status unavailable")
            }
        } catch (e) {
            actionError = true
            actionMessage = statusError.text.trim() || "Status refresh returned no valid data"
        }
    }

    component PresetButton: Rectangle {
        id: preset
        property string label: ""
        property bool selected: false
        property bool pending: false
        property bool queued: false
        signal clicked()
        implicitHeight: Style.space(36.1)
        color: selected ? Color.accent : Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.04)
        border.width: 1
        border.color: selected || activeFocus ? Color.accent : Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.25)
        opacity: enabled ? 1 : 0.5
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: label
        Keys.onReturnPressed: clicked()
        Keys.onSpacePressed: clicked()
        Text {
            anchors.centerIn: parent
            textFormat: Text.PlainText
            text: preset.label
            color: preset.selected ? Color.background : Color.foreground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Math.round(Style.font.body * 1.1)
            font.bold: preset.selected
        }
        Canvas {
            id: outline
            anchors.fill: parent
            visible: preset.pending || preset.queued
            property bool pending: preset.pending
            property bool queued: preset.queued
            property color stroke: preset.selected ? Color.background : (preset.queued ? "#e5b567" : Color.accent)
            onPendingChanged: requestPaint()
            onQueuedChanged: requestPaint()
            onStrokeChanged: requestPaint()
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.fillStyle = stroke
                var dash = queued ? 1 : 4, step = queued ? 3 : 7, inset = 4
                for (var x = inset; x < width - inset; x += step) {
                    var w = Math.min(dash, width - inset - x)
                    ctx.fillRect(x, inset, w, 1); ctx.fillRect(x, height - inset - 1, w, 1)
                }
                for (var y = inset; y < height - inset; y += step) {
                    var h = Math.min(dash, height - inset - y)
                    ctx.fillRect(inset, y, 1, h); ctx.fillRect(width - inset - 1, y, 1, h)
                }
            }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: preset.clicked()
        }
    }

    PopupCard {
        id: popup
        anchorItem: root.anchorItem
        owner: root
        bar: root.bar
        open: hostWidget ? hostWidget.panelOpen : false
        contentWidth: fittedContentWidth(Style.space(712.5))
        contentHeight: footerLine.y + Style.space(28.5) + verticalContentInset

        Rectangle {
            id: visual
            x: 0; y: 0
            width: Style.space(152.0); height: footerLine.y
            color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.07)
            HoverHandler { id: visualHover }
            Image {
                id: mouseImage
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top
                anchors.topMargin: Style.space(9.5)
                width: Style.space(114.0); height: Style.space(218)
                fillMode: Image.PreserveAspectFit
                source: root.appearances.length ? Qt.resolvedUrl(root.appearances[root.appearance].asset) : ""
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (root.appearances.length) root.appearance = (root.appearance + 1) % root.appearances.length
                }
            }
            Row {
                visible: visualHover.hovered
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: mouseImage.bottom
                anchors.topMargin: Style.space(7.6)
                spacing: Style.space(5.7)
                Repeater {
                    model: root.appearances
                    delegate: Rectangle {
                        required property int index
                        required property var modelData
                        width: Style.space(12.35); height: Style.space(12.35)
                        color: modelData.color
                        border.width: root.appearance === index ? 2 : 1
                        border.color: root.appearance === index ? Color.accent : Color.popups.border
                        Accessible.role: Accessible.Button
                        Accessible.name: modelData.name.replace("-", " ") + " mouse illustration"
                        activeFocusOnTab: true
                        Keys.onReturnPressed: root.appearance = index
                        Keys.onSpacePressed: root.appearance = index
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.appearance = parent.index }
                    }
                }
            }
        }

        Column {
            id: content
            x: visual.width + Style.space(19.0)
            y: 0
            width: popup.contentWidth - popup.padding * 2 - x
            spacing: Style.space(13.5)

            Item {
                width: parent.width; height: Style.space(51.3)
                Column {
                    anchors.left: parent.left; anchors.right: refresh.left
                    anchors.rightMargin: Style.space(7.6)
                    Text {
                        textFormat: Text.PlainText; text: root.capabilities ? root.capabilities.name : "Attack Shark"
                        color: Color.foreground; font.family: root.bar ? root.bar.fontFamily : Style.font.family
                        font.pixelSize: Math.round(Style.font.body * 1.25); font.bold: true
                    }
                    Text {
                        width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText
                        text: root.connected ? (root.transportLabels[hostWidget.transport] || "X11SE mouse")
                                              + " · DPI slot " + (hostWidget.activeStage || "—")
                            : (hostWidget && hostWidget.errorMessage ? hostWidget.errorMessage : "Connecting to mouse…")
                        color: root.connected ? Color.accent : Color.muted
                        font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Math.round(Style.font.body * 1.1)
                    }
                }
                Button {
                    id: refresh
                    anchors.right: parent.right; anchors.top: parent.top
                    text: "Refresh"; bordered: true; focusable: true
                    enabled: !statusProcess.running && !commandProcess.running
                    opacity: enabled ? 1 : 0.5
                    fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                    fontSize: Math.round(Style.font.body * 1.1)
                    onClicked: root.refreshStatus()
                }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.25) }
            }

            Item {
                visible: !root.editingPresets
                width: parent.width; height: Style.space(22.8)
                Text {
                    id: batteryLabel; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    textFormat: Text.PlainText; text: "BATTERY"; color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.72)
                    font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Math.round(Style.font.body * 1.1)
                }
                Text {
                    id: batteryValue; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    textFormat: Text.PlainText; text: hostWidget && hostWidget.battery >= 0 ? hostWidget.battery + "%" : "—"
                    color: root.lowBattery ? Color.urgent : Color.foreground
                    font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Math.round(Style.font.body * 1.25); font.bold: true
                }
                Rectangle {
                    anchors.left: batteryLabel.right; anchors.right: batteryValue.left; anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: Style.space(13.3); anchors.rightMargin: Style.space(13.3)
                    height: Style.space(3.8); color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.12)
                    Rectangle {
                        height: parent.height; width: parent.width * (hostWidget && hostWidget.battery >= 0 ? hostWidget.battery / 100 : 0)
                        color: root.lowBattery ? Color.urgent : Color.accent
                    }
                }
            }

            Column {
                visible: !root.editingPresets
                width: parent.width; spacing: Style.space(5.7)
                Item {
                    width: parent.width; height: dpiSelect.height
                    Rectangle {
                        id: dpiLabel
                        anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                        width: dpiLabelText.implicitWidth + Style.space(8); height: dpiLabelText.implicitHeight + Style.space(6)
                        color: labelMouse.containsMouse || activeFocus ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.12) : "transparent"
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: "Edit DPI presets"
                        function openEditor() { root.presetDraft = root.presets.slice(); root.editingPresets = true }
                        Keys.onReturnPressed: openEditor()
                        Keys.onEnterPressed: openEditor()
                        Keys.onSpacePressed: openEditor()
                        Text {
                            id: dpiLabelText; anchors.centerIn: parent
                            textFormat: Text.PlainText; text: "DPI PRESET"
                            color: labelMouse.containsMouse || dpiLabel.activeFocus ? Color.accent : Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.72)
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Math.round(Style.font.body * 1.1); font.underline: true
                        }
                        MouseArea {
                            id: labelMouse; anchors.fill: parent; hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: dpiLabel.openEditor()
                        }
                    }
                    BoundedDropdown {
                        id: dpiSelect; anchors.right: parent.right
                        boundsItem: visual.parent
                        width: Style.space(133.0)
                        enabled: root.connected; opacity: enabled ? 1 : 0.5
                        value: String(root.displayDpi); options: root.dpiOptions
                        fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                        onChanged: function(value) {
                            var n = Number(value)
                            dpiSelect.value = Qt.binding(function() { return String(root.displayDpi) })
                            if (root.verifiedDpi.indexOf(n) < 0 || n === root.displayDpi) return
                            root.dpiDraft = n; root.runCommand("set-dpi", n)
                        }
                    }
                }
                Row {
                    id: dpiRow; width: parent.width; spacing: Style.space(4.75)
                    Repeater {
                        model: root.presets
                        delegate: PresetButton {
                            required property int modelData
                            width: (dpiRow.width - dpiRow.spacing * 6) / 7
                            label: root.formatInteger(modelData)
                            selected: root.hostWidget && root.hostWidget.dpi === modelData
                            pending: commandProcess.running && root.pendingAction === "set-dpi" && root.pendingValue === String(modelData)
                            queued: root.queuedCommands.some(function(c) { return c.name === "set-dpi" && c.value === String(modelData) })
                            enabled: root.connected
                            onClicked: { if (root.displayDpi !== modelData) { root.dpiDraft = modelData; root.runCommand("set-dpi", modelData) } }
                        }
                    }
                }
            }
            Column {
                visible: !root.editingPresets
                width: parent.width; spacing: Style.space(5.7)
                Item {
                    width: parent.width; height: Style.space(19.0)
                    Text {
                        anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                        textFormat: Text.PlainText; text: "POLLING RATE"; color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.72)
                        font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Math.round(Style.font.body * 1.1)
                    }
                    Text {
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        textFormat: Text.PlainText; text: root.displayPolling > 0 ? root.formatInteger(root.displayPolling) + " Hz" : "—"
                        color: Color.foreground; font.family: root.bar ? root.bar.fontFamily : Style.font.family
                        font.pixelSize: Math.round(Style.font.body * 1.25); font.bold: true
                    }
                }
                Row {
                    id: rateRow; width: parent.width; spacing: Style.space(5.7)
                    Repeater {
                        model: root.pollingRates
                        delegate: PresetButton {
                            required property int modelData
                            width: (rateRow.width - rateRow.spacing * Math.max(0, root.pollingRates.length - 1)) / Math.max(1, root.pollingRates.length)
                            label: root.formatInteger(modelData) + " Hz"
                            selected: root.hostWidget && root.hostWidget.polling === modelData
                            pending: commandProcess.running && root.pendingAction === "set-polling" && root.pendingValue === String(modelData)
                            queued: root.queuedCommands.some(function(c) { return c.name === "set-polling" && c.value === String(modelData) })
                            enabled: root.connected
                            onClicked: { if (root.displayPolling !== modelData) { root.pollingDraft = modelData; root.runCommand("set-polling", modelData) } }
                        }
                    }
                }
            }
            Column {
                visible: root.editingPresets
                width: parent.width; spacing: Style.space(10)
                Text {
                    textFormat: Text.PlainText; text: "Edit DPI presets"
                    color: Color.foreground; font.family: root.bar ? root.bar.fontFamily : Style.font.family
                    font.pixelSize: Math.round(Style.font.body * 1.1); font.bold: true
                }
                Text {
                    width: parent.width; wrapMode: Text.WordWrap; textFormat: Text.PlainText
                    text: "Choose a different value for each preset. Saving won’t change the current DPI."
                    color: Color.muted; font.family: root.bar ? root.bar.fontFamily : Style.font.family
                    font.pixelSize: Style.font.body
                }
                Grid {
                    id: presetGrid
                    width: parent.width; columns: 4; spacing: Style.space(7)
                    Repeater {
                        model: root.presetDraft
                        delegate: Column {
                            required property int index
                            required property int modelData
                            width: (presetGrid.width - presetGrid.spacing * 3) / 4
                            spacing: Style.space(3)
                            Text {
                                textFormat: Text.PlainText; text: "Preset " + (parent.index + 1)
                                color: Color.muted; font.family: root.bar ? root.bar.fontFamily : Style.font.family
                                font.pixelSize: Style.font.caption
                            }
                            BoundedDropdown {
                                id: slotSelect
                                boundsItem: visual.parent
                                width: parent.width
                                enabled: !root.presetSaving
                                value: String(parent.modelData); options: root.presetOptions(parent.index)
                                fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                                onChanged: function(value) {
                                    var next = root.presetDraft.slice()
                                    next[parent.index] = Number(value)
                                    if (root.validPresets(next)) root.presetDraft = next
                                    slotSelect.value = Qt.binding(function() { return String(slotSelect.parent.modelData) })
                                }
                            }
                        }
                    }
                }
                Item {
                    width: parent.width; height: Math.max(resetButton.implicitHeight, cancelButton.implicitHeight, saveButton.implicitHeight)
                    Button {
                        id: resetButton; anchors.left: parent.left
                        text: "Reset defaults"; bordered: true; focusable: true; enabled: !root.presetSaving
                        fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                        onClicked: root.presetDraft = root.defaultPresets.slice()
                    }
                    Row {
                        anchors.right: parent.right; spacing: Style.space(8)
                        Button {
                            id: cancelButton; text: "Cancel"; bordered: true; focusable: true; enabled: !root.presetSaving
                            fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                            onClicked: root.editingPresets = false
                        }
                        Button {
                            id: saveButton; text: "Save"; selected: true; bordered: true; focusable: true; enabled: !root.presetSaving
                            fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                            onClicked: root.savePresetDraft()
                        }
                    }
                }
            }
        }
        Rectangle {
            id: footerLine
            anchors.left: parent.left; anchors.right: parent.right
            y: Math.max(content.implicitHeight + Style.space(12), mouseImage.y + mouseImage.height + Style.space(29)); height: 1; color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.25)
        }
        Rectangle {
            id: statusDot; x: Style.space(3.8); anchors.verticalCenter: statusText.verticalCenter
            width: Style.space(5.7); height: Style.space(5.7)
            color: root.actionError || (root.hostWidget && root.hostWidget.deviceState === "disconnected") ? Color.urgent
                : (root.presetSaving || commandProcess.running || statusProcess.running || root.lowBattery || (root.hostWidget && root.hostWidget.cacheUnavailable) ? "#e5b567" : Color.accent)
        }
        Text {
            id: statusText
            anchors.left: statusDot.right; anchors.right: parent.right
            anchors.leftMargin: Style.space(8.55); y: (footerLine.y + parent.height + popup.padding - height) / 2; height: Style.space(25.65)
            textFormat: Text.PlainText; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
            text: (root.hostWidget && root.hostWidget.cacheUnavailable && !root.actionError && !root.presetSaving && !commandProcess.running && !statusProcess.running)
                ? (root.actionMessage === "Presets saved" || root.actionMessage === "Presets already saved" ? root.actionMessage + " · status cache unavailable" : "Status cache unavailable · check CLI warnings")
                : root.actionMessage || (root.lowBattery ? "Battery low · " + hostWidget.battery + "%" : (root.connected ? "Last known settings" : "Receiver unavailable. Check the receiver and refresh."))
            color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.72); font.family: root.bar ? root.bar.fontFamily : Style.font.family; font.pixelSize: Math.round(Style.font.body * 1.1)
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
            if (code !== 0 && root.actionMessage.indexOf("Refreshing status") === 0) {
                root.actionError = true
                root.actionMessage = statusError.text.trim() || "Status refresh failed"
            }
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
                root.actionError = true
                root.actionMessage = "Command failed: " + commandStderr.text.trim()
                if (!root.hasQueuedCommand("set-dpi") && root.pendingAction === "set-dpi")
                    root.dpiDraft = root.hostWidget && root.hostWidget.dpi > 0 ? root.hostWidget.dpi : -1
                if (!root.hasQueuedCommand("set-polling") && root.pendingAction === "set-polling")
                    root.pollingDraft = root.hostWidget && root.hostWidget.polling > 0 ? root.hostWidget.polling : -1
            }
            root.pendingAction = ""
            root.pendingValue = ""
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
        : (hostWidget && hostWidget.dpi > 0 ? hostWidget.dpi : -1)
    readonly property int displayPolling: pollingDraft > 0
        ? pollingDraft
        : (hostWidget && hostWidget.polling > 0 ? hostWidget.polling : -1)

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
