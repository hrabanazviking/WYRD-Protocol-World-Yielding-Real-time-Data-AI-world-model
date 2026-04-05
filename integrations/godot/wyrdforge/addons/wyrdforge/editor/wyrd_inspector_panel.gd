@tool
extends Control
## WyrdForge Inspector Panel — editor dock showing live WYRD world state.
##
## Added to DOCK_SLOT_RIGHT_BR by wyrd_plugin.gd when plugin is enabled.
## Shows: registered entities, server status, last query result.

var _status_label: Label
var _entity_list: ItemList
var _refresh_btn: Button
var _query_output: TextEdit


func _ready() -> void:
	_build_ui()
	set_process(false)


func _build_ui() -> void:
	var vbox := VBoxContainer.new()
	vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_child(vbox)

	var title := Label.new()
	title.text = "ᚹ WyrdForge"
	title.add_theme_color_override("font_color", Color(0.83, 0.66, 0.33))
	vbox.add_child(title)

	_status_label = Label.new()
	_status_label.text = "Status: unknown"
	_status_label.add_theme_font_size_override("font_size", 11)
	vbox.add_child(_status_label)

	_refresh_btn = Button.new()
	_refresh_btn.text = "Refresh"
	_refresh_btn.pressed.connect(_on_refresh)
	vbox.add_child(_refresh_btn)

	var entity_label := Label.new()
	entity_label.text = "Registered Entities:"
	entity_label.add_theme_font_size_override("font_size", 11)
	vbox.add_child(entity_label)

	_entity_list = ItemList.new()
	_entity_list.custom_minimum_size = Vector2(0, 80)
	vbox.add_child(_entity_list)

	var output_label := Label.new()
	output_label.text = "Last Query:"
	output_label.add_theme_font_size_override("font_size", 11)
	vbox.add_child(output_label)

	_query_output = TextEdit.new()
	_query_output.editable = false
	_query_output.custom_minimum_size = Vector2(0, 120)
	_query_output.add_theme_font_size_override("font_size", 10)
	vbox.add_child(_query_output)


func _on_refresh() -> void:
	_refresh_btn.disabled = true
	_status_label.text = "Status: checking…"
	_entity_list.clear()

	var bridge := get_node_or_null("/root/WyrdBridge")
	if bridge == null:
		_status_label.text = "Status: WyrdBridge not loaded"
		_refresh_btn.disabled = false
		return

	var healthy: bool = await bridge.health_check()
	_status_label.text = "Status: %s" % ("online" if healthy else "offline")

	var personas := bridge.get_registered_personas()
	for pid in personas:
		_entity_list.add_item(pid)

	_refresh_btn.disabled = false
