import QtQuick
import qs.Commons

Rectangle {
  id: root
  property string label: ""
  property bool selected: false
  property bool enabled: true
  signal clicked()
  implicitWidth: title.implicitWidth + Style.space(22)
  implicitHeight: Style.space(36)
  radius: 8
  opacity: enabled ? 1 : 0.45
  color: selected ? Color.accent : (pointer.containsMouse ? Color.bar.background : Color.popups.background)
  border.color: selected ? Color.accent : Color.popups.border
  border.width: 1
  Text { textFormat: Text.PlainText;
    id: title
    anchors.centerIn: parent
    text: root.label
    color: root.selected ? Color.background : Color.popups.text
    font.family: Style.font.family
    font.pixelSize: Style.font.caption
  }
  MouseArea {
    id: pointer
    anchors.fill: parent
    enabled: root.enabled
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: root.clicked()
  }
}
