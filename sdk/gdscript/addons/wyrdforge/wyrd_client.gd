extends Node
## WyrdClient — lightweight HTTP client node for ad-hoc WYRD requests.
##
## Used internally by WyrdBridge and can be used standalone.
## Freed automatically after use if created via WyrdBridge.sync_node().
##
## Usage:
##   var client := WyrdClient.new("http://localhost:8765")
##   add_child(client)
##   var result = await client.query("sigrid", "Hello")
##   client.queue_free()

var _base_url: String

func _init(base_url: String = "http://localhost:8765") -> void:
	_base_url = base_url


func query(persona_id: String, user_input: String = "") -> Dictionary:
	return await _post("/query", {
		"persona_id": persona_id,
		"user_input": user_input if user_input != "" else "What is the current world state?",
		"use_turn_loop": false,
	})


func push_event(event_type: String, payload: Dictionary) -> Dictionary:
	return await _post("/event", {"event_type": event_type, "payload": payload})


func health() -> Dictionary:
	return await _get("/health")


func _post(path: String, body_dict: Dictionary) -> Dictionary:
	var http := HTTPRequest.new()
	add_child(http)
	var headers := PackedStringArray(["Content-Type: application/json"])
	var err := http.request(
		_base_url + path,
		headers,
		HTTPClient.METHOD_POST,
		JSON.stringify(body_dict)
	)
	if err != OK:
		http.queue_free()
		return {"error": "HTTPRequest error %d" % err}
	var response: Array = await http.request_completed
	http.queue_free()
	return _parse(response)


func _get(path: String) -> Dictionary:
	var http := HTTPRequest.new()
	add_child(http)
	var err := http.request(_base_url + path)
	if err != OK:
		http.queue_free()
		return {"error": "HTTPRequest error %d" % err}
	var response: Array = await http.request_completed
	http.queue_free()
	return _parse(response)


func _parse(response: Array) -> Dictionary:
	if response[0] != HTTPRequest.RESULT_SUCCESS:
		return {"error": "HTTP request failed (result=%d)" % response[0]}
	var text: String = response[3].get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text)
	if parsed == null:
		return {"error": "Invalid JSON"}
	var code: int = response[1]
	if code < 200 or code >= 300:
		var msg: String = (parsed as Dictionary).get("error", "HTTP %d" % code) if parsed is Dictionary else "HTTP %d" % code
		return {"error": msg}
	return parsed as Dictionary
