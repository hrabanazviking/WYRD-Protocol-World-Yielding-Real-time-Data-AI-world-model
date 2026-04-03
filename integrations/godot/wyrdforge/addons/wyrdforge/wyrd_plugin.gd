@tool
extends EditorPlugin
## WyrdForge Godot 4 integration plugin.
##
## Registers WyrdBridge autoload, adds WyrdEntity inspector dock,
## and provides editor menu for server health check.

const AUTOLOAD_NAME := "WyrdBridge"
const AUTOLOAD_PATH := "res://addons/wyrdforge/wyrd_bridge.gd"

var _inspector_panel: Control
var _inspector_plugin: EditorInspectorPlugin


func _enable_plugin() -> void:
	add_autoload_singleton(AUTOLOAD_NAME, AUTOLOAD_PATH)
	_add_inspector_panel()
	print("WyrdForge: plugin enabled. WyrdBridge autoload registered.")


func _disable_plugin() -> void:
	remove_autoload_singleton(AUTOLOAD_NAME)
	_remove_inspector_panel()
	print("WyrdForge: plugin disabled.")


func _add_inspector_panel() -> void:
	# Load and add the WYRD inspector dock to the editor
	var panel_script := load("res://addons/wyrdforge/editor/wyrd_inspector_panel.gd")
	if panel_script:
		_inspector_panel = panel_script.new()
		add_control_to_dock(DOCK_SLOT_RIGHT_BR, _inspector_panel)


func _remove_inspector_panel() -> void:
	if _inspector_panel:
		remove_control_from_docks(_inspector_panel)
		_inspector_panel.queue_free()
		_inspector_panel = null
