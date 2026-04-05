/// @file wyrd_bridge.gml
/// WyrdForge — WYRD Protocol integration for GameMaker Studio 2 (Phase 11C).
///
/// This script package provides GML functions for connecting GameMaker games
/// to a running WyrdHTTPServer. Uses GMS2's built-in http_request() functions.
///
/// Setup:
///   1. Add this script to your GameMaker project.
///   2. Call wyrd_init("localhost", 8765) at game start (e.g., in a persistent controller object's Create event).
///   3. Handle http_request responses in your Async HTTP event.
///   4. Use wyrd_query(), wyrd_push_observation(), wyrd_push_fact() in any object.
///
/// Async HTTP event pattern (add to your controller object's Async HTTP event):
///   if (wyrd_handle_response(async_load)) {
///       var result = wyrd_get_last_result();
///       // use result.response or result.ok
///   }
///
/// Example usage:
///   wyrd_init("localhost", 8765);
///   wyrd_query("sigrid", "What is happening?", wyrd_callback_sigrid);
///   wyrd_push_observation("Dragon appears", "A dragon flew over the village.");
///   wyrd_push_fact("sigrid", "location", "village");

// -------------------------------------------------------------------------
// Internal state (stored in global variables)
// -------------------------------------------------------------------------

/// Initialize WyrdForge. Call once at game start.
/// @param {string} _host  — WyrdHTTPServer hostname
/// @param {real}   _port  — WyrdHTTPServer port
function wyrd_init(_host, _port) {
    global.__wyrd_host = _host;
    global.__wyrd_port = _port;
    global.__wyrd_base_url = "http://" + string(_host) + ":" + string(_port);
    global.__wyrd_enabled = true;
    global.__wyrd_pending = ds_map_create();   // request_id → callback
    global.__wyrd_last_result = undefined;
    show_debug_message("[WyrdForge] Initialized. Server: " + global.__wyrd_base_url);
}

/// Enable or disable WyrdForge.
/// @param {bool} _enabled
function wyrd_set_enabled(_enabled) {
    global.__wyrd_enabled = _enabled;
}

/// Check if WyrdForge is initialized and enabled.
/// @returns {bool}
function wyrd_is_ready() {
    return (variable_global_exists("__wyrd_enabled") and global.__wyrd_enabled);
}

// -------------------------------------------------------------------------
// Request builders (pure, testable)
// -------------------------------------------------------------------------

/// Build a /query request body JSON string.
/// @param {string} _persona_id
/// @param {string} _user_input
/// @returns {string}  JSON string
function wyrd_build_query_body(_persona_id, _user_input) {
    var _query = (_user_input != "") ? _user_input : "What is the current world state?";
    var _body = json_stringify({
        "persona_id": _persona_id,
        "user_input": _query,
        "use_turn_loop": false
    });
    return _body;
}

/// Build an /event observation body JSON string.
/// @param {string} _title
/// @param {string} _summary
/// @returns {string}  JSON string
function wyrd_build_observation_body(_title, _summary) {
    return json_stringify({
        "event_type": "observation",
        "payload": {
            "title": _title,
            "summary": _summary
        }
    });
}

/// Build an /event fact body JSON string.
/// @param {string} _subject_id
/// @param {string} _key
/// @param {string} _value
/// @returns {string}  JSON string
function wyrd_build_fact_body(_subject_id, _key, _value) {
    return json_stringify({
        "event_type": "fact",
        "payload": {
            "subject_id": _subject_id,
            "key": _key,
            "value": _value
        }
    });
}

/// Normalize a character name to a WYRD persona_id.
/// @param {string} _name
/// @returns {string}
function wyrd_normalize_persona_id(_name) {
    var _result = string_lower(_name);
    var _out = "";
    var _last_under = false;
    var _len = string_length(_result);
    for (var _i = 1; _i <= _len; _i++) {
        var _c = string_char_at(_result, _i);
        var _ord = ord(_c);
        if ((_ord >= 97 and _ord <= 122) or (_ord >= 48 and _ord <= 57) or _ord == 95) {
            _out += _c;
            _last_under = (_ord == 95);
        } else if (!_last_under) {
            _out += "_";
            _last_under = true;
        }
    }
    // Strip leading/trailing underscores
    while (string_pos("_", _out) == 1 and string_length(_out) > 0) {
        _out = string_delete(_out, 1, 1);
    }
    while (string_length(_out) > 0 and string_char_at(_out, string_length(_out)) == "_") {
        _out = string_delete(_out, string_length(_out), 1);
    }
    // Truncate
    if (string_length(_out) > 64) {
        _out = string_copy(_out, 1, 64);
    }
    return _out;
}

