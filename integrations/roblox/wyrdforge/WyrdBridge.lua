--[[
  WyrdBridge.lua — WyrdForge server-side bridge for Roblox (Phase 12C).

  IMPORTANT: This ModuleScript must run in a SERVER Script, not a LocalScript.
  Roblox HttpService is only available on the server. Clients must use
  WyrdClientBridge.lua + WyrdRemoteSetup.lua to reach this module via RemoteEvents.

  SETUP:
    1. Start WyrdHTTPServer on a machine reachable from Roblox servers:
         python -m wyrdforge.server --port 8765
       For testing in Studio, enable Studio Access to API Services in Game Settings.
    2. Place this ModuleScript and WyrdMapper inside your ServerScriptService.
    3. In a Script (not LocalScript):
         local WyrdConfig = require(script.Parent.WyrdConfig)
         WyrdConfig.Host = "your.server.ip"
         local WyrdBridge = require(script.Parent.WyrdBridge)
         WyrdBridge:Init(WyrdConfig)
    4. In NPC dialogue Scripts:
         local reply = WyrdBridge:Query("sigrid_npc", playerMessage)
         npcTextLabel.Text = reply

  API:
    WyrdBridge:Init(config?)          — initialise with optional config override
    WyrdBridge:Query(personaId, input) → string (blocking coroutine yield)
    WyrdBridge:PushObservation(title, summary)   — fire-and-forget
    WyrdBridge:PushFact(subjectId, key, value)   — fire-and-forget
    WyrdBridge:SyncNpc(npcId, facts)             — fire-and-forget per fact
    WyrdBridge:Health()               → boolean
    WyrdBridge:GetLastError()         → string|nil
--]]

-- Roblox services (stubbed for testability — replace with game:GetService() in-engine)
local HttpService
local ok, svc = pcall(function() return game:GetService("HttpService") end)
if ok then HttpService = svc end

local WyrdMapper = require(script.Parent.WyrdMapper)
local DEFAULT_CONFIG = require(script.Parent.WyrdConfig)

-- ---------------------------------------------------------------------------
-- Module
-- ---------------------------------------------------------------------------

local WyrdBridge = {}
WyrdBridge.__index = WyrdBridge

-- Singleton state
local _config    = nil
local _lastError = nil

-- ---------------------------------------------------------------------------
-- Initialisation
-- ---------------------------------------------------------------------------

--- Initialise WyrdBridge with optional config table.
--- Merges provided fields over defaults. Safe to call multiple times.
function WyrdBridge:Init(config)
    _config = {}
    -- Copy defaults
    for k, v in pairs(DEFAULT_CONFIG) do _config[k] = v end
    -- Apply overrides
    if config then
        for k, v in pairs(config) do _config[k] = v end
    end

    if not HttpService then
        warn("[WyrdForge] HttpService not available — running in stub mode.")
    end

    print(string.format(
        "[WyrdForge] Initialised. host=%s port=%d enabled=%s",
        _config.Host, _config.Port, tostring(_config.Enabled)
    ))
end

-- Ensure init has been called (lazy default init)
local function ensureInit()
    if not _config then
        WyrdBridge:Init(nil)
    end
end

-- ---------------------------------------------------------------------------
-- Base URL
-- ---------------------------------------------------------------------------

local function baseUrl()
    return string.format("http://%s:%d", _config.Host, _config.Port)
end

-- ---------------------------------------------------------------------------
-- Internal HTTP
-- ---------------------------------------------------------------------------

--- POST body_json to path. Returns (ok: bool, body: string).
local function post(path, body_json)
    if not HttpService then
        return false, "HttpService unavailable"
    end

    local success, result = pcall(function()
        return HttpService:RequestAsync({
            Url    = baseUrl() .. path,
            Method = "POST",
            Headers = { ["Content-Type"] = "application/json" },
            Body   = body_json,
        })
    end)

    if not success then
        return false, tostring(result)
    end

    if result.StatusCode >= 200 and result.StatusCode < 300 then
        return true, result.Body
    end

    return false, "HTTP " .. tostring(result.StatusCode)
end

--- Fire-and-forget POST — errors captured in _lastError, not raised.
local function fireAndForget(path, body_json)
    -- Roblox: use task.spawn to avoid blocking the calling thread
    local spawnFn = (task and task.spawn) or coroutine.wrap
    spawnFn(function()
        local ok_, err = post(path, body_json)
        if not ok_ then
            _lastError = err
            warn("[WyrdForge] fire-and-forget error on " .. path .. ": " .. tostring(err))
        end
    end)
    if spawnFn == coroutine.wrap then
        -- coroutine.wrap returns a function — call it
        -- (task.spawn calls it automatically)
    end
end

-- ---------------------------------------------------------------------------
-- Public API
-- ---------------------------------------------------------------------------

--- Query WYRD world context for a persona. Blocking (yields current thread).
--- @param personaId string  WYRD persona_id
--- @param input     string  Player message; empty → default world-state query
--- @return          string  Response text
function WyrdBridge:Query(personaId, input)
    ensureInit()
    if not _config.Enabled then
        return _config.FallbackResponse
    end

    local body = WyrdMapper.buildQueryBody(personaId, input)
    local ok_, responseBody = post("/query", body)

    if ok_ then
        return WyrdMapper.parseResponse(responseBody)
    end

    _lastError = responseBody
    if _config.SilentOnError then
        return _config.FallbackResponse
    end
    error("[WyrdForge] Query failed: " .. tostring(responseBody))
end

--- Push an observation event. Fire-and-forget.
function WyrdBridge:PushObservation(title, summary)
    ensureInit()
    if not _config.Enabled then return end
    fireAndForget("/event", WyrdMapper.buildObservationBody(title, summary))
end

--- Push a single fact. Fire-and-forget.
function WyrdBridge:PushFact(subjectId, key, value)
    ensureInit()
    if not _config.Enabled then return end
    fireAndForget("/event", WyrdMapper.buildFactBody(subjectId, key, value))
end

--- Sync an NPC to WYRD by pushing all its facts. Fire-and-forget per fact.
--- @param npcId string  WYRD persona_id for the NPC
--- @param facts table   Array of {key=string, value=string} from WyrdMapper.toFacts()
function WyrdBridge:SyncNpc(npcId, facts)
    ensureInit()
    if not _config.Enabled then return end
    for _, fact in ipairs(facts) do
        self:PushFact(npcId, fact.key, fact.value)
    end
end

--- Check WyrdHTTPServer health. Blocking.
--- @return boolean  true if /health returns 2xx
function WyrdBridge:Health()
    ensureInit()
    if not HttpService then return false end

    local success, result = pcall(function()
        return HttpService:RequestAsync({
            Url    = baseUrl() .. "/health",
            Method = "GET",
        })
    end)

    if not success then
        _lastError = tostring(result)
        return false
    end
    return result.StatusCode >= 200 and result.StatusCode < 300
end

--- Return the last error message from a failed or fire-and-forget call.
--- Returns nil if no error has occurred since Init.
function WyrdBridge:GetLastError()
    return _lastError
end

return WyrdBridge
