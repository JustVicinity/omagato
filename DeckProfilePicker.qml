import QtQuick
import qs.Commons

Column {
  id: picker
  property var words: ({})
  property var decks: []
  property var profiles: ({})
  property string selectedDevice: ""
  property bool resetPending: false
  readonly property var choices: decks.concat(Object.keys(profiles).filter(function(id) {
    return !picker.decks.some(function(deck) { return deck.profile === id })
  }).map(function(id) { return { profile: id, name: picker.t("saved_deck") + " · " + id.slice(-6) } }))
  signal deviceSelected(string device)
  signal resetRequested(string device)
  spacing: Style.space(8)
  function t(key) { return words[key] || key.split("_").join(" ") }
  onSelectedDeviceChanged: resetPending = false
  UiSelect {
    width: parent.width
    model: [picker.t("shared_template")].concat(picker.choices.map(function(item, index) { return item.name + " · " + (index + 1) }))
    currentIndex: Math.max(0, picker.choices.findIndex(function(item) { return item.profile === picker.selectedDevice }) + 1)
    onActivated: function(index) { picker.deviceSelected(index ? picker.choices[index - 1].profile : "") }
  }
  Text { width: parent.width; wrapMode: Text.Wrap; color: Color.muted; font.family: Style.font.family; text: picker.t("device_profile_hint") }
  ActionChip {
    visible: !!picker.profiles[picker.selectedDevice] && !picker.resetPending
    label: picker.t("reset_device")
    onClicked: picker.resetPending = true
  }
  Column {
    visible: picker.resetPending; width: parent.width; spacing: Style.space(6)
    Text { width: parent.width; wrapMode: Text.Wrap; color: Color.foreground; font.family: Style.font.family; text: picker.t("reset_device_confirm") }
    Row {
      spacing: Style.space(8)
      ActionChip { label: picker.t("no"); onClicked: picker.resetPending = false }
      ActionChip { label: picker.t("yes"); onClicked: { picker.resetRequested(picker.selectedDevice); picker.resetPending = false } }
    }
  }
}