// -------------------------------------------------------------------------
// Async HTTP request dispatch
// -------------------------------------------------------------------------

/// Send a /query request to WyrdHTTPServer.
/// @param {string} _persona_id
/// @param {string} _user_input
/// @param {function|undefined} _callback  — called with result struct on completion
/// @returns {real}  request_id
function wyrd_query(_persona_id, _user_input, _callback) {
    if (!wyrd_is_ready()) return -1;
    var _body = wyrd_build_query_body(_persona_id, _user_input);
    var _headers = ds_map_create();
    ds_map_set(_headers, "Content-Type", "application/json");
    var _req_id = http_request(
        global.__wyrd_base_url + "/query",
        "POST",
        _headers,
        _body
    );
    ds_map_destroy(_headers);
    if (!is_undefined(_callback)) {
        ds_map_set(global.__wyrd_pending, _req_id, _callback);
    }
    return _req_id;
}

/// Send a push_observation event.
/// @param {string} _title
/// @param {string} _summary
/// @param {function|undefined} _callback
/// @returns {real}  request_id
function wyrd_push_observation(_title, _summary, _callback) {
    if (!wyrd_is_ready()) return -1;
    var _body = wyrd_build_observation_body(_title, _summary);
    var _headers = ds_map_create();
    ds_map_set(_headers, "Content-Type", "application/json");
    var _req_id = http_request(
        global.__wyrd_base_url + "/event",
        "POST",
        _headers,
        _body
    );
    ds_map_destroy(_headers);
    if (!is_undefined(_callback)) {
        ds_map_set(global.__wyrd_pending, _req_id, _callback);
    }
    return _req_id;
}

/// Send a push_fact event.
/// @param {string} _subject_id
/// @param {string} _key
/// @param {string} _value
/// @param {function|undefined} _callback
/// @returns {real}  request_id
function wyrd_push_fact(_subject_id, _key, _value, _callback) {
    if (!wyrd_is_ready()) return -1;
    var _body = wyrd_build_fact_body(_subject_id, _key, _value);
    var _headers = ds_map_create();
    ds_map_set(_headers, "Content-Type", "application/json");
    var _req_id = http_request(
        global.__wyrd_base_url + "/event",
        "POST",
        _headers,
        _body
    );
    ds_map_destroy(_headers);
    if (!is_undefined(_callback)) {
        ds_map_set(global.__wyrd_pending, _req_id, _callback);
    }
    return _req_id;
}

/// Send a health check request.
/// @param {function|undefined} _callback
/// @returns {real}  request_id
function wyrd_health_check(_callback) {
    if (!wyrd_is_ready()) return -1;
    var _req_id = http_get(global.__wyrd_base_url + "/health");
    if (!is_undefined(_callback)) {
        ds_map_set(global.__wyrd_pending, _req_id, _callback);
    }
    return _req_id;
}

// -------------------------------------------------------------------------
// Async HTTP event handler
// -------------------------------------------------------------------------

/// Call this in your Async HTTP event to dispatch WyrdForge callbacks.
/// @param {id.DsMap} _async_load  — the async_load ds_map from Async HTTP event
/// @returns {bool}  true if this was a WyrdForge request
function wyrd_handle_response(_async_load) {
    if (!variable_global_exists("__wyrd_pending")) return false;
    var _req_id = _async_load[? "id"];
    if (!ds_map_exists(global.__wyrd_pending, _req_id)) return false;

    var _callback = ds_map_find_value(global.__wyrd_pending, _req_id);
    ds_map_delete(global.__wyrd_pending, _req_id);

    var _status = _async_load[? "status"];
    var _result = undefined;

    if (_status == 0) {  // complete
        var _http_status = _async_load[? "http_status"];
        var _body = _async_load[? "result"];
        if (_http_status >= 200 and _http_status < 300) {
            _result = json_parse(_body);
        } else {
            _result = { "error": "HTTP " + string(_http_status) };
        }
    } else {
        _result = { "error": "Request failed (status=" + string(_status) + ")" };
    }

    global.__wyrd_last_result = _result;
    if (!is_undefined(_callback)) {
        script_execute(_callback, _result);
    }
    return true;
}

/// Get the last response result struct.
/// @returns {struct|undefined}
function wyrd_get_last_result() {
    return global.__wyrd_last_result ?? undefined;
}

/// Clean up WyrdForge resources. Call on game end.
function wyrd_cleanup() {
    if (variable_global_exists("__wyrd_pending")) {
        ds_map_destroy(global.__wyrd_pending);
    }
}
