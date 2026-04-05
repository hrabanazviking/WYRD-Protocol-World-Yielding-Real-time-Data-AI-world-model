--- wyrdforge.lua — WyrdForge HTTP client module for Defold (Phase 11F).
--
-- Provides the full WYRD Protocol Lua API for Defold games.
-- Uses Defold's built-in http and json modules for async HTTP.
-- Requires the wyrdforge native extension (src/wyrdforge.cpp) to be loaded.
--
-- SETUP
--   1. Add the wyrdforge extension to your game.project dependencies.
--   2. Require this module in any script that needs WYRD.
--
-- QUICK START
--   local wyrd = require("wyrdforge.lua.wyrdforge")
--
--   function init(self)
--       wyrd.init("localhost", 8765)
--   end
--
--   function on_input(self, action_id, action)
--       if action_id == hash("talk") and action.pressed then
--           wyrd.query("sigrid", "What do the runes say?", function(ok, response, err)
--               if ok then
--                   msg.post("/npc#dialogue", "show_text", {text = response})
--               else
--                   print("[WyrdForge] Query error:", err)
--               end
--           end)
--       end
--   end
--
-- API REFERENCE
--   wyrd.init(host, port)
--   wyrd.set_enabled(bool)
--   wyrd.query(persona_id, user_input, callback)
--   wyrd.push_observation(title, summary, callback)
--   wyrd.push_fact(subject_id, key, value, callback)
--   wyrd.health(callback)

local M = {}

-- ---------------------------------------------------------------------------
-- Internal state
-- ---------------------------------------------------------------------------

local _host    = "localhost"
local _port    = 8765
local _enabled = true

-- ---------------------------------------------------------------------------
-- Private helpers
-- ---------------------------------------------------------------------------

local function _base_url()
    return string.format("http://%s:%d", _host, _port)
end

--- Fire a POST request to WyrdHTTPServer.
-- @param path        string     e.g. "/query" or "/event"
-- @param body_json   string     pre-built JSON body string
-- @param on_raw      function   called with (ok, decoded_table_or_nil, err_string_or_nil)
local function _post(path, body_json, on_raw)
    if not _enabled then return end
    local headers = {["Content-Type"] = "application/json"}
    http.request(
        _base_url() .. path,
        "POST",
        function(self, id, response)
            if response.status >= 200 and response.status < 300 then
                local ok, data = pcall(json.decode, response.response)
                if ok and data ~= nil then
                    if on_raw then on_raw(true, data, nil) end
                else
                    if on_raw then on_raw(false, nil, "WyrdForge: invalid JSON response") end
                end
            else
                local msg = string.format("WyrdForge: HTTP %d", response.status)
                if on_raw then on_raw(false, nil, msg) end
            end
        end,
        headers,
        body_json
    )
end

-- ---------------------------------------------------------------------------
-- Public API
-- ---------------------------------------------------------------------------

--- Initialize WyrdForge. Call once from your game script's init() function.
-- @param host  string   WyrdHTTPServer hostname (default: "localhost")
-- @param port  number   WyrdHTTPServer port (default: 8765)
function M.init(host, port)
    _host    = host or "localhost"
    _port    = port or 8765
    _enabled = true
end

--- Enable or disable WyrdForge without changing host/port.
-- @param enabled boolean
function M.set_enabled(enabled)
    _enabled = enabled == true
end

--- Query WYRD world context for a character.
-- Fires an async HTTP POST to /query. The callback runs when the response arrives.
-- @param persona_id  string    WYRD persona ID (e.g. "sigrid")
-- @param user_input  string    Player message or query text. Empty string = default context.
-- @param callback    function  function(ok, response_text, error_msg)
--                              ok            boolean — true on success
--                              response_text string  — the character context string
--                              error_msg     string  — error message on failure, nil on success
function M.query(persona_id, user_input, callback)
    local body = wyrdforge.build_query_body(persona_id or "", user_input or "")
    _post("/query", body, function(ok, data, err)
        if ok then
            if callback then callback(true, data.response or "", nil) end
        else
            if callback then callback(false, nil, err) end
        end
    end)
end

--- Push a world event observation to WYRD memory.
-- Fires an async HTTP POST to /event. Use to record things that happened in the game world.
-- @param title     string    Short title for the observation (e.g. "Dragon appears")
-- @param summary   string    Description of what happened
-- @param callback  function  function(ok, data, error_msg) — optional
function M.push_observation(title, summary, callback)
    local payload = json.encode({title = title or "", summary = summary or ""})
    local body = wyrdforge.build_event_body("observation", payload)
    _post("/event", body, callback)
end

--- Push a canonical world fact about an entity to WYRD.
-- Fires an async HTTP POST to /event. Use to record persistent facts.
-- @param subject_id  string    Entity or character ID this fact is about
-- @param key         string    Fact key (e.g. "location", "role", "alignment")
-- @param value       string    Fact value
-- @param callback    function  function(ok, data, error_msg) — optional
function M.push_fact(subject_id, key, value, callback)
    local payload = json.encode({
        subject_id = subject_id or "",
        key        = key or "",
        value      = value or "",
    })
    local body = wyrdforge.build_event_body("fact", payload)
    _post("/event", body, callback)
end

--- Check whether WyrdHTTPServer is reachable and healthy.
-- @param callback  function  function(ok, data, error_msg)
--                            ok   boolean — true if server responds with status="ok"
function M.health(callback)
    if not _enabled then return end
    http.request(
        _base_url() .. "/health",
        "GET",
        function(self, id, response)
            if response.status == 200 then
                local ok, data = pcall(json.decode, response.response)
                if ok and data ~= nil then
                    if callback then callback(data.status == "ok", data, nil) end
                else
                    if callback then callback(false, nil, "WyrdForge: invalid JSON on health check") end
                end
            else
                local msg = string.format("WyrdForge: health check HTTP %d", response.status)
                if callback then callback(false, nil, msg) end
            end
        end,
        {},
        nil
    )
end

return M
