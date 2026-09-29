import QtQuick
import qs.Commons

Column {
  id: root
  property var catalog: []
  property string theme: "tokyo-night"
  property string selectedIcon: ""
  property string searchPlaceholder: "Search icons…"
  property string assetsPath: ""
  signal chosen(string icon)
  width: parent ? parent.width : 400
  spacing: Style.space(8)

  UiField {
    id: search
    width: parent.width
    placeholderText: root.searchPlaceholder
  }
  Grid {
    id: grid
    width: parent.width
    columns: 6
    spacing: Style.space(6)
    Repeater {
      model: root.catalog.filter(function(item) {
        return item.name.toLowerCase().includes(search.text.toLowerCase())
      })
      delegate: Column {
        id: tile
        required property var modelData
        width: (grid.width - grid.spacing * (grid.columns - 1)) / grid.columns
        spacing: Style.space(2)
        Rectangle {
          width: tile.width
          height: tile.width
          radius: 9
          color: Color.popups.background
          border.width: root.selectedIcon === tile.modelData.id ? 3 : 1
          border.color: root.selectedIcon === tile.modelData.id ? Color.accent : Color.popups.border
          Image {
            anchors.fill: parent
            anchors.margins: 3
            source: "file://" + root.assetsPath + "/" + root.theme + "/" + tile.modelData.id + ".png"
            fillMode: Image.PreserveAspectFit
            asynchronous: true
          }
          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.chosen(tile.modelData.id)
          }
        }
        Text { textFormat: Text.PlainText;
          width: parent.width
          text: tile.modelData.name
          color: Color.muted
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
          horizontalAlignment: Text.AlignHCenter
        }
      }
    }
  }
}
