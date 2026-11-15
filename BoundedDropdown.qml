import QtQuick
import QtQuick.Controls as Controls
import qs.Commons

Item {
    id: root
    property string value: ""
    property var options: []
    property string fontFamily: Style.font.family
    property Item boundsItem: null
    signal changed(string value)

    implicitHeight: Style.spacing.controlHeight
    activeFocusOnTab: true
    Accessible.role: Accessible.ComboBox
    Accessible.name: currentLabel()

    function currentLabel() {
        for (var i = 0; i < options.length; i++)
            if (String(options[i].value) === value) return String(options[i].label)
        return value
    }
    function toggle() {
        if (menu.opened) { menu.close(); return }
        if (!boundsItem) return
        var position = root.mapToItem(boundsItem, 0, 0)
        var gap = Style.spacing.xxs
        var edge = Style.space(8)
        var above = Math.max(0, position.y - gap - edge)
        var below = Math.max(0, boundsItem.height - position.y - root.height - gap - edge)
        var desired = Math.min(root.options.length * Style.spacing.popupRowHeight + 2,
                               Style.spacing.popupRowHeight * 4 + 2)
        var openBelow = below >= desired || below >= above
        menu.height = Math.min(desired, openBelow ? below : above)
        menu.y = openBelow ? root.height + gap : -menu.height - gap
        menu.open()
    }
    Keys.onReturnPressed: toggle()
    Keys.onEnterPressed: toggle()
    Keys.onSpacePressed: toggle()
    Keys.onDownPressed: toggle()

    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.04)
        border.width: 1
        border.color: root.activeFocus || hover.containsMouse ? Color.accent : Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.25)
        Text {
            anchors.left: parent.left; anchors.right: arrow.left; anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: Style.spacing.controlPaddingX; anchors.rightMargin: Style.spacing.md
            textFormat: Text.PlainText; text: root.currentLabel(); elide: Text.ElideRight
            color: Color.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.body
        }
        Text {
            id: arrow
            anchors.right: parent.right; anchors.rightMargin: Style.spacing.controlGap; anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText; text: "󰅀"; color: Color.muted
            font.family: root.fontFamily; font.pixelSize: Style.font.body
        }
        MouseArea {
            id: hover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: { root.forceActiveFocus(); root.toggle() }
        }
    }

    Controls.Popup {
        id: menu
        parent: root
        width: root.width
        x: 0
        margins: 0
        padding: 1
        focus: true
        closePolicy: Controls.Popup.CloseOnPressOutsideParent | Controls.Popup.CloseOnEscape
        background: Rectangle { color: Color.popups.background; border.width: 1; border.color: Color.popups.border }
        onOpened: {
            list.currentIndex = Math.max(0, root.options.findIndex(function(option) { return String(option.value) === root.value }))
            list.positionViewAtIndex(list.currentIndex, ListView.Beginning)
            list.forceActiveFocus()
        }
        contentItem: ListView {
            id: list
            clip: true; model: root.options; boundsBehavior: Flickable.StopAtBounds
            Controls.ScrollBar.vertical: Controls.ScrollBar { policy: list.contentHeight > list.height ? Controls.ScrollBar.AsNeeded : Controls.ScrollBar.AlwaysOff }
            function selectCurrent() {
                if (currentIndex < 0 || currentIndex >= root.options.length) return
                var selected = String(root.options[currentIndex].value)
                menu.close()
                root.changed(selected)
            }
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Down || event.text === "j") { currentIndex = Math.min(root.options.length - 1, currentIndex + 1); event.accepted = true }
                else if (event.key === Qt.Key_Up || event.text === "k") { currentIndex = Math.max(0, currentIndex - 1); event.accepted = true }
                else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) { selectCurrent(); event.accepted = true }
                else if (event.key === Qt.Key_Escape) { menu.close(); event.accepted = true }
            }
            delegate: Rectangle {
                required property var modelData
                required property int index
                readonly property bool selected: String(modelData.value) === root.value
                width: list.width; height: Style.spacing.popupRowHeight
                color: selected ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.16)
                    : index === list.currentIndex ? Style.hoverFillFor(Color.foreground, Color.accent) : "transparent"
                Text {
                    anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: Style.spacing.controlPaddingX; anchors.rightMargin: Style.spacing.controlPaddingX
                    textFormat: Text.PlainText; text: String(parent.modelData.label); elide: Text.ElideRight
                    color: parent.selected ? Color.accent : Color.foreground
                    font.family: root.fontFamily; font.pixelSize: Style.font.body; font.bold: parent.selected
                }
                MouseArea {
                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onPositionChanged: list.currentIndex = parent.index
                    onClicked: { list.currentIndex = parent.index; list.selectCurrent() }
                }
            }
        }
    }
}
