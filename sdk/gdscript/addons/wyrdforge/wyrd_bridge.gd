extends Node
## WyrdBridge — Autoload singleton for WYRD Protocol integration.
##
## Add this as an autoload via the WyrdForge plugin or manually:
##   Project → Project Settings → Autoload → wyrd_bridge.gd as "WyrdBridge"
##
## Usage:
##   var context = await WyrdBridge.query("sigrid", "What is happening?")
##   await WyrdBridge.push_observation("Storm", "A storm hit the coast.")
##   await WyrdBridge.push_fact("sigrid", "role", "seer")
##   await WyrdBridge.sync_node(my_character_node)

## Emitted when a query completes. context_text is the WYRD world context block.
signal query_completed(persona_id: String, context_text: String)
## Emitted when a query fails.
signal query_failed(persona_id: String, error: String)
## Emitted when an event push completes.
signal event_pushed(event_type: String, ok: bool)

## WyrdHTTPServer hostname.
@export var host: String = "localhost"
## WyrdHTTPServer port.
@export var port: int = 8765
## Whether WyrdForge integration is active.
@export var enabled: bool = true

var _base_url: String

func _ready() -> void:
	_base_url = "http://%s:%d" % [host, port]


# -------------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------------

## Query WYRD world context for a persona.
## Returns the context string, or empty string on failure.
## Emits query_completed or query_failed.
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


## Push an observation event to WYRD memory.
func push_observation(title: String, summary: String) -> bool:
	if not enabled:
		return false
	var payload := {"title": title, "summary": summary}
	var result := await _post("/event", {"event_type": "observation", "payload": payload})
	var ok: bool = result.get("ok", false)
	event_pushed.emit("observation", ok)
	return ok


## Push a canonical fact to WYRD memory.
func push_fact(subject_id: String, key: String, value: String) -> bool:
	if not enabled:
		return false
	var payload := {"subject_id": subject_id, "key": key, "value": value}
	var result := await _post("/event", {"event_type": "fact", "payload": payload})
	var ok: bool = result.get("ok", false)
	event_pushed.emit("fact", ok)
	return ok


## Check WyrdHTTPServer health. Returns true if server is reachable.
func health_check() -> bool:
	var result := await _get("/health")
	return result.get("status", "") == "ok"


## Sync a game node (character) to WYRD. Reads node's name property.
## Optionally reads metadata keys: wyrd_class, wyrd_description, wyrd_location.
func sync_node(node: Node) -> bool:
	if not enabled or node == null:
		return false
	var persona_id := normalize_persona_id(node.name)
	var client := WyrdClient.new(_base_url)
	add_child(client)

	var ok := true
	ok = ok and await push_fact(persona_id, "name", node.name)

	if node.has_meta("wyrd_class"):
		ok = ok and await push_fact(persona_id, "class", str(node.get_meta("wyrd_class")))
	if node.has_meta("wyrd_description"):
		ok = ok and await push_fact(persona_id, "description", str(node.get_meta("wyrd_description")))
	if node.has_meta("wyrd_location"):
		ok = ok and await push_fact(persona_id, "location", str(node.get_meta("wyrd_location")))

	client.queue_free()
	return ok


## Normalize a node/character name to a WYRD persona_id.
## Lowercases, replaces non-alphanumeric with underscore, collapses, truncates.
static func normalize_persona_id(name: String) -> String:
	var result := name.to_lower()
	var out := PackedByteArray()
	var last_was_underscore := false
	for i in result.length():
		var c := result.unicode_at(i)
		if (c >= 97 and c <= 122) or (c >= 48 and c <= 57) or c == 95:  # a-z, 0-9, _
			out.append(c)
			last_was_underscore = (c == 95)
		elif not last_was_underscore:
			out.append(95)  # _
			last_was_underscore = true
	var s := out.get_string_from_utf8().strip_edges().lstrip("_").rstrip("_")
	if s.length() > 64:
		s = s.substr(0, 64)
	return s


# -------------------------------------------------------------------------
# Internal HTTP helpers
# -------------------------------------------------------------------------

func _post(path: String, body_dict: Dictionary) -> Dictionary:
	var http := HTTPRequest.new()
	add_child(http)
	var headers := PackedStringArray(["Content-Type: application/json"])
	var body_json := JSON.stringify(body_dict)
	var err := http.request(
		_base_url + path,
		headers,
		HTTPClient.METHOD_POST,
		body_json
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
	# response = [result, response_code, headers, body]
	var result_code: int = response[0]
	var http_code: int = response[1]
	var body: PackedByteArray = response[3]

	if result_code != HTTPRequest.RESULT_SUCCESS:
		return {"error": "HTTP request failed (result=%d)" % result_code}

	var text := body.get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text)
	if parsed == null:
		return {"error": "Invalid JSON response"}

	if http_code < 200 or http_code >= 300:
		var msg: String = (parsed as Dictionary).get("error", "HTTP %d" % http_code) if parsed is Dictionary else "HTTP %d" % http_code
		return {"error": msg}

	return parsed as Dictionary
