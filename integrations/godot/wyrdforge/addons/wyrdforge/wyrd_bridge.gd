extends Node
## WyrdBridge — Godot 4 game integration autoload singleton.
##
## Full game integration version (Phase 11A). Extends the SDK wyrd_bridge.gd
## with game-specific features:
##   - Scene load hook (syncs scene entities on load)
##   - World event bus (maps Godot signals → WYRD observations)
##   - Location tracking (syncs Yggdrasil node on scene change)
##   - Entity registry (tracks all WyrdEntity nodes in the scene)
##
## Usage:
##   # Query context for a character
##   var ctx = await WyrdBridge.query("sigrid", "What is happening?")
##
##   # Write an observation when something notable happens
##   await WyrdBridge.push_observation("Battle begins", "The orcs attacked at dawn.")
##
##   # Register current scene as a Yggdrasil location
##   await WyrdBridge.sync_scene_location()

## Emitted when a query completes.
signal query_completed(persona_id: String, context_text: String)
## Emitted when a query fails.
signal query_failed(persona_id: String, error: String)
## Emitted when an event push completes.
signal event_pushed(event_type: String, ok: bool)
## Emitted when scene sync completes.
signal scene_synced(scene_name: String, entity_count: int)

@export var host: String = "localhost"
@export var port: int = 8765
@export var enabled: bool = true
## When true, automatically sync scene entities on scene change.
@export var auto_sync_on_scene_change: bool = true
## Scene name → Yggdrasil location_id mapping. Set via Inspector.
@export var scene_location_map: Dictionary = {}

var _base_url: String
## Registered WyrdEntity nodes in the current scene.
var _entity_registry: Array[Node] = []


func _ready() -> void:
	_base_url = "http://%s:%d" % [host, port]
	get_tree().node_added.connect(_on_node_added)
	get_tree().node_removed.connect(_on_node_removed)


# -------------------------------------------------------------------------
# Core API (mirrors SDK wyrd_bridge.gd)
# -------------------------------------------------------------------------

func query(persona_id: String, user_input: String = "") -> String:
	if not enabled:
		return ""
	var body := {
		"persona_id": persona_id,
		"user_input": user_input if user_input != "" else "What is the current world state?",
		"use_turn_loop": false,
	}
	var result := await _post("/query", body)
	if result.has("error"):
		query_failed.emit(persona_id, result["error"])
		return ""
	var context := str(result.get("response", ""))
	query_completed.emit(persona_id, context)
	return context


func push_observation(title: String, summary: String) -> bool:
	if not enabled:
		return false
	var payload := {"title": title, "summary": summary}
	var result := await _post("/event", {"event_type": "observation", "payload": payload})
	var ok: bool = result.get("ok", false)
	event_pushed.emit("observation", ok)
	return ok


func push_fact(subject_id: String, key: String, value: String) -> bool:
	if not enabled:
		return false
	var payload := {"subject_id": subject_id, "key": key, "value": value}
	var result := await _post("/event", {"event_type": "fact", "payload": payload})
	var ok: bool = result.get("ok", false)
	event_pushed.emit("fact", ok)
	return ok


func health_check() -> bool:
	var result := await _get("/health")
	return result.get("status", "") == "ok"


# -------------------------------------------------------------------------
# Game integration features
# -------------------------------------------------------------------------

## Sync the current scene name as a Yggdrasil location.
func sync_scene_location() -> bool:
	if not enabled:
		return false
	var scene_name := get_tree().current_scene.name if get_tree().current_scene else "unknown"
	var location_id := scene_location_map.get(scene_name, normalize_persona_id(scene_name))
	return await push_fact("__world__", "current_location", location_id)


## Sync all registered WyrdEntity nodes in the scene.
func sync_all_entities() -> int:
	var count := 0
	for entity in _entity_registry:
		if is_instance_valid(entity) and entity.has_method("sync"):
			await entity.sync()
			count += 1
	return count


## Register a WyrdEntity node (called automatically from WyrdEntity._ready).
func register_entity(entity: Node) -> void:
	if entity not in _entity_registry:
		_entity_registry.append(entity)


## Unregister a WyrdEntity node.
func unregister_entity(entity: Node) -> void:
	_entity_registry.erase(entity)


## Get all currently registered entity persona IDs.
func get_registered_personas() -> PackedStringArray:
	var ids := PackedStringArray()
	for entity in _entity_registry:
		if is_instance_valid(entity) and entity.has_method("get_persona_id"):
			ids.append(entity.get_persona_id())
	return ids


## Push a custom world event. Use for game events that should be recorded.
## Example: await WyrdBridge.push_world_event("combat_start", {"attacker": "sigrid", "target": "goblin"})
func push_world_event(event_name: String, data: Dictionary = {}) -> bool:
	var summary_parts := PackedStringArray()
	for key in data:
		summary_parts.append("%s=%s" % [key, str(data[key])])
	var summary := summary_parts.join(", ") if summary_parts.size() > 0 else event_name
	return await push_observation(event_name, summary)


# -------------------------------------------------------------------------
# Normalize helper (same algorithm as SDK)
# -------------------------------------------------------------------------

static func normalize_persona_id(name: String) -> String:
	var result := name.to_lower()
	var out := PackedByteArray()
	var last_was_underscore := false
	for i in result.length():
		var c := result.unicode_at(i)
		if (c >= 97 and c <= 122) or (c >= 48 and c <= 57) or c == 95:
			out.append(c)
			last_was_underscore = (c == 95)
		elif not last_was_underscore:
			out.append(95)
			last_was_underscore = true
	var s := out.get_string_from_utf8().strip_edges().lstrip("_").rstrip("_")
	return s.substr(0, 64) if s.length() > 64 else s


# -------------------------------------------------------------------------
# Automatic entity tracking
# -------------------------------------------------------------------------

func _on_node_added(node: Node) -> void:
	if node.get_script() and str(node.get_script().resource_path).ends_with("wyrd_entity.gd"):
		register_entity(node)


func _on_node_removed(node: Node) -> void:
	unregister_entity(node)


# -------------------------------------------------------------------------
# HTTP helpers
# -------------------------------------------------------------------------

func _post(path: String, body_dict: Dictionary) -> Dictionary:
	var http := HTTPRequest.new()
	add_child(http)
	var headers := PackedStringArray(["Content-Type: application/json"])
	var err := http.request(
		_base_url + path, headers, HTTPClient.METHOD_POST, JSON.stringify(body_dict)
	)
	if err != OK:
		http.queue_free()
		return {"error": "HTTPRequest error %d" % err}
	var response: Array = await http.request_completed
	http.queue_free()
	return _parse_response(response)


func _get(path: String) -> Dictionary:
	var http := HTTPRequest.new()
	add_child(http)
	var err := http.request(_base_url + path)
	if err != OK:
		http.queue_free()
		return {"error": "HTTPRequest error %d" % err}
	var response: Array = await http.request_completed
	http.queue_free()
	return _parse_response(response)


func _parse_response(response: Array) -> Dictionary:
	if response[0] != HTTPRequest.RESULT_SUCCESS:
		return {"error": "HTTP request failed (result=%d)" % response[0]}
	var text: String = response[3].get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text)
	if parsed == null:
		return {"error": "Invalid JSON response"}
	var code: int = response[1]
	if code < 200 or code >= 300:
		var msg: String = (parsed as Dictionary).get("error", "HTTP %d" % code) if parsed is Dictionary else "HTTP %d" % code
		return {"error": msg}
	return parsed as Dictionary
