--[[
  WyrdConfig.lua — WyrdForge Roblox integration configuration (Phase 12C).

  Require this module and override fields before calling WyrdBridge:Init().

  Example:
    local WyrdConfig = require(script.Parent.WyrdConfig)
    WyrdConfig.Host    = "192.168.1.50"
    WyrdConfig.Port    = 8765
    WyrdConfig.Enabled = true

    local WyrdBridge = require(script.Parent.WyrdBridge)
    WyrdBridge:Init(WyrdConfig)
--]]

local WyrdConfig = {}

-- WyrdHTTPServer hostname or IP.
-- In Roblox Studio you can use localhost for testing if Studio HttpService
-- is set to allow external requests. In published games, use a public server.
WyrdConfig.Host = "localhost"

-- WyrdHTTPServer port (default 8765).
WyrdConfig.Port = 8765

-- Request timeout in seconds (Roblox HttpService max is 30).
WyrdConfig.Timeout = 10

-- Master on/off switch. Set false to disable all HTTP calls (no-op mode).
WyrdConfig.Enabled = true

-- If true, WyrdBridge:Query() returns a fallback string instead of erroring
-- when WyrdHTTPServer is unreachable.
WyrdConfig.SilentOnError = true

-- Fallback response when WyrdHTTPServer is unreachable.
WyrdConfig.FallbackResponse = "The spirits whisper nothing of note."

return WyrdConfig
