extends Node
## WyrdEntity — attach to any character node to auto-sync with WYRD.
##
## When added to a scene, this component automatically syncs the parent
## node's data to WyrdBridge when the scene loads and when properties change.
##
## Usage: add WyrdEntity as a child of any character node. Set persona_id
## (or leave blank to auto-derive from parent node name).
##
## Inspector properties:
##   persona_id: string (auto from parent.name if empty)
##   auto_sync: bool (sync on _ready)
##   sync_on_property_change: bool (sync when tracked properties change)

## Override to use a custom persona ID. Defaults to normalized parent name.
@export var persona_id: String = ""
## Automatically sync to WYRD when this node enters the scene tree.
@export var auto_sync: bool = true
## Metadata keys on parent node to include as WYRD facts.
@export var fact_keys: PackedStringArray = []

## Emitted when sync completes.
signal synced(persona_id: String)


func _ready() -> void:
	if auto_sync:
		sync.call_deferred()


## Get the effective persona_id (custom or derived from parent name).
func get_persona_id() -> String:
	if persona_id != "":
		return persona_id
	var parent := get_parent()
	if parent == null:
		return ""
	return WyrdBridge.normalize_persona_id(parent.name)


## Sync this entity to WYRD. Reads parent node name + fact_keys metadata.
func sync() -> void:
	if not Engine.has_singleton("WyrdBridge") and not get_node_or_null("/root/WyrdBridge"):
		push_warning("WyrdEntity: WyrdBridge autoload not found.")
		return
	var bridge := get_node("/root/WyrdBridge")
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


## Query WYRD context for this entity. Returns the context string.
func query(user_input: String = "") -> String:
	var bridge := get_node_or_null("/root/WyrdBridge")
	if bridge == null:
		return ""
	return await bridge.query(get_persona_id(), user_input)
