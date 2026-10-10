import QtQuick
import qs.Commons

Column {
  id: rules
  property var words: ({})
  property var pages: []
  property var bindings: ({})
  property var windows: []
  property int pageIndex: 0
  property bool expanded: false
  readonly property var apps: windows.map(function(item) { return item.appId || "" }).filter(function(app, index, all) { return !!app && all.indexOf(app) === index })
  signal bindRequested(string app, int page)
  spacing: Style.space(8)
  function t(key) { return words[key] || key.split("_").join(" ") }
  ActionChip { label: rules.t("app_rules"); selected: rules.expanded; onClicked: rules.expanded = !rules.expanded }
  Column {
    width: parent.width; spacing: Style.space(8); visible: rules.expanded
    Text { text: rules.t("app_page_hint"); width: parent.width; wrapMode: Text.Wrap; color: Color.muted; font.family: Style.font.family }
    UiSelect {
      width: parent.width
      model: [rules.t("choose_running_app")].concat(rules.apps)
      onActivated: function(index) { if (index) appClass.text = rules.apps[index - 1] }
    }
    Row {
      width: parent.width; spacing: Style.space(8)
      UiField { id: appClass; width: Math.max(Style.space(80), parent.width - bindButton.implicitWidth - Style.space(8)); placeholderText: rules.t("app_class") }
      ActionChip { id: bindButton; label: rules.t("bind_page"); onClicked: { if (appClass.text.trim()) rules.bindRequested(appClass.text.trim(), rules.pageIndex) } }
    }
    Repeater {
      model: Object.keys(rules.bindings)
      ActionChip {
        required property string modelData
        label: modelData + " → " + (rules.pages[rules.bindings[modelData]] || {}).name + " ×"
        onClicked: rules.bindRequested(modelData, -1)
      }
    }
  }
}
