@tool
extends EditorPlugin
## WyrdForge Godot 4 plugin entry point.

const AUTOLOAD_NAME := "WyrdBridge"
const AUTOLOAD_PATH := "res://addons/wyrdforge/wyrd_bridge.gd"

func _enable_plugin() -> void:
	add_autoload_singleton(AUTOLOAD_NAME, AUTOLOAD_PATH)

func _disable_plugin() -> void:
	remove_autoload_singleton(AUTOLOAD_NAME)
