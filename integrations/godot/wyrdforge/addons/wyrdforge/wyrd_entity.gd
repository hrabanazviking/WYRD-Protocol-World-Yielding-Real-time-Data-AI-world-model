extends Node
## WyrdEntity — attach to any character node to integrate with WYRD.
##
## On _ready(), registers with WyrdBridge and optionally auto-syncs.
## On exit, unregisters from WyrdBridge.
##
## Inspector properties:
##   persona_id: override (auto from parent.name if empty)
##   auto_sync: sync on _ready
##   fact_keys: metadata keys from parent to include as WYRD facts

@export var persona_id: String = ""
@export var auto_sync: bool = true
@export var fact_keys: PackedStringArray = []

signal synced(persona_id: String)
signal context_ready(persona_id: String, context: String)


func _ready() -> void:
	var bridge := get_node_or_null("/root/WyrdBridge")
	if bridge:
		bridge.register_entity(self)
	if auto_sync:
		sync.call_deferred()


func _exit_tree() -> void:
	var bridge := get_node_or_null("/root/WyrdBridge")
	if bridge:
		bridge.unregister_entity(self)


func get_persona_id() -> String:
	if persona_id != "":
		return persona_id
	var parent := get_parent()
	if parent == null:
		return ""
	var bridge := get_node_or_null("/root/WyrdBridge")
	if bridge:
		return bridge.normalize_persona_id(parent.name)
	return parent.name.to_lower().replace(" ", "_").left(64)


func sync() -> void:
	var bridge := get_node_or_null("/root/WyrdBridge")
	if bridge == null:
		push_warning("WyrdEntity: WyrdBridge not found.")
		return
	var pid := get_persona_id()
	if pid == "":
		return
	var parent := get_parent()
	if parent == null:
		return

	await bridge.push_fact(pid, "name", parent.name)

	for key in fact_keys:
		if parent.has_meta(key):
			await bridge.push_fact(pid, key, str(parent.get_meta(key)))

	synced.emit(pid)


func query(user_input: String = "") -> String:
	var bridge := get_node_or_null("/root/WyrdBridge")
	if bridge == null:
		return ""
	var pid := get_persona_id()
	var ctx: String = await bridge.query(pid, user_input)
	context_ready.emit(pid, ctx)
	return ctx
